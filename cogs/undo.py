import discord
from discord.ext import commands
import aiosqlite
from command_helpers import get_rank, get_sp
from dotenv import load_dotenv
import os 

class Undo(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def undo(self, ctx):

        load_dotenv()
        ADMIN_ID = os.environ['ADMIN_ID']
        undo_authorized_id = ADMIN_ID
        
        if ctx.author.id != undo_authorized_id:
            await ctx.send("You are not authorized to undo matches.")
            return

        async with aiosqlite.connect("rankings.db") as db:

            # --- GET LATEST MATCH ---
            match_row = await db.execute(
                "SELECT match_id, total_rounds, game_mode FROM matches ORDER BY match_id DESC LIMIT 1"
            )
            match = await match_row.fetchone()

            if not match:
                await ctx.send("No matches to undo.")
                return

            match_id, total_rounds, game_mode = match

            # --- GET ALL PARTICIPANTS ---
            async with db.execute("""
                SELECT player_id, placement, rounds_won, elo_change, sp_change, straftcoin_change
                FROM match_participants
                WHERE match_id = ?
                ORDER BY placement ASC
            """, (match_id,)) as cursor:
                participants = await cursor.fetchall()

            if not participants:
                await ctx.send("Match found but no participants on record. Database may be inconsistent.")
                return

            # --- SET COLUMN NAMES BASED ON MODE ---
            if game_mode == '1v1':
                sp_col     = 'sp_1v1'
                rating_col = 'rating_1v1'
                rank_col   = 'rank_1v1'
                wins_col   = 'wins_1v1'
                losses_col = 'losses_1v1'
                rw_col     = 'rounds_won_1v1'
                rl_col     = 'rounds_lost_1v1'
            else:
                sp_col     = 'sp_mp'
                rating_col = 'rating_mp'
                rank_col   = 'rank_mp'
                wins_col   = 'wins_mp'
                losses_col = 'losses_mp'
                rw_col     = 'rounds_won_mp'
                rl_col     = 'rounds_lost_mp'

            # --- REVERSE EACH PARTICIPANT ---
            for player_id, placement, rounds_won, elo_change, sp_change, straftcoin_change in participants:

                current_sp   = await get_sp(db, player_id, mode=game_mode)
                restored_sp  = max(0, current_sp - sp_change)
                restored_rank, _ = await get_rank(restored_sp)

                rounds_lost_in_match = total_rounds - rounds_won
                is_winner = placement == 1

                await db.execute(f"""
                    UPDATE players SET
                        {rating_col} = {rating_col} - ?,
                        {sp_col}     = ?,
                        {rank_col}   = ?,
                        {wins_col}   = {wins_col} - ?,
                        {losses_col} = {losses_col} - ?,
                        {rw_col}     = {rw_col} - ?,
                        {rl_col}     = {rl_col} - ?,
                        straftcoins  = MAX(0, straftcoins - ?)
                    WHERE user_id = ?
                """, (
                    elo_change,
                    restored_sp,
                    restored_rank,
                    1 if is_winner else 0,
                    0 if is_winner else 1,
                    rounds_won,
                    rounds_lost_in_match,
                    straftcoin_change,
                    player_id
                ))

            # --- REVERSE BETS ---
            async with db.execute(
                "SELECT * FROM past_bets WHERE match_id = ?", (match_id,)
            ) as cursor:
                past_bets = await cursor.fetchall()

            if past_bets:
                for bet in past_bets:
                    bet_id, user_id, _, match_title, player_bet_on_id, bet_type, bet_value, bet_odds, bet_amount, result, amount_won = bet

                    # Claw back the payout
                    await db.execute(
                        "UPDATE players SET straftcoins = MAX(0, straftcoins - ?) WHERE user_id = ?",
                        (amount_won, user_id)
                    )

                    # Restore to live_bets so it re-settles when match is re-recorded
                    await db.execute("""
                        INSERT INTO live_bets
                            (user_id, match_title, player_bet_on_id, bet_type, bet_value, bet_odds, bet_amount)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (user_id, match_title, player_bet_on_id, bet_type, bet_value, bet_odds, bet_amount))

                    await db.execute("DELETE FROM past_bets WHERE bet_id = ?", (bet_id,))

            # --- DELETE MATCH RECORDS ---
            await db.execute("DELETE FROM match_participants WHERE match_id = ?", (match_id,))
            await db.execute("DELETE FROM matches WHERE match_id = ?", (match_id,))
            await db.commit()

        # --- CONFIRMATION ---
        mode_label = '1v1' if game_mode == '1v1' else 'Multiplayer'
        participant_mentions = " vs ".join(f"<@{pid}>" for pid, *_ in participants)
        await ctx.send(f"**{mode_label}** match ({participant_mentions}) has been undone!")


async def setup(bot):
    await bot.add_cog(Undo(bot))