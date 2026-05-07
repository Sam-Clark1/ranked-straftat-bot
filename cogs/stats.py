import discord
from discord.ext import commands
import aiosqlite
from command_helpers import get_emoji

_PALE_GREEN = discord.Color(0x90ee90)

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

            total_matches_1v1 = wins_1v1 + losses_1v1
            total_rounds_1v1  = rounds_won_1v1 + rounds_lost_1v1
            win_pct_1v1       = (wins_1v1 / total_matches_1v1 * 100) if total_matches_1v1 > 0 else 0
            round_pct_1v1     = (rounds_won_1v1 / total_rounds_1v1 * 100) if total_rounds_1v1 > 0 else 0

            total_matches_mp = wins_mp + losses_mp
            total_rounds_mp  = rounds_won_mp + rounds_lost_mp
            win_pct_mp       = (wins_mp / total_matches_mp * 100) if total_matches_mp > 0 else 0
            round_pct_mp     = (rounds_won_mp / total_rounds_mp * 100) if total_rounds_mp > 0 else 0

            emojis = await get_emoji([
                rank_1v1, highest_rank_1v1,
                rank_mp, highest_rank_mp,
                'Straftcoin'
            ])

        embed = discord.Embed(title=f'Stats — {player.display_name}', color=_PALE_GREEN)
        embed.set_thumbnail(url=player.display_avatar.url)

        embed.add_field(
            name=f'1v1 · {rank_1v1} {emojis[0]}',
            value=(
                f"SP: **{sp_1v1}** · Elo: {rating_1v1:.0f}\n"
                f"W/L: {wins_1v1}/{losses_1v1} ({win_pct_1v1:.1f}%)\n"
                f"Rounds: {rounds_won_1v1}/{rounds_lost_1v1} ({round_pct_1v1:.1f}%)\n"
                f"Peak: {highest_rank_1v1} {emojis[1]}"
            ),
            inline=True
        )

        embed.add_field(
            name=f'Multiplayer · {rank_mp} {emojis[2]}',
            value=(
                f"SP: **{sp_mp}** · Elo: {rating_mp:.0f}\n"
                f"1st/Other: {wins_mp}/{losses_mp} ({win_pct_mp:.1f}%)\n"
                f"Rounds: {rounds_won_mp}/{rounds_lost_mp} ({round_pct_mp:.1f}%)\n"
                f"Peak: {highest_rank_mp} {emojis[3]}"
            ),
            inline=True
        )

        embed.add_field(
            name='Straftcoins',
            value=f'**{straftcoins}** {emojis[4]}',
            inline=False
        )

        stats_message = await ctx.send(f"**Stats for {player.mention}**")
        thread = await ctx.channel.create_thread(
            name=f'Stats for {player.display_name}',
            message=stats_message
        )
        await thread.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Stats(bot))
