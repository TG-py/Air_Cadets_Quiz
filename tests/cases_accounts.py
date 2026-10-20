"""End-to-end cases grouped by accounts."""

SECTIONS = {
    6: r'''
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
    ''',
    15: r'''
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
    ''',
    16: r'''
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
    ''',
    31: r'''
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
reset_js = app_js.split("async function resetProgress(")[1].split("\nasync function ")[0]
check("progress reset asks twice", reset_js.count("await confirmAction({") >= 2,
      "expected a double in-page confirm")

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
    ''',
    32: r'''
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
    ''',
    34: r'''
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
    ''',
    37: r'''
def _run_users_case():
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

_run_users_case()
    ''',
}
