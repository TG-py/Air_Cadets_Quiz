"""HTTP transport, static-file delivery, and application startup."""
import json
import logging
import mimetypes
import os
import secrets
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, unquote, urlparse

import db
from api import COMPILED
from api_common import ApiError, Ctx, bad_request

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
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
LOGGER = logging.getLogger("air_cadets_quiz.http")


class QuizHandler(BaseHTTPRequestHandler):
    server_version = "AirCadetsQuiz/1.0"
    protocol_version = "HTTP/1.1"

    def client_ip(self):
        return self.client_address[0] if self.client_address else "unknown"

    def set_cookie(self, token):
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
        relative_path = os.path.normpath(unquote(path)).lstrip("/\\")
        full_path = os.path.realpath(os.path.join(STATIC_DIR, relative_path))
        static_root = os.path.realpath(STATIC_DIR)
        try:
            is_inside_static_root = os.path.commonpath((static_root, full_path)) == static_root
        except ValueError:
            is_inside_static_root = False
        if not is_inside_static_root or not os.path.isfile(full_path):
            return self.send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
        ctype, _ = mimetypes.guess_type(full_path)
        with open(full_path, "rb") as handle:
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
                try:
                    with db.connection() as conn:
                        conn.execute("SELECT 1").fetchone()
                except Exception:
                    LOGGER.exception("health_check_failed")
                    return self.send_json(HTTPStatus.SERVICE_UNAVAILABLE, {"ok": False, "error": "database unavailable"})
                return self.send_json(HTTPStatus.OK, {"ok": True, "database": "ok"})
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
        except Exception:  # noqa: BLE001
            LOGGER.exception("request_failed method=%s path=%s", method, urlparse(self.path).path)
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
            LOGGER.info("request remote=%s detail=%s", self.address_string(), fmt % args)

    def log_error(self, fmt, *args):
        LOGGER.error("http_error remote=%s detail=%s", self.address_string(), fmt % args)


