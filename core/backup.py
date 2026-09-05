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


_AUTO_BACKUP_DIR_NAME = "auto_backups"
_AUTO_BACKUPS_TO_KEEP = 3


def create_auto_backup_if_due(db_conn: sqlite3.Connection, profile_dir: Path, today: str,
                               last_auto_backup_date: str | None) -> str | None:
    """A silent, automatic safety net — separate from Tools > Backup My
    Data, which nobody remembers to click until after they've already
    lost something. Takes at most one snapshot per calendar day (checked
    by the caller comparing `today` against the last date this returned),
    so it's a real safeguard against a parsing bug silently corrupting
    months of stats without adding meaningful overhead to every import —
    especially the live folder watcher's frequent small imports, which
    would otherwise re-snapshot the whole database every few seconds
    during a session.

    Keeps only the last _AUTO_BACKUPS_TO_KEEP snapshots (oldest deleted
    first) so this can't grow the data folder unbounded. Returns the new
    `today` string to persist as last_auto_backup_date, or None if a
    backup wasn't due (caller should keep whatever it already had)."""
    if last_auto_backup_date == today:
        return None

    auto_dir = profile_dir / _AUTO_BACKUP_DIR_NAME
    auto_dir.mkdir(parents=True, exist_ok=True)
    dest = auto_dir / f"auto_backup_{today}.zip"
    create_backup(db_conn, profile_dir, dest)

    existing = sorted(auto_dir.glob("auto_backup_*.zip"))
    for stale in existing[:-_AUTO_BACKUPS_TO_KEEP]:
        stale.unlink(missing_ok=True)

    return today


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
