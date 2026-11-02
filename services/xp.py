"""The ONLY place cogs should use to change XP.

    grant_xp           add / remove XP right now                  -> rank check
    award_mission      complete a mission (held while paused)     -> announce + rank check
    pause_mission_xp   pause mission XP for EVERYONE
    resume_mission_xp  resume for EVERYONE, credit all held XP    -> rank check per user

Because every path ends in `check_rank`, a rank can never be missed, and the
pause logic lives in exactly one DB module (database.pause / database.missions).
"""
import discord

from database import complete_mission, pause_all, resume_all, xp_update

from .notify import post_mission_complete
from .ranks import check_rank


async def grant_xp(
    guild: discord.Guild, user_id: int, username: str, amount: int, *, msg_count: int = 0
) -> dict:
    """Add (amount > 0) or remove (amount < 0) XP. Not affected by the mission-XP pause."""
    result = await xp_update(user_id, username, amount, msg_count=msg_count)
    # Removing XP never downgrades a rank, so only check on gains.
    result["ranked_up"] = amount > 0 and await check_rank(guild, user_id, result["xp"]["total_xp"])
    return result


async def award_mission(
    guild: discord.Guild, user_id: int, username: str, mission_key: str,
    *, assigner: str = "Auto assigned.",
) -> dict:
    """Progress / complete a mission. On completion: announce, then rank check.

    While the global pause is on the mission is still recorded and announced,
    but its XP is held and no rank check is needed yet.
    Returns the database result (see database.missions.complete_mission).
    """
    result = await complete_mission(user_id, username, mission_key)
    if not result["success"]:
        return result

    await post_mission_complete(
        guild, user_id, result["mission"], paused=result["paused"], assigner=assigner)
    if not result["paused"]:
        await check_rank(guild, user_id, result["total_xp"])
    return result


async def pause_mission_xp(admin_id: int, reason: str | None = None) -> dict:
    """Pause mission XP for every user."""
    return await pause_all(admin_id, reason)


async def resume_mission_xp(guild: discord.Guild, admin_id: int) -> dict:
    """Resume mission XP for every user, credit everything held, then rank-check each user.

    Adds "ranked_up": number of users promoted by the released XP.
    """
    result = await resume_all(admin_id)
    result["ranked_up"] = 0
    for item in result.get("users", []):
        if await check_rank(guild, item["user_id"], item["total_xp"]):
            result["ranked_up"] += 1
    return result
