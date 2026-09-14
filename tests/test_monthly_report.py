"""core/monthly_report.py's build_monthly_report — pure aggregation over
pre-computed query results (no database needed; database/test_queries.py
and tests/test_leak_finder.py cover the pieces this assembles)."""
from core.monthly_report import build_monthly_report


def _pos_data(rate_by_stat, sample=50):
    values = dict(rate_by_stat)
    opp_counts = {stat: sample for stat in rate_by_stat}
    return values, sample, opp_counts


def test_headline_stats_carry_current_and_previous_values():
    current = {"hands": 500, "profit": 120.0, "bb100": 5.0, "vpip": 24.0}
    previous = {"hands": 400, "profit": -30.0, "bb100": -1.0, "vpip": 30.0}

    report = build_monthly_report(2026, 9, current, previous, {}, {}, {}, {})

    by_key = {h.key: h for h in report.headline}
    assert by_key["hands"].value == 500
    assert by_key["hands"].previous_value == 400
    assert by_key["hands"].delta == 100
    assert by_key["vpip"].delta == -6.0


def test_headline_delta_is_none_without_previous_month_data():
    report = build_monthly_report(2026, 9, {"hands": 500}, None, {}, None, {}, None)
    hands_stat = next(h for h in report.headline if h.key == "hands")
    assert hands_stat.previous_value is None
    assert hands_stat.delta is None
    assert report.has_previous_month_data is False


def test_finds_the_biggest_leak_for_the_current_month():
    current_by_position = {"BB": _pos_data({"fold_3bet": 74.0})}
    current_pop = {"BB": _pos_data({"fold_3bet": 55.0})}

    report = build_monthly_report(
        2026, 9, {"hands": 300}, None, current_by_position, None, current_pop, None)

    assert report.biggest_leak is not None
    assert report.biggest_leak.position == "BB"
    assert report.biggest_leak.stat_id == "fold_3bet"


def test_no_leak_when_nothing_qualifies():
    report = build_monthly_report(2026, 9, {"hands": 300}, None, {}, None, {}, None)
    assert report.biggest_leak is None


def test_finds_the_biggest_improvement_when_previous_month_data_exists():
    current_by_position = {"BB": _pos_data({"fold_3bet": 60.0})}
    previous_by_position = {"BB": _pos_data({"fold_3bet": 74.0})}
    current_pop = {"BB": _pos_data({"fold_3bet": 55.0})}
    previous_pop = {"BB": _pos_data({"fold_3bet": 55.0})}

    report = build_monthly_report(
        2026, 9, {"hands": 300}, {"hands": 280},
        current_by_position, previous_by_position, current_pop, previous_pop)

    assert report.biggest_improvement is not None
    assert report.biggest_improvement.stat_id == "fold_3bet"
    assert report.has_previous_month_data is True


def test_no_improvement_computed_when_previous_month_has_no_hands():
    """previous_overview['hands'] == 0 (or missing) means the player
    simply didn't play that month — nothing to meaningfully compare
    against, even if empty position dicts were technically passed."""
    current_by_position = {"BB": _pos_data({"fold_3bet": 60.0})}

    report = build_monthly_report(
        2026, 9, {"hands": 300}, {"hands": 0},
        current_by_position, {}, {"BB": _pos_data({"fold_3bet": 55.0})}, {})

    assert report.biggest_improvement is None
    assert report.has_previous_month_data is False


def test_year_and_month_are_carried_through():
    report = build_monthly_report(2026, 3, {"hands": 1}, None, {}, None, {}, None)
    assert report.year == 2026
    assert report.month == 3
