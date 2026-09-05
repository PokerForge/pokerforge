"""Coverage for core/stats.py's preflop flag engine — the raise-level
state machine behind VPIP/PFR/3-bet/4-bet/squeeze is the single most
load-bearing (and least self-evidently-correct-by-reading) piece of the
whole stats product, so it gets built up from explicit, hand-traced action
sequences rather than only exercised indirectly through the UI."""
from models.hand import Hand, Player, Action
from core.stats import (
    analyze_preflop, analyze_showdown, compute_invested, aggregate_player_stats,
)


def _hand(actions, players=("BTN", "SB", "BB"), board=None, winnings=None, big_blind=0.30, hand_id="1"):
    return Hand(
        hand_id=hand_id,
        big_blind=big_blind,
        players=[Player(name=n) for n in players],
        actions=[Action(street, player, action, amount) for street, player, action, amount in actions],
        board=board or [],
        winnings=winnings or {},
    )


def test_open_raise_and_a_flat_call():
    hand = _hand([
        ("PREFLOP", "SB", "Post SB", 0.15),
        ("PREFLOP", "BB", "Post BB", 0.30),
        ("PREFLOP", "BTN", "Raise", 0.90),
        ("PREFLOP", "SB", "Fold", None),
        ("PREFLOP", "BB", "Call", 0.60),
    ])
    flags = analyze_preflop(hand)

    assert flags["BTN"].vpip is True and flags["BTN"].pfr is True
    assert flags["BTN"].three_bet_opp is False  # opening isn't "facing" a raise

    assert flags["SB"].vpip is False and flags["SB"].pfr is False
    assert flags["SB"].three_bet_opp is True and flags["SB"].folded_vs_open is True
    assert flags["SB"].three_bet is False

    assert flags["BB"].vpip is True and flags["BB"].pfr is False
    assert flags["BB"].three_bet_opp is True and flags["BB"].three_bet is False


def test_direct_three_bet_with_no_prior_call_is_not_a_squeeze():
    hand = _hand([
        ("PREFLOP", "SB", "Post SB", 0.15),
        ("PREFLOP", "BB", "Post BB", 0.30),
        ("PREFLOP", "BTN", "Raise", 0.90),
        ("PREFLOP", "SB", "Raise", 2.70),
        ("PREFLOP", "BB", "Fold", None),
        ("PREFLOP", "BTN", "Fold", None),
    ])
    flags = analyze_preflop(hand)

    assert flags["SB"].three_bet_opp is True and flags["SB"].three_bet is True
    assert flags["SB"].squeeze_opp is False and flags["SB"].squeeze is False

    assert flags["BTN"].faced_3bet_opp is True and flags["BTN"].folded_to_3bet is True
    assert flags["BTN"].four_bet_opp is True and flags["BTN"].four_bet is False
    assert flags["BTN"].squeeze_def_opp is False  # no squeeze happened, just a plain 3-bet

    assert flags["BB"].faced_3bet_opp is True and flags["BB"].folded_to_3bet is True


def test_squeeze_is_a_3bet_that_follows_a_call_not_a_direct_reraise():
    hand = _hand([
        ("PREFLOP", "SB", "Post SB", 0.15),
        ("PREFLOP", "BB", "Post BB", 0.30),
        ("PREFLOP", "BTN", "Raise", 0.90),
        ("PREFLOP", "SB", "Call", 0.75),
        ("PREFLOP", "BB", "Raise", 3.00),
        ("PREFLOP", "BTN", "Fold", None),
        ("PREFLOP", "SB", "Fold", None),
    ])
    flags = analyze_preflop(hand)

    assert flags["BB"].three_bet is True
    assert flags["BB"].squeeze_opp is True and flags["BB"].squeeze is True

    # Both the opener and the caller are "squeeze defense" opportunities.
    assert flags["BTN"].squeeze_def_opp is True and flags["BTN"].folded_to_squeeze is True
    assert flags["SB"].squeeze_def_opp is True and flags["SB"].folded_to_squeeze is True
    assert flags["BTN"].raised_vs_squeeze is False and flags["SB"].raised_vs_squeeze is False


def test_four_bet_after_facing_a_3bet():
    hand = _hand([
        ("PREFLOP", "SB", "Post SB", 0.15),
        ("PREFLOP", "BB", "Post BB", 0.30),
        ("PREFLOP", "BTN", "Raise", 0.90),
        ("PREFLOP", "SB", "Raise", 2.70),
        ("PREFLOP", "BB", "Fold", None),
        ("PREFLOP", "BTN", "Raise", 7.00),
        ("PREFLOP", "SB", "Fold", None),
    ])
    flags = analyze_preflop(hand)

    assert flags["BTN"].faced_3bet_opp is True
    assert flags["BTN"].four_bet is True
    assert flags["SB"].faced_4bet_opp is True and flags["SB"].folded_to_4bet is True


