import os
import asyncio
from keep_alive import keep_alive
import discord
from discord.ext import commands
from dotenv import load_dotenv

from version import VERSION, CHANGELOG
from utils.state import get_last_announced_version, set_last_announced_version
from utils.channels import get_channel
from utils.embeds import action_embed

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# Optional: set this in .env to your test server's ID for instant slash-command
# syncing while developing. Guild-specific syncs show up immediately; a global
# sync (no GUILD_ID set) can take up to an hour to propagate everywhere.
DEV_GUILD_ID = os.getenv("DEV_GUILD_ID")

intents = discord.Intents.default()
intents.message_content = True   # kept for now; not required once everything is slash commands
intents.members = True           # required for join/leave events, member lookups

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# List of cogs to load. Add new ones here as you build them (e.g. "cogs.dsa").
INITIAL_EXTENSIONS = [
    "cogs.moderation",
    "cogs.automod",
    "cogs.utility",
    "cogs.admin",
    "cogs.help",
    "cogs.power",
]


async def announce_update_if_needed():
    """Compares VERSION (version.py) against the last version we announced
    (data/state.json). If it's new, posts that version's CHANGELOG entry to
    every server's #updates channel, then remembers the new version so it
    doesn't announce it again on the next restart.

    Workflow: bump VERSION + add a CHANGELOG entry in version.py whenever you
    ship a change, then restart the bot — the announcement happens on its own."""
    last = get_last_announced_version()
    if last == VERSION:
        return

    changes = CHANGELOG.get(VERSION, ["No changelog notes were added for this version."])
    embed = action_embed(
        "update", f"Bot updated to v{VERSION}",
        description="\n".join(f"• {c}" for c in changes),
        color=discord.Color.green(),
        footer=f"Previous version: v{last}" if last else None,
    )

    for guild in bot.guilds:
        channel = get_channel(guild, "updates")
        if channel:
            try:
                await channel.send(embed=embed)
            except discord.HTTPException:
                pass

    set_last_announced_version(VERSION)


@bot.event
async def on_ready():
    print(f"Bot is online as {bot.user} (id: {bot.user.id})")
    print(f"Connected to {len(bot.guilds)} guild(s)")

    try:
        if DEV_GUILD_ID:
            guild = discord.Object(id=int(DEV_GUILD_ID))
            bot.tree.copy_global_to(guild=guild)
            synced = await bot.tree.sync(guild=guild)
            print(f"Synced {len(synced)} slash command(s) to dev guild {DEV_GUILD_ID} (instant).")
        else:
            synced = await bot.tree.sync()
            print(f"Synced {len(synced)} slash command(s) globally (can take up to ~1 hour to appear everywhere).")
    except Exception as e:
        print(f"Failed to sync slash commands: {e}")

    await announce_update_if_needed()


async def main():
    async with bot:
        for extension in INITIAL_EXTENSIONS:
            try:
                await bot.load_extension(extension)
                print(f"Loaded extension: {extension}")
            except Exception as e:
                print(f"Failed to load extension {extension}: {e}")
        await bot.start(TOKEN)


if __name__ == "__main__":
    keep_alive()
    asyncio.run(main())
