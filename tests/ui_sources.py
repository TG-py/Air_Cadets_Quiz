"""Compose the split frontend sources for static-content checks."""
import os
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC = os.path.join(ROOT, "static")
APP_FILES = ("app-core.js", "app-staff.js", "app-admin.js")


def read(relative_path):
    with open(os.path.join(STATIC, relative_path), encoding="utf-8") as handle:
        return handle.read()


def index_source():
    learning = read(os.path.join("nav", "learning-public.html"))
    learning = learning.replace("<!-- nav-staff -->", read(os.path.join("nav", "learning-staff.html")))
    scripts = "\n    ".join(
        '<script src="/static/%s"></script>' % name for name in APP_FILES
    )
    replacements = {
        "<!-- nav-learning -->": learning,
        "<!-- nav-admin -->": read(os.path.join("nav", "admin.html")),
        "<!-- views-public -->": read(os.path.join("views", "public.html")),
        "<!-- views-staff -->": read(os.path.join("views", "staff.html")),
        "<!-- views-admin -->": read(os.path.join("views", "admin.html")),
        "<!-- scripts -->": scripts,
    }
    html = read("index.html")
    for token, content in replacements.items():
        html = html.replace(token, content)
    return html


def app_source():
    return "\n".join(read(name) for name in APP_FILES)


def combined_app_path():
    path = os.path.join(tempfile.gettempdir(), "rafac_app_all.js")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(app_source())
    return path
