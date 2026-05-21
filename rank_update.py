import discord
from config import RANK_THRESHOLDS, MISSION_CHANNEL_ID, LOG_CHANNEL_ID
from database import update_user_rank

async def rank_update_embed(interaction: discord.Interaction, userid: int, total_xp: int) -> None:
    member = interaction.guild.get_member(userid)
    eligible_rank = None

    for rank in RANK_THRESHOLDS:
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
            channel = interaction.guild.get_channel(MISSION_CHANNEL_ID)
            if channel:
                await channel.send(embed=embed)

            staff_channel = interaction.guild.get_channel(LOG_CHANNEL_ID)
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