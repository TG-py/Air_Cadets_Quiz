import os
import logging
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("QUIZ_DB", os.path.join(BASE_DIR, "questions.db"))
SCHEMA_VERSION = 2
LOGGER = logging.getLogger("air_cadets_quiz.db")

USER_STAFF = "staff"
USER_ADMIN = "admin"

Q_PENDING = "pending"
Q_APPROVED = "approved"
Q_REJECTED = "rejected"

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    salt          TEXT NOT NULL,
    role          TEXT NOT NULL CHECK (role IN ('admin', 'staff')),
    display_name  TEXT NOT NULL DEFAULT '',
    active        INTEGER NOT NULL DEFAULT 1,
    must_change   INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    token      TEXT PRIMARY KEY,
    user_id    INTEGER REFERENCES users(id) ON DELETE CASCADE,
    csrf       TEXT NOT NULL,
    recent     TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS sessions_user ON sessions(user_id);

CREATE TABLE IF NOT EXISTS questions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    question_text TEXT NOT NULL,
    answer_text   TEXT NOT NULL DEFAULT '',
    topic         TEXT NOT NULL DEFAULT 'General',
    status        TEXT NOT NULL DEFAULT 'pending'
                  CHECK (status IN ('pending', 'approved', 'rejected')),
    board_state   TEXT NOT NULL DEFAULT 'approval'
                  CHECK (board_state IN ('active', 'time-sensitive', 'reported', 'approval', 'archive')),
    submitted_by  TEXT NOT NULL DEFAULT '',
    source        TEXT NOT NULL DEFAULT 'staff',
    review_note   TEXT NOT NULL DEFAULT '',
    reviewed_by   INTEGER REFERENCES users(id) ON DELETE SET NULL,
    reviewed_at   TEXT,
    archived_at   TEXT,
    outdated      INTEGER NOT NULL DEFAULT 0,
    needs_review  INTEGER NOT NULL DEFAULT 0,
    ai_pending    INTEGER NOT NULL DEFAULT 0,
    ai_question_text TEXT NOT NULL DEFAULT '',
    ai_answer_text TEXT NOT NULL DEFAULT '',
    ai_topic      TEXT NOT NULL DEFAULT '',
    ai_reason     TEXT NOT NULL DEFAULT '',
    created_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS questions_status ON questions(status);
CREATE INDEX IF NOT EXISTS questions_topic ON questions(topic);

CREATE TABLE IF NOT EXISTS quiz_sessions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER REFERENCES users(id) ON DELETE SET NULL,
    username     TEXT NOT NULL DEFAULT '',
    display_name TEXT NOT NULL DEFAULT '',
    topic        TEXT NOT NULL DEFAULT '',
    started_at   TEXT NOT NULL,
    ended_at     TEXT,
    created_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS quiz_sessions_user ON quiz_sessions(user_id);
CREATE INDEX IF NOT EXISTS quiz_sessions_ended ON quiz_sessions(ended_at);

CREATE TABLE IF NOT EXISTS attempts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    question_id INTEGER NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
    correct     INTEGER NOT NULL DEFAULT 0 CHECK (correct IN (0, 1)),
    skipped     INTEGER NOT NULL DEFAULT 0 CHECK (skipped IN (0, 1)),
    answered_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at  TEXT NOT NULL,
    quiz_session_id INTEGER REFERENCES quiz_sessions(id) ON DELETE CASCADE,
    question_text TEXT NOT NULL DEFAULT '',
    answer_text   TEXT NOT NULL DEFAULT '',
    topic         TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS attempts_question ON attempts(question_id);

