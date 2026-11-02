# Cog: EVERYTHING that touches Telegram + community statistics, in one place.
#
#   1. Telegram tracking  - member joins/leaves + messages for the two Telegram chats
#   2. Discord tracking   - member joins/leaves + messages
#   3. Tweet mirroring    - new tweet links posted by bots in TWEET_CHANNEL_ID -> Telegram
#   4. Admin commands     - /stats and /exportstats
#
# (Replaces tg_auto.py and the tweet-forwarding code that used to live in xp.py.)
import datetime as dt
import json
import re
from typing import Literal, Optional

import discord
from cachetools import TTLCache
from discord import app_commands
from discord.ext import commands
from telegram import (
    InlineKeyboardButton, InlineKeyboardMarkup, LinkPreviewOptions, Update,
)
from telegram.ext import (
    Application, ApplicationBuilder, ChatMemberHandler, ContextTypes, MessageHandler, filters,
)

from config import TG_BOT_TOKEN, TG_CHAT_ID, TG_GROUP_ID, TWEET_CHANNEL_ID
from database import get_stats_range, record_stat_event
from utils.checks import admin_only
from utils.errors import report_task_error

URL_RE = re.compile(r"https?://[^\s<>]+")
X_HOST_RE = re.compile(r"^https?://(?:www\.)?x\.com/", re.IGNORECASE)

# Platform names stored in the database (unchanged from the old stats cog).
PLATFORM_DISCORD = "discord"
PLATFORM_TG_GROUP = "telegram_group"      # TG_CHAT_ID  (community chat)
PLATFORM_TG_CHANNEL = "telegram_channel"  # TG_GROUP_ID (casino channel)
PlatformName = Literal["discord", "telegram_group", "telegram_channel"]


class StatsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.telegram_app: Optional[Application] = None
        # Member counts change slowly: cache them instead of one API call per message.
        self._member_counts: TTLCache = TTLCache(maxsize=8, ttl=600)

    # ══════════════════════════════════════════════════════════════════════
    # Lifecycle
    # ══════════════════════════════════════════════════════════════════════
    async def cog_load(self):
        if not TG_BOT_TOKEN:
            print("StatsCog: TG_BOT_TOKEN not set - Telegram features disabled.")
            return

        app = ApplicationBuilder().token(TG_BOT_TOKEN).build()
        app.add_handler(ChatMemberHandler(self._on_tg_chat_member, ChatMemberHandler.CHAT_MEMBER))
        # NOTE: a bare filters.ALL also matches *edited* messages, which would
        # inflate message counts. Only count brand-new messages / channel posts.
        new_posts = filters.UpdateType.MESSAGE | filters.UpdateType.CHANNEL_POST
        app.add_handler(MessageHandler(new_posts & ~filters.StatusUpdate.ALL, self._on_tg_message))
        app.add_error_handler(self._on_tg_error)

        # Start polling without run_polling() so we share the Discord bot's event loop.
        await app.initialize()
        await app.start()
        # chat_member updates are NOT sent unless explicitly requested.
        await app.updater.start_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)
        self.telegram_app = app
        print("StatsCog: Telegram polling started.")

    async def cog_unload(self):
        app, self.telegram_app = self.telegram_app, None
        if app is None:
            return
        await app.updater.stop()
        await app.stop()
        await app.shutdown()
        print("StatsCog: Telegram stopped cleanly.")

    # ══════════════════════════════════════════════════════════════════════
    # Telegram: tracking
    # ══════════════════════════════════════════════════════════════════════
    @staticmethod
    def _tg_platform(chat_id: int) -> Optional[str]:
        if str(chat_id) == str(TG_GROUP_ID):
            return PLATFORM_TG_CHANNEL
        if str(chat_id) == str(TG_CHAT_ID):
            return PLATFORM_TG_GROUP
        return None

    async def _tg_member_count(self, bot, chat_id: int, *, refresh: bool = False) -> Optional[int]:
        if not refresh and chat_id in self._member_counts:
            return self._member_counts[chat_id]
        try:
            count = await bot.get_chat_member_count(chat_id)
        except Exception as exc:  # a missing count must never lose the event itself
            print(f"StatsCog: could not fetch Telegram member count for {chat_id}: {exc}")
            return self._member_counts.get(chat_id)
        self._member_counts[chat_id] = count
        return count

    @staticmethod
    def _is_in_chat(member) -> bool:
        """True if a telegram.ChatMember is currently inside the chat."""
        if member.status in ("member", "administrator", "creator"):
            return True
        return member.status == "restricted" and bool(member.is_member)

    async def _on_tg_chat_member(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        change = update.chat_member
        platform = self._tg_platform(update.effective_chat.id)
        if platform is None or change is None or change.new_chat_member.user.is_bot:
            return

        was_in, is_in = self._is_in_chat(change.old_chat_member), self._is_in_chat(change.new_chat_member)
        if was_in == is_in:
            return  # promotion / restriction change, not a join or leave

        total = await self._tg_member_count(context.bot, update.effective_chat.id, refresh=True)
        await record_stat_event(platform, "join" if is_in else "leave",
                                change.new_chat_member.user.id, total_members=total)

    async def _on_tg_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        message, chat = update.effective_message, update.effective_chat
        platform = self._tg_platform(chat.id) if chat else None
        if message is None or platform is None:
            return
        if update.effective_user and update.effective_user.is_bot:
            return

        # Channel posts have no user; attribute them to the channel itself.
        user_id = update.effective_user.id if update.effective_user else f"channel:{chat.id}"
        total = await self._tg_member_count(context.bot, chat.id)
        await record_stat_event(platform, "message", user_id, total_members=total)

    async def _on_tg_error(self, update: object, context: ContextTypes.DEFAULT_TYPE):
        await report_task_error(self.bot, context.error, "telegram handler")

    # ══════════════════════════════════════════════════════════════════════
    # Discord: tracking + tweet mirroring
    # ══════════════════════════════════════════════════════════════════════
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        await record_stat_event(PLATFORM_DISCORD, "join", member.id, total_members=member.guild.member_count)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        await record_stat_event(PLATFORM_DISCORD, "leave", member.id, total_members=member.guild.member_count)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild:
            return

        # Every message counts for Discord stats - bots included.
        await record_stat_event(PLATFORM_DISCORD, "message", message.author.id,
                                total_members=message.guild.member_count)

        # Tweet bot posted a link -> mirror it to Telegram.
        if message.author.bot and message.channel.id == TWEET_CHANNEL_ID:
            await self._forward_tweet(message)

    @staticmethod
    def _find_link(message: discord.Message) -> Optional[str]:
        """First URL in the message text, falling back to its embeds."""
        candidates = [message.content, *(e.url or "" for e in message.embeds)]
        for text in candidates:
            match = URL_RE.search(text or "")
            if match:
                return match.group(0)
        return None

    async def _forward_tweet(self, message: discord.Message):
        if self.telegram_app is None:
            return
        link = self._find_link(message)
        if link is None:
            return
        # twitter.com links give Telegram a better preview than x.com
        link = X_HOST_RE.sub("https://twitter.com/", link)

        await self.telegram_app.bot.send_message(
            chat_id=TG_CHAT_ID,
            text=f"🔥 New Tweet Alert Panda's 🐼\n\n{link}",
            link_preview_options=LinkPreviewOptions(
                is_disabled=False, prefer_large_media=True, show_above_text=False),
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("View Tweet 𝕏", url=link)]]),
        )

    # ══════════════════════════════════════════════════════════════════════
    # Admin commands
    # ══════════════════════════════════════════════════════════════════════
    @staticmethod
    async def _range_stats(platform: str, days: int) -> dict:
        end = dt.datetime.now(dt.timezone.utc).date()
        start = end - dt.timedelta(days=days - 1)
        return await get_stats_range(platform, start.isoformat(), end.isoformat())

    @app_commands.command(name="stats", description="View platform stats for a date range (admins).")
    @app_commands.describe(platform="Which platform to check", days="How many days back to include (default 7)")
    @admin_only()
    async def stats_cmd(self, interaction: discord.Interaction,
                        platform: PlatformName = "discord",
                        days: app_commands.Range[int, 1, 365] = 7):
        await interaction.response.defer()
        data = await self._range_stats(platform, days)

        embed = discord.Embed(
            title=f"{platform.replace('_', ' ').title()} Stats — last {days} day(s)",
            color=discord.Color.teal())
        for name, key in (("Total Joined", "total_joined"), ("Total Left", "total_left"),
                          ("Growth", "member_growth"), ("Total Messages", "total_messages"),
                          ("Avg Daily", "average_daily_messages"), ("Active Members", "active_members"),
                          ("Total Members", "total_members")):
            value = data[key]
            embed.add_field(name=f"● {name}", value="N/A" if value is None else str(value))
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="exportstats", description="Export platform stats as raw JSON (admins).")
    @app_commands.describe(platform="Which platform to check", days="How many days back to include (default 7)")
    @admin_only()
    async def export_stats_cmd(self, interaction: discord.Interaction,
                               platform: PlatformName = "discord",
                               days: app_commands.Range[int, 1, 365] = 7):
        await interaction.response.defer()
        data = await self._range_stats(platform, days)
        await interaction.followup.send(f"```json\n{json.dumps(data, indent=2)}\n```")


async def setup(bot: commands.Bot):
    await bot.add_cog(StatsCog(bot))
