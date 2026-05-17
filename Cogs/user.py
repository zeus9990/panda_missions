# Cog: User Commands and stats
import discord
from discord.ext import commands
from discord import app_commands
from database import user_details, get_user_rank_position, get_leaderboard
import config
import logging

logger = logging.getLogger(__name__)

class UserCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="profile", description="Display your current rank, XP totals, and progress.")
    async def user_profile(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            target = interaction.user
            user_db = await user_details(userid=target.id)
            if not user_db['success']:
                await interaction.followup.send(user_db['message'])
                return

            user_data = user_db['message']
            total_xp = user_data.get("total_xp", 0)
            monthly_xp = user_data.get("monthly_xp", 0)
            current_rank_role_id = user_data.get("rank")
            completed_missions = user_data.get("missions", [])
            data = await get_user_rank_position(userid=target.id)
            monthly_position = data['monthly_position']
            total_position = data['total_position']

            # Resolve rank name from role_id
            current_rank_name = "Unranked"
            for rank in config.RANK_THRESHOLDS:
                if rank["role_id"] == current_rank_role_id:
                    current_rank_name = rank["name"]
                    break

            # Determine next rank and progress
            sorted_thresholds = sorted(config.RANK_THRESHOLDS, key=lambda x: x["xp"])

            next_rank_name = "Max Rank Achieved"
            next_rank_xp = 0
            current_rank_min_xp = 0
            progress_pct = 100

            for idx, rank in enumerate(sorted_thresholds):
                if total_xp < rank["xp"]:
                    next_rank_name = rank["name"]
                    next_rank_xp = rank["xp"]
                    current_rank_min_xp = sorted_thresholds[idx - 1]["xp"] if idx > 0 else 0
                    break

            if next_rank_xp > 0:
                xp_span = next_rank_xp - current_rank_min_xp
                xp_progress = total_xp - current_rank_min_xp
                progress_pct = min(100.0, round((xp_progress / xp_span) * 100, 1)) if xp_span > 0 else 0.0

            blocks = int(progress_pct / 5)  # 5% per block, 20 total
            prog_bar = f"`[{'█' * blocks}{'░' * (20 - blocks)}]` {progress_pct}% ({xp_progress:,} / {xp_span:,} XP)"

            if next_rank_xp > 0:
                next_rank_value = f"**{next_rank_name}** ({next_rank_xp - total_xp:,} XP to go)"
            else:
                next_rank_value = "**Max Rank Achieved**"

            active_mission_ids = {m["mission_id"] for m in config.WEEKLY_MISSIONS.values() if m["status"] == "Active"}
            completed_count = sum(1 for mid in completed_missions if mid in active_mission_ids)
            total_active = len(active_mission_ids)

            embed = discord.Embed(color=discord.Color.green())
            embed.set_author(name=f"🐼 {target.display_name}'s Bamboo Stats Profile",icon_url=target.display_avatar.url if target.display_avatar else None)
            embed.add_field(name="🏆 Current Rank", value=f"**{current_rank_name}**", inline=True)
            embed.add_field(name="📅 Monthly Leaderboard Position", value=f"**#{monthly_position}**", inline=True)
            embed.add_field(name="✨ Monthly XP", value=f"`{monthly_xp:,} XP`", inline=True)
            embed.add_field(name="📅 All-time Leaderboard Position", value=f"**#{total_position}**", inline=True)
            embed.add_field(name="✨ Total XP", value=f"`{total_xp:,} XP`", inline=True)
            embed.add_field(name="🎯 Next Rank", value=next_rank_value, inline=True)
            embed.add_field(name="📈 Rank Progress", value=prog_bar, inline=False)
            embed.add_field(
                name="🏁 Weekly Missions",
                value=f"Completed **{completed_count} / {total_active}** missions this week. (Run `/missions` to view details)",
                inline=False
            )
            embed.set_footer(text="Be active in community channels and complete missions to earn more XP!")
            await interaction.followup.send(embed=embed)

        except Exception as e:
            logger.error("Profile command failed for user %s: %s", interaction.user.id, e, exc_info=True)
            await interaction.followup.send("❌ Something went wrong loading your profile.")

    @app_commands.command(name="leaderboard", description="Show the top 10 members with highest XP this month or all-time")
    @app_commands.describe(leaderboard_type="Select the leaderboard type that you want to check.")
    @app_commands.choices(leaderboard_type=[
        app_commands.Choice(name="All-time", value="total"),
        app_commands.Choice(name="Monthly", value="monthly")
    ])
    async def monthly_leaderboard(self, interaction: discord.Interaction, leaderboard_type: app_commands.Choice[str]):
        await interaction.response.defer()
        try:
            leaderboard = await get_leaderboard(userid=interaction.user.id, leaderboard_type=leaderboard_type.value)
            if not leaderboard['success']:
                await interaction.followup.send(leaderboard['message'], ephemeral=True)
                return

            user_position = leaderboard['user']['position']
            user_xp = leaderboard['user']['xp']
            desc = ""

            embed = discord.Embed(
                title=f"🏆 {leaderboard_type.name} Panda XP Leaderboard!!",
                color=discord.Color.green()
            )

            for user in leaderboard['top_10']:
                position = str(user['position']).zfill(2)
                desc += f"**• {position}** {user['username']} - `{user['xp']:,} XP`\n"

            if not desc:
                desc = "No active users logged yet! Be the first to chat and score points."

            embed.description = desc
            embed.set_footer(text=f"Your Standing: #{user_position} with {user_xp:,} {leaderboard_type.name} XP.")
            await interaction.followup.send(embed=embed)

        except Exception as e:
            logger.error("Leaderboard command failed for user %s: %s", interaction.user.id, e, exc_info=True)
            await interaction.followup.send("❌ Something went wrong loading the leaderboard.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(UserCog(bot))