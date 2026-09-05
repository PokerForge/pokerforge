"""ui/settings_dialog.py — must actually persist changes via
config/settings.py, must not restart the app when nothing changed
(cancelling out of a no-op save shouldn't interrupt the user's session),
and must reject an empty username rather than silently saving one."""
import pytest


@pytest.fixture()
def qapp():
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    return app


@pytest.fixture(autouse=True)
def _isolated_settings(tmp_path, monkeypatch):
    import config.settings as settings_mod
    monkeypatch.setattr(settings_mod, "SETTINGS_PATH", tmp_path / "settings.json")


def test_prefills_current_hero_and_currency(qapp):
    from config.settings import set_hero_name, set_currency_symbol
    from ui.settings_dialog import SettingsDialog

    set_hero_name("ExistingHero")
    set_currency_symbol("€")
    dlg = SettingsDialog()
    assert dlg.hero_edit.text() == "ExistingHero"
    assert dlg.currency_cb.currentText() == "€"


def test_saving_a_change_persists_and_triggers_restart(qapp, monkeypatch):
    from config.settings import set_hero_name, set_currency_symbol, get_hero_name, get_currency_symbol
    import ui.settings_dialog as mod

    set_hero_name("OldName")
    set_currency_symbol("£")

    restart_calls = []
    monkeypatch.setattr(mod, "restart_app", lambda: restart_calls.append(True))
    monkeypatch.setattr(mod.QMessageBox, "information", staticmethod(lambda *a, **k: None))

    dlg = mod.SettingsDialog()
    dlg.hero_edit.setText("NewName")
    dlg.currency_cb.setCurrentText("$")
    dlg._on_save()

    assert get_hero_name() == "NewName"
    assert get_currency_symbol() == "$"
    assert restart_calls == [True]


def test_saving_with_no_changes_does_not_restart(qapp, monkeypatch):
    from config.settings import set_hero_name, set_currency_symbol
    import ui.settings_dialog as mod

    set_hero_name("SameName")
    set_currency_symbol("£")

    restart_calls = []
    monkeypatch.setattr(mod, "restart_app", lambda: restart_calls.append(True))

    dlg = mod.SettingsDialog()
    # Don't touch hero_edit/currency_cb — identical to what's already saved.
    dlg._on_save()

    assert restart_calls == []
    assert dlg.result() == 0  # rejected, not accepted — nothing to apply


def test_empty_username_is_rejected(qapp, monkeypatch):
    from config.settings import set_hero_name, get_hero_name
    import ui.settings_dialog as mod

    set_hero_name("OldName")
    warn_calls = []
    monkeypatch.setattr(mod.QMessageBox, "warning", staticmethod(lambda *a, **k: warn_calls.append(True)))
    restart_calls = []
    monkeypatch.setattr(mod, "restart_app", lambda: restart_calls.append(True))

    dlg = mod.SettingsDialog()
    dlg.hero_edit.setText("   ")
    dlg._on_save()

    assert warn_calls == [True]
    assert restart_calls == []
    assert get_hero_name() == "OldName"  # unchanged
