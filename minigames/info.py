"""/games - overview of every game plus a select menu with the full rules of each."""
import discord

from config import DAILY_BET_LIMIT, MAX_BET_PER_GAME
from database import payout_multiplier

from .base import GOLD, GREY, safe_edit

# Order = order shown to players. `odds` states the real chances so nothing is hidden.
TIE_GAMES = {"rps", "blackjack", "dealerschoice"}   # games where a tie returns the bet

GAMES: dict[str, dict] = {
    "coinflip": {
        "name": "Coin Flip", "emoji": "🪙", "command": "/coinflip <side> <amount>",
        "summary": "Call heads or tails.",
        "how": ["Run `/coinflip`, choose **Heads** or **Tails** and your bet.",
                "The bot flips a fair coin.", "If it lands on your side, you win."],
        "odds": "50% win · 50% lose",
    },
    "diceduel": {
        "name": "Dice Duel", "emoji": "🎲", "command": "/diceduel <amount>",
        "summary": "Even, odd, over or under the bot's target.",
        "how": ["Run `/diceduel` with your bet. The bot shows a **target number**.",
                "The bot rolls **two dice**. Bet on **Even**, **Odd**, **Over** or **Under** the target.",
                "Over / Under compare the **sum** of the dice with the target - "
                "a sum exactly equal to the target loses."],
        "odds": "Even / Odd: 50% · Over / Under: between 28% and 58% depending on the target (the bot shows it first)",
    },
    "guess": {
        "name": "Guess the Number", "emoji": "🔢", "command": "/guess <amount>",
        "summary": "Find the secret number in 5 guesses.",
        "how": ["Run `/guess` with your bet. The bot picks a number from **1 to 100**.",
                "Press **Make a guess** and type a number. The bot tells you if the secret number is "
                "**higher** or **lower**.",
                "You have **5 guesses**. Find the number to win. Invalid or repeated guesses don't count."],
        "odds": "Depends on your skill - halving the range every guess finds it about 31% of the time",
    },
    "rps": {
        "name": "Rock Paper Scissors", "emoji": "✊", "command": "/rps <amount>",
        "summary": "Beat the bot's move. A draw returns your bet.",
        "how": ["Run `/rps` with your bet and press **Rock**, **Paper** or **Scissors**.",
                "🪨 beats ✂️ · ✂️ beats 📄 · 📄 beats 🪨",
                "If you both pick the same move it's a **tie** and your bet is returned."],
        "odds": "33% win · 33% tie (bet returned) · 33% lose",
    },
    "blackjack": {
        "name": "Blackjack", "emoji": "🃏", "command": "/blackjack <amount>",
        "summary": "Get closer to 21 than the dealer.",
        "how": ["Run `/blackjack` with your bet. You and the dealer get 2 cards; you see one dealer card.",
                "**Hit** to draw a card or **Stand** to keep your hand. Go over 21 and you bust.",
                "The dealer draws until 17 or more. Cards: 2-10 = face value, J/Q/K = 10, "
                "Ace = 11 or 1.",
                "A natural 21 (Ace + 10-card) wins immediately. Equal totals are a **tie**."],
        "odds": "About 43% win · 9% tie · 48% lose with sensible play",
    },
    "dealerschoice": {
        "name": "Dealer's Choice", "emoji": "🃏", "command": "/dealerschoice <amount>",
        "summary": "Pick a face-down card that beats the dealer's.",
        "how": ["Run `/dealerschoice` with your bet. The dealer shows one card.",
                "Pick one of **5 face-down cards**.",
                "If your card is **higher** than the dealer's you win. Ace is highest. "
                "The same rank is a **tie** (bet returned)."],
        "odds": "47% win · 6% tie (bet returned) · 47% lose",
    },
    "cups": {
        "name": "Cups", "emoji": "🥤", "command": "/cups <amount>",
        "summary": "Find the diamond under one of 5 cups.",
        "how": ["Run `/cups` with your bet. The bot hides a 💎 under one of **5 cups**.",
                "Open the menu and pick the cup you think hides it.",
                "Find the diamond to win."],
        "odds": "20% win (1 in 5) · 80% lose",
    },
}


def _payout_line(game: str) -> str:
    return f"**Win:** +{payout_multiplier(game)}× your bet • **Lose:** -your bet"


def overview_embed() -> discord.Embed:
    embed = discord.Embed(
        title="🎮 Panda Mini-Games",
        description=(
            "Bet your XP against the bot! Pick a game in the menu below to see how to play it.\n\n"
            f"● Bet limits: up to **{MAX_BET_PER_GAME:,} XP** per game, **{DAILY_BET_LIMIT:,} XP** "
            "in total per day (resets at 00:00 UTC)\n"
            "● You can only bet XP you hold this month (monthly XP)\n"
            "● One game at a time - and only you can see your game\n"
            "● A tie returns your bet\n"
            "● Check your allowance in `/profile`"),
        color=GOLD)
    for info in GAMES.values():
        embed.add_field(name=f"{info['emoji']} {info['name']}",
                        value=f"`{info['command']}`\n{info['summary']}", inline=True)
    embed.set_footer(text="Play responsibly - XP you lose is gone! • betpanda.io")
    return embed


def game_embed(key: str) -> discord.Embed:
    info = GAMES[key]
    embed = discord.Embed(title=f"{info['emoji']} {info['name']}", color=GOLD,
                          description=f"**Command:** `{info['command']}`")
    embed.add_field(name="📖 How to play",
                    value="\n".join(f"{i}. {line}" for i, line in enumerate(info["how"], 1)), inline=False)
    #embed.add_field(name="🎯 Your chances", value=info["odds"], inline=False)
    payout = _payout_line(key) + ("\n**Tie:** your bet is returned" if key in TIE_GAMES else "")
    embed.add_field(name="💰 Payout", value=payout, inline=False)
    embed.add_field(name="📏 Limits", value=f"Max bet {MAX_BET_PER_GAME:,} XP • {DAILY_BET_LIMIT:,} XP per day",
                    inline=False)
    embed.set_footer(text="Pick another game in the menu, or go back to the overview • betpanda.io")
    return embed


class GamesSelect(discord.ui.Select):
    def __init__(self):
        options = [discord.SelectOption(label="Overview", value="overview", emoji="🎮",
                                        description="All games at a glance")]
        options += [discord.SelectOption(label=info["name"], value=key, emoji=info["emoji"],
                                         description=info["summary"][:100])
                    for key, info in GAMES.items()]
        super().__init__(placeholder="📖 How do I play...?", options=options)

    async def callback(self, interaction: discord.Interaction):
        choice = self.values[0]
        embed = overview_embed() if choice == "overview" else game_embed(choice)
        await interaction.response.edit_message(embed=embed, view=self.view)


class GamesInfoView(discord.ui.View):
    def __init__(self, owner_id: int):
        super().__init__(timeout=180)
        self.owner_id = owner_id
        self.interaction: discord.Interaction | None = None
        self.add_item(GamesSelect())

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("Run `/games` to open your own guide.", ephemeral=True)
            return False
        return True

    async def on_timeout(self) -> None:
        if self.interaction is not None:
            self.clear_items()
            await safe_edit(self.interaction, view=None)
