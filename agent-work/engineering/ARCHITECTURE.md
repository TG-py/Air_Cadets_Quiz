# Architecture and code map

How RAFAC Questions is put together and how to extend it safely. Read this
alongside [`../product/FEATURE-GUIDE.md`](../product/FEATURE-GUIDE.md), which
explains the product behaviour these modules implement.

## Stack

- Python 3.9+ standard library only. No third-party runtime dependencies.
- SQLite for persistence, accessed through `db.py`.
- Plain HTTP via `http.server.ThreadingHTTPServer`; static assets served from
  `static/`.
- The browser client is vanilla JavaScript split into `static/app-core.js`
  (shared and public), `static/app-staff.js` (squadron quiz), and
  `static/app-admin.js` (admin). `webserver.py` composes `static/index.html`
  from the shell plus `static/views/` and `static/nav/` partials, and only
  includes the scripts the signed-in role may use. No build step.

## Module map

| Module | Responsibility |
| --- | --- |
| `app.py` | Entry point: logging setup, `db.init()`, first-run admin bootstrap, server start |
| `webserver.py` | `QuizHandler`: routing to API or static files, security headers, cookies, auth/CSRF gate, body draining, JSON responses, `/healthz` |
| `api.py` | Route table: method, URL regex, handler, and access level. Compiled into `COMPILED` |
| `api_common.py` | `Ctx` request context, `ApiError`, field validation helpers |
| `api_auth.py` | `/api/auth/*` and squad quiz endpoints (`/api/quiz/*`, `/api/attempts`) |
| `api_questions.py` | Question bank, board, submissions, review, reports, AI staging |
| `api_practice.py` | Solo practice sessions and practice stats |
| `api_admin.py` | Admin reports, progress/stats, users, quiz-session admin, CSV import |
| `api_issues.py` | Website issue submission (public) and admin list/delete |
| `auth.py` | scrypt password hashing/verification, session tokens, CSRF, login rate limiting |
| `db.py` | Schema, `user_version` migrations, connection pool, all SQL |
| `quiz.py` | Eligibility pool, weighting, and random question selection |
| `import_questions.py` | CSV/JSON command-line importer (also used by the admin import route) |
| `test_quiz.py` | End-to-end runner; boots a server on a temporary database |
| `tests/` | Feature case modules executed by the runner |

## Request lifecycle

1. `webserver.QuizHandler.do_GET/do_POST/do_HEAD` set request state and call
   `dispatch(method)`.
2. `dispatch` composes the role-specific index for `/`, serves gated static
   files, handles `/healthz`, or, for `/api/*`, opens a pooled `db.connection()`
   and calls `handle_api`.
3. `handle_api` matches the first route in `api.COMPILED`, resolves the session
   and user from the cookie, enforces the route's access level, checks the CSRF
   header for non-GET requests, then reads the JSON body and calls the handler
   with a `Ctx`.
4. Handlers return a JSON-serialisable dict or raise `ApiError`. `dispatch`
   converts `ApiError` to a `{"error": ...}` response and logs unexpected
   exceptions as 500s.
5. `dispatch`'s `finally` calls `consume_body()` so any request body a handler
   did not read is drained before the connection is reused. Keep this: an
   unread body on an HTTP/1.1 keep-alive connection is parsed as the next
   request line and breaks the browser (this caused the post-logout
   "server doesn't respond" failure).

## Access model

Routes carry one of four access labels in `api.py`:

| Label | Meaning |
| --- | --- |
| `open` | No session or CSRF required |
| `csrf` | Any session, including a guest session, plus a valid CSRF token |
| `staff` | A signed-in user |
| `admin` | A signed-in user with the `admin` role |

Guest sessions are issued by `GET /api/auth/me` when no session exists. The
browser hides role-specific controls, but the server gate is the security
boundary; never rely on hiding a view.

The server also limits what frontend code is delivered. Anonymous visitors get
only the public views and `app-core.js`; staff/NCO sessions additionally get the
quiz view and `app-staff.js`; admins get the admin views and `app-admin.js`.
Requests for a role asset the session cannot use return 404, and the view/nav
partials are never served directly. This reduces information exposure but does
not replace the per-route access checks above.

## Route map

`api.py` is the complete list with access labels; this groups it by feature.

