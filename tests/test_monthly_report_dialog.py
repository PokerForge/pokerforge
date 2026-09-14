"""ui/monthly_report_dialog.py — month navigation and the Overview tab
button that opens it. The report content itself is covered by
tests/test_monthly_report.py (pure logic) and tests/test_leak_finder.py;
this just covers the Qt wiring around it."""
import pytest
from datetime import date


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
def dlg(qapp, db):
    from ui.monthly_report_dialog import MonthlyReportDialog
    d = MonthlyReportDialog(db, "Hero", "$", year=2026, month=6)
    yield d
    d.close()


def test_shows_the_requested_month_and_year(dlg):
    assert dlg._month_lbl.text() == "June 2026"


def test_no_hands_shows_the_empty_state(dlg):
    assert "No hands played in June 2026" in dlg._status.text() or any(
        "No hands played" in dlg._body.itemAt(i).widget().text()
        for i in range(dlg._body.count()) if dlg._body.itemAt(i).widget()
    )


def test_prev_month_navigates_back_a_month(dlg):
    dlg._on_prev_month()
    assert (dlg.year, dlg.month) == (2026, 5)
    assert dlg._month_lbl.text() == "May 2026"


def test_prev_month_crosses_a_year_boundary(dlg):
    dlg.year, dlg.month = 2026, 1
    dlg._on_prev_month()
    assert (dlg.year, dlg.month) == (2025, 12)


def test_next_month_button_disabled_at_the_current_calendar_month(qapp, db):
    from ui.monthly_report_dialog import MonthlyReportDialog
    today = date.today()
    d = MonthlyReportDialog(db, "Hero", "$", year=today.year, month=today.month)
    assert d._next_btn.isEnabled() is False
    d.close()


def test_next_month_button_enabled_for_a_past_month(dlg):
    assert dlg._next_btn.isEnabled() is True


def test_clicking_next_past_the_current_month_is_a_no_op(qapp, db):
    from ui.monthly_report_dialog import MonthlyReportDialog
    today = date.today()
    d = MonthlyReportDialog(db, "Hero", "$", year=today.year, month=today.month)
    d._on_next_month()
    assert (d.year, d.month) == (today.year, today.month)
    d.close()


def test_overview_tab_button_opens_the_dialog(qapp, db, monkeypatch):
    from ui.overview_tab import OverviewTab
    tab = OverviewTab()
    tab._db, tab._hero, tab._currency, tab._site = db, "Hero", "$", None

    opened = {}

    class _FakeDialog:
        def __init__(self, db, hero, currency, site=None, parent=None):
            opened["args"] = (db, hero, currency, site)

        def exec(self):
            opened["executed"] = True

    monkeypatch.setattr("ui.overview_tab.MonthlyReportDialog", _FakeDialog)
    tab._on_monthly_report_clicked()

    assert opened["executed"] is True
    assert opened["args"] == (db, "Hero", "$", None)
