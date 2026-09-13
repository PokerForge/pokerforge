"""ui/main_window.py's _ClickableFrame — a real production crash
(RuntimeError: wrapped C/C++ object of type _ClickableFrame has been
deleted) happened when a click was already queued for a villain-profile
stat card at the exact moment a refresh tore it down and rebuilt it —
made far more likely once the live folder watcher (ui/live_watcher.py)
started triggering that same rebuild automatically every few seconds
during play, not just on a rare manual period change. mousePressEvent
must swallow that RuntimeError rather than crash the whole app."""
import pytest
from PyQt6 import sip

from ui.main_window import _ClickableFrame


@pytest.fixture()
def qapp():
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _left_click_event():
    from PyQt6.QtCore import QPointF
    from PyQt6.QtGui import QMouseEvent
    from PyQt6.QtCore import Qt
    return QMouseEvent(
        QMouseEvent.Type.MouseButtonPress, QPointF(1, 1), Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)


def test_normal_click_still_emits_signal(qapp):
    frame = _ClickableFrame()
    calls = []
    frame.clicked.connect(lambda: calls.append(True))
    frame.mousePressEvent(_left_click_event())
    assert calls == [True]


def test_click_on_a_deleted_frame_does_not_raise(qapp):
    frame = _ClickableFrame()
    calls = []
    frame.clicked.connect(lambda: calls.append(True))
    event = _left_click_event()

    sip.delete(frame)
    assert sip.isdeleted(frame)

    # Must not raise — this is exactly the production crash: a click
    # queued for a frame whose C++ object is now gone.
    frame.mousePressEvent(event)
