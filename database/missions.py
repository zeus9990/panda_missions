"""Mission completion.

XP for a completed mission is either credited or - while the GLOBAL mission-XP
pause is on (database/pause.py) - held on the user document:

    not paused -> total_xp / monthly_xp += reward
    paused     -> pending_xp += reward, entry added to pending_missions

The credit/hold and the "mark mission completed" happen in ONE atomic update.
Prefer `services.xp.award_mission`, which also announces and runs the rank check.
"""
from pymongo import ReturnDocument

from config import WEEKLY_MISSIONS

from .connection import users_col
from .pause import flush_user_pending, is_paused
from .users import user_register

# Counter that is maintained by the message-XP code (xp_update). For it
# complete_mission only READS the counter; it must not add 1 on top of it.
# (daily_streak intentionally still gets +1 here: the streak mission completes
# on day 6, exactly as before the refactor.)
EXTERNALLY_TRACKED = {"msg_general"}


def _award_pipeline(mission_key: str, mission: dict, paused: bool) -> list:
    xp = mission["xp_reward"]
    held = {"mission_id": mission["mission_id"], "key": mission_key,
            "name": mission["name"], "xp": xp}

    def add(field: str, amount):
        return {"$add": [{"$ifNull": [f"${field}", 0]}, amount]}

    return [{"$set": {
        "missions": {"$concatArrays": [
            {"$ifNull": ["$missions", []]}, {"$literal": [mission["mission_id"]]}]},
        "total_xp": add("total_xp", 0 if paused else xp),
        "monthly_xp": add("monthly_xp", 0 if paused else xp),
        "pending_xp": add("pending_xp", xp if paused else 0),
        "pending_missions": {"$concatArrays": [
            {"$ifNull": ["$pending_missions", []]},
            {"$literal": [held]} if paused else []]},
    }}]


async def complete_mission(userid: int, username: str, mission_key: str) -> dict:
    """Progress / complete a mission for a user.

    Returns {"success": bool, "message": str, ...}. On success also:
        paused      -> True when the XP was held instead of credited
        total_xp    -> credited total after this call
        pending_xp  -> XP currently held for the user
        mission     -> {description, mission_id, name, xp_reward}
    """
    mission = WEEKLY_MISSIONS.get(mission_key)
    if not mission:
        return {"success": False, "message": "Invalid mission."}
    if mission.get("status") != "Active":
        return {"success": False, "message": "This mission is not active."}

    await user_register(userid, username)

    mission_id = mission["mission_id"]
    required = mission.get("count")
    not_done = {"_id": userid, "missions": {"$ne": mission_id}}

    if required:
        if mission_key in EXTERNALLY_TRACKED:
            doc = await users_col.find_one(not_done, {mission_key: 1})
        else:
            doc = await users_col.find_one_and_update(
                not_done, {"$inc": {mission_key: 1}},
                projection={mission_key: 1}, return_document=ReturnDocument.AFTER)
        if doc is None:
            return {"success": False, "message": "This Mission is already completed for this user."}

        current = doc.get(mission_key, 0)
        if current < required:
            return {
                "success": False,
                "message": f"Progress updated for <@{userid}>! ({current}/{required})",
                "progress": {"current": current, "required": required},
            }

    paused = await is_paused()
    updated = await users_col.find_one_and_update(
        not_done, _award_pipeline(mission_key, mission, paused),
        return_document=ReturnDocument.AFTER)
    if updated is None:  # a concurrent call completed it first
        return {"success": False, "message": "This Mission is already completed for this user."}

    if paused and not await is_paused():
        # The pause was lifted while we were writing: our held XP may have been
        # missed by the resume sweep, so credit it ourselves.
        flushed = await flush_user_pending(userid)
        if flushed:
            paused = False
            updated["total_xp"] = flushed["total_xp"]
            updated["pending_xp"] = 0

    xp = mission["xp_reward"]
    return {
        "success": True,
        "paused": paused,
        "message": (
            f"Mission completed for <@{userid}>! +{xp} XP"
            + (" (held - mission XP is paused)" if paused else "")
        ),
        "total_xp": updated.get("total_xp", 0),
        "pending_xp": updated.get("pending_xp", 0),
        "mission": {
            "description": mission["description"],
            "mission_id": mission_id,
            "name": mission["name"],
            "xp_reward": xp,
        },
    }
