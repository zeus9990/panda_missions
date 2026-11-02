"""MongoDB client, collection handles and index setup.

Every other module in this package imports its collection from here, so
there is exactly one place that knows the database/collection names.
"""
import motor.motor_asyncio

from config import DB_URL

client = motor.motor_asyncio.AsyncIOMotorClient(DB_URL, tz_aware=True)  # tz_aware: datetimes come back as UTC-aware
db = client["Betpanda"]

users_col = db["betpanda"]              # one document per Discord user
platform_stats_col = db["platform_stats"]  # one document per platform per day
daily_xp_col = db["daily_xp_state"]     # per-user daily state: message-XP cap + XP staked on bets
settings_col = db["settings"]           # global switches (e.g. mission-XP pause)
game_history_col = db["game_history"]   # one document per settled mini-game bet


async def setup_indexes() -> None:
    await users_col.create_index([("total_xp", -1)])
    await users_col.create_index([("monthly_xp", -1)])
    await platform_stats_col.create_index([("platform", 1), ("date", 1)], unique=True)
    await daily_xp_col.create_index([("date", 1)])
    await game_history_col.create_index([("user_id", 1), ("at", -1)])
    await game_history_col.create_index([("game", 1), ("date", 1)])