CREATE TABLE IF NOT EXISTS reports (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    question_id   INTEGER NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
    reported_by   INTEGER REFERENCES users(id) ON DELETE SET NULL,
    reporter_name TEXT NOT NULL DEFAULT '',
    reason        TEXT NOT NULL DEFAULT '',
    status        TEXT NOT NULL DEFAULT 'pending'
                  CHECK (status IN ('pending', 'resolved', 'dismissed')),
    created_at    TEXT NOT NULL,
    resolved_at   TEXT,
    resolved_by   INTEGER REFERENCES users(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS reports_question ON reports(question_id);
CREATE INDEX IF NOT EXISTS reports_status ON reports(status);

CREATE TABLE IF NOT EXISTS practice_sessions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL DEFAULT '',
    topic      TEXT NOT NULL DEFAULT '',
    started_at TEXT NOT NULL,
    ended_at   TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS practice_sessions_ended ON practice_sessions(ended_at);

CREATE TABLE IF NOT EXISTS practice_attempts (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    practice_session_id INTEGER NOT NULL REFERENCES practice_sessions(id) ON DELETE CASCADE,
    question_id         INTEGER NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
    correct             INTEGER NOT NULL DEFAULT 0 CHECK (correct IN (0, 1)),
    skipped             INTEGER NOT NULL DEFAULT 0 CHECK (skipped IN (0, 1)),
    created_at          TEXT NOT NULL,
    question_text       TEXT NOT NULL DEFAULT '',
    answer_text         TEXT NOT NULL DEFAULT '',
    topic               TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS practice_attempts_session ON practice_attempts(practice_session_id);
CREATE INDEX IF NOT EXISTS practice_attempts_question ON practice_attempts(question_id);
"""


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


POOL_SIZE = 8

_pool = []
_pool_lock = threading.Lock()


def _open():
    conn = sqlite3.connect(
        DB_PATH, timeout=15, isolation_level=None, check_same_thread=False
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 15000")
    return conn


def acquire():
    with _pool_lock:
        if _pool:
            return _pool.pop()
    return _open()


def release(conn):
    if conn.in_transaction:
        try:
            conn.execute("ROLLBACK")
        except sqlite3.Error:
            pass
    with _pool_lock:
        if len(_pool) < POOL_SIZE:
            _pool.append(conn)
            return
    conn.close()


@contextmanager
def connection():
    conn = acquire()
    try:
        yield conn
    finally:
        release(conn)


@contextmanager
def transaction(conn):
    conn.execute("BEGIN")
    try:
        yield conn
    except Exception:
        conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")


def drop_readable_passwords(conn):
    """Erase the readable password copy left by an earlier build of this app.

    Passwords are hashes only, so any database that picked up the column is
    holding secrets nobody needs any more. Blank it first, then drop it.
    """
    if "password_text" not in {row["name"] for row in conn.execute("PRAGMA table_info(users)")}:
        return
    conn.execute("UPDATE users SET password_text = ''")
    if sqlite3.sqlite_version_info < (3, 35, 0):
        LOGGER.warning("migration_legacy_column_retained column=users.password_text reason=sqlite_drop_column_unsupported")
    else:
        conn.execute("ALTER TABLE users DROP COLUMN password_text")


def ensure_quiz_session_schema(conn):
    """Bring older databases up to date with per-session quiz history.

    Fresh databases get the tables from SCHEMA. Databases created before
    quiz sessions existed only have the old attempts table, so add the
    missing table and columns here rather than losing any history.
    """
    conn.execute(
        "CREATE TABLE IF NOT EXISTS quiz_sessions ("
        "    id           INTEGER PRIMARY KEY AUTOINCREMENT,"
        "    user_id      INTEGER REFERENCES users(id) ON DELETE SET NULL,"
        "    username     TEXT NOT NULL DEFAULT '',"
        "    display_name TEXT NOT NULL DEFAULT '',"
        "    topic        TEXT NOT NULL DEFAULT '',"
        "    started_at   TEXT NOT NULL,"
        "    ended_at     TEXT,"
        "    created_at   TEXT NOT NULL"
        ")"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS quiz_sessions_user ON quiz_sessions(user_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS quiz_sessions_ended ON quiz_sessions(ended_at)")
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(attempts)")}
    for column, ddl in (
        ("quiz_session_id", "INTEGER REFERENCES quiz_sessions(id) ON DELETE CASCADE"),
        ("question_text", "TEXT NOT NULL DEFAULT ''"),
        ("answer_text", "TEXT NOT NULL DEFAULT ''"),
        ("topic", "TEXT NOT NULL DEFAULT ''"),
    ):
        if column not in existing:
            conn.execute(f"ALTER TABLE attempts ADD COLUMN {column} {ddl}")
    conn.execute("CREATE INDEX IF NOT EXISTS attempts_quiz_session ON attempts(quiz_session_id)")
    # attempts recorded before snapshots existed keep only the question id, so
    # copy the current bank text across where the question still exists
    conn.execute(
        "UPDATE attempts SET question_text = "
        "(SELECT question_text FROM questions WHERE questions.id = attempts.question_id), "
        "answer_text = "
        "(SELECT answer_text FROM questions WHERE questions.id = attempts.question_id), "
        "topic = "
        "(SELECT topic FROM questions WHERE questions.id = attempts.question_id) "
        "WHERE (question_text IS NULL OR question_text = '') "
        "AND EXISTS (SELECT 1 FROM questions WHERE questions.id = attempts.question_id)"
    )


def init():
    conn = sqlite3.connect(DB_PATH, timeout=15, isolation_level=None)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        conn.executescript(SCHEMA)
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if version > SCHEMA_VERSION:
            raise RuntimeError(
                "database schema version %d is newer than this app supports (%d)"
                % (version, SCHEMA_VERSION)
            )
        while version < SCHEMA_VERSION:
            next_version = version + 1
            conn.execute("BEGIN IMMEDIATE")
            try:
                if next_version == 1:
                    _migrate_legacy_schema(conn)
                elif next_version == 2:
                    _migrate_website_issue_reports(conn)
                else:
                    raise RuntimeError("no migration defined for schema version %d" % next_version)
                conn.execute("PRAGMA user_version = %d" % next_version)
                conn.execute("COMMIT")
                version = next_version
            except Exception:
                conn.execute("ROLLBACK")
                LOGGER.exception("migration_failed from_version=%s to_version=%s", version, next_version)
                raise
        conn.execute("PRAGMA wal_autocheckpoint = 512")
    finally:
        conn.close()


def _migrate_legacy_schema(conn):
    """Apply the idempotent upgrades used by databases before schema version 1.

    Future schema changes should add a numbered migration and advance
    SCHEMA_VERSION. ``PRAGMA user_version`` is only advanced after every step
    completes successfully, so an interrupted upgrade can be retried safely.
    """
    LOGGER.info("migration_started from_version=0 to_version=1")
    question_columns = {row["name"] for row in conn.execute("PRAGMA table_info(questions)")}
    if "archived_at" not in question_columns:
        conn.execute("ALTER TABLE questions ADD COLUMN archived_at TEXT")
    ensure_outdated_schema(conn)
    ensure_needs_review_schema(conn)
    ensure_ai_review_schema(conn)
    ensure_practice_schema(conn)
    conn.execute("CREATE INDEX IF NOT EXISTS questions_archived ON questions(archived_at)")
    ensure_reports_schema(conn)
    ensure_question_board_state_schema(conn)
    drop_readable_passwords(conn)
    ensure_quiz_session_schema(conn)
    LOGGER.info("migration_completed to_version=1")


def _migrate_website_issue_reports(conn):
    LOGGER.info("migration_started from_version=1 to_version=2")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS website_issue_reports ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "reported_by INTEGER REFERENCES users(id) ON DELETE SET NULL, "
        "reporter_name TEXT NOT NULL DEFAULT '', "
        "title TEXT NOT NULL, details TEXT NOT NULL, page TEXT NOT NULL DEFAULT '', "
        "status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'resolved', 'dismissed')), "
        "created_at TEXT NOT NULL, resolved_at TEXT, "
        "resolved_by INTEGER REFERENCES users(id) ON DELETE SET NULL)"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS website_issue_reports_status ON website_issue_reports(status)")
    LOGGER.info("migration_completed to_version=2")


def ensure_outdated_schema(conn):
    """A single tag collecting the questions that may need updating.

    Fresh databases get the column from SCHEMA. Older databases gain it here
    so nothing in the bank is lost. Flags from the retired flag/note/due-date
    system are carried across, then those columns are dropped.
    """
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(questions)")}
    if "outdated" not in existing:
        conn.execute("ALTER TABLE questions ADD COLUMN outdated INTEGER NOT NULL DEFAULT 0")
    if "stale_flag" in existing:
        condition = "stale_flag = 1"
        if "stale_due" in existing:
            condition += " OR (stale_due IS NOT NULL AND stale_due != '')"
        conn.execute("UPDATE questions SET outdated = 1 WHERE " + condition)
    for column in ("stale_flag", "stale_note", "stale_due", "last_verified_at"):
        if column in existing:
            if sqlite3.sqlite_version_info >= (3, 35, 0):
                conn.execute(f"ALTER TABLE questions DROP COLUMN {column}")
            else:
                LOGGER.warning("migration_legacy_column_retained column=questions.%s reason=sqlite_drop_column_unsupported", column)
    conn.execute("CREATE INDEX IF NOT EXISTS questions_outdated ON questions(outdated)")


def ensure_needs_review_schema(conn):
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(questions)")}
    if "needs_review" not in existing:
        conn.execute("ALTER TABLE questions ADD COLUMN needs_review INTEGER NOT NULL DEFAULT 0")
    conn.execute("CREATE INDEX IF NOT EXISTS questions_needs_review ON questions(needs_review)")


def set_question_needs_review(conn, question_id, tagged):
    ensure_needs_review_schema(conn)
    conn.execute("UPDATE questions SET needs_review = ? WHERE id = ?", (1 if tagged else 0, question_id))
    sync_question_board_state(conn, question_id)


def list_needs_review(conn, limit=5000):
    ensure_needs_review_schema(conn)
    return conn.execute(
        "SELECT * FROM questions WHERE archived_at IS NULL AND needs_review = 1 ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()


def needs_review_count(conn):
    ensure_needs_review_schema(conn)
    row = conn.execute("SELECT COUNT(*) AS n FROM questions WHERE archived_at IS NULL AND needs_review = 1").fetchone()
    return row["n"] or 0


def ensure_ai_review_schema(conn):
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(questions)")}
    columns = {
        "ai_pending": "INTEGER NOT NULL DEFAULT 0",
        "ai_question_text": "TEXT NOT NULL DEFAULT ''",
        "ai_answer_text": "TEXT NOT NULL DEFAULT ''",
        "ai_topic": "TEXT NOT NULL DEFAULT ''",
        "ai_reason": "TEXT NOT NULL DEFAULT ''",
    }
    for name, definition in columns.items():
        if name not in existing:
            conn.execute("ALTER TABLE questions ADD COLUMN %s %s" % (name, definition))
    conn.execute("CREATE INDEX IF NOT EXISTS questions_ai_pending ON questions(ai_pending)")


def list_ai_pending(conn, limit=5000):
    ensure_ai_review_schema(conn)
    return conn.execute(
        "SELECT * FROM questions WHERE archived_at IS NULL AND ai_pending = 1 ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()


def ai_pending_count(conn):
    ensure_ai_review_schema(conn)
    row = conn.execute("SELECT COUNT(*) AS n FROM questions WHERE archived_at IS NULL AND ai_pending = 1").fetchone()
    return row["n"] or 0


REPORT_PENDING = "pending"
REPORT_RESOLVED = "resolved"
REPORT_DISMISSED = "dismissed"


def ensure_reports_schema(conn):
    """Let NCOs flag questions they think are wrong while asking them.

    Fresh databases get the table from SCHEMA. Older databases gain it here,
    so the bank and its history are left untouched.
    """
    conn.execute(
        "CREATE TABLE IF NOT EXISTS reports ("
        "    id            INTEGER PRIMARY KEY AUTOINCREMENT,"
        "    question_id   INTEGER NOT NULL REFERENCES questions(id) ON DELETE CASCADE,"
        "    reported_by   INTEGER REFERENCES users(id) ON DELETE SET NULL,"
        "    reporter_name TEXT NOT NULL DEFAULT '',"
        "    reason        TEXT NOT NULL DEFAULT '',"
        "    status        TEXT NOT NULL DEFAULT 'pending'"
        "                CHECK (status IN ('pending', 'resolved', 'dismissed')),"
        "    created_at    TEXT NOT NULL,"
        "    resolved_at   TEXT,"
        "    resolved_by   INTEGER REFERENCES users(id) ON DELETE SET NULL"
        ")"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS reports_question ON reports(question_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS reports_status ON reports(status)")


def ensure_question_board_state_schema(conn):
    """Persist the board column while preserving existing question placement."""
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(questions)")}
    if "board_state" in existing:
        return
    conn.execute(
        "ALTER TABLE questions ADD COLUMN board_state TEXT NOT NULL DEFAULT 'approval' "
        "CHECK (board_state IN ('active', 'time-sensitive', 'reported', 'approval', 'archive'))"
    )
    conn.execute(
        "UPDATE questions SET board_state = CASE "
        "WHEN archived_at IS NOT NULL THEN 'archive' "
        "WHEN EXISTS (SELECT 1 FROM reports WHERE reports.question_id = questions.id AND reports.status = 'pending') THEN 'reported' "
        "WHEN status != 'approved' OR ai_pending = 1 OR needs_review = 1 THEN 'approval' "
        "WHEN outdated = 1 THEN 'time-sensitive' ELSE 'active' END"
    )


def sync_question_board_state(conn, question_id):
    """Keep the saved board column aligned with lifecycle events and flags."""
    question = conn.execute("SELECT * FROM questions WHERE id = ?", (question_id,)).fetchone()
    if not question:
        return
    if question["archived_at"]:
        state = "archive"
    elif conn.execute(
        "SELECT 1 FROM reports WHERE question_id = ? AND status = 'pending' LIMIT 1", (question_id,)
    ).fetchone():
        state = "reported"
    elif question["status"] != Q_APPROVED or question["ai_pending"] or question["needs_review"]:
        state = "approval"
    elif question["outdated"]:
        state = "time-sensitive"
    else:
        state = "active"
    conn.execute("UPDATE questions SET board_state = ? WHERE id = ?", (state, question_id))


def add_report(conn, question_id, user_id, reporter_name, reason):
    ensure_reports_schema(conn)
    cur = conn.execute(
        "INSERT INTO reports (question_id, reported_by, reporter_name, reason, status, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (question_id, user_id, reporter_name or "", reason, REPORT_PENDING, now()),
    )
    conn.execute("UPDATE questions SET board_state = 'reported' WHERE id = ?", (question_id,))
    return cur.lastrowid


def get_report(conn, report_id):
    ensure_reports_schema(conn)
    return conn.execute("SELECT * FROM reports WHERE id = ?", (report_id,)).fetchone()


def has_pending_report(conn, question_id, user_id):
    ensure_reports_schema(conn)
    row = conn.execute(
        "SELECT id FROM reports WHERE question_id = ? AND reported_by = ? AND status = ? LIMIT 1",
        (question_id, user_id, REPORT_PENDING),
    ).fetchone()
    return row is not None


def list_reports(conn, status="pending", limit=200):
    """Reports newest first, with the live question text alongside each one."""
    ensure_reports_schema(conn)
    base = (
        "SELECT r.*, q.question_text AS live_text, q.answer_text AS live_answer, "
        "q.topic AS live_topic, q.status AS live_status, q.archived_at "
        "FROM reports r LEFT JOIN questions q ON q.id = r.question_id "
    )
    if status == "all":
        sql = base + "ORDER BY CASE WHEN r.status = 'pending' THEN 0 ELSE 1 END, r.id DESC LIMIT ?"
        args = (limit,)
    elif status == "resolved":
        sql = base + "WHERE r.status IN ('resolved', 'dismissed') ORDER BY r.id DESC LIMIT ?"
        args = (limit,)
    else:
        sql = base + "WHERE r.status = 'pending' ORDER BY r.id DESC LIMIT ?"
        args = (limit,)
    return conn.execute(sql, args).fetchall()


def report_json(row):
    return {
        "id": row["id"],
        "question_id": row["question_id"],
        "question_text": row["live_text"] or "",
        "answer_text": row["live_answer"] or "",
        "topic": row["live_topic"] or "",
        "question_status": row["live_status"],
        "question_archived": bool(row["archived_at"]),
        "question_missing": row["live_text"] is None,
        "reporter_name": row["reporter_name"] or "",
        "reason": row["reason"] or "",
        "status": row["status"],
        "created_at": row["created_at"],
        "resolved_at": row["resolved_at"],
    }


def pending_report_count(conn):
    ensure_reports_schema(conn)
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM reports WHERE status = ?", (REPORT_PENDING,)
    ).fetchone()
    return row["n"] or 0


def resolve_report(conn, report_id, status, resolver_id):
    """Mark one report fixed or dismissed. Returns 1 when it was pending."""
    ensure_reports_schema(conn)
    cur = conn.execute(
        "UPDATE reports SET status = ?, resolved_at = ?, resolved_by = ? "
        "WHERE id = ? AND status = ?",
        (status, now(), resolver_id, report_id, REPORT_PENDING),
    )
    if cur.rowcount:
        report = conn.execute("SELECT question_id FROM reports WHERE id = ?", (report_id,)).fetchone()
        if report:
            sync_question_board_state(conn, report["question_id"])
    return cur.rowcount


def add_website_issue(conn, reported_by, title, details, page):
    cur = conn.execute(
        "INSERT INTO website_issue_reports "
        "(reported_by, reporter_name, title, details, page, status, created_at) "
        "VALUES (?, '', ?, ?, ?, 'pending', ?)",
        (reported_by, title, details, page or "", now()),
    )
    return cur.lastrowid


def list_website_issues(conn, limit=500):
    return conn.execute(
        "SELECT id, reported_by, title, details, page, created_at "
        "FROM website_issue_reports ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()


def delete_website_issue(conn, issue_id):
    cur = conn.execute("DELETE FROM website_issue_reports WHERE id = ?", (issue_id,))
    return cur.rowcount


def user_count():
    with connection() as conn:
        return conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]


def get_user(conn, username):
    return conn.execute(
        "SELECT * FROM users WHERE username = ? COLLATE NOCASE", (username,)
    ).fetchone()


def get_user_by_id(conn, user_id):
    return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


def list_users(conn):
    return conn.execute(
        "SELECT id, username, display_name, role, active, must_change, created_at "
        "FROM users ORDER BY role DESC, username COLLATE NOCASE"
    ).fetchall()


def create_user(conn, username, password, salt, password_hash, role, display_name, must_change=0):
    cur = conn.execute(
        "INSERT INTO users (username, password_hash, salt, role, display_name, must_change, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (username, password_hash, salt, role, display_name or username, must_change, now()),
    )
    return cur.lastrowid


def update_password(conn, user_id, password_hash, salt):
    conn.execute(
        "UPDATE users SET password_hash = ?, salt = ?, must_change = 0 WHERE id = ?",
        (password_hash, salt, user_id),
    )


def set_user_active(conn, user_id, active):
    conn.execute("UPDATE users SET active = ? WHERE id = ?", (1 if active else 0, user_id))


def update_username(conn, user_id, username):
    conn.execute(
        "UPDATE users SET username = ?, display_name = CASE WHEN display_name = '' THEN ? ELSE display_name END "
        "WHERE id = ?",
        (username, username, user_id),
    )


def admin_set_password(conn, user_id, password_hash, salt):
    # the admin decides the password outright, so nothing is flagged for later
    conn.execute(
        "UPDATE users SET password_hash = ?, salt = ?, must_change = 0 WHERE id = ?",
        (password_hash, salt, user_id),
    )


def reset_progress(conn):
    """Wipe every recorded answer and let all sessions start the quiz afresh."""
    ensure_quiz_session_schema(conn)
    conn.execute("DELETE FROM attempts")
    conn.execute("DELETE FROM quiz_sessions")
    conn.execute("UPDATE sessions SET recent = ''")
    return conn.total_changes


def add_question(conn, question_text, answer_text, topic, status, submitted_by="", source="staff"):
    cur = conn.execute(
        "INSERT INTO questions (question_text, answer_text, topic, status, board_state, submitted_by, source, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (question_text, answer_text, topic, status, "active" if status == Q_APPROVED else "approval", submitted_by, source, now()),
    )
    return cur.lastrowid


def get_question(conn, question_id):
    return conn.execute("SELECT * FROM questions WHERE id = ?", (question_id,)).fetchone()


def list_questions(
    conn, status=None, topic=None, search=None, limit=500, offset=0,
    include_archived=False,
):
    sql = "SELECT * FROM questions WHERE 1 = 1"
    args = []
    if not include_archived:
        sql += " AND archived_at IS NULL"
    if status:
        sql += " AND status = ?"
        args.append(status)
    if topic:
        sql += " AND topic = ? COLLATE NOCASE"
        args.append(topic)
    if search:
        sql += " AND (question_text LIKE ? OR answer_text LIKE ?)"
        args.extend(["%" + search + "%", "%" + search + "%"])
    sql += " ORDER BY id DESC LIMIT ? OFFSET ?"
    args.extend([limit, offset])
    return conn.execute(sql, args).fetchall()


def list_pending(conn, limit=500):
    return conn.execute(
        "SELECT * FROM questions WHERE status = ? ORDER BY created_at ASC, id ASC LIMIT ?",
        (Q_PENDING, limit),
    ).fetchall()


def review_question(conn, question_id, status, reviewer_id, note=""):
    conn.execute(
        "UPDATE questions SET status = ?, "
        "reviewed_by = ?, reviewed_at = ?, review_note = ? WHERE id = ?",
        (status, reviewer_id, now(), note or "", question_id),
    )
    sync_question_board_state(conn, question_id)


def delete_question(conn, question_id):
    conn.execute("DELETE FROM questions WHERE id = ?", (question_id,))


def archive_question(conn, question_id):
    cur = conn.execute(
        "UPDATE questions SET archived_at = ?, board_state = 'archive' "
        "WHERE id = ? AND status = ? AND archived_at IS NULL",
        (now(), question_id, Q_APPROVED),
    )
    return cur.rowcount


def restore_question(conn, question_id):
    cur = conn.execute(
        "UPDATE questions SET archived_at = NULL, board_state = CASE WHEN outdated = 1 "
        "THEN 'time-sensitive' ELSE 'active' END "
        "WHERE id = ? AND status = ? AND archived_at IS NOT NULL",
        (question_id, Q_APPROVED),
    )
    if cur.rowcount:
        sync_question_board_state(conn, question_id)
    return cur.rowcount


def set_question_outdated(conn, question_id, tagged):
    """Give or remove a question's out-of-date tag."""
    ensure_outdated_schema(conn)
    conn.execute(
        "UPDATE questions SET outdated = ?, board_state = CASE "
        "WHEN board_state IN ('active', 'time-sensitive') THEN ? ELSE board_state END WHERE id = ?",
        (1 if tagged else 0, "time-sensitive" if tagged else "active", question_id),
    )


def list_stale(conn, limit=5000):
    """Every tagged question, newest first."""
    ensure_outdated_schema(conn)
    return conn.execute(
        "SELECT * FROM questions WHERE archived_at IS NULL AND outdated = 1 AND ai_pending = 0 "
        "ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()


def stale_count(conn):
    ensure_outdated_schema(conn)
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM questions WHERE archived_at IS NULL AND outdated = 1 AND ai_pending = 0"
    ).fetchone()
    return row["n"] or 0


def rename_topic(conn, old_topic, new_topic):
    """Move every question on one topic to another, across all statuses."""
    cur = conn.execute(
        "UPDATE questions SET topic = ? WHERE topic = ? COLLATE NOCASE",
        (new_topic, old_topic),
    )
    return cur.rowcount


def question_counts(conn):
    row = conn.execute(
        "SELECT "
        "SUM(CASE WHEN archived_at IS NULL THEN 1 ELSE 0 END) AS total, "
        "SUM(CASE WHEN status = 'approved' AND archived_at IS NULL THEN 1 ELSE 0 END) AS approved, "
        "SUM(CASE WHEN status = 'pending' AND archived_at IS NULL THEN 1 ELSE 0 END) AS pending, "
        "SUM(CASE WHEN status = 'rejected' AND archived_at IS NULL THEN 1 ELSE 0 END) AS rejected "
        "FROM questions"
    ).fetchone()
    return {
        "total": row["total"] or 0,
        "approved": row["approved"] or 0,
        "pending": row["pending"] or 0,
        "rejected": row["rejected"] or 0,
    }


def list_topics(conn, statuses=(Q_APPROVED,)):
    """Distinct topics, optionally across several statuses at once."""
    placeholders = ", ".join("?" for _ in statuses)
    return [
        r["topic"]
        for r in conn.execute(
            "SELECT DISTINCT topic FROM questions WHERE archived_at IS NULL "
            "AND status IN (%s) "
            "ORDER BY topic COLLATE NOCASE" % placeholders,
            tuple(statuses),
        )
    ]


def add_session(conn, token, user_id, csrf, expires_at):
    conn.execute(
        "INSERT INTO sessions (token, user_id, csrf, expires_at, created_at) VALUES (?, ?, ?, ?, ?)",
        (token, user_id, csrf, expires_at, now()),
    )


def get_session(conn, token):
    if not token:
        return None
    return conn.execute(
        "SELECT * FROM sessions WHERE token = ? AND expires_at > ?", (token, now())
    ).fetchone()


def delete_session(conn, token):
    conn.execute("DELETE FROM sessions WHERE token = ?", (token,))


def delete_sessions_for_user(conn, user_id):
    conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))


def purge_expired_sessions(conn):
    conn.execute("DELETE FROM sessions WHERE expires_at <= ?", (now(),))


def parse_recent(raw):
    out = []
    for part in (raw or "").split(","):
        part = part.strip()
        if part.isdigit():
            out.append(int(part))
    return out


def push_recent(conn, token, question_id, keep=2000):
    row = conn.execute("SELECT recent FROM sessions WHERE token = ?", (token,)).fetchone()
    recent = [q for q in parse_recent(row["recent"] if row else "") if q != question_id]
    recent.insert(0, question_id)
    conn.execute(
        "UPDATE sessions SET recent = ? WHERE token = ?",
        (",".join(str(q) for q in recent[:keep]), token),
    )


def record_attempt(conn, question_id, correct, skipped, answered_by,
                   quiz_session_id=None, question_text="", answer_text="", topic=""):
    ensure_quiz_session_schema(conn)
    conn.execute(
        "INSERT INTO attempts (question_id, correct, skipped, answered_by, created_at, "
        "quiz_session_id, question_text, answer_text, topic) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (question_id, 1 if correct else 0, 1 if skipped else 0, answered_by, now(),
         quiz_session_id, question_text or "", answer_text or "", topic or ""),
    )


