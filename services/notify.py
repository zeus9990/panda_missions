"""Embeds posted to the mission channel and the staff log channel."""
import logging

import discord

from config import LOG_CHANNEL_ID, MISSION_CHANNEL_ID

log = logging.getLogger(__name__)


async def send_to_channel(guild: discord.Guild, channel_id: int, embed: discord.Embed) -> None:
    channel = guild.get_channel(channel_id)
    if channel is None:
        return
    try:
        await channel.send(embed=embed)
    except discord.HTTPException:
        log.exception("Could not post to channel %s.", channel_id)


async def send_staff_log(guild: discord.Guild, embed: discord.Embed) -> None:
    await send_to_channel(guild, LOG_CHANNEL_ID, embed)


def _stamp(embed: discord.Embed) -> discord.Embed:
    embed.timestamp = discord.utils.utcnow()
    embed.set_footer(text="betpanda.io")
    return embed


async def post_mission_complete(
    guild: discord.Guild, user_id: int, mission: dict, *, paused: bool, assigner: str
) -> None:
    """Public + staff announcement for a completed mission."""
    reward = f"`+{mission['xp_reward']:,} XP`" + (" ⏸️ *held - mission XP is paused*" if paused else "")
    mention = f"<@{user_id}>"

    public = _stamp(discord.Embed(
        title="🎉 Weekly Mission Completed!",
        description=(
            f"**Congratulations {mention}!**\n"
            f"● **You completed:** {mission['name']}\n"
            f"● **Mission Description:** {mission['description']}\n"
            f"● **Rewarded:** {reward}"
        ),
        color=discord.Color.green(),
    ))
    staff = _stamp(discord.Embed(
        title="📈 Mission Complete!",
        description=(
            f"**✧ User:** {mention}\n"
            f"**✧ User ID:** {user_id}\n"
            f"**✧ Mission Title:** {mission['name']}\n"
            f"**✧ Mission ID:** `{mission['mission_id']}`\n"
            f"**✧ Mission Reward:** {reward}\n"
            f"**✧ Reward Assigner:** {assigner}"
        ),
        color=discord.Color.blue(),
    ))
    await send_to_channel(guild, MISSION_CHANNEL_ID, public)
    await send_to_channel(guild, LOG_CHANNEL_ID, staff)
