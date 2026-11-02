"""Betting for mini-games. A game cog does only this:

    bet = await start_bet(user.id, amount)
    if not bet["success"]:
        return await interaction.followup.send(bet["message"], ephemeral=True)
    ...play the game and decide won: bool...
    result = await finish_bet(guild, user.id, user.name, "coinflip", amount, won)

`finish_bet` applies the XP change (win: +bet x multiplier, loss: -bet,
both on total AND monthly XP; ties use `finish_push`), records the game history and runs the central
rank check after a win. If the game is abandoned call `cancel_bet` instead.
Game winnings are NOT held by the mission-XP pause.
"""
import logging

import discord

from database import payout_multiplier, place_bet, refund_bet, settle_bet, settle_push

from .ranks import check_rank

log = logging.getLogger(__name__)


async def start_bet(user_id: int, amount: int) -> dict:
    """Validate the bet against per-bet / daily limits and the user's XP, and reserve it."""
    return await place_bet(user_id, amount)


async def cancel_bet(user_id: int, amount: int) -> dict:
    """Release a reserved bet (game aborted before a result)."""
    return await refund_bet(user_id, amount)


async def finish_bet(
    guild: discord.Guild, user_id: int, username: str, game: str, amount: int, won: bool,
    details: dict | None = None,
) -> dict:
    """Apply the result. Raises ONLY if the XP was not changed (so the caller may `cancel_bet`)."""
    result = await settle_bet(user_id, username, game, amount, won, details)
    result["ranked_up"] = False
    if won:
        try:
            result["ranked_up"] = await check_rank(guild, user_id, result["total_xp"])
        except Exception:  # XP is already applied; the rank is re-checked on the user's next XP gain
            log.exception("Rank check failed after a %s win for user %s.", game, user_id)
    return result


async def finish_push(user_id: int, game: str, amount: int, details: dict | None = None) -> dict:
    """A tie: the bet is returned (no XP change, allowance freed)."""
    return await settle_push(user_id, game, amount, details)


def win_amount(game: str, amount: int) -> int:
    """XP a win of `amount` pays for this game."""
    return amount * payout_multiplier(game)
