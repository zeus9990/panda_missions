# Cog: ONE central place for every error the bot can raise.
#
# Covers three sources of errors:
#   1. slash commands          -> bot.tree.on_error
#   2. prefix commands (^^)    -> on_command_error
#   3. event listeners/tasks   -> bot.on_error   (on_message, on_member_join, ...)
#
# Expected problems (missing role, bad cooldown, ...) get a friendly message.
# Anything else is a bug: it gets a short ERROR ID, the full traceback is written
# to bot.log and posted to the staff log channel, and the user is shown the ID.
# To find a bug: copy the ID from the user's message -> search bot.log / staff channel.
import logging
import sys
import traceback
import uuid
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from config import LOG_CHANNEL_ID
from utils.checks import WrongChannel

log = logging.getLogger("bot.errors")


def unwrap(error: BaseException) -> BaseException:
    """Strip discord.py's CommandInvokeError wrappers to get the real exception."""
    while isinstance(error, (app_commands.CommandInvokeError, commands.CommandInvokeError)):
        error = error.original
    return error


def friendly_message(error: BaseException) -> Optional[str]:
    """User-facing text for EXPECTED errors; None means 'this is a bug'."""
    # Permissions / checks (order matters: specific before general)
    if isinstance(error, (app_commands.MissingAnyRole, app_commands.MissingRole,
                          commands.MissingAnyRole, commands.MissingRole)):
        return "❌ You don't have the required role to use this command."
    if isinstance(error, (app_commands.MissingPermissions, commands.MissingPermissions)):
        perms = ", ".join(p.replace("_", " ").title() for p in error.missing_permissions)
        return f"❌ You need these permissions: **{perms}**."
    if isinstance(error, (app_commands.BotMissingPermissions, commands.BotMissingPermissions)):
        perms = ", ".join(p.replace("_", " ").title() for p in error.missing_permissions)
        return f"❌ I'm missing these permissions: **{perms}**."
    if isinstance(error, (app_commands.NoPrivateMessage, commands.NoPrivateMessage)):
        return "❌ This command can only be used inside the server."
    if isinstance(error, (app_commands.CommandOnCooldown, commands.CommandOnCooldown)):
        return f"⏳ Slow down! Try again in **{error.retry_after:.1f}s**."
    if isinstance(error, WrongChannel):
        where = ", ".join(f"<#{c}>" for c in error.channel_ids)
        return f"🎲 Games can only be played in {where}."
    if isinstance(error, (app_commands.CheckFailure, commands.CheckFailure)):
        return "❌ You can't use this command here."

    # Bad input
    if isinstance(error, app_commands.TransformerError):
        return f"❌ Invalid value for `{error.value}`."
    if isinstance(error, commands.MissingRequiredArgument):
        return f"❌ Missing argument: `{error.param.name}`."
    if isinstance(error, commands.UserInputError):
        return f"❌ {error}"
    if isinstance(error, app_commands.CommandNotFound):
        return "❌ That command is out of date. Please try again in a minute."

    # Discord API problems that are not our bug
    if isinstance(error, discord.Forbidden):
        return "❌ I don't have permission to do that."
    return None


class ErrorHandlerCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._old_tree_on_error = None
        self._old_bot_on_error = None

    # ── install / uninstall hooks (restored on unload so reloads are clean) ──
    async def cog_load(self):
        self._old_tree_on_error = self.bot.tree.on_error
        self._old_bot_on_error = self.bot.on_error
        self.bot.tree.on_error = self.on_app_command_error
        self.bot.on_error = self.on_event_error

    async def cog_unload(self):
        self.bot.tree.on_error = self._old_tree_on_error
        self.bot.on_error = self._old_bot_on_error

    # ── 1. slash commands ───────────────────────────────────────────────────
    async def on_app_command_error(self, interaction: discord.Interaction,
                                   error: app_commands.AppCommandError):
        original = unwrap(error)

        # Interaction expired / already answered: nothing the user can still see.
        if isinstance(original, discord.NotFound) and original.code in (10062, 10015):
            return

        text = friendly_message(original)
        if text is None:
            command = interaction.command.qualified_name if interaction.command else "unknown"
            error_id = await self.report(
                original, where=f"/{command}", user=interaction.user,
                guild=interaction.guild, channel=interaction.channel)
            text = f"⚠️ Something went wrong. Error ID: `{error_id}`"
        await self._reply(interaction, text)

    @staticmethod
    async def _reply(interaction: discord.Interaction, text: str):
        try:
            if interaction.response.is_done():
                await interaction.followup.send(text, ephemeral=True)
            else:
                await interaction.response.send_message(text, ephemeral=True)
        except discord.HTTPException:
            log.warning("Could not deliver error message to user %s.", interaction.user.id)

    # ── 2. prefix commands ──────────────────────────────────────────────────
    @commands.Cog.listener()
    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError):
        if isinstance(error, commands.CommandNotFound):
            return
        # Let commands/cogs that define their own handler keep working.
        if ctx.command and ctx.command.has_error_handler():
            return
        if ctx.cog and ctx.cog.has_error_handler():
            return

        original = unwrap(error)
        text = friendly_message(original)
        if text is None:
            error_id = await self.report(
                original, where=f"{ctx.prefix}{ctx.command}", user=ctx.author,
                guild=ctx.guild, channel=ctx.channel)
            text = f"⚠️ Something went wrong. Error ID: `{error_id}`"
        try:
            await ctx.reply(text, mention_author=False)
        except discord.HTTPException:
            pass

    # ── 3. event listeners (on_message, on_member_join, ...) ────────────────
    async def on_event_error(self, event_method: str, *args, **kwargs):
        error = sys.exc_info()[1]  # still set: discord.py calls this inside `except`
        if error is None:
            return
        await self.report(error, where=f"event {event_method}")

    # ── shared reporting ────────────────────────────────────────────────────
    async def report(
        self, error: BaseException, *, where: str,
        user: Optional[discord.abc.User] = None,
        guild: Optional[discord.Guild] = None,
        channel: Optional[discord.abc.Messageable] = None,
    ) -> str:
        """Log an unexpected error everywhere and return its short ERROR ID."""
        error_id = uuid.uuid4().hex[:8].upper()
        tb = "".join(traceback.format_exception(type(error), error, error.__traceback__))
        log.error("[%s] Unhandled error in %s (user=%s guild=%s)\n%s",
                  error_id, where, getattr(user, "id", None), getattr(guild, "id", None), tb)

        embed = discord.Embed(
            title=f"🚨 Error `{error_id}`",
            description=f"```py\n{tb[-3400:].replace('```', 'ʼʼʼ')}\n```",
            color=discord.Color.red(), timestamp=discord.utils.utcnow())
        embed.add_field(name="Where", value=where[:1000], inline=False)
        embed.add_field(name="Type", value=f"`{type(error).__name__}`", inline=True)
        if user:
            embed.add_field(name="User", value=f"{user} (`{user.id}`)", inline=True)
        if channel is not None and getattr(channel, "id", None):
            embed.add_field(name="Channel", value=f"<#{channel.id}>", inline=True)

        staff = self.bot.get_channel(LOG_CHANNEL_ID)
        if staff is not None:
            try:
                await staff.send(embed=embed)
            except discord.HTTPException:
                log.warning("Could not post error %s to the staff channel.", error_id)
        return error_id


async def setup(bot: commands.Bot):
    await bot.add_cog(ErrorHandlerCog(bot))
