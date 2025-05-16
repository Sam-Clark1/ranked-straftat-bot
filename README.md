# Ranked-Straftat-Bot

A Discord bot to facilitate ranked 1v1 gameplay in [Straftat](https://store.steampowered.com/app/2386720/STRAFTAT/), complete with Elo & Ranked Points (SP) tracking, in-game currency betting with basic ML-powered match predictions, and leaderboards

---

## 🚀 Features
All features can be accessed through commands in a discord chat
- **Match Recording**  
  Log match results (`!record`) and automatically update:
  - Elo rating  
  - Skill Points (SP)  
  - “Straftcoin” balance (in-game currency)  
  - Win/loss and round statistics  
  - Ex: !record @Player1 @Player2 Winner's Total Rounds Loser's Total Rounds
  - NOTE: Games are played to a total of 10 rounds so Winner's Total Rounds will always be 10

- **Player Statistics**  
  - `!stats @Player` shows overall stats (win%, SP, rating, balance, etc.)  
  - `!matchstats @Player` breaks down head-to-head performance vs. each opponent  

- **Leaderboards**  
  - `!lb` — SP-based global ranking  
  - `!slb` — Straftcoin balance ranking  

- **Betting System**  
  - `!bet @Player1 @Player2` opens a 2-minute betting thread  
  - Place Spread, Moneyline, or Over/Under bets with virtual Straftcoin  
  - Automatic settlement when match is recorded  

- **Help & Guidance**  
  - `!help` lists all commands with usage examples  

- **Prediction Models**  
  - Trains an XGBoost regressor on past matches to predict match spread  
  - Model retraining triggered on each `!record`  

---

## 📋 Table of Contents

1. [Prerequisites](#-prerequisites)  
2. [Installation](#-installation)  
3. [Configuration](#-configuration)  
4. [Running the Bot](#-running-the-bot)  
5. [Commands](#-commands)  
6. [Development & Contributing](#-development--contributing)  
7. [License](#-license)  

---

## 🔧 Prerequisites

- **Python 3.8+**  
- Discord bot token & “Message Content Intent” enabled  
- Recommended packages (see `requirements.txt`):

  ```text
  discord.py
  aiosqlite
  python-dotenv
  pandas
  matplotlib
  xgboost
  scikit-learn