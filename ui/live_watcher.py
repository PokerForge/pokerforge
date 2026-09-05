"""Watches the configured hand-history folders for changes while the app
is open, so new hands show up automatically instead of only at the next
manual Refresh or restart (see AppWindow's _on_live_files_changed()).

QFileSystemWatcher doesn't watch subdirectories recursively and won't
notice a brand new file until something is already watching its parent
directory — watch() walks each root once to explicitly add every
subdirectory and hand-history file found, and the caller re-calls
watch() after every import so newly-appeared files/folders get covered
next time too.

Debounced rather than reacting to every single event: a live poker
client writes to its hand-history file more than once per hand (often
once per street), so importing on every raw filesystem event would mean
repeatedly re-parsing a file that's still mid-write."""
from pathlib import Path

from PyQt6.QtCore import QObject, QFileSystemWatcher, QTimer, pyqtSignal

DEBOUNCE_MS = 4000
_WATCHED_SUFFIXES = ('.txt', '.xml')


class LiveFolderWatcher(QObject):
    changed = pyqtSignal()

    def __init__(self, parent=None, debounce_ms: int = DEBOUNCE_MS):
        super().__init__(parent)
        self._watcher = QFileSystemWatcher(self)
        self._watcher.directoryChanged.connect(self._on_change)
        self._watcher.fileChanged.connect(self._on_change)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(debounce_ms)
        self._timer.timeout.connect(self.changed.emit)

    def _on_change(self, _path):
        self._timer.start()  # (re)starts the debounce window on every event

    def watch(self, root_dirs: list[str]):
        """Replaces the entire watched set with `root_dirs` and everything
        found under them right now. Safe to call repeatedly — existing
        watched paths are cleared first so nothing accumulates forever.
        Passing an empty list stops watching entirely (used when the user
        turns the "auto-refresh while playing" setting off)."""
        if self._watcher.directories():
            self._watcher.removePaths(self._watcher.directories())
        if self._watcher.files():
            self._watcher.removePaths(self._watcher.files())

        dirs, files = set(), set()
        for root in root_dirs:
            root_path = Path(root)
            if not root_path.is_dir():
                continue
            dirs.add(str(root_path))
            for sub in root_path.rglob('*'):
                if sub.is_dir():
                    dirs.add(str(sub))
                elif sub.suffix.lower() in _WATCHED_SUFFIXES:
                    files.add(str(sub))

        if dirs:
            self._watcher.addPaths(sorted(dirs))
        if files:
            self._watcher.addPaths(sorted(files))

    def watched_paths(self) -> set[str]:
        """For tests/diagnostics — everything currently being watched."""
        return set(self._watcher.directories()) | set(self._watcher.files())
