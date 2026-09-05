"""ui/diagnostics_dialog.py's "Copy Diagnostic Info" button — must put a
plain-text block covering version, OS, database size, and both file paths
onto the clipboard, since that's the whole point of the button (letting a
user paste a support-ready diagnostic into a bug report without typing any
of it by hand themselves)."""
import pytest

from config.version import APP_VERSION
from core.currency import FX_RATES_AS_OF


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


def test_copy_diagnostic_info_puts_key_facts_on_clipboard(qapp, db):
    from ui.diagnostics_dialog import DiagnosticsDialog
    dlg = DiagnosticsDialog(db)
    dlg._copy_diagnostic_info()

    copied = qapp.clipboard().text()
    assert APP_VERSION in copied
    assert "Hands in database: 0" in copied
    assert "Log file:" in copied
    assert "Database file:" in copied
    assert FX_RATES_AS_OF in copied


def test_view_log_button_disabled_when_no_log_file_exists(qapp, db, monkeypatch, tmp_path):
    import ui.diagnostics_dialog as mod
    monkeypatch.setattr(mod, "LOG_PATH", tmp_path / "no_such_log.log")
    dlg = mod.DiagnosticsDialog(db)
    view_log_buttons = [
        w for w in dlg.findChildren(mod.QPushButton) if w.text() == "View Log File"
    ]
    assert len(view_log_buttons) == 1
    assert view_log_buttons[0].isEnabled() is False
