import discord
from discord.ext import commands
import aiosqlite
from command_helpers import get_emoji

class Stats(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def stats(self, ctx, player: discord.Member):
        async with aiosqlite.connect("rankings.db") as db:
            player_row = await db.execute("""
                SELECT
                    rating_1v1, sp_1v1, rank_1v1,
                    wins_1v1, losses_1v1,
                    rounds_won_1v1, rounds_lost_1v1,
                    highest_rank_1v1,
                    rating_mp, sp_mp, rank_mp,
                    wins_mp, losses_mp,
                    rounds_won_mp, rounds_lost_mp,
                    highest_rank_mp,
                    straftcoins
                FROM players WHERE user_id = ?
            """, (player.id,))
            player_data = await player_row.fetchone()

            if not player_data:
                await ctx.send(f"No stats available for {player.mention}.")
                return

            (
                rating_1v1, sp_1v1, rank_1v1,
                wins_1v1, losses_1v1,
                rounds_won_1v1, rounds_lost_1v1,
                highest_rank_1v1,
                rating_mp, sp_mp, rank_mp,
                wins_mp, losses_mp,
                rounds_won_mp, rounds_lost_mp,
                highest_rank_mp,
                straftcoins
            ) = player_data

            # --- 1v1 calculations ---
            total_matches_1v1 = wins_1v1 + losses_1v1
            total_rounds_1v1  = rounds_won_1v1 + rounds_lost_1v1
            win_pct_1v1       = (wins_1v1 / total_matches_1v1 * 100) if total_matches_1v1 > 0 else 0
            round_pct_1v1     = (rounds_won_1v1 / total_rounds_1v1 * 100) if total_rounds_1v1 > 0 else 0

            # --- MP calculations ---
            total_matches_mp = wins_mp + losses_mp
            total_rounds_mp  = rounds_won_mp + rounds_lost_mp
            win_pct_mp       = (wins_mp / total_matches_mp * 100) if total_matches_mp > 0 else 0
            round_pct_mp     = (rounds_won_mp / total_rounds_mp * 100) if total_rounds_mp > 0 else 0

            emojis = await get_emoji([
                rank_1v1, highest_rank_1v1,
                rank_mp, highest_rank_mp,
                'Straftcoin'
            ])

        stats_message = await ctx.send(f"**Stats for {player.mention}**")

        thread = await ctx.channel.create_thread(
            name=f'Stats for {player.display_name}',
            message=stats_message
        )

        await thread.send(
            f"**── 1v1 ──**\n"
            f"Rank: {rank_1v1} {emojis[0]}\n"
            f"Rating: {rating_1v1:.1f} | SP: {sp_1v1}\n"
            f"Wins: {wins_1v1} | Losses: {losses_1v1} | Win Rate: {win_pct_1v1:.2f}%\n"
            f"Rounds Won: {rounds_won_1v1} | Rounds Lost: {rounds_lost_1v1} | Round Win Rate: {round_pct_1v1:.2f}%\n"
            f"Highest Rank: {highest_rank_1v1} {emojis[1]}\n"
            f"\n"
            f"**── Multiplayer ──**\n"
            f"Rank: {rank_mp} {emojis[2]}\n"
            f"Rating: {rating_mp:.1f} | SP: {sp_mp}\n"
            f"1st Place Finishes: {wins_mp} | Non-1st Finishes: {losses_mp} | 1st Place Rate: {win_pct_mp:.2f}%\n"
            f"Rounds Won: {rounds_won_mp} | Rounds Lost: {rounds_lost_mp} | Round Win Rate: {round_pct_mp:.2f}%\n"
            f"Highest Rank: {highest_rank_mp} {emojis[3]}\n"
            f"\n"
            f"**── General ──**\n"
            f"Straftcoin Balance: {straftcoins}{emojis[4]}\n"
        )

async def setup(bot):
    await bot.add_cog(Stats(bot))