def get_active_quiz_session(conn, user_id):
    """The quiz run this account is currently asking, if any."""
    ensure_quiz_session_schema(conn)
    if not user_id:
        return None
    return conn.execute(
        "SELECT * FROM quiz_sessions WHERE user_id = ? AND ended_at IS NULL "
        "ORDER BY id DESC LIMIT 1",
        (user_id,),
    ).fetchone()


def create_quiz_session(conn, user_id, username="", display_name="", topic=""):
    ensure_quiz_session_schema(conn)
    stamp = now()
    cur = conn.execute(
        "INSERT INTO quiz_sessions (user_id, username, display_name, topic, "
        "started_at, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, username or "", display_name or "", topic or "", stamp, stamp),
    )
    return cur.lastrowid


def get_quiz_session(conn, session_id):
    ensure_quiz_session_schema(conn)
    return conn.execute(
        "SELECT * FROM quiz_sessions WHERE id = ?", (session_id,)
    ).fetchone()


def note_quiz_session_topic(conn, session_id, topic_filter):
    """Remember which topic filter a run is using, for the admin list.

    A run that stays on one topic keeps its name. One that moves between
    topics is labelled Mixed so the list does not pretend otherwise.
    """
    topic_filter = (topic_filter or "").strip()
    if not topic_filter:
        return
    row = get_quiz_session(conn, session_id)
    if not row:
        return
    current = row["topic"] or ""
    if not current:
        conn.execute("UPDATE quiz_sessions SET topic = ? WHERE id = ?", (topic_filter, session_id))
    elif current != topic_filter and current != "Mixed":
        conn.execute("UPDATE quiz_sessions SET topic = 'Mixed' WHERE id = ?", (session_id,))


