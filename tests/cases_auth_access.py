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
}
