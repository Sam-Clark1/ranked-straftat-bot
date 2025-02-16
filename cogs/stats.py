import discord
from discord.ext import commands
import aiosqlite
from command_helpers import get_emoji

class Stats(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # Show player stats
    @commands.command()
    async def stats(self, ctx, player: discord.Member):
        async with aiosqlite.connect("rankings.db") as db:
            player_row = await db.execute("""
                SELECT rating, sp, rank, wins, losses, rounds_won, rounds_lost, straftcoins, highest_rank_achieved, highest_sp_achieved FROM players WHERE user_id = ?
            """, (player.id,))
            player_data = await player_row.fetchone()
            
            if not player_data:
                await ctx.send(f"No stats available for {player.mention}.")
                return

            rating, sp, rank, wins, losses, rounds_won, rounds_lost, straftcoins, highest_rank_achieved, highest_sp_achieved = player_data
            total_matches = wins + losses
            total_rounds = rounds_won + rounds_lost
            match_win_percentage = (wins / total_matches) * 100 if total_matches > 0 else 0
            round_win_percentage = (rounds_won / total_rounds * 100) if total_rounds > 0 else 0
            emojis = await get_emoji([rank, 'Straftcoin', highest_rank_achieved])
            
        
        stats_message = await ctx.send(f"**Stats for {player.mention}**")

        thread = await ctx.channel.create_thread(
            name=f'Stats for {player.display_name}',
            message=stats_message
        )

        await thread.send(
            f"Rank: {rank} {emojis[0]}\nRating: {rating}\nSP: {sp}\n"
            f"Match Wins: {wins}\nMatch Losses: {losses}\n"
            f"Match Win Percentage: {match_win_percentage:.2f}%\n"
            f"Rounds Won: {rounds_won}\nRounds Lost: {rounds_lost}\n"
            f"Round Win Percentage: {round_win_percentage:.2f}%\n"
            f"Straftcoin Balance: {straftcoins}{emojis[1]}\n"
            f"Highest Rank Achieved: {highest_rank_achieved}{emojis[2]}\n"
            f"Highest SP Achieved: {highest_sp_achieved}\n"
        )

async def setup(bot):
    await bot.add_cog(Stats(bot))