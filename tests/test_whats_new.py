"""core/changelog.py's per-version parsing, and config/settings.py's
last_seen_version — together these decide whether the "What's new" popup
(ui/whats_new_dialog.py) appears, so a parsing bug here would mean either
an annoying popup on every single launch or one that never shows at all."""
import pytest

import config.settings as settings_mod
import core.changelog as changelog_mod

_CHANGELOG_TEXT = """# Changelog

Some intro text, not part of any version's section.

## [1.1.0] — 2026-01-01

Highlights:

- Added a thing
- Fixed another thing

## [1.0.0] — 2025-12-01

Initial release.

- First feature
"""


@pytest.fixture(autouse=True)
def _isolated_settings(tmp_path, monkeypatch):
    monkeypatch.setattr(settings_mod, "SETTINGS_PATH", tmp_path / "settings.json")


@pytest.fixture()
def changelog_file(tmp_path, monkeypatch):
    path = tmp_path / "CHANGELOG.md"
    path.write_text(_CHANGELOG_TEXT, encoding="utf-8")
    monkeypatch.setattr(changelog_mod, "CHANGELOG_PATH", path)
    return path


def test_get_changelog_entry_returns_that_versions_body_only(changelog_file):
    body = changelog_mod.get_changelog_entry("1.1.0")
    assert "Added a thing" in body
    assert "Fixed another thing" in body
    assert "First feature" not in body  # belongs to the 1.0.0 section, not 1.1.0


def test_get_changelog_entry_finds_earlier_version_too(changelog_file):
    body = changelog_mod.get_changelog_entry("1.0.0")
    assert "First feature" in body
    assert "Added a thing" not in body


def test_get_changelog_entry_missing_version_returns_none(changelog_file):
    assert changelog_mod.get_changelog_entry("9.9.9") is None


def test_get_changelog_entry_missing_file_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(changelog_mod, "CHANGELOG_PATH", tmp_path / "does_not_exist.md")
    assert changelog_mod.get_changelog_entry("1.0.0") is None


def test_last_seen_version_defaults_to_none():
    assert settings_mod.get_last_seen_version() is None


def test_last_seen_version_roundtrips():
    settings_mod.set_last_seen_version("1.2.3")
    assert settings_mod.get_last_seen_version() == "1.2.3"


@pytest.fixture()
def qapp():
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_whats_new_dialog_renders_the_changelog_body(qapp):
    from PyQt6.QtWidgets import QTextBrowser
    from ui.whats_new_dialog import WhatsNewDialog
    dlg = WhatsNewDialog("1.1.0", "- Added a thing\n- Fixed another thing")
    assert "Added a thing" in dlg.findChild(QTextBrowser).toPlainText()
