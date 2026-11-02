"""GLOBAL pause / resume of mission XP (one switch for every user).

While the switch is ON:
    * completed missions are still recorded, but their XP is held per user in
      `pending_xp` / `pending_missions` instead of being credited.
When it is switched OFF:
    * every user's held XP is credited to total_xp + monthly_xp.

Only MISSION XP is held; message XP, admin add/remove and mini-game results are
unaffected. Held XP survives the weekly reset.

Why the extra re-check in database.missions: the switch lives in `settings`
while the XP lives on the user document, so they cannot change in one atomic
update. Resume therefore (1) turns the switch off, then (2) flushes each user's
held XP with a per-user atomic update; a mission that read "paused" just before
step 1 re-checks the switch after holding and flushes itself. Nothing is stranded.
"""
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from .connection import settings_col, users_col
from .helpers import utc_now

_SETTING_ID = "mission_xp_pause"


async def get_pause_state() -> dict:
    """{"paused": bool, "paused_at", "paused_by", "reason"}  (cheap: one read)."""
    doc = await settings_col.find_one({"_id": _SETTING_ID}) or {}
    return {
        "paused": bool(doc.get("paused")),
        "paused_at": doc.get("paused_at"),
        "paused_by": doc.get("paused_by"),
        "reason": doc.get("reason"),
    }


async def is_paused() -> bool:
    doc = await settings_col.find_one({"_id": _SETTING_ID}, {"paused": 1})
    return bool(doc and doc.get("paused"))


async def pause_all(admin_id: int, reason: str | None = None) -> dict:
    """Pause mission XP for everyone."""
    try:
        result = await settings_col.update_one(
            {"_id": _SETTING_ID, "paused": {"$ne": True}},
            {"$set": {"paused": True, "paused_at": utc_now(), "paused_by": admin_id, "reason": reason}},
            upsert=True,
        )
    except DuplicateKeyError:  # document exists and is already paused
        return {"success": False, "message": "Mission XP is already paused for everyone."}
    if result.matched_count == 0 and result.upserted_id is None:
        return {"success": False, "message": "Mission XP is already paused for everyone."}
    return {"success": True, "message": "Mission XP paused for everyone."}


async def flush_user_pending(userid: int) -> dict | None:
    """Atomically credit one user's held XP. Returns None if they had none."""
    before = await users_col.find_one_and_update(
        {"_id": userid, "pending_xp": {"$gt": 0}},
        [{"$set": {
            "total_xp": {"$add": [{"$ifNull": ["$total_xp", 0]}, "$pending_xp"]},
            "monthly_xp": {"$add": [{"$ifNull": ["$monthly_xp", 0]}, "$pending_xp"]},
            "pending_xp": 0,
            "pending_missions": [],
        }}],
        return_document=ReturnDocument.BEFORE,
    )
    if before is None:
        return None
    credited = before["pending_xp"]
    return {
        "user_id": userid,
        "credited_xp": credited,
        "missions": before.get("pending_missions", []),
        "total_xp": before.get("total_xp", 0) + credited,
        "monthly_xp": before.get("monthly_xp", 0) + credited,
    }


async def resume_all(admin_id: int) -> dict:
    """Resume mission XP for everyone and credit every user's held XP.

    Returns {"success", "was_paused", "users": [flush results], "total_credited"}.
    Also credits leftovers if an earlier resume was interrupted (e.g. a restart),
    so it is safe to simply run it again.
    """
    result = await settings_col.update_one(
        {"_id": _SETTING_ID, "paused": True},
        {"$set": {"paused": False, "resumed_at": utc_now(), "resumed_by": admin_id},
         "$unset": {"paused_at": "", "paused_by": "", "reason": ""}},
    )
    was_paused = result.modified_count > 0

    user_ids = [d["_id"] async for d in users_col.find({"pending_xp": {"$gt": 0}}, {"_id": 1})]
    flushed = []
    for user_id in user_ids:
        item = await flush_user_pending(user_id)
        if item:
            flushed.append(item)

    if not was_paused and not flushed:
        return {"success": False, "message": "Mission XP is not paused.",
                "was_paused": False, "users": [], "total_credited": 0}
    return {
        "success": True,
        "message": "Mission XP resumed for everyone.",
        "was_paused": was_paused,
        "users": flushed,
        "total_credited": sum(u["credited_xp"] for u in flushed),
    }


async def get_pause_summary() -> dict:
    """Global state + how many users / how much XP is currently held."""
    state = await get_pause_state()
    agg = await users_col.aggregate([
        {"$match": {"pending_xp": {"$gt": 0}}},
        {"$group": {"_id": None, "users": {"$sum": 1}, "xp": {"$sum": "$pending_xp"}}},
    ]).to_list(length=1)
    held = agg[0] if agg else {"users": 0, "xp": 0}
    return {**state, "held_users": held["users"], "held_xp": held["xp"]}


async def get_user_held(userid: int) -> dict:
    """What a single user currently has held."""
    user = await users_col.find_one({"_id": userid}, {"pending_xp": 1, "pending_missions": 1})
    if user is None:
        return {"success": False, "message": "User not found."}
    return {"success": True, "pending_xp": user.get("pending_xp", 0) or 0,
            "pending_missions": user.get("pending_missions", [])}
