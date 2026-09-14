"""Tools > (Population tab) Pool Insights — population-wide patterns
mined across the user's WHOLE showdown history, not one villain's
profile. Currently just river bet-sizing vs revealed hand strength
(core/river_sizing.py); a real, on-demand report rather than something
recomputed on every Population tab refresh, since it needs to load full
Hand objects for every showdown hand — meaningfully heavier than the
precomputed-column queries the rest of the tab runs."""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QProgressBar

from ui.theme import STYLE, BG3, DIM, TEXT, GREEN, lbl
from ui.async_worker import AsyncRunner
from database.queries import showdown_hand_ids_query
from database.hand_loader import load_hands_bulk
from core.river_sizing import classify_river_sizing_vs_strength, SIZING_BUCKETS


class PoolInsightsDialog(QDialog, AsyncRunner):
    def __init__(self, db, hero, d_from, d_to, stake=None, site=None, parent=None):
        super().__init__(parent)
        self._init_async()
        self.setStyleSheet(STYLE)
        self.setWindowTitle("Pool Insights")
        self.resize(480, 360)
        self.setModal(True)

        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(20, 20, 20, 20)
        self._lay.setSpacing(10)
        self._lay.addWidget(lbl(
            "RIVER BET SIZE vs REVEALED HAND STRENGTH  ·  pooled across every showdown in your database",
            size=11, dim=True))

        self._status = lbl("Loading showdown hands...", dim=True)
        self._lay.addWidget(self._status)
        self._progress = QProgressBar()
        self._progress.setRange(0, 0)  # indeterminate — hand count isn't known until the query returns
        self._lay.addWidget(self._progress)

        self.run_async(
            lambda: self._compute(db, hero, d_from, d_to, stake, site),
            self._render,
            on_error=self._on_error,
        )

    def _compute(self, db, hero, d_from, d_to, stake, site):
        hand_ids = showdown_hand_ids_query(db, hero, d_from, d_to, stake, site)
        hands_by_id = load_hands_bulk(db, hand_ids)
        return classify_river_sizing_vs_strength(list(hands_by_id.values()), exclude_player=hero)

    def _on_error(self, msg):
        self._status.setText(f"Couldn't build this report: {msg}")
        self._progress.hide()

    def _render(self, result):
        self._status.hide()
        self._progress.hide()

        total_hands = sum(v["strong"] + v["weak"] for v in result.values())
        if total_hands == 0:
            self._lay.addWidget(lbl(
                "Not enough showdown hands with a river bet in this period to build this report yet.",
                dim=True))
            self._lay.addStretch()
            return

        for label, _lo, _hi in SIZING_BUCKETS:
            bucket = result[label]
            n = bucket["strong"] + bucket["weak"]
            if n == 0:
                continue
            strong_pct = round(100.0 * bucket["strong"] / n, 1)
            row = QLabel()
            row.setStyleSheet(f"background:{BG3};border-radius:6px;")
            row.setTextFormat(Qt.TextFormat.RichText)
            row.setText(
                f"<div style='padding:10px 14px;'>"
                f"<span style='font-size:13px;font-weight:600;color:{TEXT};'>{label}</span><br>"
                f"<span style='font-size:12px;color:{DIM};'>"
                f"<span style='color:{GREEN};font-weight:600;'>{strong_pct:.1f}%</span> three-of-a-kind or "
                f"better &middot; {n:,} hand(s)</span></div>")
            self._lay.addWidget(row)

        self._lay.addWidget(lbl(
            f"Drawn from {total_hands:,} showdown hand(s) with a river bet in this period — "
            "a pattern for your own player pool, not a universal claim.", dim=True, size=11))
        self._lay.addStretch()
