"""Low-cost, local-only personalization memory. Raw messages are never stored."""

import os
import re

from utils.json_store import load_json, save_json

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
MEMORY_FILE = os.path.join(DATA_DIR, "member_memory.json")

POLITE = ("please", "thanks", "thank you", "appreciate", "could you", "would you", "kindly")
HOSTILE = ("idiot", "stupid", "dumbass", "shut up", "fuck you", "useless bot", "hate you")


def _load():
    os.makedirs(DATA_DIR, exist_ok=True)
    data = load_json(MEMORY_FILE, {"guilds": {}})
    if not isinstance(data.get("guilds"), dict):
        data["guilds"] = {}
    return data


def observe_interaction(guild_id, user_id, text):
    """Store only aggregate tone signals, never the user's prompt or message text."""
    folded = re.sub(r"\s+", " ", str(text or "").casefold()).strip()
    if not folded:
        return
    if any(term in folded for term in HOSTILE):
        signal = "hostile"
    elif any(term in folded for term in POLITE):
        signal = "courteous"
    else:
        signal = "direct"
    data = _load()
    profile = data.setdefault("guilds", {}).setdefault(str(guild_id), {}).setdefault("users", {}).setdefault(str(user_id), {
        "interactions": 0, "courteous": 0, "direct": 0, "hostile": 0,
    })
    profile["interactions"] = int(profile.get("interactions", 0)) + 1
    profile[signal] = int(profile.get(signal, 0)) + 1
    save_json(MEMORY_FILE, data)


def get_personalization(guild_id, user_id):
    profile = _load().get("guilds", {}).get(str(guild_id), {}).get("users", {}).get(str(user_id), {})
    total = int(profile.get("interactions", 0))
    if total < 3:
        return None
    courteous = int(profile.get("courteous", 0))
    hostile = int(profile.get("hostile", 0))
    direct = int(profile.get("direct", 0))
    if hostile / total >= 0.4:
        return "direct"
    if courteous / total >= 0.4:
        return "warm"
    if direct / total >= 0.6:
        return "concise"
    return "neutral"


def erase_personalization(guild_id, user_id):
    data = _load()
    guild = data.get("guilds", {}).get(str(guild_id), {})
    users = guild.get("users", {})
    existed = users.pop(str(user_id), None) is not None
    if not users:
        data["guilds"].pop(str(guild_id), None)
    save_json(MEMORY_FILE, data)
    # The normal JSON store preserves the previous version as a recovery backup.
    # After an explicit erase, advance that backup to the erased state as well,
    # and remove stale recovery/temp copies that could contain the old profile.
    save_json(MEMORY_FILE, data)
    for filename in os.listdir(DATA_DIR):
        if filename.startswith("member_memory.json.corrupt.") or filename in {
            "member_memory.json.tmp", "member_memory.json.bak.tmp",
        }:
            try:
                os.remove(os.path.join(DATA_DIR, filename))
            except OSError:
                pass
    return existed
