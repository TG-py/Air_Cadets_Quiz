import csv
import io
import json
import mimetypes
import os
import re
import secrets
import sys
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, unquote

import auth
import db
import quiz

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")

HOST = os.environ.get("QUIZ_HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", os.environ.get("QUIZ_PORT", "8001")))
SECURE_COOKIES = os.environ.get("QUIZ_SECURE_COOKIES", "0") == "1"
LOG_REQUESTS = os.environ.get("QUIZ_LOG", "0") == "1"
COOKIE_NAME = "quiz_session"
MAX_BODY_BYTES = 8 * 1024 * 1024

CONTENT_SECURITY_POLICY = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
    "form-action 'self'; frame-ancestors 'none'; base-uri 'none'"
)


class ApiError(Exception):
    def __init__(self, status, message, reason=None):
        super().__init__(message)
        self.status = status
        self.message = message
        self.reason = reason


def bad_request(message):
    return ApiError(HTTPStatus.BAD_REQUEST, message)


def require_fields(data, *fields):
    out = {}
    for field in fields:
        value = (data.get(field) or "").strip() if isinstance(data.get(field), str) else data.get(field)
        if value in (None, ""):
            raise bad_request("%s is required" % field.replace("_", " "))
        out[field] = value
    return out


class Ctx:
    def __init__(self, handler, conn, session, user, query, body, match):
        self.handler = handler
        self.conn = conn
        self.session = session
        self.user = user
        self.query = query
        self.body = body if isinstance(body, dict) else {}
        self.match = match

    def q(self, name, default=None):
        values = self.query.get(name)
        return values[0] if values else default


def issue_guest_session(ctx):
    token, csrf, expires = auth.start_session(ctx.conn, None)
    ctx.handler.set_cookie(token, expires)
    return csrf


def api_me(ctx):
    csrf = ctx.session["csrf"] if ctx.session else issue_guest_session(ctx)
    payload = {
        "user": auth.public_user(ctx.user),
        "csrf": csrf,
        "counts": db.question_counts(ctx.conn),
        "topics": db.list_topics(ctx.conn),
    }
    if ctx.user and ctx.user["role"] == db.USER_ADMIN:
        payload["stale_count"] = db.stale_count(ctx.conn)
        payload["report_count"] = db.pending_report_count(ctx.conn)
    return payload


def api_login(ctx):
    fields = require_fields(ctx.body, "username", "password")
    ip = ctx.handler.client_ip()
    key = auth.login_rate_key(ip, fields["username"])
    remaining = auth.lockout_remaining(key)
    if remaining:
        raise ApiError(
            HTTPStatus.TOO_MANY_REQUESTS,
            "too many failed attempts, wait %d seconds" % remaining,
        )

    user = db.get_user(ctx.conn, fields["username"])
    if not user or not user["active"] or not auth.verify_password(fields["password"], user):
        auth.register_failure(key)
        raise ApiError(HTTPStatus.UNAUTHORIZED, "incorrect username or password")

    auth.clear_failures(key)
    if ctx.session:
        db.delete_session(ctx.conn, ctx.session["token"])
    db.purge_expired_sessions(ctx.conn)
    token, csrf, expires = auth.start_session(ctx.conn, user["id"])
    ctx.handler.set_cookie(token, expires)
    return {
        "user": auth.public_user(user),
        "csrf": csrf,
        "counts": db.question_counts(ctx.conn),
    }


def api_logout(ctx):
    if ctx.user:
        db.finish_active_quiz_session(ctx.conn, ctx.user["id"])
    if ctx.session:
        db.delete_session(ctx.conn, ctx.session["token"])
    ctx.handler.clear_cookie()
    return {"ok": True}


def api_change_password(ctx):
    fields = require_fields(ctx.body, "current_password", "new_password")
    if not auth.verify_password(fields["current_password"], ctx.user):
        raise ApiError(HTTPStatus.FORBIDDEN, "current password is incorrect")
    auth.validate_password(fields["new_password"])
    digest, salt = auth.hash_password(fields["new_password"])
    db.update_password(ctx.conn, ctx.user["id"], digest, salt)
    db.delete_sessions_for_user(ctx.conn, ctx.user["id"])
    ctx.handler.clear_cookie()
    return {"ok": True, "message": "password changed, please log in again"}


