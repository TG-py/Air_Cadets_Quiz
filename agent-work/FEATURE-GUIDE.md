# Web app feature guide for agents

This document describes the current RAFAC Questions web app so agents can work on features without having to reconstruct the product from individual screens. It covers user roles, the main workflows, important behaviour, and where each part lives in the code.

For visual work, also follow [`UI-DESIGN-RULES.md`](UI-DESIGN-RULES.md). The running interface and current code are authoritative when older documentation or retained markup describes a previous layout.

## What the app does

RAFAC Questions is a small self-hosted knowledge-check app. Staff ask one question at a time to a squadron and record a shared result. Questions are selected randomly with weights informed by the squadron's past answers, so questions the group often misses are more likely to return. Anyone can also practise individually, submit questions, or report a question that may be wrong.

The server uses Python's standard library and SQLite. There is no required external AI service: AI-assisted reviews use a prompt and structured text that an admin can copy to an AI service and bring back for approval. AI suggestions are never applied automatically.

## Roles and access

| Role | Main capabilities |
| --- | --- |
| Visitor / cadet | Solo practice, question submission, and question reports. No account is needed. |
| Staff / NCO | Sign in, run squadron quizzes, record shared answers, view squadron progress, report questions, and add questions directly. |
| Admin | Staff capabilities plus manage all questions, handle submissions/reports/updates, manage staff accounts, inspect quiz and practice sessions, and reset squadron progress. |

The navigation is role-aware: public practice is available to everyone, visitors and staff can use the question-submission entry, quiz/progress require staff sign-in, and admin destinations are only shown to admins. The server also enforces access at each route; hiding a view in the browser is not the security boundary.

Success and error messages use a shared banner inside the site header. The header grows to fit a message and pushes regular page content down; on the desktop fixed-height question board, the available content area starts below the expanded header. The mobile drawer and backdrop also begin below the measured header height.

## Main features

### Squadron quiz

- Staff select all topics or one topic and ask the squadron one question at a time.
- The answer can be revealed before the result is recorded.
- Staff mark each question correct, incorrect, or skipped. Skips are recorded but do not affect accuracy.
- The next question is randomly weighted using squadron history. Never-asked questions retain a useful chance of appearing, and repeated wrong answers increase a question's weight. The same question is not repeated in a session until the available pool is exhausted.
- A quiz run is stored as a session. Finish closes it and presents a summary; logging out or closing/reloading the app also closes an open run.
- A question can be reported from its options menu. The report reason is optional for signed-in staff.

### Solo practice

- Visitors enter a name and optionally choose a topic. No account is required.
- Practice uses the same eligible question pool and weighting as the squadron quiz, but tracks questions faced within that practice run.
- Each practice question opens with its answer hidden. The initial choices are Show answer, Skip, and Finish practice. Revealing the answer swaps Show answer and Skip for Got it right and Got it wrong.
- Correct, incorrect, and skipped practice answers are stored separately. They never change squadron progress or squadron weighting.
- A practice run is closed and saved automatically when leaving the practice page or closing/reloading the app, so the Finish button is optional.
- Practice runs can report a question. Visitors provide the name they practised under; signed-in staff are identified from their account.
- Admins can inspect finished runs, grouped alphabetically by the practised name with the newest run first, and delete an individual run.
- Admins also get **Overall practice data** and **Practice trends**, built from the practice answers only. The Progress menu splits these and the squadron pages into expandable **Squadron progress** and **Practice progress** groups.

### Question submission

- Visitors submit their name, question, answer, and topic. They may choose an existing topic or propose a new one. Visitor submissions enter the Approval column and do not enter quiz pools until an admin approves them.
- Signed-in staff can use the submission form to add an approved question directly; admins use the board's add-question control.
- Admins can approve or reject submissions from the question editor. Rejected submissions remain available on the board for reconsideration unless deleted.

### Admin question board

The board is the central admin workspace for the question lifecycle. It replaces the separate question bank and submitted-question, report, and update-review destinations. Compact cards show the topic, question, and answer. Each question stores one `board_state` value naming its current column; the value is migrated from the older status, flag, archive, and report data when upgrading an existing database.

| Column | Meaning and quiz behaviour |
| --- | --- |
| Active | Approved questions available to quizzes and practice |
| Active · time sensitive | Approved questions flagged for future checking; still available to quizzes and practice |
| Reported | Has one or more open user reports; excluded from new quiz/practice draws until an admin handles the report |
| Approval | New submissions, rejected questions awaiting reconsideration, questions marked for human review, or proposed AI updates awaiting approval |
| Archive | Retained questions kept for history, excluded from quizzes and practice |

The saved board state is the source for column placement. Lifecycle actions keep it in sync: reports move questions to Reported, approvals and review flags move them to Approval, outdated flags move approved questions to Active · time sensitive, and archive actions move them to Archive.

