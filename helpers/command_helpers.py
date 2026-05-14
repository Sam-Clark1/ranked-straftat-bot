import math
from datetime import datetime

def chunk_message(text, max_len=1900):
    """Split text into chunks that fit within Discord's 2000-char message limit."""
    chunks = []
    while len(text) > max_len:
        split_at = text.rfind('\n', 0, max_len)
        if split_at == -1:
            split_at = max_len
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip('\n')
    if text:
        chunks.append(text)
    return chunks

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

async def get_players(db):
    async with db.execute("SELECT user_id, straftcoins FROM players") as cursor:
        players = await cursor.fetchall()

    if not players:
        return False
    
    return players

async def get_player_matches(db, user_id):
    cursor = await db.execute(
        "SELECT participant_id FROM match_participants WHERE player_id = ? LIMIT 1",
        (user_id,)
    )
    result = await cursor.fetchone()
    return result is not None

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
                1000, 0, 'Shitterton IV',
                0, 0, 0, 0,
                'Shitterton IV', 0,
                1000, 0, 'Shitterton IV',
                0, 0, 0, 0,
                'Shitterton IV', 0,
                1000
            )
        """, (player_id,))
    await db.commit()

async def match_to_db(player_rounds, rounds_to_win, db):
    """
    player_rounds : list of (player_id, rounds_won) tuples, sorted descending by rounds_won
    rounds_to_win : int
    db            : active aiosqlite connection

    Returns list of result dicts sorted by placement (1st first).
    """

    ELO_K = 100

    # --- Determine mode from player count ---
    game_mode = '1v1' if len(player_rounds) == 2 else 'mp'

    # --- SP threshold table: expected_score → base SP for winner/1st ---
    SP_THRESHOLDS = [
        (0.95, 110), (0.85, 120), (0.80, 140), (0.70, 150),
        (0.65, 200), (0.60, 250), (0.55, 275), (0.50, 300),
        (0.40, 325), (0.30, 350), (0.20, 375), (0.10, 400),
    ]

    # --- SC threshold table: expected_score → (base SC, loser SC fraction) ---
    SC_THRESHOLDS = [
        (0.95, 4000, 0.95), (0.85, 5000, 0.90), (0.80, 5200, 0.85),
        (0.70, 5400, 0.80), (0.65, 5600, 0.775), (0.60, 5800, 0.75),
        (0.55, 6000, 0.725), (0.50, 6200, 0.7), (0.40, 6400, 0.675),
        (0.30, 6600, 0.65), (0.20, 6800, 0.625), (0.10, 7000, 0.6),
    ]

    def _sp_lookup(expected):
        for threshold, sp in SP_THRESHOLDS:
            if expected >= threshold:
                return sp
        return 500

    def _sc_lookup(expected):
        for threshold, sc, pct in SC_THRESHOLDS:
            if expected >= threshold:
                return sc, pct
        return 10000, 0.5

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

    # --- Pairwise Elo with round-margin adjustment ---
    elo_changes = {pid: 0.0 for pid in player_ids}

    for i in range(len(placements)):
        for j in range(i + 1, len(placements)):
            pid_a, rounds_a, _ = placements[i]
            pid_b, rounds_b, _ = placements[j]

            expected_a     = 1 / (1 + 10 ** ((ratings[pid_b] - ratings[pid_a]) / 400))
            round_ratio    = (rounds_a - rounds_b) / rounds_to_win
            round_adj      = (ELO_K / 5) * round_ratio  # ±20 max, zero-sum

            if game_mode == 'mp':
                pair_total = rounds_a + rounds_b
                actual_a   = rounds_a / pair_total if pair_total > 0 else 0.5
            else:
                actual_a = 1.0

            elo_changes[pid_a] += ELO_K * (actual_a - expected_a) + round_adj
            elo_changes[pid_b] += ELO_K * ((1 - actual_a) - (1 - expected_a)) - round_adj

    # --- Pre-compute winner expected score and SP/SC for the match ---
    pid_1st, rounds_1st, _ = placements[0]

    if game_mode == '1v1':
        pid_2nd, rounds_2nd, _ = placements[1]
        exp_winner       = 1 / (1 + 10 ** ((ratings[pid_2nd] - ratings[pid_1st]) / 400))
        winner_elo_diff  = ratings[pid_2nd] - ratings[pid_1st]   # +ve if underdog won
        winner_rnd_ratio = (rounds_1st - rounds_2nd) / rounds_to_win
        loser_rating_ref = ratings[pid_2nd]
    else:
        other_pids       = [pid for pid, _, pl in placements if pl != 1]
        avg_other_rating = sum(ratings[p] for p in other_pids) / len(other_pids)
        exp_winner       = 1 / (1 + 10 ** ((avg_other_rating - ratings[pid_1st]) / 400))
        winner_elo_diff  = avg_other_rating - ratings[pid_1st]
        avg_other_rounds = sum(r for _, r, pl in placements if pl != 1) / len(other_pids)
        winner_rnd_ratio = (rounds_1st - avg_other_rounds) / rounds_to_win
        loser_rating_ref = avg_other_rating

    base_sp      = _sp_lookup(exp_winner)
    sp_ratio     = base_sp // 4
    winner_sp    = int(max(5, base_sp + (winner_elo_diff / 7.5) + (winner_rnd_ratio * sp_ratio)))

    base_sc, loser_sc_pct = _sc_lookup(exp_winner)
    sc_ratio     = base_sc // 4
    winner_sc    = int(max(0, base_sc + (sc_ratio * winner_rnd_ratio)))
    loser_sc_raw = int(max(0, base_sc * loser_sc_pct + sc_ratio * (1 - abs(winner_rnd_ratio))))

    winner_rating_ref = ratings[pid_1st]
    elo_diff_pct      = loser_rating_ref / winner_rating_ref if winner_rating_ref > 0 else 1.0
    loser_sp_full     = -int(max(5, winner_sp * 0.17 * elo_diff_pct))

    # --- Apply changes ---
    results = []

    for pid, rounds_won, placement in placements:
        elo_change = round(elo_changes[pid], 2)
        is_winner  = placement == 1

        if game_mode == '1v1':
            sp_change         = winner_sp if is_winner else loser_sp_full
            straftcoin_change = winner_sc if is_winner else loser_sc_raw
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
            # SP: top ceil(n/2) placements gain, rest lose
            n_players   = len(placements)
            gain_cutoff = math.ceil(n_players / 2)

            if placement <= gain_cutoff:
                # Gainers: 1st gets winner_sp, last gainer gets 25% of winner_sp
                if gain_cutoff == 1:
                    sp_change = winner_sp
                else:
                    frac = 1.0 - ((placement - 1) / (gain_cutoff - 1)) * 0.575
                    sp_change = max(1, int(winner_sp * frac))
            else:
                # Losers: first loser gets 25% of full loss, last gets full loss
                n_losers  = n_players - gain_cutoff
                loser_pos = placement - gain_cutoff   # 1 = mildest, n_losers = worst
                frac      = loser_pos / n_losers if n_losers > 0 else 1.0
                sp_change = min(-1, int(loser_sp_full * frac))

            # SC: winner gets full; lower placements get scaled fraction of loser base
            
            if is_winner:
                straftcoin_change = winner_sc
            else:
                for i in range(1, n_players):
                    if placement == i + 1:
                        placement_pct = 0.9 - (0.105*(i-2))
                        straftcoin_change = int(loser_sc_raw * placement_pct)
                        break
        
            sp_col     = 'sp_mp'
            rating_col = 'rating_mp'
            rank_col   = 'rank_mp'
            wins_col   = 'wins_mp'
            losses_col = 'losses_mp'
            rw_col     = 'rounds_won_mp'
            rl_col     = 'rounds_lost_mp'
            hr_col     = 'highest_rank_mp'
            hsp_col    = 'highest_sp_mp'

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

        # Store the actual change applied (post-floor) so undo can reverse it exactly
        actual_sp_change = new_sp - current_sp

        await db.execute("""
            INSERT INTO match_participants
                (match_id, player_id, placement, rounds_won, elo_change, sp_change, straftcoin_change)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (match_id, pid, placement, rounds_won, elo_change, actual_sp_change, straftcoin_change))

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