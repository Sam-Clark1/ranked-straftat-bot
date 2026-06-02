# Ranked Straftat Bot

A Discord bot for running a competitive ranked ladder in [Straftat](https://store.steampowered.com/app/2386720/STRAFTAT/), supporting both 1v1 and multiplayer matches. Tracks ELO ratings, Skill Points (SP), and a virtual Straftcoin economy with an integrated betting system backed by XGBoost ML predictions.

---

## Features

### Match Recording
- Records 1v1 and multiplayer (up to 10 players) results with `!record`
- Each match updates per-player:
  - **ELO rating** - pairwise, K=100, with round-margin adjustment
  - **Skill Points (SP)** - threshold-based, scaled by opponent strength and round performance
  - **Straftcoin balance** - performance-scaled virtual currency rewards
  - Win/loss record and round statistics
- Separate 1v1 and multiplayer rating tracks
- rounds_to_win limits: 1v1 min 10 / max 50 · MP min 3 / max 50

### Ranking System
- ELO-based ratings with expected-score weighting; underdogs gain more for upsets
- SP threshold table: beating a heavy favourite earns significantly more than beating a weaker opponent
- Top half of a multiplayer lobby gains SP; bottom half loses SP
- **MP SP scales by game size**: Larger lobbies and longer games earn more SP; time-crunched shorter games earn less
- Rank titles tied to SP milestones, tracked per mode (1v1 and MP separately)

### Betting System
- `!bet` opens a configurable betting window (default 5 min, set via `BET_TIME_SECONDS`) with live odds displayed as images
- **1v1 bet types**: Spread, Moneyline, Over/Under total rounds
- **MP bet types**: Moneyline, Head-to-Head, Podium (top 3), Last Place, Over/Under total rounds, Over/Under per-player rounds
- **Parlays**: combine up to 6 legs across bet types; multiplier shown in American odds
- Conflict detection prevents contradictory parlay combinations (e.g. favourite spread + underdog moneyline, H2H cycles)
- Players in a match have betting restrictions - can only bet on their own positive outcomes; cannot bet on Last Place bets at all
- Tied last place finish → all Last Place bets on those players push (stake refunded)
- Bets settle automatically when the match is recorded; results posted in a thread with full leg breakdown for parlays

### ML Predictions
- **1v1**: XGBoost regressor trained on match history to predict point spread
- **MP**: Separate XGBoost models for total rounds (ratio-normalised) and per-player rounds
- Models retrain automatically after each match (minimum 5 matches required)
- Models are trained on startup if the model files are missing
- Predictions feed into odds generation, adjusted by recent win rates and round rates

### Player Stats & Leaderboards
- `!stats` - per-player 1v1 and MP stats: rating, SP, rank, win %, round stats, Straftcoin balance
- `!matchstats` - head-to-head breakdown vs. each opponent
- `!lb` - 1v1 SP leaderboard
- `!mlb` - multiplayer SP leaderboard
- `!slb` - Straftcoin balance leaderboard
- All Straftcoin amounts displayed with comma formatting (e.g. 1,250,000)

### Database Backups
- Automatic backup of `rankings.db` before every `!record` and `!undo` call
- Rolling cap of 10 backups; oldest deleted automatically when cap is exceeded
- Backups stored in `backups/` (gitignored)

### Admin Tools
- `!undo` - reverts the most recent match, restoring all stats, ratings, and bet states
- `!undobets` - cancels all live bets and refunds stakes to every bettor

---

## Project Structure

```
├── __main__.py          # Bot entry point, DB schema creation, cog loader
├── pytest.ini           # pytest configuration (asyncio_mode = auto)
├── cogs/
│   ├── bet.py           # !bet command, bet validation, parlay logic
│   ├── help.py          # !help command
│   ├── leaderboard.py   # !lb and !mlb commands
│   ├── matchstats.py    # !matchstats command
│   ├── record.py        # !record command, bet settlement trigger
│   ├── slb.py           # !slb command
│   ├── stats.py         # !stats command
│   ├── undo.py          # !undo command
│   └── undobets.py      # !undobets command
├── helpers/
│   ├── bet_helpers.py   # Odds calculation, bet settlement, image generation
│   ├── command_helpers.py  # ELO/SP/SC formulas, DB helpers, backup utility
│   └── model_helpers.py    # XGBoost training and prediction
├── models/              # Trained model files (auto-generated, gitignored)
│   ├── spread_model.ubj
│   ├── mp_total_ratio_model.ubj
│   └── mp_player_ratio_model.ubj
├── tests/               # Unit and end-to-end test suite
│   ├── conftest.py
│   ├── test_command_helpers.py
│   ├── test_bet_helpers.py
│   ├── test_cogs_bet.py
│   └── test_end_to_end.py
└── rankings.db          # SQLite database (gitignored)
```

---

## Prerequisites

- Python 3.8+
- Discord bot token with **Message Content Intent** enabled (Discord Developer Portal → Bot → Privileged Gateway Intents)

---

## Installation

```bash
git clone https://github.com/Sam-Clark1/dev-ranked-straftat.git
cd dev-ranked-straftat
pip install -r requirements.txt
```

---

## Configuration

Create a `.env` file in the project root:

```env
DISCORD_API_KEY=your_bot_token_here
ADMIN_ID=your_discord_user_id_here
BET_TIME_SECONDS=300
```

- `ADMIN_ID` - Discord user ID authorised to use `!undo` and `!undobets`
- `BET_TIME_SECONDS` - betting window duration in seconds (default: 300 = 5 minutes)

---

## Running

```bash
python __main__.py
```

The bot creates the SQLite database and all tables on first launch, creates the `models/` and `backups/` folders, attempts to train models from any existing data, then loads all cogs automatically.

---

## Commands

| Command | Description |
|---|---|
| `!record <rtw> @P1 <rounds> @P2 <rounds> ...` | Record a match result. `rtw` = rounds to win (1v1: 10–50, MP: 3–50). Exactly one player must have `rtw` rounds. |
| `!bet <rtw> @P1 @P2 [@P3 ...]` | Open a betting window for an upcoming match. |
| `!stats @Player` | Show 1v1 and MP stats for a player. |
| `!matchstats @Player` | Show head-to-head history vs. each opponent. |
| `!lb` | 1v1 SP leaderboard. |
| `!mlb` | Multiplayer SP leaderboard. |
| `!slb` | Straftcoin balance leaderboard. |
| `!help` | List all commands with usage examples. |
| `!undo` | *(Admin only)* Revert the most recent match. |
| `!undobets` | *(Admin only)* Cancel all live bets and refund stakes. |

### Placing Bets

Inside a `!bet` thread, after the odds image is posted:

- **Single bet**: `<label> <stake>` - e.g. `A 200`
- **Parlay**: `P <label1> <label2> ... <stake>` - e.g. `P A C 200`

All bets are placed in Straftcoin. New players start with 1,000 SC.

---

## Testing

```bash
pytest tests/ -v
```

72 tests covering: SP/ELO formulas, odds utilities, all bet types (moneyline, spread, H2H, podium, last place, O/U), parlay conflict detection, and full end-to-end match recording + bet settlement pipelines.

---

## Tech Stack

| Library | Use |
|---|---|
| discord.py 2.4 | Bot framework |
| aiosqlite | Async SQLite access |
| xgboost | Match prediction models |
| scikit-learn | Train/test split and evaluation |
| pandas | Feature engineering |
| matplotlib | Odds display image generation |
| python-dotenv | Environment variable loading |
| pytest + pytest-asyncio | Unit and integration testing |
