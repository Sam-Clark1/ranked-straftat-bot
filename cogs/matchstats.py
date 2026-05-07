import discord
from discord.ext import commands
import aiosqlite
from command_helpers import get_display_name

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
                    SUM(CASE WHEN mp1.placement < mp2.placement THEN 1 ELSE 0 END) AS wins_against,
                    SUM(CASE WHEN mp1.placement > mp2.placement THEN 1 ELSE 0 END) AS losses_against,
                    SUM(mp1.rounds_won) AS rounds_won_against,
                    SUM(mp2.rounds_won) AS rounds_lost_against
                FROM match_participants mp1
                JOIN match_participants mp2
                    ON mp1.match_id = mp2.match_id AND mp2.player_id != mp1.player_id
                WHERE mp1.player_id = ?
                GROUP BY mp2.player_id
            """, (player.id,)) as cursor:
                rows = await cursor.fetchall()

        if not rows:
            await ctx.send(f"No match stats found for {player.mention}.")
            return

        stats_message = await ctx.send(f"**Match Stats for {player.mention}**")
        thread = await ctx.channel.create_thread(
            name=f'Match Stats for {player.display_name}',
            message=stats_message
        )

        embeds      = []
        current     = discord.Embed(title=f'Match Stats — {player.display_name}', color=_PALE_GREEN)
        current.set_thumbnail(url=player.display_avatar.url)
        field_count = 0

        for row in rows:
            opponent_id, wins, losses, rounds_won, rounds_lost = row
            opponent_name = await get_display_name(ctx, opponent_id)

            total_matches = wins + losses
            total_rounds  = rounds_won + rounds_lost
            win_pct       = (wins / total_matches * 100)      if total_matches > 0 else 0
            round_pct     = (rounds_won / total_rounds * 100) if total_rounds  > 0 else 0

            if field_count >= 25:
                embeds.append(current)
                current     = discord.Embed(color=_PALE_GREEN)
                field_count = 0

            current.add_field(
                name=f'vs {opponent_name}',
                value=(
                    f"**{wins}W — {losses}L** ({win_pct:.1f}%)\n"
                    f"Rounds: {rounds_won}–{rounds_lost} ({round_pct:.1f}%)"
                ),
                inline=True
            )
            field_count += 1

        embeds.append(current)
        for embed in embeds:
            await thread.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Matchstats(bot))
