"""Licence verification for the subscription paid tier — currently a
no-op (LICENSE_ENFORCED is False, so is_licensed() always returns True,
nothing in the app is gated, and refresh_license_status() makes no
network call at all). Flipping that one flag is what turns enforcement
on once you're ready to charge.

Licences are Ed25519-signed tokens:

    PF1.<base64url payload>.<base64url signature>

with the payload carrying the subscription it belongs to and the date it
is paid up to. This module only ever *verifies* them, using the public
key below — signing happens on the licence server
(server/license_signing.py), and the private key never leaves it. That
asymmetry is the point: this file, and the shipped app around it, can be
read freely without giving anyone the ability to mint a licence.

It also means the expiry date can be trusted offline. Because the date is
inside the signed payload rather than sitting in local settings, the app
can honour a licence without contacting anything — a forged or edited
token simply fails verification.

Networking: refresh_license_status() is the ONE exception to this app's
"no network calls unless you ask" stance (see PRIVACY_POLICY.md and
core/update_checker.py's docstring), and only for someone who has
already entered a licence. A free-tier user causes no network calls at
all."""
import base64
import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from config.settings import (
    get_license_key, set_license_key,
    get_license_expires_at, set_license_expires_at,
    set_license_last_checked_at,
)

LICENSE_ENFORCED = False

# Verifies signatures; cannot create them. Safe to ship and safe to read.
# Its private counterpart lives only on the licence server — rotating the
# pair invalidates every issued licence, so treat it as permanent.
LICENSE_PUBLIC_KEY = "dXu4gyw7Cq+/IACLSNlAOyjuOb7Sm1mvbDYcevXcMmc="

# Scheme version, so a future change can be told apart from this one
# rather than silently failing.
TOKEN_PREFIX = "PF1"

# How long a licence keeps working past the date it's paid up to. This
# covers the gap between a subscription renewing and the app next
# managing to fetch the extended token — someone offline for a fortnight
# after their renewal shouldn't be locked out. It can afford to be
# generous now that expiry is signed: unlike a checksum scheme, extra
# grace can't be farmed by minting fresh tokens, because minting is
# impossible without the private key.
LICENSE_GRACE_DAYS = 14

# Where the deployed licence server (server/webhook_server.py) lives.
LICENSE_SERVER_URL: str | None = "https://pokerforge-license-server.onrender.com"


def _b64url_decode(segment: str) -> bytes:
    padding = "=" * (-len(segment) % 4)
    return base64.urlsafe_b64decode(segment + padding)


def verify_license_key(token: str) -> dict | None:
    """Returns the token's payload if its signature is genuine, else
    None. Everything downstream depends on this: an unverified token is
    treated exactly like no licence at all."""
    parts = (token or "").strip().split(".")
    if len(parts) != 3 or parts[0] != TOKEN_PREFIX:
        return None
    _, payload_segment, signature_segment = parts

    try:
        public_key = Ed25519PublicKey.from_public_bytes(
            base64.b64decode(LICENSE_PUBLIC_KEY))
        public_key.verify(_b64url_decode(signature_segment),
                          payload_segment.encode("ascii"))
        payload = json.loads(_b64url_decode(payload_segment))
    except (InvalidSignature, ValueError, TypeError, json.JSONDecodeError):
        return None

    return payload if isinstance(payload, dict) else None


def validate_license_key(token: str) -> bool:
    """Whether a token is genuine. Used by the licence dialog to reject
    a mistyped or made-up entry before saving it."""
    return verify_license_key(token) is not None


def license_expiry(token: str) -> date | None:
    """The date a verified token is paid up to, or None if the token
    isn't genuine or carries no usable date."""
    payload = verify_license_key(token)
    if not payload:
        return None
    try:
        return date.fromisoformat(str(payload.get("e", ""))[:10])
    except ValueError:
        return None


def activate_key(token: str) -> bool:
    """Stores a licence entered by the user. Returns False (storing
    nothing) if the token isn't genuine.

    Unlike a checksum scheme there's no need to optimistically grant
    access pending a server check: the expiry is inside the signed
    payload, so a genuine token is proof of entitlement on its own, and
    a forged one can't get this far."""
    expiry = license_expiry(token)
    if expiry is None:
        return False
    set_license_key(token.strip())
    set_license_expires_at(expiry.isoformat())
    return True


def refresh_license_status(timeout: float = 5.0) -> bool:
    """Asks the licence server for a token with an extended expiry,
    which is how a renewal reaches the app, and how a cancellation
    eventually stops it working (the server simply stops extending).

    Returns True if the server was reached, False otherwise — callers
    use that only to decide whether to mention connectivity, never as
    the licensing decision itself, which is is_licensed().

    Network-free unless LICENSE_ENFORCED, a server URL is configured,
    and a licence is actually present."""
    if not LICENSE_ENFORCED or not LICENSE_SERVER_URL:
        return False
    token = get_license_key()
    if not token:
        return False

    url = (f"{LICENSE_SERVER_URL.rstrip('/')}/license/refresh"
           f"?token={urllib.parse.quote(token)}")
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return False

    set_license_last_checked_at(date.today().isoformat())

    refreshed = data.get("token")
    if refreshed and activate_key(refreshed):
        return True

    # Reached the server and it declined to renew — the subscription is
    # gone. Drop the cached expiry so access lapses now rather than
    # riding out a grace period it hasn't earned.
    if data.get("valid") is False:
        set_license_expires_at(None)
    return True


def is_licensed() -> bool:
    """While LICENSE_ENFORCED is off: always True. Once on: a genuine
    token whose signed expiry hasn't passed by more than
    LICENSE_GRACE_DAYS."""
    if not LICENSE_ENFORCED:
        return True

    expiry = license_expiry(get_license_key() or "")
    if expiry is None:
        return False
    return date.today() <= expiry + timedelta(days=LICENSE_GRACE_DAYS)


# Free-tier stake ceiling. Cash: up to and including 5NL (a 5-cent big
# blind). Tournaments: buy-in under $5. Compared against hand_player_stats'
# own big_blind/buy_in columns, which are already converted to one common
# currency at import time (core/currency.py's convert_hands_to_usd runs
# before a hand is ever stored) -- so this threshold is a real, consistent
# "5 cents' worth" across every currency a user plays in, not a native
# amount that would mean something different in £ versus $.
FREE_TIER_MAX_CASH_BB = 0.05
FREE_TIER_MAX_TOURNEY_BUYIN = 5.0


def should_gate_by_stakes() -> bool:
    """Whether queries should restrict themselves to the free tier's
    stake ceiling -- i.e. the inverse of is_licensed(). Always False
    today since LICENSE_ENFORCED is still off; this exists so the
    query-layer plumbing is already correct and in place for whenever a
    real pricing model ships, the same reasoning as is_licensed() itself."""
    return not is_licensed()
