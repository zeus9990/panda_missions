# Cog: Moderator/Admin Commands and Staff Audits
import discord
from discord import app_commands
from discord.ext import commands
from database import xp_update, update_user_rank, complete_mission, user_details, get_user_rank_position
import config

class AdminCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def is_moderator(self, interaction: discord.Interaction) -> bool:
        """Helper to verify if the user has the designated admin/mod role."""
        if not interaction.guild:
            return False
        return (
            interaction.user.id == interaction.guild.owner_id or
            any(role.id in config.ADMIN_ROLE_IDS for role in interaction.user.roles)
        )

    @app_commands.command(name="award", description="Award bonus XP to a user (Moderators only).")
    @app_commands.describe(member="The member to award XP to", amount="Amount of XP to award", reason="Reason for the award")
    async def award_xp(self, interaction: discord.Interaction, member: discord.Member, amount: int, reason: str = "Good behaviour & community vibes"):
        if not self.is_moderator(interaction):
            await interaction.response.send_message(
                "> ❌ **Access Denied**: Only server staff with the administrator role can use this command.",
                ephemeral=True
            )
            return

        if amount <= 0:
            await interaction.response.send_message("> ❌ **Invalid Amount**: You must award more than 0 XP.", ephemeral=True)
            return

        await interaction.response.defer()
        xp_change = await xp_update(userid=member.id, username=member.name, xp_amount=amount)
        if xp_change['success']:
            embed = discord.Embed(
                title="🎁 XP Awarded!",
                description=(
                    f"● **{xp_change['message']}**\n"
                    f"● **Reason:** {reason}\n"
                    f"● **Total XP:** `{xp_change['xp']['total_xp']:,} XP`\n"
                    f"● **Monthly XP:** `{xp_change['xp']['monthly_xp']:,} XP`"
                ),
                color=discord.Color.green()
            )
            embed.timestamp = discord.utils.utcnow()
            embed.set_footer(text="betpanda.io")
            await interaction.followup.send(embed=embed)

            # Log in staff channel
            log_channel = self.bot.get_channel(config.LOG_CHANNEL_ID)
            if log_channel:
                staff_embed = discord.Embed(
                    title="🛡️ Moderator Audit: XP Awarded",
                    description=(
                        f"**✧ Moderator:** {interaction.user.mention} (`{interaction.user.id}`)\n"
                        f"**✧ Recipient:** {member.mention} (`{member.id}`)\n"
                        f"**✧ Amount:** `+{amount:,} XP`\n"
                        f"**✧ Reason:** {reason}\n"
                        f"**✧ New Total XP:** `{xp_change['xp']['total_xp']:,} XP`\n"
                        f"**✧ New Monthly XP:** `{xp_change['xp']['monthly_xp']:,} XP`"
                    ),
                    color=discord.Color.blue()
                )
                embed.timestamp = discord.utils.utcnow()
                embed.set_footer(text="betpanda.io")
                await log_channel.send(embed=staff_embed)

            # Handle rank progression
            total_xp = xp_change['xp']['total_xp']
            eligible_rank = None

            for rank in config.RANK_THRESHOLDS:
                if total_xp >= rank["xp"]:
                    eligible_rank = rank
            
            if eligible_rank:
                role_id = eligible_rank['role_id']
                data = await update_user_rank(userid=member.id, role_id=role_id)
                if data['success']:
                    role = interaction.guild.get_role(role_id)
                    await member.add_roles(role)
                    embed = discord.Embed(
                        title="🐼 Rank Up! Level Cleared!",
                        description=f"**🎉 Congratulations {member.mention}**!\n"
                                    f"● **You have reached the rank of: ** <@&{role_id}>!\n"
                                    f"● **Total Cumulative XP: ** {total_xp} XP",
                        color=discord.Color.gold()
                    )
                    embed.set_thumbnail(url=member.display_avatar.url if member.display_avatar else None)
                    embed.timestamp = discord.utils.utcnow()
                    embed.set_footer(text="betpanda.io")
                    channel = self.bot.get_channel(config.MISSION_CHANNEL_ID)
                    if channel:
                        await channel.send(embed=embed)

                    staff_channel = self.bot.get_channel(config.LOG_CHANNEL_ID)
                    if staff_channel:
                        embed = discord.Embed(
                            title="🏆 Rank Up!",
                            description=f"**✧ User:** {member.mention}\n"
                                        f"**✧ User ID:** {member.id}\n"
                                        f"**✧ Role Assigned:** <@&{role_id}>\n"
                                        f"**✧ Role ID:** {role_id}\n"
                                        f"**✧ Reward Assigner:** Auto assigned.",
                            color=discord.Color.blue()                                      
                        )
                        embed.timestamp = discord.utils.utcnow()
                        embed.set_footer(text="betpanda.io")
                        await staff_channel.send(embed=embed)

    @app_commands.command(name="verify_mission", description="Manually approve and award XP for user weekly missions (Moderators only).")
    @app_commands.describe(member="The member to verify mission for")
    @app_commands.choices(mission=[
        app_commands.Choice(name=m["name"], value=key)
        for key, m in config.WEEKLY_MISSIONS.items()
        if not m["auto_track"] and m["status"] == "Active"
    ])
    async def verify_mission(self, interaction: discord.Interaction, member: discord.Member, mission: app_commands.Choice[str]):
        if not self.is_moderator(interaction):
            await interaction.response.send_message(
                "> ❌ **Access Denied**: Only server staff can verify missions.",
                ephemeral=True
            )
            return

        mission_key = mission.value
        mission_cfg = config.WEEKLY_MISSIONS.get(mission_key)

        if not mission_cfg:
            await interaction.response.send_message("> ❌ **Invalid Mission**: Mission configuration not found.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        mission_data = await complete_mission(userid=member.id, username=member.name, mission_key=mission_key)
        if mission_data['success']:
            embed = discord.Embed(
                title="🛡️ Mission Verified & Awarded!",
                description=(
                    f"**{interaction.user.display_name}** verified completion for **{member.mention}**!\n\n"
                    f"● **Completed Mission:** {mission_cfg['name']}\n"
                    f"● **Mission Details:** {mission_cfg['description']}\n"
                    f"● **Reward Granted:** `+{mission_cfg['xp_reward']:,} XP`"
                ),
                color=discord.Color.green()
            )
            embed.timestamp = discord.utils.utcnow()
            embed.set_footer(text="betpanda.io")
            await interaction.followup.send(embed=embed)
            channel = self.bot.get_channel(config.MISSION_CHANNEL_ID)
            if channel:
                await channel.send(embed=embed)

            # Log in staff channel
            log_channel = self.bot.get_channel(config.LOG_CHANNEL_ID)
            if log_channel:
                staff_embed = discord.Embed(
                    title="🛡️ Moderator Audit: Mission Verified",
                    description=(
                        f"**✧ Moderator:** {interaction.user.mention} (`{interaction.user.id}`)\n"
                        f"**✧ Recipient:** {member.mention} (`{member.id}`)\n"
                        f"**✧ Mission:** {mission_cfg['name']}\n"
                        f"**✧ Mission ID:** `{mission_cfg['mission_id']}`\n"
                        f"**✧ Reward:** `+{mission_cfg['xp_reward']:,} XP`\n"
                        f"**✧ Verification:** Manual Staff Review"
                    ),
                    color=discord.Color.blue()
                )
                embed.timestamp = discord.utils.utcnow()
                embed.set_footer(text="betpanda.io")
                await log_channel.send(embed=staff_embed)

    @app_commands.command(name="admin_profile", description="Display mentioned users current rank, XP totals, and progress.")
    @app_commands.describe(member="Member whose profile needs to be checked")
    async def user_profile_admin(self, interaction: discord.Interaction, member: discord.Member):
        await interaction.response.defer(ephemeral=True)
        target = member
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


async def setup(bot):
    await bot.add_cog(AdminCog(bot))