use actix_files::Files;
use actix_web::{web, App, HttpResponse, HttpServer, Responder};
use lazy_static::lazy_static;
use serde::Serialize;
use std::collections::HashMap;
use std::process::{Command, Stdio};
use std::time::Instant;
use tera::{Context, Tera};
use tempfile::NamedTempFile;
use std::io::Write;

#[derive(Serialize, Clone)]
struct Problem {
    title: &'static str,
    description: &'static str,
    time_limit: f64,
    memory_limit: usize,
    difficulty: &'static str,
    input_format: &'static str,
    output_format: &'static str,
    constraints: &'static str,
    sample_input: &'static str,
    sample_output: &'static str,
    test_cases: Vec<(&'static str, &'static str)>,
}

lazy_static! {
    static ref PROBLEMS: HashMap<&'static str, Problem> = {
        let mut m = HashMap::new();
        m.insert("1", Problem {
            title: "1. A + B",
            description: "Read two integers A and B, then print their sum.",
            time_limit: 1.0,
            memory_limit: 16,
            difficulty: "easy",
            input_format: "Two integers A and B separated by a space.",
            output_format: "A single integer — the sum of A and B.",
            constraints: "1 ≤ A, B ≤ 10^9",
            sample_input: "3 5",
            sample_output: "8",
            test_cases: vec![
                ("3 5\n", "8"),
                ("10 20\n", "30"),
                ("28282929 2828282\n", "31111211"),
            ],
        });
        m
    };
    static ref TEMPLATES: Tera = {
        let mut tera = Tera::new("templates/**/*").unwrap();
        tera.autoescape_on(vec!["html"]);
        tera
    };
}

async fn home() -> impl Responder {
    let mut ctx = Context::new();
    ctx.insert("problems", &*PROBLEMS);
    let body = TEMPLATES.render("home.html", &ctx).unwrap();
    HttpResponse::Ok().content_type("text/html").body(body)
}

async fn problem_page(web::Path(pid): web::Path<String>) -> impl Responder {
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

#[derive(Serialize)]
struct TestResult {
    test_num: usize,
    status: String,
    passed: bool,
    time_sec: Option<f64>,
    memory_kb: usize,
}

#[derive(Serialize)]
struct JsonResponse {
    status: String,
    compile_log: String,
    compile_time_sec: f64,
    score: usize,
    test_results: Vec<TestResult>,
}

async fn submit(form: actix_multipart::Multipart) -> impl Responder {
    use futures_util::stream::StreamExt as _;
    let mut code = String::new();
    let mut problem_id = String::new();

    let mut payload = form;
    while let Some(item) = payload.next().await {
        let mut field = item.unwrap();
        let name = field.name().to_string();
        let mut data = Vec::new();
        while let Some(chunk) = field.next().await {
            data.extend_from_slice(&chunk.unwrap());
        }
        if name == "code" {
            code = String::from_utf8(data).unwrap();
        } else if name == "problem_id" {
            problem_id = String::from_utf8(data).unwrap();
        }
    }

    let problem = match PROBLEMS.get(problem_id.as_str()) {
        Some(p) => p,
        None => return HttpResponse::BadRequest().json(serde_json::json!({ "error": "Invalid problem ID" })),
    };

    let src_file = NamedTempFile::new().unwrap();
    let src_path = src_file.path().with_extension("cpp");
    std::fs::write(&src_path, code).unwrap();

    let exe_path = src_path.with_extension("out");
    let start = Instant::now();
    let compile = Command::new("g++")
        .args(["-O2", "-std=c++17", src_path.to_str().unwrap(), "-o", exe_path.to_str().unwrap()])
        .stderr(Stdio::piped())
        .output()
        .unwrap();
    let compile_time_sec = start.elapsed().as_secs_f64();
    let compile_log = String::from_utf8_lossy(&compile.stderr).to_string();
    if !compile.status.success() {
        return HttpResponse::Ok().json(JsonResponse {
            status: "Compilation Failed".into(),
            compile_log,
            compile_time_sec,
            score: 0,
            test_results: vec![],
        });
    }

    let mut total_score = 0;
    let mut test_results = vec![];

    for (i, (input, expected)) in problem.test_cases.iter().enumerate() {
        let run = Command::new(&exe_path)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .spawn();
        let mut child = match run {
            Ok(p) => p,
            Err(_) => continue,
        };
        {
            let mut stdin = child.stdin.take().unwrap();
            stdin.write_all(input.as_bytes()).unwrap();
        }

        let start = Instant::now();
        let output = child.wait_with_output().unwrap();
        let time_sec = start.elapsed().as_secs_f64();
        let actual = String::from_utf8_lossy(&output.stdout).trim().to_string();
        let expected_trimmed = expected.trim();

        let passed = actual == expected_trimmed;
        let status = if passed { "Accepted" } else { "Wrong Answer" }.to_string();
        if passed {
            total_score += 100 / problem.test_cases.len();
        }

        test_results.push(TestResult {
            test_num: i + 1,
            status,
            passed,
            time_sec: Some(time_sec),
            memory_kb: 0,
        });
    }

    HttpResponse::Ok().json(JsonResponse {
        status: "Finished".into(),
        compile_log,
        compile_time_sec,
        score: total_score,
        test_results,
    })
}

#[actix_web::main]
async fn main() -> std::io::Result<()> {
    HttpServer::new(|| {
        App::new()
            .service(Files::new("/static", "./static"))
            .route("/", web::get().to(home))
            .route("/problem/{id}", web::get().to(problem_page))
            .route("/submit", web::post().to(submit))
    })
    .bind(("0.0.0.0", 8080))?
    .run()
    .await
}
