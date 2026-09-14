"""core/licensing.py — currently inert (LICENSE_ENFORCED is False) but
must behave correctly the moment enforcement is flipped on, since that's
the whole point of building this ahead of actually needing it."""
import json
import urllib.error
from datetime import date, timedelta

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


def test_is_licensed_when_enforced_checks_stored_key_and_cached_expiry(monkeypatch):
    monkeypatch.setattr(lic, "LICENSE_ENFORCED", True)
    settings_mod.set_license_key(None)
    assert lic.is_licensed() is False

    key = lic.generate_license_key("PF-A1B2C-C3D4E-F5G6H")
    lic.activate_key(key)
    assert lic.is_licensed() is True


def test_is_licensed_false_for_a_valid_key_with_no_cached_expiry(monkeypatch):
    """A well-formed key alone isn't enough -- is_licensed() also needs a
    cached expiry (from activate_key or a real server check), otherwise a
    key that was never actually entered through the app (just poked into
    settings.json directly) would pass forever."""
    monkeypatch.setattr(lic, "LICENSE_ENFORCED", True)
    key = lic.generate_license_key("PF-A1B2C-C3D4E-F5G6H")
    settings_mod.set_license_key(key)
    settings_mod.set_license_expires_at(None)

    assert lic.is_licensed() is False


def test_is_licensed_true_within_the_grace_period_past_a_stale_expiry(monkeypatch):
    monkeypatch.setattr(lic, "LICENSE_ENFORCED", True)
    key = lic.generate_license_key("PF-A1B2C-C3D4E-F5G6H")
    settings_mod.set_license_key(key)
    stale = date.today() - timedelta(days=lic.LICENSE_STATUS_GRACE_DAYS)
    settings_mod.set_license_expires_at(stale.isoformat())

    assert lic.is_licensed() is True


def test_is_licensed_false_once_the_grace_period_has_elapsed(monkeypatch):
    monkeypatch.setattr(lic, "LICENSE_ENFORCED", True)
    key = lic.generate_license_key("PF-A1B2C-C3D4E-F5G6H")
    settings_mod.set_license_key(key)
    expired = date.today() - timedelta(days=lic.LICENSE_STATUS_GRACE_DAYS + 1)
    settings_mod.set_license_expires_at(expired.isoformat())

    assert lic.is_licensed() is False


def test_should_gate_by_stakes_is_false_while_unenforced(monkeypatch):
    monkeypatch.setattr(lic, "LICENSE_ENFORCED", False)
    settings_mod.set_license_key(None)
    assert lic.should_gate_by_stakes() is False


def test_should_gate_by_stakes_when_enforced_and_unlicensed(monkeypatch):
    monkeypatch.setattr(lic, "LICENSE_ENFORCED", True)
    settings_mod.set_license_key(None)
    assert lic.should_gate_by_stakes() is True

    key = lic.generate_license_key("PF-A1B2C-C3D4E-F5G6H")
    lic.activate_key(key)
    assert lic.should_gate_by_stakes() is False


def test_license_key_setting_roundtrips():
    assert settings_mod.get_license_key() is None
    settings_mod.set_license_key("PF-TEST")
    assert settings_mod.get_license_key() == "PF-TEST"


def test_license_expiry_and_last_checked_settings_roundtrip():
    assert settings_mod.get_license_expires_at() is None
    assert settings_mod.get_license_last_checked_at() is None

    settings_mod.set_license_expires_at("2027-01-15")
    settings_mod.set_license_last_checked_at("2027-01-01")

    assert settings_mod.get_license_expires_at() == "2027-01-15"
    assert settings_mod.get_license_last_checked_at() == "2027-01-01"


def test_activate_key_persists_the_key_and_a_provisional_expiry():
    key = lic.generate_license_key("PF-A1B2C-C3D4E-F5G6H")
    lic.activate_key(key)

    assert settings_mod.get_license_key() == key
    assert settings_mod.get_license_expires_at() == date.today().isoformat()


def test_refresh_license_status_is_a_noop_while_unenforced(monkeypatch):
    monkeypatch.setattr(lic, "LICENSE_ENFORCED", False)
    monkeypatch.setattr(lic, "LICENSE_SERVER_URL", "https://license.example.com")
    lic.activate_key(lic.generate_license_key("PF-A1B2C-C3D4E-F5G6H"))

    assert lic.refresh_license_status() is False


