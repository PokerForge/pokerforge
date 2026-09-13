"""ui/stats_tab.py's cross-dimensional "Leaks by Position" card — built
directly on a real StatsTab instance (constructing one is cheap; the
async refresh() pipeline is what's expensive, and isn't needed to test
these two methods in isolation)."""
import pytest

from core.leak_finder import LeakEntry


@pytest.fixture()
def qapp():
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def stats_tab(qapp, tmp_path):
    from database.repository import PokerDatabase
    from ui.stats_tab import StatsTab
    db = PokerDatabase(tmp_path / "test.db")
    tab = StatsTab("Hero", db, "£")
    tab._current_d_from = "2026-06-01"
    tab._current_d_to = "2026-06-30"
    tab._current_stake = None
    yield tab
    db.close()


def _leak(position="BB", stat_id="fold_3bet", stat_label="Fold to 3-Bet",
          hero_rate=74.0, population_rate=55.0, sample=120):
    return LeakEntry(position=position, stat_id=stat_id, stat_label=stat_label,
                      hero_rate=hero_rate, population_rate=population_rate,
                      sample=sample, score=abs(hero_rate - population_rate) * sample)


def test_card_shows_a_callout_for_the_biggest_leak_and_rows_for_the_rest(stats_tab):
    from PyQt6.QtWidgets import QLabel
    leaks = [_leak(stat_label="Biggest"), _leak(stat_label="Second"), _leak(stat_label="Third")]
    card = stats_tab._build_cross_leaks_card(leaks)
    all_text = " ".join(l.text() for l in card.findChildren(QLabel))
    assert "Biggest" in all_text
    assert "Second" in all_text
    assert "Third" in all_text


def test_callout_shows_higher_or_lower_direction_correctly(stats_tab):
    from PyQt6.QtWidgets import QLabel
    higher = _leak(hero_rate=74.0, population_rate=55.0)  # hero > population
    card = stats_tab._build_cross_leaks_card([higher])
    all_text = " ".join(l.text() for l in card.findChildren(QLabel))
    assert "higher" in all_text

    lower = _leak(hero_rate=4.0, population_rate=8.7)  # hero < population
    card2 = stats_tab._build_cross_leaks_card([lower])
    all_text2 = " ".join(l.text() for l in card2.findChildren(QLabel))
    assert "lower" in all_text2


def test_clicking_a_cross_leak_queries_hands_for_that_stat_and_position(stats_tab, monkeypatch):
    import ui.stats_tab as mod
    calls = []
    monkeypatch.setattr(mod, "hands_for_stat_query",
                         lambda db, hero, stat_id, d_from, d_to, stake, position=None:
                             calls.append((stat_id, position)) or [])
    monkeypatch.setattr(mod, "HandListDialog", lambda *a, **k: _NullDialog())

    leak = _leak(stat_id="fold_3bet", position="BB")
    stats_tab._on_cross_leak_clicked(leak)

    assert calls == [("fold_3bet", "BB")]


def test_rows_below_the_callout_also_state_their_own_deviation(stats_tab):
    from PyQt6.QtWidgets import QLabel
    higher = _leak(stat_label="Second", hero_rate=74.0, population_rate=55.0)  # +19.0, higher
    lower = _leak(stat_label="Third", hero_rate=4.0, population_rate=8.7)  # -4.7, lower
    card = stats_tab._build_cross_leaks_card([_leak(stat_label="Biggest"), higher, lower])
    all_text = " ".join(l.text() for l in card.findChildren(QLabel))
    assert "19.0 points higher" in all_text
    assert "4.7 points lower" in all_text
    assert "You 74.0%" in all_text and "Population 55.0%" in all_text


def test_only_shows_up_to_five_leaks_total(stats_tab):
    from PyQt6.QtWidgets import QLabel
    leaks = [_leak(stat_label=f"Leak{i}") for i in range(10)]
    card = stats_tab._build_cross_leaks_card(leaks)
    all_text = " ".join(l.text() for l in card.findChildren(QLabel))
    for i in range(5):
        assert f"Leak{i}" in all_text
    for i in range(5, 10):
        assert f"Leak{i}" not in all_text


class _NullDialog:
    def exec(self):
        pass
