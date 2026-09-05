"""License-key scaffolding for a future paid tier — currently a no-op
(LICENSE_ENFORCED is False, so is_licensed() always returns True and
nothing in the app is gated). This exists so that whenever a real pricing
model, payment processor, and key-issuing process are decided, turning
enforcement on is a one-line flip here rather than a rewrite of whatever
code needs to check it.

This is NOT real DRM — _CHECKSUM_SECRET lives in the shipped app, so
anyone willing to read the bytecode/binary can forge a key that passes
validate_license_key(). It's a soft gate (stops accidental/casual sharing
of a key past a typo-check) appropriate for a small indie app, not a
defense against a determined cracker. Do not rely on it for anything a
real security boundary would need to hold."""
import hashlib

from config.settings import get_license_key

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
    by appending the correct checksum — a stand-in for whatever a future
    purchase flow would generate server-side."""
    return f"{body}-{_checksum(body)}"


def validate_license_key(key: str) -> bool:
    """Format + checksum check only — does not contact any server, since
    there isn't one. A well-formed key is accepted whether or not it was
    ever "issued" anywhere, which is fine for a soft gate but means this
    must never be the only thing standing between a user and something
    that costs real money to provide."""
    key = (key or "").strip().upper()
    if not key.startswith("PF-") or "-" not in key[3:]:
        return False
    body, _, checksum = key.rpartition("-")
    if len(checksum) != 2:
        return False
    return _checksum(body) == checksum


def is_licensed() -> bool:
    if not LICENSE_ENFORCED:
        return True
    return validate_license_key(get_license_key() or "")
