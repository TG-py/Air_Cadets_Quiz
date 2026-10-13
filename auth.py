import hashlib
import hmac
import re
import secrets
import time
from datetime import datetime, timedelta, timezone

import db

SCRYPT_N = 2 ** 14
SCRYPT_R = 8
SCRYPT_P = 1
DKLEN = 64
# 128 * n * r is the working set scrypt needs. Set explicitly so this cannot
# fail with "memory limit exceeded" on builds whose default maxmem is smaller.
SCRYPT_MAXMEM = 128 * SCRYPT_N * SCRYPT_R * 2

USER_TTL = timedelta(days=7)
GUEST_TTL = timedelta(hours=12)

LOGIN_WINDOW_SECONDS = 300
LOGIN_MAX_FAILURES = 8
LOGIN_LOCK_SECONDS = 60

USERNAME_RE = re.compile(r"^[A-Za-z0-9._-]{3,32}$")
MIN_PASSWORD_LENGTH = 8

_login_failures = {}


def utc_now():
    return datetime.now(timezone.utc)


def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt.encode("utf-8"),
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        dklen=DKLEN,
        maxmem=SCRYPT_MAXMEM,
    )
    return digest.hex(), salt


def verify_password(password, row):
    if not row:
        return False
    candidate, _ = hash_password(password, row["salt"])
    return hmac.compare_digest(candidate, row["password_hash"])


def validate_username(username):
    if not USERNAME_RE.match(username or ""):
        raise ValueError(
            "username must be 3-32 characters using letters, numbers, dot, underscore or dash"
        )
    return username


def validate_password(password):
    if len(password or "") < MIN_PASSWORD_LENGTH:
        raise ValueError(
            "password must be at least %d characters" % MIN_PASSWORD_LENGTH
        )
    return password


def new_token():
    return secrets.token_urlsafe(32)


def new_csrf():
    return secrets.token_urlsafe(24)


def start_session(conn, user_id):
    token = new_token()
    csrf = new_csrf()
    ttl = USER_TTL if user_id else GUEST_TTL
    expires = (utc_now() + ttl).replace(microsecond=0).isoformat()
    db.add_session(conn, token, user_id, csrf, expires)
    return token, csrf, expires


def login_rate_key(ip, username):
    return "%s|%s" % (ip, (username or "").lower())


def register_failure(key):
    entry = _login_failures.get(key)
    now_ts = time.time()
    if not entry or now_ts - entry["first"] > LOGIN_WINDOW_SECONDS:
        entry = {"count": 0, "first": now_ts, "locked_until": 0}
    entry["count"] += 1
    if entry["count"] >= LOGIN_MAX_FAILURES:
        entry["locked_until"] = now_ts + LOGIN_LOCK_SECONDS
        entry["count"] = 0
    _login_failures[key] = entry
    return entry


def clear_failures(key):
    _login_failures.pop(key, None)


def lockout_remaining(key):
    entry = _login_failures.get(key)
    if not entry:
        return 0
    remaining = entry["locked_until"] - time.time()
    return int(remaining) + 1 if remaining > 0 else 0


def public_user(row):
    if not row:
        return None
    return {
        "id": row["id"],
        "username": row["username"],
        "display_name": row["display_name"] or row["username"],
        "role": row["role"],
        "must_change": bool(row["must_change"]),
    }
