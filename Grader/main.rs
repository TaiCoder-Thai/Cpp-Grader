use actix_web::{web, App, HttpResponse, HttpServer, Responder};
use serde::Serialize;
use std::collections::HashMap;
use std::fs::File;
use std::io::Write;
use std::process::{Child, Command, Stdio};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};
use tempfile::tempdir;
use sysinfo::{Pid, ProcessExt, System, SystemExt};
use wait_timeout::ChildExt;

#[derive(Serialize)]
struct TestResult {
    test_num: usize,
    status: String,
    passed: bool,
    time_sec: f64,
    memory_kb: u64,
    stdout_snippet: String,
    stderr_snippet: String,
}

#[derive(Serialize)]
struct SubmissionResponse {
    status: String,
    score: u32,
    test_results: Vec<TestResult>,
    compile_log: String,
    compile_time_sec: f64,
}

struct Problem {
    title: &'static str,
    description: &'static str,
    time_limit: f64,
    memory_limit_kb: u64,
    test_cases: Vec<(&'static str, &'static str)>,
}

lazy_static::lazy_static! {
    static ref PROBLEMS: HashMap<&'static str, Problem> = {
        let mut m = HashMap::new();
        m.insert("1", Problem {
            title: "1. A + B",
            description: "Sum two numbers",
            time_limit: 0.67,
            memory_limit_kb: 10 * 1024,
            test_cases: vec![
                ("3 5\n", "8"),
                ("10 20\n", "30"),
                ("28282929 2828282\n", "31111211"),
            ],
        });
        m
    };
}

const MAX_CONCURRENT_SUBMISSIONS: usize = 3;
static SUBMISSION_SEMAPHORE: once_cell::sync::Lazy<Arc<Mutex<usize>>> =
    once_cell::sync::Lazy::new(|| Arc::new(Mutex::new(MAX_CONCURRENT_SUBMISSIONS)));

fn normalize_whitespace(s: &str) -> String {
    s.split_whitespace().collect::<Vec<_>>().join(" ")
}

