"""License-key scaffolding for the subscription paid tier — currently a
no-op (LICENSE_ENFORCED is False, so is_licensed() always returns True and
nothing in the app is gated, and refresh_license_status() makes no network
call at all). This exists so that once server/ is deployed and given real
Stripe/SendGrid credentials, turning enforcement on is a one-line flip here
rather than a rewrite of whatever code needs to check it.

Key format/checksum (generate_license_key/validate_license_key) is NOT
real DRM — _CHECKSUM_SECRET lives in the shipped app, so anyone willing to
read the bytecode/binary can forge a key that passes validate_license_key()
on its own. What actually enforces a *subscription* (as opposed to a
one-time key) is refresh_license_status() below, which asks the license
server whether a key's subscription is still paid-through — a forged key
that was never issued by the server will simply come back invalid the
first time the app can reach the server, same as an offline-only forged
key would for anyone reading the source. Do not rely on any of this for a
real security boundary — it's a soft, honesty-based gate appropriate for a
small indie app.

Networking: refresh_license_status() is the ONE exception to this app's
"no network calls unless you ask" stance (see PRIVACY_POLICY.md and
core/update_checker.py's docstring) — and even then, only for someone who
has already entered a paid license key (see ui/app_window.py, which only
calls it when get_license_key() is set). A free-tier user who never enters
a key causes zero network calls, exactly as before."""
import hashlib
import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta

from config.settings import (
    get_license_key, set_license_key,
    get_license_expires_at, set_license_expires_at,
    set_license_last_checked_at,
)

LICENSE_ENFORCED = False

# Keys look like "PF-XXXXX-XXXXX-XXXXX-CC" where CC is a 2-character
# checksum of the preceding characters — catches typos/made-up keys
# without needing a server round-trip. Change this string (and every
# previously-issued key) if it's ever believed to have leaked.
_CHECKSUM_SECRET = "pokerforge-license-v1"


def _checksum(body: str) -> str:
    digest = hashlib.sha256((_CHECKSUM_SECRET + body).encode("utf-8")).hexdigest()
    return digest[:2].upper()


def generate_license_key(body: str) -> str:
    """Builds a well-formed key from a chosen body (e.g. "PF-A1B2C-C3D4E-F5G6H")
    by appending the correct checksum. Used both by scripts/generate_license_key.py
    (manual issuance) and server/webhook_server.py (automatic issuance) — the
    two are deliberately interchangeable, same checksum secret either way."""
    return f"{body}-{_checksum(body)}"


def validate_license_key(key: str) -> bool:
    """Format + checksum check only — does not contact any server. A
    well-formed key is accepted whether or not it was ever issued by
    server/webhook_server.py; is_licensed() layers the real subscription
    check (refresh_license_status's cached result) on top of this."""
    key = (key or "").strip().upper()
    if not key.startswith("PF-") or "-" not in key[3:]:
        return False
    body, _, checksum = key.rpartition("-")
    if len(checksum) != 2:
        return False
    return _checksum(body) == checksum


# Where the deployed license server (server/webhook_server.py) lives. None
# until that service is actually deployed — refresh_license_status() is a
# no-op while this is unset, same as everything else here while
# LICENSE_ENFORCED is False. Update this one line once you have a real
# deployed URL (see server/README.md).
LICENSE_SERVER_URL: str | None = None

# How many days of "couldn't reach the server" a subscriber's cached
# expiry is trusted past its face value before locking back to free tier.
# Covers both a temporarily offline app and a subscription that just
# renewed but hasn't been re-checked yet — see is_licensed()'s docstring.
LICENSE_STATUS_GRACE_DAYS = 14


def activate_key(key: str) -> None:
    """Called right after a user enters a key in the License dialog —
    persists it and grants a provisional grace window immediately (today,
    which combined with is_licensed()'s own +LICENSE_STATUS_GRACE_DAYS
    means a correctly-formatted key works right away even if the very
    first server check (kicked off right after this — see
    ui/app_window.py) can't complete straight away, e.g. briefly offline.
    A key that was never actually issued gets rejected the moment that
    check does succeed — see refresh_license_status()."""
    set_license_key(key)
    set_license_expires_at(date.today().isoformat())


def refresh_license_status(timeout: float = 5.0) -> bool:
    """Asks the license server whether the currently-entered key's
    subscription is still paid-through, and caches the answer
    (get_license_expires_at) for is_licensed() to use offline. Returns
    True if the server was actually reached (regardless of its verdict),
    False if the check couldn't be attempted or the network call failed —
    callers use this only to decide whether to warn about connectivity,
    never as the licensing decision itself (that's is_licensed()).

    A no-op — network-free — unless LICENSE_ENFORCED, a server URL is
    configured, AND a key is actually set. This is what keeps the app's
    "no network calls unless you ask" stance true for every free-tier
    user who never enters a key."""
    if not LICENSE_ENFORCED or not LICENSE_SERVER_URL:
        return False
    key = get_license_key()
    if not key:
        return False

    url = f"{LICENSE_SERVER_URL.rstrip('/')}/license/status?key={urllib.parse.quote(key)}"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return False

    set_license_last_checked_at(date.today().isoformat())
    if data.get("valid") and data.get("expires_at"):
        set_license_expires_at(data["expires_at"])
    else:
        # An explicit "no" from the server (never issued, or subscription
        # canceled and past its paid-through date) — reject outright
        # rather than granting a grace period on top of a real answer.
        set_license_expires_at(None)
    return True


def is_licensed() -> bool:
    """While LICENSE_ENFORCED is off: always True (today). Once on: a
    well-formed key AND a cached expiry (from activate_key's provisional
    value, or a real one from refresh_license_status) that hasn't passed
    by more than LICENSE_STATUS_GRACE_DAYS. The grace window is what lets
    a genuinely active subscriber keep working through a spotty-internet
    day or the gap between a renewal and the app's next check-in, while
    still locking a truly canceled subscription back to free tier within
    two weeks rather than never."""
    if not LICENSE_ENFORCED:
        return True
    if not validate_license_key(get_license_key() or ""):
        return False

    expires_at = get_license_expires_at()
    if not expires_at:
        return False
    try:
        expiry = date.fromisoformat(expires_at[:10])
    except ValueError:
        return False
    return date.today() <= expiry + timedelta(days=LICENSE_STATUS_GRACE_DAYS)


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
