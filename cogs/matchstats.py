import discord
from discord.ext import commands
import aiosqlite
from helpers.command_helpers import get_display_name

_PALE_GREEN = discord.Color(0x90ee90)

class Matchstats(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def matchstats(self, ctx, player: discord.Member):
        async with aiosqlite.connect("rankings.db") as db:
            async with db.execute("""
                SELECT
                    mp2.player_id AS opponent_id,
                    m.game_mode,
                    COUNT(*) AS shared_games,
                    SUM(CASE WHEN mp1.placement < mp2.placement THEN 1 ELSE 0 END) AS above_count,
                    SUM(CASE WHEN mp1.placement > mp2.placement THEN 1 ELSE 0 END) AS below_count,
                    SUM(CASE WHEN mp1.placement = mp2.placement THEN 1 ELSE 0 END) AS tied_count,
                    SUM(mp1.rounds_won) AS rounds_won,
                    SUM(mp2.rounds_won) AS rounds_lost,
                    SUM(CASE WHEN mp1.placement = 1 THEN 1 ELSE 0 END) AS first_place_count,
                    AVG(CAST(mp2.placement AS REAL) - mp1.placement) AS avg_placement_diff
                FROM match_participants mp1
                JOIN match_participants mp2
                    ON mp1.match_id = mp2.match_id AND mp2.player_id != mp1.player_id
                JOIN matches m ON mp1.match_id = m.match_id
                WHERE mp1.player_id = ?
                GROUP BY mp2.player_id, m.game_mode
                ORDER BY m.game_mode, mp2.player_id
            """, (player.id,)) as cursor:
                rows = await cursor.fetchall()

        if not rows:
            await ctx.send(f"No match stats found for {player.mention}.")
            return

        stats_1v1 = {}
        stats_mp  = {}
        for opponent_id, game_mode, shared, above, below, tied, rw, rl, first_place, avg_diff in rows:
            entry = (shared, above, below, tied, rw, rl, first_place, avg_diff)
            if game_mode == '1v1':
                stats_1v1[opponent_id] = entry
            else:
                stats_mp[opponent_id] = entry

        thread = await ctx.message.create_thread(name=f'Match Stats for {player.display_name}')

        # 1v1 section
        if stats_1v1:
            embeds      = []
            current     = discord.Embed(
                title=f'1v1 Match Stats - {player.display_name}', color=_PALE_GREEN
            )
            current.set_thumbnail(url=player.display_avatar.url)
            field_count = 0

            for opponent_id, (shared, wins, losses, _, rw, rl, _, _) in stats_1v1.items():
                opponent_name = await get_display_name(ctx, opponent_id)
                total_rounds  = rw + rl
                win_pct   = wins / shared * 100       if shared > 0       else 0
                round_pct = rw   / total_rounds * 100 if total_rounds > 0 else 0

                if field_count >= 25:
                    embeds.append(current)
                    current     = discord.Embed(color=_PALE_GREEN)
                    field_count = 0

                current.add_field(
                    name=f'vs {opponent_name}',
                    value=(
                        f"**{wins}W - {losses}L** ({win_pct:.1f}%)\n"
                        f"Rounds: {rw}–{rl} ({round_pct:.1f}%)\n"
                        ' ———————————' 
                    ),
                    inline=True
                )
                field_count += 1

            embeds.append(current)
            for embed in embeds:
                await thread.send(embed=embed)

        # MP section
        if stats_mp:
            embeds      = []
            current     = discord.Embed(
                title=f'MP Match Stats - {player.display_name}', color=_PALE_GREEN
            )
            current.set_thumbnail(url=player.display_avatar.url)
            field_count = 0

            for opponent_id, (shared, above, below, tied, _, _, first_place, avg_diff) in stats_mp.items():
                opponent_name = await get_display_name(ctx, opponent_id)
                above_pct  = above / shared * 100       if shared > 0 else 0
                below_pct  = below / shared * 100       if shared > 0 else 0
                tied_pct   = tied  / shared * 100       if shared > 0 else 0
                win_rate   = first_place / shared * 100 if shared > 0 else 0
                diff_str   = f"+{avg_diff:.1f}" if avg_diff >= 0 else f"{avg_diff:.1f}"
                tied_str   = f" | Tied: {tied} ({tied_pct:.1f}%)" if tied > 0 else ""

                if field_count >= 25:
                    embeds.append(current)
                    current     = discord.Embed(color=_PALE_GREEN)
                    field_count = 0

                current.add_field(
                    name=f'vs {opponent_name} - {shared} shared games',
                    value=(
                        f"Final Placements:\n"
                        f"Above: {above} ({above_pct:.1f}%) | Below: {below} ({below_pct:.1f}%){tied_str}\n"
                        f"Avg placement diff: {diff_str}\n"
                        f"Win rate: {win_rate:.1f}%\n"
                        ' ———————————'
                    ),
                    inline=True
                )
                field_count += 1

            embeds.append(current)
            for embed in embeds:
                await thread.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Matchstats(bot))
