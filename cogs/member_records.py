"""Achievement screenshot classification and member activity tracking."""

import base64
from datetime import datetime, timezone
import hashlib
import json
import logging
import os
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import discord
from discord.ext import commands

from utils.config import get_guild_config
from utils.member_records import (
    has_seen_screenshot, record_non_leetcode_image, record_solution,
)

logger = logging.getLogger(__name__)
MAX_IMAGE_BYTES = 8 * 1024 * 1024
VISION_MODEL = os.getenv("GROQ_VISION_MODEL", "qwen/qwen3.8-27b")
IMAGE_MIMES = {"image/jpeg", "image/png", "image/webp", "image/gif"}


class MemberRecords(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def _classify(self, client, mime, image_bytes):
        encoded = base64.b64encode(image_bytes).decode("ascii")
        response = await client.chat.completions.create(
            model=VISION_MODEL,
            temperature=0,
            max_completion_tokens=180,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": (
                    'Classify the image for an achievement tracker. Return JSON only with keys '
                    '"leetcode" (boolean), "solved" (boolean), "title" (string), "slug" (string). '
                    'leetcode=true only when visible evidence clearly shows LeetCode. solved=true only '
                    'when the screenshot clearly shows an accepted/successful submission, not merely '
                    'code or a problem page. Use an empty slug if not readable. Do not guess.'
                )},
                {"role": "user", "content": [
                    {"type": "text", "text": "Does this image clearly prove a LeetCode problem was solved?"},
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{encoded}"}},
                ]},
            ],
        )
        text = response.choices[0].message.content
        result = json.loads(text)
        return result if isinstance(result, dict) else {}

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot or not message.attachments:
            return
        cfg = get_guild_config(message.guild.id)
        if message.channel.id != cfg.get("achievements_channel_id"):
            return
        ai = self.bot.get_cog("DotAI")
        client = getattr(ai, "client", None)
        for attachment in message.attachments:
            mime = (attachment.content_type or "").split(";", 1)[0].lower()
            if mime not in IMAGE_MIMES or attachment.size > MAX_IMAGE_BYTES:
                continue
            try:
                image = await attachment.read(use_cached=True)
                digest = hashlib.sha256(image).hexdigest()
                if has_seen_screenshot(message.guild.id, message.author.id, digest):
                    continue
                if client is None:
                    logger.warning("Cannot classify achievement screenshot: Groq AI is not configured")
                    continue
                result = await self._classify(client, mime, image)
                if result.get("leetcode") is not True or result.get("solved") is not True:
                    record_non_leetcode_image(message.guild.id, message.author.id, digest, message.author.name, message.author.display_name)
                    continue
                title = str(result.get("title") or "").strip()
                slug = str(result.get("slug") or "").strip()
                if not title and not slug:
                    record_non_leetcode_image(message.guild.id, message.author.id, digest, message.author.name, message.author.display_name)
                    continue
                try:
                    day = datetime.now(ZoneInfo(cfg.get("daily_task_timezone", "UTC"))).date().isoformat()
                except (ZoneInfoNotFoundError, TypeError):
                    day = datetime.now(timezone.utc).date().isoformat()
                is_new, _new_day = record_solution(
                    message.guild.id, message.author.id, day, digest,
                    title or slug, slug or None,
                    username=message.author.name, display_name=message.author.display_name,
                )
                if is_new:
                    from utils.member_records import get_member_record
                    record = get_member_record(message.guild.id, message.author.id)
                    await message.reply(
                        f"✅ LeetCode solution recorded for {message.author.mention}. "
                        f"That’s **{record['questions_solved']}** unique question(s) solved so far.",
                        mention_author=False,
                        allowed_mentions=discord.AllowedMentions.none(),
                    )
            except Exception:
                logger.exception("Failed to classify achievement screenshot in guild %s", message.guild.id)


async def setup(bot: commands.Bot):
    await bot.add_cog(MemberRecords(bot))
