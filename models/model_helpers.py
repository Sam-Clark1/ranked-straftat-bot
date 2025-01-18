import pandas as pd
import xgboost as xgb
import os

async def fetch_data(db):
    matches = await db.execute_fetchall("SELECT * FROM matches")
    players = await db.execute_fetchall("SELECT * FROM players")
    
    matches_df = pd.DataFrame(matches, columns=["match_id", "winner_id", "loser_id", "winner_rounds", "loser_rounds",
                                                "winner_elo_change", "loser_elo_change", "winner_sp_change", 
                                                "loser_sp_change", "timestamp", 'outcome', 'spread', 
                                                'total_rounds', 'winner_straftcoin_change', 'loser_straftcoin_change'])
    
    players_df = pd.DataFrame(players, columns=["user_id", "rating", "sp", "rank", "wins", "losses", 
                                                "rounds_won", "rounds_lost", 'straftcoins'])
    return matches_df, players_df

async def prepare_features(matches_df_init, players_df_init, predicted_variable):
    matches_df = matches_df_init.copy()
    players_df = players_df_init.copy()
    
    players_df = players_df.set_index("user_id")
    
    matches_df["elo_diff"] = abs(matches_df["winner_id"].map(players_df["rating"]) - matches_df["loser_id"].map(players_df["rating"]))
    matches_df["sp_diff"] = abs(matches_df["winner_id"].map(players_df["sp"]) - matches_df["loser_id"].map(players_df["sp"]))

    for stat in ["rating", "sp", "wins", "losses", "rounds_won", "rounds_lost"]:
        matches_df[f"winner_{stat}"] = matches_df["winner_id"].map(players_df[stat])
        matches_df[f"loser_{stat}"] = matches_df["loser_id"].map(players_df[stat])

    matches_df["winner_win_rate"] = matches_df["winner_wins"] / (matches_df["winner_wins"] + matches_df["winner_losses"])
    matches_df["loser_win_rate"] = matches_df["loser_wins"] / (matches_df["loser_wins"] + matches_df["loser_losses"])
    matches_df["winner_round_rate"] = matches_df["winner_rounds_won"] / (matches_df["winner_rounds_won"] + matches_df["winner_rounds_lost"])
    matches_df["loser_round_rate"] = matches_df["loser_rounds_won"] / (matches_df["loser_rounds_won"] + matches_df["loser_rounds_lost"])

    features = ["winner_rating", "loser_rating", "elo_diff", "sp_diff", 
                "winner_win_rate", "loser_win_rate", "winner_round_rate", "loser_round_rate"]
    X = matches_df[features]
    y = matches_df[predicted_variable]

    return X, y

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
            "winner_rating": [player_stats.loc[winner_id, "rating"]],
            "loser_rating": [player_stats.loc[loser_id, "rating"]],
            "elo_diff": [abs(player_stats.loc[winner_id, "rating"] - player_stats.loc[loser_id, "rating"])],
            "sp_diff": [abs(player_stats.loc[winner_id, "sp"] - player_stats.loc[loser_id, "sp"])],
            "winner_win_rate": [player_stats.loc[winner_id, "wins"] / (player_stats.loc[winner_id, "wins"] + player_stats.loc[winner_id, "losses"])],
            "loser_win_rate": [player_stats.loc[loser_id, "wins"] / (player_stats.loc[loser_id, "wins"] + player_stats.loc[loser_id, "losses"])],
            "winner_round_rate": [player_stats.loc[winner_id, "rounds_won"] / (player_stats.loc[winner_id, "rounds_won"] + player_stats.loc[winner_id, "rounds_lost"])],
            "loser_round_rate": [player_stats.loc[loser_id, "rounds_won"] / (player_stats.loc[loser_id, "rounds_won"] + player_stats.loc[loser_id, "rounds_lost"])]
        })
        return xgb.DMatrix(new_data)

    dnew1 = prepare_new_data(player1_id, player2_id)
    dnew2 = prepare_new_data(player2_id, player1_id)

    pred_variable1 = booster.predict(dnew1)[0]
    pred_variable2 = booster.predict(dnew2)[0]

    avg_pred_variable = (pred_variable1 + pred_variable2) / 2
    avg_pred_variable = round(avg_pred_variable*2)/2
    
    return avg_pred_variable

async def incremental_train(match_id, predicted_variable, db):
    
    if predicted_variable == 'spread':
        model_path = 'spread_model.booster'
    elif predicted_variable == 'total_rounds':
        model_path = 'over_under_model.booster'  
    
    if os.path.exists(model_path):
        booster = xgb.Booster()
        booster.load_model(model_path)
    else:
        print("No existing model found. Train a model first.")
        return

    # Fetch player data and new match data
    matches_df, players_df = await fetch_data(db)

    new_match_data = matches_df[matches_df["match_id"] == match_id]

    # Prepare features for the new match
    X_new, y_new = await prepare_features(new_match_data, players_df, predicted_variable)

    # Convert to DMatrix for XGBoost
    dnew = xgb.DMatrix(X_new, label=y_new)

    # Incrementally update the model
    booster.update(dnew, iteration=1)

    # Save the updated model
    booster.save_model(model_path)
    print('Model Updated')