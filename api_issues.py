"""Website issue reporting API handlers."""
from http import HTTPStatus

import db
from api_common import ApiError, bad_request, require_fields


def api_submit_website_issue(ctx):
    fields = require_fields(ctx.body, "title", "details")
    title = fields["title"]
    details = fields["details"]
    reporter_name = ctx.body.get("reporter_name", "")
    page = ctx.body.get("page", "")
    if len(title) > 120:
        raise bad_request("title must be 120 characters or fewer")
    if len(details) > 3000:
        raise bad_request("details must be 3000 characters or fewer")
    if not isinstance(reporter_name, str) or len(reporter_name.strip()) > 80:
        raise bad_request("name must be 80 characters or fewer")
    reporter_name = reporter_name.strip()
    if not reporter_name and ctx.user:
        reporter_name = ctx.user.get("display_name") or ctx.user.get("username") or ""
    if not isinstance(page, str):
        page = ""
    issue_id = db.add_website_issue(
        ctx.conn,
        ctx.user["id"] if ctx.user else None,
        reporter_name, title, details, page[:120],
    )
    return {"ok": True, "id": issue_id, "message": "Thanks. Your website issue was sent to the admin team."}


def api_list_website_issues(ctx):
    status = (ctx.q("status") or "pending").strip().lower()
    if status not in ("pending", "resolved", "all"):
        raise bad_request("unknown issue status")
    try:
        limit = int(ctx.q("limit") or 500)
    except ValueError:
        raise bad_request("limit must be a number")
    if not 1 <= limit <= 5000:
        raise bad_request("limit must be between 1 and 5000")
    rows = db.list_website_issues(ctx.conn, status, limit)
    return {"issues": [dict(row) for row in rows]}


def api_resolve_website_issue(ctx):
    issue_id = int(ctx.match.group("id"))
    row = ctx.conn.execute("SELECT id, status FROM website_issue_reports WHERE id = ?", (issue_id,)).fetchone()
    if not row:
        raise ApiError(HTTPStatus.NOT_FOUND, "website issue not found")
    action = ctx.body.get("action", "resolved")
    if not isinstance(action, str) or action.strip().lower() not in ("resolved", "dismissed"):
        raise bad_request("action must be resolved or dismissed")
    action = action.strip().lower()
    if not db.resolve_website_issue(ctx.conn, issue_id, action, ctx.user["id"]):
        raise ApiError(HTTPStatus.CONFLICT, "that issue is already handled")
    return {"ok": True}
