"""admin API handlers."""
import csv
import io
import json
from datetime import datetime, timedelta, timezone
from http import HTTPStatus

import auth
import db
import quiz
from api_common import ApiError, bad_request, require_fields

def api_list_reports(ctx):
    status = (ctx.q("status") or "pending").strip().lower()
    if status not in ("pending", "resolved", "all"):
        raise bad_request("unknown report status")
    try:
        limit = int(ctx.q("limit") or 200)
    except ValueError:
        raise bad_request("limit must be a number")
    if limit < 1 or limit > 5000:
        raise bad_request("limit must be between 1 and 5000")
    rows = db.list_reports(ctx.conn, status, limit)
    return {
        "reports": [db.report_json(r) for r in rows],
        "counts": db.question_counts(ctx.conn),
        "stale_count": db.stale_count(ctx.conn),
        "report_count": db.pending_report_count(ctx.conn),
    }


def api_resolve_report(ctx):
    report_id = int(ctx.match.group("id"))
    report = db.get_report(ctx.conn, report_id)
    if not report:
        raise ApiError(HTTPStatus.NOT_FOUND, "report not found")
    action = (ctx.body.get("action") or "resolved").strip().lower() \
        if isinstance(ctx.body.get("action"), str) else "resolved"
    if action not in ("resolved", "dismissed"):
        raise bad_request("action must be resolved or dismissed")
    if not db.resolve_report(ctx.conn, report_id, action, ctx.user["id"]):
        raise ApiError(HTTPStatus.CONFLICT, "that report is already handled")
    return {"ok": True, "counts": db.question_counts(ctx.conn),
            "stale_count": db.stale_count(ctx.conn),
            "report_count": db.pending_report_count(ctx.conn)}


def api_edit_question(ctx):
    question_id = int(ctx.match.group("id"))
    existing = db.get_question(ctx.conn, question_id)
    if not existing:
        raise ApiError(HTTPStatus.NOT_FOUND, "question not found")
    question_text = (ctx.body.get("question_text") or existing["question_text"]).strip()
    answer_text = (ctx.body.get("answer_text") or "").strip()
    if ctx.body.get("answer_text") is None:
        answer_text = existing["answer_text"]
    topic = (ctx.body.get("topic") or existing["topic"]).strip() or "General"
    ctx.conn.execute(
        "UPDATE questions SET question_text = ?, answer_text = ?, topic = ?, outdated = 0, needs_review = 0, "
        "ai_pending = 0, ai_question_text = '', ai_answer_text = '', ai_topic = '', ai_reason = '' WHERE id = ?",
        (question_text, answer_text, topic, question_id),
    )
    db.sync_question_board_state(ctx.conn, question_id)
    return {"ok": True}


def api_rename_topic(ctx):
    # a topic is only a label, so renaming it moves every question carrying it,
    # whatever its status, and leaves the questions themselves untouched
    old_topic = (ctx.body.get("from") or "").strip()
    new_topic = (ctx.body.get("to") or "").strip()
    if not old_topic:
        raise bad_request("current topic is required")
    if not new_topic:
        raise bad_request("new topic is required")
    if len(new_topic) > 80:
        raise bad_request("topic is too long")
    if new_topic.lower() == old_topic.lower():
        raise bad_request("that is the same topic")
    moved = db.rename_topic(ctx.conn, old_topic, new_topic)
    if not moved:
        raise ApiError(HTTPStatus.NOT_FOUND, "no questions on that topic")
    return {
        "ok": True,
        "from": old_topic,
        "to": new_topic,
        "moved": moved,
        "counts": db.question_counts(ctx.conn),
    }


def parse_import(text, fmt):
    if fmt == "json":
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise bad_request(f"invalid json: {exc.msg} at line {exc.lineno}")
        if isinstance(data, dict):
            data = data.get("questions", data.get("data", []))
        if not isinstance(data, list):
            raise bad_request("json must be a list of questions")
        rows = []
        for item in data:
            if not isinstance(item, dict):
                continue
            rows.append(
                (
                    (item.get("question") or item.get("question_text") or "").strip(),
                    (item.get("answer") or item.get("answer_text") or "").strip(),
                    (item.get("topic") or "General").strip() or "General",
                )
            )
        return [r for r in rows if r[0]]

    rows = []
    for record in csv.reader(io.StringIO(text)):
        if not record or not any(cell.strip() for cell in record):
            continue
        cells = [cell.strip() for cell in record]
        if cells[0].lower() in ("question", "question_text"):
            continue
        rows.append(
            (
                cells[0],
                cells[1] if len(cells) > 1 else "",
                cells[2] if len(cells) > 2 else "General",
            )
        )
    return [r for r in rows if r[0]]


