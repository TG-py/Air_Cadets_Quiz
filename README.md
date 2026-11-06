# RAFAC Questions

A small self-hosted web app for running knowledge-check quizzes at Air Cadets
parade. Staff/NCO log in, the first question appears straight away, and they record
whether the squad got it right or wrong. The next question is chosen at random -
weighted towards the questions the squadron keeps getting wrong.

Scores are kept for the squadron as a whole. There is no cadet name to enter:
everyone in the room is answering the same question, so the result is one
shared record rather than a sheet of individual marks.

Cadets do not need an account. They can open the page and submit new questions
with a name, question, answer and topic - all four are required. You review and
approve each one before it joins the bank.

No external dependencies. Python 3.9+ standard library and SQLite only.

## Who can do what

| Role | Can do |
| --- | --- |
| Cadet (no login) | Practise questions under your own name, submit new questions on the Submit page, pick an existing topic or add a new one |
| NCO / staff | Log in, ask questions, record correct/incorrect or skip, add questions directly, see progress |
| Admin | Everything staff/NCO can do, plus approve or reject submitted questions, review reported questions, archive and restore accepted questions, permanently delete questions and their history, flag questions whose answers may change, import a question list, create, edit and disable staff/NCO accounts, review finished quiz sessions, review solo practice runs and practice statistics, delete all progress |

Only staff/NCO and admins can see questions or record answers - cadets get a 401 on
those endpoints. Cadets see the Submit page and nothing else.

Submitted questions are never shown in a quiz until an admin approves them.

## Solo practice

Anyone can open *Practise questions* - no account needed. Enter a name,
pick a topic, and work through the same active question bank on your own.
The page is styled differently on purpose (green solo-practice banner and
card) so it cannot be mistaken for asking the squadron.

Each question starts with its answer hidden. At that point you can **Show
answer**, **Skip**, or **Finish practice**. Revealing the answer replaces the
reveal and skip options with **Got it right** and **Got it wrong**. Questions
are drawn from the same squadron-history weighting as the main quiz, so the
questions the squadron struggles with come up more often.

Practice scores are recorded separately and never touch the squadron
scoreboard or its weighting. A run closes automatically when you leave the
practice page or close the app, so its score is saved without needing the
Finish button.

Admins get a *Practice results* page grouped by the name used to practise,
with names in alphabetical order and the newest run first inside each name.
Opening a run shows when it happened and each question with its answer and
whether it was right, wrong or skipped. A run can be deleted on its own after
the usual double confirmation.

Anyone practising can report a wrong question from the three-dots menu on
the card, exactly like NCOs asking the squadron. Signed-in staff report
under their account name; everyone else gives the name they practised
under.

While asking questions, NCOs and admins can open the three-dots menu on the
question card and report a question they think is wrong. The description is
optional - a bare flag is enough. Reports land on the admin *Reports* page,
newest first, where each one can be marked fixed or dismissed
after checking the bank.

The three-dots button beside the menu title opens a menu with a **Report a
website issue** option. Choosing it opens a form where anyone can send a short
title and description; the current page is attached. Admins see every report in
one list on **Website issue reports** and can delete each one after dealing with
it.

## Running it

```bash
python3 app.py
```

Then open <http://localhost:8001>.

The first run creates the database and an admin account. Unless you set
`ADMIN_PASSWORD`, a random password is printed to the console **once** - save
it, and you will be asked to change it after logging in.

To choose the password yourself:

```bash
ADMIN_PASSWORD='something-long' python3 app.py
```

> Earlier builds scored each cadet separately and stored a `cadets` table.
> That is gone - scores are now a single squadron total. If you have a
> `questions.db` from one of those builds, delete it (`rm -f questions.db*`)
> and it will be recreated with the current layout. Nothing is carried over.

### Settings

