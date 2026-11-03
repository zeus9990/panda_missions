"""Aggregated mini-game statistics (for /admin game-status), built from `game_history`.

Terms (always from the PLAYERS' point of view):
    net            sum of xp_change: + means players gained XP (XP created), - means they lost it
    per_bet        net / XP at risk (wins + losses; ties excluded) = observed XP gained per XP bet
    even_multiplier  the win multiplier at which this period would have broken even for players
                     (= XP staked on losses / XP staked on wins)
"""
from datetime import timedelta

from .connection import game_history_col
from .helpers import utc_now


def period_range(period: str) -> tuple[str | None, str]:
    """(first date included as an ISO string or None for all time, label). Dates are UTC."""
    now = utc_now()
    today = now.date()
    if period == "today":
        return today.isoformat(), f"Today ({today.isoformat()})"
    if period == "week":
        return (today - timedelta(days=6)).isoformat(), "Last 7 days"
    if period == "month":
        return today.replace(day=1).isoformat(), now.strftime("%B %Y")
    return None, "All time"


def _count(outcome: str) -> dict:
    return {"$sum": {"$cond": [{"$eq": ["$oc", outcome]}, 1, 0]}}


def _stake(outcome: str) -> dict:
    return {"$sum": {"$cond": [{"$eq": ["$oc", outcome]}, "$bet", 0]}}


def _finish(row: dict) -> dict:
    """Derived numbers for one group of rounds."""
    at_risk = row["win_stake"] + row["loss_stake"]
    row["win_rate"] = row["wins"] / row["rounds"] if row["rounds"] else 0.0
    row["per_bet"] = row["net"] / at_risk if at_risk else 0.0
    row["even_multiplier"] = (row["loss_stake"] / row["win_stake"]) if row["win_stake"] else None
    return row


async def get_game_overview(since: str | None = None, game: str | None = None) -> dict:
    """Statistics for rounds from `since` (ISO date, inclusive) until now; optional single game."""
    match: dict = {}
    if since:
        match["date"] = {"$gte": since}
    if game:
        match["game"] = game

    def top(sign: int) -> list:   # biggest single result for players (win: xp_change > 0, loss: < 0)
        return [{"$match": {"xp_change": {"$gt": 0} if sign > 0 else {"$lt": 0}}},
                {"$sort": {"xp_change": -sign}}, {"$limit": 1},
                {"$project": {"_id": 0, "user_id": 1, "game": 1, "bet": 1, "xp_change": 1}}]

    def players(sign: int) -> list:   # best / worst players by net XP
        return [{"$group": {"_id": "$user_id", "net": {"$sum": "$xp_change"},
                            "rounds": {"$sum": 1}, "volume": {"$sum": "$bet"}}},
                {"$match": {"net": {"$gt": 0} if sign > 0 else {"$lt": 0}}},
                {"$sort": {"net": -sign}}, {"$limit": 3}]

    pipeline = [
        {"$match": match},
        # history rows written before ties existed have no `outcome`: derive it from `won`
        {"$addFields": {"oc": {"$ifNull": ["$outcome", {"$cond": ["$won", "win", "loss"]}]}}},
        {"$facet": {
            "per_game": [
                {"$group": {
                    "_id": "$game", "rounds": {"$sum": 1},
                    "wins": _count("win"), "losses": _count("loss"), "pushes": _count("push"),
                    "volume": {"$sum": "$bet"}, "win_stake": _stake("win"), "loss_stake": _stake("loss"),
                    "net": {"$sum": "$xp_change"}, "max_win": {"$max": "$xp_change"},
                    "max_loss": {"$min": "$xp_change"}, "max_bet": {"$max": "$bet"},
                    "players": {"$addToSet": "$user_id"}}},
                {"$addFields": {"players": {"$size": "$players"}}}],
            "unique": [{"$group": {"_id": "$user_id"}}, {"$count": "n"}],
            "biggest_win": top(+1), "biggest_loss": top(-1),
            "biggest_bet": [{"$sort": {"bet": -1}}, {"$limit": 1},
                            {"$project": {"_id": 0, "user_id": 1, "game": 1, "bet": 1, "xp_change": 1}}],
            "top_winners": players(+1), "top_losers": players(-1),
        }},
    ]
    facet = (await game_history_col.aggregate(pipeline).to_list(length=1))[0]

    games = []
    for row in facet["per_game"]:
        row["game"] = row.pop("_id")
        games.append(_finish(row))

    totals = {k: sum(g[k] for g in games) for k in
              ("rounds", "wins", "losses", "pushes", "volume", "win_stake", "loss_stake", "net")}
    totals["players"] = facet["unique"][0]["n"] if facet["unique"] else 0
    _finish(totals)

    def first(key):
        return facet[key][0] if facet[key] else None

    def named(rows):
        return [{"user_id": r["_id"], "net": r["net"], "rounds": r["rounds"], "volume": r["volume"]}
                for r in rows]

    return {
        "success": True, "games": games, "totals": totals,
        "biggest_win": first("biggest_win"), "biggest_loss": first("biggest_loss"),
        "biggest_bet": first("biggest_bet"),
        "top_winners": named(facet["top_winners"]), "top_losers": named(facet["top_losers"]),
    }