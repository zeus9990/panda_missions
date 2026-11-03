"""The /admin game-status report: what is played, how much is staked, and whether a game pays too much."""
import discord

from database import payout_multiplier

from .info import GAMES

SHORT = {"coinflip": "Coin Flip", "diceduel": "Dice Duel", "guess": "Guess", "rps": "RPS",
         "blackjack": "Blackjack", "dealerschoice": "Dealer's", "cups": "Cups"}


def _name(key: str) -> str:
    return SHORT.get(key, key)


def _label(key: str) -> str:
    info = GAMES.get(key)
    return f"{info['emoji']} {info['name']}" if info else key


def _table(header: list[str], rows: list[list[str]]) -> str:
    """Monospace table inside a code block: first column left-aligned, the rest right-aligned."""
    widths = [max(len(h), *(len(r[i]) for r in rows)) for i, h in enumerate(header)]
    def line(cells):
        return " ".join(c.ljust(w) if i == 0 else c.rjust(w) for i, (c, w) in enumerate(zip(cells, widths)))
    return "```\n" + "\n".join([line(header), *(line(r) for r in rows)]) + "\n```"


def _signed(n: float, digits: int = 0) -> str:
    return f"{n:+,.{digits}f}"


def build_game_status_embed(data: dict, label: str, game: str | None = None) -> discord.Embed:
    games, totals = data["games"], data["totals"]
    title = f"🎮 Game Status - {_label(game)}" if game else "🎮 Game Status"
    embed = discord.Embed(title=f"{title} • {label}", color=discord.Color.blurple(),
                          timestamp=discord.utils.utcnow())
    if not games:
        embed.description = "No games were played in this period."
        return embed

    embed.add_field(name="🧾 Summary", value=(
        f"● **Rounds played:** {totals['rounds']:,} • **Players:** {totals['players']:,}\\n"
        f"● **Total bet volume:** `{totals['volume']:,} XP`\\n"
        f"● **Wins / Losses / Ties:** {totals['wins']:,} / {totals['losses']:,} / {totals['pushes']:,}\\n"
        f"● **Net XP for players:** `{_signed(totals['net'])} XP` "
        f"(`{_signed(totals['per_bet'], 2)}` per XP bet)").replace("\\n", "\n"), inline=False)

    by_rounds = sorted(games, key=lambda g: g["rounds"], reverse=True)
    embed.add_field(name="📊 Activity", value=_table(
        ["Game", "Rounds", "Bet XP", "Win%", "W/L/T"],
        [[_name(g["game"]), f"{g['rounds']:,}", f"{g['volume']:,}", f"{g['win_rate']:.0%}",
          f"{g['wins']}/{g['losses']}/{g['pushes']}"] for g in by_rounds]), inline=False)

    by_generous = sorted(games, key=lambda g: g["per_bet"], reverse=True)
    embed.add_field(name="⚖️ Balance (most generous first)", value=_table(
        ["Game", "Net XP", "XP/bet", "Now", "Even"],
        [[_name(g["game"]), _signed(g["net"]), _signed(g["per_bet"], 2), f"{payout_multiplier(g['game'])}x",
          "-" if g["even_multiplier"] is None else f"{g['even_multiplier']:.2f}x"] for g in by_generous]),
        inline=False)

    lines = []
    if not game:
        most_played = max(games, key=lambda g: g["rounds"])
        favourite = max(games, key=lambda g: g["volume"])
        generous = max(games, key=lambda g: g["net"])
        sink = min(games, key=lambda g: g["net"])
        lines += [f"● **Most played:** {_label(most_played['game'])} ({most_played['rounds']:,} rounds)",
                  f"● **Favourite (most XP staked):** {_label(favourite['game'])} ({favourite['volume']:,} XP)",
                  ]
        if generous["net"] > 0:   # only claim this when a game really paid players XP
            lines.append(f"● **Paid players most:** {_label(generous['game'])} ({_signed(generous['net'])} XP)")
        if sink["net"] < 0:       # ...and this only when a game really took XP from them
            lines.append(f"● **Took most XP from players:** {_label(sink['game'])} ({_signed(sink['net'])} XP)")
    for key, text in (("biggest_bet", "Biggest bet"), ("biggest_win", "Biggest single win"),
                      ("biggest_loss", "Biggest single loss")):
        row = data[key]
        if row:
            value = row["bet"] if key == "biggest_bet" else row["xp_change"]
            shown = f"{value:,}" if key == "biggest_bet" else _signed(value)
            lines.append(f"● **{text}:** `{shown} XP` - <@{row['user_id']}> in {_label(row['game'])}")
    if lines:
        embed.add_field(name="🏅 Highlights", value="\n".join(lines), inline=False)

    for key, title_ in (("top_winners", "🏆 Biggest winners"), ("top_losers", "💸 Biggest losers")):
        if data[key]:
            embed.add_field(name=title_, inline=True, value="\n".join(
                f"<@{p['user_id']}> `{_signed(p['net'])} XP` ({p['rounds']} rounds)" for p in data[key]))

    embed.set_footer(text="Net XP: + = players gained XP, - = players lost XP • Even = multiplier that would "
                          "have broken even • small samples are noisy • betpanda.io")
    return embed