| Variable | Default | Meaning |
| --- | --- | --- |
| `PORT` | `8001` | Port to listen on |
| `QUIZ_HOST` | `0.0.0.0` | Address to bind |
| `QUIZ_DB` | `./questions.db` | SQLite database location |
| `ADMIN_USERNAME` | `admin` | Username for the first admin |
| `ADMIN_PASSWORD` | random | Password for the first admin |
| `QUIZ_SECURE_COOKIES` | `0` | Set to `1` when serving over HTTPS |
| `QUIZ_LOG` | `0` | Set to `1` to log every request |

## Adding your questions

The database ships empty, so load your existing list. Anything already in the
bank is skipped, so it is safe to re-run.

**In the browser** - log in as admin, open the question board's **Import CSV**
control, and choose a `.csv` file or paste CSV text.

**From the command line:**

```bash
python3 import_questions.py questions.csv
python3 import_questions.py questions.json --format json
python3 import_questions.py questions.csv --dry-run     # show what would load
python3 import_questions.py questions.csv --pending     # load as pending, for review
python3 import_questions.py questions.csv --topic "Rank structure"
cat questions.csv | python3 import_questions.py -
```

CSV wants `question, answer, topic`. Only the question is required, and the
topic defaults to `General`. Commas, semicolons, tabs and pipes are all
detected automatically, and a header row is ignored. JSON accepts a list of
objects with `question`, `answer` and `topic` keys.

## How questions get chosen

Every question is given a weight from the squadron's own answer history, and
one is picked at random in proportion to those weights.

| Situation | Weight | Notes |
| --- | --- | --- |
| Never asked | 3.0 | So new questions still get asked |
| Always wrong | 4.0 | `0.25 + 3.75 x (1 - accuracy)^2` |
| Always right | 0.25 | Barely asked again |
| Half right | 1.19 | Quadratic, so near-misses rise fast |
| Two or more wrong in a row | x1.5 | Keeps drilling what they keep missing |

The result is a quiz that drifts towards the squad's weak spots without ever
repeating the same question twice in a row, and without ignoring questions they
have never seen. The exact numbers are at the top of `quiz.py`.

Skipped questions are recorded but excluded from scoring, so skipping never
counts against the squadron.

## Progress

The *Progress* page is built in three layers:

1. **Overall** - questions asked, correct, incorrect, skipped and squadron
   accuracy.
2. **Per topic** - a box for each topic, weakest first. Open one to see the
   questions inside it.
3. **Per question** - inside each topic box, every question with how often it
   was asked, how often the squad got it right or wrong, and its accuracy.

That is the page to look at when deciding what to drill next week.

The *Progress* menu is split into two expandable groups. **Squadron progress**
contains the squadron page, its trends and quiz sessions. **Practice progress**
contains *Overall practice data*, *Practice trends* and *Practice results*.
The practice pages use the same topic and accuracy layout as the squadron
pages, but only count solo practice answers, so they stay separate from the
squadron scoreboard.

Admins can archive an accepted question from the question bank. Archived
questions are removed from the quiz but keep their answer history; restoring
one puts it back into the quiz with that history intact. Permanent deletion is
separate and removes the question's recorded attempts and their references in
quiz sessions.

Some answers change over time - names of office holders, numbers, equipment.
Admins can tag such a question from the bank with "Flag out of date". The
*Out of date* page collects every tagged question in one place so nothing
slips through; removing the tag takes it back off the list. Tagged
questions stay in the quiz throughout.

## Quiz sessions

Every quiz is stored as its own session. Answering questions groups them
into the current session, and pressing **Finish** closes it so the next
question starts a fresh one. Logging out finishes any open session too.

Admins get a *Quiz sessions* page listing every finished session, newest
first, with who ran it, when, which topic filter was used, and how many
were correct, incorrect or skipped. Opening a session expands it to show
each question asked, its answer, and whether it was correct, incorrect or
skipped. When the bank runs dry the ask view keeps a **Finish** button, so
an exhausted run can still be closed (which also clears the asked list so
asking again starts fresh). Finishing as an admin jumps straight to the
sessions board, and closing or reloading the tab finishes any open run so
it lands on the board instead of staying open. A session can be deleted on its own after the same double
confirmation used for deleting all progress - only that session's answers
are removed, and the question bank and accounts are kept.

