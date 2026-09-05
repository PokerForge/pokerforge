"""Sessions tab: one row per (date, stakes) group hero played, matching
poker_dashboard_legacy.py's SessionsTab — a starting point to iterate on
once it's confirmed to look/behave the same as the legacy version."""
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem, QHeaderView

from ui.theme import lbl, GREEN, RED
from ui.async_worker import AsyncRunner
from ui.hand_list_dialog import HandListDialog
from database.queries import sessions_query, hands_for_session_query

COLUMNS = ["Date", "Stakes", "Hands", "Profit", "BB/100", "EV BB/100", "Hours"]


class SessionsTab(QWidget, AsyncRunner):
    def __init__(self):
        super().__init__()
        self._init_async()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(12)
        lay.addWidget(lbl("SESSIONS", size=11, dim=True))

        self.table = QTableWidget()
        self.table.setColumnCount(len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setToolTip("Double-click a session to see the hands played in it")
        self.table.doubleClicked.connect(self._on_double_click)
        lay.addWidget(self.table)

        self._currency = "£"
        self._db = None
        self._hero = None
        self._sessions = []

    def refresh(self, db, hero, d_from, d_to, currency="£", stake=None):
        self._currency = currency
        self._db = db
        self._hero = hero
        self.run_async(
            lambda: sessions_query(db, hero, d_from, d_to, stake),
            self._render,
        )

    def _on_double_click(self, index):
        session_date, stakes_label, hands, profit, bb100, ev_bb100, hours = self._sessions[index.row()]
        rows = hands_for_session_query(self._db, self._hero, session_date, stakes_label)
        label = f"{session_date} · {stakes_label or 'Unknown stakes'}"
        HandListDialog(rows, self._db, self._hero, label, self._currency, parent=self).exec()

    def _render(self, sessions):
        currency = self._currency
        self._sessions = sessions
        self.table.setRowCount(0)
        for d, stakes_label, hands, profit, bb100, ev_bb100, hours in sessions:
            r = self.table.rowCount()
            self.table.insertRow(r)
            vals = [
                (str(d), None),
                (stakes_label or "—", None),
                (f"{hands:,}", None),
                (f"{currency}{profit:+,.2f}", GREEN if profit >= 0 else RED),
                (f"{bb100:+.2f}", GREEN if bb100 >= 0 else RED),
                (f"{ev_bb100:+.2f}", GREEN if ev_bb100 >= 0 else RED),
                (f"{hours:.1f}h", None),
            ]
            for c, (val, color) in enumerate(vals):
                item = QTableWidgetItem(val)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if color:
                    item.setForeground(QColor(color))
                self.table.setItem(r, c, item)
            self.table.setRowHeight(r, 32)
