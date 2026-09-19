import discord

ACTION_EMOJI = {
    "kick": "👢",
    "mute": "🔇",
    "unmute": "🔊",
    "warn": "⚠️",
    "clearwarns": "🧹",
    "clear": "🧽",
    "lock": "🔒",
    "unlock": "🔓",
    "slowmode": "🐢",
    "join": "📥",
    "leave": "📤",
    "automod": "🚨",
    "config": "⚙️",
    "update": "🔧",
}


def member_action_embed(action_key: str, title: str, target, moderator, reason: str = None,
                         color=discord.Color.orange(), extra_fields=None):
    """For actions targeting a specific member (kick/mute/warn/etc.). Shows
    the target's avatar as the author + thumbnail, moderator + any extra
    fields side by side, and the reason on its own line at the bottom."""
    embed = discord.Embed(
        title=f"{ACTION_EMOJI.get(action_key, '')} {title}".strip(),
        color=color,
        timestamp=discord.utils.utcnow(),
    )
    if target is not None:
        avatar = getattr(target, "display_avatar", None)
        avatar_url = avatar.url if avatar else None
        embed.set_author(name=str(target), icon_url=avatar_url)
        if avatar_url:
            embed.set_thumbnail(url=avatar_url)
        embed.set_footer(text=f"User ID: {target.id}")

    embed.add_field(name="Moderator", value=getattr(moderator, "mention", str(moderator)), inline=True)
    if extra_fields:
        for name, value, inline in extra_fields:
            embed.add_field(name=name, value=value, inline=inline)
    embed.add_field(name="Reason", value=reason or "No reason provided", inline=False)
    return embed


def action_embed(action_key: str, title: str, description: str = None, color=discord.Color.blurple(),
                  actor=None, fields=None, footer: str = None):
    """For actions that aren't about one member (channel locks, config
    changes, join/leave, automod flags, update announcements)."""
    embed = discord.Embed(
        title=f"{ACTION_EMOJI.get(action_key, '')} {title}".strip(),
        description=description,
        color=color,
        timestamp=discord.utils.utcnow(),
    )
    if actor is not None:
        avatar = getattr(actor, "display_avatar", None)
        embed.set_author(name=str(actor), icon_url=avatar.url if avatar else None)
        if avatar:
            embed.set_thumbnail(url=avatar.url)
    if fields:
        for name, value, inline in fields:
            embed.add_field(name=name, value=value, inline=inline)
    if footer:
        embed.set_footer(text=footer)
    return embed
