"""practice API handlers."""
from datetime import datetime, timedelta, timezone
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
    """Next practice question: the same squadron-weighted pool as the quiz,
    minus the ones already faced in this run. Open to everyone."""
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

def api_practice_stats(ctx):
    """Overall practice totals grouped by topic and question, kept apart from
    the squadron scoreboard."""
    questions = db.practice_question_stats(ctx.conn)
    for question in questions:
        question["accuracy"] = (
            round(question["correct"] / question["asked"] * 100, 1)
            if question["asked"]
            else None
        )
    questions.sort(key=lambda q: (q["topic"].casefold(), q["question_text"].casefold()))

    by_topic = {}
    for question in questions:
        by_topic.setdefault(question["topic"], []).append(question)

    topics = []
    for name, items in by_topic.items():
        asked = sum(item["asked"] for item in items)
        correct = sum(item["correct"] for item in items)
        topics.append(
            {
                "topic": name,
                "question_count": len(items),
                "asked": asked,
                "correct": correct,
                "incorrect": asked - correct,
                "skipped": sum(item["skipped"] for item in items),
                "accuracy": round(correct / asked * 100, 1) if asked else None,
            }
        )
    topics.sort(key=lambda t: (t["accuracy"] is None, t["accuracy"] if t["accuracy"] is not None else 0))

    return {
        "overall": db.practice_overall_stats(ctx.conn),
        "topics": topics,
        "questions": questions,
    }


def api_practice_trends(ctx):
    """Return the last 12 complete/current weeks of solo practice answers."""
    db.ensure_practice_schema(ctx.conn)
    today = datetime.now(timezone.utc).date()
    this_monday = today - timedelta(days=today.weekday())
    first_monday = this_monday - timedelta(weeks=11)
    rows = ctx.conn.execute(
        "SELECT date(created_at, '-' || ((CAST(strftime('%w', created_at) AS INTEGER) + 6) % 7) || ' days') AS week_start, "
        "SUM(CASE WHEN skipped = 0 AND correct = 1 THEN 1 ELSE 0 END) AS correct, "
        "SUM(CASE WHEN skipped = 0 AND correct = 0 THEN 1 ELSE 0 END) AS incorrect, "
        "SUM(CASE WHEN skipped = 1 THEN 1 ELSE 0 END) AS skipped "
        "FROM practice_attempts WHERE created_at >= ? GROUP BY week_start ORDER BY week_start",
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

