"""🃏 Dealer's Choice (higher card) - the dealer shows one card, you pick one of 5 face-down cards.

Your card must be HIGHER than the dealer's to win (ace is highest). The same rank is a tie.
"""
import discord

from .base import (BetSession, ChoiceButton, GameView, play_embed, result_embed, safe_edit)
from .cards import CARD_BACK_URL, Card, new_deck, show

GAME = "dealerschoice"
CARD_COUNT = 5


def deal() -> tuple[Card, list[Card]]:
    """(dealer's card, the 5 face-down cards) - 6 different cards from one shuffled deck."""
    deck = new_deck()
    return deck.pop(), [deck.pop() for _ in range(CARD_COUNT)]


def judge(player: Card, dealer: Card) -> str:
    if player.value == dealer.value:
        return "push"
    return "win" if player.value > dealer.value else "loss"


class DealersChoiceView(GameView):
    def __init__(self, session: BetSession, dealer: Card, cards: list[Card]):
        super().__init__(session)
        self.dealer, self.cards = dealer, cards
        for i in range(CARD_COUNT):
            self.add_item(ChoiceButton(str(i), self.pick, label=f"Card {i + 1}", emoji="🃏",
                                       style=discord.ButtonStyle.secondary))

    def intro_embed(self) -> discord.Embed:
        embed = play_embed(self.session, "🃏 Dealer's Choice", (
            f"The dealer drew: **`{self.dealer}`**\n\n"
            f"Pick one of the **{CARD_COUNT} face-down cards**. If your card is **higher** than "
            "the dealer's, you win!\n*(ace is highest; the same rank is a tie)*"))
        embed.set_thumbnail(url=self.dealer.image_url)
        embed.set_image(url=CARD_BACK_URL)
        return embed

    async def pick(self, interaction: discord.Interaction, key: str) -> None:
        if not self.claim():
            await interaction.response.defer()
            return
        index = int(key)
        mine = self.cards[index]
        outcome = judge(mine, self.dealer)
        result = await self.settle(outcome, {
            "dealer": str(self.dealer), "cards": [str(c) for c in self.cards], "picked": index + 1})

        # Turn the buttons into the revealed cards; colour the one that was picked.
        picked_style = {"win": discord.ButtonStyle.success, "loss": discord.ButtonStyle.danger,
                        "push": discord.ButtonStyle.primary}[outcome]
        for item in self.children:
            i = int(item.key)
            item.label, item.emoji, item.disabled = str(self.cards[i]), None, True
            item.style = picked_style if i == index else discord.ButtonStyle.secondary

        verdict = {"win": "Your card is **higher** 🎉", "loss": "Your card is **lower** 😢",
                   "push": "**Same rank** - it's a tie"}[outcome]
        body = (f"Dealer's card: **`{self.dealer}`**\nYou picked card **{index + 1}**: **`{mine}`**\n"
                f"{verdict}\n\nAll cards: {show(self.cards)}")
        await safe_edit(interaction, view=self, embed=result_embed(
            self.session, outcome, result, "🃏 Dealer's Choice", body, thumbnail=mine.image_url))


async def play(interaction: discord.Interaction, amount: int) -> None:
    session = await BetSession.open(interaction, GAME, amount)
    if session is None:
        return
    async with session.guard():
        dealer, cards = deal()
        view = DealersChoiceView(session, dealer, cards)
        await interaction.response.send_message(embed=view.intro_embed(), view=view, ephemeral=True)
