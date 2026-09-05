"""core/licensing.py — currently inert (LICENSE_ENFORCED is False) but
must behave correctly the moment enforcement is flipped on, since that's
the whole point of building this ahead of actually needing it."""
import pytest

import core.licensing as lic
import config.settings as settings_mod


@pytest.fixture(autouse=True)
def _isolated_settings(tmp_path, monkeypatch):
    monkeypatch.setattr(settings_mod, "SETTINGS_PATH", tmp_path / "settings.json")


def test_is_licensed_always_true_while_unenforced(monkeypatch):
    monkeypatch.setattr(lic, "LICENSE_ENFORCED", False)
    settings_mod.set_license_key(None)
    assert lic.is_licensed() is True


def test_generated_key_validates(monkeypatch):
    key = lic.generate_license_key("PF-A1B2C-C3D4E-F5G6H")
    assert lic.validate_license_key(key) is True


def test_tampered_key_fails_validation():
    key = lic.generate_license_key("PF-A1B2C-C3D4E-F5G6H")
    tampered = key[:-1] + ("0" if key[-1] != "0" else "1")
    assert lic.validate_license_key(tampered) is False


def test_made_up_key_without_real_checksum_fails():
    assert lic.validate_license_key("PF-FREE-FOREVER-99") is False


def test_malformed_keys_are_rejected():
    assert lic.validate_license_key("") is False
    assert lic.validate_license_key("not-a-key") is False
    assert lic.validate_license_key(None) is False


def test_validation_is_case_insensitive():
    key = lic.generate_license_key("PF-A1B2C-C3D4E-F5G6H")
    assert lic.validate_license_key(key.lower()) is True


def test_is_licensed_when_enforced_checks_stored_key(monkeypatch):
    monkeypatch.setattr(lic, "LICENSE_ENFORCED", True)
    settings_mod.set_license_key(None)
    assert lic.is_licensed() is False

    key = lic.generate_license_key("PF-A1B2C-C3D4E-F5G6H")
    settings_mod.set_license_key(key)
    assert lic.is_licensed() is True


def test_license_key_setting_roundtrips():
    assert settings_mod.get_license_key() is None
    settings_mod.set_license_key("PF-TEST")
    assert settings_mod.get_license_key() == "PF-TEST"


@pytest.fixture()
def qapp():
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_license_dialog_rejects_invalid_key(qapp):
    from ui.license_dialog import LicenseDialog
    dlg = LicenseDialog()
    dlg._input.setText("not-a-real-key")
    dlg._on_accept()
    assert dlg.entered_key() is None
    assert "valid" in dlg._error_label.text()


def test_license_dialog_accepts_valid_key(qapp):
    from ui.license_dialog import LicenseDialog
    key = lic.generate_license_key("PF-A1B2C-C3D4E-F5G6H")
    dlg = LicenseDialog()
    dlg._input.setText(key)
    dlg._on_accept()
    assert dlg.entered_key() == key
