"""core/licensing.py — currently inert (LICENSE_ENFORCED is False) but
must behave correctly the moment enforcement is flipped on, since that's
the whole point of building it ahead of needing it.

Licences are Ed25519-signed tokens. These tests sign with a throwaway
keypair generated per-test rather than the real one, so they prove the
verification logic without depending on (or embedding) the production
signing key."""
import base64
import json
import urllib.error
from datetime import date, timedelta

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import core.licensing as lic
import config.settings as settings_mod


@pytest.fixture(autouse=True)
def _isolated_settings(tmp_path, monkeypatch):
    monkeypatch.setattr(settings_mod, "SETTINGS_PATH", tmp_path / "settings.json")


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


@pytest.fixture()
def sign(monkeypatch):
    """Returns a function that mints licences the app will accept, by
    pointing LICENSE_PUBLIC_KEY at a keypair created just for this test."""
    private = Ed25519PrivateKey.generate()
    public_raw = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw)
    monkeypatch.setattr(lic, "LICENSE_PUBLIC_KEY", base64.b64encode(public_raw).decode())

    def _sign(expires="2099-01-01", subscription="sub_test"):
        payload = {"e": expires, "s": subscription}
        segment = _b64url(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
        return f"PF1.{segment}.{_b64url(private.sign(segment.encode('ascii')))}"

    return _sign


# --- verification -----------------------------------------------------

def test_a_signed_licence_verifies(sign):
    token = sign()
    assert lic.validate_license_key(token) is True
    assert lic.verify_license_key(token) == {"e": "2099-01-01", "s": "sub_test"}


def test_a_tampered_payload_is_rejected(sign):
    """Editing the expiry to buy more time must invalidate the signature —
    this is the property the whole scheme rests on."""
    prefix, payload, signature = sign(expires="2026-01-01").split(".")
    forged_payload = _b64url(json.dumps({"e": "2099-01-01", "s": "sub_test"},
                                         separators=(",", ":"), sort_keys=True).encode())
    assert lic.validate_license_key(f"{prefix}.{forged_payload}.{signature}") is False


def test_a_licence_signed_by_the_wrong_key_is_rejected(sign):
    sign()                                    # installs this test's public key
    other = Ed25519PrivateKey.generate()      # ...but sign with a different one
    payload = _b64url(json.dumps({"e": "2099-01-01", "s": "x"},
                                  separators=(",", ":"), sort_keys=True).encode())
    token = f"PF1.{payload}.{_b64url(other.sign(payload.encode('ascii')))}"
    assert lic.validate_license_key(token) is False


def test_malformed_and_made_up_licences_are_rejected(sign):
    sign()
    for junk in ["", "not-a-key", "PF1.abc.def", "PF1.only-two-parts",
                 "PF-A1B2C-C3D4E-F5G6H-7A", None]:
        assert lic.validate_license_key(junk) is False


def test_expiry_is_read_from_the_signed_payload(sign):
    assert lic.license_expiry(sign(expires="2027-03-04")) == date(2027, 3, 4)
    assert lic.license_expiry("rubbish") is None


# --- activation -------------------------------------------------------

def test_activating_a_licence_stores_it_with_its_signed_expiry(sign):
    token = sign(expires="2027-06-30")
    assert lic.activate_key(token) is True
    assert settings_mod.get_license_key() == token
    assert settings_mod.get_license_expires_at() == "2027-06-30"


def test_activating_a_forged_licence_stores_nothing(sign):
    sign()
    assert lic.activate_key("PF1.forged.nonsense") is False
    assert settings_mod.get_license_key() is None
    assert settings_mod.get_license_expires_at() is None


# --- the licensing decision -------------------------------------------

def test_is_licensed_always_true_while_unenforced(monkeypatch):
    monkeypatch.setattr(lic, "LICENSE_ENFORCED", False)
    settings_mod.set_license_key(None)
    assert lic.is_licensed() is True


def test_is_licensed_false_with_no_licence(monkeypatch):
    monkeypatch.setattr(lic, "LICENSE_ENFORCED", True)
    settings_mod.set_license_key(None)
    assert lic.is_licensed() is False


def test_is_licensed_true_for_a_current_licence(monkeypatch, sign):
    monkeypatch.setattr(lic, "LICENSE_ENFORCED", True)
    lic.activate_key(sign(expires=(date.today() + timedelta(days=20)).isoformat()))
    assert lic.is_licensed() is True


def test_is_licensed_true_within_the_grace_period(monkeypatch, sign):
    """Covers a renewal the app hasn't fetched yet — safe to be generous
    because the expiry is signed and can't be extended by the user."""
    monkeypatch.setattr(lic, "LICENSE_ENFORCED", True)
    lapsed = date.today() - timedelta(days=lic.LICENSE_GRACE_DAYS)
    lic.activate_key(sign(expires=lapsed.isoformat()))
    assert lic.is_licensed() is True


def test_is_licensed_false_once_grace_has_elapsed(monkeypatch, sign):
    monkeypatch.setattr(lic, "LICENSE_ENFORCED", True)
    lapsed = date.today() - timedelta(days=lic.LICENSE_GRACE_DAYS + 1)
    lic.activate_key(sign(expires=lapsed.isoformat()))
    assert lic.is_licensed() is False


def test_a_forged_licence_poked_straight_into_settings_is_refused(monkeypatch, sign):
    """The scheme's real job: editing settings.json by hand gets you
    nothing, because entitlement comes from the signature, not the file."""
    monkeypatch.setattr(lic, "LICENSE_ENFORCED", True)
    sign()
    settings_mod.set_license_key("PF1.made.up")
    settings_mod.set_license_expires_at("2099-01-01")
    assert lic.is_licensed() is False


def test_should_gate_by_stakes_is_the_inverse_of_is_licensed(monkeypatch, sign):
    monkeypatch.setattr(lic, "LICENSE_ENFORCED", False)
    assert lic.should_gate_by_stakes() is False

    monkeypatch.setattr(lic, "LICENSE_ENFORCED", True)
    settings_mod.set_license_key(None)
    assert lic.should_gate_by_stakes() is True

    lic.activate_key(sign(expires=(date.today() + timedelta(days=5)).isoformat()))
    assert lic.should_gate_by_stakes() is False


# --- refreshing against the server ------------------------------------

class _FakeResponse:
    def __init__(self, payload: dict):
        self._body = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_refresh_is_network_free_unless_enforced_configured_and_licensed(monkeypatch, sign):
    def _explode(*a, **kw):
        raise AssertionError("refresh must not touch the network here")
    monkeypatch.setattr(lic.urllib.request, "urlopen", _explode)

    monkeypatch.setattr(lic, "LICENSE_ENFORCED", False)
    monkeypatch.setattr(lic, "LICENSE_SERVER_URL", "https://example.com")
    lic.activate_key(sign())
    assert lic.refresh_license_status() is False

    monkeypatch.setattr(lic, "LICENSE_ENFORCED", True)
    monkeypatch.setattr(lic, "LICENSE_SERVER_URL", None)
    assert lic.refresh_license_status() is False

    monkeypatch.setattr(lic, "LICENSE_SERVER_URL", "https://example.com")
    settings_mod.set_license_key(None)
    assert lic.refresh_license_status() is False


def test_refresh_stores_the_extended_licence(monkeypatch, sign):
    monkeypatch.setattr(lic, "LICENSE_ENFORCED", True)
    monkeypatch.setattr(lic, "LICENSE_SERVER_URL", "https://example.com")
    lic.activate_key(sign(expires="2026-01-01"))

    renewed = sign(expires="2026-02-01")
    monkeypatch.setattr(lic.urllib.request, "urlopen",
                         lambda url, timeout=5.0: _FakeResponse({"valid": True, "token": renewed}))

    assert lic.refresh_license_status() is True
    assert settings_mod.get_license_key() == renewed
    assert settings_mod.get_license_expires_at() == "2026-02-01"
    assert settings_mod.get_license_last_checked_at() == date.today().isoformat()


def test_refresh_drops_the_licence_when_the_server_declines(monkeypatch, sign):
    """A cancelled subscription: the server stops extending, so access
    ends now rather than riding out a grace period it hasn't earned."""
    monkeypatch.setattr(lic, "LICENSE_ENFORCED", True)
    monkeypatch.setattr(lic, "LICENSE_SERVER_URL", "https://example.com")
    lic.activate_key(sign(expires=(date.today() + timedelta(days=5)).isoformat()))

    monkeypatch.setattr(lic.urllib.request, "urlopen",
                         lambda url, timeout=5.0: _FakeResponse({"valid": False}))

    assert lic.refresh_license_status() is True
    assert settings_mod.get_license_expires_at() is None


def test_refresh_keeps_working_offline(monkeypatch, sign):
    monkeypatch.setattr(lic, "LICENSE_ENFORCED", True)
    monkeypatch.setattr(lic, "LICENSE_SERVER_URL", "https://example.com")
    token = sign(expires=(date.today() + timedelta(days=5)).isoformat())
    lic.activate_key(token)

    def _unreachable(url, timeout=5.0):
        raise urllib.error.URLError("no route to host")
    monkeypatch.setattr(lic.urllib.request, "urlopen", _unreachable)

    assert lic.refresh_license_status() is False
    # The signed licence still stands on its own.
    assert settings_mod.get_license_key() == token
    assert lic.is_licensed() is True


# --- settings ---------------------------------------------------------

def test_licence_settings_roundtrip():
    assert settings_mod.get_license_key() is None
    settings_mod.set_license_key("PF1.x.y")
    settings_mod.set_license_expires_at("2027-01-15")
    settings_mod.set_license_last_checked_at("2027-01-01")
    assert settings_mod.get_license_key() == "PF1.x.y"
    assert settings_mod.get_license_expires_at() == "2027-01-15"
    assert settings_mod.get_license_last_checked_at() == "2027-01-01"


# --- UI wiring --------------------------------------------------------

@pytest.fixture()
def qapp():
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_license_dialog_rejects_an_invalid_licence(qapp, sign):
    from ui.license_dialog import LicenseDialog
    sign()
    dlg = LicenseDialog()
    dlg._input.setText("not-a-real-key")
    dlg._on_accept()
    assert dlg.entered_key() is None
    assert "valid" in dlg._error_label.text()


def test_license_dialog_accepts_a_signed_licence(qapp, sign):
    from ui.license_dialog import LicenseDialog
    token = sign()
    dlg = LicenseDialog()
    dlg._input.setText(token)
    dlg._on_accept()
    assert dlg.entered_key() == token


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


def test_entering_a_licence_via_the_menu_action_persists_it(qapp, tmp_path, monkeypatch,
                                                            _synchronous_run_async, sign):
    """ui/app_window.py's File > Enter License Key... action."""
    from database.repository import PokerDatabase
    from ui.app_window import AppWindow
    import ui.app_window as app_window_mod

    db = PokerDatabase(tmp_path / "test.db")
    win = AppWindow("Hero", db, "$")

    token = sign(expires="2027-09-09")
    monkeypatch.setattr(app_window_mod, "LicenseDialog",
                         lambda current_key=None, parent=None: _FakeAcceptedDialog(token))

    win._on_enter_license_key_clicked()

    assert settings_mod.get_license_key() == token
    assert settings_mod.get_license_expires_at() == "2027-09-09"
    db.close()


class _FakeAcceptedDialog:
    def __init__(self, key):
        self._key = key

    def exec(self):
        return True

    def entered_key(self):
        return self._key
