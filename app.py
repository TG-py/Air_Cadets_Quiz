"""Application entry point for the RAFAC quiz."""
import logging
import os
import secrets
import sys
from http.server import ThreadingHTTPServer

import auth
import db
from webserver import HOST, PORT, QuizHandler

LOGGER = logging.getLogger("air_cadets_quiz")

def bootstrap_admin():
    if db.user_count():
        return
    with db.connection() as conn:
        username = os.environ.get("ADMIN_USERNAME", "admin").strip() or "admin"
        generated = None
        password = os.environ.get("ADMIN_PASSWORD")
        must_change = 0
        if not password:
            generated = secrets.token_urlsafe(9)
            password = generated
            must_change = 1
        try:
            auth.validate_username(username)
            auth.validate_password(password)
        except ValueError as exc:
            sys.stderr.write("cannot create admin account: %s\n" % exc)
            return
        digest, salt = auth.hash_password(password)
        db.create_user(
            conn,
            username=username,
            password=password,
            salt=salt,
            password_hash=digest,
            role=db.USER_ADMIN,
            display_name="Administrator",
            must_change=must_change,
        )
        sys.stderr.write("=" * 62 + "\n")
        sys.stderr.write("Created the admin account '%s'.\n" % username)
        if generated:
            sys.stderr.write("  password: %s\n" % generated)
            sys.stderr.write("  Save this now - it is not stored in plain text and\n")
            sys.stderr.write("  you will be asked to change it after logging in.\n")
        else:
            sys.stderr.write("  password taken from ADMIN_PASSWORD.\n")
        sys.stderr.write("=" * 62 + "\n")


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    try:
        db.init()
        bootstrap_admin()
        server = ThreadingHTTPServer((HOST, PORT), QuizHandler)
    except Exception:
        LOGGER.exception("startup_failed")
        raise
    LOGGER.info("server_started host=%s port=%s", HOST, PORT)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        LOGGER.info("server_stopping")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
