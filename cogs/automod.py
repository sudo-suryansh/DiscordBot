import datetime
import re
import time

import discord
from discord import app_commands
from discord.ext import commands

from utils.config import get_guild_config, set_guild_value
from utils.channels import get_channel
from utils.checks import is_mod
from utils.embeds import action_embed

INVITE_RE = re.compile(r"(discord\.gg/|discord(?:app)?\.com/invite/)", re.IGNORECASE)


class AutoMod(commands.Cog):
    """Lightweight, configurable anti-spam.

    Deliberately lenient by default (this is a DSA study server, not a
    server that needs heavy-handed moderation) — it only steps in for
    obvious spam: message flooding, mass mentions, and invite links.
    Mods/admins and the bot itself are always exempt so staff activity is
    never accidentally flagged.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.message_log: dict[tuple[int, int], list[float]] = {}

    async def log_flag(self, message: discord.Message, reason: str, action: str):
        channel = get_channel(message.guild, "automod")
        if not channel:
            return
        content = message.content[:500] if message.content else "*(no text content)*"
        embed = action_embed(
            "automod", "Automod flag", color=discord.Color.red(), actor=message.author,
            fields=[
                ("Channel", message.channel.mention, True),
                ("Action taken", action, True),
                ("Reason", reason, False),
                ("Message", content, False),
            ],
            footer=f"User ID: {message.author.id}",
        )
        try:
            await channel.send(embed=embed)
        except discord.HTTPException:
            pass

    def is_exempt(self, message: discord.Message) -> bool:
        if message.author.bot or message.guild is None:
            return True
        perms = message.author.guild_permissions
        return perms.administrator or perms.manage_messages

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if getattr(self.bot, "is_shutdown", False):
            return
        if self.is_exempt(message):
            return

        cfg = get_guild_config(message.guild.id)
        if not cfg.get("automod_enabled", True):
            return

        # ---- Invite links ----
        if cfg.get("automod_block_invites", True) and INVITE_RE.search(message.content or ""):
            try:
                await message.delete()
            except discord.HTTPException:
                pass
            await self.log_flag(message, "Posted a Discord invite link", "Message deleted")
            try:
                await message.author.send(
                    f"Your message in **{message.guild.name}** was removed for containing an invite link."
                )
            except discord.Forbidden:
                pass
            return

        # ---- Mass mentions ----
        max_mentions = cfg.get("automod_max_mentions", 5)
        mention_count = len(message.mentions) + len(message.role_mentions)
        if mention_count > max_mentions:
            try:
                await message.delete()
            except discord.HTTPException:
                pass
            await self.log_flag(
                message,
                f"Mentioned {mention_count} users/roles (limit is {max_mentions})",
                "Message deleted",
            )
            return

        # ---- Message flooding ----
        key = (message.guild.id, message.author.id)
        now = time.time()
        window = cfg.get("automod_spam_seconds", 5)
        limit = cfg.get("automod_spam_count", 5)

        timestamps = self.message_log.setdefault(key, [])
        timestamps.append(now)
        self.message_log[key] = [t for t in timestamps if now - t <= window]

        if len(self.message_log[key]) > limit:
            self.message_log[key] = []  # reset so this doesn't re-fire on every message after
            mute_minutes = cfg.get("automod_mute_minutes", 5)
            action = "Flagged only (missing Timeout Members permission)"
            if message.guild.me.guild_permissions.moderate_members:
                try:
                    await message.author.timeout(
                        datetime.timedelta(minutes=mute_minutes), reason="Automod: message spam"
                    )
                    action = f"Timed out for {mute_minutes}m"
                except discord.HTTPException:
                    action = "Timeout failed — flagged only"
            await self.log_flag(
                message,
                f"Sent {limit + 1}+ messages within {window}s",
                action,
            )
            try:
                await message.channel.send(
                    f"{message.author.mention} slow down a bit — that's a lot of messages in a short time.",
                    delete_after=8,
                )
            except discord.HTTPException:
                pass

    # ---------- Config commands ----------
    @commands.hybrid_group(name="automod", description="View current automod settings.", invoke_without_command=True)
    @is_mod()
    async def automod(self, ctx: commands.Context):
        cfg = get_guild_config(ctx.guild.id)
        embed = discord.Embed(title="Automod settings", color=discord.Color.blurple())
        embed.add_field(name="Enabled", value=str(cfg.get("automod_enabled", True)))
        embed.add_field(
            name="Spam threshold",
            value=f"{cfg.get('automod_spam_count', 5)} msgs / {cfg.get('automod_spam_seconds', 5)}s",
        )
        embed.add_field(name="Timeout on spam", value=f"{cfg.get('automod_mute_minutes', 5)}m")
        embed.add_field(name="Max mentions/message", value=str(cfg.get("automod_max_mentions", 5)))
        embed.add_field(name="Block invite links", value=str(cfg.get("automod_block_invites", True)))
        embed.set_footer(text="Change these with /automod toggle, spamlimit, mentionlimit, mutetime, invites")
        await ctx.send(embed=embed)

    @automod.command(name="toggle", description="Turn automod fully on or off.")
    @is_mod()
    async def automod_toggle(self, ctx: commands.Context):
        cfg = get_guild_config(ctx.guild.id)
        new_val = not cfg.get("automod_enabled", True)
        set_guild_value(ctx.guild.id, "automod_enabled", new_val)
        await ctx.send(f"Automod is now **{'ON' if new_val else 'OFF'}**.")

    @automod.command(name="spamlimit", description="Set the message-flood threshold.")
    @app_commands.describe(count="Messages allowed", seconds="...within this many seconds")
    @is_mod()
    async def automod_spamlimit(self, ctx: commands.Context, count: int, seconds: int):
        if not 1 <= count <= 100 or not 1 <= seconds <= 3600:
            return await ctx.send("Use 1–100 messages and a 1–3600 second window.", ephemeral=True)
        set_guild_value(ctx.guild.id, "automod_spam_count", count)
        set_guild_value(ctx.guild.id, "automod_spam_seconds", seconds)
        await ctx.send(f"Spam threshold set to {count} messages per {seconds}s.")

    @automod.command(name="mentionlimit", description="Set the max mentions allowed in one message.")
    @is_mod()
    async def automod_mentionlimit(self, ctx: commands.Context, max_mentions: int):
        if not 0 <= max_mentions <= 100:
            return await ctx.send("The mention limit must be between 0 and 100.", ephemeral=True)
        set_guild_value(ctx.guild.id, "automod_max_mentions", max_mentions)
        await ctx.send(f"Max mentions per message set to {max_mentions}.")

    @automod.command(name="mutetime", description="Set how long spammers get timed out for.")
    @is_mod()
    async def automod_mutetime(self, ctx: commands.Context, minutes: int):
        if not 1 <= minutes <= 40320:
            return await ctx.send("Timeout duration must be between 1 and 40320 minutes (28 days).", ephemeral=True)
        set_guild_value(ctx.guild.id, "automod_mute_minutes", minutes)
        await ctx.send(f"Automod timeout duration set to {minutes} minutes.")

    @automod.command(name="invites", description="Turn invite-link blocking on or off.")
    @is_mod()
    async def automod_invites(self, ctx: commands.Context, enabled: bool):
        set_guild_value(ctx.guild.id, "automod_block_invites", enabled)
        await ctx.send(f"Invite link blocking is now **{'ON' if enabled else 'OFF'}**.")

    @automod.error
    @automod_toggle.error
    @automod_spamlimit.error
    @automod_mentionlimit.error
    @automod_mutetime.error
    @automod_invites.error
    async def automod_error(self, ctx: commands.Context, error):
        if isinstance(error, commands.CheckFailure):
            await ctx.send("You don't have permission to change automod settings.", ephemeral=True)
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"Missing argument: `{error.param.name}`.", ephemeral=True)
        else:
            await ctx.send(f"Something went wrong: {error}", ephemeral=True)
            raise error


async def setup(bot: commands.Bot):
    await bot.add_cog(AutoMod(bot))
