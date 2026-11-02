import logging

import discord
from discord.ext import commands

import config
from database import setup_indexes

logging.basicConfig(
    level=logging.ERROR,
    format="%(asctime)s %(name)s: %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler("bot.log")],
)
log = logging.getLogger("bot")

# error_handler first so it is active before anything else can fail.
EXTENSIONS = [
    "Cogs.error_handler",
    "Cogs.user",       # user commands:  /profile /missions /leaderboard
    "Cogs.admin",      # admin commands: /admin ...
    "Cogs.games",      # mini-games played in channels: /coinflip
    "Cogs.xp",         # message XP
    "Cogs.x_engage",   # X (Twitter) engagement missions
    "Cogs.poll",       # poll vote mission
    "Cogs.reset",      # weekly / monthly resets
    "Cogs.stats",      # Telegram + Discord stats + tweet mirroring
]


class PandaBot(commands.Bot):
    async def setup_hook(self):
        await setup_indexes()
        for extension in EXTENSIONS:
            try:
                await self.load_extension(extension)
                print(f"SUCCESS: Extension {extension} is loaded!")
            except Exception:
                # Keep the bot up if one cog is broken, but never hide why.
                log.exception("Failed to load extension %s", extension)
                print(f"ERROR: Extension {extension} failed to load (see bot.log)")
        await self.tree.sync()

    async def on_ready(self):
        print(f"Logged in as {self.user}")


bot = PandaBot(command_prefix="^^", intents=discord.Intents.all())

if __name__ == "__main__":
    bot.run(config.BOT_TOKEN, log_handler=None)  # log_handler=None keeps the logging config above
