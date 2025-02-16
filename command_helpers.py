from datetime import datetime

#get ranks based on sp number
async def get_ranks():
    RANKS = [
        (0, "Shitterton"),
        (500, "Bronze"),
        (1000, "Silver"),
        (1500, "Gold"),
        (2000, "Platinum"),
        (2500, "Diamond"),
        (3000, "Daddy")
    ]
    return RANKS

#get emojis for each rank
async def get_emoji(desired_emoji_names):
    EMOJIS = {
        "Shitterton": "<:neilLet:834091985547689984>",
        "Bronze": "🥉",
        "Silver": "🥈",
        "Gold": "🥇",
        "Platinum": "💍",
        "Diamond": "💎",
        "Daddy": "<:PogSam:983164966809002036>", 
        "Poggers": "<:POGGERS:834061791571083315>",
        "KEKW": "<:KEKW:834061671973781504>", 
        'Straftcoin': "<:straftcoin:1329553425217622076>"
    }
    
    emojis_list = []
    for emoji_name in desired_emoji_names:
        emoji = EMOJIS.get(emoji_name) 
        emojis_list.append(emoji)

    return emojis_list

# Determine rank based on SP
async def get_rank(sp):
    ranks = await get_ranks()
    for threshold, rank in reversed(ranks):
        if sp >= threshold:
            rank_emote = await get_emoji([rank])
            return rank, rank_emote[0]
    return "Shitterton"

#get server specific display names of players from their user id
async def get_display_name(ctx, user_id):
    member = ctx.guild.get_member(user_id)
    username = member.display_name if member else f"User ID {user_id}"
    return username

#get current sp value for specific player
async def get_sp(db, user_id):
    cursor = await db.execute("SELECT sp FROM players WHERE user_id = ?", (user_id,))
    row = await cursor.fetchone()
    return row[0] if row else 0

#get current elo rating for specific player
async def get_rating(db, user_id):
    cursor = await db.execute("SELECT rating FROM players WHERE user_id = ?", (user_id,))
    row = await cursor.fetchone()
    return row[0] if row else 1000

#get current straftat balance for specific player
async def get_straftcoin(db, user_id):
    cursor = await db.execute("SELECT straftcoins FROM players WHERE user_id = ?", (user_id,))
    row = await cursor.fetchone()
    return row[0] if row else 1000

#get current highest rank achieved for specific player
async def get_highest_rank_achieved(db, user_id):
    cursor = await db.execute("SELECT highest_rank_achieved FROM players WHERE user_id = ?", (user_id,))
    row = await cursor.fetchone()
    return row[0] if row else 'Shitterton'

#get current highest sp achieved for specific player
async def get_highest_sp_achieved(db, user_id):
    cursor = await db.execute("SELECT highest_sp_achieved FROM players WHERE user_id = ?", (user_id,))
    row = await cursor.fetchone()
    return row[0] if row else 0

async def get_players(db):
    async with db.execute("SELECT user_id, straftcoins FROM players") as cursor:
        players = await cursor.fetchall()

    if not players:
        return False
    
    return players

async def get_player_matches(db, user_id):
    player_wins_cursor = await db.execute("SELECT * FROM matches WHERE winner_id = ?", (user_id,))
    player_losses_cursor = await db.execute("SELECT * FROM matches WHERE loser_id = ?", (user_id,))

    player_wins = await player_wins_cursor.fetchone()
    player_losses = await player_losses_cursor.fetchone()
    
    if player_wins or player_losses:
        return True
    else:
        return False 

# checks if players are in players table and adds if they aren't
async def handle_inputted_players(players, db):
    
    for player in players:
        cursor = await db.execute("SELECT * FROM players WHERE user_id = ?", (player,))
        result = await cursor.fetchone()

        if result:
            continue
        else:
            await db.execute(
                "INSERT INTO players (user_id) VALUES (?)",
                (player,)
            )

# Calculate Elo change
async def calculate_elo(winner_rounds, loser_rounds, rating1, rating2):
    K_FACTOR = 100  # Elo constant
    round_ratio = (winner_rounds - loser_rounds) / 10
    round_adjustment = (K_FACTOR/5)*round_ratio

    winner_expected_score = 1 / (1 + 10 ** ((rating2 - rating1) / 400))
    loser_expected_score = 1 / (1 + 10 ** ((rating1 - rating2) / 400))

    winner_elo_change =int(K_FACTOR * (1 - winner_expected_score)) + round_adjustment
    loser_elo_change =abs(int(K_FACTOR * (0 - loser_expected_score))) + round_adjustment

    return winner_elo_change, loser_elo_change, winner_expected_score, loser_expected_score

