# Cog: XP Earning and Role-Management Rules
import random
import discord
from discord.ext import commands
from cachetools import TTLCache
from database import update_streak, get_daily_xp_progress, add_daily_xp
from config import COOLDOWN_SECONDS, XP_LENGTH_RULES, XP_CHANNELS, GENERAL_CHAT_ID, WEEKLY_MISSIONS
from services.xp import award_mission, grant_xp

# ── New rule constants ────────────────────────────────────────────────────────
MIN_MESSAGE_LENGTH   = 15       # messages shorter than this earn 0 XP
DAILY_XP_CAP         = 50       # max XP a user can earn per day from messages
LONG_MESSAGE_BONUS   = 1        # +XP when message >= LONG_MESSAGE_THRESHOLD chars
LONG_MESSAGE_THRESHOLD = 100
NEWCOMER_REPLY_BONUS = 2        # +XP for replying to user <7 days old
NEWCOMER_DAYS        = 7        # account age threshold in days
DAILY_LOGIN_BONUS    = 3        # +XP for first valid message of the calendar day
VARIETY_BONUS        = 1        # +XP for being active in 3+ channels today
VARIETY_CHANNEL_THRESHOLD = 3
# ─────────────────────────────────────────────────────────────────────────────


class XPCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.cooldown_cache = TTLCache(maxsize=10_000, ttl=COOLDOWN_SECONDS)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def calculate_message_xp(self, message_content: str) -> int:
        """Calculate dynamic XP reward based on message character length."""
        content_length = len(message_content)
        for rule in XP_LENGTH_RULES:
            if content_length <= rule["max_len"]:
                return random.randint(rule["min_xp"], rule["max_xp"])
        return random.randint(1, 2)

    def calculate_bonus_xp(self, message: discord.Message, is_first_message_today: bool, channels_today: list) -> int:
        """
        Calculate bonus XP from the new quality rules.
        Evaluated after base XP so bonuses can be capped together.
        """
        bonus = 0

        # ── Long message bonus ────────────────────────────────────────────────
        if len(message.content) >= LONG_MESSAGE_THRESHOLD:
            bonus += LONG_MESSAGE_BONUS

        # ── Reply bonuses ─────────────────────────────────────────────────────
        if message.reference and message.reference.resolved:
            resolved = message.reference.resolved
            if isinstance(resolved, discord.Message) and resolved.author:
                account_age_days = (
                    discord.utils.utcnow() - resolved.author.created_at
                ).days
                if account_age_days < NEWCOMER_DAYS:
                    bonus += NEWCOMER_REPLY_BONUS

        # ── Daily first-message bonus ─────────────────────────────────────────
        if is_first_message_today:
            bonus += DAILY_LOGIN_BONUS

        # ── Multi-channel variety bonus ───────────────────────────────────────
        if len(channels_today) >= VARIETY_CHANNEL_THRESHOLD:
            bonus += VARIETY_BONUS

        return bonus

    async def handle_streak_mission(self, message: discord.Message) -> None:
        """Advance the daily streak; from a streak of 5 each new day counts toward the mission.

        Unchanged behaviour: update_streak stores the streak and complete_mission adds
        its own +1 on top, so the 7-count streak mission completes on day 6.
        """
        user_id = message.author.id
        streak_result = await update_streak(userid=user_id)
        if not streak_result["success"]:
            return
        if streak_result["streak"] < 5:
            return
        await award_mission(message.guild, user_id, message.author.name, "daily_streak")

    async def handle_msg_general_mission(self, message: discord.Message, weekly_message_count: int) -> None:
        """Complete the weekly general-chat message mission once the count is reached."""
        if weekly_message_count < WEEKLY_MISSIONS["msg_general"]["count"]:
            return
        await award_mission(message.guild, message.author.id, message.author.name, "msg_general")

    # ── Main listener ─────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Discord/Telegram message statistics and tweet forwarding live in Cogs/stats.py.
        if not message.guild or message.author.bot:
            return

        # Only award XP in designated channels
        if message.channel.id not in XP_CHANNELS:
            return

        # Minimum length check (before cooldown so cooldown isn't wasted)
        if len(message.content) < MIN_MESSAGE_LENGTH:
            return

        # Cooldown check
        user_id = message.author.id
        now = discord.utils.utcnow()
        last_xp_time = self.cooldown_cache.get(user_id)
        time_delta = (now - last_xp_time).total_seconds() if last_xp_time else float("inf")
        if time_delta < COOLDOWN_SECONDS:
            return

        # Fetch (and auto-reset on a new day) this user's daily XP-cap state,
        # registering the current channel as visited today.
        daily_progress = await get_daily_xp_progress(user_id, message.channel.id)

        # Update cooldown and calculate base + bonus XP
        self.cooldown_cache[user_id] = now
        xp_to_award = self.calculate_message_xp(message.content)
        xp_to_award += self.calculate_bonus_xp(
            message=message,
            is_first_message_today=daily_progress["is_first_message_today"],
            channels_today=daily_progress["channels"],
        )

        # The daily cap applies ONLY to per-message XP. It does NOT block
        # missions, streaks, or msg_general counting below.
        remaining_daily_xp = max(0, DAILY_XP_CAP - daily_progress["xp_earned"])
        xp_to_award = min(xp_to_award, remaining_daily_xp)
        await add_daily_xp(user_id, xp_to_award)

        is_general = message.channel.id == GENERAL_CHAT_ID

        # Streak mission (general chat only) - always runs, uncapped
        if is_general:
            await self.handle_streak_mission(message)

        # Award message XP (0 is fine: msg_count still counts toward the weekly mission).
        # grant_xp runs the central rank check.
        result = await grant_xp(
            message.guild, user_id, message.author.name, xp_to_award,
            msg_count=1 if is_general else 0)

        if is_general:
            await self.handle_msg_general_mission(message, result["xp"]["msg_general"])


async def setup(bot):
    await bot.add_cog(XPCog(bot))