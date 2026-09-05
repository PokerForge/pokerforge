"""Overview tab: hero's own profit graph + top-line stat row. Visually
mirrors poker_dashboard_legacy.py's OverviewTab, minus the EV line/stat
(no all-in equity calculator exists yet — see project notes)."""
import pyqtgraph as pg
from PyQt6.QtCore import Qt, QEvent
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFrame, QCheckBox, QLabel,
    QScrollArea, QSplitter, QPushButton,
)

from ui.hero_overview import OVERVIEW_STATS
from database.queries import hero_overview_query, hands_for_stat_query, DRILLDOWN_STAT_IDS
from ui.theme import lbl, BG2, GREEN, RED, ORANGE, TEXT, ACCENT2, BG3, DIM, BORDER, hand_axis_ticks
from ui.async_worker import AsyncRunner
from ui.hand_list_dialog import HandListDialog
from ui.main_window import _ClickableFrame
from ui.graph_overlay import DraggableStatsBox, ScreenshotButton, HoverCrosshair


class OverviewTab(QWidget, AsyncRunner):
    def __init__(self):
        super().__init__()
        self._init_async()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(16)

        # Graph and stats sit in a vertical splitter (same mechanism as the
        # villain profile panel) so the graph can be dragged taller.
        self.v_splitter = QSplitter(Qt.Orientation.Vertical)
        self.v_splitter.setHandleWidth(6)

        top_card = QWidget()
        top_lay = QVBoxLayout(top_card)
        top_lay.setContentsMargins(0, 0, 0, 0)
        top_lay.setSpacing(16)

        self.plot = pg.PlotWidget()
        self.plot.setMinimumHeight(280)
        self.plot.setBackground(BG2)
        self.plot.showGrid(x=True, y=True, alpha=0.15)
        pi = self.plot.getPlotItem()
        pi.hideAxis('left')
        pi.showAxis('right')
        pi.getAxis('right').linkToView(pi.vb)
        pi.getAxis('right').setLabel('Profit')
        pi.getAxis('bottom').setLabel('Hands')
        pi.vb.setMouseEnabled(x=False, y=False)
        pi.vb.enableAutoRange(axis='x', enable=False)
        pi.setMenuEnabled(False)
        # Leaves a sliver of breathing room below the "Hands" axis label
        # instead of it being cut off flush against the plot's edge.
        pi.layout.setContentsMargins(0, 0, 0, 10)
        zero_line = pg.InfiniteLine(pos=0, angle=0, pen=pg.mkPen(color="#8b949e", width=1.2))
        pi.addItem(zero_line)

        self.c_total = self.plot.plot(pen=pg.mkPen(color=GREEN, width=2.5))
        self.c_sd = self.plot.plot(pen=pg.mkPen(color=ACCENT2, width=1.5))
        self.c_nsd = self.plot.plot(pen=pg.mkPen(color=RED, width=1.5))
        self.c_ev = self.plot.plot(pen=pg.mkPen(color="#e3b341", width=1.5, style=Qt.PenStyle.DashLine))
        self._curve_specs = [("Total", self.c_total, GREEN), ("Showdown", self.c_sd, ACCENT2),
                              ("Non-Showdown", self.c_nsd, RED), ("EV", self.c_ev, "#e3b341")]

        # Header row — section label + camera button that grabs the plot
        # and puts it on the clipboard, so it can be pasted elsewhere
        # without a separate screenshot tool.
        header_row = QHBoxLayout()
        header_row.setSpacing(8)
        header_row.addWidget(lbl("Personal Results", size=15, bold=True))
        self.screenshot_btn = ScreenshotButton(self.plot)
        header_row.addWidget(self.screenshot_btn)
        header_row.addStretch()
        top_lay.addLayout(header_row)

        top_lay.addWidget(self.plot)

        # Exact hand-total label pinned at the end of the "Hands" axis — a
        # real floating widget, not a pyqtgraph tick, because pyqtgraph
        # silently drops the last tick's text when it's centered right on
        # the boundary (it would render partly outside the axis rect).
        self._last_hand_total = None
        self.hand_end_lbl = QLabel("", self.plot)
        self.hand_end_lbl.setStyleSheet(f"color:{DIM};font-size:10px;background:{BG2};padding:0 2px;")
        self.hand_end_lbl.hide()

        # PT4-style movable summary box, floating over the plot.
        self.stats_box = DraggableStatsBox(self.plot)
        self.stats_box.set_row("hands", "Hands: —")
        self.stats_box.set_row("won", "Won: —", color=GREEN)
        self.stats_box.set_row("ev", "EV: —", color="#e3b341")
        self.stats_box.set_row("bb100", "BB/100: —", color=GREEN)
        self.stats_box.set_row("ev_bb100", "EV BB/100: —", color="#e3b341")

        # PT4-style hover crosshair — shows every visible curve's value at
        # the hand index under the cursor, live as the mouse moves.
        self.crosshair = HoverCrosshair(self.plot, self._curve_specs, value_formatter=self._format_value)

        self.plot.installEventFilter(self)

        legend_row = QHBoxLayout()
        legend_row.setSpacing(18)
        for name, curve, color in self._curve_specs:
            cb = QCheckBox(name)
            cb.setChecked(True)
            cb.setCursor(Qt.CursorShape.PointingHandCursor)
            cb.setStyleSheet(f"""
                QCheckBox {{ color:{color}; font-size:11px; font-weight:600; spacing:6px; }}
                QCheckBox::indicator {{ width:12px; height:12px; border-radius:3px;
                    border:1.5px solid {color}; background:{BG3}; }}
                QCheckBox::indicator:checked {{ background:{color}; }}
            """)
            cb.toggled.connect(lambda checked, c=curve: c.setVisible(checked))
            if name == "Total":
                cb.toggled.connect(lambda checked: (
                    self.stats_box.set_row_visible("won", checked),
                    self.stats_box.set_row_visible("bb100", checked)))
            elif name == "EV":
                cb.toggled.connect(lambda checked: (
                    self.stats_box.set_row_visible("ev", checked),
                    self.stats_box.set_row_visible("ev_bb100", checked)))
            legend_row.addWidget(cb)

        # $/BB toggle — swaps every curve between its dollar series and its
        # per-hand-big-blind-normalized series (same idea as the bb100
        # stat, just as a running total instead of a per-100 rate), so
        # mixed stakes still combine correctly. Label always names the
        # unit a click will switch TO, not the one currently showing.
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
        legend_w = QWidget()
        legend_w.setLayout(legend_row)
        top_lay.addWidget(legend_w)

        self.v_splitter.addWidget(top_card)

        below_scroll = QScrollArea()
        below_scroll.setWidgetResizable(True)
        below_scroll.setStyleSheet("QScrollArea{border:none;background:transparent;}")
        below_widget = QWidget()
        below_lay = QVBoxLayout(below_widget)
        below_lay.setContentsMargins(0, 10, 0, 0)
        below_lay.setSpacing(16)
        below_lay.addWidget(lbl("STATS", size=11, dim=True))
        grid_w = QWidget()
        self.grid = QGridLayout(grid_w)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(10)
        below_lay.addWidget(grid_w)
        below_lay.addStretch()
        below_scroll.setWidget(below_widget)
        self.v_splitter.addWidget(below_scroll)

        # Unlike the villain profile panel (where the stats/notes section
        # below should soak up extra space), here the chart is the main
        # attraction — it should claim the lion's share of any extra room
        # the window has, while the stat cards stay close to their natural
        # size.
        self.v_splitter.setStretchFactor(0, 1)
        self.v_splitter.setStretchFactor(1, 0)
        self.v_splitter.setSizes([620, 300])
        lay.addWidget(self.v_splitter, 1)

        self.cards = {}
        self._currency = "£"
        self._db, self._hero, self._d_from, self._d_to, self._stake = None, None, None, None, None
        for i, spec in enumerate(OVERVIEW_STATS):
            key = spec[1]
            drillable = key in DRILLDOWN_STAT_IDS
            card = _ClickableFrame() if drillable else QFrame()
            card.setObjectName("card")
            if drillable:
                card.setCursor(Qt.CursorShape.PointingHandCursor)
                card.setToolTip("Click to see the hands behind this stat")
                card.clicked.connect(lambda k=key, label=spec[0]: self._on_stat_clicked(k, label))
            cl = QVBoxLayout(card)
            cl.setContentsMargins(10, 8, 10, 8)
            cl.setSpacing(2)
            cl.addWidget(lbl(spec[0], size=10, dim=True))
            val_lbl = lbl("—", size=16, bold=True)
            cl.addWidget(val_lbl)
            self.cards[key] = val_lbl
            self.grid.addWidget(card, i // 6, i % 6)

    def _on_stat_clicked(self, stat_id, stat_label):
        rows = hands_for_stat_query(self._db, self._hero, stat_id, self._d_from, self._d_to, self._stake)
        HandListDialog(rows, self._db, self._hero, stat_label, self._currency, parent=self).exec()

    def eventFilter(self, obj, event):
        if obj is self.plot and event.type() == QEvent.Type.Resize:
            if self._last_hand_total is not None:
                self._position_hand_end_label(self._last_hand_total)
            self.stats_box._resize_and_place()
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

    def refresh(self, db, hero, d_from, d_to, currency="£", stake=None):
        self._currency = currency
        self._db, self._hero, self._d_from, self._d_to, self._stake = db, hero, d_from, d_to, stake
        self.run_async(
            lambda: hero_overview_query(db, hero, d_from, d_to, stake),
            self._render,
        )

    def _render(self, result):
        values, graph = result
        currency = getattr(self, '_currency', '£')

        for spec in OVERVIEW_STATS:
            label, key, kind = spec[0], spec[1], spec[2]
            v = values.get(key)
            card = self.cards[key]
            if v is None:
                card.setText("—")
                card.setStyleSheet(f"color:{TEXT};font-size:16px;font-weight:700;background:transparent;border:none;")
                continue
            if kind == "int":
                text, color = f"{int(v):,}", TEXT
            elif kind == "money":
                text, color = f"{currency}{v:+,.2f}", (GREEN if v >= 0 else RED)
            elif kind == "signed":
                text, color = f"{v:+.2f}", (GREEN if v >= 0 else RED)
            else:  # pct
                lo, hi = (spec[3], spec[4]) if len(spec) > 4 else (None, None)
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
                text = f"{v:.2f}%"
            card.setText(text)
            card.setStyleSheet(f"color:{color};font-size:16px;font-weight:700;background:transparent;border:none;")

        hands = values.get('hands') or 0
        bb100 = values.get('bb100')
        ev_bb100 = values.get('ev_bb100')
        self.stats_box.set_row("hands", f"Hands: {hands:,}")
        if bb100 is not None:
            self.stats_box.set_row("bb100", f"BB/100: {bb100:+.2f}", color=GREEN if bb100 >= 0 else RED)
        if ev_bb100 is not None:
            self.stats_box.set_row("ev_bb100", f"EV BB/100: {ev_bb100:+.2f}", color=GREEN if ev_bb100 >= 0 else RED)

        xs, total, sd, nonsd, ev_line, total_bb, sd_bb, nonsd_bb, ev_bb_line = graph
        self._xs = xs
        if xs:
            self._series = {
                '$': {'total': total, 'sd': sd, 'nonsd': nonsd, 'ev': ev_line if ev_line else None},
                'bb': {'total': total_bb, 'sd': sd_bb, 'nonsd': nonsd_bb, 'ev': ev_bb_line if ev_bb_line else None},
            }
            self.plot.getPlotItem().vb.setXRange(xs[0], xs[-1], padding=0)
            self.plot.getPlotItem().getAxis('bottom').setTicks(hand_axis_ticks(xs[-1]))
            self._position_hand_end_label(xs[-1])
        else:
            self._series = None
            self._last_hand_total = None
            self.hand_end_lbl.hide()
            # No data yet (e.g. a brand-new install with nothing imported)
            # — without an explicit range, pyqtgraph's auto-range defaults
            # to roughly (0, 1) and labels the "Hands" axis in fractions
            # (0.1, 0.2, ...), which reads oddly for a hand count.
            self.plot.getPlotItem().vb.setXRange(0, 1, padding=0)
            self.plot.getPlotItem().getAxis('bottom').setTicks(hand_axis_ticks(0))
        self._apply_unit()

    def _format_value(self, v):
        if self._unit == 'bb':
            return f"{v:+.2f} BB"
        return f"{getattr(self, '_currency', '£')}{v:+,.2f}"

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
            if series['ev'] is not None:
                self.c_ev.setData(self._xs, series['ev'])
            else:
                self.c_ev.setData([], [])
        else:
            self.c_total.setData([], [])
            self.c_sd.setData([], [])
            self.c_nsd.setData([], [])
            self.c_ev.setData([], [])

        won = series['total'][-1] if series else None
        if won is not None:
            self.stats_box.set_row("won", f"Won: {self._format_value(won)}", color=GREEN if won >= 0 else RED)
        else:
            self.stats_box.set_row("won", "Won: —", color=DIM)

        ev_final = series['ev'][-1] if series and series['ev'] else None
        if ev_final is not None:
            self.stats_box.set_row("ev", f"EV: {self._format_value(ev_final)}", color=GREEN if ev_final >= 0 else RED)
            self.stats_box.set_row_visible("ev", True)
        elif series is not None:
            self.stats_box.set_row("ev", "EV: n/a (too many hands)", color=DIM)
        else:
            self.stats_box.set_row("ev", "EV: —", color=DIM)
