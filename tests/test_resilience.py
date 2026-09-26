import asyncio
import json
import os
import tempfile
import unittest
from collections import defaultdict, deque
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import discord
from discord.ext import commands

from cogs import daily_tasks, dsa, dotai
from cogs.automod import AutoMod
from utils import json_store
from utils import member_records
from utils import member_memory
from utils import intro_receipts
from cogs.help import DotIntroView, Help, INTRO_PAGES, build_intro_embed


class JsonStoreTests(unittest.TestCase):
    def test_atomic_saves_keep_previous_valid_backup_and_recover_corruption(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "state.json")
            json_store.save_json(path, {"version": 1})
            json_store.save_json(path, {"version": 2})
            with open(path, "w", encoding="utf-8") as file:
                file.write('{"version":')

            recovered = json_store.load_json(path, {})

            self.assertEqual(recovered, {"version": 1})
            with open(path, encoding="utf-8") as file:
                self.assertEqual(json.load(file), {"version": 1})
            backups = [name for name in os.listdir(directory) if ".corrupt." in name]
            self.assertEqual(len(backups), 1)

    def test_malformed_primary_and_backup_returns_independent_default(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "state.json")
            for candidate in (path, path + ".bak"):
                with open(candidate, "w", encoding="utf-8") as file:
                    file.write("invalid")
            default = {"guilds": {}}
            loaded = json_store.load_json(path, default)
            loaded["guilds"]["1"] = {}
            self.assertEqual(default, {"guilds": {}})


