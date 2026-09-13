"""ui/app_window.py's _prompt_first_run_scan_issues — shown once, right
after the first-run scan, covering every outcome: real parse errors
(regardless of whether other files also succeeded), a genuinely empty
result, or a clean success (nothing shown). QMessageBox is faked
entirely (not just its static convenience methods) since the real
class's .exec() would block waiting for a real user click."""
import pytest


@pytest.fixture()
def qapp():
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


class _FakeMessageBox:
    """`simulate_click_index` selects which of the buttons added (in add
    order) exec() pretends the user clicked — 0 is always the "action"
    button ("Manage Folders..." or "Report a Bug..."), 1 is always "OK",
    matching the real function's add order."""
    simulate_click_index = 1
    info_calls = []

    class Icon:
        Information = 1
        Warning = 2

    class ButtonRole:
        ActionRole = 1
        AcceptRole = 2

    def __init__(self, icon, title, text):
        self.icon = icon
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


class _RecordingBox(_FakeMessageBox):
    """Records the last instance created, since _FakeMessageBox itself
    doesn't keep a reference to what the function under test builds."""
    def __init__(self, icon, title, text):
        super().__init__(icon, title, text)
        _FakeMessageBox.last = self


@pytest.fixture(autouse=True)
def _fake_message_box(qapp, monkeypatch):
    import ui.app_window as mod
    _FakeMessageBox.simulate_click_index = 1
    _FakeMessageBox.info_calls = []
    monkeypatch.setattr(mod, "QMessageBox", _FakeMessageBox)


def test_no_hands_no_errors_clicking_ok_leaves_folders_untouched(monkeypatch):
    import ui.app_window as mod
    _FakeMessageBox.simulate_click_index = 1  # "OK"
    opened = []
    monkeypatch.setattr(mod, "HandHistoryDirsDialog", lambda *a, **k: opened.append(True))

    mod._prompt_first_run_scan_issues(["C:\\hands"], [], [])

    assert opened == []


def test_no_hands_no_errors_clicking_manage_folders_opens_the_dialog(monkeypatch):
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

    mod._prompt_first_run_scan_issues(["C:\\old_hands"], [], [])

    assert opened == {"dirs": ["C:\\old_hands"], "first_run": False}
    assert saved == [["C:\\new_hands"]]
    assert len(_FakeMessageBox.info_calls) == 1  # the "saved, next launch" confirmation


def test_no_hands_no_errors_cancelling_the_folder_dialog_does_not_save(monkeypatch):
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

    mod._prompt_first_run_scan_issues(["C:\\hands"], [], [])

    assert saved == []
    assert _FakeMessageBox.info_calls == []


def test_no_hands_no_errors_shows_the_reassuring_message(monkeypatch):
    import ui.app_window as mod
    _FakeMessageBox.simulate_click_index = 1  # "OK"
    monkeypatch.setattr(mod, "QMessageBox", _RecordingBox)

    mod._prompt_first_run_scan_issues(["C:\\hands"], [], [])

    box = _FakeMessageBox.last
    assert box.icon == _FakeMessageBox.Icon.Information
    assert "haven't played" in box.text


def test_errors_with_no_hands_show_a_warning_not_the_reassuring_message(monkeypatch):
    import ui.app_window as mod
    _FakeMessageBox.simulate_click_index = 1  # "OK"
    monkeypatch.setattr(mod, "QMessageBox", _RecordingBox)

    errors = [("C:\\hands\\bad1.xml", "unexpected end of file"), ("C:\\hands\\bad2.xml", "bad encoding")]
    mod._prompt_first_run_scan_issues(["C:\\hands"], [], errors)

    box = _FakeMessageBox.last
    assert box.icon == _FakeMessageBox.Icon.Warning
    assert "2 file" in box.text
    assert "bad1.xml" in box.text
    assert "unexpected end of file" in box.text
    assert "haven't played" not in box.text
    assert "successfully import" not in box.text  # no hands to mention


def test_errors_alongside_successful_hands_still_warns_and_mentions_the_success(monkeypatch):
    import ui.app_window as mod
    _FakeMessageBox.simulate_click_index = 1  # "OK"
    monkeypatch.setattr(mod, "QMessageBox", _RecordingBox)

    errors = [("C:\\hands\\bad1.xml", "unexpected end of file")]
    mod._prompt_first_run_scan_issues(["C:\\hands"], ["hand1", "hand2", "hand3"], errors)

    box = _FakeMessageBox.last
    assert box.icon == _FakeMessageBox.Icon.Warning
    assert "3 hand" in box.text


def test_hands_found_with_no_errors_shows_nothing(monkeypatch):
    import ui.app_window as mod
    monkeypatch.setattr(mod, "QMessageBox", _RecordingBox)
    _FakeMessageBox.last = None

    mod._prompt_first_run_scan_issues(["C:\\hands"], ["hand1"], [])

    assert _FakeMessageBox.last is None


def test_clicking_report_a_bug_opens_the_email_with_error_details(monkeypatch):
    import ui.app_window as mod
    _FakeMessageBox.simulate_click_index = 0  # "Report a Bug..."
    emailed = []
    monkeypatch.setattr(mod, "_open_bug_report_email", lambda extra_body="": emailed.append(extra_body))

    errors = [("C:\\hands\\bad1.xml", "unexpected end of file")]
    mod._prompt_first_run_scan_issues(["C:\\hands"], [], errors)

    assert len(emailed) == 1
    assert "bad1.xml" in emailed[0]
    assert "unexpected end of file" in emailed[0]
