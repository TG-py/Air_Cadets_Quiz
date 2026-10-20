"""Website issue reporting API handlers."""
from http import HTTPStatus

import db
from api_common import ApiError, bad_request, require_fields


def api_submit_website_issue(ctx):
    fields = require_fields(ctx.body, "title", "details")
    title = fields["title"]
    details = fields["details"]
    page = ctx.body.get("page", "")
    if len(title) > 120:
        raise bad_request("title must be 120 characters or fewer")
    if len(details) > 3000:
        raise bad_request("details must be 3000 characters or fewer")
    if not isinstance(page, str):
        page = ""
    issue_id = db.add_website_issue(
        ctx.conn,
        ctx.user["id"] if ctx.user else None,
        title, details, page[:120],
    )
    return {"ok": True, "id": issue_id, "message": "Thanks. Your website issue was sent to the admin team."}


def api_list_website_issues(ctx):
    try:
        limit = int(ctx.q("limit") or 500)
    except ValueError:
        raise bad_request("limit must be a number")
    if not 1 <= limit <= 5000:
        raise bad_request("limit must be between 1 and 5000")
    rows = db.list_website_issues(ctx.conn, limit)
    return {"issues": [dict(row) for row in rows]}


def api_delete_website_issue(ctx):
    issue_id = int(ctx.match.group("id"))
    if not db.delete_website_issue(ctx.conn, issue_id):
        raise ApiError(HTTPStatus.NOT_FOUND, "website issue not found")
    return {"ok": True}