def quiz_session_counts(conn, session_id):
    row = conn.execute(
        "SELECT COUNT(*) AS total, "
        "COALESCE(SUM(CASE WHEN skipped = 0 THEN 1 ELSE 0 END), 0) AS asked, "
        "COALESCE(SUM(CASE WHEN skipped = 0 AND correct = 1 THEN 1 ELSE 0 END), 0) AS correct, "
        "COALESCE(SUM(CASE WHEN skipped = 1 THEN 1 ELSE 0 END), 0) AS skipped "
        "FROM attempts WHERE quiz_session_id = ?",
        (session_id,),
    ).fetchone()
    asked = row["asked"] or 0
    correct = row["correct"] or 0
    return {
        "asked": asked,
        "correct": correct,
        "incorrect": asked - correct,
        "skipped": row["skipped"] or 0,
        "total": row["total"] or 0,
        "accuracy": round(correct / asked * 100, 1) if asked else 0.0,
    }


def quiz_session_json(conn, row):
    counts = quiz_session_counts(conn, row["id"])
    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "username": row["username"],
        "display_name": row["display_name"] or row["username"],
        "topic": row["topic"],
        "started_at": row["started_at"],
        "ended_at": row["ended_at"],
        "asked": counts["asked"],
        "correct": counts["correct"],
        "incorrect": counts["incorrect"],
        "skipped": counts["skipped"],
        "total": counts["total"],
        "accuracy": counts["accuracy"],
    }


