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
ROLE_GUEST = "guest"
ROLE_STAFF = "staff"
ROLE_ADMIN = "admin"
LOGGER = logging.getLogger("air_cadets_quiz.http")


def read_static_text(relative_path):
    with open(os.path.join(STATIC_DIR, relative_path), encoding="utf-8") as handle:
        return handle.read()


def build_scripts(role):
    scripts = ['<script src="/static/app-core.js"></script>']
    if role in (ROLE_STAFF, ROLE_ADMIN):
        scripts.append('<script src="/static/app-staff.js"></script>')
    if role == ROLE_ADMIN:
        scripts.append('<script src="/static/app-admin.js"></script>')
    return "\n    ".join(scripts)


def build_index(role):
    staff = role in (ROLE_STAFF, ROLE_ADMIN)
    admin = role == ROLE_ADMIN
    learning = read_static_text(os.path.join("nav", "learning-public.html"))
    learning = learning.replace(
        "<!-- nav-staff -->",
        read_static_text(os.path.join("nav", "learning-staff.html")) if staff else "",
    )
    replacements = {
        "<!-- nav-learning -->": learning,
        "<!-- nav-admin -->": read_static_text(os.path.join("nav", "admin.html")) if admin else "",
        "<!-- views-public -->": read_static_text(os.path.join("views", "public.html")),
        "<!-- views-staff -->": read_static_text(os.path.join("views", "staff.html")) if staff else "",
        "<!-- views-admin -->": read_static_text(os.path.join("views", "admin.html")) if admin else "",
        "<!-- scripts -->": build_scripts(role),
    }
    html = read_static_text("index.html")
    for token, content in replacements.items():
        html = html.replace(token, content)
    return html


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

    def current_user(self):
        token = self.read_cookie_token()
        if not token:
            return None
        with db.connection() as conn:
            session = db.get_session(conn, token)
            if not session or not session["user_id"]:
                return None
            user = db.get_user_by_id(conn, session["user_id"])
            if not user or not user["active"]:
                return None
            return user

    def current_role(self):
        user = self.current_user()
        if not user:
            return ROLE_GUEST
        if user["role"] == db.USER_ADMIN:
            return ROLE_ADMIN
        return ROLE_STAFF

    def send_index(self):
        body = build_index(self.current_role()).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Vary", "Cookie")
        self.send_security_headers()
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def send_static(self, path, role_variant=False):
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
        if role_variant:
            self.send_header("Vary", "Cookie")
            self.send_header("Cache-Control", "no-store")
        else:
            self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def send_asset(self, relative_path):
        safe_path = os.path.normpath(unquote(relative_path)).lstrip("/\\")
        if safe_path in ("index.html", "app.js", "views", "nav") or safe_path.startswith("views/") or safe_path.startswith("nav/"):
            return self.send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
        if safe_path in ("app-staff.js", "app-admin.js"):
            role = self.current_role()
            if safe_path == "app-staff.js" and role not in (ROLE_STAFF, ROLE_ADMIN):
                return self.send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            if safe_path == "app-admin.js" and role != ROLE_ADMIN:
                return self.send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return self.send_static(safe_path, role_variant=True)
        return self.send_static(safe_path)

    def read_body(self):
        # Once this runs the body is either read or the connection is closed,
        # so consume_body leaves it alone from here on.
        self._body_read = True
        length = self.headers.get("Content-Length")
        if not length:
            return {}
        try:
            size = int(length)
        except ValueError:
            self.close_connection = True
            raise bad_request("invalid content length")
        if size <= 0:
            return {}
        if size > MAX_BODY_BYTES:
            self.close_connection = True
            raise ApiError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "request body is too large")
        raw = self.rfile.read(size)
        if not raw.strip():
            return {}
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise bad_request("request body must be valid json")

    def consume_body(self):
        """Drain any request body a handler did not read.

        Responses such as 401/403/404/405 are sent before the body is parsed,
        so on a kept-alive connection the unread bytes would be mistaken for
        the next request line. Read them here to keep the socket in sync.
        """
        if self._body_read:
            return
        self._body_read = True
        length = self.headers.get("Content-Length")
        try:
            remaining = int(length) if length else 0
        except ValueError:
            self.close_connection = True
            return
        if remaining > MAX_BODY_BYTES:
            self.close_connection = True
            return
        while remaining > 0:
            chunk = self.rfile.read(min(remaining, 65536))
            if not chunk:
                break
            remaining -= len(chunk)

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
                return self.send_index()
            if path.startswith("/static/"):
                return self.send_asset(path[len("/static/"):])
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
        finally:
            self.consume_body()

    def do_GET(self):
        self._pending_cookie = None
        self._body_read = False
        self.dispatch("GET")

    def do_POST(self):
        self._pending_cookie = None
        self._body_read = False
        self.dispatch("POST")

    def do_HEAD(self):
        self._pending_cookie = None
        self._body_read = False
        self.dispatch("GET")

    def log_message(self, fmt, *args):
        if LOG_REQUESTS:
            LOGGER.info("request remote=%s detail=%s", self.address_string(), fmt % args)

    def log_error(self, fmt, *args):
        LOGGER.error("http_error remote=%s detail=%s", self.address_string(), fmt % args)


