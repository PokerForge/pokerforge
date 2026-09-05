"""Backup/restore (core/backup.py) and multi-profile support
(config/profiles.py, config/paths.py) are each well-tested on their own,
but never together. Restoring a backup into a DIFFERENT profile than it
came from is a real thing a user can do (Tools > Restore from Backup
doesn't check which profile a zip originated from) — this must fully
replace the target profile's data, not merge it, and must never touch
the source profile's own files."""
import sqlite3

import pytest

import config.paths as paths_mod
import config.profiles as profiles_mod
from core.backup import create_backup, restore_backup


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    appdata_dir = tmp_path / "appdata"
    appdata_dir.mkdir()

    def fake_app_data_dir():
        appdata_dir.mkdir(parents=True, exist_ok=True)
        return appdata_dir

    monkeypatch.setattr(paths_mod, "app_data_dir", fake_app_data_dir)
    monkeypatch.setattr(profiles_mod, "REGISTRY_PATH", appdata_dir / "profiles.json")


def _seed_profile(profile_dir, hero_name, hand_id, profit):
    profile_dir.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(profile_dir / "sf_poker.db")
    conn.execute("CREATE TABLE hands (hand_id TEXT PRIMARY KEY, profit REAL)")
    conn.execute("INSERT INTO hands VALUES (?, ?)", (hand_id, profit))
    conn.commit()
    (profile_dir / "settings.json").write_text(
        f'{{"hero_name": "{hero_name}"}}', encoding="utf-8")
    return conn


def test_restoring_into_a_different_profile_fully_replaces_its_data(tmp_path):
    alt_id = profiles_mod.create_profile("Alt Account")

    default_dir = paths_mod.profile_data_dir(profiles_mod.DEFAULT_PROFILE_ID)
    alt_dir = paths_mod.profile_data_dir(alt_id)

    default_conn = _seed_profile(default_dir, "HeroA", "h_from_default", 100.0)
    backup_zip = tmp_path / "default_backup.zip"
    create_backup(default_conn, default_dir, backup_zip)
    default_conn.close()

    alt_conn = _seed_profile(alt_dir, "HeroB", "h_from_alt", -50.0)
    alt_conn.close()

    # Restore the DEFAULT profile's backup into the ALT profile's folder —
    # the scenario the caller (ui/app_window.py's restore flow) must
    # guard against confusing the user about, since nothing here stops it
    # mechanically.
    restore_backup(backup_zip, alt_dir)

    restored_conn = sqlite3.connect(alt_dir / "sf_poker.db")
    rows = restored_conn.execute("SELECT hand_id, profit FROM hands").fetchall()
    restored_conn.close()
    assert rows == [("h_from_default", 100.0)]
    assert "h_from_alt" not in [r[0] for r in rows]
    assert '"HeroA"' in (alt_dir / "settings.json").read_text(encoding="utf-8")

    # The source (default) profile's own data must be completely untouched.
    source_conn = sqlite3.connect(default_dir / "sf_poker.db")
    source_rows = source_conn.execute("SELECT hand_id, profit FROM hands").fetchall()
    source_conn.close()
    assert source_rows == [("h_from_default", 100.0)]
    assert '"HeroA"' in (default_dir / "settings.json").read_text(encoding="utf-8")


def test_alt_profile_data_dir_is_separate_from_default(tmp_path):
    alt_id = profiles_mod.create_profile("Alt Account")
    default_dir = paths_mod.profile_data_dir(profiles_mod.DEFAULT_PROFILE_ID)
    alt_dir = paths_mod.profile_data_dir(alt_id)
    assert default_dir != alt_dir
    assert alt_dir.is_relative_to(paths_mod.app_data_dir())
