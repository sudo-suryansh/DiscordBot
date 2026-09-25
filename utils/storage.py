import os
import logging
from utils.json_store import load_json, save_json

logger = logging.getLogger(__name__)

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
WARNINGS_FILE = os.path.join(DATA_DIR, "warnings.json")


def _ensure_file():
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(WARNINGS_FILE):
        save_json(WARNINGS_FILE, {})


def load_warnings() -> dict:
    _ensure_file()
    data = load_json(WARNINGS_FILE, {})
    cleaned = {}
    for guild_id, users in data.items():
        if not isinstance(users, dict):
            logger.error("Ignoring malformed warning data for guild %s", guild_id)
            continue
        cleaned[guild_id] = {}
        for user_id, warnings in users.items():
            if isinstance(warnings, list):
                cleaned[guild_id][user_id] = [item for item in warnings if isinstance(item, dict)]
            else:
                logger.error("Ignoring malformed warning list for guild %s, user %s", guild_id, user_id)
                cleaned[guild_id][user_id] = []
    return cleaned


def save_warnings(data: dict) -> None:
    _ensure_file()
    save_json(WARNINGS_FILE, data)


def add_warning(guild_id: int, user_id: int, moderator_id: int, reason: str) -> int:
    """Adds a warning and returns the user's new warning count."""
    data = load_warnings()
    gid, uid = str(guild_id), str(user_id)
    data.setdefault(gid, {}).setdefault(uid, [])
    data[gid][uid].append({"moderator_id": moderator_id, "reason": reason})
    save_warnings(data)
    return len(data[gid][uid])


def get_warnings(guild_id: int, user_id: int) -> list:
    data = load_warnings()
    return data.get(str(guild_id), {}).get(str(user_id), [])


def clear_warnings(guild_id: int, user_id: int) -> None:
    data = load_warnings()
    gid, uid = str(guild_id), str(user_id)
    if gid in data and uid in data[gid]:
        data[gid][uid] = []
        save_warnings(data)
