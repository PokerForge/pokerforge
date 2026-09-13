"""Single source of truth for the app version — shown in Help > About and
worth bumping on every release once there's a real release process."""
APP_VERSION = "1.0.0-beta.1"

# "owner/repo" for Help > Check for Updates to query GitHub's own Releases
# API (no hosting to set up — GitHub already serves this for any public
# repo, and the API works for a private repo too as long as the release
# itself is public). Takes priority over UPDATE_MANIFEST_URL below when
# both are set. None until the app has an actual GitHub repo with tagged
# releases (see core/update_checker.py's check_for_update).
GITHUB_REPO = "PokerForge/pokerforge"

# Fallback: where Help > Check for Updates looks for {"version": "...",
# "url": "...", "notes": "..."} — a static JSON file, not an API. Only
# used if GITHUB_REPO above isn't set. Leaving both unset means the check
# reports itself as "not set up" instead of failing against a fake URL.
UPDATE_MANIFEST_URL = None

# Help > Report a Bug's mailto: recipient.
SUPPORT_EMAIL = "pokerforge@outlook.com"
