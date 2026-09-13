"""core/leak_finder.py — the ranking logic behind the cross-dimensional
leak finder. Pure function over pre-computed position-breakdown dicts
(the exact shape database.queries.position_breakdown_query /
population_by_position_query already return), so no database needed
here — database/test_queries.py covers those two queries themselves."""
from core.leak_finder import find_leaks, MIN_SAMPLE


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
