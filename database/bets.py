"""Mini-game betting storage (game-agnostic: any game can use it).

Flow for a game:
    1. place_bet(...)    reserve the stake against the user's DAILY limit
    2. ...play the game...
    3. settle_bet(...)   win  -> +bet x multiplier XP (total + monthly)
                         loss -> -bet XP (total + monthly)
       settle_push(...)  tie  -> bet returned, no XP change, allowance freed
       or refund_bet(...) if the game was cancelled (frees the daily allowance)
    (multiplier = GAME_MULTIPLIER_OVERRIDES.get(game, BET_WIN_MULTIPLIER))

Daily tracking lives in the `daily_xp_state` document (same collection the
message-XP cap uses) in its own fields:
    bet_date  UTC day the counter belongs to
    bet_xp    XP staked that day
A new UTC day simply has a different `bet_date`, so everybody starts again from 0
without any reset job, and the message-XP bonuses (which key off `date`) are untouched.

Every settled bet is written to `game_history` for stats / audits / leaderboards.
Prefer `services.betting`, which also runs the central rank check after a win.
"""
import logging

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from config import BET_WIN_MULTIPLIER, DAILY_BET_LIMIT, GAME_MULTIPLIER_OVERRIDES, MAX_BET_PER_GAME

from .connection import daily_xp_col, game_history_col, users_col
from .helpers import not_registered_message, utc_now, utc_today
from .xp import xp_update

log = logging.getLogger(__name__)


async def get_bet_status(userid: int) -> dict:
    """How much the user has staked today and how much they may still stake."""
    today = utc_today()
    doc = await daily_xp_col.find_one({"_id": userid}, {"bet_date": 1, "bet_xp": 1}) or {}
    staked = doc.get("bet_xp", 0) if doc.get("bet_date") == today else 0
    return {
        "success": True,
        "staked_today": staked,
        "remaining_today": max(0, DAILY_BET_LIMIT - staked),
        "daily_limit": DAILY_BET_LIMIT,
        "max_per_bet": MAX_BET_PER_GAME,
    }


async def place_bet(userid: int, amount: int) -> dict:
    """Reserve `amount` XP of today's allowance. Atomic, safe against double-clicks.

    Fails (nothing reserved) if: amount < 1, above MAX_BET_PER_GAME, above the
    remaining daily allowance, or above the XP the user holds THIS MONTH (monthly_xp)
    or in total. The monthly check matters because monthly_xp restarts at 0 after
    every monthly reset, while total_xp keeps growing.
    """
    if amount < 1:
        return {"success": False, "message": "Your bet must be at least 1 XP."}
    if amount > min(MAX_BET_PER_GAME, DAILY_BET_LIMIT):
        return {"success": False,
                "message": f"The maximum bet is {min(MAX_BET_PER_GAME, DAILY_BET_LIMIT):,} XP."}

    user = await users_col.find_one({"_id": userid}, {"total_xp": 1, "monthly_xp": 1})
    if user is None:
        return {"success": False, "message": not_registered_message(userid)}
    monthly = user.get("monthly_xp") or 0
    total = user.get("total_xp") or 0
    if amount > monthly:
        return {"success": False,
                "message": (f"You only have {monthly:,} monthly XP, so you can't bet {amount:,} XP. "
                            "Bets can only use XP you hold this month (monthly XP restarts at 0 "
                            "after each monthly reset).")}
    if amount > total:
        return {"success": False,
                "message": f"You only have {total:,} XP, so you can't bet {amount:,} XP."}

    today = utc_today()
    doc = None
    for _ in range(5):  # retries only happen when simultaneous bets race to create today's record
        # Same day: add to the counter only if it stays within the daily limit.
        doc = await daily_xp_col.find_one_and_update(
            {"_id": userid, "bet_date": today, "bet_xp": {"$lte": DAILY_BET_LIMIT - amount}},
            {"$inc": {"bet_xp": amount}},
            return_document=ReturnDocument.AFTER,
        )
        if doc:
            break
        status = await get_bet_status(userid)
        if status["staked_today"] + amount > DAILY_BET_LIMIT:
            left = status["remaining_today"]
            return {"success": False,
                    "message": f"Daily bet limit reached. You can still bet {left:,} XP today "
                               f"(limit {DAILY_BET_LIMIT:,} XP per day, resets at 00:00 UTC)."}
        if status["staked_today"] > 0:
            continue  # the bet fits: we only lost a race with another bet, so try again
        # First bet of a new day: start the counter from 0 + this bet.
        try:
            doc = await daily_xp_col.find_one_and_update(
                {"_id": userid, "bet_date": {"$ne": today}},
                {"$set": {"bet_date": today, "bet_xp": amount}},
                upsert=True, return_document=ReturnDocument.AFTER,
            )
            break
        except DuplicateKeyError:
            continue
    if not doc:
        return {"success": False, "message": "Could not place the bet, please try again."}

    return {
        "success": True,
        "message": f"Bet of {amount:,} XP placed.",
        "bet": amount,
        "staked_today": doc["bet_xp"],
        "remaining_today": max(0, DAILY_BET_LIMIT - doc["bet_xp"]),
    }