| Area | Routes |
| --- | --- |
| Authentication | `GET /api/auth/me` (`open`), `POST /api/auth/login` and `/logout` (`csrf`), `POST /api/auth/change-password` (`staff`) |
| Squadron quiz | `GET /api/quiz/next`, `POST /api/attempts`, `POST /api/quiz/finish` (all `staff`) |
| Solo practice | `POST /api/practice/start`, `/attempts`, `/finish` (`csrf`), `GET /api/practice/next` (`open`) |
| Public questions | `GET /api/questions` (`staff`), `GET /api/questions/counts` and `/api/topics` (`open`), `POST /api/questions` and `/api/questions/{id}/report` (`csrf`) |
| Admin board | `GET /api/admin/question-board`, `POST /api/admin/questions/{id}/board-state` (both `admin`) |
| Admin questions | `GET /api/admin/pending`, `POST /api/admin/questions/{id}/{approve,reject,delete,archive,restore,stale,needs-review,edit,accept-ai,reject-ai,send-to-human}`, `POST /api/admin/question-updates`, `POST /api/admin/question-check-review`, `POST /api/admin/import`, `POST /api/admin/questions/delete-all` (all `admin`) |
| Reports | `GET /api/admin/reports`, `POST /api/admin/reports/{id}/resolve` (`admin`) |
| Progress | `GET /api/stats` (`staff`), `GET /api/admin/progress-trends` (`admin`) |
| Admin users/topics | `GET`/`POST /api/admin/users*`, `POST /api/admin/topics/rename`, `POST /api/admin/reset-progress` (`admin`) |
| History | `GET /api/admin/quiz-sessions*`, `GET /api/admin/practice-sessions*`, `GET /api/admin/practice-stats`, `GET /api/admin/practice-trends`, plus their delete routes (`admin`) |
| Website issues | `POST /api/website-issues` (`csrf`), `GET /api/admin/website-issues`, `POST /api/admin/website-issues/{id}/delete` (`admin`) |

The exact request and response shapes live in the handlers. When behaviour
changes, update the handler, the matching browser module
(`static/app-core.js`, `static/app-staff.js`, or `static/app-admin.js`), and the
matching test together.

## Data model

Tables defined in `db.py` (`SCHEMA_VERSION` currently `2`):

| Table | Holds |
| --- | --- |
| `users` | Accounts: scrypt hash + salt, role (`staff`/`admin`), `active`, `must_change` |
| `sessions` | Random tokens with `user_id` (NULL for guests), `csrf`, `recent` question list, expiry |
| `questions` | Bank: text, answer, topic, `status`, `board_state`, flags (`outdated`, `needs_review`, `ai_pending`), staged AI text |
| `quiz_sessions` | One row per squadron run; closed by `ended_at` |
| `attempts` | Squadron answers linked to a `quiz_session_id`, with question/answer snapshots |
| `reports` | Question reports with status and resolver |
| `practice_sessions` | Solo practice runs, kept apart from squadron data |
| `practice_attempts` | Practice answers with snapshots |
| `website_issue_reports` | Website issue reports (added in schema version 2) |

Migrations run in `db.init()` guarded by `PRAGMA user_version`. Older columns
are upgraded in place by the `ensure_*_schema` helpers so existing history is
preserved. `db.connection()` hands out pooled connections with foreign keys on
and a busy timeout; `db.transaction(conn)` wraps multi-statement writes.

## Question state model

`questions.board_state` is the source of truth for the admin board column:
`active`, `time-sensitive`, `reported`, `approval`, or `archive`. Lifecycle
actions and `db.sync_question_board_state` keep it in sync with `status`, the
flag columns, and open reports.

Quiz/practice eligibility lives in `quiz.build_pool` and `db.list_questions`:
only approved, unarchived questions with no pending report, AI proposal, or
human-review flag are drawn. Time-sensitive questions stay eligible. Keep the
board's derived state, the server transitions, and `quiz.build_pool` aligned
when you change any of them.

## Conventions and guardrails

- No new third-party runtime dependencies. Standard library and SQLite only.
- All SQL lives in `db.py` and uses bound parameters. Never interpolate user
  input into SQL.
- Render user-supplied text with `textContent`, never as HTML. The CSP forbids
  inline script and external assets.
- State-changing requests require the CSRF header. Preserve that check when
  adding routes.
- Do not let submitted, rejected, reported, or AI-staged questions leak into
  quiz or practice pools.
- Solo practice must never affect squadron scores, weights, or sessions.
- AI output is untrusted: validate it, store it as text, and require explicit
  admin approval before applying changes.
- Keep element IDs, state classes, and `hidden` attributes intact; JavaScript
  navigation, role gating, dialogs, and banners depend on them.
- Update `api.py`, the `api_*.py` handler, the browser client, and the tests
  together when behaviour changes.

## How to make common changes

- **Add an API route:** add a handler in the matching `api_*.py` module and a
  `(method, regex, handler, access)` entry in `api.py`. Add coverage in `tests/`.
- **Add or change a table/column:** update `SCHEMA` and add an idempotent
  `ensure_*_schema`/migration step guarded by `user_version`, then update
  `SCHEMA_VERSION`. Never edit a released migration in place.
- **Change quiz selection:** edit `quiz.py` and confirm `build_pool` still
  matches the eligibility rules above.
- **Change the board:** keep `board_state` in sync server-side and mirror the
  change in `static/app-admin.js` and the board cases in `tests/cases_interface.py`
  and `tests/cases_questions.py`.
- **Add a test:** append a new `SECTIONS` number to the relevant
  `tests/cases_*.py` module. Section numbers are unique and run in order, and
  some cases share seeded data, so keep dependencies in mind. Run with
  `python3 test_quiz.py`.

## Verification

- Full suite: `python3 test_quiz.py` (own server on port 8099, temporary
  database, removed afterwards).
- Manual run: `python3 app.py`, then open <http://localhost:8001>.
- Health: `GET /healthz` checks database access and returns 503 if it fails.
- The suite count is reported in
  [`IMPLEMENTED-IMPROVEMENTS.md`](IMPLEMENTED-IMPROVEMENTS.md); keep it current.
