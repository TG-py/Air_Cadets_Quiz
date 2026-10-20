"""practice API handlers."""
from http import HTTPStatus

import db
import quiz
from api_common import ApiError, bad_request

def api_practice_start(ctx):
    """Begin a solo practice run under a name. Open to everyone, including
    guests - the run is recorded apart from the squadron results."""
    raw = ctx.body.get("name")
    name = raw.strip() if isinstance(raw, str) else ""
    if len(name) < 2:
        raise bad_request("please enter your name before practising")
    if len(name) > 80:
        raise bad_request("name is too long (max 80 characters)")
    topic = ctx.body.get("topic")
    topic = topic.strip() if isinstance(topic, str) else ""
    if topic and topic not in db.list_topics(ctx.conn):
        raise bad_request("unknown topic")
    session_id = db.create_practice_session(ctx.conn, name, topic)
    return {"ok": True, "practice_session_id": session_id, "name": name, "topic": topic}


def api_practice_next(ctx):
    """Next practice question: same active bank as the squadron quiz, minus
    the ones already faced in this run. Open to everyone."""
    try:
        session_id = int((ctx.q("practice_session_id") or "").strip())
    except (TypeError, ValueError):
        raise bad_request("practice_session_id must be a number")
    run = db.get_practice_session(ctx.conn, session_id)
    if not run or run["ended_at"]:
        raise bad_request("unknown practice session")
    topic = run["topic"] or None
    pool = quiz.build_pool(ctx.conn, topic)
    answered = db.practice_answered_ids(ctx.conn, session_id)
    question = quiz.pick(pool, answered)
    if not question:
        counts = db.question_counts(ctx.conn)
        if counts["approved"] == 0:
            raise ApiError(HTTPStatus.CONFLICT, "no approved questions yet", "empty")
        if not pool:
            raise ApiError(
                HTTPStatus.CONFLICT, "no approved questions match that topic", "topic"
            )
        raise ApiError(
            HTTPStatus.CONFLICT,
            "you have practised every question - finish to see your score",
            "exhausted",
        )
    return {"question": question}


def api_practice_attempt(ctx):
    """Record one practice answer. Squadron totals are never touched."""
    try:
        session_id = int(ctx.body.get("practice_session_id") or 0)
    except (TypeError, ValueError):
        raise bad_request("practice_session_id must be a number")
    try:
        question_id = int((ctx.body.get("question_id") or ""))
    except (TypeError, ValueError):
        raise bad_request("question_id must be a number")
    run = db.get_practice_session(ctx.conn, session_id)
    if not run or run["ended_at"]:
        raise bad_request("unknown practice session")
    question = db.get_question(ctx.conn, question_id)
    if not question or question["status"] != db.Q_APPROVED or question["archived_at"]:
        raise bad_request("unknown question")
    skipped = 1 if ctx.body.get("skipped") else 0
    correct = 1 if ctx.body.get("correct") else 0
    db.record_practice_attempt(
        ctx.conn,
        session_id,
        question_id,
        correct,
        skipped,
        question_text=question["question_text"],
        answer_text=question["answer_text"],
        topic=question["topic"],
    )
    return {"ok": True, "session": db.practice_session_counts(ctx.conn, session_id)}


def api_practice_finish(ctx):
    """Close a practice run and return its score."""
    try:
        session_id = int(ctx.body.get("practice_session_id") or 0)
    except (TypeError, ValueError):
        raise bad_request("practice_session_id must be a number")
    run = db.get_practice_session(ctx.conn, session_id)
    if not run:
        raise bad_request("unknown practice session")
    outcome = db.finish_practice_session(ctx.conn, session_id)
    counts = db.practice_session_counts(ctx.conn, session_id) if outcome == "finished" else None
    return {
        "ok": True,
        "finished": outcome == "finished",
        "practice_session_id": session_id,
        "session": counts,
    }


def api_list_practice_sessions(ctx):
    return {"sessions": db.list_practice_sessions(ctx.conn, completed_only=True)}


def api_get_practice_session(ctx):
    session_id = int(ctx.match.group("id"))
    row = db.get_practice_session(ctx.conn, session_id)
    if not row or not row["ended_at"]:
        raise ApiError(HTTPStatus.NOT_FOUND, "session not found")
    return {
        "session": db.practice_session_json(ctx.conn, row),
        "attempts": db.list_practice_attempts(ctx.conn, session_id),
    }


def api_delete_practice_session(ctx):
    if not ctx.body.get("confirm"):
        raise bad_request("confirmation required before deleting this session")
    session_id = int(ctx.match.group("id"))
    row = db.get_practice_session(ctx.conn, session_id)
    if not row:
        raise ApiError(HTTPStatus.NOT_FOUND, "session not found")
    db.delete_practice_session(ctx.conn, session_id)
    return {"ok": True, "message": "that practice session has been deleted"}


