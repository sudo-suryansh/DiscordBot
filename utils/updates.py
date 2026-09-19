import discord

from version import VERSION, CHANGELOG
from utils.state import get_last_announced_version, set_last_announced_version
from utils.channels import get_channel
from utils.embeds import action_embed


async def announce_update(bot, force: bool = False):
    """Posts the current version's changelog to each guild's #updates channel.

    Returns a list of (guild_name, status) tuples so callers (console log on
    startup, or the /checkupdate command) can see exactly what happened
    instead of it failing silently.

    Skips entirely if VERSION already matches what was last announced,
    unless force=True (used by /checkupdate for testing).
    """
    last = get_last_announced_version()
    if last == VERSION and not force:
        return [("*", f"Already announced v{VERSION} — nothing new. Use /checkupdate to force a resend.")]

    changes = CHANGELOG.get(VERSION, ["No changelog notes were added for this version."])
    embed = action_embed(
        "update", f"Bot updated to v{VERSION}",
        description="\n".join(f"• {c}" for c in changes),
        color=discord.Color.green(),
        footer=f"Previous version: v{last}" if last else None,
    )

    results = []
    if not bot.guilds:
        results.append(("*", "Bot isn't in any guilds — nothing to announce to."))
        return results

    for guild in bot.guilds:
        channel = get_channel(guild, "updates")
        if not channel:
            results.append((
                guild.name,
                "No #updates channel found. Check the channel name contains 'update', "
                "or set one explicitly with /setchannel updates #your-channel.",
            ))
            continue
        try:
            await channel.send(embed=embed)
            results.append((guild.name, f"Sent to #{channel.name}."))
        except discord.Forbidden:
            results.append((
                guild.name,
                f"Found #{channel.name} but I don't have permission to send messages there "
                f"(check the bot's role permissions / channel overrides).",
            ))
        except discord.HTTPException as e:
            results.append((guild.name, f"Found #{channel.name} but sending failed: {e}"))

    if not force:
        set_last_announced_version(VERSION)
    return results
