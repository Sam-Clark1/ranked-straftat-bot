import discord
from discord.ext import commands
import aiosqlite
from helpers.command_helpers import get_emoji, get_display_name, sc_fmt

_PALE_GREEN = discord.Color(0x90ee90)

class StraftcoinLB(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def slb(self, ctx):
        sc_emoji = (await get_emoji(['Straftcoin']))[0]

        async with aiosqlite.connect("rankings.db") as db:
            leaderboard_data = await db.execute(
                "SELECT user_id, straftcoins FROM players ORDER BY straftcoins DESC"
            )
            rows = await leaderboard_data.fetchall()

        if not rows:
            await ctx.send('No Players in Database')
            return

        thread = await ctx.message.create_thread(name='Straftcoin Leaderboard')

        placement_emoji = {1: '🥇', 2: '🥈', 3: '🥉'}
        embeds  = []
        current = discord.Embed(title='Straftcoin Leaderboard', color=_PALE_GREEN)
        desc    = ''
        LIMIT   = 4000

        for i, (user_id, straftcoins) in enumerate(rows, 1):
            username = await get_display_name(ctx, user_id)
            pos      = placement_emoji.get(i, f'{i}.')
            line     = f"{pos} **{username}** - {sc_fmt(straftcoins)} {sc_emoji}\n"

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

async def setup(bot):
    await bot.add_cog(StraftcoinLB(bot))
