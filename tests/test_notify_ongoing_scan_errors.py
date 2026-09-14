"""ui/app_window.py's _notify_ongoing_scan_errors — the Refresh
button/live folder watcher's quieter counterpart to
_prompt_first_run_scan_issues. A file that fails to parse never gets its
fingerprint marked imported, so without this it would re-report the
exact same error on every single poll or click forever; this function
is what makes it "warn once per file, not every tick." QMessageBox is
faked entirely, same approach as test_first_run_no_hands.py, since the
real class's .exec() would block waiting for a real click."""
import pytest


@pytest.fixture()
def qapp():
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


class _FakeMessageBox:
    simulate_click_index = 1  # 0 = "Report a Bug...", 1 = "OK"

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
        _FakeMessageBox.last = self

    def addButton(self, label, role):
        btn = object()
        self.buttons.append(btn)
        return btn

    def exec(self):
        self._clicked = self.buttons[_FakeMessageBox.simulate_click_index]

    def clickedButton(self):
        return self._clicked


@pytest.fixture(autouse=True)
def _fake_message_box(qapp, monkeypatch):
    import ui.app_window as mod
    _FakeMessageBox.simulate_click_index = 1
    _FakeMessageBox.last = None
    monkeypatch.setattr(mod, "QMessageBox", _FakeMessageBox)


def test_a_new_real_error_shows_a_warning_and_is_added_to_warned(monkeypatch):
    import ui.app_window as mod
    warned = set()
    errors = [("C:\\hands\\bad.xml", "unexpected end of file")]

    mod._notify_ongoing_scan_errors(errors, warned)

    box = _FakeMessageBox.last
    assert box is not None
    assert box.icon == _FakeMessageBox.Icon.Warning
    assert "bad.xml" in box.text
    assert warned == {("C:\\hands\\bad.xml", "unexpected end of file")}


def test_the_same_error_is_not_shown_a_second_time(monkeypatch):
    import ui.app_window as mod
    warned = set()
    errors = [("C:\\hands\\bad.xml", "unexpected end of file")]

    mod._notify_ongoing_scan_errors(errors, warned)
    _FakeMessageBox.last = None
    mod._notify_ongoing_scan_errors(errors, warned)

    assert _FakeMessageBox.last is None  # no second dialog


def test_a_file_failing_with_a_different_message_warns_again(monkeypatch):
    import ui.app_window as mod
    warned = {("C:\\hands\\bad.xml", "unexpected end of file")}

    mod._notify_ongoing_scan_errors([("C:\\hands\\bad.xml", "bad encoding")], warned)

    box = _FakeMessageBox.last
    assert box is not None
    assert "bad encoding" in box.text


def test_known_limitation_errors_are_absorbed_silently(monkeypatch):
    """Tournament hands (or any other documented gap) were already
    explained once at first run — repeating that forever for a file
    that's still sitting in a watched folder would just be nagging."""
    import ui.app_window as mod
    warned = set()
    errors = [("C:\\hands\\t1.txt", "Tournament hands are not supported yet (cash games only)")]

    mod._notify_ongoing_scan_errors(errors, warned)

    assert _FakeMessageBox.last is None
    assert warned == set(errors)  # still marked warned, so it stays silent


def test_no_errors_is_a_no_op(monkeypatch):
    import ui.app_window as mod
    warned = set()

    mod._notify_ongoing_scan_errors([], warned)

    assert _FakeMessageBox.last is None
    assert warned == set()


def test_report_a_bug_button_opens_the_email_with_the_failed_files(monkeypatch):
    import ui.app_window as mod
    _FakeMessageBox.simulate_click_index = 0  # "Report a Bug..."
    opened = []
    monkeypatch.setattr(mod, "_open_bug_report_email", lambda body: opened.append(body))
    warned = set()
    errors = [("C:\\hands\\bad.xml", "unexpected end of file")]

    mod._notify_ongoing_scan_errors(errors, warned)

    assert len(opened) == 1
    assert "bad.xml" in opened[0]
