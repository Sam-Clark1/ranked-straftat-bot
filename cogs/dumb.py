import discord
from discord.ext import commands
import random
from command_helpers import match_to_db, get_display_name
from model_helpers import train_models
import aiosqlite

class Dumb(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def dumb(self, ctx):
        async with aiosqlite.connect("rankings.db") as db:
            dummy_authorized_id = 141371022938079233  # Replace with the authorized user's ID or role
            if ctx.author.id != dummy_authorized_id:
                await ctx.send("You are not authorized to undo matches.")
                return
            
            # Hardcoded list of player IDs (replace these with actual Discord user IDs)
            # player_ids = [1321317232797810749, 946593018226540545, 947655647955140659]
            player_ids = [141371022938079233, 946593018226540545, 947655647955140659, 1321317232797810749]

            # Randomize matches between players
            matches_to_create = 10  # Number of dummy matches to generate
            results = []

            for _ in range(matches_to_create):
                # Randomly select winner and loser
                winner_id, loser_id = random.sample(player_ids, 2)

                winner_display_name = await get_display_name(ctx, winner_id)
                loser_display_namee = await get_display_name(ctx, loser_id)

                # Generate random rounds won and lost
                winner_rounds = 10
                loser_rounds = random.randint(0, 9)
                
                try:
                    winner_sp_change, _, winner_straftcoin_change, _, _, _, loser_sp_change, _, loser_straftcoin_change, _, _, _, _, _, _ = await match_to_db(
                        winner_id, loser_id, winner_rounds, loser_rounds, db
                    )

                except Exception as e:
                    await ctx.send(f"An error occurred while recording the match: {e}")

                results.append(f"Match: Winner {winner_display_name} ({winner_rounds} rounds) (win sp chng: {winner_sp_change}) (win sc chng: {winner_straftcoin_change}) vs Loser {loser_display_namee} ({loser_rounds} rounds) (lsr sp chng: {loser_sp_change}) (lsr sc chng: {loser_straftcoin_change})")

            dummy_match_message = await ctx.send('Dummy Matches Created')

            thread = await ctx.channel.create_thread(
                name='Dummy Matches that were Created',
                message=dummy_match_message
            )

            # Send results to the Discord channel
            await thread.send("**Dummy Matches Created:**\n" + "\n".join(results))

            await train_models('spread', db)
            
async def setup(bot):
    await bot.add_cog(Dumb(bot))