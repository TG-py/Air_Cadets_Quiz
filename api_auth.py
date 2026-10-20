"""auth API handlers."""
from http import HTTPStatus

import auth
import db
import quiz
from api_common import ApiError, bad_request, require_fields

def issue_guest_session(ctx):
    token, csrf, _ = auth.start_session(ctx.conn, None)
    ctx.handler.set_cookie(token)
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
    token, csrf, _ = auth.start_session(ctx.conn, user["id"])
    ctx.handler.set_cookie(token)
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