def import_questions(ctx):
    fields = require_fields(ctx.body, "content", "format")
    fmt = fields["format"].strip().lower()
    if fmt not in ("csv", "json"):
        raise bad_request("format must be csv or json")

    rows = parse_import(fields["content"], fmt)
    if not rows:
        raise bad_request("no questions found in that file")

    seen = set()
    added = 0
    duplicates = 0
    with db.transaction(ctx.conn):
        for question_text, answer_text, topic in rows:
            key = question_text.lower()
            if key in seen:
                duplicates += 1
                continue
            seen.add(key)
            existing = ctx.conn.execute(
                "SELECT id FROM questions WHERE question_text = ? COLLATE NOCASE", (question_text,)
            ).fetchone()
            if existing:
                duplicates += 1
                continue
            db.add_question(
                ctx.conn,
                question_text=question_text[:2000],
                answer_text=answer_text[:2000],
                topic=topic[:80] or "General",
                status=db.Q_APPROVED,
                submitted_by=ctx.user["display_name"],
                source="import",
            )
            added += 1
    return {
        "added": added,
        "duplicates": duplicates,
        "counts": db.question_counts(ctx.conn),
        "message": f"imported {added} questions ({duplicates} already existed)",
    }


def api_delete_all_questions(ctx):
    if (ctx.body.get("confirm") or "").strip() != "DELETE ALL QUESTIONS":
        raise bad_request("type DELETE ALL QUESTIONS to confirm")
    count = ctx.conn.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
    with db.transaction(ctx.conn):
        ctx.conn.execute("DELETE FROM questions")
    return {
        "ok": True,
        "deleted": count,
        "counts": db.question_counts(ctx.conn),
        "stale_count": db.stale_count(ctx.conn),
        "report_count": db.pending_report_count(ctx.conn),
        "message": f"deleted all {count} questions",
    }


def api_stats(ctx):
    stats = db.question_stats(ctx.conn)
    rows = db.list_questions(ctx.conn, status=db.Q_APPROVED)

    questions = []
    for row in rows:
        stat = stats.get(row["id"], {"asked": 0, "correct": 0, "incorrect": 0, "skipped": 0})
        questions.append(
            {
                "id": row["id"],
                "question_text": row["question_text"],
                "topic": row["topic"],
                "asked": stat["asked"],
                "correct": stat["correct"],
                "incorrect": stat["incorrect"],
                "skipped": stat["skipped"],
                "accuracy": round(stat["correct"] / stat["asked"] * 100, 1)
                if stat["asked"]
                else None,
                "weight": round(quiz.weight_for(stat["asked"], stat["correct"], 0), 3),
            }
        )

    # Weakest topics first so the areas needing work are at the top.
    by_topic = {}
    for question in questions:
        by_topic.setdefault(question["topic"], []).append(question)

    topics = []
    for name, items in by_topic.items():
        asked = sum(i["asked"] for i in items)
        correct = sum(i["correct"] for i in items)
        topics.append(
            {
                "topic": name,
                "question_count": len(items),
                "asked": asked,
                "correct": correct,
                "incorrect": asked - correct,
                "skipped": sum(i["skipped"] for i in items),
                "accuracy": round(correct / asked * 100, 1) if asked else None,
            }
        )
    topics.sort(key=lambda t: (t["accuracy"] is None, t["accuracy"] if t["accuracy"] is not None else 0))

    return {
        "overall": db.overall_stats(ctx.conn),
        "topics": topics,
        "questions": questions,
    }


def api_progress_trends(ctx):
    """Return the last 12 complete/current weeks of squadron quiz attempts."""
    today = datetime.now(timezone.utc).date()
    this_monday = today - timedelta(days=today.weekday())
    first_monday = this_monday - timedelta(weeks=11)
    rows = ctx.conn.execute(
        "SELECT date(created_at, '-' || ((CAST(strftime('%w', created_at) AS INTEGER) + 6) % 7) || ' days') AS week_start, "
        "SUM(CASE WHEN skipped = 0 AND correct = 1 THEN 1 ELSE 0 END) AS correct, "
        "SUM(CASE WHEN skipped = 0 AND correct = 0 THEN 1 ELSE 0 END) AS incorrect, "
        "SUM(CASE WHEN skipped = 1 THEN 1 ELSE 0 END) AS skipped "
        "FROM attempts WHERE created_at >= ? GROUP BY week_start ORDER BY week_start",
        (first_monday.isoformat(),),
    ).fetchall()
    by_week = {row["week_start"]: row for row in rows}
    weeks = []
    for offset in range(12):
        week_start = first_monday + timedelta(weeks=offset)
        row = by_week.get(week_start.isoformat())
        correct = row["correct"] if row else 0
        incorrect = row["incorrect"] if row else 0
        skipped = row["skipped"] if row else 0
        scored = correct + incorrect
        weeks.append({
            "week_start": week_start.isoformat(),
            "correct": correct,
            "incorrect": incorrect,
            "skipped": skipped,
            "scored": scored,
            "accuracy": round(correct / scored * 100, 1) if scored else None,
        })
    return {"weeks": weeks, "minimum_sample": 5}


