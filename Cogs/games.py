# Cog: bot-vs-user mini-games. Every response is ephemeral (only the player sees their game),
# so everyone can play in the same channel.
#
#   /games                    what is available + how to play (select menu)
#   /coinflip  <side> <amt>   /diceduel <amt>   /guess <amt>   /rps <amt>
#   /blackjack <amt>          /dealerschoice <amt>             /cups <amt>
#
# All games share the same rules, defined once (see minigames/base.py + config.py):
#   bet 1..MAX_BET_PER_GAME, DAILY_BET_LIMIT per day, only XP held this month,
#   win -> +bet x multiplier, loss -> -bet (total + monthly XP), tie -> bet returned.
# To add a game: create minigames/<game>.py with a `play(interaction, amount)` (copy rps.py),
# add it to minigames/info.py GAMES, then add a command below.
import discord
from discord import app_commands
from discord.ext import commands

from config import MAX_BET_PER_GAME
from minigames import blackjack as blackjack_game
from minigames import coinflip as coinflip_game
from minigames import cups as cups_game
from minigames import dealers_choice as dealers_choice_game
from minigames import dice_duel as dice_duel_game
from minigames import guess_number as guess_game
from minigames import rps as rps_game
from minigames.info import GamesInfoView, overview_embed
from utils.checks import games_channel_only

Amount = app_commands.Range[int, 1, MAX_BET_PER_GAME]
AMOUNT_HELP = "How much XP to bet"


class GamesCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="games", description="See the mini-games you can play and how to play them.")
    async def games(self, interaction: discord.Interaction):
        view = GamesInfoView(interaction.user.id)
        await interaction.response.send_message(embed=overview_embed(), view=view, ephemeral=True)
        view.interaction = interaction

    # Checks run bottom-up: channel check first, then the per-user cooldown.
    @app_commands.command(name="coinflip", description="Bet XP on a coin flip against the bot.")
    @app_commands.describe(side="Which side do you bet on?", amount=AMOUNT_HELP)
    @app_commands.choices(side=[
        app_commands.Choice(name="Heads", value="heads"),
        app_commands.Choice(name="Tails", value="tails"),
    ])
    @app_commands.checks.cooldown(1, 5.0)
    @games_channel_only()
    async def coinflip(self, interaction: discord.Interaction, side: app_commands.Choice[str], amount: Amount):
        await coinflip_game.play(interaction, side.value, amount)

    @app_commands.command(name="diceduel", description="Bet on even, odd, or over/under the bot's target number.")
    @app_commands.describe(amount=AMOUNT_HELP)
    @app_commands.checks.cooldown(1, 5.0)
    @games_channel_only()
    async def diceduel(self, interaction: discord.Interaction, amount: Amount):
        await dice_duel_game.play(interaction, amount)

    @app_commands.command(name="guess", description="Guess the bot's secret number (1-100) in 5 tries.")
    @app_commands.describe(amount=AMOUNT_HELP)
    @app_commands.checks.cooldown(1, 5.0)
    @games_channel_only()
    async def guess(self, interaction: discord.Interaction, amount: Amount):
        await guess_game.play(interaction, amount)

    @app_commands.command(name="rps", description="Play rock paper scissors against the bot.")
    @app_commands.describe(amount=AMOUNT_HELP)
    @app_commands.checks.cooldown(1, 5.0)
    @games_channel_only()
    async def rps(self, interaction: discord.Interaction, amount: Amount):
        await rps_game.play(interaction, amount)

    @app_commands.command(name="blackjack", description="Beat the dealer to 21.")
    @app_commands.describe(amount=AMOUNT_HELP)
    @app_commands.checks.cooldown(1, 5.0)
    @games_channel_only()
    async def blackjack(self, interaction: discord.Interaction, amount: Amount):
        await blackjack_game.play(interaction, amount)

    @app_commands.command(name="dealerschoice", description="Pick a face-down card that beats the dealer's card.")
    @app_commands.describe(amount=AMOUNT_HELP)
    @app_commands.checks.cooldown(1, 5.0)
    @games_channel_only()
    async def dealerschoice(self, interaction: discord.Interaction, amount: Amount):
        await dealers_choice_game.play(interaction, amount)

    @app_commands.command(name="cups", description="Find the diamond hidden under one of 5 cups.")
    @app_commands.describe(amount=AMOUNT_HELP)
    @app_commands.checks.cooldown(1, 5.0)
    @games_channel_only()
    async def cups(self, interaction: discord.Interaction, amount: Amount):
        await cups_game.play(interaction, amount)


async def setup(bot: commands.Bot):
    await bot.add_cog(GamesCog(bot))
