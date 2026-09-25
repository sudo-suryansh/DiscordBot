import discord

# Keywords used to auto-detect a channel by name when nothing has been
# configured explicitly with /setchannel. Matching is a simple substring
# check against the channel name (lowercased), so "malcious-activity",
# "mod-commands", etc. all match without needing exact IDs.
CHANNEL_KEYWORDS = {
    "welcome": ["welcome"],
    "logs": ["logs", "log"],
    "modlog": ["mod-commands", "mod-command", "modcommands"],
    "kickban": ["kicks-bans-mutes", "kick-ban", "kicksbansmutes", "kicks-bans"],
    "automod": ["malcious-activity", "malicious-activity", "automod"],
    "updates": ["updates", "update"],
}

# Maps a channel_type -> the key it's stored under in a guild's config.json
CONFIG_KEY_MAP = {
    "welcome": "welcome_channel_id",
    "commands": "commands_channel_id",
    "logs": "log_channel_id",
    "modlog": "mod_log_channel_id",
    "kickban": "kick_ban_channel_id",
    "automod": "automod_channel_id",
    "updates": "update_channel_id",
    "problem": "problem_channel_id",
}


def find_channel_by_keywords(guild: discord.Guild, keywords):
    for channel in guild.text_channels:
        name = channel.name.lower()
        if any(kw in name for kw in keywords):
            return channel
    return None


def get_channel(guild: discord.Guild, channel_type: str):
    """Returns the channel configured for `channel_type` (welcome, logs,
    modlog, kickban, automod, updates). Falls back to auto-detecting a text
    channel whose name matches that type's keywords if nothing has been set
    with /setchannel, so this works out of the box with no setup."""
    from utils.config import get_guild_config  # local import avoids a circular import

    cfg = get_guild_config(guild.id)
    key = CONFIG_KEY_MAP.get(channel_type)
    channel_id = cfg.get(key) if key else None
    if channel_id:
        channel = guild.get_channel(channel_id)
        if channel:
            return channel
    return find_channel_by_keywords(guild, CHANNEL_KEYWORDS.get(channel_type, []))


def get_command_channels(guild: discord.Guild):
    """Return configured command channels, including the legacy single-channel setting."""
    from utils.config import get_guild_config

    cfg = get_guild_config(guild.id)
    ids = cfg.get("command_channel_ids") or []
    legacy_id = cfg.get("commands_channel_id")
    if legacy_id:
        ids = [legacy_id, *ids]
    channels = []
    seen = set()
    for channel_id in ids:
        if channel_id in seen:
            continue
        seen.add(channel_id)
        channel = guild.get_channel(channel_id)
        if channel is not None and isinstance(channel, discord.TextChannel):
            channels.append(channel)
    return channels
