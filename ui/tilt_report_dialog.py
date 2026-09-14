"""Sessions tab > Tilt Report — whether hero's own VPIP shifts in the
window right after a big loss, vs. their normal baseline. On-demand like
PoolInsightsDialog: needs the full per-hand VPIP sequence for the period,
not the precomputed aggregates the rest of the tab runs on."""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QProgressBar

from ui.theme import STYLE, BG3, DIM, TEXT, GREEN, ORANGE, lbl
from ui.async_worker import AsyncRunner
from database.queries import hero_vpip_sequence_query
from core.tilt_correlation import compute_post_loss_vpip_shift, BIG_LOSS_BB, WINDOW_MINUTES

MIN_SAMPLE = 20


class TiltReportDialog(QDialog, AsyncRunner):
    def __init__(self, db, hero, d_from, d_to, stake=None, site=None, parent=None):
        super().__init__(parent)
        self._init_async()
        self.setStyleSheet(STYLE)
        self.setWindowTitle("Tilt Report")
        self.resize(480, 320)
        self.setModal(True)

        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(20, 20, 20, 20)
        self._lay.setSpacing(10)
        self._lay.addWidget(lbl(
            f"VPIP IN THE {WINDOW_MINUTES} MINUTES AFTER A {BIG_LOSS_BB:.0f}BB+ LOSS  ·  vs. your normal baseline",
            size=11, dim=True))

        self._status = lbl("Loading hand sequence...", dim=True)
        self._lay.addWidget(self._status)
        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._lay.addWidget(self._progress)

        self.run_async(
            lambda: self._compute(db, hero, d_from, d_to, stake, site),
            self._render,
            on_error=self._on_error,
        )

    def _compute(self, db, hero, d_from, d_to, stake, site):
        rows = hero_vpip_sequence_query(db, hero, d_from, d_to, stake, site)
        return compute_post_loss_vpip_shift(rows)

    def _on_error(self, msg):
        self._status.setText(f"Couldn't build this report: {msg}")
        self._progress.hide()

    def _render(self, result):
        self._status.hide()
        self._progress.hide()

        if result["post_loss_sample"] < MIN_SAMPLE or result["baseline_sample"] < MIN_SAMPLE:
            self._lay.addWidget(lbl(
                "Not enough hands after a big loss in this period to build this report yet "
                f"(need at least {MIN_SAMPLE} in each bucket).", dim=True))
            self._lay.addStretch()
            return

        baseline = result["baseline_rate"]
        post_loss = result["post_loss_rate"]
        shift = post_loss - baseline
        shifted = abs(shift) >= 3.0
        shift_color = ORANGE if (shifted and shift > 0) else (GREEN if shifted else DIM)

        row = QLabel()
        row.setStyleSheet(f"background:{BG3};border-radius:6px;")
        row.setTextFormat(Qt.TextFormat.RichText)
        row.setText(
            f"<div style='padding:14px;'>"
            f"<span style='font-size:12px;color:{DIM};'>NORMAL VPIP</span><br>"
            f"<span style='font-size:20px;font-weight:700;color:{TEXT};'>{baseline:.1f}%</span>"
            f"<span style='font-size:12px;color:{DIM};'> &middot; {result['baseline_sample']:,} hands</span>"
            f"<br><br>"
            f"<span style='font-size:12px;color:{DIM};'>VPIP AFTER A BIG LOSS</span><br>"
            f"<span style='font-size:20px;font-weight:700;color:{shift_color};'>{post_loss:.1f}%</span>"
            f"<span style='font-size:12px;color:{DIM};'> &middot; {result['post_loss_sample']:,} hands</span>"
            f"</div>")
        self._lay.addWidget(row)

        if shifted and shift > 0:
            note = (f"You play {shift:+.1f} points looser in the {WINDOW_MINUTES} minutes after dropping "
                    f"{BIG_LOSS_BB:.0f}bb+ in a hand — a pattern worth watching for.")
        elif shifted:
            note = (f"You play {shift:+.1f} points tighter in the {WINDOW_MINUTES} minutes after dropping "
                    f"{BIG_LOSS_BB:.0f}bb+ in a hand.")
        else:
            note = "No meaningful shift detected — your VPIP holds steady after a big loss."
        self._lay.addWidget(lbl(note, dim=True, size=11))
        self._lay.addStretch()