# Calculate SP changes
async def calculate_sp_changes(winner_rating, loser_rating, winner_rounds, loser_rounds, expected_score):
    
    elo_difference = loser_rating - winner_rating
    elo_difference_percentage = loser_rating / winner_rating
    
    round_ratio = (winner_rounds - loser_rounds) / 10  # Normalize to a scale of -1 to 1
    
    thresholds = [
    (0.95, 110), (0.85, 120), (0.80, 140), (0.70, 160), (0.65, 160), (0.60, 170), 
    (0.55, 180), (0.50, 200), (0.40, 200), (0.30, 200), (0.20, 200), 
    (0.10, 200)
    ]

    for threshold, sp in thresholds:
        if expected_score >= threshold:
            base_sp = sp
            break
    else:
        base_sp = 250
    
    sp_for_round_ratio = int(round(base_sp / 4))
    
    # Winner SP calculation
    winner_sp_change = int(max(0, (base_sp + (elo_difference / 7.5))) + (round_ratio * sp_for_round_ratio))
    
    winner_sp_change = int(round(winner_sp_change))  # Ensure at least 1 SP is gained
     
    # Loser SP calculation
    loser_sp_change = int(winner_sp_change * 0.35)  # Loser loses 50% of what the winner gains

    loser_sp_change = loser_sp_change * elo_difference_percentage
    
    loser_sp_change = int(round(loser_sp_change))  # Ensure SP loss is non-negative
    
    return winner_sp_change, loser_sp_change

# Calculate Straftat changes
async def calculate_straftcoin_changes(winner_rounds, loser_rounds, expected_score):
    
    round_ratio = (winner_rounds - loser_rounds) / 10

    thresholds = [
    (0.95, 1000, 0.95), (0.85, 1100, 0.9), (0.80, 1200, 0.8), (0.70, 1300, 0.7), 
    (0.65, 1400, 0.6), (0.60, 1500, 0.6), (0.55, 1600, 0.5), (0.50, 1700, 0.5), 
    (0.40, 1800, 0.5), (0.30, 1900, 0.5), (0.20, 2000, 0.5), (0.10, 2100, 0.5)
    ]

    for threshold, straftcoin, percentage in thresholds:
        if expected_score >= threshold:
            base_straftcoin = straftcoin
            loser_percent_cut = percentage
            break
    else:
        base_straftcoin = 2500
        loser_percent_cut = 0.5

    straftcoin_for_round_ratio = int(round(base_straftcoin / 4))

    winner_straftcoin_change = base_straftcoin + (straftcoin_for_round_ratio * round_ratio)
    winner_straftcoin_change = int(round(max(winner_straftcoin_change, 0)))

    loser_straftcoin_change = (base_straftcoin * loser_percent_cut) + (straftcoin_for_round_ratio * (abs(round_ratio-1)))
    loser_straftcoin_change = int(round(max(loser_straftcoin_change, 0)))

    return winner_straftcoin_change, loser_straftcoin_change

async def add_player_to_db(player_id, player_new_rating, player_new_sp, player_rank, winner_rounds, loser_rounds, player_new_straftcoins, outcome, db):

    if outcome == 'winner':
        winr_or_lsr_rounds = [winner_rounds, loser_rounds]
        outcome_table_identifier = 'wins'
    elif outcome == 'loser':
        winr_or_lsr_rounds = [loser_rounds, winner_rounds]
        outcome_table_identifier = 'losses'
    
    current_highest_rank_achieved = await get_highest_rank_achieved(db, player_id)
    current_highest_sp_achieved = await get_highest_sp_achieved(db, player_id)
    
    if player_new_sp > current_highest_sp_achieved:
        current_highest_rank_achieved = player_rank
        current_highest_sp_achieved = player_new_sp

    variables = (player_new_rating, player_new_sp, 
                 player_rank, 
                 winr_or_lsr_rounds[0], 
                 winr_or_lsr_rounds[1], 
                 player_new_straftcoins,
                 current_highest_rank_achieved,
                 current_highest_sp_achieved,
                 player_id)
    
    await db.execute(f"""
    UPDATE players SET 
        rating = ?,
        sp = ?,
        rank = ?,
        {outcome_table_identifier} = {outcome_table_identifier} + 1,
        rounds_won = rounds_won + ?,
        rounds_lost = rounds_lost + ?,
        straftcoins = ?,
        highest_rank_achieved = ?,
        highest_sp_achieved = ?
        WHERE user_id = ?                 
    """, variables)
    
    await db.commit()

