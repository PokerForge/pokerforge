"""Tools > Database & Diagnostics — surfaces exactly where a player's data
lives and how big it is, mostly so a support conversation can start from
"here's my log file" instead of "where do I even look.\""""
import os
import platform
import subprocess
import sys

from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QDialogButtonBox, QApplication

from ui.theme import STYLE, lbl
from config.paths import profile_data_dir
from config.version import APP_VERSION
from core.logging_setup import LOG_PATH


class DiagnosticsDialog(QDialog):
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.setStyleSheet(STYLE)
        self.setWindowTitle("Database & Diagnostics")
        self.resize(520, 280)
        self.setModal(True)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(10)

        data_dir = profile_data_dir()
        db_path = data_dir / "sf_poker.db"
        db_size_mb = db_path.stat().st_size / (1024 * 1024) if db_path.exists() else 0.0
        hand_count = db.hand_count()

        lay.addWidget(lbl(f"Hands in database: {hand_count:,}", size=14, bold=True))
        lay.addWidget(lbl(f"Database size: {db_size_mb:,.1f} MB", size=12, dim=True))
        lay.addWidget(lbl(f"Database file:  {db_path}", size=12, dim=True))
        lay.addWidget(lbl(f"Log file:  {LOG_PATH}", size=12, dim=True))
        lay.addStretch()

        self._diagnostic_text = (
            f"PokerForge {APP_VERSION}\n"
            f"OS: {platform.platform()}\n"
            f"Hands in database: {hand_count:,}\n"
            f"Database size: {db_size_mb:,.1f} MB\n"
            f"Database file: {db_path}\n"
            f"Log file: {LOG_PATH}"
        )

        button_row = QHBoxLayout()
        open_folder_btn = QPushButton("Open Data Folder")
        open_folder_btn.clicked.connect(lambda: self._open_folder(data_dir))
        button_row.addWidget(open_folder_btn)

        open_log_btn = QPushButton("View Log File")
        open_log_btn.clicked.connect(self._open_log_file)
        open_log_btn.setEnabled(LOG_PATH.exists())
        button_row.addWidget(open_log_btn)

        copy_btn = QPushButton("Copy Diagnostic Info")
        copy_btn.clicked.connect(self._copy_diagnostic_info)
        button_row.addWidget(copy_btn)
        lay.addLayout(button_row)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(self.accept)
        lay.addWidget(buttons)

    def _open_folder(self, path):
        if sys.platform == "win32":
            os.startfile(str(path))
        else:
            subprocess.Popen(["xdg-open", str(path)])

    def _open_log_file(self):
        if sys.platform == "win32":
            os.startfile(str(LOG_PATH))
        else:
            subprocess.Popen(["xdg-open", str(LOG_PATH)])

    def _copy_diagnostic_info(self):
        QApplication.clipboard().setText(self._diagnostic_text)
