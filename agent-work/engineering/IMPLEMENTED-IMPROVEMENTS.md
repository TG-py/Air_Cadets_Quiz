# Implemented improvement record

This note records the improvements selected from the project review and their implemented behaviour. It is intended as working context for future agents. The source code and current interface remain authoritative if implementation details change.

## GUI improvements

### G3 — Progress trend charts

**Status: implemented.** The Progress area now includes a separate **Progress trends** page that is visible only to admins. It shows weekly counts of correct, incorrect, and skipped answers for the last 12 weeks, alongside a weekly accuracy chart. Accuracy uses correct and incorrect answers; skipped answers are excluded. Weeks with fewer than five scored answers are omitted from the accuracy series to avoid presenting a very small sample as a reliable trend. The page explains this threshold.

The browser view and chart rendering are in `static/index.html`, `static/app.js`, and `static/style.css`. Trend data is provided by the admin-only `/api/admin/progress-trends` endpoint in `api_admin.py`, registered through `api.py`.

### G4 — Clear feedback during requests

**Status: implemented.** The shared `api()` request wrapper in `static/app.js` marks the relevant action or form as busy while a request is pending, disables submit controls to prevent duplicate submissions, and shows a small spinner. It restores the prior disabled state after the request completes. The shared site banner continues to communicate request success and failure.

### G5 — Keyboard and focus support

**Status: implemented.** Changing views no longer selects or focuses the destination view heading. Navigation popovers use disclosure-button semantics with `aria-controls` and `aria-expanded`, rather than menu roles without the keyboard model those roles require. Escape closes a popover and returns focus to its trigger.

On mobile, opening the board editor focuses the question field and makes the background header/navigation inert. Tab and Shift+Tab stay within the editor, Escape cancels it, and closing restores focus to the control that opened it.

### In-page confirmation dialogs

**Status: implemented.** Consequential actions use a reusable in-page confirmation dialog instead of browser `confirm` boxes. This covers question deletion, archive and approval moves, discarding editor changes, resetting progress, deleting quiz sessions and practice runs, and deleting website issue reports. The dialog supports a title, explanatory message, confirm label, destructive or primary styling, Escape and Cancel handling.

### Practice answer reveal

**Status: implemented.** Each practice question starts with its answer hidden. The initial actions are Show answer, Skip and Finish practice. Revealing the answer replaces Show answer and Skip with Got it right and Got it wrong, so the self-assessment is recorded only after the answer has been seen. The revealed state is reset for every new question.

Practice draws from the same squadron-weighted pool as the main quiz. Practice answers remain in the separate practice tables, so they never alter squadron progress, question weights, or any data outside the existing individual practice scores and results.

### Question board editing reliability

**Status: implemented.** Selecting text inside the expanded card's question, answer, topic, or action controls no longer starts a card drag, so normal text selection works. Dragging the card outside those controls still saves it to a column.

Saving an edit now refreshes the board while the editor is still open, then removes the editor only after the refresh succeeds. This prevents a stale card from being restored after a move. Dropping the expanded card into a column immediately shows it in that column and returns the dashed edit box while the save completes. If saving or refreshing fails, the preview is removed and the editor reopens with the entered text so the admin can retry. Focus returns to the saved question's new card when it remains visible.

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

### HTTP keep-alive request-body handling

**Status: implemented.** `webserver.QuizHandler` now drains any request body a handler did not read before the connection is reused (`consume_body`, called from `dispatch`'s `finally`), and closes the connection when the body is invalid or oversized instead of leaving it unread. Responses such as 401/403/404/405 are sent before the body is parsed, so on an HTTP/1.1 keep-alive connection the unread bytes were previously mistaken for the next request line. This caused the reported failure where logging out appeared to leave the server unresponsive: the `pagehide` finish request is rejected after the session cookie is cleared, and its unread body corrupted the connection reused for the reloaded page. A new end-to-end case sends a rejected keep-alive POST followed by a request on the same socket and checks that the second request is understood.

### Website issue reporting

**Status: implemented.** A three-dots button beside the menu title opens a menu with a **Report a website issue** option, which opens the report form for visitors and signed-in staff. The form asks only for a title and details, and records the originating page. The admin-only **Website issue reports** page shows all reports in one list with a delete button for each report. The database migration advances the schema to version 2.

### Page switching cleanup

**Status: implemented.** Switching views clears shared status banners and closes question menus and open dialogs. Admin navigation tabs remain visible on every view. Identity and board refreshes only reveal admin-only controls, not admin-only page sections, so the Progress trends and Website issue reports pages cannot appear alongside All questions.

### Practice auto-save and reporting

**Status: implemented.** Leaving the practice view, or closing/reloading the page, closes the active practice run and saves it. In-app navigation posts the finish request and refreshes Practice results when that page is open; page unload uses a keepalive request so the score is not lost. Empty runs are still discarded by the existing finish rule.

Practice results are grouped by the practised name. Names sort alphabetically, and runs within a name sort newest first by their saved date and time. Each run keeps its existing open/delete controls.

Admin practice reporting now mirrors the squadron reporting pages. **Overall practice data** shows practice-only totals, per-topic statistics, and per-question accuracy. **Practice trends** shows the same 12-week volume and accuracy charts using practice answers only. The Progress navigation is split into expandable **Squadron progress** and **Practice progress** groups.

### Agent documentation structure

**Status: implemented.** The agent notes are grouped under `agent-work/` by purpose — `product/`, `ui/`, and `engineering/` — with an index in `agent-work/README.md` and a root `AGENTS.md` entry point. The code map, API map, and change guidance moved out of the product guide into `engineering/ARCHITECTURE.md` so each note has one job. Documentation links were updated to the new paths.

## Verification status

The changes above are implemented and were checked with the repository's end-to-end suite on 20 October 2026. The runner completed all 452 checks with no failures, including the website issue API workflow, schema migration, page-switching cleanup, menu-based issue reporting, report deletion, in-page confirmations, the practice reveal flow, practice auto-save and grouped results, practice overall/trend reporting, Progress trends access checks, question-board editor drag/save behaviour, and keep-alive handling after a rejected POST. The suite starts its own server and temporary database on port 8099. Interface assertions from the retired bank/review navigation were updated to match the current question-board design, and the suite now compiles and runs every registered case.
