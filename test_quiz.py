import json
import os
import re
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
import http.cookiejar

from tests.ui_sources import index_source, app_source, combined_app_path

BASE = "http://127.0.0.1:8099"
ROOT = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(ROOT, "test_run.db")
ADMIN_PASSWORD = "testpass123"

passed = []
failed = []


def check(name, condition, detail=""):
    if condition:
        passed.append(name)
        print("  PASS  %s" % name)
    else:
        failed.append((name, detail))
        print("  FAIL  %s %s" % (name, detail))


def remove_db(path):
    for suffix in ("", "-wal", "-shm"):
        for _ in range(20):
            try:
                os.remove(path + suffix)
                break
            except FileNotFoundError:
                break
            except PermissionError:
                time.sleep(0.1)
        else:
            raise PermissionError("could not remove database file: %s" % (path + suffix))


def close_test_db_pool():
    module = sys.modules.get("db")
    if not module:
        return
    with module._pool_lock:
        connections = list(module._pool)
        module._pool.clear()
    for conn in connections:
        conn.close()


class Client:
    def __init__(self):
        self.base = BASE
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.jar)
        )
        self.csrf = None

    def request(self, method, path, body=None, headers=None, use_csrf=True, raw=False, binary=False):
        url = self.base + path
        data = None
        hdrs = {"Accept": "application/json"}
        if body is not None:
            data = json.dumps(body).encode()
            hdrs["Content-Type"] = "application/json"
        if use_csrf and self.csrf and method != "GET":
            hdrs["X-CSRF-Token"] = self.csrf
        if headers:
            hdrs.update(headers)
        req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
        if os.environ.get("QUIZ_TRACE"):
            print("    -> %s %s" % (method, path), flush=True)
        try:
            with self.opener.open(req) as resp:
                blob = resp.read()
                if binary:
                    return resp.status, blob, dict(resp.headers)
                text = blob.decode()
                if raw:
                    return resp.status, text, dict(resp.headers)
                return resp.status, (json.loads(text) if text else {}), dict(resp.headers)
        except urllib.error.HTTPError as exc:
            text = exc.read().decode()
            if raw:
                return exc.code, text, dict(exc.headers)
            try:
                return exc.code, json.loads(text) if text else {}, dict(exc.headers)
            except json.JSONDecodeError:
                return exc.code, {"raw": text}, dict(exc.headers)

    def get(self, path, **kw):
        return self.request("GET", path, **kw)

    def post(self, path, body=None, **kw):
        return self.request("POST", path, body if body is not None else {}, **kw)


def wait_for(base, attempts=60):
    for _ in range(attempts):
        try:
            with urllib.request.urlopen(base + "/healthz", timeout=1) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            time.sleep(0.25)
    return False


def start_server():
    remove_db(DB)
    env = dict(os.environ, QUIZ_DB=DB, ADMIN_PASSWORD=ADMIN_PASSWORD, PORT="8099")
    proc = subprocess.Popen(
        [sys.executable, "app.py"],
        cwd=ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if wait_for(BASE):
        return proc
    proc.kill()
    raise SystemExit("server did not start")


def main():
    proc = start_server()
    try:
        run_tests()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        close_test_db_pool()
        remove_db(DB)

    print("\n%d passed, %d failed" % (len(passed), len(failed)))
    for name, detail in failed:
        print("  FAILED: %s %s" % (name, detail))
    return 1 if failed else 0


def run_tests():
    from tests import cases_accounts, cases_auth_access, cases_database, cases_interface
    from tests import cases_questions, cases_quiz_progress

    sections = {}
    # The original end-to-end checks share seeded accounts and questions.
    # Keep one execution context and run feature-grouped sections in their
    # original order so those scenarios retain their dependencies.
    for module in (cases_auth_access, cases_accounts, cases_database, cases_questions,
                   cases_quiz_progress, cases_interface):
        sections.update(module.SECTIONS)

    context = dict(globals())
    context.update(admin=Client(), staff=Client(), guest=Client())
    for _, section_code in sorted(sections.items()):
        exec(compile(section_code, "<quiz end-to-end case>", "exec"), context)


if __name__ == "__main__":
    sys.exit(main())
