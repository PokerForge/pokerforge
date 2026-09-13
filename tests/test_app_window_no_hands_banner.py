"""ui/app_window.py's AppWindow._update_no_hands_banner — a banner shown
above the tabs whenever the database is genuinely empty, instead of every
tab silently rendering as blank charts/dashes with no explanation. Builds
a real AppWindow against a real (empty) on-disk database — run_async is
monkeypatched synchronous so this doesn't race a background QThread."""
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


@pytest.fixture()
def win(qapp, db):
    from ui.app_window import AppWindow
    w = AppWindow("Hero", db, "$")
    yield w
    w.close()


def test_banner_visible_on_construction_with_an_empty_database(win):
    # isVisible() reflects real on-screen visibility, which requires the
    # top-level window itself to be shown (never done in this test) — the
    # widget's own explicit hidden flag via isHidden() is what actually
    # reflects the .hide()/.show()/.setVisible() calls under test.
    assert win.no_hands_banner.isHidden() is False


def test_banner_hides_once_hands_exist(win, monkeypatch):
    monkeypatch.setattr(win.db, "hand_count", lambda: 5)
    win._update_no_hands_banner()
    assert win.no_hands_banner.isHidden() is True


def test_banner_reappears_if_hand_count_drops_back_to_zero(win, monkeypatch):
    monkeypatch.setattr(win.db, "hand_count", lambda: 5)
    win._update_no_hands_banner()
    monkeypatch.setattr(win.db, "hand_count", lambda: 0)
    win._update_no_hands_banner()
    assert win.no_hands_banner.isHidden() is False


def test_manage_folders_button_opens_the_dialog(win, monkeypatch):
    import ui.app_window as mod
    opened = []
    monkeypatch.setattr(mod, "HandHistoryDirsDialog", lambda *a, **k: opened.append(True) or _NullDialog())

    win._on_manage_folders_clicked()

    assert opened == [True]


class _NullDialog:
    def exec(self):
        return False
