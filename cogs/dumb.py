import asyncio
import os
import discord
from discord.ext import commands
import random
from dotenv import load_dotenv
from command_helpers import match_to_db, get_display_name
from model_helpers import train_models
import aiosqlite

class Dumb(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def dumb(self, ctx):
        async with aiosqlite.connect("rankings.db") as db:
            load_dotenv()
            ADMIN_ID = int(os.environ['ADMIN_ID'])
            dummy_authorized_id = ADMIN_ID

            if ctx.author.id != dummy_authorized_id:
                await ctx.send("You are not authorized to undo matches.")
                return
            
            
            DUMB_PLAYER_IDS = os.environ['DUMB_PLAYER_IDS']
            player_ids = [int(id.strip()) for id in DUMB_PLAYER_IDS.split(',')]

            # Randomize matches between players
            matches_to_create = 10 
            summaries = []

            for _ in range(matches_to_create):
                winner_id, loser_id = random.sample(player_ids, 2)

                winner_display_name = await get_display_name(ctx, winner_id)
                loser_display_name  = await get_display_name(ctx, loser_id)   # fixed typo

                winner_rounds = 10
                loser_rounds  = random.randint(0, 9)

                try:
                    match_results = await match_to_db(
                        [(winner_id, winner_rounds), (loser_id, loser_rounds)],
                        10,
                        db
                    )
                    winner_result = next(r for r in match_results if r['player_id'] == winner_id)
                    loser_result  = next(r for r in match_results if r['player_id'] == loser_id)

                    winner_sp_change         = winner_result['sp_change']
                    winner_straftcoin_change = winner_result['straftcoin_change']
                    loser_sp_change          = loser_result['sp_change']
                    loser_straftcoin_change  = loser_result['straftcoin_change']

                except Exception as e:
                    await ctx.send(f"An error occurred while recording a dummy match: {e}")
                    continue

                summaries.append(
                    f"Winner {winner_display_name} ({winner_rounds}r) "
                    f"SP: {winner_sp_change:+} SC: {winner_straftcoin_change:+} | "
                    f"Loser {loser_display_name} ({loser_rounds}r) "
                    f"SP: {loser_sp_change:+} SC: {loser_straftcoin_change:+}"
                )

            dummy_match_message = await ctx.send('Dummy Matches Created')

            thread = await ctx.channel.create_thread(
                name='Dummy Matches that were Created',
                message=dummy_match_message
            )

            await thread.send("**Dummy Matches Created:**\n" + "\n".join(summaries))

            asyncio.create_task(train_models('spread'))


async def setup(bot):
    await bot.add_cog(Dumb(bot))