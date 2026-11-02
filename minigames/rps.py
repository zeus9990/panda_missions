"""✊ Rock Paper Scissors - best of one against the bot. A draw returns your bet."""
import asyncio
import secrets

import discord

from .base import (BetSession, ChoiceButton, GameView, play_embed, result_embed, safe_edit)

GAME = "rps"
THINK_SECONDS = 1.0
MOVES = {"rock": ("Rock", "🪨"), "paper": ("Paper", "📄"), "scissors": ("Scissors", "✂️")}
BEATS = {"rock": "scissors", "paper": "rock", "scissors": "paper"}   # key beats value


def bot_move() -> str:
    return secrets.choice(list(MOVES))


def judge(player: str, bot: str) -> str:
    if player == bot:
        return "push"
    return "win" if BEATS[player] == bot else "loss"


def label(move: str) -> str:
    name, emoji = MOVES[move]
    return f"{emoji} {name}"


class RpsView(GameView):
    def __init__(self, session: BetSession):
        super().__init__(session)
        for key, (name, emoji) in MOVES.items():
            self.add_item(ChoiceButton(key, self.pick, label=name, emoji=emoji,
                                       style=discord.ButtonStyle.primary))

    def intro_embed(self) -> discord.Embed:
        return play_embed(self.session, "✊ Rock Paper Scissors",
                          "Choose your move!\n\n🪨 beats ✂️  •  ✂️ beats 📄  •  📄 beats 🪨\n"
                          "*A draw returns your bet.*")

    async def pick(self, interaction: discord.Interaction, move: str) -> None:
        if not self.claim():
            await interaction.response.defer()
            return
        await interaction.response.edit_message(view=None, embed=play_embed(
            self.session, "✊ Rock Paper Scissors", f"You chose **{label(move)}**\n\n🤖 The bot is choosing..."))

        bot = bot_move()
        outcome = judge(move, bot)
        result = await self.settle(outcome, {"player": move, "bot": bot})

        await asyncio.sleep(THINK_SECONDS)
        body = f"You chose **{label(move)}**\nThe bot chose **{label(bot)}**"
        await safe_edit(interaction, embed=result_embed(self.session, outcome, result,
                                                        "✊ Rock Paper Scissors", body))


async def play(interaction: discord.Interaction, amount: int) -> None:
    session = await BetSession.open(interaction, GAME, amount)
    if session is None:
        return
    async with session.guard():
        view = RpsView(session)
        await interaction.response.send_message(embed=view.intro_embed(), view=view, ephemeral=True)
