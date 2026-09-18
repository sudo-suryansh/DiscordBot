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
from discord.ext import commands

OWNER_ID_ENV = os.getenv("OWNER_ID")  # optional — set this in .env for a hard-coded owner check


class Power(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.bot.is_shutdown = False  # shared flag other cogs/events can also check if needed
        self.bot.add_check(self.global_shutdown_check)

    async def is_owner_user(self, user: discord.abc.User) -> bool:
        if OWNER_ID_ENV:
            try:
                return user.id == int(OWNER_ID_ENV)
            except ValueError:
                pass  # fall through to Discord's own check if OWNER_ID is malformed
        return await self.bot.is_owner(user)

    async def global_shutdown_check(self, ctx: commands.Context) -> bool:
        """Registered as a global check — runs before every command.
        Returning False silently blocks the command (no error message),
        so the bot appears completely unresponsive to non-owners while shut down."""
        if not self.bot.is_shutdown:
            return True
        return await self.is_owner_user(ctx.author)

    @commands.hybrid_command(name="shutdown", description="Owner only: make the bot stop responding to everyone.")
    async def shutdown(self, ctx: commands.Context):
        if not await self.is_owner_user(ctx.author):
            return  # stay silent — don't reveal this command exists to non-owners
        if self.bot.is_shutdown:
            return await ctx.send("Already shut down.", ephemeral=True)
        self.bot.is_shutdown = True
        await ctx.send("🔴 Shutting down — I'll ignore everyone except you until `!start`.")

    @commands.hybrid_command(name="start", description="Owner only: bring the bot back to normal.")
    async def start(self, ctx: commands.Context):
        if not await self.is_owner_user(ctx.author):
            return
        if not self.bot.is_shutdown:
            return await ctx.send("Already running normally.", ephemeral=True)
        self.bot.is_shutdown = False
        await ctx.send("🟢 Back online — responding to everyone again.")


async def setup(bot: commands.Bot):
    await bot.add_cog(Power(bot))