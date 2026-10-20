"""End-to-end cases grouped by quiz progress."""

SECTIONS = {
    7: r'''
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
    ''',
    9: r'''
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
    ''',
    10: r'''
print("\n[10] weighting formula")
sys.path.insert(0, ROOT)
import quiz as quizmod

check("never asked = 3.0", quizmod.weight_for(0, 0, 0) == 3.0)
check("always right = 0.25", abs(quizmod.weight_for(4, 4, 0) - 0.25) < 1e-9)
check("always wrong = 4.0", abs(quizmod.weight_for(4, 0, 0) - 4.0) < 1e-9)
check("half right = 1.1875", abs(quizmod.weight_for(4, 2, 0) - 1.1875) < 1e-9)
check("wrong streak boosted", quizmod.weight_for(2, 0, 3) > quizmod.weight_for(2, 0, 0))
check("weight capped at 6.0", quizmod.weight_for(10, 0, 9) <= 6.0)
    ''',
    11: r'''
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
    ''',
    12: r'''
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
    ''',
    13: r'''
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
    ''',
    14: r'''
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
    ''',
    14.5: r'''
print("\n[14b] admin progress trends")
status, payload, _ = admin.get("/api/admin/progress-trends")
check("admin gets 12 weekly trend buckets", status == 200 and len(payload.get("weeks", [])) == 12, str(payload))
check("trend endpoint explains its small-sample threshold", payload.get("minimum_sample") == 5, str(payload))
status, payload, _ = staff.get("/api/admin/progress-trends")
check("staff cannot access admin progress trends", status == 403, str(status))
status, payload, _ = guest.get("/api/admin/progress-trends")
check("guests cannot access admin progress trends", status == 401, str(status))
    ''',
    39: r'''
print("\n[36] solo practice is public and kept off the scoreboard")
cadet = Client()
status, payload, _ = cadet.get("/api/auth/me")
cadet.csrf = payload["csrf"]
check("a guest gets a session", status == 200 and payload["user"] is None, str(status))

status, payload, _ = cadet.post("/api/practice/start", {"name": ""})
check("practice without a name is refused", status == 400, str(status))
status, payload, _ = cadet.post("/api/practice/start", {"name": "x"})
check("practice with a too-short name is refused", status == 400, str(status))
status, payload, _ = cadet.post(
    "/api/practice/start", {"name": "Practice Tester", "topic": "No Such Topic"})
check("practice with an unknown topic is refused", status == 400, str(status))
status, payload, _ = cadet.post("/api/practice/start", {"name": "Practice Tester"})
check("practice starts with just a name", status == 200 and payload.get("practice_session_id"),
      str(payload))
practice_id = payload["practice_session_id"]

status, payload, _ = cadet.get("/api/practice/next?practice_session_id=999999")
check("an unknown practice session is refused", status == 400, str(status))
status, payload, _ = cadet.get("/api/practice/next?practice_session_id=%d" % practice_id)
check("practice deals a question to guests", status == 200 and "question" in payload,
      str(payload)[:120])
first_q = payload["question"]["id"]

before = admin.get("/api/stats")[1]["overall"]
status, payload, _ = cadet.post(
    "/api/practice/attempts",
    {"practice_session_id": practice_id, "question_id": first_q, "correct": True})
check("a practice answer records", status == 200 and payload["session"]["asked"] == 1,
      str(payload))
after = admin.get("/api/stats")[1]["overall"]
check("practice leaves the squadron scoreboard untouched",
      after == before, "%s vs %s" % (after, before))

approved = admin.get("/api/questions/counts")[1]["counts"]["approved"]
seen = {first_q}
status, payload = 200, {}
for _ in range(approved + 5):
    status, payload, _ = cadet.get("/api/practice/next?practice_session_id=%d" % practice_id)
    if status != 200:
        break
    qid = payload["question"]["id"]
    seen.add(qid)
    cadet.post("/api/practice/attempts",
               {"practice_session_id": practice_id, "question_id": qid, "correct": True})
check("practice asks each active question once", len(seen) == approved,
      "%d seen vs %d approved" % (len(seen), approved))
check("a finished bank ends practice cleanly",
      status == 409 and payload.get("reason") == "exhausted", str(payload))

status, payload, _ = cadet.post("/api/practice/finish", {"practice_session_id": practice_id})
check("finishing practice scores the run",
      status == 200 and payload["finished"] and payload["session"]["asked"] == approved,
      str(payload))

status, payload, _ = staff_live.get("/api/admin/practice-sessions")
check("staff/NCO cannot see practice results", status == 403, str(status))
status, payload, _ = guest.get("/api/admin/practice-sessions")
check("guests cannot see practice results", status == 401, str(status))
status, payload, _ = admin.get("/api/admin/practice-sessions")
mine = [s for s in payload["sessions"] if s["name"] == "Practice Tester"]
check("the admin sees the finished run",
      status == 200 and len(mine) == 1 and mine[0]["asked"] == approved, str(payload)[:200])
detail_id = mine[0]["id"]
status, payload, _ = admin.get("/api/admin/practice-sessions/%d" % detail_id)
bank = {q["id"]: q for q in admin.get("/api/questions?status=approved")[1]["questions"]}
check("the run opens with every question and answer",
      status == 200 and len(payload["attempts"]) == approved
      and all(a["question_text"] == bank[a["question_id"]]["question_text"]
              and a["answer_text"] == bank[a["question_id"]]["answer_text"]
              for a in payload["attempts"]),
      str(status))
check("practice answers never leak into squadron history",
      admin.get("/api/stats")[1]["overall"] == before, "squadron totals moved")
status, payload, _ = admin.post(
    "/api/admin/practice-sessions/%d/delete" % detail_id, {})
check("deleting without confirmation is refused", status == 400, str(status))
status, payload, _ = admin.post(
    "/api/admin/practice-sessions/%d/delete" % detail_id, {"confirm": True})
check("the admin can delete the run", status == 200, str(payload))
check("the deleted run is gone",
      all(s["id"] != detail_id
          for s in admin.get("/api/admin/practice-sessions")[1]["sessions"]))
    ''',
    40: r'''
print("\n[37] anyone can report a wrong question")
status, payload, _ = cadet.post("/api/practice/start", {"name": "Reporter Cadet"})
rep_id = payload["practice_session_id"]
status, payload, _ = cadet.get("/api/practice/next?practice_session_id=%d" % rep_id)
rep_q = payload["question"]["id"]
status, payload, _ = cadet.post(
    "/api/questions/%d/report" % rep_q, {"reason": "guest thinks this is wrong"})
check("a nameless guest report is refused", status == 400, str(status))
status, payload, _ = cadet.post(
    "/api/questions/%d/report" % rep_q,
    {"reason": "guest thinks this is wrong", "reporter_name": "Reporter Cadet"})
check("a named guest report is accepted", status == 200, str(payload))
status, payload, _ = cadet.post(
    "/api/questions/%d/report" % rep_q,
    {"reason": "again", "reporter_name": "Reporter Cadet"})
check("the same guest cannot report twice", status == 409, str(status))
status, payload, _ = admin.get("/api/admin/reports?status=pending")
guest_reports = [r for r in payload["reports"]
                 if r["question_id"] == rep_q and r["reporter_name"] == "Reporter Cadet"]
check("the guest report reaches the admin queue", len(guest_reports) == 1,
      str(len(payload["reports"])))
check("staff reporting still uses the account name",
      staff_live.post("/api/questions/%d/report" % rep_q, {"reason": "nco report"})[0] == 200)
    ''',
    41: r'''
print("\n[38] the practice page stands apart from the squadron page")
check("practice has its own nav entry", 'data-view="practice"' in served_index)
check("practice results are admin only",
      'data-view="practice-results"' in served_index and "admin-only" in served_index)
check("the practice view exists", 'id="view-practice"' in served_index)
check("the practice results view exists", 'id="view-practice-results"' in served_index)
check("practice carries a solo banner", "practice-notice" in served_index
      and "SOLO PRACTICE" in served_index, "no solo marker")
check("practice uses its own card style", "practice-card" in served_index
      and "practice-card" in css, "no distinct card")
check("practice buttons speak to the individual",
      "Got it right" in served_index and "Got it wrong" in served_index
      and "Finish practice" in served_index, "same wording as the squadron page")
check("practice asks for a name first", 'id="practice-name"' in served_index
      and "Enter your name" in served_index, "no name gate")
check("practice offers the same report menu", 'id="practice-report-btn"' in served_index
      and "Report incorrect question" in served_index, "no report option")
check("practice result rows reuse the answered styling",
      "sessionAttemptItem" in app_js and "loadPracticeResults" in app_js,
      "no results rendering")
    ''',
}
