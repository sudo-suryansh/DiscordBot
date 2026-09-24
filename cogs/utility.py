import discord
from discord import app_commands
from discord.ext import commands

from utils.motivation import generate_welcome_dm
from utils.channels import get_channel
from utils.embeds import action_embed


class Utility(commands.Cog):
    """Non-moderation commands, plus join/leave events (events aren't commands,
    so the ! vs / conversion doesn't touch them).

    Joins: a friendly public message + DM go to the welcome channel, same as
    before. Leaves no longer post in #welcome — they, along with a join audit
    entry, go to the logs channel instead."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if getattr(self.bot, "is_shutdown", False):
            return
        welcome_channel = get_channel(member.guild, "welcome")
        if welcome_channel:
            await welcome_channel.send(
                f"Welcome to the server, {member.mention}! 🎉 "
                f"Check the rules and intro yourself. Happy grinding on DSA!"
            )

        # Best-effort personalized DM — many users have DMs closed to
        # non-friends, so this fails silently rather than erroring out
        # or spamming the public channel about it.
        try:
            dm_text = generate_welcome_dm(member.display_name)
            await member.send(dm_text)
        except discord.Forbidden:
            pass  # user has DMs disabled for this server — nothing we can do
        except discord.HTTPException:
            pass  # transient Discord error — not worth failing the join event over

        log_channel = get_channel(member.guild, "logs")
        if log_channel:
            embed = action_embed(
                "join", "Member joined", color=discord.Color.green(), actor=member,
                fields=[
                    ("Account created", member.created_at.strftime("%b %d, %Y"), True),
                    ("Member count", str(member.guild.member_count), True),
                ],
                footer=f"User ID: {member.id}",
            )
            try:
                await log_channel.send(embed=embed)
            except discord.HTTPException:
                pass

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        if getattr(self.bot, "is_shutdown", False):
            return
        # Leave messages no longer go to #welcome — only the logs channel.
        log_channel = get_channel(member.guild, "logs")
        if log_channel:
            joined = member.joined_at.strftime("%b %d, %Y") if member.joined_at else "Unknown"
            embed = action_embed(
                "leave", "Member left", color=discord.Color.red(), actor=member,
                fields=[
                    ("Had joined on", joined, True),
                    ("Member count", str(member.guild.member_count), True),
                ],
                footer=f"User ID: {member.id}",
            )
            try:
                await log_channel.send(embed=embed)
            except discord.HTTPException:
                pass

    @commands.hybrid_command(name="ping", description="Check the bot's latency.")
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def ping(self, ctx: commands.Context):
        await ctx.send(f"Pong! `{round(self.bot.latency * 1000)}ms`")

    @commands.hybrid_command(name="serverinfo", description="Show information about this server.")
    async def serverinfo(self, ctx: commands.Context):
        guild = ctx.guild
        embed = discord.Embed(title=guild.name, color=discord.Color.blurple())
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        embed.add_field(name="Owner", value=str(guild.owner))
        embed.add_field(name="Members", value=guild.member_count)
        embed.add_field(name="Created", value=guild.created_at.strftime("%b %d, %Y"))
        embed.add_field(name="Channels", value=len(guild.channels))
        embed.add_field(name="Roles", value=len(guild.roles))
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="userinfo", description="Show information about a member.")
    @app_commands.describe(member="The user to look up (defaults to you)")
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def userinfo(self, ctx: commands.Context, member: discord.User = None):
        member = member or ctx.author
        guild_member = ctx.guild.get_member(member.id) if ctx.guild else None
        embed = discord.Embed(
            title=str(member),
            color=guild_member.color if guild_member else discord.Color.blurple(),
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="ID", value=member.id)
        embed.add_field(name="Account created", value=member.created_at.strftime("%b %d, %Y"))
        if ctx.guild:
            embed.add_field(
                name="Joined server",
                value=guild_member.joined_at.strftime("%b %d, %Y") if guild_member and guild_member.joined_at else "Not a member of this server",
            )
            roles = [r.mention for r in guild_member.roles if r.name != "@everyone"] if guild_member else []
            embed.add_field(name="Roles", value=", ".join(roles) if roles else "None", inline=False)
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Utility(bot))
