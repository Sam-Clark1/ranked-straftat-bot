from datetime import datetime

#get ranks based on sp number
async def get_ranks():
    
    RANKS = [
        (0, "Shitterton IV"),
        (200, "Shitterton III"),
        (400, "Shitterton II"),
        (600, "Shitterton I"),
        (800, "Bronze IV"),
        (1000, "Bronze III"),
        (1200, "Bronze II"),
        (1400, "Bronze I"),
        (1600, "Silver IV"),
        (1800, "Silver III"),
        (2000, "Silver II"),
        (2200, "Silver I"),
        (2400, "Gold IV"),
        (2600, "Gold III"),
        (2800, "Gold II"),
        (3000, "Gold I"),
        (3200, "Platinum IV"),
        (3400, "Platinum III"),
        (3600, "Platinum II"),
        (3800, "Platinum I"),
        (4000, "Diamond IV"),
        (4200, "Diamond III"),
        (4400, "Diamond II"),
        (4600, "Diamond I"),
        (4800, "Daddy")
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
        emoji_name_base = emoji_name.split()
        emoji = EMOJIS.get(emoji_name_base[0]) 
        emojis_list.append(emoji)

    return emojis_list

# Determine rank based on SP
async def get_rank(sp):
    ranks = await get_ranks()
    for threshold, rank in reversed(ranks):
        if sp >= threshold:
            rank_emote = await get_emoji([rank])
            return rank, rank_emote[0]
        
    shitterton_emote = await get_emoji(["Shitterton"])
    return "Shitterton IV", shitterton_emote[0]

#get server specific display names of players from their user id
async def get_display_name(ctx, user_id):
    member = ctx.guild.get_member(user_id)
    username = member.display_name if member else f"User ID {user_id}"
    return username

#get current sp value for specific player
async def get_sp(db, player_id, mode='1v1'):
    col = 'sp_1v1' if mode == '1v1' else 'sp_mp'
    row = await db.execute(f"SELECT {col} FROM players WHERE user_id = ?", (player_id,))
    result = await row.fetchone()
    return result[0] if result else 0

#get current elo rating for specific player
async def get_rating(db, player_id, mode='1v1'):
    col = 'rating_1v1' if mode == '1v1' else 'rating_mp'
    row = await db.execute(f"SELECT {col} FROM players WHERE user_id = ?", (player_id,))
    result = await row.fetchone()
    return result[0] if result else 1000

#get current straftat balance for specific player
async def get_straftcoin(db, user_id):
    cursor = await db.execute("SELECT straftcoins FROM players WHERE user_id = ?", (user_id,))
    row = await cursor.fetchone()
    return row[0] if row else 1000

#get current highest rank achieved for specific player
async def get_highest_rank_achieved(db, user_id):
    cursor = await db.execute("SELECT highest_rank_achieved FROM players WHERE user_id = ?", (user_id,))
    row = await cursor.fetchone()
    return row[0] if row else 'Shitterton IV'

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
async def handle_inputted_players(player_ids, db):
    for player_id in player_ids:
        await db.execute("""
            INSERT OR IGNORE INTO players (
                user_id,
                rating_1v1, sp_1v1, rank_1v1,
                wins_1v1, losses_1v1,
                rounds_won_1v1, rounds_lost_1v1,
                highest_rank_1v1, highest_sp_1v1,
                rating_mp, sp_mp, rank_mp,
                wins_mp, losses_mp,
                rounds_won_mp, rounds_lost_mp,
                highest_rank_mp, highest_sp_mp,
                straftcoins
            ) VALUES (
                ?,
                1000, 0, 'Unranked',
                0, 0, 0, 0,
                'Unranked', 0,
                1000, 0, 'Unranked',
                0, 0, 0, 0,
                'Unranked', 0,
                1000
            )
        """, (player_id,))
    await db.commit()

# Calculate Elo change
async def calculate_elo(winner_rounds, loser_rounds, rating1, rating2):
    K_FACTOR = 80  # Elo constant
    round_ratio = (winner_rounds - loser_rounds) / 10
    round_adjustment = (K_FACTOR/4)*round_ratio

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
    (0.95, 100), (0.85, 110), (0.80, 120), (0.70, 120), (0.65, 120), (0.60, 130), 
    (0.55, 130), (0.50, 150), (0.40, 150), (0.30, 160), (0.20, 200), 
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
    (0.95, 4000, 0.95), (0.85, 5000, 0.9), (0.80, 5200, 0.8), (0.70, 5400, 0.7), 
    (0.65, 5600, 0.8), (0.60, 5800, 0.8), (0.55, 6000, 0.8), (0.50, 6200, 0.8), 
    (0.40, 6400, 0.8), (0.30, 6600, 0.8), (0.20, 6800, 0.8), (0.10, 7000, 0.8)
    ]

    for threshold, straftcoin, percentage in thresholds:
        if expected_score >= threshold:
            base_straftcoin = straftcoin
            loser_percent_cut = percentage
            break
    else:
        base_straftcoin = 10000
        loser_percent_cut = 0.8

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

