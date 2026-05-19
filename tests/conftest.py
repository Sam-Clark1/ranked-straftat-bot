import pytest
import aiosqlite

SCHEMA = """
CREATE TABLE players (
    user_id INTEGER PRIMARY KEY,
    rating_1v1 REAL DEFAULT 1000,
    sp_1v1 INTEGER DEFAULT 0,
    rank_1v1 TEXT DEFAULT 'Shitterton IV',
    wins_1v1 INTEGER DEFAULT 0, losses_1v1 INTEGER DEFAULT 0,
    rounds_won_1v1 INTEGER DEFAULT 0, rounds_lost_1v1 INTEGER DEFAULT 0,
    highest_rank_1v1 TEXT DEFAULT 'Shitterton IV', highest_sp_1v1 INTEGER DEFAULT 0,
    rating_mp REAL DEFAULT 1000,
    sp_mp INTEGER DEFAULT 0,
    rank_mp TEXT DEFAULT 'Shitterton IV',
    wins_mp INTEGER DEFAULT 0, losses_mp INTEGER DEFAULT 0,
    rounds_won_mp INTEGER DEFAULT 0, rounds_lost_mp INTEGER DEFAULT 0,
    highest_rank_mp TEXT DEFAULT 'Shitterton IV', highest_sp_mp INTEGER DEFAULT 0,
    straftcoins INTEGER DEFAULT 1000
);
CREATE TABLE matches (
    match_id INTEGER PRIMARY KEY AUTOINCREMENT,
    rounds_to_win INTEGER NOT NULL,
    total_rounds INTEGER NOT NULL,
    game_mode TEXT DEFAULT '1v1',
    date TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE match_participants (
    participant_id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id INTEGER NOT NULL,
    player_id INTEGER NOT NULL,
    placement INTEGER NOT NULL,
    rounds_won INTEGER NOT NULL,
    elo_change REAL NOT NULL,
    sp_change INTEGER NOT NULL,
    straftcoin_change INTEGER NOT NULL
);
CREATE TABLE live_bets (
    bet_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    match_title TEXT NOT NULL,
    player_bet_on_id INTEGER,
    player_b_id INTEGER,
    bet_type TEXT NOT NULL,
    bet_value TEXT NOT NULL,
    bet_odds INTEGER NOT NULL,
    bet_amount INTEGER NOT NULL,
    parlay_id INTEGER
);
CREATE TABLE past_bets (
    bet_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    match_id INTEGER NOT NULL,
    match_title TEXT NOT NULL,
    player_bet_on_id INTEGER,
    player_b_id INTEGER,
    bet_type TEXT NOT NULL,
    bet_value TEXT NOT NULL,
    bet_odds INTEGER NOT NULL,
    bet_amount INTEGER NOT NULL,
    result TEXT NOT NULL,
    amount_won INTEGER NOT NULL,
    parlay_id INTEGER
);
CREATE TABLE parlays (
    parlay_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    match_title TEXT NOT NULL,
    total_stake INTEGER NOT NULL,
    num_legs INTEGER NOT NULL,
    combined_multiplier REAL NOT NULL,
    status TEXT DEFAULT 'live',
    payout INTEGER DEFAULT 0
);
"""

@pytest.fixture
async def db():
    async with aiosqlite.connect(":memory:") as conn:
        await conn.executescript(SCHEMA)
        await conn.commit()
        yield conn
