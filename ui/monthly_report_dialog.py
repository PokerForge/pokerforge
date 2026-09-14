"""Overview tab > Monthly Report — a generated summary for one calendar
month: headline stats with a delta vs the previous month, that month's
biggest leak, and (once a previous month exists to compare against) the
stat that improved the most. On-demand like Pool Insights / Tilt Report /
Backtest Deviations, since it needs its own two months' worth of
position-breakdown + population queries, not the aggregates the rest of
the tab already has loaded."""
import calendar
from datetime import date

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar, QPushButton, QFrame

from ui.theme import STYLE, BG3, DIM, TEXT, GREEN, RED, lbl
from ui.async_worker import AsyncRunner
from ui.date_utils import month_range, previous_month, next_month
from database.queries import hero_overview_query, position_breakdown_query, population_by_position_query
from core.monthly_report import build_monthly_report

_MONTH_NAMES = [calendar.month_name[m] for m in range(13)]


def _delta_html(delta: float | None, higher_is_better: bool | None = None) -> str:
    """higher_is_better=None renders a neutral (non-colored) delta — for
    stats like VPIP/PFR where "up" isn't inherently good or bad."""
    if delta is None:
        return f"<span style='color:{DIM};'>—</span>"
    if delta == 0:
        return f"<span style='color:{DIM};'>no change</span>"
    if higher_is_better is None:
        color = TEXT
    else:
        good = delta > 0 if higher_is_better else delta < 0
        color = GREEN if good else RED
    arrow = "▲" if delta > 0 else "▼"
    return f"<span style='color:{color};'>{arrow} {abs(delta):,.2f}</span>"


