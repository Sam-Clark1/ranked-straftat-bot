import os
import pandas as pd
import xgboost as xgb
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error

_PLAYERS_COLUMNS = [
    'user_id',
    'rating_1v1', 'sp_1v1', 'rank_1v1',
    'wins_1v1', 'losses_1v1',
    'rounds_won_1v1', 'rounds_lost_1v1',
    'highest_rank_1v1', 'highest_sp_1v1',
    'rating_mp', 'sp_mp', 'rank_mp',
    'wins_mp', 'losses_mp',
    'rounds_won_mp', 'rounds_lost_mp',
    'highest_rank_mp', 'highest_sp_mp',
    'straftcoins'
]

_XGB_PARAMS = {
    'objective': 'reg:squarederror',
    'learning_rate': 0.1,
    'max_depth': 5,
    'seed': 42,
}

async def fetch_data(db):
    """
    Reconstructs a 1v1 match dataset by joining matches + match_participants.
    Only 1v1 games are used for model training since spread is a 1v1 concept.
    """
    raw = await db.execute_fetchall("""
        SELECT
            m.match_id,
            mp1.player_id   AS winner_id,
            mp2.player_id   AS loser_id,
            mp1.rounds_won  AS winner_rounds,
            mp2.rounds_won  AS loser_rounds,
            mp1.rounds_won - mp2.rounds_won AS spread,
            m.total_rounds
        FROM matches m
        JOIN match_participants mp1
            ON m.match_id = mp1.match_id AND mp1.placement = 1
        JOIN match_participants mp2
            ON m.match_id = mp2.match_id AND mp2.placement = 2
        WHERE m.game_mode = '1v1'
    """)

    players = await db.execute_fetchall("SELECT * FROM players")

    matches_df = pd.DataFrame(raw, columns=[
        'match_id', 'winner_id', 'loser_id',
        'winner_rounds', 'loser_rounds',
        'spread', 'total_rounds'
    ])

    players_df = pd.DataFrame(players, columns=_PLAYERS_COLUMNS)

    return matches_df, players_df


async def prepare_features(matches_df_init, players_df_init, predicted_variable):
    matches_df = matches_df_init.copy()
    players_df = players_df_init.copy().set_index('user_id')

    matches_df['elo_diff'] = abs(
        matches_df['winner_id'].map(players_df['rating_1v1']) -
        matches_df['loser_id'].map(players_df['rating_1v1'])
    )
    matches_df['sp_diff'] = abs(
        matches_df['winner_id'].map(players_df['sp_1v1']) -
        matches_df['loser_id'].map(players_df['sp_1v1'])
    )

    for stat in ['rating_1v1', 'sp_1v1', 'wins_1v1', 'losses_1v1',
                 'rounds_won_1v1', 'rounds_lost_1v1']:
        short = stat.replace('_1v1', '')
        matches_df[f'winner_{short}'] = matches_df['winner_id'].map(players_df[stat])
        matches_df[f'loser_{short}']  = matches_df['loser_id'].map(players_df[stat])

    w_matches = matches_df['winner_wins']   + matches_df['winner_losses']
    l_matches = matches_df['loser_wins']    + matches_df['loser_losses']
    w_rounds  = matches_df['winner_rounds_won'] + matches_df['winner_rounds_lost']
    l_rounds  = matches_df['loser_rounds_won']  + matches_df['loser_rounds_lost']

    matches_df['winner_win_rate']   = (matches_df['winner_wins']      / w_matches).where(w_matches > 0, 0.5)
    matches_df['loser_win_rate']    = (matches_df['loser_wins']       / l_matches).where(l_matches > 0, 0.5)
    matches_df['winner_round_rate'] = (matches_df['winner_rounds_won'] / w_rounds).where(w_rounds  > 0, 0.5)
    matches_df['loser_round_rate']  = (matches_df['loser_rounds_won']  / l_rounds).where(l_rounds  > 0, 0.5)

    features = [
        'winner_rating', 'loser_rating', 'elo_diff', 'sp_diff',
        'winner_win_rate', 'loser_win_rate',
        'winner_round_rate', 'loser_round_rate'
    ]
    return matches_df[features], matches_df[predicted_variable]

