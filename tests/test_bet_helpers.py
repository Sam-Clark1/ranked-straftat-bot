import pytest
from helpers.bet_helpers import (
    percentage_to_odds, odds_to_percentage,
    _american_to_decimal, _format_odds, _multiplier_to_american,
    win_loss_determination,
)

# ── Odds utilities ────────────────────────────────────────────────────────────

async def test_percentage_to_odds_favourite():
    odds = await percentage_to_odds(0.7)
    assert odds < 0  # favourite → negative American

async def test_percentage_to_odds_underdog():
    odds = await percentage_to_odds(0.3)
    assert odds > 0  # underdog → positive American

async def test_percentage_to_odds_even():
    odds = await percentage_to_odds(0.5)
    assert odds == -100

def test_american_to_decimal_negative():
    result = _american_to_decimal(-110)
    assert abs(result - 1.909) < 0.01

def test_american_to_decimal_positive():
    result = _american_to_decimal(150)
    assert abs(result - 2.5) < 0.01

def test_format_odds_positive():
    assert _format_odds(150) == "+150"

def test_format_odds_negative():
    assert _format_odds(-110) == "-110"

def test_multiplier_to_american_over_2():
    assert _multiplier_to_american(2.5) == "+150"

def test_multiplier_to_american_under_2():
    assert _multiplier_to_american(1.5) == "-200"

async def test_odds_to_percentage_win():
    payout, _ = await odds_to_percentage('win', -110, 110)
    assert payout == 210  # stake × decimal

async def test_odds_to_percentage_loss():
    _, lost = await odds_to_percentage('loss', -110, 100)
    assert lost == 100

async def test_odds_to_percentage_push():
    payout, lost = await odds_to_percentage('push', -110, 100)
    assert payout == 0 and lost == 0

# ── win_loss_determination ────────────────────────────────────────────────────

MATCH_ID  = 1
WINNER_ID = 10
LOSER_ID  = 20
BETTOR_ID = 99

def _make_bet(bet_id, bet_type, bet_value, odds=-110, amount=100,
              player_a=WINNER_ID, player_b=None, parlay_id=None):
    return (bet_id, BETTOR_ID, "test match",
            player_a, player_b,
            bet_type, bet_value, odds, amount,
            parlay_id)

async def _setup_participants(db, participants):
    await db.execute(
        "INSERT INTO matches (match_id, rounds_to_win, total_rounds, game_mode) VALUES (?,?,?,?)",
        (MATCH_ID, 10, sum(r for _, r in participants), '1v1' if len(participants) == 2 else 'mp')
    )
    for pid, (player_id, rounds), placement in zip(
        range(1, len(participants)+1), participants, range(1, len(participants)+1)
    ):
        await db.execute(
            "INSERT INTO match_participants VALUES (?,?,?,?,?,?,?,?)",
            (pid, MATCH_ID, player_id, placement, rounds, 0.0, 0, 0)
        )
    await db.commit()

# Moneyline

async def test_moneyline_winner_wins(db):
    await _setup_participants(db, [(WINNER_ID, 10), (LOSER_ID, 7)])
    bet = _make_bet(1, 'moneyline', 'Player wins', player_a=WINNER_ID)
    all_bets, winning, _ = await win_loss_determination(
        [bet], MATCH_ID, spread=3, winner_id=WINNER_ID, total_rounds=17, db=db
    )
    assert any(b[9] == 'win' for b in all_bets)
    assert len(winning) == 1

async def test_moneyline_loser_loses(db):
    await _setup_participants(db, [(WINNER_ID, 10), (LOSER_ID, 7)])
    bet = _make_bet(1, 'moneyline', 'Player wins', player_a=LOSER_ID)
    all_bets, winning, _ = await win_loss_determination(
        [bet], MATCH_ID, spread=3, winner_id=WINNER_ID, total_rounds=17, db=db
    )
    assert all_bets[0][9] == 'loss'
    assert len(winning) == 0

# Spread

async def test_spread_favourite_covers(db):
    await _setup_participants(db, [(WINNER_ID, 10), (LOSER_ID, 6)])
    bet = _make_bet(1, 'spread', '-3.5', player_a=WINNER_ID)
    all_bets, winning, _ = await win_loss_determination(
        [bet], MATCH_ID, spread=4, winner_id=WINNER_ID, total_rounds=16, db=db
    )
    assert all_bets[0][9] == 'win'

