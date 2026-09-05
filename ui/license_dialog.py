"""Enter/replace a license key — not wired into the menu bar yet (see
core/licensing.py's LICENSE_ENFORCED). Built now so that turning
enforcement on later is just adding one menu action that opens this,
not designing and testing a new dialog under release pressure."""
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLineEdit, QDialogButtonBox

from ui.theme import STYLE, lbl
from core.licensing import validate_license_key


class LicenseDialog(QDialog):
    def __init__(self, current_key: str | None = None, parent=None):
        super().__init__(parent)
        self.setStyleSheet(STYLE)
        self.setWindowTitle("Enter License Key")
        self.resize(420, 160)
        self.setModal(True)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(10)

        lay.addWidget(lbl("Enter your PokerForge license key:", size=13))

        self._input = QLineEdit(current_key or "")
        self._input.setPlaceholderText("PF-XXXXX-XXXXX-XXXXX-XX")
        lay.addWidget(self._input)

        self._error_label = lbl("", size=12, color="#f85149")
        lay.addWidget(self._error_label)
        lay.addStretch()

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def _on_accept(self):
        key = self._input.text().strip()
        if not validate_license_key(key):
            self._error_label.setText("That doesn't look like a valid license key.")
            return
        self._key = key
        self.accept()

    def entered_key(self) -> str | None:
        return getattr(self, "_key", None)
