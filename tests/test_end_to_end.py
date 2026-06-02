"""
End-to-end tests: record a match then settle its bets, verifying the full
pipeline through match_to_db → win_loss_determination → handle_bet_payouts.
"""
import pytest
from helpers.command_helpers import match_to_db
from helpers.bet_helpers import handle_bet_payouts, _american_to_decimal

P1, P2, P3, P4 = 10, 20, 30, 40
BETTOR = 99
STAKE  = 200

async def _seed(db, *ids):
    for uid in ids:
        await db.execute(
            "INSERT OR IGNORE INTO players (user_id, straftcoins) VALUES (?, 5000)", (uid,)
        )
    await db.commit()

async def _place_bet(db, match_title, bet_type, bet_value, odds, player_a, player_b=None):
    await db.execute(
        "INSERT INTO live_bets "
        "(user_id, match_title, player_bet_on_id, player_b_id, bet_type, bet_value, bet_odds, bet_amount, parlay_id) "
        "VALUES (?,?,?,?,?,?,?,?,NULL)",
        (BETTOR, match_title, player_a, player_b, bet_type, bet_value, odds, STAKE)
    )
    await db.execute(
        "UPDATE players SET straftcoins = straftcoins - ? WHERE user_id = ?",
        (STAKE, BETTOR)
    )
    await db.commit()

async def _settle(db, results, match_title):
    winner = results[0]
    second = results[1]
    spread = winner['rounds_won'] - second['rounds_won']
    total  = sum(r['rounds_won'] for r in results)
    return await handle_bet_payouts(
        winner['match_id'], match_title, winner['player_id'],
        spread, total, db
    )

async def _bettor_balance(db):
    async with db.execute("SELECT straftcoins FROM players WHERE user_id = ?", (BETTOR,)) as cur:
        row = await cur.fetchone()
    return row[0]

async def _past_bet_result(db):
    async with db.execute("SELECT result FROM past_bets WHERE user_id = ?", (BETTOR,)) as cur:
        row = await cur.fetchone()
    return row[0] if row else None

async def _live_bets_count(db):
    async with db.execute("SELECT COUNT(*) FROM live_bets") as cur:
        return (await cur.fetchone())[0]

# ── 1v1 moneyline win ─────────────────────────────────────────────────────────

async def test_1v1_moneyline_bet_win(db):
    await _seed(db, P1, P2, BETTOR)
    title = "[FT10] P1 vs P2"
    await _place_bet(db, title, 'moneyline', 'P1 wins', odds=-150, player_a=P1)

    results = await match_to_db([(P1, 10), (P2, 7)], rounds_to_win=10, db=db)
    await _settle(db, results, title)

    assert await _past_bet_result(db) == 'win'
    assert await _live_bets_count(db) == 0
    # Balance should be above starting 5000 - STAKE (bettor won)
    assert await _bettor_balance(db) > 5000 - STAKE

# ── 1v1 spread loss ───────────────────────────────────────────────────────────

async def test_1v1_spread_bet_loss(db):
    await _seed(db, P1, P2, BETTOR)
    title = "[FT10] P1 vs P2"
    # Bet favourite (-3.5) but actual spread = 2 - doesn't cover
    await _place_bet(db, title, 'spread', '-3.5', odds=-110, player_a=P1)

    results = await match_to_db([(P1, 10), (P2, 8)], rounds_to_win=10, db=db)
    await _settle(db, results, title)

    assert await _past_bet_result(db) == 'loss'
    assert await _live_bets_count(db) == 0
    assert await _bettor_balance(db) == 5000 - STAKE  # stake lost

# ── 1v1 spread push ───────────────────────────────────────────────────────────

async def test_1v1_spread_push(db):
    await _seed(db, P1, P2, BETTOR)
    title = "[FT10] P1 vs P2"
    await _place_bet(db, title, 'spread', '-3.0', odds=-110, player_a=P1)

    results = await match_to_db([(P1, 10), (P2, 7)], rounds_to_win=10, db=db)
    await _settle(db, results, title)

    assert await _past_bet_result(db) == 'push'
    assert await _bettor_balance(db) == 5000  # stake returned

# ── MP last place win ─────────────────────────────────────────────────────────

async def test_mp_last_place_bet_win(db):
    await _seed(db, P1, P2, P3, P4, BETTOR)
    title = "[FT10] MP"
    await _place_bet(db, title, 'last_place', 'P4 last', odds=200, player_a=P4)

    results = await match_to_db(
        [(P1, 10), (P2, 7), (P3, 4), (P4, 1)], rounds_to_win=10, db=db
    )
    await _settle(db, results, title)

    assert await _past_bet_result(db) == 'win'
    assert await _live_bets_count(db) == 0

