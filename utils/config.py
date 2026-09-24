import json
import os

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
CONFIG_FILE = os.path.join(DATA_DIR, "config.json")

DEFAULTS = {
    "admin_role_id": None,       # role allowed to use mod commands (kick, mute, warn, etc.)
    "welcome_channel_id": None,  # channel where join messages + join DMs originate from
    "log_channel_id": None,      # general audit log: joins/leaves, lock/unlock, etc.
    "mod_log_channel_id": None,  # warn/clearwarns/clear/lock/unlock/slowmode/admin-config logs
    "kick_ban_channel_id": None, # kick/mute/unmute logs
    "automod_channel_id": None,  # automod flags (spam, mass mentions, invite links)
    "update_channel_id": None,   # bot version/changelog announcements
    "problem_channel_id": None,  # requested LeetCode problems

    # Automod is on by default but deliberately lenient — see cogs/automod.py.
    "automod_enabled": True,
    "automod_spam_count": 5,       # messages...
    "automod_spam_seconds": 5,     # ...within this many seconds triggers a flag
    "automod_mute_minutes": 5,     # timeout duration when spam is caught
    "automod_max_mentions": 5,     # mentions (users+roles) allowed per message
    "automod_block_invites": True,
}


def _ensure_file():
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "w") as f:
            json.dump({}, f)


def _load() -> dict:
    _ensure_file()
    with open(CONFIG_FILE, "r") as f:
        return json.load(f)


def _save(data: dict) -> None:
    _ensure_file()
    with open(CONFIG_FILE, "w") as f:
        json.dump(data, f, indent=2)


def get_guild_config(guild_id: int) -> dict:
    data = _load()
    cfg = data.get(str(guild_id), {})
    return {**DEFAULTS, **cfg}


def set_guild_value(guild_id: int, key: str, value) -> None:
    data = _load()
    gid = str(guild_id)
    data.setdefault(gid, {})
    data[gid][key] = value
    _save(data)
