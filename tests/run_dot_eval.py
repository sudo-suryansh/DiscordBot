"""Run the small intent corpus against the configured AI model with all tools mocked.

This makes provider calls but cannot send messages, moderate members, or edit tasks.
Run with: python -m tests.run_dot_eval
"""

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

from dotenv import load_dotenv

from cogs.dotai import DotAI, MILD_PROMPT, is_today_task_lookup


async def run():
    load_dotenv()
    dot = DotAI(SimpleNamespace())
    if dot.client is None:
        raise SystemExit("Set GROQ_API_KEY to run the live intent evaluation.")

    cases = json.loads((Path(__file__).parent / "evals" / "dot_tool_intents.json").read_text(encoding="utf-8"))
    failures = []
    try:
        for index, case in enumerate(cases, start=1):
            expected = case["expected_tool"]
            calls = []
            if expected == "direct_task_lookup":
                selected = "direct_task_lookup" if is_today_task_lookup(case["text"]) else None
            else:
                async def mock_execute(_ctx, name, _arguments):
                    calls.append((name, _arguments))
                    return {"ok": True, "message": "Evaluation action simulated successfully."}

                dot._execute_tool = mock_execute
                author = SimpleNamespace(id=index, guild_permissions=SimpleNamespace(administrator=True))
                ctx = SimpleNamespace(guild=SimpleNamespace(id=1), author=author)
                await dot.ask((1, index, "eval"), case["text"], MILD_PROMPT, ctx)
                selected = calls[0][0] if calls else None
            args_ok = True
            if case.get("expected_args") and calls:
                actual = next((arguments for name, arguments in calls if name == expected), {})
                args_ok = all(actual.get(key) == value for key, value in case["expected_args"].items())
            passed = selected == expected and args_ok
            suffix = "" if args_ok else f", expected_args={case['expected_args']!r}, actual_args={actual!r}"
            print(f"{'PASS' if passed else 'FAIL'} {index:02d}: expected={expected!r}, selected={selected!r}{suffix} — {case['text']}")
            if not passed:
                failures.append(index)
    finally:
        await dot.client.close()
    print(f"\n{len(cases) - len(failures)}/{len(cases)} cases passed")
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(run())
