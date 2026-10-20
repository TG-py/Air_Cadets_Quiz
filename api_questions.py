"""questions API handlers."""
import csv
import io
from http import HTTPStatus

import db
from api_common import ApiError, bad_request

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
        "board_state": row["board_state"],
        "archived_at": row["archived_at"],
        "created_at": row["created_at"],
        "outdated": bool(row["outdated"]),
        "needs_review": bool(row["needs_review"]),
        "ai_pending": bool(row["ai_pending"]),
        "ai_question_text": row["ai_question_text"],
        "ai_answer_text": row["ai_answer_text"],
        "ai_topic": row["ai_topic"],
        "ai_reason": row["ai_reason"],
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
    try:
        requested_limit = int(ctx.q("limit") or 500)
    except ValueError:
        raise bad_request("limit must be a number")
    if requested_limit < 1 or requested_limit > 5000:
        raise bad_request("limit must be between 1 and 5000")
    rows = db.list_questions(
        ctx.conn,
        status=status,
        topic=(ctx.q("topic") or "").strip() or None,
        search=(ctx.q("q") or "").strip() or None,
        limit=requested_limit,
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


def question_board_state(question):
    return question["board_state"]


def api_question_board(ctx):
    search = (ctx.q("q") or "").strip() or None
    topic = (ctx.q("topic") or "").strip() or None
    questions = db.list_questions(
        ctx.conn, search=search, topic=topic, limit=2147483647, include_archived=True
    )
    report_rows = db.list_reports(ctx.conn, "all", 2147483647)
    reports_by_question = {}
    for row in report_rows:
        report = db.report_json(row)
        reports_by_question.setdefault(report["question_id"], []).append(report)
    items = []
    for row in questions:
        question = question_json(row)
        question["reports"] = reports_by_question.get(row["id"], [])
        question["board_state"] = question_board_state(row)
        question["report_count"] = sum(1 for report in question["reports"] if report["status"] == "pending")
        items.append(question)
    return {
        "questions": items,
        "counts": db.question_counts(ctx.conn),
        "topics": db.list_topics(ctx.conn, statuses=(db.Q_APPROVED, db.Q_PENDING, db.Q_REJECTED)),
        "stale_count": db.stale_count(ctx.conn),
        "needs_review_count": db.needs_review_count(ctx.conn),
        "ai_pending_count": db.ai_pending_count(ctx.conn),
        "report_count": db.pending_report_count(ctx.conn),
    }


def api_set_question_board_state(ctx):
    question_id = int(ctx.match.group("id"))
    target = ctx.body.get("state")
    if target not in ("active", "time-sensitive", "reported", "approval", "archive"):
        raise bad_request("unknown question board state")
    question = db.get_question(ctx.conn, question_id)
    if not question:
        raise ApiError(HTTPStatus.NOT_FOUND, "question not found")
    if target == "reported":
        raise bad_request("questions enter Reported when a user submits a report")
    if target == "archive" and not question["archived_at"] and question["status"] != db.Q_APPROVED:
        raise ApiError(HTTPStatus.CONFLICT, "only accepted questions can be archived")

    # Leaving Reported is an explicit admin decision that closes all open reports.
    pending_reports = ctx.conn.execute(
        "SELECT id FROM reports WHERE question_id = ? AND status = 'pending'", (question_id,)
    ).fetchall()
    for report in pending_reports:
        db.resolve_report(ctx.conn, report["id"], "resolved", ctx.user["id"])

    question = db.get_question(ctx.conn, question_id)
    if target == "archive":
        if not question["archived_at"] and not db.archive_question(ctx.conn, question_id):
            raise ApiError(HTTPStatus.CONFLICT, "only accepted questions can be archived")
    elif target in ("active", "time-sensitive"):
        if question["archived_at"]:
            if not db.restore_question(ctx.conn, question_id):
                raise ApiError(HTTPStatus.CONFLICT, "question could not be restored")
            question = db.get_question(ctx.conn, question_id)
        if question["ai_pending"]:
            ctx.conn.execute(
                "UPDATE questions SET question_text=COALESCE(NULLIF(ai_question_text,''),question_text), "
                "answer_text=COALESCE(NULLIF(ai_answer_text,''),answer_text), "
                "topic=COALESCE(NULLIF(ai_topic,''),topic), status=?, outdated=?, needs_review=0, ai_pending=0, "
                "ai_question_text='', ai_answer_text='', ai_topic='', ai_reason='', reviewed_by=?, reviewed_at=?, "
                "review_note=? WHERE id=?",
                (db.Q_APPROVED, int(target == "time-sensitive"), ctx.user["id"], db.now(),
                 "Approved from the question board.", question_id),
            )
        else:
            if question["status"] != db.Q_APPROVED:
                db.review_question(ctx.conn, question_id, db.Q_APPROVED, ctx.user["id"], "Approved from the question board.")
            ctx.conn.execute(
                "UPDATE questions SET outdated=?, needs_review=0, ai_pending=0, ai_question_text='', "
                "ai_answer_text='', ai_topic='', ai_reason='' WHERE id=?",
                (int(target == "time-sensitive"), question_id),
            )
    elif target == "approval":
        if question["status"] == db.Q_APPROVED and not question["ai_pending"]:
            ctx.conn.execute("UPDATE questions SET needs_review=1 WHERE id=?", (question_id,))

    ctx.conn.execute("UPDATE questions SET board_state=? WHERE id=?", (target, question_id))

    question = db.get_question(ctx.conn, question_id)
    return {
        "ok": True,
        "state": question_board_state(question),
        "counts": db.question_counts(ctx.conn),
        "stale_count": db.stale_count(ctx.conn),
        "needs_review_count": db.needs_review_count(ctx.conn),
        "ai_pending_count": db.ai_pending_count(ctx.conn),
        "report_count": db.pending_report_count(ctx.conn),
    }


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
    review_rows = db.list_needs_review(ctx.conn)
    ai_rows = db.list_ai_pending(ctx.conn)
    return {
        "questions": [question_json(r) for r in rows],
        "review_questions": [question_json(r) for r in review_rows],
        "ai_questions": [question_json(r) for r in ai_rows],
        "counts": db.question_counts(ctx.conn),
        "stale_count": db.stale_count(ctx.conn),
        "needs_review_count": db.needs_review_count(ctx.conn),
        "ai_pending_count": db.ai_pending_count(ctx.conn),
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


def api_set_needs_review(ctx):
    question_id = int(ctx.match.group("id"))
    question = db.get_question(ctx.conn, question_id)
    if not question or question["archived_at"]:
        raise ApiError(HTTPStatus.NOT_FOUND, "question not found")
    tagged = bool(ctx.body.get("tagged"))
    db.set_question_needs_review(ctx.conn, question_id, tagged)
    if not tagged:
        ctx.conn.execute("UPDATE questions SET ai_question_text='', ai_answer_text='', ai_topic='', ai_reason='' WHERE id=?", (question_id,))
    return {"ok": True, "counts": db.question_counts(ctx.conn), "stale_count": db.stale_count(ctx.conn),
            "needs_review_count": db.needs_review_count(ctx.conn), "report_count": db.pending_report_count(ctx.conn)}


def api_accept_ai_question(ctx):
    question_id = int(ctx.match.group("id"))
    row = db.get_question(ctx.conn, question_id)
    if not row or not row["ai_pending"]:
        raise ApiError(HTTPStatus.NOT_FOUND, "AI suggestion not found")
    outdated = bool(ctx.body.get("outdated"))
    ctx.conn.execute(
        "UPDATE questions SET question_text=ai_question_text, answer_text=ai_answer_text, topic=ai_topic, "
        "outdated=?, needs_review=0, ai_pending=0, ai_question_text='', ai_answer_text='', ai_topic='', ai_reason='' "
        "WHERE id=?", (1 if outdated else 0, question_id)
    )
    db.sync_question_board_state(ctx.conn, question_id)
    return {"ok": True, "counts": db.question_counts(ctx.conn), "stale_count": db.stale_count(ctx.conn),
            "needs_review_count": db.needs_review_count(ctx.conn), "ai_pending_count": db.ai_pending_count(ctx.conn),
            "report_count": db.pending_report_count(ctx.conn)}


def api_reject_ai_question(ctx):
    question_id = int(ctx.match.group("id"))
    row = db.get_question(ctx.conn, question_id)
    if not row or not row["ai_pending"]:
        raise ApiError(HTTPStatus.NOT_FOUND, "AI suggestion not found")
    ctx.conn.execute(
        "UPDATE questions SET ai_pending=0, ai_question_text='', ai_answer_text='', ai_topic='', ai_reason='' WHERE id=?",
        (question_id,),
    )
    db.sync_question_board_state(ctx.conn, question_id)
    return {"ok": True, "counts": db.question_counts(ctx.conn), "stale_count": db.stale_count(ctx.conn),
            "needs_review_count": db.needs_review_count(ctx.conn), "ai_pending_count": db.ai_pending_count(ctx.conn),
            "report_count": db.pending_report_count(ctx.conn)}


def api_send_ai_to_human(ctx):
    question_id = int(ctx.match.group("id"))
    row = db.get_question(ctx.conn, question_id)
    if not row or not row["ai_pending"]:
        raise ApiError(HTTPStatus.NOT_FOUND, "AI suggestion not found")
    ctx.conn.execute("UPDATE questions SET ai_pending=0, needs_review=1, outdated=0 WHERE id=?", (question_id,))
    db.sync_question_board_state(ctx.conn, question_id)
    return {"ok": True, "counts": db.question_counts(ctx.conn), "stale_count": db.stale_count(ctx.conn),
            "needs_review_count": db.needs_review_count(ctx.conn), "ai_pending_count": db.ai_pending_count(ctx.conn),
            "report_count": db.pending_report_count(ctx.conn)}


def api_apply_question_updates(ctx):
    rows = read_review_csv(ctx.body.get("content"), ["id", "question", "answer", "topic"])
    staged = 0
    seen = set()
    for row in rows:
        try:
            question_id = int((row.get("id") or "").strip())
        except ValueError:
            raise bad_request("each row needs a numeric question id")
        if question_id in seen:
            raise bad_request("each question id can appear only once")
        seen.add(question_id)
        existing = db.get_question(ctx.conn, question_id)
        if not existing or existing["status"] != db.Q_APPROVED or existing["archived_at"]:
            raise bad_request("question %s is missing, archived or not accepted" % question_id)
        question = (row.get("question") or "").strip() or existing["question_text"]
        answer = (row.get("answer") or "").strip() or existing["answer_text"]
        topic = (row.get("topic") or "").strip() or existing["topic"]
        if max(len(question), len(answer)) > 2000 or len(topic) > 80:
            raise bad_request("question and answer must be 2000 characters or less; topic 80 or less")
        ctx.conn.execute("UPDATE questions SET ai_pending=1, ai_question_text=?, ai_answer_text=?, ai_topic=?, "
                         "ai_reason='AI suggested an update; admin approval required.', outdated=0, needs_review=0 WHERE id=?",
                         (question, answer, topic, question_id))
        db.sync_question_board_state(ctx.conn, question_id)
        staged += 1
    return {"ok": True, "updated": staged, "staged": staged, "ai_pending_count": db.ai_pending_count(ctx.conn),
            "counts": db.question_counts(ctx.conn), "stale_count": db.stale_count(ctx.conn),
            "report_count": db.pending_report_count(ctx.conn)}


def api_mark_scan_results(ctx):
    ids = ctx.body.get("ids")
    if not isinstance(ids, list) or not ids or len(ids) > 500:
        raise bad_request("provide between 1 and 500 question ids")
    normalized = []
    for value in ids:
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise bad_request("question ids must be positive whole numbers")
        if value not in normalized:
            normalized.append(value)
    for question_id in normalized:
        row = db.get_question(ctx.conn, question_id)
        if not row or row["status"] != db.Q_APPROVED or row["archived_at"]:
            raise bad_request("question %s is missing, archived or not accepted" % question_id)
    for question_id in normalized:
        db.set_question_outdated(ctx.conn, question_id, True)
    return {"ok": True, "marked": len(normalized), "counts": db.question_counts(ctx.conn),
            "stale_count": db.stale_count(ctx.conn), "report_count": db.pending_report_count(ctx.conn)}


def read_review_csv(content, required):
    if not isinstance(content, str) or not content.strip():
        raise bad_request("paste the CSV results first")
    try:
        # AI tools commonly wrap CSV in a code fence, include a UTF-8 BOM,
        # or rename the prompt's fields slightly. Normalize those harmless
        # variations before validating the schema.
        lines = [line.strip() for line in content.lstrip("\ufeff").splitlines()]
        lines = [line for line in lines if line and not line.startswith("```")]
        normalized = []
        for line in lines:
            cell = line.strip().strip('"').lower().replace(" ", "_").replace("-", "_")
            normalized.append(cell)
        aliases = {
            "question_id": "id", "questionid": "id", "id_question": "id",
            "question_text": "question", "updated_question": "question",
            "answer_text": "answer", "updated_answer": "answer",
            "topic_name": "topic", "change": "action", "status": "action",
            "decision": "action", "reportid": "report_id",
            "report_reason": "reason", "explanation": "reason",
        }
        # Find the actual header if the model added a short preface.
        header_index = next((i for i, line in enumerate(normalized)
                             if "question" in line and "answer" in line
                             and ("id" in line or "question_id" in line)), None)
        if header_index is None:
            raise ValueError("Could not find the CSV header. Paste the CSV starting with id,action,question,answer,topic,reason.")
        data = "\n".join(lines[header_index:])
        try:
            dialect = csv.Sniffer().sniff(data[:4096], delimiters=",;\t|")
        except csv.Error:
            dialect = csv.excel
        reader = csv.DictReader(io.StringIO(data), dialect=dialect)
        headers = [aliases.get(str(h or "").strip().lstrip("\ufeff").lower().replace(" ", "_").replace("-", "_"),
                               str(h or "").strip().lstrip("\ufeff").lower().replace(" ", "_").replace("-", "_"))
                   for h in (reader.fieldnames or [])]
        if "report_id" in headers and "id" in headers and "question_id" not in headers:
            headers[headers.index("id")] = "question_id"
        reader.fieldnames = headers
        # A plain id,question,answer,topic CSV is the legacy update format.
        missing = set(required) - set(headers)
        if missing == {"action"} and {"id", "question", "answer", "topic"}.issubset(headers):
            headers.append("action")
            reader.fieldnames = headers
            rows = []
            for row in reader:
                row["action"] = "update"
                rows.append(row)
        elif missing:
            raise ValueError("CSV needs these columns: " + ",".join(required))
        else:
            rows = list(reader)
    except (csv.Error, ValueError) as exc:
        raise bad_request(str(exc))
    if not rows or len(rows) > 5000:
        raise bad_request("include between 1 and 5000 result rows")
    return rows


def api_apply_scan_review(ctx):
    rows = read_review_csv(ctx.body.get("content"), ["id", "action", "question", "answer", "topic"])
    prepared = []
    seen = set()
    for row in rows:
        try:
            question_id = int((row.get("id") or "").strip())
        except ValueError:
            raise bad_request("each row needs a numeric question id")
        action = (row.get("action") or "").strip().lower()
        if action not in ("update", "flag", "review", "ok"):
            raise bad_request("action must be update, flag, review or ok")
        if question_id in seen:
            raise bad_request("each question id can appear only once")
        seen.add(question_id)
        existing = db.get_question(ctx.conn, question_id)
        if not existing or existing["status"] != db.Q_APPROVED or existing["archived_at"]:
            raise bad_request("question %s is missing, archived or not accepted" % question_id)
        question = (row.get("question") or "").strip() or existing["question_text"]
        answer = (row.get("answer") or "").strip() or existing["answer_text"]
        topic = (row.get("topic") or "").strip() or existing["topic"]
        if max(len(question), len(answer)) > 2000 or len(topic) > 80:
            raise bad_request("question and answer must be 2000 characters or less; topic 80 or less")
        prepared.append((question_id, action, question, answer, topic))
    staged = marked = 0
    for question_id, action, question, answer, topic in prepared:
        if action == "update":
            ctx.conn.execute(
                "UPDATE questions SET ai_pending=1, ai_question_text=?, ai_answer_text=?, ai_topic=?, "
                "ai_reason=?, outdated=0, needs_review=0 WHERE id=?",
                (question, answer, topic, "AI suggested an update; admin approval required.", question_id),
            )
            staged += 1
        elif action == "flag":
            ctx.conn.execute("UPDATE questions SET outdated=1, needs_review=0, ai_pending=0, "
                             "ai_question_text='', ai_answer_text='', ai_topic='', ai_reason='' WHERE id=?", (question_id,))
            marked += 1
        elif action == "review":
            ctx.conn.execute("UPDATE questions SET needs_review=1, outdated=0, ai_pending=0 WHERE id=?", (question_id,))
        elif action == "ok":
            ctx.conn.execute("UPDATE questions SET outdated=0, needs_review=0, ai_pending=0, "
                             "ai_question_text='', ai_answer_text='', ai_topic='', ai_reason='' WHERE id=?", (question_id,))
    return {"ok": True, "updated": staged, "staged": staged, "marked": marked,
            "needs_review_count": db.needs_review_count(ctx.conn), "ai_pending_count": db.ai_pending_count(ctx.conn),
            "counts": db.question_counts(ctx.conn), "stale_count": db.stale_count(ctx.conn),
            "report_count": db.pending_report_count(ctx.conn)}


def api_apply_report_review(ctx):
    rows = read_review_csv(ctx.body.get("content"), ["report_id", "question_id", "action", "question", "answer", "topic"])
    prepared = []
    seen = set()
    for row in rows:
        try:
            report_id = int((row.get("report_id") or "").strip())
            question_id = int((row.get("question_id") or "").strip())
        except ValueError:
            raise bad_request("each row needs numeric report_id and question_id values")
        action = (row.get("action") or "").strip().lower()
        if action not in ("update", "review", "dismiss"):
            raise bad_request("report action must be update, review or dismiss")
        if report_id in seen:
            raise bad_request("each report id can appear only once")
        seen.add(report_id)
        report = db.get_report(ctx.conn, report_id)
        if not report or report["status"] != "pending" or report["question_id"] != question_id:
            raise bad_request("report %s is missing, handled, or does not match that question" % report_id)
        existing = db.get_question(ctx.conn, question_id)
        if action in ("update", "review") and (not existing or existing["archived_at"] or existing["status"] != db.Q_APPROVED):
            raise bad_request("question %s cannot be updated" % question_id)
        question = (row.get("question") or "").strip() or (existing["question_text"] if existing else "")
        answer = (row.get("answer") or "").strip() or (existing["answer_text"] if existing else "")
        topic = (row.get("topic") or "").strip() or (existing["topic"] if existing else "")
        if max(len(question), len(answer)) > 2000 or len(topic) > 80:
            raise bad_request("question and answer must be 2000 characters or less; topic 80 or less")
        prepared.append((report_id, question_id, action, question, answer, topic))
    updated = 0
    for report_id, question_id, action, question, answer, topic in prepared:
        if action == "update":
            ctx.conn.execute(
                "UPDATE questions SET ai_pending=1, ai_question_text=?, ai_answer_text=?, ai_topic=?, ai_reason=?, "
                "outdated=0, needs_review=0 WHERE id=?",
                (question, answer, topic, "AI suggestion from a reported question; admin approval required.", question_id),
            )
            updated += 1
        elif action == "review":
            ctx.conn.execute("UPDATE questions SET needs_review=1, outdated=0, ai_pending=0 WHERE id=?", (question_id,))
        db.resolve_report(ctx.conn, report_id, "dismissed" if action == "dismiss" else "resolved", ctx.user["id"])
    return {"ok": True, "updated": updated, "ai_pending_count": db.ai_pending_count(ctx.conn),
            "needs_review_count": db.needs_review_count(ctx.conn),
            "counts": db.question_counts(ctx.conn), "stale_count": db.stale_count(ctx.conn),
            "report_count": db.pending_report_count(ctx.conn)}


def api_apply_combined_review(ctx):
    rows = read_review_csv(ctx.body.get("content"), ["id", "report_ids", "action", "question", "answer", "topic"])
    prepared = []
    seen = set()
    for row in rows:
        try:
            question_id = int((row.get("id") or "").strip())
        except ValueError:
            raise bad_request("each row needs a numeric question id")
        if question_id in seen:
            raise bad_request("each question id can appear only once")
        seen.add(question_id)
        report_ids = []
        raw_ids = (row.get("report_ids") or "").strip()
        if raw_ids:
            try:
                report_ids = [int(value.strip()) for value in raw_ids.replace(",", ";").split(";") if value.strip()]
            except ValueError:
                raise bad_request("report_ids must be blank or a semicolon-separated list of report ids")
            if len(report_ids) != len(set(report_ids)):
                raise bad_request("report_ids cannot contain duplicates")
        action = (row.get("action") or "").strip().lower()
        if action not in ("update", "flag", "review", "ok", "dismiss"):
            raise bad_request("action must be update, flag, review, ok or dismiss")
        if action == "dismiss" and not report_ids:
            raise bad_request("dismiss can only be used for a question with report ids")
        existing = db.get_question(ctx.conn, question_id)
        if not existing:
            raise bad_request("question %s no longer exists" % question_id)
        if report_ids:
            for report_id in report_ids:
                report = db.get_report(ctx.conn, report_id)
                if not report or report["status"] != "pending" or report["question_id"] != question_id:
                    raise bad_request("report %s is missing, already handled, or belongs to another question" % report_id)
        if action != "dismiss" and (existing["archived_at"] or existing["status"] != db.Q_APPROVED):
            raise bad_request("question %s is archived or not accepted; only its report can be dismissed" % question_id)
        question = (row.get("question") or "").strip() or existing["question_text"]
        answer = (row.get("answer") or "").strip() or existing["answer_text"]
        topic = (row.get("topic") or "").strip() or existing["topic"]
        if max(len(question), len(answer)) > 2000 or len(topic) > 80:
            raise bad_request("question and answer must be 2000 characters or less; topic 80 or less")
        prepared.append((question_id, report_ids, action, question, answer, topic, existing))

    staged = marked = sent_to_human = 0
    with db.transaction(ctx.conn):
        for question_id, report_ids, action, question, answer, topic, existing in prepared:
            if action == "update":
                ctx.conn.execute(
                    "UPDATE questions SET ai_pending=1, ai_question_text=?, ai_answer_text=?, ai_topic=?, ai_reason=?, "
                    "needs_review=0 WHERE id=?",
                    (question, answer, topic, "AI suggested an update; admin approval required.", question_id),
                )
                staged += 1
            elif action == "flag":
                ctx.conn.execute("UPDATE questions SET outdated=1, needs_review=0, ai_pending=0, "
                                 "ai_question_text='', ai_answer_text='', ai_topic='', ai_reason='' WHERE id=?", (question_id,))
                marked += 1
            elif action == "review":
                ctx.conn.execute("UPDATE questions SET needs_review=1, outdated=0, ai_pending=0, "
                                 "ai_question_text='', ai_answer_text='', ai_topic='', ai_reason='' WHERE id=?", (question_id,))
                sent_to_human += 1
            elif action == "ok":
                ctx.conn.execute("UPDATE questions SET outdated=0, needs_review=0, ai_pending=0, "
                                 "ai_question_text='', ai_answer_text='', ai_topic='', ai_reason='' WHERE id=?", (question_id,))
            for report_id in report_ids:
                db.resolve_report(ctx.conn, report_id, "dismissed" if action == "dismiss" else "resolved", ctx.user["id"])
            db.sync_question_board_state(ctx.conn, question_id)
    return {"ok": True, "staged": staged, "marked": marked, "sent_to_human": sent_to_human,
            "needs_review_count": db.needs_review_count(ctx.conn), "ai_pending_count": db.ai_pending_count(ctx.conn),
            "counts": db.question_counts(ctx.conn), "stale_count": db.stale_count(ctx.conn),
            "report_count": db.pending_report_count(ctx.conn)}


def api_report_question(ctx):
    # anyone on the quiz can flag a wrong question - signed-in staff under
    # their account name, everyone else under the name they give. The report
    # lands with the admin either way.
    question_id = int(ctx.match.group("id"))
    question = db.get_question(ctx.conn, question_id)
    if not question or question["status"] != db.Q_APPROVED or question["archived_at"]:
        raise bad_request("unknown question")
    reason = (ctx.body.get("reason") or "").strip() if isinstance(ctx.body.get("reason"), str) else ""
    if len(reason) > 1000:
        raise bad_request("report is too long (max 1000 characters)")
    if ctx.user:
        if db.has_pending_report(ctx.conn, question_id, ctx.user["id"]):
            raise ApiError(HTTPStatus.CONFLICT, "you have already reported this question")
        user_id = ctx.user["id"]
        name = ctx.user["display_name"] or ctx.user["username"]
    else:
        raw = ctx.body.get("reporter_name")
        name = raw.strip() if isinstance(raw, str) else ""
        if len(name) < 2:
            raise bad_request("please give your name so the admin knows who reported it")
        if len(name) > 80:
            raise bad_request("name is too long (max 80 characters)")
        if db.has_pending_report_by_name(ctx.conn, question_id, name):
            raise ApiError(HTTPStatus.CONFLICT, "you have already reported this question")
        user_id = None
    db.add_report(ctx.conn, question_id, user_id, name, reason)
    return {"ok": True, "message": "reported - an admin will check it"}


