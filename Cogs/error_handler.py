# Cogs/error_handler.py
import discord
from discord import app_commands
from discord.ext import commands
import logging

logger = logging.getLogger(__name__)

class ErrorHandlerCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        bot.tree.on_error = self.on_app_command_error

    async def on_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        original = getattr(error, "original", error)

        if isinstance(original, discord.NotFound) and original.code == 10062:
            return

        if isinstance(original, discord.Forbidden):
            await self._safe_send(interaction, "❌ I don't have permission to do that.")
            return

        command_name = interaction.command.name if interaction.command else "Unknown"
        logger.error(
            "Unhandled error in command '%s' by user %s: %s",
            command_name, interaction.user.id, original, exc_info=True
        )
        await self._safe_send(interaction, "❌ Something went wrong.")

    async def _safe_send(self, interaction: discord.Interaction, message: str):
        try:
            if interaction.response.is_done():
                await interaction.followup.send(message, ephemeral=True)
            else:
                await interaction.response.send_message(message, ephemeral=True)
        except discord.NotFound:
            pass


async def setup(bot):
    await bot.add_cog(ErrorHandlerCog(bot))