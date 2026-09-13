"""core/tilt_correlation.py — the sliding-window "was this hand shortly
after a big loss" logic. Pure function over (played_at, profit,
big_blind, vpip, vpip_pfr_opp) tuples, so no database needed."""
from core.tilt_correlation import compute_post_loss_vpip_shift


def _row(minute, profit, big_blind=1.0, vpip=0, opp=1, day=1):
    hour, minute = divmod(minute, 60)
    return (f"2026-06-{day:02d}T{hour:02d}:{minute:02d}:00", profit, big_blind, vpip, opp)


def test_hand_within_window_after_a_big_loss_counts_as_post_loss():
    rows = [
        _row(0, profit=-35.0),   # a 35bb loss -> a trigger
        _row(10, profit=0.0, vpip=1),  # 10 minutes later, within the 30-min window
    ]
    result = compute_post_loss_vpip_shift(rows)
    assert result["post_loss_sample"] == 1
    assert result["post_loss_rate"] == 100.0


def test_hand_outside_the_window_does_not_count():
    rows = [
        _row(0, profit=-35.0),
        _row(45, profit=0.0, vpip=1),  # 45 minutes later, outside a 30-min window
    ]
    result = compute_post_loss_vpip_shift(rows)
    assert result["post_loss_sample"] == 0
    assert result["post_loss_rate"] is None


def test_a_loss_below_the_threshold_is_not_a_trigger():
    rows = [
        _row(0, profit=-10.0),  # only a 10bb loss, below the 30bb threshold
        _row(5, profit=0.0, vpip=1),
    ]
    result = compute_post_loss_vpip_shift(rows)
    assert result["post_loss_sample"] == 0


def test_baseline_includes_every_eligible_hand_trigger_or_not():
    rows = [
        _row(0, profit=-35.0),        # trigger, opp=1 by default via _row
        _row(10, profit=0.0, vpip=1),  # post-loss
        _row(60, profit=5.0, vpip=0),  # not post-loss, still counts toward baseline
    ]
    result = compute_post_loss_vpip_shift(rows)
    assert result["baseline_sample"] == 3
    assert result["post_loss_sample"] == 1


def test_rows_missing_played_at_or_big_blind_are_skipped():
    rows = [
        (None, -35.0, 1.0, 1, 1),
        ("2026-06-01T00:00:00", -35.0, None, 1, 1),
        ("2026-06-01T00:05:00", 0.0, 1.0, 1, 1),
    ]
    result = compute_post_loss_vpip_shift(rows)
    assert result["baseline_sample"] == 1  # only the third, fully-populated row
    assert result["post_loss_sample"] == 0  # its would-be trigger was skipped for missing big_blind


def test_hands_with_zero_opportunity_are_excluded_from_both_rates():
    rows = [
        _row(0, profit=-35.0, opp=0),  # still a valid trigger even with opp=0
        _row(5, profit=0.0, vpip=1, opp=0),  # no vpip opportunity -> excluded from both counts
    ]
    result = compute_post_loss_vpip_shift(rows)
    assert result["baseline_sample"] == 0
    assert result["post_loss_sample"] == 0


def test_no_hands_at_all_returns_none_rates_not_a_crash():
    result = compute_post_loss_vpip_shift([])
    assert result["baseline_rate"] is None
    assert result["post_loss_rate"] is None


def test_a_hand_can_be_both_post_loss_and_a_new_trigger():
    rows = [
        _row(0, profit=-35.0),               # trigger #1
        _row(5, profit=-35.0, vpip=1),        # post-loss (of #1) AND a new trigger #2
        _row(15, profit=0.0, vpip=1),         # within 30 min of trigger #2 (at minute 5)
    ]
    result = compute_post_loss_vpip_shift(rows)
    # Hand at minute 5 counts post-loss (after trigger #1); hand at minute
    # 15 counts post-loss too (after the closer trigger #2 at minute 5).
    assert result["post_loss_sample"] == 2


def test_unsorted_input_is_sorted_before_analysis():
    rows = [
        _row(10, profit=0.0, vpip=1),  # appears first in the list, but is chronologically AFTER the loss
        _row(0, profit=-35.0),
    ]
    result = compute_post_loss_vpip_shift(rows)
    assert result["post_loss_sample"] == 1


def test_custom_thresholds_are_respected():
    rows = [
        _row(0, profit=-15.0),        # a 15bb loss -> not a trigger at the default 30bb threshold...
        _row(5, profit=0.0, vpip=1),
    ]
    default_result = compute_post_loss_vpip_shift(rows)
    assert default_result["post_loss_sample"] == 0

    lenient_result = compute_post_loss_vpip_shift(rows, big_loss_bb=10.0)
    assert lenient_result["post_loss_sample"] == 1