def list_quiz_sessions(conn, completed_only=True):
    """Every stored quiz run, newest first, each with its own totals."""
    ensure_quiz_session_schema(conn)
    sql = "SELECT * FROM quiz_sessions"
    if completed_only:
        sql += " WHERE ended_at IS NOT NULL"
    sql += " ORDER BY COALESCE(ended_at, started_at) DESC, id DESC"
    return [quiz_session_json(conn, row) for row in conn.execute(sql).fetchall()]


def list_quiz_session_attempts(conn, session_id):
    """Each answer inside one run, oldest first, with the question text kept.

    The question text is snapshotted when the answer is recorded, so deleting
    or editing the bank later does not rewrite what was actually asked.
    """
    ensure_quiz_session_schema(conn)
    rows = conn.execute(
        "SELECT a.id, a.question_id, a.correct, a.skipped, a.created_at, "
        "a.answered_by, a.question_text AS snap_text, a.answer_text AS snap_answer, "
        "a.topic AS snap_topic, "
        "q.question_text AS live_text, q.answer_text AS live_answer, q.topic AS live_topic "
        "FROM attempts a LEFT JOIN questions q ON q.id = a.question_id "
        "WHERE a.quiz_session_id = ? ORDER BY a.id ASC",
        (session_id,),
    ).fetchall()
    out = []
    for row in rows:
        if row["skipped"]:
            result = "skipped"
        elif row["correct"]:
            result = "correct"
        else:
            result = "incorrect"
        out.append(
            {
                "id": row["id"],
                "question_id": row["question_id"],
                "question_text": row["snap_text"] or row["live_text"] or "",
                "answer_text": row["snap_answer"] or row["live_answer"] or "",
                "topic": row["snap_topic"] or row["live_topic"] or "",
                "correct": bool(row["correct"]),
                "skipped": bool(row["skipped"]),
                "result": result,
                "created_at": row["created_at"],
            }
        )
    return out


