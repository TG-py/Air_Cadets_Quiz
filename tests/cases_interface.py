"""End-to-end cases grouped by interface."""

SECTIONS = {
    24: r'''
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
    ''',
    25: r'''
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
for view in ("quiz", "practice", "submit", "stats", "progress-trends", "sessions",
             "practice-stats", "practice-trends", "practice-results",
             "board", "website-issues", "users"):
    check("menu still offers the %s view" % view, 'data-view="%s"' % view in index_html)
check("menu can be opened and closed", "setMenuOpen" in app_js)
check("redundant close button is removed", 'id="menu-close"' not in index_html
      and 'el("menu-close")' not in app_js)
check("escape closes the menu", 'event.key === "Escape"' in app_js)
check("choosing a view closes the menu", "setMenuOpen(false)" in app_js)
check("toggle reports expanded state", 'aria-expanded' in index_html and "aria-expanded" in app_js)

css = open(os.path.join(ROOT, "static", "style.css"), encoding="utf-8").read()
check("quiz buttons all share the same top margin",
      "margin: 0" in css.split(".controls > button")[1].split("}")[0])
check("form submit buttons keep their spacing",
      "margin-top: .65rem" in css.split(".primary {")[1].split("}")[0])
    ''',
    26: r'''
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

check("application canvas uses the light palette", "background: var(--bg)" in css)
check("page background is local, not a remote asset", "url(http" not in css and "url(https" not in css)
check("the interface does not depend on a photograph", "plane.jpg" not in css)
    ''',
    27: r'''
print("\n[26] progress and review text sits in boxes")
stats_view = index_html.split('id="view-stats"')[1].split("</section>")[0]
review_view = index_html.split('id="view-review"')[1].split("</section>")[0]

check("text-box style defined", ".text-box {" in css)
check("stat tiles share the card treatment",
      ".text-box, .stat {" in css and "border: 1px solid var(--line)" in css.split(".text-box, .stat {")[1].split("}")[0])
check("progress hint is boxed", 'class="hint text-box"' in stats_view)
check("progress empty message is boxed", 'id="stats-empty" hidden>No questions have been asked yet.' in stats_view
      and "muted text-box" in stats_view)
check("overall stats no longer wrapped in a card", "card stat-row" not in stats_view)
check("review summary is boxed", 'id="review-summary"' in review_view and "hint text-box" in review_view)
check("review empty message is boxed", "muted text-box" in review_view)
for heading in ("<h2>Squadron progress</h2>", "<h2>Review submitted questions</h2>"):
    check("title left unboxed: %s" % heading, heading in index_html)
    ''',
    28: r'''
print("\n[27] quiz buttons use semantic solid styles")
check("skip button is solid amber", 'class="warn" id="skip-btn"' in index_html)
check("correct button is solid green", 'class="success" id="correct-btn"' in index_html)
check("incorrect button is solid red", 'class="danger" id="incorrect-btn"' in index_html)
check("finish button is solid blue", 'class="primary" id="finish-btn"' in index_html)
check("practice reveal keeps a neutral style", 'class="secondary" id="practice-reveal-btn"' in index_html)
check("the empty-state finish matches too", 'class="primary" id="quiz-empty-finish"' in index_html)
check("solid amber defined", ".warn {" in css)
check("solid neutral defined", ".secondary, .ghost" in css)
check("solid green defined", ".success {" in css)
check("solid red defined", ".danger, .no {" in css)
check("the controls share one button height", "min-height: 44px" in css.split(".controls > button")[1].split("}")[0])
check("no boxed wrapper around the buttons", "quiz-actions" not in index_html and "quiz-actions" not in css)
check("no washed-out tints remain", ".ghost-warn" not in css and ".ghost-accent" not in css)
check("menu toggle is a symbol, not words",
      'id="menu-toggle"' in index_html
      and ">Menu</button>" not in index_html
      and "&#9776;" in index_html.split('id="side-menu"')[0])
check("menu toggle keeps an accessible name", 'aria-label="Open menu"' in index_html)
    ''',
    29: r'''
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
    ''',
    35: r'''
print("\n[33] no browser prompt boxes remain")
check("no window.prompt calls remain", "window.prompt(" not in app_js, "still prompting")
check("no browser confirm or alert calls remain",
      "window.confirm(" not in app_js and "window.alert(" not in app_js, "still using browser popups")
check("confirmations use an in-page dialog",
      "function confirmAction(" in app_js and "confirmAction({" in app_js, "no confirm dialog")
check("an in-page dialog is used instead",
      "function askForValues(" in app_js and "dialog.showModal()" in app_js, "no dialog helper")
check("the dialog can be cancelled or escaped away",
      'dialog.addEventListener("cancel"' in app_js, "no escape handling")
check("the dialog builds real input fields",
      'document.createElement(field.rows ? "textarea" : "input")' in app_js, "no inputs")
check("the edit dialog offers the known topics",
      'list: "known-topics"' in app_js, "no topic suggestions when editing")
check("the dialog is styled", ".modal-form" in css and ".modal::backdrop" in css, "no dialog styling")
    ''',
    36: r'''
print("\n[33b] the two dialog buttons match")
check("cancel is a styled button, not a bare one",
      'cancel.className = "ghost"' in app_js, "cancel button is unstyled")
check("the confirm button is still the primary one",
      'submit.className = "primary"' in app_js, "submit lost its primary class")
button_base = css.split(".primary, .secondary, .ghost")[1].split("}")[0]
check("both buttons share the same padding",
      bool(button_base) and "padding: .62rem .9rem;" in button_base, button_base)
check("both buttons share the same weight",
      bool(button_base) and "font-weight: 700;" in button_base, button_base)
check("the stacked-layout margin is cancelled inside the dialog row",
      ".modal-actions .primary," in css and ".modal-actions .ghost {" in css,
      "margin-top would offset the pair")
    ''',
    43: r'''
print("\n[40] action feedback and keyboard accessibility")
app_js = open(os.path.join(ROOT, "static", "app.js"), encoding="utf-8").read()
css = open(os.path.join(ROOT, "static", "style.css"), encoding="utf-8").read()
index_html = open(os.path.join(ROOT, "static", "index.html"), encoding="utf-8").read()
check("in-flight actions disable their control", "control.disabled = true" in app_js)
check("busy actions expose their state", 'setAttribute("aria-busy", "true")' in app_js
      and 'button[aria-busy="true"]::after' in css)
check("question options use disclosure semantics", 'aria-controls="question-menu"' in index_html
      and 'role="menuitem"' not in index_html)
check("mobile question editor traps keyboard focus", "document.activeElement === first" in app_js
      and "document.activeElement === last" in app_js)
check("page navigation does not select or focus the destination heading",
      "heading.focus" not in app_js and "focusHeading" not in app_js)
check("progress trends page is admin-only", 'class="view admin-only" id="view-progress-trends"' in index_html)
check("the website issue form has its own page", 'id="view-report-issue"' in index_html
      and 'id="website-issue-form"' in index_html)
check("the website issue form does not ask for a name", 'id="website-issue-name"' not in index_html)
check("the menu offers website issue reporting", 'id="issue-menu-btn"' in index_html
      and 'aria-label="Website issue options"' in index_html
      and 'id="issue-menu"' in index_html and 'id="issue-report-btn"' in index_html)
check("the issue report button opens the form from its menu option",
      'el("issue-report-btn")' in app_js and 'setView("report-issue")' in app_js
      and 'state.issueOriginView' in app_js)
check("admins get a separate website issue page", 'id="view-website-issues"' in index_html
      and 'id="website-issues-nav"' in index_html and 'data-view="website-issues"' in index_html)
website_issues_js = app_js.split("async function loadWebsiteIssues(")[1].split("\nasync function ")[0]
check("website issue reports use one list with delete buttons",
      "Handled reports" not in index_html and 'id="website-issues-pending"' not in index_html
      and "Mark fixed" not in website_issues_js and 'Delete report' in website_issues_js)
set_view = app_js.split("function setView(")[1].split("\nfunction ")[0]
check("view switching clears stale banners", "clearBanners();" in set_view)
check("view switching closes question menus", "closeDotsMenus();" in set_view)
check("view switching closes open dialogs", 'dialog[open]' in set_view and "dialog.close()" in set_view)
check("view switching closes the navigation drawer", "setMenuOpen(false);" in set_view)
check("view switching hides the previous view", 'section.id !== "view-" + name' in set_view)
check("admin navigation tabs stay available on every view", "syncAdminNav" not in app_js
      and 'id="progress-trends-nav"' in index_html and 'id="website-issues-nav"' in index_html)
check("identity refreshes do not unhide admin-only page sections",
      'querySelectorAll(".admin-only:not(.view)")' in app_js)
    ''',
    44: r'''
print("\n[41] website issue reporting")
issue_guest = Client()
status, payload, _ = issue_guest.get("/api/auth/me")
issue_guest.csrf = payload["csrf"]
status, payload, _ = issue_guest.post(
    "/api/website-issues",
    {"title": "Broken link", "details": "The link does not open.", "page": "practice"},
)
check("a visitor can report a website issue", status == 200 and payload.get("id"), str(payload))
issue_id = payload.get("id")
status, payload, _ = issue_guest.post(
    "/api/website-issues", {"title": "   ", "details": "missing title"}
)
check("a blank website issue title is refused", status == 400, str(status))
status, payload, _ = issue_guest.get("/api/admin/website-issues")
check("visitors cannot read website issue reports", status in (401, 403), str(status))
status, payload, _ = staff_live.get("/api/admin/website-issues")
check("staff cannot read website issue reports", status == 403, str(status))
status, payload, _ = admin.get("/api/admin/website-issues")
found = [issue for issue in payload.get("issues", []) if issue["id"] == issue_id]
check("an admin sees the website issue", status == 200 and len(found) == 1, str(payload)[:200])
check("the report keeps its page and anonymous status",
      bool(found) and found[0]["page"] == "practice" and found[0]["reported_by"] is None,
      str(found[:1]))
status, payload, _ = staff_live.post("/api/admin/website-issues/%d/delete" % issue_id)
check("staff cannot delete website issue reports", status == 403, str(status))
status, payload, _ = admin.post("/api/admin/website-issues/%d/delete" % issue_id)
check("an admin can delete a website issue", status == 200, str(payload))
status, payload, _ = admin.get("/api/admin/website-issues")
deleted = [issue for issue in payload.get("issues", []) if issue["id"] == issue_id]
check("a deleted website issue leaves the list", status == 200 and not deleted, str(payload)[:200])
status, payload, _ = admin.post("/api/admin/website-issues/%d/delete" % issue_id)
check("a deleted website issue cannot be deleted twice", status == 404, str(status))
    ''',
}
