"""🔢 Guess the Number - the bot picks 1-100, you get 5 guesses and a higher/lower hint after each."""
import secrets

import discord

from .base import (BetSession, GameView, handle_ui_error, play_embed, result_embed, safe_edit)

GAME = "guess"
LOW, HIGH = 1, 100
MAX_ATTEMPTS = 5


def pick_number() -> int:
    return secrets.randbelow(HIGH - LOW + 1) + LOW


class GuessModal(discord.ui.Modal, title="🔢 Guess the number"):
    guess = discord.ui.TextInput(label=f"Your guess ({LOW}-{HIGH})", placeholder="Type a whole number",
                                 min_length=1, max_length=3)

    def __init__(self, view: "GuessView"):
        super().__init__(timeout=300)  # clean up if the player closes the pop-up without submitting
        self.view = view

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self.view.handle_guess(interaction, self.guess.value)

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        await handle_ui_error(self.view.session, interaction, error, "game guess (modal)")


class GuessView(GameView):
    def __init__(self, session: BetSession, secret: int):
        super().__init__(session)
        self.secret = secret
        self.guesses: list[int] = []
        self.low, self.high = LOW, HIGH   # the range the number can still be in

    @property
    def attempts_left(self) -> int:
        return MAX_ATTEMPTS - len(self.guesses)

    def embed(self, warning: str | None = None) -> discord.Embed:
        lines = [f"I'm thinking of a number between **{LOW}** and **{HIGH}**.",
                 f"You have **{self.attempts_left}** of {MAX_ATTEMPTS} guesses left.", ""]
        for i, g in enumerate(self.guesses, 1):
            hint = "⬆️ the number is **higher**" if g < self.secret else "⬇️ the number is **lower**"
            lines.append(f"`{i}.` **{g}** → {hint}")
        if self.guesses:
            lines.append(f"\n🎯 It must be between **{self.low}** and **{self.high}**.")
        if warning:
            lines.append(f"\n⚠️ {warning}")
        return play_embed(self.session, "🔢 Guess the Number", "\n".join(lines))

    @discord.ui.button(label="Make a guess", emoji="🔢", style=discord.ButtonStyle.primary)
    async def make_guess(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(GuessModal(self))

    async def handle_guess(self, interaction: discord.Interaction, raw: str) -> None:
        async with self.lock:
            if self.session.done:
                await interaction.response.send_message("This game has already ended.", ephemeral=True)
                return

            try:
                number = int(raw.strip())
            except ValueError:
                number = None
            if number is None or not LOW <= number <= HIGH:
                await interaction.response.edit_message(
                    embed=self.embed(f"Please enter a whole number from {LOW} to {HIGH}. "
                                     "That didn't use up a guess."), view=self)
                return
            if number in self.guesses:
                await interaction.response.edit_message(
                    embed=self.embed(f"You already guessed {number}. That didn't use up a guess."), view=self)
                return

            self.guesses.append(number)
            if number < self.secret:
                self.low = max(self.low, number + 1)
            elif number > self.secret:
                self.high = min(self.high, number - 1)

            if number == self.secret or self.attempts_left == 0:
                await self.finish(interaction, won=number == self.secret)
            else:
                await interaction.response.edit_message(embed=self.embed(), view=self)

    async def finish(self, interaction: discord.Interaction, *, won: bool) -> None:
        outcome = "win" if won else "loss"
        result = await self.settle(outcome, {"secret": self.secret, "guesses": self.guesses})
        used = len(self.guesses)
        body = (f"The number was **{self.secret}**.\n"
                + (f"You found it in **{used}** guess{'es' if used != 1 else ''}! 🎯" if won
                   else f"You used all {MAX_ATTEMPTS} guesses: {', '.join(map(str, self.guesses))}"))
        await safe_edit(interaction, view=None,
                        embed=result_embed(self.session, outcome, result, "🔢 Guess the Number", body))


async def play(interaction: discord.Interaction, amount: int) -> None:
    session = await BetSession.open(interaction, GAME, amount)
    if session is None:
        return
    async with session.guard():
        view = GuessView(session, pick_number())
        await interaction.response.send_message(embed=view.embed(), view=view, ephemeral=True)
