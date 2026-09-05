"""Parses CHANGELOG.md's per-version sections for the "What's new" popup
(ui/whats_new_dialog.py) — one real source of truth instead of a second,
easily-forgotten copy of the release notes baked into the app itself."""
import re

from config.paths import resource_dir

CHANGELOG_PATH = resource_dir() / "CHANGELOG.md"

# Matches a "## [1.2.3] — ..." heading and captures everything up to the
# next such heading (or end of file) as that version's body.
_ENTRY_RE = re.compile(r"^## \[([^\]]+)\][^\n]*\n(.*?)(?=^## \[|\Z)", re.MULTILINE | re.DOTALL)


def get_changelog_entry(version: str) -> str | None:
    """The markdown body for `version`'s own "## [version]" section, or
    None if CHANGELOG.md is missing or has no section for that version."""
    if not CHANGELOG_PATH.exists():
        return None
    text = CHANGELOG_PATH.read_text(encoding="utf-8")
    for match_version, body in _ENTRY_RE.findall(text):
        if match_version == version:
            return body.strip()
    return None
