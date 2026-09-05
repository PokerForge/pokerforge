"""First-run confirmation for the auto-detected hero identity and currency —
detect_hero()/dominant_currency() (ui/hero_detect.py) guess right the large
majority of the time (hero is whoever appears in the most hands), but
there's no way to correct a wrong guess without hand-editing the settings
JSON unless this exists."""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, QComboBox, QDialogButtonBox,
)

from ui.theme import STYLE, lbl

_COMMON_CURRENCIES = ["£", "$", "€"]


class HeroSetupDialog(QDialog):
    def __init__(self, detected_hero: str, detected_currency: str, parent=None):
        super().__init__(parent)
        self.setStyleSheet(STYLE)
        self.setWindowTitle("Confirm Your Details")
        self.resize(420, 200)
        self.setModal(True)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(12)

        lay.addWidget(lbl(
            "We detected the following from your hand histories — "
            "correct them if they're wrong.", dim=True))

        hero_row = QHBoxLayout()
        hero_row.addWidget(lbl("Your username", dim=True))
        self.hero_edit = QLineEdit(detected_hero)
        hero_row.addWidget(self.hero_edit, 1)
        lay.addLayout(hero_row)

        currency_row = QHBoxLayout()
        currency_row.addWidget(lbl("Currency", dim=True))
        self.currency_cb = QComboBox()
        self.currency_cb.setEditable(True)
        self.currency_cb.addItems(_COMMON_CURRENCIES)
        if detected_currency not in _COMMON_CURRENCIES:
            self.currency_cb.addItem(detected_currency)
        self.currency_cb.setCurrentText(detected_currency)
        currency_row.addWidget(self.currency_cb, 1)
        lay.addLayout(currency_row)

        lay.addStretch()
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Continue")
        buttons.accepted.connect(self.accept)
        lay.addWidget(buttons)

    def selected_hero(self) -> str:
        return self.hero_edit.text().strip()

    def selected_currency(self) -> str:
        return self.currency_cb.currentText().strip()
