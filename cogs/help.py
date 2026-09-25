"""Interactive Dot introduction and personalized command help."""

import asyncio
import logging

import discord
from discord import app_commands
from discord.ext import commands

from utils.config import get_guild_config
from utils.intro_receipts import mark_received, received_users

logger = logging.getLogger(__name__)

INTRO_PAGES = {
    "welcome": (
        "👋 Welcome to Dot!",
        "Dot was created by **Suryansh** to make this server a more helpful place to learn, practice, "
        "and stay consistent. Ask questions naturally with `!dot` or `/dot`, or use the buttons below "
        "to explore.\n\n"
        "✨ Dot can explain coding and DSA, help you use LeetCode practice tools, keep track of task and "
        "solution progress, and answer questions about this server. Some server-management actions are "
        "available to Administrators only.\n\n"
        "📬 Use `!help` any time to get this intro and your command list again."
    ),
    "ai": (
        "🤖 Ask Dot",
        "• `!dot <question>` — ask about programming, DSA, concepts, or this server. Dot understands "
        "ordinary wording and follow-ups.\n"
        "• `!dot <question> !dm` — get Dot’s answer in your own DMs.\n"
        "• `!dot what is today's task?` — check the task that is actually scheduled.\n"
        "• `!review <code>` — get a code review for bugs, complexity, and improvements.\n\n"
        "Dot only performs supported actions. It checks permissions before server actions and does not "
        "pretend an action succeeded."
    ),
    "practice": (
        "💻 LeetCode & DSA practice",
        "• `!leet easy arrays` — get a practice problem by difficulty and optional topic. `mid` and `hard` work too.\n"
        "• `!leet 20` — fetch a specific problem by number. Premium problems are not provided.\n"
        "• `!another` — get another problem like your last one, or choose a different difficulty/topic.\n"
        "• `/leet` and `/another` — use the guided slash-command options.\n\n"
        "Problem statements and details come from LeetCode."
    ),
    "progress": (
        "📅 Tasks, streaks & progress",
        "• Admins can schedule daily LeetCode or custom tasks.\n"
        "• Complete the day’s work, then use `!done` in the configured task channel. Dot tracks completed "
        "task days and your current and best task streak.\n"
        "• Post a solved LeetCode screenshot in the configured achievements channel. Dot counts clearly "
        "identified accepted solutions, ignores duplicate images and repeat questions, and tracks your "
        "posting streak.\n"
        "• `!userinfo` or `!userinfo @member` — view account details plus task days, streaks, and unique "
        "questions recorded for that server.\n\n"
        "Screenshot tracking depends on the server admin configuring the channel and the bot’s vision API."
    ),
    "server": (
        "🛡️ Server tools & privacy",
        "• Everyone can ask Dot to DM **only themselves**. Only an Administrator can ask Dot to DM another member.\n"
        "• Administrators can set channels and automod rules; schedule, add, and cancel task plans; "
        "manage warnings, timeouts, and kicks; and lock channels, set slowmode, or clear recent messages. "
        "Some owner-only controls are also available.\n"
        "• `!ping` checks latency, `!serverinfo` shows server details, and `!version` shows the bot version.\n\n"
        "🧠 Dot learns a broad reply style from messages sent directly to Dot and uses your recorded task/solution "
        "totals. It stores aggregate tone counts, not your prompts, and makes no extra AI calls for this. "
        "Say `!dot erase my memory` or use `!forgetme` to erase personalization and recent Dot chat context. "
        "Your task history, streaks, and LeetCode records stay intact."
    ),
}


def build_intro_embed(page="welcome") -> discord.Embed:
    title, description = INTRO_PAGES.get(page, INTRO_PAGES["welcome"])
    embed = discord.Embed(title=title, description=description, color=discord.Color.blurple())
    embed.set_footer(text="Dot · Created by Suryansh · Use the buttons to explore")
    return embed


class DotIntroView(discord.ui.View):
    def __init__(self, owner_id: int):
        super().__init__(timeout=900)
        self.owner_id = owner_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("This intro belongs to another member.", ephemeral=True)
            return False
        return True

    async def _show(self, interaction: discord.Interaction, page: str):
        await interaction.response.edit_message(embed=build_intro_embed(page), view=self)

    @discord.ui.button(label="Start", emoji="👋", style=discord.ButtonStyle.primary, row=0)
    async def welcome(self, interaction: discord.Interaction, _button: discord.ui.Button):
        await self._show(interaction, "welcome")

    @discord.ui.button(label="Ask Dot", emoji="🤖", style=discord.ButtonStyle.secondary, row=0)
    async def ai(self, interaction: discord.Interaction, _button: discord.ui.Button):
        await self._show(interaction, "ai")

    @discord.ui.button(label="Practice", emoji="💻", style=discord.ButtonStyle.secondary, row=0)
    async def practice(self, interaction: discord.Interaction, _button: discord.ui.Button):
        await self._show(interaction, "practice")

    @discord.ui.button(label="Progress", emoji="📅", style=discord.ButtonStyle.secondary, row=1)
    async def progress(self, interaction: discord.Interaction, _button: discord.ui.Button):
        await self._show(interaction, "progress")

    @discord.ui.button(label="Server & privacy", emoji="🛡️", style=discord.ButtonStyle.secondary, row=1)
    async def server(self, interaction: discord.Interaction, _button: discord.ui.Button):
        await self._show(interaction, "server")


