import discord
from discord.ext import commands
import aiosqlite
from helpers.command_helpers import get_emoji, sc_fmt

_PALE_GREEN = discord.Color(0x90ee90)
_PLACE_EMOJI = {1: '🥇', 2: '🥈', 3: '🥉'}

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

            # MP placement distribution
            async with db.execute("""
                SELECT mp.placement, COUNT(*) AS cnt
                FROM match_participants mp
                JOIN matches m ON mp.match_id = m.match_id
                WHERE mp.player_id = ? AND m.game_mode != '1v1'
                GROUP BY mp.placement
                ORDER BY mp.placement
            """, (player.id,)) as cursor:
                placement_rows = await cursor.fetchall()

            emojis = await get_emoji([
                rank_1v1, highest_rank_1v1,
                rank_mp,  highest_rank_mp,
                'Straftcoin'
            ])

        # 1v1 calculations
        total_matches_1v1 = wins_1v1 + losses_1v1
        total_rounds_1v1  = rounds_won_1v1 + rounds_lost_1v1
        win_pct_1v1   = (wins_1v1 / total_matches_1v1 * 100)   if total_matches_1v1 > 0 else 0
        round_pct_1v1 = (rounds_won_1v1 / total_rounds_1v1 * 100) if total_rounds_1v1 > 0 else 0

        # MP calculations 
        total_matches_mp = wins_mp + losses_mp
        total_rounds_mp  = rounds_won_mp + rounds_lost_mp
        win_pct_mp   = (wins_mp / total_matches_mp * 100)   if total_matches_mp > 0 else 0
        round_pct_mp = (rounds_won_mp / total_rounds_mp * 100) if total_rounds_mp > 0 else 0

        # Placement distribution string  e.g.  🥇 5  🥈 3  🥉 2  4th: 4
        place_parts = []
        for placement, cnt in placement_rows:
            label = _PLACE_EMOJI.get(placement, f'{placement}th:')
            place_parts.append(f'{label} {cnt}')
        placement_str = '  '.join(place_parts) if place_parts else '—'

        # Build embed 
        embed = discord.Embed(title=f'Stats — {player.display_name}', color=_PALE_GREEN)
        embed.set_thumbnail(url=player.display_avatar.url)

        embed.add_field(
            name=f'1v1 · {rank_1v1} {emojis[0]}',
            value=(
                f"Games: **{total_matches_1v1}**\n"
                f"SP: **{sp_1v1}**\n"
                f"W/L: {wins_1v1}/{losses_1v1} ({win_pct_1v1:.1f}%)\n"
                f"Rounds: {rounds_won_1v1}/{rounds_lost_1v1} ({round_pct_1v1:.1f}%)\n"
                f"Peak: {highest_rank_1v1} {emojis[1]}"
            ),
            inline=True
        )

        embed.add_field(
            name=f'Multiplayer · {rank_mp} {emojis[2]}',
            value=(
                f"Games: **{total_matches_mp}**\n"
                f"SP: **{sp_mp}**\n"
                f"Wins: {wins_mp}/{total_matches_mp} ({win_pct_mp:.1f}%)\n"
                f"Rounds: {rounds_won_mp}/{rounds_lost_mp} ({round_pct_mp:.1f}%)\n"
                f"Peak: {highest_rank_mp} {emojis[3]}"
            ),
            inline=True
        )

        embed.add_field(
            name='MP Placements',
            value=placement_str,
            inline=False
        )

        embed.add_field(
            name='Straftcoins',
            value=f'**{sc_fmt(straftcoins)}** {emojis[4]}',
            inline=False
        )

        thread = await ctx.message.create_thread(name=f'Stats for {player.display_name}')
        await thread.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Stats(bot))
