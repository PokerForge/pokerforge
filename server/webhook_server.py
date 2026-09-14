"""Stripe webhook receiver for PokerForge's subscription license. Dormant
until deployed and given real Stripe/SendGrid credentials -- see README.md.
A separate, standalone service: the desktop app never imports or starts
it, it only ever calls GET /license/status (see
core/licensing.py::refresh_license_status), and only once a paid key has
already been entered.

Reuses core.licensing.generate_license_key so every key this server issues
validates against the exact same checksum the shipped app already checks --
there is deliberately only one place that secret lives.

Subscription lifecycle, as three kinds of Stripe event:
- checkout.session.completed -- first payment. Issues + emails a new key,
  tied to the subscription's id.
- invoice.paid -- a renewal. Same key, just extends current_period_end.
- customer.subscription.updated / .deleted -- cancellation, a failed
  payment, etc. Updates status/current_period_end from Stripe's own
  subscription object; no new key, no email.

/license/status is what the desktop app actually calls: given a key, is
its subscription currently paid-through, and until when.
"""
import os
import secrets
import sqlite3
import string
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
import stripe
from flask import Flask, request, jsonify

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.licensing import generate_license_key  # noqa: E402

app = Flask(__name__)

stripe.api_key = os.environ.get("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET")
SENDGRID_API_KEY = os.environ.get("SENDGRID_API_KEY")
SENDGRID_FROM_EMAIL = os.environ.get("SENDGRID_FROM_EMAIL", "licenses@pokerforge.app")
DB_PATH = Path(os.environ.get("LICENSE_LEDGER_PATH") or Path(__file__).resolve().parent / "licenses.db")

# Statuses (mirroring Stripe's own Subscription.status) that still count as
# entitled -- current_period_end is the real gate either way, this just
# excludes states where Stripe has already given up on collecting.
_ACTIVE_STATUSES = {"active", "trialing", "past_due"}

# Excludes visually-ambiguous characters (0/O, 1/I/L) since a customer may
# have to retype this by hand from an email -- matches
# scripts/generate_license_key.py's manual-issuance equivalent.
_ALPHABET = "".join(c for c in string.ascii_uppercase + string.digits if c not in "01OIL")


def _random_group(length: int = 5) -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(length))


def _new_key() -> str:
    body = f"PF-{_random_group()}-{_random_group()}-{_random_group()}"
    return generate_license_key(body)


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS licenses ("
        "license_key TEXT PRIMARY KEY, email TEXT, stripe_customer_id TEXT, "
        "stripe_subscription_id TEXT UNIQUE, status TEXT, current_period_end TEXT, "
        "created_at TEXT, updated_at TEXT)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS processed_events ("
        "event_id TEXT PRIMARY KEY, processed_at TEXT)"
    )
    return conn


def _event_already_processed(conn: sqlite3.Connection, event_id: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM processed_events WHERE event_id = ?", (event_id,)
    ).fetchone() is not None


def _mark_event_processed(conn: sqlite3.Connection, event_id: str) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO processed_events (event_id, processed_at) VALUES (?, datetime('now'))",
        (event_id,),
    )


def _license_for_subscription(conn: sqlite3.Connection, subscription_id: str):
    return conn.execute(
        "SELECT license_key FROM licenses WHERE stripe_subscription_id = ?", (subscription_id,)
    ).fetchone()


def _subscription_period_end(subscription) -> int | None:
    """Stripe moved current_period_end from the Subscription object itself
    onto its line items in newer API versions -- covers both shapes since
    we don't control which API version any given account is pinned to.
    Safe for our case (one Price per subscription, never multi-item)."""
    top_level = subscription.get("current_period_end")
    if top_level is not None:
        return top_level
    items = (subscription.get("items") or {}).get("data") or []
    if items:
        return items[0].get("current_period_end")
    return None


def _period_end_iso(unix_ts) -> str | None:
    if unix_ts is None:
        return None
    return datetime.fromtimestamp(unix_ts, tz=timezone.utc).date().isoformat()


