import os
from utils.json_store import load_json, save_json

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
STATE_FILE = os.path.join(DATA_DIR, "state.json")


def _ensure_file():
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(STATE_FILE):
        save_json(STATE_FILE, {})


def get_last_announced_version():
    _ensure_file()
    return load_json(STATE_FILE, {}).get("last_announced_version")


def set_last_announced_version(version: str) -> None:
    _ensure_file()
    data = load_json(STATE_FILE, {})
    data["last_announced_version"] = version
    save_json(STATE_FILE, data)
