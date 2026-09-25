"""Scheduled LeetCode practice tasks and completion reminders."""

import asyncio
from datetime import date, datetime, time as day_time, timedelta, timezone
import json
import os
import random
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import discord
from discord import app_commands
from discord.ext import commands, tasks

from cogs.dsa import DETAIL_QUERY, LEARNING_NOTES, LIST_QUERY, _clean_statement, _fetch_json, _topic_match
from utils.channels import get_channel
from utils.config import get_guild_config, set_guild_value
from utils.embeds import action_embed

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
TASK_STATE_FILE = os.path.join(DATA_DIR, "daily_tasks.json")
TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
REMINDER_AFTER = timedelta(hours=6)
RETRY_AFTER = timedelta(hours=1)


def _get_timezone(name: str):
    if name in {"UTC", "Etc/UTC", "GMT"}:
        return timezone.utc
    return ZoneInfo(name)


def _load_state() -> dict:
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(TASK_STATE_FILE):
        return {"guilds": {}}
    with open(TASK_STATE_FILE, "r", encoding="utf-8") as file:
        data = json.load(file)
    data.setdefault("guilds", {})
    return data


def _save_state(data: dict) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    temp_path = TASK_STATE_FILE + ".tmp"
    with open(temp_path, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=2)
    os.replace(temp_path, TASK_STATE_FILE)


def get_current_task_context(guild_id: int) -> str | None:
    """Return today's posted task for Dot's AI context, if one is running."""
    cfg = get_guild_config(guild_id)
    try:
        today = datetime.now(_get_timezone(cfg.get("daily_task_timezone", "UTC"))).date().isoformat()
    except (ZoneInfoNotFoundError, TypeError):
        today = datetime.now(timezone.utc).date().isoformat()
    record = _load_state().get("guilds", {}).get(str(guild_id), {}).get("tasks", {}).get(today, {})
    task = record.get("task") if record.get("sent_at") and not record.get("cancelled_at") else None
    if not task:
        return None
    topics = ", ".join(task.get("topics", [])) or "not specified"
    context = (
        f"Day {task.get('day')} — {task.get('title')} ({task.get('difficulty')}). "
        f"Topics: {topics}. Task instructions/problem: {task.get('statement', '')}"
    )
    custom_tasks = task.get("custom_tasks", [])
    if not custom_tasks and task.get("custom_task"):
        custom_tasks = [task["custom_task"]]
    for index, custom in enumerate(custom_tasks, start=1):
        context += (
            f" Additional custom task {index}: {custom.get('title')}. "
            f"Topics: {', '.join(custom.get('topics', [])) or 'not specified'}. "
            f"Instructions: {custom.get('statement', '')}"
        )
    return context


def get_current_task(guild_id: int) -> dict | None:
    """Return today's already-posted task, using its configured local date."""
    cfg = get_guild_config(guild_id)
    try:
        today = datetime.now(_get_timezone(cfg.get("daily_task_timezone", "UTC"))).date().isoformat()
    except (ZoneInfoNotFoundError, TypeError):
        today = datetime.now(timezone.utc).date().isoformat()
    record = _load_state().get("guilds", {}).get(str(guild_id), {}).get("tasks", {}).get(today, {})
    return record.get("task") if record.get("sent_at") and not record.get("cancelled_at") else None


def _task_embed(task: dict, reminder: bool = False) -> discord.Embed:
    if task.get("difficulty") == "CUSTOM":
        custom_tasks = [task, *task.get("custom_tasks", [])]
        source = "Custom tasks"
    else:
        custom_tasks = task.get("custom_tasks", [])
        if not custom_tasks and task.get("custom_task"):
            custom_tasks = [task["custom_task"]]
        source = "LeetCode + custom tasks" if custom_tasks else "LeetCode task"
    label = f"Daily {source} reminder" if reminder else f"Daily {source}"
    if task.get("difficulty") == "CUSTOM":
        description = f"**Day {task['day']} · CUSTOM**"
        for index, custom in enumerate(custom_tasks, start=1):
            description += f"\n\n**Task {index}: {custom['title']}**\n{custom['statement'][:500]}"
            if custom.get("url"):
                description += f"\n[Open task resource]({custom['url']})"
    else:
        statement = task["statement"][:800] if custom_tasks else task["statement"]
        description = f"**Day {task['day']} · {task['difficulty']}**\n\n{statement}"
        for index, custom in enumerate(custom_tasks, start=1):
            description += f"\n\n**Custom task {index}: {custom['title']}**\n{custom['statement'][:500]}"
            if custom.get("url"):
                description += f"\n[Open task resource]({custom['url']})"
    if reminder:
        description = f"You haven't marked today's task done yet.\n\n{description}"
    embed = discord.Embed(
        title=f"{label}: {task['title']}",
        url=task.get("url") or None,
        description=description[:4090],
        color=discord.Color.blurple(),
    )
    if task.get("topics") and task.get("difficulty") != "CUSTOM":
        embed.add_field(name="LeetCode topics", value=" · ".join(task["topics"][:10])[:1024], inline=False)
    all_custom_topics = list(dict.fromkeys(topic for custom in custom_tasks for topic in custom.get("topics", [])))
    if all_custom_topics:
        label = "Topics" if task.get("difficulty") == "CUSTOM" else "Custom task topics"
        embed.add_field(name=label, value=" · ".join(all_custom_topics[:20])[:1024], inline=False)
    if not task.get("topics") and not all_custom_topics:
        embed.add_field(name="Topics", value="No topics specified", inline=False)
    if reminder:
        embed.set_footer(text="Post !done in the task channel after completing today's task(s).")
    else:
        embed.set_footer(text="Post !done in this channel after completing today's task(s).")
    return embed


class TaskEntryModal(discord.ui.Modal, title="Add a daily custom task"):
    title = discord.ui.TextInput(label="Task title", placeholder="Arrays and two pointers", max_length=80)
    instructions = discord.ui.TextInput(
        label="Instructions",
        placeholder="Describe the goal, steps, or learning outcome",
        style=discord.TextStyle.paragraph,
        max_length=500,
    )
    topics = discord.ui.TextInput(
        label="Topics (optional, comma separated)",
        placeholder="Leave blank for no topics",
        required=False,
        max_length=200,
    )
    link = discord.ui.TextInput(
        label="Reference link (optional)",
        placeholder="https://...",
        required=False,
        max_length=200,
    )

    def __init__(self, cog, day):
        super().__init__()
        self.cog = cog
        self.day = day

    async def on_submit(self, interaction: discord.Interaction):
        try:
            _ok, message = self.cog.store_custom_task(
                interaction.guild.id, self.day, self.title.value, self.instructions.value,
                self.topics.value, self.link.value,
            )
            await interaction.response.send_message(message, ephemeral=True)
        except Exception as error:
            print(f"[daily_tasks] task form submit failed: {error!r}")
            await interaction.response.send_message(
                "I couldn't save that task because of a server-side error. Please reopen `/taskadd` and try again; if it keeps failing, ask an admin to check the bot log.",
                ephemeral=True,
            )


