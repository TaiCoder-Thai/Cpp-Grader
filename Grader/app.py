import os
import json
import uuid
import time
import shutil
import signal
import tempfile
import subprocess
import threading
from threading import BoundedSemaphore
from concurrent.futures import ThreadPoolExecutor
from flask import Flask, render_template, request, jsonify
import psutil

app = Flask(__name__)

# -----------------------------
# CONFIG
# -----------------------------
PROBLEMS_DIR = "problems"
MAX_CONCURRENT_SUBMISSIONS = 3
WORKER_POOL_SIZE = 3

submission_semaphore = BoundedSemaphore(MAX_CONCURRENT_SUBMISSIONS)
executor = ThreadPoolExecutor(max_workers=WORKER_POOL_SIZE)

# -----------------------------
# LOAD PROBLEMS META ON START
# -----------------------------
def load_all_problems():
    problems = {}
    for folder in os.listdir(PROBLEMS_DIR):
        folder_path = os.path.join(PROBLEMS_DIR, folder)
        meta_path = os.path.join(folder_path, "meta.json")
        if os.path.isdir(folder_path) and os.path.exists(meta_path):
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
            meta["folder"] = folder_path
            problems[meta["id"]] = meta
    return problems

problems = load_all_problems()

# -----------------------------
# HELPER: Run code with limits
# -----------------------------
def run_with_limits(executable_path, input_file, time_limit, memory_limit_kb):
    peak_kb = 0
    killed_for_mem = False
    timeout_flag = False

    popen_kwargs = dict(stdin=open(input_file, "r"), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if os.name == "posix":
        popen_kwargs["preexec_fn"] = os.setsid
    else:
        popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP

    proc = subprocess.Popen(executable_path, **popen_kwargs)

    def monitor():
        nonlocal peak_kb, killed_for_mem
        try:
            p = psutil.Process(proc.pid)
        except psutil.NoSuchProcess:
            return
        try:
            while proc.poll() is None:
                try:
                    mem = p.memory_info().rss // 1024
                except psutil.NoSuchProcess:
                    break
                if mem > peak_kb:
                    peak_kb = mem
                if memory_limit_kb and mem > memory_limit_kb:
                    try:
                        for child in p.children(recursive=True):
                            child.kill()
                        p.kill()
                    except Exception:
                        pass
                    killed_for_mem = True
                    break
                time.sleep(0.05)
        except Exception:
            pass

    mon_thread = threading.Thread(target=monitor, daemon=True)
    mon_thread.start()

    try:
        stdout, stderr = proc.communicate(timeout=time_limit)
        elapsed = round(proc.cpu_times().user + proc.cpu_times().system, 3)
        return subprocess.CompletedProcess([executable_path], proc.returncode, stdout, stderr), peak_kb, elapsed, killed_for_mem, False
    except subprocess.TimeoutExpired:
        timeout_flag = True
        try:
            if os.name == "posix":
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            else:
                parent = psutil.Process(proc.pid)
                for child in parent.children(recursive=True):
                    child.kill()
                parent.kill()
        except Exception:
            pass
        fake = subprocess.CompletedProcess([executable_path], 1, stdout="", stderr="Time Limit Exceeded")
        return fake, peak_kb, time_limit, killed_for_mem, True
    except Exception as e:
        fake = subprocess.CompletedProcess([executable_path], 1, stdout="", stderr=str(e))
        return fake, peak_kb, 0, killed_for_mem, False

# -----------------------------
# HELPER: Load testcases (file paths only)
# -----------------------------
def load_testcases(problem):
    folder = problem["folder"]
    test_cases = []
    for i in range(1, problem["test_count"] + 1):
        input_file = os.path.join(folder, f"input{i}.txt")
        output_file = os.path.join(folder, f"output{i}.txt")
        test_cases.append({"input_file": input_file, "expected_file": output_file})
    return test_cases

# -----------------------------
# SUBMIT ROUTE
# -----------------------------
@app.route("/submit", methods=["POST"])
def submit():
    if psutil.virtual_memory().available < 200 * 1024 * 1024:
        return jsonify({"status": "Server busy, try later"}), 429

    if not submission_semaphore.acquire(blocking=False):
        return jsonify({"status": "Error", "error": "Server busy - too many concurrent submissions."}), 429

    tmp_dir = None
    try:
        code = request.form.get("code")
        uploaded_file = request.files.get("codefile")
        problem_id = request.form.get("problem_id", "1")
        language = request.form.get("language", "cpp").lower()  # kept but ignored

        if uploaded_file and uploaded_file.filename:
            code = uploaded_file.read().decode("utf-8")
        elif not code:
            return jsonify({"status": "Error", "error": "No code provided"})

        if problem_id not in problems:
            return jsonify({"status": "Error", "error": "Invalid problem ID"})

        problem = problems[problem_id]
        time_limit = problem.get("time_limit", 1.0)
        memory_limit = problem.get("memory_limit", 256)
        memory_limit_kb = memory_limit * 1024
        test_cases = load_testcases(problem)

        # --- Create temp folder ---
        tmp_dir = tempfile.mkdtemp(prefix="submission_")
        uid = uuid.uuid4().hex
        code_path = os.path.join(tmp_dir, f"solution_{uid}.cpp")
        exe_name = f"solution_{uid}.exe" if os.name == "nt" else f"solution_{uid}"
        exe_path = os.path.join(tmp_dir, exe_name)

        with open(code_path, "w", encoding="utf-8") as f:
            f.write(code)

        # --- Compile C++ ---
        start_compile = time.time()
        compile_cmd = ["g++", "-std=c++17", "-O2", code_path, "-o", exe_path]
        compile_result = subprocess.run(compile_cmd, capture_output=True, text=True)
        compile_time_sec = round(time.time() - start_compile, 3)
        compile_log = compile_result.stderr
        if compile_result.returncode != 0:
            return jsonify({"status": "Compilation Error",
                            "compile_log": compile_log,
                            "compile_time_sec": compile_time_sec})

        # --- Run test cases ---
        test_results = []
        for idx, case in enumerate(test_cases):
            run_result, memory_used_kb, elapsed_time, killed_mem, timed_out = run_with_limits(
                exe_path, case["input_file"], time_limit, memory_limit_kb
            )

            if timed_out:
                status = "Time Limit Exceeded"
                passed = False
            elif killed_mem:
                status = "Memory Limit Exceeded"
                passed = False
            elif run_result.returncode != 0:
                status = "Runtime Error"
                passed = False
            else:
                # Compare output line-by-line from files
                with open(case["expected_file"], "r", encoding="utf-8") as f:
                    expected_lines = [line.rstrip() for line in f]
                output_lines = run_result.stdout.splitlines()
                passed = (output_lines == expected_lines)
                status = "Passed" if passed else "Wrong Answer"

            test_results.append({
                "test_num": idx + 1,
                "status": status,
                "passed": passed,
                "time_sec": round(elapsed_time, 3),
                "memory_kb": memory_used_kb,
                "stdout_snippet": run_result.stdout[:200] if run_result.stdout else "",
                "stderr_snippet": run_result.stderr[:200] if run_result.stderr else ""
            })

        score = int(100 * sum(1 for t in test_results if t['passed']) / len(test_results))
        verdict = "✅ Accepted" if all(t['passed'] for t in test_results) else f"❌ Rejected - {sum(t['passed'] for t in test_results)}/{len(test_results)} tests passed"

        return jsonify({
            "status": verdict,
            "score": score,
            "test_results": test_results,
            "compile_log": compile_log,
            "compile_time_sec": compile_time_sec
        })

    finally:
        try:
            if tmp_dir and os.path.exists(tmp_dir):
                shutil.rmtree(tmp_dir)
        except Exception:
            pass
        submission_semaphore.release()


# -----------------------------
# Routes
# -----------------------------
@app.route("/")
def home():
    return render_template("home.html", problems=problems)

@app.route("/problem/<pid>")
def problem(pid):
    if pid not in problems:
        return "Problem not found", 404
    return render_template("problem.html", problem_id=pid, problem=problems[pid])


# -----------------------------
# MAIN
# -----------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, threaded=True)
