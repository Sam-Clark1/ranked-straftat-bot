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
            rank TEXT DEFAULT 'Shitterton',
            wins INTEGER DEFAULT 0,
            losses INTEGER DEFAULT 0,
            rounds_won INTEGER DEFAULT 0,
            rounds_lost INTEGER DEFAULT 0, 
            straftcoins INTEGER DEFAULT 1000
        )
        """)
        await db.execute("""
        CREATE TABLE IF NOT EXISTS matches (
            match_id INTEGER PRIMARY KEY AUTOINCREMENT,
            winner_id INTEGER,
            loser_id INTEGER,
            winner_rounds INTEGER,
            loser_rounds INTEGER,
            winner_elo_change INTEGER,
            loser_elo_change INTEGER,
            winner_sp_change INTEGER,
            loser_sp_change INTEGER,
            timestamp TEXT,
            outcome INTEGER,
            spread INTEGER, 
            total_rounds INTEGER, 
            winner_straftcoin_change INTEGER,
            loser_straftcoin_change INTEGER
        )
        """)
        await db.execute('''
            CREATE TABLE IF NOT EXISTS live_bets (
            bet_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            match_title TEXT NOT NULL,
            match_favorite_id INTEGER NOT NULL,
            match_underdog_id INTEGER NOT NULL,
            playerid_bet_on INTEGER NOT NULL,
            bet_type TEXT NOT NULL,
            bet_value TEXT NOT NULL,
            bet_odds INTEGER NOT NULL,
            bet_amount INTEGER NOT NULL
        )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS past_bets (
            bet_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            match_id INTEGER NOT NULL,
            match_title TEXT NOT NULL,
            match_favorite_id INTEGER NOT NULL,
            match_underdog_id INTEGER NOT NULL,
            playerid_bet_on INTEGER NOT NULL,
            bet_type TEXT NOT NULL,
            bet_value TEXT NOT NULL,
            bet_odds INTEGER NOT NULL,
            bet_amount INTEGER NOT NULL,
            bet_outcome TEXT NOT NULL,
            amount_won INTEGER NOT NULL,
            amount_lost INTEGER NOT NULL
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