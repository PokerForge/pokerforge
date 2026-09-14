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


def test_auto_refresh_defaults_to_enabled(qapp):
    from ui.settings_dialog import SettingsDialog
    dlg = SettingsDialog()
    assert dlg.auto_refresh_cb.isChecked() is True


def test_toggling_auto_refresh_alone_saves_without_restarting(qapp, monkeypatch):
    """A pure auto-refresh toggle, with hero/currency untouched, must not
    trigger the app-restart flow that only hero/currency changes need."""
    from config.settings import get_live_auto_refresh_enabled, set_hero_name, set_currency_symbol
    import ui.settings_dialog as mod

    set_hero_name("ExistingHero")
    set_currency_symbol("£")

    restart_calls = []
    monkeypatch.setattr(mod, "restart_app", lambda: restart_calls.append(True))

    dlg = mod.SettingsDialog()
    dlg.auto_refresh_cb.setChecked(False)
    dlg._on_save()

    assert get_live_auto_refresh_enabled() is False
    assert restart_calls == []
    assert dlg.result() == 1  # accepted — the change was actually saved


def test_prefills_existing_aliases(qapp):
    from config.settings import set_hero_name, set_hero_aliases
    from ui.settings_dialog import SettingsDialog

    set_hero_name("Akali8010")
    set_hero_aliases(["Doire11", "Hero"])
    dlg = SettingsDialog()

    items = [dlg.alias_list.item(i).text() for i in range(dlg.alias_list.count())]
    assert items == ["Doire11", "Hero"]


def test_adding_an_alias_and_saving_persists_it(qapp, monkeypatch):
    from config.settings import set_hero_name, set_hero_aliases, get_hero_aliases
    import ui.settings_dialog as mod

    set_hero_name("Akali8010")
    set_hero_aliases([])
    restart_calls = []
    monkeypatch.setattr(mod, "restart_app", lambda: restart_calls.append(True))

    dlg = mod.SettingsDialog()
    dlg.alias_edit.setText("AlwaysSpeedin")
    dlg._on_add_alias()
    dlg._on_save()

    assert get_hero_aliases() == ["AlwaysSpeedin"]
    assert restart_calls == []  # alias-only change never needs a restart
    assert dlg.result() == 1  # accepted — the change was actually saved


def test_pressing_enter_in_the_alias_field_also_adds_it(qapp):
    from config.settings import set_hero_name, set_hero_aliases
    import ui.settings_dialog as mod

    set_hero_name("Akali8010")
    set_hero_aliases([])
    dlg = mod.SettingsDialog()
    dlg.alias_edit.setText("AlwaysSpeedin")
    dlg.alias_edit.returnPressed.emit()

    assert dlg._aliases == ["AlwaysSpeedin"]
    assert dlg.alias_edit.text() == ""  # cleared for the next one


def test_removing_a_selected_alias_and_saving_persists_it(qapp, monkeypatch):
    from config.settings import set_hero_name, set_hero_aliases, get_hero_aliases
    import ui.settings_dialog as mod

    set_hero_name("Akali8010")
    set_hero_aliases(["Doire11", "Hero"])
    monkeypatch.setattr(mod, "restart_app", lambda: None)

    dlg = mod.SettingsDialog()
    dlg.alias_list.setCurrentItem(dlg.alias_list.item(dlg._aliases.index("Hero")))
    dlg._on_remove_alias()
    dlg._on_save()

    assert get_hero_aliases() == ["Doire11"]


def test_adding_the_current_username_itself_is_rejected(qapp, monkeypatch):
    from config.settings import set_hero_name, set_hero_aliases
    import ui.settings_dialog as mod

    set_hero_name("Akali8010")
    set_hero_aliases([])
    warn_calls = []
    monkeypatch.setattr(mod.QMessageBox, "warning", staticmethod(lambda *a, **k: warn_calls.append(True)))

    dlg = mod.SettingsDialog()
    dlg.alias_edit.setText("Akali8010")
    dlg._on_add_alias()

    assert warn_calls == [True]
    assert dlg._aliases == []


def test_adding_a_duplicate_alias_is_a_silent_no_op(qapp):
    from config.settings import set_hero_name, set_hero_aliases
    import ui.settings_dialog as mod

    set_hero_name("Akali8010")
    set_hero_aliases(["Doire11"])
    dlg = mod.SettingsDialog()
    dlg.alias_edit.setText("Doire11")
    dlg._on_add_alias()

    assert dlg._aliases == ["Doire11"]


def test_only_touching_aliases_does_not_trigger_a_restart(qapp, monkeypatch):
    from config.settings import set_hero_name, set_currency_symbol, set_hero_aliases
    import ui.settings_dialog as mod

    set_hero_name("Akali8010")
    set_currency_symbol("£")
    set_hero_aliases([])
    restart_calls = []
    monkeypatch.setattr(mod, "restart_app", lambda: restart_calls.append(True))

    dlg = mod.SettingsDialog()
    dlg.alias_edit.setText("Hero")
    dlg._on_add_alias()
    dlg._on_save()

    assert restart_calls == []


def test_auto_refresh_toggle_persists_alongside_a_restart_triggering_change(qapp, monkeypatch):
    from config.settings import get_live_auto_refresh_enabled, set_hero_name, set_currency_symbol
    import ui.settings_dialog as mod

    set_hero_name("OldName")
    set_currency_symbol("£")
    monkeypatch.setattr(mod, "restart_app", lambda: None)
    monkeypatch.setattr(mod.QMessageBox, "information", staticmethod(lambda *a, **k: None))

    dlg = mod.SettingsDialog()
    dlg.hero_edit.setText("NewName")
    dlg.auto_refresh_cb.setChecked(False)
    dlg._on_save()

    assert get_live_auto_refresh_enabled() is False
