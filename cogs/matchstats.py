import discord
from discord.ext import commands
import aiosqlite
from command_helpers import get_display_name

class Matchstats(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def matchstats(self, ctx, player: discord.Member):
        async with aiosqlite.connect("rankings.db") as db:

            # Query match stats against each opponent
            async with db.execute("""
                SELECT 
                    CASE WHEN winner_id = ? THEN loser_id ELSE winner_id END AS opponent_id,
                    SUM(CASE WHEN winner_id = ? THEN 1 ELSE 0 END) AS wins_against,
                    SUM(CASE WHEN loser_id = ? THEN 1 ELSE 0 END) AS losses_against,
                    SUM(CASE WHEN winner_id = ? THEN winner_rounds ELSE loser_rounds END) AS rounds_won_against,
                    SUM(CASE WHEN winner_id = ? THEN loser_rounds ELSE winner_rounds END) AS rounds_lost_against
                FROM matches
                WHERE winner_id = ? OR loser_id = ?
                GROUP BY opponent_id
            """, (player.id, player.id, player.id, player.id, player.id, player.id, player.id)) as cursor:
                rows = await cursor.fetchall()

        if not rows:
            await ctx.send(f"No match stats found for {player.mention}.")
            return

        stats_message = await ctx.send(f"**Match Stats for {player.mention}**")

        thread = await ctx.channel.create_thread(
            name=f'Match Stats for {player.display_name}',
            message=stats_message
        )

        stats_message_body= ''

        for row in rows:
            opponent_id, wins, losses, rounds_won, rounds_lost = row
            opponent_name = await get_display_name(ctx, opponent_id)

            # Calculate percentages
            total_matches = wins + losses
            total_rounds = rounds_won + rounds_lost
            win_percentage = (wins / total_matches) * 100 if total_matches > 0 else 0
            round_percentage = (rounds_won / total_rounds) * 100 if total_rounds > 0 else 0

            stats_message_body += f"""
Opponent: **{opponent_name}**
Matches Played: {total_matches}
Wins: {wins}
Losses: {losses}
Win Percentage: {win_percentage:.2f}%
Rounds Won: {rounds_won}
Rounds Lost: {rounds_lost}
Rounds Won Percentage: {round_percentage:.2f}%
"""
        await thread.send(stats_message_body)

async def setup(bot):
    await bot.add_cog(Matchstats(bot))