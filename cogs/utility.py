import datetime
import discord
from discord import app_commands
from discord.ext import commands

from utils.motivation import generate_welcome_dm
from utils.channels import get_channel


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
            embed = discord.Embed(
                title="📥 Member joined",
                description=f"{member.mention} ({member})",
                color=discord.Color.green(),
                timestamp=datetime.datetime.utcnow(),
            )
            embed.add_field(name="Account created", value=member.created_at.strftime("%b %d, %Y"))
            embed.add_field(name="Member count", value=str(member.guild.member_count))
            try:
                await log_channel.send(embed=embed)
            except discord.HTTPException:
                pass

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        # Leave messages no longer go to #welcome — only the logs channel.
        log_channel = get_channel(member.guild, "logs")
        if log_channel:
            embed = discord.Embed(
                title="📤 Member left",
                description=f"{member} ({member.id})",
                color=discord.Color.red(),
                timestamp=datetime.datetime.utcnow(),
            )
            joined = member.joined_at.strftime("%b %d, %Y") if member.joined_at else "Unknown"
            embed.add_field(name="Had joined on", value=joined)
            embed.add_field(name="Member count", value=str(member.guild.member_count))
            try:
                await log_channel.send(embed=embed)
            except discord.HTTPException:
                pass

    @commands.hybrid_command(name="ping", description="Check the bot's latency.")
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
    @app_commands.describe(member="The member to look up (defaults to you)")
    async def userinfo(self, ctx: commands.Context, member: discord.Member = None):
        member = member or ctx.author
        embed = discord.Embed(title=str(member), color=member.color)
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="ID", value=member.id)
        embed.add_field(name="Joined server", value=member.joined_at.strftime("%b %d, %Y") if member.joined_at else "Unknown")
        embed.add_field(name="Account created", value=member.created_at.strftime("%b %d, %Y"))
        roles = [r.mention for r in member.roles if r.name != "@everyone"]
        embed.add_field(name="Roles", value=", ".join(roles) if roles else "None", inline=False)
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Utility(bot))
