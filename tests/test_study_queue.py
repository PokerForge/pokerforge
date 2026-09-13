"""core/study_queue.py — thin wrapper over diversify_leaks with a
tighter one-per-stat cap for a short "what to study today" list."""
from core.leak_finder import LeakEntry
from core.study_queue import build_study_queue, MAX_PRIORITIES


def _entry(stat_id, position, score):
    return LeakEntry(position=position, stat_id=stat_id, stat_label=stat_id,
                      hero_rate=0.0, population_rate=0.0, sample=100, score=score)


def test_returns_at_most_one_entry_per_stat():
    leaks = [_entry("vpip", "SB", 100), _entry("vpip", "BB", 90), _entry("three_bet", "CO", 80)]
    queue = build_study_queue(leaks)
    assert [e.stat_id for e in queue] == ["vpip", "three_bet"]


def test_caps_at_max_priorities():
    leaks = [_entry(f"stat{i}", "BB", 100 - i) for i in range(10)]
    queue = build_study_queue(leaks)
    assert len(queue) == MAX_PRIORITIES


def test_preserves_input_order():
    # build_study_queue assumes cross_leaks arrives already score-sorted,
    # same as diversify_leaks — it doesn't re-sort on its own.
    leaks = [_entry("b", "BB", 90), _entry("c", "BB", 70), _entry("a", "BB", 50)]
    queue = build_study_queue(leaks)
    assert [e.stat_id for e in queue] == ["b", "c", "a"]


def test_empty_leaks_returns_empty_queue():
    assert build_study_queue([]) == []


def test_custom_max_priorities_is_respected():
    leaks = [_entry(f"stat{i}", "BB", 100 - i) for i in range(5)]
    queue = build_study_queue(leaks, max_priorities=2)
    assert len(queue) == 2
