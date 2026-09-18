import json
import os

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
WARNINGS_FILE = os.path.join(DATA_DIR, "warnings.json")


def _ensure_file():
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(WARNINGS_FILE):
        with open(WARNINGS_FILE, "w") as f:
            json.dump({}, f)


def load_warnings() -> dict:
    _ensure_file()
    with open(WARNINGS_FILE, "r") as f:
        return json.load(f)


def save_warnings(data: dict) -> None:
    _ensure_file()
    with open(WARNINGS_FILE, "w") as f:
        json.dump(data, f, indent=2)


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
