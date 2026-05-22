import asyncio
import aiohttp
import discord
from typing import Optional
from discord.ext import commands, tasks
from config import ENGAGE_API_KEY, LOG_CHANNEL_ID, MISSION_CHANNEL_ID, ADMIN_ROLE_IDS
from database import user_details, user_register, complete_mission, update_engage_cache
from rank_update import rank_update_embed

ENGAGE_ORDER = ["x_likes", "x_retweets", "x_comments"]

class XEngageCog(commands.Cog):

    def is_moderator(self, interaction: discord.Interaction) -> bool:
        """Helper to verify if the user has the designated admin/mod role."""
        if not interaction.guild:
            return False
        return (
            interaction.user.id == interaction.guild.owner_id or
            any(role.id in ADMIN_ROLE_IDS for role in interaction.user.roles)
        )
    
    def __init__(self, bot: commands.Bot):
        self.bot  = bot
        self._session: Optional[aiohttp.ClientSession] = None
        self.engage_loop.start()

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
        params  = {"page": page, "sortBy": "points"}
        try:
            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    print("[XEngage] request error: {resp.status}")
                    return None
                return await resp.json()
        except aiohttp.ClientError as exc:
            print(f"[XEngage] HTTP error fetching page: {exc}")
            return None

    @tasks.loop(minutes=30)
    async def engage_loop(self):
        print("[XEngage] Sync started.")
        page = 0
        total_users = 0
        total_awards = 0

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
            for entry in leaderboard:
                awarded = await self._process_entry(entry)
                total_users  += 1
                total_awards += awarded
            if not has_next:
                break
            page += 1

    @engage_loop.before_loop
    async def before_engage_loop(self):
        await self.bot.wait_until_ready()

    async def _process_entry(self, entry: dict) -> int:
        discord_id_str = entry.get("discordId")
        username = entry.get("discordName")
        api_points = entry.get("points")
        if discord_id_str is None or api_points is None:
            return 0
        try:
            discord_id = int(discord_id_str)
        except (ValueError, TypeError):
            print(f"[XEngage] Invalid discordId value: {discord_id_str}")
            return 0
        user = await user_details(userid=discord_id)

        if not user['success']:
            await user_register(userid=discord_id, username=username)
            cached_points = 0
        else:
            cached_points: int = user.get("engage_points", 0)

        diff = api_points - cached_points
        if diff <= 0:
            return 0

        increments = diff // 3
        if increments == 0:
            return 0

        for mission_key in ENGAGE_ORDER:
            for _ in range(increments):
                await asyncio.sleep(5)
                mission_data = await complete_mission(userid=discord_id, username=username, mission_key=mission_key)
                if mission_data['success']:
                    try:
                        user_object = await self.bot.fetch_user(discord_id)
                    except discord.NotFound:
                        print(f"[XEngage] Could not fetch user {discord_id}, skipping embed.")
                        user_object = None
                    if user_object:
                        embed = discord.Embed(
                            title="🎉 Weekly Mission Completed!",
                            description=f"**Congratulations {user_object.mention}!**\n"
                                        f"● **You completed:** {mission_data['mission']['name']}\n"
                                        f"● **Mission Description:** {mission_data['mission']['description']}\n"
                                        f"● **Rewarded:** `+{mission_data['mission']['xp_reward']} XP`",
                            color=discord.Color.green()
                        )
                        embed.timestamp = discord.utils.utcnow()
                        embed.set_footer(text="betpanda.io")
                        channel = self.bot.get_channel(MISSION_CHANNEL_ID)
                        if channel:
                            await channel.send(embed=embed)
        
                        # Log in staff channel
                        staff_channel = self.bot.get_channel(LOG_CHANNEL_ID)
                        if staff_channel:
                            embed = discord.Embed(
                                title="📈 Mission Complete!",
                                description=f"**✧ User:** {user_object.mention}\n"
                                            f"**✧ User ID:** {user_object.id}\n"
                                            f"**✧ Mission Title:** {mission_data['mission']['name']}\n"
                                            f"**✧ Mission ID:** `{mission_data['mission']['mission_id']}`\n"
                                            f"**✧ Mission Reward:** `+{mission_data['mission']['xp_reward']} XP`\n"
                                            f"**✧ Reward Assigner:** Auto assigned.",
                                color=discord.Color.blue()                                      
                            )
                            embed.timestamp = discord.utils.utcnow()
                            embed.set_footer(text="betpanda.io")
                            await staff_channel.send(embed=embed)

                        total_xp = mission_data['total_xp']
                        await rank_update_embed(interaction=staff_channel, userid=discord_id, total_xp=total_xp)
        await update_engage_cache(userid=discord_id, engage_points=api_points)
        return increments
    
    
    @discord.app_commands.command(name="sync_engage", description="Manually trigger an engagement sync right now.")
    async def sync_engage(self, interaction: discord.Interaction):
        if not self.is_moderator(interaction):
            await interaction.response.send_message("> ❌ You don't have permission to use this command.", ephemeral=True)
            return
 
        await interaction.response.send_message("> ⏳ Running engagement sync...", ephemeral=True)
        await self.engage_loop()
        await interaction.followup.send("> ✅ Engagement sync complete.", ephemeral=True)
 
    @discord.app_commands.command(name="engage_status", description="Show cached engage points for a member.")
    @discord.app_commands.describe(member="The member to check")
    async def engage_status(self, interaction: discord.Interaction, member: discord.Member):
        if not self.is_moderator(interaction):
            await interaction.response.send_message("> ❌ You don't have permission to use this command.", ephemeral=True)
            return
 
        user = await user_details(member.id)
        if not user:
            await interaction.response.send_message(f"> ❌ No DB entry found for {member.mention}.", ephemeral=True)
            return
 
        cached = user.get("engage_points", 0)
 
        embed = discord.Embed(
            title=f"Engage Points — {member.display_name}",
            color=discord.Color.green()
        )
        embed.add_field(name="Cached (DB)", value=str(cached),                        inline=True)
        embed.add_field(name="x_likes",     value=str(user.get("x_likes", 0)),        inline=True)
        embed.add_field(name="x_retweets",  value=str(user.get("x_retweets", 0)),     inline=True)
        embed.add_field(name="x_comments",  value=str(user.get("x_comments", 0)),     inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)
 
 
async def setup(bot: commands.Bot):
    await bot.add_cog(XEngageCog(bot))