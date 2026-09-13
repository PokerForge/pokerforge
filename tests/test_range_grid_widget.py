"""ui/range_grid.py's _CellLabel — shares the exact same "click queued
for a widget the C++ side already deleted" crash pattern fixed in
ui/main_window.py's _ClickableFrame (see
tests/test_clickable_frame_crash_guard.py for the real production
crash this guards against). Fixed proactively here since the range-grid
popup can be closed (position filter change, toggle again, cell click)
while a click on one of its 169 cells is still in flight."""
import pytest
from PyQt6 import sip
from PyQt6.QtCore import Qt, QPointF
from PyQt6.QtGui import QMouseEvent

from ui.range_grid import RangeGridWidget


@pytest.fixture()
def qapp():
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _left_click_event():
    return QMouseEvent(
        QMouseEvent.Type.MouseButtonPress, QPointF(1, 1), Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)


def test_clicking_a_populated_cell_emits_cell_clicked(qapp):
    widget = RangeGridWidget([("h1", ("A♠", "A♦"))])
    calls = []
    widget.cell_clicked.connect(lambda notation, ids: calls.append((notation, ids)))
    widget.cells["AA"].mousePressEvent(_left_click_event())
    assert calls == [("AA", ["h1"])]


def test_clicking_an_empty_cell_does_nothing(qapp):
    widget = RangeGridWidget([("h1", ("A♠", "A♦"))])
    calls = []
    widget.cell_clicked.connect(lambda notation, ids: calls.append((notation, ids)))
    widget.cells["72o"].mousePressEvent(_left_click_event())
    assert calls == []


def test_click_on_a_deleted_cell_does_not_raise(qapp):
    widget = RangeGridWidget([("h1", ("A♠", "A♦"))])
    cell = widget.cells["AA"]
    event = _left_click_event()

    sip.delete(cell)
    assert sip.isdeleted(cell)

    # Must not raise — the exact crash pattern seen in production
    # elsewhere in the app (ui/main_window.py's _ClickableFrame).
    cell.mousePressEvent(event)
