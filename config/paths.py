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


def resource_dir() -> Path:
    """Base directory for bundled, read-only resources (assets/) — the
    source tree's project root when running from source, or PyInstaller's
    extraction/install directory when frozen (sys._MEIPASS for --onefile,
    the executable's own folder for --onedir). Plain __file__-relative
    paths only resolve correctly in the former case."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    return Path(__file__).resolve().parent.parent
