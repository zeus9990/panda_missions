"""Shared building blocks for every mini-game.

BetSession  owns ONE bet from start to finish:
              open()    validates limits/XP, reserves the stake, allows only one game per player
              settle()  win / loss / push -> XP, history, rank check (exactly once)
              cancel()  gives the stake back (error, timeout)
GameView    a discord.ui.View with the rules every game needs:
              only the player can press the buttons, inactivity cancels the bet and tells the player,
              an unexpected error cancels the bet, gets an Error ID and tells the player.
Responses are always ephemeral, so players can all play in the same channel without clutter.
"""
import asyncio
import logging
from contextlib import asynccontextmanager

import discord

from services.betting import cancel_bet, finish_bet, finish_push, start_bet, win_amount
from utils.errors import report_task_error

log = logging.getLogger(__name__)

VIEW_TIMEOUT = 120  # seconds without a click before an unfinished game is cancelled

GOLD, GREEN, RED, GREY = (discord.Color.gold(), discord.Color.green(),
                          discord.Color.red(), discord.Color.light_grey())

# user_id -> BetSession. Players may only run ONE game at a time; this also guarantees the
# balance check made when the bet is placed is still true when it is settled.
ACTIVE: dict[int, "BetSession | object"] = {}
_PENDING = object()


class BetSession:
    def __init__(self, interaction: discord.Interaction, game: str, amount: int, bet: dict):
        self.interaction = interaction
        self.user = interaction.user
        self.user_id = interaction.user.id
        self.guild = interaction.guild
        self.game = game
        self.amount = amount
        self.remaining_today: int = bet["remaining_today"]
        self.done = False          # settled or cancelled
        self.outcome: str | None = None   # "win" | "loss" | "push" once settled

    # ── lifecycle ───────────────────────────────────────────────────────────
    @classmethod
    async def open(cls, interaction: discord.Interaction, game: str, amount: int) -> "BetSession | None":
        """Reserve the bet. On refusal the player is told privately and None is returned."""
        user_id = interaction.user.id
        if user_id in ACTIVE:
            await interaction.response.send_message(
                "> ⏳ You already have a game in progress. Finish it (or wait for it to time out) "
                "before starting another.", ephemeral=True)
            return None
        ACTIVE[user_id] = _PENDING  # claim the slot BEFORE any await so two commands can't both pass

        try:
            bet = await start_bet(user_id, amount)
        except BaseException:
            ACTIVE.pop(user_id, None)
            raise
        if not bet["success"]:
            ACTIVE.pop(user_id, None)
            await interaction.response.send_message(f"> ❌ {bet['message']}", ephemeral=True)
            return None

        session = cls(interaction, game, amount, bet)
        ACTIVE[user_id] = session
        return session

    def _release(self) -> None:
        if ACTIVE.get(self.user_id) is self:
            del ACTIVE[self.user_id]

    async def settle(self, outcome: str, details: dict | None = None) -> dict:
        """Apply the result exactly once. outcome: "win" | "loss" | "push".

        Raises only if the XP could NOT be changed (the caller then cancels the bet).
        """
        if self.done:
            raise RuntimeError("This bet was already settled or cancelled.")
        self.done = True
        try:
            if outcome == "push":
                result = await finish_push(self.user_id, self.game, self.amount, details)
                self.remaining_today += self.amount
            else:
                result = await finish_bet(self.guild, self.user_id, self.user.name, self.game,
                                          self.amount, outcome == "win", details)
        except BaseException:
            self.done = False
            raise
        self.outcome = outcome
        self._release()
        return result

    async def cancel(self) -> None:
        """Give the stake back. Does nothing if the bet is already settled/cancelled."""
        if self.done:
            return
        self.done = True
        try:
            await cancel_bet(self.user_id, self.amount)
        finally:
            self._release()

    @asynccontextmanager
    async def guard(self):
        """Wrap the first phase of a game: any failure cancels the bet and tells the player."""
        try:
            yield
        except Exception:
            unsettled = not self.done
            await self.cancel()
            if unsettled:
                await safe_edit(self.interaction, content="⚠️ Something went wrong - your bet was "
                                "cancelled and nothing was deducted.", embed=None, view=None)
            raise


