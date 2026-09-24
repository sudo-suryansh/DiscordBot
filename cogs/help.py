import discord
from discord import app_commands
from discord.ext import commands


class Help(commands.Cog):
    """Custom help command. Reads the bot's live command list every time it
    runs, so a newly added command shows up automatically — nothing to
    maintain by hand. Visibility per command is decided by actually running
    that command's own checks (permissions, is_mod, etc.) against the
    person asking, so a regular member won't see mod-only commands like
    kick/mute, but a mod or admin will."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="help", description="DM yourself the list of commands you have access to.")
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def help(self, ctx: commands.Context):
        if ctx.guild is None:
            embed = discord.Embed(
                title="Commands available in DMs",
                description=(
                    "**Light commands** · available every 20 seconds\n"
                    "`ping` · check latency\n"
                    "`userinfo [@user]` · look up an account\n"
                    "`version` · check the bot version\n\n"
                    "**Problem picks** · available every 30 seconds\n"
                    "`leet <easy|mid|hard> [topic]`\n"
                    "`another [difficulty] [topic]` · reuse your previous choice\n\n"
                    "You can still put `!` before a command. DM commands are paused for an hour if more than 10 messages arrive within a minute."
                ),
                color=discord.Color.blurple(),
            )
            return await ctx.send(embed=embed)

        # Group visible commands by their cog, in whatever order cogs were loaded
        sections: dict[str, list[commands.Command]] = {}

        for cmd in self.bot.commands:
            if cmd.hidden:
                continue
            try:
                allowed = await cmd.can_run(ctx)
            except commands.CommandError:
                allowed = False
            if not allowed:
                continue

            cog_name = cmd.cog.qualified_name if cmd.cog else "Other"
            sections.setdefault(cog_name, []).append(cmd)

        embed = discord.Embed(
            title="Commands you can use",
            description="Prefix `!` also works for every command below — pick whichever you prefer.",
            color=discord.Color.blurple(),
        )
        for cog_name, cmds in sorted(sections.items()):
            cmds.sort(key=lambda c: c.name)
            lines = [f"**/{c.name}** — {c.description or 'No description.'}" for c in cmds]
            embed.add_field(name=cog_name, value="\n".join(lines), inline=False)

        try:
            await ctx.author.send(embed=embed)
            if ctx.guild is not None:
                await ctx.send("Sent you a DM with your available commands.", ephemeral=True)
        except discord.Forbidden:
            # Can't DM them — fall back to sending it where they asked, so
            # they're not left with nothing (visible to others in-channel
            # only for prefix invocation; slash replies stay ephemeral).
            await ctx.send(
                "I couldn't DM you (check your Privacy Settings), so here it is instead:",
                embed=embed,
                ephemeral=True,
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(Help(bot))
