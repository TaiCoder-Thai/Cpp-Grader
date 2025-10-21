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
        "title": "1. Maximum Pair Sum with Index Constraint",
        "description": "Given an array of integers, find the maximum sum of any two numbers such that their indices differ by at least k.",
        "difficulty": "medium-hard",
        "input_format": "First line: two integers n and k (size of array and index difference constraint).\nSecond line: n integers a1, a2, ..., an.",
        "output_format": "A single integer - the maximum valid sum.",
        "constraints": "2 ≤ n ≤ 10^5, 1 ≤ k < n, -10^9 ≤ ai ≤ 10^9",
        "time_limit": 1.0,   
        "memory_limit": 128,
        "sample_input": "5 2\n1 2 3 4 5",
        "sample_output": "9",
        "test_cases": [
            {"input": "5 2\n1 2 3 4 5\n", "output": "8"},
            {"input": "6 3\n-1 -2 -3 -4 -5 -6\n", "output": "-5"},
            {"input": "4 1\n100 1 100 1\n", "output": "200"},
            {"input": "5 4\n1 2 3 4 5\n", "output": "6"},
            {"input": "10 5\n1 2 3 4 5 6 7 8 9 10\n", "output": "15"},
            {"input": "3 2\n10 20 30\n", "output": "40"},
            {"input": "7 3\n5 -1 4 -2 3 -3 2\n", "output": "8"},
            {"input": "8 2\n-10 -20 -30 40 50 -5 -15 25\n", "output": "75"},
            {"input": "9 4\n1 2 3 4 5 6 7 8 9\n", "output": "14"},
            {"input": "5 1\n0 0 0 0 0\n", "output": "0"}
        ]
    },
    "2": {
        "title": "2. Maximum Subarray Sum with One Deletion",
        "description": "Find the maximum sum of a subarray where you are allowed to delete at most one element.",
        "difficulty": "hard",
        "input_format": "First line: n (size of array)\nSecond line: n integers",
        "output_format": "A single integer - maximum sum achievable.",
        "constraints": "1 ≤ n ≤ 10^5, -10^9 ≤ ai ≤ 10^9",
        "time_limit": 1.0,   
        "memory_limit": 128,
        "sample_input": "5\n1 -2 0 3 -1",
        "sample_output": "4",
        "test_cases": [
            {"input": "5\n1 -2 0 3 -1\n", "output": "4"},
            {"input": "4\n-1 -1 -1 -1\n", "output": "-1"},
            {"input": "6\n1 2 3 -2 5 -3\n", "output": "11"},
            {"input": "5\n10 -5 10 -5 10\n", "output": "25"},
            {"input": "7\n-2 -1 -2 -3 -4 -5 -1\n", "output": "-1"},
            {"input": "8\n1 -2 3 4 -5 6 -1 2\n", "output": "14"},
            {"input": "3\n-1 -2 -3\n", "output": "-1"},
            {"input": "10\n5 -1 2 -1 3 -1 4 -1 5 -1\n", "output": "16"},
            {"input": "4\n1 -2 3 4\n", "output": "8"},
            {"input": "6\n-2 -3 4 -1 -2 1\n", "output": "4"}
        ]
    },
    "3": {
        "title": "3. Count Subarrays with Sum Divisible by K",
        "description": "Count the number of subarrays whose sum is divisible by a given integer k.",
        "difficulty": "hard",
        "input_format": "First line: n k\nSecond line: n integers",
        "output_format": "A single integer - number of valid subarrays",
        "constraints": "1 ≤ n ≤ 10^5, 1 ≤ k ≤ 10^5, -10^9 ≤ ai ≤ 10^9",
        "time_limit": 1.0,   
        "memory_limit": 64,
        "sample_input": "5 3\n1 2 3 4 1",
        "sample_output": "4",
        "test_cases": [
            {"input": "5 3\n1 2 3 4 1\n", "output": "4"},
            {"input": "4 2\n2 4 6 8\n", "output": "10"},
            {"input": "6 5\n1 2 3 4 5 6\n", "output": "6"},
            {"input": "3 1\n-1 2 -1\n", "output": "6"},
            {"input": "5 7\n7 7 7 7 7\n", "output": "15"},
            {"input": "8 4\n1 2 3 4 5 6 7 8\n", "output": "6"},
            {"input": "10 10\n1 2 3 4 5 6 7 8 9 10\n", "output": "6"},
            {"input": "5 5\n1 2 3 4 5\n", "output": "4"},
            {"input": "6 3\n3 3 3 3 3 3\n", "output": "21"},
            {"input": "7 2\n1 3 2 4 5 6 7\n", "output": "13"}
        ]
    },
    "4": {
        "title": "4. Longest Increasing Subsequence",
        "description": "Given an array, find the length of the longest strictly increasing subsequence.",
        "difficulty": "hard",
        "input_format": "First line: n\nSecond line: n integers",
        "output_format": "A single integer - length of the longest increasing subsequence",
        "constraints": "1 ≤ n ≤ 10^4, -10^9 ≤ ai ≤ 10^9",
        "time_limit": 1.0,   
        "memory_limit": 64,
        "sample_input": "6\n10 9 2 5 3 7",
        "sample_output": "3",
        "test_cases": [
            {"input": "6\n10 9 2 5 3 7\n", "output": "3"},
            {"input": "5\n1 2 3 4 5\n", "output": "5"},
            {"input": "5\n5 4 3 2 1\n", "output": "1"},
            {"input": "7\n3 1 4 1 5 9 2\n", "output": "4"},
            {"input": "4\n10 10 10 10\n", "output": "1"},
            {"input": "8\n0 8 4 12 2 10 6 14\n", "output": "4"},
            {"input": "6\n7 7 7 7 7 7\n", "output": "1"},
            {"input": "9\n1 3 2 4 3 5 4 6 5\n", "output": "5"},
            {"input": "5\n5 1 6 2 7\n", "output": "3"},
            {"input": "10\n10 22 9 33 21 50 41 60 80 1\n", "output": "6"}
        ]
    },
    "5": {
        "title": "5. Next Greater Element",
        "description": "For each element in the array, find the next element to the right that is greater. If none, output -1.",
        "difficulty": "medium-hard",
        "input_format": "First line: n\nSecond line: n integers",
        "output_format": "n integers separated by spaces",
        "constraints": "1 ≤ n ≤ 10^6, -10^9 ≤ ai ≤ 10^9",
        "time_limit": 1.0,   
        "memory_limit": 32,
        "sample_input": "4\n4 5 2 25",
        "sample_output": "5 25 25 -1",
        "test_cases": [
            {"input": "4\n4 5 2 25\n", "output": "5 25 25 -1"},
            {"input": "5\n1 2 3 4 5\n", "output": "2 3 4 5 -1"},
            {"input": "5\n5 4 3 2 1\n", "output": "-1 -1 -1 -1 -1"},
            {"input": "6\n3 2 1 5 4 6\n", "output": "5 5 5 6 6 -1"},
            {"input": "3\n10 10 10\n", "output": "-1 -1 -1"},
            {"input": "7\n1 3 2 4 5 3 2\n", "output": "3 4 4 5 -1 -1 -1"},
            {"input": "4\n7 8 1 4\n", "output": "8 -1 4 -1"},
            {"input": "8\n11 13 21 3 6 5 8 9\n", "output": "13 21 -1 6 8 8 9 -1"},
            {"input": "5\n6 4 5 2 3\n", "output": "-1 5 -1 3 -1"},
            {"input": "6\n2 1 5 6 3 4\n", "output": "5 5 6 -1 4 -1"}
        ]
    },
    "6": {
        "title": "6. Count Inversions",
        "description": "Count how many pairs (i, j) exist such that i < j and arr[i] > arr[j].",
        "difficulty": "hard",
        "input_format": "First line: n\nSecond line: n integers",
        "output_format": "A single integer - number of inversions",
        "constraints": "1 ≤ n ≤ 10^5, -10^9 ≤ ai ≤ 10^9",
        "time_limit": 1.0,   
        "memory_limit": 16,
        "sample_input": "5\n2 4 1 3 5",
        "sample_output": "3",
        "test_cases": [
            {"input": "5\n2 4 1 3 5\n", "output": "3"},
            {"input": "5\n1 2 3 4 5\n", "output": "0"},
            {"input": "5\n5 4 3 2 1\n", "output": "10"},
            {"input": "3\n3 1 2\n", "output": "2"},
            {"input": "4\n4 3 2 1\n", "output": "6"},
            {"input": "6\n1 6 3 2 5 4\n", "output": "6"},
            {"input": "4\n2 2 2 2\n", "output": "0"},
            {"input": "7\n7 6 5 4 3 2 1\n", "output": "21"},
            {"input": "3\n1 3 2\n", "output": "1"},
            {"input": "8\n8 4 2 1 7 5 3 6\n", "output": "15"}
        ]
    },
    "7": {
        "title": "7. Kadane's Maximum Subarray Sum",
        "description": "Find the maximum sum of any contiguous subarray.",
        "difficulty": "medium-hard",
        "input_format": "First line: n\nSecond line: n integers",
        "output_format": "A single integer - maximum subarray sum",
        "constraints": "1 ≤ n ≤ 10^6, -10^9 ≤ ai ≤ 10^9",
        "time_limit": 1.0,   
        "memory_limit": 128,
        "sample_input": "8\n-2 -3 4 -1 -2 1 5 -3",
        "sample_output": "7",
        "test_cases": [
            {"input": "8\n-2 -3 4 -1 -2 1 5 -3\n", "output": "7"},
            {"input": "5\n1 2 3 4 5\n", "output": "15"},
            {"input": "5\n-1 -2 -3 -4 -5\n", "output": "-1"},
            {"input": "6\n5 -3 5 -3 5 -3\n", "output": "9"},
            {"input": "4\n-2 1 -3 4\n", "output": "4"},
            {"input": "7\n1 -1 1 -1 1 -1 1\n", "output": "1"},
            {"input": "9\n-2 1 -3 4 -1 2 1 -5 4\n", "output": "6"},
            {"input": "3\n10 -5 10\n", "output": "15"},
            {"input": "5\n-5 -2 -3 -1 -4\n", "output": "-1"},
            {"input": "6\n3 -2 5 -1 7 -3\n", "output": "12"}
        ]
    },
    "8": {
        "title": "8. Matrix Transpose",
        "description": "Transpose a given r x c matrix.",
        "difficulty": "medium",
        "input_format": "First line: r c\nNext r lines: c integers",
        "output_format": "c lines of r integers each",
        "constraints": "1 ≤ r, c ≤ 100, -10^9 ≤ ai ≤ 10^9",
        "time_limit": 1.0,   
        "memory_limit": 64,
        "sample_input": "2 3\n1 2 3\n4 5 6",
        "sample_output": "1 4\n2 5\n3 6",
        "test_cases": [
            {"input": "2 3\n1 2 3\n4 5 6\n", "output": "1 4\n2 5\n3 6"},
            {"input": "3 2\n1 2\n3 4\n5 6\n", "output": "1 3 5\n2 4 6"},
            {"input": "1 4\n7 8 9 10\n", "output": "7\n8\n9\n10"},
            {"input": "3 3\n1 0 0\n0 1 0\n0 0 1\n", "output": "1 0 0\n0 1 0\n0 0 1"},
            {"input": "2 2\n5 10\n15 20\n", "output": "5 15\n10 20"},
            {"input": "4 1\n1\n2\n3\n4\n", "output": "1 2 3 4"},
            {"input": "2 4\n1 2 3 4\n5 6 7 8\n", "output": "1 5\n2 6\n3 7\n4 8"},
            {"input": "3 3\n9 8 7\n6 5 4\n3 2 1\n", "output": "9 6 3\n8 5 2\n7 4 1"},
            {"input": "2 2\n-1 -2\n-3 -4\n", "output": "-1 -3\n-2 -4"},
            {"input": "1 1\n42\n", "output": "42"}
        ]
    },
    "9": {
        "title": "9. Sliding Window Maximum",
        "description": "Given an array and window size k, find the maximum in each sliding window of size k.",
        "difficulty": "hard",
        "input_format": "First line: n k\nSecond line: n integers",
        "output_format": "n-k+1 integers separated by spaces",
        "constraints": "1 ≤ n ≤ 10^5, 1 ≤ k ≤ n, -10^9 ≤ ai ≤ 10^9",
        "time_limit": 1.0,   
        "memory_limit": 128,
        "sample_input": "8 3\n1 3 -1 -3 5 3 6 7",
        "sample_output": "3 3 5 5 6 7",
        "test_cases": [
            {"input": "8 3\n1 3 -1 -3 5 3 6 7\n", "output": "3 3 5 5 6 7"},
            {"input": "5 2\n1 2 3 4 5\n", "output": "2 3 4 5"},
            {"input": "5 1\n5 4 3 2 1\n", "output": "5 4 3 2 1"},
            {"input": "6 3\n2 1 5 3 4 6\n", "output": "5 5 5 6"},
            {"input": "4 4\n1 2 3 4\n", "output": "4"},
            {"input": "7 3\n1 3 -1 -3 5 3 6\n", "output": "3 3 5 5 6"},
            {"input": "3 2\n-1 -2 -3\n", "output": "-1 -2"},
            {"input": "8 4\n1 3 1 2 0 5 1 2\n", "output": "3 3 5 5 5"},
            {"input": "5 5\n1 2 3 4 5\n", "output": "5"},
            {"input": "6 3\n1 2 3 4 5 6\n", "output": "3 4 5 6"}
        ]
    },
    "10": {
        "title": "10. Longest Palindromic Substring",
        "description": "Given a string, find the length of the longest substring which is a palindrome.",
        "difficulty": "hard",
        "input_format": "Single line: string s",
        "output_format": "Single integer - length of the longest palindromic substring",
        "constraints": "1 ≤ |s| ≤ 10^5, s consists of lowercase letters",
        "time_limit": 1.0,   
        "memory_limit": 64,
        "sample_input": "babad",
        "sample_output": "3",
        "test_cases": [
            {"input": "babad\n", "output": "3"},
            {"input": "cbbd\n", "output": "2"},
            {"input": "a\n", "output": "1"},
            {"input": "ac\n", "output": "1"},
            {"input": "racecar\n", "output": "7"},
            {"input": "aaaa\n", "output": "4"},
            {"input": "abcde\n", "output": "1"},
            {"input": "abccba\n", "output": "6"},
            {"input": "abacdfgdcaba\n", "output": "3"},
            {"input": "forgeeksskeegfor\n", "output": "10"}
        ]
    },
    "11": {
       "title": "11. A + B",
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
    # Try to acquire a slot for concurrent submissions
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

        # Parse limits (strict)
        try:
            time_limit = float(request.form.get('time_limit', 1) or 1)
            if math.isnan(time_limit) or time_limit <= 0:
                time_limit = 1.0
        except Exception:
            time_limit = 1.0

        try:
            memory_limit = int(request.form.get('memory_limit', 256) or 256)  # in MB
            if memory_limit <= 0:
                memory_limit = 256
        except Exception:
            memory_limit = 256

        memory_limit_kb = int(memory_limit * 1024)

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
