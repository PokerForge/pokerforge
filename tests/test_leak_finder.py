"""core/leak_finder.py — the ranking logic behind the cross-dimensional
leak finder. Pure function over pre-computed position-breakdown dicts
(the exact shape database.queries.position_breakdown_query /
population_by_position_query already return), so no database needed
here — database/test_queries.py covers those two queries themselves."""
from core.leak_finder import (
    find_leaks, diversify_leaks, find_biggest_improvement, LeakEntry, MIN_SAMPLE, LEAK_CATEGORIES,
)


def _pos_data(rate_by_stat, sample=50):
    """Builds one position's (values, hand_count, opp_counts) tuple."""
    values = dict(rate_by_stat)
    opp_counts = {stat: sample for stat in rate_by_stat}
    return values, sample, opp_counts


def test_finds_a_leak_where_hero_deviates_from_population():
    hero = {"BB": _pos_data({"fold_3bet": 74.0})}
    population = {"BB": _pos_data({"fold_3bet": 55.0})}

    leaks = find_leaks(hero, population)

    assert len(leaks) == 1
    leak = leaks[0]
    assert leak.position == "BB"
    assert leak.stat_id == "fold_3bet"
    assert leak.hero_rate == 74.0
    assert leak.population_rate == 55.0
    assert leak.deviation == 19.0


def test_ranks_by_deviation_times_sample_not_deviation_alone():
    # BTN: huge deviation but small sample; CO: smaller deviation but huge sample.
    hero = {
        "BTN": _pos_data({"three_bet": 20.0}, sample=25),
        "CO": _pos_data({"three_bet": 12.0}, sample=25),
    }
    population = {
        "BTN": _pos_data({"three_bet": 5.0}, sample=25),
        "CO": _pos_data({"three_bet": 8.0}, sample=25),
    }
    # Bump CO's sample way up while keeping the same rates, via opp_counts override.
    hero["CO"][2]["three_bet"] = 5000

    leaks = find_leaks(hero, population)
    assert leaks[0].position == "CO"  # smaller deviation, but sample-weighted score wins


def test_skips_stats_below_the_minimum_sample():
    hero = {"BB": _pos_data({"fold_3bet": 90.0}, sample=MIN_SAMPLE - 1)}
    population = {"BB": _pos_data({"fold_3bet": 55.0}, sample=MIN_SAMPLE - 1)}

    assert find_leaks(hero, population) == []


def test_includes_stats_exactly_at_the_minimum_sample():
    hero = {"BB": _pos_data({"fold_3bet": 90.0}, sample=MIN_SAMPLE)}
    population = {"BB": _pos_data({"fold_3bet": 55.0}, sample=MIN_SAMPLE)}

    assert len(find_leaks(hero, population)) == 1


def test_position_with_no_population_data_is_skipped_not_crashed():
    hero = {"UTG": _pos_data({"vpip": 30.0})}
    population = {}  # hero played a position no population data exists for

    assert find_leaks(hero, population) == []


def test_missing_stat_value_is_skipped_not_treated_as_zero():
    hero = {"BB": ({"vpip": None}, 50, {"vpip": 50})}
    population = {"BB": ({"vpip": 25.0}, 50, {"vpip": 50})}

    assert find_leaks(hero, population) == []


def test_no_deviation_produces_a_zero_score_not_an_error():
    hero = {"BB": _pos_data({"vpip": 25.0})}
    population = {"BB": _pos_data({"vpip": 25.0})}

    leaks = find_leaks(hero, population)
    assert len(leaks) == 1
    assert leaks[0].score == 0.0


def test_multiple_stats_and_positions_all_get_evaluated():
    hero = {
        "BTN": _pos_data({"vpip": 40.0, "pfr": 10.0}),
        "BB": _pos_data({"fold_to_steal": 80.0}),
    }
    population = {
        "BTN": _pos_data({"vpip": 30.0, "pfr": 20.0}),
        "BB": _pos_data({"fold_to_steal": 60.0}),
    }

    leaks = find_leaks(hero, population)
    assert {(l.position, l.stat_id) for l in leaks} == {
        ("BTN", "vpip"), ("BTN", "pfr"), ("BB", "fold_to_steal"),
    }


def _entry(stat_id, position, score):
    return LeakEntry(position=position, stat_id=stat_id, stat_label=stat_id,
                      hero_rate=0.0, population_rate=0.0, sample=100, score=score)


