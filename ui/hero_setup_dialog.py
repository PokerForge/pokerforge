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

# Below this, the detected name appears in too small a fraction of hands
# to plausibly be the account owner of this actual data — a real hero's
# own export should include them in nearly every hand, so a low share
# usually means the wrong folder was picked (a shared/sample export,
# someone else's history, etc.), not a trustworthy detection.
_LOW_SHARE_WARNING_THRESHOLD = 0.5


class HeroSetupDialog(QDialog):
    def __init__(self, detected_hero: str, detected_currency: str, hero_share: float | None = None, parent=None):
        super().__init__(parent)
        self.setStyleSheet(STYLE)
        self.setWindowTitle("Confirm Your Details")
        self.resize(420, 220)
        self.setModal(True)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(12)

        lay.addWidget(lbl(
            "We detected the following from your hand histories — "
            "correct them if they're wrong.", dim=True))

        if hero_share is not None and hero_share < _LOW_SHARE_WARNING_THRESHOLD:
            warning = lbl(
                f"⚠ \"{detected_hero}\" only appears in {hero_share:.0%} of the hands found — "
                "this doesn't look like it's all your own history. Double-check the username "
                "below, and that you pointed SF Poker at the right folder.",
                size=12, color="#f85149")
            warning.setWordWrap(True)
            lay.addWidget(warning)

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
