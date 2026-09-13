"""Correlates hero's own VPIP against what just happened in the session —
specifically, whether a hand falls shortly after a big loss — rather than
treating every hand's timestamp purely as a filter axis. Every hand
already carries a real played_at and profit; this doesn't add any new
data, just a different question asked of what's already there."""
import bisect
from datetime import datetime, timedelta

BIG_LOSS_BB = 30.0
WINDOW_MINUTES = 30


def compute_post_loss_vpip_shift(hand_rows, big_loss_bb: float = BIG_LOSS_BB,
                                   window_minutes: float = WINDOW_MINUTES) -> dict:
    """`hand_rows`: (played_at, profit, big_blind, vpip, vpip_pfr_opp)
    tuples for one player — the exact shape
    database.queries.hero_vpip_sequence_query returns. A hand counts as
    "post-loss" if it falls within `window_minutes` after the most
    recent earlier hand where profit/big_blind <= -big_loss_bb (a loss
    of at least that many big blinds). Rows with no big_blind or no
    played_at are skipped entirely — there's nothing to time-order or
    scale a loss threshold against without both.

    Returns baseline_rate/sample (every eligible hand) and
    post_loss_rate/sample (only the post-loss subset) — None for a rate
    with zero sample, never a division by zero."""
    parsed = []
    for played_at, profit, big_blind, vpip, opp in hand_rows:
        if not played_at or not big_blind:
            continue
        parsed.append((datetime.fromisoformat(played_at), profit, big_blind, vpip, opp))
    parsed.sort(key=lambda r: r[0])

    total_made = sum(1 for r in parsed if r[4] and r[3])
    total_opp = sum(1 for r in parsed if r[4])
    baseline_rate = round(100.0 * total_made / total_opp, 1) if total_opp else None

    trigger_times = sorted(dt for dt, profit, bb, vpip, opp in parsed if (profit / bb) <= -big_loss_bb)
    window = timedelta(minutes=window_minutes)

    post_loss_made = post_loss_opp = 0
    for dt, profit, bb, vpip, opp in parsed:
        if not opp:
            continue
        idx = bisect.bisect_left(trigger_times, dt) - 1  # latest trigger strictly before this hand
        if idx >= 0 and dt - trigger_times[idx] <= window:
            post_loss_opp += 1
            if vpip:
                post_loss_made += 1
    post_loss_rate = round(100.0 * post_loss_made / post_loss_opp, 1) if post_loss_opp else None

    return {
        "baseline_rate": baseline_rate, "baseline_sample": total_opp,
        "post_loss_rate": post_loss_rate, "post_loss_sample": post_loss_opp,
        "big_loss_bb": big_loss_bb, "window_minutes": window_minutes,
    }
