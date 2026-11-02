"""Central rank check. EVERY XP credit must end up here (via services.xp)."""
import logging

import discord

from config import LOG_CHANNEL_ID, MISSION_CHANNEL_ID, RANK_THRESHOLDS
from database import get_current_rank, update_user_rank

log = logging.getLogger(__name__)

_RANKS = sorted(RANK_THRESHOLDS, key=lambda r: r["xp"])  # ascending by XP


def eligible_rank(total_xp: int) -> dict | None:
    """Highest rank whose threshold `total_xp` reaches (None if below the first)."""
    best = None
    for rank in _RANKS:
        if total_xp >= rank["xp"]:
            best = rank
    return best


def _xp_for_role(role_id: int) -> int:
    """XP threshold of a stored rank role id (-1 if it is not a known rank)."""
    return next((r["xp"] for r in _RANKS if r["role_id"] == role_id), -1)


async def _get_member(guild: discord.Guild, user_id: int) -> discord.Member | None:
    member = guild.get_member(user_id)
    if member is not None:
        return member
    try:
        return await guild.fetch_member(user_id)
    except discord.NotFound:
        return None


async def check_rank(guild: discord.Guild, user_id: int, total_xp: int) -> bool:
    """Promote the user if `total_xp` earned a higher rank. Returns True if promoted.

    Ranks are never downgraded: removing XP does not remove a rank.
    """
    target = eligible_rank(total_xp)
    if target is None:
        return False

    role_id = target["role_id"]
    current = await get_current_rank(user_id)
    if current == role_id or _xp_for_role(current) >= target["xp"]:
        return False

    member = await _get_member(guild, user_id)
    if member is None:
        log.info("Rank check skipped: %s is not in the server.", user_id)
        return False
    role = guild.get_role(role_id)
    if role is None:
        log.error("Rank role %s (%s) does not exist in the server.", role_id, target["name"])
        return False

    # Claim the promotion in the DB first so two concurrent XP events can't both announce it.
    if not (await update_user_rank(user_id, role_id))["success"]:
        return False
    try:
        await member.add_roles(role, reason=f"Auto rank-up: {target['name']}")
    except discord.HTTPException:
        log.exception("Could not give role %s to %s; reverting stored rank.", role_id, user_id)
        await update_user_rank(user_id, current)
        return False

    await _announce(guild, member, role_id, total_xp)
    return True


async def _announce(guild: discord.Guild, member: discord.Member, role_id: int, total_xp: int) -> None:
    public = discord.Embed(
        title="🐼 Rank Up! Level Cleared!",
        description=(
            f"**🎉 Congratulations {member.mention}**!\n"
            f"● **You have reached the rank of: ** <@&{role_id}>!\n"
            f"● **Total Cumulative XP: ** {total_xp:,} XP"
        ),
        color=discord.Color.gold(),
        timestamp=discord.utils.utcnow(),
    )
    public.set_thumbnail(url=member.display_avatar.url)
    public.set_footer(text="betpanda.io")

    staff = discord.Embed(
        title="🏆 Rank Up!",
        description=(
            f"**✧ User:** {member.mention}\n"
            f"**✧ User ID:** {member.id}\n"
            f"**✧ Role Assigned:** <@&{role_id}>\n"
            f"**✧ Role ID:** {role_id}\n"
            f"**✧ Reward Assigner:** Auto assigned."
        ),
        color=discord.Color.blue(),
        timestamp=discord.utils.utcnow(),
    )
    staff.set_footer(text="betpanda.io")

    for channel_id, embed in ((MISSION_CHANNEL_ID, public), (LOG_CHANNEL_ID, staff)):
        channel = guild.get_channel(channel_id)
        if channel is None:
            continue
        try:
            await channel.send(embed=embed)
        except discord.HTTPException:
            log.exception("Could not post rank-up embed to channel %s.", channel_id)
