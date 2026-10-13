import random

import db

WEIGHT_NEVER_ASKED = 3.0
WEIGHT_FLOOR = 0.25
WEIGHT_CEILING = 4.0
WRONG_STREAK_THRESHOLD = 2
WRONG_STREAK_MULTIPLIER = 1.5
ABSOLUTE_MAX_WEIGHT = 6.0


def weight_for(asked, correct, wrong_streak):
    if asked <= 0:
        return WEIGHT_NEVER_ASKED
    wrong_ratio = 1.0 - (correct / asked)
    weight = WEIGHT_FLOOR + (WEIGHT_CEILING - WEIGHT_FLOOR) * (wrong_ratio ** 2)
    if wrong_streak >= WRONG_STREAK_THRESHOLD:
        weight *= WRONG_STREAK_MULTIPLIER
    return min(weight, ABSOLUTE_MAX_WEIGHT)


def wrong_streaks(conn):
    """How many wrong answers in a row each question currently has."""
    streaks = {}
    for row in conn.execute(
        "SELECT question_id, correct FROM attempts WHERE skipped = 0 ORDER BY id ASC"
    ):
        if row["correct"]:
            streaks[row["question_id"]] = 0
        else:
            streaks[row["question_id"]] = streaks.get(row["question_id"], 0) + 1
    return streaks


def build_pool(conn, topic=None):
    stats = db.question_stats(conn)
    streaks = wrong_streaks(conn)

    if topic:
        rows = conn.execute(
            "SELECT id, question_text, answer_text, topic FROM questions "
            "WHERE status = ? AND topic = ? COLLATE NOCASE",
            (db.Q_APPROVED, topic),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, question_text, answer_text, topic FROM questions WHERE status = ?",
            (db.Q_APPROVED,),
        ).fetchall()

    pool = []
    for row in rows:
        stat = stats.get(row["id"], {"asked": 0, "correct": 0})
        asked = stat["asked"]
        correct = stat["correct"]
        streak = streaks.get(row["id"], 0)
        pool.append(
            {
                "id": row["id"],
                "question_text": row["question_text"],
                "answer_text": row["answer_text"],
                "topic": row["topic"],
                "asked": asked,
                "correct": correct,
                "wrong_streak": streak,
                "weight": round(weight_for(asked, correct, streak), 3),
            }
        )
    return pool


def pick(pool, exclude_ids=()):
    if not pool:
        return None
    excluded = set(exclude_ids)
    candidates = [q for q in pool if q["id"] not in excluded]
    if not candidates:
        return None
    return random.choices(candidates, weights=[q["weight"] for q in candidates], k=1)[0]
