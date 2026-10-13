import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("QUIZ_DB", os.path.join(BASE_DIR, "questions.db"))

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
    submitted_by  TEXT NOT NULL DEFAULT '',
    source        TEXT NOT NULL DEFAULT 'staff',
    review_note   TEXT NOT NULL DEFAULT '',
    reviewed_by   INTEGER REFERENCES users(id) ON DELETE SET NULL,
    reviewed_at   TEXT,
    created_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS questions_status ON questions(status);
CREATE INDEX IF NOT EXISTS questions_topic ON questions(topic);

CREATE TABLE IF NOT EXISTS attempts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    question_id INTEGER NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
    correct     INTEGER NOT NULL DEFAULT 0 CHECK (correct IN (0, 1)),
    skipped     INTEGER NOT NULL DEFAULT 0 CHECK (skipped IN (0, 1)),
    answered_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS attempts_question ON attempts(question_id);
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
    try:
        conn.execute("ALTER TABLE users DROP COLUMN password_text")
    except sqlite3.Error:
        # older sqlite cannot drop a column; it stays, empty and unread
        pass


def init():
    conn = sqlite3.connect(DB_PATH, timeout=15, isolation_level=None)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        conn.executescript(SCHEMA)
        drop_readable_passwords(conn)
        conn.execute("PRAGMA wal_autocheckpoint = 512")
    finally:
        conn.close()


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
    conn.execute("DELETE FROM attempts")
    conn.execute("UPDATE sessions SET recent = ''")
    return conn.total_changes


def add_question(conn, question_text, answer_text, topic, status, submitted_by="", source="staff"):
    cur = conn.execute(
        "INSERT INTO questions (question_text, answer_text, topic, status, submitted_by, source, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (question_text, answer_text, topic, status, submitted_by, source, now()),
    )
    return cur.lastrowid


def get_question(conn, question_id):
    return conn.execute("SELECT * FROM questions WHERE id = ?", (question_id,)).fetchone()


def list_questions(conn, status=None, topic=None, search=None, limit=500, offset=0):
    sql = "SELECT * FROM questions WHERE 1 = 1"
    args = []
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
        "UPDATE questions SET status = ?, reviewed_by = ?, reviewed_at = ?, review_note = ? WHERE id = ?",
        (status, reviewer_id, now(), note or "", question_id),
    )


def delete_question(conn, question_id):
    conn.execute("DELETE FROM questions WHERE id = ?", (question_id,))


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
        "COUNT(*) AS total, "
        "SUM(CASE WHEN status = 'approved' THEN 1 ELSE 0 END) AS approved, "
        "SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) AS pending, "
        "SUM(CASE WHEN status = 'rejected' THEN 1 ELSE 0 END) AS rejected "
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
            "SELECT DISTINCT topic FROM questions WHERE status IN (%s) "
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


def record_attempt(conn, question_id, correct, skipped, answered_by):
    conn.execute(
        "INSERT INTO attempts (question_id, correct, skipped, answered_by, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (question_id, 1 if correct else 0, 1 if skipped else 0, answered_by, now()),
    )


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
