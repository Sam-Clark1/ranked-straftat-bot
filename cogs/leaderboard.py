import discord
from discord.ext import commands
import aiosqlite
from helpers.command_helpers import get_emoji, get_display_name

_PALE_GREEN = discord.Color(0x90ee90)

class Leaderboard(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def _send_leaderboard(self, ctx, mode: str):
        if mode == '1v1':
            sp_col   = 'sp_1v1'
            rank_col = 'rank_1v1'
            title    = 'Leaderboard - 1v1'
        else:
            sp_col   = 'sp_mp'
            rank_col = 'rank_mp'
            title    = 'Leaderboard - Multiplayer'

        async with aiosqlite.connect("rankings.db") as db:
            leaderboard_data = await db.execute(f"""
                SELECT user_id, {sp_col}, {rank_col} FROM players ORDER BY {sp_col} DESC
            """)
            rows = await leaderboard_data.fetchall()

        if not rows:
            await ctx.send('No Players in Database')
            return

        thread = await ctx.message.create_thread(name=title)

        placement_emoji = {1: '🥇', 2: '🥈', 3: '🥉'}
        embeds  = []
        current = discord.Embed(title=f'Ranked Straftat {title}', color=_PALE_GREEN)
        desc    = ''
        LIMIT   = 4000

        for i, (user_id, sp, rank) in enumerate(rows, 1):
            username   = await get_display_name(ctx, user_id)
            rank_emote = (await get_emoji([rank]))[0]
            pos        = placement_emoji.get(i, f'{i}.')
            line       = f"{pos} **{username}** - {sp} SP · {rank} {rank_emote}\n"

            if len(desc) + len(line) > LIMIT:
                current.description = desc
                embeds.append(current)
                current = discord.Embed(color=_PALE_GREEN)
                desc = ''
            desc += line

        if desc:
            current.description = desc
            embeds.append(current)

        for embed in embeds:
            await thread.send(embed=embed)

    @commands.command()
    async def lb(self, ctx):
        await self._send_leaderboard(ctx, '1v1')

    @commands.command()
    async def mlb(self, ctx):
        await self._send_leaderboard(ctx, 'mp')

async def setup(bot):
    await bot.add_cog(Leaderboard(bot))
