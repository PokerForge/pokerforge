"""Enter/replace a licence key (File > Enter License Key...).

Licences are signed tokens rather than short codes, so they're long and
meant to be pasted from the email they arrived in — hence the wide field
and the wording below. Validation here is a real signature check
(core/licensing.py), so anything mistyped or made up is refused before
it can be saved."""
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLineEdit, QDialogButtonBox

from ui.theme import STYLE, lbl
from core.licensing import validate_license_key


class LicenseDialog(QDialog):
    def __init__(self, current_key: str | None = None, parent=None):
        super().__init__(parent)
        self.setStyleSheet(STYLE)
        self.setWindowTitle("Enter License Key")
        self.resize(560, 180)
        self.setModal(True)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(10)

        lay.addWidget(lbl("Paste the licence key from your email:", size=13))

        self._input = QLineEdit(current_key or "")
        self._input.setPlaceholderText("PF1....")
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
            self._error_label.setText("That licence key isn't valid — check the whole line was copied.")
            return
        self._key = key
        self.accept()

    def entered_key(self) -> str | None:
        return getattr(self, "_key", None)
