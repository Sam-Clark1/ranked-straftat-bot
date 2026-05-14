import discord
from discord.ext import commands
import aiosqlite
from helpers.command_helpers import get_rank, get_sp, backup_db
from dotenv import load_dotenv
import os 

class Undo(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def undo(self, ctx):

        load_dotenv()
        ADMIN_ID = int(os.environ['ADMIN_ID'])
        undo_authorized_id = ADMIN_ID
        
        if ctx.author.id != undo_authorized_id:
            await ctx.send("You are not authorized to undo matches.")
            return

        async with aiosqlite.connect("rankings.db") as db:

            
            # GET LATEST MATCH
            
            match_row = await db.execute(
                "SELECT match_id, total_rounds, game_mode "
                "FROM matches ORDER BY match_id DESC LIMIT 1"
            )
            match = await match_row.fetchone()

            if not match:
                await ctx.send("No matches to undo.")
                return

            match_id, total_rounds, game_mode = match

            
            # GET ALL PARTICIPANTS
            
            async with db.execute("""
                SELECT player_id, placement, rounds_won,
                       elo_change, sp_change, straftcoin_change
                FROM match_participants
                WHERE match_id = ?
                ORDER BY placement ASC
            """, (match_id,)) as cursor:
                participants = await cursor.fetchall()

            if not participants:
                await ctx.send(
                    "Match found but no participants on record. "
                    "Database may be inconsistent."
                )
                return

            
            # MODE-SPECIFIC COLUMN NAMES
            
            if game_mode == '1v1':
                sp_col     = 'sp_1v1'
                rating_col = 'rating_1v1'
                rank_col   = 'rank_1v1'
                wins_col   = 'wins_1v1'
                losses_col = 'losses_1v1'
                rw_col     = 'rounds_won_1v1'
                rl_col     = 'rounds_lost_1v1'
                hr_col     = 'highest_rank_1v1'
                hsp_col    = 'highest_sp_1v1'
            else:
                sp_col     = 'sp_mp'
                rating_col = 'rating_mp'
                rank_col   = 'rank_mp'
                wins_col   = 'wins_mp'
                losses_col = 'losses_mp'
                rw_col     = 'rounds_won_mp'
                rl_col     = 'rounds_lost_mp'
                hr_col     = 'highest_rank_mp'
                hsp_col    = 'highest_sp_mp'

            
            backup_db()

            # REVERSE EACH PARTICIPANT'S STATS
            
            for (player_id, placement, rounds_won,
                 elo_change, sp_change, straftcoin_change) in participants:

                current_sp   = await get_sp(db, player_id, mode=game_mode)
                restored_sp  = max(0, current_sp - sp_change)
                restored_rank, _ = await get_rank(restored_sp)

                rounds_lost_in_match = total_rounds - rounds_won
                is_winner = placement == 1

                await db.execute(f"""
                    UPDATE players SET
                        {rating_col} = ROUND({rating_col} - ?, 2),
                        {sp_col}     = ?,
                        {rank_col}   = ?,
                        {wins_col}   = {wins_col}   - ?,
                        {losses_col} = {losses_col} - ?,
                        {rw_col}     = {rw_col}     - ?,
                        {rl_col}     = {rl_col}     - ?,
                        straftcoins  = MAX(0, straftcoins - ?),
                        {hsp_col}    = MIN({hsp_col}, ?),
                        {hr_col}     = CASE WHEN ? < {hsp_col} THEN ? ELSE {hr_col} END
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
                    restored_sp,
                    restored_sp, restored_rank,
                    player_id
                ))

            
            # REVERSE BETS
            
            async with db.execute(
                "SELECT * FROM past_bets WHERE match_id = ?", (match_id,)
            ) as cursor:
                past_bets = await cursor.fetchall()

            if past_bets:
                # Track which parlay IDs we've already processed so we don't
                # double-claw parlay payouts if multiple legs are in the same match
                processed_parlay_ids = set()

                for bet in past_bets:
                    (bet_id, user_id, _, match_title,
                     player_bet_on_id, player_b_id,
                     bet_type, bet_value, bet_odds, bet_amount,
                     result, amount_won, parlay_id) = bet

                    if parlay_id is not None:
                        # ── PARLAY LEG ──────────────────────────────────────
                        if parlay_id not in processed_parlay_ids:
                            processed_parlay_ids.add(parlay_id)

                            async with db.execute(
                                "SELECT user_id, status, payout "
                                "FROM parlays WHERE parlay_id = ?",
                                (parlay_id,)
                            ) as cursor:
                                parlay_row = await cursor.fetchone()

                            if parlay_row:
                                p_user_id, p_status, p_payout = parlay_row

                                # Claw back payout only if the parlay won
                                if p_status == 'won' and p_payout > 0:
                                    await db.execute(
                                        "UPDATE players SET "
                                        "straftcoins = MAX(0, straftcoins - ?) "
                                        "WHERE user_id = ?",
                                        (p_payout, p_user_id)
                                    )

                                # Reset parlay to live so it re-settles on re-record
                                await db.execute(
                                    "UPDATE parlays SET status = 'live', payout = 0 "
                                    "WHERE parlay_id = ?",
                                    (parlay_id,)
                                )

                        # Restore leg to live_bets with parlay_id intact
                        await db.execute("""
                            INSERT INTO live_bets
                                (user_id, match_title,
                                 player_bet_on_id, player_b_id,
                                 bet_type, bet_value, bet_odds,
                                 bet_amount, parlay_id)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            user_id, match_title,
                            player_bet_on_id, player_b_id,
                            bet_type, bet_value, bet_odds,
                            bet_amount, parlay_id
                        ))

                    else:
                        # ── SINGLE BET ───────────────────────────────────────
                        if result == 'win':
                            # Claw back the payout that was credited at settlement
                            await db.execute(
                                "UPDATE players SET "
                                "straftcoins = MAX(0, straftcoins - ?) "
                                "WHERE user_id = ?",
                                (amount_won, user_id)
                            )
                        elif result == 'push':
                            # Claw back the stake refund that was credited
                            await db.execute(
                                "UPDATE players SET "
                                "straftcoins = MAX(0, straftcoins - ?) "
                                "WHERE user_id = ?",
                                (bet_amount, user_id)
                            )
                        # result == 'loss': nothing to claw back, stake stays deducted

                        # Restore bet to live_bets
                        await db.execute("""
                            INSERT INTO live_bets
                                (user_id, match_title,
                                 player_bet_on_id, player_b_id,
                                 bet_type, bet_value, bet_odds,
                                 bet_amount, parlay_id)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL)
                        """, (
                            user_id, match_title,
                            player_bet_on_id, player_b_id,
                            bet_type, bet_value, bet_odds,
                            bet_amount
                        ))

                    await db.execute(
                        "DELETE FROM past_bets WHERE bet_id = ?", (bet_id,)
                    )

            
            # DELETE MATCH RECORDS
            
            await db.execute(
                "DELETE FROM match_participants WHERE match_id = ?", (match_id,)
            )
            await db.execute(
                "DELETE FROM matches WHERE match_id = ?", (match_id,)
            )
            await db.commit()

        
        # CONFIRMATION
        
        mode_label = '1v1' if game_mode == '1v1' else 'Multiplayer'
        participant_mentions = " vs ".join(
            f"<@{pid}>" for pid, *_ in participants
        )
        await ctx.send(
            f"**{mode_label}** match ({participant_mentions}) has been undone!"
        )


async def setup(bot):
    await bot.add_cog(Undo(bot))