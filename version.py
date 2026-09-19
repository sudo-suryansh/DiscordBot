# Bump VERSION and add a CHANGELOG entry every time you make a change you
# want announced. On the next restart, the bot compares VERSION against the
# last version it announced (stored in data/state.json) and, if it's new,
# posts the changelog entry below to each server's #updates channel
# automatically — no manual command needed.

VERSION = "1.2.0"

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
    # "1.3.0": ["next change here"],
}
