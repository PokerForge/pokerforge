"""ui/tilt_report_dialog.py — TiltReportDialog wires hero_vpip_sequence_query
+ compute_post_loss_vpip_shift together and renders the result. run_async is
monkeypatched to execute synchronously, same as test_pool_insights_dialog.py,
so these tests don't race a background thread."""
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


def _result(baseline_rate=25.0, baseline_sample=100, post_loss_rate=25.0, post_loss_sample=100):
    return {
        "baseline_rate": baseline_rate, "baseline_sample": baseline_sample,
        "post_loss_rate": post_loss_rate, "post_loss_sample": post_loss_sample,
        "big_loss_bb": 30.0, "window_minutes": 30,
    }


def test_shows_a_message_when_sample_is_too_small(qapp, db, monkeypatch):
    import ui.tilt_report_dialog as mod
    from datetime import date
    monkeypatch.setattr(mod, "hero_vpip_sequence_query", lambda *a, **k: [])
    monkeypatch.setattr(mod, "compute_post_loss_vpip_shift",
                         lambda rows: _result(post_loss_sample=2, baseline_sample=2))

    dlg = mod.TiltReportDialog(db, "Hero", date(2026, 6, 1), date(2026, 6, 30))
    from PyQt6.QtWidgets import QLabel
    all_text = " ".join(l.text() for l in dlg.findChildren(QLabel))
    assert "Not enough hands" in all_text


def test_shows_a_looser_shift_when_post_loss_vpip_is_meaningfully_higher(qapp, db, monkeypatch):
    import ui.tilt_report_dialog as mod
    from datetime import date
    monkeypatch.setattr(mod, "hero_vpip_sequence_query", lambda *a, **k: ["row"])
    monkeypatch.setattr(mod, "compute_post_loss_vpip_shift",
                         lambda rows: _result(baseline_rate=22.0, post_loss_rate=40.0))

    dlg = mod.TiltReportDialog(db, "Hero", date(2026, 6, 1), date(2026, 6, 30))
    from PyQt6.QtWidgets import QLabel
    all_text = " ".join(l.text() for l in dlg.findChildren(QLabel))
    assert "22.0%" in all_text
    assert "40.0%" in all_text
    assert "play +18.0 points looser" in all_text


def test_shows_a_tighter_shift_when_post_loss_vpip_is_meaningfully_lower(qapp, db, monkeypatch):
    import ui.tilt_report_dialog as mod
    from datetime import date
    monkeypatch.setattr(mod, "hero_vpip_sequence_query", lambda *a, **k: ["row"])
    monkeypatch.setattr(mod, "compute_post_loss_vpip_shift",
                         lambda rows: _result(baseline_rate=22.0, post_loss_rate=10.0))

    dlg = mod.TiltReportDialog(db, "Hero", date(2026, 6, 1), date(2026, 6, 30))
    from PyQt6.QtWidgets import QLabel
    all_text = " ".join(l.text() for l in dlg.findChildren(QLabel))
    assert "play -12.0 points tighter" in all_text


def test_shows_no_shift_message_when_difference_is_small(qapp, db, monkeypatch):
    import ui.tilt_report_dialog as mod
    from datetime import date
    monkeypatch.setattr(mod, "hero_vpip_sequence_query", lambda *a, **k: ["row"])
    monkeypatch.setattr(mod, "compute_post_loss_vpip_shift",
                         lambda rows: _result(baseline_rate=22.0, post_loss_rate=23.0))

    dlg = mod.TiltReportDialog(db, "Hero", date(2026, 6, 1), date(2026, 6, 30))
    from PyQt6.QtWidgets import QLabel
    all_text = " ".join(l.text() for l in dlg.findChildren(QLabel))
    assert "holds steady" in all_text


def test_error_from_the_query_shows_an_error_message_not_a_crash(qapp, db, monkeypatch):
    import ui.tilt_report_dialog as mod
    from datetime import date

    def _boom(*a, **k):
        raise RuntimeError("disk on fire")

    monkeypatch.setattr(mod, "hero_vpip_sequence_query", _boom)

    dlg = mod.TiltReportDialog(db, "Hero", date(2026, 6, 1), date(2026, 6, 30))
    assert "Couldn't build this report" in dlg._status.text()


def test_sessions_tab_button_opens_the_dialog(qapp, db, monkeypatch):
    import ui.sessions_tab as tab_mod
    from datetime import date

    opened = {}

    class _FakeDialog:
        def __init__(self, db, hero, d_from, d_to, stake, site=None, parent=None):
            opened["args"] = (db, hero, d_from, d_to, stake, site)

        def exec(self):
            opened["executed"] = True

    monkeypatch.setattr(tab_mod, "TiltReportDialog", _FakeDialog)

    tab = tab_mod.SessionsTab()
    tab._db, tab._hero = db, "Hero"
    tab._d_from, tab._d_to, tab._stake = date(2026, 6, 1), date(2026, 6, 30), "NL10"
    tab._on_tilt_report_clicked()

    assert opened["executed"] is True
    assert opened["args"] == (db, "Hero", date(2026, 6, 1), date(2026, 6, 30), "NL10", None)
