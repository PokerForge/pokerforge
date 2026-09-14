"""Global Cash/Tournament switch for the filter bar — a segmented "$ / T"
pill (matching PT4/Hold'em Manager's own game-type switch) rather than a
separate Tournaments tab: clicking it changes what Overview/Sessions/
Stats/Population show, not which tab you're on."""
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QButtonGroup

from ui.theme import BG3, BORDER, TEXT, GREEN

_LABELS = {'cash': '$', 'tournament': 'T'}


class GameTypeToggle(QWidget):
    changed = pyqtSignal(str)  # 'cash' or 'tournament'

    def __init__(self, parent=None):
        super().__init__(parent)
        self._value = 'cash'

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons: dict[str, QPushButton] = {}
        for i, (value, label) in enumerate(_LABELS.items()):
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setChecked(value == self._value)
            btn.setFixedSize(28, 24)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip("Cash games" if value == 'cash' else "Tournaments")
            # One shared border, squared-off where the two buttons meet, so
            # they read as a single pill rather than two separate buttons.
            left_radius, right_radius = (4, 0) if i == 0 else (0, 4)
            border_sides = "border-right: none;" if i == 0 else ""
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {BG3}; color: {TEXT}; border: 1px solid {BORDER};
                    {border_sides}
                    border-top-left-radius: {left_radius}px; border-bottom-left-radius: {left_radius}px;
                    border-top-right-radius: {right_radius}px; border-bottom-right-radius: {right_radius}px;
                    font-size: 12px; font-weight: 700; padding: 0px;
                }}
                QPushButton:checked {{ background: {GREEN}; color: #0d1117; }}
                QPushButton:hover:!checked {{ border-color: {GREEN}; }}
            """)
            btn.clicked.connect(lambda _checked, v=value: self._on_clicked(v))
            self._group.addButton(btn)
            self._buttons[value] = btn
            lay.addWidget(btn)

    def _on_clicked(self, value: str):
        if value == self._value:
            return
        self._value = value
        self.changed.emit(value)

    def value(self) -> str:
        return self._value

    def set_value(self, value: str):
        if value not in self._buttons or value == self._value:
            return
        self._value = value
        self._buttons[value].setChecked(True)
