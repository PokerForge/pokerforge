"""Stats tab: hero's own full stat breakdown (Overall/Preflop/Flop/Turn/
River) over whatever period/stakes filter is active — reuses the exact
same stat registry, card rendering, and query the villain profile uses,
since hero is just another player_name in hand_player_stats. Laid out as
three sub-tabs (Overview / By Position / Trend) rather than one long
scrolling page, once that page got long enough to feel cluttered."""
import pyqtgraph as pg
from ui.graph_overlay import HoverCrosshair
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QFontMetrics
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFrame, QScrollArea, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QDialog, QCheckBox, QTabWidget,
)

from ui.stat_registry import STAT_REGISTRY, STAT_CATEGORIES, STAT_REGISTRY_BY_ID
from ui.theme import STYLE, BG2, lbl, DIM, TEXT, BG3, GREEN, RED, ORANGE, ACCENT2
from ui.async_worker import AsyncRunner
from ui.main_window import _make_stat_card, _ClickableFrame
from ui.player_classify import generate_hero_leaks
from ui.hand_list_dialog import HandListDialog, HandListPanel
from ui.csv_export import export_table_to_csv
from ui.deviation_backtest_dialog import DeviationBacktestDialog
from core.leak_finder import find_leaks
from database.queries import (
    villain_stats_query, position_breakdown_query, population_by_position_query, pct_trend_query,
    hands_for_stat_query, hands_for_leak_query, hands_for_position_query, DRILLDOWN_STAT_IDS,
)
from config.settings import (
    get_position_table_stat_ids, set_position_table_stat_ids,
    get_trend_stat_ids, set_trend_stat_ids, get_trend_interval_days, set_trend_interval_days,
)

# label, days — the "check in every N" cadence the Trend tab buckets by.
TREND_INTERVALS = [("Weekly", 7), ("Every 2 Weeks", 14), ("Monthly", 30)]
TREND_DEFAULT_STAT_IDS = ["vpip", "pfr", "three_bet"]
TREND_LINE_COLORS = [GREEN, ACCENT2, RED, ORANGE, "#e3b341", "#b48ead"]

# Fixed, always-shown columns that aren't part of STAT_REGISTRY (profit and
# bb/hand are raw totals, not "made this stat y/n" flags) — everything
# else in the By Position table is user-customizable.
POSITION_FIXED_COLUMNS = [
    ("Hands", None, "int"),
    ("My C Won", "profit", "money"),
    ("bb/Hand", "bb_per_hand", "signed"),
]
# The original hand-picked "first pass" set — used as the default until
# the user customizes it, and as the Reset-to-default target afterward.
POSITION_DEFAULT_STAT_IDS = [
    "bb100", "wtsd", "wsd", "wwsf", "total_af", "total_afq",
    "vpip", "pfr", "three_bet", "squeeze", "fold_3bet", "fold_to_steal",
    "flop_cbet", "flop_fold_cbet", "flop_float", "flop_fold_float", "flop_xr", "flop_fold_xr",
    "turn_probe", "turn_fold_probe",
]
POSITION_ROW_ORDER = ["UTG", "MP", "CO", "BTN", "SB", "BB"]
_KIND_SAMPLE = {"pct": "100.00%", "signed": "-100.00", "money": "-$9,999.99", "plain": "999.99", "int": "999,999"}

# Matches ui/theme.py's QHeaderView::section / QTableWidget::item rules
# EXACTLY (font-size 12px, header bold, 12px left/right item padding) —
# measuring width with anything else (e.g. a freshly-constructed
# QTableWidget's own .fontMetrics(), before the app stylesheet has been
# polished onto it) undershoots the real rendered size and clips text.
# This bit the card-widget sizing in the hand-list dialog earlier for the
# same underlying reason: Qt applies stylesheet fonts lazily, not at
# construction time.
def _table_font_metrics() -> QFontMetrics:
    # Bold throughout (not just for the header) because the ALL/totals
    # row is rendered bold — measuring with the heavier weight is the
    # conservative choice that keeps that row from overflowing a column
    # sized only for the lighter regular-weight rows above it.
    font = QFont("Segoe UI")
    font.setPixelSize(12)
    font.setBold(True)
    return QFontMetrics(font)


