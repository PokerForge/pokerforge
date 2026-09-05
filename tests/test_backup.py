"""core/backup.py — must produce a real, restorable snapshot of a LIVE
(open) SQLite connection, and must refuse to "restore" a zip that isn't
actually one of ours rather than silently extracting garbage."""
import sqlite3
import zipfile

import pytest

from core.backup import create_backup, restore_backup, create_auto_backup_if_due


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


def test_auto_backup_is_taken_when_none_was_taken_today(tmp_path):
    profile_dir = tmp_path / "profile"
    profile_dir.mkdir()
    conn = _live_db(profile_dir)

    result = create_auto_backup_if_due(conn, profile_dir, "2026-06-01", None)
    conn.close()

    assert result == "2026-06-01"
    auto_dir = profile_dir / "auto_backups"
    assert (auto_dir / "auto_backup_2026-06-01.zip").exists()


def test_auto_backup_is_skipped_if_already_taken_today(tmp_path):
    profile_dir = tmp_path / "profile"
    profile_dir.mkdir()
    conn = _live_db(profile_dir)

    result = create_auto_backup_if_due(conn, profile_dir, "2026-06-01", "2026-06-01")
    conn.close()

    assert result is None
    assert not (profile_dir / "auto_backups").exists()


def test_auto_backup_runs_again_on_a_new_day(tmp_path):
    profile_dir = tmp_path / "profile"
    profile_dir.mkdir()
    conn = _live_db(profile_dir)

    result = create_auto_backup_if_due(conn, profile_dir, "2026-06-02", "2026-06-01")
    conn.close()

    assert result == "2026-06-02"
    assert (profile_dir / "auto_backups" / "auto_backup_2026-06-02.zip").exists()


def test_auto_backup_keeps_only_the_last_three_snapshots(tmp_path):
    profile_dir = tmp_path / "profile"
    profile_dir.mkdir()
    conn = _live_db(profile_dir)

    dates = ["2026-06-01", "2026-06-02", "2026-06-03", "2026-06-04", "2026-06-05"]
    last_date = None
    for d in dates:
        create_auto_backup_if_due(conn, profile_dir, d, last_date)
        last_date = d
    conn.close()

    remaining = sorted(p.name for p in (profile_dir / "auto_backups").glob("*.zip"))
    assert remaining == [
        "auto_backup_2026-06-03.zip",
        "auto_backup_2026-06-04.zip",
        "auto_backup_2026-06-05.zip",
    ]


def test_auto_backup_is_a_real_restorable_snapshot(tmp_path):
    profile_dir = tmp_path / "profile"
    profile_dir.mkdir()
    conn = _live_db(profile_dir)

    create_auto_backup_if_due(conn, profile_dir, "2026-06-01", None)
    conn.close()

    restore_dir = tmp_path / "restored"
    restore_dir.mkdir()
    restore_backup(profile_dir / "auto_backups" / "auto_backup_2026-06-01.zip", restore_dir)

    restored_conn = sqlite3.connect(restore_dir / "sf_poker.db")
    rows = restored_conn.execute("SELECT hand_id, profit FROM hands").fetchall()
    restored_conn.close()
    assert rows == [("h1", 12.5)]
