"""End-to-end cases grouped by auth access."""

SECTIONS = {
    1: r'''
print("\n[1] anonymous access")
status, payload, _ = admin.get("/api/auth/me")
check("me returns 200 for guests", status == 200, str(status))
check("guest has no user", payload.get("user") is None, str(payload.get("user")))
check("guest gets csrf token", bool(payload.get("csrf")))
admin.csrf = payload["csrf"]
check("bank is empty", payload["counts"]["approved"] == 0, str(payload["counts"]))

status, payload, _ = guest.get("/api/auth/me")
guest.csrf = payload["csrf"]
    ''',
    2: r'''
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
    ''',
    17: r'''
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
check("no inline script in index", "<script>" not in body, "inline script found")
check("no cadet name field in the ask view", "cadet-select" not in body and "add-cadet-btn" not in body, "cadet controls still present")
check("no start button in the ask view", "start-quiz-btn" not in body, "start button still present")
status, body, headers = admin.request("GET", "/static/style.css", raw=True)
check("stylesheet served", status == 200 and ":root" in body, str(status))
status, body, headers = admin.request("GET", "/static/app-core.js", raw=True)
check("shared script served", status == 200 and "csrf" in body, str(status))
status, body, headers = admin.request("GET", "/static/app-admin.js", raw=True)
check("admin script served to an admin", status == 200 and "/api/admin/" in body, str(status))
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
    ''',
    18: r'''
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
    ''',
    47: r'''
print("\n[47] role-based frontend delivery")
asset_staff = Client()
status, payload, _ = asset_staff.get("/api/auth/me")
asset_staff.csrf = payload["csrf"]
status, payload, _ = asset_staff.post(
    "/api/auth/login", {"username": "nco1", "password": "newpass12345"}
)
asset_staff.csrf = payload["csrf"]
check("a staff/NCO can log in for asset checks", status == 200, str(payload))

status, guest_index, headers = guest.request("GET", "/", raw=True)
check("guest index is served", status == 200, str(status))
check("guest gets only the core script",
      "/static/app-core.js" in guest_index
      and "/static/app-staff.js" not in guest_index
      and "/static/app-admin.js" not in guest_index, guest_index[-300:])
check("guest gets no staff quiz page", 'id="view-quiz"' not in guest_index)
check("guest gets no admin pages",
      all(marker not in guest_index for marker in
          ('id="view-board"', 'id="view-users"', 'id="view-stats"', 'id="view-checks"')),
      "admin markup leaked")
check("guest keeps the public pages",
      all(marker in guest_index for marker in
          ('id="view-practice"', 'id="view-submit"', 'id="view-report-issue"')))
check("index tells caches the response depends on the cookie",
      "Cookie" in headers.get("Vary", ""), str(headers.get("Vary")))

status, staff_index, _ = asset_staff.request("GET", "/", raw=True)
check("staff index is served", status == 200, str(status))
check("staff gets the quiz page", 'id="view-quiz"' in staff_index)
check("staff gets core and staff scripts, not admin",
      "/static/app-core.js" in staff_index and "/static/app-staff.js" in staff_index
      and "/static/app-admin.js" not in staff_index, "wrong staff scripts")
check("staff gets no admin pages",
      'id="view-board"' not in staff_index and 'id="view-users"' not in staff_index)

status, admin_index, _ = admin.request("GET", "/", raw=True)
check("admin index is served", status == 200, str(status))
check("admin gets every role script",
      all(name in admin_index for name in
          ("/static/app-core.js", "/static/app-staff.js", "/static/app-admin.js")))
check("admin gets the admin pages",
      'id="view-board"' in admin_index and 'id="view-users"' in admin_index)

for path in ("/static/app-staff.js", "/static/app-admin.js"):
    status, _, _ = guest.request("GET", path, raw=True)
    check("guest cannot fetch %s" % path, status == 404, str(status))
status, _, _ = asset_staff.request("GET", "/static/app-admin.js", raw=True)
check("staff/NCO cannot fetch the admin script", status == 404, str(status))
status, staff_asset, headers = asset_staff.request("GET", "/static/app-staff.js", raw=True)
check("staff/NCO can fetch the staff script", status == 200 and "loadNextQuestion" in staff_asset, str(status))
check("role script is not cached across sessions",
      "Cookie" in headers.get("Vary", "") and headers.get("Cache-Control") == "no-store",
      str(sorted(headers)))
status, core_asset, _ = guest.request("GET", "/static/app-core.js", raw=True)
check("core script excludes admin api calls", status == 200 and "/api/admin/" not in core_asset, str(status))
status, admin_asset, _ = admin.request("GET", "/static/app-admin.js", raw=True)
check("admin script includes admin api calls", status == 200 and "/api/admin/" in admin_asset, str(status))

for path in ("/static/views/admin.html", "/static/nav/admin.html",
             "/static/index.html", "/static/app.js"):
    status, _, _ = admin.request("GET", path, raw=True)
    check("partial or legacy source %s is never served" % path, status == 404, str(status))
    ''',
}