## Docker

### Docker Desktop, no terminal

Open this project folder in Docker Desktop (use the folder/project view, not
just the built image). Docker Desktop should detect `docker-compose.yml` and
show a Compose project. Click **Run** / **Start** on that project rather than
running the individual image.

You do not need to create a `.env` file: if `ADMIN_PASSWORD` is unset the
app generates a random password on first run and prints it to the container
logs (view them in Docker Desktop). The container listens on port 8001 and
stores data in the `quiz-data` volume automatically.
Requires Docker with the `compose` plugin (Docker Desktop, or `docker-compose` v2).

```bash
cp .env.example .env
# edit .env and set ADMIN_PASSWORD
docker compose up -d
```

Then open <http://localhost:8001> and log in as `admin` with that password.

Useful commands:

```bash
docker compose logs -f     # follow the request/startup log
docker compose down        # stop, keep the data
docker compose down -v     # stop and DELETE the database volume
```

The database lives in a named volume (`quiz-data`) mounted at `/srv/data`, so
questions and accounts survive a rebuild or an image upgrade. `.env` is not
copied into the image.

### Production hosting

The app serves plain HTTP and is intended to sit behind a reverse proxy that
handles HTTPS. Do not expose port 8001 directly to the public internet. Restrict
it to the proxy host with a firewall or bind the Compose port to loopback
(`127.0.0.1:8001:8001`) when the proxy runs on the same machine. Set
`QUIZ_SECURE_COOKIES=1` in the app environment after HTTPS is enabled.

For example, an Nginx virtual host can forward requests to a loopback-bound
Compose service:

```nginx
server {
    listen 443 ssl;
    server_name quiz.example.org;

    # Configure certificate and key paths for your host here.
    ssl_certificate     /etc/letsencrypt/live/quiz.example.org/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/quiz.example.org/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8001;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_read_timeout 30s;
    }
}
```

Keep the database volume on persistent storage and include it in regular
backups. Stop the container before copying a raw database file. For a live
SQLite backup, use Python's online backup API inside the container:

```bash
docker compose exec -T air-cadets-quiz python -c \
  "import sqlite3; src=sqlite3.connect('/srv/data/questions.db'); dst=sqlite3.connect('/tmp/questions-backup.db'); src.backup(dst); dst.close(); src.close()"
docker compose cp air-cadets-quiz:/tmp/questions-backup.db ./questions-backup.db
```

To restore, stop the app, copy the backup into `/srv/data/questions.db`, then
start the app again:

```bash
docker compose stop air-cadets-quiz
docker compose cp ./questions-backup.db air-cadets-quiz:/srv/data/questions.db
docker compose start air-cadets-quiz
```

Keep backups outside the container and periodically confirm that a backup can
be opened before relying on it.

On startup, the app reads SQLite's schema version and applies any pending
upgrade before serving requests. The version advances only after the migration
finishes; a failed migration is logged and stops startup so the database is not
served in a partially upgraded state. Keep a backup before upgrading the app.

The server's `/healthz` endpoint checks both HTTP handling and database access.
Docker uses it for the container health status. Startup failures, request
errors, and health-check failures are written to container logs; set `QUIZ_LOG=1`
to include successful request lines as well. When the app is behind a proxy,
login throttling sees the proxy connection address unless the deployment gives
each client a direct connection; the app does not trust forwarded addresses
for security decisions.

To import your list into a running container:

```bash
docker compose exec air-cadets-quiz \
  python import_questions.py -i questions.csv
```

or use **Import CSV** on the admin question board.

### Without compose

```bash
docker build -t air-cadets-quiz .
docker run -d --name air-cadets-quiz -p 8001:8001 \
  -e ADMIN_PASSWORD='something-long' \
  -v air-cadets-quiz-data:/srv/data \
  air-cadets-quiz
```

