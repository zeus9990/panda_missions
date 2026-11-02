"""Embed builders shared by the user and admin commands."""
import discord

from config import RANK_THRESHOLDS, WEEKLY_MISSIONS

_RANKS = sorted(RANK_THRESHOLDS, key=lambda r: r["xp"])


def _paused_notice(user_data: dict, *, admin_view: bool) -> str:
    held = user_data.get("pending_xp", 0) or 0
    if admin_view:
        return (f"⏸️ **Mission XP is PAUSED for everyone.** This user has `{held:,} XP` held, "
                "credited when staff resume mission XP.")
    return (f"⏸️ **Mission XP is currently paused by staff.** Missions you complete are still "
            f"tracked and `{held:,} XP` is being held for you. It will be credited to your "
            "account automatically as soon as staff resume mission XP.")


def build_missions_embed(
    user_data: dict, target: discord.abc.User, pause_state: dict | None = None,
    *, admin_view: bool = False,
) -> discord.Embed:
    """The /missions board. Shows a banner while mission XP is paused (globally)."""
    completed_ids = set(user_data.get("missions", []))
    held_ids = {m["mission_id"] for m in user_data.get("pending_missions", [])}
    paused = bool(pause_state and pause_state.get("paused"))

    active = {k: m for k, m in WEEKLY_MISSIONS.items() if m.get("status") == "Active"}
    completed_count = sum(1 for m in active.values() if m["mission_id"] in completed_ids)
    total = len(active)
    filled = int((completed_count / total) * 20) if total else 0
    bar = f"`[{'█' * filled}{'░' * (20 - filled)}]` {completed_count}/{total}"

    lines = []
    if paused:
        lines.append(_paused_notice(user_data, admin_view=admin_view) + "\n")
    lines += [
        "**Complete these tasks each week to earn massive XP rewards!**",
        "**Some missions track automatically, others are verified manually by moderators.**\n",
        f"● **Overall Progress:** {bar}",
    ]
    embed = discord.Embed(
        description="\n".join(lines),
        color=discord.Color.orange() if paused else discord.Color.green(),
    )
    embed.set_author(
        name=("🐼 Weekly Panda Mission Board" if not admin_view
              else f"🐼 {target.display_name}'s Weekly Missions"),
        icon_url=target.display_avatar.url,
    )

    for key, mission in active.items():
        done = mission["mission_id"] in completed_ids
        status = "✅ Completed" if done else "⏳ In Progress"
        if done and mission["mission_id"] in held_ids:
            status += " ⏸️ (XP held)"
        tracking = "🤖 Auto-tracked" if mission["auto_track"] else "🛡️ Moderator Verified"
        value = (
            f"● **XP Award:** `{mission['xp_reward']:,} XP`\n"
            f"● **Status:** {status}\n"
            f"● **Type:** {tracking}\n"
        )
        if mission.get("count") is not None:
            progress = mission["count"] if done else min(user_data.get(key, 0), mission["count"])
            value += f"● **Progress:** `{progress}/{mission['count']}`\n"
        value += f"*{mission['description']}*"
        embed.add_field(name=f"{'🟢' if done else '🟠'} {mission['name']}", value=value, inline=False)

    footer = f"Weekly missions reset, but total XP stacks forever! ● Total XP: {user_data.get('total_xp', 0):,}"
    embed.set_footer(text=footer)
    return embed


def _bets_text(user_data: dict, bet_status: dict) -> str:
    """The "Mini-game Bets" section of the profile."""
    limit, staked = bet_status["daily_limit"], bet_status["staked_today"]
    monthly = user_data.get("monthly_xp", 0) or 0
    total = user_data.get("total_xp", 0) or 0
    # Same rules as database.bets.place_bet: per-bet cap, daily allowance left, monthly + total XP held.
    max_now = max(0, min(bet_status["max_per_bet"], bet_status["remaining_today"], monthly, total))

    filled = int(min(staked / limit, 1) * 20) if limit else 0
    text = (
        f"`[{'█' * filled}{'░' * (20 - filled)}]` {staked:,} / {limit:,} XP staked today\n"
        f"● **Max bet right now:** `{max_now:,} XP`\n"
        f"● **Daily allowance left:** `{bet_status['remaining_today']:,} XP` (resets 00:00 UTC)"
    )
    if monthly <= 0:
        text += "\n⚠️ You have 0 monthly XP - bets can only use XP you hold this month."
    return text


def build_profile_embed(
    target: discord.abc.User, user_data: dict, positions: dict, pause_state: dict | None = None,
    bet_status: dict | None = None,
) -> discord.Embed:
    """Profile card used by /profile and /admin profile."""
    total_xp = user_data.get("total_xp", 0)
    monthly_xp = user_data.get("monthly_xp", 0)
    role_id = user_data.get("rank")

    rank_name = next((r["name"] for r in RANK_THRESHOLDS if r["role_id"] == role_id), "Unranked")

    # Next rank + progress bar. (The old copies of this code crashed with
    # UnboundLocalError for users at max rank because xp_span was never set.)
    next_rank = next((r for r in _RANKS if total_xp < r["xp"]), None)
    if next_rank:
        floor = max((r["xp"] for r in _RANKS if r["xp"] <= total_xp), default=0)
        span = next_rank["xp"] - floor
        progress = total_xp - floor
        pct = min(100.0, round(progress / span * 100, 1)) if span > 0 else 0.0
        next_value = f"**{next_rank['name']}** ({next_rank['xp'] - total_xp:,} XP to go)"
        detail = f" ({progress:,} / {span:,} XP)"
    else:
        pct, next_value, detail = 100.0, "**Max Rank Achieved**", ""
    blocks = int(pct / 5)
    bar = f"`[{'█' * blocks}{'░' * (20 - blocks)}]` {pct}%{detail}"

    active_ids = {m["mission_id"] for m in WEEKLY_MISSIONS.values() if m["status"] == "Active"}
    done = sum(1 for mid in user_data.get("missions", []) if mid in active_ids)

    embed = discord.Embed(color=discord.Color.green())
    embed.set_author(name=f"🐼 {target.display_name}'s Bamboo Stats Profile",
                     icon_url=target.display_avatar.url)
    embed.add_field(name="🏆 Current Rank", value=f"**{rank_name}**", inline=True)
    embed.add_field(name="📅 Monthly Leaderboard Position",
                    value=f"**#{positions.get('monthly_position', '?')}**", inline=True)
    embed.add_field(name="✨ Monthly XP", value=f"`{monthly_xp:,} XP`", inline=True)
    embed.add_field(name="📅 All-time Leaderboard Position",
                    value=f"**#{positions.get('total_position', '?')}**", inline=True)
    embed.add_field(name="✨ Total XP", value=f"`{total_xp:,} XP`", inline=True)
    embed.add_field(name="🎯 Next Rank", value=next_value, inline=True)
    embed.add_field(name="📈 Rank Progress", value=bar, inline=False)

    missions_text = f"Completed **{done} / {len(active_ids)}** missions this week. (Run `/missions` to view details)"
    if pause_state and pause_state.get("paused"):
        missions_text += f"\n⏸️ Mission XP is paused - `{user_data.get('pending_xp', 0):,} XP` held for you."
    embed.add_field(name="🏁 Weekly Missions", value=missions_text, inline=False)
    if bet_status:
        embed.add_field(name="🎲 Mini-game Bets", value=_bets_text(user_data, bet_status), inline=False)
    embed.set_footer(text="Be active in community channels and complete missions to earn more XP!")
    return embed
