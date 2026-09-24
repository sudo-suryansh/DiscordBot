"""
Owner-only kill switch.

!shutdown — only works if sent by the bot owner (checked against OWNER_ID
            in .env, falling back to Discord's own application-owner check
            if OWNER_ID isn't set). Once triggered, the bot ignores every
            command and event from everyone except the owner.
!start     — owner-only, undoes the shutdown. Everyone else is ignored again
            as normal (i.e. the bot goes back to working normally for all).

How the block works: a global check is registered via bot.add_check, so it
runs before every single command, for every user, including hybrid/slash
commands. Regular non-command events (on_member_join, etc.) are NOT touched
by this — this only gates commands. Say so if you want events silenced too.
"""

import os
import discord
from discord import app_commands
from discord.ext import commands

from utils.channels import get_channel

OWNER_ID_ENV = os.getenv("OWNER_ID")  # optional — set this in .env for a hard-coded owner check


class Power(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.bot.is_shutdown = False  # shared flag other cogs/events can also check if needed
        self.bot.is_shutting_down = False
        self.bot.shutdown_reason = None
        self.bot.add_check(self.global_shutdown_check)

    async def is_owner_user(self, user: discord.abc.User) -> bool:
        if OWNER_ID_ENV:
            try:
                return user.id == int(OWNER_ID_ENV)
            except ValueError:
                pass  # fall through to Discord's own check if OWNER_ID is malformed
        return await self.bot.is_owner(user)

    async def global_shutdown_check(self, ctx: commands.Context) -> bool:
        """While shut down, only the owner may run the recovery command."""
        if not getattr(self.bot, "is_shutdown", False):
            return True
        command_name = ctx.command.qualified_name.split(" ", 1)[0] if ctx.command else ""
        return (
            command_name == "start"
            and not getattr(self.bot, "is_shutting_down", False)
            and await self.is_owner_user(ctx.author)
        )

    @commands.hybrid_command(name="shutdown", description="Owner only, in DMs: pause the bot and notify every server.")
    @app_commands.describe(reason="Optional reason shown in each server's updates channel")
    @app_commands.allowed_contexts(guilds=False, dms=True, private_channels=False)
    async def shutdown(self, ctx: commands.Context, *, reason: str = None):
        if not await self.is_owner_user(ctx.author):
            return
        if ctx.guild is not None:
            return await ctx.send("Use `!shutdown [reason]` in a direct message to the bot.")
        if self.bot.is_shutdown:
            return await ctx.send("Already shut down.", ephemeral=True)

        self.bot.is_shutdown = True
        self.bot.is_shutting_down = True

        notice = discord.Embed(
            title="⛔ Bot is shutting down",
            description=f"**Reason**\n{reason or 'No reason provided.'}",
            color=discord.Color.red(),
            timestamp=discord.utils.utcnow(),
        )
        notice.set_footer(text="The bot is paused by its owner.")
        self.bot.shutdown_reason = reason or "No reason provided."
        results = []
        for guild in self.bot.guilds:
            channel = get_channel(guild, "updates")
            if channel is None:
                results.append(f"{guild.name}: no updates channel configured")
                continue
            try:
                await channel.send(embed=notice, allowed_mentions=discord.AllowedMentions.none())
                results.append(f"{guild.name}: notified in #{channel.name}")
            except discord.HTTPException:
                results.append(f"{guild.name}: could not post in #{channel.name}")

        self.bot.is_shutting_down = False
        summary = "🔴 The bot is paused. Only your `!start` command will be accepted until it is resumed."
        if results:
            summary += "\n\n" + "\n".join(results)
        await ctx.send(summary)

    @commands.hybrid_command(name="start", description="Owner only: bring the bot back to normal.")
    @app_commands.allowed_contexts(guilds=False, dms=True, private_channels=False)
    async def start(self, ctx: commands.Context):
        if not await self.is_owner_user(ctx.author):
            return
        if getattr(self.bot, "is_shutting_down", False):
            return await ctx.send("Shutdown notifications are still being sent. Try `!start` again in a moment.")
        if not self.bot.is_shutdown:
            return await ctx.send("Already running normally.", ephemeral=True)
        self.bot.is_shutting_down = True

        reason = getattr(self.bot, "shutdown_reason", None)
        description = "The bot has resumed normal service."
        if reason:
            description += f"\n\n**Previous shutdown reason**\n{reason}"
        notice = discord.Embed(
            title="✅ Bot is back online",
            description=description,
            color=discord.Color.green(),
            timestamp=discord.utils.utcnow(),
        )
        notice.set_footer(text="Normal bot commands and activity have resumed.")

        results = []
        for guild in self.bot.guilds:
            channel = get_channel(guild, "updates")
            if channel is None:
                results.append(f"{guild.name}: no updates channel configured")
                continue
            try:
                await channel.send(embed=notice, allowed_mentions=discord.AllowedMentions.none())
                results.append(f"{guild.name}: notified in #{channel.name}")
            except discord.HTTPException:
                results.append(f"{guild.name}: could not post in #{channel.name}")

        self.bot.is_shutdown = False
        self.bot.is_shutting_down = False
        self.bot.shutdown_reason = None
        summary = "🟢 The bot is back online."
        if results:
            summary += "\n\n" + "\n".join(results)
        await ctx.send(summary)

    @commands.command(name="reset", help="Owner only: clear DM limits for yourself or a mentioned user.")
    async def reset(self, ctx: commands.Context, user: discord.User = None):
        if ctx.guild is not None:
            return await ctx.send("Use `!reset` in your bot DM. It only clears your own DM cooldown and lockout.")
        if not await self.is_owner_user(ctx.author):
            return await ctx.send("Only the bot owner can reset their DM lockout.")
        guard = getattr(self.bot, "dm_command_guard", None)
        if guard is None:
            return await ctx.send("The DM guard is not loaded, so there is no DM lockout to reset.")
        target = user or ctx.author
        guard.reset_user(target.id)
        if target.id == ctx.author.id:
            await ctx.send("Your DM cooldown and lockout are cleared. Other users' limits are unchanged.")
        else:
            await ctx.send(f"Cleared the DM cooldown and lockout for {target.mention}. No one else's limits changed.")


async def setup(bot: commands.Bot):
    await bot.add_cog(Power(bot))
