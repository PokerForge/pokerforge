"""Tools > Database & Diagnostics — surfaces exactly where a player's data
lives and how big it is, mostly so a support conversation can start from
"here's my log file" instead of "where do I even look.\""""
import os
import subprocess
import sys

from PyQt6.QtWidgets import QDialog, QVBoxLayout, QPushButton, QDialogButtonBox

from ui.theme import STYLE, lbl
from config.paths import profile_data_dir
from core.logging_setup import LOG_PATH


class DiagnosticsDialog(QDialog):
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.setStyleSheet(STYLE)
        self.setWindowTitle("Database & Diagnostics")
        self.resize(520, 260)
        self.setModal(True)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(10)

        data_dir = profile_data_dir()
        db_path = data_dir / "sf_poker.db"
        db_size_mb = db_path.stat().st_size / (1024 * 1024) if db_path.exists() else 0.0

        lay.addWidget(lbl(f"Hands in database: {db.hand_count():,}", size=14, bold=True))
        lay.addWidget(lbl(f"Database size: {db_size_mb:,.1f} MB", size=12, dim=True))
        lay.addWidget(lbl(f"Database file:  {db_path}", size=12, dim=True))
        lay.addWidget(lbl(f"Log file:  {LOG_PATH}", size=12, dim=True))
        lay.addStretch()

        open_btn = QPushButton("Open Data Folder")
        open_btn.clicked.connect(lambda: self._open_folder(data_dir))
        lay.addWidget(open_btn)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(self.accept)
        lay.addWidget(buttons)

    def _open_folder(self, path):
        if sys.platform == "win32":
            os.startfile(str(path))
        else:
            subprocess.Popen(["xdg-open", str(path)])
