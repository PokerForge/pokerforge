"""ui/live_watcher.py's LiveFolderWatcher — must find every existing
subfolder/hand-history file under the configured roots (QFileSystemWatcher
itself doesn't watch recursively), debounce rapid-fire changes into a
single signal, and fully clear out the previous watch list on every call
so re-scanning doesn't accumulate paths forever."""
import pytest
from PyQt6.QtTest import QSignalSpy

from ui.live_watcher import LiveFolderWatcher


@pytest.fixture()
def qapp():
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_watch_picks_up_existing_subfolders_and_files(qapp, tmp_path):
    root = tmp_path / "Tables"
    sub = root / "2026-01-01"
    sub.mkdir(parents=True)
    (sub / "hand1.xml").write_text("<session></session>", encoding="utf-8")
    (root / "notes.png").write_text("not a hand history file", encoding="utf-8")

    watcher = LiveFolderWatcher(debounce_ms=50)
    watcher.watch([str(root)])

    watched = watcher.watched_paths()
    assert str(root) in watched
    assert str(sub) in watched
    assert str(sub / "hand1.xml") in watched
    assert str(root / "notes.png") not in watched  # not a hand-history extension


def test_watch_ignores_nonexistent_roots(qapp, tmp_path):
    watcher = LiveFolderWatcher(debounce_ms=50)
    watcher.watch([str(tmp_path / "does_not_exist")])
    assert watcher.watched_paths() == set()


def test_watch_clears_previous_watch_list(qapp, tmp_path):
    root_a = tmp_path / "A"
    root_a.mkdir()
    root_b = tmp_path / "B"
    root_b.mkdir()

    watcher = LiveFolderWatcher(debounce_ms=50)
    watcher.watch([str(root_a)])
    assert str(root_a) in watcher.watched_paths()

    watcher.watch([str(root_b)])
    assert str(root_a) not in watcher.watched_paths()
    assert str(root_b) in watcher.watched_paths()


def test_watch_with_empty_list_stops_watching_everything(qapp, tmp_path):
    root = tmp_path / "Tables"
    root.mkdir()
    watcher = LiveFolderWatcher(debounce_ms=50)
    watcher.watch([str(root)])
    assert watcher.watched_paths() != set()

    watcher.watch([])
    assert watcher.watched_paths() == set()


def test_rapid_changes_are_debounced_into_one_signal(qapp, tmp_path):
    root = tmp_path / "Tables"
    root.mkdir()
    watcher = LiveFolderWatcher(debounce_ms=50)
    watcher.watch([str(root)])

    spy = QSignalSpy(watcher.changed)
    # Simulate several rapid filesystem events, each restarting the timer.
    for _ in range(5):
        watcher._on_change(str(root))
    assert len(spy) == 0  # debounce window hasn't elapsed yet

    assert spy.wait(500)
    assert len(spy) == 1  # only one signal despite 5 triggering events