def _send_license_email(to_email: str, key: str) -> None:
    """Isolated on purpose -- swap this one function for a different email
    provider and nothing else in this file needs to change."""
    if not SENDGRID_API_KEY:
        app.logger.warning("SENDGRID_API_KEY not set -- skipping email send to %s", to_email)
        return
    resp = requests.post(
        "https://api.sendgrid.com/v3/mail/send",
        headers={"Authorization": f"Bearer {SENDGRID_API_KEY}"},
        json={
            "personalizations": [{"to": [{"email": to_email}]}],
            "from": {"email": SENDGRID_FROM_EMAIL},
            "subject": "Your PokerForge license key",
            "content": [{
                "type": "text/plain",
                "value": (
                    "Thanks for subscribing to PokerForge!\n\n"
                    f"Your license key:\n\n{key}\n\n"
                    "Enter it via File > Enter License Key... in the app. "
                    "It'll keep working for as long as your subscription is active."
                ),
            }],
        },
        timeout=10,
    )
    resp.raise_for_status()


def _handle_checkout_completed(conn: sqlite3.Connection, event) -> None:
    session = event["data"]["object"]
    subscription_id = session.get("subscription")
    if not subscription_id:
        app.logger.error("checkout.session.completed with no subscription (event %s)", event["id"])
        return
    if _license_for_subscription(conn, subscription_id):
        return  # already issued for this subscription -- a retried delivery

    email = (session.get("customer_details") or {}).get("email") or session.get("customer_email")
    if not email:
        app.logger.error("checkout.session.completed with no customer email (event %s)", event["id"])
        return

    subscription = stripe.Subscription.retrieve(subscription_id)
    key = _new_key()
    conn.execute(
        "INSERT INTO licenses (license_key, email, stripe_customer_id, stripe_subscription_id, "
        "status, current_period_end, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))",
        (key, email, session.get("customer"), subscription_id,
         subscription["status"], _period_end_iso(_subscription_period_end(subscription))),
    )
    _send_license_email(email, key)


def _handle_invoice_paid(conn: sqlite3.Connection, event) -> None:
    subscription_id = event["data"]["object"].get("subscription")
    if not subscription_id:
        return
    subscription = stripe.Subscription.retrieve(subscription_id)
    conn.execute(
        "UPDATE licenses SET status = ?, current_period_end = ?, updated_at = datetime('now') "
        "WHERE stripe_subscription_id = ?",
        (subscription["status"], _period_end_iso(_subscription_period_end(subscription)), subscription_id),
    )


def _handle_subscription_updated(conn: sqlite3.Connection, event) -> None:
    subscription = event["data"]["object"]
    conn.execute(
        "UPDATE licenses SET status = ?, current_period_end = ?, updated_at = datetime('now') "
        "WHERE stripe_subscription_id = ?",
        (subscription["status"], _period_end_iso(_subscription_period_end(subscription)), subscription["id"]),
    )


_EVENT_HANDLERS = {
    "checkout.session.completed": _handle_checkout_completed,
    "invoice.paid": _handle_invoice_paid,
    "customer.subscription.updated": _handle_subscription_updated,
    "customer.subscription.deleted": _handle_subscription_updated,
}


@app.route("/healthz", methods=["GET"])
def healthz():
    return jsonify(status="ok")


@app.route("/webhook/stripe", methods=["POST"])
def stripe_webhook():
    payload = request.data
    sig_header = request.headers.get("Stripe-Signature", "")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except (ValueError, stripe.error.SignatureVerificationError):
        return jsonify(error="invalid signature"), 400

    handler = _EVENT_HANDLERS.get(event["type"])
    if handler is None:
        return jsonify(status="ignored"), 200

    conn = _db()
    try:
        if _event_already_processed(conn, event["id"]):
            return jsonify(status="already processed"), 200
        # Stripe treats anything but a 2xx as "retry later" -- so a
        # handler that skips a malformed event (logged, not raised) still
        # gets marked processed rather than retried forever.
        handler(conn, event)
        _mark_event_processed(conn, event["id"])
        conn.commit()
    finally:
        conn.close()

    return jsonify(status="ok"), 200


@app.route("/license/status", methods=["GET"])
def license_status():
    key = request.args.get("key", "")
    conn = _db()
    try:
        row = conn.execute(
            "SELECT status, current_period_end FROM licenses WHERE license_key = ?", (key,)
        ).fetchone()
    finally:
        conn.close()

    if not row:
        return jsonify(valid=False, expires_at=None), 200

    status, expires_at = row
    valid = status in _ACTIVE_STATUSES and bool(expires_at)
    return jsonify(valid=valid, expires_at=expires_at), 200


if __name__ == "__main__":
    app.run(port=int(os.environ.get("PORT", 5000)))
