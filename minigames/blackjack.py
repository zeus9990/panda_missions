"""🃏 Blackjack - beat the dealer without going over 21. Hit or Stand.

Rules: dealer stands on every 17, blackjack (21 with two cards) beats a normal 21,
both blackjack or equal totals = tie (bet returned). A win pays like every other game.
"""
import discord

from .base import (BetSession, ChoiceButton, GameView, play_embed, result_embed, safe_edit)
from .cards import Card, new_deck, show

GAME = "blackjack"


def card_points(card: Card) -> int:
    if card.rank == "A":
        return 11
    return 10 if card.rank in ("10", "J", "Q", "K") else int(card.rank)


def hand_value(cards: list[Card]) -> int:
    """Best total: aces count 11 unless that would bust, then 1."""
    total = sum(card_points(c) for c in cards)
    aces = sum(1 for c in cards if c.rank == "A")
    while total > 21 and aces:
        total -= 10
        aces -= 1
    return total


def is_blackjack(cards: list[Card]) -> bool:
    return len(cards) == 2 and hand_value(cards) == 21


def dealer_play(deck: list[Card], dealer: list[Card]) -> None:
    """The dealer draws until reaching 17 or more."""
    while hand_value(dealer) < 17:
        dealer.append(deck.pop())


def judge(player: list[Card], dealer: list[Card]) -> str:
    """Final result once both hands are complete."""
    p_bj, d_bj = is_blackjack(player), is_blackjack(dealer)
    if p_bj or d_bj:
        return "push" if p_bj and d_bj else ("win" if p_bj else "loss")
    p, d = hand_value(player), hand_value(dealer)
    if p > 21:
        return "loss"
    if d > 21 or p > d:
        return "win"
    return "push" if p == d else "loss"


def table_embed(session: BetSession, player: list[Card], dealer: list[Card], *, reveal: bool,
                note: str = "") -> discord.Embed:
    dealer_text = (f"{show(dealer)} → **{hand_value(dealer)}**" if reveal
                   else f"`{dealer[0]}` `??`")
    body = (f"**Your hand:** {show(player)} → **{hand_value(player)}**\n"
            f"**Dealer:** {dealer_text}")
    if note:
        body += f"\n\n{note}"
    embed = play_embed(session, "🃏 Blackjack", body)
    embed.set_thumbnail(url=player[-1].image_url)
    return embed


class BlackjackView(GameView):
    def __init__(self, session: BetSession, deck: list[Card], player: list[Card], dealer: list[Card]):
        super().__init__(session)
        self.deck, self.player, self.dealer = deck, player, dealer
        self.add_item(ChoiceButton("hit", self.act, label="Hit", emoji="➕", style=discord.ButtonStyle.success))
        self.add_item(ChoiceButton("stand", self.act, label="Stand", emoji="✋", style=discord.ButtonStyle.primary))

    def embed(self) -> discord.Embed:
        return table_embed(self.session, self.player, self.dealer, reveal=False,
                           note="**Hit** to draw a card, **Stand** to keep your hand.")

    async def act(self, interaction: discord.Interaction, action: str) -> None:
        async with self.lock:
            if self.session.done:
                await interaction.response.defer()
                return
            if action == "hit":
                self.player.append(self.deck.pop())
                total = hand_value(self.player)
                if total > 21:
                    await self.finish(interaction, "💥 **Bust!** You went over 21.")
                    return
                if total < 21:
                    await interaction.response.edit_message(embed=self.embed(), view=self)
                    return
            # Stand, or a hit that made exactly 21 (stand automatically)
            dealer_play(self.deck, self.dealer)
            await self.finish(interaction, "")

    async def finish(self, interaction: discord.Interaction, note: str) -> None:
        outcome = judge(self.player, self.dealer)
        result = await self.settle(outcome, {
            "player": [str(c) for c in self.player], "dealer": [str(c) for c in self.dealer],
            "player_total": hand_value(self.player), "dealer_total": hand_value(self.dealer)})
        embed = result_embed(self.session, outcome, result, "🃏 Blackjack", table_embed(
            self.session, self.player, self.dealer, reveal=True, note=note).description,
            thumbnail=self.player[-1].image_url)
        await safe_edit(interaction, embed=embed, view=None)


async def play(interaction: discord.Interaction, amount: int) -> None:
    session = await BetSession.open(interaction, GAME, amount)
    if session is None:
        return
    async with session.guard():
        deck = new_deck()
        player = [deck.pop(), deck.pop()]
        dealer = [deck.pop(), deck.pop()]

        if is_blackjack(player) or is_blackjack(dealer):   # settled immediately, no decisions to make
            outcome = judge(player, dealer)
            result = await session.settle(outcome, {
                "player": [str(c) for c in player], "dealer": [str(c) for c in dealer], "natural": True})
            note = ("🃏 **Blackjack!** " + ("You got a natural 21." if is_blackjack(player) else
                    "The dealer has a natural 21."))
            body = table_embed(session, player, dealer, reveal=True, note=note).description
            await interaction.response.send_message(
                embed=result_embed(session, outcome, result, "🃏 Blackjack", body,
                                   thumbnail=player[-1].image_url), ephemeral=True)
            return

        view = BlackjackView(session, deck, player, dealer)
        await interaction.response.send_message(embed=view.embed(), view=view, ephemeral=True)