async def match_to_db(winner_id, loser_id, winner_rounds, loser_rounds, db):

    # Checks if players are in players table and if not, add
    await handle_inputted_players([winner_id, loser_id], db)

    # Fetch ratings
    winner_row = await db.execute("SELECT rating, sp, straftcoins FROM players WHERE user_id = ?", (winner_id,))
    loser_row = await db.execute("SELECT rating, sp, straftcoins FROM players WHERE user_id = ?", (loser_id,))

    winner_data = await winner_row.fetchone()
    loser_data = await loser_row.fetchone()

    winner_rating, winner_sp, winner_straftcoins = winner_data
    loser_rating, loser_sp, loser_straftcoins = loser_data

    # Calculate Elo changes
    winner_elo_change, loser_elo_change, winner_expected_score, _ = await calculate_elo(winner_rounds, loser_rounds, winner_rating, loser_rating)
    
    # Update player stats
    winner_new_rating = max(winner_rating + winner_elo_change, 0)  # Ensure rating doesn't go below 0
    loser_new_rating = max(loser_rating - loser_elo_change, 0)  # Ensure rating doesn't go below 0

    if loser_new_rating == 0:
        loser_elo_change = 0

    # Calculate SP changes
    winner_sp_change, loser_sp_change = await calculate_sp_changes(winner_rating, loser_rating, winner_rounds, loser_rounds, winner_expected_score)

    # Update player stats
    winner_new_sp = max(winner_sp + winner_sp_change, 0)  # Ensure SP doesn't go below 0
    loser_new_sp = max(loser_sp - loser_sp_change, 0)  # Ensure SP doesn't go below 0

    if loser_new_sp == 0:
        loser_sp_change = 0
    
    # Caculate straftcoin changes
    winner_straftcoin_change, loser_straftcoin_change = await calculate_straftcoin_changes(winner_rounds, loser_rounds, winner_expected_score)

    # Update straftcoin stats
    winner_new_straftcoins = max(winner_straftcoins + winner_straftcoin_change, 0)
    loser_new_straftcoins = max(loser_straftcoins + loser_straftcoin_change, 0)

    # Get updated ranks
    winner_rank, winner_emoji = await get_rank(winner_new_sp)
    loser_rank, loser_emoji = await get_rank(loser_new_sp)
    
    # Calculate spread of match
    spread = winner_rounds - loser_rounds

    # Calculate total rounds in match
    total_rounds = winner_rounds + loser_rounds
    
    #add winner to db
    await add_player_to_db(winner_id, winner_new_rating, winner_new_sp, winner_rank, winner_rounds, loser_rounds, winner_new_straftcoins, 'winner', db)

    #add loser to db
    await add_player_to_db(loser_id, loser_new_rating, loser_new_sp, loser_rank, winner_rounds, loser_rounds, loser_new_straftcoins, 'loser', db)

    # Log the match
    await db.execute("""
        INSERT INTO matches (
            winner_id, loser_id, winner_rounds, loser_rounds, 
            winner_elo_change, loser_elo_change, winner_sp_change, 
            loser_sp_change, timestamp, outcome, spread, total_rounds, 
            winner_straftcoin_change, loser_straftcoin_change
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (winner_id, loser_id, winner_rounds, loser_rounds, 
        winner_elo_change, -loser_elo_change, winner_sp_change, -loser_sp_change, 
        datetime.now().isoformat(), winner_id, spread, total_rounds, 
        winner_straftcoin_change, loser_straftcoin_change))

    await db.commit()

    cursor = await db.execute('SELECT match_id FROM matches ORDER BY match_id DESC LIMIT 1;')
    result = await cursor.fetchone()
    match_id = result[0]

    return winner_sp_change, winner_new_sp, winner_straftcoin_change, winner_new_straftcoins, winner_rank, winner_emoji, loser_sp_change, loser_new_sp, loser_straftcoin_change, loser_new_straftcoins, loser_rank, loser_emoji, spread, total_rounds, match_id