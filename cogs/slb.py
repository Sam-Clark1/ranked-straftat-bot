import discord
from discord.ext import commands
import aiosqlite
from command_helpers import get_emoji, get_display_name

class StraftcoinLB(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def slb(self, ctx):
        rank_emote = await get_emoji(['Straftcoin'])

        async with aiosqlite.connect("rankings.db") as db:
            leaderboard_data = await db.execute("""
                SELECT user_id, straftcoins FROM players ORDER BY straftcoins DESC
            """)
            rows = await leaderboard_data.fetchall()

        if not rows:
            await ctx.send('No Players in Database')
            return 
        
        leaderboard_message = await ctx.send('**Straftcoin Leaderboard**')

        thread = await ctx.channel.create_thread(
            name='Straftcoin Leaderboard',
            message=leaderboard_message
        )

        # Build leaderboard message
        leaderboard_message_body = ''

        for user_id, straftcoin in rows:
            username = await get_display_name(ctx, user_id)
            
            leaderboard_message_body += f"- {username}: {straftcoin}{rank_emote[0]}\n"

        await thread.send(leaderboard_message_body)

async def setup(bot):
    await bot.add_cog(StraftcoinLB(bot))