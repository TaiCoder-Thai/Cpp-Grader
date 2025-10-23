from flask import Flask, render_template, request, jsonify
import os
import subprocess
import time
import signal, psutil, threading
import uuid
import tempfile
import shutil
import errno
import functools
import math
from threading import BoundedSemaphore

app = Flask(__name__)

problems = {
    "1": {
        "title": "1. A + B",
        "description": "Given two integers A and B, find their sum.",
        "difficulty": "easy",
        "input_format": "Single line: two integers A and B",
        "output_format": "Single integer - the sum of A and B",
        "constraints": "-10^9 ≤ A, B ≤ 10^9",
        "time_limit": 0.67,
        "memory_limit": 10,
        "sample_input": "3 5",
        "sample_output": "8",
        "test_cases": [
            {"input": "3 5\n", "output": "8"},
            {"input": "10 20\n", "output": "30"},
            {"input": "-10 5\n", "output": "-5"},
            {"input": "0 0\n", "output": "0"},
            {"input": "1000000000 1000000000\n", "output": "2000000000"},
            {"input": "-1000000000 -1000000000\n", "output": "-2000000000"},
            {"input": "123456789 987654321\n", "output": "1111111110"},
            {"input": "-987654321 -123456789\n", "output": "-1111111110"},
            {"input": "1 1\n", "output": "2"},
            {"input": "-1 -1\n", "output": "-2"}
        ]
    },
    "2": {
    "title": "2. A + B (Hard)",
    "description": "Given two integers A and B, find their sum.",
    "difficulty": "hard",
    "input_format": "Single line: two integers A and B",
    "output_format": "Single integer - the sum of A and B",
    "constraints": "-10^10000 ≤ A, B ≤ 10^10000",
    "time_limit": 0.1,
    "memory_limit": 2,
    "sample_input": "3 5",
    "sample_output": "8",
    "test_cases": [
        {"input": "1" + "0"*9999 + " 1", "output": "1" + "0"*9999 + "1"},
        {"input": "-1" + "0"*9999 + " -1", "output": "-1" + "0"*9999 + "1"},
        {"input": "9" + "9"*9998 + " 1", "output": "1" + "0"*9999},
        {"input": "-9" + "9"*9998 + " -1", "output": "-" + "1" + "0"*9999},
        {"input": "1234567890123456789012345678901234567890123456789012345678901234567890 9876543210987654321098765432109876543210987654321098765432109876543210", "output": "11111111101111111110111111111011111111101111111110111111111011111111100"},
        {"input": "999999999999999999999999999999999999999999999999999999999999999999 -999999999999999999999999999999999999999999999999999999999999999998", "output": "1"},
        {"input": "3141592653589793238462643383279502884197169399375105820974944592 2718281828459045235360287471352662497757247093699959574966967627", "output": "5859874482048838473822930854632165381954416493075065395941912219"},
        {"input": "-123456789123456789123456789123456789123456789123456789 -987654321987654321987654321987654321987654321987654321", "output": "-1111111111111111111111111111111111111111111111111110"},
        {"input": "5" + "0"*249 + " 5" + "0"*249, "output": "1" + "0"*250},
        {"input": "98765432109876543210987654321098765432109876543210987654321098765432109876543210 12345678901234567890123456789012345678901234567890123456789012345678901234567890", "output": "111111111011111111101111111110111111111011111111101111111110111111111101111111100"}
    ]
    }
}


MAX_CONCURRENT_SUBMISSIONS = 5
submission_semaphore = BoundedSemaphore(MAX_CONCURRENT_SUBMISSIONS)