def _wrap_header(label: str) -> str:
    """Splits a multi-word header into two lines at whichever gap
    minimizes the longer of the two resulting lines — a generic version
    of a hand-picked "My C\\nWon" mapping that works for any of
    STAT_REGISTRY's ~60 labels without maintaining one entry per stat."""
    words = label.split(" ")
    if len(words) < 2:
        return label
    best = None
    for i in range(1, len(words)):
        line1, line2 = " ".join(words[:i]), " ".join(words[i:])
        score = max(len(line1), len(line2))
        if best is None or score < best[0]:
            best = (score, line1, line2)
    return f"{best[1]}\n{best[2]}"


def _column_width(header_fm, header_text: str, kind: str) -> int:
    header_w = max(header_fm.horizontalAdvance(line) for line in header_text.split("\n"))
    # The ALL/totals row is rendered bold — measuring the data sample with
    # the (also bold) header font, not a regular-weight one, keeps that
    # row's wider glyphs from overflowing a column sized for every other
    # (regular-weight) row.
    data_w = header_fm.horizontalAdvance(_KIND_SAMPLE.get(kind, "100.00%"))
    # 24px = QHeaderView::section's / QTableWidget::item's own 12px+12px
    # left/right padding; the rest is a safety margin against font
    # substitution differences between machines.
    return max(header_w, data_w) + 24 + 10


