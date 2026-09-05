"""Manual "Check for Updates" — nothing calls this automatically. It only
runs when the user picks Help > Check for Updates, which keeps the app's
"no network calls unless you ask" privacy stance true by default (see
PRIVACY_POLICY.md's "Third-party services" section).

Fetches a small static JSON manifest — no server, no API, just a file
somewhere reachable over HTTPS shaped like:
    {"version": "1.0.1", "url": "https://.../download", "notes": "..."}
— and compares it against config.version.APP_VERSION.

config.version.UPDATE_MANIFEST_URL is None until real release hosting is
set up (GitHub raw file, your own site, anything serving that JSON) —
until then, check_for_update() reports itself as unconfigured rather than
failing against a fake placeholder URL that would just 404."""
import json
import logging
import urllib.request
from dataclasses import dataclass

from config.version import APP_VERSION, UPDATE_MANIFEST_URL

logger = logging.getLogger(__name__)


@dataclass
class UpdateCheckResult:
    checked: bool  # False if not configured, unreachable, or malformed
    update_available: bool
    latest_version: str | None = None
    download_url: str | None = None
    notes: str | None = None
    error: str | None = None


def _parse_version(v: str) -> tuple:
    parts = []
    for p in v.split('.'):
        try:
            parts.append(int(p))
        except ValueError:
            parts.append(0)
    return tuple(parts)


def _version_gt(a: str, b: str) -> bool:
    """True if version `a` is greater than `b` — pads to equal length
    first, since plain tuple comparison treats a shorter-but-equal prefix
    as "less than" (e.g. (1,0) < (1,0,0)), which would wrongly flag "1.0.0"
    as newer than "1.0" even though they're the same version."""
    pa, pb = _parse_version(a), _parse_version(b)
    n = max(len(pa), len(pb))
    pa += (0,) * (n - len(pa))
    pb += (0,) * (n - len(pb))
    return pa > pb


def check_for_update(timeout: float = 5.0) -> UpdateCheckResult:
    if not UPDATE_MANIFEST_URL:
        return UpdateCheckResult(checked=False, update_available=False,
                                  error="Update checking isn't set up yet.")
    try:
        with urllib.request.urlopen(UPDATE_MANIFEST_URL, timeout=timeout) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        latest = str(data.get('version') or '')
        if not latest:
            return UpdateCheckResult(checked=False, update_available=False,
                                      error="Update manifest didn't include a version number.")
        return UpdateCheckResult(
            checked=True, update_available=_version_gt(latest, APP_VERSION),
            latest_version=latest, download_url=data.get('url'), notes=data.get('notes'),
        )
    except Exception as exc:
        logger.warning("Update check failed: %s", exc)
        return UpdateCheckResult(checked=False, update_available=False,
                                  error="Couldn't reach the update server.")
