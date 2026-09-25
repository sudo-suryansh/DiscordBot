import unittest

import discord
from discord.ext import commands


EXTENSIONS = [
    "cogs.moderation",
    "cogs.automod",
    "cogs.utility",
    "cogs.admin",
    "cogs.help",
    "cogs.dotai",
    "cogs.power",
    "cogs.dsa",
    "cogs.dm_guard",
    "cogs.daily_tasks",
    "cogs.member_records",
]


class StartupSmokeTests(unittest.IsolatedAsyncioTestCase):
    async def test_all_extensions_load_and_unload_without_connecting(self):
        bot = commands.Bot(command_prefix="!", intents=discord.Intents.none(), help_command=None)
        loaded = []
        try:
            for extension in EXTENSIONS:
                await bot.load_extension(extension)
                loaded.append(extension)
            self.assertEqual(loaded, EXTENSIONS)
            self.assertIsNotNone(bot.get_cog("DailyTasks"))
            self.assertIsNotNone(bot.get_cog("DotAI"))
        finally:
            for extension in reversed(loaded):
                await bot.unload_extension(extension)
            await bot.close()


if __name__ == "__main__":
    unittest.main()
