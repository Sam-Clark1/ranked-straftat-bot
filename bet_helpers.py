import pandas as pd
import matplotlib.pyplot as plt
from io import BytesIO
import math
from command_helpers import get_straftcoin, get_emoji

async def create_table_image(data, columns, file_name="table.png"):
    bg_color = '#40444b'
    text_gridline_color = '#FFFFFF'

    # Create a DataFrame
    df = pd.DataFrame(data, columns=columns)

    # Create a Matplotlib figure and axis
    fig, ax = plt.subplots(figsize=(6, len(data) + 1), facecolor=bg_color)
    ax.axis('tight')
    ax.axis('off')

    # Create a table plot
    table = ax.table(cellText=df.values, 
                        colLabels=df.columns, 
                        cellLoc='center', 
                        loc='center')
    table.auto_set_font_size(False)
    table.set_fontsize(12)
    table.auto_set_column_width(col=list(range(len(columns))))

    for key, cell in table.get_celld().items():
        cell.set_height(0.3)
        cell.set_edgecolor(text_gridline_color)

        if key[0] == 0:
            cell.set_facecolor(bg_color)
            cell.set_text_props(color=text_gridline_color, weight='bold')
        else:
            cell.set_facecolor(bg_color)
            cell.set_text_props(color=text_gridline_color)

    # Save the table to an image file
    buf = BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight', dpi=500)
    buf.seek(0)

    return buf

async def handle_bet_placements(match_title, favorite, underdog, match, thread, message, bets_info, db):
    
    user_id = message.author.id
    bet_amount = int(match.group(2))
    emojis = await get_emoji(['Straftcoin'])

    async def bet_to_tuple():
        option_value = match.group(1).upper()

        if option_value=='A' or option_value=='B':
            playerid_bet_on = favorite
        elif option_value=='D' or option_value=='E':
            playerid_bet_on = underdog
        else:
            playerid_bet_on = 0

        bet_info = bets_info[option_value]
        bet_type = bet_info['type']
        bet_value = bet_info['value']
        bet_odd = bet_info['odds']
        
        return (user_id, match_title, favorite, underdog, playerid_bet_on, bet_type, bet_value, bet_odd, bet_amount)
            
    # Check if the user is already in the table
    cursor = await db.execute("SELECT straftcoins FROM players WHERE user_id = ?", (user_id,))
    result = await cursor.fetchone()

    if result:
        # User exists, update their straftcoins
        current_coins = result[0]
        if bet_amount > current_coins:
            await thread.send(f"{message.author.mention}, insufficeint Straftcoins! You only have {current_coins}{emojis[0]} left.")
            return False
        
        bet = await bet_to_tuple()
        _, _, _, _, _, bet_type, bet_value, bet_odds, _ = bet

        amount_to_win, _ = await odds_to_percentage('win', bet_odds, bet_amount)

        await db.execute(
            "UPDATE players SET straftcoins = straftcoins - ? WHERE user_id = ?",
            (bet_amount, user_id)
        )
        await thread.send(f"{message.author.mention}\n- Bet: {bet_amount}{emojis[0]} on {bet_type} (**{bet_value}**, {bet_odds} odds)\n- To Win: {amount_to_win}{emojis[0]}\n- Current Balance: {current_coins - bet_amount}{emojis[0]}")
       
    else:
        # User doesn't exist, insert them and deduct the bet
        initial_coins = 1000
        if bet_amount > initial_coins:
            await db.execute(
                "INSERT INTO players (user_id) VALUES (?)",
                (user_id,)
            )
            await thread.send(f"{message.author.mention}, insufficient Straftcoin! You start with {initial_coins}{emojis[0]}.")
            return False
        
        bet = await bet_to_tuple()
        _, _, _, _, _, bet_type, bet_value, bet_odds, _ = bet

        amount_to_win, _ = await odds_to_percentage('win', bet_odds, bet_amount)

        await db.execute(
            "INSERT INTO players (user_id, straftcoins) VALUES (?, ?)",
            (user_id, initial_coins - bet_amount)
        )
        await thread.send(f"{message.author.mention} added as player!\n- Bet: {bet_amount}{emojis[0]} on {bet_type} (**{bet_value}**, {bet_odds} odds)\n- To Win: {amount_to_win}{emojis[0]}\n- Current Balance: {initial_coins - bet_amount}{emojis[0]}")

    await db.commit()

    return bet