- On desktop, the five state columns sit side by side in a horizontal scroller. Each question column scrolls vertically; a red dashed Delete drop column is at the end. On phones, the five state columns become full-width horizontally swipeable pages with scroll snapping; horizontal swipes work from the full column, including its card list. Delete is hidden because touch users get a direct delete action on expanded cards.
- The board has no text search bar. A compact topic selector sits beside the subtitle and filters all columns.
- Dragging a card between columns changes its saved board state. Moving a reported card out of Reported resolves its open reports. Reported is entered by a user report, not by dragging.
- Dropping a card in the dashed editor area opens that same card in an expanded editing layout. Moving a card between columns does not open the editor.
- The expanded card contains editable question and answer text fields, a topic dropdown, its saved state label, report history, and any proposed AI text. The details are arranged within one card; there are no separate preview, form, and tag panels.
- To save, drag the expanded card into a board column. Dropping it into its current column saves edits without changing its state; dropping it into another column saves edits and applies that state. Dropping an item back into Reported saves edits and keeps its reports open. Dragging it out of Reported closes the open reports.
- Approval and review-state changes happen by moving the card to the appropriate column. Rejecting a proposed AI update remains an explicit action in the expanded card.
- The expanded card has no save button, state-selection control, Google search button, corner drag handle, or delete button. Drag from anywhere on the card to save it in a column; left/right arrows and Enter provide a keyboard destination choice. Editing controls remain available to keyboard users.
- A red dashed Delete drop column follows Archive. Dropping any question there asks for confirmation before permanent deletion. Question deletion is not exposed through a separate button.
- Dragging any question card carries a Google search link for its question text. Dropping it on the browser tab bar opens a Google search in browsers that support link drops there. The board subtitle explains this gesture; browser behavior varies.
- Topic filtering and the “Manage questions” controls are locked while the card is being edited. View changes and browser reload/close are guarded so unsaved field edits are not silently discarded; drag the card into a column first.
- The compact editor dock has a **+** control that opens a blank question card directly in the editor. Enter a question, answer, and existing topic, then drag the card to a board column to create it there. New questions cannot be placed in Reported; that column is reserved for questions with user reports. An unsaved new card can be discarded by dragging it to Delete and confirming.
- The dock's **Import CSV** control opens a dialog where an admin can choose a `.csv` file or paste CSV text. The import is applied to the board, then the dialog closes and the board refreshes. The supported columns are question, answer, and topic. Topic rename, the legacy add form, and clear-bank controls remain under “Manage questions.”
- On phones, collapsed cards show only the question and answer. Tapping a card expands it to show its topic and explicit Edit question, Move to, and Delete question actions. Only one card across the board expands at a time. Moving out of Reported continues to close its open reports, and existing approval/archive confirmations still apply.
- Each phone status page has an Add question button that opens the existing editor with that page's status selected. The Reported page's button starts a new question in Active because Reported can only be entered through a user report.
- The mobile add/edit editor opens as a centered overlay card with destination, Save changes, and Cancel controls. The Manage questions disclosure is replaced by a static topic/bank controls card; CSV import is hidden on phones. Desktop keeps its drag-to-edit/save and import workflows and keyboard destination controls.

#### Board layout and scrolling

- When the board is open, it uses the available browser height below the compact site header and alongside the navigation rail. The page itself is held in place so the whole document does not need to scroll.
- The columns expand to fill the remaining workspace. Each column scrolls vertically through its cards, and the row of columns scrolls horizontally only when the browser is too narrow to fit them at a useful width.
- The topic selector stays beside the subtitle in the desktop board header and is temporarily disabled while a card is being edited. On phones, it sits below the title and description. The desktop editor dock opens into the expanded card and uses more height, which correspondingly reduces the visible column area.
- The board title and subtitle sit side by side on desktop and stack on phones. The subtitle is left-aligned and wraps across multiple lines as needed. Status and error messages appear in the site header, which expands so they do not cover board elements.
- On desktop, the board uses a fixed-height workspace below the header and alongside the rail. On phones, it returns to normal document scrolling below a sticky header, so the browser's changing viewport height and the on-screen keyboard do not trap the user in a clipped canvas.
- The phone header menu button sits in the header row. The board header, topic filter, management forms and editor use a readable single-column flow, with larger text and touch targets. The status columns are separate swipeable pages; cards reveal actions only when tapped, and add/edit opens as an overlay card rather than below the columns.
- Error and confirmation banners appear in the site header; destructive and consequential actions use in-page confirmation dialogs rather than browser confirm boxes. The desktop board workspace begins below the full header height, while the phone board remains in normal page flow below its sticky header.

### Reports and keeping questions accurate

