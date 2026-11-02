"""Shared permission check for admin / moderator commands."""
import discord
from discord import app_commands

from config import ADMIN_ROLE_IDS, GAME_CHANNEL_IDS


def is_staff(interaction: discord.Interaction) -> bool:
    """Guild owner or anyone holding one of ADMIN_ROLE_IDS."""
    guild, user = interaction.guild, interaction.user
    if guild is None or not isinstance(user, discord.Member):
        return False
    return user.id == guild.owner_id or any(r.id in ADMIN_ROLE_IDS for r in user.roles)


def require_staff(interaction: discord.Interaction) -> None:
    """Raise the proper discord.py error if the caller is not staff.

    The central error handler turns these into a friendly message.
    """
    if interaction.guild is None:
        raise app_commands.NoPrivateMessage()
    if not is_staff(interaction):
        raise app_commands.MissingAnyRole(list(ADMIN_ROLE_IDS))


def admin_only():
    """Decorator for a single app command: @admin_only()"""
    async def predicate(interaction: discord.Interaction) -> bool:
        require_staff(interaction)
        return True
    return app_commands.check(predicate)


class WrongChannel(app_commands.CheckFailure):
    """Raised when a game is used outside GAME_CHANNEL_IDS (shown nicely by the error handler)."""

    def __init__(self, channel_ids):
        self.channel_ids = list(channel_ids)
        super().__init__("Games can only be played in the games channel(s).")


def games_channel_only():
    """Decorator for game commands: server only, and only in GAME_CHANNEL_IDS (if any are set)."""
    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.guild is None:
            raise app_commands.NoPrivateMessage()
        if GAME_CHANNEL_IDS and interaction.channel_id not in GAME_CHANNEL_IDS:
            raise WrongChannel(GAME_CHANNEL_IDS)
        return True
    return app_commands.check(predicate)
