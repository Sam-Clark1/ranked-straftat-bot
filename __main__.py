import discord
from discord.ext import commands
import aiosqlite
import os
from dotenv import load_dotenv

intents = discord.Intents.default()
intents.members = True
intents.messages = True
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

@bot.event
async def on_ready():
    async with aiosqlite.connect("rankings.db") as db:

        await db.execute("""
        CREATE TABLE IF NOT EXISTS players (
            user_id             INTEGER PRIMARY KEY,
            rating_1v1          REAL DEFAULT 1000,
            sp_1v1              INTEGER DEFAULT 0,
            rank_1v1            TEXT DEFAULT 'Shitterton IV',
            wins_1v1            INTEGER DEFAULT 0,
            losses_1v1          INTEGER DEFAULT 0,
            rounds_won_1v1      INTEGER DEFAULT 0,
            rounds_lost_1v1     INTEGER DEFAULT 0,
            highest_rank_1v1    TEXT DEFAULT 'Shitterton IV',
            highest_sp_1v1      INTEGER DEFAULT 0,
            rating_mp           REAL DEFAULT 1000,
            sp_mp               INTEGER DEFAULT 0,
            rank_mp             TEXT DEFAULT 'Shitterton IV',
            wins_mp             INTEGER DEFAULT 0,
            losses_mp           INTEGER DEFAULT 0,
            rounds_won_mp       INTEGER DEFAULT 0,
            rounds_lost_mp      INTEGER DEFAULT 0,
            highest_rank_mp     TEXT DEFAULT 'Shitterton IV',
            highest_sp_mp       INTEGER DEFAULT 0,
            straftcoins         INTEGER DEFAULT 1000
        )
        """)

        await db.execute("""
        CREATE TABLE IF NOT EXISTS matches (
            match_id        INTEGER PRIMARY KEY AUTOINCREMENT,
            rounds_to_win   INTEGER NOT NULL,
            total_rounds    INTEGER NOT NULL,
            game_mode       TEXT DEFAULT '1v1',
            date            TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """)

        await db.execute("""
        CREATE TABLE IF NOT EXISTS match_participants (
            participant_id      INTEGER PRIMARY KEY AUTOINCREMENT,
            match_id            INTEGER NOT NULL,
            player_id           INTEGER NOT NULL,
            placement           INTEGER NOT NULL,
            rounds_won          INTEGER NOT NULL,
            elo_change          REAL NOT NULL,
            sp_change           INTEGER NOT NULL,
            straftcoin_change   INTEGER NOT NULL,
            FOREIGN KEY (match_id) REFERENCES matches(match_id),
            FOREIGN KEY (player_id) REFERENCES players(user_id)
        )
        """)

        await db.execute("""
        CREATE TABLE IF NOT EXISTS parlays (
            parlay_id           INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id             INTEGER NOT NULL,
            match_title         TEXT NOT NULL,
            total_stake         INTEGER NOT NULL,
            num_legs            INTEGER NOT NULL,
            combined_multiplier REAL NOT NULL,
            status              TEXT DEFAULT 'live',
            payout              INTEGER DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES players(user_id)
        )
        """)

        await db.execute("""
        CREATE TABLE IF NOT EXISTS live_bets (
            bet_id              INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id             INTEGER NOT NULL,
            match_title         TEXT NOT NULL,
            player_bet_on_id    INTEGER,
            player_b_id         INTEGER,
            bet_type            TEXT NOT NULL,
            bet_value           TEXT NOT NULL,
            bet_odds            INTEGER NOT NULL,
            bet_amount          INTEGER NOT NULL,
            parlay_id           INTEGER,
            FOREIGN KEY (parlay_id) REFERENCES parlays(parlay_id)
        )
        """)

        await db.execute("""
        CREATE TABLE IF NOT EXISTS past_bets (
            bet_id              INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id             INTEGER NOT NULL,
            match_id            INTEGER NOT NULL,
            match_title         TEXT NOT NULL,
            player_bet_on_id    INTEGER,
            player_b_id         INTEGER,
            bet_type            TEXT NOT NULL,
            bet_value           TEXT NOT NULL,
            bet_odds            INTEGER NOT NULL,
            bet_amount          INTEGER NOT NULL,
            result              TEXT NOT NULL,
            amount_won          INTEGER NOT NULL,
            parlay_id           INTEGER,
            FOREIGN KEY (match_id) REFERENCES matches(match_id),
            FOREIGN KEY (parlay_id) REFERENCES parlays(parlay_id)
        )
        """)

        await db.commit()

    try:
        files = os.listdir("./cogs")
        files.remove('__init__.py')
        for filename in files:
            if filename.endswith(".py"):
                await bot.load_extension(f"cogs.{filename[:-3]}")
    except Exception as e:
        print(f"Failed to load cog: {e}")

    print(f'{bot.user} is online and ready!')

load_dotenv()
api_key = os.environ['DISCORD_API_KEY']
bot.run(api_key)