- Any visitor or staff member can report a question they believe is incorrect. The report reason is optional; a visitor supplies a name.
- A pending report moves the question into Reported and removes it from new quiz/practice draws. Repeated reports can be made by different people, but a person cannot keep duplicate open reports on the same question.
- Admins review report history and the question together. Dragging the card out of Reported closes its pending reports as resolved; the board does not offer a separate dismiss action.
- The time-sensitive flag indicates an answer may change. It does not remove the question from quizzes. Admins can review it manually or use the copy/paste AI-assisted review workflow.
- An AI suggestion is a proposal only. It appears in Approval, and an admin reviews and explicitly accepts or rejects it. Questions needing human judgement can be sent to the human-review state and edited directly.

### AI-assisted review and imports

- The app does not make paid API calls or send question data to an AI service on its own.
- The earlier combined-review workflow can create a prompt containing reported/time-sensitive questions, copy it to an AI tool of the admin's choice, and parse structured results. Its markup and server routes are retained, but that review view is not a current navigation destination after the board consolidation.
- The board can display and approve/reject an already-staged AI proposal. The current board does not expose a prompt-generation control for starting a new AI review.
- The server-side review handlers validate proposed actions and stage text changes for admin approval. A staged suggestion does not replace the live question until accepted.
- The board supports adding a question from the editor dock and importing a list as CSV through the popup. The command-line importer in `import_questions.py` supports dry runs and can load entries as pending for review.

### Progress and history

- The Progress view shows squadron-wide totals and accuracy, then per-topic and per-question statistics.
- Quiz sessions preserve the runner, time, topic filter, outcomes, and question/answer text as it appeared during that run. Admins can open and delete an individual session.
- Practice results show completed solo runs grouped by name, with question-level results kept separately from squadron totals. Admins can open and delete an individual run.
- Overall practice data mirrors the squadron topic/question statistics using practice answers only. Practice trends mirror the 12-week squadron charts. Neither page changes the squadron scoreboard.
- Admins can reset squadron answer progress without deleting the question bank or staff accounts. This is a destructive action and should remain clearly labelled and confirmed.
- Archiving preserves question and answer history while removing the question from future quiz/practice pools. Restoring brings it back. Permanent deletion removes linked history and reports.

### Accounts and passwords

- The first run creates the initial admin account. The password can be configured at startup or generated and printed once; a first-use admin may be required to change it.
- Any signed-in account can change its own password from the Change password page. Admins can also create staff or admin accounts, set usernames and display names, reset passwords, and disable accounts.
- Passwords are stored as scrypt hashes with salts. Sessions use random HTTP-only cookies; state-changing requests require CSRF protection, and failed logins are rate-limited.

## Important product rules

- Only approved, unarchived questions with no pending reports, AI proposal, or human-review flag are eligible for new quiz/practice draws.
- Time-sensitive questions remain eligible. Keep this aligned with the Active · time sensitive board label.
- One open report is sufficient to pause a question. Do not require a minimum report count before moving it to review.
- Submitted and rejected questions must not leak into quiz or practice pools before approval.
- Solo practice must never change squadron score or quiz-session records.
- AI output is untrusted proposal data. Validate it, display it as text, and require explicit admin approval before applying question/answer changes.
- Question and answer content is user-provided. Continue using bound SQL parameters and safe text rendering; do not interpolate it as HTML or SQL.
- Make state-changing actions understandable and recoverable where possible. Archive is reversible; permanent delete and progress reset are not.

## Code map

| Area | Files and responsibilities |
| --- | --- |
| Browser page and navigation | `static/index.html` — views, forms, navigation and accessible labels |
| Browser behaviour | `static/app.js` — view switching, API calls, rendering, quiz/practice flows, board interactions |
| Visual styling | `static/style.css` — app shell, responsive layouts, question cards and board states |
| Application startup | `app.py` — startup and initial admin account |
| Database | `db.py` — SQLite schema, migrations, queries, and persistence for questions, reports, attempts, sessions and users |
| HTTP transport and static files | `webserver.py` — HTTP request handling, static file responses, security headers, and health endpoint |
| Route registration | `api.py` — maps URL patterns and access requirements to feature handlers |
| Shared API helpers | `api_common.py` — request context, validation, and consistent API errors |
| Authentication and squad quiz routes | `api_auth.py` — sign-in and squad quiz workflows |
| Question routes | `api_questions.py` — public submissions and question reports |
| Practice routes | `api_practice.py` — individual practice sessions and answers |
| Admin routes | `api_admin.py` — admin workflows, including progress trends |
| Website issue reports | `api_issues.py` — public report submission and admin list/delete |
| Quiz selection | `quiz.py` — eligibility pool, weights, and random question selection |
| Batch import | `import_questions.py` — CSV/JSON command-line import |
| Product overview and operations | `README.md` — setup, configuration, deployment and project notes |
| Agent feature guide | `agent-work/FEATURE-GUIDE.md` — roles, workflows, behaviour and code map |
| UI guidance | `agent-work/UI-DESIGN-RULES.md` — visual language and accessibility guidance |
| Responsive layout notes | `agent-work/MOBILE-RESPONSIVE-DIFFERENCES.md` — desktop and phone layout/interaction differences |

