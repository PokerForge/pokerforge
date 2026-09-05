"""core/backup.py — must produce a real, restorable snapshot of a LIVE
(open) SQLite connection, and must refuse to "restore" a zip that isn't
actually one of ours rather than silently extracting garbage."""
import sqlite3
import zipfile

import pytest

from core.backup import create_backup, restore_backup


def _live_db(tmp_path):
    conn = sqlite3.connect(tmp_path / "sf_poker.db")
    conn.execute("CREATE TABLE hands (hand_id TEXT PRIMARY KEY, profit REAL)")
    conn.execute("INSERT INTO hands VALUES ('h1', 12.5)")
    conn.commit()
    return conn


def test_backup_captures_a_consistent_snapshot_of_a_live_connection(tmp_path):
    profile_dir = tmp_path / "profile"
    profile_dir.mkdir()
    conn = _live_db(profile_dir)
    (profile_dir / "settings.json").write_text('{"hero_name": "Test"}', encoding="utf-8")

    dest = tmp_path / "backup.zip"
    create_backup(conn, profile_dir, dest)
    conn.close()

    assert dest.exists()
    with zipfile.ZipFile(dest) as zf:
        assert set(zf.namelist()) == {"sf_poker.db", "settings.json"}


def test_backup_without_settings_file_still_backs_up_the_database(tmp_path):
    profile_dir = tmp_path / "profile"
    profile_dir.mkdir()
    conn = _live_db(profile_dir)

    dest = tmp_path / "backup.zip"
    create_backup(conn, profile_dir, dest)
    conn.close()

    with zipfile.ZipFile(dest) as zf:
        assert zf.namelist() == ["sf_poker.db"]


def test_restore_round_trip_recovers_the_data(tmp_path):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    conn = _live_db(source_dir)
    (source_dir / "settings.json").write_text('{"hero_name": "Test"}', encoding="utf-8")

    backup_zip = tmp_path / "backup.zip"
    create_backup(conn, source_dir, backup_zip)
    conn.close()

    restore_dir = tmp_path / "restored"
    restore_dir.mkdir()
    restore_backup(backup_zip, restore_dir)

    restored_conn = sqlite3.connect(restore_dir / "sf_poker.db")
    rows = restored_conn.execute("SELECT hand_id, profit FROM hands").fetchall()
    restored_conn.close()
    assert rows == [("h1", 12.5)]
    assert (restore_dir / "settings.json").read_text(encoding="utf-8") == '{"hero_name": "Test"}'


def test_restoring_a_zip_with_no_database_raises(tmp_path):
    fake_zip = tmp_path / "not_a_backup.zip"
    with zipfile.ZipFile(fake_zip, "w") as zf:
        zf.writestr("readme.txt", "not a real backup")

    with pytest.raises(ValueError):
        restore_backup(fake_zip, tmp_path / "restored")


def test_restore_ignores_extra_unrelated_files_in_the_zip(tmp_path):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    conn = _live_db(source_dir)
    backup_zip = tmp_path / "backup.zip"
    create_backup(conn, source_dir, backup_zip)
    conn.close()

    # Simulate a zip that also happens to contain something unexpected
    # (e.g. hand-edited, or from a future version with extra files).
    with zipfile.ZipFile(backup_zip, "a") as zf:
        zf.writestr("some_future_file.txt", "unexpected")

    restore_dir = tmp_path / "restored"
    restore_dir.mkdir()
    restore_backup(backup_zip, restore_dir)
    assert (restore_dir / "sf_poker.db").exists()
    assert not (restore_dir / "some_future_file.txt").exists()
