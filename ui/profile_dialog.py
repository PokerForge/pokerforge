"""Switch/create profiles — see config/profiles.py for why switching
takes effect on restart rather than live, and how the default profile's
data location is left untouched for every pre-multi-profile install."""
import sys
import subprocess

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem, QPushButton,
    QInputDialog, QMessageBox, QDialogButtonBox,
)

from ui.theme import STYLE, lbl
from config.profiles import list_profiles, get_active_profile_id, set_active_profile, create_profile


class ProfileDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(STYLE)
        self.setWindowTitle("Switch Profile")
        self.resize(420, 320)
        self.setModal(True)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(12)

        lay.addWidget(lbl(
            "Each profile keeps its own hand histories, hero identity, and "
            "settings — useful for a shared computer, or tracking two "
            "separate accounts as separate identities.", dim=True))

        self.list = QListWidget()
        self._reload_list()
        lay.addWidget(self.list, 1)

        new_btn = QPushButton("New Profile...")
        new_btn.clicked.connect(self._on_new_profile)
        lay.addWidget(new_btn)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        switch_btn = buttons.addButton("Switch To Selected", QDialogButtonBox.ButtonRole.AcceptRole)
        switch_btn.clicked.connect(self._on_switch)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def _reload_list(self):
        self.list.clear()
        active = get_active_profile_id()
        for profile_id, display_name in list_profiles():
            label = f"{display_name}  (active)" if profile_id == active else display_name
            item = QListWidgetItem(label)
            item.setData(1000, profile_id)
            self.list.addItem(item)
            if profile_id == active:
                self.list.setCurrentItem(item)

    def _on_new_profile(self):
        name, ok = QInputDialog.getText(self, "New Profile", "Profile name:")
        if not ok or not name.strip():
            return
        create_profile(name.strip())
        self._reload_list()

    def _on_switch(self):
        item = self.list.currentItem()
        if not item:
            return
        profile_id = item.data(1000)
        if profile_id == get_active_profile_id():
            self.reject()
            return
        set_active_profile(profile_id)
        choice = QMessageBox.question(
            self, "Restart Required",
            "SF Poker needs to restart to switch profiles. Restart now?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        self.accept()
        if choice == QMessageBox.StandardButton.Yes:
            restart_app()


def restart_app():
    """Relaunches the current executable (frozen .exe or `python main.py`,
    sys.executable/sys.argv cover both correctly) and exits this process —
    the freshly-started one re-reads config/profiles.py's registry, which
    is exactly how the newly-switched profile takes effect."""
    subprocess.Popen([sys.executable] + sys.argv)
    sys.exit(0)
