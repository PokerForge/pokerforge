"""config/profiles.py — the registry every profile-aware path decision
(config/paths.py's profile_data_dir()) reads from, so a bug here would
silently point settings/database reads at the wrong profile's data."""
import pytest

import config.profiles as profiles


@pytest.fixture(autouse=True)
def _isolated_registry(tmp_path, monkeypatch):
    monkeypatch.setattr(profiles, "REGISTRY_PATH", tmp_path / "profiles.json")


def test_fresh_install_has_only_the_default_profile():
    assert profiles.list_profiles() == [("default", "Default")]
    assert profiles.get_active_profile_id() == "default"
    assert profiles.get_active_display_name() == "Default"


def test_create_profile_does_not_switch_to_it():
    profiles.create_profile("Alt Account")
    assert profiles.get_active_profile_id() == "default"
    ids = [pid for pid, _ in profiles.list_profiles()]
    assert "default" in ids and "alt_account" in ids


def test_switch_to_a_created_profile():
    pid = profiles.create_profile("Alt Account")
    profiles.set_active_profile(pid)
    assert profiles.get_active_profile_id() == pid
    assert profiles.get_active_display_name() == "Alt Account"


def test_switching_to_unknown_profile_raises():
    with pytest.raises(ValueError):
        profiles.set_active_profile("does_not_exist")


def test_duplicate_display_names_get_distinct_ids():
    first = profiles.create_profile("Shane")
    second = profiles.create_profile("Shane")
    assert first != second
    ids = {pid for pid, _ in profiles.list_profiles()}
    assert first in ids and second in ids


def test_slugify_handles_names_with_no_alnum_characters():
    # A display name that's entirely punctuation must still yield a
    # non-empty, usable folder-safe id rather than an empty string.
    pid = profiles.create_profile("!!!")
    assert pid and pid != ""
    assert all(c.isalnum() or c == "_" for c in pid)


def test_delete_profile_falls_back_active_to_default_if_it_was_active():
    pid = profiles.create_profile("Temp")
    profiles.set_active_profile(pid)
    profiles.delete_profile(pid)
    assert profiles.get_active_profile_id() == "default"
    assert pid not in [p for p, _ in profiles.list_profiles()]


def test_delete_profile_leaves_active_alone_if_a_different_profile_was_deleted():
    a = profiles.create_profile("A")
    profiles.create_profile("B")
    profiles.set_active_profile(a)
    b_id = [pid for pid, name in profiles.list_profiles() if name == "B"][0]
    profiles.delete_profile(b_id)
    assert profiles.get_active_profile_id() == a


def test_cannot_delete_the_default_profile():
    with pytest.raises(ValueError):
        profiles.delete_profile("default")


def test_registry_persists_across_reloads(tmp_path, monkeypatch):
    monkeypatch.setattr(profiles, "REGISTRY_PATH", tmp_path / "profiles.json")
    pid = profiles.create_profile("Persisted")
    profiles.set_active_profile(pid)
    # Simulate a fresh process re-reading the same file from disk.
    assert profiles.get_active_profile_id() == pid
    assert ("Persisted" in name for _, name in profiles.list_profiles())


def test_corrupt_registry_file_falls_back_to_default(tmp_path, monkeypatch):
    path = tmp_path / "profiles.json"
    path.write_text("{ not valid json", encoding="utf-8")
    monkeypatch.setattr(profiles, "REGISTRY_PATH", path)
    assert profiles.get_active_profile_id() == "default"
    assert profiles.list_profiles() == [("default", "Default")]