def api_next_question(ctx):
    topic = (ctx.q("topic") or "").strip() or None

    if topic and topic not in db.list_topics(ctx.conn):
        raise bad_request("unknown topic")

    recent = db.parse_recent(ctx.session["recent"]) if ctx.session else []
    pool = quiz.build_pool(ctx.conn, topic)
    question = quiz.pick(pool, recent)

    if not question:
        counts = db.question_counts(ctx.conn)
        if counts["approved"] == 0:
            raise ApiError(
                HTTPStatus.CONFLICT,
                f"no approved questions yet{' - log in as admin and add some' if not ctx.user else ''}",
                "empty",
            )
        if not pool:
            raise ApiError(
                HTTPStatus.CONFLICT, "no approved questions match that topic", "topic"
            )
        raise ApiError(
            HTTPStatus.CONFLICT,
            "every approved question has already been asked in this session - "
            "sign out and back in to start a fresh one",
            "exhausted",
        )

    return {"question": question}


def api_record_attempt(ctx):
    fields = require_fields(ctx.body, "question_id")
    try:
        question_id = int(fields["question_id"])
    except (TypeError, ValueError):
        raise bad_request("question_id must be a number")

    question = db.get_question(ctx.conn, question_id)
    if not question or question["status"] != db.Q_APPROVED or question["archived_at"]:
        raise bad_request("unknown question")

    skipped = 1 if ctx.body.get("skipped") else 0
    correct = 1 if ctx.body.get("correct") else 0
    topic_filter = (ctx.body.get("topic_filter") or ctx.body.get("topic") or "")
    topic_filter = topic_filter.strip() if isinstance(topic_filter, str) else ""

    # every answer belongs to one stored quiz run, so the admin can later open
    # each session on its own. The run is created lazily so older clients that
    # just post answers still get grouped without calling anything else first.
    run = db.get_active_quiz_session(ctx.conn, ctx.user["id"])
    if not run:
        run_id = db.create_quiz_session(
            ctx.conn,
            ctx.user["id"],
            ctx.user["username"],
            ctx.user["display_name"] or ctx.user["username"],
            topic_filter,
        )
        run = db.get_quiz_session(ctx.conn, run_id)
    elif topic_filter:
        db.note_quiz_session_topic(ctx.conn, run["id"], topic_filter)

    db.record_attempt(
        ctx.conn,
        question_id,
        correct,
        skipped,
        ctx.user["id"],
        quiz_session_id=run["id"],
        question_text=question["question_text"],
        answer_text=question["answer_text"],
        topic=question["topic"],
    )
    # a question counts as asked once it has been put to the squadron, so
    # switching topic without answering leaves it available to come back to
    if ctx.session:
        db.push_recent(ctx.conn, ctx.session["token"], question_id)
    return {"ok": True, "overall": db.overall_stats(ctx.conn), "quiz_session_id": run["id"]}


def api_finish_quiz_session(ctx):
    """Close the current quiz run and let the next question start a fresh one.

    Finishing clears the "already asked" list for this login, so asking again
    after the summary offers every question once more.
    """
    finished = db.finish_active_quiz_session(ctx.conn, ctx.user["id"])
    if ctx.session:
        ctx.conn.execute("UPDATE sessions SET recent = '' WHERE token = ?", (ctx.session["token"],))
    if not finished:
        return {"ok": True, "finished": False, "overall": db.overall_stats(ctx.conn)}
    counts = db.quiz_session_counts(ctx.conn, finished["id"]) if finished["outcome"] == "finished" else None
    return {
        "ok": True,
        "finished": finished["outcome"] == "finished",
        "quiz_session_id": finished["id"],
        "session": counts,
        "overall": db.overall_stats(ctx.conn),
    }


def api_topics(ctx):
    """Topics a submitted question can be filed under: anything approved or
    awaiting review. Available without an account so cadets can pick one."""
    return {
        "topics": db.list_topics(ctx.conn, statuses=(db.Q_APPROVED, db.Q_PENDING))
    }


def api_question_counts(ctx):
    return {
        "counts": db.question_counts(ctx.conn),
        "topics": db.list_topics(ctx.conn),
        "pending": db.question_counts(ctx.conn)["pending"] if ctx.user and ctx.user["role"] == db.USER_ADMIN else 0,
    }


def question_json(row, include_private=True):
    out = {
        "id": row["id"],
        "question_text": row["question_text"],
        "answer_text": row["answer_text"],
        "topic": row["topic"],
        "status": row["status"],
        "archived_at": row["archived_at"],
        "created_at": row["created_at"],
        "outdated": bool(row["outdated"]),
    }
    if include_private:
        out.update(
            {
                "submitted_by": row["submitted_by"],
                "source": row["source"],
                "review_note": row["review_note"],
                "reviewed_at": row["reviewed_at"],
            }
        )
    return out