def test_bb_walk_is_not_a_vpip_pfr_opportunity():
    """BB never acts because everyone else folded — PT4 excludes a walked
    BB from the VPIP/PFR denominator entirely (no decision was made)."""
    hand = _hand([
        ("PREFLOP", "SB", "Post SB", 0.15),
        ("PREFLOP", "BB", "Post BB", 0.30),
        ("PREFLOP", "SB", "Fold", None),
    ])
    flags = analyze_preflop(hand)
    assert flags["BB"].vpip_pfr_opp is False


def test_bb_defending_is_a_vpip_pfr_opportunity_even_without_voluntary_money():
    hand = _hand([
        ("PREFLOP", "SB", "Post SB", 0.15),
        ("PREFLOP", "BB", "Post BB", 0.30),
        ("PREFLOP", "SB", "Raise", 0.90),
        ("PREFLOP", "BB", "Fold", None),
    ])
    flags = analyze_preflop(hand)
    assert flags["BB"].vpip_pfr_opp is True
    assert flags["BB"].vpip is False


def test_compute_invested_caps_the_larger_stack_down_to_the_second_largest():
    hand = _hand([
        ("FLOP", "BTN", "Bet", 5.00),
        ("FLOP", "SB", "Allin", 2.00),
    ], board=["2♠", "3♦", "4♥"])
    invested = compute_invested(hand)
    assert invested == {"BTN": 2.00, "SB": 2.00}


def test_compute_invested_no_capping_when_amounts_match():
    hand = _hand([
        ("FLOP", "BTN", "Bet", 3.00),
        ("FLOP", "SB", "Call", 3.00),
    ], board=["2♠", "3♦", "4♥"])
    invested = compute_invested(hand)
    assert invested == {"BTN": 3.00, "SB": 3.00}


def test_analyze_showdown_two_way_showdown_vs_a_preflop_fold():
    hand = _hand([
        ("PREFLOP", "SB", "Post SB", 0.15),
        ("PREFLOP", "BB", "Post BB", 0.30),
        ("PREFLOP", "BTN", "Fold", None),
        ("PREFLOP", "SB", "Call", 0.15),
        ("FLOP", "SB", "Check", None),
        ("FLOP", "BB", "Check", None),
        ("TURN", "SB", "Check", None),
        ("TURN", "BB", "Check", None),
        ("RIVER", "SB", "Check", None),
        ("RIVER", "BB", "Check", None),
    ], board=["2♠", "3♦", "4♥", "5♣", "6♠"], winnings={"SB": 0.60})
    result = analyze_showdown(hand)

    assert result["BTN"].saw_flop is False
    assert result["BTN"].reached_showdown is False

    assert result["SB"].saw_flop is True
    assert result["SB"].reached_showdown is True
    assert result["SB"].won_hand is True

    assert result["BB"].reached_showdown is True
    assert result["BB"].won_hand is False


def test_analyze_showdown_uncontested_win_is_not_a_showdown():
    hand = _hand([
        ("PREFLOP", "SB", "Post SB", 0.15),
        ("PREFLOP", "BB", "Post BB", 0.30),
        ("PREFLOP", "BTN", "Fold", None),
        ("PREFLOP", "SB", "Fold", None),
    ], winnings={"BB": 0.15})
    result = analyze_showdown(hand)
    assert result["BB"].reached_showdown is False
    assert result["BB"].won_hand is True


def test_aggregate_player_stats_over_multiple_hands():
    hand1 = _hand([
        ("PREFLOP", "SB", "Post SB", 0.15),
        ("PREFLOP", "BB", "Post BB", 0.30),
        ("PREFLOP", "BTN", "Raise", 0.90),
        ("PREFLOP", "SB", "Fold", None),
        ("PREFLOP", "BB", "Fold", None),
    ], winnings={"BTN": 0.45}, hand_id="h1")
    hand2 = _hand([
        ("PREFLOP", "SB", "Post SB", 0.15),
        ("PREFLOP", "BB", "Post BB", 0.30),
        ("PREFLOP", "BTN", "Fold", None),
        ("PREFLOP", "SB", "Fold", None),
    ], winnings={"BB": 0.15}, hand_id="h2")

    agg = aggregate_player_stats([hand1, hand2], "BTN")
    assert agg.hands == 2
    assert agg.vpip == 1
    assert agg.pfr == 1
    assert agg.vpip_pct == 50.0
    assert agg.pfr_pct == 50.0


def test_aggregate_player_stats_ignores_hands_the_player_wasnt_in():
    hand = _hand([
        ("PREFLOP", "SB", "Post SB", 0.15),
        ("PREFLOP", "BB", "Post BB", 0.30),
        ("PREFLOP", "BTN", "Fold", None),
        ("PREFLOP", "SB", "Fold", None),
    ], winnings={"BB": 0.15})
    agg = aggregate_player_stats([hand], "SomeoneNotInThisHand")
    assert agg.hands == 0
