import argparse
import csv
import io
import json
import os
import sys

import db

QUESTION_KEYS = ("question", "question_text", "q")
ANSWER_KEYS = ("answer", "answer_text", "a")
TOPIC_KEYS = ("topic", "category", "subject")


def read_text(path):
    if path == "-":
        return sys.stdin.read()
    encodings = ["utf-8-sig", "utf-8", "cp1252", "latin-1"]
    for encoding in encodings:
        try:
            with open(path, "r", encoding=encoding) as handle:
                return handle.read()
        except UnicodeDecodeError:
            continue
    raise SystemExit("could not decode %s, try re-saving it as utf-8" % path)


def first_value(item, keys):
    for key in keys:
        if key in item and str(item[key]).strip():
            return str(item[key]).strip()
    return ""


def parse_json(text):
    data = json.loads(text)
    if isinstance(data, dict):
        data = data.get("questions", data.get("data", []))
    if not isinstance(data, list):
        raise SystemExit("json file must contain a list of questions")
    rows = []
    for item in data:
        if isinstance(item, str):
            rows.append((item.strip(), "", "General"))
        elif isinstance(item, dict):
            rows.append(
                (
                    first_value(item, QUESTION_KEYS),
                    first_value(item, ANSWER_KEYS),
                    first_value(item, TOPIC_KEYS) or "General",
                )
            )
    return rows


def parse_delimited(text):
    sample = text[:4096]
    delimiter = ","
    try:
        delimiter = csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except csv.Error:
        pass
    rows = []
    for record in csv.reader(io.StringIO(text), delimiter=delimiter):
        if not record or not any(cell.strip() for cell in record):
            continue
        cells = [cell.strip() for cell in record]
        if cells[0].lower() in ("question", "question_text"):
            continue
        rows.append(
            (
                cells[0],
                cells[1] if len(cells) > 1 else "",
                cells[2] if len(cells) > 2 else "General",
            )
        )
    return rows


def load_rows(path, fmt):
    text = read_text(path)
    if fmt == "json":
        try:
            return parse_json(text)
        except json.JSONDecodeError as exc:
            raise SystemExit("invalid json in %s: %s" % (path, exc))
    if fmt == "csv":
        return parse_delimited(text)
    stripped = text.lstrip()
    if stripped.startswith("[") or stripped.startswith("{"):
        try:
            return parse_json(text)
        except json.JSONDecodeError:
            pass
    return parse_delimited(text)


def main():
    parser = argparse.ArgumentParser(
        description="Import questions into the Air Cadets quiz bank."
    )
    parser.add_argument("path", help="path to a csv/json/txt file, or - for stdin")
    parser.add_argument(
        "--format",
        choices=["auto", "csv", "json"],
        default="auto",
        help="how to read the file (default: auto)",
    )
    parser.add_argument(
        "--topic", default=None, help="topic applied to every imported question"
    )
    parser.add_argument(
        "--pending",
        action="store_true",
        help="import as pending so you can review them first",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="report what would be imported and stop"
    )
    args = parser.parse_args()

    if not os.path.exists(args.path) and args.path != "-":
        raise SystemExit("no such file: %s" % args.path)

    db.init()
    rows = load_rows(args.path, args.format)
    rows = [r for r in rows if r[0]]
    if not rows:
        raise SystemExit("no questions found in %s" % args.path)

    status = db.Q_PENDING if args.pending else db.Q_APPROVED
    added = 0
    duplicates = 0
    skipped_blank = 0

    conn = db.acquire()
    try:
        if args.dry_run:
            for question_text, answer_text, topic in rows:
                print("- %s | %s | %s" % (question_text, answer_text, topic))
            print("\n%d question(s) would be imported as '%s'." % (len(rows), status))
            return

        seen = set()
        with db.transaction(conn):
            for question_text, answer_text, topic in rows:
                key = question_text.lower()
                if key in seen:
                    duplicates += 1
                    continue
                seen.add(key)
                existing = conn.execute(
                    "SELECT id FROM questions WHERE question_text = ? COLLATE NOCASE",
                    (question_text,),
                ).fetchone()
                if existing:
                    duplicates += 1
                    continue
                if not answer_text:
                    skipped_blank += 1
                db.add_question(
                    conn,
                    question_text=question_text[:2000],
                    answer_text=answer_text[:2000],
                    topic=(args.topic or topic or "General")[:80],
                    status=status,
                    submitted_by="import",
                    source="import",
                )
                added += 1
    finally:
        db.release(conn)

    with db.connection() as conn:
        counts = db.question_counts(conn)
    print("Imported %d question(s) as '%s'." % (added, status))
    print("  already in the bank: %d" % duplicates)
    if skipped_blank:
        print("  no answer supplied:  %d" % skipped_blank)
    print(
        "  bank now holds %d approved, %d pending, %d rejected"
        % (counts["approved"], counts["pending"], counts["rejected"])
    )


if __name__ == "__main__":
    main()
