# Cog: XP Earning and Role-Management Rules
import re
import random
import discord
from discord.ext import commands
from cachetools import TTLCache
from tg_auto import send_telegram_message
from database import xp_update, complete_mission
from config import COOLDOWN_SECONDS, XP_LENGTH_RULES, TWEET_CHANNEL_ID, XP_CHANNELS, GENERAL_CHAT_ID, MISSION_CHANNEL_ID, LOG_CHANNEL_ID, WEEKLY_MISSIONS
from rank_update import rank_update_embed


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
        # Default fallback
        return random.randint(5, 15)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            if message.channel.id == TWEET_CHANNEL_ID:
                await send_telegram_message(message=message.content)
            return

        # Check if the message is in an XP-awarding channel
        if message.channel.id not in XP_CHANNELS:
            return

        user_id = message.author.id
        time = discord.utils.utcnow()
        last_xp_time = self.cooldown_cache.get(user_id)
        time_delta = (time - last_xp_time).total_seconds() if last_xp_time else float('inf')
        
        if time_delta < COOLDOWN_SECONDS:
            # Cooldown is active. We silent-ignore XP award to prevent farming.
            # But we still let normal discord messages pass without spamming notifications.
            return

        # Cooldown passed! Calculate dynamic length-based XP
        xp_to_award = self.calculate_message_xp(message.content)
        self.cooldown_cache[user_id] = time

        # Award XP in DB
        msg_count = 1 if message.channel.id == GENERAL_CHAT_ID else 0
        result = await xp_update(userid=user_id, username=message.author.name, xp_amount=xp_to_award, msg_count=msg_count)
        if result['success']:
            weekly_message_count = result['xp']['msg_general']
            mission_data = WEEKLY_MISSIONS['msg_general']
            if weekly_message_count >= mission_data['count']:
                mission_status = await complete_mission(userid=user_id, username=message.author.name, mission_key='msg_general')
                if mission_status['success']:
                    embed = discord.Embed(
                        title="🎉 Weekly Mission Completed!",
                        description=f"**Congratulations {message.author.mention}!**\n"
                                    f"● **You completed:** {mission_data['name']}\n"
                                    f"● **Mission Description:** {mission_data['description']}\n"
                                    f"● **Rewarded:** `+{mission_data['xp_reward']} XP`",
                        color=discord.Color.green()
                    )
                    embed.timestamp = discord.utils.utcnow()
                    embed.set_footer(text="betpanda.io")
                    channel = self.bot.get_channel(MISSION_CHANNEL_ID)
                    if channel:
                        await channel.send(embed=embed)
    
                    # Log in staff channel
                    staff_channel = self.bot.get_channel(LOG_CHANNEL_ID)
                    if staff_channel:
                        embed = discord.Embed(
                            title="📈 Mission Complete!",
                            description=f"**✧ User:** {message.author.mention}\n"
                                        f"**✧ User ID:** {user_id}\n"
                                        f"**✧ Mission Title:** {mission_data['name']}\n"
                                        f"**✧ Mission ID:** `{mission_data['mission_id']}`\n"
                                        f"**✧ Mission Reward:** `+{mission_data['xp_reward']} XP`\n"
                                        f"**✧ Reward Assigner:** Auto assigned.",
                            color=discord.Color.blue()                                      
                        )
                        embed.timestamp = discord.utils.utcnow()
                        embed.set_footer(text="betpanda.io")
                        await staff_channel.send(embed=embed)
                        
                    total_xp = mission_status['total_xp']
                    await rank_update_embed(interaction=message, userid=user_id, total_xp=total_xp)
            total_xp = result['xp']['total_xp']
            await rank_update_embed(interaction=message, userid=user_id, total_xp=total_xp)

async def setup(bot):
    await bot.add_cog(XPCog(bot))
