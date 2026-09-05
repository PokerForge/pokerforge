"""Hand-history folder management — shown as a first-run setup step (no
folders configured yet) and reachable afterward via the header's gear
button, so a player can add/remove watched folders (new poker sites,
a moved export directory, etc.) without touching source code or the
settings JSON by hand."""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QPushButton,
    QFileDialog, QDialogButtonBox, QLabel,
)

from ui.theme import STYLE, lbl


class HandHistoryDirsDialog(QDialog):
    def __init__(self, current_dirs: list[str], first_run: bool = False, parent=None):
        super().__init__(parent)
        self.setStyleSheet(STYLE)
        self.setWindowTitle("Welcome to SF Poker" if first_run else "Hand History Folders")
        self.resize(560, 360)
        self.setModal(True)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(12)

        if first_run:
            lay.addWidget(lbl("Welcome to SF Poker", size=16, bold=True))
            lay.addWidget(lbl(
                "Add the folder(s) where your poker client saves hand histories "
                "(or where you export them to) — SF Poker scans these for new "
                "hands every time it starts.", dim=True))
        else:
            lay.addWidget(lbl(
                "Folders SF Poker scans for hand histories. Add or remove as needed — "
                "changes take effect the next time hands are checked.", dim=True))

        self.list = QListWidget()
        self.list.addItems(current_dirs)
        lay.addWidget(self.list, 1)

        btn_row = QHBoxLayout()
        add_btn = QPushButton("Add Folder...")
        add_btn.clicked.connect(self._add_folder)
        remove_btn = QPushButton("Remove Selected")
        remove_btn.clicked.connect(self._remove_selected)
        btn_row.addWidget(add_btn)
        btn_row.addWidget(remove_btn)
        btn_row.addStretch()
        lay.addLayout(btn_row)

        self.empty_hint = QLabel("Add at least one folder to continue.")
        self.empty_hint.setStyleSheet("color:#f85149;")
        self.empty_hint.setVisible(False)
        lay.addWidget(self.empty_hint)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        if not first_run:
            buttons.addButton(QDialogButtonBox.StandardButton.Cancel)
        ok_btn = buttons.button(QDialogButtonBox.StandardButton.Ok)
        ok_btn.setText("Get Started" if first_run else "Save")
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

        self._first_run = first_run

    def _add_folder(self):
        directory = QFileDialog.getExistingDirectory(self, "Select a hand-history folder")
        if not directory:
            return
        existing = [self.list.item(i).text() for i in range(self.list.count())]
        if directory not in existing:
            self.list.addItem(directory)
        self.empty_hint.setVisible(False)

    def _remove_selected(self):
        for item in self.list.selectedItems():
            self.list.takeItem(self.list.row(item))

    def _on_accept(self):
        if self._first_run and self.list.count() == 0:
            self.empty_hint.setVisible(True)
            return
        self.accept()

    def selected_dirs(self) -> list[str]:
        return [self.list.item(i).text() for i in range(self.list.count())]
