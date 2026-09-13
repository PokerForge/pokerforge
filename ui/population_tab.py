"""Population tab: sortable villain pool table (search, player-type filter,
min-hand filter) + full stat-card profile panel — matches the layout of
poker_dashboard_legacy.py's PopulationTab."""
import html

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QLineEdit, QComboBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QPushButton,
)

from ui.main_window import VillainDetail
from ui.population_averages import compute_population_averages
from ui.population_summary import PopulationRow
from ui.player_classify import classify_player
from ui.theme import ACCENT2, BG3, GREEN, RED, lbl
from ui.async_worker import AsyncRunner
from ui.csv_export import export_table_to_csv
from database.queries import population_summary_query

MIN_HAND_OPTIONS = [("Min 1 hand", 1), ("Min 10 hands", 10), ("Min 50 hands", 50),
                    ("Min 100 hands", 100), ("Min 200 hands", 200)]
TYPE_OPTIONS = ["All Players", "Fish \U0001f41f", "Regs \U0001f3af", "Nits \U0001f9ca",
                "LAG \U0001f525", "Calling Station \U0001f4de"]
_TYPE_CHECK = {
    "Fish \U0001f41f": lambda p: "Fish" in p,
    "Regs \U0001f3af": lambda p: "Reg" in p,
    "Nits \U0001f9ca": lambda p: "Nit" in p,
    "LAG \U0001f525": lambda p: "LAG" in p,
    "Calling Station \U0001f4de": lambda p: "Calling" in p,
}

COLUMNS = ["Player", "Hands", "Profit", "VPIP", "PFR", "3Bet", "Fold 3-Bet", "WWSF"]

_POOLED_FIELDS = [
    'hands', 'vpip_pfr_opp', 'vpip', 'pfr', 'three_bet_opp', 'three_bet',
    'faced_3bet_opp', 'folded_to_3bet', 'reached_showdown', 'saw_flop',
    'won_saw_flop', 'total_profit',
]


def _pooled_row(label: str, rows: list) -> PopulationRow:
    """Sums raw counts across every row in the group and derives percentages
    from those pooled totals — NOT an average of each villain's own
    percentage, which would misweight low-hand-count villains just as
    heavily as high-volume ones (the same pooled-stats lesson from this
    app's accuracy work applies here)."""
    pooled = PopulationRow(label)
    for r in rows:
        for field in _POOLED_FIELDS:
            setattr(pooled, field, getattr(pooled, field) + getattr(r, field))
    return pooled


