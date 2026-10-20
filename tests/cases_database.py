"""End-to-end cases grouped by database migrations."""

SECTIONS = {
    21: r'''

print("\n[19b] upgrade an existing database for archiving")
legacy_db = os.path.join(ROOT, "test_legacy_archive.db")
remove_db(legacy_db)
legacy_conn = sqlite3.connect(legacy_db)
legacy_conn.executescript("""
    CREATE TABLE users (id INTEGER PRIMARY KEY);
    CREATE TABLE questions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        question_text TEXT NOT NULL,
        answer_text TEXT NOT NULL DEFAULT '',
        topic TEXT NOT NULL DEFAULT 'General',
        status TEXT NOT NULL DEFAULT 'pending'
            CHECK (status IN ('pending', 'approved', 'rejected')),
        submitted_by TEXT NOT NULL DEFAULT '',
        source TEXT NOT NULL DEFAULT 'staff',
        review_note TEXT NOT NULL DEFAULT '',
        reviewed_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
        reviewed_at TEXT,
        created_at TEXT NOT NULL
    );
    CREATE TABLE attempts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        question_id INTEGER NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
        correct INTEGER NOT NULL DEFAULT 0 CHECK (correct IN (0, 1)),
        skipped INTEGER NOT NULL DEFAULT 0 CHECK (skipped IN (0, 1)),
        answered_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
        created_at TEXT NOT NULL
    );
    INSERT INTO questions (question_text, answer_text, topic, status, created_at)
        VALUES ('Legacy question', 'Legacy answer', 'Legacy topic', 'approved', '2025-01-01');
    INSERT INTO attempts (question_id, correct, created_at)
        VALUES (1, 1, '2025-01-02');
""")
legacy_conn.close()
previous_db_path = dbmod.DB_PATH
try:
    dbmod.DB_PATH = legacy_db
    dbmod.init()
    legacy_conn = sqlite3.connect(legacy_db)
    columns = {row[1] for row in legacy_conn.execute("PRAGMA table_info(questions)")}
    attempt_count = legacy_conn.execute("SELECT COUNT(*) FROM attempts").fetchone()[0]
    legacy_schema_version = legacy_conn.execute("PRAGMA user_version").fetchone()[0]
    website_table = legacy_conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'website_issue_reports'"
    ).fetchone()
    legacy_conn.close()
finally:
    dbmod.DB_PATH = previous_db_path
    remove_db(legacy_db)
check("old question tables gain the archive field", "archived_at" in columns)
check("old attempts survive the archive migration", attempt_count == 1, str(attempt_count))
check("successful legacy migration records its schema version", legacy_schema_version == dbmod.SCHEMA_VERSION, str(legacy_schema_version))
check("legacy migration creates the website issue table", website_table is not None, str(website_table))
    
    ''',
}