# ── MP last place tied push ───────────────────────────────────────────────────

async def test_mp_last_place_tied_push(db):
    await _seed(db, P1, P2, P3, P4, BETTOR)
    title = "[FT10] MP"
    await _place_bet(db, title, 'last_place', 'P3 last', odds=200, player_a=P3)

    results = await match_to_db(
        [(P1, 10), (P2, 7), (P3, 4), (P4, 4)], rounds_to_win=10, db=db
    )
    await _settle(db, results, title)

    assert await _past_bet_result(db) == 'push'
    assert await _bettor_balance(db) == 5000  # stake returned

# ── Parlay - both legs win ────────────────────────────────────────────────────

async def test_parlay_both_legs_win(db):
    await _seed(db, P1, P2, BETTOR)
    title = "[FT10] P1 vs P2"

    # Build a 2-leg parlay manually
    ml_odds  = -150
    ou_odds  = -110
    mult = round(_american_to_decimal(ml_odds) * _american_to_decimal(ou_odds), 4)
    payout = round(STAKE * mult)

    cur = await db.execute(
        "INSERT INTO parlays (user_id, match_title, total_stake, num_legs, combined_multiplier) "
        "VALUES (?,?,?,?,?)", (BETTOR, title, STAKE, 2, mult)
    )
    parlay_id = cur.lastrowid

    for bet_type, bet_value, odds, player_a in [
        ('moneyline', 'P1 wins', ml_odds, P1),
        ('ou_total',  'O16.5',   ou_odds, None),
    ]:
        await db.execute(
            "INSERT INTO live_bets "
            "(user_id, match_title, player_bet_on_id, player_b_id, bet_type, bet_value, bet_odds, bet_amount, parlay_id) "
            "VALUES (?,?,?,NULL,?,?,?,?,?)",
            (BETTOR, title, player_a, bet_type, bet_value, odds, STAKE, parlay_id)
        )
    await db.execute(
        "UPDATE players SET straftcoins = straftcoins - ? WHERE user_id = ?", (STAKE, BETTOR)
    )
    await db.commit()

    # Record match: P1 wins 10-7 (total=17 > 16.5)
    results = await match_to_db([(P1, 10), (P2, 7)], rounds_to_win=10, db=db)
    await _settle(db, results, title)

    async with db.execute("SELECT status, payout FROM parlays WHERE parlay_id = ?", (parlay_id,)) as cur:
        row = await cur.fetchone()
    assert row[0] == 'won'
    assert row[1] == payout
    assert await _bettor_balance(db) == 5000 - STAKE + payout

# ── Parlay - one leg loses ────────────────────────────────────────────────────

async def test_parlay_one_leg_loses(db):
    await _seed(db, P1, P2, BETTOR)
    title = "[FT10] P1 vs P2"

    ml_odds  = -150
    ou_odds  = -110
    mult = round(_american_to_decimal(ml_odds) * _american_to_decimal(ou_odds), 4)

    cur = await db.execute(
        "INSERT INTO parlays (user_id, match_title, total_stake, num_legs, combined_multiplier) "
        "VALUES (?,?,?,?,?)", (BETTOR, title, STAKE, 2, mult)
    )
    parlay_id = cur.lastrowid

    for bet_type, bet_value, odds, player_a in [
        ('moneyline', 'P1 wins', ml_odds, P1),
        ('ou_total',  'U16.5',   ou_odds, None),  # Under - will lose (total=17)
    ]:
        await db.execute(
            "INSERT INTO live_bets "
            "(user_id, match_title, player_bet_on_id, player_b_id, bet_type, bet_value, bet_odds, bet_amount, parlay_id) "
            "VALUES (?,?,?,NULL,?,?,?,?,?)",
            (BETTOR, title, player_a, bet_type, bet_value, odds, STAKE, parlay_id)
        )
    await db.execute(
        "UPDATE players SET straftcoins = straftcoins - ? WHERE user_id = ?", (STAKE, BETTOR)
    )
    await db.commit()

    results = await match_to_db([(P1, 10), (P2, 7)], rounds_to_win=10, db=db)
    await _settle(db, results, title)

    async with db.execute("SELECT status FROM parlays WHERE parlay_id = ?", (parlay_id,)) as cur:
        row = await cur.fetchone()
    assert row[0] == 'lost'
    assert await _bettor_balance(db) == 5000 - STAKE  # no payout
