import discord, config
import logging
from discord.ext import commands
from database import setup_indexes

logging.basicConfig(
    level=logging.ERROR,
    format="%(asctime)s %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("bot.log"),
    ]
)

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="^^", intents=intents)

initial_extensions = [
    "Cogs.admin",
    "Cogs.missions",
    "Cogs.reset",
    "Cogs.user",
    "Cogs.xp",
    "Cogs.error_handler",
    "Cogs.x_engage",
    "Cogs.poll"
]

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

@bot.event
async def setup_hook():
    await setup_indexes()
    for extension in initial_extensions:
        try:
            await bot.load_extension(extension)
            print(f'SUCCESS: Extension {extension} is loaded!')
        except Exception as e:
            print(f'ERROR: {e}')
    await bot.tree.sync()

bot.run(config.BOT_TOKEN)