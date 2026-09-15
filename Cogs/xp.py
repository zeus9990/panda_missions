# Cog: XP Earning and Role-Management Rules
import random
import discord
from discord.ext import commands
from cachetools import TTLCache
from tg_auto import send_telegram_message
from database import (
    xp_update,
    complete_mission,
    update_streak,
    record_stat_event,
    get_daily_xp_progress,
    add_daily_xp,
)
from config import COOLDOWN_SECONDS, XP_LENGTH_RULES, TWEET_CHANNEL_ID, XP_CHANNELS, GENERAL_CHAT_ID, MISSION_CHANNEL_ID, LOG_CHANNEL_ID, WEEKLY_MISSIONS
from rank_update import rank_update_embed
from typing import Optional

# ── New rule constants ────────────────────────────────────────────────────────
MIN_MESSAGE_LENGTH   = 15       # messages shorter than this earn 0 XP
DAILY_XP_CAP         = 150      # max XP a user can earn per day from messages
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
        return random.randint(1, 3)

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

    async def send_mission_embeds(self, message: discord.Message, mission_data: dict) -> None:
        """Send mission completion embed to mission channel and log channel."""
        user = message.author

        # Public mission channel
        channel = self.bot.get_channel(MISSION_CHANNEL_ID)
        if channel:
            embed = discord.Embed(
                title="🎉 Weekly Mission Completed!",
                description=(
                    f"**Congratulations {user.mention}!**\n"
                    f"● **You completed:** {mission_data['name']}\n"
                    f"● **Mission Description:** {mission_data['description']}\n"
                    f"● **Rewarded:** `+{mission_data['xp_reward']} XP`"
                ),
                color=discord.Color.green(),
                timestamp=discord.utils.utcnow()
            )
            embed.set_footer(text="betpanda.io")
            await channel.send(embed=embed)

        # Staff log channel
        staff_channel = self.bot.get_channel(LOG_CHANNEL_ID)
        if staff_channel:
            embed = discord.Embed(
                title="📈 Mission Complete!",
                description=(
                    f"**✧ User:** {user.mention}\n"
                    f"**✧ User ID:** {user.id}\n"
                    f"**✧ Mission Title:** {mission_data['name']}\n"
                    f"**✧ Mission ID:** `{mission_data['mission_id']}`\n"
                    f"**✧ Mission Reward:** `+{mission_data['xp_reward']} XP`\n"
                    f"**✧ Reward Assigner:** Auto assigned."
                ),
                color=discord.Color.blue(),
                timestamp=discord.utils.utcnow()
            )
            embed.set_footer(text="betpanda.io")
            await staff_channel.send(embed=embed)

    async def handle_streak_mission(self, message: discord.Message) -> None:
        """Check and handle daily streak mission for general chat messages."""
        user_id = message.author.id

        streak_result = await update_streak(userid=user_id)
        if not streak_result["success"]:
            return

        if streak_result["streak"] < 5:
            return

        mission_result = await complete_mission(
            userid=user_id,
            username=message.author.name,
            mission_key="daily_streak"
        )
        if not mission_result["success"]:
            return

        await self.send_mission_embeds(message, mission_result["mission"])
        await rank_update_embed(interaction=message, userid=user_id, total_xp=mission_result["total_xp"])

    async def handle_msg_general_mission(self, message: discord.Message, weekly_message_count: int) -> Optional[int]:
        """Check and handle the weekly message count mission. Returns total_xp if mission completed."""
        user_id = message.author.id
        mission_data = WEEKLY_MISSIONS["msg_general"]

        if weekly_message_count < mission_data["count"]:
            return None

        mission_result = await complete_mission(
            userid=user_id,
            username=message.author.name,
            mission_key="msg_general"
        )
        if not mission_result["success"]:
            return None

        await self.send_mission_embeds(message, mission_data)
        return mission_result["total_xp"]

    # ── Main listener ─────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        await record_stat_event("discord", "message", message.author.id, total_members=message.guild.member_count)

        # Forward bot messages in tweet channel to Telegram
        if message.author.bot:
            if message.channel.id == TWEET_CHANNEL_ID:
                await send_telegram_message(message=message.content)
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

        # Fetch (and auto-reset if it's a new day) this user's daily XP-cap
        # state from MongoDB, registering the current channel as visited today.
        daily_progress = await get_daily_xp_progress(user_id, message.channel.id)
        is_first_message_today = daily_progress["is_first_message_today"]
        channels_today = daily_progress["channels"]
        xp_earned_today = daily_progress["xp_earned"]

        # Update cooldown and calculate base XP
        self.cooldown_cache[user_id] = now
        xp_to_award = self.calculate_message_xp(message.content)

        # Add bonus XP from quality rules
        bonus_xp = self.calculate_bonus_xp(
            message=message,
            is_first_message_today=is_first_message_today,
            channels_today=channels_today,
        )
        xp_to_award += bonus_xp

        # Clamp to remaining daily cap
        # IMPORTANT: this cap applies ONLY to per-message XP. It does NOT block
        # missions, streaks, or msg_general counting below — those always run,
        # even if the user has hit their daily message-XP cap.
        remaining_daily_xp = max(0, DAILY_XP_CAP - xp_earned_today)
        xp_to_award = min(xp_to_award, remaining_daily_xp)

        # Persist the updated daily-cap total (0 is still written so the
        # record stays "touched" for today, matching prior in-memory behavior).
        await add_daily_xp(user_id, xp_to_award)

        is_general = message.channel.id == GENERAL_CHAT_ID

        # Handle streak mission (general chat only) — always runs, uncapped
        if is_general:
            await self.handle_streak_mission(message)

        # Award XP (xp_to_award may be 0 here if the cap was hit — that's fine,
        # msg_count still increments so weekly/mission counters stay accurate)
        msg_count = 1 if is_general else 0
        xp_result = await xp_update(
            userid=user_id,
            username=message.author.name,
            xp_amount=xp_to_award,
            msg_count=msg_count
        )

        if not xp_result["success"]:
            return

        total_xp = xp_result["xp"]["total_xp"]

        # Handle message count mission (general chat only)
        if is_general:
            weekly_message_count = xp_result["xp"]["msg_general"]
            mission_total_xp = await self.handle_msg_general_mission(message, weekly_message_count)
            if mission_total_xp is not None:
                total_xp = mission_total_xp

        await rank_update_embed(interaction=message, userid=user_id, total_xp=total_xp)


async def setup(bot):
    await bot.add_cog(XPCog(bot))