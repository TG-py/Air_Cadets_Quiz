"""Shared API errors, request context, and validation helpers."""
from http import HTTPStatus

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


