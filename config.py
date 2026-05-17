# Discord Bot Configuration Settings
import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")          # Discord bot token from discord developer portal.
DB_URL = os.getenv("DB_URL")                # Database cluster connection url from MongoDB.

ADMIN_ROLE_IDS = [987654321098765432]       # Role ID that can execute Moderator / Admin commands.
LOG_CHANNEL_ID = 1505503532240080997        # Channel ID where bot alerts & bonus logs are posted.
MISSION_CHANNEL_ID = 1505503435938730115    # Channel ID where bot will ping users upon mission complition and role grants.
GENERAL_CHAT_ID = 1505503470101201037       # General chat ID required for completion of general chat message mission.
WEEKLY_MSG_COUNT = 20                       # Required weekly message count for mission.
COOLDOWN_SECONDS = 60                       # Cooldown time between messages to avoid spam.

# Message length-based XP formula configurations.
# e.g., XP earned = random(min, max) based on message length ranges.
XP_LENGTH_RULES = [
    {"max_len": 10, "min_xp": 5, "max_xp": 10},
    {"max_len": 50, "min_xp": 10, "max_xp": 20}
]

# Channel IDs that award XP (Channel IDs)
XP_CHANNELS = [111111111111111111, 1505503470101201037, 1342783479703797760, 874537537577357]

# Rank Thresholds
# Auto-assigned role IDs when hitting required XP levels.
# Users keep their highest rank (no downgrades) and XP accumulates forever.
RANK_THRESHOLDS = [
    {
        "name": "Bamboo Sprout",
        "xp": 1000,
        "role_id": 1416418249935159348
    },
    {
        "name": "Bamboo Muncher",
        "xp": 10000,
        "role_id": 1416418292821917756
    },
    {
        "name": "High Stakes Panda",
        "xp": 25000,
        "role_id": 1505503784514879488
    },
    {
        "name": "Grand Pandonian",
        "xp": 70000,
        "role_id": 1505503793691758784
    }
]

# Weekly Missions Configuration
# Some missions are automatically completed (auto_track = True),
# while others are verified manually by moderators (auto_track = False).
WEEKLY_MISSIONS = {
    "msg_general": {
        "mission_id": "GDF90",
        "name": "Send 20 messages in #general-chat",
        "xp_reward": 500,
        "auto_track": True,
        "status": "Active",
        "description": "Chat and get involved! Messages in #general-chat grant a bonus upon reaching 20 posts."
    },
    "predictions": {
        "mission_id": "KTSR9",
        "name": "Make 3 predictions in #predictions",
        "xp_reward": 1000,
        "auto_track": False,
        "status": "Active",
        "description": "Submit 3 Match predictions in the #predictions channel."
    },
    "memes": {
        "mission_id": "UEH86",
        "name": "Post a meme in #memes",
        "xp_reward": 400,
        "auto_track": False,
        "status": "Active",
        "description": "Post an original meme in the #memes channel."
    },
    "match_take": {
        "mission_id": "RTW54",
        "name": "Share a take in #match-of-the-day",
        "xp_reward": 800,
        "auto_track": False,
        "status": "Active",
        "description": "Give your analytical take in #match-of-the-day on two separate occasions."
    },
    "weekly_added": {
        "mission_id": "VAF42",
        "name": "Weekly added mission: Chat in Live Events",
        "xp_reward": 600,
        "auto_track": True,
        "status": "Active",
        "description": "Send 10 messages in #live-events during matches."
    },
    "motd_correct_score": {
        "mission_id": "QBG02",
        "name": "Match of the Day correct score",
        "xp_reward": 2500,
        "auto_track": False,
        "status": "Active",
        "description": "Predict the exact score in Match of the Day correctly."
    },
    "x_likes": {
        "mission_id": "XPS01",
        "name": "Like 5 Betpanda posts on X",
        "xp_reward": 100,
        "auto_track": False,
        "status": "Active",
    "description": "Post 5 Betpanda-related posts on X."
    },
    "x_retweets": {
        "mission_id": "XRT02",
        "name": "Retweet 5 Betpanda posts on X",
        "xp_reward": 150,
        "auto_track": False,
        "status": "Active",
        "description": "Retweet 5 official Betpanda posts on X."
    },
    "x_comments": {
        "mission_id": "XCM03",
        "name": "Comment on 5 Betpanda posts on X",
        "xp_reward": 250,
        "auto_track": False,
        "status": "Active",
        "description": "Leave a comment on 5 Betpanda posts on X."
    },
}
