# Cog: Daily stats of Telegram and Discord
import discord
from dotenv import load_dotenv
from typing import Literal
import datetime as dt
import os, json
from config import TG_CHAT_ID, TG_GROUP_ID
from database import record_stat_event, get_stats_range
from discord.ext import commands
from discord import app_commands
from telegram import Update
from telegram.ext import (
    Application,
    ApplicationBuilder,
    ChatMemberHandler,
    MessageHandler,
    ContextTypes,
    filters,
)


load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("TG_BOT_TOKEN")
TELEGRAM_CHAT_ID = TG_CHAT_ID


class StatsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.telegram_app: Application | None = None

    def _resolve_telegram_platform(self, chat_id) -> str | None:
        if str(chat_id) == str(TG_GROUP_ID):
            return "telegram_channel"
        elif str(chat_id) == str(TG_CHAT_ID):
            return "telegram_group"
        return None
    
    async def cog_load(self):
        if not TELEGRAM_BOT_TOKEN:
            print(
                "StatsCog: TELEGRAM_BOT_TOKEN not set - Telegram tracking disabled."
            )
            return

        self.telegram_app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

        # Track members joining/leaving a group or channel
        self.telegram_app.add_handler(
            ChatMemberHandler(self._on_telegram_chat_member, ChatMemberHandler.CHAT_MEMBER)
        )
        # Track messages
        self.telegram_app.add_handler(
            MessageHandler(filters.ALL & ~filters.StatusUpdate.ALL, self._on_telegram_message)
        )

        # Start polling manually (non-blocking) instead of run_polling(),
        # since run_polling() wants to own the event loop itself. This way
        # it shares the loop your Discord bot is already running on.
        await self.telegram_app.initialize()
        await self.telegram_app.start()
        # allowed_updates=Update.ALL_TYPES is required here — Telegram does NOT
        # send "chat_member" updates by default (for backwards compatibility
        # with older bots), even if a handler is registered for them. Without
        # this, join/leave events are silently never delivered.
        await self.telegram_app.updater.start_polling(
            drop_pending_updates=True,
            allowed_updates=Update.ALL_TYPES,
        )
        print("StatsCog: Telegram bot polling started.")

    async def cog_unload(self):
        if self.telegram_app:
            await self.telegram_app.updater.stop()
            await self.telegram_app.stop()
            await self.telegram_app.shutdown()
            print("StatsCog: Telegram bot stopped cleanly.")

    # ---------------------------------------------------------------
    # Discord handlers
    # ---------------------------------------------------------------
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        await record_stat_event("discord", "join", member.id, total_members=member.guild.member_count)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        await record_stat_event("discord", "leave", member.id, total_members=member.guild.member_count)

    # ---------------------------------------------------------------
    # Telegram handlers
    # ---------------------------------------------------------------
    async def _on_telegram_chat_member(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.effective_chat.id
        platform = self._resolve_telegram_platform(chat_id)
        if platform is None:
            return
        old_status = update.chat_member.old_chat_member.status
        new_status = update.chat_member.new_chat_member.status
        user_id = update.chat_member.new_chat_member.user.id

        left_statuses = {"left", "kicked"}
        joined_statuses = {"member", "administrator", "restricted"}

        event_type = None
        if new_status in joined_statuses and old_status in left_statuses:
            event_type = "join"
        elif new_status in left_statuses and old_status not in left_statuses:
            event_type = "leave"

        if event_type is None:
            return

        total_members = None
        try:
            total_members = await context.bot.get_chat_member_count(chat_id)
        except Exception as e:
            print("Could not fetch Telegram member count: %s", e)

        await record_stat_event(platform, event_type, user_id, total_members=total_members)

    async def _on_telegram_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.effective_message:
            return
        chat_id = update.effective_chat.id
        platform = self._resolve_telegram_platform(chat_id)
        if platform is None:
            return

        # Channel posts have no effective_user (posts are attributed to the
        # channel, not a person) — fall back to a channel-scoped placeholder
        # so we still record the message/total_members snapshot.
        user_id = update.effective_user.id if update.effective_user else f"channel:{chat_id}"

        total_members = None
        try:
            total_members = await context.bot.get_chat_member_count(chat_id)
        except Exception as e:
            print("Could not fetch Telegram member count: %s", e)

        await record_stat_event(platform, "message", user_id, total_members=total_members)

    # ---------------------------------------------------------------
    # Commands
    # ---------------------------------------------------------------
    @app_commands.command(name="stats", description="View platform stats for a date range")
    @app_commands.describe(platform="Which platform to check", days="How many days back to include (default 7)")
    async def stats_cmd(self, interaction: discord.Interaction, platform: Literal["discord", "telegram_group", "telegram_channel"] = "discord", days: int = 7,):
        """
        /stats platform:discord days:7           -> last 7 days, summed
        /stats platform:telegram_group days:1     -> today only
        """
        is_telegram = platform.startswith("telegram")

        if is_telegram and not TG_GROUP_ID and not TG_CHAT_ID:
            await interaction.response.send_message(
                "Telegram chat IDs are not configured.", ephemeral=True
            )
            return

        if platform == "discord" and interaction.guild_id is None:
            await interaction.response.send_message(
                "This command needs to be used in a server.", ephemeral=True
            )
            return

        await interaction.response.defer()

        end_date = dt.datetime.now(dt.timezone.utc).date()
        start_date = end_date - dt.timedelta(days=days - 1)

        data = await get_stats_range(
            platform, start_date.isoformat(), end_date.isoformat()
        )

        display_name = platform.replace("_", " ").title()

        embed = discord.Embed(
            title=f"{display_name} Stats — last {days} day(s)",
            color=discord.Color.teal(),
        )
        embed.add_field(name="● Total Joined", value=data["total_joined"])
        embed.add_field(name="● Total Left", value=data["total_left"])
        embed.add_field(name="● Growth", value=data["member_growth"])
        embed.add_field(name="● Total Messages", value=data["total_messages"])
        embed.add_field(name="● Avg Daily", value=data["average_daily_messages"])
        embed.add_field(name="● Active Members", value=data["active_members"])
        embed.add_field(name="● Total Members", value=data["total_members"])
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="exportstats", description="Export platform stats as raw JSON")
    @app_commands.describe(platform="Which platform to check", days="How many days back to include (default 7)")
    async def export_stats_cmd(self, interaction: discord.Interaction, platform: Literal["discord", "telegram_group", "telegram_channel"] = "discord", days: int = 7):
        """/exportstats platform:discord days:7"""
        is_telegram = platform.startswith("telegram")

        if is_telegram and not TG_GROUP_ID and not TG_CHAT_ID:
            await interaction.response.send_message(
                "Telegram chat IDs are not configured.", ephemeral=True
            )
            return

        if platform == "discord" and interaction.guild_id is None:
            await interaction.response.send_message(
                "This command needs to be used in a server.", ephemeral=True
            )
            return

        await interaction.response.defer()

        end_date = dt.datetime.now(dt.timezone.utc).date()
        start_date = end_date - dt.timedelta(days=days - 1)

        data = await get_stats_range(
            platform, start_date.isoformat(), end_date.isoformat()
        )
        data["platform"] = platform
        data["start_date"] = start_date.isoformat()
        data["end_date"] = end_date.isoformat()

        await interaction.followup.send(f"```json\n{json.dumps(data, indent=2)}\n```")

async def setup(bot: commands.Bot):
    await bot.add_cog(StatsCog(bot))