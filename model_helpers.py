import pandas as pd
import xgboost as xgb
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error

async def fetch_data(db):
    matches = await db.execute_fetchall("SELECT * FROM matches")
    players = await db.execute_fetchall("SELECT * FROM players")
    
    matches_df = pd.DataFrame(matches, columns=["match_id", "winner_id", "loser_id", "winner_rounds", "loser_rounds",
                                                "winner_elo_change", "loser_elo_change", "winner_sp_change", 
                                                "loser_sp_change", "timestamp", 'outcome', 'spread', 
                                                'total_rounds', 'winner_straftcoin_change', 'loser_straftcoin_change'])
    
    players_df = pd.DataFrame(players, columns=["user_id", "rating", "sp", "rank", "wins", "losses", 
                                                "rounds_won", "rounds_lost", 'straftcoins', 'highest_rank_achieved', 'highest_sp_achieved'])
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
    # dnew2 = prepare_new_data(player2_id, player1_id)

    pred_variable1 = booster.predict(dnew1)[0]
    # pred_variable2 = booster.predict(dnew2)[0]

    # avg_pred_variable = (pred_variable1 + pred_variable2) / 2
    pred_variable1 = round(pred_variable1*2)/2
    
    return pred_variable1

async def train_models(predicted_variable, db):
    
    # Fetch data
    matches_df, players_df = await fetch_data(db)

    # Prepare features and target
    X, y = await prepare_features(matches_df, players_df, predicted_variable)

    # Train-test split
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    # Convert to DMatrix
    dtrain = xgb.DMatrix(X_train, label=y_train)
    dtest = xgb.DMatrix(X_test, label=y_test)

    # Set parameters for training
    params = {
        "objective": "reg:squarederror",
        "learning_rate": 0.1,
        "max_depth": 5,
        "seed": 42,
    }
    num_boost_round = 100

    # Train the model
    booster = xgb.train(
        params, 
        dtrain, 
        num_boost_round=num_boost_round, 
        # evals=[(dtest, "test")],
        verbose_eval=True
    )

    if predicted_variable == 'spread':
        booster.save_model("spread_model.booster")
    elif predicted_variable == 'total_rounds':
        booster.save_model("over_under_model.booster")

    # Evaluate the model
    # y_pred = booster.predict(dtest)
    # mae = mean_absolute_error(y_test, y_pred)
    # print(f"Mean Absolute Error: {mae:.2f}")