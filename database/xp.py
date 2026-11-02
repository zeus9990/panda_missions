"""Direct XP changes (messages, admin add/remove) and daily message-XP cap state."""
from pymongo import ReturnDocument

from .connection import daily_xp_col, users_col
from .helpers import utc_today
from .users import user_register


async def xp_update(userid: int, username: str, xp_amount: int, msg_count: int = 0) -> dict:
    """Add (positive) or remove (negative) XP. Totals never drop below 0.

    Prefer `services.xp.grant_xp`, which also runs the central rank check.
    """
    await user_register(userid, username)

    def bump(field: str):
        return {"$max": [0, {"$add": [{"$ifNull": [f"${field}", 0]}, xp_amount]}]}

    updated = await users_col.find_one_and_update(
        {"_id": userid},
        [{"$set": {
            "total_xp": bump("total_xp"),
            "monthly_xp": bump("monthly_xp"),
            "msg_general": {"$add": [{"$ifNull": ["$msg_general", 0]}, msg_count]},
        }}],
        return_document=ReturnDocument.AFTER,
    )
    return {
        "success": True,
        "message": (
            f"{'Added' if xp_amount >= 0 else 'Removed'} {abs(xp_amount)} XP "
            f"{'to' if xp_amount >= 0 else 'from'} <@{userid}>."
        ),
        "xp": {
            "total_xp": updated["total_xp"],
            "monthly_xp": updated["monthly_xp"],
            "msg_general": updated["msg_general"],
        },
    }


async def get_daily_xp_progress(userid: int, channel_id: int) -> dict:
    """Fetch today's cap-tracking state, registering `channel_id` as visited.

    Resets automatically on a new UTC day. Returns
    {"is_first_message_today", "channels", "xp_earned"}.
    """
    today = utc_today()
    updated = await daily_xp_col.find_one_and_update(
        {"_id": userid, "date": today},
        {"$addToSet": {"channels": channel_id}},
        return_document=ReturnDocument.AFTER,
    )
    if updated:
        return {
            "is_first_message_today": False,
            "channels": updated.get("channels", []),
            "xp_earned": updated.get("xp_earned", 0),
        }

    updated = await daily_xp_col.find_one_and_update(
        {"_id": userid},
        {"$set": {"date": today, "channels": [channel_id], "xp_earned": 0}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return {
        "is_first_message_today": True,
        "channels": updated.get("channels", [channel_id]),
        "xp_earned": updated.get("xp_earned", 0),
    }


async def add_daily_xp(userid: int, xp_amount: int) -> int:
    """Add to today's tracked message XP (cap tracking only). Returns the new value."""
    today = utc_today()
    updated = await daily_xp_col.find_one_and_update(
        {"_id": userid, "date": today},
        {"$inc": {"xp_earned": xp_amount}},
        return_document=ReturnDocument.AFTER,
    )
    if updated is None:
        # No record for today yet. (The old code upserted on {_id, date}, which
        # raises DuplicateKeyError when yesterday's record still exists.)
        updated = await daily_xp_col.find_one_and_update(
            {"_id": userid},
            {"$set": {"date": today, "channels": [], "xp_earned": xp_amount}},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
    return updated.get("xp_earned", xp_amount)
