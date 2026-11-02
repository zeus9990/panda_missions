# Cog: ADMIN commands. Everything is under one group:  /admin <subcommand>
#
#   /admin xp            add or remove XP
#   /admin verify-mission  manually verify a mission
#   /admin profile       a user's rank/XP profile
#   /admin missions      a user's mission board
#   /admin pause-xp      pause MISSION XP FOR EVERYONE (it is held, not lost)
#   /admin resume-xp     resume for EVERYONE and credit all held XP
#   /admin xp-status     is mission XP paused? how many users / how much XP is held?
#
# Staff check (owner or ADMIN_ROLE_IDS) runs once for the whole group in
# `interaction_check`; failures are formatted by Cogs/error_handler.py.
import asyncio
from typing import Literal, Optional

import discord
from discord import app_commands
from discord.ext import commands

from config import WEEKLY_MISSIONS
from database import get_bet_status, get_pause_state, get_pause_summary, get_user_held, get_user_rank_position, user_details
from services.notify import send_staff_log
from services.xp import award_mission, grant_xp, pause_mission_xp, resume_mission_xp
from utils.checks import require_staff
from utils.embeds import build_missions_embed, build_profile_embed

MANUAL_MISSIONS = [
    app_commands.Choice(name=m["name"][:100], value=key)
    for key, m in WEEKLY_MISSIONS.items()
    if not m["auto_track"] and m["status"] == "Active"
]


def _stamp(embed: discord.Embed) -> discord.Embed:
    embed.timestamp = discord.utils.utcnow()
    embed.set_footer(text="betpanda.io")
    return embed


