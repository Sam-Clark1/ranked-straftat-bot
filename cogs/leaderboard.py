import discord
from discord.ext import commands
import aiosqlite
from command_helpers import get_emoji, get_display_name

class Leaderboard(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def _send_leaderboard(self, ctx, mode: str):
        if mode == '1v1':
            sp_col   = 'sp_1v1'
            rank_col = 'rank_1v1'
            title    = 'Ranked Straftat Leaderboard — 1v1'
        else:
            sp_col   = 'sp_mp'
            rank_col = 'rank_mp'
            title    = 'Ranked Straftat Leaderboard — Multiplayer'

        async with aiosqlite.connect("rankings.db") as db:
            leaderboard_data = await db.execute(f"""
                SELECT user_id, {sp_col}, {rank_col} FROM players ORDER BY {sp_col} DESC
            """)
            rows = await leaderboard_data.fetchall()

        if not rows:
            await ctx.send('No Players in Database')
            return

        leaderboard_message = await ctx.send(f'**{title}**')

        thread = await ctx.channel.create_thread(
            name=title,
            message=leaderboard_message
        )

        leaderboard_message_body = ''

        for user_id, sp, rank in rows:
            username   = await get_display_name(ctx, user_id)
            rank_emote = await get_emoji([rank])
            leaderboard_message_body += f"- {username}: {rank}{rank_emote[0]} {sp} SP\n"

        await thread.send(leaderboard_message_body)

    @commands.command()
    async def lb(self, ctx):
        await self._send_leaderboard(ctx, '1v1')

    @commands.command()
    async def mlb(self, ctx):
        await self._send_leaderboard(ctx, 'mp')

async def setup(bot):
    await bot.add_cog(Leaderboard(bot))