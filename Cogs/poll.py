# Cog: Poll Vote Mission
import discord
from discord.ext import commands

from config import POLL_CHANNEL
from services.xp import award_mission


class PollMissionCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_raw_poll_vote_add(self, payload: discord.RawPollVoteActionEvent):
        if payload.channel_id != POLL_CHANNEL or payload.user_id == self.bot.user.id:
            return

        guild = self.bot.get_guild(payload.guild_id) if payload.guild_id else None
        if guild is None:
            return

        member = guild.get_member(payload.user_id)
        if member is None:
            try:
                member = await guild.fetch_member(payload.user_id)
            except discord.NotFound:
                return
        if member.bot:
            return

        await award_mission(guild, member.id, member.name, "poll_vote")


async def setup(bot: commands.Bot):
    await bot.add_cog(PollMissionCog(bot))