class AdminCog(commands.GroupCog, group_name="admin", group_description="Moderator / admin tools"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        super().__init__()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        require_staff(interaction)  # raises -> central error handler
        return True

    async def _audit(self, interaction: discord.Interaction, title: str, **fields: str) -> None:
        lines = [f"**✧ Moderator:** {interaction.user.mention} (`{interaction.user.id}`)"]
        lines += [f"**✧ {name.replace('_', ' ').title()}:** {value}" for name, value in fields.items()]
        embed = _stamp(discord.Embed(title=f"🛡️ Moderator Audit: {title}",
                                     description="\n".join(lines), color=discord.Color.blue()))
        await send_staff_log(interaction.guild, embed)

    # ── XP: add / remove ────────────────────────────────────────────────────
    @app_commands.command(name="xp", description="Add or remove XP from a user.")
    @app_commands.describe(action="Add or remove XP", user="The user", amount="Amount of XP",
                           reason="Reason (shown in the staff log)")
    async def xp(self, interaction: discord.Interaction, action: Literal["add", "remove"],
                 user: discord.Member, amount: app_commands.Range[int, 1, 1_000_000],
                 reason: Optional[str] = "No reason given"):
        if user.bot:
            await interaction.response.send_message("> ❌ Bots don't earn XP.", ephemeral=True)
            return
        await interaction.response.defer()

        delta = amount if action == "add" else -amount
        result = await grant_xp(interaction.guild, user.id, user.name, delta)
        xp = result["xp"]

        embed = _stamp(discord.Embed(
            title="🎁 XP Awarded!" if delta > 0 else "➖ XP Removed",
            description=(
                f"● **{result['message']}**\n"
                f"● **Reason:** {reason}\n"
                f"● **Total XP:** `{xp['total_xp']:,} XP`\n"
                f"● **Monthly XP:** `{xp['monthly_xp']:,} XP`"
            ),
            color=discord.Color.green() if delta > 0 else discord.Color.red()))
        await interaction.followup.send(embed=embed)
        await self._audit(
            interaction, f"XP {'Awarded' if delta > 0 else 'Removed'}",
            recipient=f"{user.mention} (`{user.id}`)", amount=f"`{delta:+,} XP`",
            reason=str(reason), new_total_xp=f"`{xp['total_xp']:,} XP`",
            new_monthly_xp=f"`{xp['monthly_xp']:,} XP`")

    # ── Missions ────────────────────────────────────────────────────────────
    @app_commands.command(name="verify-mission", description="Manually approve a weekly mission for a user.")
    @app_commands.describe(user="The user to verify the mission for", mission="The mission to verify")
    @app_commands.choices(mission=MANUAL_MISSIONS)
    async def verify_mission(self, interaction: discord.Interaction, user: discord.Member,
                             mission: app_commands.Choice[str]):
        await interaction.response.defer(ephemeral=True)
        result = await award_mission(
            interaction.guild, user.id, user.name, mission.value,
            assigner=f"{interaction.user.mention} (manual review)")
        if not result["success"]:
            await interaction.followup.send(f"> {result['message']}", ephemeral=True)
            return

        note = "\n⏸️ Mission XP is **paused**, so this XP is being held until it is resumed." if result["paused"] else ""
        await interaction.followup.send(
            f"> ✅ **{result['mission']['name']}** verified for {user.mention} "
            f"(`+{result['mission']['xp_reward']:,} XP`).{note}", ephemeral=True)

    @app_commands.command(name="missions", description="View a user's weekly mission progress.")
    @app_commands.describe(user="The user to check")
    async def missions(self, interaction: discord.Interaction, user: discord.Member):
        await interaction.response.defer(ephemeral=True)
        user_db = await user_details(user.id)
        if not user_db["success"]:
            await interaction.followup.send(f"> ❌ {user.mention} is not registered yet.", ephemeral=True)
            return
        await interaction.followup.send(
            embed=build_missions_embed(user_db["message"], user, await get_pause_state(), admin_view=True),
            ephemeral=True)

    @app_commands.command(name="profile", description="Display a user's rank, XP totals, and progress.")
    @app_commands.describe(user="The user to check")
    async def profile(self, interaction: discord.Interaction, user: discord.Member):
        await interaction.response.defer(ephemeral=True)
        user_db = await user_details(user.id)
        if not user_db["success"]:
            await interaction.followup.send(f"> ❌ {user.mention} is not registered yet.", ephemeral=True)
            return
        positions, pause_state, bet_status = await asyncio.gather(
            get_user_rank_position(user.id), get_pause_state(), get_bet_status(user.id))
        await interaction.followup.send(
            embed=build_profile_embed(user, user_db["message"], positions, pause_state, bet_status),
            ephemeral=True)

    # ── Pause / resume / status (GLOBAL - applies to every user) ────────────
    @app_commands.command(name="pause-xp", description="Pause MISSION XP for EVERYONE (held until you resume).")
    @app_commands.describe(reason="Why mission XP is being paused (shown in the staff log and /admin xp-status)")
    async def pause_xp_cmd(self, interaction: discord.Interaction, reason: Optional[str] = None):
        await interaction.response.defer(ephemeral=True)
        result = await pause_mission_xp(interaction.user.id, reason)
        if not result["success"]:
            await interaction.followup.send(f"> ℹ️ {result['message']}", ephemeral=True)
            return
        await interaction.followup.send(
            "> ⏸️ Mission XP is now **paused for everyone**. Missions are still tracked, but their XP "
            "is held per user until you run `/admin resume-xp`. Users see this on `/missions`.",
            ephemeral=True)
        await self._audit(interaction, "Mission XP Paused (everyone)", reason=reason or "No reason given")

    @app_commands.command(name="resume-xp", description="Resume MISSION XP for EVERYONE and credit all held XP.")
    async def resume_xp_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        result = await resume_mission_xp(interaction.guild, interaction.user.id)
        if not result["success"]:
            await interaction.followup.send(f"> ℹ️ {result['message']}", ephemeral=True)
            return

        users, total = len(result["users"]), result["total_credited"]
        await interaction.followup.send(
            f"> ▶️ Mission XP **resumed for everyone**. Credited `{total:,} XP` to **{users}** "
            f"user(s); **{result['ranked_up']}** ranked up.", ephemeral=True)
        await self._audit(interaction, "Mission XP Resumed (everyone)",
                          users_credited=str(users), total_credited=f"`{total:,} XP`",
                          rank_ups=str(result["ranked_up"]))

    @app_commands.command(name="xp-status", description="Check whether mission XP is paused and how much is held.")
    @app_commands.describe(user="Optional: also show what this user has held")
    async def xp_status(self, interaction: discord.Interaction, user: Optional[discord.Member] = None):
        await interaction.response.defer(ephemeral=True)
        summary = await get_pause_summary()

        if summary["paused"]:
            embed = discord.Embed(title="⏸️ Mission XP: PAUSED (everyone)", color=discord.Color.orange())
            if summary["paused_at"]:
                embed.add_field(name="Paused", value=discord.utils.format_dt(summary["paused_at"], "R"), inline=True)
            if summary["paused_by"]:
                embed.add_field(name="Paused by", value=f"<@{summary['paused_by']}>", inline=True)
            embed.add_field(name="Reason", value=summary["reason"] or "No reason given", inline=False)
        else:
            embed = discord.Embed(title="▶️ Mission XP: Active", color=discord.Color.green(),
                                  description="Mission XP is **not** paused.")
        embed.add_field(name="Users with held XP", value=f"`{summary['held_users']:,}`", inline=True)
        embed.add_field(name="Total held XP", value=f"`{summary['held_xp']:,} XP`", inline=True)

        if user is not None:
            held = await get_user_held(user.id)
            if not held["success"]:
                text = f"{user.mention} is not registered yet."
            elif not held["pending_xp"]:
                text = f"{user.mention} has nothing held."
            else:
                lines = "\n".join(f"● {m['name']} - `{m['xp']:,} XP`" for m in held["pending_missions"])
                text = f"{user.mention}: `{held['pending_xp']:,} XP` held\n{lines}"
            embed.add_field(name="Selected user", value=text[:1000], inline=False)
        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(AdminCog(bot))