async def odds_to_percentage(w_or_l_or_p, bet_odds, bet_amount):
    if w_or_l_or_p == 'win':

        bet_odds_str = str(bet_odds)

        if bet_odds_str[0] == '-':
            odds_prcnt = 1 - (100/bet_odds)
            amount1 = round(bet_amount * odds_prcnt)
            amount2 = 0
        else:
            odds_prcnt = 1 + (bet_odds/100)
            amount1 = round(bet_amount * odds_prcnt)
            amount2 = 0

    elif w_or_l_or_p == 'loss':
        amount1 = 0
        amount2 = bet_amount
        
    else:
        amount1 = 0
        amount2 = 0

    return amount1, amount2

async def percentage_to_odds(percent_odds):
    if percent_odds >= 0.5:
        odds = ((percent_odds*100) / (1 - percent_odds)) * -1 
    else:
        odds = (100 / percent_odds) - 100
    
    return round(odds)

async def check_match_titles(player1_name, player2_name, db):
    
    match_title = f"{player1_name} vs {player2_name}"
    match_title_alt = f"{player2_name} vs {player1_name}"
    
    # Retrieve all live bets for the match
    async with db.execute(
        "SELECT * FROM live_bets WHERE match_title = ?", (match_title,)
    ) as cursor:
        bets = await cursor.fetchall()

    # If there are no bets, notify and return
    if not bets:
        async with db.execute(
        "SELECT * FROM live_bets WHERE match_title = ?", (match_title_alt,)
        ) as cursor:
            bets = await cursor.fetchall()

        match_title = match_title_alt

    return bets, match_title

async def win_loss_determination(bets, match_id, spread, match_winner_id, total_rounds):
    winning_bets = []
    losing_bets = []
    pushed_bets = []

    for _, user_id, match_title, match_favorite_id, match_underdog_id, playerid_bet_on, bet_type, bet_value, bet_odds, bet_amount in bets:
        
        async def win_loss_info(w_or_l_or_p):
            bet_outcome = w_or_l_or_p
            amount1, amount2 = await odds_to_percentage(w_or_l_or_p, bet_odds, bet_amount)
            amount_won = amount1
            amount_lost = amount2

            bet_info = (user_id,
                        match_id,
                        match_title, 
                        match_favorite_id, 
                        match_underdog_id, 
                        playerid_bet_on, 
                        bet_type, 
                        bet_value, 
                        bet_odds, 
                        bet_amount, 
                        bet_outcome, 
                        amount_won, 
                        amount_lost)
            
            return bet_info
        
        async def append_result(is_winner):
            if is_winner == 'win':
                winning_bets.append(await win_loss_info('win'))

            elif is_winner == 'loss':
                losing_bets.append(await win_loss_info('loss'))

            else:
                pushed_bets.append(await win_loss_info('push'))

        if bet_type == 'Spread':
            placed_neg_or_pos = bet_value[0]
            placed_value = float(bet_value[1:])
            is_winner = 'loss'
            
            if placed_neg_or_pos == '-':
                if match_winner_id == match_favorite_id and spread > placed_value:
                    is_winner = 'win'
                elif match_winner_id == match_favorite_id and spread == placed_value:
                    is_winner = 'push'
            elif placed_neg_or_pos == '+':
                if match_winner_id != match_favorite_id or spread < placed_value:
                    is_winner = 'win'
                elif spread == placed_value:
                    is_winner = 'push'
                
            await append_result(is_winner)

        elif bet_type == 'Moneyline':
            is_winner = 'loss'

            if playerid_bet_on == match_winner_id:
                is_winner = 'win'

            await append_result(is_winner)

        elif bet_type == 'O/U':
            placed_o_or_u = bet_value[0]
            placed_value = float(bet_value[1:])
            is_winner = 'loss'

            if (placed_o_or_u == 'O' and total_rounds > placed_value) or (placed_o_or_u == 'U' and total_rounds < placed_value):
                is_winner = 'win'

            if total_rounds == placed_value:
                is_winner = 'push'

            await append_result(is_winner)

    all_bets = winning_bets + losing_bets + pushed_bets

    return all_bets, winning_bets, pushed_bets

