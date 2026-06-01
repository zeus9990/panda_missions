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

class XPCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.cooldown_cache = TTLCache(maxsize=10_000, ttl=COOLDOWN_SECONDS)

    def calculate_message_xp(self, message_content: str) -> int:
        """Calculate dynamic XP reward based on message character length."""
        content_length = len(message_content)
        for rule in XP_LENGTH_RULES:
            if content_length <= rule["max_len"]:
                return random.randint(rule["min_xp"], rule["max_xp"])
        return random.randint(2, 8)

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

        # Cooldown check
        user_id = message.author.id
        now = discord.utils.utcnow()
        last_xp_time = self.cooldown_cache.get(user_id)
        time_delta = (now - last_xp_time).total_seconds() if last_xp_time else float("inf")

        if time_delta < COOLDOWN_SECONDS:
            return

        # Update cooldown and calculate XP
        self.cooldown_cache[user_id] = now
        xp_to_award = self.calculate_message_xp(message.content)
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