def test_refresh_license_status_is_a_noop_without_a_configured_server_url(monkeypatch):
    monkeypatch.setattr(lic, "LICENSE_ENFORCED", True)
    monkeypatch.setattr(lic, "LICENSE_SERVER_URL", None)
    lic.activate_key(lic.generate_license_key("PF-A1B2C-C3D4E-F5G6H"))

    assert lic.refresh_license_status() is False


def test_refresh_license_status_is_a_noop_without_a_key_entered(monkeypatch):
    monkeypatch.setattr(lic, "LICENSE_ENFORCED", True)
    monkeypatch.setattr(lic, "LICENSE_SERVER_URL", "https://license.example.com")
    settings_mod.set_license_key(None)

    assert lic.refresh_license_status() is False


class _FakeHttpResponse:
    def __init__(self, payload: dict):
        self._body = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_refresh_license_status_updates_cached_expiry_on_success(monkeypatch):
    monkeypatch.setattr(lic, "LICENSE_ENFORCED", True)
    monkeypatch.setattr(lic, "LICENSE_SERVER_URL", "https://license.example.com")
    key = lic.generate_license_key("PF-A1B2C-C3D4E-F5G6H")
    lic.activate_key(key)

    monkeypatch.setattr(lic.urllib.request, "urlopen",
                         lambda url, timeout=5.0: _FakeHttpResponse({"valid": True, "expires_at": "2027-06-01"}))

    assert lic.refresh_license_status() is True
    assert settings_mod.get_license_expires_at() == "2027-06-01"
    assert settings_mod.get_license_last_checked_at() == date.today().isoformat()


def test_refresh_license_status_clears_expiry_when_server_says_invalid(monkeypatch):
    """An explicit "no" (never issued, or canceled) clears the cached
    expiry outright rather than leaving the old value to ride out a grace
    period it hasn't earned."""
    monkeypatch.setattr(lic, "LICENSE_ENFORCED", True)
    monkeypatch.setattr(lic, "LICENSE_SERVER_URL", "https://license.example.com")
    key = lic.generate_license_key("PF-A1B2C-C3D4E-F5G6H")
    lic.activate_key(key)

    monkeypatch.setattr(lic.urllib.request, "urlopen",
                         lambda url, timeout=5.0: _FakeHttpResponse({"valid": False, "expires_at": None}))

    assert lic.refresh_license_status() is True
    assert settings_mod.get_license_expires_at() is None
    assert lic.is_licensed() is False


def test_refresh_license_status_returns_false_on_network_error(monkeypatch):
    monkeypatch.setattr(lic, "LICENSE_ENFORCED", True)
    monkeypatch.setattr(lic, "LICENSE_SERVER_URL", "https://license.example.com")
    key = lic.generate_license_key("PF-A1B2C-C3D4E-F5G6H")
    lic.activate_key(key)

    def _raise(url, timeout=5.0):
        raise urllib.error.URLError("no route to host")

    monkeypatch.setattr(lic.urllib.request, "urlopen", _raise)

    assert lic.refresh_license_status() is False
    # The provisional expiry from activate_key survives an unreachable
    # server -- this is exactly the grace period's job.
    assert settings_mod.get_license_expires_at() == date.today().isoformat()


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


@pytest.fixture()
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


def test_entering_a_license_key_via_the_menu_action_persists_it(qapp, tmp_path, monkeypatch, _synchronous_run_async):
    """ui/app_window.py's File > Enter License Key... menu action --
    confirms the wiring itself (dialog -> settings persistence), not
    LicenseDialog's own validation (already covered above)."""
    from database.repository import PokerDatabase
    from ui.app_window import AppWindow
    import ui.app_window as app_window_mod

    db = PokerDatabase(tmp_path / "test.db")
    win = AppWindow("Hero", db, "$")

    key = lic.generate_license_key("PF-A1B2C-C3D4E-F5G6H")
    monkeypatch.setattr(app_window_mod, "LicenseDialog", lambda current_key=None, parent=None: _FakeAcceptedDialog(key))

    win._on_enter_license_key_clicked()

    assert settings_mod.get_license_key() == key
    assert settings_mod.get_license_expires_at() == date.today().isoformat()
    db.close()


class _FakeAcceptedDialog:
    def __init__(self, key):
        self._key = key

    def exec(self):
        return True

    def entered_key(self):
        return self._key


def test_generate_license_key_script_produces_valid_unique_keys():
    """scripts/generate_license_key.py -- the manual-issuance stopgap until
    the Stripe webhook backend ever ships (server/README.md)."""
    from scripts.generate_license_key import new_key

    keys = [new_key() for _ in range(20)]

    assert all(lic.validate_license_key(k) for k in keys)
    assert len(set(keys)) == len(keys)
