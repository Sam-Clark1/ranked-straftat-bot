import discord
from discord.ext import commands
import asyncio
import re
import aiosqlite
import random
from model_helpers import predict_variable
from bet_helpers import check_match_titles, handle_bet_placements, create_table_image, percentage_to_odds, calc_performance_score, calculate_win_probability
from command_helpers import handle_inputted_players, get_rating, get_emoji, calculate_elo, get_players, get_display_name, get_player_matches

class Bet(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # Gamble command
    @commands.command()
    async def bet(self, ctx, player1: discord.Member, player2: discord.Member):
        async with aiosqlite.connect('rankings.db') as db:
            
            if player1.id == player2.id:
                await ctx.send("Invalid input dumbass: Cannot record bet against yourself.")
                return 
            
            bets, existing_match_title = await check_match_titles(player1.display_name, player2.display_name, db)

            if bets:
                await ctx.send(f'Bets for the next **{existing_match_title}** match have already been placed. Please wait for that match to conclude before placing new bets.')
                return 
            
            await handle_inputted_players([player1.id, player2.id], db)

            # Generate match title
            match_title = f"{player1.display_name} vs {player2.display_name}"
            
            # Set variables for countdown timer
            seconds = 120
            minutes, secs = divmod(seconds, 60)

            # Bot sends a message
            bot_message = await ctx.send(f"Bets for {match_title}\n**Time Remaining to Bet: {minutes:02}:{secs:02}**")
            
            # Create a thread on the message
            thread = await ctx.channel.create_thread(
                name=match_title,
                message=bot_message
            )

            # player1_rating = await get_rating(db, player1.id)
            # player2_rating = await get_rating(db, player2.id)
            
            # _, _, player1_win_prob, player2_win_prob = await calculate_elo(1, 1, player1_rating, player2_rating)

            player_1_p_score = await calc_performance_score(player1.id, player2.id, db)
            player_2_p_score = await calc_performance_score(player2.id, player1.id, db)

            player1_win_prob, player2_win_prob = await calculate_win_probability(player_1_p_score, player_2_p_score)

            player1_info = [player1.display_name, player1_win_prob, player1.id]
            player2_info = [player2.display_name, player2_win_prob, player2.id]

            if player1_win_prob >= player2_win_prob:
                favorite = player1_info
                underdog = player2_info
            else:
                favorite = player2_info
                underdog = player1_info
            
            player1_played_true = await get_player_matches(db, player1_info[2])
            player2_played_true = await get_player_matches(db, player2_info[2])
           
            if player1_played_true and player2_played_true:
                predicted_spread = await predict_variable(favorite[2], underdog[2], 'spread', db)
                # predicted_ou = await predict_variable(player1_info[2], player2_info[2], 'total_rounds', db)
            elif player1_played_true or player2_played_true:
                predicted_spread = 6.5
                # predicted_ou = 15
            else:
                predicted_spread = 4.5
                # predicted_ou = 15

            favorite_spread, favorite_moneyline, over_value = f'-{predicted_spread}', favorite[0], f'O{20 - predicted_spread}'
            underdog_spread, underdog_moneyline, under_value = f'+{predicted_spread}', underdog[0], f'U{20 - predicted_spread}'

            favorite_spread_odds, favorite_moneyline_odds, over_value_odds = (-100 - random.randint(10, 15)), await percentage_to_odds(favorite[1]), (-100 - random.randint(11, 15))
            underdog_spread_odds, underdog_moneyline_odds, under_value_odds =(-100 - random.randint(0, 10)), await percentage_to_odds(underdog[1]), (-100 - random.randint(0, 10))

            available_player_balances = await get_players(db)

            if available_player_balances:
                embed = discord.Embed(
                    title="Player Balances",
                    color=discord.Colour.dark_embed()
                )

                # Add players to the embed
                for player in available_player_balances:
                    user_id, straftcoins = player
                    embed.add_field(
                        name=f"{await get_display_name(ctx, user_id)}",
                        value=f"Straftcoins: {straftcoins}",
                        inline=True
                    )

                # Send the embed
                await thread.send(embed=embed)

            straftcoin_emoji = await get_emoji(['Straftcoin'])

            # Notify users in the thread
            await thread.send(f"Welcome to the betting thread for **{match_title}**!\n"
                            f"- Bet using **'A 100'**, where **A** is the bet type and **100** is the amount you\'re betting.\n"
                            f"- Bets lock in after 2 minutes. No more bets on this matchup can be made until the match is played.\n"
                            f"- Everyone can bet, even if you\'ve never played a ranked match (you\'ll start with 1000 {straftcoin_emoji[0]})."
                              )

            async def send_table_image(thread, favorite, underdog):
                data = [
                    [favorite[0], 
                     f'A\n{favorite_spread}\n{favorite_spread_odds}', 
                     f'B\n\n{favorite_moneyline_odds}', 
                     f'C\n{over_value}\n{over_value_odds}'],
                    [underdog[0], 
                     f'D\n{underdog_spread}\n{underdog_spread_odds}', 
                     f"E\n\n{'+' if underdog_moneyline_odds > 0 else ''}{underdog_moneyline_odds}", 
                     f'F\n{under_value}\n{under_value_odds}']
                ]
                columns = ["Player", "Spread", "Moneyline", "O/U"]
                
                # Generate the table image
                image_buf = await create_table_image(data, columns)

                # Send the image in Discord
                await thread.send(file=discord.File(fp=image_buf, filename="table.png"))
                        
            await send_table_image(thread, favorite, underdog)

            # Wait for 5 minutes
            for remaining in range(seconds - 1, -1, -1):
                await asyncio.sleep(1)
                minutes, secs = divmod(remaining, 60)
                await bot_message.edit(content=f"Bets for {match_title}\n**Time Remaining to Bet: {minutes:02}:{secs:02}**")

            bets_info = {
                "A": {"type": "Spread", "value": favorite_spread, "odds": favorite_spread_odds},
                "B": {"type": "Moneyline", "value": favorite_moneyline, "odds": favorite_moneyline_odds},
                "C": {"type": "O/U", "value": over_value, "odds": over_value_odds},
                "D": {"type": "Spread", "value": underdog_spread, "odds": underdog_spread_odds},
                "E": {"type": "Moneyline", "value": underdog_moneyline, "odds": underdog_moneyline_odds},
                "F": {"type": "O/U", "value": under_value, "odds": under_value_odds},
            }

            # Collect and process bets
            bets = []
            async for message in thread.history(oldest_first=True):
                match = re.match(r"^([A-Fa-f]{1})\s(\d+)$", message.content)
                if match:
                    if message.author.id == player1.id or message.author.id == player2.id:

                        await thread.send(f"Can't bet on games you're in, {message.author.mention}. Bet not logged.")
                        
                    else:
                        bet = await handle_bet_placements(match_title, favorite[2], 
                                                        underdog[2], match, 
                                                        thread, message, 
                                                        bets_info, db)
                        if bet != False:
                            bets.append(bet)
                        
            await db.executemany(
                """
                INSERT INTO live_bets (user_id, match_title, match_favorite_id, match_underdog_id, playerid_bet_on, bet_type, bet_value, bet_odds, bet_amount)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                bets
            )
            await db.commit()

            await thread.send(f"Bets for the next **{match_title}** match have been locked in")

            # Modify permissions to make the thread reaction-only
            await thread.edit(locked=True)

async def setup(bot):
    await bot.add_cog(Bet(bot))