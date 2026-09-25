import discord
from discord import app_commands
from discord.ext import commands

from utils.storage import add_warning, get_warnings, clear_warnings
from utils.config import get_guild_config
from utils.checks import is_mod
from utils.channels import get_channel
from utils.embeds import member_action_embed, action_embed


class Moderation(commands.Cog):
    """Core moderation commands: kick, mute, warn, clear, lock, slowmode.
    Works as both !command and /command (hybrid commands).
    Restricted to real Administrators or the server's configured admin role
    (see cogs/admin.py for setadminrole).

    Logging is split across two channels instead of one:
      - kick/mute/unmute        -> the "kickban" channel (auto: kicks-bans-mutes)
      - warn/clear/lock/slowmode -> the "modlog" channel (auto: mod-commands)
    Both are auto-detected by channel name, or can be pinned explicitly with
    /setchannel (see cogs/admin.py).
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def log_to(self, guild: discord.Guild, channel_type: str, embed: discord.Embed):
        channel = get_channel(guild, channel_type)
        if channel:
            try:
                await channel.send(embed=embed)
            except discord.HTTPException:
                pass

    # ---------- KICK ----------
    @commands.hybrid_command(name="kick", description="Kick a member from the server.")
    @app_commands.describe(member="The member to kick", reason="Why they're being kicked")
    @is_mod()
    async def kick(self, ctx: commands.Context, member: discord.Member, *, reason: str = None):
        if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            return await ctx.send("You can't kick someone with an equal or higher role than you.", ephemeral=True)
        if not ctx.guild.me.guild_permissions.kick_members:
            return await ctx.send("I don't have permission to kick members.", ephemeral=True)
        await member.kick(reason=reason)
        embed = member_action_embed("kick", "Member Kicked", member, ctx.author, reason, discord.Color.orange())
        await ctx.send(embed=embed)
        await self.log_to(ctx.guild, "kickban", embed)

    # ---------- MUTE (native timeout) ----------
    @commands.hybrid_command(name="mute", description="Timeout a member for a number of minutes.")
    @app_commands.describe(member="The member to mute", minutes="Duration in minutes", reason="Why they're being muted")
    @is_mod()
    async def mute(self, ctx: commands.Context, member: discord.Member, minutes: int, *, reason: str = None):
        if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            return await ctx.send("You can't mute someone with an equal or higher role than you.", ephemeral=True)
        if not ctx.guild.me.guild_permissions.moderate_members:
            return await ctx.send("I don't have permission to timeout members.", ephemeral=True)
        import datetime
        await member.timeout(datetime.timedelta(minutes=minutes), reason=reason)
        embed = member_action_embed(
            "mute", "Member Muted", member, ctx.author, reason, discord.Color.dark_orange(),
            extra_fields=[("Duration", f"{minutes} minutes", True)],
        )
        await ctx.send(embed=embed)
        await self.log_to(ctx.guild, "kickban", embed)

    @commands.hybrid_command(name="unmute", description="Remove a member's timeout.")
    @app_commands.describe(member="The member to unmute", reason="Why they're being unmuted")
    @is_mod()
    async def unmute(self, ctx: commands.Context, member: discord.Member, *, reason: str = None):
        if not ctx.guild.me.guild_permissions.moderate_members:
            return await ctx.send("I don't have permission to manage timeouts.", ephemeral=True)
        await member.timeout(None, reason=reason)
        embed = member_action_embed("unmute", "Member Unmuted", member, ctx.author, reason, discord.Color.green())
        await ctx.send(embed=embed)
        await self.log_to(ctx.guild, "kickban", embed)

    # ---------- WARN ----------
    @commands.hybrid_command(name="warn", description="Issue a warning to a member.")
    @app_commands.describe(member="The member to warn", reason="Why they're being warned")
    @is_mod()
    async def warn(self, ctx: commands.Context, member: discord.Member, *, reason: str = None):
        count = add_warning(ctx.guild.id, member.id, ctx.author.id, reason or "No reason provided")
        embed = member_action_embed(
            "warn", "Member Warned", member, ctx.author, reason, discord.Color.yellow(),
            extra_fields=[("Total warnings", str(count), True)],
        )
        await ctx.send(embed=embed)
        await self.log_to(ctx.guild, "modlog", embed)

    @commands.hybrid_command(name="warnings", description="List a member's warnings.")
    @app_commands.describe(member="The member to check")
    @is_mod()
    async def warnings(self, ctx: commands.Context, member: discord.Member):
        warns = get_warnings(ctx.guild.id, member.id)
        if not warns:
            return await ctx.send(f"{member.mention} has no warnings.", ephemeral=True)
        embed = discord.Embed(title=f"⚠️ Warnings for {member}", color=discord.Color.yellow())
        embed.set_thumbnail(url=member.display_avatar.url)
        for i, w in enumerate(warns, start=1):
            mod = ctx.guild.get_member(w["moderator_id"])
            embed.add_field(
                name=f"#{i} — {w.get('reason', 'No reason recorded')}",
                value=f"By {mod.mention if mod else w.get('moderator_id', 'unknown')}",
                inline=False,
            )
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="clearwarns", description="Clear all warnings for a member.")
    @app_commands.describe(member="The member whose warnings will be cleared")
    @is_mod()
    async def clearwarns(self, ctx: commands.Context, member: discord.Member):
        clear_warnings(ctx.guild.id, member.id)
        embed = member_action_embed("clearwarns", "Warnings Cleared", member, ctx.author, None, discord.Color.green())
        await ctx.send(f"Cleared all warnings for {member.mention}.")
        await self.log_to(ctx.guild, "modlog", embed)

    # ---------- CLEAR / PURGE ----------
    @commands.hybrid_command(name="clear", description="Bulk delete recent messages in this channel.")
    @app_commands.describe(amount="How many messages to delete (1-100)")
    @is_mod()
    async def clear(self, ctx: commands.Context, amount: int = 10):
        if amount < 1 or amount > 100:
            return await ctx.send("Please choose a number between 1 and 100.", ephemeral=True)
        if not ctx.guild.me.guild_permissions.manage_messages:
            return await ctx.send("I don't have permission to manage messages.", ephemeral=True)
        await ctx.defer(ephemeral=True)
        limit = amount + 1 if ctx.interaction is None else amount
        deleted = await ctx.channel.purge(limit=limit)
        await ctx.send(f"Deleted {len(deleted)} messages.", ephemeral=True)
        embed = action_embed(
            "clear", "Messages Cleared", color=discord.Color.blurple(), actor=ctx.author,
            fields=[
                ("Channel", ctx.channel.mention, True),
                ("Messages deleted", str(len(deleted)), True),
            ],
        )
        await self.log_to(ctx.guild, "modlog", embed)

    # ---------- LOCK / UNLOCK ----------
    @commands.hybrid_command(name="lock", description="Lock a channel so @everyone can't send messages.")
    @app_commands.describe(channel="Channel to lock (defaults to the current channel)", reason="Why it's being locked")
    @is_mod()
    async def lock(self, ctx: commands.Context, channel: discord.TextChannel = None, *, reason: str = None):
        channel = channel or ctx.channel
        if not ctx.guild.me.guild_permissions.manage_channels:
            return await ctx.send("I don't have permission to manage channels.", ephemeral=True)
        overwrite = channel.overwrites_for(ctx.guild.default_role)
        overwrite.send_messages = False
        await channel.set_permissions(ctx.guild.default_role, overwrite=overwrite, reason=reason)
        embed = action_embed(
            "lock", f"{channel.name} locked", color=discord.Color.red(), actor=ctx.author,
            fields=[("Reason", reason or "No reason provided", False)],
        )
        await ctx.send(embed=embed)
        await self.log_to(ctx.guild, "modlog", embed)

    @commands.hybrid_command(name="unlock", description="Unlock a previously locked channel.")
    @app_commands.describe(channel="Channel to unlock (defaults to the current channel)", reason="Why it's being unlocked")
    @is_mod()
    async def unlock(self, ctx: commands.Context, channel: discord.TextChannel = None, *, reason: str = None):
        channel = channel or ctx.channel
        if not ctx.guild.me.guild_permissions.manage_channels:
            return await ctx.send("I don't have permission to manage channels.", ephemeral=True)
        overwrite = channel.overwrites_for(ctx.guild.default_role)
        overwrite.send_messages = None  # reset to default rather than forcing True, respects other role overrides
        await channel.set_permissions(ctx.guild.default_role, overwrite=overwrite, reason=reason)
        embed = action_embed(
            "unlock", f"{channel.name} unlocked", color=discord.Color.green(), actor=ctx.author,
            fields=[("Reason", reason or "No reason provided", False)],
        )
        await ctx.send(embed=embed)
        await self.log_to(ctx.guild, "modlog", embed)

    # ---------- SLOWMODE ----------
    @commands.hybrid_command(name="slowmode", description="Set slowmode delay for a channel (0 turns it off).")
    @app_commands.describe(seconds="Delay in seconds (0-21600)", channel="Channel to apply this to (defaults to current)")
    @is_mod()
    async def slowmode(self, ctx: commands.Context, seconds: int, channel: discord.TextChannel = None):
        channel = channel or ctx.channel
        if seconds < 0 or seconds > 21600:  # Discord's own cap is 6 hours
            return await ctx.send("Slowmode must be between 0 and 21600 seconds (0 turns it off).", ephemeral=True)
        if not ctx.guild.me.guild_permissions.manage_channels:
            return await ctx.send("I don't have permission to manage channels.", ephemeral=True)
        await channel.edit(slowmode_delay=seconds)
        if seconds == 0:
            await ctx.send(f"Slowmode turned off in {channel.mention}.")
        else:
            await ctx.send(f"Slowmode set to {seconds}s in {channel.mention}.")
        embed = action_embed(
            "slowmode", "Slowmode changed", color=discord.Color.blurple(), actor=ctx.author,
            fields=[("Channel", channel.mention, True), ("Delay", f"{seconds}s", True)],
        )
        await self.log_to(ctx.guild, "modlog", embed)

    # ---------- Error handling ----------
    @kick.error
    @mute.error
    @unmute.error
    @warn.error
    @warnings.error
    @clearwarns.error
    @clear.error
    @lock.error
    @unlock.error
    @slowmode.error
    async def moderation_error(self, ctx: commands.Context, error):
        if isinstance(error, commands.CheckFailure):
            cfg = get_guild_config(ctx.guild.id)
            if cfg.get("admin_role_id") is None:
                await ctx.send(
                    "No admin role is set up yet, so only server Administrators can use this. "
                    "An Administrator can set one with `setadminrole`.",
                    ephemeral=True,
                )
            else:
                await ctx.send("You don't have permission to use this command.", ephemeral=True)
        elif isinstance(error, commands.BotMissingPermissions):
            await ctx.send("I don't have the required permissions to do that.", ephemeral=True)
        elif isinstance(error, (commands.MemberNotFound, commands.ChannelNotFound)):
            await ctx.send("Couldn't find that member or channel.", ephemeral=True)
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"Missing argument: `{error.param.name}`.", ephemeral=True)
        elif isinstance(error, commands.BadArgument):
            await ctx.send("That doesn't look right — check the arguments and try again.", ephemeral=True)
        else:
            await ctx.send(f"Something went wrong: {error}", ephemeral=True)
            raise error


async def setup(bot: commands.Bot):
    await bot.add_cog(Moderation(bot))