class MonthlyReportDialog(QDialog, AsyncRunner):
    def __init__(self, db, hero, currency="£", site=None, year=None, month=None, parent=None):
        super().__init__(parent)
        self._init_async()
        self.db = db
        self.hero = hero
        self.currency = currency
        self.site = site
        today = date.today()
        self.year = year or today.year
        self.month = month or today.month

        self.setStyleSheet(STYLE)
        self.setWindowTitle("Monthly Performance Report")
        self.resize(560, 480)
        self.setModal(True)

        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(20, 20, 20, 20)
        self._lay.setSpacing(12)

        nav_row = QHBoxLayout()
        self._prev_btn = QPushButton("◀")
        self._prev_btn.setFixedWidth(32)
        self._prev_btn.clicked.connect(self._on_prev_month)
        nav_row.addWidget(self._prev_btn)
        self._month_lbl = lbl("", size=14, bold=True)
        self._month_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        nav_row.addWidget(self._month_lbl, 1)
        self._next_btn = QPushButton("▶")
        self._next_btn.setFixedWidth(32)
        self._next_btn.clicked.connect(self._on_next_month)
        nav_row.addWidget(self._next_btn)
        self._lay.addLayout(nav_row)

        self._status = lbl("Loading...", dim=True)
        self._lay.addWidget(self._status)
        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._lay.addWidget(self._progress)

        self._body = QVBoxLayout()
        self._body.setSpacing(12)
        self._lay.addLayout(self._body)
        self._lay.addStretch()

        self._refresh()

    def _on_prev_month(self):
        self.year, self.month = previous_month(self.year, self.month)
        self._refresh()

    def _on_next_month(self):
        today = date.today()
        if (self.year, self.month) >= (today.year, today.month):
            return
        self.year, self.month = next_month(self.year, self.month)
        self._refresh()

    def _clear_body(self):
        while self._body.count():
            item = self._body.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def _refresh(self):
        today = date.today()
        self._next_btn.setEnabled((self.year, self.month) < (today.year, today.month))
        self._month_lbl.setText(f"{_MONTH_NAMES[self.month]} {self.year}")
        self._clear_body()
        self._status.setText("Loading...")
        self._status.show()
        self._progress.show()

        year, month = self.year, self.month
        self.run_async(lambda: self._compute(year, month), self._render, on_error=self._on_error)

    def _compute(self, year, month):
        d_from, d_to = month_range(year, month)
        current_overview, _ = hero_overview_query(self.db, self.hero, d_from, d_to, site=self.site)
        current_by_position = position_breakdown_query(self.db, self.hero, d_from, d_to, site=self.site)
        current_pop = population_by_position_query(self.db, self.hero, d_from, d_to, site=self.site)

        prev_year, prev_month_num = previous_month(year, month)
        p_from, p_to = month_range(prev_year, prev_month_num)
        previous_overview, _ = hero_overview_query(self.db, self.hero, p_from, p_to, site=self.site)
        previous_by_position = position_breakdown_query(self.db, self.hero, p_from, p_to, site=self.site)
        previous_pop = population_by_position_query(self.db, self.hero, p_from, p_to, site=self.site)

        return build_monthly_report(
            year, month, current_overview, previous_overview,
            current_by_position, previous_by_position, current_pop, previous_pop)

    def _on_error(self, msg):
        self._status.setText(f"Couldn't build this report: {msg}")
        self._progress.hide()

    def _render(self, report):
        self._status.hide()
        self._progress.hide()

        if not report.headline or not (report.headline[0].value or 0):
            self._body.addWidget(lbl(
                f"No hands played in {_MONTH_NAMES[report.month]} {report.year}.", dim=True))
            return

        grid_frame = QFrame()
        grid_frame.setStyleSheet(f"background:{BG3};border-radius:6px;")
        grid_lay = QHBoxLayout(grid_frame)
        grid_lay.setContentsMargins(16, 12, 16, 12)
        grid_lay.setSpacing(20)
        for stat in report.headline:
            cell = QVBoxLayout()
            cell.setSpacing(2)
            cell.addWidget(lbl(stat.label, size=10, dim=True))
            if stat.suffix == "money":
                value_text = f"{self.currency}{(stat.value or 0):+,.2f}"
                value_color = GREEN if (stat.value or 0) >= 0 else RED
            elif stat.suffix == "%":
                value_text = f"{stat.value:.1f}%" if stat.value is not None else "—"
                value_color = TEXT
            else:
                value_text = f"{stat.value:,.2f}" if stat.value is not None else "—"
                value_color = TEXT
            value_lbl = QLabel(value_text)
            value_lbl.setStyleSheet(f"color:{value_color};font-size:16px;font-weight:600;")
            cell.addWidget(value_lbl)
            higher_is_better = True if stat.key in ("hands", "profit", "bb100", "wtsd", "wsd") else None
            delta_lbl = QLabel(_delta_html(stat.delta, higher_is_better))
            delta_lbl.setStyleSheet("font-size:11px;")
            cell.addWidget(delta_lbl)
            grid_lay.addLayout(cell)
        self._body.addWidget(grid_frame)

        if not report.has_previous_month_data:
            self._body.addWidget(lbl(
                "No hands from the previous month to compare against yet.", dim=True))

        leak_frame = QFrame()
        leak_frame.setStyleSheet(f"background:{BG3};border-radius:6px;")
        leak_lay = QVBoxLayout(leak_frame)
        leak_lay.setContentsMargins(16, 12, 16, 12)
        leak_lay.addWidget(lbl("BIGGEST LEAK THIS MONTH", size=10, dim=True))
        if report.biggest_leak:
            leak = report.biggest_leak
            leak_lay.addWidget(lbl(
                f"{leak.stat_label} from {leak.position}: {leak.hero_rate:.1f}% vs "
                f"{leak.population_rate:.1f}% population average ({leak.sample:,} hands)",
                size=13))
        else:
            leak_lay.addWidget(lbl("Not enough hands this month to find a reliable leak yet.", dim=True))
        self._body.addWidget(leak_frame)

        improvement_frame = QFrame()
        improvement_frame.setStyleSheet(f"background:{BG3};border-radius:6px;")
        improvement_lay = QVBoxLayout(improvement_frame)
        improvement_lay.setContentsMargins(16, 12, 16, 12)
        improvement_lay.addWidget(lbl("BIGGEST IMPROVEMENT THIS MONTH", size=10, dim=True))
        if report.biggest_improvement:
            imp = report.biggest_improvement
            improvement_lay.addWidget(lbl(
                f"{imp.stat_label} from {imp.position}: {imp.previous_rate:.1f}% → {imp.current_rate:.1f}% "
                f"(population average is {imp.population_rate:.1f}%)",
                size=13))
        elif report.has_previous_month_data:
            improvement_lay.addWidget(lbl(
                "Nothing moved closer to the population average this month — steady, or worth "
                "a look at the Leaks card above.", dim=True))
        else:
            improvement_lay.addWidget(lbl(
                "Needs a previous month with enough hands to compare against.", dim=True))
        self._body.addWidget(improvement_frame)
