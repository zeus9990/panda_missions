"""🪙 Coin Flip - pick heads or tails; the bot flips a fair coin."""
import asyncio
import secrets

import discord

from .base import BetSession, play_embed, result_embed, safe_edit

GAME = "coinflip"
FLIP_SECONDS = 1.5  # suspense before the result is revealed
SIDES = {"heads": "Heads 🪙", "tails": "Tails 🌙"}


def flip() -> str:
    """A fair coin (cryptographically random, so it can't be predicted or gamed)."""
    return "heads" if secrets.randbelow(2) == 0 else "tails"


async def play(interaction: discord.Interaction, side: str, amount: int) -> None:
    session = await BetSession.open(interaction, GAME, amount)
    if session is None:
        return

    async with session.guard():
        await interaction.response.send_message(
            embed=play_embed(session, "🪙 Coin Flip",
                             f"You bet on **{SIDES[side]}**\n\nThe coin is in the air... 🌀"),
            ephemeral=True)
        landed = flip()
        outcome = "win" if landed == side else "loss"
        result = await session.settle(outcome, {"pick": side, "landed": landed})

    await asyncio.sleep(FLIP_SECONDS)
    body = f"You picked **{SIDES[side]}**\nThe coin landed on **{SIDES[landed]}**"
    await safe_edit(interaction, embed=result_embed(session, outcome, result, "🪙 Coin Flip", body))