async fn submit(form: web::Form<HashMap<String, String>>) -> impl Responder {
    let mut sem = SUBMISSION_SEMAPHORE.lock().unwrap();
    if *sem == 0 {
        return HttpResponse::TooManyRequests().json("Server busy, try later");
    }
    *sem -= 1;
    drop(sem);

    let tmp_dir = match tempdir() {
        Ok(t) => t,
        Err(e) => {
            let mut sem = SUBMISSION_SEMAPHORE.lock().unwrap();
            *sem += 1;
            return HttpResponse::InternalServerError().json(format!("tempdir error: {}", e));
        }
    };

    let code = form.get("code").cloned().unwrap_or_default();
    let problem_id = form.get("problem_id").cloned().unwrap_or_else(|| "1".to_string());

    if !PROBLEMS.contains_key(problem_id.as_str()) {
        let mut sem = SUBMISSION_SEMAPHORE.lock().unwrap();
        *sem += 1;
        return HttpResponse::BadRequest().json("Invalid problem ID");
    }

    let problem = PROBLEMS.get(problem_id.as_str()).unwrap();
    let code_path = tmp_dir.path().join("solution.cpp");
    let exe_path = tmp_dir.path().join("solution_exe");

    if let Err(e) = (|| -> Result<(), std::io::Error> {
        let mut f = File::create(&code_path)?;
        f.write_all(code.as_bytes())?;
        Ok(())
    })() {
        let mut sem = SUBMISSION_SEMAPHORE.lock().unwrap();
        *sem += 1;
        return HttpResponse::InternalServerError().json(format!("write code error: {}", e));
    }

    let start_compile = Instant::now();
    let compile_output = match Command::new("g++")
        .arg("-std=c++17")
        .arg("-O2")
        .arg(&code_path)
        .arg("-o")
        .arg(&exe_path)
        .output()
    {
        Ok(o) => o,
        Err(e) => {
            let mut sem = SUBMISSION_SEMAPHORE.lock().unwrap();
            *sem += 1;
            return HttpResponse::InternalServerError().json(format!("compile spawn error: {}", e));
        }
    };
    let compile_time = start_compile.elapsed().as_secs_f64();

    if !compile_output.status.success() {
        let compile_log = String::from_utf8_lossy(&compile_output.stderr).to_string();
        let mut sem = SUBMISSION_SEMAPHORE.lock().unwrap();
        *sem += 1;
        return HttpResponse::Ok().json(SubmissionResponse {
            status: "Compilation Error".into(),
            score: 0,
            test_results: vec![],
            compile_log,
            compile_time_sec: compile_time,
        });
    }

    let mut test_results = Vec::new();
    let mut passed_count = 0usize;

    for (i, (input, expected)) in problem.test_cases.iter().enumerate() {
        let start_time = Instant::now();
        let mut child = match Command::new(&exe_path)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
        {
            Ok(c) => c,
            Err(e) => {
                let mut sem = SUBMISSION_SEMAPHORE.lock().unwrap();
                *sem += 1;
                return HttpResponse::InternalServerError().json(format!("spawn error: {}", e));
            }
        };

        if let Some(mut stdin) = child.stdin.take() {
            if let Err(e) = stdin.write_all(input.as_bytes()) {
                let _ = child.kill();
                let _ = child.wait();
                let mut sem = SUBMISSION_SEMAPHORE.lock().unwrap();
                *sem += 1;
                return HttpResponse::InternalServerError().json(format!("write input error: {}", e));
            }
        }

        let timeout = Duration::from_secs_f64(problem.time_limit);
        let timed_out = match child.wait_timeout(timeout) {
            Ok(Some(status)) => {
                !status.success()
            }
            Ok(None) => {
                let _ = child.kill();
                let _ = child.wait();
                true
            }
            Err(e) => {
                let _ = child.kill();
                let _ = child.wait();
                let mut sem = SUBMISSION_SEMAPHORE.lock().unwrap();
                *sem += 1;
                return HttpResponse::InternalServerError().json(format!("wait_timeout error: {}", e));
            }
        };

        let elapsed = start_time.elapsed().as_secs_f64();
        let output = match child.wait_with_output() {
            Ok(o) => o,
            Err(e) => {
                let mut sem = SUBMISSION_SEMAPHORE.lock().unwrap();
                *sem += 1;
                return HttpResponse::InternalServerError().json(format!("wait_with_output error: {}", e));
            }
        };

        let stdout_str = String::from_utf8_lossy(&output.stdout).to_string();
        let stderr_str = String::from_utf8_lossy(&output.stderr).to_string();

        let mut sys = System::new_all();
        sys.refresh_processes();
        let memory_used_kb = sys
            .process(Pid::from(child.id() as usize))
            .map(|p| p.memory())
            .unwrap_or(0);

        let passed = normalize_whitespace(&stdout_str) == normalize_whitespace(expected) && !timed_out;
        if passed {
            passed_count += 1;
        }

        test_results.push(TestResult {
            test_num: i + 1,
            status: if timed_out {
                "Time Limit Exceeded".into()
            } else if !passed {
                "Wrong Answer".into()
            } else {
                "Passed".into()
            },
            passed,
            time_sec: elapsed,
            memory_kb: memory_used_kb,
            stdout_snippet: stdout_str.chars().take(200).collect(),
            stderr_snippet: stderr_str.chars().take(200).collect(),
        });
    }

    let total_tests = test_results.len();
    let score = if total_tests > 0 {
        (100 * passed_count / total_tests) as u32
    } else {
        0
    };
    let verdict = if passed_count == total_tests && total_tests > 0 {
        "✅ Accepted".into()
    } else {
        format!("❌ Rejected - {}/{} tests passed", passed_count, total_tests)
    };

    let mut sem = SUBMISSION_SEMAPHORE.lock().unwrap();
    *sem += 1;

    HttpResponse::Ok().json(SubmissionResponse {
        status: verdict,
        score,
        test_results,
        compile_log: String::from_utf8_lossy(&compile_output.stderr).to_string(),
        compile_time_sec: compile_time,
    })
}

#[actix_web::main]
async fn main() -> std::io::Result<()> {
    let port: u16 = std::env::var("PORT")
        .unwrap_or_else(|_| "5000".to_string())
        .parse()
        .unwrap_or(5000);

    HttpServer::new(|| App::new().route("/submit", web::post().to(submit)))
        .bind(("0.0.0.0", port))?
        .run()
        .await
}