The HTML still contains some legacy review sections and the JavaScript still contains supporting handlers for existing admin routes. They are not current navigation destinations: use the question board as the admin question-management interface unless a deliberate product change says otherwise.

## Feature API map

Routes are registered in `api.py`; feature handlers live in the corresponding `api_*.py` module. The route's access label determines whether it is public, staff-only, admin-only, or CSRF-protected. The browser client calls these routes from `static/app.js`.

- Authentication: `/api/auth/*`
- Quiz and squadron attempts: `/api/quiz/*`, `/api/attempts`
- Practice: `/api/practice/*`
- Admin practice reporting: `/api/admin/practice-sessions*`, `/api/admin/practice-stats`, `/api/admin/practice-trends`
- Public question submission and reporting: `/api/questions`, `/api/questions/{id}/report`
- Admin board and board state: `/api/admin/question-board`, `/api/admin/questions/{id}/board-state`
- Admin question editing, approval, archive, reports, and import: `/api/admin/*`
- Progress: `/api/stats`
- Admin progress trends: `/api/admin/progress-trends` (admin-only)
- Admin practice trends: `/api/admin/practice-trends` (admin-only)
- Website issue reports: `POST /api/website-issues`; admin list/delete at `/api/admin/website-issues*`
- Topic list: `/api/topics`

The exact request and response formats are defined in the route handlers. When changing behaviour, update the browser client, server validation/state transitions, and quiz eligibility together where relevant.

## Recently implemented improvements

The following accepted improvements are implemented. The detailed implementation record, including scope and verification status, is in [`IMPLEMENTED-IMPROVEMENTS.md`](IMPLEMENTED-IMPROVEMENTS.md).

- **G3 — Admin progress charts:** Adds a separate admin-only **Progress trends** page under Progress. It displays weekly correct, incorrect, and skipped counts for the last 12 weeks, plus an accuracy trend that omits weeks with fewer than five scored answers. Skipped answers do not count toward accuracy.
- **G4 — Request feedback:** Shared API requests give immediate in-flight feedback, prevent duplicate submissions while a request is pending, and restore the prior control state when it finishes.
- **G5 — Keyboard and focus behaviour:** View changes do not select or focus the destination heading; disclosure controls expose expanded state and support Escape; the mobile board editor manages focus, traps Tab within the open editor, and restores focus when closed.
- **B3 — Database migrations:** SQLite `user_version` tracks schema version 1. Migrations run transactionally, reject databases from a newer unsupported version, and log migration outcomes.
- **B4 — Backend module split:** Startup, route registration, shared helpers, authentication/quiz, questions, practice, admin features, and HTTP transport now have separate modules.
- **B7 — Hosting guidance:** The README documents HTTPS reverse proxy deployment, secure-cookie configuration, network exposure, backups/restores, health checks, and forwarded IP considerations.
- **B8 — Test organization:** The existing end-to-end suite is divided into feature case modules and run in its original shared-data order by `test_quiz.py`.
- **B9 — Runtime health and logs:** Startup and request failures use Python logging. `/healthz` checks database access and returns an unhealthy response when it fails; the container health check uses this endpoint.
- **Website issue reports:** The menu title's three-dots button opens a menu with a **Report a website issue** option, available to visitors and staff. Reports are stored separately from question reports and include the originating page. The admin-only **Website issue reports** page shows every report in one list and offers a delete button for each report.
- **Page switching:** Changing views closes transient dialogs and question menus and clears stale header banners. Admin navigation tabs remain visible on every view, while admin-only page sections stay hidden unless their own view is selected; identity and board refreshes cannot reveal Progress trends or Website issue reports alongside All questions.

## Working on the app

- Start by checking `agent-work/FEATURE-GUIDE.md`, `README.md`, and `agent-work/UI-DESIGN-RULES.md`, then inspect the relevant implementation before changing it.
- Preserve the role boundaries and product rules above when adding screens or API routes.
- Keep question-state logic consistent between the board's derived state, server transitions, and `quiz.build_pool`.
- Treat `db.py` as the owner of persistence and migrations; avoid duplicating SQL rules across features when a database helper exists.
- Keep the board as the primary admin surface for question maintenance unless the product direction is explicitly changed.
- The README and older hidden views may retain names from earlier layouts. Confirm current navigation and behaviour in `static/index.html` and `static/app.js` before relying on old labels.
- The repository includes `test_quiz.py` as its end-to-end test suite. Run verification only when requested or required by the task instructions.
