import os
import asyncio
import logging
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
logger = logging.getLogger("dot")


def _unwrap_error(error):
    while isinstance(error, (commands.CommandInvokeError, discord.app_commands.CommandInvokeError)):
        error = error.original
    return error


def _error_message(error, *, interaction=False):
    error = _unwrap_error(error)
    if isinstance(error, (commands.CommandOnCooldown, discord.app_commands.CommandOnCooldown)):
        return f"Please wait {int(error.retry_after + 0.999)}s before trying again."
    if isinstance(error, (commands.MissingRequiredArgument, commands.BadArgument, commands.UserInputError, discord.app_commands.TransformerError)):
        return "Some command details are missing or invalid. Check the command arguments and try again."
    if isinstance(error, (commands.MissingPermissions, discord.app_commands.MissingPermissions)):
        return "You don't have permission to use that command."
    if isinstance(error, (commands.BotMissingPermissions, discord.app_commands.BotMissingPermissions)):
        return "I don't have the Discord permissions needed to complete that action."
    if isinstance(error, (commands.CheckFailure, discord.app_commands.CheckFailure)):
        return "I couldn't run that command because one of its requirements wasn't met."
    if isinstance(error, discord.Forbidden):
        return "Discord denied that action. Check my permissions and the target's role or channel settings."
    if isinstance(error, discord.NotFound):
        return "I couldn't find that Discord item; it may have been removed."
    if isinstance(error, discord.HTTPException):
        return "Discord couldn't complete that action just now. Please try again shortly."
    if interaction:
        return "Something went wrong while handling that command. Please try again shortly."
    return "Something went wrong while handling that command. Please try again shortly."


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    if isinstance(error, commands.CheckFailure) and (ctx.guild is None or getattr(bot, "is_shutdown", False)):
        # The DM guard and shutdown switch intentionally handle or silence these checks.
        return
    root_error = _unwrap_error(error)
    if isinstance(root_error, commands.CommandOnCooldown):
        logger.info(
            "Prefix command %s is cooling down for user %s (%.2fs remaining)",
            getattr(ctx.command, "qualified_name", "unknown"),
            getattr(ctx.author, "id", "unknown"),
            root_error.retry_after,
        )
        try:
            await ctx.send(_error_message(error), ephemeral=ctx.interaction is not None)
        except discord.HTTPException:
            logger.info("Could not send cooldown response for prefix command %s", getattr(ctx.command, "qualified_name", "unknown"))
        return
    if root_error.__traceback__ is not None:
        logger.error(
            "Prefix command %s failed: %r",
            getattr(ctx.command, "qualified_name", "unknown"),
            root_error,
            exc_info=(type(root_error), root_error, root_error.__traceback__),
        )
    else:
        logger.error("Prefix command %s failed: %r", getattr(ctx.command, "qualified_name", "unknown"), error)
    try:
        await ctx.send(_error_message(error), ephemeral=ctx.interaction is not None)
    except discord.HTTPException:
        logger.exception("Could not send error response for prefix command %s", getattr(ctx.command, "qualified_name", "unknown"))


@bot.tree.error
async def on_app_command_error(interaction, error):
    root_error = _unwrap_error(error)
    command_name = getattr(getattr(interaction, "command", None), "qualified_name", "unknown")
    if isinstance(root_error, discord.app_commands.CommandOnCooldown):
        logger.info("Slash command %s is cooling down for user %s (%.2fs remaining)", command_name, interaction.user.id, root_error.retry_after)
    else:
        logger.error("Slash command %s failed: %r", command_name, error, exc_info=(type(error), error, error.__traceback__))
    if isinstance(error, discord.app_commands.CheckFailure) and (
        interaction.response.is_done() or interaction.guild is None or getattr(bot, "is_shutdown", False)
    ):
        return
    if interaction.response.is_done() and getattr(bot, "is_shutdown", False):
        return
    try:
        message = _error_message(error, interaction=True)
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)
    except discord.HTTPException:
        logger.exception("Could not send slash-command error response")


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
    "cogs.daily_tasks",
    "cogs.member_records",
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