def api_list_users(ctx):
    return {"users": [dict(r) for r in db.list_users(ctx.conn)]}


def api_create_user(ctx):
    fields = require_fields(ctx.body, "username", "password", "role")
    if fields["role"] not in (db.USER_ADMIN, db.USER_STAFF):
        raise bad_request("role must be admin or staff")
    try:
        auth.validate_username(fields["username"])
        auth.validate_password(fields["password"])
    except ValueError as exc:
        raise bad_request(str(exc))
    if db.get_user(ctx.conn, fields["username"]):
        raise ApiError(HTTPStatus.CONFLICT, "that username already exists")
    digest, salt = auth.hash_password(fields["password"])
    user_id = db.create_user(
        ctx.conn,
        username=fields["username"],
        password=fields["password"],
        salt=salt,
        password_hash=digest,
        role=fields["role"],
        display_name=(ctx.body.get("display_name") or "").strip() or fields["username"],
    )
    return {"ok": True, "id": user_id}


def api_set_user_active(ctx):
    user_id = int(ctx.match.group("id"))
    active = 1 if ctx.body.get("active") else 0
    target = db.get_user_by_id(ctx.conn, user_id)
    if not target:
        raise ApiError(HTTPStatus.NOT_FOUND, "user not found")
    if target["role"] == db.USER_ADMIN and not active:
        raise bad_request("you cannot disable your own admin account")
    if target["id"] == ctx.user["id"]:
        raise bad_request("you cannot change your own account")
    db.set_user_active(ctx.conn, user_id, active)
    if not active:
        db.delete_sessions_for_user(ctx.conn, user_id)
    return {"ok": True}


def api_set_user_username(ctx):
    user_id = int(ctx.match.group("id"))
    target = db.get_user_by_id(ctx.conn, user_id)
    if not target:
        raise ApiError(HTTPStatus.NOT_FOUND, "user not found")
    if target["id"] == ctx.user["id"]:
        raise bad_request("you cannot change your own username here")
    username = (ctx.body.get("username") or "").strip()
    try:
        auth.validate_username(username)
    except ValueError as exc:
        raise bad_request(str(exc))
    existing = db.get_user(ctx.conn, username)
    if existing and existing["id"] != user_id:
        raise ApiError(HTTPStatus.CONFLICT, "that username already exists")
    if username == target["username"]:
        return {"ok": True, "id": user_id}
    db.update_username(ctx.conn, user_id, username)
    return {"ok": True, "id": user_id}


def api_set_user_password(ctx):
    user_id = int(ctx.match.group("id"))
    target = db.get_user_by_id(ctx.conn, user_id)
    if not target:
        raise ApiError(HTTPStatus.NOT_FOUND, "user not found")
    if target["id"] == ctx.user["id"]:
        raise bad_request("use change password for your own account")
    password = ctx.body.get("password") or ""
    try:
        auth.validate_password(password)
    except ValueError as exc:
        raise bad_request(str(exc))
    digest, salt = auth.hash_password(password)
    db.admin_set_password(ctx.conn, user_id, digest, salt)
    # the old password no longer works, so any open session must be dropped
    db.delete_sessions_for_user(ctx.conn, user_id)
    return {"ok": True, "id": user_id, "message": "password updated"}


def api_reset_progress(ctx):
    # this is destructive and irreversible, so insist the client confirmed it
    if not ctx.body.get("confirm"):
        raise bad_request("confirmation required before deleting all progress")
    db.reset_progress(ctx.conn)
    return {"ok": True, "message": "all recorded progress has been deleted",
            "overall": db.overall_stats(ctx.conn)}


def api_list_quiz_sessions(ctx):
    return {"sessions": db.list_quiz_sessions(ctx.conn, completed_only=True)}


def api_get_quiz_session(ctx):
    session_id = int(ctx.match.group("id"))
    row = db.get_quiz_session(ctx.conn, session_id)
    if not row or not row["ended_at"]:
        raise ApiError(HTTPStatus.NOT_FOUND, "session not found")
    return {
        "session": db.quiz_session_json(ctx.conn, row),
        "attempts": db.list_quiz_session_attempts(ctx.conn, session_id),
    }


def api_delete_quiz_session(ctx):
    # deleting one session is destructive and irreversible, like the
    # delete-all-progress control, so insist the client confirmed it
    if not ctx.body.get("confirm"):
        raise bad_request("confirmation required before deleting this session")
    session_id = int(ctx.match.group("id"))
    row = db.get_quiz_session(ctx.conn, session_id)
    if not row:
        raise ApiError(HTTPStatus.NOT_FOUND, "session not found")
    db.delete_quiz_session(ctx.conn, session_id)
    return {"ok": True, "message": "that quiz session has been deleted",
            "overall": db.overall_stats(ctx.conn)}


