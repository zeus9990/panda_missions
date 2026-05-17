import discord, config
import logging
from discord import app_commands
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
    "Cogs.xp"
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

@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    original = getattr(error, "original", error)
    
    if isinstance(original, discord.NotFound) and original.code == 10062:
        return  # silently ignore expired interactions

    logging.getLogger(__name__).error("App command error: %s", error, exc_info=True)

bot.run(config.BOT_TOKEN)