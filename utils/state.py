import json
import os

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
STATE_FILE = os.path.join(DATA_DIR, "state.json")


def _ensure_file():
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(STATE_FILE):
        with open(STATE_FILE, "w") as f:
            json.dump({}, f)


def get_last_announced_version():
    _ensure_file()
    with open(STATE_FILE, "r") as f:
        return json.load(f).get("last_announced_version")


def set_last_announced_version(version: str) -> None:
    _ensure_file()
    with open(STATE_FILE, "r") as f:
        data = json.load(f)
    data["last_announced_version"] = version
    with open(STATE_FILE, "w") as f:
        json.dump(data, f, indent=2)
