# Implemented improvement record

This note records the improvements selected from the project review and their implemented behaviour. It is intended as working context for future agents. The source code and current interface remain authoritative if implementation details change.

## GUI improvements

### G3 — Progress trend charts

**Status: implemented.** The Progress area now includes a separate **Progress trends** page that is visible only to admins. It shows weekly counts of correct, incorrect, and skipped answers for the last 12 weeks, alongside a weekly accuracy chart. Accuracy uses correct and incorrect answers; skipped answers are excluded. Weeks with fewer than five scored answers are omitted from the accuracy series to avoid presenting a very small sample as a reliable trend. The page explains this threshold.

The browser view and chart rendering are in `static/index.html`, `static/app.js`, and `static/style.css`. Trend data is provided by the admin-only `/api/admin/progress-trends` endpoint in `api_admin.py`, registered through `api.py`.

### G4 — Clear feedback during requests

**Status: implemented.** The shared `api()` request wrapper in `static/app.js` marks the relevant action or form as busy while a request is pending, disables submit controls to prevent duplicate submissions, and shows a small spinner. It restores the prior disabled state after the request completes. The shared site banner continues to communicate request success and failure.

### G5 — Keyboard and focus support

**Status: implemented.** Changing views moves keyboard focus to the destination view heading. Navigation popovers use disclosure-button semantics with `aria-controls` and `aria-expanded`, rather than menu roles without the keyboard model those roles require. Escape closes a popover and returns focus to its trigger.

On mobile, opening the board editor focuses the question field and makes the background header/navigation inert. Tab and Shift+Tab stay within the editor, Escape cancels it, and closing restores focus to the control that opened it.

## Backend improvements

### B3 — Explicit database schema versioning

**Status: implemented.** `db.py` defines schema version 2 and reads/writes SQLite's `PRAGMA user_version`. Legacy databases are migrated within a transaction; the version stamp advances only after each migration succeeds. Startup refuses a database stamped with a newer version than the application supports. Migration start, completion, and failure are logged. Critical migration errors are no longer silently swallowed; unsupported legacy column removals are logged. Version 2 adds persistent website issue reports.

### B4 — Split backend responsibilities into modules

**Status: implemented.** The former all-in-one server module is now divided by responsibility:

| Module | Responsibility |
| --- | --- |
| `app.py` | Application startup and initial admin setup |
| `api.py` | Route registration and access requirements |
| `api_common.py` | Shared API context, validation, and error handling |
| `api_auth.py` | Authentication and squad quiz endpoints |
| `api_questions.py` | Question submission and reporting endpoints |
| `api_practice.py` | Individual practice endpoints |
| `api_admin.py` | Admin workflows, including progress trends |
| `webserver.py` | HTTP transport, static files, security headers, and health endpoint |

The Docker image includes the split modules. `db.py` remains the owner of schema and database persistence.

### B7 — Production hosting and backup guidance

**Status: implemented.** `README.md` now covers deployment behind an HTTPS reverse proxy, keeping the app port off the public internet, secure-cookie settings, backups and restores, health checks, and logging. It also describes the implications of forwarded client IP headers for rate limiting. The project file map reflects the backend module split.

### B8 — Organize end-to-end scenarios by feature

**Status: implemented.** Feature scenarios are split into `tests/cases_auth_access.py`, `tests/cases_accounts.py`, `tests/cases_database.py`, `tests/cases_questions.py`, `tests/cases_quiz_progress.py`, and `tests/cases_interface.py`. `test_quiz.py` remains the runner and preserves the original execution order because scenarios share state and data. The cases include coverage for the admin trends endpoint, schema versioning, website issue reporting, page-switching cleanup, and interface feedback/accessibility behaviour.

### B9 — Runtime logs and database-aware health checks

**Status: implemented.** Python logging reports application startup, migration outcomes, request exceptions, HTTP errors, and startup failures. The `/healthz` endpoint performs a simple database query and returns HTTP 503 if database access fails. The Docker health check uses `/healthz`.

### Website issue reporting

**Status: implemented.** A three-dots button beside the menu title opens a website issue form for visitors and signed-in staff. Reports store a title, details, originating page, optional reporter name, and status in a separate SQLite table. The admin-only **Website issue reports** page lists open and handled reports and lets admins mark an issue fixed or dismiss it. The database migration advances the schema to version 2.

### Page switching cleanup

**Status: implemented.** Switching views clears shared status banners, closes question menus and open dialogs, and explicitly hides the Progress trends link while the All questions board is active. This prevents transient interface elements from carrying over between pages.

## Verification status

The changes above are implemented and were checked with the repository's end-to-end suite on 20 October 2026. The runner completed all 410 checks with no failures, including the new website issue API workflow, schema migration, page-switching cleanup, and Progress trends access checks. The suite starts its own server and temporary database on port 8099. Interface assertions from the retired bank/review navigation were updated to match the current question-board design, and the suite now compiles and runs every registered case.
