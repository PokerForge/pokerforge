"""Single source of truth for the app version — shown in Help > About and
worth bumping on every release once there's a real release process."""
APP_VERSION = "1.0.0"

# Where Help > Check for Updates looks for {"version": "...", "url": "...",
# "notes": "..."} — a static JSON file, not an API. None until release
# hosting is decided (see core/update_checker.py); leaving it unset means
# the check reports itself as "not set up" instead of failing against a
# fake URL. Point this at e.g. a raw file in a GitHub repo once one exists.
UPDATE_MANIFEST_URL = None

# Help > Report a Bug's mailto: recipient. None until a real support
# address is decided — left blank in the mailto: link rather than
# invented, so the user picks who to send it to themselves in the
# meantime instead of it silently going nowhere.
SUPPORT_EMAIL = None
