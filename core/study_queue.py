"""Turns the already-ranked cross-dimensional leak list (core.leak_finder)
into a short, prioritized study plan — reusing diversify_leaks with a
tighter one-per-stat cap, so a 3-item plan covers 3 genuinely different
problems (e.g. VPIP, fold-to-3-bet, fold-to-cbet) rather than the same
stat at three different positions, which the "Leaks by Position" card
can already show on its own."""
from datetime import date, timedelta

from core.leak_finder import diversify_leaks

MAX_PRIORITIES = 3
HANDS_PER_STUDY_SESSION = 20
# How long a "Mark Studied" click keeps showing as done before a
# priority (if the underlying leak is still real) starts nagging again —
# long enough not to feel repetitive, short enough that a genuinely
# unaddressed leak doesn't stay silently checked off forever.
STUDIED_RECENTLY_DAYS = 7


def build_study_queue(cross_leaks, max_priorities: int = MAX_PRIORITIES):
    """`cross_leaks`: find_leaks's score-sorted list. Returns up to
    `max_priorities` LeakEntry objects, at most one per stat_id, in
    score order — the same entries the Leaks by Position card already
    renders, just capped tighter for a short "what to study today" list."""
    return diversify_leaks(cross_leaks, max_per_stat=1)[:max_priorities]


def compute_streak_days(completion_dates, today: date | None = None) -> int:
    """Consecutive calendar days (ending today, or ending yesterday if
    nothing's been marked studied yet today — a streak isn't broken
    until a full day passes with no completion logged, not the instant
    the clock ticks past midnight) with at least one "Mark Studied"
    click on ANY priority. `completion_dates`: whatever
    database.repository.PokerDatabase.get_study_completion_dates()
    returns — real `date`s, not datetimes, since a streak counts days
    worked, not individual clicks."""
    today = today or date.today()
    dates = set(completion_dates)
    if today in dates:
        cur = today
    elif (today - timedelta(days=1)) in dates:
        cur = today - timedelta(days=1)
    else:
        return 0
    streak = 0
    while cur in dates:
        streak += 1
        cur -= timedelta(days=1)
    return streak
