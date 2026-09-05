"""Manual "Check for Updates" — nothing calls this automatically. It only
runs when the user picks Help > Check for Updates, which keeps the app's
"no network calls unless you ask" privacy stance true by default (see
PRIVACY_POLICY.md's "Third-party services" section).

Two possible sources, tried in this order:
1. config.version.GITHUB_REPO ("owner/repo") — queries GitHub's own
   Releases API, no hosting needed.
2. config.version.UPDATE_MANIFEST_URL — a small static JSON file
   shaped like {"version": "1.0.1", "url": "https://.../download",
   "notes": "..."}, for when releases don't live on GitHub.

Both compare the result against config.version.APP_VERSION. Until at
least one is configured, check_for_update() reports itself as
unconfigured rather than failing against a fake placeholder URL that
would just 404."""
import json
import logging
import urllib.request
from dataclasses import dataclass

from config.version import APP_VERSION, GITHUB_REPO, UPDATE_MANIFEST_URL

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


def _check_github_releases(repo: str, timeout: float) -> UpdateCheckResult:
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    request = urllib.request.Request(
        url, headers={"Accept": "application/vnd.github+json", "User-Agent": "PokerForge-UpdateChecker"})
    with urllib.request.urlopen(request, timeout=timeout) as resp:
        data = json.loads(resp.read().decode('utf-8'))
    latest = str(data.get('tag_name') or '').lstrip('vV')
    if not latest:
        return UpdateCheckResult(checked=False, update_available=False,
                                  error="Latest GitHub release didn't have a tag name.")
    # Prefer a direct link to the installer .exe asset over the release
    # page itself, if one was uploaded to the release.
    download_url = data.get('html_url')
    for asset in data.get('assets') or []:
        if str(asset.get('name', '')).lower().endswith('.exe'):
            download_url = asset.get('browser_download_url', download_url)
            break
    return UpdateCheckResult(
        checked=True, update_available=_version_gt(latest, APP_VERSION),
        latest_version=latest, download_url=download_url, notes=data.get('body'),
    )


def _check_manifest_url(manifest_url: str, timeout: float) -> UpdateCheckResult:
    with urllib.request.urlopen(manifest_url, timeout=timeout) as resp:
        data = json.loads(resp.read().decode('utf-8'))
    latest = str(data.get('version') or '')
    if not latest:
        return UpdateCheckResult(checked=False, update_available=False,
                                  error="Update manifest didn't include a version number.")
    return UpdateCheckResult(
        checked=True, update_available=_version_gt(latest, APP_VERSION),
        latest_version=latest, download_url=data.get('url'), notes=data.get('notes'),
    )


def check_for_update(timeout: float = 5.0) -> UpdateCheckResult:
    if not GITHUB_REPO and not UPDATE_MANIFEST_URL:
        return UpdateCheckResult(checked=False, update_available=False,
                                  error="Update checking isn't set up yet.")
    try:
        if GITHUB_REPO:
            return _check_github_releases(GITHUB_REPO, timeout)
        return _check_manifest_url(UPDATE_MANIFEST_URL, timeout)
    except Exception as exc:
        logger.warning("Update check failed: %s", exc)
        return UpdateCheckResult(checked=False, update_available=False,
                                  error="Couldn't reach the update server.")
