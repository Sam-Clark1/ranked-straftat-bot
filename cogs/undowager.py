import discord
from discord.ext import commands
import aiosqlite
from dotenv import load_dotenv
import os
from helpers.command_helpers import backup_db, sc_fmt


class UndoWager(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def undowager(self, ctx):
        load_dotenv()
        if ctx.author.id != int(os.environ['ADMIN_ID']):
            await ctx.send("You are not authorized to cancel wagers.")
            return

        async with aiosqlite.connect("rankings.db") as db:
            async with db.execute(
                "SELECT wager_id, player_a_id, player_b_id, player_a_amount, player_b_amount "
                "FROM wagers WHERE status = 'active'"
            ) as cursor:
                active_wagers = await cursor.fetchall()

            if not active_wagers:
                await ctx.send("No active wagers to cancel.")
                return

            backup_db()

            # Merge refunds per user (a player could theoretically have multiple active wagers)
            refunds = {}
            for _, a_id, b_id, a_amt, b_amt in active_wagers:
                refunds[a_id] = refunds.get(a_id, 0) + a_amt
                refunds[b_id] = refunds.get(b_id, 0) + b_amt

            # Credit each player
            for user_id, amount in refunds.items():
                await db.execute(
                    "UPDATE players SET straftcoins = straftcoins + ? WHERE user_id = ?",
                    (amount, user_id)
                )

            await db.execute("UPDATE wagers SET status = 'cancelled' WHERE status = 'active'")
            await db.commit()

        embed = discord.Embed(
            title='Active Wagers Cancelled',
            description='\n'.join(f'<@{uid}> - +{sc_fmt(amt)} SC' for uid, amt in refunds.items()),
            color=discord.Color(0x90ee90)
        )
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(UndoWager(bot))
