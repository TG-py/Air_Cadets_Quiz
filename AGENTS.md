# AGENTS.md

Guidance for AI agents working on RAFAC Questions, a self-hosted squadron
knowledge-check web app.

## What this project is

Python 3.9+ standard library and SQLite only. No third-party runtime
dependencies, no frontend build step. Staff run a weighted quiz for a squadron;
anyone can practise solo, submit questions, or report a problem. See
[`agent-work/product/FEATURE-GUIDE.md`](agent-work/product/FEATURE-GUIDE.md) for
roles, workflows, and product rules.

## Commands

```bash
python3 app.py                 # run on http://localhost:8001
python3 test_quiz.py           # full end-to-end suite (port 8099, temp DB)
python3 import_questions.py questions.csv --dry-run
docker compose up -d           # container deployment
```

`test_quiz.py` starts its own server and database, so it is safe to run at any
time. Run it after changing behaviour; the suite currently has 452 checks.

Set `ADMIN_PASSWORD` to avoid a generated first-run admin password. Other
settings are documented in the README.

## Layout

```
app.py            startup and first-run admin
webserver.py      HTTP transport, static files, cookies, auth/CSRF gate
api.py            route table (method, regex, handler, access)
api_common.py     request context, ApiError, validation helpers
api_auth.py       auth and squadron quiz routes
api_questions.py  question bank, board, submissions, review, reports
api_practice.py   solo practice routes
api_admin.py      admin reports, stats, users, sessions, CSV import
api_issues.py     website issue reports
auth.py           password hashing, sessions, CSRF, login throttling
db.py             schema, migrations, connection pool, all SQL
quiz.py           eligibility pool, weighting, selection
import_questions.py  CSV/JSON importer
static/           index.html, app.js, style.css, icons
tests/            feature case modules run by test_quiz.py
agent-work/       product, UI, and engineering notes for agents
```

Full module and request-lifecycle details:
[`agent-work/engineering/ARCHITECTURE.md`](agent-work/engineering/ARCHITECTURE.md).

## Non-negotiable conventions

- Keep the runtime dependency-free: standard library and SQLite only.
- All SQL belongs in `db.py` and must use bound parameters. Never interpolate
  user input into SQL.
- Render user text with `textContent`, never as HTML. The CSP blocks inline
  script and external assets.
- The server enforces access; hiding UI is not security. Non-GET API requests
  require a valid CSRF header (`X-CSRF-Token`).
- Only approved, unarchived questions with no pending report/AI/human-review
  flag are eligible for quiz/practice. Solo practice never affects squadron
  scores.
- AI output is untrusted: store/display as text and require explicit admin
  approval before applying it.
- Preserve element IDs, state classes, and `hidden` attributes used by
  `static/app.js`; they drive navigation, role gating, dialogs, and banners.
- If a handler may reject a request before reading its body, keep
  `dispatch`'s `consume_body()` drain in place. Unread bodies corrupt HTTP/1.1
  keep-alive connections (this caused the post-logout hang).
- No comments unless they explain non-obvious behaviour. Match the existing
  style.

## How to change things

- **API route:** add a handler in the matching `api_*.py`, register it in
  `api.py`, update `static/app.js`, add a test.
- **Schema:** update `SCHEMA` and add an idempotent migration guarded by
  `PRAGMA user_version`; bump `SCHEMA_VERSION`. Never edit a released migration.
- **Question state:** keep `board_state`, `status`, flags, and
  `quiz.build_pool` consistent. The board is the primary admin surface.
- **Tests:** add a new unique section number to the relevant
  `tests/cases_*.py`. Sections share seeded data and run in order.
- **UI:** read
  [`agent-work/ui/UI-DESIGN-RULES.md`](agent-work/ui/UI-DESIGN-RULES.md) and
  [`agent-work/ui/MOBILE-RESPONSIVE-DIFFERENCES.md`](agent-work/ui/MOBILE-RESPONSIVE-DIFFERENCES.md)
  first.

## Documentation

Start at [`agent-work/README.md`](agent-work/README.md). Keep docs current in the
same change that alters behaviour, routes, modules, or verification. Record
accepted work in
[`agent-work/engineering/IMPLEMENTED-IMPROVEMENTS.md`](agent-work/engineering/IMPLEMENTED-IMPROVEMENTS.md).
The README and hidden markup may contain historical labels; confirm current
behaviour in the code and the running interface.