async def predict_variable(player1_id, player2_id, predicted_variable, db):

    if predicted_variable == 'spread':
        model_file = 'models/spread_model.ubj'
    elif predicted_variable == 'total_rounds':
        model_file = 'models/over_under_model.ubj'

    booster = xgb.Booster()
    booster.load_model(model_file)
    _, players_df = await fetch_data(db)

    def prepare_new_data(winner_id, loser_id):
        player_stats = players_df.set_index("user_id")

        def win_rate(pid):
            w = player_stats.loc[pid, "wins_1v1"]
            l = player_stats.loc[pid, "losses_1v1"]
            return w / (w + l) if (w + l) > 0 else 0.5

        def round_rate(pid):
            rw = player_stats.loc[pid, "rounds_won_1v1"]
            rl = player_stats.loc[pid, "rounds_lost_1v1"]
            return rw / (rw + rl) if (rw + rl) > 0 else 0.5

        new_data = pd.DataFrame({
            "winner_rating":    [player_stats.loc[winner_id, "rating_1v1"]],
            "loser_rating":     [player_stats.loc[loser_id,  "rating_1v1"]],
            "elo_diff":         [abs(player_stats.loc[winner_id, "rating_1v1"] -
                                     player_stats.loc[loser_id,  "rating_1v1"])],
            "sp_diff":          [abs(player_stats.loc[winner_id, "sp_1v1"] -
                                     player_stats.loc[loser_id,  "sp_1v1"])],
            "winner_win_rate":  [win_rate(winner_id)],
            "loser_win_rate":   [win_rate(loser_id)],
            "winner_round_rate":[round_rate(winner_id)],
            "loser_round_rate": [round_rate(loser_id)],
        })
        return xgb.DMatrix(new_data)

    dnew1 = prepare_new_data(player1_id, player2_id)
    # dnew2 = prepare_new_data(player2_id, player1_id)

    pred_variable1 = booster.predict(dnew1)[0]
    # pred_variable2 = booster.predict(dnew2)[0]

    # avg_pred_variable = (pred_variable1 + pred_variable2) / 2
    pred_variable1 = round(pred_variable1*2)/2
    
    return pred_variable1

async def train_models(predicted_variable):
    import aiosqlite
    async with aiosqlite.connect('rankings.db') as db:
        matches_df, players_df = await fetch_data(db)
    X, y = await prepare_features(matches_df, players_df, predicted_variable)

    # Need enough samples to split into train and test sets.
    # Below this threshold the model wouldn't be meaningful anyway.
    if len(X) < 5:
        print(f"Skipping model training - only {len(X)} sample(s) available, need at least 5.")
        return

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    dtrain = xgb.DMatrix(X_train, label=y_train)
    dtest  = xgb.DMatrix(X_test,  label=y_test)

    booster = xgb.train(_XGB_PARAMS, dtrain, num_boost_round=100)

    if predicted_variable == 'spread':
        booster.save_model("models/spread_model.ubj")
    elif predicted_variable == 'total_rounds':
        booster.save_model("models/over_under_model.ubj")


# MP MODEL HELPERS

def _pstats(players_df, pid):
    """Return (rating_mp, wr_mp, rr_mp) for a player."""
    if pid not in players_df.index:
        return 1000.0, 0.5, 0.5
    p = players_df.loc[pid]
    def _r(w, l): return w / (w + l) if (w + l) > 0 else 0.5
    return (
        float(p['rating_mp']),
        _r(p['wins_mp'],       p['losses_mp']),
        _r(p['rounds_won_mp'], p['rounds_lost_mp']),
    )


