"""Report errors from background tasks and UI views through the central error handler."""
import logging
import uuid

from discord.ext import commands

log = logging.getLogger("bot.errors")


async def report_task_error(bot: commands.Bot, error: BaseException, where: str, **context) -> str:
    """Gives the error an ID, logs the traceback and posts it to the staff channel.

    `context` may hold user=, guild=, channel= for the staff embed. Returns the error ID.
    """
    cog = bot.get_cog("ErrorHandlerCog")
    if cog is not None:
        return await cog.report(error, where=where, **context)
    error_id = uuid.uuid4().hex[:8].upper()  # error handler cog not loaded
    log.error("[%s] Unhandled error in %s", error_id, where, exc_info=error)
    return error_id