def test_diversify_caps_entries_per_stat_id():
    entries = [
        _entry("vpip", "SB", 100), _entry("vpip", "BB", 90), _entry("vpip", "BTN", 80),
        _entry("three_bet", "CO", 70),
    ]
    diversified = diversify_leaks(entries, max_per_stat=2)
    assert [(e.stat_id, e.position) for e in diversified] == [
        ("vpip", "SB"), ("vpip", "BB"), ("three_bet", "CO"),
    ]


def test_diversify_keeps_the_highest_scoring_entries_for_a_capped_stat():
    # Already sorted by score descending, as find_leaks would produce.
    entries = [_entry("vpip", "SB", 100), _entry("vpip", "BB", 90), _entry("vpip", "UTG", 50)]
    diversified = diversify_leaks(entries, max_per_stat=2)
    assert [e.position for e in diversified] == ["SB", "BB"]


def test_diversify_with_no_entries_over_the_cap_returns_everything():
    entries = [_entry("vpip", "SB", 100), _entry("three_bet", "BB", 90)]
    assert diversify_leaks(entries, max_per_stat=2) == entries


def test_leak_categories_cover_every_stat_with_no_overlap():
    from core.leak_finder import LEAK_STAT_IDS
    all_categorized = [stat_id for stats in LEAK_CATEGORIES.values() for stat_id in stats]
    assert sorted(all_categorized) == sorted(LEAK_STAT_IDS)
    assert len(all_categorized) == len(set(all_categorized))


def test_finds_biggest_improvement_when_deviation_shrank():
    current = {"BB": _pos_data({"fold_3bet": 60.0})}
    previous = {"BB": _pos_data({"fold_3bet": 74.0})}
    current_pop = {"BB": _pos_data({"fold_3bet": 55.0})}
    previous_pop = {"BB": _pos_data({"fold_3bet": 55.0})}

    result = find_biggest_improvement(current, previous, current_pop, previous_pop)

    assert result is not None
    assert result.position == "BB"
    assert result.stat_id == "fold_3bet"
    # |74-55|=19 -> |60-55|=5: improvement of 14
    assert result.improvement == 14.0


def test_returns_none_when_the_deviation_got_worse_not_better():
    current = {"BB": _pos_data({"fold_3bet": 80.0})}
    previous = {"BB": _pos_data({"fold_3bet": 60.0})}
    current_pop = {"BB": _pos_data({"fold_3bet": 55.0})}
    previous_pop = {"BB": _pos_data({"fold_3bet": 55.0})}

    assert find_biggest_improvement(current, previous, current_pop, previous_pop) is None


def test_returns_none_without_enough_sample_in_both_periods():
    current = {"BB": _pos_data({"fold_3bet": 60.0}, sample=MIN_SAMPLE - 1)}
    previous = {"BB": _pos_data({"fold_3bet": 74.0})}
    current_pop = {"BB": _pos_data({"fold_3bet": 55.0})}
    previous_pop = {"BB": _pos_data({"fold_3bet": 55.0})}

    assert find_biggest_improvement(current, previous, current_pop, previous_pop) is None


def test_returns_none_when_position_missing_from_a_prior_period():
    current = {"CO": _pos_data({"fold_3bet": 60.0})}
    previous = {"BB": _pos_data({"fold_3bet": 74.0})}
    current_pop = {"CO": _pos_data({"fold_3bet": 55.0})}
    previous_pop = {"BB": _pos_data({"fold_3bet": 55.0})}

    assert find_biggest_improvement(current, previous, current_pop, previous_pop) is None


def test_picks_the_largest_improvement_across_multiple_candidates():
    current = {
        "BB": _pos_data({"fold_3bet": 60.0}),   # 19 -> 5, improvement 14
        "CO": _pos_data({"vpip": 30.0}),        # 20 -> 5, improvement 15
    }
    previous = {
        "BB": _pos_data({"fold_3bet": 74.0}),
        "CO": _pos_data({"vpip": 45.0}),
    }
    current_pop = {"BB": _pos_data({"fold_3bet": 55.0}), "CO": _pos_data({"vpip": 25.0})}
    previous_pop = {"BB": _pos_data({"fold_3bet": 55.0}), "CO": _pos_data({"vpip": 25.0})}

    result = find_biggest_improvement(current, previous, current_pop, previous_pop)

    assert result.stat_id == "vpip"
    assert result.position == "CO"
    assert result.improvement == 15.0
