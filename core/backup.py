"""Backup/restore for the active profile's data (database + settings —
not the log file, deliberately: it's held open by a RotatingFileHandler
for the app's entire lifetime, and overwriting an open file out from
under a live handle is a Windows file-locking problem for no real
benefit, since old log lines aren't "data" anyone is restoring for).

The database is captured via SQLite's own backup API (Connection.backup())
rather than a raw file copy — that produces a consistent snapshot safe to
take even while the app has the database open mid-session, unlike copying
the file directly which could catch it mid-write."""
import shutil
import sqlite3
import tempfile
import zipfile
from pathlib import Path

_DB_NAME = "sf_poker.db"
_SETTINGS_NAME = "settings.json"


def create_backup(db_conn: sqlite3.Connection, profile_dir: Path, dest_zip_path: Path):
    with tempfile.TemporaryDirectory() as tmp:
        tmp_db = Path(tmp) / _DB_NAME
        backup_conn = sqlite3.connect(tmp_db)
        try:
            db_conn.backup(backup_conn)
        finally:
            backup_conn.close()

        with zipfile.ZipFile(dest_zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(tmp_db, arcname=_DB_NAME)
            settings_path = profile_dir / _SETTINGS_NAME
            if settings_path.exists():
                zf.write(settings_path, arcname=_SETTINGS_NAME)


def restore_backup(zip_path: Path, profile_dir: Path):
    """Extracts sf_poker.db and settings.json from a backup zip over
    `profile_dir`. The caller MUST ensure the database connection for this
    profile is already closed before calling this — overwriting an open
    SQLite file out from under a live connection can corrupt it. The app
    should be restarted immediately after this returns, not have its
    existing (now-stale) database re-used in place."""
    with zipfile.ZipFile(zip_path, "r") as zf:
        names = zf.namelist()
        if _DB_NAME not in names:
            raise ValueError("This doesn't look like a PokerForge backup — no sf_poker.db inside.")
        zf.extract(_DB_NAME, profile_dir)
        if _SETTINGS_NAME in names:
            zf.extract(_SETTINGS_NAME, profile_dir)
