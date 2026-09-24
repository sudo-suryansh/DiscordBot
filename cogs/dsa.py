"""LeetCode problem picker for the DSA study server."""

import asyncio
from html.parser import HTMLParser
import json
import random
import re
import time
from urllib.request import Request, urlopen
from urllib.parse import urljoin

import discord
from discord import app_commands
from discord.ext import commands

from utils.channels import get_channel
from utils.config import set_guild_value


LEETCODE_URL = "https://leetcode.com/graphql/"
REQUEST_COOLDOWN = 30
ANOTHER_WINDOW = 5 * 60
LIST_QUERY = """
query problemsetQuestionList($categorySlug: String, $limit: Int, $skip: Int, $filters: QuestionListFilterInput) {
  questionList(categorySlug: $categorySlug, limit: $limit, skip: $skip, filters: $filters) {
    totalNum
    data { questionFrontendId title titleSlug difficulty isPaidOnly topicTags { name } }
  }
}
"""
DETAIL_QUERY = """
query questionData($titleSlug: String!) {
  question(titleSlug: $titleSlug) { questionFrontendId title titleSlug difficulty content topicTags { name } }
}
"""

LEARNING_NOTES = {
    "array": "Organizing and scanning indexed data",
    "hash table": "Fast lookups, counting, and tracking seen values",
    "string": "Character processing and careful text manipulation",
    "two pointers": "Coordinating two positions to avoid extra passes",
    "sliding window": "Maintaining a moving range efficiently",
    "binary search": "Narrowing a sorted search space step by step",
    "linked list": "Pointer updates and careful edge-case handling",
    "stack": "Using last-in, first-out state to simplify decisions",
    "queue": "Processing items in first-in, first-out order",
    "tree": "Recursive structure, traversal, and subtree reasoning",
    "binary search tree": "Ordering properties and guided tree searches",
    "depth-first search": "Exploring a branch fully before backtracking",
    "breadth-first search": "Level-by-level traversal and shortest paths",
    "graph": "Representing relationships and traversing connected data",
    "dynamic programming": "Breaking a problem into reusable subproblems",
    "greedy": "Making and validating locally optimal choices",
    "heap": "Efficiently tracking the smallest or largest items",
    "priority queue": "Choosing the next item by priority",
    "backtracking": "Building candidates and pruning invalid paths",
    "trie": "Prefix trees and efficient string lookup",
    "sorting": "Ordering data to reveal useful structure",
    "bit manipulation": "Using binary operations to represent compact state",
    "math": "Turning mathematical observations into an algorithm",
}


class _TextExtractor(HTMLParser):
    """Turn LeetCode's HTML problem statement into readable text."""
    BLOCK_TAGS = {"p", "div", "br", "li", "pre", "h1", "h2", "h3", "ul", "ol"}

    def __init__(self):
        super().__init__()
        self.parts = []
        self.images = []

    def handle_starttag(self, tag, attrs):
        if tag in self.BLOCK_TAGS:
            self.parts.append("\n• " if tag == "li" else "\n")
        elif tag == "code":
            self.parts.append("`")
        elif tag == "img":
            src = dict(attrs).get("src")
            if src:
                image_url = urljoin("https://leetcode.com", src)
                if image_url.startswith("https://") and image_url not in self.images:
                    self.images.append(image_url)

    def handle_endtag(self, tag):
        if tag in self.BLOCK_TAGS:
            self.parts.append("\n")
        elif tag == "code":
            self.parts.append("`")

    def handle_data(self, data):
        self.parts.append(data)


def _fetch_json(query: str, variables: dict) -> dict:
    payload = json.dumps({"query": query, "variables": variables}).encode("utf-8")
    request = Request(
        LEETCODE_URL,
        data=payload,
        headers={"Content-Type": "application/json", "User-Agent": "DSA-Server-Bot/1.0"},
    )
    with urlopen(request, timeout=12) as response:
        return json.loads(response.read().decode("utf-8"))


