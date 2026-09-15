"""Signs licence tokens. Server-side only — this is the half of the
scheme that holds the private key, and it must never be bundled into the
desktop app (core/licensing.py verifies with the public key and has no
signing code at all, deliberately).

Token format, matching core/licensing.py:

    PF1.<base64url payload>.<base64url signature>

The payload records which subscription the licence belongs to and the
date it's paid up to. Because that date is signed, the app can trust it
offline without asking anything — and can't be talked into extending it.

Requires LICENSE_SIGNING_KEY (base64 of a raw Ed25519 private key, as
printed by scripts/generate_signing_key.py).
"""
import base64
import json
import os
from datetime import date

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

TOKEN_PREFIX = "PF1"


class SigningKeyMissing(RuntimeError):
    """Raised rather than issuing an unsigned or placeholder licence."""


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _private_key() -> Ed25519PrivateKey:
    encoded = os.environ.get("LICENSE_SIGNING_KEY")
    if not encoded:
        raise SigningKeyMissing(
            "LICENSE_SIGNING_KEY is not set — cannot sign a licence. "
            "Generate one with scripts/generate_signing_key.py.")
    return Ed25519PrivateKey.from_private_bytes(base64.b64decode(encoded))


def sign_license(subscription_id: str, expires_at: str | date) -> str:
    """Builds a signed licence token.

    `expires_at` is the date the subscription is paid up to — normally
    Stripe's current_period_end. Renewing means signing a fresh token
    with a later date, which is how an extension reaches the app.
    """
    if isinstance(expires_at, date):
        expires_at = expires_at.isoformat()

    payload = {"s": subscription_id, "e": str(expires_at)[:10]}
    segment = _b64url(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    signature = _private_key().sign(segment.encode("ascii"))
    return f"{TOKEN_PREFIX}.{segment}.{_b64url(signature)}"


def verify_license(token: str) -> dict | None:
    """Verifies a token's signature using the public half of the signing
    key, returning its payload or None.

    The refresh endpoint needs this: without it, someone could present a
    token they made up naming a real subscription and be handed a
    genuine one in exchange."""
    payload = read_license(token)
    if payload is None:
        return None
    _, segment, signature_segment = token.strip().split(".")
    try:
        signature = base64.urlsafe_b64decode(
            signature_segment + "=" * (-len(signature_segment) % 4))
        _private_key().public_key().verify(signature, segment.encode("ascii"))
    except Exception:
        return None
    return payload


def read_license(token: str) -> dict | None:
    """Reads a token's payload WITHOUT verifying it. Only for looking up
    which subscription a token refers to before checking that
    subscription's real state — never for deciding entitlement."""
    parts = (token or "").strip().split(".")
    if len(parts) != 3 or parts[0] != TOKEN_PREFIX:
        return None
    segment = parts[1]
    try:
        raw = base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4))
        payload = json.loads(raw)
    except (ValueError, TypeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None
