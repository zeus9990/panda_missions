# Cog: Weekly Mission resets and Monthly Leaderboard reset
from datetime import datetime, timezone, time
import discord
from discord.ext import commands, tasks
from database import monthly_reset, weekly_reset
from config import MISSION_CHANNEL_ID, LOG_CHANNEL_ID

MIDNIGHT_UTC = time(0, 0, tzinfo=timezone.utc)

class ResetCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.reset_check.start()

    def cog_unload(self):
        self.reset_check.cancel()

    @tasks.loop(time=MIDNIGHT_UTC)
    async def reset_check(self):
        """Background task running daily at midnight UTC. Weekly reset of missions on Monday."""
        today = datetime.now(timezone.utc)

        if today.weekday() == 0:
            print("Triggering automated Weekly Mission Reset.")
            result = await weekly_reset()

            mission_channel = self.bot.get_channel(MISSION_CHANNEL_ID)
            if mission_channel:
                embed = discord.Embed(
                    title="📆 New Week Reset Complete!",
                    description="The weekly missions and message counts have been reset!\n"
                                "New missions are now available. Good luck this week!",
                    color=discord.Color.blurple(),
                    timestamp=discord.utils.utcnow()
                )
                await mission_channel.send(embed=embed)

            log_channel = self.bot.get_channel(LOG_CHANNEL_ID)
            if log_channel:
                embed = discord.Embed(
                    title="📆 Weekly Reset — Snapshot",
                    description="📊 Weekly reset complete! Here's the snapshot before the wipe:",
                    color=discord.Color.blue(),
                    timestamp=discord.utils.utcnow()
                )
                embed.add_field(name="● Users Modified", value=str(result["modified_users"]), inline=True)
                embed.add_field(name="● Reset Type", value="Weekly", inline=True)
                embed.add_field(name="● Snapshot File", value=f"`{result['filename']}`", inline=False)
                embed.set_footer(text="Data captured before reset")
                with result["file"] as fp:
                    await log_channel.send(embed=embed)
                    await log_channel.send(file=discord.File(fp=fp, filename=result["filename"]))

    @reset_check.before_loop
    async def before_reset_check(self):
        await self.bot.wait_until_ready()

    @discord.app_commands.command(name="monthly_reset", description="Manually trigger the monthly XP leaderboard reset.")
    @discord.app_commands.checks.has_permissions(administrator=True)
    async def monthly_reset_command(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        result = await monthly_reset()

        mission_channel = self.bot.get_channel(MISSION_CHANNEL_ID)
        if mission_channel:
            embed = discord.Embed(
                title="📅 New Month Reset Complete!",
                description="● The monthly XP leaderboard has been officially archived and reset for the new month!\n"
                            "● Total cumulative XP and server ranks remain fully untouched. Let the new race begin!",
                color=discord.Color.orange(),
                timestamp=discord.utils.utcnow()
            )
            embed.set_footer(text="betpanda.io")
            await mission_channel.send(embed=embed)

        log_channel = self.bot.get_channel(LOG_CHANNEL_ID)
        if log_channel:
            embed = discord.Embed(
                title="📅 Monthly Reset — Snapshot",
                description="📊 Monthly reset complete! Here's the snapshot before the wipe:",
                color=discord.Color.blue(),
                timestamp=discord.utils.utcnow()
            )
            embed.add_field(name="● Users Modified", value=str(result["modified_users"]), inline=True)
            embed.add_field(name="● Reset Type", value="Monthly", inline=True)
            embed.add_field(name="● Snapshot File", value=f"`{result['filename']}`", inline=False)
            embed.set_footer(text="Data captured before reset")
            with result["file"] as fp:
                await log_channel.send(embed=embed)
                await log_channel.send(file=discord.File(fp=fp, filename=result["filename"]))

        await interaction.followup.send("> ✅ Monthly reset completed successfully.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(ResetCog(bot))