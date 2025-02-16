import discord
from discord.ext import commands
from command_helpers import match_to_db
from bet_helpers import handle_bet_payouts
from model_helpers import train_models
import aiosqlite

class Record(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    # Record a match result
    @commands.command()
    async def record(self, ctx, winner: discord.Member, loser: discord.Member, winner_rounds: int, loser_rounds: int):
        async with aiosqlite.connect("rankings.db") as db:
            if winner_rounds != 10 or loser_rounds >= 10:
                await ctx.send("Invalid input: Matches end when one player wins exactly 10 rounds.")
                return

            if winner.id == loser.id:
                await ctx.send("Invalid input dumbass: Cannot record a match against yourself.")
                return    

            # try:
            winner_sp_change, winner_new_sp, winner_straftcoin_change, winner_new_straftcoins, winner_rank, winner_emoji, loser_sp_change, loser_new_sp, loser_straftcoin_change, loser_new_straftcoins, loser_rank, loser_emoji, spread, total_rounds, match_id = await match_to_db(
                winner.id, loser.id, winner_rounds, loser_rounds, db
            )
            message = await ctx.send(f"Match recorded:\n"
                            f"**Winner:** {winner.mention} \n"
                            f"- SP Gained: +{winner_sp_change}\n"
                            f"- Total SP: {winner_new_sp}\n"
                            f"- Rank: **{winner_rank}** {winner_emoji}\n"
                            f"- Straftcoin Gained: +{winner_straftcoin_change}\n"
                            f"- Total Straftcoin: {winner_new_straftcoins}\n"
                            f"**Loser:** {loser.mention} \n"
                            f"- SP Lost: -{loser_sp_change}\n"
                            f"- Total SP: {loser_new_sp}\n"
                            f"- Rank: **{loser_rank}** {loser_emoji}\n"
                            f"- Straftcoin Gained: +{loser_straftcoin_change}\n"
                            f"- Total Straftcoin: {loser_new_straftcoins}"
                            )

            bet_settlements_message = await handle_bet_payouts(match_id, winner.display_name, loser.display_name, winner.id, spread, total_rounds, db)
            
            if bet_settlements_message:
                
                thread = await ctx.channel.create_thread(
                    name=f'Resolved Bets for {winner.display_name} vs. {loser.display_name}',
                    message=message
                )

                await thread.send(f'**Spread**: {spread}\n**Total Rounds**: {total_rounds}')    

                await thread.send(bet_settlements_message)

            await train_models('spread', db)
            # await train_models('total_rounds', db)

            # except Exception as e:
            #     await ctx.send(f"An error occurred while recording the match: {e}")

async def setup(bot):
    await bot.add_cog(Record(bot))