def api_list_questions(ctx):
    if not ctx.user:
        raise ApiError(HTTPStatus.FORBIDDEN, "staff/NCO only")
    status = ctx.q("status") or None
    include_archived = ctx.q("include_archived") == "1"
    if include_archived and ctx.user["role"] != db.USER_ADMIN:
        raise ApiError(HTTPStatus.FORBIDDEN, "only admins can view archived questions")
    if status and ctx.user["role"] != db.USER_ADMIN and status != db.Q_APPROVED:
        raise ApiError(HTTPStatus.FORBIDDEN, "only admins can review submissions")
    rows = db.list_questions(
        ctx.conn,
        status=status,
        topic=(ctx.q("topic") or "").strip() or None,
        search=(ctx.q("q") or "").strip() or None,
        include_archived=include_archived,
    )
    payload = {
        "questions": [question_json(r) for r in rows],
        "counts": db.question_counts(ctx.conn),
        "topics": db.list_topics(ctx.conn),
    }
    if ctx.user and ctx.user["role"] == db.USER_ADMIN:
        payload["stale_count"] = db.stale_count(ctx.conn)
        payload["report_count"] = db.pending_report_count(ctx.conn)
    return payload


SUBMIT_FIELDS = (
    ("question_text", "question", 5, 2000),
    ("answer_text", "answer", 1, 2000),
    ("topic", "topic", 1, 80),
)
NAME_FIELD = ("submitted_by", "name", 2, 80)


def clean_field(ctx, key, label, minimum, maximum):
    raw = ctx.body.get(key)
    value = raw.strip() if isinstance(raw, str) else ""
    if not value:
        raise bad_request("%s is required" % label)
    if len(value) < minimum:
        raise bad_request("%s is too short" % label)
    if len(value) > maximum:
        raise bad_request(f"{label} is too long (max {maximum} characters)")
    return value


def api_submit_question(ctx):
    staff = bool(ctx.user)
    values = {
        key: clean_field(ctx, key, label, minimum, maximum)
        for key, label, minimum, maximum in SUBMIT_FIELDS
    }

    if staff:
        # adding straight from the question bank, so the account supplies the name
        provided = ctx.body.get("submitted_by")
        values["submitted_by"] = provided.strip() if isinstance(provided, str) and provided.strip() else (
            ctx.user["display_name"] or ctx.user["username"]
        )
    else:
        values["submitted_by"] = clean_field(ctx, *NAME_FIELD)

    status = db.Q_APPROVED if staff else db.Q_PENDING
    question_id = db.add_question(
        ctx.conn,
        question_text=values["question_text"],
        answer_text=values["answer_text"],
        topic=values["topic"],
        status=status,
        submitted_by=values["submitted_by"],
        source="staff" if staff else "cadet",
    )
    return {
        "id": question_id,
        "status": status,
        "message": "question added" if staff else "question submitted for review, thank you",
    }


def api_pending(ctx):
    return {
        "questions": [question_json(r) for r in db.list_pending(ctx.conn)],
        "counts": db.question_counts(ctx.conn),
        "stale_count": db.stale_count(ctx.conn),
        "report_count": db.pending_report_count(ctx.conn),
    }


def api_review(ctx):
    status = ctx.match.group("status")
    if status not in ("approve", "reject"):
        raise bad_request("unknown review action")
    question_id = int(ctx.match.group("id"))
    question = db.get_question(ctx.conn, question_id)
    if not question or question["archived_at"]:
        raise ApiError(HTTPStatus.NOT_FOUND, "question not found")
    note = (ctx.body.get("note") or "").strip()[:300]
    db.review_question(
        ctx.conn,
        question_id,
        db.Q_APPROVED if status == "approve" else db.Q_REJECTED,
        ctx.user["id"],
        note,
    )
    return {"ok": True, "counts": db.question_counts(ctx.conn),
            "stale_count": db.stale_count(ctx.conn),
            "report_count": db.pending_report_count(ctx.conn)}


def api_delete_question(ctx):
    question_id = int(ctx.match.group("id"))
    if not db.get_question(ctx.conn, question_id):
        raise ApiError(HTTPStatus.NOT_FOUND, "question not found")
    db.delete_question(ctx.conn, question_id)
    return {"ok": True, "counts": db.question_counts(ctx.conn),
            "stale_count": db.stale_count(ctx.conn),
            "report_count": db.pending_report_count(ctx.conn)}


