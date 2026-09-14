"""Stats tab > Trend > Backtest Deviations — for each stat currently
plotted on the Trend tab, splits hero's own history into the check-in
periods where that stat ran meaningfully high or low vs. hero's own
average, and shows what bb100 actually looked like in those periods.
On-demand like Pool Insights / Tilt Report, since it needs bb100 pulled
into the same query alongside whatever stats are currently selected."""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QProgressBar

from ui.theme import STYLE, BG3, DIM, TEXT, GREEN, RED, lbl
from ui.async_worker import AsyncRunner
from ui.stat_registry import STAT_REGISTRY_BY_ID
from database.queries import pct_trend_query
from core.deviation_backtest import backtest_stat_deviation


def _bb100_html(bb100):
    if bb100 is None:
        return f"<span style='color:{DIM};'>—</span>"
    color = GREEN if bb100 >= 0 else RED
    return f"<span style='color:{color};font-weight:600;'>{bb100:+.1f}</span>"


class DeviationBacktestDialog(QDialog, AsyncRunner):
    def __init__(self, db, hero, d_from, d_to, stat_ids, interval_days, stake=None, site=None, parent=None):
        super().__init__(parent)
        self._init_async()
        self.setStyleSheet(STYLE)
        self.setWindowTitle("Backtest Deviations")
        self.resize(520, 400)
        self.setModal(True)

        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(20, 20, 20, 20)
        self._lay.setSpacing(10)
        self._lay.addWidget(lbl(
            "BB/100 DURING YOUR OWN HIGH/LOW PERIODS FOR EACH TREND STAT  ·  "
            "a replay of your own history, not a causal claim",
            size=11, dim=True))

        self._status = lbl("Loading trend history...", dim=True)
        self._lay.addWidget(self._status)
        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._lay.addWidget(self._progress)

        self._stat_ids = list(stat_ids)
        query_stat_ids = list(dict.fromkeys(self._stat_ids + ["bb100"]))
        self.run_async(
            lambda: pct_trend_query(db, hero, d_from, d_to, query_stat_ids, stake, site, interval_days),
            self._render,
            on_error=self._on_error,
        )

    def _on_error(self, msg):
        self._status.setText(f"Couldn't build this report: {msg}")
        self._progress.hide()

    def _render(self, trend):
        self._status.hide()
        self._progress.hide()
        bucket_starts, series, hand_counts = trend
        bb100_values = series.get("bb100", [])

        results = []
        for stat_id in self._stat_ids:
            result = backtest_stat_deviation(bucket_starts, series.get(stat_id, []), hand_counts, bb100_values)
            if not result or (result["high"] is None and result["low"] is None):
                continue
            normal_bb100 = (result["normal"] or {}).get("bb100")
            impact = 0.0
            for group in ("high", "low"):
                g = result[group]
                if g and g["bb100"] is not None and normal_bb100 is not None:
                    impact = max(impact, abs(g["bb100"] - normal_bb100) * g["hands"])
            results.append((impact, stat_id, result))

        if not results:
            self._lay.addWidget(lbl(
                "No stat in your current Trend selection has a period that deviated meaningfully "
                "from your own average with enough hands to compare.", dim=True))
            self._lay.addStretch()
            return

        results.sort(key=lambda r: r[0], reverse=True)
        for _impact, stat_id, result in results[:4]:
            self._lay.addWidget(self._build_card(stat_id, result))
        self._lay.addStretch()

    def _build_card(self, stat_id, result):
        label = STAT_REGISTRY_BY_ID.get(stat_id, {}).get("label", stat_id)
        rows_html = []
        if result["high"]:
            rows_html.append(
                f"<span style='color:{DIM};'>{label} above {result['baseline_stat']:.1f}% avg</span> "
                f"&middot; {_bb100_html(result['high']['bb100'])} bb/100 "
                f"<span style='color:{DIM};'>({result['high']['hands']:,} hands)</span>")
        if result["normal"]:
            rows_html.append(
                f"<span style='color:{DIM};'>Normal periods</span> "
                f"&middot; {_bb100_html(result['normal']['bb100'])} bb/100 "
                f"<span style='color:{DIM};'>({result['normal']['hands']:,} hands)</span>")
        if result["low"]:
            rows_html.append(
                f"<span style='color:{DIM};'>{label} below {result['baseline_stat']:.1f}% avg</span> "
                f"&middot; {_bb100_html(result['low']['bb100'])} bb/100 "
                f"<span style='color:{DIM};'>({result['low']['hands']:,} hands)</span>")

        row = QLabel()
        row.setStyleSheet(f"background:{BG3};border-radius:6px;")
        row.setTextFormat(Qt.TextFormat.RichText)
        row.setText(
            f"<div style='padding:10px 14px;font-size:12px;'>"
            f"<span style='font-size:13px;font-weight:600;color:{TEXT};'>{label}</span><br><br>"
            + "<br>".join(rows_html) + "</div>")
        return row
