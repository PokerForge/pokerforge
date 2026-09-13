"""core/deviation_backtest.py — splitting Trend-tab buckets into
high/low/normal groups relative to hero's own hand-weighted average,
and reporting each group's weighted bb100."""
from core.deviation_backtest import backtest_stat_deviation


def test_returns_none_with_fewer_than_two_eligible_buckets():
    assert backtest_stat_deviation(["b1"], [25.0], [50], [2.0]) is None
    assert backtest_stat_deviation([], [], [], []) is None


def test_buckets_below_min_hands_are_excluded_from_eligibility():
    bucket_starts = ["b1", "b2", "b3"]
    stat_values = [25.0, 40.0, 25.0]
    hand_counts = [50, 5, 50]  # b2 has too few hands to count
    bb100_values = [2.0, 100.0, 2.0]

    result = backtest_stat_deviation(bucket_starts, stat_values, hand_counts, bb100_values)
    # only b1 and b3 are eligible, both at 25.0 -> baseline 25.0, no deviation
    assert result["high"] is None
    assert result["low"] is None
    assert result["normal"]["hands"] == 100


def test_a_high_deviation_bucket_is_correctly_split_out():
    bucket_starts = ["b1", "b2", "b3"]
    stat_values = [20.0, 20.0, 40.0]  # b3 is way above the ~20 baseline
    hand_counts = [100, 100, 50]
    bb100_values = [5.0, 5.0, -20.0]

    result = backtest_stat_deviation(bucket_starts, stat_values, hand_counts, bb100_values)
    assert result["baseline_stat"] == 24.0  # (20*100 + 20*100 + 40*50) / 250
    assert result["high"] == {"hands": 50, "bb100": -20.0}
    assert result["low"] is None
    assert result["normal"] == {"hands": 200, "bb100": 5.0}


def test_a_low_deviation_bucket_is_correctly_split_out():
    bucket_starts = ["b1", "b2", "b3"]
    stat_values = [20.0, 20.0, 5.0]  # b3 is way below the ~20 baseline
    hand_counts = [100, 100, 50]
    bb100_values = [3.0, 3.0, 30.0]

    result = backtest_stat_deviation(bucket_starts, stat_values, hand_counts, bb100_values)
    assert result["low"] == {"hands": 50, "bb100": 30.0}
    assert result["high"] is None
    assert result["normal"] == {"hands": 200, "bb100": 3.0}


def test_buckets_with_no_bb100_are_excluded_from_the_weighted_average_but_still_counted():
    bucket_starts = ["b1", "b2", "b3"]
    stat_values = [20.0, 20.0, 40.0]
    hand_counts = [100, 100, 50]
    bb100_values = [5.0, 5.0, None]  # the high bucket has no bb100 data

    result = backtest_stat_deviation(bucket_starts, stat_values, hand_counts, bb100_values)
    assert result["high"] == {"hands": 50, "bb100": None}


def test_a_deviation_exactly_at_the_threshold_counts_as_a_deviation():
    bucket_starts = ["b1", "b2"]
    stat_values = [20.0, 25.0]  # baseline (100*20+100*25)/200 = 22.5; b2 diff = +2.5 < 5
    hand_counts = [100, 100]
    bb100_values = [5.0, 5.0]
    result = backtest_stat_deviation(bucket_starts, stat_values, hand_counts, bb100_values,
                                       deviation_points=2.5)
    # exactly +2.5 above baseline and exactly -2.5 below -> both count (inclusive <=/>=)
    assert result["high"]["hands"] == 100
    assert result["low"]["hands"] == 100
    assert result["normal"] is None


def test_stat_values_of_none_are_excluded_from_eligibility():
    bucket_starts = ["b1", "b2", "b3"]
    stat_values = [25.0, None, 25.0]
    hand_counts = [50, 50, 50]
    bb100_values = [2.0, 2.0, 2.0]

    result = backtest_stat_deviation(bucket_starts, stat_values, hand_counts, bb100_values)
    assert result["normal"]["hands"] == 100  # only b1 and b3
