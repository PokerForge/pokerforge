"""File > Settings — lets the hero name/currency be corrected after
first run, since HeroSetupDialog only ever runs once (on first launch)
and there was previously no way back into those two values short of
hand-editing settings.json. Changing hero identity affects every query
in the app (they all filter WHERE player_name = hero), so — like
switching profiles — this takes effect on restart rather than live."""
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, QComboBox, QDialogButtonBox, QMessageBox

from ui.theme import STYLE, lbl
from ui.profile_dialog import restart_app
from config.settings import get_hero_name, set_hero_name, get_currency_symbol, set_currency_symbol

_COMMON_CURRENCIES = ["£", "$", "€"]


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(STYLE)
        self.setWindowTitle("Settings")
        self.resize(420, 200)
        self.setModal(True)

        current_hero = get_hero_name() or ""
        current_currency = get_currency_symbol() or "£"

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(12)

        lay.addWidget(lbl(
            "Changing either of these restarts SF Poker — hero identity and "
            "currency are used throughout every query in the app.", dim=True))

        hero_row = QHBoxLayout()
        hero_row.addWidget(lbl("Your username", dim=True))
        self.hero_edit = QLineEdit(current_hero)
        hero_row.addWidget(self.hero_edit, 1)
        lay.addLayout(hero_row)

        currency_row = QHBoxLayout()
        currency_row.addWidget(lbl("Currency", dim=True))
        self.currency_cb = QComboBox()
        self.currency_cb.setEditable(True)
        self.currency_cb.addItems(_COMMON_CURRENCIES)
        if current_currency not in _COMMON_CURRENCIES:
            self.currency_cb.addItem(current_currency)
        self.currency_cb.setCurrentText(current_currency)
        currency_row.addWidget(self.currency_cb, 1)
        lay.addLayout(currency_row)

        lay.addStretch()
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

        self._original_hero = current_hero
        self._original_currency = current_currency

    def _on_save(self):
        new_hero = self.hero_edit.text().strip()
        new_currency = self.currency_cb.currentText().strip()
        if not new_hero:
            QMessageBox.warning(self, "Settings", "Username can't be empty.")
            return
        if new_hero == self._original_hero and new_currency == self._original_currency:
            self.reject()
            return

        set_hero_name(new_hero)
        set_currency_symbol(new_currency)
        self.accept()

        QMessageBox.information(
            self, "Settings",
            "SF Poker needs to restart to apply this change.")
        restart_app()
