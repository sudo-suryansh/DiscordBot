import os
import discord
from discord import app_commands
from discord.ext import commands

from utils.config import get_guild_config, set_guild_value
from utils.channels import get_channel, CONFIG_KEY_MAP
from utils.embeds import action_embed

DEV_GUILD_ID = os.getenv("DEV_GUILD_ID")

CHANNEL_TYPE_CHOICES = [
    app_commands.Choice(name=t, value=t) for t in CONFIG_KEY_MAP
]


class AdminConfig(commands.Cog):
    """Server configuration commands. Locked to real Discord
    'Administrator' permission only — never the configurable admin role —
    so nobody can use the bot to grant themselves more power than they
    already have."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def log_config_change(self, guild: discord.Guild, title: str, description: str, actor=None):
        channel = get_channel(guild, "modlog")
        if channel:
            embed = action_embed("config", title, description, color=discord.Color.blurple(), actor=actor)
            try:
                await channel.send(embed=embed)
            except discord.HTTPException:
                pass

    # ---------- ADMIN ROLE ----------
    @commands.hybrid_command(name="setadminrole", description="Grant a role Administrator permission and mod-command access.")
    @app_commands.describe(role="The role to promote")
    @commands.has_permissions(administrator=True)
    async def setadminrole(self, ctx: commands.Context, role: discord.Role):
        if not ctx.guild.me.guild_permissions.manage_roles:
            return await ctx.send("I need the 'Manage Roles' permission to do that.", ephemeral=True)

        if role.position >= ctx.guild.me.top_role.position:
            return await ctx.send(
                f"I can't grant permissions to {role.mention} — it's positioned above (or equal to) "
                f"my own role in the role list. Move my bot role above it in Server Settings > Roles, "
                f"then try again.",
                ephemeral=True,
            )

        new_permissions = role.permissions
        new_permissions.administrator = True
        await role.edit(permissions=new_permissions, reason=f"Set as admin role by {ctx.author}")

        set_guild_value(ctx.guild.id, "admin_role_id", role.id)
        await ctx.send(
            f"✅ {role.mention} now has real server Administrator permission, "
            f"and can use all mod commands (kick, mute, warn, clear).\n"
            f"⚠️ This means anyone with that role can do anything in the server — "
            f"assign it carefully."
        )
        await self.log_config_change(
            ctx.guild, "Admin role changed",
            f"Granted real Administrator permission to {role.mention}.",
            actor=ctx.author,
        )

    @commands.hybrid_command(name="revokeadminrole", description="Remove Administrator permission from the current admin role.")
    @commands.has_permissions(administrator=True)
    async def revokeadminrole(self, ctx: commands.Context):
        if not ctx.guild.me.guild_permissions.manage_roles:
            return await ctx.send("I need the 'Manage Roles' permission to do that.", ephemeral=True)

        cfg = get_guild_config(ctx.guild.id)
        role_id = cfg.get("admin_role_id")
        if role_id is None:
            return await ctx.send("No admin role is currently set.", ephemeral=True)
        role = ctx.guild.get_role(role_id)
        if role:
            new_permissions = role.permissions
            new_permissions.administrator = False
            await role.edit(permissions=new_permissions, reason=f"Admin role revoked by {ctx.author}")
        set_guild_value(ctx.guild.id, "admin_role_id", None)
        await ctx.send(f"Removed Administrator permission from {role.mention if role else 'that role'} and cleared the admin role setting.")
        await self.log_config_change(
            ctx.guild, "Admin role changed",
            f"Revoked Administrator permission from {role.mention if role else '(deleted role)'}.",
            actor=ctx.author,
        )

    @commands.hybrid_command(name="adminrole", description="Show the server's current admin role.")
    async def adminrole(self, ctx: commands.Context):
        cfg = get_guild_config(ctx.guild.id)
        role_id = cfg.get("admin_role_id")
        if role_id is None:
            return await ctx.send("No admin role set yet. An Administrator can set one with `setadminrole`.", ephemeral=True)
        role = ctx.guild.get_role(role_id)
        await ctx.send(f"Current admin role: {role.mention if role else '(role no longer exists)'}")

    # ---------- WELCOME CHANNEL ----------
    @commands.hybrid_command(name="setwelcome", description="Set the channel used for join messages.")
    @app_commands.describe(channel="The channel to post welcome messages in")
    @commands.has_permissions(administrator=True)
    async def setwelcome(self, ctx: commands.Context, channel: discord.TextChannel):
        set_guild_value(ctx.guild.id, "welcome_channel_id", channel.id)
        await ctx.send(f"Welcome messages will now be posted in {channel.mention}.")

    @commands.hybrid_command(name="welcomechannel", description="Show the server's current welcome channel.")
    async def welcomechannel(self, ctx: commands.Context):
        channel = get_channel(ctx.guild, "welcome")
        if channel is None:
            return await ctx.send(
                "No welcome channel found or set yet. An Administrator can set one explicitly with `setwelcome`.",
                ephemeral=True,
            )
        await ctx.send(f"Current welcome channel: {channel.mention}")

    # ---------- GENERAL CHANNEL ROUTING ----------
    @commands.hybrid_command(
        name="setchannel",
        description="Point a bot feature (logs, modlog, kickban, automod, updates, welcome) at a specific channel.",
    )
    @app_commands.describe(channel_type="Which feature to route", channel="The channel to send it to")
    @app_commands.choices(channel_type=CHANNEL_TYPE_CHOICES)
    @commands.has_permissions(administrator=True)
    async def setchannel(self, ctx: commands.Context, channel_type: str, channel: discord.TextChannel):
        if channel_type not in CONFIG_KEY_MAP:
            return await ctx.send(
                f"Unknown channel type. Choose from: {', '.join(CONFIG_KEY_MAP)}", ephemeral=True
            )
        set_guild_value(ctx.guild.id, CONFIG_KEY_MAP[channel_type], channel.id)
        await ctx.send(f"`{channel_type}` will now use {channel.mention}.")

    @commands.hybrid_command(name="channels", description="Show which channel each bot feature is currently using.")
    async def channels(self, ctx: commands.Context):
        embed = discord.Embed(
            title="Channel routing",
            description="Auto-detected by channel name unless set explicitly with `/setchannel`.",
            color=discord.Color.blurple(),
        )
        labels = {
            "welcome": "👋 Welcome (joins)",
            "logs": "📜 Logs (leaves, audit trail)",
            "modlog": "🛠️ Mod log (warn/clear/lock/slowmode)",
            "kickban": "🔨 Kick/ban/mute log",
            "automod": "🚨 Automod flags",
            "updates": "🔧 Bot update announcements",
        }
        for ctype, label in labels.items():
            channel = get_channel(ctx.guild, ctype)
            embed.add_field(
                name=label,
                value=channel.mention if channel else "*(not found — set with /setchannel)*",
                inline=False,
            )
        await ctx.send(embed=embed)

    # ---------- SYNC (push new/changed commands to Discord without restarting) ----------
    @commands.hybrid_command(
        name="synccommands",
        description="Re-sync slash commands with Discord (run this after code adds/changes a command).",
    )
    @commands.is_owner()
    async def synccommands(self, ctx: commands.Context):
        await ctx.defer(ephemeral=True)
        if DEV_GUILD_ID:
            guild = discord.Object(id=int(DEV_GUILD_ID))
            self.bot.tree.copy_global_to(guild=guild)
            synced = await self.bot.tree.sync(guild=guild)
            await ctx.send(f"Synced {len(synced)} command(s) to the dev guild (instant).", ephemeral=True)
        else:
            synced = await self.bot.tree.sync()
            await ctx.send(f"Synced {len(synced)} command(s) globally (can take up to ~1 hour to show everywhere).", ephemeral=True)

    # ---------- Error handling ----------
    @setadminrole.error
    @revokeadminrole.error
    @setwelcome.error
    @setchannel.error
    async def admin_config_error(self, ctx: commands.Context, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("Only server Administrators can change this setting.", ephemeral=True)
        elif isinstance(error, commands.BotMissingPermissions):
            await ctx.send("I need the 'Manage Roles' permission to do that.", ephemeral=True)
        elif isinstance(error, (commands.RoleNotFound, commands.ChannelNotFound)):
            await ctx.send("Couldn't find that role or channel.", ephemeral=True)
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"Missing argument: `{error.param.name}`.", ephemeral=True)
        else:
            await ctx.send(f"Something went wrong: {error}", ephemeral=True)
            raise error

    @synccommands.error
    async def sync_error(self, ctx: commands.Context, error):
        if isinstance(error, commands.NotOwner):
            await ctx.send("Only the bot's owner can run this.", ephemeral=True)
        else:
            await ctx.send(f"Something went wrong: {error}", ephemeral=True)
            raise error


async def setup(bot: commands.Bot):
    await bot.add_cog(AdminConfig(bot))
