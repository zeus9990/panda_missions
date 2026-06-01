import motor.motor_asyncio
from pymongo import ReturnDocument
from datetime import datetime, timezone, date
from config import WEEKLY_MISSIONS, DB_URL
import io
import csv
import asyncio

# data_set ={
#     "_id": 7892377357757735,
#     "username": "zeus",
#     "total_xp": 23472,
#     "monthly_xp": 788,
#     "rank": 723873773873472472,
#     "missions": [], #mission_ids of completed missions goes in here
#     "msg_general": 77,
#     "correct_match_take": 0,
#     "predictions": 0,
#     "x_comments": 0,
#     "x_retweets": 0,
#     "x_likes": 0,
#     "engage_points": 0,
#     "daily_streak": 0,
#     "last_msg_date": None,
#     "created_at": "23-08-26"
# }


database = motor.motor_asyncio.AsyncIOMotorClient(DB_URL)
pandabase = database["Betpanda"]
betpanda = pandabase["betpanda"]
print("Database connection Successfull!!")

# Database indexing
async def setup_indexes() -> None:
    await betpanda.create_index([("total_xp", -1)])
    await betpanda.create_index([("monthly_xp", -1)])

# Generates an in-memory CSV snapshot of all users.
async def generate_snapshot_csv(reset_type: str) -> tuple[io.BytesIO, str]:
    now = datetime.now(timezone.utc)
    timestamp = now.strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"{reset_type}_reset_snapshot_{timestamp}.csv"
    users = await betpanda.find({}).to_list(length=None)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["Username", "User ID", "Total XP", "Monthly XP", "Missions Completed"])

    for user in users:
        writer.writerow([
            user.get("username", ""),
            user.get("_id", ""),
            user.get("total_xp", 0),
            user.get("monthly_xp", 0),
            len(user.get("missions", []))
        ])

    byte_buffer = io.BytesIO(buffer.getvalue().encode("utf-8"))
    byte_buffer.seek(0)
    return byte_buffer, filename

# Register a new user in the database at first interaction with the bot.
async def user_register(userid: int, username: str) -> dict:
    today_str = datetime.now(timezone.utc).date().isoformat()

    result = await betpanda.update_one(
        {"_id": userid},
        {
            "$setOnInsert": {
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
                "last_msg_date": None,
                "created_at": today_str
            }
        },
        upsert=True
    )

    if result.upserted_id:
        return {"success": True, "message": "Registration successful."}

    return {"success": False, "message": "User already registered."}
    
# Fetches data of a user from the database.
async def user_details(userid: int) -> dict:
    user_details = await betpanda.find_one({'_id': userid})
    if user_details:
        return {"success": True, "message": user_details}
    else:
        return {"success": False, "message": f"Sorry <@{userid}> you're not registered yet, send a message in general chat to register yourself."}

# Add or remove Xp from a user also updates the weekly message count if given.
async def xp_update(userid: int, username: str, xp_amount: int, msg_count: int=0) -> dict:
    await user_register(userid, username)
    updated_user = await betpanda.find_one_and_update(
        {"_id": userid},
        {
            "$inc": {
                "msg_general": msg_count,
                "total_xp": xp_amount,
                "monthly_xp": xp_amount
            }
        },
        return_document=ReturnDocument.AFTER
    )

    return {
        "success": True,
        "message": f"{'Added' if xp_amount >= 0 else 'Removed'} {abs(xp_amount)} XP {'to' if xp_amount >= 0 else 'from'} <@{userid}>.",
        "xp": {
            "total_xp": updated_user["total_xp"],
            "monthly_xp": updated_user["monthly_xp"],
            "msg_general": updated_user["msg_general"]
            }
        }