async def handle_bet_payouts(match_id, player1_name, player2_name, match_winner_id, spread, total_rounds, db):
    
    try:
        
        bets, match_title = await check_match_titles(player1_name, player2_name, db)
        
        if not bets:
            return False

        all_bets, winning_bets, pushed_bets = await win_loss_determination(bets, match_id, spread, match_winner_id, total_rounds)
        
        # Insert the bets into the past_bets table
        await db.executemany(
            """
            INSERT INTO past_bets (user_id, match_id, match_title, match_favorite_id, match_underdog_id, playerid_bet_on, bet_type, bet_value, bet_odds, bet_amount, bet_outcome, amount_won, amount_lost)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, all_bets
        )

        # Handle bets that won
        if len(winning_bets)>0:
            win_updates = [(bet[11], bet[0]) for bet in winning_bets]

            async with db.executemany(
                "UPDATE players SET straftcoins = straftcoins + ? WHERE user_id = ?", win_updates
            ):
                pass
        
        # Handle bets that pushed
        if len(pushed_bets) > 0:
            push_updates = [(bet[9], bet[0]) for bet in pushed_bets]

            async with db.executemany(
                "UPDATE players SET straftcoins = straftcoins + ? WHERE user_id = ?", push_updates
            ):
                pass

        # Remove the bets from the live_bets table
        await db.execute(
            "DELETE FROM live_bets WHERE match_title = ?", (match_title,)
        )

        # Commit the transaction
        await db.commit()

        bet_settlements_message = ''
        
        emojis = await get_emoji(['Poggers', 'KEKW', 'Straftcoin'])

        for user_id, match_id, match_title, _, _, _, bet_type, bet_value, bet_odds, bet_amount, bet_outcome, amount_won, _ in all_bets:
            bettor = f'<@{user_id}>'
            new_straftcoin_balance = await get_straftcoin(db, user_id)

            if bet_outcome == 'win':
                bet_settlements_message += f"{bettor}: **Bet Won** {emojis[0]}\n- Bet: {bet_type} (**{bet_value}**, {bet_amount}{emojis[2]}, {'+' if bet_odds > 0 else ''}{bet_odds} odds)\n- Amount Won: {amount_won}{emojis[2]}\n- Balance: {new_straftcoin_balance}{emojis[2]}\n"
            if bet_outcome == 'loss':
                bet_settlements_message += f"{bettor}: **Bet Lost** {emojis[1]}\n- Bet: {bet_type} (**{bet_value}**, {bet_amount}{emojis[2]}, {'+' if bet_odds > 0 else ''}{bet_odds} odds)\n- Balance: {new_straftcoin_balance}{emojis[2]}\n"
            if bet_outcome == 'push':
                bet_settlements_message += f"{bettor}: **Bet Pushed** {emojis[1]}\n- Bet: {bet_type} (**{bet_value}**, {bet_amount}{emojis[2]}, {'+' if bet_odds > 0 else ''}{bet_odds} odds)\n- Amount Returned: {bet_amount}{emojis[2]}\n- Balance: {new_straftcoin_balance}{emojis[2]}\n"

        return bet_settlements_message

    except Exception as e:
        # Rollback in case of an error
        await db.rollback()
        await print(f"An error occurred while recording the match: {e}")

async def get_matchup_data(playerid, db):
    async with db.execute("""
        SELECT 
            CASE WHEN winner_id = ? THEN loser_id ELSE winner_id END AS opponent_id,
            SUM(CASE WHEN winner_id = ? THEN 1 ELSE 0 END) AS wins_against,
            SUM(CASE WHEN loser_id = ? THEN 1 ELSE 0 END) AS losses_against,
            SUM(CASE WHEN winner_id = ? THEN winner_rounds ELSE loser_rounds END) AS rounds_won_against,
            SUM(CASE WHEN winner_id = ? THEN loser_rounds ELSE 0 END) AS rounds_lost_against, 
            AVG(CASE WHEN winner_id = ? THEN spread ELSE NULL END) AS avg_winning_spread,   
            AVG(CASE WHEN loser_id = ? THEN spread ELSE NULL END) AS avg_losing_spread 
        FROM matches
        WHERE winner_id = ? OR loser_id = ?
        GROUP BY opponent_id
    """, (playerid, playerid, playerid, playerid, playerid, playerid, playerid, playerid, playerid)) as cursor:
        rows = await cursor.fetchall()
    
    return rows

async def get_player_stats(playerid, db):
    player_cursor = await db.execute("SELECT wins, losses, rounds_won, rounds_lost FROM players WHERE user_id = ?", (playerid,))
    player = await player_cursor.fetchone()

    async with db.execute('''
        SELECT 
            AVG(CASE WHEN winner_id = ? THEN spread ELSE NULL END) AS avg_winning_spread,
            AVG(CASE WHEN loser_id = ? THEN spread ELSE NULL END) AS avg_losing_spread
        FROM matches 
        WHERE winner_id = ? OR loser_id = ?
    ''', (playerid, playerid, playerid, playerid)) as spread_cursor:
        player_spread = await spread_cursor.fetchone()
        
    return player, player_spread

async def calc_performance_score(playerid, op_id, db):
        
        player, player_spread = await get_player_stats(playerid, db)

        total_wins, total_losses, tot_rounds_won, tot_rounds_lost = player
        avg_winning_spread, avg_losing_spread  = player_spread

        if total_wins == 0 and total_losses == 0:
            return 10

        avg_winning_spread = player_spread[0] if player_spread[0] is not None else 0
        avg_losing_spread = player_spread[1] if player_spread[1] is not None else 0
        
        tot_matches = total_wins + total_losses
        tot_rounds = tot_rounds_won + tot_rounds_lost

        tot_win_ratio = total_wins / tot_matches if tot_matches > 0 else 0
        rounds_won_ratio = tot_rounds_won / tot_rounds if tot_rounds > 0 else 0
        
        winning_spread_ratio = avg_winning_spread / 10 if avg_winning_spread > 0 else 0
        losing_spread_ratio = avg_losing_spread / 10 if avg_losing_spread > 0 else 0

        match_stabilization = tot_matches / (tot_matches + 10)
        
        W1, W2, W3, W4, W5 = 50, 20, 10, 15, 5

        performance_score = (
            (W1 * tot_win_ratio) +
            (W2 * winning_spread_ratio) -
            (W3 * losing_spread_ratio) +
            (W4 * rounds_won_ratio) +
            (W5 * match_stabilization)
        )
        
        rows = await get_matchup_data(playerid, db)
        
        if rows:
            for row in rows:
                opponent_id, wins, losses, rounds_won, rounds_lost, avg_win_spread_v_op, avg_loss_spread_v_op = row
                if opponent_id == op_id:
                    tot_op_matches = wins + losses
                    tot_op_rounds = rounds_won + rounds_lost

                    avg_win_spread_v_op = avg_win_spread_v_op if avg_win_spread_v_op is not None else 0
                    avg_loss_spread_v_op = avg_loss_spread_v_op if avg_loss_spread_v_op is not None else 0

                    win_ratio_v_op = wins / tot_op_matches if tot_op_matches > 0 else 0
                    round_ratio_v_op = rounds_won / tot_op_rounds if tot_op_rounds > 0 else 0
                    
                    winning_spread_ratio_v_op = avg_win_spread_v_op / 10
                    losing_spread_ratio_v_op = avg_loss_spread_v_op / 10

                    match_stabilization_v_op = tot_op_matches / (tot_op_matches + 10)

                    W6, W7, W8, W9, W10 = 50, 20, 10, 15, 5
                    
                    performance_score = performance_score + (
                        (W6 * win_ratio_v_op) +
                        (W7 * winning_spread_ratio_v_op) -
                        (W8 * losing_spread_ratio_v_op) +
                        (W9 * round_ratio_v_op) +
                        (W10 * match_stabilization_v_op)
                    )

        return performance_score

async def calculate_win_probability(score_a, score_b, scaling_factor=100):
    probability_a = round(1 / (1 + 10 ** ((score_b - score_a) / scaling_factor)), 2)
    probability_b = round(1 - probability_a, 2)
    return probability_a, probability_b