# DSA Server Bot

## Structure
```
bot.py                 # entry point — loads cogs, starts the bot
cogs/
  moderation.py          # kick, mute, unmute, warn, warnings, clearwarns, clear
  admin.py                # !setadminrole, !setwelcome — config commands, Administrator-only
  utility.py               # ping, serverinfo, userinfo, welcome/leave messages
utils/
  storage.py              # JSON-backed warning storage
  config.py                # JSON-backed per-server config (admin role, welcome channel)
  checks.py                # is_mod() — the permission gate mod commands use
data/
  warnings.json           # created automatically
  config.json              # created automatically
.env                    # your actual secrets (not committed)
.env.example            # template for required env vars
requirements.txt
```

## Setup
1. `pip install -r requirements.txt`
2. Copy `.env.example` to `.env` and fill in `DISCORD_TOKEN` (and optionally `MOD_LOG_CHANNEL_ID`)
3. Enable **Message Content Intent** and **Server Members Intent** in the Discord Developer Portal (Bot tab)
4. `python bot.py`
5. In your server, an Administrator runs:
   - `!setadminrole @Moderator` — whoever has this role can now use kick/mute/warn/clear
   - `!setwelcome #welcome😃` — sets where join/leave messages go (optional — see below)

## Who can do what
- **`!setadminrole @role`** — locked to real Discord **Administrator** permission only, and it does something significant: it grants that role **real server Administrator permission** via Discord itself (not just bot-command access). Anyone holding that role can then do anything in the server — ban, delete channels, change permissions — whether or not the bot is even online. Use `!revokeadminrole` to undo it (removes the Administrator permission from the role and clears the setting).
- **`!setwelcome`** — also Administrator-only, just sets the welcome channel, no permission changes.
- **`!kick`, `!mute`, `!unmute`, `!warn`, `!warnings`, `!clearwarns`, `!clear`** — usable by real Administrators, which now includes anyone holding the configured admin role.
- Ban/unban were removed for now — easy to add back later if you want them.
- **Bot role position matters:** for `!setadminrole` to work, your bot's own role must sit *above* the target role in Server Settings → Roles. Discord won't let a bot grant permissions to a role above its own.

## Welcome messages
- If you run `!setwelcome #channel`, that channel is used.
- If you don't, the bot auto-detects any text channel with "welcome" in its name (e.g. `#welcome😃`) at join/leave time — no setup needed if you already have a channel named like that.
- Check what's active any time with `!welcomechannel`.

## Commands (prefix `!`)
**Moderation** (admin role or Administrator required)
- `!kick @user [reason]`
- `!mute @user <minutes> [reason]` — uses Discord's native timeout
- `!unmute @user [reason]`
- `!warn @user [reason]`
- `!warnings @user`
- `!clearwarns @user`
- `!clear <amount>` — bulk delete (max 100)

**Admin config** (Administrator only)
- `!setadminrole @role` — grants the role real Administrator permission
- `!revokeadminrole` — removes it
- `!adminrole` — show current admin role
- `!setwelcome #channel`
- `!welcomechannel` — show current welcome channel

**Utility** (anyone)
- `!ping`
- `!serverinfo`
- `!userinfo [@user]`

## Adding the DSA question feature later
Create `cogs/dsa.py` following the same pattern (a `Cog` subclass + `async def setup(bot)`), add `"cogs.dsa"` to `INITIAL_EXTENSIONS` in `bot.py`. No other files need to change.