# Pull leaderboard and current position in the leaderboard.
async def get_leaderboard(userid: int, leaderboard_type: str = "total") -> dict:
    xp_field = "monthly_xp" if leaderboard_type == "monthly" else "total_xp"
    current_user = await betpanda.find_one({"_id": userid}, {"username": 1, xp_field: 1})
    if not current_user:
        return {
            "success": False,
            "message": f"Sorry <@{userid}> you're not registered yet, send a message in general chat to register yourself."
        }

    # Single aggregation pipeline gets top 10 + current user rank atomically
    pipeline = [
        {
            "$setWindowFields": {
                "sortBy": {xp_field: -1},
                "output": {
                    "position": {"$rank": {}}
                }
            }
        },
        {
            "$match": {
                "$or": [
                    {"position": {"$lte": 10}},
                    {"_id": userid}
                ]
            }
        },
        {
            "$project": {
                "_id": 1,
                "username": 1,
                xp_field: 1,
                "position": 1
            }
        }
    ]

    results = await betpanda.aggregate(pipeline).to_list(length=None)

    top_10 = []
    user_entry = None

    for entry in results:
        formatted = {
            "position": entry["position"],
            "username": entry["username"],
            "xp": entry.get(xp_field, 0)
        }
        if entry["position"] <= 10:
            top_10.append(formatted)
        if entry["_id"] == userid:
            user_entry = formatted
    top_10.sort(key=lambda x: x["position"])

    return {
        "success": True,
        "leaderboard_type": leaderboard_type,
        "top_10": top_10,
        "user": user_entry
    }

# Get position of a user in monthly and total xp leaderboard.
async def get_user_rank_position(userid: int) -> dict:
    pipeline_total = [
        {
            "$setWindowFields": {
                "sortBy": {"total_xp": -1},
                "output": {"position": {"$rank": {}}}
            }
        },
        {"$match": {"_id": userid}},
        {"$project": {"_id": 1, "username": 1, "total_xp": 1, "position": 1}}
    ]

    pipeline_monthly = [
        {
            "$setWindowFields": {
                "sortBy": {"monthly_xp": -1},
                "output": {"position": {"$rank": {}}}
            }
        },
        {"$match": {"_id": userid}},
        {"$project": {"_id": 1, "monthly_xp": 1, "position": 1}}
    ]

    total_result, monthly_result = await asyncio.gather(
        betpanda.aggregate(pipeline_total).to_list(length=1),
        betpanda.aggregate(pipeline_monthly).to_list(length=1)
    )

    if not total_result:
        return {
            "success": False,
            "message": "User not found!"
        }

    total_entry = total_result[0]
    monthly_entry = monthly_result[0] if monthly_result else {}

    return {
        "success": True,
        "username": total_entry["username"],
        "total_xp": total_entry.get("total_xp", 0),
        "total_position": total_entry["position"],
        "monthly_xp": monthly_entry.get("monthly_xp", 0),
        "monthly_position": monthly_entry.get("position")
    }

