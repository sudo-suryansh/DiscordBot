from discord.ext import commands

from utils.config import get_guild_config


def is_mod():
    """
    Allows a command (prefix OR slash — hybrid commands share one check) only if
    the user:
      - has the real Discord 'Administrator' permission, OR
      - has the role configured as this server's admin role (via setadminrole)

    Real Administrator permission always works so a server owner can never
    lock themselves out. The configured role is what most mods will actually
    have day-to-day.
    """

    async def predicate(ctx: commands.Context) -> bool:
        if ctx.guild is None:
            return False

        if ctx.author.guild_permissions.administrator:
            return True

        cfg = get_guild_config(ctx.guild.id)
        role_id = cfg.get("admin_role_id")
        if role_id is None:
            # No admin role configured yet — fall back to requiring real Administrator
            # so this can't be silently bypassed by anyone.
            return False

        return any(role.id == role_id for role in ctx.author.roles)

    return commands.check(predicate)