async def test_spread_favourite_fails_to_cover(db):
    await _setup_participants(db, [(WINNER_ID, 10), (LOSER_ID, 8)])
    bet = _make_bet(1, 'spread', '-3.5', player_a=WINNER_ID)
    all_bets, _, _ = await win_loss_determination(
        [bet], MATCH_ID, spread=2, winner_id=WINNER_ID, total_rounds=18, db=db
    )
    assert all_bets[0][9] == 'loss'

async def test_spread_push(db):
    await _setup_participants(db, [(WINNER_ID, 10), (LOSER_ID, 7)])
    bet = _make_bet(1, 'spread', '-3.0', player_a=WINNER_ID)
    all_bets, _, pushed = await win_loss_determination(
        [bet], MATCH_ID, spread=3, winner_id=WINNER_ID, total_rounds=17, db=db
    )
    assert all_bets[0][9] == 'push'
    assert len(pushed) == 1

# O/U Total

async def test_ou_total_over_wins(db):
    await _setup_participants(db, [(WINNER_ID, 10), (LOSER_ID, 7)])
    bet = _make_bet(1, 'ou_total', 'O16.5')
    all_bets, winning, _ = await win_loss_determination(
        [bet], MATCH_ID, spread=3, winner_id=WINNER_ID, total_rounds=17, db=db
    )
    assert all_bets[0][9] == 'win'

async def test_ou_total_under_wins(db):
    await _setup_participants(db, [(WINNER_ID, 10), (LOSER_ID, 7)])
    bet = _make_bet(1, 'ou_total', 'U17.5')
    all_bets, winning, _ = await win_loss_determination(
        [bet], MATCH_ID, spread=3, winner_id=WINNER_ID, total_rounds=17, db=db
    )
    assert all_bets[0][9] == 'win'

async def test_ou_total_push(db):
    await _setup_participants(db, [(WINNER_ID, 10), (LOSER_ID, 7)])
    bet = _make_bet(1, 'ou_total', 'O17.0')
    all_bets, _, pushed = await win_loss_determination(
        [bet], MATCH_ID, spread=3, winner_id=WINNER_ID, total_rounds=17, db=db
    )
    assert all_bets[0][9] == 'push'

# O/U Player rounds

async def test_ou_player_over_wins(db):
    await _setup_participants(db, [(WINNER_ID, 10), (LOSER_ID, 7)])
    bet = _make_bet(1, 'ou_player', 'O8.5', player_a=WINNER_ID)
    all_bets, _, _ = await win_loss_determination(
        [bet], MATCH_ID, spread=3, winner_id=WINNER_ID, total_rounds=17, db=db
    )
    assert all_bets[0][9] == 'win'

async def test_ou_player_push(db):
    await _setup_participants(db, [(WINNER_ID, 10), (LOSER_ID, 7)])
    bet = _make_bet(1, 'ou_player', 'O10.0', player_a=WINNER_ID)
    all_bets, _, pushed = await win_loss_determination(
        [bet], MATCH_ID, spread=3, winner_id=WINNER_ID, total_rounds=17, db=db
    )
    assert all_bets[0][9] == 'push'

# H2H

async def test_h2h_winner_wins(db):
    await _setup_participants(db, [(WINNER_ID, 10), (LOSER_ID, 7)])
    bet = _make_bet(1, 'head_to_head', 'W>L', player_a=WINNER_ID, player_b=LOSER_ID)
    all_bets, winning, _ = await win_loss_determination(
        [bet], MATCH_ID, spread=3, winner_id=WINNER_ID, total_rounds=17, db=db
    )
    assert all_bets[0][9] == 'win'

async def test_h2h_loser_loses(db):
    await _setup_participants(db, [(WINNER_ID, 10), (LOSER_ID, 7)])
    bet = _make_bet(1, 'head_to_head', 'L>W', player_a=LOSER_ID, player_b=WINNER_ID)
    all_bets, _, _ = await win_loss_determination(
        [bet], MATCH_ID, spread=3, winner_id=WINNER_ID, total_rounds=17, db=db
    )
    assert all_bets[0][9] == 'loss'

