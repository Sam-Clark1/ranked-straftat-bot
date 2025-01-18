import discord
from discord.ext import commands
from command_helpers import get_emoji

class Help(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # Help command
    @commands.command()
    async def help(self, ctx):
        emojis = await get_emoji(['Straftcoin'])

        help_message_str = f"""
    1. **!record <winner> <loser> <winner_rounds> <loser_rounds>**
    - Records the result of a match.
    - Example: `!record @Player1 @Player2 10 6`
    - Note: Matches must end with one player winning exactly 10 rounds.

    2. **!stats <player>**
    - Shows the statistics for a specific player.
    - Example: `!stats @Player1`

    3. **!lb**
    - Displays the leaderboard sorted by SP in descending order.
    - Shows player name, rank, and SP.
    - Example: `!lb`

    4. **!matchstats <player>**
    - Shows match history stats for a specific player.
    - Example: `!matchstats @Player1`

    5. **!bet <player1> <player2>**
    - Shows odds for the Spread, Moneyline, and Over/Under for these two players against each other.
    - Allows you to bet on those odds with Straftcoin{emojis[0]} during a 5 minute period.
    - Once time is up, bets will be locked in and no more bets can be made on that matchup till it is played and recorded. 
    - Example: `!bet @Player1 @Player2`

    6. **!help**
    - Displays this help message.
    - Example: `!help`
    """
        help_message = await ctx.send('**Available Commands**')
        
        thread = await ctx.channel.create_thread(
            name=f'Available Commands for Ranked Straftat Bot',
            message=help_message
        )

        await thread.send(help_message_str)

async def setup(bot):
    await bot.add_cog(Help(bot))