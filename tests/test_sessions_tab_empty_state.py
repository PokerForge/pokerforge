"""ui/sessions_tab.py's empty-state message — distinct from the
totally-empty-database case (handled by AppWindow's top banner): the
account has hands, but the active Period/Stakes/Site filter matches no
sessions, which would otherwise look like a silently broken, bare
table."""
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
def tab(qapp):
    from ui.sessions_tab import SessionsTab
    return SessionsTab()


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


def test_zero_sessions_with_an_otherwise_populated_db_shows_the_message(tab, db):
    _import_one_hand(db)
    tab._db = db

    tab._render_cash([])

    assert not tab.empty_state_lbl.isHidden()
    assert "filter" in tab.empty_state_lbl.text().lower()


def test_zero_sessions_with_a_totally_empty_db_keeps_the_message_hidden(tab, db):
    tab._db = db

    tab._render_cash([])

    assert tab.empty_state_lbl.isHidden()


def test_nonempty_sessions_keeps_the_message_hidden(tab, db):
    _import_one_hand(db)
    tab._db = db

    tab._render_cash([("2020-01-01", "£0.01/£0.02", 1, 0.5, 1.0, 0.0, 0.1)])

    assert tab.empty_state_lbl.isHidden()
