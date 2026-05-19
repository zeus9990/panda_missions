# Cog: Weekly Missions and Tracking Status
import discord
from discord import app_commands
from discord.ext import commands
from config import WEEKLY_MISSIONS
from database import user_details

class MissionsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="missions", description="View your weekly mission progress and rewards.")
    async def view_missions(self, interaction: discord.Interaction):
        """Displays user's current progress for all active weekly missions."""
        await interaction.response.defer(ephemeral=True)
        user_data = await user_details(userid=interaction.user.id)
        if user_data['success']:
            completed_mission_ids = user_data['message']['missions']
            total_missions = len(WEEKLY_MISSIONS)
            completed_count = sum(
                1 for details in WEEKLY_MISSIONS.values()
                if details['mission_id'] in completed_mission_ids
            )
        
            # Progress bar
            filled = int((completed_count / total_missions) * 20) if total_missions > 0 else 0
            overall_bar = f"`[{'█' * filled}{'░' * (20 - filled)}]` {completed_count}/{total_missions}"
        
            embed = discord.Embed(
                description=(
                    "**Complete these tasks each week to earn massive XP rewards!**\n"
                    "**Some missions track automatically, others are verified manually by moderators.**\n\n"
                    f"● **Overall Progress:** {overall_bar}"
                ),
                color=discord.Color.green()
            )
        
            avatar_url = interaction.user.display_avatar.url if interaction.user.display_avatar else None
            embed.set_author(name="🐼 Weekly Panda Mission Board", icon_url=avatar_url)
        
            for key, details in WEEKLY_MISSIONS.items():
                mission_id = details['mission_id']
                is_completed = mission_id in completed_mission_ids
                status_emoji = "✅" if is_completed else "⏳"
                status_text = "Completed" if is_completed else "In Progress"
                status_color = "🟢" if is_completed else "🟠"
                tracking_info = "🤖 Auto-tracked" if details['auto_track'] else "🛡️ Moderator Verified"
                value = (
                    f"● **XP Award:** `{details['xp_reward']:,} XP`\n"
                    f"● **Status:** {status_emoji} {status_text}\n"
                    f"● **Type:** {tracking_info}\n"
                )

                # Add progress only if count exists
                if details.get("count") is not None:
                    progress = f"{details['count'] if is_completed else user_data['message'][key]} /{details['count']}"
                    value += f"● **Progress:** `{progress}`\n"

                value += f"\n*{details['description']}*"
                embed.add_field(
                    name=f"{status_color} {details['name']}",
                    value=value,
                    inline=False
                )
        
            embed.set_footer(text=f"Weekly missions reset, but total XP stacks forever! ● Total XP: {user_data['message']['total_xp']:,}")
            await interaction.followup.send(embed=embed)
        else:
            await interaction.followup.send("> ❌ Something went wrong loading your mission stats.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(MissionsCog(bot))
