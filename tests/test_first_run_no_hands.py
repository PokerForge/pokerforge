"""ui/app_window.py's _prompt_no_hands_found_at_first_run — shown when the
first-run wizard's chosen folder(s) yield zero hands, instead of silently
locking in a meaningless "Hero" placeholder identity. QMessageBox is
faked entirely (not just its static convenience methods) since the real
class's .exec() would block waiting for a real user click."""
import pytest


@pytest.fixture()
def qapp():
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


class _FakeMessageBox:
    """`simulate_click_index` selects which of the buttons added (in add
    order) exec() pretends the user clicked — 0 is always "Manage
    Folders...", 1 is always "OK", matching the real function's add order."""
    simulate_click_index = 1
    info_calls = []

    class Icon:
        Information = 1

    class ButtonRole:
        ActionRole = 1
        AcceptRole = 2

    def __init__(self, icon, title, text):
        self.title = title
        self.text = text
        self.buttons = []
        self._clicked = None

    def addButton(self, label, role):
        btn = object()
        self.buttons.append(btn)
        return btn

    def exec(self):
        self._clicked = self.buttons[_FakeMessageBox.simulate_click_index]

    def clickedButton(self):
        return self._clicked

    @staticmethod
    def information(*a, **k):
        _FakeMessageBox.info_calls.append((a, k))


@pytest.fixture(autouse=True)
def _fake_message_box(qapp, monkeypatch):
    import ui.app_window as mod
    _FakeMessageBox.simulate_click_index = 1
    _FakeMessageBox.info_calls = []
    monkeypatch.setattr(mod, "QMessageBox", _FakeMessageBox)


def test_clicking_ok_leaves_folders_untouched(monkeypatch):
    import ui.app_window as mod
    _FakeMessageBox.simulate_click_index = 1  # "OK"
    opened = []
    monkeypatch.setattr(mod, "HandHistoryDirsDialog", lambda *a, **k: opened.append(True))

    mod._prompt_no_hands_found_at_first_run(["C:\\hands"])

    assert opened == []


def test_clicking_manage_folders_opens_the_dialog(monkeypatch):
    import ui.app_window as mod
    _FakeMessageBox.simulate_click_index = 0  # "Manage Folders..."
    opened = {}

    class _FakeDirsDialog:
        def __init__(self, dirs, first_run=False):
            opened["dirs"] = dirs
            opened["first_run"] = first_run

        def exec(self):
            return True

        def selected_dirs(self):
            return ["C:\\new_hands"]

    monkeypatch.setattr(mod, "HandHistoryDirsDialog", _FakeDirsDialog)
    saved = []
    monkeypatch.setattr(mod, "set_hand_history_dirs", lambda dirs: saved.append(dirs))

    mod._prompt_no_hands_found_at_first_run(["C:\\old_hands"])

    assert opened == {"dirs": ["C:\\old_hands"], "first_run": False}
    assert saved == [["C:\\new_hands"]]
    assert len(_FakeMessageBox.info_calls) == 1  # the "saved, next launch" confirmation


def test_cancelling_the_folder_dialog_does_not_save(monkeypatch):
    import ui.app_window as mod
    _FakeMessageBox.simulate_click_index = 0  # "Manage Folders..."

    class _FakeDirsDialog:
        def __init__(self, dirs, first_run=False):
            pass

        def exec(self):
            return False

        def selected_dirs(self):
            return ["should not be used"]

    monkeypatch.setattr(mod, "HandHistoryDirsDialog", _FakeDirsDialog)
    saved = []
    monkeypatch.setattr(mod, "set_hand_history_dirs", lambda dirs: saved.append(dirs))

    mod._prompt_no_hands_found_at_first_run(["C:\\hands"])

    assert saved == []
    assert _FakeMessageBox.info_calls == []
