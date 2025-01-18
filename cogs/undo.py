import discord
from discord.ext import commands
import aiosqlite
from command_helpers import get_rank, get_sp

class Undo(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def undo(self, ctx):
        
        undo_authorized_id = 141371022938079233  # Replace with the authorized user's ID or role
        if ctx.author.id != undo_authorized_id:
            await ctx.send("You are not authorized to undo matches.")
            return

        async with aiosqlite.connect("rankings.db") as db:
            # Get the latest match
            match_row = await db.execute("SELECT * FROM matches ORDER BY match_id DESC LIMIT 1")
            match = await match_row.fetchone()

            if not match:
                await ctx.send("No matches to undo.")
                return

            match_id, winner_id, loser_id, winner_rounds, loser_rounds, winner_elo_gain, loser_elo_loss, winner_sp_gain, loser_sp_loss, _, _, _, _, winner_straftcoin_change, loser_straftcoin_change = match

            prev_sp = max(0, await get_sp(db, winner_id))
            new_sp = prev_sp - winner_sp_gain
            winner_new_rank, _ = await get_rank(new_sp)

            await db.execute("""
                UPDATE players 
                SET 
                    rating = rating - ?,
                    sp = sp - ?,
                    wins = wins - 1,
                    rounds_won = rounds_won - ?,
                    rounds_lost = rounds_lost - ?,
                    rank = ?, 
                    straftcoins = straftcoins - ?
                WHERE user_id = ?
            """, (winner_elo_gain, winner_sp_gain, winner_rounds, loser_rounds, winner_new_rank, winner_straftcoin_change, winner_id))

            prev_sp = max(0, await get_sp(db, loser_id))
            new_sp = prev_sp - loser_sp_loss
            loser_new_rank, _ = await get_rank(new_sp)
            
            await db.execute("""
                UPDATE players 
                SET 
                    rating = rating - ?,
                    sp = sp - ?,
                    losses = losses - 1,
                    rounds_won = rounds_won - ?,
                    rounds_lost = rounds_lost - ?,
                    rank = ?,
                    straftcoins = straftcoins - ?
                WHERE user_id = ?
            """, (loser_elo_loss, loser_sp_loss, loser_rounds, winner_rounds, loser_new_rank, loser_straftcoin_change, loser_id))
            
            async with db.execute(
                "SELECT * FROM past_bets WHERE match_id = ?", (match_id,)
            ) as cursor:
                past_bets = await cursor.fetchall()

            if past_bets:
                for bet_id, user_id, match_id, match_title, match_favorite_id, match_underdog_id, playerid_bet_on, bet_type, bet_value, bet_odds, bet_amount, _, amount_won, _ in past_bets:
                    
                    live_bet_columns = [user_id, match_title, match_favorite_id, match_underdog_id, playerid_bet_on, bet_type, bet_value, bet_odds, bet_amount]
                    
                    await db.execute(
                        """
                        UPDATE players SET straftcoins = straftcoins - ? WHERE user_id = ?
                        """, (amount_won, user_id)
                    )

                    await db.execute(
                        """
                        INSERT INTO live_bets (user_id, match_title, match_favorite_id, match_underdog_id, playerid_bet_on, bet_type, bet_value, bet_odds, bet_amount)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        live_bet_columns
                    )

                    await db.execute("DELETE FROM past_bets WHERE bet_id = ?", (bet_id,))

            # Remove the match record
            await db.execute("DELETE FROM matches WHERE match_id = ?", (match_id,))
            await db.commit()

        await ctx.send(f"Match between <@{winner_id}> and <@{loser_id}> has been undone!")
    
async def setup(bot):
    await bot.add_cog(Undo(bot))