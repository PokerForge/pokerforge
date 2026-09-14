"""ui/overview_tab.py's Tournament-mode page — summary cards + the
cumulative-profit graph, toggled in via refresh(..., session_type=
'tournament') instead of a separate tab (see ui/game_type_toggle.py)."""
from datetime import date, datetime

import pytest

from ui.overview_tab import OverviewTab
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
    return OverviewTab()


def _tournament_hand(hand_id, tournament_id, played_at=None):
    return Hand(
        hand_id=hand_id, source="pokerstars", big_blind=200.0, played_at=played_at or datetime(2026, 6, 1),
        session_type="tournament", tournament_id=tournament_id, buy_in=10.0, fee=1.0,
        players=[Player("Hero", 1, 10000.0), Player("Villain1", 2, 10000.0)],
        actions=[Action("PREFLOP", "Hero", "Post SB", 100.0), Action("PREFLOP", "Villain1", "Post BB", 200.0),
                 Action("PREFLOP", "Hero", "Fold", None)],
    )


def test_switching_to_tournament_mode_shows_the_tournament_page(tab, db):
    tab.refresh(db, "Hero", date(2026, 1, 1), date(2026, 12, 31), "$", session_type="tournament")
    assert not tab._tournament_page.isHidden()
    assert tab._cash_page.isHidden()


def test_cash_mode_shows_the_cash_page(tab, db):
    tab.refresh(db, "Hero", date(2026, 1, 1), date(2026, 12, 31), "$", session_type="cash")
    assert not tab._cash_page.isHidden()
    assert tab._tournament_page.isHidden()


def test_tournament_summary_cards_populate(tab, db):
    db.import_hands([_tournament_hand("h1", "t1")], ev_iterations=1)
    db.set_tournament_result("t1", finish_position=2, field_size=90, payout=45.0, currency="$")

    tab.refresh(db, "Hero", date(2026, 1, 1), date(2026, 12, 31), "$", session_type="tournament")

    assert tab._tournament_summary_labels["Tournaments"].text() == "1"
    assert tab._tournament_summary_labels["Logged"].text() == "1 of 1"
    assert "34.00" in tab._tournament_summary_labels["Profit"].text()  # 45 payout - (10 buy-in + 1 fee)


def test_tournament_graph_plots_cumulative_profit(tab, db):
    db.import_hands([_tournament_hand("h1", "t1")], ev_iterations=1)
    db.set_tournament_result("t1", finish_position=1, field_size=90, payout=50.0, currency="$")

    tab.refresh(db, "Hero", date(2026, 1, 1), date(2026, 12, 31), "$", session_type="tournament")

    xdata, ydata = tab.tournament_curve.getData()
    assert list(xdata) == [1]
    assert list(ydata) == [39.0]  # 50 - (10 buy-in + 1 fee)


def test_no_tournament_hands_on_a_totally_empty_db_shows_no_message(tab, db):
    tab.refresh(db, "Hero", date(2026, 1, 1), date(2026, 12, 31), "$", session_type="tournament")
    assert tab.tournament_empty_state_lbl.isHidden()


def test_cash_only_db_in_tournament_mode_shows_the_zero_filter_message(tab, db):
    cash_hand = Hand(
        hand_id="c1", source="pokerstars", big_blind=0.10, played_at=datetime(2026, 6, 1), session_type="cash",
        players=[Player("Hero", 1, 2.0), Player("Villain1", 2, 2.0)],
        actions=[Action("PREFLOP", "Hero", "Fold", None)],
    )
    db.import_hands([cash_hand], ev_iterations=1)

    tab.refresh(db, "Hero", date(2026, 1, 1), date(2026, 12, 31), "$", session_type="tournament")

    assert not tab.tournament_empty_state_lbl.isHidden()
    assert "filter" in tab.tournament_empty_state_lbl.text().lower()
