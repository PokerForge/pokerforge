"""server/webhook_server.py -- dormant until deployed with real Stripe/
SendGrid credentials (see server/README.md), but must behave correctly the
moment it's ever pointed at a live webhook. Requires this service's own
dependencies (server/requirements.txt); skips cleanly in the main desktop
app's dev environment where they aren't installed."""
import pytest

pytest.importorskip("flask")
pytest.importorskip("stripe")
pytest.importorskip("requests")

import core.licensing as lic
import server.webhook_server as srv


@pytest.fixture(autouse=True)
def _isolated_ledger(tmp_path, monkeypatch):
    monkeypatch.setattr(srv, "DB_PATH", tmp_path / "licenses.db")
    monkeypatch.setattr(srv, "STRIPE_WEBHOOK_SECRET", "whsec_test")
    monkeypatch.setattr(srv, "SENDGRID_API_KEY", None)


@pytest.fixture()
def client():
    srv.app.config["TESTING"] = True
    return srv.app.test_client()


def _subscription(sub_id="sub_1", status="active", period_end=1_900_000_000):
    return {"id": sub_id, "status": status, "current_period_end": period_end, "items": {"data": []}}


def _mock_retrieve(monkeypatch, subscription):
    monkeypatch.setattr(srv.stripe.Subscription, "retrieve", lambda sub_id: subscription)


def _checkout_completed_event(event_id="evt_1", email="customer@example.com",
                               subscription_id="sub_1", customer_id="cus_1"):
    return {
        "id": event_id,
        "type": "checkout.session.completed",
        "data": {"object": {
            "customer_details": {"email": email},
            "customer": customer_id,
            "subscription": subscription_id,
        }},
    }


def _post_event(client, event, monkeypatch):
    monkeypatch.setattr(srv.stripe.Webhook, "construct_event",
                         lambda payload, sig, secret: event)
    return client.post("/webhook/stripe", data=b"{}", headers={"Stripe-Signature": "sig"})


def _license_row(subscription_id="sub_1"):
    conn = srv._db()
    row = conn.execute(
        "SELECT license_key, email, status, current_period_end FROM licenses "
        "WHERE stripe_subscription_id = ?", (subscription_id,)
    ).fetchone()
    conn.close()
    return row


def test_rejects_a_request_with_an_invalid_signature(client, monkeypatch):
    def _raise(*a, **kw):
        raise srv.stripe.error.SignatureVerificationError("bad sig", "sig_header")
    monkeypatch.setattr(srv.stripe.Webhook, "construct_event", _raise)

    resp = client.post("/webhook/stripe", data=b"{}", headers={"Stripe-Signature": "bogus"})

    assert resp.status_code == 400


def test_checkout_completed_issues_a_valid_key_and_activates_the_license(client, monkeypatch):
    _mock_retrieve(monkeypatch, _subscription())

    resp = _post_event(client, _checkout_completed_event(), monkeypatch)

    assert resp.status_code == 200
    key, email, status, expires_at = _license_row()
    assert email == "customer@example.com"
    assert lic.validate_license_key(key)
    assert status == "active"
    assert expires_at == srv._period_end_iso(1_900_000_000)


def test_status_endpoint_reports_a_freshly_issued_license_as_valid(client, monkeypatch):
    _mock_retrieve(monkeypatch, _subscription(period_end=1_900_000_000))
    _post_event(client, _checkout_completed_event(), monkeypatch)
    key = _license_row()[0]

    body = client.get(f"/license/status?key={key}").get_json()

    assert body["valid"] is True
    assert body["expires_at"] == srv._period_end_iso(1_900_000_000)


def test_retried_checkout_completed_does_not_issue_a_second_key(client, monkeypatch):
    _mock_retrieve(monkeypatch, _subscription())
    event = _checkout_completed_event()

    _post_event(client, event, monkeypatch)
    first_key = _license_row()[0]
    _post_event(client, event, monkeypatch)  # Stripe redelivering the same event id

    conn = srv._db()
    count = conn.execute(
        "SELECT COUNT(*) FROM licenses WHERE stripe_subscription_id = 'sub_1'"
    ).fetchone()[0]
    conn.close()
    assert count == 1
    assert _license_row()[0] == first_key


def test_invoice_paid_extends_the_existing_key_without_issuing_a_new_one(client, monkeypatch):
    _mock_retrieve(monkeypatch, _subscription(period_end=1_700_000_000))
    _post_event(client, _checkout_completed_event(), monkeypatch)
    original_key = _license_row()[0]

    _mock_retrieve(monkeypatch, _subscription(period_end=1_900_000_000))  # renewed further out
    invoice_event = {
        "id": "evt_invoice_1",
        "type": "invoice.paid",
        "data": {"object": {"subscription": "sub_1"}},
    }
    _post_event(client, invoice_event, monkeypatch)

    key, _, status, expires_at = _license_row()
    assert key == original_key
    assert status == "active"
    assert expires_at == srv._period_end_iso(1_900_000_000)


def test_subscription_deleted_marks_the_license_invalid(client, monkeypatch):
    _mock_retrieve(monkeypatch, _subscription())
    _post_event(client, _checkout_completed_event(), monkeypatch)
    key = _license_row()[0]

    canceled_event = {
        "id": "evt_cancel_1",
        "type": "customer.subscription.deleted",
        "data": {"object": {"id": "sub_1", "status": "canceled", "current_period_end": 1_900_000_000}},
    }
    _post_event(client, canceled_event, monkeypatch)

    body = client.get(f"/license/status?key={key}").get_json()
    assert body["valid"] is False


def test_period_end_falls_back_to_line_item_when_absent_at_top_level(client, monkeypatch):
    """A defensive case for Stripe's own API version migration -- some
    accounts no longer carry current_period_end on the Subscription
    itself, only on its line items (see _subscription_period_end)."""
    subscription = {"id": "sub_1", "status": "active", "current_period_end": None,
                     "items": {"data": [{"current_period_end": 1_900_000_000}]}}
    _mock_retrieve(monkeypatch, subscription)

    _post_event(client, _checkout_completed_event(), monkeypatch)

    assert _license_row()[3] == srv._period_end_iso(1_900_000_000)


def test_checkout_completed_with_no_subscription_id_is_skipped_without_error(client, monkeypatch):
    event = {
        "id": "evt_no_sub",
        "type": "checkout.session.completed",
        "data": {"object": {"customer_details": {"email": "x@example.com"}}},
    }

    resp = _post_event(client, event, monkeypatch)

    assert resp.status_code == 200


def test_checkout_completed_with_no_customer_email_is_skipped_without_error(client, monkeypatch):
    _mock_retrieve(monkeypatch, _subscription())
    event = _checkout_completed_event()
    event["data"]["object"]["customer_details"] = None

    resp = _post_event(client, event, monkeypatch)

    assert resp.status_code == 200
    assert _license_row() is None


def test_ignores_event_types_it_does_not_handle(client, monkeypatch):
    other_event = {"id": "evt_x", "type": "payment_intent.created", "data": {"object": {}}}

    resp = _post_event(client, other_event, monkeypatch)

    assert resp.status_code == 200
    assert resp.get_json()["status"] == "ignored"


def test_status_endpoint_reports_an_unknown_key_as_invalid(client):
    resp = client.get("/license/status?key=PF-DOES-NOT-EXIST")
    body = resp.get_json()
    assert body["valid"] is False
    assert body["expires_at"] is None


def test_healthz_reports_ok(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "ok"
