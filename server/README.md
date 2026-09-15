# PokerForge license server (dormant)

Turns a paid Stripe subscription into an emailed license key that stays
valid for as long as the subscription is active. **Not deployed anywhere
yet** — this is ready-to-deploy code for once you're ready to go live.
Until then, issue keys manually with `python scripts/generate_license_key.py`
from the repo root (note: a manually-issued key never expires, since there's
no subscription behind it for the server to track — fine for a one-off
favor, not a substitute for a real subscription).

This is a separate standalone service — it is not started by, or bundled
with, the desktop app. The desktop app's only connection to it is a single
outbound `GET /license/status` call (see `core/licensing.py::refresh_license_status`),
made only once a paid key has already been entered.

## The pieces

- **`webhook_server.py`** — the Flask service. Listens for Stripe webhook
  events and exposes `/license/status` for the desktop app to poll.
- **`setup_stripe_products.py`** — a one-off script that creates the
  PokerForge subscription Product, its Monthly/Annual Prices, and a
  Payment Link for each (the actual "click here to subscribe" URLs).
- **`licenses.db`** — a local SQLite ledger the webhook service maintains:
  one row per subscription, tracking its license key, status, and
  paid-through date. Gitignored; nothing here belongs in version control.

## Subscription lifecycle

Three kinds of Stripe webhook event, all pointed at the same
`/webhook/stripe` endpoint:

1. **`checkout.session.completed`** — first payment. Generates a new key
   with the exact same `core.licensing.generate_license_key` the desktop
   app already validates against, records it against the subscription id,
   and emails it via SendGrid. Idempotent — a redelivered event (Stripe
   retries on anything but a 2xx response) reuses the existing key rather
   than issuing and emailing a second one.
2. **`invoice.paid`** — a renewal. Same key, just extends the recorded
   paid-through date. No new email.
3. **`customer.subscription.updated` / `.deleted`** — cancellation, a
   failed payment, etc. Updates status/paid-through date from Stripe's own
   subscription object.

`GET /license/status?key=...` is what the desktop app actually calls: is
this key's subscription currently paid-through, and until when. See
`core/licensing.py`'s module docstring for how the app uses (and caches)
that answer, including its offline grace period.

## Setting this up for real, when you're ready

1. Copy `.env.example` to `.env` and fill in `STRIPE_SECRET_KEY` (from the
   Stripe Dashboard → Developers → API keys).
2. Run `python server/setup_stripe_products.py` — creates the Product,
   both Prices ($9.99/mo, $99.99/yr), and prints two Payment Link URLs.
   Safe to re-run (Product/Prices are looked up, not duplicated); each run
   does create fresh Payment Links, so only keep the ones you mean to
   share.
3. Put those Payment Link URLs wherever a new customer would find them —
   your site, a link in the app's About/Settings dialog, wherever.
   `success_url` isn't something you need to configure: the email is what
   actually delivers the key, not the post-payment redirect page.
4. Deploy this `server/` directory to something that can run a small
   always-on Python web service. `render.yaml` is set up for
   [Render](https://render.com) specifically — push this repo to GitHub,
   create a Render account, "New +" > "Blueprint", point it at the repo,
   and Render reads `render.yaml` and configures the service itself
   (you'll be prompted to paste in the secret env vars — `STRIPE_SECRET_KEY`,
   `STRIPE_WEBHOOK_SECRET`, `SENDGRID_API_KEY` — since those deliberately
   aren't in the file). Railway and Fly.io work too, just without the
   Blueprint shortcut — build/start commands are the same either way:
   - Build command: `pip install -r server/requirements.txt`
   - Start command: `gunicorn --chdir server --bind 0.0.0.0:$PORT webhook_server:app`
     (`$PORT` is set by the host automatically — binding to it, and to
     `0.0.0.0` rather than just localhost, is what makes the service
     actually reachable from the outside).

   **Storage note:** a free-tier web service's filesystem is ephemeral,
   so `licenses.db` is wiped on every redeploy. That's survivable by
   design: every issued key is also written to its Stripe subscription's
   metadata (`pokerforge_license_key`), which makes Stripe the durable
   record and the ledger a disposable cache. If a key isn't found
   locally, `/license/status` looks it up in Stripe and repopulates the
   row, so a customer's key keeps working across a wipe. A persistent
   disk is therefore optional — worth adding for speed if the customer
   list ever grows large enough that a rebuild scan gets slow.
5. In the Stripe Dashboard, add a webhook endpoint pointing at
   `https://<your-deployed-host>/webhook/stripe`, subscribed to
   `checkout.session.completed`, `invoice.paid`,
   `customer.subscription.updated`, and `customer.subscription.deleted`.
   Copy its signing secret into `STRIPE_WEBHOOK_SECRET` on the host.
6. Create a SendGrid account (or swap `_send_license_email` in
   `webhook_server.py` for whatever provider you'd rather use instead —
   it's isolated into one function precisely so that's a one-function
   change), verify a sender address, and set `SENDGRID_API_KEY` /
   `SENDGRID_FROM_EMAIL`.
7. In `core/licensing.py`, set `LICENSE_SERVER_URL` to your deployed
   host's URL, and flip `LICENSE_ENFORCED = True` once you're ready for
   the free tier to actually start applying.

Steps 1–3 work fine with a `sk_test_...` key, so you can build and click
through the whole purchase experience before anything real is at stake.
Re-run `setup_stripe_products.py` with your `sk_live_...` key when you're
ready to actually charge people — test and live mode keep entirely
separate Products/Prices/Payment Links in Stripe.

## Local testing without deploying anywhere

Stripe's CLI can forward real test-mode webhook events to a local server:

```
stripe listen --forward-to localhost:5000/webhook/stripe
```

Then trigger a synthetic event:

```
stripe trigger checkout.session.completed
```

`stripe listen` prints a `whsec_...` value to use as `STRIPE_WEBHOOK_SECRET`
for this local run. The triggered test event won't carry a real customer
email or a real subscription, so the server will log an error and skip
issuing a key for it — that's expected; it still confirms the endpoint is
reachable and the signature verifies. To test the full loop for real, use
one of the Payment Links from `setup_stripe_products.py` and complete a
test-mode checkout (any of [Stripe's test card numbers](https://docs.stripe.com/testing) work) —
while `stripe listen` is running, that triggers the real event chain.

## One privacy-policy note

`refresh_license_status()` is a deliberate, narrow exception to this app's
otherwise-true "no network calls unless you ask" stance (see
`PRIVACY_POLICY.md` and `core/update_checker.py`'s docstring) — and only
for someone who has already entered a paid key; a free-tier user still
causes zero network calls. Update `PRIVACY_POLICY.md` to disclose this
(only the license key itself is sent, never hand-history or personal
poker data) before flipping `LICENSE_ENFORCED` on for real.

## Running the test suite for this service

The main app's test suite doesn't depend on Flask/Stripe/requests being
installed, since they're unrelated to the desktop app itself. To run
`tests/test_license_webhook_server.py`, install this service's own
dependencies first:

```
pip install -r server/requirements.txt
python -m pytest tests/test_license_webhook_server.py -q
```
