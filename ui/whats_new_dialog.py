"""Help > (shown automatically once per new version) — a lightweight
changelog popup so a user who updates PokerForge actually notices what
changed, instead of the CHANGELOG only ever being visible to someone who
thinks to go look at the file on disk."""
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QTextBrowser, QDialogButtonBox

from ui.theme import STYLE, lbl


class WhatsNewDialog(QDialog):
    def __init__(self, version: str, changelog_body: str, parent=None):
        super().__init__(parent)
        self.setStyleSheet(STYLE)
        self.setWindowTitle("What's New in PokerForge")
        self.resize(520, 420)
        self.setModal(True)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(10)

        lay.addWidget(lbl(f"What's new in PokerForge {version}", size=16, bold=True))

        body = QTextBrowser()
        body.setOpenExternalLinks(True)
        body.setMarkdown(changelog_body)
        lay.addWidget(body)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(self.accept)
        lay.addWidget(buttons)
