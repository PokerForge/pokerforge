"""core/demo_data.py — the generated hands must be structurally valid
enough for the real stat engine to process without error (that's the
actual bar; the poker logic itself is deliberately simplified, not a
faithful simulation — see the module's own docstring)."""
import pytest

from core.demo_data import generate_demo_hands, DEMO_HERO
from core.stats import analyze_preflop, analyze_showdown, compute_invested, aggregate_player_stats
from core.position import assign_positions


def test_generates_the_requested_number_of_hands():
    hands = generate_demo_hands(n=50)
    assert len(hands) == 50


def test_same_seed_is_deterministic():
    a = generate_demo_hands(n=20, seed=7)
    b = generate_demo_hands(n=20, seed=7)
    assert [h.hand_id for h in a] == [h.hand_id for h in b]
    assert [h.winnings for h in a] == [h.winnings for h in b]


def test_different_seeds_produce_different_hands():
    a = generate_demo_hands(n=20, seed=1)
    b = generate_demo_hands(n=20, seed=2)
    assert [h.winnings for h in a] != [h.winnings for h in b]


def test_hero_appears_in_every_hand():
    hands = generate_demo_hands(n=100)
    for h in hands:
        assert any(p.name == DEMO_HERO for p in h.players)


def test_every_hand_has_a_winner_who_gets_the_pot():
    hands = generate_demo_hands(n=100)
    for h in hands:
        assert h.winnings
        assert sum(h.winnings.values()) > 0


def test_every_hand_survives_the_real_stat_engine():
    hands = generate_demo_hands(n=300)
    for h in hands:
        analyze_preflop(h)
        analyze_showdown(h)
        compute_invested(h)
        assign_positions(h)  # must resolve for the fixed 6-max seat layout used


def test_hands_are_chronologically_ordered():
    hands = generate_demo_hands(n=100)
    timestamps = [h.played_at for h in hands]
    assert timestamps == sorted(timestamps)


def test_hero_aggregate_stats_are_in_plausible_ranges():
    hands = generate_demo_hands(n=1000)
    agg = aggregate_player_stats(hands, DEMO_HERO)
    assert agg.hands == 1000
    assert 0 < agg.vpip_pct < 100
    assert 0 < agg.pfr_pct < 100
    assert agg.pfr_pct <= agg.vpip_pct + 1  # PFR can't meaningfully exceed VPIP
