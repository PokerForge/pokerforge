"""Per-user, per-machine app data directory — independent of wherever the
app itself is installed or unpacked to. Settings/database/log paths used
to be computed relative to the source file's own location, which breaks
for a packaged build: PyInstaller's --onefile mode extracts to a fresh
temp directory on every single launch, so anything written "next to" the
running code would look like it silently vanished between sessions. This
also avoids needing write access to the install location itself (e.g.
Program Files), which a real installer often won't grant."""
import os
import sys
from pathlib import Path


def app_data_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home()))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    d = base / "SFPoker"
    d.mkdir(parents=True, exist_ok=True)
    return d


def profile_data_dir(profile_id: str | None = None) -> Path:
    """The given profile's own data folder — settings/database live here
    (see config/profiles.py). Defaults to the currently active profile if
    none is given. The default profile's data stays exactly where
    app_data_dir() already points every existing (pre-multi-profile)
    install at, so nothing needs migrating unless a second profile is
    actually created. Deferred import to avoid a circular import with
    config.profiles (which itself imports app_data_dir from here)."""
    from config.profiles import DEFAULT_PROFILE_ID, get_active_profile_id
    if profile_id is None:
        profile_id = get_active_profile_id()
    d = app_data_dir() if profile_id == DEFAULT_PROFILE_ID else app_data_dir() / "profiles" / profile_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def resource_dir() -> Path:
    """Base directory for bundled, read-only resources (assets/) — the
    source tree's project root when running from source, or PyInstaller's
    extraction/install directory when frozen (sys._MEIPASS for --onefile,
    the executable's own folder for --onedir). Plain __file__-relative
    paths only resolve correctly in the former case."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    return Path(__file__).resolve().parent.parent
