"""Weekly / monthly resets and the CSV snapshot taken before each one."""
import csv
import io

from .connection import users_col
from .helpers import utc_now


async def generate_snapshot_csv(reset_type: str) -> tuple[io.BytesIO, str]:
    timestamp = utc_now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"{reset_type}_reset_snapshot_{timestamp}.csv"

    users = await users_col.find({}).to_list(length=None)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["Username", "User ID", "Total XP", "Monthly XP",
                     "Missions Completed", "Held XP"])
    for user in users:
        writer.writerow([
            user.get("username", ""), user.get("_id", ""),
            user.get("total_xp", 0), user.get("monthly_xp", 0),
            len(user.get("missions", [])),
            user.get("pending_xp", 0),
        ])

    byte_buffer = io.BytesIO(buffer.getvalue().encode("utf-8"))
    byte_buffer.seek(0)
    return byte_buffer, filename


async def weekly_reset() -> dict:
    """Clear weekly mission progress. XP held by the global pause is intentionally kept."""
    file, filename = await generate_snapshot_csv("weekly")
    result = await users_col.update_many({}, {"$set": {
        "msg_general": 0, "missions": [], "correct_match_take": 0, "predictions": 0,
        "x_comments": 0, "x_retweets": 0, "x_likes": 0, "daily_streak": 0,
        "memes": 0, "last_msg_date": None,
    }})
    return {"success": True, "modified_users": result.modified_count,
            "file": file, "filename": filename}


async def monthly_reset() -> dict:
    file, filename = await generate_snapshot_csv("monthly")
    result = await users_col.update_many({}, {"$set": {"monthly_xp": 0}})
    return {"success": True, "modified_users": result.modified_count,
            "file": file, "filename": filename}