async def refund_bet(userid: int, amount: int) -> dict:
    """Release a reserved stake (game cancelled / crashed before settling)."""
    result = await daily_xp_col.update_one(
        {"_id": userid, "bet_date": utc_today(), "bet_xp": {"$gte": amount}},
        {"$inc": {"bet_xp": -amount}},
    )
    return {"success": result.modified_count > 0}


def payout_multiplier(game: str) -> int:
    """Win multiplier for a game: its override in config, else the global BET_WIN_MULTIPLIER."""
    return GAME_MULTIPLIER_OVERRIDES.get(game, BET_WIN_MULTIPLIER)


async def _record_history(userid: int, game: str, amount: int, outcome: str, delta: int,
                          total_xp: int | None, details: dict | None) -> None:
    try:
        await game_history_col.insert_one({
            "user_id": userid,
            "game": game,
            "bet": amount,
            "outcome": outcome,          # "win" | "loss" | "push"
            "won": outcome == "win",
            "xp_change": delta,
            "total_xp_after": total_xp,
            "date": utc_today(),
            "at": utc_now(),
            "details": details or {},
        })
    except Exception:  # the XP is already settled; a failed log line must not look like a failed bet
        log.exception("Could not write game history for user %s (%s).", userid, game)


async def settle_bet(userid: int, username: str, game: str, amount: int, won: bool,
                     details: dict | None = None) -> dict:
    """Apply the result of a bet that was reserved with place_bet.

    win  -> +amount x payout_multiplier(game) to total_xp AND monthly_xp
    loss -> -amount from total_xp AND monthly_xp (never below 0)
    """
    delta = amount * payout_multiplier(game) if won else -amount
    result = await xp_update(userid, username, delta)
    xp = result["xp"]
    await _record_history(userid, game, amount, "win" if won else "loss", delta,
                          xp["total_xp"], details)
    return {
        "success": True,
        "won": won,
        "xp_change": delta,
        "total_xp": xp["total_xp"],
        "monthly_xp": xp["monthly_xp"],
        "message": (f"You won! +{delta:,} XP" if won else f"You lost {amount:,} XP"),
    }


async def settle_push(userid: int, game: str, amount: int, details: dict | None = None) -> dict:
    """A tie: nobody wins. No XP changes and the stake is released from today's allowance."""
    await refund_bet(userid, amount)
    await _record_history(userid, game, amount, "push", 0, None, details)
    return {"success": True, "won": False, "push": True, "xp_change": 0,
            "message": "It's a tie - your bet was returned."}


async def get_game_stats(userid: int, game: str | None = None) -> dict:
    """Lifetime totals for a user (optionally for one game)."""
    match: dict = {"user_id": userid}
    if game:
        match["game"] = game
    rows = await game_history_col.aggregate([
        {"$match": match},
        {"$group": {"_id": None, "played": {"$sum": 1},
                    "wins": {"$sum": {"$cond": ["$won", 1, 0]}},
                    "pushes": {"$sum": {"$cond": [{"$eq": ["$outcome", "push"]}, 1, 0]}},
                    "staked": {"$sum": {"$cond": [{"$eq": ["$outcome", "push"]}, 0, "$bet"]}},
                    "net_xp": {"$sum": "$xp_change"}}},
    ]).to_list(length=1)
    r = rows[0] if rows else {"played": 0, "wins": 0, "pushes": 0, "staked": 0, "net_xp": 0}
    return {"success": True, "played": r["played"], "wins": r["wins"], "pushes": r["pushes"],
            "losses": r["played"] - r["wins"] - r["pushes"], "staked": r["staked"],
            "net_xp": r["net_xp"]}
