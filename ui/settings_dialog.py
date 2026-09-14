"""File > Settings — lets the hero name/currency be corrected after
first run, since HeroSetupDialog only ever runs once (on first launch)
and there was previously no way back into those two values short of
hand-editing settings.json. Changing hero identity affects every query
in the app (they all filter WHERE player_name = hero), so — like
switching profiles — this takes effect on restart rather than live."""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, QComboBox, QCheckBox, QDialogButtonBox, QMessageBox,
    QListWidget, QPushButton,
)

from ui.theme import STYLE, lbl
from ui.profile_dialog import restart_app
from config.settings import (
    get_hero_name, set_hero_name, get_currency_symbol, set_currency_symbol,
    get_live_auto_refresh_enabled, set_live_auto_refresh_enabled,
    get_hero_aliases, set_hero_aliases,
    get_rakeback_pct, set_rakeback_pct,
)

_COMMON_CURRENCIES = ["£", "$", "€"]


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(STYLE)
        self.setWindowTitle("Settings")
        self.resize(420, 420)
        self.setModal(True)

        current_hero = get_hero_name() or ""
        current_currency = get_currency_symbol() or "£"

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(12)

        lay.addWidget(lbl(
            "Changing either of these restarts PokerForge — hero identity and "
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

        self._original_aliases = sorted(get_hero_aliases())
        self._aliases = list(self._original_aliases)
        lay.addWidget(lbl(
            "Aliases — other usernames that are also you (e.g. a second account, or a "
            "site like GGPoker that always labels your own hands \"Hero\"). Adding or "
            "removing one here only affects hands imported from now on; it won't relabel "
            "hands you've already imported.", dim=True))
        self.alias_list = QListWidget()
        self.alias_list.addItems(self._aliases)
        self.alias_list.setFixedHeight(90)
        lay.addWidget(self.alias_list)

        alias_add_row = QHBoxLayout()
        self.alias_edit = QLineEdit()
        self.alias_edit.setPlaceholderText("Another username...")
        self.alias_edit.returnPressed.connect(self._on_add_alias)
        alias_add_row.addWidget(self.alias_edit, 1)
        add_alias_btn = QPushButton("Add")
        add_alias_btn.clicked.connect(self._on_add_alias)
        alias_add_row.addWidget(add_alias_btn)
        remove_alias_btn = QPushButton("Remove Selected")
        remove_alias_btn.clicked.connect(self._on_remove_alias)
        alias_add_row.addWidget(remove_alias_btn)
        lay.addLayout(alias_add_row)

        self._original_rakeback_pct = get_rakeback_pct()
        rakeback_row = QHBoxLayout()
        rakeback_row.addWidget(lbl("Rakeback %", dim=True))
        self.rakeback_edit = QLineEdit(
            "" if self._original_rakeback_pct is None else str(self._original_rakeback_pct))
        self.rakeback_edit.setPlaceholderText("e.g. 30")
        self.rakeback_edit.setToolTip(
            "Your rakeback deal, if you have one — the Overview tab's Rakeback\n"
            "card applies this to the total rake in whatever hands the current\n"
            "Period/Stakes/Site filter matches. Leave blank if not applicable.")
        rakeback_row.addWidget(self.rakeback_edit, 1)
        lay.addLayout(rakeback_row)

        self._original_auto_refresh = get_live_auto_refresh_enabled()
        self.auto_refresh_cb = QCheckBox("Automatically check for new hands while the app is open")
        self.auto_refresh_cb.setChecked(self._original_auto_refresh)
        self.auto_refresh_cb.setToolTip(
            "Watches your hand-history folders and imports new hands as they\n"
            "appear, instead of only at startup or when you click Refresh.\n"
            "Takes effect immediately — no restart needed.")
        lay.addWidget(self.auto_refresh_cb)

        lay.addStretch()
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

        self._original_hero = current_hero
        self._original_currency = current_currency

    def _on_add_alias(self):
        name = self.alias_edit.text().strip()
        if not name:
            return
        if name == self.hero_edit.text().strip():
            QMessageBox.warning(self, "Settings", "That's already your username, not an alias for it.")
            return
        if name in self._aliases:
            self.alias_edit.clear()
            return
        self._aliases.append(name)
        self._aliases.sort()
        self.alias_list.clear()
        self.alias_list.addItems(self._aliases)
        self.alias_edit.clear()

    def _on_remove_alias(self):
        for item in self.alias_list.selectedItems():
            name = item.text()
            if name in self._aliases:
                self._aliases.remove(name)
        self.alias_list.clear()
        self.alias_list.addItems(self._aliases)

    def _on_save(self):
        new_hero = self.hero_edit.text().strip()
        new_currency = self.currency_cb.currentText().strip()
        new_auto_refresh = self.auto_refresh_cb.isChecked()
        if not new_hero:
            QMessageBox.warning(self, "Settings", "Username can't be empty.")
            return

        rakeback_text = self.rakeback_edit.text().strip()
        if not rakeback_text:
            new_rakeback_pct = None
        else:
            try:
                new_rakeback_pct = float(rakeback_text)
            except ValueError:
                QMessageBox.warning(self, "Settings", "Rakeback % must be a number, e.g. 30.")
                return
            if not (0 <= new_rakeback_pct <= 100):
                QMessageBox.warning(self, "Settings", "Rakeback % must be between 0 and 100.")
                return

        identity_changed = new_hero != self._original_hero or new_currency != self._original_currency
        auto_refresh_changed = new_auto_refresh != self._original_auto_refresh
        aliases_changed = sorted(self._aliases) != self._original_aliases
        rakeback_changed = new_rakeback_pct != self._original_rakeback_pct
        if not identity_changed and not auto_refresh_changed and not aliases_changed and not rakeback_changed:
            self.reject()
            return

        if auto_refresh_changed:
            set_live_auto_refresh_enabled(new_auto_refresh)
        if aliases_changed:
            set_hero_aliases(self._aliases)
        if rakeback_changed:
            set_rakeback_pct(new_rakeback_pct)

        if not identity_changed:
            self.accept()
            return

        set_hero_name(new_hero)
        set_currency_symbol(new_currency)
        self.accept()

        QMessageBox.information(
            self, "Settings",
            "PokerForge needs to restart to apply this change.")
        restart_app()
