"""Stripe webhook receiver for PokerForge's subscription licences.
Dormant until deployed and given real Stripe/SendGrid credentials -- see
README.md. A separate, standalone service: the desktop app never imports
or starts it, it only ever calls GET /license/refresh (see
core/licensing.py::refresh_license_status), and only once a customer has
entered a licence.

Licences are Ed25519-signed tokens carrying the subscription they belong
to and the date it is paid up to (server/license_signing.py). The private
key lives only here; the app ships the public half and can verify but
never mint. That also means the ledger below isn't load-bearing -- a
licence proves itself, and /license/refresh reads subscription state
straight from Stripe -- so losing the database file costs nothing a
customer would notice.

Subscription lifecycle, as three kinds of Stripe event:
- checkout.session.completed -- first payment. Signs and emails a
  licence for the new subscription.
- invoice.paid -- a renewal. Records the later paid-through date; the
  app picks up an extended licence on its next refresh.
- customer.subscription.updated / .deleted -- cancellation, a failed
  payment, etc. Updates the recorded status.
"""
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
import stripe
from flask import Flask, request, jsonify

# Both entries matter: gunicorn runs this with server/ as the working
# directory, while the tests import it as server.webhook_server from the
# repo root. Adding both makes the sibling import work either way.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from license_signing import sign_license, verify_license  # noqa: E402

app = Flask(__name__)

stripe.api_key = os.environ.get("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET")
SENDGRID_API_KEY = os.environ.get("SENDGRID_API_KEY")
SENDGRID_FROM_EMAIL = os.environ.get("SENDGRID_FROM_EMAIL", "licenses@pokerforge.app")
DB_PATH = Path(os.environ.get("LICENSE_LEDGER_PATH") or Path(__file__).resolve().parent / "licenses.db")

# Where a subscription's issued licence is recorded on the Stripe
# Subscription object, so support can see what a customer was sent.
LICENSE_KEY_METADATA = "pokerforge_license_key"

# Statuses (mirroring Stripe's own Subscription.status) that still count as
# entitled -- current_period_end is the real gate either way, this just
# excludes states where Stripe has already given up on collecting.
_ACTIVE_STATUSES = {"active", "trialing", "past_due"}

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


def _field(obj, key: str, default=None):
    """Reads `key` from `obj`, whether `obj` is a plain dict (as our test
    fixtures build) or a real Stripe SDK object (as production webhooks
    actually deliver). These are NOT interchangeable: stripe.StripeObject
    supports [] indexing and `in`, but does not implement .get() the way
    dict does -- calling .get() on one raises AttributeError. A real
    checkout.session.completed event hit exactly this the first time this
    went live: the handler crashed before ever issuing a key, silently
    (from the customer's perspective -- they just never got an email)."""
    return obj[key] if obj and key in obj else default


def _subscription_period_end(subscription) -> int | None:
    """Stripe moved current_period_end from the Subscription object itself
    onto its line items in newer API versions -- covers both shapes since
    we don't control which API version any given account is pinned to.
    Safe for our case (one Price per subscription, never multi-item)."""
    top_level = _field(subscription, "current_period_end")
    if top_level is not None:
        return top_level
    items = _field(_field(subscription, "items"), "data") or []
    if items:
        return _field(items[0], "current_period_end")
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
    subscription_id = _field(session, "subscription")
    if not subscription_id:
        app.logger.error("checkout.session.completed with no subscription (event %s)", event["id"])
        return
    if _license_for_subscription(conn, subscription_id):
        return  # already issued for this subscription -- a retried delivery

    email = _field(_field(session, "customer_details"), "email") or _field(session, "customer_email")
    if not email:
        app.logger.error("checkout.session.completed with no customer email (event %s)", event["id"])
        return

    subscription = stripe.Subscription.retrieve(subscription_id)
    expires_at = _period_end_iso(_subscription_period_end(subscription))
    if not expires_at:
        app.logger.error("subscription %s has no period end; not signing a licence",
                         subscription_id)
        return
    key = sign_license(subscription_id, expires_at)

    # Record the issued licence against the subscription. Support can
    # then see what a customer was sent; the licence itself doesn't
    # depend on this, since it carries its own signed expiry.
    stripe.Subscription.modify(subscription_id, metadata={LICENSE_KEY_METADATA: key})

    conn.execute(
        "INSERT INTO licenses (license_key, email, stripe_customer_id, stripe_subscription_id, "
        "status, current_period_end, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))",
        (key, email, _field(session, "customer"), subscription_id,
         subscription["status"], expires_at),
    )
    _send_license_email(email, key)


def _handle_invoice_paid(conn: sqlite3.Connection, event) -> None:
    subscription_id = _field(event["data"]["object"], "subscription")
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


@app.route("/license/refresh", methods=["GET"])
def license_refresh():
    """Where the desktop app asks for a licence with a later expiry.

    This is how a renewal reaches a customer, and how a cancellation
    eventually bites: the server simply stops extending, and the licence
    lapses at the date it was last paid up to.

    Stripe is consulted directly rather than the local ledger, so losing
    the ledger file (this runs on an ephemeral filesystem) costs nothing
    a customer would notice."""
    payload = verify_license(request.args.get("token", ""))
    if not payload:
        # Unsigned, edited, or simply not ours.
        return jsonify(valid=False), 200

    subscription_id = payload.get("s")
    try:
        subscription = stripe.Subscription.retrieve(subscription_id)
    except Exception:
        app.logger.exception("could not load subscription %s", subscription_id)
        return jsonify(valid=False), 200

    status = subscription["status"]
    expires_at = _period_end_iso(_subscription_period_end(subscription))
    if status not in _ACTIVE_STATUSES or not expires_at:
        return jsonify(valid=False), 200

    conn = _db()
    try:
        conn.execute(
            "UPDATE licenses SET status = ?, current_period_end = ?, "
            "updated_at = datetime('now') WHERE stripe_subscription_id = ?",
            (status, expires_at, subscription_id),
        )
        conn.commit()
    finally:
        conn.close()

    return jsonify(valid=True, token=sign_license(subscription_id, expires_at)), 200


if __name__ == "__main__":
    app.run(port=int(os.environ.get("PORT", 5000)))
