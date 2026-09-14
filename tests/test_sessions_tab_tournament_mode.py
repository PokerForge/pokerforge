"""ui/sessions_tab.py's Tournament-mode table — the results table + Log
Result flow, toggled in via refresh(..., session_type='tournament')
instead of a separate tab (see ui/game_type_toggle.py). Ported from the
now-removed standalone Tournaments tab."""
from datetime import date, datetime

import pytest

from ui.sessions_tab import SessionsTab
from models.hand import Hand, Player, Action


@pytest.fixture()
def qapp():
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _synchronous_run_async(monkeypatch):
    import ui.async_worker as worker_mod

    def _sync_run_async(self, fn, on_done, on_error=None, key="default"):
        try:
            result = fn()
        except Exception as exc:
            if on_error:
                on_error(str(exc))
            return
        on_done(result)

    monkeypatch.setattr(worker_mod.AsyncRunner, "run_async", _sync_run_async)


@pytest.fixture()
def db(tmp_path):
    from database.repository import PokerDatabase
    database = PokerDatabase(tmp_path / "test.db")
    yield database
    database.close()


@pytest.fixture()
def tab(qapp):
    return SessionsTab()


def _tournament_hand(hand_id, tournament_id, played_at=None):
    return Hand(
        hand_id=hand_id, source="pokerstars", big_blind=200.0, played_at=played_at or datetime(2026, 6, 1),
        session_type="tournament", tournament_id=tournament_id, buy_in=10.0, fee=1.0,
        players=[Player("Hero", 1, 10000.0), Player("Villain1", 2, 10000.0)],
        actions=[Action("PREFLOP", "Hero", "Post SB", 100.0), Action("PREFLOP", "Villain1", "Post BB", 200.0),
                 Action("PREFLOP", "Hero", "Fold", None)],
    )


def test_tournament_mode_reconfigures_the_table_columns(tab, db):
    from ui.sessions_tab import TOURNAMENT_COLUMNS
    db.import_hands([_tournament_hand("h1", "t1")], ev_iterations=1)

    tab.refresh(db, "Hero", date(2026, 1, 1), date(2026, 12, 31), "$", session_type="tournament")

    assert tab.table.columnCount() == len(TOURNAMENT_COLUMNS)
    headers = [tab.table.horizontalHeaderItem(c).text() for c in range(tab.table.columnCount())]
    assert headers == TOURNAMENT_COLUMNS
    assert tab.table.rowCount() == 1
    assert tab.table.item(0, 2).text() == "t1"  # Tournament column


def test_tilt_report_button_hidden_in_tournament_mode(tab, db):
    tab.refresh(db, "Hero", date(2026, 1, 1), date(2026, 12, 31), "$", session_type="tournament")
    assert tab.tilt_btn.isHidden()


def test_tilt_report_button_visible_in_cash_mode(tab, db):
    tab.refresh(db, "Hero", date(2026, 1, 1), date(2026, 12, 31), "$", session_type="cash")
    assert not tab.tilt_btn.isHidden()


def test_no_tournament_hands_on_a_totally_empty_db_shows_no_message(tab, db):
    tab.refresh(db, "Hero", date(2026, 1, 1), date(2026, 12, 31), "$", session_type="tournament")
    assert tab.empty_state_lbl.isHidden()


def test_double_click_opens_the_log_result_dialog_and_saves(tab, db, monkeypatch):
    db.import_hands([_tournament_hand("h1", "t1")], ev_iterations=1)
    tab.refresh(db, "Hero", date(2026, 1, 1), date(2026, 12, 31), "$", session_type="tournament")
    row = tab._rows[0]

    class _FakeDialog:
        def __init__(self, *a, **k):
            pass

        def exec(self):
            return True

        def result_values(self):
            return (5, 100, 20.0)

    monkeypatch.setattr("ui.sessions_tab.LogTournamentResultDialog", _FakeDialog)

    tab._on_log_result_clicked(row)

    assert db.get_tournament_results()["t1"] == (5, 100, 20.0, "$")


def test_cancelling_the_dialog_does_not_save(tab, db, monkeypatch):
    db.import_hands([_tournament_hand("h1", "t1")], ev_iterations=1)
    tab.refresh(db, "Hero", date(2026, 1, 1), date(2026, 12, 31), "$", session_type="tournament")
    row = tab._rows[0]

    class _FakeDialog:
        def __init__(self, *a, **k):
            pass

        def exec(self):
            return False

    monkeypatch.setattr("ui.sessions_tab.LogTournamentResultDialog", _FakeDialog)

    tab._on_log_result_clicked(row)

    assert db.get_tournament_results() == {}


def test_double_click_in_tournament_mode_routes_to_log_result_not_hand_list(tab, db, monkeypatch):
    db.import_hands([_tournament_hand("h1", "t1")], ev_iterations=1)
    tab.refresh(db, "Hero", date(2026, 1, 1), date(2026, 12, 31), "$", session_type="tournament")

    called = []
    monkeypatch.setattr(tab, "_on_log_result_clicked", lambda row: called.append(row))

    class _FakeIndex:
        def row(self):
            return 0

    tab._on_double_click(_FakeIndex())

    assert len(called) == 1
    assert called[0]['tournament_id'] == 't1'
