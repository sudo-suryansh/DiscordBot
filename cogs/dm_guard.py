"""Rate-limit bot commands in DMs and temporarily ignore DM spam."""

import os
import time
from collections import defaultdict, deque

import discord
from discord.ext import commands


DM_COMMANDS = {
    "another", "checkupdate", "help", "leet", "ping", "reset", "shutdown", "start",
    "synccommands", "userinfo", "version",
}
HEAVY_COMMANDS = {"another", "checkupdate", "leet", "synccommands"}
LIGHT_GAP_SECONDS = 20
HEAVY_GAP_SECONDS = 30
SPAM_WINDOW_SECONDS = 60
SPAM_MESSAGE_LIMIT = 10
DM_MUTE_SECONDS = 60 * 60


class DMGuard(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.last_command: dict[int, float] = {}
        self.recent_activity: dict[int, deque[float]] = defaultdict(deque)
        self.blocked_until: dict[int, float] = {}
        bot.dm_command_guard = self
        bot.add_check(self.dm_check)

    def cog_unload(self):
        self.bot.remove_check(self.dm_check)
        if getattr(self.bot, "dm_command_guard", None) is self:
            del self.bot.dm_command_guard

    def reset_user(self, user_id: int) -> None:
        """Clear only this user's DM cooldown, activity window, and lockout."""
        self.blocked_until.pop(user_id, None)
        self.recent_activity.pop(user_id, None)
        self.last_command.pop(user_id, None)

    async def is_owner_user(self, user: discord.abc.User) -> bool:
        owner_id = os.getenv("OWNER_ID")
        if owner_id:
            try:
                return user.id == int(owner_id)
            except ValueError:
                pass
        return await self.bot.is_owner(user)

    def _is_blocked(self, user_id: int, now: float) -> bool:
        until = self.blocked_until.get(user_id)
        if until is None:
            return False
        if now < until:
            return True
        self.blocked_until.pop(user_id, None)
        self.recent_activity.pop(user_id, None)
        self.last_command.pop(user_id, None)
        return False

    async def _record_activity(self, user_id: int, now: float, notify) -> bool:
        events = self.recent_activity[user_id]
        while events and now - events[0] > SPAM_WINDOW_SECONDS:
            events.popleft()
        events.append(now)
        if len(events) <= SPAM_MESSAGE_LIMIT:
            return False

        self.blocked_until[user_id] = now + DM_MUTE_SECONDS
        self.recent_activity.pop(user_id, None)
        try:
            await notify(
                "You've sent too many messages or commands in a short time. "
                "I'll ignore your DMs for one hour to prevent spam. "
                "This won't affect your use of the bot in servers."
            )
        except discord.HTTPException:
            pass
        return True

    async def observe_dm_message(self, message: discord.Message) -> bool:
        """Return True when the message should be ignored before command parsing."""
        if message.author.bot or message.guild is not None:
            return False
        first_word = message.content.strip().casefold().split(maxsplit=1)
        if (
            getattr(self.bot, "is_shutdown", False)
            and first_word
            and first_word[0] == "!start"
            and await self.is_owner_user(message.author)
        ):
            return False
        if first_word and first_word[0] == "!reset" and await self.is_owner_user(message.author):
            return False
        now = time.monotonic()
        if self._is_blocked(message.author.id, now):
            return True
        return await self._record_activity(
            message.author.id,
            now,
            lambda text: message.channel.send(text),
        )

    async def dm_check(self, ctx: commands.Context) -> bool:
        if ctx.guild is not None:
            return True

        now = time.monotonic()
        user_id = ctx.author.id
        command_name = ctx.command.qualified_name.split(" ", 1)[0].lower() if ctx.command else ""
        if command_name == "start" and getattr(self.bot, "is_shutdown", False) and await self.is_owner_user(ctx.author):
            self.reset_user(user_id)
            return True
        if command_name == "reset" and await self.is_owner_user(ctx.author):
            return True
        if self._is_blocked(user_id, now):
            return False

        # Prefix messages are counted by observe_dm_message. Slash interactions
        # do not pass through on_message, so count them here.
        if ctx.interaction is not None and await self._record_activity(
            user_id, now, lambda text: ctx.send(text)
        ):
            return False

        if command_name not in DM_COMMANDS:
            await ctx.send("That command needs a server. In DMs, try `!help` for the available commands.")
            return False

        gap = HEAVY_GAP_SECONDS if command_name in HEAVY_COMMANDS else LIGHT_GAP_SECONDS
        previous = self.last_command.get(user_id)
        if previous:
            elapsed = now - previous
            remaining = gap - elapsed
            if remaining > 0:
                await ctx.send(f"Please wait **{int(remaining + 0.999)}s** before using another bot command in DMs.")
                return False

        self.last_command[user_id] = now
        return True


async def setup(bot: commands.Bot):
    await bot.add_cog(DMGuard(bot))