def _fetch_numbered_problem(question_number: int) -> dict | None:
    """Find a numbered problem across LeetCode's paginated problem listing."""
    skip = 0
    while True:
        result = _fetch_json(LIST_QUERY, {
            "categorySlug": "algorithms", "skip": skip, "limit": 1000,
            "filters": {},
        })
        listing = result.get("data", {}).get("questionList", {})
        page = listing.get("data", [])
        selected = next(
            (item for item in page if str(item.get("questionFrontendId")) == str(question_number)),
            None,
        )
        if selected:
            if selected.get("isPaidOnly"):
                return {"isPaidOnly": True}
            detail = _fetch_json(DETAIL_QUERY, {"titleSlug": selected["titleSlug"]})
            return detail.get("data", {}).get("question")
        if len(page) < 1000:
            return None
        skip += len(page)


def _clean_statement(html: str) -> tuple[str, list[str]]:
    parser = _TextExtractor()
    parser.feed(html or "")
    text = re.sub(r"[ \t]+", " ", "".join(parser.parts))
    return re.sub(r"\n\s*\n+", "\n\n", text).strip(), parser.images


def _topic_match(problem: dict, topic: str) -> bool:
    tags = [tag["name"].lower() for tag in problem.get("topicTags", [])]
    query = topic.lower().strip()
    return any(query in tag or tag in query for tag in tags)


def _parse_dm_suffix(topic: str = None) -> tuple[str | None, bool]:
    """Treat a final `dm` token as delivery choice, not a topic word."""
    if not topic:
        return None, False
    words = topic.split()
    if words and words[-1].casefold() == "dm":
        topic = " ".join(words[:-1]).strip()
        return topic or None, True
    return topic.strip() or None, False


def _learning_outcomes(tags: list[str]) -> str:
    notes = []
    for tag in tags:
        normalized = tag.lower()
        note = next((description for key, description in LEARNING_NOTES.items() if key in normalized), None)
        if note and note not in notes:
            notes.append(note)
        if len(notes) == 3:
            break
    return "\n".join(f"• {note}" for note in notes) or "Practice translating an idea into a clear, efficient solution."


def _make_problem_embed(problem: dict, requested_by: discord.abc.User, requested_difficulty: str) -> tuple[discord.Embed, discord.ui.View]:
    difficulty = problem.get("difficulty", requested_difficulty.title())
    color = {
        "EASY": discord.Color.green(),
        "MEDIUM": discord.Color.orange(),
        "HARD": discord.Color.red(),
    }.get(difficulty.upper(), discord.Color.blurple())
    url = f"https://leetcode.com/problems/{problem['titleSlug']}/"
    title = problem["title"]
    question_id = problem.get("questionFrontendId")
    if question_id:
        title = f"{question_id}. {title}"

    statement, images = _clean_statement(problem.get("content", ""))
    # Leave room for the section headings while respecting Discord's 4,096-char limit.
    if len(statement) > 3300:
        statement = statement[:3297].rsplit(" ", 1)[0] + "..."
    if not statement:
        statement = "Open the challenge on LeetCode to read the full problem statement."
    tags = [tag["name"] for tag in problem.get("topicTags", [])]

    embed = discord.Embed(
        title=title,
        url=url,
        description=f"**THE CHALLENGE**\n{statement}",
        color=color,
    )
    embed.set_author(name=f"LEETCODE PRACTICE  /  {difficulty.upper()}")
    embed.add_field(
        name="🧠  What you’ll practice",
        value=_learning_outcomes(tags),
        inline=False,
    )
    embed.add_field(
        name="🏷️  Topics",
        value=" · ".join(tags[:6]) or "Problem solving",
        inline=False,
    )
    embed.set_footer(text=f"Requested by {requested_by.display_name}  •  Try !another after 5 minutes")
    if images:
        embed.set_image(url=images[0])

    view = discord.ui.View(timeout=None)
    view.add_item(discord.ui.Button(label="Open problem on LeetCode", url=url, emoji="↗️"))
    return embed, view


