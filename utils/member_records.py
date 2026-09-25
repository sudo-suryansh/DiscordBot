"""Persistent guild member activity records and streak calculations."""

import os
import re
from datetime import date, timedelta

from utils.json_store import load_json, save_json

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
RECORDS_FILE = os.path.join(DATA_DIR, "member_records.json")


def _load():
    os.makedirs(DATA_DIR, exist_ok=True)
    data = load_json(RECORDS_FILE, {"guilds": {}})
    if not isinstance(data.get("guilds"), dict):
        data["guilds"] = {}
    return data


def _save(data):
    os.makedirs(DATA_DIR, exist_ok=True)
    save_json(RECORDS_FILE, data)


def streak_for_dates(days, today=None):
    """Return current/longest streaks from unique ISO calendar dates."""
    today = today or date.today()
    parsed = sorted({date.fromisoformat(value) for value in days})
    if not parsed:
        return 0, 0
    longest = run = 0
    previous = None
    for day in parsed:
        run = run + 1 if previous and day == previous + timedelta(days=1) else 1
        longest = max(longest, run)
        previous = day
    current = 0
    cursor = today if today.isoformat() in {d.isoformat() for d in parsed} else today - timedelta(days=1)
    present = set(parsed)
    while cursor in present:
        current += 1
        cursor -= timedelta(days=1)
    return current, longest


def _user_record(data, guild_id, user_id):
    guilds = data.setdefault("guilds", {})
    guild = guilds.setdefault(str(guild_id), {})
    return guild.setdefault("users", {}).setdefault(str(user_id), {
        "task_dates": [], "task_total": 0,
        "solution_dates": [], "solutions": [], "screenshots_seen": [],
        "random_screenshots": 0,
    })


def record_task_completion(guild_id, user_id, day):
    data = _load()
    record = _user_record(data, guild_id, user_id)
    dates = set(record.setdefault("task_dates", []))
    if day not in dates:
        dates.add(day)
        record["task_dates"] = sorted(dates)
        record["task_total"] = len(dates)
    _save(data)


def get_member_record(guild_id, user_id, today=None):
    data = _load()
    record = data.get("guilds", {}).get(str(guild_id), {}).get("users", {}).get(str(user_id), {})
    result = dict(record)
    result["task_total"] = len(set(record.get("task_dates", [])))
    result["task_streak"], result["task_longest_streak"] = streak_for_dates(record.get("task_dates", []), today=today)
    result["questions_solved"] = len({item.get("key") for item in record.get("solutions", []) if item.get("key")})
    result["solution_streak"], result["solution_longest_streak"] = streak_for_dates(record.get("solution_dates", []), today=today)
    result["solution_dates"] = sorted(set(record.get("solution_dates", [])))
    result["random_screenshots"] = int(record.get("random_screenshots", 0))
    return result


def record_non_leetcode_image(guild_id, user_id, digest=None):
    data = _load()
    record = _user_record(data, guild_id, user_id)
    if digest and digest in record.setdefault("screenshots_seen", []):
        return
    if digest:
        record["screenshots_seen"].append(digest)
    record["random_screenshots"] = int(record.get("random_screenshots", 0)) + 1
    _save(data)


def has_seen_screenshot(guild_id, user_id, digest):
    data = _load()
    record = data.get("guilds", {}).get(str(guild_id), {}).get("users", {}).get(str(user_id), {})
    return digest in record.get("screenshots_seen", [])


def record_solution(guild_id, user_id, day, digest, title, slug=None):
    """Store a confirmed solution once per image and once per identifiable problem."""
    data = _load()
    record = _user_record(data, guild_id, user_id)
    seen = set(record.setdefault("screenshots_seen", []))
    if digest in seen:
        return False, False
    seen.add(digest)
    record["screenshots_seen"] = list(seen)
    title = " ".join(str(title or "").split())[:120]
    normalized = re.sub(r"[^a-z0-9]+", "-", (slug or title).casefold()).strip("-")
    if not normalized:
        return False, False
    solutions = record.setdefault("solutions", [])
    new_question = normalized not in {item.get("key") for item in solutions}
    if new_question:
        solutions.append({"key": normalized, "title": title or normalized, "first_seen": day})
    dates = set(record.setdefault("solution_dates", []))
    new_day = day not in dates
    dates.add(day)
    record["solution_dates"] = sorted(dates)
    _save(data)
    return new_question, new_day
