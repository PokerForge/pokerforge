"""server/webhook_server.py -- dormant until deployed with real Stripe/
SendGrid credentials (see server/README.md), but must behave correctly
the moment it's pointed at a live webhook. Requires this service's own
dependencies (server/requirements.txt); skips cleanly in the desktop
app's dev environment where they aren't installed.

Signing uses a throwaway key generated here, so these tests never touch
(or embed) the production one."""
import base64
import os

import pytest

pytest.importorskip("flask")
pytest.importorskip("stripe")
pytest.importorskip("requests")
pytest.importorskip("cryptography")

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

# Must exist before the server module is imported, since issuing a
# licence without it is deliberately an error rather than a fallback.
_TEST_SIGNING_KEY = Ed25519PrivateKey.generate().private_bytes(
    encoding=serialization.Encoding.Raw,
    format=serialization.PrivateFormat.Raw,
    encryption_algorithm=serialization.NoEncryption())
os.environ["LICENSE_SIGNING_KEY"] = base64.b64encode(_TEST_SIGNING_KEY).decode()

import core.licensing as lic
import server.webhook_server as srv
from server.license_signing import sign_license, verify_license


@pytest.fixture(autouse=True)
def _isolated_ledger(tmp_path, monkeypatch):
    monkeypatch.setattr(srv, "DB_PATH", tmp_path / "licenses.db")
    monkeypatch.setattr(srv, "STRIPE_WEBHOOK_SECRET", "whsec_test")
    monkeypatch.setattr(srv, "SENDGRID_API_KEY", None)
    monkeypatch.setattr(srv.stripe.Subscription, "modify", lambda sub_id, **kw: None)


@pytest.fixture()
def client():
    srv.app.config["TESTING"] = True
    return srv.app.test_client()


def _stripe_obj(data: dict):
    """Wraps a dict as a real StripeObject -- the shape production
    delivers. Not interchangeable with a dict: StripeObject supports []
    and `in` but not .get(), which is exactly the bug this suite once
    missed by using plain dicts (see webhook_server._field)."""
    return srv.stripe.StripeObject.construct_from(data, "sk_test_dummy")


def _subscription(sub_id="sub_1", status="active", period_end=1_900_000_000):
    return {"id": sub_id, "status": status, "current_period_end": period_end,
            "items": {"data": []}}


def _mock_retrieve(monkeypatch, subscription):
    monkeypatch.setattr(srv.stripe.Subscription, "retrieve",
                         lambda sub_id, **kw: _stripe_obj(subscription))


def _checkout_completed_event(event_id="evt_1", email="customer@example.com",
                               subscription_id="sub_1", customer_id="cus_1"):
    return {"id": event_id, "type": "checkout.session.completed",
            "data": {"object": {"customer_details": {"email": email},
                                "customer": customer_id,
                                "subscription": subscription_id}}}


def _post_event(client, event, monkeypatch):
    monkeypatch.setattr(srv.stripe.Webhook, "construct_event",
                         lambda payload, sig, secret: _stripe_obj(event))
    return client.post("/webhook/stripe", data=b"{}", headers={"Stripe-Signature": "sig"})


def _license_row(subscription_id="sub_1"):
    conn = srv._db()
    row = conn.execute(
        "SELECT license_key, email, status, current_period_end FROM licenses "
        "WHERE stripe_subscription_id = ?", (subscription_id,)).fetchone()
    conn.close()
    return row


# --- webhook ----------------------------------------------------------

def test_rejects_a_request_with_an_invalid_signature(client, monkeypatch):
    def _raise(*a, **kw):
        raise srv.stripe.error.SignatureVerificationError("bad sig", "sig_header")
    monkeypatch.setattr(srv.stripe.Webhook, "construct_event", _raise)

    assert client.post("/webhook/stripe", data=b"{}",
                       headers={"Stripe-Signature": "bogus"}).status_code == 400


def test_checkout_issues_a_signed_licence_for_the_subscription(client, monkeypatch):
    _mock_retrieve(monkeypatch, _subscription())

    assert _post_event(client, _checkout_completed_event(), monkeypatch).status_code == 200

    token, email, status, expires_at = _license_row()
    assert email == "customer@example.com"
    assert status == "active"
    assert expires_at == srv._period_end_iso(1_900_000_000)

    payload = verify_license(token)
    assert payload is not None, "issued licence must carry a genuine signature"
    assert payload["s"] == "sub_1"
    assert payload["e"] == expires_at


def test_the_issued_licence_is_recorded_on_the_stripe_subscription(client, monkeypatch):
    _mock_retrieve(monkeypatch, _subscription())
    recorded = {}
    monkeypatch.setattr(srv.stripe.Subscription, "modify",
                         lambda sub_id, **kw: recorded.update({"id": sub_id, **kw}))

    _post_event(client, _checkout_completed_event(), monkeypatch)

    assert recorded["id"] == "sub_1"
    assert recorded["metadata"][srv.LICENSE_KEY_METADATA] == _license_row()[0]


