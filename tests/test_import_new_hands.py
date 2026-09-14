"""ui/app_window.py's _import_new_hands — shared by the startup check, the
Refresh button, and the live folder watcher. The `dialog_threshold`
parameter must skip the modal progress dialog for a small batch (the
live watcher's typical case — 1-2 hands during play) while still showing
it for a large one (a manual Refresh/startup catching up on a real
backlog), and must import hands correctly either way."""
import pytest

import ui.app_window as mod

_GAME_XML = """<session>
<general><tablename>T1</tablename><tablesize>6</tablesize>
<smallblind>0.05</smallblind><bigblind>0.10</bigblind><gametype>Holdem NL</gametype></general>
<game gamecode="{gamecode}">
  <general>
    <startdate>2026-01-01T00:00:00</startdate>
    <players>
      <player name="Hero" seat="1" chips="10.00" bet="0.05" win="0.15" />
      <player name="Villain" seat="2" chips="9.90" bet="0.10" />
    </players>
  </general>
  <round no="0">
    <action no="1" type="1" player="Hero" sum="0.05" />
    <action no="2" type="0" player="Villain" sum="0.00" />
  </round>
</game>
</session>"""


@pytest.fixture()
def qapp():
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def db(tmp_path):
    from database.repository import PokerDatabase
    database = PokerDatabase(tmp_path / "test.db")
    yield database
    database.close()


@pytest.fixture()
def hand_dir(tmp_path, monkeypatch):
    d = tmp_path / "hands"
    d.mkdir()
    monkeypatch.setattr(mod, "get_hand_history_dirs", lambda: [str(d)])
    return d


def _write_hands(hand_dir, count):
    for i in range(count):
        (hand_dir / f"session{i}.xml").write_text(
            _GAME_XML.format(gamecode=str(i)), encoding="utf-8")


def test_small_batch_skips_the_progress_dialog(qapp, db, hand_dir, monkeypatch):
    _write_hands(hand_dir, 2)
    dialog_calls = []
    monkeypatch.setattr(mod, "QProgressDialog", lambda *a, **k: dialog_calls.append(True) or _FakeDialog())

    count, errors = mod._import_new_hands(None, db, "Hero", dialog_threshold=15)

    assert count == 2
    assert errors == []
    assert dialog_calls == []
    assert db.hand_count() == 2


def test_large_batch_still_shows_the_progress_dialog(qapp, db, hand_dir, monkeypatch):
    _write_hands(hand_dir, 20)
    dialog_calls = []
    monkeypatch.setattr(mod, "QProgressDialog", lambda *a, **k: dialog_calls.append(True) or _FakeDialog())

    count, errors = mod._import_new_hands(None, db, "Hero", dialog_threshold=15)

    assert count == 20
    assert errors == []
    assert dialog_calls == [True]
    assert db.hand_count() == 20


def test_default_threshold_always_shows_dialog_for_any_nonempty_batch(qapp, db, hand_dir, monkeypatch):
    """No caller-supplied threshold (main() and the Refresh button) must
    behave exactly as before this feature existed — dialog every time."""
    _write_hands(hand_dir, 1)
    dialog_calls = []
    monkeypatch.setattr(mod, "QProgressDialog", lambda *a, **k: dialog_calls.append(True) or _FakeDialog())

    count, errors = mod._import_new_hands(None, db, "Hero")

    assert count == 1
    assert errors == []
    assert dialog_calls == [True]


def test_no_new_hands_imports_nothing_and_skips_dialog_either_way(qapp, db, hand_dir, monkeypatch):
    dialog_calls = []
    monkeypatch.setattr(mod, "QProgressDialog", lambda *a, **k: dialog_calls.append(True) or _FakeDialog())

    count, errors = mod._import_new_hands(None, db, "Hero", dialog_threshold=15)

    assert count == 0
    assert errors == []
    assert dialog_calls == []


class _FakeDialog:
    def setWindowTitle(self, *a): pass
    def setMinimumDuration(self, *a): pass
    def setWindowModality(self, *a): pass
    def setValue(self, *a): pass
