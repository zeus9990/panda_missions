"""🎲 Dice Duel - the bot rolls two dice; bet on even, odd, or over/under the target it shows."""
import asyncio
import secrets

import discord

from .base import (BetSession, ChoiceButton, GameView, play_embed, result_embed, safe_edit)

GAME = "diceduel"
TARGETS = (6, 7, 8)   # the number the bot displays for the over/under bets
ROLL_SECONDS = 1.2


def pick_target() -> int:
    return secrets.choice(TARGETS)


def roll() -> tuple[int, int]:
    return secrets.randbelow(6) + 1, secrets.randbelow(6) + 1


def is_win(choice: str, total: int, target: int) -> bool:
    """even / odd -> parity of the sum. over / under -> strictly above / below the target
    (a sum EQUAL to the target loses both over and under)."""
    return {
        "even": total % 2 == 0,
        "odd": total % 2 == 1,
        "over": total > target,
        "under": total < target,
    }[choice]


class DiceView(GameView):
    def __init__(self, session: BetSession, target: int):
        super().__init__(session)
        self.target = target
        self.labels = {"even": "Even", "odd": "Odd", "over": f"Over {target}", "under": f"Under {target}"}
        styles = {"even": discord.ButtonStyle.primary, "odd": discord.ButtonStyle.primary,
                  "over": discord.ButtonStyle.success, "under": discord.ButtonStyle.danger}
        emojis = {"even": "2️⃣", "odd": "1️⃣", "over": "⬆️", "under": "⬇️"}
        for key, label in self.labels.items():
            self.add_item(ChoiceButton(key, self.pick, label=label, style=styles[key], emoji=emojis[key]))

    def intro_embed(self) -> discord.Embed:
        return play_embed(self.session, "🎲 Dice Duel", (
            f"The bot will roll **two dice** 🎲🎲.\n\n"
            f"🎯 **Target number: {self.target}**\n\n"
            "**Pick your bet:**\n"
            "● **Even** / **Odd** - the *sum* of the dice\n"
            f"● **Over {self.target}** / **Under {self.target}** - the sum is higher / lower than the target\n"
            f"*(a sum of exactly {self.target} loses Over and Under)*"))

    async def pick(self, interaction: discord.Interaction, choice: str) -> None:
        if not self.claim():
            await interaction.response.defer()
            return
        await interaction.response.edit_message(view=None, embed=play_embed(
            self.session, "🎲 Dice Duel",
            f"You bet on **{self.labels[choice]}** (target {self.target})\n\nRolling the dice... 🎲🎲"))

        d1, d2 = roll()
        total = d1 + d2
        outcome = "win" if is_win(choice, total, self.target) else "loss"
        result = await self.settle(outcome, {"pick": choice, "target": self.target, "dice": [d1, d2]})

        await asyncio.sleep(ROLL_SECONDS)
        body = (f"You bet on **{self.labels[choice]}** (target {self.target})\n"
                f"The bot rolled 🎲 **{d1}** + 🎲 **{d2}** = **{total}**")
        await safe_edit(interaction, embed=result_embed(self.session, outcome, result, "🎲 Dice Duel", body))


async def play(interaction: discord.Interaction, amount: int) -> None:
    session = await BetSession.open(interaction, GAME, amount)
    if session is None:
        return
    async with session.guard():
        view = DiceView(session, pick_target())
        await interaction.response.send_message(embed=view.intro_embed(), view=view, ephemeral=True)
