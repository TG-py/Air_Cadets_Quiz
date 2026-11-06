"""End-to-end cases grouped by question workflows."""

SECTIONS = {
    3: r'''

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
    
    ''',
    4: r'''

print("\n[4] topics available to guests for the dropdown")
status, payload, _ = guest.get("/api/topics")
check("guest can list topics", status == 200, str(status))
check("pending topics offered too", "Motto" in payload.get("topics", []), str(payload.get("topics")))
    
    ''',
    5: r'''

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
    
    ''',
    8: r'''

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
    
    ''',
    19: r'''

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
    
    ''',
    20: r'''

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
    
    ''',
    22: r'''

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
    
    ''',
    23: r'''

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
    
    ''',
    30: r'''
def _legacy_bank_case():
    print("\n[28] legacy bank view checks are retired")
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
            ["node", bank_path, combined_app_path()],
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
          buttons.get("PENDINGBTNS") == "Accept,Flag out of date,Edit,Delete", buttons.get("PENDINGBTNS", "none"))
    check("an accepted question in the bank can be removed, archived, edited and deleted",
          buttons.get("APPROVEDBTNS") == "Remove from quiz,Archive,Flag out of date,Edit,Delete",
          buttons.get("APPROVEDBTNS", "none"))
    check("a rejected question in the bank can be accepted, edited and deleted",
          buttons.get("REJECTEDBTNS") == "Accept,Flag out of date,Edit,Delete", buttons.get("REJECTEDBTNS", "none"))
    check("an archived question in the bank can be restored, edited and deleted",
          buttons.get("ARCHIVEDBTNS") == "Restore to quiz,Edit,Delete",
          buttons.get("ARCHIVEDBTNS", "none"))
    check("the bank edit button calls the edit handler",
          buttons.get("EDITWIRING") == "true", buttons.get("EDITWIRING", "none"))
    
    ''',
    33: r'''

print("\n[31] wording and the add-question topic")
app_py = open(os.path.join(ROOT, "app.py"), encoding="utf-8").read()
readme = open(os.path.join(ROOT, "README.md"), encoding="utf-8").read()
for bad in ("Staff accounts", "staff accounts", "staff account"):
    check('no "%s" wording anywhere' % bad,
          bad not in served_index and bad not in app_js and bad not in readme, bad)
check("the accounts page says staff/NCO", "Staff/NCO accounts" in served_index, "wording not updated")
check("the login link says staff/NCO", "Staff/NCO login" in served_index, "wording not updated")
check("the staff-only error mentions staff/NCO", "staff/NCO only" in app_py
      or "staff/NCO only" in open(os.path.join(ROOT, "api_questions.py"), encoding="utf-8").read(),
      "wording not updated")
check("General is not offered when adding a question",
      'state.topics, "General", true' not in app_js, "General is still a dropdown option")
check("a topic must be chosen", 'id="bank-topic" aria-label="Topic" required' in served_index,
      "the topic select is not required")
check("an untopiced question is refused rather than filed as General",
      'Choose a topic for the question.' in app_js and '|| "General"' not in app_js,
      "a General fallback is still in the add path")
    
    ''',
    38: r'''

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
    
    ''',
    42: r'''

print("\n[39] combined AI question checks and proposal decisions")
current_index = index_source()
current_js = app_source()
check("reports and flagged updates share one page", 'id="view-checks"' in current_index
      and 'id="checks-prompt-btn"' in current_index)
check("whole-bank AI check is removed", 'data-view="scan"' not in current_index
      and 'id="view-scan"' not in current_index and "makeScanPrompt" not in current_js)
check("combined results use the dedicated endpoint", "/api/admin/question-check-review" in current_js)
check("AI approval offers both tag choices and reject", "Accept without future-update tag" in current_js
      and "Accept and mark for future update" in current_js and "Reject AI proposal" in current_js)

def add_admin_question(text):
    status, payload, _ = admin.post("/api/questions", {
        "question_text": text, "answer_text": "Original answer", "topic": "AI workflow tests",
    })
    check("create AI workflow question", status == 200 and payload.get("id") is not None, str(payload))
    return payload.get("id")

def combined_result(question_id, action, report_ids="", question=None, answer=None):
    fields = [question_id, report_ids, action, question or "", answer or "", "AI workflow tests", "test reason"]
    quoted = ['"%s"' % str(value).replace('"', '""') for value in fields]
    csv_text = "id,report_ids,action,question,answer,topic,reason\n" + ",".join(quoted)
    return admin.post("/api/admin/question-check-review", {"content": csv_text})

update_id = add_admin_question("AI update proposal test question")
status, payload, _ = admin.post("/api/questions/%d/report" % update_id, {"reason": "The answer may be wrong"})
check("admin can report test question", status == 200, str(payload))
status, payload, _ = admin.get("/api/admin/reports?status=pending&limit=5000")
update_report_ids = [str(r["id"]) for r in payload["reports"] if r["question_id"] == update_id]
check("combined queue includes pending reports", len(update_report_ids) == 1, str(update_report_ids))
status, payload, _ = combined_result(update_id, "update", ";".join(update_report_ids),
                                     "AI corrected test question", "Corrected answer")
check("combined update stages an AI proposal", status == 200 and payload.get("staged") == 1, str(payload))
pending_ai = admin.get("/api/admin/stale")[1]["ai_questions"]
update_proposal = next((q for q in pending_ai if q["id"] == update_id), None)
check("proposal appears on AI approval page", update_proposal is not None, str(update_proposal))
status, payload, _ = admin.post("/api/admin/questions/%d/accept-ai" % update_id, {"outdated": True})
check("AI proposal can be accepted with future tag", status == 200, str(payload))
accepted_update = next((q for q in admin.get("/api/questions?status=approved")[1]["questions"]
                        if q["id"] == update_id), None)
check("tagged acceptance applies corrected fields and future tag",
      accepted_update is not None and accepted_update["question_text"] == "AI corrected test question"
      and accepted_update["outdated"], str(accepted_update))

flag_id = add_admin_question("AI future flag test question")
status, payload, _ = combined_result(flag_id, "flag")
check("combined results can apply the future tag", status == 200 and payload.get("marked") == 1, str(payload))
check("future-tagged question appears in flagged queue",
      any(q["id"] == flag_id for q in admin.get("/api/admin/stale")[1]["questions"]))

review_id = add_admin_question("AI human review test question")
status, payload, _ = combined_result(review_id, "review")
check("uncertain combined result enters human review", status == 200 and payload.get("sent_to_human") == 1,
      str(payload))
check("manual-review question appears in human queue",
      any(q["id"] == review_id for q in admin.get("/api/admin/stale")[1]["review_questions"]))

ok_id = add_admin_question("AI stable question test")
admin.post("/api/admin/questions/%d/stale" % ok_id, {"tagged": True})
status, payload, _ = combined_result(ok_id, "ok")
check("stable combined result clears the future tag", status == 200 and payload.get("marked") == 0
      and all(q["id"] != ok_id for q in admin.get("/api/admin/stale")[1]["questions"]), str(payload))

dismiss_id = add_admin_question("AI report dismissal test question")
pending_report_count_before_dismiss = admin.get("/api/admin/reports?status=pending")[1]["report_count"]
admin.post("/api/questions/%d/report" % dismiss_id, {"reason": "No action needed"})
reports = admin.get("/api/admin/reports?status=pending&limit=5000")[1]["reports"]
dismiss_report = next(r for r in reports if r["question_id"] == dismiss_id)
status, payload, _ = combined_result(dismiss_id, "dismiss", str(dismiss_report["id"]))
check("combined dismiss closes a report", status == 200
      and payload.get("report_count") == pending_report_count_before_dismiss, str(payload))

no_tag_id = add_admin_question("AI accept without tag test question")
status, payload, _ = admin.post("/api/admin/question-updates", {
    "content": "id,question,answer,topic\n%d,Accepted unchanged tag test,Accepted answer,AI workflow tests" % no_tag_id,
})
check("stage second proposal for no-tag acceptance", status == 200, str(payload))
status, payload, _ = admin.post("/api/admin/questions/%d/accept-ai" % no_tag_id, {"outdated": False})
check("AI proposal can be accepted without future tag", status == 200
      and all(q["id"] != no_tag_id for q in admin.get("/api/admin/stale")[1]["questions"]), str(payload))

reject_id = add_admin_question("AI rejection keeps original test question")
admin.post("/api/admin/question-updates", {
    "content": "id,question,answer,topic\n%d,Rejected changed version,Changed answer,AI workflow tests" % reject_id,
})
status, payload, _ = admin.post("/api/admin/questions/%d/reject-ai" % reject_id, {})
rejected_question = next(q for q in admin.get("/api/questions?status=approved")[1]["questions"]
                         if q["id"] == reject_id)
check("rejecting proposal preserves original question", status == 200
      and rejected_question["question_text"] == "AI rejection keeps original test question"
      and not rejected_question["ai_pending"], str(rejected_question))

forward_id = add_admin_question("AI forward to human test question")
admin.post("/api/admin/question-updates", {
    "content": "id,question,answer,topic\n%d,Human version,Human answer,AI workflow tests" % forward_id,
})
status, payload, _ = admin.post("/api/admin/questions/%d/send-to-human" % forward_id, {})
check("AI proposal can be forwarded to human review", status == 200
      and any(q["id"] == forward_id for q in admin.get("/api/admin/stale")[1]["review_questions"]), str(payload))
    
    ''',
}
