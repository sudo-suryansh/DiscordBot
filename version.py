# Bump VERSION and add a CHANGELOG entry every time you make a change you
# want announced. On the next restart, the bot compares VERSION against the
# last version it announced (stored in data/state.json) and, if it's new,
# posts the changelog entry below to each server's #updates channel
# automatically — no manual command needed.

VERSION = "2.18.0"

CHANGELOG = {
    "1.1.0": [
        "Added a configurable automod system: message-flood, mass-mention, and invite-link protection (`/automod`)",
        "Bot output is now routed into dedicated channels (mod-commands, kicks-bans-mutes, logs, malcious-activity, updates) instead of dumping everything into 1-2 channels",
        "Member-leave messages now go to #logs instead of #welcome; joins are now also logged there for an audit trail",
        "Added `/setchannel` and `/channels` to point each feature at whichever channel you want, per server",
    ],
    "1.2.0": [
        "Redesigned every log embed — avatars, inline fields, and an emoji per action instead of plain stacked text",
        "Added `/version` to check the running version and `/checkupdate` (owner-only) to manually resend the update announcement with a diagnostic report",
        "Fixed a bug where a failed #updates announcement (e.g. missing Send Messages permission) failed completely silently",
    ],
    "1.3.0": [
        "Added /leet to send a random LeetCode problem by difficulty and optional topic, with its statement and learning topics",
        "Added /setprobchannel so Administrators can choose where requested problems are posted",
    ],
    "1.4.0": [
        "Redesigned LeetCode problem cards with clearer sections, learning outcomes, topic tags, and a direct solve button",
        "Added /another to repeat the last difficulty and topic after a five-minute cooldown, or choose new ones",
    ],
    "1.5.0": [
        "Problem cards now display an illustration when one is included in LeetCode's statement",
        "LeetCode requests can now be made in direct messages; private requests stay in DMs, and !another keeps working when switching between DMs and the server",
    ],
    "1.6.0": [
        "Added a 30-second cooldown between all problem requests, regardless of whether /leet or /another was used",
        "Limited /another to the five-minute window after the last problem; use /leet to start a new request after it expires",
    ],
    "1.7.0": [
        "Enabled lightweight bot commands in DMs with per-user 20-second cooldowns, and LeetCode requests with 30-second cooldowns",
        "Added a one-hour DM spam lockout after more than 10 messages or commands in one minute, with a warning before ignoring further DMs",
    ],
    "1.8.0": [
        "DM commands can now be typed without a prefix while retaining ! command support",
        "Added owner-only !reset in DMs to clear only the owner's own cooldown and DM spam lockout",
    ],
    "1.9.0": [
        "Extended the owner-only DM !reset command to clear cooldowns and lockouts for a mentioned user",
    ],
    "2.0.0": [
        "Reworked owner-only DM shutdown to announce its reason in each server's updates channel",
        "Paused bot commands, automod, and join/leave activity during shutdown while preserving the owner's DM-only !start recovery command",
    ],
    "2.1.0": [
        "LeetCode problem requests in servers are now channel-only by default; append dm to also send the problem privately",
        "Bare /another repeats the previous problem's DM delivery preference",
    ],
    "2.2.0": [
        "Added exact LeetCode problem-number lookup with optional DM delivery",
        "Premium problem numbers now receive a direct notice instead of being posted as regular problems",
    ],
    "2.3.0": [
        "Bot now posts a back-online notice in each server's updates channel when the owner resumes it with !start",
    ],
    "2.4.0": [
        "Added `!dot <question>`: ask the AI in the channel an admin sets with `/setchannel commands`",
    ],
    "2.5.0": [
        "Added `/limits` (owner-only): view remaining Groq API quota after the last `!dot`/`!review` use",
        "Added `/savage on|off` (admin-only): toggle Dot's roast personality for this server",
        "Added `!review <code>`: get an AI code review — bugs, edge cases, and complexity, hints first",
        "Added `!dotstats`: see total AI questions asked, top askers, and the busiest hour",
    ],
    "2.6.0": [
        "Added `/addcommandchannel` and `/removecommandchannel` so Dot's AI commands can be enabled in multiple channels",
    ],
    "2.7.0": [
        "Updated Dot's AI instructions to describe only features the bot actually provides",
    ],
    "2.8.0": [
        "Added the `!dm` marker to send `!dot` answers to the requester by direct message",
    ],
    "2.9.0": [
        "Added scheduled daily LeetCode tasks with a no-repeat question history, `!done` tracking, and six-hour DM reminders",
    ],
    "2.10.0": [
        "Made LeetCode difficulty stage lengths configurable and added fully custom daily task plans",
        "Dot now receives the current daily task and its topics as context for `!dot` questions",
    ],
    "2.11.0": [
        "Simplified task setup, added optional multi-topic LeetCode filters and a form for custom tasks",
        "Prevented overlapping schedules and bundled custom work with running LeetCode plans",
    ],
    "2.12.0": [
        "Added a tap-through setup wizard for channels, plan type, duration, stages, time, timezone, and optional topics",
        "Added a day picker and support for up to four custom tasks on each day",
    ],
    "2.13.0": [
        "Made !dot an interactive assistant for approved, permission-checked Discord actions, including channel posts, moderation, channel locks, message cleanup, and private task delivery",
        "Improved custom-task form error reporting and timezone fallback when saving tasks",
    ],
    "2.14.0": [
        "Expanded Dot's natural-language actions to send direct messages and remove member timeouts",
        "Passed verified admin status into Dot's AI context and made action replies concise and consistent",
    ],
    "2.15.0": [
        "Expanded Dot's admin tools to warnings, warning cleanup, and channel slowmode",
        "Tightened natural-language action handling so Dot uses available tools instead of making up refusals",
    ],
    "2.16.0": [
        "Dot now answers direct questions about today's task from the saved local-date schedule, or clearly reports when no task is posted",
        "Added an admin-only natural-language lookup for a member's recorded warnings",
    ],
    "2.17.0": [
        "Changed /taskstop into a task-day picker with selected-day cancellation or stopping all remaining tasks",
        "Added admin-only natural-language task cancellation and ensured cancellations stop reminders and hide cancelled tasks from Dot and !done",
    ],
    "2.18.0": [
        "Dot now uses server channel names, categories, topics, configured bot roles, and admin-written channel purposes to answer channel questions and route channel actions",
        "Added Administrator-only !setchannelpurpose and !clearchannelpurpose commands",
    ],
    # "1.3.0": ["next change here"],
}
