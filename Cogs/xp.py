# Cog: XP Earning and Role-Management Rules
import random
import discord
from discord.ext import commands
from cachetools import TTLCache
from tg_auto import send_telegram_message
from database import xp_update, complete_mission, update_streak
from config import COOLDOWN_SECONDS, XP_LENGTH_RULES, TWEET_CHANNEL_ID, XP_CHANNELS, GENERAL_CHAT_ID, MISSION_CHANNEL_ID, LOG_CHANNEL_ID, WEEKLY_MISSIONS
from rank_update import rank_update_embed
from typing import Optional
from collections import defaultdict
from datetime import datetime, timezone

# ── New rule constants ────────────────────────────────────────────────────────
MIN_MESSAGE_LENGTH   = 10       # messages shorter than this earn 0 XP
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
        self._last_xp_date: dict[int, str] = {}  # user_id -> "YYYY-MM-DD"
        self._daily_channels: dict[int, set] = defaultdict(set)  # user_id -> {channel_id, ...}
        self._daily_xp: dict[int, int] = defaultdict(int)  # user_id -> xp earned today

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _today_utc(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def _reset_daily_state_if_needed(self, user_id: int) -> bool:
        """Returns True if this is the user's first XP event today (new day detected)."""
        today = self._today_utc()
        if self._last_xp_date.get(user_id) != today:
            # New day — wipe daily tracking for this user
            self._daily_channels[user_id] = set()
            self._daily_xp[user_id] = 0
            self._last_xp_date[user_id] = today
            return True
        return False

    def _remaining_daily_xp(self, user_id: int) -> int:
        """How much more XP this user can earn today before hitting the cap."""
        return max(0, DAILY_XP_CAP - self._daily_xp[user_id])

    def calculate_message_xp(self, message_content: str) -> int:
        """Calculate dynamic XP reward based on message character length."""
        content_length = len(message_content)
        for rule in XP_LENGTH_RULES:
            if content_length <= rule["max_len"]:
                return random.randint(rule["min_xp"], rule["max_xp"])
        return random.randint(1, 6)

    def calculate_bonus_xp(
        self,
        message: discord.Message,
        is_first_message_today: bool,
        user_id: int,
    ) -> int:
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
            # Make sure the referenced object is an actual message with an author
            if isinstance(resolved, discord.Message) and resolved.author:
                # Bonus for helping newcomers (account < NEWCOMER_DAYS days old)
                account_age_days = (
                    discord.utils.utcnow() - resolved.author.created_at
                ).days
                if account_age_days < NEWCOMER_DAYS:
                    bonus += NEWCOMER_REPLY_BONUS

        # ── Daily first-message bonus ─────────────────────────────────────────
        if is_first_message_today:
            bonus += DAILY_LOGIN_BONUS

        # ── Multi-channel variety bonus ───────────────────────────────────────
        channels_today = self._daily_channels[user_id]
        if len(channels_today) >= VARIETY_CHANNEL_THRESHOLD:
            bonus += VARIETY_BONUS

        return bonus

    # ── Embed helpers ─────────────────────────────────────────────

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
        # Forward bot messages in tweet channel to Telegram
        if message.author.bot:
            if message.channel.id == TWEET_CHANNEL_ID:
                await send_telegram_message(message=message.content)
            return

        # Only award XP in designated channels
        if message.channel.id not in XP_CHANNELS:
            return

        # Minimum length check 
        if len(message.content) < MIN_MESSAGE_LENGTH:
            return

        # Cooldown check
        user_id = message.author.id
        now = discord.utils.utcnow()
        last_xp_time = self.cooldown_cache.get(user_id)
        time_delta = (now - last_xp_time).total_seconds() if last_xp_time else float("inf")

        if time_delta < COOLDOWN_SECONDS:
            return

        # Detect new day and reset daily counters for this user
        is_first_message_today = self._reset_daily_state_if_needed(user_id)

        # Daily XP cap pre-check
        if self._remaining_daily_xp(user_id) <= 0:
            return

        # Update cooldown and calculate base XP
        self.cooldown_cache[user_id] = now
        xp_to_award = self.calculate_message_xp(message.content)

        # Add bonus XP from quality rules
        # Register the channel before checking variety bonus
        self._daily_channels[user_id].add(message.channel.id)
        bonus_xp = self.calculate_bonus_xp(
            message=message,
            is_first_message_today=is_first_message_today,
            user_id=user_id,
        )
        xp_to_award += bonus_xp

        # Clamp to remaining daily cap
        xp_to_award = min(xp_to_award, self._remaining_daily_xp(user_id))
        self._daily_xp[user_id] += xp_to_award

        is_general = message.channel.id == GENERAL_CHAT_ID

        # Handle streak mission (general chat only)
        if is_general:
            await self.handle_streak_mission(message)

        # Award XP
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