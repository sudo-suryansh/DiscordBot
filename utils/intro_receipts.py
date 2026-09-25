"""Track successful delivery of Dot's one-time member introduction."""

import os

from utils.json_store import load_json, save_json

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
RECEIPTS_FILE = os.path.join(DATA_DIR, "dot_intro_receipts.json")


def _load():
    os.makedirs(DATA_DIR, exist_ok=True)
    data = load_json(RECEIPTS_FILE, {"guilds": {}})
    if not isinstance(data.get("guilds"), dict):
        data["guilds"] = {}
    return data


def has_received(guild_id, user_id):
    guild = _load().get("guilds", {}).get(str(guild_id), {})
    return str(user_id) in guild


def received_users(guild_id):
    return set(_load().get("guilds", {}).get(str(guild_id), {}))


def mark_received(guild_id, user_id):
    data = _load()
    data.setdefault("guilds", {}).setdefault(str(guild_id), {})[str(user_id)] = True
    save_json(RECEIPTS_FILE, data)