def run_with_limits(executable_path, input_data, time_limit, memory_limit_kb):
    with submission_semaphore:
        start = time.time()
        popen_kwargs = dict(stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        if os.name == "posix":
            popen_kwargs["preexec_fn"] = os.setsid
        else:
            popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP

        proc = subprocess.Popen([executable_path], **popen_kwargs)

        peak_kb = 0
        killed_for_mem = False
        timeout_flag = False

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
                        # kill whole tree
                        try:
                            for child in p.children(recursive=True):
                                try:
                                    child.kill()
                                except Exception:
                                    pass
                            p.kill()
                        except Exception:
                            pass
                        killed_for_mem = True
                        break
                    time.sleep(0.05)
            except Exception:
                # monitor should be best-effort; never raise to main thread
                pass

        mon_thread = threading.Thread(target=monitor, daemon=True)
        mon_thread.start()

        try:
            stdout, stderr = proc.communicate(input=input_data, timeout=time_limit)
            elapsed = round(time.time() - start, 3)
            # Build CompletedProcess-like object for compatibility
            cp = subprocess.CompletedProcess([executable_path], proc.returncode, stdout, stderr)
            return cp, peak_kb, elapsed, killed_for_mem, False
        except subprocess.TimeoutExpired:
            timeout_flag = True
            # kill process tree
            try:
                if os.name == "posix":
                    # kill process group
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                else:
                    # Windows: use psutil to kill tree
                    parent = psutil.Process(proc.pid)
                    for child in parent.children(recursive=True):
                        try:
                            child.kill()
                        except Exception:
                            pass
                    try:
                        parent.kill()
                    except Exception:
                        pass
            except Exception:
                pass
            elapsed = round(time.time() - start, 3)
            fake = subprocess.CompletedProcess([executable_path], 1, stdout="", stderr="Time Limit Exceeded")
            return fake, peak_kb, elapsed, killed_for_mem, True
        except Exception as e:
            # generic error
            elapsed = round(time.time() - start, 3)
            fake = subprocess.CompletedProcess([executable_path], 1, stdout="", stderr=str(e))
            return fake, peak_kb, elapsed, killed_for_mem, False

# -------------------------
# Stronger / safer submit route
# -------------------------
@app.route('/submit', methods=['POST'])
def submit():
    if psutil.virtual_memory().available < 350*1024*1024:
        return jsonify({"status": "Server busy, try later"}), 429

    if not submission_semaphore.acquire(blocking=False):
        return jsonify({"status": "Error", "error": "Server busy - too many concurrent submissions. Try again shortly."}), 429

    tmp_dir = None
    try:
        code = request.form.get('code')
        uploaded_file = request.files.get('codefile')

        if uploaded_file and uploaded_file.filename:
            code = uploaded_file.read().decode('utf-8')
        elif not code:
            return jsonify({"status": "Error", "error": "No code provided"})

        problem_id = request.form.get('problem_id', '1')
        if problem_id not in problems:
            return jsonify({"status": "Error", "error": "Invalid problem ID"})

        problem = problems[problem_id]

        # Get the problem-specific limits
        time_limit = problem.get("time_limit", 1.0)         # default 1s if not specified
        memory_limit = problem.get("memory_limit", 256)     # default 256 MB
        memory_limit_kb = memory_limit * 1024

        # Get the test cases
        test_cases = problem.get('test_cases', [])


        # Create isolated temp dir for this submission
        tmp_dir = tempfile.mkdtemp(prefix="submission_")
        uid = uuid.uuid4().hex
        cpp_path = os.path.join(tmp_dir, f"solution_{uid}.cpp")
        exe_name = f"solution_{uid}.exe" if os.name == "nt" else f"solution_{uid}"
        exe_path = os.path.join(tmp_dir, exe_name)

        with open(cpp_path, 'w', encoding='utf-8') as f:
            f.write(code)

        # Compile inside temp dir
        start_compile = time.time()
        compile_cmd = ["g++", "-std=c++17", "-O2", cpp_path, "-o", exe_path]
        compile_result = subprocess.run(compile_cmd, capture_output=True, text=True)
        compile_time_sec = round(time.time() - start_compile, 3)

        if compile_result.returncode != 0:
            # Clean up compile artifacts (we will in finally too)
            return jsonify({
                "status": "Compilation Error",
                "compile_log": compile_result.stderr,
                "compile_time_sec": compile_time_sec
            })

        # Run tests (each test uses its own process and monitor)
        test_results = []
        for idx, case in enumerate(test_cases):
            # Run the program with per-test memory/time limits
            run_result, memory_used_kb, elapsed_time, killed_for_mem, timed_out = run_with_limits(
                exe_path, case['input'], time_limit, memory_limit_kb
            )

            # Strict (byte-for-byte) comparison
            if timed_out:
                status = "Time Limit Exceeded"
                passed = False
            elif killed_for_mem:
                status = "Memory Limit Exceeded"
                passed = False
            elif run_result.returncode != 0:
                # Return code nonzero: runtime error. Provide stderr for debugging.
                status = "Runtime Error"
                passed = False
            else:
                output = run_result.stdout
                expected = case['output']
                passed = (output == expected)
                status = "Passed" if passed else "Wrong Answer"

            # Optionally include stderr for runtime error debugging (but be careful exposing it publicly)
            test_results.append({
                "test_num": idx + 1,
                "status": status,
                "passed": passed,
                "time_sec": round(elapsed_time, 3),
                "memory_kb": memory_used_kb,
                "stdout_snippet": run_result.stdout[:200] if run_result.stdout else "",
                "stderr_snippet": run_result.stderr[:200] if run_result.stderr else ""
            })

        score = int(100 * sum(1 for t in test_results if t['passed']) / len(test_results)) if test_results else 0
        passed_count = sum(1 for t in test_results if t['passed'])
        total_tests = len(test_results)
        verdict = "✅ Accepted" if passed_count == total_tests and total_tests > 0 else f"❌ Rejected - {passed_count}/{total_tests} tests passed"

        return jsonify({
            "status": verdict,
            "score": score,
            "test_results": test_results,
            "compile_log": compile_result.stderr,
            "compile_time_sec": compile_time_sec
        })

    except Exception as e:
        return jsonify({"status": "Error", "error": str(e)}), 500

    finally:
        # Cleanup temporary directory and release slot
        try:
            if tmp_dir and os.path.exists(tmp_dir):
                shutil.rmtree(tmp_dir)
        except Exception:
            pass
        submission_semaphore.release()
    
# -------------------------
# Routes
# -------------------------
@app.route('/')
def home():
    return render_template('home.html', problems=problems)

@app.route('/problem/<pid>')
def problem(pid):
    if pid not in problems:
        return "Problem not found", 404
    return render_template('problem.html', problem_id=pid, problem=problems[pid])


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, threaded=True)