class LeetCode(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Keyed by requester so !another works when they switch between server and DM.
        self.last_problem: dict[int, dict] = {}

    @commands.hybrid_command(name="setprobchannel", description="Set the channel where LeetCode problem requests are posted.")
    @app_commands.describe(channel="Channel for requested LeetCode problems")
    @commands.has_permissions(administrator=True)
    async def setprobchannel(self, ctx: commands.Context, channel: discord.TextChannel):
        set_guild_value(ctx.guild.id, "problem_channel_id", channel.id)
        await ctx.send(f"LeetCode problems will be posted in {channel.mention}.")

    @setprobchannel.error
    async def setprobchannel_error(self, ctx: commands.Context, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("Only server Administrators can set the problem channel.", ephemeral=True)
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send("Choose a channel, for example `!setprobchannel #dsa-problems`.", ephemeral=True)
        else:
            await ctx.send("Couldn't set the problem channel. Check the channel and bot permissions.", ephemeral=True)

    async def _send_problem(
        self,
        ctx: commands.Context,
        difficulty: str,
        topic: str = None,
        exclude_slug: str = None,
        send_dm: bool = False,
    ):
        is_dm = ctx.guild is None
        channel = get_channel(ctx.guild, "problem") if ctx.guild else None
        if not is_dm and channel is None:
            await ctx.send("No problem channel is configured. Ask an Administrator to run `!setprobchannel #channel`.", ephemeral=True)
            return None

        level = {"easy": "EASY", "mid": "MEDIUM", "medium": "MEDIUM", "hard": "HARD"}.get(difficulty.lower())
        question_number = None
        if level is None:
            try:
                question_number = int(difficulty)
                if question_number < 1:
                    raise ValueError
            except ValueError:
                question_number = None
        if level is None and question_number is None:
            await ctx.send("Difficulty must be `easy`, `mid`, or `hard`.", ephemeral=not is_dm)
            return None
        if question_number is not None and topic:
            await ctx.send("For a numbered problem, use `!leet <number> [dm]`.", ephemeral=not is_dm)
            return None

        previous = self.last_problem.get(ctx.author.id)
        if previous is not None:
            remaining = REQUEST_COOLDOWN - (time.monotonic() - previous["sent_at"])
            if remaining > 0:
                await ctx.send(
                    f"Gandu pehle wala padh toh le, Time left to request another: **{int(remaining + 0.999)}s**.",
                    ephemeral=not is_dm,
                )
                return None

        await ctx.defer()
        try:
            if question_number is not None:
                problem = await asyncio.to_thread(_fetch_numbered_problem, question_number)
                if problem and problem.get("isPaidOnly"):
                    await ctx.send("bhadwe, question paid hai", ephemeral=not is_dm)
                    return None
                if problem is None:
                    await ctx.send(f"I couldn't find LeetCode problem #{question_number}.")
                    return None
            else:
                listing = await asyncio.to_thread(_fetch_json, LIST_QUERY, {
                    "categorySlug": "algorithms", "skip": 0, "limit": 1000,
                    "filters": {"difficulty": level},
                })
                candidates = listing.get("data", {}).get("questionList", {}).get("data", [])
                candidates = [problem for problem in candidates if not problem.get("isPaidOnly")]
                if topic:
                    candidates = [problem for problem in candidates if _topic_match(problem, topic)]
                if exclude_slug and len(candidates) > 1:
                    candidates = [problem for problem in candidates if problem.get("titleSlug") != exclude_slug]
                if not candidates:
                    note = f" tagged {topic!r}" if topic else ""
                    await ctx.send(f"I couldn't find a free {difficulty.title()} problem{note}. Try a broader topic.")
                    return None

                selected = random.choice(candidates)
                detail = await asyncio.to_thread(_fetch_json, DETAIL_QUERY, {"titleSlug": selected["titleSlug"]})
                problem = detail.get("data", {}).get("question")
            if not problem:
                raise ValueError("LeetCode returned no problem details")
        except Exception:
            await ctx.send("I couldn't fetch a problem from LeetCode right now. Please try again shortly.")
            return None

        embed, view = _make_problem_embed(problem, ctx.author, difficulty)
        if channel is not None:
            try:
                await channel.send(content=f"**Problem pick**  ·  requested by {ctx.author.mention}", embed=embed, view=view)
            except discord.Forbidden:
                await ctx.send(f"I found {channel.mention}, but I can't post there. Check my channel permissions.", ephemeral=True)
                return None

        key = ctx.author.id
        repeat_difficulty = difficulty.lower()
        if question_number is not None:
            repeat_difficulty = {
                "EASY": "easy", "MEDIUM": "mid", "HARD": "hard",
            }.get(problem.get("difficulty", "").upper(), "mid")
        self.last_problem[key] = {
            "difficulty": repeat_difficulty,
            "topic": topic,
            "send_dm": send_dm,
            "slug": problem["titleSlug"],
            "sent_at": time.monotonic(),
        }
        if is_dm:
            await ctx.send(embed=embed, view=view)
        elif send_dm:
            try:
                await ctx.author.send(embed=embed, view=view)
                await ctx.send(f"Problem posted in {channel.mention} and sent to your DMs.", ephemeral=True)
            except discord.Forbidden:
                await ctx.send(f"Problem posted in {channel.mention}, but I couldn't DM you. Check your server DM privacy settings.", ephemeral=True)
        else:
            await ctx.send(f"Problem posted in {channel.mention}.", ephemeral=True)
        return problem

    @commands.hybrid_command(name="leet", description="Get a random LeetCode problem by difficulty/topic, or fetch a problem by number.")
    @app_commands.describe(difficulty="Problem difficulty", topic="Optional topic; append 'dm' to also receive it privately")
    @app_commands.choices(difficulty=[
        app_commands.Choice(name="Easy", value="easy"),
        app_commands.Choice(name="Mid (Medium)", value="mid"),
        app_commands.Choice(name="Hard", value="hard"),
    ])
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def leet(self, ctx: commands.Context, difficulty: str, *, topic: str = None):
        topic, send_dm = _parse_dm_suffix(topic)
        await self._send_problem(ctx, difficulty, topic, send_dm=send_dm)

    @commands.hybrid_command(name="another", description="Get another problem. Bare command repeats your last difficulty and topic; available every 5 minutes.")
    @app_commands.describe(difficulty="Optional new difficulty", topic="Optional topic; append 'dm' to also receive it privately")
    @app_commands.choices(difficulty=[
        app_commands.Choice(name="Easy", value="easy"),
        app_commands.Choice(name="Mid (Medium)", value="mid"),
        app_commands.Choice(name="Hard", value="hard"),
    ])
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def another(self, ctx: commands.Context, difficulty: str = None, *, topic: str = None):
        is_dm = ctx.guild is None
        key = ctx.author.id
        previous = self.last_problem.get(key)
        if previous is None:
            return await ctx.send("Get your first problem with `!leet easy`, `!leet mid`, or `!leet hard`.", ephemeral=not is_dm)

        elapsed = time.monotonic() - previous["sent_at"]
        if elapsed > ANOTHER_WINDOW:
            return await ctx.send(
                "That problem request is more than five minutes old. Start a fresh one with `!leet <easy|mid|hard> [topic]`.",
                ephemeral=not is_dm,
            )

        if difficulty is None:
            difficulty = previous["difficulty"]
            topic = previous["topic"]
            send_dm = previous.get("send_dm", False)
        else:
            topic, send_dm = _parse_dm_suffix(topic)
        return await self._send_problem(
            ctx, difficulty, topic, exclude_slug=previous["slug"], send_dm=send_dm
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(LeetCode(bot))
