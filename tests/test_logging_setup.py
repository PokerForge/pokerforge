"""core/logging_setup.py's crash handler — must never itself be the thing
that crashes (there's nowhere left to report that), and must degrade
gracefully when no QApplication exists yet to show a dialog on."""
import sys

import pytest

from core.logging_setup import install_crash_handler


@pytest.fixture(autouse=True)
def _restore_excepthook():
    original = sys.excepthook
    yield
    sys.excepthook = original


def test_handles_exception_before_any_qapplication_exists():
    install_crash_handler()
    try:
        raise ValueError("boom before app exists")
    except ValueError:
        # Must not raise, even though there's no QApplication to show a
        # dialog on yet — this is the exact gap between configure_logging()
        # and QApplication(sys.argv) in main().
        sys.excepthook(*sys.exc_info())


def test_shows_a_dialog_when_a_qapplication_exists(monkeypatch):
    from PyQt6.QtWidgets import QApplication, QMessageBox
    from core.logging_setup import LOG_PATH

    app = QApplication.instance() or QApplication([])  # noqa: F841 — must outlive this test, not be GC'd
    install_crash_handler()
    calls = []
    monkeypatch.setattr(QMessageBox, "critical", staticmethod(lambda *a, **k: calls.append((a, k))))

    try:
        raise RuntimeError("boom with app running")
    except RuntimeError:
        sys.excepthook(*sys.exc_info())

    assert len(calls) == 1
    args = calls[0][0]
    assert str(LOG_PATH) in args[2]
    assert "unexpected problem" in args[2]


def test_keyboard_interrupt_is_not_swallowed():
    install_crash_handler()
    called = {}
    original = sys.__excepthook__
    try:
        sys.__excepthook__ = lambda *a: called.setdefault("hit", True)
        try:
            raise KeyboardInterrupt()
        except KeyboardInterrupt:
            sys.excepthook(*sys.exc_info())
        assert called.get("hit") is True
    finally:
        sys.__excepthook__ = original