async def fetch_mp_data(db):
    match_raw = await db.execute_fetchall("""
        SELECT m.match_id, m.rounds_to_win, m.total_rounds,
               COUNT(mp.participant_id) AS num_players
        FROM matches m
        JOIN match_participants mp ON m.match_id = mp.match_id
        WHERE m.game_mode = 'mp'
        GROUP BY m.match_id
    """)
    player_raw = await db.execute_fetchall("""
        SELECT mp.match_id, mp.player_id, mp.rounds_won, m.rounds_to_win
        FROM match_participants mp
        JOIN matches m ON mp.match_id = m.match_id
        WHERE m.game_mode = 'mp'
    """)
    players_raw = await db.execute_fetchall("SELECT * FROM players")

    matches_df  = pd.DataFrame(match_raw,   columns=['match_id', 'rounds_to_win', 'total_rounds', 'num_players'])
    player_rows = pd.DataFrame(player_raw,  columns=['match_id', 'player_id', 'rounds_won', 'rounds_to_win'])
    players_df  = pd.DataFrame(players_raw, columns=_PLAYERS_COLUMNS)
    return matches_df, player_rows, players_df


async def prepare_mp_total_features(matches_df, player_rows, players_df):
    ps   = players_df.set_index('user_id')
    rows = []
    for _, m in matches_df.iterrows():
        pids = player_rows[player_rows['match_id'] == m['match_id']]['player_id'].tolist()
        if not pids:
            continue
        stats = [_pstats(ps, pid) for pid in pids]
        rmp, wrm, rrm = zip(*stats)
        rows.append({
            'num_players':        m['num_players'],
            'avg_rating_mp':      sum(rmp)  / len(rmp),
            'std_rating_mp':      pd.Series(list(rmp)).std(ddof=0),
            'avg_win_rate_mp':    sum(wrm)  / len(wrm),
            'avg_round_rate_mp':  sum(rrm)  / len(rrm),
            # Target: ratio so the model learns the multiplier, not the absolute scale
            'total_rounds_ratio': m['total_rounds'] / m['rounds_to_win'],
        })
    df = pd.DataFrame(rows)
    if df.empty:
        return df, pd.Series(dtype=float)
    features = [
        'num_players',
        'avg_rating_mp', 'std_rating_mp', 'avg_win_rate_mp', 'avg_round_rate_mp',
    ]
    return df[features], df['total_rounds_ratio']


async def prepare_mp_player_features(player_rows, players_df):
    ps   = players_df.set_index('user_id')
    rows = []
    for mid, grp in player_rows.groupby('match_id'):
        pids      = grp['player_id'].tolist()
        all_stats = [_pstats(ps, pid) for pid in pids]
        rmp, wrm, rrm = zip(*all_stats)
        fa_rmp = sum(rmp) / len(rmp)
        fa_wrm = sum(wrm) / len(wrm)
        fa_rrm = sum(rrm) / len(rrm)
        rounds_to_win   = grp['rounds_to_win'].iloc[0]
        for _, row in grp.iterrows():
            prm, pwm, prrm = _pstats(ps, row['player_id'])
            rows.append({
                'player_rating_mp':        prm,
                'rating_vs_field_mp':      prm  - fa_rmp,
                'player_win_rate_mp':      pwm,
                'win_rate_vs_field_mp':    pwm  - fa_wrm,
                'player_round_rate_mp':    prrm,
                'round_rate_vs_field_mp':  prrm - fa_rrm,
                'num_players':             len(pids),
                # Target: ratio so predictions scale correctly with rounds_to_win
                'rounds_ratio':            row['rounds_won'] / rounds_to_win,
            })
    df = pd.DataFrame(rows)
    if df.empty:
        return df, pd.Series(dtype=float)
    features = [
        'player_rating_mp',
        'rating_vs_field_mp',
        'player_win_rate_mp',
        'win_rate_vs_field_mp',
        'player_round_rate_mp',
        'round_rate_vs_field_mp',
        'num_players',
    ]
    return df[features], df['rounds_ratio']


