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

# Initialize database
@bot.event
async def on_ready():
    async with aiosqlite.connect("rankings.db") as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS players (
            user_id INTEGER PRIMARY KEY,
            rating INTEGER DEFAULT 1000,
            sp INTEGER DEFAULT 0,
            rank TEXT DEFAULT 'Shitterton IV',
            wins INTEGER DEFAULT 0,
            losses INTEGER DEFAULT 0,
            rounds_won INTEGER DEFAULT 0,
            rounds_lost INTEGER DEFAULT 0, 
            straftcoins INTEGER DEFAULT 1000,
            highest_rank_achieved TEXT DEFAULT 'Shitterton IV',
            highest_sp_achieved INTEGER DEFAULT 0
        )
        """)
        await db.execute("""
        CREATE TABLE matches (
            match_id        INTEGER PRIMARY KEY AUTOINCREMENT,
            rounds_to_win   INTEGER NOT NULL,
            total_rounds    INTEGER NOT NULL,
            date           TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """)
        await db.execute('''
        CREATE TABLE match_participants (
            participant_id      INTEGER PRIMARY KEY AUTOINCREMENT,
            match_id            INTEGER NOT NULL,
            player_id           INTEGER NOT NULL,
            placement           INTEGER NOT NULL,  -- 1 = winner, 2 = 2nd, etc.
            rounds_won          INTEGER NOT NULL,
            elo_change          REAL NOT NULL,
            sp_change           INTEGER NOT NULL,
            straftcoin_change   INTEGER NOT NULL,
            FOREIGN KEY (match_id) REFERENCES matches(match_id),
            FOREIGN KEY (player_id) REFERENCES players(user_id)
        )
        ''')
        await db.execute('''
            CREATE TABLE live_bets (
            bet_id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id         INTEGER NOT NULL,
            match_title     TEXT NOT NULL,
            player_bet_on_id INTEGER,          -- NULL for O/U bets
            bet_type        TEXT NOT NULL,     -- 'moneyline', 'over', 'under'
            bet_value       TEXT NOT NULL,
            bet_odds        INTEGER NOT NULL,
            bet_amount      INTEGER NOT NULL
        )
        ''')
        await db.execute('''
            CREATE TABLE past_bets (
            bet_id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id         INTEGER NOT NULL,
            match_id        INTEGER NOT NULL,
            match_title     TEXT NOT NULL,
            player_bet_on_id INTEGER,
            bet_type        TEXT NOT NULL,
            bet_value       TEXT NOT NULL,
            bet_odds        INTEGER NOT NULL,
            bet_amount      INTEGER NOT NULL,
            result          TEXT NOT NULL,     -- 'win' or 'loss'
            amount_won      INTEGER NOT NULL,
            FOREIGN KEY (match_id) REFERENCES matches(match_id)
        )
        ''')
        await db.commit()

    try:
        files = os.listdir("./cogs")
        files.remove('__init__.py')
        for filename in files:
            if filename.endswith(".py"):
                await bot.load_extension(f"cogs.{filename[:-3]}")
    except Exception as e:
        print(f"Failed to load cog 'record': {e}")

    print(f'{bot.user} is online and ready!')

load_dotenv()
api_key = os.environ['DISCORD_API_KEY']
bot.run(api_key)