class _TaskDaySelect(discord.ui.Select):
    def __init__(self, view):
        start = view.first_day + view.page * 25
        end = min(view.total_days, start + 24)
        super().__init__(
            placeholder=f"Choose plan day · {start}–{end}",
            options=[discord.SelectOption(label=f"Day {day}", value=str(day)) for day in range(start, end + 1)],
            min_values=1,
            max_values=1,
            row=0,
        )
        self.owner_view = view

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(TaskEntryModal(self.owner_view.cog, int(self.values[0])))


class _TaskDayPageButton(discord.ui.Button):
    def __init__(self, owner_view, direction):
        self.owner_view = owner_view
        self.direction = direction
        super().__init__(
            label="Previous" if direction < 0 else "Next",
            style=discord.ButtonStyle.secondary,
            disabled=(owner_view.page == 0 if direction < 0 else owner_view.page >= owner_view.max_page),
            row=1,
        )

    async def callback(self, interaction: discord.Interaction):
        self.owner_view.page += self.direction
        self.owner_view.build()
        await interaction.response.edit_message(content=self.owner_view.page_text(), view=self.owner_view)


class TaskAddDayView(discord.ui.View):
    def __init__(self, cog, owner_id, first_day, total_days):
        super().__init__(timeout=300)
        self.cog = cog
        self.owner_id = owner_id
        self.first_day = first_day
        self.total_days = total_days
        self.page = 0
        self.max_page = max(0, (total_days - first_day) // 25)
        self.build()

    def build(self):
        self.clear_items()
        self.add_item(_TaskDaySelect(self))
        self.add_item(_TaskDayPageButton(self, -1))
        self.add_item(_TaskDayPageButton(self, 1))

    def page_text(self):
        first = self.first_day + self.page * 25
        last = min(self.total_days, first + 24)
        return f"Choose a future plan day ({first}–{last}, page {self.page + 1}/{self.max_page + 1})."

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("Only the person who opened this picker can use it.", ephemeral=True)
            return False
        return True


class _WizardChannelSelect(discord.ui.ChannelSelect):
    def __init__(self, wizard):
        super().__init__(
            placeholder="Choose the task channel",
            channel_types=[discord.ChannelType.text],
            min_values=1,
            max_values=1,
        )
        self.wizard = wizard

    async def callback(self, interaction: discord.Interaction):
        self.wizard.data["channel"] = self.values[0]
        self.wizard.build_page()
        await interaction.response.edit_message(content=self.wizard.page_text(), view=self.wizard)


class _WizardSelect(discord.ui.Select):
    def __init__(self, wizard, key, placeholder, choices, *, multi=False):
        selected = wizard.data.get(key)
        options = [
            app_commands.Choice(name=label, value=value)
            for label, value in choices
        ]
        select_options = [
            discord.SelectOption(label=choice.name, value=str(choice.value), default=(
                str(choice.value) in selected if isinstance(selected, list) else str(choice.value) == str(selected)
            ))
            for choice in options
        ]
        super().__init__(
            placeholder=placeholder,
            options=select_options,
            min_values=0 if multi else 1,
            max_values=min(10, len(select_options)) if multi else 1,
        )
        self.wizard = wizard
        self.key = key
        self.multi = multi

    async def callback(self, interaction: discord.Interaction):
        values = list(self.values) if self.multi else self.values[0]
        self.wizard.data[self.key] = values
        if self.key == "days":
            days = int(values)
            easy = min(int(self.wizard.data["easy_days"]), days)
            self.wizard.data["easy_days"] = str(easy)
            self.wizard.data["medium_days"] = str(min(int(self.wizard.data["medium_days"]), days - easy))
        elif self.key == "easy_days":
            days = int(self.wizard.data["days"])
            self.wizard.data["medium_days"] = str(min(int(self.wizard.data["medium_days"]), days - int(values)))
        self.wizard.build_page()
        await interaction.response.edit_message(content=self.wizard.page_text(), view=self.wizard)


class _WizardButton(discord.ui.Button):
    def __init__(self, wizard, *, cancel=False):
        super().__init__(
            label="Cancel" if cancel else ("Start plan" if wizard.page == 4 else "Continue"),
            style=discord.ButtonStyle.secondary if cancel else discord.ButtonStyle.primary,
            row=4,
        )
        self.wizard = wizard
        self.cancel = cancel

    async def callback(self, interaction: discord.Interaction):
        if self.cancel:
            return await interaction.response.edit_message(content="Task setup cancelled.", view=None)
        if self.wizard.page == 1 and self.wizard.data["channel"] is None:
            return await interaction.response.send_message("Choose a task channel first.", ephemeral=True)
        if self.wizard.page < 4:
            self.wizard.page += 1
            self.wizard.build_page()
            return await interaction.response.edit_message(content=self.wizard.page_text(), view=self.wizard)
        mode = self.wizard.data["task_type"]
        topics = self.wizard.data["topics"] if mode == "leetcode" else []
        ok, message = self.wizard.cog.configure_plan(
            interaction.guild.id,
            self.wizard.data["channel"],
            int(self.wizard.data["days"]),
            f"{self.wizard.data['hour']}:{self.wizard.data['minute']}",
            self.wizard.data["timezone"],
            mode,
            topics,
        )
        await interaction.response.edit_message(content=message, view=None)


class _WizardBackButton(discord.ui.Button):
    def __init__(self, wizard):
        super().__init__(label="Back", style=discord.ButtonStyle.secondary, row=4)
        self.wizard = wizard

    async def callback(self, interaction: discord.Interaction):
        self.wizard.page -= 1
        self.wizard.build_page()
        await interaction.response.edit_message(content=self.wizard.page_text(), view=self.wizard)


class TaskSetupWizard(discord.ui.View):
    def __init__(self, cog, owner_id):
        super().__init__(timeout=300)
        self.cog = cog
        self.owner_id = owner_id
        self.page = 1
        self.data = {
            "channel": None,
            "task_type": "leetcode",
            "days": "30",
            "easy_days": "7",
            "medium_days": "7",
            "hour": "09",
            "minute": "00",
            "timezone": "Asia/Kolkata",
            "topics": [],
        }
        self.build_page()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("Only the person who started task setup can use these controls.", ephemeral=True)
            return False
        return True

    def page_text(self):
        channel = getattr(self.data["channel"], "mention", "not selected")
        if self.page == 1:
            return f"**Task setup · Step 1 of 4**\nChoose where the daily task should be posted. Current: {channel}."
        if self.page == 2:
            mode = self.data["task_type"].title()
            extra = (
                f" Difficulty: {self.data['easy_days']} Easy days, {self.data['medium_days']} Medium days, then Hard."
                if self.data["task_type"] == "leetcode" else " You'll add your custom tasks after setup."
            )
            return f"**Task setup · Step 2 of 4**\nPlan: {mode}. Duration: {self.data['days']} days.{extra}"
        if self.page == 3:
            return (
                f"**Task setup · Step 3 of 4**\nDaily send time: **{self.data['hour']}:{self.data['minute']}** "
                f"({self.data['timezone']}). Use the menus to change it."
            )
        if self.data["task_type"] == "leetcode":
            topics = ", ".join(self.data["topics"]) or "any topic"
            return f"**Task setup · Step 4 of 4**\nTopics: **{topics}**. Select several, or leave the menu empty for any topic. Then start the plan."
        return "**Task setup · Step 4 of 4**\nThis is a custom plan, so topic filters are not needed. Start the plan, then add tasks with `/taskadd`."

    def build_page(self):
        self.clear_items()
        if self.page == 1:
            self.add_item(_WizardChannelSelect(self))
        elif self.page == 2:
            self.add_item(_WizardSelect(self, "task_type", "Choose a plan type", [("LeetCode", "leetcode"), ("Custom tasks", "custom")]))
            day_choices = [(f"{n} days", str(n)) for n in (1, 3, 5, 7, 14, 30, 60, 90, 180, 365)]
            self.add_item(_WizardSelect(self, "days", "Choose plan duration", day_choices))
            if self.data["task_type"] == "leetcode":
                days = int(self.data["days"])
                def stage_choices(maximum, label):
                    values = list(range(min(maximum, 15) + 1))
                    values.extend(n for n in (21, 30, 45, 60, 90, 120, 180, 270, 365) if n <= maximum and len(values) < 25)
                    return [(f"{n} {label} days", str(n)) for n in values]

                easy_choices = stage_choices(days, "Easy")
                medium_max = days - int(self.data["easy_days"])
                medium_choices = stage_choices(medium_max, "Medium")
                self.add_item(_WizardSelect(self, "easy_days", "Easy stage length", easy_choices))
                self.add_item(_WizardSelect(self, "medium_days", "Medium stage length", medium_choices))
        elif self.page == 3:
            self.add_item(_WizardSelect(self, "hour", "Choose hour", [(f"{n:02}", f"{n:02}") for n in range(24)]))
            self.add_item(_WizardSelect(self, "minute", "Choose minute", [(f"{n:02}", f"{n:02}") for n in range(0, 60, 5)]))
            zones = [
                ("India · Asia/Kolkata", "Asia/Kolkata"), ("UTC", "UTC"),
                ("Singapore · Asia/Singapore", "Asia/Singapore"), ("Dubai · Asia/Dubai", "Asia/Dubai"),
                ("Tokyo · Asia/Tokyo", "Asia/Tokyo"), ("Sydney · Australia/Sydney", "Australia/Sydney"),
                ("London · Europe/London", "Europe/London"), ("Paris · Europe/Paris", "Europe/Paris"),
                ("New York · America/New_York", "America/New_York"), ("Chicago · America/Chicago", "America/Chicago"),
                ("Denver · America/Denver", "America/Denver"), ("Los Angeles · America/Los_Angeles", "America/Los_Angeles"),
            ]
            self.add_item(_WizardSelect(self, "timezone", "Choose timezone", zones))
        elif self.page == 4 and self.data["task_type"] == "leetcode":
            topics = [(topic.title(), topic) for topic in LEARNING_NOTES]
            self.add_item(_WizardSelect(self, "topics", "Optional topics · select none or several", topics, multi=True))
        if self.page > 1:
            self.add_item(_WizardBackButton(self))
        self.add_item(_WizardButton(self))
        self.add_item(_WizardButton(self, cancel=True))


class _TaskStopDaySelect(discord.ui.Select):
    def __init__(self, owner):
        self.owner = owner
        entries = owner.page_entries()
        options = [
            discord.SelectOption(
                label=entry["label"][:100],
                value=str(entry["day"]),
                description=("Posted task bundle" if entry["posted"] else "Scheduled task bundle")[:100],
                default=entry["day"] in owner.selected_days,
            )
            for entry in entries
        ]
        super().__init__(placeholder="Select plan days to cancel", options=options, min_values=0, max_values=max(1, len(options)), row=0)

    async def callback(self, interaction: discord.Interaction):
        page_days = {entry["day"] for entry in self.owner.page_entries()}
        self.owner.selected_days.difference_update(page_days)
        self.owner.selected_days.update(int(value) for value in self.values)
        self.owner.build()
        await interaction.response.edit_message(content=self.owner.page_text(), view=self.owner)


class _TaskStopPageButton(discord.ui.Button):
    def __init__(self, owner, direction):
        self.owner = owner
        self.direction = direction
        super().__init__(
            label="Previous" if direction < 0 else "Next",
            style=discord.ButtonStyle.secondary,
            disabled=(owner.page == 0 if direction < 0 else owner.page >= owner.max_page),
            row=1,
        )

    async def callback(self, interaction: discord.Interaction):
        self.owner.page += self.direction
        self.owner.build()
        await interaction.response.edit_message(content=self.owner.page_text(), view=self.owner)


class _TaskStopActionButton(discord.ui.Button):
    def __init__(self, owner, stop_all=False):
        self.owner = owner
        self.stop_all = stop_all
        super().__init__(
            label="Stop all remaining tasks" if stop_all else "Cancel selected days",
            style=discord.ButtonStyle.danger if stop_all else discord.ButtonStyle.primary,
            disabled=not stop_all and not owner.selected_days,
            row=2,
        )

    async def callback(self, interaction: discord.Interaction):
        days = [entry["day"] for entry in self.owner.entries] if self.stop_all else sorted(self.owner.selected_days)
        message = await self.owner.cog.cancel_plan_days(
            interaction.guild, days, stop_schedule=self.stop_all, actor=interaction.user
        )
        await interaction.response.edit_message(content=message, view=None)


class TaskStopView(discord.ui.View):
    def __init__(self, cog, owner_id, guild_id, entries):
        super().__init__(timeout=300)
        self.cog = cog
        self.owner_id = owner_id
        self.guild_id = guild_id
        self.entries = entries
        self.page = 0
        self.max_page = max(0, (len(entries) - 1) // 25)
        self.selected_days = set()
        self.build()

    def page_entries(self):
        return self.entries[self.page * 25:(self.page + 1) * 25]

    def page_text(self):
        cfg = get_guild_config(self.guild_id)
        selected = ", ".join(f"Day {day}" for day in sorted(self.selected_days)) or "none"
        lines = [
            "**Cancel scheduled task days**",
            "Choose one or more days, then cancel them. Cancelling a day cancels its whole bundle, including any custom tasks.",
            f"Selected: {selected}.",
        ]
        if cfg.get("daily_task_enabled"):
            lines.append("**Stop all remaining tasks** also disables the schedule, cancels posted tasks and pending reminders, and prevents future posts.")
        else:
            lines.append("The schedule is already stopped. You can still cancel posted tasks that are awaiting reminders.")
        if not self.entries:
            lines.append("No uncancelled task days remain.")
            return "\n".join(lines)
        first = self.page * 25 + 1
        last = min(len(self.entries), first + 24)
        lines.append(f"Showing {first}–{last} of {len(self.entries)} available plan days.")
        return "\n".join(lines)

    def build(self):
        self.clear_items()
        if self.page_entries():
            self.add_item(_TaskStopDaySelect(self))
        self.add_item(_TaskStopPageButton(self, -1))
        self.add_item(_TaskStopPageButton(self, 1))
        self.add_item(_TaskStopActionButton(self))
        self.add_item(_TaskStopActionButton(self, stop_all=True))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("Only the administrator who opened this picker can use it.", ephemeral=True)
            return False
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("Only server Administrators can cancel daily tasks.", ephemeral=True)
            return False
        return True


class DailyTasks(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.schedule_tick.start()

    def cog_unload(self):
        self.schedule_tick.cancel()

    @tasks.loop(minutes=1)
    async def schedule_tick(self):
        for guild in self.bot.guilds:
            try:
                await self.process_guild(guild)
            except Exception as error:
                print(f"[daily tasks] {guild.name}: {error}")

    @schedule_tick.before_loop
    async def before_schedule_tick(self):
        await self.bot.wait_until_ready()

    async def process_guild(self, guild: discord.Guild):
        cfg = get_guild_config(guild.id)
        try:
            tz = _get_timezone(cfg.get("daily_task_timezone", "UTC"))
        except (ZoneInfoNotFoundError, TypeError):
            print(f"[daily tasks] Invalid timezone configured for {guild.name}")
            return

        state = _load_state()
        guild_state = state["guilds"].setdefault(str(guild.id), {"tasks": {}})
        now = datetime.now(tz)
        if cfg.get("daily_task_enabled"):
            await self.maybe_post_task(guild, cfg, guild_state, state, now)
        await self.maybe_send_reminders(guild, cfg, guild_state, state, datetime.now(timezone.utc))
        start_value = cfg.get("daily_task_start_date")
        duration = cfg.get("daily_task_days")
        if cfg.get("daily_task_enabled") and start_value and duration:
            final_day = date.fromisoformat(start_value) + timedelta(days=duration - 1)
            if now.date() > final_day:
                set_guild_value(guild.id, "daily_task_enabled", False)

    def current_plan_day(self, guild_id: int) -> int | None:
        cfg = get_guild_config(guild_id)
        start_value = cfg.get("daily_task_start_date")
        try:
            today = datetime.now(_get_timezone(cfg.get("daily_task_timezone", "UTC"))).date()
            start = date.fromisoformat(start_value)
        except (ZoneInfoNotFoundError, TypeError, ValueError):
            return None
        day = (today - start).days + 1
        return day if 1 <= day <= int(cfg.get("daily_task_days", 0)) else None

    def get_cancelable_task_days(self, guild_id: int) -> list[dict]:
        cfg = get_guild_config(guild_id)
        try:
            today = datetime.now(_get_timezone(cfg.get("daily_task_timezone", "UTC"))).date()
        except (ZoneInfoNotFoundError, TypeError):
            today = datetime.now(timezone.utc).date()
        state = _load_state()
        guild_state = state.get("guilds", {}).get(str(guild_id), {}).get("tasks", {})
        entries = []
        start_value = cfg.get("daily_task_start_date")
        duration = int(cfg.get("daily_task_days", 0) or 0)
        if start_value and duration:
            try:
                start = date.fromisoformat(start_value)
            except ValueError:
                start = None
            if start:
                for day in range(1, duration + 1):
                    task_date = start + timedelta(days=day - 1)
                    record = guild_state.get(task_date.isoformat(), {})
                    if record.get("cancelled_at"):
                        continue
                    pending_reminder = bool(record.get("sent_at") and not record.get("reminder_complete"))
                    if task_date < today and not pending_reminder:
                        continue
                    if not cfg.get("daily_task_enabled") and task_date != today and not pending_reminder:
                        continue
                    if not cfg.get("daily_task_enabled") and not record.get("sent_at"):
                        continue
                    task = record.get("task") or {}
                    if task:
                        task_titles = [task.get("title", "Task")]
                        task_titles.extend(item.get("title", "Custom task") for item in task.get("custom_tasks", []))
                        title = " + ".join(task_titles[:3])
                        if len(task_titles) > 3:
                            title += f" + {len(task_titles) - 3} more"
                    else:
                        title = "LeetCode task" if cfg.get("daily_task_type", "leetcode") == "leetcode" else "Custom task"
                        planned_custom = cfg.get("daily_task_custom_tasks", {}).get(str(day), [])
                        if isinstance(planned_custom, dict):
                            planned_custom = [planned_custom]
                        custom_titles = [item.get("title", "Custom task") for item in planned_custom]
                        if custom_titles:
                            title += " + " + " + ".join(custom_titles[:2])
                            if len(custom_titles) > 2:
                                title += f" + {len(custom_titles) - 2} more"
                    when = "Today" if task_date == today else task_date.isoformat()
                    entries.append({
                        "day": day,
                        "date": task_date.isoformat(),
                        "posted": bool(record.get("sent_at")),
                        "label": f"Day {day} · {when} · {title}",
                    })
                return entries
        # A stopped schedule may still have today's already-posted task to cancel.
        record = guild_state.get(today.isoformat(), {})
        if record.get("sent_at") and not record.get("cancelled_at"):
            task = record.get("task") or {}
            day = int(task.get("day", 1))
            entries.append({"day": day, "date": today.isoformat(), "posted": True, "label": f"Day {day} · Today · {task.get('title', 'Posted task')}"})
        return entries

    async def cancel_plan_days(self, guild: discord.Guild, days, *, stop_schedule: bool = False, actor=None) -> str:
        cfg = get_guild_config(guild.id)
        entries = {entry["day"]: entry for entry in self.get_cancelable_task_days(guild.id)}
        selected = sorted({int(day) for day in days if int(day) in entries})
        if stop_schedule:
            set_guild_value(guild.id, "daily_task_enabled", False)
        if not selected:
            return "The schedule is stopped." if stop_schedule else "I couldn't find any selected task days that are still active."

        state = _load_state()
        guild_state = state["guilds"].setdefault(str(guild.id), {"tasks": {}})
        records_to_edit = []
        for day in selected:
            entry = entries[day]
            record = guild_state["tasks"].setdefault(entry["date"], {})
            if record.get("cancelled_at"):
                continue
            record["cancelled_at"] = datetime.now(timezone.utc).isoformat()
            record["cancelled_by"] = getattr(actor, "id", None)
            record["reminder_complete"] = True
            records_to_edit.append((entry, record))
        _save_state(state)

        channel = guild.get_channel(cfg.get("daily_task_channel_id"))
        for entry, record in records_to_edit:
            if channel and record.get("message_id"):
                try:
                    message = channel.get_partial_message(record["message_id"])
                    await message.edit(
                        content=f"🚫 Day {entry['day']} was cancelled by an administrator.",
                        embed=None,
                        view=None,
                        allowed_mentions=discord.AllowedMentions.none(),
                    )
                except discord.NotFound:
                    pass
                except discord.HTTPException as error:
                    print(f"[daily tasks] couldn't update cancelled task post {record['message_id']}: {error!r}")

        if stop_schedule:
            title = "Remaining Daily Tasks Cancelled"
            description = "The schedule was stopped and all remaining posted/planned days were cancelled."
        else:
            title = "Daily Task Days Cancelled"
            description = "Cancelled " + ", ".join(f"Day {day}" for day in selected) + "."
        if actor is not None:
            log_channel = get_channel(guild, "modlog")
            if log_channel:
                embed = action_embed("config", title, description, actor=actor, color=discord.Color.orange())
                try:
                    await log_channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
                except discord.HTTPException as error:
                    print(f"[daily tasks] couldn't write cancellation log: {error!r}")
        if stop_schedule:
            return f"Schedule stopped. Cancelled {len(records_to_edit)} remaining task day(s); their reminders and future posts are stopped."
        return f"Cancelled {len(records_to_edit)} task day(s): " + ", ".join(f"Day {day}" for day in selected) + "."

    async def maybe_post_task(self, guild, cfg, guild_state, state, now):
        start_value = cfg.get("daily_task_start_date")
        duration = cfg.get("daily_task_days")
        channel = guild.get_channel(cfg.get("daily_task_channel_id"))
        if not start_value or not duration or channel is None:
            return
        start_date = date.fromisoformat(start_value)
        day_number = (now.date() - start_date).days + 1
        if day_number < 1 or day_number > duration:
            return
        match = TIME_RE.fullmatch(cfg.get("daily_task_time", ""))
        if not match:
            return
        send_at = day_time(int(match.group(1)), int(match.group(2)))
        if now.timetz().replace(tzinfo=None) < send_at:
            return

        date_key = now.date().isoformat()
        task_record = guild_state["tasks"].setdefault(date_key, {})
        if task_record.get("sent_at") or task_record.get("cancelled_at"):
            return
        last_attempt = task_record.get("last_attempt")
        if last_attempt:
            attempted = datetime.fromisoformat(last_attempt)
            if datetime.now(timezone.utc) - attempted < RETRY_AFTER:
                return
        task_record["last_attempt"] = datetime.now(timezone.utc).isoformat()
        _save_state(state)

        configured_custom = cfg.get("daily_task_custom_tasks", {}).get(str(day_number), [])
        custom_tasks = configured_custom if isinstance(configured_custom, list) else ([configured_custom] if configured_custom else [])
        if cfg.get("daily_task_type", "leetcode") == "custom":
            if not custom_tasks:
                print(f"[daily tasks] Custom task for day {day_number} is not configured in {guild.name}")
                return
            task = {"day": day_number, "difficulty": "CUSTOM", **custom_tasks[0], "custom_tasks": custom_tasks[1:]}
            message = await channel.send(embed=_task_embed(task), allowed_mentions=discord.AllowedMentions.none())
            task_record["task"] = task
            task_record["sent_at"] = datetime.now(timezone.utc).isoformat()
            task_record["message_id"] = message.id
            task_record["completed_ids"] = []
            task_record["reminded_ids"] = []
            _save_state(state)
            print(f"[daily tasks] Sent custom day {day_number}/{duration} to {guild.name}: {task['title']}")
            return

        easy_days = cfg.get("daily_task_easy_days", 7)
        medium_days = cfg.get("daily_task_medium_days", 7)
        difficulty = "EASY" if day_number <= easy_days else "MEDIUM" if day_number <= easy_days + medium_days else "HARD"
        sent_slugs = {
            task.get("slug")
            for item in guild_state["tasks"].values()
            if (task := item.get("task")) and task.get("slug")
        }
        try:
            listing = await asyncio.to_thread(_fetch_json, LIST_QUERY, {
                "categorySlug": "algorithms", "skip": 0, "limit": 1000,
                "filters": {"difficulty": difficulty},
            })
            candidates = listing.get("data", {}).get("questionList", {}).get("data", [])
            candidates = [p for p in candidates if not p.get("isPaidOnly") and p.get("titleSlug") not in sent_slugs]
            topic_filters = cfg.get("daily_task_topics", [])
            if topic_filters:
                candidates = [
                    problem for problem in candidates
                    if any(_topic_match(problem, selected_topic) for selected_topic in topic_filters)
                ]
            if not candidates:
                print(f"[daily tasks] No unused {difficulty} LeetCode questions remain for {guild.name}")
                return
            selected = random.choice(candidates)
            detail = await asyncio.to_thread(_fetch_json, DETAIL_QUERY, {"titleSlug": selected["titleSlug"]})
            problem = detail.get("data", {}).get("question")
            if not problem:
                raise ValueError("LeetCode returned no question details")
            statement, _images = _clean_statement(problem.get("content", ""))
            if len(statement) > 3300:
                statement = statement[:3297].rsplit(" ", 1)[0] + "..."
            topics = [tag["name"] for tag in problem.get("topicTags", [])]
            task = {
                "day": day_number,
                "difficulty": problem.get("difficulty", difficulty).upper(),
                "title": f"{problem.get('questionFrontendId', '')}. {problem['title']}",
                "slug": problem["titleSlug"],
                "url": f"https://leetcode.com/problems/{problem['titleSlug']}/",
                "statement": statement or "Open LeetCode to read the full problem statement.",
                "topics": topics,
            }
            if custom_tasks:
                task["custom_tasks"] = custom_tasks
            message = await channel.send(embed=_task_embed(task), allowed_mentions=discord.AllowedMentions.none())
            task_record["task"] = task
            task_record["sent_at"] = datetime.now(timezone.utc).isoformat()
            task_record["message_id"] = message.id
            task_record["completed_ids"] = []
            task_record["reminded_ids"] = []
            _save_state(state)
            print(f"[daily tasks] Sent day {day_number}/{duration} to {guild.name}: {task['title']}")
        except Exception as error:
            print(f"[daily tasks] Could not post today's task in {guild.name}: {error}")

    async def maybe_send_reminders(self, guild, cfg, guild_state, state, now_utc):
        channel = guild.get_channel(cfg.get("daily_task_channel_id"))
        if channel is None:
            return
        for task_record in guild_state["tasks"].values():
            sent_at = task_record.get("sent_at")
            if not sent_at or task_record.get("cancelled_at") or task_record.get("reminder_complete"):
                continue
            if now_utc - datetime.fromisoformat(sent_at) < REMINDER_AFTER:
                continue
            task = task_record.get("task")
            if not task:
                task_record["reminder_complete"] = True
                continue
            completed = set(task_record.get("completed_ids", []))
            reminded = set(task_record.get("reminded_ids", []))
            recipients = [
                member for member in guild.members
                if not member.bot
                and member.id not in completed
                and member.id not in reminded
                and channel.permissions_for(member).view_channel
            ]
            for member in recipients:
                try:
                    await member.send(embed=_task_embed(task, reminder=True), allowed_mentions=discord.AllowedMentions.none())
                except discord.HTTPException:
                    pass
                reminded.add(member.id)
                task_record["reminded_ids"] = list(reminded)
                _save_state(state)
                await asyncio.sleep(0.35)
            task_record["reminder_complete"] = True
            _save_state(state)

    def configure_plan(self, guild_id, channel, days, send_time, timezone_name, task_type, topics=None):
        cfg = get_guild_config(guild_id)
        if cfg.get("daily_task_enabled"):
            return False, "A task plan is already running. Use `/taskadd` to add a custom task to a future day, or `/taskstop` before setting up a new plan."
        if days < 1 or days > 365:
            return False, "Choose between 1 and 365 days."
        match = TIME_RE.fullmatch(send_time)
        if not match:
            return False, "Use 24-hour time in HH:MM format, for example `09:30`."
        try:
            tz = _get_timezone(timezone_name)
        except (ZoneInfoNotFoundError, TypeError):
            return False, "Use a valid IANA time zone, such as `Asia/Kolkata` or `UTC`."

        topics = [topic.strip()[:100] for topic in (topics or []) if topic.strip()][:10]
        easy_days = cfg.get("daily_task_easy_days", 7)
        medium_days = cfg.get("daily_task_medium_days", 7)
        if easy_days < 0 or medium_days < 0 or easy_days + medium_days > days:
            easy_days, medium_days = min(7, days), min(7, max(days - min(7, days), 0))

        now = datetime.now(tz)
        scheduled = day_time(int(match.group(1)), int(match.group(2)))
        first_date = now.date() if now.timetz().replace(tzinfo=None) < scheduled else now.date() + timedelta(days=1)
        # A cancelled day's LeetCode slug remains in history to prevent repeats,
        # but its cancellation marker must not block a newly configured plan.
        state = _load_state()
        task_history = state.get("guilds", {}).get(str(guild_id), {}).get("tasks", {})
        state_changed = False
        for plan_day in range(1, days + 1):
            previous = task_history.get((first_date + timedelta(days=plan_day - 1)).isoformat(), {})
            if previous.get("cancelled_at"):
                for key in ("sent_at", "cancelled_at", "cancelled_by", "reminder_complete", "message_id", "completed_ids", "reminded_ids"):
                    previous.pop(key, None)
                state_changed = True
        if state_changed:
            _save_state(state)
        values = {
            "daily_task_channel_id": channel.id,
            "daily_task_days": days,
            "daily_task_time": send_time,
            "daily_task_timezone": timezone_name,
            "daily_task_start_date": first_date.isoformat(),
            "daily_task_enabled": True,
            "daily_task_type": task_type,
            "daily_task_easy_days": easy_days,
            "daily_task_medium_days": medium_days,
            "daily_task_custom_tasks": {},
            "daily_task_topics": topics,
        }
        for key, value in values.items():
            set_guild_value(guild_id, key, value)
        progression = f" It starts with {easy_days} Easy days, then {medium_days} Medium days, then Hard." if task_type == "leetcode" else ""
        topic_text = f" Topics: {', '.join(topics)}." if topics else " Topics: no filter (any topic)."
        return True, (
            f"Daily {task_type} plan set for <#{channel.id}>: {days} days at {send_time} "
            f"({timezone_name}), starting {first_date.isoformat()}.{progression}{topic_text} "
            "Use `/taskadd` to add up to 4 custom tasks to any future day. Members who can view "
            "the channel get one DM reminder after six hours if they haven't used `!done`."
        )

    @commands.hybrid_command(name="tasksetup", description="Start a daily LeetCode plan (leave topics blank for any topic).")
    @app_commands.describe(
        channel="Where tasks are posted and !done is used",
        days="Number of consecutive daily tasks, 1–365",
        send_time="Local 24-hour time, for example 09:00",
        timezone_name="IANA timezone; India is Asia/Kolkata",
        topics="Optional comma-separated LeetCode topics; blank means any topic",
    )
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def tasksetup(
        self, ctx: commands.Context, channel: discord.TextChannel = None, days: int = None,
        send_time: str = None, timezone_name: str = "Asia/Kolkata", *, topics: str = "",
    ):
        if channel is None or days is None or send_time is None:
            if get_guild_config(ctx.guild.id).get("daily_task_enabled"):
                return await ctx.send(
                    "A plan is already running. Use `/taskadd` to add custom tasks to future days, or `/taskstop` before starting another.",
                    ephemeral=True,
                )
            view = TaskSetupWizard(self, ctx.author.id)
            return await ctx.send(
                view= view,
                content=view.page_text(),
                ephemeral=ctx.interaction is not None,
            )
        topic_list = [topic for topic in topics.split(",") if topic.strip()]
        ok, message = self.configure_plan(ctx.guild.id, channel, days, send_time, timezone_name, "leetcode", topic_list)
        await ctx.send(message, ephemeral=not ok or ctx.interaction is not None)

    @tasksetup.error
    async def tasksetup_error(self, ctx: commands.Context, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("Only server Administrators can set up daily tasks.", ephemeral=True)
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send("Usage: `!tasksetup #task-channel <days> <HH:MM> [timezone] [topic1, topic2]`", ephemeral=True)
        else:
            await ctx.send("Couldn't configure daily tasks.", ephemeral=True)
            raise error

    @commands.hybrid_command(name="taskcustomplan", description="Start a plan made from your own daily tasks.")
    @app_commands.describe(
        channel="Where tasks are posted and !done is used",
        days="Number of consecutive daily tasks, 1–365",
        send_time="Local 24-hour time, for example 09:00",
        timezone_name="IANA timezone; India is Asia/Kolkata",
    )
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def taskcustomplan(self, ctx: commands.Context, channel: discord.TextChannel, days: int, send_time: str, timezone_name: str = "UTC"):
        ok, message = self.configure_plan(ctx.guild.id, channel, days, send_time, timezone_name, "custom")
        if ok:
            message = message.replace("Use `/taskadd` to add up to 4 custom tasks to any future day.", "Use `/taskadd` to add one or more tasks to each plan day before its scheduled send time.")
        await ctx.send(message, ephemeral=not ok or ctx.interaction is not None)

    @taskcustomplan.error
    async def taskcustomplan_error(self, ctx: commands.Context, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("Only server Administrators can set up daily tasks.", ephemeral=True)
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send("Usage: `!taskcustomplan #task-channel <days> <HH:MM> [timezone]`", ephemeral=True)
        else:
            await ctx.send("Couldn't configure the custom task plan.", ephemeral=True)
            raise error

    def store_custom_task(self, guild_id, day, title, instructions, topic_text="", url=""):
        cfg = get_guild_config(guild_id)
        if not cfg.get("daily_task_enabled"):
            return False, "Set up a task plan first."
        # LeetCode plans accept one optional custom task per day; both are bundled together.
        if day < 1 or day > cfg.get("daily_task_days", 0):
            return False, f"Choose a day from 1 to {cfg.get('daily_task_days')}."
        if not title.strip() or not instructions.strip():
            return False, "Add both a title and instructions."
        if len(title) > 80 or len(instructions) > 500:
            return False, "Keep the title under 80 characters and instructions under 500."
        if url and not url.startswith(("https://", "http://")):
            return False, "The optional URL must start with `https://` or `http://`."
        planned_date = date.fromisoformat(cfg["daily_task_start_date"]) + timedelta(days=day - 1)
        try:
            today = datetime.now(_get_timezone(cfg.get("daily_task_timezone", "UTC"))).date()
        except (ZoneInfoNotFoundError, TypeError):
            today = datetime.now(timezone.utc).date()
        if planned_date < today:
            return False, f"Day {day} is in the past. Choose a future plan day."
        record = _load_state().get("guilds", {}).get(str(guild_id), {}).get("tasks", {}).get(planned_date.isoformat(), {})
        if record.get("cancelled_at"):
            return False, f"Day {day} was cancelled. Reconfigure the task plan to schedule it again."
        if record.get("sent_at"):
            return False, f"Day {day} has already been posted. Add custom tasks before that day's scheduled time."
        topics = [topic.strip()[:100] for topic in topic_text.split(",") if topic.strip()][:10]
        custom_tasks = dict(cfg.get("daily_task_custom_tasks", {}))
        day_tasks = custom_tasks.get(str(day), [])
        if isinstance(day_tasks, dict):  # upgrade a task saved by the earlier single-task format
            day_tasks = [day_tasks]
        else:
            day_tasks = list(day_tasks)
        new_task = {
            "title": title,
            "statement": instructions,
            "topics": topics,
            "url": url,
        }
        existing_index = next((i for i, item in enumerate(day_tasks) if item.get("title", "").casefold() == title.casefold()), None)
        if existing_index is not None:
            day_tasks[existing_index] = new_task
            saved_as = "Updated"
        else:
            if len(day_tasks) >= 4:
                return False, "A day can have up to 4 custom tasks. Edit one by submitting it again with the same title."
            day_tasks.append(new_task)
            saved_as = "Added"
        custom_tasks[str(day)] = day_tasks
        set_guild_value(guild_id, "daily_task_custom_tasks", custom_tasks)
        mode_note = "This will be combined with that day's LeetCode question in one post." if cfg.get("daily_task_type") == "leetcode" else ""
        return True, f"{saved_as} custom task for day {day}: **{title}** ({len(day_tasks)}/4). {mode_note}".strip()

    @app_commands.command(name="taskadd", description="Open a form to add a custom task to a future plan day.")
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(administrator=True)
    async def taskadd_form(self, interaction: discord.Interaction):
        cfg = get_guild_config(interaction.guild.id)
        if not cfg.get("daily_task_enabled"):
            return await interaction.response.send_message("There is no active task plan. Start one with `/tasksetup` first.", ephemeral=True)
        try:
            today = datetime.now(_get_timezone(cfg.get("daily_task_timezone", "UTC"))).date()
        except (ZoneInfoNotFoundError, TypeError):
            today = datetime.now(timezone.utc).date()
        start_date = date.fromisoformat(cfg["daily_task_start_date"])
        first_day = max(1, (today - start_date).days + 1)
        today_record = _load_state().get("guilds", {}).get(str(interaction.guild.id), {}).get("tasks", {}).get(today.isoformat(), {})
        if today_record.get("sent_at"):
            first_day += 1
        total_days = cfg.get("daily_task_days", 1)
        if first_day > total_days:
            return await interaction.response.send_message("There are no future plan days left for custom tasks.", ephemeral=True)
        view = TaskAddDayView(self, interaction.user.id, first_day, total_days)
        await interaction.response.send_message(view= view, content=view.page_text(), ephemeral=True)

    @taskadd_form.error
    async def taskadd_form_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.MissingPermissions):
            message = "Only server Administrators can edit daily tasks."
        else:
            print(f"[daily_tasks] taskadd form failed: {error!r}")
            message = "Couldn't open the custom-task form. Please retry; if it keeps failing, ask an admin to check the bot log."
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)

    @commands.command(name="taskadd", help="Add a custom task: !taskadd <day> Title | instructions | topics | optional URL")
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def taskadd_prefix(self, ctx: commands.Context, *, task: str = ""):
        parts = [part.strip() for part in task.split("|")]
        if len(parts) not in {4, 5}:
            return await ctx.send("Use `/taskadd` for a form, or `!taskadd <day> Title | instructions | topics | optional URL`.")
        try:
            day = int(parts[0])
        except ValueError:
            return await ctx.send("The first item must be the plan day number.")
        url = parts[4] if len(parts) == 5 else ""
        _ok, message = self.store_custom_task(ctx.guild.id, day, parts[1], parts[2], parts[3], url)
        await ctx.send(message)

    @taskadd_prefix.error
    async def taskadd_prefix_error(self, ctx: commands.Context, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("Only server Administrators can edit the task plan.", ephemeral=True)
        else:
            await ctx.send("Couldn't save that task.")
            raise error

    @commands.hybrid_command(name="taskstages", description="Set the Easy and Medium stage lengths for future LeetCode plans.")
    @app_commands.describe(easy_days="Easy days at the start", medium_days="Medium days after Easy; the rest are Hard")
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def taskstages(self, ctx: commands.Context, easy_days: int, medium_days: int):
        if get_guild_config(ctx.guild.id).get("daily_task_enabled"):
            return await ctx.send("A plan is running. Difficulty stages can only be changed before the next plan starts.", ephemeral=True)
        if easy_days < 0 or medium_days < 0 or easy_days + medium_days > 365:
            return await ctx.send("Stages must be non-negative and total no more than 365 days.", ephemeral=True)
        set_guild_value(ctx.guild.id, "daily_task_easy_days", easy_days)
        set_guild_value(ctx.guild.id, "daily_task_medium_days", medium_days)
        await ctx.send(f"Future LeetCode plans will use {easy_days} Easy day(s), then {medium_days} Medium day(s), then Hard.")

    @commands.hybrid_command(name="taskstop", description="Choose daily task days to cancel or stop the whole schedule.")
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def taskstop(self, ctx: commands.Context):
        entries = self.get_cancelable_task_days(ctx.guild.id)
        cfg = get_guild_config(ctx.guild.id)
        if not entries and not cfg.get("daily_task_enabled"):
            return await ctx.send("There is no active schedule or posted task to cancel.", ephemeral=ctx.interaction is not None)
        view = TaskStopView(self, ctx.author.id, ctx.guild.id, entries)
        await ctx.send(
            content=view.page_text(),
            view=view,
            ephemeral=ctx.interaction is not None,
        )

    @commands.hybrid_command(name="taskstatus", description="Show this server's daily LeetCode task schedule.")
    @commands.guild_only()
    async def taskstatus(self, ctx: commands.Context):
        cfg = get_guild_config(ctx.guild.id)
        channel = ctx.guild.get_channel(cfg.get("daily_task_channel_id"))
        if not cfg.get("daily_task_enabled"):
            return await ctx.send("No daily task schedule is currently active.", ephemeral=True)
        custom_progress = ""
        configured = len(cfg.get("daily_task_custom_tasks", {}))
        if cfg.get("daily_task_type") == "custom" or configured:
            custom_progress = f" · {configured}/{cfg.get('daily_task_days')} custom days configured"
        topic_text = ", ".join(cfg.get("daily_task_topics", [])) or "any topic"
        await ctx.send(
            f"Daily tasks: {channel.mention if channel else '(channel missing)'} · "
            f"{cfg.get('daily_task_days')} days · {cfg.get('daily_task_type', 'leetcode')} · "
            f"{cfg.get('daily_task_time')} ({cfg.get('daily_task_timezone')}) · topics: {topic_text}{custom_progress} · "
            f"starts {cfg.get('daily_task_start_date')}"
        )

    @commands.hybrid_command(name="done", description="Mark today's task complete in the configured task channel.")
    @commands.guild_only()
    async def done(self, ctx: commands.Context):
        cfg = get_guild_config(ctx.guild.id)
        if ctx.channel.id != cfg.get("daily_task_channel_id"):
            return await ctx.send("Use `!done` in this server's configured task channel.", ephemeral=True)
        try:
            today = datetime.now(_get_timezone(cfg.get("daily_task_timezone", "UTC"))).date().isoformat()
        except (ZoneInfoNotFoundError, TypeError):
            today = datetime.now(timezone.utc).date().isoformat()
        state = _load_state()
        record = state["guilds"].get(str(ctx.guild.id), {}).get("tasks", {}).get(today)
        if record and record.get("cancelled_at"):
            return await ctx.send("Today's task was cancelled by an admin, so it can't be marked done.", ephemeral=True)
        if not record or not record.get("sent_at"):
            return await ctx.send("There isn't a daily task posted today yet.", ephemeral=True)
        completed = set(record.get("completed_ids", []))
        completed.add(ctx.author.id)
        record["completed_ids"] = list(completed)
        _save_state(state)
        await ctx.send(f"✅ {ctx.author.mention} marked today's task done!", allowed_mentions=discord.AllowedMentions.none())


async def setup(bot: commands.Bot):
    await bot.add_cog(DailyTasks(bot))
