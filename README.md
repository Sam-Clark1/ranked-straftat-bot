# Ranked Straftat Bot

A Discord bot for running a competitive ranked ladder in [Straftat](https://store.steampowered.com/app/2386720/STRAFTAT/), supporting both 1v1 and multiplayer matches. Tracks ELO ratings, Skill Points (SP), and a virtual Straftcoin economy with an integrated betting system backed by XGBoost ML predictions.

---

## Features

### Match Recording
- Records 1v1 and multiplayer (up to 10 players) results with `!record`
- Each match updates per-player:
  - **ELO rating** — pairwise, K=100, with round-margin adjustment
  - **Skill Points (SP)** — threshold-based, scaled by opponent strength and round performance
  - **Straftcoin balance** — performance-scaled virtual currency rewards
  - Win/loss record and round statistics
- Separate 1v1 and multiplayer rating tracks

### Ranking System
- ELO-based ratings with expected-score weighting; underdogs gain more for upsets
- SP threshold table: beating a heavy favourite earns significantly more than beating a weaker opponent
- Top half of a multiplayer lobby gains SP; bottom half loses SP
- Rank titles tied to SP milestones, tracked per mode (1v1 and MP separately)

### Betting System
- `!bet` opens a 2-minute betting window with live odds displayed as images
- **1v1 bet types**: Spread, Moneyline, Over/Under total rounds
- **MP bet types**: Moneyline, Head-to-Head, Podium (top 3), Last Place, Over/Under total rounds, Over/Under per-player rounds
- **Parlays**: combine up to 6 legs across bet types; multiplier shown in American odds
- Conflict detection prevents contradictory parlay combinations (e.g. favourite spread + underdog moneyline, H2H cycles)
- Players in a match have betting restrictions — can only bet on their own positive outcomes
- Bets settle automatically when the match is recorded; results posted in a thread with full leg breakdown for parlays

### ML Predictions
- **1v1**: XGBoost regressor trained on match history to predict point spread
- **MP**: Separate XGBoost models for total rounds (ratio-normalised) and per-player rounds
- Models retrain automatically after each match (minimum 5 matches required)
- Predictions feed into odds generation, adjusted by recent win rates and round rates

### Player Stats & Leaderboards
- `!stats` — per-player 1v1 and MP stats: rating, SP, rank, win %, round stats, Straftcoin balance
- `!matchstats` — head-to-head breakdown vs. each opponent
- `!lb` — 1v1 SP leaderboard
- `!mlb` — multiplayer SP leaderboard
- `!slb` — Straftcoin balance leaderboard

### Admin Tools
- `!undo` — reverts the most recent match, restoring all stats, ratings, and bet states

---

## Project Structure

```
├── __main__.py          # Bot entry point, DB schema creation, cog loader
├── cogs/
│   ├── bet.py           # !bet command, bet validation, parlay logic
│   ├── help.py          # !help command
│   ├── leaderboard.py   # !lb and !mlb commands
│   ├── matchstats.py    # !matchstats command
│   ├── record.py        # !record command, bet settlement trigger
│   ├── slb.py           # !slb command
│   ├── stats.py         # !stats command
│   └── undo.py          # !undo command
├── helpers/
│   ├── bet_helpers.py   # Odds calculation, bet settlement, image generation
│   ├── command_helpers.py  # ELO/SP/SC formulas, DB helpers
│   └── model_helpers.py    # XGBoost training and prediction
├── models/              # Trained model files (auto-generated, gitignored)
│   ├── spread_model.ubj
│   ├── mp_total_ratio_model.ubj
│   └── mp_player_ratio_model.ubj
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
```

- `ADMIN_ID` is the Discord user ID that is authorised to use `!undo`

---

## Running

```bash
python __main__.py
```

The bot creates the SQLite database and all tables on first launch, then loads all cogs automatically.

---

## Commands

| Command | Description |
|---|---|
| `!record <rtw> @P1 <rounds> @P2 <rounds> ...` | Record a match result. `rtw` = rounds to win (≥10 for 1v1). Exactly one player must have `rtw` rounds. |
| `!bet <rtw> @P1 @P2 [@P3 ...]` | Open a 2-minute betting window for an upcoming match. |
| `!stats @Player` | Show 1v1 and MP stats for a player. |
| `!matchstats @Player` | Show head-to-head history vs. each opponent. |
| `!lb` | 1v1 SP leaderboard. |
| `!mlb` | Multiplayer SP leaderboard. |
| `!slb` | Straftcoin balance leaderboard. |
| `!help` | List all commands with usage examples. |
| `!undo` | *(Admin only)* Revert the most recent match. |

### Placing Bets

Inside a `!bet` thread, after the odds image is posted:

- **Single bet**: `<label> <stake>` — e.g. `A 200`
- **Parlay**: `P <label1> <label2> ... <stake>` — e.g. `P A C 200`

All bets are placed in Straftcoin. New players start with 1,000 SC.

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
