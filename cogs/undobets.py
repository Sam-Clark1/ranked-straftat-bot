import discord
from discord.ext import commands
import aiosqlite
from dotenv import load_dotenv
import os
from helpers.command_helpers import backup_db


class UndoBets(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def undobets(self, ctx):
        load_dotenv()
        if ctx.author.id != int(os.environ['ADMIN_ID']):
            await ctx.send("You are not authorized to cancel bets.")
            return

        async with aiosqlite.connect("rankings.db") as db:

            # Single bet refunds — sum bet_amount per user where no parlay
            async with db.execute(
                "SELECT user_id, SUM(bet_amount) FROM live_bets "
                "WHERE parlay_id IS NULL GROUP BY user_id"
            ) as cursor:
                single_refunds = await cursor.fetchall()

            # Parlay refunds — use parlays.total_stake, not live_bets rows,
            # because each leg row carries the full stake (would over-refund otherwise)
            async with db.execute(
                "SELECT user_id, SUM(total_stake) FROM parlays "
                "WHERE status = 'live' GROUP BY user_id"
            ) as cursor:
                parlay_refunds = await cursor.fetchall()

            if not single_refunds and not parlay_refunds:
                await ctx.send("No live bets to cancel.")
                return

            backup_db()

            # Merge refunds per user
            refunds = {}
            for user_id, amount in single_refunds:
                refunds[user_id] = refunds.get(user_id, 0) + amount
            for user_id, amount in parlay_refunds:
                refunds[user_id] = refunds.get(user_id, 0) + amount

            # Credit each player
            for user_id, amount in refunds.items():
                await db.execute(
                    "UPDATE players SET straftcoins = straftcoins + ? WHERE user_id = ?",
                    (amount, user_id)
                )

            await db.execute("DELETE FROM live_bets")
            await db.execute(
                "UPDATE parlays SET status = 'cancelled', payout = 0 WHERE status = 'live'"
            )
            await db.commit()

        embed = discord.Embed(
            title='Live Bets Cancelled',
            description='\n'.join(f'<@{uid}> — +{amt} SC' for uid, amt in refunds.items()),
            color=discord.Color(0x90ee90)
        )
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(UndoBets(bot))