def api_archive_question(ctx):
    question_id = int(ctx.match.group("id"))
    if not db.archive_question(ctx.conn, question_id):
        raise ApiError(
            HTTPStatus.CONFLICT,
            "only an accepted question can be archived",
        )
    return {"ok": True, "counts": db.question_counts(ctx.conn),
            "stale_count": db.stale_count(ctx.conn),
            "report_count": db.pending_report_count(ctx.conn)}


def api_restore_question(ctx):
    question_id = int(ctx.match.group("id"))
    if not db.restore_question(ctx.conn, question_id):
        raise ApiError(HTTPStatus.CONFLICT, "question is not archived")
    return {"ok": True, "counts": db.question_counts(ctx.conn),
            "stale_count": db.stale_count(ctx.conn),
            "report_count": db.pending_report_count(ctx.conn)}


def api_list_stale(ctx):
    rows = db.list_stale(ctx.conn)
    return {
        "questions": [question_json(r) for r in rows],
        "counts": db.question_counts(ctx.conn),
        "stale_count": db.stale_count(ctx.conn),
        "report_count": db.pending_report_count(ctx.conn),
    }


def api_set_stale(ctx):
    question_id = int(ctx.match.group("id"))
    question = db.get_question(ctx.conn, question_id)
    if not question or question["archived_at"]:
        raise ApiError(HTTPStatus.NOT_FOUND, "question not found")
    tagged = bool(ctx.body.get("tagged"))
    db.set_question_outdated(ctx.conn, question_id, tagged)
    return {"ok": True, "counts": db.question_counts(ctx.conn),
            "stale_count": db.stale_count(ctx.conn),
            "report_count": db.pending_report_count(ctx.conn)}


def api_report_question(ctx):
    # NCOs spot wrong questions while asking them; the report lands with the admin
    question_id = int(ctx.match.group("id"))
    question = db.get_question(ctx.conn, question_id)
    if not question or question["status"] != db.Q_APPROVED or question["archived_at"]:
        raise bad_request("unknown question")
    reason = (ctx.body.get("reason") or "").strip() if isinstance(ctx.body.get("reason"), str) else ""
    if len(reason) > 1000:
        raise bad_request("report is too long (max 1000 characters)")
    if db.has_pending_report(ctx.conn, question_id, ctx.user["id"]):
        raise ApiError(HTTPStatus.CONFLICT, "you have already reported this question")
    db.add_report(
        ctx.conn,
        question_id,
        ctx.user["id"],
        ctx.user["display_name"] or ctx.user["username"],
        reason,
    )
    return {"ok": True, "message": "reported - an admin will check it"}


def api_list_reports(ctx):
    status = (ctx.q("status") or "pending").strip().lower()
    if status not in ("pending", "resolved", "all"):
        raise bad_request("unknown report status")
    rows = db.list_reports(ctx.conn, status)
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
        "UPDATE questions SET question_text = ?, answer_text = ?, topic = ? WHERE id = ?",
        (question_text, answer_text, topic, question_id),
    )
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


