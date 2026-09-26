# Dot — Discord DSA & Server Assistant

Dot is a Discord bot for coding communities. It brings together LeetCode practice, scheduled task plans, member progress, an AI assistant, moderation utilities, and server activity logs. Members can ask in natural language; administrators get guided task and configuration workflows.

> **At a glance:** ask Dot a question with `!dot`, fetch a problem with `!leet`, track a solution by posting an accepted-submission screenshot, or complete the daily task with `!done`.

## Contents

- [Features](#features)
- [Get started](#get-started)
- [First-time server setup](#first-time-server-setup)
- [Commands](#commands)
- [Dot, the assistant](#dot-the-assistant)
- [LeetCode practice](#leetcode-practice)
- [Daily task plans](#daily-task-plans)
- [Progress and achievements](#progress-and-achievements)
- [Moderation and automod](#moderation-and-automod)
- [Privacy and saved data](#privacy-and-saved-data)
- [Updates and releases](#updates-and-releases)
- [Development](#development)

## Features

- **A practical DSA assistant:** explain concepts, answer server questions, review code, look up current task details, and perform supported server actions with permission checks.
- **LeetCode on demand:** request random problems by difficulty/topic, fetch a problem by number, repeat a recent request, or ask Dot in ordinary language.
- **Daily practice plans:** schedule LeetCode or custom tasks for 1–365 days, with a timezone, send time, optional topic filters, task completion, and reminders.
- **Task management in conversation:** administrators can create, edit, or delete a named custom task for one plan day or an inclusive range. Dot asks a follow-up when required details are missing.
- **Member progress:** track completed task days and streaks, plus accepted LeetCode submissions recognized from screenshots.
- **Community utilities:** welcome and activity logs, server/member info, warnings, timeouts, kicks, channel controls, and configurable automod.
- **Persistent configuration:** per-server settings and activity data are saved locally as JSON and survive bot restarts.

## Get started

### Requirements

- Python 3.10 or newer
- A Discord application and bot
- A Groq API key for `!dot`, `!review`, and screenshot recognition

### Install and run

```bash
git clone <your-repository-url>
cd dot
python -m venv .venv
```

Activate the virtual environment, then install and configure the bot:

```bash
python -m pip install -r requirements.txt
```

Copy `.env.example` to `.env` and set the required values:

```dotenv
DISCORD_TOKEN=your-discord-bot-token
OWNER_ID=your-discord-user-id
GROQ_API_KEY=your-groq-api-key

# Optional: choose model IDs available to your Groq account.
GROQ_MODEL=openai/gpt-oss-120b
GROQ_VISION_MODEL=qwen/qwen3.8-27b

# Optional: sync slash commands to a development server immediately.
DEV_GUILD_ID=your-test-server-id
```

Keep `.env` private. Do not commit bot tokens, API keys, or live server data. Enable **Message Content Intent** and **Server Members Intent** in the Discord Developer Portal, install the bot with the `bot` and `applications.commands` scopes, then start it:

```bash
python bot.py
```

Give the bot only the Discord permissions its enabled features need. Common permissions include View Channels, Send Messages, Embed Links, Read Message History, Manage Messages, Moderate Members, Kick Members, Manage Channels, Manage Roles, and Attach Files. Some features need only a subset. The bot's role must be above members/roles it moderates and above roles it edits.

## First-time server setup

1. Invite the bot and confirm its role and permissions.
2. An existing Discord Administrator runs `!setchannel commands #bot-commands` (or `/setchannel`) to enable `!dot` and `!review`. Add more channels with `!addcommandchannel`.
3. Set up channels with recognizable names (`welcome`, `logs`, `mod-commands`, `kicks-bans-mutes`, `automod`, `updates`, `achievements`) or assign them explicitly using `/setchannel`.
4. Configure a LeetCode problem channel with `!setprobchannel #dsa-problems` if you want problem requests posted to a dedicated channel.
5. Optionally configure a daily task plan with `/tasksetup` and a solution screenshot channel with `/setchannel achievements #achievements`.
6. Use `!channels` to review the active channel routing and `!help` to open Dot's interactive introduction.

Dot auto-detects several channels by name if no explicit channel is saved. Explicit settings take precedence. `!channels` shows the detected or configured routes.

## Commands

Most commands are available as both prefix commands (`!command`) and slash commands (`/command`). A few owner or task-form commands are prefix-only or slash-only as noted. In direct messages, supported commands can be typed without `!`.

### Everyday commands

| Command | What it does |
| --- | --- |
| `!help` | Opens the interactive guide and command tour. |
| `!ping` | Shows bot latency. |
| `!serverinfo` | Shows basic information about the current server. |
| `!userinfo [@member]` | Shows Discord account/server details and saved progress where available. |
| `!dot <question>` | Ask Dot about coding, DSA, LeetCode, tasks, member records, server channels, or supported actions. |
| `!review <code>` | Ask Dot for a code review focused on bugs, edge cases, and complexity. |
| `!leet <easy|mid|hard|number> [topic] [dm]` | Fetch a random topic-filtered problem or a specific LeetCode problem. |
| `!another [difficulty] [topic] [dm]` | Get another problem, repeating the last settings when no options are given. |
| `!done` | Mark today's task complete in the configured task channel. |
| `!version` | Show the running version and last announced version. |

### Server configuration

| Command | Access | What it does |
| --- | --- | --- |
| `!setchannel <type> #channel` | Administrator | Route a feature such as `commands`, `welcome`, `logs`, `modlog`, `kickban`, `automod`, `updates`, `problem`, or `achievements`. |
| `!channels` | Members | Show current channel routes. |
| `!setwelcome #channel` / `!welcomechannel` | Administrator / members | Set or view the welcome channel. |
| `!setprobchannel #channel` | Administrator | Set the destination for LeetCode problem requests. |
| `!addcommandchannel #channel` / `!removecommandchannel #channel` | Administrator | Allow or disallow Dot and code review commands in a channel. |
| `!setchannelpurpose #channel <purpose>` / `!clearchannelpurpose #channel` | Administrator | Save or clear a short channel description Dot can use when answering routing questions. |
| `!setadminrole @role` / `!revokeadminrole` / `!adminrole` | Administrator | Grant, revoke, or inspect the configured admin role. See the security note below. |
| `!synccommands` | Bot owner | Sync slash commands; useful after changing commands during development. |

> **Important:** `!setadminrole` grants the selected Discord role the platform's real **Administrator** permission. Anyone with that role can manage the whole server, independent of the bot. Assign it only to a trusted role. The bot needs Manage Roles, and its role must be positioned above the selected role. `!revokeadminrole` removes that Administrator permission from the currently configured role.

### Moderation

These commands require Discord Administrator permission or the configured admin role, except where Discord's own permission checks also apply. The bot itself must have the relevant permission and role position.

| Command | What it does |
| --- | --- |
| `!kick @member [reason]` | Remove a member from the server. |
| `!mute @member <minutes> [reason]` | Apply a Discord timeout. |
| `!unmute @member [reason]` | Remove a timeout. |
| `!warn @member [reason]` | Record a warning. |
| `!warnings @member` | View recorded warnings. |
| `!clearwarns @member` | Clear recorded warnings. |
| `!clear <amount>` | Delete up to 100 recent messages from the current channel. |
| `!lock [#channel] [reason]` / `!unlock [#channel] [reason]` | Lock or unlock a channel for `@everyone`. |
| `!slowmode <seconds> [#channel]` | Set a channel slowmode; `0` turns it off. |

### Automod

Automod is enabled by default with lenient starting limits. Administrators and the bot are exempt from its message checks.

| Command | What it does |
| --- | --- |
| `!automod` | Show the current settings. |
| `!automod toggle` | Enable or disable automod. |
| `!automod spamlimit <count> <seconds>` | Set the message-flood threshold. Defaults: 5 messages in 5 seconds. |
| `!automod mentionlimit <max>` | Set the maximum mentions allowed in one message. Default: 5. |
| `!automod mutetime <minutes>` | Set the timeout length for detected flooding. Default: 5 minutes. |
| `!automod invites <on|off>` | Enable or disable Discord invite-link blocking. |

## Dot, the assistant

Ask naturally; for example:

```text
!dot explain binary search with a small example
!dot what is today's task?
!dot fetch LeetCode problem 42
!dot what's my task streak?
!dot how many problems has @member solved?
!dot add "Graph practice" with instructions "Solve one graph traversal problem" on days 3 through 9
!dot edit "Graph practice" on days 3-9 to "Graph BFS"
!dot delete "Graph BFS" from days 3-9
```

Dot's capabilities include:

- Explain programming and DSA concepts and answer follow-up questions.
- Review submitted code for likely bugs, edge cases, and complexity.
- Look up a member's current Discord name, username, roles, account creation date, and server join date.
- Report saved task completion totals and task streaks, plus recorded solved-problem totals/titles and LeetCode posting streaks.
- Answer today's task and channel-purpose questions from configured/saved data.
- Fetch LeetCode problems via ordinary language, including exact problem numbers.
- For Administrators: post messages, send DMs, manage supported moderation actions, open task setup, create today's or tomorrow's task, and manage named custom tasks over plan-day ranges.

### Facts, permissions, and clarification

- Personal/member details are answered from Discord or local records. Dot reports when information is missing; it must not invent a streak, name, profile, or other saved fact.
- Mention the member you mean when asking about someone else. If Dot cannot identify the member unambiguously, it asks you to clarify.
- Server actions are limited to supported tools. Dot checks requester authorization and the bot's Discord permissions, and reports a failure instead of claiming an action succeeded.
- Anyone can ask Dot to DM themselves. Sending a DM to another member is Administrator-only.
- For task changes, Dot asks for missing operation, day/range, task name, title, or instructions before acting. Day ranges are inclusive. Editing a posted task updates its post and restarts its completion/reminder tracking.
- Add `!dm` as a standalone marker in a `!dot` question to receive its reply privately, for example `!dot explain binary search !dm`.

### Personalization and usage

- Dot's lightweight personalization uses aggregate tone counters from direct `!dot` interactions, not saved message text, and adds no extra model calls.
- `!dot erase my memory` or `!forgetme` clears Dot personalization and recent conversation context. It does not delete task completions or LeetCode records.
- `!dotstats` shows AI usage totals, top askers, and busiest hour since the bot last restarted.
- `!limits` is bot-owner-only and shows remaining Groq quota information from the last request.
- `!savage on|off` lets an Administrator choose Dot's response tone for that server.

## LeetCode practice

- `!leet easy arrays`, `!leet mid graph`, or `!leet hard` gets a random problem at the requested difficulty and optional topic.
- `!leet 20` fetches a specific problem by number. Premium-only problems are not posted.
- Add `dm` to also receive a private copy: `!leet 20 dm` or `!leet mid graph dm`.
- `!another` repeats the previous difficulty, topic, and delivery preference. `!another hard trees` changes the options.
- `/leet` and `/another` provide slash-command forms with interactive options. Both also work in direct messages.
- Natural language also works: `!dot give me an easy graph problem` or `!dot fetch LeetCode problem 42`.
- Problem content and tags are fetched from LeetCode. The configured problem channel is used for server requests; a server request stays in-channel unless `dm` is requested.
- Successful `!leet` and `!another` requests have a 30-second cooldown. `!another` is available for five minutes after the previous problem.

## Daily task plans

### Start a plan

An Administrator can run `/tasksetup` and use the interactive wizard, or provide the settings directly:

```text
/tasksetup channel:#daily-tasks days:30 send_time:09:00 timezone_name:Asia/Kolkata topics:arrays,graphs
```

Plans support 1–365 consecutive days, a send time and IANA timezone. The default timezone is `Asia/Kolkata`; the default LeetCode progression is 7 Easy days, then 7 Medium days, then Hard. Previously sent problems are excluded from future picks. Optionally set the Easy and Medium stage lengths with `!taskstages <easy-days> <medium-days>` before starting a plan.

For a plan made only from administrator-written work, use `/taskcustomplan` or select **Custom tasks** in the setup wizard. `/taskadd` opens a form for adding tasks; the prefix form is:

```text
!taskadd <day> Title | instructions | topic1, topic2 | optional URL
```

Plans can contain up to four custom tasks per day. Custom tasks can also be combined with LeetCode plans.

### Manage, complete, and cancel

- Use `!taskstatus` to see the active schedule.
- Administrators can ask `!dot` to create, edit, or delete a named custom task on one day or an inclusive range. Examples are shown in the [Dot examples](#dot-the-assistant). A range may be one day, a week, or any number of days inside the plan.
- Dot asks for missing information before making a change. It checks that matching tasks exist across the requested range and updates existing posts when possible.
- Use `!done` in the configured task channel to complete today's task. Repeating the command reports that the task was already recorded.
- Members who can view the task channel receive one DM reminder six hours after posting if they have not completed the task.
- Use `/taskstop` to select days to cancel or stop the remaining schedule. Dot also understands requests such as `!dot cancel today's task`, `!dot cancel days 3 and 4`, and `!dot stop all remaining tasks`.
- Cancelling a task day stops reminders and prevents cancelled work from being treated as the active task. The task plan and question history persist across restarts.

## Progress and achievements

- Each successful `!done` records a task day and updates the member's current and best task streak.
- Configure the achievement channel with `/setchannel achievements #achievements`. Members can post screenshots of accepted LeetCode submissions there.
- Dot uses the configured Groq vision model to recognize clearly readable accepted submissions. It counts distinct problems, ignores duplicate images and repeat problems, and tracks posting streaks. Unclear or unidentifiable screenshots are not counted as confirmed solutions.
- `!userinfo` and `!userinfo @member` show account details, task-day totals and streaks, unique solved problems, and solution-posting streaks in the server.
- `!dot what's my streak?` or `!dot how many problems has @member solved?` asks about the saved records directly.

## Welcome, logs, and update announcements

When a member joins, Dot can post a welcome, send the interactive introduction by DM, and audit-log the join. Leaves go to the logs channel. Moderation and configuration actions are logged to the relevant configured channel where available. The bot also posts release notes in the updates channel after a version bump.

Channel auto-detection recognizes names such as `welcome`, `logs`, `mod-commands`, `kicks-bans-mutes`, `automod`, `updates`, and `achievements`. Configure exact destinations with `!setchannel`, or review them with `!channels`. Dot can use a channel's name/category/topic and an optional administrator-written purpose to answer questions about where messages belong.

## Privacy and saved data

Dot stores server configuration, schedules, task completion records, warnings, and bot/update state in local JSON files under `data/`. Exact files are created as features are used. Keep `.env` and live `data/` private and out of public commits; keep backups of `data/` if you need to preserve progress when moving hosts.

Member records include Discord IDs, available name snapshots, completed task dates, and confirmed LeetCode solution details. Dot does not collect arbitrary biographies, schools, birthdays, or locations. Erasing Dot memory only removes personalization and recent Dot chat context; it does not erase activity records. Treat the local `data/` directory as private operational data.

## Updates and releases

`version.py` contains `VERSION` and the version-keyed `CHANGELOG`. Add a new version and its user-facing notes when preparing a release. On startup, Dot posts the matching changelog to each server's updates channel if that version has not been announced yet. The bot owner can use `!checkupdate` to force a resend and see delivery results. `!version` reports the running and last-announced versions.

## Development

```bash
python -m pip install -r requirements.txt
python -m unittest discover -v
```

The tests are offline and do not connect to Discord. To run the optional live intent evaluation, set `GROQ_API_KEY` and run `python -m tests.run_dot_eval`; its Discord action tools are mocked.

Useful project layout:

```text
bot.py                 Discord bot entry point and extension loading
cogs/                  Commands and feature modules
utils/                 Configuration, JSON storage, channel routing, and records
tests/                 Offline regression tests and intent evaluation data
data/                  Runtime JSON data (created automatically; keep private)
.env.example           Environment-variable template
requirements.txt       Python dependencies
version.py             Running version and update announcement notes
```

## Owner controls

The bot owner can use `!shutdown [reason]` in a direct message to pause commands and announce the reason in each configured updates channel. `!start` resumes service and announces that the bot is back. Set `OWNER_ID` in `.env` to explicitly identify the owner. `!reset [@user]` is also owner-only in DMs and clears that user's DM command cooldown/lockout.