class PositionColumnsDialog(QDialog):
    """Lets the user pick which STAT_REGISTRY stats appear as columns in
    the By Position table, grouped the same way the stat cards above are
    (Overall/Preflop/Flop/Turn/River)."""

    def __init__(self, selected_ids: list[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Customise By Position Columns")
        self.setStyleSheet(STYLE)
        self.resize(420, 600)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(10)
        lay.addWidget(lbl("Choose which stats to show as columns (Hands, My C Won and "
                          "bb/Hand are always shown).", size=11, dim=True))

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea{border:none;background:transparent;}")
        inner = QWidget()
        inner_lay = QVBoxLayout(inner)
        inner_lay.setSpacing(6)
        self._checks: dict[str, QCheckBox] = {}
        for category in STAT_CATEGORIES:
            stats_in_cat = [s for s in STAT_REGISTRY if s["category"] == category]
            if not stats_in_cat:
                continue
            inner_lay.addWidget(lbl(category.upper(), size=11, bold=True))
            for stat in stats_in_cat:
                cb = QCheckBox(stat["label"])
                cb.setChecked(stat["id"] in selected_ids)
                cb.setCursor(Qt.CursorShape.PointingHandCursor)
                self._checks[stat["id"]] = cb
                inner_lay.addWidget(cb)
        inner_lay.addStretch()
        scroll.setWidget(inner)
        lay.addWidget(scroll, 1)

        btn_row = QHBoxLayout()
        reset_btn = QPushButton("Reset to Default")
        reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        reset_btn.clicked.connect(self._reset)
        btn_row.addWidget(reset_btn)
        btn_row.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        ok_btn = QPushButton("OK")
        ok_btn.clicked.connect(self.accept)
        btn_row.addWidget(ok_btn)
        lay.addLayout(btn_row)

    def _reset(self):
        for stat_id, cb in self._checks.items():
            cb.setChecked(stat_id in POSITION_DEFAULT_STAT_IDS)

    def selected_ids(self) -> list[str]:
        # Keep STAT_REGISTRY's own (category-grouped) order rather than
        # dict-insertion order, so column order stays stable/sensible
        # regardless of what the user (un)checks.
        return [s["id"] for s in STAT_REGISTRY if self._checks[s["id"]].isChecked()]


class TrendOptionsDialog(QDialog):
    """Which percentage stats to plot on the Trend tab, plus the check-in
    interval to bucket by — only "pct"-kind stats are offered, since the
    chart's y-axis is a shared 0-100% scale (a bb/100 line wouldn't be
    comparable on the same axis)."""

    def __init__(self, selected_ids: list[str], interval_days: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Customise Trend")
        self.setStyleSheet(STYLE)
        self.resize(420, 600)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(10)

        lay.addWidget(lbl("Check in every:", size=11, dim=True))
        interval_row = QHBoxLayout()
        self._interval_group: dict[int, QCheckBox] = {}
        for label, days in TREND_INTERVALS:
            cb = QCheckBox(label)
            cb.setCursor(Qt.CursorShape.PointingHandCursor)
            cb.setChecked(days == interval_days)
            cb.toggled.connect(lambda checked, d=days: checked and self._select_interval(d))
            self._interval_group[days] = cb
            interval_row.addWidget(cb)
        interval_row.addStretch()
        lay.addLayout(interval_row)

        lay.addWidget(lbl("Which stats to plot (percentage stats only):", size=11, dim=True))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea{border:none;background:transparent;}")
        inner = QWidget()
        inner_lay = QVBoxLayout(inner)
        inner_lay.setSpacing(6)
        self._checks: dict[str, QCheckBox] = {}
        for category in STAT_CATEGORIES:
            stats_in_cat = [s for s in STAT_REGISTRY if s["category"] == category and s["kind"] == "pct"]
            if not stats_in_cat:
                continue
            inner_lay.addWidget(lbl(category.upper(), size=11, bold=True))
            for stat in stats_in_cat:
                cb = QCheckBox(stat["label"])
                cb.setChecked(stat["id"] in selected_ids)
                cb.setCursor(Qt.CursorShape.PointingHandCursor)
                self._checks[stat["id"]] = cb
                inner_lay.addWidget(cb)
        inner_lay.addStretch()
        scroll.setWidget(inner)
        lay.addWidget(scroll, 1)

        btn_row = QHBoxLayout()
        reset_btn = QPushButton("Reset to Default")
        reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        reset_btn.clicked.connect(self._reset)
        btn_row.addWidget(reset_btn)
        btn_row.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        ok_btn = QPushButton("OK")
        ok_btn.clicked.connect(self.accept)
        btn_row.addWidget(ok_btn)
        lay.addLayout(btn_row)

    def _select_interval(self, days):
        # Simple mutually-exclusive checkboxes (a small QButtonGroup
        # substitute) rather than radio buttons, just to match this
        # dialog's existing checkbox-based look.
        for d, cb in self._interval_group.items():
            if d != days:
                cb.setChecked(False)

    def _reset(self):
        for stat_id, cb in self._checks.items():
            cb.setChecked(stat_id in TREND_DEFAULT_STAT_IDS)
        self._select_interval(14)
        self._interval_group[14].setChecked(True)

    def selected_ids(self) -> list[str]:
        return [s["id"] for s in STAT_REGISTRY if s["id"] in self._checks and self._checks[s["id"]].isChecked()]

    def selected_interval_days(self) -> int:
        for days, cb in self._interval_group.items():
            if cb.isChecked():
                return days
        return 14


def _scroll_page():
    """A QScrollArea + inner QVBoxLayout, the shape every sub-tab page
    here uses — returns (scroll_widget, inner_vbox_layout)."""
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setStyleSheet("QScrollArea{border:none;background:transparent;}")
    inner = QWidget()
    lay = QVBoxLayout(inner)
    lay.setContentsMargins(16, 16, 16, 40)
    lay.setSpacing(16)
    scroll.setWidget(inner)
    return scroll, lay


class StatsTab(QWidget, AsyncRunner):
    def __init__(self, hero, db, currency="£"):
        super().__init__()
        self._init_async()
        self.hero = hero
        self.db = db
        self.currency = currency
        self._current_d_from = self._current_d_to = self._current_stake = None
        self._last_result = None
        self._position_stat_ids = get_position_table_stat_ids() or list(POSITION_DEFAULT_STAT_IDS)
        self._position_row_labels: list[str] = []
        self._position_col_stat_ids: list[str | None] = []
        self._trend_stat_ids = get_trend_stat_ids() or list(TREND_DEFAULT_STAT_IDS)
        self._trend_interval_days = get_trend_interval_days()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(12)

        self.hands_lbl = lbl("", dim=True)
        outer.addWidget(self.hands_lbl)

        self.sub_tabs = QTabWidget()
        self.overview_scroll, self.overview_lay = _scroll_page()
        self.position_scroll, self.position_lay = _scroll_page()
        self.trend_page = self._build_trend_page()
        self.sub_tabs.addTab(self.position_scroll, "  By Position  ")
        self.sub_tabs.addTab(self.overview_scroll, "  Leaks  ")
        self.sub_tabs.addTab(self.trend_page, "  Trend  ")
        outer.addWidget(self.sub_tabs, 1)

    def refresh(self, db, hero, d_from, d_to, currency="£", stake=None):
        self.db = db
        self.hero = hero
        self.currency = currency
        self._current_d_from, self._current_d_to, self._current_stake = d_from, d_to, stake
        self.run_async(
            lambda: (villain_stats_query(db, hero, d_from, d_to, stake),
                      position_breakdown_query(db, hero, d_from, d_to, stake),
                      population_by_position_query(db, hero, d_from, d_to, stake)),
            self._render,
        )
        self._refresh_trend()

    def _refresh_trend(self):
        self.run_async(
            lambda: pct_trend_query(self.db, self.hero, self._current_d_from, self._current_d_to,
                                      self._trend_stat_ids, self._current_stake, self._trend_interval_days),
            self._render_trend,
            key="trend",
        )

    def _on_stat_clicked(self, stat):
        rows = hands_for_stat_query(self.db, self.hero, stat['id'],
                                     self._current_d_from, self._current_d_to, self._current_stake)
        HandListDialog(rows, self.db, self.hero, stat['label'], self.currency, parent=self).exec()

    def _on_leak_clicked(self, leak_id, title):
        rows = hands_for_leak_query(self.db, self.hero, leak_id,
                                     self._current_d_from, self._current_d_to, self._current_stake)
        HandListDialog(rows, self.db, self.hero, title, self.currency, parent=self).exec()

    def _build_cross_leaks_card(self, cross_leaks):
        """The top of ranked list is a callout for the single biggest leak
        (deviation-from-population weighted by sample size, see
        core/leak_finder.py); the rest render as compact rows below it."""
        frame = QFrame()
        frame.setObjectName("card")
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)
        lay.addWidget(lbl(
            "LEAKS BY POSITION  ·  ranked by deviation × sample size  ·  click one to see example hands",
            size=11, dim=True))

        biggest = cross_leaks[0]
        callout = _ClickableFrame()
        callout.setStyleSheet(f"background:{BG3};border-radius:6px;border:none;border-left:3px solid {RED};")
        callout.setCursor(Qt.CursorShape.PointingHandCursor)
        callout.setToolTip("Click to see example hands")
        callout.clicked.connect(lambda l=biggest: self._on_cross_leak_clicked(l))
        cl = QVBoxLayout(callout)
        cl.setContentsMargins(14, 10, 14, 10)
        cl.setSpacing(4)
        direction = "higher" if biggest.deviation > 0 else "lower"
        cl.addWidget(lbl(
            f"{biggest.stat_label} from {biggest.position} — {abs(biggest.deviation):.1f} points {direction} "
            f"than the population", bold=True, size=13))
        cl.addWidget(lbl(
            f"You {biggest.hero_rate:.1f}%  ·  Population {biggest.population_rate:.1f}%  ·  "
            f"{biggest.sample:,} hands", dim=True, size=11))
        lay.addWidget(callout)

        for leak in cross_leaks[1:5]:
            row_w = _ClickableFrame()
            row_w.setStyleSheet(f"background:{BG3};border-radius:6px;border:none;")
            row_w.setCursor(Qt.CursorShape.PointingHandCursor)
            row_w.setToolTip("Click to see example hands")
            row_w.clicked.connect(lambda l=leak: self._on_cross_leak_clicked(l))
            rl = QHBoxLayout(row_w)
            rl.setContentsMargins(12, 8, 12, 8)
            direction = "higher" if leak.deviation > 0 else "lower"
            rl.addWidget(lbl(
                f"{leak.stat_label} — {leak.position}  ·  {abs(leak.deviation):.1f} pts {direction}",
                size=12), 1)
            rl.addWidget(lbl(
                f"You {leak.hero_rate:.1f}%  ·  Pop {leak.population_rate:.1f}%  ·  {leak.sample:,} hands",
                dim=True, size=11))
            lay.addWidget(row_w)

        return frame

    def _on_cross_leak_clicked(self, leak):
        # Always the hands where the stat's own condition was made (same
        # convention _on_stat_clicked already uses for a plain stat-card
        # click) rather than direction-aware "opportunities you missed"
        # framing — that finer illustrative-condition system exists for
        # ui/player_classify.py's fixed leak set (LEAK_HAND_CONDITIONS),
        # not attempted here across 10 stats x 2 possible directions.
        rows = hands_for_stat_query(self.db, self.hero, leak.stat_id,
                                     self._current_d_from, self._current_d_to, self._current_stake,
                                     position=leak.position)
        label = f"{leak.stat_label} — {leak.position}"
        HandListDialog(rows, self.db, self.hero, label, self.currency, parent=self).exec()

    def _on_position_cell_double_clicked(self, row, col):
        if col >= len(self._position_col_stat_ids):
            return
        stat_id = self._position_col_stat_ids[col]
        position = self._position_row_labels[row]
        position_filter = None if position == "ALL" else position

        if stat_id is None:  # the "Position" label column itself — every hand played there
            rows = hands_for_position_query(self.db, self.hero, position_filter,
                                             self._current_d_from, self._current_d_to, self._current_stake)
            label = "All Hands" if position_filter is None else f"All Hands — {position_filter}"
            self._show_position_hands(rows, label)
            return

        if stat_id not in DRILLDOWN_STAT_IDS:
            return
        stat = STAT_REGISTRY_BY_ID[stat_id]
        rows = hands_for_stat_query(self.db, self.hero, stat_id,
                                     self._current_d_from, self._current_d_to, self._current_stake,
                                     position=position_filter)
        label = stat['label'] if position_filter is None else f"{stat['label']} — {position_filter}"
        self._show_position_hands(rows, label)

    def _show_position_hands(self, rows, label):
        self._clear(self._position_hands_layout)
        panel = HandListPanel(rows, self.db, self.hero, label, self.currency,
                               parent=self._position_hands_card, embedded=True)
        self._position_hands_layout.addWidget(panel)
        self._position_hands_card.show()

    def _on_customise_clicked(self):
        dlg = PositionColumnsDialog(self._position_stat_ids, parent=self)
        if dlg.exec():
            self._position_stat_ids = dlg.selected_ids()
            set_position_table_stat_ids(self._position_stat_ids)
            if self._last_result is not None:
                self._render(self._last_result)

    def _on_trend_customise_clicked(self):
        dlg = TrendOptionsDialog(self._trend_stat_ids, self._trend_interval_days, parent=self)
        if dlg.exec():
            self._trend_stat_ids = dlg.selected_ids()
            self._trend_interval_days = dlg.selected_interval_days()
            set_trend_stat_ids(self._trend_stat_ids)
            set_trend_interval_days(self._trend_interval_days)
            self._refresh_trend()

    def _on_backtest_deviations_clicked(self):
        DeviationBacktestDialog(
            self.db, self.hero, self._current_d_from, self._current_d_to,
            self._trend_stat_ids, self._trend_interval_days, self._current_stake, parent=self).exec()

    def _clear(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def _render(self, result):
        self._last_result = result
        (values, hand_count, _, opp_counts), by_position, population_by_position = result
        self.hands_lbl.setText(f"{hand_count:,} hands")

        self._render_overview(values, opp_counts, by_position, population_by_position)
        self._render_position(values, hand_count, by_position)

    def _render_overview(self, values, opp_counts, by_position, population_by_position):
        self._clear(self.overview_lay)

        cross_leaks = find_leaks(by_position, population_by_position)
        if cross_leaks:
            self.overview_lay.addWidget(self._build_cross_leaks_card(cross_leaks))

        leaks_frame = QFrame()
        leaks_frame.setObjectName("card")
        lfl = QVBoxLayout(leaks_frame)
        lfl.setContentsMargins(12, 12, 12, 12)
        lfl.setSpacing(8)
        lfl.addWidget(lbl("YOUR LEAKS  ·  click one to see example hands", size=11, dim=True))
        for icon, title, advice, leak_id in generate_hero_leaks(values, opp_counts):
            drillable = leak_id is not None
            row_w = _ClickableFrame() if drillable else QFrame()
            row_w.setStyleSheet(f"background:{BG3};border-radius:6px;border:none;")
            if drillable:
                row_w.setCursor(Qt.CursorShape.PointingHandCursor)
                row_w.setToolTip("Click to see example hands")
                row_w.clicked.connect(lambda lid=leak_id, t=title: self._on_leak_clicked(lid, t))
            rl = QVBoxLayout(row_w)
            rl.setContentsMargins(12, 8, 12, 8)
            rl.setSpacing(2)
            rl.addWidget(lbl(f"{icon}  {title}", bold=True, size=12))
            rl.addWidget(lbl(advice, dim=True, size=11))
            lfl.addWidget(row_w)
        self.overview_lay.addWidget(leaks_frame)

        for category in STAT_CATEGORIES:
            stats_in_cat = [s for s in STAT_REGISTRY if s['category'] == category]
            if not stats_in_cat:
                continue
            card_frame = QFrame()
            card_frame.setObjectName("card")
            cfl = QVBoxLayout(card_frame)
            cfl.setContentsMargins(12, 12, 12, 12)
            cfl.setSpacing(8)

            grid_holder = QWidget()
            grid = QGridLayout(grid_holder)
            grid.setContentsMargins(0, 0, 0, 0)
            grid.setSpacing(8)
            for i, stat in enumerate(stats_in_cat):
                grid.addWidget(
                    _make_stat_card(stat, values.get(stat['id']), None, self._on_stat_clicked,
                                     sample_n=opp_counts.get(stat['id'])),
                    i // 7, i % 7)

            # Clickable header collapses/expands this category's stat grid
            # — same interaction as the villain profile panel. Turn/River
            # start collapsed since they're the least-studied streets by
            # default; Overall/Preflop/Flop start open.
            start_open = category not in ("Turn", "River")
            grid_holder.setVisible(start_open)
            header_btn = QPushButton(f"{chr(0x25be) if start_open else chr(0x25b8)}  {category.upper()}")
            header_btn.setCheckable(True)
            header_btn.setChecked(start_open)
            header_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            header_btn.setStyleSheet(
                f"QPushButton{{background:transparent;border:none;color:{DIM};"
                f"font-size:11px;font-weight:600;text-align:left;padding:0;}}"
                f"QPushButton:hover{{color:{TEXT};}}")

            def _toggle(checked, btn=header_btn, content=grid_holder, cat=category.upper()):
                content.setVisible(checked)
                btn.setText(f"{chr(0x25be) if checked else chr(0x25b8)}  {cat}")
            header_btn.toggled.connect(_toggle)

            cfl.addWidget(header_btn)
            cfl.addWidget(grid_holder)
            self.overview_lay.addWidget(card_frame)
        self.overview_lay.addStretch()

    def _position_columns(self):
        """Fixed columns + whichever STAT_REGISTRY stats are currently
        selected, as (label, stat_id, kind) triples."""
        cols = list(POSITION_FIXED_COLUMNS)
        for stat_id in self._position_stat_ids:
            stat = STAT_REGISTRY_BY_ID.get(stat_id)
            if stat:
                cols.append((stat["label"], stat_id, stat["kind"]))
        return cols

    def _render_position(self, overall_values, overall_hand_count, by_position):
        self._clear(self.position_lay)

        card = QFrame()
        card.setObjectName("card")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(12, 12, 12, 12)
        cl.setSpacing(8)

        header_row = QHBoxLayout()
        header_row.addWidget(lbl("BY POSITION  ·  double-click a position for all its hands, or a stat for example hands",
                                  size=11, dim=True))
        header_row.addStretch()
        export_btn = QPushButton("Export to CSV...")
        export_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        header_row.addWidget(export_btn)
        customise_btn = QPushButton("Customise")
        customise_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        customise_btn.clicked.connect(self._on_customise_clicked)
        header_row.addWidget(customise_btn)
        cl.addLayout(header_row)

        position_columns = self._position_columns()
        labels = [label for label, _, _ in position_columns]
        kinds = [kind for _, _, kind in position_columns]
        self._position_col_stat_ids = [None] + [stat_id for _, stat_id, _ in position_columns]

        header_texts = ["Position"] + [_wrap_header(label) for label in labels]
        table = QTableWidget()
        table.setColumnCount(len(header_texts))
        table.setHorizontalHeaderLabels(header_texts)
        header = table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setAlternatingRowColors(True)
        table.cellDoubleClicked.connect(self._on_position_cell_double_clicked)
        export_btn.clicked.connect(lambda: export_table_to_csv(table, self, default_filename="by_position.csv"))
        table.setToolTip("Double-click a cell to see the hands behind it")

        fm = _table_font_metrics()
        # Two stacked lines of this font plus the header's own 8px top +
        # 8px bottom padding (see ui/theme.py's QHeaderView::section rule).
        header.setFixedHeight(fm.lineSpacing() * 2 + 16)
        for col, full_label in enumerate(["Position"] + labels):
            table.horizontalHeaderItem(col).setToolTip(full_label)
        widths = [max(fm.horizontalAdvance("Position"), fm.horizontalAdvance("BTN/SB")) + 24 + 10] + [
            _column_width(fm, header_texts[i + 1], kinds[i]) for i in range(len(labels))
        ]
        for col, w in enumerate(widths):
            table.setColumnWidth(col, w)

        rows = [pos for pos in POSITION_ROW_ORDER if pos in by_position]
        rows += [pos for pos in by_position if pos not in POSITION_ROW_ORDER]
        self._position_row_labels = rows + ["ALL"]
        table.setRowCount(len(rows) + 1)  # + totals row

        def fill_row(r, label, values, hand_count, bold=False):
            table.setRowHeight(r, 32)
            cells = [(label, None)] + self._format_position_cells(position_columns, values, hand_count)
            for c, (text, color) in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter if c else
                                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                if color:
                    item.setForeground(QColor(color))
                if bold:
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                table.setItem(r, c, item)

        for r, pos in enumerate(rows):
            values, hand_count, _ = by_position[pos]
            fill_row(r, pos, values, hand_count)
        fill_row(len(rows), "ALL", overall_values, overall_hand_count, bold=True)

        # QTableWidget's own default height shows only a couple of rows —
        # give it the exact height its content needs instead, since this
        # table's row count is small and fixed (positions + a totals row),
        # not a scroll-internally kind of table. Padded generously (not
        # just the frame border) since setRowHeight is a minimum, not a
        # guarantee — a taller-than-expected row here would otherwise
        # force an internal scrollbar that hides the ALL row.
        table.setFixedHeight(header.height() + (len(rows) + 1) * 32 + 16)

        cl.addWidget(table)
        self.position_lay.addWidget(card)

        # Inline hand-list panel — filled in by _on_position_cell_double_clicked
        # rather than a popup dialog, since there's plenty of room on this
        # page to just show the hands below the table.
        self._position_hands_card = QFrame()
        self._position_hands_card.setObjectName("card")
        self._position_hands_layout = QVBoxLayout(self._position_hands_card)
        self._position_hands_layout.setContentsMargins(12, 12, 12, 12)
        self._position_hands_card.hide()
        self.position_lay.addWidget(self._position_hands_card)

        self.position_lay.addStretch()

    def _format_position_cells(self, position_columns, values, hand_count):
        cells = []
        for label, stat_id, kind in position_columns:
            if stat_id is None:  # Hands
                cells.append((f"{hand_count:,}", None))
                continue
            v = values.get(stat_id)
            if v is None:
                cells.append(("—", DIM))
                continue
            if kind == "money":
                cells.append((f"{self.currency}{v:+,.2f}", GREEN if v >= 0 else RED))
            elif kind == "signed":
                cells.append((f"{v:+.2f}", GREEN if v >= 0 else RED))
            elif kind == "plain":
                cells.append((f"{v:.2f}", TEXT))
            else:  # pct
                stat = STAT_REGISTRY_BY_ID.get(stat_id, {})
                lo, hi = stat.get('lo'), stat.get('hi')
                if lo is None:
                    color = "#d8dee9"
                else:
                    margin = (hi - lo) * 0.5
                    if lo <= v <= hi:
                        color = GREEN
                    elif (lo - margin) <= v <= (hi + margin):
                        color = ORANGE
                    else:
                        color = RED
                cells.append((f"{v:.2f}%", color))
        return cells

    def _build_trend_page(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(12)

        header_row = QHBoxLayout()
        self.trend_info_lbl = lbl("", dim=True)
        header_row.addWidget(self.trend_info_lbl)
        header_row.addStretch()
        backtest_btn = QPushButton("Backtest Deviations")
        backtest_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        backtest_btn.setToolTip("What did your results look like during your own high/low periods for these stats?")
        backtest_btn.clicked.connect(self._on_backtest_deviations_clicked)
        header_row.addWidget(backtest_btn)
        customise_btn = QPushButton("Customise")
        customise_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        customise_btn.clicked.connect(self._on_trend_customise_clicked)
        header_row.addWidget(customise_btn)
        lay.addLayout(header_row)

        self.trend_plot = pg.PlotWidget()
        self.trend_plot.setMinimumHeight(360)
        self.trend_plot.setBackground(BG2)
        self.trend_plot.showGrid(x=True, y=True, alpha=0.15)
        pi = self.trend_plot.getPlotItem()
        pi.hideAxis('left')
        pi.showAxis('right')
        pi.getAxis('right').linkToView(pi.vb)
        pi.getAxis('right').setLabel('%')
        pi.vb.setMouseEnabled(x=False, y=False)
        pi.setMenuEnabled(False)
        lay.addWidget(self.trend_plot)

        # A mutable list, not reassigned — _render_trend() clears and
        # repopulates it in place on every customize/refresh, so this one
        # HoverCrosshair (built once here) always sees the current curves
        # without needing to be torn down and rebuilt alongside them.
        self._trend_curve_specs = []
        self._trend_bucket_starts = []
        self.trend_crosshair = HoverCrosshair(
            self.trend_plot, self._trend_curve_specs,
            value_formatter=lambda v: f"{v:.2f}%",
            x_label_formatter=self._trend_x_label,
        )

        self.trend_legend_row = QHBoxLayout()
        self.trend_legend_row.setSpacing(18)
        self.trend_legend_row.addStretch()
        legend_w = QWidget()
        legend_w.setLayout(self.trend_legend_row)
        lay.addWidget(legend_w)
        lay.addStretch()
        return page

    def _trend_x_label(self, x):
        idx = max(0, min(len(self._trend_bucket_starts) - 1, int(round(x)) - 1))
        return self._trend_bucket_starts[idx] if self._trend_bucket_starts else ""

    def _render_trend(self, trend):
        bucket_starts, series, hand_counts = trend

        # Trim leading/trailing check-in periods with zero hands (before
        # you started, or after you stopped, playing within the selected
        # range) — they aren't real check-ins, just empty axis space. A
        # zero-hand gap in the MIDDLE of the range is left alone; that one
        # is real (a stretch with no play at all).
        first = next((i for i, h in enumerate(hand_counts) if h), None)
        if first is None:
            bucket_starts, hand_counts, series = [], [], {sid: [] for sid in series}
        else:
            last = len(hand_counts) - 1 - next(i for i, h in enumerate(reversed(hand_counts)) if h)
            bucket_starts = bucket_starts[first:last + 1]
            hand_counts = hand_counts[first:last + 1]
            series = {sid: vals[first:last + 1] for sid, vals in series.items()}

        self._trend_bucket_starts = bucket_starts
        total_hands = sum(hand_counts)
        interval_label = next((label for label, days in TREND_INTERVALS
                               if days == self._trend_interval_days), f"{self._trend_interval_days}-day")
        self.trend_info_lbl.setText(
            f"{interval_label} check-ins  ·  {len(bucket_starts)} points  ·  {total_hands:,} hands")

        self.trend_plot.clear()
        self.trend_crosshair.reattach()
        self._trend_curve_specs.clear()
        self._clear(self.trend_legend_row)
        pi = self.trend_plot.getPlotItem()
        axis = pi.getAxis('bottom')

        if not bucket_starts or not self._trend_stat_ids:
            axis.setTicks(None)
            self.trend_legend_row.addStretch()
            return

        xs = list(range(1, len(bucket_starts) + 1))

        # Shaded healthy-range band — only when exactly one stat is
        # selected, since overlapping bands for 2-3 stats at once would
        # just be visual noise rather than useful reference lines.
        if len(self._trend_stat_ids) == 1:
            stat = STAT_REGISTRY_BY_ID.get(self._trend_stat_ids[0], {})
            lo, hi = stat.get('lo'), stat.get('hi')
            if lo is not None and hi is not None:
                region = pg.LinearRegionItem(values=(lo, hi), orientation='horizontal',
                                              brush=pg.mkBrush(63, 185, 80, 40))
                region.setMovable(False)
                region.setZValue(-10)
                pi.addItem(region)

        for i, stat_id in enumerate(self._trend_stat_ids):
            stat = STAT_REGISTRY_BY_ID.get(stat_id)
            if stat is None:
                continue
            color = TREND_LINE_COLORS[i % len(TREND_LINE_COLORS)]
            values = series.get(stat_id, [])
            # A check-in period with no opportunities for this stat comes
            # back as None — plot it as a gap (NaN + connect='finite'),
            # not a misleading 0%.
            ys = [v if v is not None else float('nan') for v in values]
            curve = self.trend_plot.plot(xs, ys, pen=pg.mkPen(color=color, width=2.5),
                                          symbol='o', symbolSize=6, symbolBrush=color,
                                          symbolPen=None, connect='finite')
            cb = QCheckBox(stat['label'])
            cb.setChecked(True)
            cb.setCursor(Qt.CursorShape.PointingHandCursor)
            cb.setStyleSheet(f"""
                QCheckBox {{ color:{color}; font-size:11px; font-weight:600; spacing:6px; }}
                QCheckBox::indicator {{ width:12px; height:12px; border-radius:3px;
                    border:1.5px solid {color}; background:{BG3}; }}
                QCheckBox::indicator:checked {{ background:{color}; }}
            """)
            cb.toggled.connect(lambda checked, c=curve: c.setVisible(checked))
            self.trend_legend_row.addWidget(cb)
            self._trend_curve_specs.append((stat['label'], curve, color))
        self.trend_legend_row.addStretch()

        pi.vb.setXRange(xs[0] - 0.5, xs[-1] + 0.5, padding=0)
        # Thin the tick labels out so they don't overlap on a long range —
        # show at most ~12 across the whole axis.
        step = max(1, len(xs) // 12)
        ticks = [(x, bucket_starts[x - 1]) for x in xs if (x - 1) % step == 0]
        axis.setTicks([ticks])