ROUTES = [
    ("GET", r"^/api/auth/me$", api_me, "open"),
    ("POST", r"^/api/auth/login$", api_login, "csrf"),
    ("POST", r"^/api/auth/logout$", api_logout, "csrf"),
    ("POST", r"^/api/auth/change-password$", api_change_password, "staff"),
    ("GET", r"^/api/quiz/next$", api_next_question, "staff"),
    ("POST", r"^/api/attempts$", api_record_attempt, "staff"),
    ("POST", r"^/api/quiz/finish$", api_finish_quiz_session, "staff"),
    ("GET", r"^/api/questions$", api_list_questions, "staff"),
    ("GET", r"^/api/questions/counts$", api_question_counts, "open"),
    ("GET", r"^/api/topics$", api_topics, "open"),
    ("POST", r"^/api/questions$", api_submit_question, "csrf"),
    ("GET", r"^/api/admin/pending$", api_pending, "admin"),
    ("POST", r"^/api/admin/questions/(?P<id>\d+)/(?P<status>approve|reject)$", api_review, "admin"),
    ("POST", r"^/api/admin/questions/(?P<id>\d+)/delete$", api_delete_question, "admin"),
    ("POST", r"^/api/admin/questions/(?P<id>\d+)/archive$", api_archive_question, "admin"),
    ("POST", r"^/api/admin/questions/(?P<id>\d+)/restore$", api_restore_question, "admin"),
    ("GET", r"^/api/admin/stale$", api_list_stale, "admin"),
    ("POST", r"^/api/admin/questions/(?P<id>\d+)/stale$", api_set_stale, "admin"),
    ("POST", r"^/api/questions/(?P<id>\d+)/report$", api_report_question, "staff"),
    ("GET", r"^/api/admin/reports$", api_list_reports, "admin"),
    ("POST", r"^/api/admin/reports/(?P<id>\d+)/resolve$", api_resolve_report, "admin"),
    ("POST", r"^/api/admin/questions/(?P<id>\d+)/edit$", api_edit_question, "admin"),
    ("POST", r"^/api/admin/import$", import_questions, "admin"),
    ("GET", r"^/api/admin/users$", api_list_users, "admin"),
    ("POST", r"^/api/admin/users$", api_create_user, "admin"),
    ("POST", r"^/api/admin/users/(?P<id>\d+)/active$", api_set_user_active, "admin"),
    ("POST", r"^/api/admin/users/(?P<id>\d+)/username$", api_set_user_username, "admin"),
    ("POST", r"^/api/admin/users/(?P<id>\d+)/password$", api_set_user_password, "admin"),
    ("POST", r"^/api/admin/topics/rename$", api_rename_topic, "admin"),
    ("POST", r"^/api/admin/reset-progress$", api_reset_progress, "admin"),
    ("GET", r"^/api/admin/quiz-sessions$", api_list_quiz_sessions, "admin"),
    ("GET", r"^/api/admin/quiz-sessions/(?P<id>\d+)$", api_get_quiz_session, "admin"),
    ("POST", r"^/api/admin/quiz-sessions/(?P<id>\d+)/delete$", api_delete_quiz_session, "admin"),
    ("GET", r"^/api/stats$", api_stats, "staff"),
]

COMPILED = [(method, re.compile(pattern), fn, access) for method, pattern, fn, access in ROUTES]


