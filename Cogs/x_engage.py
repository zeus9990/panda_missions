import asyncio
import aiohttp
import discord
from typing import Optional
from discord.ext import commands, tasks
from config import ENGAGE_API_KEY, LOG_CHANNEL_ID
from database import user_details, user_register, update_engage_cache
from services.xp import award_mission
from utils.checks import admin_only
from utils.errors import report_task_error

ENGAGE_ORDER = ["x_likes", "x_retweets", "x_comments"]

# Limits how many users are processed truly simultaneously.
# Tune this up or down based on your MongoDB connection pool size.
USER_CONCURRENCY = 5


class XEngageCog(commands.Cog):

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._session: Optional[aiohttp.ClientSession] = None
        self.engage_loop.start()

    def _guild(self) -> Optional[discord.Guild]:
        """The server the bot runs in (taken from the staff log channel)."""
        channel = self.bot.get_channel(LOG_CHANNEL_ID)
        return channel.guild if channel else None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={"x-api-key": ENGAGE_API_KEY}
            )
        return self._session

    async def cog_unload(self):
        self.engage_loop.cancel()
        if self._session and not self._session.closed:
            await self._session.close()

    async def _fetch_page(self, page: int) -> Optional[dict]:
        session = await self._get_session()
        url = f"https://engages.io/api/v1/leaderboard"
        params = {"page": page, "sortBy": "points"}
        try:
            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    print(f"[XEngage] request error: {resp.status}")
                    return None
                return await resp.json()
        except aiohttp.ClientError as exc:
            print(f"[XEngage] HTTP error fetching page: {exc}")
            return None

    @tasks.loop(minutes=30)
    async def engage_loop(self):
        # A tasks.loop dies for good on an unhandled error, so catch + report here.
        try:
            await self._sync()
        except Exception as exc:
            await report_task_error(self.bot, exc, "task XEngage.engage_loop")

    async def _sync(self):
        print("[XEngage] Sync started.")

        # ── 1. Collect ALL entries from every page first ──────────────────────
        all_entries: list[dict] = []
        page = 0
        while True:
            data = await self._fetch_page(page)
            if data is None:
                print(f"[XEngage] Aborting sync — page {page} fetch failed.")
                break
            leaderboard = data.get("leaderboard", [])
            usage = data.get("usage", 0)
            limit = data.get("limit", 10_000)
            has_next = data.get("hasNextPage", False)
            print(f"[XEngage] Page {page} — {len(leaderboard)} entries | API usage {usage}/{limit}")
            all_entries.extend(leaderboard)
            if not has_next:
                break
            page += 1

        print(f"[XEngage] Total entries to process: {len(all_entries)}")

        # ── 2. Process all users concurrently, capped by semaphore ────────────
        semaphore = asyncio.Semaphore(USER_CONCURRENCY)

        async def bounded(entry: dict):
            async with semaphore:
                return await self._process_entry(entry)

        results = await asyncio.gather(*[bounded(e) for e in all_entries], return_exceptions=True)

        total_users  = len(all_entries)
        total_awards = sum(r for r in results if isinstance(r, int))
        errors       = sum(1 for r in results if isinstance(r, Exception))

        print(f"[XEngage] Sync complete — {total_users} users, {total_awards} missions awarded, {errors} errors.")

    @engage_loop.before_loop
    async def before_engage_loop(self):
        await self.bot.wait_until_ready()

    async def _process_entry(self, entry: dict) -> int:
        discord_id_str = entry.get("discordId")
        username       = entry.get("discordName")
        api_points     = entry.get("points")

        if discord_id_str is None or api_points is None:
            return 0
        try:
            discord_id = int(discord_id_str)
        except (ValueError, TypeError):
            print(f"[XEngage] Invalid discordId value: {discord_id_str}")
            return 0

        user = await user_details(userid=discord_id)
        if not user["success"]:
            await user_register(userid=discord_id, username=username)
            cached_points = 0
        else:
            cached_points: int = user["message"].get("engage_points", 0)

        diff = api_points - cached_points
        if diff <= 0:
            return 0

        increments = diff // 3
        if increments == 0:
            return 0

        guild = self._guild()
        if guild is None:
            print("[XEngage] Staff log channel not found - cannot award missions.")
            return 0

        awarded = 0
        for mission_key in ENGAGE_ORDER:
            for _ in range(increments):
                # award_mission announces, honours mission-XP pause and runs the rank check.
                result = await award_mission(guild, discord_id, username or str(discord_id), mission_key)
                if result["success"]:
                    awarded += 1

        await update_engage_cache(userid=discord_id, engage_points=api_points)
        return awarded


    @discord.app_commands.command(name="sync_engage", description="Manually trigger an engagement sync right now.")
    @admin_only()
    async def sync_engage(self, interaction: discord.Interaction):
        await interaction.response.send_message("> ⏳ Running engagement sync...", ephemeral=True)
        await self._sync()
        await interaction.followup.send("> ✅ Engagement sync complete.", ephemeral=True)

    @discord.app_commands.command(name="engage_status", description="Show cached engage points for a member.")
    @discord.app_commands.describe(member="The member to check")
    @admin_only()
    async def engage_status(self, interaction: discord.Interaction, member: discord.Member):
        result = await user_details(member.id)
        if not result["success"]:
            await interaction.response.send_message(f"> ❌ No DB entry found for {member.mention}.", ephemeral=True)
            return
        user = result["message"]  # user_details wraps the document in {"success", "message"}
        embed = discord.Embed(title=f"Engage Points — {member.display_name}", color=discord.Color.green())
        embed.add_field(name="Cached (DB)", value=str(user.get("engage_points", 0)), inline=True)
        embed.add_field(name="x_likes",     value=str(user.get("x_likes", 0)),    inline=True)
        embed.add_field(name="x_retweets",  value=str(user.get("x_retweets", 0)), inline=True)
        embed.add_field(name="x_comments",  value=str(user.get("x_comments", 0)), inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(XEngageCog(bot))