# Last place

async def test_last_place_clear_winner(db):
    # 4-player: P4 clearly last
    await db.execute("INSERT INTO matches VALUES (?,?,?,?,?)", (MATCH_ID, 10, 22, 'mp', '2024-01-01'))
    for pid, player_id, placement, rounds in [
        (1, 10, 1, 10), (2, 20, 2, 7), (3, 30, 3, 4), (4, 40, 4, 1)
    ]:
        await db.execute("INSERT INTO match_participants VALUES (?,?,?,?,?,?,?,?)",
                         (pid, MATCH_ID, player_id, placement, rounds, 0.0, 0, 0))
    await db.commit()
    bet = _make_bet(1, 'last_place', 'P4 last', player_a=40)
    all_bets, winning, _ = await win_loss_determination(
        [bet], MATCH_ID, spread=3, winner_id=10, total_rounds=22, db=db
    )
    assert all_bets[0][9] == 'win'

async def test_last_place_tied_pushes(db):
    # P3 and P4 tie for last
    await db.execute("INSERT INTO matches VALUES (?,?,?,?,?)", (MATCH_ID, 10, 24, 'mp', '2024-01-01'))
    for pid, player_id, placement, rounds in [
        (1, 10, 1, 10), (2, 20, 2, 7), (3, 30, 3, 4), (4, 40, 3, 4)
    ]:
        await db.execute("INSERT INTO match_participants VALUES (?,?,?,?,?,?,?,?)",
                         (pid, MATCH_ID, player_id, placement, rounds, 0.0, 0, 0))
    await db.commit()
    bet = _make_bet(1, 'last_place', 'P3 last', player_a=30)
    all_bets, _, pushed = await win_loss_determination(
        [bet], MATCH_ID, spread=3, winner_id=10, total_rounds=24, db=db
    )
    assert all_bets[0][9] == 'push'

# Podium

async def test_podium_in_top3(db):
    await db.execute("INSERT INTO matches VALUES (?,?,?,?,?)", (MATCH_ID, 10, 22, 'mp', '2024-01-01'))
    for pid, player_id, placement, rounds in [
        (1, 10, 1, 10), (2, 20, 2, 7), (3, 30, 3, 4), (4, 40, 4, 1)
    ]:
        await db.execute("INSERT INTO match_participants VALUES (?,?,?,?,?,?,?,?)",
                         (pid, MATCH_ID, player_id, placement, rounds, 0.0, 0, 0))
    await db.commit()
    bet = _make_bet(1, 'podium', 'P3 top3', player_a=30)
    all_bets, winning, _ = await win_loss_determination(
        [bet], MATCH_ID, spread=3, winner_id=10, total_rounds=22, db=db
    )
    assert all_bets[0][9] == 'win'

async def test_podium_outside_top3(db):
    await db.execute("INSERT INTO matches VALUES (?,?,?,?,?)", (MATCH_ID, 10, 22, 'mp', '2024-01-01'))
    for pid, player_id, placement, rounds in [
        (1, 10, 1, 10), (2, 20, 2, 7), (3, 30, 3, 4), (4, 40, 4, 1)
    ]:
        await db.execute("INSERT INTO match_participants VALUES (?,?,?,?,?,?,?,?)",
                         (pid, MATCH_ID, player_id, placement, rounds, 0.0, 0, 0))
    await db.commit()
    bet = _make_bet(1, 'podium', 'P4 top3', player_a=40)
    all_bets, _, _ = await win_loss_determination(
        [bet], MATCH_ID, spread=3, winner_id=10, total_rounds=22, db=db
    )
    assert all_bets[0][9] == 'loss'

async def test_missing_player_h2h_pushes(db):
    # H2H where one player isn't in the match → push
    await _setup_participants(db, [(WINNER_ID, 10), (LOSER_ID, 7)])
    bet = _make_bet(1, 'head_to_head', 'W>Ghost', player_a=WINNER_ID, player_b=9999)
    all_bets, _, pushed = await win_loss_determination(
        [bet], MATCH_ID, spread=3, winner_id=WINNER_ID, total_rounds=17, db=db
    )
    assert all_bets[0][9] == 'push'