class QuizHandler(BaseHTTPRequestHandler):
    server_version = "AirCadetsQuiz/1.0"
    protocol_version = "HTTP/1.1"

    def client_ip(self):
        return self.client_address[0] if self.client_address else "unknown"

    def set_cookie(self, token, expires):
        cookie = SimpleCookie()
        cookie[COOKIE_NAME] = token
        morsel = cookie[COOKIE_NAME]
        morsel["path"] = "/"
        morsel["httponly"] = True
        morsel["samesite"] = "Strict"
        if SECURE_COOKIES:
            morsel["secure"] = True
        self._pending_cookie = morsel.OutputString()

    def clear_cookie(self):
        cookie = SimpleCookie()
        cookie[COOKIE_NAME] = ""
        morsel = cookie[COOKIE_NAME]
        morsel["path"] = "/"
        morsel["httponly"] = True
        morsel["samesite"] = "Strict"
        morsel["max-age"] = 0
        if SECURE_COOKIES:
            morsel["secure"] = True
        self._pending_cookie = morsel.OutputString()

    def read_cookie_token(self):
        raw = self.headers.get("Cookie")
        if not raw:
            return None
        try:
            cookie = SimpleCookie()
            cookie.load(raw)
        except Exception:
            return None
        morsel = cookie.get(COOKIE_NAME)
        return morsel.value if morsel else None

    def send_security_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "same-origin")
        self.send_header("Content-Security-Policy", CONTENT_SECURITY_POLICY)
        self.send_header("Cache-Control", "no-store")

    def send_json(self, status, payload, cookie=None):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_security_headers()
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def send_static(self, path):
        safe = os.path.normpath(unquote(path)).lstrip("/\\")
        full = os.path.normpath(os.path.join(STATIC_DIR, safe))
        if not full.startswith(STATIC_DIR + os.sep) or not os.path.isfile(full):
            return self.send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
        ctype, _ = mimetypes.guess_type(full)
        with open(full, "rb") as handle:
            body = handle.read()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", ctype or "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "same-origin")
        self.send_header("Content-Security-Policy", CONTENT_SECURITY_POLICY)
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def read_body(self):
        length = self.headers.get("Content-Length")
        if not length:
            return {}
        try:
            size = int(length)
        except ValueError:
            raise bad_request("invalid content length")
        if size <= 0:
            return {}
        if size > MAX_BODY_BYTES:
            raise ApiError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "request body is too large")
        raw = self.rfile.read(size)
        if not raw.strip():
            return {}
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise bad_request("request body must be valid json")

    def handle_api(self, method, path, query, conn):
        cookie = None
        for route_method, pattern, fn, access in COMPILED:
            match = pattern.match(path)
            if not match or route_method != method:
                continue

            token = self.read_cookie_token()
            session = db.get_session(conn, token) if token else None
            user = None
            if session and session["user_id"]:
                user = db.get_user_by_id(conn, session["user_id"])
                if not user or not user["active"]:
                    session = None
                    user = None

            if access in ("staff", "admin") and not user:
                raise ApiError(HTTPStatus.UNAUTHORIZED, "please log in")
            if access == "admin" and user["role"] != db.USER_ADMIN:
                raise ApiError(HTTPStatus.FORBIDDEN, "admin only")
            if method != "GET":
                if not session:
                    raise ApiError(HTTPStatus.FORBIDDEN, "session expired, reload the page")
                supplied = self.headers.get("X-CSRF-Token", "")
                if not secrets.compare_digest(supplied, session["csrf"]):
                    raise ApiError(HTTPStatus.FORBIDDEN, "invalid csrf token, reload the page")

            body = self.read_body() if method != "GET" else {}
            ctx = Ctx(self, conn, session, user, query, body, match)
            payload = fn(ctx)
            cookie = getattr(self, "_pending_cookie", None)
            self._pending_cookie = None
            return self.send_json(HTTPStatus.OK, payload, cookie)

        allowed = any(pattern.match(path) and route_method != method for route_method, pattern, _, _ in COMPILED)
        if allowed:
            return self.send_json(HTTPStatus.METHOD_NOT_ALLOWED, {"error": "method not allowed"})
        return self.send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})

    def dispatch(self, method):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)
        try:
            if path == "/" or path == "/index.html":
                return self.send_static("index.html")
            if path.startswith("/static/"):
                return self.send_static(path[len("/static/"):])
            if path == "/healthz":
                return self.send_json(HTTPStatus.OK, {"ok": True})
            if path.startswith("/api/"):
                with db.connection() as conn:
                    return self.handle_api(method, path, query, conn)
            return self.send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
        except ApiError as exc:
            self._pending_cookie = None
            body = {"error": exc.message}
            if exc.reason:
                body["reason"] = exc.reason
            return self.send_json(exc.status, body)
        except BrokenPipeError:
            return
        except Exception as exc:  # noqa: BLE001
            sys.stderr.write(f"error handling {method} {self.path}: {exc!r}\n")
            return self.send_json(
                HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "internal server error"}
            )

    def do_GET(self):
        self._pending_cookie = None
        self.dispatch("GET")

    def do_POST(self):
        self._pending_cookie = None
        self.dispatch("POST")

    def do_HEAD(self):
        self._pending_cookie = None
        self.dispatch("GET")

    def log_message(self, fmt, *args):
        if LOG_REQUESTS:
            sys.stderr.write(f"{self.address_string()} {fmt % args}\n")

    def log_error(self, fmt, *args):
        sys.stderr.write("error: " + (fmt % args) + "\n")


def bootstrap_admin():
    if db.user_count():
        return
    with db.connection() as conn:
        username = os.environ.get("ADMIN_USERNAME", "admin").strip() or "admin"
        generated = None
        password = os.environ.get("ADMIN_PASSWORD")
        must_change = 0
        if not password:
            generated = secrets.token_urlsafe(9)
            password = generated
            must_change = 1
        try:
            auth.validate_username(username)
            auth.validate_password(password)
        except ValueError as exc:
            sys.stderr.write("cannot create admin account: %s\n" % exc)
            return
        digest, salt = auth.hash_password(password)
        db.create_user(
            conn,
            username=username,
            password=password,
            salt=salt,
            password_hash=digest,
            role=db.USER_ADMIN,
            display_name="Administrator",
            must_change=must_change,
        )
        sys.stderr.write("=" * 62 + "\n")
        sys.stderr.write("Created the admin account '%s'.\n" % username)
        if generated:
            sys.stderr.write("  password: %s\n" % generated)
            sys.stderr.write("  Save this now - it is not stored in plain text and\n")
            sys.stderr.write("  you will be asked to change it after logging in.\n")
        else:
            sys.stderr.write("  password taken from ADMIN_PASSWORD.\n")
        sys.stderr.write("=" * 62 + "\n")


def main():
    db.init()
    bootstrap_admin()
    server = ThreadingHTTPServer((HOST, PORT), QuizHandler)
    sys.stderr.write(f"Air Cadets quiz running on http://{HOST}:{PORT}\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        sys.stderr.write("\nshutting down\n")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
