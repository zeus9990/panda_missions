# Cog: USER commands (everyone can run these): /profile /missions /leaderboard
import asyncio

import discord
from discord import app_commands
from discord.ext import commands

from database import get_bet_status, get_leaderboard, get_pause_state, get_user_rank_position, user_details
from utils.embeds import build_missions_embed, build_profile_embed


class UserCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="profile", description="Display your current rank, XP totals, and progress.")
    async def profile(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        user_db = await user_details(interaction.user.id)
        if not user_db["success"]:
            await interaction.followup.send(user_db["message"], ephemeral=True)
            return
        positions, pause_state, bet_status = await asyncio.gather(
            get_user_rank_position(interaction.user.id), get_pause_state(),
            get_bet_status(interaction.user.id))
        embed = build_profile_embed(
            interaction.user, user_db["message"], positions, pause_state, bet_status)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="missions", description="View your weekly mission progress and rewards.")
    async def missions(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        user_db = await user_details(interaction.user.id)
        if not user_db["success"]:
            await interaction.followup.send(user_db["message"], ephemeral=True)
            return
        embed = build_missions_embed(user_db["message"], interaction.user, await get_pause_state())
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="leaderboard", description="Show the top 10 members with highest XP this month or all-time")
    @app_commands.describe(leaderboard_type="Select the leaderboard type that you want to check.")
    @app_commands.choices(leaderboard_type=[
        app_commands.Choice(name="All-time", value="total"),
        app_commands.Choice(name="Monthly", value="monthly"),
    ])
    async def leaderboard(self, interaction: discord.Interaction,
                          leaderboard_type: app_commands.Choice[str]):
        await interaction.response.defer()
        board = await get_leaderboard(interaction.user.id, leaderboard_type.value)
        if not board["success"]:
            await interaction.followup.send(board["message"], ephemeral=True)
            return

        lines = [f"**● {str(u['position']).zfill(2)}** {u['username']} - `{u['xp']:,} XP`"
                 for u in board["top_10"]]
        embed = discord.Embed(
            title=f"🏆 {leaderboard_type.name} Panda XP Leaderboard!!",
            description="\n".join(lines) or "No active users logged yet! Be the first to chat and score points.",
            color=discord.Color.green(),
        )
        me = board["user"]
        if me:
            embed.set_footer(text=f"Your Standing: #{me['position']} with {me['xp']:,} {leaderboard_type.name} XP.")
        await interaction.followup.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(UserCog(bot))
