"""Daily Discord / Telegram join, leave and message statistics."""
from typing import Optional, Set, Union

from pymongo import ReturnDocument

from .connection import platform_stats_col
from .helpers import utc_now, utc_today


async def record_stat_event(
    platform: str,                      # "discord" | "telegram_group" | "telegram_channel"
    event_type: str,                    # "join" | "leave" | "message"
    user_id: Union[int, str],
    total_members: Optional[int] = None,
    event_date: Optional[str] = None,
) -> dict:
    event_date = event_date or utc_today()
    filter_ = {"platform": platform, "date": event_date}
    update: dict = {"$set": {"updated_at": utc_now()}}

    if event_type == "join":
        update["$inc"] = {"total_joined": 1, "growth": 1}
    elif event_type == "leave":
        update["$inc"] = {"total_left": 1, "growth": -1}
    elif event_type == "message":
        update["$inc"] = {"total_messages": 1}
        update["$addToSet"] = {"active_user_ids": str(user_id)}
        update["$setOnInsert"] = {"total_joined": 0, "total_left": 0, "growth": 0}
    else:
        raise ValueError(f"Unknown event_type: {event_type}")

    if total_members is not None:
        update["$set"]["total_members"] = total_members

    doc = await platform_stats_col.find_one_and_update(
        filter_, update, upsert=True, return_document=ReturnDocument.AFTER)

    if event_type == "message":
        await platform_stats_col.update_one(
            filter_, {"$set": {"active_members": len(doc.get("active_user_ids", []))}})
    return doc


async def get_stats_range(platform: str, start_date: str, end_date: str) -> dict:
    cursor = platform_stats_col.find(
        {"platform": platform, "date": {"$gte": start_date, "$lte": end_date}}
    ).sort("date", -1)  # newest first so total_members comes from the latest day

    total_joined = total_left = total_messages = days_seen = 0
    active_ids: Set[str] = set()
    total_members = None

    async for doc in cursor:
        days_seen += 1
        total_joined += doc.get("total_joined", 0)
        total_left += doc.get("total_left", 0)
        total_messages += doc.get("total_messages", 0)
        active_ids.update(doc.get("active_user_ids", []))
        if total_members is None:
            total_members = doc.get("total_members")

    return {
        "platform": platform,
        "start_date": start_date,
        "end_date": end_date,
        "total_joined": total_joined,
        "total_left": total_left,
        "member_growth": total_joined - total_left,
        "total_messages": total_messages,
        "average_daily_messages": round(total_messages / max(days_seen, 1), 2),
        "active_members": len(active_ids),
        "total_members": total_members,
    }
