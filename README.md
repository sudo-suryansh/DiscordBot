# DSA Server Bot

## Structure
```
bot.py                 # entry point — loads cogs, starts the bot, announces updates
version.py              # bump this + add a changelog entry whenever you ship a change
cogs/
  moderation.py          # kick, mute, unmute, warn, warnings, clearwarns, clear, lock, unlock, slowmode
  automod.py              # NEW — configurable anti-spam (flooding, mass mentions, invite links)
  admin.py                # !setadminrole, !setwelcome, !setchannel, !channels — config, Administrator-only
  utility.py               # ping, serverinfo, userinfo, welcome/leave events
  dsa.py                   # LeetCode problem picker and problem-channel setup
utils/
  storage.py              # JSON-backed warning storage
  config.py                # JSON-backed per-server config (admin role, channels, automod settings)
  channels.py              # NEW — resolves each feature to a channel (configured, or auto-detected by name)
  state.py                  # NEW — tracks which bot version was last announced
  checks.py                # is_mod() — the permission gate mod commands use
data/
  warnings.json           # created automatically
  config.json              # created automatically
  state.json                # created automatically
.env                    # your actual secrets (not committed)
.env.example            # template for required env vars
requirements.txt
```

## Setup
1. `pip install -r requirements.txt`
2. Copy `.env.example` to `.env` and fill in `DISCORD_TOKEN`
3. Enable **Message Content Intent** and **Server Members Intent** in the Discord Developer Portal (Bot tab)
4. `python bot.py`
5. In your server, an Administrator runs:
   - `!setadminrole @Moderator` — whoever has this role can now use kick/mute/warn/clear
   - Nothing else is required — every log channel below is auto-detected by name. Use `!channels` to see what it found, and `!setchannel` to override any of them.

## Channel routing
The bot no longer dumps everything into one or two channels. Each feature below is auto-detected by channel name (case-insensitive substring match), so it works with zero setup if your channel names look like the ones in your server:

