"""ui/deviation_backtest_dialog.py — DeviationBacktestDialog wires
pct_trend_query + backtest_stat_deviation together and renders one card
per stat with a meaningful deviation. run_async is monkeypatched to run
synchronously, same pattern as the other on-demand report dialogs."""
import pytest


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


def test_shows_a_message_when_nothing_deviates_meaningfully(qapp, db, monkeypatch):
    import ui.deviation_backtest_dialog as mod
    from datetime import date
    monkeypatch.setattr(mod, "pct_trend_query", lambda *a, **k: (
        ["b1", "b2"], {"vpip": [22.0, 23.0], "bb100": [3.0, 4.0]}, [100, 100]))

    dlg = mod.DeviationBacktestDialog(db, "Hero", date(2026, 6, 1), date(2026, 6, 30),
                                        ["vpip"], 14)
    from PyQt6.QtWidgets import QLabel
    all_text = " ".join(l.text() for l in dlg.findChildren(QLabel))
    assert "No stat in your current Trend selection" in all_text


def test_shows_a_card_for_a_stat_with_a_real_deviation(qapp, db, monkeypatch):
    import ui.deviation_backtest_dialog as mod
    from datetime import date
    monkeypatch.setattr(mod, "pct_trend_query", lambda *a, **k: (
        ["b1", "b2", "b3"],
        {"vpip": [20.0, 20.0, 40.0], "bb100": [5.0, 5.0, -20.0]},
        [100, 100, 50],
    ))

    dlg = mod.DeviationBacktestDialog(db, "Hero", date(2026, 6, 1), date(2026, 6, 30),
                                        ["vpip"], 14)
    from PyQt6.QtWidgets import QLabel
    all_text = " ".join(l.text() for l in dlg.findChildren(QLabel))
    assert "VPIP" in all_text
    assert "-20.0" in all_text
    assert "+5.0" in all_text


def test_only_bb100_is_requested_once_even_if_already_in_stat_ids(qapp, db, monkeypatch):
    import ui.deviation_backtest_dialog as mod
    from datetime import date

    seen = {}

    def _fake_query(db, hero, d_from, d_to, stat_ids, stake, interval_days):
        seen["stat_ids"] = stat_ids
        return ([], {}, [])

    monkeypatch.setattr(mod, "pct_trend_query", _fake_query)
    mod.DeviationBacktestDialog(db, "Hero", date(2026, 6, 1), date(2026, 6, 30),
                                  ["bb100", "vpip"], 14)
    assert seen["stat_ids"].count("bb100") == 1


def test_error_from_the_query_shows_an_error_message_not_a_crash(qapp, db, monkeypatch):
    import ui.deviation_backtest_dialog as mod
    from datetime import date

    def _boom(*a, **k):
        raise RuntimeError("disk on fire")

    monkeypatch.setattr(mod, "pct_trend_query", _boom)

    dlg = mod.DeviationBacktestDialog(db, "Hero", date(2026, 6, 1), date(2026, 6, 30),
                                        ["vpip"], 14)
    assert "Couldn't build this report" in dlg._status.text()


def test_trend_tab_button_opens_the_dialog(qapp, db, monkeypatch):
    import ui.stats_tab as tab_mod
    from datetime import date

    opened = {}

    class _FakeDialog:
        def __init__(self, db, hero, d_from, d_to, stat_ids, interval_days, stake, parent=None):
            opened["args"] = (db, hero, d_from, d_to, stat_ids, interval_days, stake)

        def exec(self):
            opened["executed"] = True

    monkeypatch.setattr(tab_mod, "DeviationBacktestDialog", _FakeDialog)

    tab = tab_mod.StatsTab("Hero", db)
    tab._current_d_from, tab._current_d_to, tab._current_stake = date(2026, 6, 1), date(2026, 6, 30), "NL10"
    tab._trend_stat_ids, tab._trend_interval_days = ["vpip", "pfr"], 14
    tab._on_backtest_deviations_clicked()

    assert opened["executed"] is True
    assert opened["args"] == (db, "Hero", date(2026, 6, 1), date(2026, 6, 30), ["vpip", "pfr"], 14, "NL10")
