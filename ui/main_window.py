"""Population tab's villain profile panel: search list + detail view.
Matches poker_dashboard_legacy.py's VillainProfile precisely: the header
labels and the graph's curve objects are created ONCE and only updated
in place on each villain click (setText/setData) — recreating the plot
widget itself on every click, which the first version of this rebuild did,
is the expensive operation that made switching feel sluggish compared to
the original. Stat cards, exploit notes, and the vs-open section ARE
cleared and rebuilt each time, matching the legacy code's own behavior —
those are cheap QFrame/QLabel widgets, not a QGraphicsView-based plot.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pyqtgraph as pg
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QScrollArea, QFrame, QPushButton, QTextEdit, QGraphicsBlurEffect,
    QSplitter, QLabel, QCheckBox,
)
from PyQt6.QtCore import Qt, QEvent, pyqtSignal

from ui.stat_registry import STAT_REGISTRY, STAT_CATEGORIES, pop_avg
from ui.theme import BG2, BG3, BORDER, GREEN, RED, ORANGE, DIM, TEXT, ACCENT2, lbl
from ui.async_worker import AsyncRunner
from ui.player_classify import classify_player, generate_leaks, MIN_LEAK_SAMPLE as SMALL_SAMPLE_THRESHOLD
from database.queries import (
    villain_stats_query, villain_graph_query, villain_group_stats_query, villain_group_graph_query,
    hands_for_stat_query, DRILLDOWN_STAT_IDS,
)
from ui.hand_list_dialog import HandListDialog
from ui.graph_overlay import HoverCrosshair

POSITION_ORDER = ['UTG', 'MP', 'CO', 'BTN', 'SB', 'BB', 'BTN/SB']


class _ClickableFrame(QFrame):
    clicked = pyqtSignal()

    def mousePressEvent(self, event):
        # The villain panel's stat cards are destroyed and rebuilt on
        # every refresh (see this module's docstring) — including ones
        # the live folder watcher now triggers automatically every few
        # seconds while playing (ui/live_watcher.py), not just the rare
        # manual period/stake change this used to only ever race with.
        # A click already queued for a card at the exact moment it gets
        # torn down and replaced arrives here after the underlying C++
        # QFrame is gone — a real crash seen in production (RuntimeError:
        # wrapped C/C++ object ... has been deleted). The click has
        # already lost its meaning by then; drop it instead of crashing.
        try:
            if event.button() == Qt.MouseButton.LeftButton:
                self.clicked.emit()
            super().mousePressEvent(event)
        except RuntimeError:
            pass


def _make_stat_card(stat, value, live_averages=None, on_click=None, sample_n=None):
    drillable = on_click is not None and stat['id'] in DRILLDOWN_STAT_IDS
    card = _ClickableFrame() if drillable else QFrame()
    card.setObjectName("card")
    card.setMinimumWidth(110)
    if drillable:
        card.setCursor(Qt.CursorShape.PointingHandCursor)
        card.setToolTip("Click to see the hands behind this stat")
        card.clicked.connect(lambda: on_click(stat))
    cl = QVBoxLayout(card)
    cl.setContentsMargins(10, 8, 10, 8)
    cl.setSpacing(2)
    cl.addWidget(lbl(stat['label'], size=10, dim=True))

    if value is None:
        cl.addWidget(lbl("—", size=16, bold=True))
        return card

    kind = stat['kind']
    if kind == 'signed':
        color = GREEN if value >= 0 else RED
        text = f"{value:+.2f}"
    elif kind == 'plain':
        color = TEXT
        text = f"{value:.2f}"
    else:  # pct
        lo, hi = stat.get('lo'), stat.get('hi')
        if lo is None or hi is None:
            color = "#d8dee9"
        else:
            margin = (hi - lo) * 0.5
            if lo <= value <= hi:
                color = GREEN
            elif (lo - margin) <= value <= (hi + margin):
                color = ORANGE
            else:
                color = RED
        text = f"{value:.2f}%"

    val_lbl = lbl(text, size=16, bold=True)
    val_lbl.setStyleSheet(f"color:{color};font-size:16px;font-weight:700;background:transparent;border:none;")
    cl.addWidget(val_lbl)

    live_avg = (live_averages or {}).get(stat['id'])
    avg = live_avg if live_avg is not None else pop_avg(stat)
    if avg is not None and kind == 'pct':
        cl.addWidget(lbl(f"Pop avg: {avg}%", size=9, dim=True))
    if sample_n is not None:
        n_lbl = lbl(f"({sample_n:,})", size=9, dim=True)
        if sample_n < SMALL_SAMPLE_THRESHOLD:
            n_lbl.setStyleSheet(f"color:{ORANGE};font-size:9px;background:transparent;border:none;")
        cl.addWidget(n_lbl)
    return card


class VillainDetail(QWidget, AsyncRunner):
    def __init__(self, hero, db, currency="£"):
        super().__init__()
        self.hero = hero
        self.db = db
        self.currency = currency
        self._init_async()
        self._name_blurred = False
        self._pop_averages = {}

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(16)

        self.placeholder = lbl("← Select a villain to view their profile", size=14, dim=True)
        self.placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(self.placeholder)

        # Content (built once, hidden until a villain is selected)
        self.content = QWidget()
        self.content.hide()
        clay = QVBoxLayout(self.content)
        clay.setContentsMargins(0, 0, 0, 0)
        clay.setSpacing(16)

        # Header row — built once; only text/color is updated per villain.
        self.name_lbl = lbl("", size=18, bold=True)
        self.hide_btn = QPushButton("Hide")
        self.hide_btn.setFixedSize(48, 24)
        self.hide_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.hide_btn.setToolTip("Blur villain name")
        self.hide_btn.setStyleSheet(
            f"QPushButton{{background:{BG3};border:1px solid {BORDER};border-radius:5px;"
            f"font-size:10px;color:{DIM};padding:0px;}}"
            f"QPushButton:hover{{background:#30363d;color:{TEXT};}}")
        self.hide_btn.clicked.connect(self._toggle_blur)
        self.type_lbl = lbl("", size=13)
        self.hands_lbl = lbl("", dim=True)
        self.hands_lbl.setTextFormat(Qt.TextFormat.RichText)
        hdr = QHBoxLayout()
        hdr.addWidget(self.name_lbl)
        hdr.addWidget(self.hide_btn)
        hdr.addWidget(self.type_lbl)
        hdr.addStretch()
        hdr.addWidget(self.hands_lbl)
        clay.addLayout(hdr)

        # Graph and stats sit in a vertical splitter (same mechanism as the
        # Population tab's list/detail splitter) so the graph can be dragged
        # taller — the stats pane gets its own scroll area so it doesn't just
        # get squeezed to nothing when the graph grows.
        self.v_splitter = QSplitter(Qt.Orientation.Vertical)
        self.v_splitter.setHandleWidth(6)

        # Graph — the plot widget and its curves are created ONCE; every
        # subsequent villain just calls .setData() on these same curves.
        gcard = QFrame()
        gcard.setObjectName("card")
        gl = QVBoxLayout(gcard)
        gl.setContentsMargins(12, 12, 12, 12)
        gl.addWidget(lbl("VILLAIN RESULTS", size=11, dim=True))
        self.plot = pg.PlotWidget()
        self.plot.setMinimumHeight(260)
        self.plot.setBackground(BG2)
        self.plot.showGrid(x=False, y=True, alpha=0.15)
        pi = self.plot.getPlotItem()
        pi.hideAxis('left')
        pi.showAxis('right')
        pi.getAxis('right').linkToView(pi.vb)
        pi.getAxis('right').setLabel('Profit')
        pi.getAxis('bottom').setLabel('Hands')
        pi.vb.setMouseEnabled(x=False, y=False)
        pi.vb.enableAutoRange(axis='x', enable=False)
        pi.setMenuEnabled(False)
        pi.addItem(pg.InfiniteLine(pos=0, angle=0, pen=pg.mkPen(color="#8b949e", width=1.2)))
        self.c_total = self.plot.plot(pen=pg.mkPen(color=GREEN, width=2.5))
        self.c_sd = self.plot.plot(pen=pg.mkPen(color=ACCENT2, width=1.5))
        self.c_nsd = self.plot.plot(pen=pg.mkPen(color=RED, width=1.5))
        self.c_hero = self.plot.plot(pen=pg.mkPen(color="#b48ead", width=2))
        self.c_ev = self.plot.plot(pen=pg.mkPen(color="#e3b341", width=1.5, style=Qt.PenStyle.DashLine))
        self._curve_specs = [("Total", self.c_total, GREEN), ("Showdown", self.c_sd, ACCENT2),
                              ("Non-Showdown", self.c_nsd, RED), ("Vs. Villain", self.c_hero, "#b48ead"),
                              ("EV", self.c_ev, "#e3b341")]
        gl.addWidget(self.plot)

        # PT4-style hover crosshair — shows every visible curve's value at
        # the hand index under the cursor, live as the mouse moves.
        self.crosshair = HoverCrosshair(self.plot, self._curve_specs, value_formatter=self._format_value)

        # Same toggle-chip legend style as the Overview tab's graph, instead
        # of pyqtgraph's own built-in legend overlay — consistent look, and
        # lets each line be hidden individually.
        legend_row = QHBoxLayout()
        legend_row.setSpacing(18)
        for name, curve, color in self._curve_specs:
            cb = QCheckBox(name)
            cb.setChecked(True)
            cb.setCursor(Qt.CursorShape.PointingHandCursor)
            cb.setStyleSheet(f"""
                QCheckBox {{ background:{BG2}; color:{color}; font-size:11px; font-weight:600; spacing:6px; }}
                QCheckBox::indicator {{ width:12px; height:12px; border-radius:3px;
                    border:1.5px solid {color}; background:{BG3}; }}
                QCheckBox::indicator:checked {{ background:{color}; }}
            """)
            cb.toggled.connect(lambda checked, c=curve: c.setVisible(checked))
            legend_row.addWidget(cb)

        # $/BB toggle — same idea as the Overview graph's: swaps every
        # curve between its dollar series and its per-hand-big-blind-
        # normalized series, so mixed stakes still combine correctly.
        self._unit = '$'
        self._series = None
        self._xs = []
        self.unit_btn = QPushButton("BB")
        self.unit_btn.setFixedSize(38, 22)
        self.unit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.unit_btn.setToolTip("Switch the graph between $ and BB")
        self.unit_btn.setStyleSheet(f"""
            QPushButton {{ background:{BG3}; border:1px solid {BORDER}; border-radius:4px;
                font-size:11px; font-weight:700; color:{TEXT}; padding:0px; }}
            QPushButton:hover {{ background:{BG2}; border-color:{DIM}; }}
        """)
        self.unit_btn.clicked.connect(self._toggle_unit)
        legend_row.addWidget(self.unit_btn)
        legend_row.addStretch()
        gl.addLayout(legend_row)

        self.v_splitter.addWidget(gcard)

        # Exact hand-total label pinned at the end of the "Hands" axis — a
        # real floating widget, not a pyqtgraph tick, because pyqtgraph
        # silently drops the last tick's text when it's centered right on
        # the boundary (it would render partly outside the axis rect).
        self._last_hand_total = None
        self.hand_end_lbl = QLabel("", self.plot)
        self.hand_end_lbl.setStyleSheet(f"color:{DIM};font-size:10px;background:{BG2};padding:0 2px;")
        self.hand_end_lbl.hide()
        self.plot.installEventFilter(self)

        # Everything below (stat grid, vs-open, exploit notes, notes box) is
        # cheap QFrame/QLabel content — cleared and rebuilt per villain,
        # same as the legacy dashboard does for these specific sections.
        # Lives in its own scroll area so dragging the splitter handle down
        # to grow the graph doesn't just clip this section.
        below_scroll = QScrollArea()
        below_scroll.setWidgetResizable(True)
        below_scroll.setStyleSheet("QScrollArea{border:none;background:transparent;}")
        below_widget = QWidget()
        self.below = QVBoxLayout(below_widget)
        self.below.setContentsMargins(0, 10, 0, 0)
        self.below.setSpacing(16)
        below_scroll.setWidget(below_widget)
        self.v_splitter.addWidget(below_scroll)

        # Give the graph a real chunk of extra room by default (it used to
        # stay pinned near its initial pixel size while all extra window
        # height went to the stats/notes section below) — both panes now
        # share extra space instead of just the one below the graph, and
        # the graph starts noticeably taller. Still fully adjustable via
        # the splitter handle afterwards.
        self.v_splitter.setStretchFactor(0, 1)
        self.v_splitter.setStretchFactor(1, 1)
        self.v_splitter.setSizes([420, 480])
        clay.addWidget(self.v_splitter, 1)

        outer.addWidget(self.content, 1)

    def eventFilter(self, obj, event):
        if obj is self.plot and event.type() == QEvent.Type.Resize and self._last_hand_total is not None:
            self._position_hand_end_label(self._last_hand_total)
        return super().eventFilter(obj, event)

    def _position_hand_end_label(self, total):
        self._last_hand_total = total
        self.hand_end_lbl.setText(f"{total:,}")
        self.hand_end_lbl.adjustSize()
        pi = self.plot.getPlotItem()
        bottom_h = pi.getAxis('bottom').height()
        right_w = pi.getAxis('right').width()
        x = self.plot.width() - right_w - self.hand_end_lbl.width() - 4
        y = self.plot.height() - bottom_h + 2
        self.hand_end_lbl.move(max(0, int(x)), int(y))
        self.hand_end_lbl.show()
        self.hand_end_lbl.raise_()

    def _on_stat_clicked(self, stat):
        rows = hands_for_stat_query(self.db, self._current_name, stat['id'],
                                     self._current_d_from, self._current_d_to, self._current_stake)
        HandListDialog(rows, self.db, self._current_name, stat['label'], self.currency, parent=self).exec()

    def _clear_below(self):
        while self.below.count():
            item = self.below.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def show_villain(self, name, d_from=None, d_to=None, stake=None, pop_averages=None):
        self._pop_averages = pop_averages or {}
        self._current_name = name
        self._current_d_from, self._current_d_to, self._current_stake = d_from, d_to, stake
        self.run_async(
            lambda: (villain_stats_query(self.db, name, d_from, d_to, stake),
                      villain_graph_query(self.db, self.hero, name, d_from, d_to)),
            lambda result: self._render_villain(name, result),
            on_error=lambda msg: self._show_error(name, msg),
        )

    def show_villain_group(self, names, label, d_from=None, d_to=None, stake=None, pop_averages=None):
        """Same as show_villain, but pooled across a GROUP of villains (e.g.
        everyone currently tagged "Fish") — `label` is a display string, not
        a real player_name, so per-stat drill-down (which needs one real
        name) is disabled for this view rather than silently returning
        nothing."""
        self._pop_averages = pop_averages or {}
        self._current_name = label
        self._current_d_from, self._current_d_to, self._current_stake = d_from, d_to, stake
        self.run_async(
            lambda: (villain_group_stats_query(self.db, names, d_from, d_to, stake),
                      villain_group_graph_query(self.db, self.hero, names, d_from, d_to)),
            lambda result: self._render_villain(label, result, is_group=True),
            on_error=lambda msg: self._show_error(label, msg),
        )

    def _show_error(self, name, msg):
        self.placeholder.setText(f"Error loading {name}: {msg}")
        self.placeholder.show()
        self.content.hide()

    def _format_value(self, v):
        if self._unit == 'bb':
            return f"{v:+.2f} BB"
        return f"{self.currency}{v:+,.2f}"

    def _toggle_unit(self):
        self._unit = 'bb' if self._unit == '$' else '$'
        self.unit_btn.setText('$' if self._unit == 'bb' else 'BB')
        self._apply_unit()

    def _apply_unit(self):
        pi = self.plot.getPlotItem()
        pi.getAxis('right').setLabel('Profit (BB)' if self._unit == 'bb' else 'Profit ($)')

        series = self._series.get(self._unit) if self._series else None
        if series:
            self.c_total.setData(self._xs, series['total'])
            self.c_sd.setData(self._xs, series['sd'])
            self.c_nsd.setData(self._xs, series['nonsd'])
            self.c_hero.setData(self._xs, series['hero'])
            self.c_ev.setData(self._xs, series['ev'])
        else:
            for curve in (self.c_total, self.c_sd, self.c_nsd, self.c_hero, self.c_ev):
                curve.setData([], [])

    def _toggle_blur(self):
        self._name_blurred = not self._name_blurred
        if self._name_blurred:
            effect = QGraphicsBlurEffect()
            effect.setBlurRadius(10)
            self.name_lbl.setGraphicsEffect(effect)
            self.hide_btn.setText("Show")
            self.hide_btn.setToolTip("Reveal villain name")
        else:
            self.name_lbl.setGraphicsEffect(None)
            self.hide_btn.setText("Hide")
            self.hide_btn.setToolTip("Blur villain name")

    def _render_villain(self, name, result, is_group=False):
        self.placeholder.hide()
        self.content.show()
        (values, hand_count, vs_open, opp_counts), (graph, v_profit, hero_vs_profit) = result

        ptype, pcolor = classify_player(values.get('vpip'), values.get('pfr'), values.get('three_bet'), values.get('wtsd'))
        self.name_lbl.setText(name)
        self.type_lbl.setText(ptype)
        self.type_lbl.setStyleSheet(f"color:{pcolor};font-size:13px;font-weight:600;background:transparent;border:none;")
        v_col = GREEN if v_profit >= 0 else RED
        hero_col = GREEN if hero_vs_profit >= 0 else RED
        self.hands_lbl.setText(
            f"{hand_count:,} hands  ·  "
            f"Villain: <span style='color:{v_col}'>{self.currency}{v_profit:+,.2f}</span>  ·  "
            f"vs Villain: <span style='color:{hero_col}'>{self.currency}{hero_vs_profit:+,.2f}</span>")

        (xs, v_total, v_sd, v_nonsd, v_ev, hero_vs,
         v_total_bb, v_sd_bb, v_nonsd_bb, v_ev_bb, hero_vs_bb) = graph
        self._xs = xs
        if xs:
            self._series = {
                '$': {'total': v_total, 'sd': v_sd, 'nonsd': v_nonsd, 'ev': v_ev, 'hero': hero_vs},
                'bb': {'total': v_total_bb, 'sd': v_sd_bb, 'nonsd': v_nonsd_bb, 'ev': v_ev_bb, 'hero': hero_vs_bb},
            }
            self.plot.getPlotItem().vb.setXRange(xs[0], xs[-1], padding=0)
            self._position_hand_end_label(xs[-1])
        else:
            self._series = None
            self._last_hand_total = None
            self.hand_end_lbl.hide()
        self._apply_unit()

        self._clear_below()

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
                    _make_stat_card(stat, values.get(stat['id']), self._pop_averages,
                                     None if is_group else self._on_stat_clicked,
                                     sample_n=opp_counts.get(stat['id'])),
                    i // 6, i % 6)

            # Clickable header collapses/expands this category's stat grid.
            header_btn = QPushButton(f"▾  {category.upper()}")
            header_btn.setCheckable(True)
            header_btn.setChecked(True)
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
            self.below.addWidget(card_frame)

        # 3-bet/fold-vs-open-by-position section removed for now (per user
        # request) — vs_open is still computed and available in `result`
        # if this comes back later.

        leaks_frame = QFrame()
        leaks_frame.setObjectName("card")
        lfl = QVBoxLayout(leaks_frame)
        lfl.setContentsMargins(12, 12, 12, 12)
        lfl.setSpacing(8)
        lfl.addWidget(lbl("EXPLOIT NOTES", size=11, dim=True))
        for icon, title, advice in generate_leaks(values):
            row_w = QFrame()
            row_w.setStyleSheet(f"background:{BG3};border-radius:6px;border:none;")
            rl = QVBoxLayout(row_w)
            rl.setContentsMargins(12, 8, 12, 8)
            rl.setSpacing(2)
            rl.addWidget(lbl(f"{icon}  {title}", bold=True, size=12))
            rl.addWidget(lbl(advice, dim=True, size=11))
            lfl.addWidget(row_w)
        self.below.addWidget(leaks_frame)

        notes_frame = QFrame()
        notes_frame.setObjectName("card")
        nfl = QVBoxLayout(notes_frame)
        nfl.setContentsMargins(12, 12, 12, 12)
        nfl.setSpacing(6)
        nfl.addWidget(lbl("MY NOTES  (not saved between sessions yet)", size=11, dim=True))
        notes = QTextEdit()
        notes.setPlaceholderText("Add your own notes about this player...")
        notes.setMaximumHeight(70)
        nfl.addWidget(notes)
        self.below.addWidget(notes_frame)
        self.below.addStretch()


# Note: the real application entry point is ui/app_window.py's
# AppWindow/main() — this module now only provides VillainDetail (used by
# ui/population_tab.py) and its supporting widgets/helpers.
