import discord
from discord.ext import commands
from command_helpers import get_emoji

class Help(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def help(self, ctx):
        emojis = await get_emoji(['Straftcoin'])

        help_message_str = f"""
1. **!record <rounds_to_win> <@Player> <rounds> <@Player> <rounds> ...**
   - Records the result of a match (1v1 or up to 10 players).
   - Exactly one player must have `rounds_to_win` rounds.
   - 1v1 example: `!record 10 @Player1 10 @Player2 6`
   - MP example: `!record 10 @Player1 10 @Player2 7 @Player3 4`

2. **!stats <@player>**
   - Shows 1v1 and Multiplayer stats for a player separately.
   - Example: `!stats @Player1`

3. **!lb**
   - Displays the 1v1 leaderboard sorted by SP.
   - Example: `!lb`

4. **!mlb**
   - Displays the Multiplayer leaderboard sorted by SP.
   - Example: `!mlb`

5. **!matchstats <@player>**
   - Shows head-to-head history against each opponent.
   - Example: `!matchstats @Player1`

6. **!bet <rounds_to_win> <@Player1> <@Player2> ...**
   - Opens a 2-minute betting window for an upcoming match.
   - Generates odds for Moneyline, Spread (1v1), Head-to-Head, Podium, Last Place, and O/U bets based on player count.
   - **Single bet**: type the bet label and stake — e.g. `A 100`
   - **Parlay**: type P, the labels, then the stake — e.g. `P A C 100`
   - Players in the match can only bet on their own positive outcomes.
   - Everyone starts with 1000 {emojis[0]} if they have no account.
   - Example: `!bet 10 @Player1 @Player2`

7. **!slb**
   - Displays the Straftcoin leaderboard.
   - Example: `!slb`

8. **!help**
   - Displays this help message.
   - Example: `!help`
"""
        help_message = await ctx.send('**Available Commands**')

        thread = await ctx.channel.create_thread(
            name='Available Commands for Ranked Straftat Bot',
            message=help_message
        )

        await thread.send(help_message_str)


async def setup(bot):
    await bot.add_cog(Help(bot))