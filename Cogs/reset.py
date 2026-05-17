# Cog: Weekly Mission resets and Monthly Leaderboard reset
from datetime import datetime, timezone, time
import discord
from discord.ext import commands, tasks
from database import monthly_reset, weekly_reset
import config
import logging

logger = logging.getLogger(__name__)

MIDNIGHT_UTC = time(0, 0, tzinfo=timezone.utc)

class ResetCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.reset_check.start()

    def cog_unload(self):
        self.reset_check.cancel()

    @tasks.loop(time=MIDNIGHT_UTC)
    async def reset_check(self):
        """Background task running daily. Resets the monthly XP values on the 1st of the month. And Weekly reset of missions"""
        try:
            today = datetime.now(timezone.utc)
            if today.day == 1:
                print("Detected 1st of the month! Triggering automated Monthly XP Reset.")
                result = await monthly_reset()

                mission_channel = self.bot.get_channel(config.MISSION_CHANNEL_ID)
                if mission_channel:
                    embed = discord.Embed(
                        title="📅 New Month Reset Complete!",
                        description="The monthly XP leaderboard has been officially archived and reset for the new month!\n"
                                    "Total cumulative XP and server ranks remain fully untouched. Let the new race begin!",
                        color=discord.Color.orange(),
                        timestamp=discord.utils.utcnow()
                    )
                    await mission_channel.send(embed=embed)

                log_channel = self.bot.get_channel(config.LOG_CHANNEL_ID)
                if log_channel:
                    embed = discord.Embed(
                        title="📅 Monthly Reset — Snapshot",
                        description="📊 Monthly reset complete! Here's the snapshot before the wipe:",
                        color=discord.Color.gold(),
                        timestamp=discord.utils.utcnow()
                    )
                    embed.add_field(name="Users Modified", value=str(result["modified_users"]), inline=True)
                    embed.add_field(name="Reset Type", value="Monthly", inline=True)
                    embed.add_field(name="Snapshot File", value=f"`{result['filename']}`", inline=False)
                    embed.set_footer(text="Data captured before reset")
                    with result["file"] as fp:
                        await log_channel.send(embed=embed)
                        await log_channel.send(file=discord.File(fp=fp, filename=result["filename"]))

            if today.weekday() == 6: #Sunday
                print("Triggering automated Weekly Mission Reset.")
                result = await weekly_reset()

                mission_channel = self.bot.get_channel(config.MISSION_CHANNEL_ID)
                if mission_channel:
                    embed = discord.Embed(
                        title="📆 New Week Reset Complete!",
                        description="The weekly missions and message counts have been reset!\n"
                                    "New missions are now available. Good luck this week!",
                        color=discord.Color.blurple(),
                        timestamp=discord.utils.utcnow()
                    )
                    await mission_channel.send(embed=embed)

                log_channel = self.bot.get_channel(config.LOG_CHANNEL_ID)
                if log_channel:
                    embed = discord.Embed(
                        title="📆 Weekly Reset — Snapshot",
                        description="📊 Weekly reset complete! Here's the snapshot before the wipe:",
                        color=discord.Color.blurple(),
                        timestamp=discord.utils.utcnow()
                    )
                    embed.add_field(name="Users Modified", value=str(result["modified_users"]), inline=True)
                    embed.add_field(name="Reset Type", value="Weekly", inline=True)
                    embed.add_field(name="Snapshot File", value=f"`{result['filename']}`", inline=False)
                    embed.set_footer(text="Data captured before reset")
                    with result["file"] as fp:
                        await log_channel.send(embed=embed)
                        await log_channel.send(file=discord.File(fp=fp, filename=result["filename"]))

        except Exception as e:
            logger.error(f"Reset cog crash: {e}", exc_info=True)

    @reset_check.before_loop
    async def before_reset_check(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(ResetCog(bot))