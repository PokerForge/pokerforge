"""Turns the already-ranked cross-dimensional leak list (core.leak_finder)
into a short, prioritized study plan — reusing diversify_leaks with a
tighter one-per-stat cap, so a 3-item plan covers 3 genuinely different
problems (e.g. VPIP, fold-to-3-bet, fold-to-cbet) rather than the same
stat at three different positions, which the "Leaks by Position" card
can already show on its own."""
from core.leak_finder import diversify_leaks

MAX_PRIORITIES = 3
HANDS_PER_STUDY_SESSION = 20


def build_study_queue(cross_leaks, max_priorities: int = MAX_PRIORITIES):
    """`cross_leaks`: find_leaks's score-sorted list. Returns up to
    `max_priorities` LeakEntry objects, at most one per stat_id, in
    score order — the same entries the Leaks by Position card already
    renders, just capped tighter for a short "what to study today" list."""
    return diversify_leaks(cross_leaks, max_per_stat=1)[:max_priorities]