class PopulationTab(QWidget, AsyncRunner):
    def __init__(self, hero, db, currency="£"):
        super().__init__()
        self._init_async()
        self.hero = hero
        self.db = db
        self.currency = currency
        self._d_from = self._d_to = self._stake = None
        # Populated by the first refresh() call, which AppWindow makes
        # immediately after construction — no point computing this twice
        # (once here unfiltered, once again filtered a moment later).
        self.rows = {}
        self.pop_averages = {}
        self._selected = None
        self._selected_is_group = False
        self._sort_col = None
        self._sort_asc = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(6)

        left = QWidget()
        left.setMinimumWidth(320)
        ll = QVBoxLayout(left)
        ll.setContentsMargins(20, 20, 8, 20)
        ll.setSpacing(10)
        pool_header = QHBoxLayout()
        pool_header.addWidget(lbl("VILLAIN POOL", size=11, dim=True))
        pool_header.addStretch()
        export_btn = QPushButton("Export to CSV...")
        export_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        export_btn.clicked.connect(lambda: export_table_to_csv(self.table, self, default_filename="villain_pool.csv"))
        pool_header.addWidget(export_btn)
        ll.addLayout(pool_header)

        self.search = QLineEdit()
        self.search.setPlaceholderText("\U0001f50d  Search player name...")
        self.search.textChanged.connect(self._filter)
        ll.addWidget(self.search)

        frow = QHBoxLayout()
        frow.setSpacing(8)
        self.type_cb = QComboBox()
        self.type_cb.addItems(TYPE_OPTIONS)
        self.type_cb.currentTextChanged.connect(self._filter)
        frow.addWidget(self.type_cb)
        self.minhand_cb = QComboBox()
        self.minhand_cb.addItems([label for label, _ in MIN_HAND_OPTIONS])
        self.minhand_cb.currentTextChanged.connect(self._filter)
        frow.addWidget(self.minhand_cb)
        ll.addLayout(frow)

        self.table = QTableWidget()
        self.table.setColumnCount(len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        header = self.table.horizontalHeader()
        for c in range(len(COLUMNS)):
            header.setSectionResizeMode(c, QHeaderView.ResizeMode.Interactive)
        for c, w in enumerate([130, 62, 95, 72, 68, 68, 92, 72]):
            self.table.setColumnWidth(c, w)
        header.setStretchLastSection(True)
        header.setSortIndicatorShown(True)
        header.sectionClicked.connect(self._on_header_clicked)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.cellClicked.connect(self._on_select)
        ll.addWidget(self.table)
        splitter.addWidget(left)

        self.detail = VillainDetail(hero, db, currency)
        splitter.addWidget(self.detail)

        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        # A little wider by default so more of the villain pool's columns
        # are visible without scrolling on first open — still fully
        # adjustable via the splitter handle afterwards.
        splitter.setSizes([560, 760])
        outer.addWidget(splitter)

        self._filter()

    def _visible_rows(self):
        text = self.search.text().lower()
        min_h = dict(MIN_HAND_OPTIONS)[self.minhand_cb.currentText()]
        type_sel = self.type_cb.currentText()
        checker = _TYPE_CHECK.get(type_sel)

        result = []
        for r in self.rows.values():
            if text and text not in r.name.lower():
                continue
            if r.hands < min_h:
                continue
            if checker:
                ptype, _ = classify_player(r.vpip_pct, r.pfr_pct, r.three_bet_pct, r.wtsd_pct)
                if not checker(ptype):
                    continue
            result.append(r)
        return result

    def _group_label_and_names(self, rows):
        """`rows` = the currently-filtered (search+minhand+type) individual
        rows. Returns (label, names) for the pinned combined summary row,
        or (None, None) if no type filter is active — "All Players" has no
        single tag to combine into one row."""
        type_sel = self.type_cb.currentText()
        if type_sel == "All Players" or not rows:
            return None, None
        return f"◆ All {type_sel} ({len(rows)})", [r.name for r in rows]

    def _filter(self, _text=None):
        rows = self._visible_rows()
        rows = self._apply_sort(rows)
        label, names = self._group_label_and_names(rows)
        combined = _pooled_row(label, rows) if label else None
        self._populate(rows, combined, names)

    def _apply_sort(self, rows):
        if self._sort_col is None:
            return sorted(rows, key=lambda r: -r.hands)
        key_fns = {
            0: lambda r: r.name.lower(),
            1: lambda r: r.hands,
            2: lambda r: r.total_profit,
            3: lambda r: r.vpip_pct if r.vpip_pct is not None else -1,
            4: lambda r: r.pfr_pct if r.pfr_pct is not None else -1,
            5: lambda r: r.three_bet_pct if r.three_bet_pct is not None else -1,
            6: lambda r: r.fold_3bet_pct if r.fold_3bet_pct is not None else -1,
            7: lambda r: r.wwsf_pct if r.wwsf_pct is not None else -1,
        }
        fn = key_fns.get(self._sort_col)
        if not fn:
            return rows
        return sorted(rows, key=fn, reverse=not self._sort_asc)

    def _on_header_clicked(self, col):
        if self._sort_col == col:
            self._sort_asc = not self._sort_asc
        else:
            self._sort_col = col
            self._sort_asc = False
        order = Qt.SortOrder.AscendingOrder if self._sort_asc else Qt.SortOrder.DescendingOrder
        self.table.horizontalHeader().setSortIndicator(col, order)
        self._filter()

    def _populate(self, rows, combined=None, combined_names=None):
        # setUpdatesEnabled(False) + setRowCount(len(rows)) once up front,
        # instead of insertRow() per row — with "All Time" selected this
        # table can hold 7,000+ villains, and Qt was doing a full
        # layout/repaint pass on every single insertRow()/setItem() call,
        # which dwarfed the actual (sub-3-second) database query time.
        all_rows = ([combined] if combined is not None else []) + rows
        self.table.setUpdatesEnabled(False)
        try:
            self.table.setRowCount(len(all_rows))
            for row_i, r in enumerate(all_rows):
                is_combined = combined is not None and r is combined

                def fmt(x):
                    return f"{x}%" if x is not None else "—"
                values = [r.name, f"{r.hands:,}", f"{self.currency}{r.total_profit:+,.2f}",
                          fmt(r.vpip_pct), fmt(r.pfr_pct),
                          fmt(r.three_bet_pct), fmt(r.fold_3bet_pct), fmt(r.wwsf_pct)]
                for c, val in enumerate(values):
                    item = QTableWidgetItem(val)
                    if c == 0:
                        item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                        item.setToolTip(html.escape(r.name))
                        # Carries the pooled member-name list for the click
                        # handler — None for a normal, single-villain row.
                        item.setData(Qt.ItemDataRole.UserRole, combined_names if is_combined else None)
                    else:
                        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    if c == 2:
                        item.setForeground(QColor(GREEN if r.total_profit >= 0 else RED))
                    elif is_combined:
                        item.setForeground(QColor(ACCENT2))
                    if is_combined:
                        font = item.font()
                        font.setBold(True)
                        item.setFont(font)
                        item.setBackground(QColor(BG3))
                    self.table.setItem(row_i, c, item)
                self.table.setRowHeight(row_i, 34)
        finally:
            self.table.setUpdatesEnabled(True)

    def _on_select(self, row, _col):
        name_item = self.table.item(row, 0)
        if not name_item:
            return
        name = name_item.text()
        group_names = name_item.data(Qt.ItemDataRole.UserRole)
        self._selected = name
        self._selected_is_group = bool(group_names)
        if group_names:
            self.detail.show_villain_group(group_names, name, self._d_from, self._d_to, self._stake, self.pop_averages)
        else:
            self.detail.show_villain(name, self._d_from, self._d_to, self._stake, self.pop_averages, self.rows)

    def refresh(self, d_from, d_to, stake=None):
        """Re-filter to the given period (and optional stake) and rebuild
        the villain pool — a fast indexed SQL query (database/queries.py)
        instead of a Python re-walk of raw hand actions."""
        self._d_from, self._d_to, self._stake = d_from, d_to, stake
        self.run_async(
            lambda: population_summary_query(self.db, self.hero, d_from, d_to, stake),
            self._on_refreshed,
        )

    def _on_refreshed(self, rows):
        self.rows = rows
        self.pop_averages = compute_population_averages(self.rows)
        self._filter()
        if self._selected_is_group:
            # The combined row isn't a real stored villain — re-derive its
            # (possibly changed) membership for the new period instead of
            # looking it up in self.rows.
            visible = self._apply_sort(self._visible_rows())
            label, names = self._group_label_and_names(visible)
            if label:
                self.detail.show_villain_group(names, label, self._d_from, self._d_to, self._stake, self.pop_averages)
            else:
                self._selected = None
                self._selected_is_group = False
        elif self._selected and self._selected in self.rows:
            self.detail.show_villain(self._selected, self._d_from, self._d_to, self._stake,
                                      self.pop_averages, self.rows)
        elif self._selected:
            self._selected = None
