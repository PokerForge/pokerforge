"""ui/pool_insights_dialog.py — PoolInsightsDialog wires
showdown_hand_ids_query + load_hands_bulk + classify_river_sizing_vs_strength
together and renders the result. run_async is monkeypatched to execute
synchronously (call fn() then the callback immediately, no real QThread)
so these tests don't race a background thread — the async plumbing
itself is already covered by tests exercising ui/async_worker.py
elsewhere in this suite."""
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


def test_shows_a_message_when_no_qualifying_hands_exist(qapp, db, monkeypatch):
    import ui.pool_insights_dialog as mod
    from datetime import date
    monkeypatch.setattr(mod, "showdown_hand_ids_query", lambda *a, **k: [])

    dlg = mod.PoolInsightsDialog(db, "Hero", date(2026, 6, 1), date(2026, 6, 30))
    from PyQt6.QtWidgets import QLabel
    all_text = " ".join(l.text() for l in dlg.findChildren(QLabel))
    assert "Not enough showdown hands" in all_text


def test_shows_a_row_per_nonempty_bucket_with_strong_percentage(qapp, db, monkeypatch):
    import ui.pool_insights_dialog as mod
    from datetime import date
    monkeypatch.setattr(mod, "showdown_hand_ids_query", lambda *a, **k: ["h1"])
    monkeypatch.setattr(mod, "load_hands_bulk", lambda db, ids: {"h1": object()})
    monkeypatch.setattr(mod, "classify_river_sizing_vs_strength", lambda hands, exclude_player=None: {
        "33-50% pot": {"strong": 0, "weak": 0},
        "50-100% pot": {"strong": 3, "weak": 1},
        "100%+ pot (overbet)": {"strong": 0, "weak": 0},
    })

    dlg = mod.PoolInsightsDialog(db, "Hero", date(2026, 6, 1), date(2026, 6, 30))
    from PyQt6.QtWidgets import QLabel
    all_text = " ".join(l.text() for l in dlg.findChildren(QLabel))
    assert "50-100% pot" in all_text
    assert "75.0%" in all_text  # 3 of 4
    assert "33-50% pot" not in all_text  # empty bucket, not shown
    assert "4" in all_text  # total hand count drawn from


def test_error_from_the_query_shows_an_error_message_not_a_crash(qapp, db, monkeypatch):
    import ui.pool_insights_dialog as mod
    from datetime import date

    def _boom(*a, **k):
        raise RuntimeError("disk on fire")

    monkeypatch.setattr(mod, "showdown_hand_ids_query", _boom)

    dlg = mod.PoolInsightsDialog(db, "Hero", date(2026, 6, 1), date(2026, 6, 30))
    assert "Couldn't build this report" in dlg._status.text()