def test_a_retried_checkout_does_not_issue_a_second_licence(client, monkeypatch):
    _mock_retrieve(monkeypatch, _subscription())
    event = _checkout_completed_event()

    _post_event(client, event, monkeypatch)
    first = _license_row()[0]
    _post_event(client, event, monkeypatch)

    conn = srv._db()
    count = conn.execute("SELECT COUNT(*) FROM licenses").fetchone()[0]
    conn.close()
    assert count == 1
    assert _license_row()[0] == first


def test_checkout_without_a_period_end_issues_nothing(client, monkeypatch):
    """Better to issue no licence than one that expires immediately."""
    _mock_retrieve(monkeypatch, {"id": "sub_1", "status": "active",
                                  "current_period_end": None, "items": {"data": []}})

    assert _post_event(client, _checkout_completed_event(), monkeypatch).status_code == 200
    assert _license_row() is None


def test_checkout_with_no_subscription_or_email_is_skipped(client, monkeypatch):
    no_sub = {"id": "e1", "type": "checkout.session.completed",
              "data": {"object": {"customer_details": {"email": "x@example.com"}}}}
    assert _post_event(client, no_sub, monkeypatch).status_code == 200

    _mock_retrieve(monkeypatch, _subscription())
    no_email = _checkout_completed_event(event_id="e2")
    no_email["data"]["object"]["customer_details"] = None
    assert _post_event(client, no_email, monkeypatch).status_code == 200
    assert _license_row() is None


def test_invoice_paid_records_the_extended_period(client, monkeypatch):
    _mock_retrieve(monkeypatch, _subscription(period_end=1_700_000_000))
    _post_event(client, _checkout_completed_event(), monkeypatch)
    issued = _license_row()[0]

    _mock_retrieve(monkeypatch, _subscription(period_end=1_900_000_000))
    _post_event(client, {"id": "evt_inv", "type": "invoice.paid",
                         "data": {"object": {"subscription": "sub_1"}}}, monkeypatch)

    token, _, status, expires_at = _license_row()
    assert token == issued          # the app fetches an extended one on refresh
    assert status == "active"
    assert expires_at == srv._period_end_iso(1_900_000_000)


def test_ignores_event_types_it_does_not_handle(client, monkeypatch):
    resp = _post_event(client, {"id": "e", "type": "payment_intent.created",
                                 "data": {"object": {}}}, monkeypatch)
    assert resp.get_json()["status"] == "ignored"


# --- refresh ----------------------------------------------------------

def test_refresh_extends_a_licence_for_an_active_subscription(client, monkeypatch):
    old_token = sign_license("sub_1", "2026-01-01")
    _mock_retrieve(monkeypatch, _subscription(period_end=1_900_000_000))

    body = client.get("/license/refresh", query_string={"token": old_token}).get_json()

    assert body["valid"] is True
    payload = verify_license(body["token"])
    assert payload["e"] == srv._period_end_iso(1_900_000_000)
    assert payload["e"] != "2026-01-01", "the licence should have moved forward"


def test_refresh_declines_a_cancelled_subscription(client, monkeypatch):
    token = sign_license("sub_1", "2026-01-01")
    _mock_retrieve(monkeypatch, _subscription(status="canceled"))

    body = client.get("/license/refresh", query_string={"token": token}).get_json()

    assert body["valid"] is False
    assert "token" not in body


def test_refresh_declines_an_unsigned_token(client, monkeypatch):
    """Without this the endpoint would hand out a genuine licence to
    anyone who made up a token naming a real subscription."""
    called = []
    monkeypatch.setattr(srv.stripe.Subscription, "retrieve",
                         lambda sub_id, **kw: called.append(sub_id))

    forged = "PF1." + base64.urlsafe_b64encode(b'{"e":"2099-01-01","s":"sub_1"}').decode().rstrip("=") + ".bm90YXNpZw"
    body = client.get("/license/refresh", query_string={"token": forged}).get_json()

    assert body["valid"] is False
    assert called == [], "an unverified token must not even reach Stripe"


def test_refresh_declines_junk(client):
    for junk in ["", "rubbish", "PF1.a.b"]:
        assert client.get("/license/refresh", query_string={"token": junk}).get_json()["valid"] is False


def test_a_refreshed_licence_is_accepted_by_the_app(client, monkeypatch):
    """End to end: what the server signs, core/licensing.py verifies."""
    monkeypatch.setattr(lic, "LICENSE_PUBLIC_KEY", base64.b64encode(
        Ed25519PrivateKey.from_private_bytes(_TEST_SIGNING_KEY).public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw)).decode())
    _mock_retrieve(monkeypatch, _subscription(period_end=1_900_000_000))

    body = client.get("/license/refresh",
                      query_string={"token": sign_license("sub_1", "2026-01-01")}).get_json()

    assert lic.validate_license_key(body["token"]) is True
    assert lic.license_expiry(body["token"]).isoformat() == srv._period_end_iso(1_900_000_000)


def test_healthz_reports_ok(client):
    assert client.get("/healthz").get_json()["status"] == "ok"
