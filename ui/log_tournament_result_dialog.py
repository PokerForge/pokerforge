"""No hand-history export (in any supported format, including the new
Winning Network parser) contains a finish position or payout — only the
hand-by-hand action log. Real ROI/ITM%/profit tracking for tournaments
needs the player to log each tournament's actual result themselves,
after the fact; this small dialog is that entry form, opened from
ui/tournaments_tab.py's results table."""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QSpinBox, QDoubleSpinBox, QDialogButtonBox,
)

from ui.theme import STYLE, lbl


class LogTournamentResultDialog(QDialog):
    def __init__(self, tournament_id: str, buy_in: float | None, fee: float | None,
                 currency: str = "$", existing: tuple | None = None, parent=None):
        """`existing`: (finish_position, field_size, payout, currency) from
        a previously-logged result, or None if this tournament hasn't been
        logged yet — pre-fills the form for editing rather than starting
        blank."""
        super().__init__(parent)
        self.setStyleSheet(STYLE)
        self.setWindowTitle("Log Tournament Result")
        self.resize(380, 220)
        self.setModal(True)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(12)

        buyin_text = f"{currency}{buy_in:,.2f}" if buy_in is not None else "—"
        if fee:
            buyin_text += f" + {currency}{fee:,.2f} fee"
        lay.addWidget(lbl(f"Tournament #{tournament_id}  ·  Buy-in {buyin_text}", dim=True))

        finish_row = QHBoxLayout()
        finish_row.addWidget(lbl("Finish position", dim=True))
        self.finish_spin = QSpinBox()
        self.finish_spin.setRange(0, 1_000_000)
        self.finish_spin.setSpecialValueText("Unknown")
        finish_row.addWidget(self.finish_spin, 1)
        lay.addLayout(finish_row)

        field_row = QHBoxLayout()
        field_row.addWidget(lbl("Field size", dim=True))
        self.field_spin = QSpinBox()
        self.field_spin.setRange(0, 1_000_000)
        self.field_spin.setSpecialValueText("Unknown")
        field_row.addWidget(self.field_spin, 1)
        lay.addLayout(field_row)

        payout_row = QHBoxLayout()
        payout_row.addWidget(lbl("Payout", dim=True))
        self.payout_spin = QDoubleSpinBox()
        self.payout_spin.setRange(0, 10_000_000)
        self.payout_spin.setDecimals(2)
        self.payout_spin.setPrefix(currency)
        payout_row.addWidget(self.payout_spin, 1)
        lay.addLayout(payout_row)

        if existing:
            finish_position, field_size, payout, _ = existing
            self.finish_spin.setValue(finish_position or 0)
            self.field_spin.setValue(field_size or 0)
            self.payout_spin.setValue(payout or 0.0)

        lay.addStretch()
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def result_values(self) -> tuple[int | None, int | None, float]:
        """(finish_position, field_size, payout) — the first two are None
        when left at "Unknown" (0), payout defaults to 0.0 (a real,
        meaningful result: busted with no min-cash)."""
        finish = self.finish_spin.value() or None
        field = self.field_spin.value() or None
        return finish, field, self.payout_spin.value()
