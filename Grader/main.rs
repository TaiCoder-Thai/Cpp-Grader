use actix_files as fs;
use actix_multipart::Multipart;
use actix_web::{web, App, HttpResponse, HttpServer, Responder};
use futures_util::StreamExt as _;
use once_cell::sync::Lazy;
use serde::Serialize;
use std::collections::HashMap;
use std::fs::File;
use std::io::Write;
use std::process::{Command, Stdio};
use std::sync::{Arc, Mutex};
use tera::{Context, Tera};

#[derive(Serialize, Clone)]
struct Problem {
    title: &'static str,
    description: &'static str,
    time_limit: f64,
    memory_limit_kb: u64,
    test_cases: Vec<(&'static str, &'static str)>,
}

static PROBLEMS: Lazy<HashMap<&'static str, Problem>> = Lazy::new(|| {
    let mut m = HashMap::new();
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

static SUBMISSION_LOCK: Lazy<Arc<Mutex<usize>>> = Lazy::new(|| Arc::new(Mutex::new(0)));

async fn home(tmpl: web::Data<Tera>) -> impl Responder {
    let mut ctx = Context::new();
    ctx.insert("problems", &*PROBLEMS);

    match tmpl.render("home.html", &ctx) {
        Ok(html) => HttpResponse::Ok().content_type("text/html").body(html),
        Err(e) => {
            eprintln!("Template render error: {e}");
            HttpResponse::InternalServerError().body("Template render error")
        }
    }
}

async fn problem_page(
    tmpl: web::Data<Tera>,
    path: web::Path<String>,
) -> impl Responder {
    let pid = path.into_inner();
    let mut ctx = Context::new();

    if let Some(prob) = PROBLEMS.get(pid.as_str()) {
        ctx.insert("problem", prob);
        ctx.insert("problem_id", &pid);
    } else {
        return HttpResponse::NotFound().body("Problem not found");
    }

    match tmpl.render("problem.html", &ctx) {
        Ok(html) => HttpResponse::Ok().content_type("text/html").body(html),
        Err(e) => {
            eprintln!("Template render error: {e}");
            HttpResponse::InternalServerError().body("Template render error")
        }
    }
}

#[derive(Serialize)]
struct TestResult {
    test_num: usize,
    status: String,
    passed: bool,
    time_sec: Option<f64>,
    memory_kb: u64,
}

#[derive(Serialize)]
struct SubmissionResponse {
    status: String,
    score: u32,
    test_results: Vec<TestResult>,
}

async fn submit(mut payload: Multipart) -> impl Responder {
    let mut code = String::new();
    let mut problem_id = String::new();

    while let Some(item) = payload.next().await {
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

    let prob = match PROBLEMS.get(problem_id.as_str()) {
        Some(p) => p,
        None => {
            return HttpResponse::BadRequest().json(SubmissionResponse {
                status: "❌ Problem not found".to_string(),
                score: 0,
                test_results: vec![],
            });
        }
    };

    let tmp_file = format!("/tmp/submission_{}.cpp", problem_id);
    {
        let mut f = File::create(&tmp_file).unwrap();
        f.write_all(code.as_bytes()).unwrap();
    }

    // Compile
    let exe_file = format!("/tmp/submission_{}.out", problem_id);
    let compile_status = Command::new("g++")
        .arg(&tmp_file)
        .arg("-O2")
        .arg("-std=c++17")
        .arg("-o")
        .arg(&exe_file)
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status();

    if compile_status.is_err() || !compile_status.unwrap().success() {
        return HttpResponse::Ok().json(SubmissionResponse {
            status: "❌ Compilation failed".to_string(),
            score: 0,
            test_results: vec![],
        });
    }

    // Run tests
    let mut total_score = 0;
    let mut results = vec![];

    for (i, (input, expected)) in prob.test_cases.iter().enumerate() {
        let output = Command::new(&exe_file)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .spawn()
            .and_then(|mut child| {
                if let Some(stdin) = child.stdin.as_mut() {
                    use std::io::Write;
                    stdin.write_all(input.as_bytes()).unwrap();
                }
                let output = child.wait_with_output().unwrap();
                Ok(output)
            });

        let mut result = TestResult {
            test_num: i + 1,
            status: "Error".to_string(),
            passed: false,
            time_sec: None,
            memory_kb: 0,
        };

        if let Ok(out) = output {
            let res = String::from_utf8_lossy(&out.stdout).trim().to_string();
            if res == expected.trim() {
                result.status = "Accepted".to_string();
                result.passed = true;
                total_score += 100 / prob.test_cases.len() as u32;
            } else {
                result.status = format!("Wrong Answer (got '{}')", res);
            }
        }

        results.push(result);
    }

    let response = SubmissionResponse {
        status: "✅ Finished".to_string(),
        score: total_score,
        test_results: results,
    };

    HttpResponse::Ok().json(response)
}

#[actix_web::main]
async fn main() -> std::io::Result<()> {
    let tera = Tera::new("templates/**/*").expect("Tera load failed");

    println!("🚀 Server running on http://0.0.0.0:8080");

    HttpServer::new(move || {
        App::new()
            .app_data(web::Data::new(tera.clone()))
            .service(fs::Files::new("/static", "./static").show_files_listing())
            .route("/", web::get().to(home))
            .route("/problem/{id}", web::get().to(problem_page))
            .route("/submit", web::post().to(submit))
    })
    .bind(("0.0.0.0", 8080))?
    .run()
    .await
}
