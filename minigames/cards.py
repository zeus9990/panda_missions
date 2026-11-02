"""Playing cards. The deck is shuffled locally (no network calls while a bet is open);
only the card pictures come from deckofcardsapi.com, as plain image URLs Discord loads itself."""
import random
from dataclasses import dataclass

_RNG = random.SystemRandom()  # OS randomness: can't be predicted or seeded

RANKS = ("2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A")
SUITS = {"S": "♠", "H": "♥", "D": "♦", "C": "♣"}
CARD_IMAGE_BASE = "https://deckofcardsapi.com/static/img"
CARD_BACK_URL = f"{CARD_IMAGE_BASE}/back.png"


@dataclass(frozen=True)
class Card:
    rank: str   # "2".."10", "J", "Q", "K", "A"
    suit: str   # "S", "H", "D", "C"

    @property
    def value(self) -> int:
        """Rank strength for comparing cards: 2..14 (ace high)."""
        return RANKS.index(self.rank) + 2

    @property
    def code(self) -> str:
        """deckofcardsapi.com card code (the ten is '0'), e.g. 'KH', '0S'."""
        return ("0" if self.rank == "10" else self.rank) + self.suit

    @property
    def image_url(self) -> str:
        return f"{CARD_IMAGE_BASE}/{self.code}.png"

    def __str__(self) -> str:
        return f"{self.rank}{SUITS[self.suit]}"


def new_deck() -> list[Card]:
    deck = [Card(rank, suit) for suit in SUITS for rank in RANKS]
    _RNG.shuffle(deck)
    return deck


def show(cards) -> str:
    return " ".join(f"`{card}`" for card in cards)
