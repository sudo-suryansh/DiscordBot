import os
import asyncio
from keep_alive import keep_alive
import discord
from discord.ext import commands
from dotenv import load_dotenv

from utils.updates import announce_update

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# Optional: set this in .env to your test server's ID for instant slash-command
# syncing while developing. Guild-specific syncs show up immediately; a global
# sync (no GUILD_ID set) can take up to an hour to propagate everywhere.
DEV_GUILD_ID = os.getenv("DEV_GUILD_ID")

DM_NATURAL_COMMANDS = {
    "another", "checkupdate", "help", "leet", "ping", "shutdown", "start",
    "synccommands", "userinfo", "version",
}


async def get_command_prefix(bot, message):
    # In DMs, recognize supported command words without a prefix. Keep this
    # limited to known commands so ordinary conversation is never parsed.
    if message.guild is None:
        words = (message.content or "").strip().split(maxsplit=1)
        if words and words[0].casefold() in DM_NATURAL_COMMANDS:
            return ["!", ""]
    return "!"

intents = discord.Intents.default()
intents.message_content = True   # kept for now; not required once everything is slash commands
intents.members = True           # required for join/leave events, member lookups

bot = commands.Bot(command_prefix=get_command_prefix, intents=intents, help_command=None)


@bot.event
async def on_message(message):
    guard = getattr(bot, "dm_command_guard", None)
    if getattr(bot, "is_shutdown", False):
        words = (message.content or "").strip().split(maxsplit=1)
        is_owner_start = (
            message.guild is None
            and words
            and words[0].casefold() == "!start"
            and not getattr(bot, "is_shutting_down", False)
            and guard is not None
            and await guard.is_owner_user(message.author)
        )
        if not is_owner_start:
            return
        # Recovery is always available to the owner, even during spam lockout.
        guard.reset_user(message.author.id)
        await bot.process_commands(message)
        return

    # Ignore prefix parsing during an active DM spam lockout. Discord still
    # delivers that user's gateway events to the bot.
    if message.guild is None and guard and await guard.observe_dm_message(message):
        return
    await bot.process_commands(message)

# List of cogs to load. Add new ones here as you build them (e.g. "cogs.dsa").
INITIAL_EXTENSIONS = [
    "cogs.moderation",
    "cogs.automod",
    "cogs.utility",
    "cogs.admin",
    "cogs.help",
    "cogs.dotai",
    "cogs.power",
    "cogs.dsa",
    "cogs.dm_guard",
]


@bot.event
async def on_ready():
    print(f"Bot is online as {bot.user} (id: {bot.user.id})")
    print(f"Connected to {len(bot.guilds)} guild(s)")

    if getattr(bot, "is_shutdown", False):
        print("Bot remains paused; only the owner's !start command is enabled.")
        return

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

    # Bump VERSION + add a CHANGELOG entry in version.py whenever you ship a
    # change, then restart — this checks on every startup and announces once.
    # Prints exactly what happened (or why it didn't) instead of failing silently.
    # You can also trigger this on demand with the owner-only /checkupdate command.
    results = await announce_update(bot)
    for guild_name, status in results:
        print(f"[update announce] {guild_name}: {status}")


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
