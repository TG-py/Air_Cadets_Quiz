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
| Cadet (no login) | Submit new questions on the Submit page, pick an existing topic or add a new one |
| NCO / staff | Log in, ask questions, record correct/incorrect or skip, add questions directly, see progress |
| Admin | Everything staff/NCO can do, plus approve or reject submitted questions, import a question list, create, edit and disable staff/NCO accounts, review finished quiz sessions, delete all progress |

Only staff/NCO and admins can see questions or record answers - cadets get a 401 on
those endpoints. Cadets see the Submit page and nothing else.

Submitted questions are never shown in a quiz until an admin approves them.

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

**In the browser** - log in as admin, open *Question bank*, paste your list
into the import box and choose CSV or JSON.

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

To import your list into a running container:

```bash
docker compose exec air-cadets-quiz \
  python import_questions.py -i questions.csv
```

or just paste the file into the admin page's **Question bank** tab.

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
| `app.py` | HTTP server, routing, permissions, static files |
| `db.py` | Schema, connection pooling, all SQL |
| `auth.py` | Password hashing, sessions, CSRF, login rate limiting |
| `quiz.py` | Weighting and random question selection |
| `import_questions.py` | Command line importer |
| `test_quiz.py` | End to end test suite |
| `static/` | Page, styles and browser code |
| `questions.db` | Created on first run |

## Tests

```bash
python3 test_quiz.py
```

Starts the server on a temporary database, runs 92 checks covering roles and
permissions, the approval flow, imports, the weighting maths, skipping and
session security, then shuts down. It uses port 8099 and its own database, so
it will not touch your real one.

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
the admin. If it is lost, set a new one.

An earlier build of this app kept a readable copy in a `users.password_text`
column. Starting a database with this version blanks and drops that column, so
upgrade a copy of the database first if you need it.

The server is plain HTTP. If you put it on the internet rather than a cadet
network, put it behind a reverse proxy that terminates HTTPS and set
`QUIZ_SECURE_COOKIES=1`.

Keep `questions.db` backed up - it holds the question bank and the squadron's
results.
