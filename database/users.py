"""User documents: registration, lookup, rank role, engage cache, daily streak.

Document shape (see `_new_user_doc`):
    total_xp / monthly_xp   -> credited XP
    missions                -> mission_ids completed this week
    pending_xp              -> mission XP being held while the GLOBAL pause is on
    pending_missions        -> [{mission_id, key, name, xp}] being held
"""
from datetime import date

from pymongo import ReturnDocument

from .connection import users_col
from .helpers import not_registered_message, utc_today


def _new_user_doc(username: str) -> dict:
    return {
        "username": username,
        "total_xp": 0,
        "monthly_xp": 0,
        "rank": 0,
        "missions": [],
        "msg_general": 0,
        "correct_match_take": 0,
        "predictions": 0,
        "x_likes": 0,
        "x_comments": 0,
        "x_retweets": 0,
        "engage_points": 0,
        "daily_streak": 0,
        "memes": 0,
        "last_msg_date": None,
        "created_at": utc_today(),
        # mission XP held while the global pause is on (see database/pause.py)
        "pending_xp": 0,
        "pending_missions": [],
    }


async def user_register(userid: int, username: str) -> dict:
    """Create the user on first interaction. Safe to call repeatedly."""
    result = await users_col.update_one(
        {"_id": userid},
        {"$setOnInsert": _new_user_doc(username)},
        upsert=True,
    )
    if result.upserted_id is not None:
        return {"success": True, "message": "Registration successful."}
    return {"success": False, "message": "User already registered."}


async def user_details(userid: int) -> dict:
    """Return {"success": True, "message": <user doc>} or a not-registered message."""
    user = await users_col.find_one({"_id": userid})
    if user:
        return {"success": True, "message": user}
    return {"success": False, "message": not_registered_message(userid)}


async def get_current_rank(userid: int) -> int:
    """Role id of the user's stored rank (0 when unranked / unknown)."""
    user = await users_col.find_one({"_id": userid}, {"rank": 1})
    return (user or {}).get("rank", 0) or 0


async def update_user_rank(userid: int, role_id: int) -> dict:
    """Atomically store a new rank role id. Fails if it is already stored."""
    result = await users_col.update_one(
        {"_id": userid, "rank": {"$ne": role_id}},
        {"$set": {"rank": role_id}},
    )
    if result.modified_count == 0:
        return {"success": False, "message": "User already has this rank."}
    return {"success": True, "message": "Rank updated successfully.", "role_id": role_id}


async def update_engage_cache(userid: int, engage_points: int) -> bool:
    result = await users_col.update_one(
        {"_id": userid}, {"$set": {"engage_points": engage_points}}
    )
    return result.modified_count > 0


async def update_streak(userid: int) -> dict:
    """Advance the daily message streak (once per UTC day)."""
    today = utc_today()
    user = await users_col.find_one({"_id": userid}, {"daily_streak": 1, "last_msg_date": 1})
    if not user:
        return {"success": False, "streak": 0}

    last_msg_date = user.get("last_msg_date")
    current = user.get("daily_streak", 0)
    if last_msg_date == today:
        return {"success": False, "streak": current}

    if last_msg_date:
        days = (date.fromisoformat(today) - date.fromisoformat(last_msg_date)).days
        new_streak = current + 1 if days == 1 else 1
    else:
        new_streak = 1

    # The `$ne` guard stops two simultaneous messages from advancing it twice.
    updated = await users_col.find_one_and_update(
        {"_id": userid, "last_msg_date": {"$ne": today}},
        {"$set": {"daily_streak": new_streak, "last_msg_date": today}},
        return_document=ReturnDocument.AFTER,
    )
    if updated is None:
        return {"success": False, "streak": current}
    return {"success": True, "streak": updated["daily_streak"]}
