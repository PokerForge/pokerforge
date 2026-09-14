"""ui/graph_overlay.py's DraggableStatsBox default placement — the box
sits at a fixed spot until the user drags it, which used to mean a
strong, consistent trend from hand 1 (a big upswing or downswing) ran
straight through it every time the tab rendered. suggest_stats_box_prefer_bottom
picks whichever vertical half the line ISN'T in near the start, and
set_preferred_corner applies that unless the user has already moved the
box themselves."""
import pytest

from ui.graph_overlay import DraggableStatsBox, suggest_stats_box_prefer_bottom


@pytest.fixture()
def qapp():
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_no_data_defaults_to_bottom():
    assert suggest_stats_box_prefer_bottom([]) is True


def test_flat_line_defaults_to_bottom():
    assert suggest_stats_box_prefer_bottom([10.0] * 50) is True


def test_line_starting_high_prefers_the_bottom_half():
    # Starts near the top of its own range and falls — box should move
    # out of the way, to the bottom.
    series = [200 - i for i in range(400)]
    assert suggest_stats_box_prefer_bottom(series) is True


def test_line_starting_low_prefers_the_top_half():
    # Starts near the bottom of its own range and rises — box should
    # move to the top, out of the line's path.
    series = [i * 0.5 for i in range(400)]
    assert suggest_stats_box_prefer_bottom(series) is False


@pytest.fixture()
def plot(qapp):
    from PyQt6.QtWidgets import QWidget
    w = QWidget()
    w.resize(900, 400)
    w.show()
    yield w
    w.close()


@pytest.fixture()
def box(plot):
    b = DraggableStatsBox(plot)
    b.set_row("hands", "Hands: 100")
    return b


def test_default_position_follows_preferred_corner_before_any_drag(box, plot):
    box.set_preferred_corner(prefer_bottom=False)
    top_y = box.y()
    box.set_preferred_corner(prefer_bottom=True)
    bottom_y = box.y()

    assert bottom_y > top_y


def test_repeated_calls_with_the_same_preference_are_a_no_op(box):
    box.set_preferred_corner(prefer_bottom=False)
    y1 = box.y()
    box.set_preferred_corner(prefer_bottom=False)
    assert box.y() == y1


def test_user_drag_locks_the_position_against_further_corner_suggestions(box, plot):
    from PyQt6.QtCore import QPoint
    box.move(50, 50)
    box._user_moved = True  # equivalent to what mouseMoveEvent sets on a real drag

    box.set_preferred_corner(prefer_bottom=False)

    assert box.pos() == QPoint(50, 50)