async def train_mp_models():
    import aiosqlite
    async with aiosqlite.connect('rankings.db') as db:
        matches_df, player_rows, players_df = await fetch_mp_data(db)

    X_t, y_t = await prepare_mp_total_features(matches_df, player_rows, players_df)
    if len(X_t) >= 5:
        Xtr, _, ytr, _ = train_test_split(X_t, y_t, test_size=0.2, random_state=42)
        xgb.train(_XGB_PARAMS, xgb.DMatrix(Xtr, label=ytr), num_boost_round=100) \
            .save_model('models/mp_total_ratio_model.ubj')
        print(f"MP total rounds model trained on {len(X_t)} matches.")
    else:
        print(f"Skipping MP total rounds training - {len(X_t)} sample(s), need at least 5.")

    X_p, y_p = await prepare_mp_player_features(player_rows, players_df)
    if len(X_p) >= 5:
        Xtr, _, ytr, _ = train_test_split(X_p, y_p, test_size=0.2, random_state=42)
        xgb.train(_XGB_PARAMS, xgb.DMatrix(Xtr, label=ytr), num_boost_round=100) \
            .save_model('models/mp_player_ratio_model.ubj')
        print(f"MP player rounds model trained on {len(X_p)} player-match rows.")
    else:
        print(f"Skipping MP player rounds training - {len(X_p)} sample(s), need at least 5.")


def _build_field_features(ps, player_ids):
    """Compute field-average MP stats from a list of player IDs."""
    all_stats = [_pstats(ps, pid) for pid in player_ids]
    rmp, wrm, rrm = zip(*all_stats)
    return {
        'fa_rmp':  sum(rmp) / len(rmp),
        'fa_wrm':  sum(wrm) / len(wrm),
        'fa_rrm':  sum(rrm) / len(rrm),
        'std_rmp': pd.Series(list(rmp)).std(ddof=0),
    }


async def predict_mp_total_rounds(player_ids, rounds_to_win, db):
    """Returns predicted total rounds for an MP lobby, or None if model not trained."""
    if not os.path.exists('models/mp_total_ratio_model.ubj'):
        return None
    players_raw = await db.execute_fetchall("SELECT * FROM players")
    ps  = pd.DataFrame(players_raw, columns=_PLAYERS_COLUMNS).set_index('user_id')
    fld = _build_field_features(ps, player_ids)
    features = pd.DataFrame([{
        'num_players':        len(player_ids),
        'avg_rating_mp':      fld['fa_rmp'],
        'std_rating_mp':      fld['std_rmp'],
        'avg_win_rate_mp':    fld['fa_wrm'],
        'avg_round_rate_mp':  fld['fa_rrm'],
    }])
    booster = xgb.Booster()
    booster.load_model('models/mp_total_ratio_model.ubj')
    ratio = float(booster.predict(xgb.DMatrix(features))[0])
    return ratio * rounds_to_win


_MP_PLAYER_MODEL_MIN_GAMES = 5  # games needed before model beats the formula

async def predict_mp_player_rounds_all(player_ids, rounds_to_win, db):
    """Returns {player_id: predicted_rounds} for all players, or {} if model not trained
    or if there are fewer than _MP_PLAYER_MODEL_MIN_GAMES MP games recorded."""
    if not os.path.exists('models/mp_player_ratio_model.ubj'):
        return {}
    row = await db.execute_fetchall(
        "SELECT COUNT(*) FROM matches WHERE game_mode = 'mp'"
    )
    if row[0][0] < _MP_PLAYER_MODEL_MIN_GAMES:
        return {}
    players_raw = await db.execute_fetchall("SELECT * FROM players")
    ps  = pd.DataFrame(players_raw, columns=_PLAYERS_COLUMNS).set_index('user_id')
    fld = _build_field_features(ps, player_ids)
    feature_rows = []
    for pid in player_ids:
        prm, pwm, prrm = _pstats(ps, pid)
        feature_rows.append({
            'player_rating_mp':        prm,
            'rating_vs_field_mp':      prm  - fld['fa_rmp'],
            'player_win_rate_mp':      pwm,
            'win_rate_vs_field_mp':    pwm  - fld['fa_wrm'],
            'player_round_rate_mp':    prrm,
            'round_rate_vs_field_mp':  prrm - fld['fa_rrm'],
            'num_players':             len(player_ids),
        })
    booster = xgb.Booster()
    booster.load_model('models/mp_player_ratio_model.ubj')
    preds = booster.predict(xgb.DMatrix(pd.DataFrame(feature_rows)))
    return {pid: max(0.0, float(p) * rounds_to_win) for pid, p in zip(player_ids, preds)}