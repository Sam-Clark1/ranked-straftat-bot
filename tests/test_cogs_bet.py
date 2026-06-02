import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from cogs.bet import Bet

# ── _h2h_has_cycle ────────────────────────────────────────────────────────────

def test_h2h_no_cycle():
    graph = {1: [2], 1: [3]}  # A→B, A→C
    assert Bet._h2h_has_cycle(graph) is False

def test_h2h_two_cycle():
    graph = {1: [2], 2: [1]}
    assert Bet._h2h_has_cycle(graph) is True

def test_h2h_three_cycle():
    graph = {1: [2], 2: [3], 3: [1]}
    assert Bet._h2h_has_cycle(graph) is True

def test_h2h_chain_no_cycle():
    graph = {1: [2], 2: [3], 3: [4]}
    assert Bet._h2h_has_cycle(graph) is False

def test_h2h_empty_graph():
    assert Bet._h2h_has_cycle({}) is False

# ── _has_parlay_conflict ──────────────────────────────────────────────────────

def _bet(type_, pid_a=1, pid_b=None, value='+3.5', odds=-110):
    return {
        'type': type_,
        'display': f'{type_}_{pid_a}',
        'value': value,
        'odds': odds,
        'player_bet_on_id': pid_a,
        'player_b_id': pid_b,
        'self_bettable_ids': set(),
    }

def _bets_info(*bets):
    labels = [chr(65 + i) for i in range(len(bets))]
    return labels, {lbl: b for lbl, b in zip(labels, bets)}

def test_two_moneylines_conflict():
    labels, info = _bets_info(_bet('moneyline', 1), _bet('moneyline', 2))
    assert Bet._has_parlay_conflict(labels, info) is True

def test_single_moneyline_no_conflict():
    labels, info = _bets_info(_bet('moneyline', 1))
    assert Bet._has_parlay_conflict(labels, info) is False

def test_fav_spread_and_dog_moneyline_conflict():
    labels, info = _bets_info(
        _bet('spread', pid_a=1, value='-3.5'),  # fav spread
        _bet('moneyline', pid_a=2),              # dog moneyline
    )
    assert Bet._has_parlay_conflict(labels, info) is True

def test_fav_spread_and_fav_moneyline_conflict():
    # Can't parlay fav spread + any moneyline (fav spread blocks all ML)
    labels, info = _bets_info(
        _bet('spread', pid_a=1, value='-3.5'),
        _bet('moneyline', pid_a=1),
    )
    assert Bet._has_parlay_conflict(labels, info) is True

def test_dog_spread_and_dog_moneyline_conflict():
    # underdog spread + underdog moneyline is correlated
    labels, info = _bets_info(
        _bet('spread', pid_a=2, value='+3.5'),
        _bet('moneyline', pid_a=2),
    )
    assert Bet._has_parlay_conflict(labels, info) is True

def test_h2h_opposite_directions_conflict():
    labels, info = _bets_info(
        _bet('head_to_head', pid_a=1, pid_b=2),
        _bet('head_to_head', pid_a=2, pid_b=1),
    )
    assert Bet._has_parlay_conflict(labels, info) is True

def test_h2h_cycle_conflict():
    labels, info = _bets_info(
        _bet('head_to_head', pid_a=1, pid_b=2),
        _bet('head_to_head', pid_a=2, pid_b=3),
        _bet('head_to_head', pid_a=3, pid_b=1),
    )
    assert Bet._has_parlay_conflict(labels, info) is True

def test_h2h_no_conflict():
    labels, info = _bets_info(
        _bet('head_to_head', pid_a=1, pid_b=2),
        _bet('head_to_head', pid_a=1, pid_b=3),
    )
    assert Bet._has_parlay_conflict(labels, info) is False

def test_two_last_place_conflict():
    labels, info = _bets_info(
        _bet('last_place', pid_a=1),
        _bet('last_place', pid_a=2),
    )
    assert Bet._has_parlay_conflict(labels, info) is True

def test_last_place_and_h2h_winner_conflict():
    labels, info = _bets_info(
        _bet('head_to_head', pid_a=1, pid_b=2),  # 1 beats 2
        _bet('last_place', pid_a=1),              # 1 is last - contradiction
    )
    assert Bet._has_parlay_conflict(labels, info) is True

def test_last_place_and_h2h_loser_conflict():
    labels, info = _bets_info(
        _bet('head_to_head', pid_a=1, pid_b=2),  # 1 beats 2
        _bet('last_place', pid_a=2),              # 2 is last - correlated
    )
    assert Bet._has_parlay_conflict(labels, info) is True

def test_ou_over_and_under_conflict():
    labels, info = _bets_info(
        _bet('ou_total', value='O16.5'),
        _bet('ou_total', value='U16.5'),
    )
    assert Bet._has_parlay_conflict(labels, info) is True

def test_valid_moneyline_and_ou_total():
    labels, info = _bets_info(
        _bet('moneyline', pid_a=1),
        _bet('ou_total', value='O16.5'),
    )
    assert Bet._has_parlay_conflict(labels, info) is False

def test_valid_h2h_and_last_place_unrelated():
    # H2H between players 1 and 2; last place on player 3 - no conflict
    labels, info = _bets_info(
        _bet('head_to_head', pid_a=1, pid_b=2),
        _bet('last_place', pid_a=3),
    )
    assert Bet._has_parlay_conflict(labels, info) is False