# Update missions for users as they progress.
async def complete_mission(userid: int, username: str, mission_key: str) -> dict:
    await user_register(userid, username)
    mission = WEEKLY_MISSIONS.get(mission_key)

    if not mission:
        return {"success": False, "message": "Invalid mission."}
    
    if mission.get("status") != "Active":
        return {"success": False, "message": "This mission is not active."}
    
    mission_desc = mission['description']
    mission_id = mission["mission_id"]
    xp_reward = mission["xp_reward"]
    required_count = mission.get("count")

    # Counted missions
    if required_count:
        # Only increment if mission not already completed
        inc_result = await betpanda.update_one(
            {
                "_id": userid,
                "missions": {"$ne": mission_id}
            },
            {
                "$inc": {mission_key: 1}
            }
        )

        if inc_result.modified_count == 0:
            return {"success": False, "message": "This Mission is already completed for this user."}

        # Fetch the updated counter value
        user = await betpanda.find_one(
            {"_id": userid},
            {mission_key: 1}
        )
        current_count = user.get(mission_key, 0)

        # Not there yet, return progress
        if current_count < required_count:
            return {
                "success": False,
                "message": f"Progress updated for <@{userid}>! ({current_count}/{required_count})",
                "progress": {
                    "current": current_count,
                    "required": required_count
                }
            }

        # Counter reached — mark mission as complete and award XP atomically
        updated_user = await betpanda.find_one_and_update(
            {"_id": userid},
            {
                "$addToSet": {"missions": mission_id},
                "$inc": {
                    "total_xp": xp_reward,
                    "monthly_xp": xp_reward
                }
            },
            return_document=True
        )

    # Single-action mission
    else:
        result = await betpanda.update_one(
            {
                "_id": userid,
                "missions": {"$ne": mission_id}
            },
            {
                "$addToSet": {"missions": mission_id},
                "$inc": {
                    "total_xp": xp_reward,
                    "monthly_xp": xp_reward
                }
            }
        )

        if result.modified_count == 0:
            return {"success": False, "message": "This Mission is already completed for this user."}

        updated_user = await betpanda.find_one({"_id": userid}, {"total_xp": 1})

    return {
        "success": True,
        "message": f"Mission completed for <@{userid}>! +{xp_reward} XP",
        "total_xp": updated_user.get("total_xp", 0),
        "mission": {
            "description": mission_desc,
            "mission_id": mission_id,
            "name": mission["name"],
            "xp_reward": xp_reward
        }
    }

# Updates the user's rank role_id in database.
async def update_user_rank(userid: int, role_id: int) -> dict:
    result = await betpanda.update_one(
        {
            "_id": userid,
            "rank": {"$ne": role_id}
        },
        {
            "$set": {
                "rank": role_id
            }
        }
    )

    if result.modified_count == 0:
        return {"success": False, "message": "User already has this rank."}

    return {"success": True, "message": "Rank updated successfully.", "role_id": role_id}

# Update engage points cache for user.
async def update_engage_cache(userid: int, engage_points: int) -> bool:
    result = await betpanda.update_one(
        {"_id": userid},
        {"$set": {"engage_points": engage_points}}
    )
    return result.modified_count > 0

# Update daily message streak
async def update_streak(userid: int) -> dict:
    today = datetime.now(timezone.utc).date().isoformat()

    user = await betpanda.find_one({"_id": userid}, {"daily_streak": 1, "last_msg_date": 1})
    if not user:
        return {"success": False, "streak": 0}

    last_msg_date = user.get("last_msg_date")
    current_streak = user.get("daily_streak", 0)

    if last_msg_date == today:
        # Already messaged today, no streak change
        return {"success": False, "streak": current_streak}
    
    if last_msg_date:
        last_date = date.fromisoformat(last_msg_date)
        today_date = date.fromisoformat(today)
        diff = (today_date - last_date).days
        new_streak = current_streak + 1 if diff == 1 else 1  # consecutive = +1, else reset
    else:
        new_streak = 1

    updated_user = await betpanda.find_one_and_update(
        {"_id": userid},
        {"$set": {
            "daily_streak": new_streak,
            "last_msg_date": today
        }},
        return_document=True
    )

    return {
        "success": True,
        "streak": updated_user["daily_streak"]
    }

# Weekly reset
async def weekly_reset() -> dict:
    file, filename = await generate_snapshot_csv("weekly")
    result = await betpanda.update_many(
        {},
        {"$set": {
            "msg_general": 0,
            "missions": [],
            "correct_match_take": 0,
            "predictions": 0,
            "x_comments": 0,
            "x_retweets": 0,
            "x_likes": 0,
            "daily_streak": 0,
            "last_msg_date": None
        }}
    )
    return {
        "success": True,
        "modified_users": result.modified_count,
        "file": file,
        "filename": filename
    }

# monthly xp reset
async def monthly_reset() -> dict:
    file, filename = await generate_snapshot_csv("monthly")
    result = await betpanda.update_many({}, {"$set": {"monthly_xp": 0}})
    return {
        "success": True,
        "modified_users": result.modified_count,
        "file": file,
        "filename": filename
    }