If you omit `ADMIN_PASSWORD`, the container generates one and prints it once:

```bash
docker logs air-cadets-quiz
```

### Notes

- The container runs as an unprivileged user (uid 1000) and never as root.
- If you bind-mount a host directory instead of a named volume, that directory
  must be writable by uid 1000 or startup will fail.
- Put it behind a reverse proxy with TLS for anything beyond a local network,
  and set `QUIZ_SECURE_COOKIES=1` so session cookies are marked `Secure`.

## Files

| File | Purpose |
| --- | --- |
| `app.py` | Startup and initial admin account |
| `api.py` | API route table |
| `api_common.py` | Shared API errors, request context, validation |
| `api_auth.py` | Login, session, and squadron quiz endpoints |
| `api_questions.py` | Question bank, submissions, review, and imports |
| `api_practice.py` | Solo practice endpoints |
| `api_issues.py` | Website issue submission and admin review endpoints |
| `api_admin.py` | Admin reports, progress, users, and session endpoints |
| `webserver.py` | HTTP server, static files, response headers, health checks |
| `db.py` | Schema, connection pooling, all SQL |
| `auth.py` | Password hashing, sessions, CSRF, login rate limiting |
| `quiz.py` | Weighting and random question selection |
| `import_questions.py` | Command line importer |
| `test_quiz.py`, `tests/` | End-to-end test runner and cases grouped by feature |
| `static/` | Page shell, role-specific views/nav, split browser code, styles and icons |
| `agent-work/` | Product, UI, and engineering notes for contributors and AI agents |
| `AGENTS.md` | Orientation and working rules for AI agents |
| `questions.db` | Created on first run |

## Documentation

- [`AGENTS.md`](AGENTS.md) - entry point for AI agents: commands, layout, and
  non-negotiable conventions.
- [`agent-work/README.md`](agent-work/README.md) - index of the agent notes.
- [`agent-work/product/FEATURE-GUIDE.md`](agent-work/product/FEATURE-GUIDE.md) -
  roles, workflows, and product rules.
- [`agent-work/engineering/ARCHITECTURE.md`](agent-work/engineering/ARCHITECTURE.md) -
  modules, request lifecycle, data model, and how to extend the app.
- [`agent-work/ui/UI-DESIGN-RULES.md`](agent-work/ui/UI-DESIGN-RULES.md) and
  [`agent-work/ui/MOBILE-RESPONSIVE-DIFFERENCES.md`](agent-work/ui/MOBILE-RESPONSIVE-DIFFERENCES.md) -
  visual and responsive guidance.

## Tests

```bash
python3 test_quiz.py
```

Starts the server on a temporary database, runs the end-to-end cases grouped
into authentication, account, question, quiz/progress, interface, and database
migration files under `tests/`, then shuts down. It uses port 8099 and its own
database, so it will not touch your real one.

## Security notes

Passwords are hashed with scrypt and a per-user salt, and are never stored or
logged in plain text. Sessions are random tokens in `httpOnly`, `SameSite=Strict`
cookies, and every state-changing request needs a matching CSRF token. Failed
logins are rate limited per address and username. All SQL uses bound
parameters, and all rendering uses `textContent`, so question text cannot
inject markup.

### Staff/NCO passwords

The admin sets the staff/NCO password outright and can read it straight after
setting it, but it is not kept in a readable form: only the scrypt hash and
salt are stored, so a password cannot be recovered later by anyone, including
the admin. If it is lost, set a new one. Any signed-in account can change its
own password from the menu.

An earlier build of this app kept a readable copy in a `users.password_text`
column. Starting a database with this version blanks and drops that column, so
upgrade a copy of the database first if you need it.

The server is plain HTTP. If you put it on the internet rather than a cadet
network, put it behind a reverse proxy that terminates HTTPS and set
`QUIZ_SECURE_COOKIES=1`.

Keep `questions.db` backed up - it holds the question bank and the squadron's
results.