# ── message helpers ─────────────────────────────────────────────────────────
async def safe_edit(interaction: discord.Interaction, **kwargs) -> None:
    """Edit the game message. A Discord hiccup is only logged: it must never undo a settled bet."""
    try:
        if interaction.response.is_done():
            await interaction.edit_original_response(**kwargs)
        else:
            await interaction.response.edit_message(**kwargs)
    except discord.HTTPException:
        log.exception("Could not update a game message.")


def play_embed(session: BetSession, title: str, description: str, color=GOLD) -> discord.Embed:
    embed = discord.Embed(title=title, description=description, color=color)
    embed.set_footer(text=f"Bet: {session.amount:,} XP • Win pays +{win_amount(session.game, session.amount):,} XP"
                          " • betpanda.io")
    return embed


def result_embed(session: BetSession, outcome: str, result: dict, title: str, body: str,
                 *, thumbnail: str | None = None) -> discord.Embed:
    headline = {"win": "You win! 🎉", "loss": "You lose 😢", "push": "It's a tie 🤝"}[outcome]
    color = {"win": GREEN, "loss": RED, "push": GREY}[outcome]
    lines = [body, ""]
    if outcome == "push":
        lines.append("● **Your bet was returned** - you lost nothing.")
    else:
        lines.append(f"● **XP change:** `{result['xp_change']:+,} XP`")
        lines.append(f"● **Total XP:** `{result['total_xp']:,} XP`")
    embed = discord.Embed(title=f"{title} - {headline}", description="\n".join(lines),
                          color=color, timestamp=discord.utils.utcnow())
    embed.set_footer(text=f"Bets left today: {session.remaining_today:,} XP • betpanda.io")
    if thumbnail:
        embed.set_thumbnail(url=thumbnail)
    return embed


async def handle_ui_error(session: BetSession | None, interaction: discord.Interaction,
                          error: Exception, where: str) -> None:
    """Common error path for views and modals: refund, report with an ID, tell the player."""
    unsettled = session is not None and not session.done
    if session is not None:
        await session.cancel()  # no-op when the XP was already settled
    error_id = await report_task_error(interaction.client, error, where, user=interaction.user,
                                       guild=interaction.guild, channel=interaction.channel)
    text = f"⚠️ Something went wrong. Error ID: `{error_id}`"
    if unsettled:
        text += " - your bet was cancelled and nothing was deducted."
    try:
        if interaction.response.is_done():
            await interaction.followup.send(text, ephemeral=True)
        else:
            await interaction.response.send_message(text, ephemeral=True)
    except discord.HTTPException:
        log.warning("Could not tell user %s about error %s.", interaction.user.id, error_id)


# ── UI building blocks ──────────────────────────────────────────────────────
class ChoiceButton(discord.ui.Button):
    """A button that calls `handler(interaction, key)` - lets one view own many similar buttons."""

    def __init__(self, key: str, handler, **kwargs):
        super().__init__(**kwargs)
        self.key = key
        self.handler = handler

    async def callback(self, interaction: discord.Interaction):
        await self.handler(interaction, self.key)


class GameView(discord.ui.View):
    def __init__(self, session: BetSession, *, timeout: float = VIEW_TIMEOUT):
        super().__init__(timeout=timeout)
        self.session = session
        self.lock = asyncio.Lock()   # double-clicks are handled one after the other
        self.claimed = False         # one-shot games: only the first click counts

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.session.user_id:
            await interaction.response.send_message("This isn't your game.", ephemeral=True)
            return False
        return True

    def claim(self) -> bool:
        """True for the first caller only (guards one-shot games against double-clicks)."""
        if self.claimed:
            return False
        self.claimed = True
        return True

    async def on_timeout(self) -> None:
        if self.session.done:
            return
        await self.session.cancel()
        self.clear_items()
        await safe_edit(self.session.interaction, view=None, embed=discord.Embed(
            title="⏱️ Game timed out",
            description="You took too long, so the game was cancelled. **Nothing was deducted.**",
            color=GREY))

    async def on_error(self, interaction: discord.Interaction, error: Exception, item) -> None:
        await handle_ui_error(self.session, interaction, error,
                              f"game {self.session.game} ({type(item).__name__})")

    async def settle(self, outcome: str, details: dict | None = None) -> dict:
        """Settle the bet and stop listening for clicks."""
        result = await self.session.settle(outcome, details)
        self.stop()
        return result