class Help(commands.Cog):
    """Send each human member Dot's intro once; !help deliberately resends it."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.broadcast_task: asyncio.Task | None = None
        self.in_flight: set[tuple[int, int]] = set()
        self.receipt_cache: dict[int, set[str]] = {}

    async def send_intro(self, member: discord.abc.User, *, guild_id: int | None = None, force: bool = False) -> bool:
        guild_id = guild_id or getattr(getattr(member, "guild", None), "id", None)
        key = (guild_id, member.id) if guild_id is not None else None
        if key is not None:
            if key in self.in_flight:
                return False
            receipts = self.receipt_cache.get(guild_id)
            if receipts is None:
                receipts = received_users(guild_id)
                self.receipt_cache[guild_id] = receipts
            if not force:
                if str(member.id) in receipts:
                    return False
            self.in_flight.add(key)
        try:
            await member.send(embed=build_intro_embed(), view=DotIntroView(member.id), allowed_mentions=discord.AllowedMentions.none())
            if key is not None:
                mark_received(*key)
                self.receipt_cache[guild_id].add(str(member.id))
            return True
        except discord.HTTPException:
            logger.info("Could not DM Dot intro to user %s in guild %s", member.id, guild_id)
            return False
        except Exception:
            logger.exception("Failed to record or send Dot intro for user %s in guild %s", member.id, guild_id)
            return False
        finally:
            if key is not None:
                self.in_flight.discard(key)

    async def _broadcast_unintroduced_members(self):
        sent = skipped = failed = 0
        for guild in self.bot.guilds:
            cfg = get_guild_config(guild.id)
            if not (cfg.get("commands_channel_ids") or cfg.get("commands_channel_id") or cfg.get("command_channel_ids")):
                continue
            receipts = self.receipt_cache.get(guild.id)
            if receipts is None:
                receipts = received_users(guild.id)
                self.receipt_cache[guild.id] = receipts
            for member in guild.members:
                if member.bot or str(member.id) in receipts:
                    skipped += 1
                    continue
                if await self.send_intro(member, guild_id=guild.id):
                    sent += 1
                else:
                    failed += 1
                await asyncio.sleep(0.25)
        logger.info("Dot intro delivery finished: %s sent, %s already introduced, %s unavailable", sent, skipped, failed)

    @commands.Cog.listener()
    async def on_ready(self):
        if self.broadcast_task is None or self.broadcast_task.done():
            self.broadcast_task = asyncio.create_task(self._broadcast_unintroduced_members())

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        cfg = get_guild_config(member.guild.id)
        configured_for_dot = bool(cfg.get("commands_channel_ids") or cfg.get("commands_channel_id") or cfg.get("command_channel_ids"))
        if not member.bot and configured_for_dot:
            await self.send_intro(member, guild_id=member.guild.id)

    async def _available_commands_embed(self, ctx: commands.Context) -> discord.Embed:
        sections: dict[str, list[commands.Command]] = {}
        for cmd in self.bot.commands:
            if cmd.hidden:
                continue
            try:
                allowed = await cmd.can_run(ctx)
            except commands.CommandError:
                allowed = False
            if allowed:
                sections.setdefault(cmd.cog.qualified_name if cmd.cog else "Other", []).append(cmd)

        embed = discord.Embed(
            title="📚 Commands available to you",
            description="Prefix `!` works for these commands too. Admin-only commands are hidden from regular members.",
            color=discord.Color.blurple(),
        )
        for cog_name, cmds in sorted(sections.items()):
            cmds.sort(key=lambda command: command.name)
            lines = [f"**/{command.name}** — {(command.description or 'No description.')[:90]}" for command in cmds]
            parts = []
            current = []
            current_size = 0
            for line in lines:
                if current and current_size + len(line) + 1 > 900:
                    parts.append("\n".join(current))
                    current, current_size = [], 0
                current.append(line)
                current_size += len(line) + 1
            if current:
                parts.append("\n".join(current))
            for index, part in enumerate(parts):
                if len(embed.fields) >= 25:
                    break
                name = cog_name if index == 0 else f"{cog_name} (continued)"
                embed.add_field(name=name[:256], value=part, inline=False)
        return embed

    @commands.hybrid_command(name="help", description="Get Dot's interactive introduction and your available commands.")
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def help(self, ctx: commands.Context):
        command_embed = await self._available_commands_embed(ctx)
        guild_id = ctx.guild.id if ctx.guild else None
        intro_sent = await self.send_intro(ctx.author, guild_id=guild_id, force=True)
        try:
            await ctx.author.send(embed=command_embed, allowed_mentions=discord.AllowedMentions.none())
            if ctx.guild:
                status = "Sent you Dot’s interactive intro and command list." if intro_sent else "I couldn't deliver the intro, but sent your command list. Check your DM privacy settings."
                await ctx.send(status, ephemeral=True)
        except discord.Forbidden:
            await ctx.send(
                "I couldn't DM your command list (check your Privacy Settings), so here it is instead:",
                embed=command_embed,
                ephemeral=ctx.interaction is not None,
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(Help(bot))