def finish_quiz_session(conn, session_id):
    """Close a run. Empty runs are removed so the admin list stays meaningful."""
    ensure_quiz_session_schema(conn)
    count = conn.execute(
        "SELECT COUNT(*) FROM attempts WHERE quiz_session_id = ?", (session_id,)
    ).fetchone()[0]
    if not count:
        conn.execute("DELETE FROM quiz_sessions WHERE id = ?", (session_id,))
        return "deleted"
    conn.execute(
        "UPDATE quiz_sessions SET ended_at = ? WHERE id = ? AND ended_at IS NULL",
        (now(), session_id),
    )
    return "finished"


def finish_active_quiz_session(conn, user_id):
    row = get_active_quiz_session(conn, user_id)
    if not row:
        return None
    outcome = finish_quiz_session(conn, row["id"])
    return {"id": row["id"], "outcome": outcome}


def delete_quiz_session(conn, session_id):
    """Delete one stored run and every answer recorded inside it.

    The question bank and the accounts are left untouched.
    """
    ensure_quiz_session_schema(conn)
    conn.execute("DELETE FROM attempts WHERE quiz_session_id = ?", (session_id,))
    cur = conn.execute("DELETE FROM quiz_sessions WHERE id = ?", (session_id,))
    return cur.rowcount


