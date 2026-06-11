# Cog: Poll Vote Mission
import discord
from discord.ext import commands
from database import complete_mission
from config import MISSION_CHANNEL_ID, LOG_CHANNEL_ID, WEEKLY_MISSIONS, POLL_CHANNEL
from rank_update import rank_update_embed


class PollMissionCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def send_mission_embeds(self, user: discord.User, mission_data: dict) -> None:
        """Send mission completion embed to mission channel and log channel."""

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

    @commands.Cog.listener()
    async def on_raw_poll_vote_add(self, payload: discord.RawPollVoteActionEvent):
        if payload.channel_id != POLL_CHANNEL:
            return

        if payload.user_id == self.bot.user.id:
            return

        # Fetch guild and member
        guild = self.bot.get_guild(payload.guild_id)
        if guild is None:
            return

        member = guild.get_member(payload.user_id)
        if member is None:
            member = await guild.fetch_member(payload.user_id)

        mission_data = WEEKLY_MISSIONS["poll_vote"]

        mission_result = await complete_mission(
            userid=payload.user_id,
            username=member.name,
            mission_key="poll_vote"
        )

        if not mission_result["success"]:
            return

        await self.send_mission_embeds(member, mission_data)
        await rank_update_embed(interaction=member, userid=payload.user_id, total_xp=mission_result["total_xp"])

async def setup(bot):
    await bot.add_cog(PollMissionCog(bot))