class MemberRecordTests(unittest.TestCase):
    def test_dot_member_streak_uses_guild_task_timezone(self):
        guild = SimpleNamespace(id=10, members=[])
        requester = SimpleNamespace(id=20, display_name="Member", name="member")
        with patch.object(dotai, "get_guild_config", return_value={"daily_task_timezone": "Asia/Kolkata"}), \
             patch.object(dotai, "get_member_record", return_value={
                 "task_dates": ["2026-09-25"], "task_total": 1,
                 "task_streak": 1, "task_longest_streak": 1,
                 "solution_dates": [], "solutions": [], "questions_solved": 0,
                 "solution_streak": 0, "solution_longest_streak": 0,
             }) as get_record:
            with patch.object(dotai, "ZoneInfo", return_value=timezone.utc) as zone_info:
                answer = dotai._member_fact_answer(guild, requester, "what is my task streak?")

        self.assertIn("current task streak", answer)
        zone_info.assert_called_once_with("Asia/Kolkata")
        self.assertEqual(get_record.call_args.kwargs["today"], datetime.now(timezone.utc).date())

    def test_dot_progress_question_returns_saved_task_total(self):
        guild = SimpleNamespace(id=10, members=[])
        requester = SimpleNamespace(id=20, display_name="Member", name="member")
        record = {
            "task_dates": ["2026-09-24"], "task_total": 1,
            "task_streak": 0, "task_longest_streak": 1,
            "solution_dates": [], "solutions": [], "questions_solved": 0,
            "solution_streak": 0, "solution_longest_streak": 0,
        }
        with (
            patch.object(dotai, "get_guild_config", return_value={"daily_task_timezone": "UTC"}),
            patch.object(dotai, "ZoneInfo", return_value=timezone.utc),
            patch.object(dotai, "get_member_record", return_value=record),
        ):
            answer = dotai._member_fact_answer(guild, requester, "how is my progress?")
        self.assertIn("completed **1** distinct daily task days", answer)

    def test_dot_does_not_confuse_external_usernames_with_discord_identity(self):
        guild = SimpleNamespace(id=10, members=[])
        requester = SimpleNamespace(id=20, display_name="Member", name="member")
        answer = dotai._member_fact_answer(guild, requester, "what is my GitHub username?")
        self.assertIn("don't have a verified GitHub username", answer)
        self.assertNotIn("(username: **member**)", answer)

    def test_streaks_count_consecutive_calendar_days_only(self):
        current, longest = member_records.streak_for_dates(
            ["2026-09-20", "2026-09-21", "2026-09-23", "2026-09-24"],
            today=date(2026, 9, 25),
        )
        self.assertEqual((current, longest), (2, 2))

    def test_task_days_and_solutions_are_unique_and_persistent(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(member_records, "DATA_DIR", directory), \
             patch.object(member_records, "RECORDS_FILE", os.path.join(directory, "members.json")):
            member_records.record_task_completion(10, 20, "2026-09-24")
            member_records.record_task_completion(10, 20, "2026-09-24")
            self.assertEqual(member_records.record_solution(10, 20, "2026-09-24", "img1", "Two Sum", "two-sum"), (True, True))
            self.assertEqual(member_records.record_solution(10, 20, "2026-09-25", "img2", "Two Sum", "two-sum"), (False, True))
            self.assertEqual(member_records.record_solution(10, 20, "2026-09-25", "img2", "Two Sum", "two-sum"), (False, False))
            stats = member_records.get_member_record(10, 20)
            self.assertEqual(stats["task_total"], 1)
            self.assertEqual(stats["questions_solved"], 1)
            self.assertEqual(stats["solution_dates"], ["2026-09-24", "2026-09-25"])


class MemberMemoryTests(unittest.TestCase):
    def test_memory_is_aggregate_only_and_erase_preserves_activity(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(member_memory, "DATA_DIR", directory), \
             patch.object(member_memory, "MEMORY_FILE", os.path.join(directory, "memory.json")), \
             patch.object(member_records, "DATA_DIR", directory), \
             patch.object(member_records, "RECORDS_FILE", os.path.join(directory, "records.json")):
            member_memory.observe_interaction(1, 2, "please help me")
            member_memory.observe_interaction(1, 2, "could you explain this")
            member_memory.observe_interaction(1, 2, "thanks, another example")
            with open(member_memory.MEMORY_FILE, encoding="utf-8") as file:
                saved = file.read()
            self.assertNotIn("please help me", saved)
            self.assertEqual(member_memory.get_personalization(1, 2), "warm")

            member_records.record_task_completion(1, 2, "2026-09-25")
            self.assertTrue(member_memory.erase_personalization(1, 2))
            self.assertIsNone(member_memory.get_personalization(1, 2))
            with open(member_memory.MEMORY_FILE + ".bak", encoding="utf-8") as file:
                self.assertNotIn('"2"', file.read())
            self.assertEqual(member_records.get_member_record(1, 2)["task_total"], 1)


class IntroTests(unittest.IsolatedAsyncioTestCase):
    async def test_intro_is_deduplicated_until_help_forces_a_resend(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(intro_receipts, "DATA_DIR", directory), \
             patch.object(intro_receipts, "RECEIPTS_FILE", os.path.join(directory, "receipts.json")):
            cog = Help(SimpleNamespace(guilds=[]))
            member = SimpleNamespace(id=77, send=AsyncMock())
            self.assertTrue(await cog.send_intro(member, guild_id=10))
            self.assertFalse(await cog.send_intro(member, guild_id=10))
            self.assertTrue(await cog.send_intro(member, guild_id=10, force=True))
            self.assertEqual(member.send.await_count, 2)
            self.assertTrue(intro_receipts.has_received(10, 77))

    def test_intro_pages_cover_core_features_and_have_interactive_navigation(self):
        self.assertEqual(len(INTRO_PAGES), 5)
        self.assertIn("Suryansh", build_intro_embed().description)
        self.assertTrue(any("streak" in text.casefold() for _title, text in INTRO_PAGES.values()))
        self.assertEqual(len(DotIntroView(77).children), 5)


class CancellationTests(unittest.IsolatedAsyncioTestCase):
    async def test_task_stop_picker_uses_unique_dates_for_day_zero_tasks(self):
        entries = [
            {"day": 0, "date": "2026-09-26", "posted": False, "label": "Tomorrow · Task A"},
            {"day": 0, "date": "2026-09-27", "posted": False, "label": "2026-09-27 · Task B"},
        ]
        view = daily_tasks.TaskStopView(Mock(), 123, 456, entries)
        selector = next(item for item in view.children if isinstance(item, daily_tasks._TaskStopDaySelect))
        self.assertEqual({option.value for option in selector.options}, {entry["date"] for entry in entries})
        self.assertEqual(len({option.value for option in selector.options}), 2)

    async def test_cancelling_one_date_does_not_cancel_another_standalone_task(self):
        cog = object.__new__(daily_tasks.DailyTasks)
        entries = [
            {"day": 0, "date": "2026-09-26", "posted": False, "label": "Tomorrow · Task A"},
            {"day": 0, "date": "2026-09-27", "posted": False, "label": "2026-09-27 · Task B"},
        ]
        cog.get_cancelable_task_days = Mock(return_value=entries)
        state = {"guilds": {"99": {"tasks": {entry["date"]: {} for entry in entries}}}}
        guild = SimpleNamespace(id=99, get_channel=lambda _channel_id: None)

        with patch.object(daily_tasks, "_load_state", return_value=state), \
             patch.object(daily_tasks, "_save_state") as save_state, \
             patch.object(daily_tasks, "get_guild_config", return_value={}):
            result = await cog._cancel_plan_days_locked(guild, ["2026-09-27"])

        self.assertNotIn("cancelled_at", state["guilds"]["99"]["tasks"]["2026-09-26"])
        self.assertIn("cancelled_at", state["guilds"]["99"]["tasks"]["2026-09-27"])
        save_state.assert_called_once_with(state)
        self.assertIn("2026-09-27", result)


class AutoModValidationTests(unittest.IsolatedAsyncioTestCase):
    async def test_invalid_spam_limits_do_not_persist(self):
        cog = object.__new__(AutoMod)
        ctx = SimpleNamespace(guild=SimpleNamespace(id=1), send=AsyncMock())
        with patch("cogs.automod.set_guild_value") as save:
            await AutoMod.automod_spamlimit.callback(cog, ctx, 0, 5)
        save.assert_not_called()
        ctx.send.assert_awaited_once()

    async def test_valid_automod_settings_persist(self):
        cog = object.__new__(AutoMod)
        ctx = SimpleNamespace(guild=SimpleNamespace(id=1), send=AsyncMock())
        with patch("cogs.automod.set_guild_value") as save:
            await AutoMod.automod_spamlimit.callback(cog, ctx, 6, 10)
        self.assertEqual(save.call_count, 2)

    async def test_invalid_timeout_and_mention_limits_do_not_persist(self):
        cog = object.__new__(AutoMod)
        ctx = SimpleNamespace(guild=SimpleNamespace(id=1), send=AsyncMock())
        with patch("cogs.automod.set_guild_value") as save:
            await AutoMod.automod_mutetime.callback(cog, ctx, 40321)
            await AutoMod.automod_mentionlimit.callback(cog, ctx, -1)
        save.assert_not_called()
        self.assertEqual(ctx.send.await_count, 2)


class IntentAndApiTests(unittest.TestCase):
    def test_memory_erase_phrases_are_local_and_explicit(self):
        self.assertTrue(dotai.is_memory_erase_request("erase my memory"))
        self.assertTrue(dotai.is_memory_erase_request("Please forget everything you know about me"))
        self.assertTrue(dotai.is_memory_erase_request("delete my behavioral memory"))
        self.assertFalse(dotai.is_memory_erase_request("how do I erase memory in Python?"))

    def test_today_task_lookup_recognizes_paraphrases_without_overmatching(self):
        self.assertTrue(dotai.is_today_task_lookup("What should I work on?"))
        self.assertTrue(dotai.is_today_task_lookup("Could you show today's LeetCode problem?"))
        self.assertTrue(dotai.is_today_task_lookup("which challenge do we have today"))
        self.assertFalse(dotai.is_today_task_lookup("How do I solve a graph problem?"))
        self.assertFalse(dotai.is_today_task_lookup("Cancel today's task"))

    def test_numbered_task_requests_parse_without_an_ai_call(self):
        parsed = dotai.parse_numbered_task_creation(
            "I want you to add a task to solve problem 1 of LeetCode and send the info in #tasks"
        )
        self.assertEqual(parsed, {"leetcode_number": 1, "channel": "#tasks"})
        self.assertIsNone(dotai.parse_numbered_task_creation("How do I add a task for LeetCode problem 1?"))
        self.assertFalse(dotai.should_offer_tools("Explain how LeetCode problem 1 works"))
        selected = dotai.tools_for_question("Please post a warning for @Sam")
        self.assertLess(len(selected), len(dotai.DOT_TOOLS))

    def test_natural_language_problem_request_bypasses_member_fact_lookup(self):
        guild = SimpleNamespace(id=1, members=[])
        requester = SimpleNamespace(id=2, display_name="Member", name="member")
        for question in (
            "Find me an easy LeetCode problem",
            "Can you recommend a graph question?",
            "Fetch LeetCode problem 42",
            "I want a medium graph LeetCode problem",
            "How do I solve a LeetCode problem?",
            "Why is my LeetCode solution timing out?",
            "How many LeetCode problems are there?",
        ):
            self.assertIsNone(dotai._member_fact_answer(guild, requester, question), question)
        self.assertFalse(dotai.is_natural_leetcode_lookup("How do I solve LeetCode problem 42?"))
        self.assertTrue(dotai.is_natural_leetcode_lookup("What is LeetCode problem 42?"))

    def test_natural_leetcode_parser_keeps_topics_from_casual_wording(self):
        self.assertEqual(
            dotai.parse_natural_leetcode_request("give me an easy graph LeetCode problem"),
            ("easy", "graph"),
        )
        self.assertEqual(
            dotai.parse_natural_leetcode_request("get a medium dynamic programming problem on LeetCode"),
            ("medium", "dynamic programming"),
        )
        self.assertEqual(
            dotai.parse_natural_leetcode_request("recommend me a dynamic programming LeetCode question"),
            ("mid", "dynamic programming"),
        )
        self.assertEqual(dotai.parse_natural_leetcode_request("fetch LeetCode problem number 42"), ("42", None))
        self.assertEqual(dotai.parse_natural_leetcode_request("fetch LeetCode 42"), ("42", None))

    def test_intent_router_matches_action_examples_and_ignores_quoted_commands(self):
        path = Path(__file__).parent / "evals" / "dot_tool_intents.json"
        cases = json.loads(path.read_text(encoding="utf-8"))
        for case in cases:
            expected = case["expected_tool"]
            available = {tool["function"]["name"] for tool in dotai.tools_for_question(case["text"])}
            if expected not in (None, "clarify", "direct_task_lookup"):
                self.assertIn(expected, available, case["text"])
            elif expected is None:
                self.assertFalse(dotai.should_offer_tools(case["text"]), case["text"])
        quoted = "Summarize this sentence: 'kick Ravi from the server'"
        self.assertFalse(dotai.should_offer_tools(quoted))
        self.assertEqual(dotai.tools_for_question(quoted), [])
        self.assertEqual(
            {tool["function"]["name"] for tool in dotai.tools_for_question("How many warnings does Maya have?")},
            {"read_member_warnings"},
        )

    def test_leetcode_response_shape_validation(self):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = b'{"data":{"questionList":{"data":[]}}}'
        with patch.object(dsa, "urlopen", return_value=response):
            data = dsa._fetch_json(dsa.LIST_QUERY, {})
        self.assertEqual(data["data"]["questionList"]["data"], [])

        response.read.return_value = b'{"data":{"questionList":null}}'
        with patch.object(dsa, "urlopen", return_value=response):
            with self.assertRaises(ValueError):
                dsa._fetch_json(dsa.LIST_QUERY, {})

    def test_numbered_problem_uses_minimal_problem_list_query(self):
        calls = []

        def fetch(query, variables):
            calls.append(query)
            if "questionList" in query:
                return {"data": {"questionList": {"data": [
                    {"questionFrontendId": "1", "titleSlug": "two-sum", "isPaidOnly": False},
                ]}}}
            return {"data": {"question": {
                "questionFrontendId": "1", "titleSlug": "two-sum", "title": "Two Sum",
                "content": "<p>Prompt</p>", "topicTags": [],
            }}}

        with patch.object(dsa, "_fetch_json", side_effect=fetch):
            problem = dsa._fetch_numbered_problem(1)
        self.assertEqual(problem["title"], "Two Sum")
        self.assertEqual(calls[0], dsa.NUMBER_LIST_QUERY)

    def test_ai_error_messages_cover_provider_failures(self):
        forbidden = discord.Forbidden.__new__(discord.Forbidden)
        Exception.__init__(forbidden, "denied")
        self.assertIn("permissions", __import__("bot")._error_message(forbidden))
        self.assertIn("API key", dotai._ai_service_error_message(401))
        self.assertIn("rate limiting", dotai._ai_service_error_message(429))
        self.assertIn("service", dotai._ai_service_error_message(503))

    def test_tool_arguments_reject_unsafe_types_and_extra_fields(self):
        with self.assertRaises(ValueError):
            dotai.validate_tool_arguments("set_channel_lock", {"channel": "general", "locked": "false"})
        with self.assertRaises(ValueError):
            dotai.validate_tool_arguments("timeout_member", {"member": "Ravi", "minutes": True})
        with self.assertRaises(ValueError):
            dotai.validate_tool_arguments("kick_member", {"member": "Ravi", "ban": True})
        self.assertEqual(
            dotai.validate_tool_arguments("set_channel_lock", {"channel": "general", "locked": False}),
            {"channel": "general", "locked": False},
        )

    def test_eval_corpus_has_valid_tool_labels_and_documented_schemas(self):
        path = Path(__file__).parent / "evals" / "dot_tool_intents.json"
        cases = json.loads(path.read_text(encoding="utf-8"))
        tool_names = {tool["function"]["name"] for tool in dotai.DOT_TOOLS}
        self.assertGreaterEqual(len(cases), 20)
        for case in cases:
            expected = case["expected_tool"]
            self.assertTrue(expected is None or expected in tool_names or expected in {"clarify", "direct_task_lookup"})
        for tool in dotai.DOT_TOOLS:
            name = tool["function"]["name"]
            self.assertGreater(len(dotai.TOOL_GUIDANCE[name]), 100)
            self.assertTrue(tool["function"]["description"])


class CooldownLogTests(unittest.IsolatedAsyncioTestCase):
    async def test_prefix_cooldown_is_a_normal_info_event_not_an_error(self):
        bot_module = __import__("bot")
        command = SimpleNamespace(qualified_name="dot")
        ctx = SimpleNamespace(
            command=command,
            author=SimpleNamespace(id=123),
            interaction=None,
            send=AsyncMock(),
        )
        error = commands.CommandOnCooldown(
            commands.Cooldown(1, 15), 2.65, commands.BucketType.user,
        )
        with patch.object(bot_module.logger, "info") as info, patch.object(bot_module.logger, "error") as error_log:
            await bot_module.on_command_error(ctx, error)
        info.assert_called_once()
        error_log.assert_not_called()
        self.assertIn("3s", ctx.send.await_args.args[0])


class ToolLoopTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _tool_call(call_id, name, arguments):
        return SimpleNamespace(id=call_id, function=SimpleNamespace(name=name, arguments=json.dumps(arguments)))

    @staticmethod
    def _completion(content=None, calls=None):
        message = SimpleNamespace(
            content=content,
            tool_calls=calls or [],
            model_dump=lambda **_kwargs: {"role": "assistant", "tool_calls": []},
        )
        return SimpleNamespace(headers={}, parse=lambda: SimpleNamespace(choices=[SimpleNamespace(message=message)]))

    async def _make_dot(self, responses, execute):
        async def create(**kwargs):
            self.requests.append(kwargs)
            item = responses.pop(0)
            if isinstance(item, Exception):
                raise item
            return item

        dot = object.__new__(dotai.DotAI)
        dot.model = "test-model"
        dot.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(with_raw_response=SimpleNamespace(create=create))))
        dot.slots = asyncio.Semaphore(1)
        dot.history = defaultdict(lambda: deque(maxlen=dotai.HISTORY_MESSAGES))
        dot.last_used = {}
        dot.store_limits = Mock()
        dot._execute_tool = execute
        return dot

    async def test_duplicate_calls_are_not_executed_twice_and_final_reply_is_returned(self):
        call_args = {"channel": "announcements", "message": "Meeting at 7"}
        duplicate_args = {"channel": "#ANNOUNCEMENTS", "message": "Meeting at 7"}
        calls = [self._tool_call("c1", "send_channel_message", call_args), self._tool_call("c2", "send_channel_message", duplicate_args)]
        self.requests = []
        execute = AsyncMock(return_value={"ok": True, "message": "Message posted."})
        dot = await self._make_dot([self._completion(calls=calls), self._completion(content="Posted in #announcements.")], execute)
        ctx = SimpleNamespace(guild=SimpleNamespace(id=1), author=SimpleNamespace(id=2))

        with patch.object(dotai.DotAI, "_is_admin", return_value=True):
            answer = await dot.ask((1, 2, "dot"), "Post this in announcements", "system", ctx)

        self.assertEqual(answer, "Posted in #announcements.")
        execute.assert_awaited_once()
        self.assertEqual([req["tool_choice"] for req in self.requests], ["auto", "auto"])

    async def test_non_admin_can_dm_self_but_not_another_member(self):
        dot = object.__new__(dotai.DotAI)
        author = SimpleNamespace(id=42, send=AsyncMock(), display_name="Requester")
        ctx = SimpleNamespace(guild=SimpleNamespace(), author=author)
        with patch.object(dotai.DotAI, "_is_admin", return_value=False):
            own = await dot._execute_tool(ctx, "send_direct_message", {"recipient": "<@42>", "message": "Hello me"})
            denied = await dot._execute_tool(ctx, "send_direct_message", {"recipient": "Sam", "message": "Hello Sam"})
        self.assertTrue(own["ok"])
        self.assertEqual(author.send.await_count, 1)
        self.assertFalse(denied["ok"])
        self.assertIn("Administrator", denied["message"])

    async def test_clear_numbered_task_intent_bypasses_groq(self):
        dot = object.__new__(dotai.DotAI)
        dot._execute_tool = AsyncMock(return_value={"ok": True, "message": "Posted LeetCode #1 in #tasks."})
        dot.record_usage = Mock()
        ctx = SimpleNamespace(
            guild=SimpleNamespace(id=1),
            author=SimpleNamespace(id=2),
            interaction=None,
            reply=AsyncMock(),
        )
        with patch.object(dotai, "observe_interaction"), patch.object(dotai, "is_today_task_lookup", return_value=False):
            await dotai.DotAI.dot.callback(
                dot, ctx,
                question="I want you to add a task to solve problem 1 of LeetCode and send the info in #tasks",
            )
        dot._execute_tool.assert_awaited_once_with(ctx, "create_task_today", {"leetcode_number": 1, "channel": "#tasks"})
        ctx.reply.assert_awaited_once()
        dot.record_usage.assert_called_once_with(1, 2, "dot")

    async def test_ai_failure_after_action_reports_confirmed_result(self):
        self.requests = []
        call = self._tool_call("c1", "send_channel_message", {"channel": "general", "message": "Hello"})
        execute = AsyncMock(return_value={"ok": True, "message": "Message posted in #general."})
        dot = await self._make_dot([self._completion(calls=[call]), RuntimeError("provider unavailable")], execute)
        ctx = SimpleNamespace(guild=SimpleNamespace(id=1), author=SimpleNamespace(id=2))

        with patch.object(dotai.DotAI, "_is_admin", return_value=True):
            answer = await dot.ask((1, 2, "dot"), "Post hello", "system", ctx)

        self.assertIn("Completed: Message posted in #general.", answer)
        self.assertIn("couldn't prepare a fuller reply", answer)

    async def test_failed_action_returns_result_without_another_ai_request(self):
        self.requests = []
        call = self._tool_call("c1", "create_task_today", {"leetcode_number": 1, "channel": "#tasks"})
        execute = AsyncMock(return_value={"ok": False, "message": "LeetCode is temporarily unavailable."})
        dot = await self._make_dot([self._completion(calls=[call]), self._completion(content="This should not be requested")], execute)
        ctx = SimpleNamespace(guild=SimpleNamespace(id=1), author=SimpleNamespace(id=2))

        with patch.object(dotai.DotAI, "_is_admin", return_value=True):
            answer = await dot.ask((1, 2, "dot"), "Add LeetCode problem 1 as a task in #tasks", "system", ctx)

        self.assertIn("LeetCode is temporarily unavailable", answer)
        self.assertEqual(len(self.requests), 1)

    async def test_malformed_ai_followup_still_reports_action_result(self):
        self.requests = []
        call = self._tool_call("c1", "send_channel_message", {"channel": "general", "message": "Hello"})
        malformed = SimpleNamespace(headers={}, parse=lambda: SimpleNamespace(choices=[]))
        execute = AsyncMock(return_value={"ok": True, "message": "Message posted in #general."})
        dot = await self._make_dot([self._completion(calls=[call]), malformed], execute)
        ctx = SimpleNamespace(guild=SimpleNamespace(id=1), author=SimpleNamespace(id=2))

        with patch.object(dotai.DotAI, "_is_admin", return_value=True):
            answer = await dot.ask((1, 2, "dot"), "Post hello", "system", ctx)

        self.assertIn("Message posted in #general", answer)
        self.assertIn("AI service didn't finish", answer)

    async def test_total_action_limit_is_enforced_across_one_model_message(self):
        self.requests = []
        calls = [
            self._tool_call(f"c{i}", "send_channel_message", {"channel": f"channel-{i}", "message": "hello"})
            for i in range(4)
        ]
        execute = AsyncMock(return_value={"ok": True, "message": "Posted."})
        dot = await self._make_dot([self._completion(calls=calls), self._completion(content="Three posts completed; the fourth exceeded the action limit.")], execute)
        ctx = SimpleNamespace(guild=SimpleNamespace(id=1), author=SimpleNamespace(id=2))

        with patch.object(dotai.DotAI, "_is_admin", return_value=True):
            answer = await dot.ask((1, 2, "dot"), "Post four messages", "system", ctx)

        self.assertIn("action limit", answer)
        self.assertEqual(execute.await_count, dotai.MAX_TOOL_ACTIONS)

    async def test_invalid_boolean_argument_never_reaches_tool_executor(self):
        self.requests = []
        call = self._tool_call("c1", "set_channel_lock", {"channel": "general", "locked": "false"})
        execute = AsyncMock(return_value={"ok": True, "message": "Unlocked."})
        dot = await self._make_dot([self._completion(calls=[call]), self._completion(content="I couldn't safely use that action.")], execute)
        ctx = SimpleNamespace(guild=SimpleNamespace(id=1), author=SimpleNamespace(id=2))

        with patch.object(dotai.DotAI, "_is_admin", return_value=True):
            answer = await dot.ask((1, 2, "dot"), "Unlock general", "system", ctx)

        self.assertIn("couldn't safely use", answer)
        execute.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
