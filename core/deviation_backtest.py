"""Backtests hero's OWN historical deviations from their own average in
one stat, using the same interval buckets the Trend tab already plots
(database.queries.pct_trend_query), and reports what actually happened —
in bb100 — during the buckets where hero was playing meaningfully looser,
tighter, or more/less aggressively than their own norm.

This is a correlation, not a causal claim: a period where a stat moved
and results moved with it doesn't prove the stat change caused the
result — plenty of other things (opponent pool, variance, stakes) also
differ between two periods of history. It's a replay of hero's own
numbers laid side by side, disclosed as exactly that."""

DEVIATION_POINTS = 5.0
MIN_BUCKET_HANDS = 30


def _weighted_bb100(indices, hand_counts, bb100_values):
    hands = sum(hand_counts[i] for i in indices)
    weighted = [(bb100_values[i], hand_counts[i]) for i in indices if bb100_values[i] is not None]
    weighted_hands = sum(h for _, h in weighted)
    bb100 = round(sum(v * h for v, h in weighted) / weighted_hands, 2) if weighted_hands else None
    return {"hands": hands, "bb100": bb100}


def backtest_stat_deviation(bucket_starts, stat_values, hand_counts, bb100_values,
                              deviation_points: float = DEVIATION_POINTS,
                              min_bucket_hands: int = MIN_BUCKET_HANDS) -> dict | None:
    """`bucket_starts`/`stat_values`/`hand_counts`/`bb100_values` are
    parallel lists, one entry per Trend-tab check-in bucket — the exact
    shapes pct_trend_query's (bucket_starts, series[stat_id], hand_counts)
    and series['bb100'] return.

    A bucket is "eligible" if it has at least `min_bucket_hands` hands and
    a real stat value. Eligible buckets are split into high (stat at least
    `deviation_points` above hero's own hand-weighted average across all
    eligible buckets), low (at least that far below), and normal (the
    rest) — then each group's bb100 is reported hand-weighted.

    Returns None if fewer than 2 eligible buckets exist — nothing to
    compare a period against."""
    eligible = [i for i in range(len(bucket_starts))
                if hand_counts[i] >= min_bucket_hands and stat_values[i] is not None]
    if len(eligible) < 2:
        return None

    total_hands = sum(hand_counts[i] for i in eligible)
    baseline_stat = sum(stat_values[i] * hand_counts[i] for i in eligible) / total_hands

    high, low, normal = [], [], []
    for i in eligible:
        diff = stat_values[i] - baseline_stat
        if diff >= deviation_points:
            high.append(i)
        elif diff <= -deviation_points:
            low.append(i)
        else:
            normal.append(i)

    return {
        "baseline_stat": round(baseline_stat, 1),
        "high": _weighted_bb100(high, hand_counts, bb100_values) if high else None,
        "low": _weighted_bb100(low, hand_counts, bb100_values) if low else None,
        "normal": _weighted_bb100(normal, hand_counts, bb100_values) if normal else None,
        "deviation_points": deviation_points,
        "min_bucket_hands": min_bucket_hands,
    }
