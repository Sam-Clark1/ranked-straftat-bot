import pandas as pd
import xgboost as xgb
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error

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

    players_df = pd.DataFrame(players, columns=[
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
    ])

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

    matches_df['winner_win_rate'] = (
        matches_df['winner_wins'] /
        (matches_df['winner_wins'] + matches_df['winner_losses'])
    )
    matches_df['loser_win_rate'] = (
        matches_df['loser_wins'] /
        (matches_df['loser_wins'] + matches_df['loser_losses'])
    )
    matches_df['winner_round_rate'] = (
        matches_df['winner_rounds_won'] /
        (matches_df['winner_rounds_won'] + matches_df['winner_rounds_lost'])
    )
    matches_df['loser_round_rate'] = (
        matches_df['loser_rounds_won'] /
        (matches_df['loser_rounds_won'] + matches_df['loser_rounds_lost'])
    )

    features = [
        'winner_rating', 'loser_rating', 'elo_diff', 'sp_diff',
        'winner_win_rate', 'loser_win_rate',
        'winner_round_rate', 'loser_round_rate'
    ]
    return matches_df[features], matches_df[predicted_variable]

async def predict_variable(player1_id, player2_id, predicted_variable, db):

    if predicted_variable == 'spread':
        model_file = 'spread_model.booster'
    elif predicted_variable == 'total_rounds':
        model_file = 'over_under_model.booster'

    booster = xgb.Booster()
    booster.load_model(model_file)
    _, players_df = await fetch_data(db)

    def prepare_new_data(winner_id, loser_id):
        player_stats = players_df.set_index("user_id")
        new_data = pd.DataFrame({
            "winner_rating": [player_stats.loc[winner_id, "rating_1v1"]],
            "loser_rating":  [player_stats.loc[loser_id,  "rating_1v1"]],
            "elo_diff": [abs(
                player_stats.loc[winner_id, "rating_1v1"] -
                player_stats.loc[loser_id,  "rating_1v1"]
            )],
            "sp_diff": [abs(
                player_stats.loc[winner_id, "sp_1v1"] -
                player_stats.loc[loser_id,  "sp_1v1"]
            )],
            "winner_win_rate": [
                player_stats.loc[winner_id, "wins_1v1"] /
                (player_stats.loc[winner_id, "wins_1v1"] + player_stats.loc[winner_id, "losses_1v1"])
            ],
            "loser_win_rate": [
                player_stats.loc[loser_id, "wins_1v1"] /
                (player_stats.loc[loser_id, "wins_1v1"] + player_stats.loc[loser_id, "losses_1v1"])
            ],
            "winner_round_rate": [
                player_stats.loc[winner_id, "rounds_won_1v1"] /
                (player_stats.loc[winner_id, "rounds_won_1v1"] + player_stats.loc[winner_id, "rounds_lost_1v1"])
            ],
            "loser_round_rate": [
                player_stats.loc[loser_id, "rounds_won_1v1"] /
                (player_stats.loc[loser_id, "rounds_won_1v1"] + player_stats.loc[loser_id, "rounds_lost_1v1"])
            ],
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
    if len(X) < 10:
        print(f"Skipping model training — only {len(X)} sample(s) available, need at least 10.")
        return

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    dtrain = xgb.DMatrix(X_train, label=y_train)
    dtest  = xgb.DMatrix(X_test,  label=y_test)

    params = {
        "objective":     "reg:squarederror",
        "learning_rate": 0.1,
        "max_depth":     5,
        "seed":          42,
    }

    booster = xgb.train(params, dtrain, num_boost_round=100)

    if predicted_variable == 'spread':
        booster.save_model("spread_model.booster")
    elif predicted_variable == 'total_rounds':
        booster.save_model("over_under_model.booster")

    # Evaluate the model
    # y_pred = booster.predict(dtest)
    # mae = mean_absolute_error(y_test, y_pred)
    # print(f"Mean Absolute Error: {mae:.2f}")