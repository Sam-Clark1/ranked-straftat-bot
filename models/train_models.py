import pandas as pd
import numpy as np
import xgboost as xgb
import aiosqlite
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error
from model_helpers import fetch_data, prepare_features
import asyncio

async def train_models(predicted_variable):
    async with aiosqlite.connect("rankings.db") as db:
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
            evals=[(dtest, "test")],
            verbose_eval=True
        )

        if predicted_variable == 'spread':
            booster.save_model("spread_model.booster")
        elif predicted_variable == 'total_rounds':
            booster.save_model("over_under_model.booster")

        # Evaluate the model
        y_pred = booster.predict(dtest)
        mae = mean_absolute_error(y_test, y_pred)
        print(f"Mean Absolute Error: {mae:.2f}")
        
asyncio.run(train_models('spread'))
# asyncio.run(train_models('total_rounds'))