def ensure_practice_schema(conn):
    """Solo practice runs, recorded apart from the squadron scoreboard.

    Fresh databases get the tables from SCHEMA. Older databases gain them
    here so the bank and its history are left untouched.
    """
    conn.execute(
        "CREATE TABLE IF NOT EXISTS practice_sessions ("
        "    id         INTEGER PRIMARY KEY AUTOINCREMENT,"
        "    name       TEXT NOT NULL DEFAULT '',"
        "    topic      TEXT NOT NULL DEFAULT '',"
        "    started_at TEXT NOT NULL,"
        "    ended_at   TEXT,"
        "    created_at TEXT NOT NULL"
        ")"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS practice_sessions_ended ON practice_sessions(ended_at)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS practice_attempts ("
        "    id                  INTEGER PRIMARY KEY AUTOINCREMENT,"
        "    practice_session_id INTEGER NOT NULL REFERENCES practice_sessions(id) ON DELETE CASCADE,"
        "    question_id         INTEGER NOT NULL REFERENCES questions(id) ON DELETE CASCADE,"
        "    correct             INTEGER NOT NULL DEFAULT 0 CHECK (correct IN (0, 1)),"
        "    skipped             INTEGER NOT NULL DEFAULT 0 CHECK (skipped IN (0, 1)),"
        "    created_at          TEXT NOT NULL,"
        "    question_text       TEXT NOT NULL DEFAULT '',"
        "    answer_text         TEXT NOT NULL DEFAULT '',"
        "    topic               TEXT NOT NULL DEFAULT ''"
        ")"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS practice_attempts_session ON practice_attempts(practice_session_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS practice_attempts_question ON practice_attempts(question_id)"
    )


def create_practice_session(conn, name, topic=""):
    """Start a solo practice run. Any earlier open run under the same name is
    closed first, so abandoned runs do not pile up in the admin list."""
    ensure_practice_schema(conn)
    stamp = now()
    conn.execute(
        "UPDATE practice_sessions SET ended_at = ? "
        "WHERE ended_at IS NULL AND name = ? COLLATE NOCASE",
        (stamp, name),
    )
    cur = conn.execute(
        "INSERT INTO practice_sessions (name, topic, started_at, created_at) "
        "VALUES (?, ?, ?, ?)",
        (name, topic or "", stamp, stamp),
    )
    return cur.lastrowid


def get_practice_session(conn, session_id):
    ensure_practice_schema(conn)
    return conn.execute(
        "SELECT * FROM practice_sessions WHERE id = ?", (session_id,)
    ).fetchone()


def practice_answered_ids(conn, session_id):
    """Questions already faced in this practice run, so none repeat."""
    ensure_practice_schema(conn)
    return [
        row["question_id"]
        for row in conn.execute(
            "SELECT question_id FROM practice_attempts WHERE practice_session_id = ?",
            (session_id,),
        )
    ]


def record_practice_attempt(conn, session_id, question_id, correct, skipped,
                            question_text="", answer_text="", topic=""):
    ensure_practice_schema(conn)
    conn.execute(
        "INSERT INTO practice_attempts (practice_session_id, question_id, correct, "
        "skipped, created_at, question_text, answer_text, topic) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (session_id, question_id, 1 if correct else 0, 1 if skipped else 0, now(),
         question_text or "", answer_text or "", topic or ""),
    )


def practice_session_counts(conn, session_id):
    row = conn.execute(
        "SELECT COUNT(*) AS total, "
        "COALESCE(SUM(CASE WHEN skipped = 0 THEN 1 ELSE 0 END), 0) AS asked, "
        "COALESCE(SUM(CASE WHEN skipped = 0 AND correct = 1 THEN 1 ELSE 0 END), 0) AS correct, "
        "COALESCE(SUM(CASE WHEN skipped = 1 THEN 1 ELSE 0 END), 0) AS skipped "
        "FROM practice_attempts WHERE practice_session_id = ?",
        (session_id,),
    ).fetchone()
    asked = row["asked"] or 0
    correct = row["correct"] or 0
    return {
        "asked": asked,
        "correct": correct,
        "incorrect": asked - correct,
        "skipped": row["skipped"] or 0,
        "total": row["total"] or 0,
        "accuracy": round(correct / asked * 100, 1) if asked else 0.0,
    }


def practice_session_json(conn, row):
    counts = practice_session_counts(conn, row["id"])
    return {
        "id": row["id"],
        "name": row["name"],
        "topic": row["topic"],
        "started_at": row["started_at"],
        "ended_at": row["ended_at"],
        "asked": counts["asked"],
        "correct": counts["correct"],
        "incorrect": counts["incorrect"],
        "skipped": counts["skipped"],
        "total": counts["total"],
        "accuracy": counts["accuracy"],
    }


def list_practice_sessions(conn, completed_only=True):
    """Every solo practice run, newest first, each with its own totals."""
    ensure_practice_schema(conn)
    sql = "SELECT * FROM practice_sessions"
    if completed_only:
        sql += " WHERE ended_at IS NOT NULL"
    sql += " ORDER BY name COLLATE NOCASE ASC, COALESCE(ended_at, started_at) DESC, id DESC"
    return [practice_session_json(conn, row) for row in conn.execute(sql).fetchall()]


def list_practice_attempts(conn, session_id):
    """Each answer inside one practice run, oldest first, with the question
    text kept as it was shown, so later bank edits do not rewrite history."""
    ensure_practice_schema(conn)
    rows = conn.execute(
        "SELECT a.id, a.question_id, a.correct, a.skipped, a.created_at, "
        "a.question_text AS snap_text, a.answer_text AS snap_answer, "
        "a.topic AS snap_topic, "
        "q.question_text AS live_text, q.answer_text AS live_answer, q.topic AS live_topic "
        "FROM practice_attempts a LEFT JOIN questions q ON q.id = a.question_id "
        "WHERE a.practice_session_id = ? ORDER BY a.id ASC",
        (session_id,),
    ).fetchall()
    out = []
    for row in rows:
        if row["skipped"]:
            result = "skipped"
        elif row["correct"]:
            result = "correct"
        else:
            result = "incorrect"
        out.append(
            {
                "id": row["id"],
                "question_id": row["question_id"],
                "question_text": row["snap_text"] or row["live_text"] or "",
                "answer_text": row["snap_answer"] or row["live_answer"] or "",
                "topic": row["snap_topic"] or row["live_topic"] or "",
                "correct": bool(row["correct"]),
                "skipped": bool(row["skipped"]),
                "result": result,
                "created_at": row["created_at"],
            }
        )
    return out


def finish_practice_session(conn, session_id):
    """Close a practice run. Empty runs are removed so the admin list stays
    meaningful."""
    ensure_practice_schema(conn)
    count = conn.execute(
        "SELECT COUNT(*) FROM practice_attempts WHERE practice_session_id = ?",
        (session_id,),
    ).fetchone()[0]
    if not count:
        conn.execute("DELETE FROM practice_sessions WHERE id = ?", (session_id,))
        return "deleted"
    conn.execute(
        "UPDATE practice_sessions SET ended_at = ? WHERE id = ? AND ended_at IS NULL",
        (now(), session_id),
    )
    return "finished"


def delete_practice_session(conn, session_id):
    """Delete one practice run and every answer recorded inside it.

    The question bank and the squadron results are left untouched.
    """
    ensure_practice_schema(conn)
    conn.execute("DELETE FROM practice_attempts WHERE practice_session_id = ?", (session_id,))
    cur = conn.execute("DELETE FROM practice_sessions WHERE id = ?", (session_id,))
    return cur.rowcount


def has_pending_report_by_name(conn, question_id, name):
    """A named guest already flagged this question and it is still open."""
    return conn.execute(
        "SELECT id FROM reports WHERE question_id = ? AND reported_by IS NULL "
        "AND reporter_name = ? COLLATE NOCASE AND status = ? LIMIT 1",
        (question_id, name, REPORT_PENDING),
    ).fetchone() is not None


def overall_stats(conn):
    row = conn.execute(
        "SELECT COUNT(*) AS total, "
        "COALESCE(SUM(CASE WHEN skipped = 0 THEN 1 ELSE 0 END), 0) AS asked, "
        "COALESCE(SUM(CASE WHEN skipped = 0 AND correct = 1 THEN 1 ELSE 0 END), 0) AS correct, "
        "COALESCE(SUM(CASE WHEN skipped = 1 THEN 1 ELSE 0 END), 0) AS skipped "
        "FROM attempts"
    ).fetchone()
    asked = row["asked"] or 0
    correct = row["correct"] or 0
    return {
        "asked": asked,
        "correct": correct,
        "incorrect": asked - correct,
        "skipped": row["skipped"] or 0,
        "accuracy": round(correct / asked * 100, 1) if asked else 0.0,
    }


def question_stats(conn):
    """Answer history per question across the whole squadron."""
    rows = conn.execute(
        "SELECT question_id, "
        "SUM(CASE WHEN skipped = 0 THEN 1 ELSE 0 END) AS asked, "
        "SUM(CASE WHEN skipped = 0 AND correct = 1 THEN 1 ELSE 0 END) AS correct, "
        "SUM(CASE WHEN skipped = 1 THEN 1 ELSE 0 END) AS skipped "
        "FROM attempts GROUP BY question_id"
    ).fetchall()
    return {
        r["question_id"]: {
            "asked": r["asked"] or 0,
            "correct": r["correct"] or 0,
            "incorrect": (r["asked"] or 0) - (r["correct"] or 0),
            "skipped": r["skipped"] or 0,
        }
        for r in rows
    }


def practice_overall_stats(conn):
    """Practice answer totals, kept apart from the squadron scoreboard."""
    ensure_practice_schema(conn)
    row = conn.execute(
        "SELECT COUNT(*) AS total, "
        "COALESCE(SUM(CASE WHEN skipped = 0 THEN 1 ELSE 0 END), 0) AS asked, "
        "COALESCE(SUM(CASE WHEN skipped = 0 AND correct = 1 THEN 1 ELSE 0 END), 0) AS correct, "
        "COALESCE(SUM(CASE WHEN skipped = 1 THEN 1 ELSE 0 END), 0) AS skipped "
        "FROM practice_attempts"
    ).fetchone()
    asked = row["asked"] or 0
    correct = row["correct"] or 0
    return {
        "asked": asked,
        "correct": correct,
        "incorrect": asked - correct,
        "skipped": row["skipped"] or 0,
        "accuracy": round(correct / asked * 100, 1) if asked else 0.0,
    }


def practice_question_stats(conn):
    """Practice answer history per question, using the live question text and
    topic while falling back to the snapshot kept with older attempts."""
    ensure_practice_schema(conn)
    rows = conn.execute(
        "SELECT a.question_id AS id, "
        "COALESCE(q.question_text, MAX(a.question_text), '') AS question_text, "
        "COALESCE(q.answer_text, MAX(a.answer_text), '') AS answer_text, "
        "COALESCE(q.topic, MAX(a.topic), '') AS topic, "
        "SUM(CASE WHEN a.skipped = 0 THEN 1 ELSE 0 END) AS asked, "
        "SUM(CASE WHEN a.skipped = 0 AND a.correct = 1 THEN 1 ELSE 0 END) AS correct, "
        "SUM(CASE WHEN a.skipped = 1 THEN 1 ELSE 0 END) AS skipped "
        "FROM practice_attempts a LEFT JOIN questions q ON q.id = a.question_id "
        "GROUP BY a.question_id"
    ).fetchall()
    out = []
    for row in rows:
        asked = row["asked"] or 0
        correct = row["correct"] or 0
        out.append(
            {
                "id": row["id"],
                "question_text": row["question_text"] or "",
                "answer_text": row["answer_text"] or "",
                "topic": row["topic"] or "",
                "asked": asked,
                "correct": correct,
                "incorrect": asked - correct,
                "skipped": row["skipped"] or 0,
            }
        )
    return out
