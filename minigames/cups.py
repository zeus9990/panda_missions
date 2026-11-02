"""🥤 Cups (shell game) - a 💎 is hidden under one of 5 cups; pick the right one."""
import asyncio
import secrets

import discord

from .base import (BetSession, GameView, play_embed, result_embed, safe_edit)

GAME = "cups"
CUP_COUNT = 5
LIFT_SECONDS = 1.0
NUMBERS = ("1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣")


def hide_diamond() -> int:
    """Index 0..4 of the cup that hides the diamond."""
    return secrets.randbelow(CUP_COUNT)


def cup_row(prize: int | None) -> str:
    """The cups on the table: all 🥤, or with the 💎 revealed."""
    return " ".join("💎" if i == prize else "🥤" for i in range(CUP_COUNT))


class CupSelect(discord.ui.Select):
    def __init__(self):
        super().__init__(
            placeholder="🥤 Pick a cup...",
            options=[discord.SelectOption(label=f"Cup {i + 1}", value=str(i), emoji="🥤",
                                          description="Look under this cup") for i in range(CUP_COUNT)])

    async def callback(self, interaction: discord.Interaction):
        await self.view.pick(interaction, int(self.values[0]))


class CupsView(GameView):
    def __init__(self, session: BetSession, prize: int):
        super().__init__(session)
        self.prize = prize
        self.add_item(CupSelect())

    def intro_embed(self) -> discord.Embed:
        return play_embed(self.session, "🥤 Cups", (
            f"The bot hid a 💎 under one of **{CUP_COUNT} cups**.\n\n"
            f"{' '.join(NUMBERS)}\n{cup_row(None)}\n\n"
            "Pick the cup you think hides the diamond from the menu below!"))

    async def pick(self, interaction: discord.Interaction, index: int) -> None:
        if not self.claim():
            await interaction.response.defer()
            return
        await interaction.response.edit_message(view=None, embed=play_embed(
            self.session, "🥤 Cups", f"You picked **Cup {index + 1}**\n\n"
            f"{' '.join(NUMBERS)}\n{cup_row(None)}\n\nLifting the cup... 👀"))

        outcome = "win" if index == self.prize else "loss"
        result = await self.settle(outcome, {"picked": index + 1, "diamond": self.prize + 1})

        await asyncio.sleep(LIFT_SECONDS)
        body = (f"You picked **Cup {index + 1}**\n\n{' '.join(NUMBERS)}\n{cup_row(self.prize)}\n\n"
                + ("You found the 💎!" if outcome == "win"
                   else f"The 💎 was under **Cup {self.prize + 1}**."))
        await safe_edit(interaction, embed=result_embed(self.session, outcome, result, "🥤 Cups", body))


async def play(interaction: discord.Interaction, amount: int) -> None:
    session = await BetSession.open(interaction, GAME, amount)
    if session is None:
        return
    async with session.guard():
        view = CupsView(session, hide_diamond())
        await interaction.response.send_message(embed=view.intro_embed(), view=view, ephemeral=True)
