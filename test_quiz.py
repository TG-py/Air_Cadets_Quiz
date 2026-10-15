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
    admin = Client()
    staff = Client()
    guest = Client()

    print("\n[1] anonymous access")
    status, payload, _ = admin.get("/api/auth/me")
    check("me returns 200 for guests", status == 200, str(status))
    check("guest has no user", payload.get("user") is None, str(payload.get("user")))
    check("guest gets csrf token", bool(payload.get("csrf")))
    admin.csrf = payload["csrf"]
    check("bank is empty", payload["counts"]["approved"] == 0, str(payload["counts"]))

    status, payload, _ = guest.get("/api/auth/me")
    guest.csrf = payload["csrf"]

    print("\n[2] login security")
    status, payload, _ = admin.post(
        "/api/auth/login", {"username": "admin", "password": "wrong"}
    )
    check("bad password rejected", status == 401, str(status))
    status, payload, _ = admin.post("/api/auth/login", {"username": "admin", "password": ADMIN_PASSWORD})
    check("admin can log in", status == 200 and payload["user"]["role"] == "admin", str(payload))
    admin.csrf = payload["csrf"]

    fresh = Client()
    status, payload, _ = fresh.get("/api/auth/me")
    fresh.csrf = payload["csrf"]
    status, payload, _ = fresh.post(
        "/api/auth/login",
        {"username": "admin", "password": ADMIN_PASSWORD},
        use_csrf=False,
    )
    check("csrf header required", status == 403, str(status))
    status, payload, _ = fresh.post(
        "/api/auth/login",
        {"username": "admin", "password": ADMIN_PASSWORD},
        use_csrf=False,
        headers={"X-CSRF-Token": "bogus-token"},
    )
    check("bad csrf rejected", status == 403, str(status))

    print("\n[3] submission requires every field")
    full = {
        "question_text": "What is the RAF motto?",
        "answer_text": "Per Ardua ad Astra",
        "topic": "Motto",
        "submitted_by": "Cdt Smith",
    }
    status, payload, _ = guest.post("/api/questions", full)
    check("complete submission accepted", status == 200, str(payload))
    check("submission starts as pending", payload.get("status") == "pending", str(payload))

    for field in ("submitted_by", "question_text", "answer_text", "topic"):
        partial = {k: v for k, v in full.items() if k != field}
        status, payload, _ = guest.post("/api/questions", partial)
        check("missing %s rejected" % field, status == 400, str(status))

    status, payload, _ = guest.post("/api/questions", dict(full, topic="   "))
    check("blank topic rejected", status == 400, str(status))
    status, payload, _ = guest.post("/api/questions", dict(full, submitted_by=" "))
    check("blank name rejected", status == 400, str(status))
    status, payload, _ = guest.post("/api/questions", dict(full, question_text="abc"))
    check("too-short question rejected", status == 400, str(status))
    status, payload, _ = guest.post("/api/questions", dict(full, answer_text=" "))
    check("blank answer rejected", status == 400, str(status))

    status, payload, _ = guest.post("/api/questions", dict(full, topic="Structure"))
    check("second submission accepted", status == 200, str(payload))
    status, payload, _ = guest.post("/api/questions", dict(full, topic="Doctrine"))
    check("third submission accepted", status == 200, str(payload))

    print("\n[4] topics available to guests for the dropdown")
    status, payload, _ = guest.get("/api/topics")
    check("guest can list topics", status == 200, str(status))
    check("pending topics offered too", "Motto" in payload.get("topics", []), str(payload.get("topics")))

    print("\n[5] admin reviews submissions")
    status, payload, _ = admin.get("/api/admin/pending")
    check("admin sees 3 pending", status == 200 and len(payload["questions"]) == 3, str(len(payload.get("questions", []))))
    pending_ids = [q["id"] for q in payload["questions"]]

    status, payload, _ = staff.get("/api/admin/pending")
    check("guest cannot see review queue", status == 401, str(status))

    status, payload, _ = admin.post("/api/admin/questions/%d/approve" % pending_ids[0], {})
    check("approve works", status == 200 and payload["counts"]["approved"] == 1, str(payload))
    status, payload, _ = admin.post("/api/admin/questions/%d/reject" % pending_ids[1], {"note": "duplicate"})
    check("reject works", status == 200 and payload["counts"]["rejected"] == 1, str(payload))
    status, payload, _ = admin.post("/api/admin/questions/%d/approve" % pending_ids[2], {})
    check("second approve works", payload["counts"]["approved"] == 2, str(payload))

    print("\n[6] staff account management")
    status, payload, _ = admin.post(
        "/api/admin/users",
        {"username": "nco1", "password": "ncopass123", "role": "staff", "display_name": "Cpl Jones"},
    )
    check("create staff account", status == 200, str(payload))
    status, payload, _ = admin.post(
        "/api/admin/users",
        {"username": "nco1", "password": "ncopass123", "role": "staff"},
    )
    check("duplicate username rejected", status == 409, str(status))
    status, payload, _ = admin.post(
        "/api/admin/users", {"username": "nco2", "password": "short", "role": "staff"}
    )
    check("short password rejected", status == 400, str(payload))
    status, payload, _ = admin.post(
        "/api/admin/users", {"username": "nco2", "password": "ncopass123", "role": "wizard"}
    )
    check("invalid role rejected", status == 400, str(status))

    status, payload, _ = staff.get("/api/auth/me")
    check("staff is anonymous before login", payload["user"] is None, str(payload))
    staff.csrf = payload["csrf"]
    status, payload, _ = staff.post(
        "/api/auth/login", {"username": "nco1", "password": "ncopass123"}
    )
    check("nco can log in", status == 200 and payload["user"]["role"] == "staff", str(payload))
    staff.csrf = payload["csrf"]

    print("\n[7] only staff can ask and record")
    status, payload, _ = staff.get("/api/quiz/next")
    check("staff can get a question", status == 200, str(payload))
    first_question = payload["question"]
    check("question has no cadet reference", "cadet" not in json.dumps(payload).lower(), str(payload))
    status, payload, _ = staff.post(
        "/api/attempts", {"question_id": first_question["id"], "correct": True}
    )
    check("staff records without naming anyone", status == 200, str(payload))
    check("answer counted for the squadron", payload["overall"]["asked"] == 1, str(payload["overall"]))

    status, payload, _ = staff.get("/api/admin/pending")
    check("staff blocked from review queue", status == 403, str(status))
    status, payload, _ = staff.get("/api/admin/users")
    check("staff blocked from user admin", status == 403, str(status))
    status, payload, _ = staff.post(
        "/api/admin/questions/%d/approve" % pending_ids[0], {}
    )
    check("staff cannot approve", status == 403, str(status))

    status, payload, _ = guest.get("/api/quiz/next")
    check("guest blocked from asking questions", status == 401, str(status))
    status, payload, _ = guest.post(
        "/api/attempts", {"question_id": first_question["id"], "correct": True}
    )
    check("guest blocked from recording answers", status == 401, str(status))
    status, payload, _ = guest.get("/api/cadets")
    check("cadet endpoint is gone", status == 404, str(status))
    status, payload, _ = guest.post("/api/cadets", {"name": "Sneaky"})
    check("cadet creation endpoint is gone", status == 404, str(status))

    print("\n[8] import and bank")
    csv_text = (
        "question,answer,topic\n"
        "What is the RAF motto?,Per Ardua ad Astra,Motto\n"
        "How many ranks in the RAF?,11,Ranks\n"
        "What does RAF stand for?,Royal Air Force,General\n"
        'What is a "formation"?,Units flying together,Doctrine\n'
    )
    status, payload, _ = admin.post("/api/admin/import", {"content": csv_text, "format": "csv"})
    check("csv import works", status == 200 and payload["added"] == 3, str(payload))
    check("csv import flags duplicate", payload["duplicates"] == 1, str(payload))
    status, payload, _ = admin.post("/api/admin/import", {"content": csv_text, "format": "csv"})
    check("re-import skips duplicates", payload["added"] == 0 and payload["duplicates"] == 4, str(payload))
    json_text = json.dumps(
        [
            {"question": "What is a Flight?", "answer": "A unit of 3 squadrons", "topic": "Structure"},
            {"question": "What is a Squadron?", "answer": "The RAF's middle unit", "topic": "Structure"},
        ]
    )
    status, payload, _ = admin.post("/api/admin/import", {"content": json_text, "format": "json"})
    check("json import works", payload["added"] == 2, str(payload))
    status, payload, _ = admin.post("/api/admin/import", {"content": "{bad json", "format": "json"})
    check("invalid json rejected", status == 400, str(status))
    status, payload, _ = admin.post("/api/admin/import", {"content": "only a question here", "format": "csv"})
    check("single column csv import works", status == 200, str(payload))
    status, payload, _ = staff.post(
        "/api/admin/import", {"content": "a,b,c", "format": "csv"}
    )
    check("staff cannot import", status == 403, str(status))

    print("\n[9] weighted selection across the squadron")
    total_q = admin.get("/api/questions/counts")[1]["counts"]["approved"]
    check("approved count is 8", total_q == 8, str(total_q))

    status, payload, _ = admin.get("/api/questions?status=approved")
    approved_ids = [q["id"] for q in payload["questions"]]
    wrong_id = approved_ids[0]
    right_id = approved_ids[1]
    never_ids = approved_ids[2:]

    for _ in range(3):
        staff.post("/api/attempts", {"question_id": wrong_id, "correct": False})
    for _ in range(3):
        staff.post("/api/attempts", {"question_id": right_id, "correct": True})

    status, payload, _ = admin.get("/api/stats")
    weights = {q["id"]: q["weight"] for q in payload["questions"]}
    check("questions the squadron got wrong weigh more", weights[wrong_id] > weights[never_ids[0]],
          "wrong=%s never=%s" % (weights[wrong_id], weights[never_ids[0]]))
    check("questions answered correctly weigh less", weights[right_id] < weights[never_ids[0]],
          "right=%s never=%s" % (weights[right_id], weights[never_ids[0]]))

    from collections import Counter

    import time as _t

    # point the library modules at the same database the test server is using
    os.environ["QUIZ_DB"] = DB
    sys.path.insert(0, ROOT)
    import db as dbmod
    import quiz as quizmod

    counter = Counter()
    _s = _t.time()
    with dbmod.connection() as conn:
        pool = quizmod.build_pool(conn)
        for _ in range(600):
            counter[quizmod.pick(pool)["id"]] += 1
    print("    ..sampled 600 questions in %.1fs" % (_t.time() - _s))

    never_avg = sum(counter[q] for q in never_ids) / float(len(never_ids))
    print("    ..missed %d vs never-asked %.1f vs known %d"
          % (counter[wrong_id], never_avg, counter[right_id]))
    check("questions answered wrongly come up more often", counter[wrong_id] > never_avg,
          "missed=%d never=%.1f" % (counter[wrong_id], never_avg))
    check("questions answered correctly come up least", counter[right_id] < never_avg,
          "known=%d never=%.1f" % (counter[right_id], never_avg))

    print("\n[10] weighting formula")
    sys.path.insert(0, ROOT)
    import quiz as quizmod

    check("never asked = 3.0", quizmod.weight_for(0, 0, 0) == 3.0)
    check("always right = 0.25", abs(quizmod.weight_for(4, 4, 0) - 0.25) < 1e-9)
    check("always wrong = 4.0", abs(quizmod.weight_for(4, 0, 0) - 4.0) < 1e-9)
    check("half right = 1.1875", abs(quizmod.weight_for(4, 2, 0) - 1.1875) < 1e-9)
    check("wrong streak boosted", quizmod.weight_for(2, 0, 3) > quizmod.weight_for(2, 0, 0))
    check("weight capped at 6.0", quizmod.weight_for(10, 0, 9) <= 6.0)

    print("\n[11] a question is only used once it has been answered")
    stats_before_suppression = admin.get("/api/stats")[1]["overall"]
    recent_client = Client()
    status, payload, _ = recent_client.get("/api/auth/me")
    recent_client.csrf = payload["csrf"]
    status, payload, _ = recent_client.post(
        "/api/auth/login", {"username": "nco1", "password": "ncopass123"}
    )
    recent_client.csrf = payload["csrf"]
    seen = []
    for _ in range(40):
        status, payload, _ = recent_client.get("/api/quiz/next")
        if status != 200:
            break
        qid = payload["question"]["id"]
        seen.append(qid)
        # skipped, so it is recorded as asked without moving the accuracy numbers
        recent_client.post("/api/attempts", {"question_id": qid, "correct": False, "skipped": True})
    approved = admin.get("/api/questions/counts")[1]["counts"]["approved"]
    check("no repeats within a session", len(seen) == len(set(seen)), str(seen))
    check("every approved question gets asked once", len(seen) == approved,
          "%d asked vs %d approved" % (len(seen), approved))
    check("session reports exhaustion instead of repeating",
          status == 409 and "already been asked" in payload.get("error", ""), str(payload))
    check("exhausted session is flagged with a reason", payload.get("reason") == "exhausted", str(payload))

    # the reported bug: looking at a question and changing topic must not use it up
    fresh = Client()
    status, payload, _ = fresh.get("/api/auth/me")
    fresh.csrf = payload["csrf"]
    status, payload, _ = fresh.post(
        "/api/auth/login", {"username": "nco1", "password": "ncopass123"}
    )
    fresh.csrf = payload["csrf"]
    status, payload, _ = fresh.get("/api/quiz/next?topic=General")
    check("a new session can ask again", status == 200, str(payload))
    first = payload["question"]["id"]

    # weighted selection may pick something else, so keep drawing until the
    # unanswered question shows up again - it must never have been excluded
    offered_again = False
    for _ in range(60):
        status, payload, _ = fresh.get("/api/quiz/next?topic=General")
        if status != 200:
            break
        if payload["question"]["id"] == first:
            offered_again = True
            break
    check("an unanswered question is still offered after changing topic", offered_again,
          "question %s was treated as already asked" % first)

    fresh.post("/api/attempts", {"question_id": first, "correct": False, "skipped": True})
    offered_after = []
    for _ in range(60):
        status, payload, _ = fresh.get("/api/quiz/next?topic=General")
        if status != 200:
            break
        if payload["question"]["id"] == first:
            offered_after.append(True)
    check("answering it removes it for good", not offered_after, "question %s came back" % first)

    print("\n[12] skip does not count against the squadron")
    before = admin.get("/api/stats")[1]["overall"]
    skipper = Client()
    status, payload, _ = skipper.get("/api/auth/me")
    skipper.csrf = payload["csrf"]
    status, payload, _ = skipper.post("/api/auth/login", {"username": "nco1", "password": "ncopass123"})
    skipper.csrf = payload["csrf"]
    status, payload, _ = skipper.get("/api/quiz/next")
    qid = payload["question"]["id"]
    status, payload, _ = skipper.post(
        "/api/attempts", {"question_id": qid, "correct": False, "skipped": True}
    )
    check("skip records ok", status == 200, str(payload))
    check("skip is not counted as an answer", payload["overall"]["asked"] == before["asked"],
          "%s vs %s" % (payload["overall"]["asked"], before["asked"]))
    check("skip is counted as skipped", payload["overall"]["skipped"] == before["skipped"] + 1,
          str(payload["overall"]))

    print("\n[13] topic filtering")
    status, payload, _ = admin.get("/api/questions/counts")
    topics = payload["topics"]
    check("topics collected", "Motto" in topics, str(topics))
    motto = Client()
    status, payload, _ = motto.get("/api/auth/me")
    motto.csrf = payload["csrf"]
    status, payload, _ = motto.post("/api/auth/login", {"username": "nco1", "password": "ncopass123"})
    motto.csrf = payload["csrf"]
    picked = set()
    for _ in range(15):
        status, payload, _ = motto.get("/api/quiz/next?topic=Motto")
        if status != 200:
            break
        picked.add(payload["question"]["topic"])
    check("topic filter respected", picked == {"Motto"}, str(picked))
    status, payload, _ = motto.get("/api/quiz/next?topic=Nonexistent")
    check("unknown topic rejected", status == 400, str(status))

    print("\n[14] progress page data")
    status, payload, _ = admin.get("/api/stats")
    check("stats have an overall block", "overall" in payload, str(sorted(payload)))
    # section 11 recorded skips only, so "asked" must be unchanged by it
    check("overall counts the squadron", payload["overall"]["asked"] == stats_before_suppression["asked"],
          "%s vs %s" % (payload["overall"]["asked"], stats_before_suppression["asked"]))
    expected_skips = stats_before_suppression["skipped"] + len(seen) + 2
    check("overall reports skips", payload["overall"]["skipped"] == expected_skips,
          "%s vs %s" % (payload["overall"]["skipped"], expected_skips))
    check("stats are grouped by topic", len(payload["topics"]) >= 4, str(len(payload["topics"])))

    accuracies = [t["accuracy"] for t in payload["topics"]]
    real = [a for a in accuracies if a is not None]
    check("weakest topic sorted first", real == sorted(real), str(accuracies))

    for topic in payload["topics"]:
        matching = [q for q in payload["questions"] if q["topic"] == topic["topic"]]
        check("topic '%s' lists its questions" % topic["topic"], len(matching) == topic["question_count"],
              "%d vs %d" % (len(matching), topic["question_count"]))
        check("topic '%s' totals add up" % topic["topic"],
              sum(q["asked"] for q in matching) == topic["asked"], str(topic))
    check("every approved question appears once", len(payload["questions"]) == 8, str(len(payload["questions"])))
    check("no cadet data in stats", "cadets" not in payload, str(sorted(payload)))

    print("\n[15] admin deactivates staff")
    status, payload, _ = admin.get("/api/admin/users")
    nco1 = [u for u in payload["users"] if u["username"] == "nco1"][0]
    admin_user = [u for u in payload["users"] if u["role"] == "admin"][0]
    status, payload, _ = admin.post("/api/admin/users/%d/active" % admin_user["id"], {"active": False})
    check("admin cannot disable self", status == 400, str(status))
    status, payload, _ = admin.post("/api/admin/users/%d/active" % nco1["id"], {"active": False})
    check("admin can disable staff", status == 200, str(payload))
    status, payload, _ = staff.get("/api/quiz/next")
    check("disabled staff session dies", status == 401, str(status))
    disabled = Client()
    status, payload, _ = disabled.get("/api/auth/me")
    disabled.csrf = payload["csrf"]
    status, payload, _ = disabled.post("/api/auth/login", {"username": "nco1", "password": "ncopass123"})
    check("disabled staff cannot log in", status == 401, str(status))
    status, payload, _ = admin.post("/api/admin/users/%d/active" % nco1["id"], {"active": True})
    check("staff can be re-enabled", status == 200, str(payload))

    print("\n[16] password change")
    changer = Client()
    status, payload, _ = changer.get("/api/auth/me")
    changer.csrf = payload["csrf"]
    status, payload, _ = changer.post("/api/auth/login", {"username": "nco1", "password": "ncopass123"})
    changer.csrf = payload["csrf"]
    status, payload, _ = changer.post(
        "/api/auth/change-password", {"current_password": "wrong", "new_password": "newpass12345"}
    )
    check("wrong current password rejected", status == 403, str(status))
    status, payload, _ = changer.post(
        "/api/auth/change-password", {"current_password": "ncopass123", "new_password": "newpass12345"}
    )
    check("password changed", status == 200, str(payload))
    again = Client()
    status, payload, _ = again.get("/api/auth/me")
    again.csrf = payload["csrf"]
    status, payload, _ = again.post("/api/auth/login", {"username": "nco1", "password": "ncopass123"})
    check("old password no longer works", status == 401, str(status))
    status, payload, _ = again.post("/api/auth/login", {"username": "nco1", "password": "newpass12345"})
    check("new password works", status == 200, str(status))

    print("\n[17] path traversal and static files")
    status, body, headers = admin.request("GET", "/", raw=True)
    check("index served", status == 200 and "<title>RAFAC Questions</title>" in body, str(status))
    check("the raf roundel is the favicon",
          'href="/static/favicon.svg"' in body and 'rel="icon"' in body, "no svg favicon link")
    check("a png favicon fallback is offered",
          'sizes="32x32"' in body and 'sizes="16x16"' in body, "no png sizes")
    check("an apple touch icon is offered", 'rel="apple-touch-icon"' in body, "no apple touch icon")
    # nosniff is set, so a wrong content type would stop the browser using the icon
    for path, ctype in (("/static/favicon.svg", "image/svg+xml"),
                        ("/static/favicon-32x32.png", "image/png"),
                        ("/static/favicon-16x16.png", "image/png"),
                        ("/static/favicon-64x64.png", "image/png"),
                        ("/static/apple-touch-icon.png", "image/png")):
        status, blob, hdrs = admin.request("GET", path, raw=True, binary=True)
        check("%s serves %s" % (path, ctype),
              status == 200 and hdrs.get("Content-Type", "").startswith(ctype) and blob,
              "%s %s" % (status, hdrs.get("Content-Type")))
    status, svg, _ = admin.request("GET", "/static/favicon.svg", raw=True)
    check("the favicon draws the raf roundel",
          all(colour in svg for colour in ("#1f5fbf", "#ffffff", "#c8102e")), svg[:120])
    check("the favicon is the roundel alone, with no crown",
          "#d4af37" not in svg and "<path" not in svg, "crown artwork crept back in")
    # the favicon and the heading roundel are the same mark, so keep them identical
    served_index = body
    heading = re.search(r'<svg class="roundel".*?</svg>', served_index, re.S)
    heading = heading.group(0) if heading else ""
    check("the favicon matches the roundel beside the title",
          heading and all(('r="%d"' % r) in svg for r in (48, 34, 20))
          and all(('r="%d"' % r) in heading for r in (48, 34, 20))
          and 'viewBox="0 0 100 100"' in svg and 'viewBox="0 0 100 100"' in heading,
          "favicon and heading geometry have drifted apart")
    check("security headers set", "X-Frame-Options" in headers and "Content-Security-Policy" in headers, str(sorted(headers)))
    check("no inline script in index", "<script>" not in body.replace('<script src="/static/app.js"></script>', ''), "inline script found")
    check("no cadet name field in the ask view", "cadet-select" not in body and "add-cadet-btn" not in body, "cadet controls still present")
    check("no start button in the ask view", "start-quiz-btn" not in body, "start button still present")
    status, body, headers = admin.request("GET", "/static/style.css", raw=True)
    check("stylesheet served", status == 200 and ":root" in body, str(status))
    status, body, headers = admin.request("GET", "/static/app.js", raw=True)
    check("script served", status == 200 and "csrf" in body, str(status))
    for bad in ("/static/../app.py", "/static/../../app.py", "/static/%2e%2e/app.py"):
        req = urllib.request.Request(BASE + bad)
        try:
            with urllib.request.urlopen(req) as resp:
                content = resp.read().decode(errors="replace")
            check("no traversal via %s" % bad, "sqlite3" not in content and "import db" not in content, content[:80])
        except urllib.error.HTTPError as exc:
            check("no traversal via %s" % bad, exc.code in (400, 404), str(exc.code))
    status, payload, _ = admin.get("/api/nope")
    check("unknown api route 404s", status == 404, str(status))
    status, payload, _ = admin.request("GET", "/api/admin/import")
    check("wrong method 405s", status == 405, str(status))

    print("\n[18] questions never leak to guests")
    status, payload, _ = guest.get("/api/questions?status=pending")
    check("guest cannot list questions", status in (401, 403), str(status))
    status, payload, _ = guest.get("/api/questions")
    check("guest cannot list approved questions either", status in (401, 403), str(status))
    status, payload, _ = guest.get("/api/quiz/next")
    check("guest cannot pull questions", status == 401, str(status))
    status, payload, _ = guest.get("/api/stats")
    check("guest cannot see progress data", status == 401, str(status))
    status, payload, _ = guest.get("/api/admin/users")
    check("guest cannot see accounts", status == 401, str(status))

    print("\n[19] question edit and delete")
    guest.post(
        "/api/questions",
        {"question_text": "A cadet question awaiting review", "answer_text": "yes",
         "topic": "General", "submitted_by": "Cdt Ross"},
    )
    status, payload, _ = admin.get("/api/questions?status=pending")
    check("new submission is pending", len(payload["questions"]) == 1, str(len(payload["questions"])))
    target = payload["questions"][0]
    status, payload, _ = admin.post(
        "/api/admin/questions/%d/edit" % target["id"],
        {"question_text": target["question_text"] + " (edited)", "answer_text": "edited answer"},
    )
    check("edit works", status == 200, str(payload))
    status, payload, _ = admin.get("/api/questions?status=pending")
    edited = [q for q in payload["questions"] if q["id"] == target["id"]][0]
    check("edit persisted", edited["question_text"].endswith("(edited)"), edited["question_text"])
    status, payload, _ = admin.post("/api/admin/questions/%d/delete" % target["id"], {})
    check("delete works", status == 200, str(payload))
    status, payload, _ = admin.get("/api/questions?status=pending")
    check("deleted question gone", all(q["id"] != target["id"] for q in payload["questions"]))

    print("\n[19a] archive, restore and permanently delete question history")
    archive_staff = Client()
    status, payload, _ = archive_staff.get("/api/auth/me")
    archive_staff.csrf = payload.get("csrf")
    status, payload, _ = archive_staff.post(
        "/api/auth/login", {"username": "nco1", "password": "newpass12345"}
    )
    archive_staff.csrf = payload.get("csrf")
    check("staff login for archive checks", status == 200, str(payload))
    status, payload, _ = admin.post(
        "/api/questions",
        {"question_text": "Archive workflow question", "answer_text": "kept answer",
         "topic": "Archive checks"},
    )
    archive_id = payload.get("id")
    check("admin can add archive test question", status == 200 and archive_id is not None, str(payload))
    status, attempt, _ = archive_staff.post(
        "/api/attempts", {"question_id": archive_id, "correct": True}
    )
    session_id = attempt.get("quiz_session_id")
    check("test question has recorded history", status == 200 and session_id is not None, str(attempt))
    status, payload, _ = archive_staff.post(
        "/api/admin/questions/%d/archive" % archive_id, {}
    )
    check("staff cannot archive questions", status == 403, str(status))
    status, payload, _ = archive_staff.get("/api/questions?include_archived=1")
    check("staff cannot view archived questions", status == 403, str(status))
    status, payload, _ = admin.post(
        "/api/admin/questions/%d/archive" % archive_id, {}
    )
    check("admin can archive accepted questions", status == 200, str(payload))
    status, payload, _ = admin.get("/api/questions?status=approved")
    check("archived question is excluded from active bank", all(
        q["id"] != archive_id for q in payload["questions"]
    ))
    status, payload, _ = admin.get("/api/questions?include_archived=1")
    archived = [q for q in payload["questions"] if q["id"] == archive_id]
    check("admin can view archived question", bool(archived) and bool(archived[0]["archived_at"]))
    status, payload, _ = archive_staff.post(
        "/api/attempts", {"question_id": archive_id, "correct": True}
    )
    check("archived question cannot receive new attempts", status == 400, str(status))
    status, payload, _ = archive_staff.post("/api/quiz/finish", {})
    check("history session can be finished", status == 200, str(payload))
    status, payload, _ = admin.get("/api/admin/quiz-sessions/%d" % session_id)
    check("archive keeps historical attempt", status == 200 and any(
        a["question_id"] == archive_id for a in payload.get("attempts", [])
    ))
    status, payload, _ = admin.post(
        "/api/admin/questions/%d/restore" % archive_id, {}
    )
    check("admin can restore archived question", status == 200, str(payload))
    status, payload, _ = admin.get("/api/questions?status=approved")
    check("restored question returns to active bank", any(
        q["id"] == archive_id for q in payload["questions"]
    ))
    status, payload, _ = admin.post(
        "/api/admin/questions/%d/delete" % archive_id, {}
    )
    check("admin can permanently delete restored question", status == 200, str(payload))
    status, payload, _ = admin.get("/api/admin/quiz-sessions/%d" % session_id)
    check("permanent deletion removes historical attempt references", status == 200 and all(
        a["question_id"] != archive_id for a in payload.get("attempts", [])
    ))

    print("\n[19b] upgrade an existing database for archiving")
    legacy_db = os.path.join(ROOT, "test_legacy_archive.db")
    remove_db(legacy_db)
    legacy_conn = sqlite3.connect(legacy_db)
    legacy_conn.executescript("""
        CREATE TABLE users (id INTEGER PRIMARY KEY);
        CREATE TABLE questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question_text TEXT NOT NULL,
            answer_text TEXT NOT NULL DEFAULT '',
            topic TEXT NOT NULL DEFAULT 'General',
            status TEXT NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'approved', 'rejected')),
            submitted_by TEXT NOT NULL DEFAULT '',
            source TEXT NOT NULL DEFAULT 'staff',
            review_note TEXT NOT NULL DEFAULT '',
            reviewed_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
            reviewed_at TEXT,
            created_at TEXT NOT NULL
        );
        CREATE TABLE attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question_id INTEGER NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
            correct INTEGER NOT NULL DEFAULT 0 CHECK (correct IN (0, 1)),
            skipped INTEGER NOT NULL DEFAULT 0 CHECK (skipped IN (0, 1)),
            answered_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
            created_at TEXT NOT NULL
        );
        INSERT INTO questions (question_text, answer_text, topic, status, created_at)
            VALUES ('Legacy question', 'Legacy answer', 'Legacy topic', 'approved', '2025-01-01');
        INSERT INTO attempts (question_id, correct, created_at)
            VALUES (1, 1, '2025-01-02');
    """)
    legacy_conn.close()
    previous_db_path = dbmod.DB_PATH
    try:
        dbmod.DB_PATH = legacy_db
        dbmod.init()
        legacy_conn = sqlite3.connect(legacy_db)
        columns = {row[1] for row in legacy_conn.execute("PRAGMA table_info(questions)")}
        attempt_count = legacy_conn.execute("SELECT COUNT(*) FROM attempts").fetchone()[0]
        legacy_conn.close()
    finally:
        dbmod.DB_PATH = previous_db_path
        remove_db(legacy_db)
    check("old question tables gain the archive field", "archived_at" in columns)
    check("old attempts survive the archive migration", attempt_count == 1, str(attempt_count))

    print("\n[20] no name needed when adding from the bank")
    status, payload, _ = admin.post(
        "/api/questions",
        {"question_text": "Admin added this straight from the bank",
         "answer_text": "bank answer", "topic": "General"},
    )
    check("admin can add a question with no name", status == 200, str(payload))
    check("admin addition is approved immediately", payload.get("status") == "approved", str(payload))
    status, payload, _ = admin.get("/api/questions?status=approved")
    added = [q for q in payload["questions"] if q["question_text"].startswith("Admin added this")]
    check("admin name taken from the account", bool(added) and added[0]["submitted_by"] == "Administrator",
          str(added[:1]))

    # section 15 disabled/re-enabled nco1 and section 16 changed its password
    nco = Client()
    status, payload, _ = nco.get("/api/auth/me")
    nco.csrf = payload["csrf"]
    status, payload, _ = nco.post("/api/auth/login", {"username": "nco1", "password": "newpass12345"})
    nco.csrf = payload["csrf"]
    status, payload, _ = nco.post(
        "/api/questions",
        {"question_text": "NCO added this with no name field", "answer_text": "nco answer", "topic": "General"},
    )
    check("staff can add a question with no name", status == 200, str(payload))
    status, payload, _ = admin.get("/api/questions?status=approved")
    added = [q for q in payload["questions"] if q["question_text"].startswith("NCO added this")]
    check("staff name taken from the account", bool(added) and added[0]["submitted_by"] == "Cpl Jones",
          str(added[:1]))

    status, payload, _ = guest.post(
        "/api/questions",
        {"question_text": "A guest question with no name", "answer_text": "yes", "topic": "General"},
    )
    check("guest still has to give a name", status == 400 and "name" in payload.get("error", ""), str(payload))

    print("\n[21] admin review buttons")
    guest.post(
        "/api/questions",
        {"question_text": "Pending question to accept", "answer_text": "a", "topic": "General",
         "submitted_by": "Cdt Accept"},
    )
    status, payload, _ = admin.get("/api/admin/pending")
    accept_target = [q for q in payload["questions"] if q["question_text"].startswith("Pending question to accept")][0]
    status, payload, _ = admin.post("/api/admin/questions/%d/approve" % accept_target["id"], {})
    check("admin can accept a question", status == 200, str(payload))
    status, payload, _ = admin.get("/api/questions?status=approved")
    check("accepted question is now approved",
          any(q["id"] == accept_target["id"] for q in payload["questions"]))

    guest.post(
        "/api/questions",
        {"question_text": "Pending question to reject", "answer_text": "b", "topic": "General",
         "submitted_by": "Cdt Reject"},
    )
    status, payload, _ = admin.get("/api/admin/pending")
    reject_target = [q for q in payload["questions"] if q["question_text"].startswith("Pending question to reject")][0]
    status, payload, _ = admin.post("/api/admin/questions/%d/reject" % reject_target["id"], {})
    check("admin can reject a question", status == 200, str(payload))
    status, payload, _ = admin.get("/api/questions?status=pending")
    check("rejected question left the queue",
          all(q["id"] != reject_target["id"] for q in payload["questions"]))

    print("\n[22] ask page and nav changes")
    index_html = open(os.path.join(ROOT, "static", "index.html"), encoding="utf-8").read()
    check("question stats removed from the ask view", "question-weights" not in index_html)
    check("selection priority no longer shown", "Selection priority" not in index_html)
    check("submit nav hidden for admins", "hide-for-admin" in index_html)

    app_js = open(os.path.join(ROOT, "static", "app.js"), encoding="utf-8").read()
    check("admin is moved off the submit view", 'state.view === "submit"' in app_js)
    check("empty quiz heading has an id for the quiz code to update",
          'id="quiz-empty-title"' in index_html)
    check("exhausted session shows the new wording",
          "No more questions left to ask" in app_js)
    check("empty bank keeps the original wording",
          "No questions to ask yet" in app_js)
    check("the api helper forwards the reason code", "error.reason" in app_js)

    print("\n[24] side menu replaces the top tabs")
    check("menu toggle exists", 'id="menu-toggle"' in index_html)
    check("side panel exists", 'id="side-menu"' in index_html)
    check("overlay exists", 'id="menu-overlay"' in index_html)
    check("nav now lives inside the side panel",
          index_html.index('id="side-menu"') < index_html.index('id="main-nav"'))
    check("session bar is inside the side panel",
          index_html.index('id="side-menu"') < index_html.index('id="session-bar"'))
    check("nav and session bar are not in the header",
          index_html.index('id="side-menu"') > index_html.index("</header>"))
    check("login link renamed to Staff/NCO login", "Staff/NCO login" in index_html)
    check("old login wording removed", "Staff log in" not in index_html)
    for view in ("quiz", "submit", "stats", "review", "bank", "users"):
        check("menu still offers the %s view" % view, 'data-view="%s"' % view in index_html)
    check("menu can be opened and closed", "setMenuOpen" in app_js)
    check("escape closes the menu", 'event.key === "Escape"' in app_js)
    check("choosing a view closes the menu", "setMenuOpen(false)" in app_js)
    check("toggle reports expanded state", 'aria-expanded' in index_html and "aria-expanded" in app_js)

    css = open(os.path.join(ROOT, "static", "style.css"), encoding="utf-8").read()
    check("quiz buttons all share the same top margin",
          "margin-top: 0" in css.split(".controls .primary")[1].split("}")[0])
    check("form submit buttons keep their spacing",
          "margin-top: 1rem" in css.split(".primary {")[1].split("}")[0])

    print("\n[25] branding")
    check("page title is RAFAC Questions", "<title>RAFAC Questions</title>" in index_html)
    check("heading is RAFAC Questions", ">RAFAC Questions<" in index_html)
    check("old title is gone", "Air Cadets Quiz" not in index_html)
    check("subtitle under the title removed", "header-subtitle" not in index_html)
    check("no javascript writes to the removed subtitle", "header-subtitle" not in app_js)
    check("two roundels flank the title", index_html.count('class="roundel"') == 2,
          str(index_html.count('class="roundel"')))
    check("roundels use the RAF colours",
          all(colour in index_html for colour in ("#1f5fbf", "#c8102e")))
    check("roundels are hidden from screen readers", index_html.count('aria-hidden="true"') >= 2)

    plane = os.path.join(ROOT, "static", "plane.jpg")
    check("plane background image exists", os.path.isfile(plane))
    check("old plane svg removed", not os.path.exists(os.path.join(ROOT, "static", "plane.svg")))
    check("no css or html still references the svg",
          "plane.svg" not in css and "plane.svg" not in index_html)
    check("plane used as the page background", 'url("/static/plane.jpg")' in css)
    check("background covers the page", "cover" in css)
    check("a scrim keeps the text readable", "linear-gradient" in css)
    check("plane does not block clicks", "pointer-events: none" in css)

    print("\n[26] progress and review text sits in boxes")
    stats_view = index_html.split('id="view-stats"')[1].split("</section>")[0]
    review_view = index_html.split('id="view-review"')[1].split("</section>")[0]

    check("text-box style defined", ".text-box {" in css)
    check("stat tiles are boxed", ".stat {" in css and "border: 1px solid var(--border)" in
          css.split(".stat {")[1].split("}")[0])
    check("progress hint is boxed", 'class="hint text-box"' in stats_view)
    check("progress empty message is boxed", 'id="stats-empty" hidden>No questions have been asked yet.' in stats_view
          and "muted text-box" in stats_view)
    check("overall stats no longer wrapped in a card", "card stat-row" not in stats_view)
    check("review summary is boxed", 'id="review-summary"' in review_view and "hint text-box" in review_view)
    check("review empty message is boxed", "muted text-box" in review_view)
    for heading in ("<h2>Progress</h2>", "<h2>Review submitted questions</h2>"):
        check("title left unboxed: %s" % heading, heading in index_html)
    check("only one .stat rule remains", css.count(".stat {") == 1, str(css.count(".stat {")))

    print("\n[27] quiz buttons all share one solid style")
    ghost_block = css.split(".ghost {")[1].split("}")[0]
    check("ghost buttons are filled", "background: var(--card-hover)" in ghost_block, ghost_block)
    check("ghost buttons are no longer transparent", "background: transparent" not in ghost_block)
    check("skip button is solid amber", 'class="warn" id="skip-btn"' in index_html)
    check("correct button is solid green", 'class="success" id="correct-btn"' in index_html)
    check("finish button is solid blue", 'class="primary" id="finish-btn"' in index_html)
    check("show answer button is solid white", 'class="secondary" id="reveal-btn"' in index_html
          and "background: #ffffff" in css.split(".secondary {")[1].split("}")[0])
    check("the empty-state finish matches too", 'class="primary" id="quiz-empty-finish"' in index_html)
    check("solid amber defined", ".warn {" in css)
    check("solid neutral defined", ".secondary {" in css)
    check("solid green defined", ".success {" in css)
    check("no boxed wrapper around the buttons", "quiz-actions" not in index_html and "quiz-actions" not in css)
    check("the whole set shares Show answer's edge",
          "border: 1px solid var(--muted)" in css.split(".controls .primary,")[1].split("}")[0])
    check("the whole set uses black text",
          "color: #0b1016" in css.split(".controls .primary,")[1].split("}")[0])
    check("no washed-out tints remain", ".ghost-warn" not in css and ".ghost-accent" not in css)
    check("menu toggle is a symbol, not words",
          'id="menu-toggle"' in index_html
          and ">Menu</button>" not in index_html
          and "&#9776;" in index_html.split('id="side-menu"')[0])
    check("menu toggle keeps an accessible name", 'aria-label="Open menu"' in index_html)

    print("\n[23] review buttons actually reach the page")
    # the buttons were once built into a detached div and never inserted, so exercise
    # the real render path with a minimal DOM instead of grepping the source
    dom_script = r"""
const fs = require("fs");
const src = fs.readFileSync(process.argv[2], "utf8");
function grab(name) {
    const start = src.indexOf("function " + name + "(");
    if (start < 0) { throw new Error("missing " + name); }
    let p = src.indexOf("(", start), pd = 0;
    for (let i = p; i < src.length; i++) {
        if (src[i] === "(") { pd++; }
        else if (src[i] === ")") { pd--; if (pd === 0) { p = i; break; } }
    }
    let depth = 0;
    for (let i = src.indexOf("{", p); i < src.length; i++) {
        if (src[i] === "{") { depth++; }
        else if (src[i] === "}") { depth--; if (depth === 0) return src.slice(start, i + 1); }
    }
    throw new Error("unbalanced " + name);
}
function makeEl(tag) {
    return {
        tag, children: [], className: "", textContent: "",
        appendChild(c) { this.children.push(c); return c; },
        addEventListener() {},
        classList: { add() {}, remove() {}, toggle() {} },
    };
}
global.document = { createElement: makeEl };
eval(grab("makeButton"));
eval(grab("chip"));
eval(grab("questionListItem"));
const LABELS = ["Accept", "Reject", "Edit", "Delete"];
function collect(el, out) {
    if (el.children) { el.children.forEach((c) => collect(c, out)); }
    if (LABELS.indexOf(el.textContent) !== -1) { out.push(el.textContent); }
    return out;
}
const question = { id: 7, question_text: "Q?", answer_text: "A", topic: "T",
                   status: "pending", submitted_by: "Cdt X" };
// correct usage: fill the container that questionListItem hands you
const good = questionListItem(question, {
    showAnswer: true,
    actions: (_item, actions) => { LABELS.forEach((l) => actions.appendChild(makeButton(l, "", () => {}))); },
});
// the old broken usage: build a detached div and return it
const detached = makeEl("div");
const bad = questionListItem(question, {
    showAnswer: true,
    actions: () => { LABELS.forEach((l) => detached.appendChild(makeButton(l, "", () => {}))); return detached; },
});
console.log("GOOD:" + collect(good, []).join(","));
console.log("BAD:" + collect(bad, []).join(","));
"""
    dom_path = os.path.join(ROOT, "static", "_dom_check.js")
    with open(dom_path, "w", encoding="utf-8") as handle:
        handle.write(dom_script)
    try:
        dom_out = subprocess.run(
            ["node", dom_path, os.path.join(ROOT, "static", "app.js")],
            capture_output=True, text=True, timeout=60,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        dom_out = ""
    finally:
        if os.path.exists(dom_path):
            os.remove(dom_path)

    good_line = [l for l in dom_out.splitlines() if l.startswith("GOOD:")]
    bad_line = [l for l in dom_out.splitlines() if l.startswith("BAD:")]
    check("review buttons render into the page",
          bool(good_line) and good_line[0] == "GOOD:Accept,Reject,Edit,Delete",
          good_line[0] if good_line else dom_out[:200])
    check("the old detached-div bug is caught by this test",
          bool(bad_line) and bad_line[0] == "BAD:", bad_line[0] if bad_line else "no BAD line")


    print("\n[28] bank groups by status then theme")
    check("the status filter dropdown is gone",
          'id="bank-status"' not in index_html, "bank-status still present")
    check("the bank list is no longer a bare ul",
          '<div id="bank-list">' in index_html, "expected a div host for the groups")
    check("bank group styles are defined", ".bank-group" in css, "no .bank-group rule")
    check("each status gets its own accent colour",
          all(('data-status="%s"' % s) in css for s in ("pending", "approved", "rejected", "archived")),
          "missing data-status rule in the css")
    check("groups are tagged for the accent colours",
          "section.dataset.status = group.value" in app_js, "group not tagged with its status")
    for label in ("Pending", "Accepted", "Rejected"):
        check("bank has a %s group" % label, label in app_js, label)

    bank_script = r"""
const fs = require("fs");
const src = fs.readFileSync(process.argv[2], "utf8");
function grab(name) {
    const start = src.indexOf("function " + name + "(");
    if (start < 0) { throw new Error("missing " + name); }
    let p = src.indexOf("(", start), pd = 0;
    for (let i = p; i < src.length; i++) {
        if (src[i] === "(") { pd++; }
        else if (src[i] === ")") { pd--; if (pd === 0) { p = i; break; } }
    }
    let depth = 0;
    for (let i = src.indexOf("{", p); i < src.length; i++) {
        if (src[i] === "{") { depth++; }
        else if (src[i] === "}") { depth--; if (depth === 0) return src.slice(start, i + 1); }
    }
    throw new Error("unbalanced " + name);
}
function makeEl(tag) {
    return {
        tag, children: [], className: "", textContent: "",
        appendChild(c) { this.children.push(c); return c; },
        addEventListener() {},
        classList: { add() {}, remove() {}, toggle() {} },
        dataset: {},
    };
}
global.document = { createElement: makeEl };
// the action handlers are referenced by name, so stub them
function reviewFromBank() {}
function deleteQuestion() {}
function archiveQuestion() {}
function restoreQuestion() {}
function editQuestion() {}
function renameTopic() {}
// an admin sees the rename control on every topic group
const state = { user: { role: "admin" }, topics: ["Motto"] };
eval(grab("makeButton"));
eval(grab("chip"));
eval(grab("questionListItem"));
eval(grab("questionActions"));
eval(grab("bankTopicGroup"));
const openBankGroups = new Set();
eval(grab("bankStatusGroup"));
const BANK_GROUPS = [
    { value: "pending", label: "Pending" },
    { value: "approved", label: "Accepted" },
    { value: "rejected", label: "Rejected" },
    { value: "archived", label: "Archived" },
];
function findAll(node, pred, acc) {
    acc = acc || [];
    if (node.children) { node.children.forEach((c) => findAll(c, pred, acc)); }
    if (pred(node)) { acc.push(node); }
    return acc;
}
const questions = [
    { id: 1, question_text: "p1", answer_text: "a", topic: "Motto", status: "pending" },
    { id: 2, question_text: "p2", answer_text: "a", topic: "Doctrine", status: "pending" },
    { id: 3, question_text: "a0", answer_text: "a", topic: "Motto", status: "approved" },
    { id: 4, question_text: "a1", answer_text: "a", topic: "Motto", status: "approved" },
    { id: 5, question_text: "r1", answer_text: "a", topic: "Ranks", status: "rejected" },
    { id: 6, question_text: "a2", answer_text: "a", topic: "Archive checks", status: "approved",
      archived_at: "2026-10-15T12:00:00+00:00" },
];
const out = [];
BANK_GROUPS.forEach((group) => {
    const items = group.value === "archived"
        ? questions.filter((q) => q.archived_at)
        : questions.filter((q) => !q.archived_at && q.status === group.value);
    const section = bankStatusGroup(group, items);
    const topics = findAll(section, (n) => n.className === "topic-name").map((n) => n.textContent);
    const count = findAll(section, (n) => n.className === "muted").map((n) => n.textContent);
    const items1 = findAll(section, (n) => n.className === "q-text muted").length;
    out.push(group.label + ":" + section.dataset.status + ":" + topics.join("|") + ":" + count.join("") + ":" + items1);
});
console.log("GROUPS:" + out.join(" "));
const empty = bankStatusGroup(BANK_GROUPS[1], []);
console.log("EMPTY:" + findAll(empty, (n) => n.className === "topic-box").length
    + ":" + findAll(empty, (n) => n.textContent === "Nothing here.").length
    + ":" + findAll(empty, (n) => n.className === "section-label").length);

// every question in the bank must be editable from the bank itself
function buttons(q) {
    const holder = makeEl("div");
    questionActions(q)(null, holder);
    return findAll(holder, (n) => n.tag === "button").map((n) => n.textContent).join(",");
}
const base = { question_text: "q", answer_text: "a", topic: "T" };
console.log("PENDINGBTNS:" + buttons({ id: 1, status: "pending" }));
console.log("APPROVEDBTNS:" + buttons({ id: 2, status: "approved" }));
console.log("REJECTEDBTNS:" + buttons({ id: 3, status: "rejected" }));
console.log("ARCHIVEDBTNS:" + buttons({ id: 4, status: "approved", archived_at: "2026-10-15" }));
console.log("EDITWIRING:" + /makeButton\("Edit", "", \(\) => editQuestion\(question\)\)/.test(src));
"""
    bank_path = os.path.join(ROOT, "static", "_bank_check.js")
    with open(bank_path, "w", encoding="utf-8") as handle:
        handle.write(bank_script)
    try:
        bank_out = subprocess.run(
            ["node", bank_path, os.path.join(ROOT, "static", "app.js")],
            capture_output=True, text=True, timeout=60,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        bank_out = ""
    finally:
        if os.path.exists(bank_path):
            os.remove(bank_path)

    groups_line = [l for l in bank_out.splitlines() if l.startswith("GROUPS:")]
    check("bank renders pending, accepted and rejected groups, each split by theme",
          bool(groups_line) and groups_line[0] == (
              "GROUPS:Pending:pending:Doctrine|Motto: (2):2 "
              "Accepted:approved:Motto: (2):2 "
              "Rejected:rejected:Ranks: (1):1 "
              "Archived:archived:Archive checks: (1):1"
          ),
          groups_line[0] if groups_line else bank_out[:300])
    empty_line = [l for l in bank_out.splitlines() if l.startswith("EMPTY:")]
    check("an empty status group still shows its heading and a placeholder",
          bool(empty_line) and empty_line[0] == "EMPTY:0:1:1", empty_line[0] if empty_line else "no EMPTY line")

    buttons = {l.split(":", 1)[0]: l.split(":", 1)[1] for l in bank_out.splitlines()
               if l.split(":", 1)[0] in ("PENDINGBTNS", "APPROVEDBTNS", "REJECTEDBTNS", "ARCHIVEDBTNS", "EDITWIRING")}
    check("a pending question in the bank can be accepted, edited and deleted",
          buttons.get("PENDINGBTNS") == "Accept,Edit,Delete", buttons.get("PENDINGBTNS", "none"))
    check("an accepted question in the bank can be removed, archived, edited and deleted",
          buttons.get("APPROVEDBTNS") == "Remove from quiz,Archive,Edit,Delete",
          buttons.get("APPROVEDBTNS", "none"))
    check("a rejected question in the bank can be accepted, edited and deleted",
          buttons.get("REJECTEDBTNS") == "Accept,Edit,Delete", buttons.get("REJECTEDBTNS", "none"))
    check("an archived question in the bank can be restored, edited and deleted",
          buttons.get("ARCHIVEDBTNS") == "Restore to quiz,Edit,Delete",
          buttons.get("ARCHIVEDBTNS", "none"))
    check("the bank edit button calls the edit handler",
          buttons.get("EDITWIRING") == "true", buttons.get("EDITWIRING", "none"))


    print("\n[29] admin resets all progress")
    # the shared staff client lost its session in the earlier disable test, and
    # nco1's password changed, so use a freshly logged in staff/NCO client here
    staff_live = Client()
    status, payload, _ = staff_live.get("/api/auth/me")
    staff_live.csrf = payload["csrf"]
    status, payload, _ = staff_live.post(
        "/api/auth/login", {"username": "nco1", "password": "newpass12345"}
    )
    staff_live.csrf = payload["csrf"]
    check("a live staff/NCO client is signed in", status == 200, str(payload))

    status, payload, _ = admin.request("POST", "/api/admin/reset-progress", body={})
    check("reset without confirmation is refused", status == 400, str(status))
    status, payload, _ = staff_live.post("/api/admin/reset-progress", {"confirm": True})
    check("staff/NCO cannot reset progress", status == 403, str(status))
    status, payload, _ = guest.post("/api/admin/reset-progress", {"confirm": True})
    check("guests cannot reset progress", status == 401, str(status))
    check("the reset button is admin only",
          'id="reset-progress-btn"' in served_index and "danger-zone admin-only" in served_index,
          "no admin-only reset control on the progress page")
    check("progress reset warns before deleting",
          "cannot be undone" in app_js and "are kept" in app_js, "no destructive warning")
    check("progress reset asks twice", app_js.count("window.confirm(") >= 3, "expected a double confirm")

    before = admin.get("/api/stats")[1]["overall"]
    check("there is progress to delete", before["asked"] + before["skipped"] > 0, str(before))
    questions_before = admin.get("/api/questions/counts")[1]["counts"]["total"]
    status, payload, _ = admin.post("/api/admin/reset-progress", {"confirm": True})
    check("admin can reset progress", status == 200, str(status))
    after = admin.get("/api/stats")[1]["overall"]
    check("every answer is gone",
          after["asked"] == 0 and after["correct"] == 0
          and after["incorrect"] == 0 and after["skipped"] == 0, str(after))
    check("the question bank survives the reset",
          admin.get("/api/questions/counts")[1]["counts"]["total"] == questions_before,
          "questions were deleted too")
    check("the accounts survive the reset",
          len(admin.get("/api/admin/users")[1]["users"]) >= 2, "accounts were deleted too")
    status, payload, _ = staff_live.get("/api/quiz/next")
    check("sessions can ask again after a reset", status == 200, str(payload))

    print("\n[30] admin edits staff/NCO usernames and passwords")
    status, payload, _ = admin.post(
        "/api/admin/users",
        {"username": "nco.temp", "password": "temppass123", "role": "staff", "display_name": "Temp NCO"},
    )
    check("a disposable account is created", status == 200, str(payload))
    users = {u["username"]: u for u in admin.get("/api/admin/users")[1]["users"]}
    temp_id = users["nco.temp"]["id"]
    check("the admin can see usernames in the account list",
          "nco.temp" in users and users["nco.temp"]["display_name"] == "Temp NCO", str(sorted(users)))

    status, payload, _ = admin.post(
        "/api/admin/users/%d/username" % temp_id, {"username": "nco.renamed"}
    )
    check("admin can rename an account", status == 200, str(payload))
    users = {u["username"] for u in admin.get("/api/admin/users")[1]["users"]}
    check("the new username is live", "nco.renamed" in users and "nco.temp" not in users, str(sorted(users)))
    status, payload, _ = admin.post(
        "/api/admin/users/%d/username" % temp_id, {"username": "nco1"}
    )
    check("renaming onto an existing username is rejected", status == 409, str(status))
    status, payload, _ = admin.post(
        "/api/admin/users/%d/username" % temp_id, {"username": "no!"}
    )
    check("an invalid username is rejected", status == 400, str(status))
    status, payload, _ = admin.post(
        "/api/admin/users/%d/username" % temp_id, {"username": "nco.renamed"}
    )
    check("renaming to the same name is harmless", status == 200, str(status))

    login = Client()
    status, payload, _ = login.get("/api/auth/me")
    login.csrf = payload["csrf"]
    status, payload, _ = login.post(
        "/api/auth/login", {"username": "nco.renamed", "password": "temppass123"}
    )
    check("the renamed account logs in", status == 200, str(payload))
    login.csrf = payload["csrf"]
    status, payload, _ = admin.post(
        "/api/admin/users/%d/password" % temp_id, {"password": "brandnew123"}
    )
    check("admin can reset an account password", status == 200, str(payload))
    check("the reset is reported with nothing left to change",
          payload.get("message") == "password updated", str(payload))
    status, payload, _ = login.get("/api/auth/me")
    check("the old session is dropped by a password reset", payload["user"] is None, str(payload))
    again = Client()
    status, payload, _ = again.get("/api/auth/me")
    again.csrf = payload["csrf"]
    status, payload, _ = again.post(
        "/api/auth/login", {"username": "nco.renamed", "password": "temppass123"}
    )
    check("the old password no longer works", status == 401, str(status))
    status, payload, _ = again.post(
        "/api/auth/login", {"username": "nco.renamed", "password": "brandnew123"}
    )
    check("the new password works", status == 200, str(payload))
    check("a reset password works straight away, with nothing left to change",
          payload["user"]["must_change"] is False, str(payload))
    status, payload, _ = admin.post(
        "/api/admin/users/%d/password" % temp_id, {"password": "short"}
    )
    check("a short reset password is rejected", status == 400, str(status))
    status, payload, _ = staff_live.post(
        "/api/admin/users/%d/password" % temp_id, {"password": "brandnew123"}
    )
    check("staff/NCO cannot reset another account password", status == 403, str(status))
    status, payload, _ = staff_live.post(
        "/api/admin/users/%d/username" % temp_id, {"username": "nco.stolen"}
    )
    check("staff/NCO cannot rename another account", status == 403, str(status))
    admin_id = admin.get("/api/auth/me")[1]["user"]["id"]
    status, payload, _ = admin.post(
        "/api/admin/users/%d/username" % admin_id, {"username": "admin.renamed"}
    )
    check("an admin cannot rename themselves here", status == 400, str(status))
    status, payload, _ = admin.post(
        "/api/admin/users/%d/password" % admin_id, {"password": "brandnew123"}
    )
    check("an admin cannot reset their own password here", status == 400, str(status))
    check("the account list offers username and password controls",
          '"Username", ""' in app_js and '"Password", ""' in app_js, "no edit controls rendered")

    print("\n[31] wording and the add-question topic")
    app_py = open(os.path.join(ROOT, "app.py"), encoding="utf-8").read()
    readme = open(os.path.join(ROOT, "README.md"), encoding="utf-8").read()
    for bad in ("Staff accounts", "staff accounts", "staff account"):
        check('no "%s" wording anywhere' % bad,
              bad not in served_index and bad not in app_js and bad not in readme, bad)
    check("the accounts page says staff/NCO", "Staff/NCO accounts" in served_index, "wording not updated")
    check("the login link says staff/NCO", "Staff/NCO login" in served_index, "wording not updated")
    check("the staff-only error mentions staff/NCO", "staff/NCO only" in app_py, "wording not updated")
    check("General is not offered when adding a question",
          'state.topics, "General", true' not in app_js, "General is still a dropdown option")
    check("a topic must be chosen", 'id="bank-topic" aria-label="Topic" required' in served_index,
          "the topic select is not required")
    check("an untopiced question is refused rather than filed as General",
          'Choose a topic for the question.' in app_js and '|| "General"' not in app_js,
          "a General fallback is still in the add path")


    print("\n[32] the admin owns staff/NCO passwords, stored only as a hash")
    status, payload, _ = admin.post("/api/admin/users/%d/show-password" % temp_id, {})
    check("there is no endpoint that reads a password back", status == 404, str(status))
    with dbmod.connection() as conn:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(users)")}
        stored = conn.execute("SELECT * FROM users WHERE username = ?", ("nco.renamed",)).fetchone()
    check("no readable password column survives", "password_text" not in columns, "password_text is still there")
    check("the stored record holds only the hash and salt",
          "brandnew123" not in json.dumps(dict(stored)), "a plaintext password is in the users table")
    listed = admin.get("/api/admin/users")[1]["users"]
    check("passwords are not shipped with the account list",
          all("password" not in u and "password_text" not in u for u in listed),
          "a password leaked into the listing")
    check("no password turns up anywhere in the database",
          "brandnew123" not in open(DB, "rb").read().decode("utf-8", "replace"),
          "a plaintext password is in the database file")
    check("the account row offers no read-back control",
          'makeButton("Show password"' not in app_js, "still offering a view button")
    check("the password is shown once, right after it is set",
          "await showPasswordOnce(" in app_js, "no one-time reveal")
    check("that reveal warns it cannot be shown again",
          "last time" in app_js, "no warning that the password is unrecoverable")

    # a self service change still works, and still stores nothing readable
    changer2 = Client()
    status, payload, _ = changer2.get("/api/auth/me")
    changer2.csrf = payload["csrf"]
    status, payload, _ = changer2.post(
        "/api/auth/login", {"username": "nco.renamed", "password": "brandnew123"}
    )
    changer2.csrf = payload["csrf"]
    status, payload, _ = changer2.post(
        "/api/auth/change-password", {"current_password": "brandnew123", "new_password": "selfchosen123"}
    )
    check("the account can still change its own password", status == 200, str(payload))
    check("the new password is not stored in the clear",
          "selfchosen123" not in open(DB, "rb").read().decode("utf-8", "replace"),
          "a plaintext password is in the database file")
    status, _, _ = changer2.post(
        "/api/auth/change-password", {"current_password": "brandnew123", "new_password": "another1234"}
    )
    check("the change logs the account out, as a password change should", status == 401, str(status))
    with dbmod.connection() as conn:
        after = conn.execute(
            "SELECT password_hash, must_change FROM users WHERE username = ?", ("nco.renamed",)
        ).fetchone()
    check("the stored hash was actually replaced",
          after["password_hash"] != stored["password_hash"], "hash did not change")
    check("a self service change leaves nothing flagged",
          after["must_change"] == 0, str(after))

    print("\n[33] no browser prompt boxes remain")
    check("no window.prompt calls remain", "window.prompt(" not in app_js, "still prompting")
    check("an in-page dialog is used instead",
          "function askForValues(" in app_js and "dialog.showModal()" in app_js, "no dialog helper")
    check("the dialog can be cancelled or escaped away",
          'dialog.addEventListener("cancel"' in app_js, "no escape handling")
    check("the dialog builds real input fields",
          'document.createElement(field.rows ? "textarea" : "input")' in app_js, "no inputs")
    check("the edit dialog offers the known topics",
          'list: "known-topics"' in app_js, "no topic suggestions when editing")
    check("the dialog is styled", ".modal-form" in css and ".modal::backdrop" in css, "no dialog styling")

    print("\n[33b] the two dialog buttons match")
    check("cancel is a styled button, not a bare one",
          'cancel.className = "ghost"' in app_js, "cancel button is unstyled")
    check("the confirm button is still the primary one",
          'submit.className = "primary"' in app_js, "submit lost its primary class")
    primary_pad = re.search(r"\.primary \{[^}]*padding: ([^;]+);", css)
    ghost_pad = re.search(r"\.ghost \{[^}]*padding: ([^;]+);", css)
    check("both buttons share the same padding",
          bool(primary_pad) and bool(ghost_pad) and primary_pad.group(1).strip() == ghost_pad.group(1).strip(),
          "primary=%s ghost=%s" % (primary_pad and primary_pad.group(1), ghost_pad and ghost_pad.group(1)))
    primary_weight = re.search(r"\.primary \{[^}]*font-weight: ([^;]+);", css)
    ghost_weight = re.search(r"\.ghost \{[^}]*font-weight: ([^;]+);", css)
    check("both buttons share the same weight",
          bool(primary_weight) and bool(ghost_weight) and primary_weight.group(1).strip() == ghost_weight.group(1).strip(),
          "primary=%s ghost=%s" % (primary_weight and primary_weight.group(1), ghost_weight and ghost_weight.group(1)))
    check("the stacked-layout margin is cancelled inside the dialog row",
          ".modal-actions .primary," in css and ".modal-actions .ghost {" in css,
          "margin-top would offset the pair")


    print("\n[34] every account renders, including the admin's own row")
    # the actions div used to be declared inside the "other users" branch, so the
    # admin's own row threw a ReferenceError, the whole list render aborted, and
    # any account created as an admin never appeared at all
    users_dom = r"""
const fs = require("fs");
const src = fs.readFileSync(process.argv[2], "utf8");
function grab(name) {
    const m = src.match(new RegExp("(?:async )?function " + name + "\\("));
    if (!m) { throw new Error("missing " + name); }
    const start = m.index;
    let p = src.indexOf("(", start), pd = 0;
    for (let i = p; i < src.length; i++) {
        if (src[i] === "(") { pd++; }
        else if (src[i] === ")") { pd--; if (pd === 0) { p = i; break; } }
    }
    let depth = 0;
    for (let i = src.indexOf("{", p); i < src.length; i++) {
        if (src[i] === "{") { depth++; }
        else if (src[i] === "}") { depth--; if (depth === 0) return src.slice(start, i + 1); }
    }
    throw new Error("unbalanced " + name);
}
function makeEl(tag) {
    return {
        tag, children: [], className: "", textContent: "",
        appendChild(c) { this.children.push(c); return c; },
        replaceChildren() { this.children = []; },
        addEventListener() {},
        classList: { add() {}, remove() {}, toggle() {} },
    };
}
const list = makeEl("ul");
global.document = { createElement: makeEl };
global.el = (id) => (id === "user-list" ? list : makeEl("div"));
global.state = { user: { id: 1, username: "admin" } };
global.chip = () => makeEl("span");
global.makeButton = (label) => { const b = makeEl("button"); b.textContent = label; return b; };
global.setUserUsername = () => {};
global.setUserPassword = () => {};
global.setUserActive = () => {};
global.showError = (m) => errors.push(m);
// the logged-in admin comes first: the worst case for the old bug
const USERS = [
    { id: 1, username: "admin", display_name: "Admin", role: "admin", active: 1, must_change: 0 },
    { id: 2, username: "nco1", display_name: "NCO One", role: "staff", active: 1, must_change: 0 },
    { id: 3, username: "admin2", display_name: "Second Admin", role: "admin", active: 1, must_change: 0 },
];
global.api = async () => ({ users: USERS });
function buttonNames(el, out) {
    (el.children || []).forEach((c) => {
        if (c.tag === "button") out.push(c.textContent);
        buttonNames(c, out);
    });
    return out;
}
function report(prefix) {
    console.log(prefix + "ROWS:" + list.children.length);
    console.log(prefix + "ERRORS:" + errors.length);
    console.log(prefix + "BUTTONS:" + buttonNames(list, []).join(","));
}
const errors = [];
eval(grab("loadUsers"));
loadUsers().then(() => {
    report("");
    // re-introduce the original bug to prove this harness would have caught it
    const buggy = grab("loadUsers")
        .replace("function loadUsers(", "function loadUsersBuggy(")
        .replace(/const actions = document\.createElement\("div"\);\r?\n([ \t]*)actions\.className = "q-actions";\r?\n[ \t]*if \(user\.id !== state\.user\.id\) \{/,
                 '$1if (user.id !== state.user.id) {\n$1    const actions = document.createElement("div");\n$1    actions.className = "q-actions";')
        .replace("if (actions.children.length) item.appendChild(actions);", "item.appendChild(actions);");
    if (buggy.indexOf("const actions") < 0 || buggy.indexOf("actions.children.length") >= 0) {
        console.log("MUTATION:failed");
        return;
    }
    list.replaceChildren();
    errors.length = 0;
    eval(buggy);
    return loadUsersBuggy().then(() => report("OLD"));
}).catch((e) => { console.log("THREW:" + e.message); });
"""
    users_path = os.path.join(ROOT, "static", "_users_check.js")
    with open(users_path, "w", encoding="utf-8") as handle:
        handle.write(users_dom)
    try:
        users_out = subprocess.run(
            ["node", users_path, os.path.join(ROOT, "static", "app.js")],
            capture_output=True, text=True, timeout=60,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        users_out = ""
    finally:
        if os.path.exists(users_path):
            os.remove(users_path)

    def field(name):
        for line in users_out.splitlines():
            if line.startswith(name):
                return line.split(":", 1)[1]
        return None

    check("every account reaches the page",
          field("ROWS") == "3", users_out[:300])
    check("rendering raises no error", field("ERRORS") == "0", users_out[:300])
    check("other accounts get their actions, the admin's own row gets none",
          field("BUTTONS") == "Username,Password,Disable,Username,Password,Disable",
          "got " + str(field("BUTTONS")))
    check("an account created as an admin is not hidden",
          "THREW" not in users_out and field("MUTATION") != "failed", users_out[:300])
    check("this test would have caught the old bug",
          field("OLDROWS") == "0" and field("OLDERRORS") == "1",
          "old code gave rows=" + str(field("OLDROWS")) + " errors=" + str(field("OLDERRORS")))


    print("\n[35] the admin can rename a topic across the bank")
    for text, status in (("Seeded pending q", "pending"), ("Seeded approved q", "approved"),
                         ("Seeded rejected q", "rejected")):
        with dbmod.connection() as conn:
            conn.execute(
                "INSERT INTO questions (question_text, answer_text, topic, status, submitted_by, "
                "source, review_note, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (text, "Answer", "Old Name", status, "Tester", "staff", "", "2024-01-01T00:00:00+00:00"),
            )
    status, payload, _ = admin.post("/api/admin/topics/rename", {"from": "Old Name", "to": "Aerodynamics"})
    check("the rename succeeds", status == 200, str(payload))
    check("every question on the topic moves, whatever its status",
          payload.get("moved") == 3, str(payload))
    with dbmod.connection() as conn:
        rows = conn.execute(
            "SELECT status FROM questions WHERE topic = ?", ("Aerodynamics",)
        ).fetchall()
    check("all three statuses came across",
          {r["status"] for r in rows} == {"pending", "approved", "rejected"}, str(rows))
    check("the counts still add up",
          payload["counts"]["total"] == sum(payload["counts"][k] for k in ("approved", "pending", "rejected")),
          str(payload["counts"]))
    status, payload, _ = admin.post("/api/admin/topics/rename", {"from": "old name", "to": "Avionics"})
    check("the old name is matched regardless of case", status == 404, str(status))
    status, payload, _ = admin.post("/api/admin/topics/rename", {"from": "Avionics", "to": ""})
    check("an empty new name is rejected", status == 400, str(status))
    status, payload, _ = admin.post("/api/admin/topics/rename", {"from": "Avionics", "to": "Avionics"})
    check("renaming to the same name is rejected", status == 400, str(status))
    status, payload, _ = admin.post("/api/admin/topics/rename", {"from": "Avionics", "to": "z" * 81})
    check("an over long name is rejected", status == 400, str(status))
    status, payload, _ = admin.post("/api/admin/topics/rename", {"from": "No Such Topic", "to": "X"})
    check("renaming an unused topic 404s", status == 404, str(status))
    status, payload, _ = staff_live.post("/api/admin/topics/rename", {"from": "Avionics", "to": "X"})
    check("staff/NCO cannot rename a topic", status == 403, str(status))
    check("the old topic is gone from the list",
          "Avionics" not in admin.get("/api/topics")[1]["topics"], "stale topic offered")
    check("a rename control is offered on each topic group",
          'makeButton("Rename", "", () => renameTopic(' in app_js, "no rename button")
    check("the rename button is admin only",
          'state.user.role === "admin"' in app_js.split("function bankTopicGroup")[1][:900],
          "rename not gated on the admin role")
    check("the rename button does not toggle its own group",
          app_js.count("event.stopPropagation();") >= 1, "clicking rename toggles the group")
    check("a rename confirmation counts the questions it will move",
          "questions are" in app_js, "no question count in the rename dialog")

if __name__ == "__main__":
    sys.exit(main())
