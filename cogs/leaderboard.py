import discord
from discord.ext import commands
import aiosqlite
from command_helpers import get_ranks, get_emoji, get_display_name

class Leaderboard(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def lb(self, ctx):
        
        async with aiosqlite.connect("rankings.db") as db:
            leaderboard_data = await db.execute("""
                SELECT user_id, sp, rank FROM players ORDER BY sp DESC
            """)
            rows = await leaderboard_data.fetchall()

        if not rows:
            await ctx.send('No Players in Database')
            return 
        
        leaderboard_message = await ctx.send('**Ranked Straftat Leaderboard**')

        thread = await ctx.channel.create_thread(
            name='Ranked Straftat Leaderboard',
            message=leaderboard_message
        )

        # Build leaderboard message
        leaderboard_message_body = ''

        for user_id, sp, rank in rows:
            username = await get_display_name(ctx, user_id)
            rank_emote = await get_emoji([rank])

            leaderboard_message_body += f"- {username}: {rank}{rank_emote[0]} {sp} SP\n"

        await thread.send(leaderboard_message_body)

async def setup(bot):
    await bot.add_cog(Leaderboard(bot))