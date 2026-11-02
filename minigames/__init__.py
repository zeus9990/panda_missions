"""Mini-games (bot vs player). One file per game, all built on `base.py`.

    base.py           BetSession (bet lifecycle) + GameView (timeouts, owner-only, errors) + embeds
    cards.py          playing cards (local deck, card art URLs from deckofcardsapi.com)
    coinflip.py       /coinflip      heads or tails
    dice_duel.py      /diceduel      even / odd / over / under a target
    guess_number.py   /guess         5 tries to find 1-100 (button + modal)
    rps.py            /rps           rock paper scissors
    blackjack.py      /blackjack     hit / stand
    dealers_choice.py /dealerschoice pick 1 of 5 face-down cards vs the dealer's card
    cups.py           /cups          find the diamond (select menu)
    info.py           /games         what is available + how to play (select menu)

Every game follows the same 3 steps: open a BetSession -> play -> settle (win / loss / tie).
"""
