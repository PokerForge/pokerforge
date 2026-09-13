"""Villain hand-range heatmap — the 13x13 starting-hand grid (see
core/range_grid.py), built only from hands where this player's hole
cards were actually revealed (showdown, or a voluntary show) within
whatever hand list is currently filtered to. This is NOT their true
range — folded hands are never shown by the site, so this is a small,
biased sample skewed toward stronger holdings — and RangeGridPopup says
so explicitly rather than implying otherwise.

Clicking a non-empty cell opens every hand behind it in the replayer
(HandReplayDialog's Previous/Next Hand navigation) — see
RangeGridWidget.cell_clicked."""
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QWidget, QGridLayout, QVBoxLayout, QFrame, QLabel

from ui.theme import BG2, BG3, GREEN, DIM, BORDER, lbl
from core.range_grid import grid_layout, tally_hands, group_hand_ids_by_notation

_CELL_SIZE = 30


def _to_rgb(hex_color: str) -> tuple[int, int, int]:
    return tuple(int(hex_color[i:i + 2], 16) for i in (1, 3, 5))


def _to_hex(rgb: tuple[int, int, int]) -> str:
    return "#" + "".join(f"{c:02x}" for c in rgb)


def _blend(base_hex: str, target_hex: str, t: float) -> str:
    """Linear-interpolates two "#rrggbb" colors (t=0 -> base, t=1 ->
    target) — a simple, dependency-free heatmap intensity scale."""
    r1, g1, b1 = _to_rgb(base_hex)
    r2, g2, b2 = _to_rgb(target_hex)
    return _to_hex((
        round(r1 + (r2 - r1) * t),
        round(g1 + (g2 - g1) * t),
        round(b1 + (b2 - b1) * t),
    ))


class _CellLabel(QLabel):
    """A grid cell that can be clicked — only meaningful (and only
    actually clickable) when at least one hand landed in it."""
    clicked = pyqtSignal()

    def __init__(self, text: str, clickable: bool):
        super().__init__(text)
        self.setTextFormat(Qt.TextFormat.PlainText)
        self._clickable = clickable
        if clickable:
            self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, event):
        # Same defensive guard as ui/main_window.py's _ClickableFrame — a
        # click already queued for this cell at the moment the popup
        # closes (e.g. the position filter changed, or the underlying
        # hand list refreshed) can arrive after the underlying C++
        # QLabel is gone. Drop it instead of crashing (a real production
        # crash was seen from the same pattern elsewhere in the app).
        try:
            if self._clickable and event.button() == Qt.MouseButton.LeftButton:
                self.clicked.emit()
            super().mousePressEvent(event)
        except RuntimeError:
            pass


class RangeGridWidget(QWidget):
    """The bare 13x13 grid — a QLabel per cell rather than custom
    painting, so each cell's color/text/tooltip is just normal widget
    state (easy to inspect in tests, no paint-event bookkeeping)."""
    cell_clicked = pyqtSignal(str, list)  # (notation, [hand_id, ...])

    def __init__(self, hand_entries: list[tuple[str, tuple[str, str]]], parent=None):
        super().__init__(parent)
        hole_card_pairs = [cards for _hand_id, cards in hand_entries]
        counts = tally_hands(hole_card_pairs)
        hand_ids_by_notation = group_hand_ids_by_notation(hand_entries)
        max_count = max(counts.values(), default=0)

        grid = QGridLayout(self)
        grid.setSpacing(1)
        grid.setContentsMargins(0, 0, 0, 0)

        self.cells: dict[str, QLabel] = {}
        for row_i, row in enumerate(grid_layout()):
            for col_i, notation in enumerate(row):
                count = counts.get(notation, 0)
                cell = _CellLabel(notation, clickable=count > 0)
                cell.setFixedSize(_CELL_SIZE, _CELL_SIZE)
                cell.setAlignment(Qt.AlignmentFlag.AlignCenter)
                if count > 0:
                    intensity = 0.4 + 0.6 * (count / max_count) if max_count else 0.4
                    bg = _blend(BG3, GREEN, intensity)
                    cell.setStyleSheet(
                        f"background:{bg}; color:#05130a; font-size:9px; "
                        f"font-weight:700; border-radius:2px;")
                    plural = "hand" if count == 1 else "hands"
                    cell.setToolTip(f"{notation} — seen {count}x — click to replay {plural}")
                    hand_ids = hand_ids_by_notation[notation]
                    cell.clicked.connect(lambda n=notation, ids=hand_ids: self.cell_clicked.emit(n, ids))
                else:
                    cell.setStyleSheet(
                        f"background:{BG3}; color:{DIM}; font-size:9px; "
                        f"font-weight:400; border-radius:2px;")
                    cell.setToolTip(notation)
                grid.addWidget(cell, row_i, col_i)
                self.cells[notation] = cell


class RangeGridPopup(QFrame):
    """Toggled open/closed by the caller's button — not a Qt Popup window
    (which auto-closes on any outside click and can fight a toggle
    button's own click handling), just a plain frameless tool window the
    caller shows/hides explicitly."""
    cell_clicked = pyqtSignal(str, list)  # forwarded from RangeGridWidget

    def __init__(self, hand_entries: list[tuple[str, tuple[str, str]]],
                 shown_count: int, total_count: int, parent=None):
        super().__init__(parent, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint)
        self.setStyleSheet(f"background:{BG2}; border:1px solid {BORDER}; border-radius:8px;")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 14, 14, 14)
        lay.setSpacing(10)

        caveat = lbl(
            f"{shown_count} of {total_count} hand(s) here had visible cards — "
            "not this player's true range, just what we've actually seen. "
            "Click a cell to replay its hand(s).",
            size=11, dim=True)
        caveat.setWordWrap(True)
        caveat.setFixedWidth(_CELL_SIZE * 13)
        lay.addWidget(caveat)

        self.grid_widget = RangeGridWidget(hand_entries)
        self.grid_widget.cell_clicked.connect(self.cell_clicked.emit)
        lay.addWidget(self.grid_widget)
