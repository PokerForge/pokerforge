"""One-off setup script: creates the PokerForge subscription Product and
its two Prices (monthly/annual) in Stripe, then a Payment Link for each --
the actual "click here to subscribe" links a new user uses, since this is
a solo indie app with no separate storefront/checkout page of its own.

Safe to re-run for the Product/Prices: looks them up first (by name /
lookup_key) rather than creating duplicates. Payment Links are NOT
deduplicated -- each run creates fresh ones (harmless; archive old ones in
the Stripe Dashboard if you don't want them lying around).

Requires STRIPE_SECRET_KEY (see server/.env.example, or server/.env if
you've created one locally -- this script loads it automatically). Run it
once against a sk_test_ key to build out and test the whole flow, then
again with your real sk_live_ key when you're ready to actually charge
people -- each mode has entirely separate Products/Prices/Payment Links in
Stripe, this script works identically against either.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import stripe

PRODUCT_NAME = "PokerForge Subscription"
MONTHLY_LOOKUP_KEY = "pokerforge_monthly"
ANNUAL_LOOKUP_KEY = "pokerforge_annual"
MONTHLY_PRICE_CENTS = 999    # $9.99/mo
ANNUAL_PRICE_CENTS = 9999    # $99.99/yr


def _load_dotenv(path: Path) -> None:
    """No new dependency for a one-off local script -- just enough to
    pick up server/.env if present. Real deployments set real env vars,
    this is purely a local-run convenience."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if value:
            os.environ.setdefault(key, value)


def _get_or_create_product() -> str:
    existing = stripe.Product.search(query=f'name~"{PRODUCT_NAME}"', limit=1)
    if existing.data:
        return existing.data[0].id
    product = stripe.Product.create(
        name=PRODUCT_NAME,
        description="Full access to PokerForge -- every stake, every tournament buy-in.",
    )
    return product.id


def _get_or_create_price(product_id: str, lookup_key: str, unit_amount: int, interval: str) -> str:
    existing = stripe.Price.list(lookup_keys=[lookup_key], limit=1)
    if existing.data:
        return existing.data[0].id
    price = stripe.Price.create(
        product=product_id,
        unit_amount=unit_amount,
        currency="usd",
        recurring={"interval": interval},
        lookup_key=lookup_key,
    )
    return price.id


def _create_payment_link(price_id: str) -> str:
    link = stripe.PaymentLink.create(line_items=[{"price": price_id, "quantity": 1}])
    return link.url


def main():
    _load_dotenv(Path(__file__).resolve().parent / ".env")
    stripe.api_key = os.environ.get("STRIPE_SECRET_KEY")
    if not stripe.api_key:
        raise SystemExit(
            "STRIPE_SECRET_KEY not set -- copy server/.env.example to server/.env and fill it in, "
            "or set it as a real environment variable."
        )

    mode = "TEST" if stripe.api_key.startswith("sk_test_") else "LIVE"
    print(f"Using a {mode}-mode Stripe key.\n")

    product_id = _get_or_create_product()
    print(f"Product: {product_id} ({PRODUCT_NAME})")

    monthly_price_id = _get_or_create_price(product_id, MONTHLY_LOOKUP_KEY, MONTHLY_PRICE_CENTS, "month")
    annual_price_id = _get_or_create_price(product_id, ANNUAL_LOOKUP_KEY, ANNUAL_PRICE_CENTS, "year")
    print(f"Monthly price: {monthly_price_id} (${MONTHLY_PRICE_CENTS / 100:.2f}/mo)")
    print(f"Annual price:  {annual_price_id} (${ANNUAL_PRICE_CENTS / 100:.2f}/yr)")

    monthly_link = _create_payment_link(monthly_price_id)
    annual_link = _create_payment_link(annual_price_id)
    print(f"\n{mode}-mode Payment Links -- share these (or a button pointing at them):")
    print(f"Monthly: {monthly_link}")
    print(f"Annual:  {annual_link}")


if __name__ == "__main__":
    main()
