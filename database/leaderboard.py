"""Leaderboard and rank-position queries (require MongoDB 5.0+ for $setWindowFields)."""
import asyncio

from .connection import users_col
from .helpers import not_registered_message


def _rank_pipeline(xp_field: str, *extra_stages: dict) -> list:
    return [
        {"$setWindowFields": {"sortBy": {xp_field: -1}, "output": {"position": {"$rank": {}}}}},
        *extra_stages,
    ]


async def get_leaderboard(userid: int, leaderboard_type: str = "total") -> dict:
    xp_field = "monthly_xp" if leaderboard_type == "monthly" else "total_xp"

    current_user = await users_col.find_one({"_id": userid}, {"username": 1, xp_field: 1})
    if not current_user:
        return {"success": False, "message": not_registered_message(userid)}

    pipeline = _rank_pipeline(
        xp_field,
        {"$match": {"$or": [{"position": {"$lte": 10}}, {"_id": userid}]}},
        {"$project": {"_id": 1, "username": 1, xp_field: 1, "position": 1}},
    )
    results = await users_col.aggregate(pipeline).to_list(length=None)
    # $rank only sorts by one field, so break ties by username here.
    results.sort(key=lambda x: (x["position"], x.get("username", "")))

    top_10, user_entry = [], None
    for entry in results:
        formatted = {
            "position": entry["position"],
            "username": entry.get("username", "Unknown"),
            "xp": entry.get(xp_field, 0),
        }
        if entry["_id"] == userid:
            user_entry = formatted
        if entry["position"] <= 10 and len(top_10) < 10:
            top_10.append(formatted)

    return {"success": True, "leaderboard_type": leaderboard_type,
            "top_10": top_10, "user": user_entry}


async def get_user_rank_position(userid: int) -> dict:
    """Position of a user on the total and monthly leaderboards."""
    def pipeline(field: str):
        return _rank_pipeline(
            field, {"$match": {"_id": userid}},
            {"$project": {"_id": 1, "username": 1, field: 1, "position": 1}})

    total_result, monthly_result = await asyncio.gather(
        users_col.aggregate(pipeline("total_xp")).to_list(length=1),
        users_col.aggregate(pipeline("monthly_xp")).to_list(length=1),
    )
    if not total_result:
        return {"success": False, "message": "User not found!"}

    total_entry = total_result[0]
    monthly_entry = monthly_result[0] if monthly_result else {}
    return {
        "success": True,
        "username": total_entry["username"],
        "total_xp": total_entry.get("total_xp", 0),
        "total_position": total_entry["position"],
        "monthly_xp": monthly_entry.get("monthly_xp", 0),
        "monthly_position": monthly_entry.get("position"),
    }