| Feature | Auto-detected from a channel name containing... | What goes there |
|---|---|---|
| `welcome` | `welcome` | Public join message + the bot's DM to new members |
| `logs` | `logs` / `log` | Member joins (audit) and **leaves** (moved out of #welcome) |
| `modlog` | `mod-commands` | warn / clearwarns / clear / lock / unlock / slowmode, plus admin-config changes (setadminrole etc.) |
| `kickban` | `kicks-bans-mutes` | kick / mute / unmute |
| `automod` | `malcious-activity` (also matches `malicious-activity`) | Automod flags (spam, mass mentions, invite links) |
| `updates` | `updates` | Version/changelog announcements (see below) |

To point a feature at a specific channel instead of relying on auto-detection:
```
!setchannel modlog #my-custom-modlog
```
Check what's currently active any time with `!channels`.

Set the channel for requested LeetCode problems with `!setprobchannel #dsa-problems` (Administrator only).

## Automod (new)
Lightweight and intentionally lenient — it's meant to catch obvious spam, not police normal chatting. Mods/admins and the bot itself are always exempt.

- **Message flooding** — more than N messages in a short window gets a timeout + a flag in the automod channel (default: 5 messages / 5 seconds → 5 minute timeout)
- **Mass mentions** — a message pinging more than N users/roles gets deleted + flagged (default: 5)
- **Invite links** — `discord.gg/...` links get deleted + flagged (default: on)

Configure with `!automod` (shows current settings) and:
- `!automod toggle` — turn it fully on/off
- `!automod spamlimit <count> <seconds>`
- `!automod mentionlimit <max>`
- `!automod mutetime <minutes>`
- `!automod invites <on/off>`

## Update announcements (new)
Bump `VERSION` in `version.py` and add a bullet list under it in `CHANGELOG` whenever you ship a change, then restart the bot. On startup it compares the new version against the last one it announced and, if different, posts the changelog to the `updates` channel automatically — no manual command needed.

## Who can do what
- **`!setadminrole @role`** — locked to real Discord **Administrator** permission only, and it does something significant: it grants that role **real server Administrator permission** via Discord itself (not just bot-command access). Anyone holding that role can then do anything in the server — ban, delete channels, change permissions — whether or not the bot is even online. Use `!revokeadminrole` to undo it (removes the Administrator permission from the role and clears the setting).
- **`!setwelcome` / `!setchannel`** — also Administrator-only, just point features at channels, no permission changes.
- **`!kick`, `!mute`, `!unmute`, `!warn`, `!warnings`, `!clearwarns`, `!clear`, `!lock`, `!unlock`, `!slowmode`, `!automod ...`** — usable by real Administrators, which now includes anyone holding the configured admin role.
- Ban/unban were removed for now — easy to add back later if you want them.
- **Bot role position matters:** for `!setadminrole` to work, your bot's own role must sit *above* the target role in Server Settings → Roles. Discord won't let a bot grant permissions to a role above its own.

## Commands (prefix `!`, all also work as `/`)
**Moderation** (admin role or Administrator required)
- `!kick @user [reason]`
- `!mute @user <minutes> [reason]` — uses Discord's native timeout
- `!unmute @user [reason]`
- `!warn @user [reason]`
- `!warnings @user`
- `!clearwarns @user`
- `!clear <amount>` — bulk delete (max 100)
- `!lock` / `!unlock [#channel] [reason]`
- `!slowmode <seconds> [#channel]`

**Automod** (admin role or Administrator required)
- `!automod` — show settings
- `!automod toggle`
- `!automod spamlimit <count> <seconds>`
- `!automod mentionlimit <max>`
- `!automod mutetime <minutes>`
- `!automod invites <on/off>`

**Admin config** (Administrator only)
- `!setadminrole @role` — grants the role real Administrator permission
- `!revokeadminrole` — removes it
- `!adminrole` — show current admin role
- `!setwelcome #channel`
- `!setprobchannel #channel` — choose where LeetCode problems are posted
- `!setchannel <welcome|logs|modlog|kickban|automod|updates> #channel`
- `!channels` — show all current channel routing
- `!welcomechannel` — show current welcome channel

**Utility** (anyone)
- `!ping`
- `!serverinfo`
- `!userinfo [@user]`

**DSA practice** (anyone)
- `!leet <easy|mid|hard|number> [topic] [dm]` — choose a random problem by difficulty/topic, or fetch an exact LeetCode number, e.g. `!leet 20`. Add a final `dm` to also send it privately, e.g. `!leet 20 dm` or `!leet mid graph dm`.
- If the requested number is premium, the bot replies `bhadwe, question paid hai` instead of sending the problem.
- `!another` — within five minutes of your last problem, send another at the same difficulty, topic, and DM preference. `!another <easy|mid|hard> [topic] [dm]` lets you change them.
- `/leet` provides difficulty choices and an optional topic field; add `dm` at the end of the topic to also receive it privately. Problem statements come from LeetCode; learning topics are based on its problem tags.
- `/another` provides the same repeat and override options.
- Both commands work in the bot's DMs too. A direct DM request stays private; in a server, the problem is posted there by default and sent privately only when `dm` is requested.
- Every successful problem request (`!leet` or `!another`) starts a 30-second cooldown. After five minutes, start a new request with `!leet`; `!another` expires.
- DM commands such as `!ping`, `!userinfo`, `!version`, `!leet`, and `!another` have a 20-second gap for light commands and 30 seconds for problem fetches.
- More than 10 DM messages or commands within one minute triggers a one-hour DM lockout. The bot sends a notice first, then skips that user's DM message and command processing during the lockout. Discord still delivers gateway events to the bot.
- In a bot DM, you can type commands without `!`: `ping`, `leet mid graph`, or `another`. Prefix forms like `!ping` continue to work. Natural command parsing only activates when the first word is a supported DM command.
- The bot owner can send `!reset` in the bot DM to clear their own DM cooldown and lockout, or `!reset @user` to clear another user's. Set `OWNER_ID` to your Discord user ID in `.env`.
- The owner can send `!shutdown [reason]` in a DM to announce the pause in each server's updates channel and stop commands, automod, and join/leave messages. Only the owner can use `!start` in a DM to resume it; the bot posts a back-online notice to each updates channel.

## Adding the DSA question feature later
Add new command cogs following the same pattern (a `Cog` subclass + `async def setup(bot)`), then add them to `INITIAL_EXTENSIONS` in `bot.py`.
