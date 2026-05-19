import pytest
from helpers.command_helpers import sc_fmt, get_rank, match_to_db

# ── sc_fmt ────────────────────────────────────────────────────────────────────

def test_sc_fmt_zero():
    assert sc_fmt(0) == "0"

def test_sc_fmt_small():
    assert sc_fmt(999) == "999"

def test_sc_fmt_thousands():
    assert sc_fmt(1000) == "1,000"

def test_sc_fmt_millions():
    assert sc_fmt(3000000) == "3,000,000"

def test_sc_fmt_negative():
    assert sc_fmt(-5000) == "-5,000"

# ── get_rank ──────────────────────────────────────────────────────────────────

async def test_get_rank_zero_sp():
    rank, _ = await get_rank(0)
    assert rank == "Shitterton IV"

async def test_get_rank_mid_sp():
    rank, _ = await get_rank(1000)
    assert rank == "Bronze III"

async def test_get_rank_high_sp():
    rank, _ = await get_rank(4800)
    assert rank == "Daddy"

async def test_get_rank_boundary():
    rank_below, _ = await get_rank(799)
    rank_at, _    = await get_rank(800)
    assert rank_below == "Shitterton I"
    assert rank_at    == "Bronze IV"

# ── match_to_db — 1v1 ────────────────────────────────────────────────────────

P1, P2, P3, P4 = 1, 2, 3, 4

async def _seed_players(db, *ids):
    for uid in ids:
        await db.execute(
            "INSERT OR IGNORE INTO players (user_id) VALUES (?)", (uid,)
        )
    await db.commit()

async def test_1v1_winner_gains_sp_loser_loses_sp(db):
    await _seed_players(db, P1, P2)
    results = await match_to_db([(P1, 10), (P2, 7)], rounds_to_win=10, db=db)
    winner = next(r for r in results if r['player_id'] == P1)
    loser  = next(r for r in results if r['player_id'] == P2)
    assert winner['sp_change'] > 0
    assert loser['sp_change']  < 0

async def test_1v1_elo_is_zero_sum(db):
    await _seed_players(db, P1, P2)
    results = await match_to_db([(P1, 10), (P2, 5)], rounds_to_win=10, db=db)
    total_elo = sum(r['elo_change'] for r in results)
    assert abs(total_elo) < 0.05

async def test_1v1_upset_gives_more_sp(db):
    # Underdog (P2, higher number = lower rating initially) beats favourite
    await _seed_players(db, P1, P2)
    await db.execute("UPDATE players SET rating_1v1 = 1400 WHERE user_id = ?", (P1,))
    await db.execute("UPDATE players SET rating_1v1 = 1000 WHERE user_id = ?", (P2,))
    await db.commit()

    results_upset = await match_to_db([(P2, 10), (P1, 7)], rounds_to_win=10, db=db)
    upset_winner_sp = next(r['sp_change'] for r in results_upset if r['player_id'] == P2)

    # Reset ratings and run the expected outcome (favourite wins)
    await db.execute("UPDATE players SET rating_1v1 = 1400 WHERE user_id = ?", (P1,))
    await db.execute("UPDATE players SET rating_1v1 = 1000 WHERE user_id = ?", (P2,))
    await db.commit()
    results_expected = await match_to_db([(P1, 10), (P2, 7)], rounds_to_win=10, db=db)
    expected_winner_sp = next(r['sp_change'] for r in results_expected if r['player_id'] == P1)

    assert upset_winner_sp > expected_winner_sp

async def test_1v1_placement_order(db):
    await _seed_players(db, P1, P2)
    results = await match_to_db([(P1, 10), (P2, 6)], rounds_to_win=10, db=db)
    assert results[0]['placement'] == 1
    assert results[1]['placement'] == 2

async def test_1v1_winner_is_placement_1(db):
    await _seed_players(db, P1, P2)
    results = await match_to_db([(P2, 10), (P1, 4)], rounds_to_win=10, db=db)
    winner = next(r for r in results if r['placement'] == 1)
    assert winner['player_id'] == P2

# ── match_to_db — MP ─────────────────────────────────────────────────────────

async def test_mp_top_half_gain_sp_bottom_half_lose(db):
    await _seed_players(db, P1, P2, P3, P4)
    results = await match_to_db(
        [(P1, 10), (P2, 7), (P3, 4), (P4, 2)], rounds_to_win=10, db=db
    )
    by_place = {r['placement']: r['sp_change'] for r in results}
    assert by_place[1] > 0
    assert by_place[2] > 0
    assert by_place[3] < 0
    assert by_place[4] < 0

async def test_mp_scale_shorter_game_gives_less_sp(db):
    await _seed_players(db, P1, P2, P3, P4)
    results_full = await match_to_db(
        [(P1, 10), (P2, 7), (P3, 4), (P4, 2)], rounds_to_win=10, db=db
    )
    sp_full = next(r['sp_change'] for r in results_full if r['placement'] == 1)

    # Reset and run same game but shorter
    await db.execute("UPDATE players SET sp_mp=0, wins_mp=0, losses_mp=0, rounds_won_mp=0, rounds_lost_mp=0 WHERE user_id IN (1,2,3,4)")
    await db.commit()
    results_short = await match_to_db(
        [(P1, 5), (P2, 4), (P3, 2), (P4, 1)], rounds_to_win=5, db=db
    )
    sp_short = next(r['sp_change'] for r in results_short if r['placement'] == 1)

    assert sp_short < sp_full

async def test_mp_tie_same_placement(db):
    await _seed_players(db, P1, P2, P3, P4)
    results = await match_to_db(
        [(P1, 10), (P2, 5), (P3, 5), (P4, 2)], rounds_to_win=10, db=db
    )
    p2_place = next(r['placement'] for r in results if r['player_id'] == P2)
    p3_place = next(r['placement'] for r in results if r['player_id'] == P3)
    assert p2_place == p3_place