async def match_to_db(player_rounds, rounds_to_win, db):
    """
    player_rounds : list of (player_id, rounds_won) tuples, sorted descending by rounds_won
    rounds_to_win : int
    db            : active aiosqlite connection

    Returns list of result dicts sorted by placement (1st first).
    """

    ELO_K = 32

    # --- Determine mode from player count ---
    game_mode = '1v1' if len(player_rounds) == 2 else 'mp'

    # --- SP tables (MP only — 1v1 uses Elo-derived SP) ---
    MP_SP_BY_PLACEMENT = {1: 50, 2: 25, 3: 10, 4: -5, 5: -10}
    MP_SP_FLOOR = -15

    MP_SC_BY_PLACEMENT = {1: 100, 2: 50, 3: 30, 4: 15, 5: 10}
    MP_SC_FLOOR = 5

    player_ids = [pid for pid, _ in player_rounds]

    await handle_inputted_players(player_ids, db)

    # --- Determine placements ---
    sorted_players = sorted(player_rounds, key=lambda x: x[1], reverse=True)

    placements = []
    for i, (pid, rounds) in enumerate(sorted_players):
        if i > 0 and rounds == sorted_players[i - 1][1]:
            placements.append((pid, rounds, placements[-1][2]))  # tied placement
        else:
            placements.append((pid, rounds, i + 1))

    total_rounds = sum(r for _, r in player_rounds)

    # --- Insert match row ---
    cursor = await db.execute(
        "INSERT INTO matches (rounds_to_win, total_rounds, game_mode) VALUES (?, ?, ?)",
        (rounds_to_win, total_rounds, game_mode)
    )
    match_id = cursor.lastrowid

    # --- Fetch current ratings ---
    ratings = {}
    for pid in player_ids:
        ratings[pid] = await get_rating(db, pid, mode=game_mode)

    # --- Pairwise Elo (same for both modes) ---
    elo_changes = {pid: 0.0 for pid in player_ids}

    for i in range(len(placements)):
        for j in range(i + 1, len(placements)):
            pid_a, _, place_a = placements[i]
            pid_b, _, place_b = placements[j]

            expected_a = 1 / (1 + 10 ** ((ratings[pid_b] - ratings[pid_a]) / 400))
            expected_b = 1 - expected_a

            elo_changes[pid_a] += ELO_K * (1 - expected_a)
            elo_changes[pid_b] += ELO_K * (0 - expected_b)

    # --- Per-player SP: 1v1 derives from Elo, MP uses placement table ---
    def get_1v1_sp(elo_change):
        """Scale Elo gain/loss directly into SP with a floor/ceiling."""
        if elo_change >= 0:
            return max(5, round(elo_change * 1.5))
        else:
            return min(-5, round(elo_change * 1.5))

    # --- Apply changes ---
    results = []

    for pid, rounds_won, placement in placements:
        elo_change = round(elo_changes[pid], 2)
        is_winner = placement == 1

        if game_mode == '1v1':
            sp_change = get_1v1_sp(elo_change)
            straftcoin_change = 100 if is_winner else 30
            sp_col         = 'sp_1v1'
            rating_col     = 'rating_1v1'
            rank_col       = 'rank_1v1'
            wins_col       = 'wins_1v1'
            losses_col     = 'losses_1v1'
            rw_col         = 'rounds_won_1v1'
            rl_col         = 'rounds_lost_1v1'
            hr_col         = 'highest_rank_1v1'
            hsp_col        = 'highest_sp_1v1'
        else:
            sp_change = MP_SP_BY_PLACEMENT.get(placement, MP_SP_FLOOR)
            straftcoin_change = MP_SC_BY_PLACEMENT.get(placement, MP_SC_FLOOR)
            sp_col         = 'sp_mp'
            rating_col     = 'rating_mp'
            rank_col       = 'rank_mp'
            wins_col       = 'wins_mp'
            losses_col     = 'losses_mp'
            rw_col         = 'rounds_won_mp'
            rl_col         = 'rounds_lost_mp'
            hr_col         = 'highest_rank_mp'
            hsp_col        = 'highest_sp_mp'

        row = await db.execute(
            f"SELECT {rating_col}, {sp_col}, straftcoins FROM players WHERE user_id = ?",
            (pid,)
        )
        current = await row.fetchone()
        current_rating, current_sp, current_straftcoins = current

        new_rating     = current_rating + elo_change
        new_sp         = max(0, current_sp + sp_change)
        new_straftcoins = max(0, current_straftcoins + straftcoin_change)
        new_rank, rank_emoji = await get_rank(new_sp)

        rounds_lost_in_match = total_rounds - rounds_won

        await db.execute(f"""
            UPDATE players SET
                {rating_col}   = ?,
                {sp_col}       = ?,
                {rank_col}     = ?,
                {wins_col}     = {wins_col} + ?,
                {losses_col}   = {losses_col} + ?,
                {rw_col}       = {rw_col} + ?,
                {rl_col}       = {rl_col} + ?,
                straftcoins    = ?,
                {hr_col}       = CASE WHEN ? > {hsp_col} THEN ? ELSE {hr_col} END,
                {hsp_col}      = CASE WHEN ? > {hsp_col} THEN ? ELSE {hsp_col} END
            WHERE user_id = ?
        """, (
            new_rating, new_sp, new_rank,
            1 if is_winner else 0,
            0 if is_winner else 1,
            rounds_won,
            rounds_lost_in_match,
            new_straftcoins,
            new_sp, new_rank,
            new_sp, new_sp,
            pid
        ))

        await db.execute("""
            INSERT INTO match_participants
                (match_id, player_id, placement, rounds_won, elo_change, sp_change, straftcoin_change)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (match_id, pid, placement, rounds_won, elo_change, sp_change, straftcoin_change))

        results.append({
            'match_id':          match_id,
            'game_mode':         game_mode,
            'player_id':         pid,
            'placement':         placement,
            'rounds_won':        rounds_won,
            'sp_change':         sp_change,
            'new_sp':            new_sp,
            'elo_change':        elo_change,
            'straftcoin_change': straftcoin_change,
            'new_straftcoins':   new_straftcoins,
            'rank':              new_rank,
            'rank_emoji':        rank_emoji,
        })

    await db.commit()
    return sorted(results, key=lambda x: x['placement'])