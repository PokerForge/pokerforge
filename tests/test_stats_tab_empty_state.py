"""ui/stats_tab.py's empty-state message — distinct from the
totally-empty-database case (handled by AppWindow's top banner): the
account has hands, but the active Period/Stakes/Site filter matches
zero of them, which would otherwise leave the By Position table and
Leaks sub-tab looking silently broken (bare dashes, an empty Leaks
card) with no explanation."""
import pytest


@pytest.fixture()
def qapp():
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def db(tmp_path):
    from database.repository import PokerDatabase
    database = PokerDatabase(tmp_path / "test.db")
    yield database
    database.close()


@pytest.fixture()
def stats_tab(qapp, db):
    from ui.stats_tab import StatsTab
    tab = StatsTab("Hero", db, "£")
    tab._current_d_from = "2026-06-01"
    tab._current_d_to = "2026-06-30"
    tab._current_stake = None
    tab._current_site = None
    return tab


def _import_one_hand(db):
    from models.hand import Hand, Player, Action
    from datetime import datetime
    db.import_hands([Hand(
        hand_id="H1", source="ipoker", played_at=datetime(2020, 1, 1),
        players=[Player("Hero", 1, 2.0), Player("Villain1", 2, 2.0)],
        actions=[Action("PREFLOP", "Hero", "Post SB", 0.01),
                 Action("PREFLOP", "Villain1", "Post BB", 0.02),
                 Action("PREFLOP", "Hero", "Fold", None)],
    )], ev_iterations=1)


def _empty_values():
    from database.repository import _STATS_COLS
    return {c: None for c in _STATS_COLS}


def test_position_table_shows_the_message_when_filter_matches_zero_hands_but_db_has_hands(stats_tab, db):
    _import_one_hand(db)
    from PyQt6.QtWidgets import QLabel
    stats_tab._render_position(_empty_values(), 0, {})
    card = stats_tab.position_lay.itemAt(0).widget()
    all_text = " ".join(l.text() for l in card.findChildren(QLabel))
    assert "filter" in all_text.lower()


def test_position_table_hides_the_message_on_a_totally_empty_db(stats_tab, db):
    from PyQt6.QtWidgets import QLabel
    stats_tab._render_position(_empty_values(), 0, {})
    card = stats_tab.position_lay.itemAt(0).widget()
    all_text = " ".join(l.text() for l in card.findChildren(QLabel))
    assert "filter" not in all_text.lower()


def test_position_table_hides_the_message_when_hands_are_present(stats_tab, db):
    _import_one_hand(db)
    from PyQt6.QtWidgets import QLabel
    stats_tab._render_position(_empty_values(), 5, {})
    card = stats_tab.position_lay.itemAt(0).widget()
    all_text = " ".join(l.text() for l in card.findChildren(QLabel))
    assert "filter" not in all_text.lower()


def test_leaks_tab_shows_the_message_and_skips_leak_cards_when_filter_matches_zero_hands(stats_tab, db):
    _import_one_hand(db)
    from PyQt6.QtWidgets import QLabel
    stats_tab._render_overview(_empty_values(), 0, {}, [])
    all_text = " ".join(l.text() for l in stats_tab.overview_scroll.findChildren(QLabel))
    assert "filter" in all_text.lower()
    assert "YOUR LEAKS" not in all_text


def test_leaks_tab_hides_the_message_on_a_totally_empty_db(stats_tab, db):
    from PyQt6.QtWidgets import QLabel
    stats_tab._render_overview(_empty_values(), 0, {}, [])
    all_text = " ".join(l.text() for l in stats_tab.overview_scroll.findChildren(QLabel))
    assert "filter" not in all_text.lower()


def test_study_tab_shows_the_filter_message_when_filter_matches_zero_hands(stats_tab, db):
    _import_one_hand(db)
    from PyQt6.QtWidgets import QLabel
    stats_tab._render_study(0, [])
    all_text = " ".join(l.text() for l in stats_tab.study_scroll.findChildren(QLabel))
    assert "filter" in all_text.lower()


def test_study_tab_hides_the_filter_message_on_a_totally_empty_db(stats_tab, db):
    from PyQt6.QtWidgets import QLabel
    stats_tab._render_study(0, [])
    all_text = " ".join(l.text() for l in stats_tab.study_scroll.findChildren(QLabel))
    assert "filter" not in all_text.lower()


def test_study_tab_shows_a_message_when_no_leak_qualifies_for_the_queue(stats_tab, db):
    _import_one_hand(db)
    from PyQt6.QtWidgets import QLabel
    stats_tab._render_study(1, [])
    all_text = " ".join(l.text() for l in stats_tab.study_scroll.findChildren(QLabel))
    assert "no leak stands out" in all_text.lower()


def test_overall_tab_shows_the_filter_message_when_filter_matches_zero_hands(stats_tab, db):
    _import_one_hand(db)
    from PyQt6.QtWidgets import QLabel
    stats_tab._render_overall(_empty_values(), 0, {})
    all_text = " ".join(l.text() for l in stats_tab.overall_scroll.findChildren(QLabel))
    assert "filter" in all_text.lower()
    assert "OVERALL" not in all_text


def test_overall_tab_hides_the_filter_message_on_a_totally_empty_db(stats_tab, db):
    from PyQt6.QtWidgets import QLabel
    stats_tab._render_overall(_empty_values(), 0, {})
    all_text = " ".join(l.text() for l in stats_tab.overall_scroll.findChildren(QLabel))
    assert "filter" not in all_text.lower()
