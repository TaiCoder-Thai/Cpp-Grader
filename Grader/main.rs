use actix_files as fs;
use actix_web::{web, App, HttpResponse, HttpServer, Responder};
use serde::Serialize;
use std::process::{Command, Stdio};
use sysinfo::{Pid, System, SystemExt, ProcessExt};
use tempfile::NamedTempFile;
use tera::{Tera, Context};
use once_cell::sync::Lazy;
use std::time::Instant;
use std::io::Write;

static TEMPLATES: Lazy<Tera> = Lazy::new(|| Tera::new("templates/**/*").expect("Failed to parse templates"));

#[derive(Clone, Serialize)]
struct Problem {
    title: &'static str,
    description: &'static str,
    time_limit: f64,
    memory_limit_kb: u64,
    test_cases: Vec<(&'static str, &'static str)>,
}

static PROBLEMS: Lazy<std::collections::HashMap<&'static str, Problem>> = Lazy::new(|| {
    let mut m = std::collections::HashMap::new();
    m.insert("1", Problem {
        title: "1. A + B",
        description: "Sum two numbers",
        time_limit: 1.0,
        memory_limit_kb: 10 * 1024,
        test_cases: vec![
            ("3 5\n", "8"),
            ("10 20\n", "30"),
            ("28282929 2828282\n", "31111211"),
        ],
    });
    m
});

#[derive(Serialize)]
struct TestResult {
    test_num: usize,
    status: String,
    passed: bool,
    time_sec: f64,
    memory_kb: u64,
}

#[derive(Serialize)]
struct SubmissionResponse {
    status: String,
    score: u32,
    test_results: Vec<TestResult>,
    compile_log: String,
    compile_time_sec: f64,
}

async fn home() -> impl Responder {
    let mut ctx = Context::new();
    ctx.insert("problems", &*PROBLEMS);
    let body = TEMPLATES.render("home.html", &ctx).unwrap();
    HttpResponse::Ok().content_type("text/html").body(body)
}

async fn problem_page(pid: web::Path<String>) -> impl Responder {
    let pid = pid.into_inner();
    if let Some(problem) = PROBLEMS.get(pid.as_str()) {
        let mut ctx = Context::new();
        ctx.insert("problem", problem);
        ctx.insert("problem_id", &pid);
        let body = TEMPLATES.render("problem.html", &ctx).unwrap();
        HttpResponse::Ok().content_type("text/html").body(body)
    } else {
        HttpResponse::NotFound().body("Problem not found")
    }
}

async fn submit(mut form: actix_multipart::Multipart) -> impl Responder {
    use futures_util::StreamExt as _;

    let mut code = String::new();
    let mut problem_id = String::new();

    while let Some(item) = form.next().await {
        let mut field = item.unwrap();
        let name = field.name().to_string();
        let mut data = Vec::new();
        while let Some(chunk) = field.next().await {
            data.extend_from_slice(&chunk.unwrap());
        }
        if name == "code" {
            code = String::from_utf8_lossy(&data).to_string();
        } else if name == "problem_id" {
            problem_id = String::from_utf8_lossy(&data).to_string();
        }
    }

    let problem = match PROBLEMS.get(problem_id.as_str()) {
        Some(p) => p,
        None => return HttpResponse::BadRequest().json(serde_json::json!({ "status": "Invalid problem" })),
    };

    let mut src_file = NamedTempFile::new().unwrap();
    write!(src_file, "{}", code).unwrap();
    let src_path = src_file.path().to_path_buf();

    let exe_file = NamedTempFile::new().unwrap();
    let exe_path = exe_file.path().to_path_buf();

    let start_compile = Instant::now();
    let compile_output = Command::new("g++")
        .arg("-std=c++17")
        .arg(&src_path)
        .arg("-O2")
        .arg("-o")
        .arg(&exe_path)
        .stderr(Stdio::piped())
        .output()
        .unwrap();
    let compile_time = start_compile.elapsed().as_secs_f64();

    if !compile_output.status.success() {
        return HttpResponse::Ok().json(SubmissionResponse {
            status: "Compilation Error".to_string(),
            score: 0,
            test_results: vec![],
            compile_log: String::from_utf8_lossy(&compile_output.stderr).to_string(),
            compile_time_sec: compile_time,
        });
    }

    let mut total_score = 0;
    let mut test_results = Vec::new();

    for (i, (input, expected)) in problem.test_cases.iter().enumerate() {
        let start = Instant::now();
        let mut child = Command::new(&exe_path)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .spawn()
            .unwrap();

        {
            let stdin = child.stdin.as_mut().unwrap();
            stdin.write_all(input.as_bytes()).unwrap();
        }

        let pid = child.id();
        let output = child.wait_with_output().unwrap();
        let duration = start.elapsed().as_secs_f64();

        let mut sys = System::new_all();
        sys.refresh_process(Pid::from(pid as usize));
        let memory = sys.process(Pid::from(pid as usize))
            .map(|p| p.memory())
            .unwrap_or(0);

        let passed = String::from_utf8_lossy(&output.stdout).trim() == *expected;
        let status = if passed { "Accepted" } else { "Wrong Answer" }.to_string();
        if passed { total_score += 100 / problem.test_cases.len() as u32; }

        test_results.push(TestResult {
            test_num: i + 1,
            status,
            passed,
            time_sec: duration,
            memory_kb: memory,
        });
    }

    HttpResponse::Ok().json(SubmissionResponse {
        status: "Finished".to_string(),
        score: total_score,
        test_results,
        compile_log: String::from_utf8_lossy(&compile_output.stderr).to_string(),
        compile_time_sec: compile_time,
    })
}

#[actix_web::main]
async fn main() -> std::io::Result<()> {
    let port: u16 = std::env::var("PORT").unwrap_or_else(|_| "8080".to_string()).parse().unwrap();
    println!("🚀 Server running on http://0.0.0.0:{}", port);

    HttpServer::new(|| {
        App::new()
            .route("/", web::get().to(home))
            .route("/problem/{pid}", web::get().to(problem_page))
            .route("/submit", web::post().to(submit))
            .service(fs::Files::new("/static", "static").show_files_listing())
    })
    .bind(("0.0.0.0", port))?
    .run()
    .await
}
