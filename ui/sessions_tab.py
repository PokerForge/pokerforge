"""Sessions tab: one row per (date, stakes) group hero played, matching
poker_dashboard_legacy.py's SessionsTab — a starting point to iterate on
once it's confirmed to look/behave the same as the legacy version.

Cash and Tournament are two different tables sharing this same
QTableWidget (reconfigured — Qt allows changing column count/headers on
an existing table at any time) — toggled by the global $/T switch in
the filter bar (see ui/game_type_toggle.py), not a separate tab. In
Tournament mode this becomes the results table (one row per tournament,
double-click to log or edit its finish/payout via
ui/log_tournament_result_dialog.py — no hand-history export contains
either)."""
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem, QHeaderView, QPushButton,
)

from ui.theme import lbl, GREEN, RED, DIM
from ui.async_worker import AsyncRunner
from ui.hand_list_dialog import HandListDialog
from ui.csv_export import export_table_to_csv
from ui.pdf_export import export_table_to_pdf
from ui.tilt_report_dialog import TiltReportDialog
from ui.log_tournament_result_dialog import LogTournamentResultDialog
from ui.sites import site_label
from database.queries import sessions_query, hands_for_session_query, tournament_list_query

CASH_COLUMNS = ["Date", "Stakes", "Hands", "Profit", "BB/100", "EV BB/100", "Hours"]
TOURNAMENT_COLUMNS = ["Date", "Site", "Tournament", "Hands", "Buy-in", "Field", "Finish", "Payout", "ROI", "Result"]


class SessionsTab(QWidget, AsyncRunner):
    def __init__(self):
        super().__init__()
        self._init_async()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(12)

        header_row = QHBoxLayout()
        header_row.addWidget(lbl("SESSIONS", size=11, dim=True))
        header_row.addStretch()
        export_btn = QPushButton("Export to CSV...")
        export_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        export_btn.clicked.connect(lambda: export_table_to_csv(self.table, self, default_filename="sessions.csv"))
        header_row.addWidget(export_btn)
        export_pdf_btn = QPushButton("Export to PDF...")
        export_pdf_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        export_pdf_btn.setToolTip("A printable summary — for your own tax/accounting records")
        export_pdf_btn.clicked.connect(self._on_export_pdf)
        header_row.addWidget(export_pdf_btn)
        self.tilt_btn = QPushButton("Tilt Report...")
        self.tilt_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.tilt_btn.setToolTip("Does your VPIP shift in the minutes after a big loss?")
        self.tilt_btn.clicked.connect(self._on_tilt_report_clicked)
        header_row.addWidget(self.tilt_btn)
        lay.addLayout(header_row)

        # Explains an otherwise-bare table when the current filter (not the
        # whole account) matches zero sessions/tournaments — see _render.
        self.empty_state_lbl = lbl("", dim=True)
        self.empty_state_lbl.setWordWrap(True)
        self.empty_state_lbl.hide()
        lay.addWidget(self.empty_state_lbl)

        self.table = QTableWidget()
        self.table.setColumnCount(len(CASH_COLUMNS))
        self.table.setHorizontalHeaderLabels(CASH_COLUMNS)
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
        self._rows = []
        self._d_from = None
        self._d_to = None
        self._stake = None
        self._site = None
        self._session_type = 'cash'

    def refresh(self, db, hero, d_from, d_to, currency="£", stake=None, site=None, session_type='cash'):
        self._currency = currency
        self._db = db
        self._hero = hero
        self._d_from = d_from
        self._d_to = d_to
        self._stake = stake
        self._site = site
        self._session_type = session_type
        self.tilt_btn.setVisible(session_type == 'cash')  # doesn't apply to tournaments
        if session_type == 'tournament':
            self.table.setToolTip("Double-click a row to log or edit its finish and payout")
            self.run_async(
                lambda: tournament_list_query(db, hero, d_from, d_to, site),
                self._render_tournament,
            )
        else:
            self.table.setToolTip("Double-click a session to see the hands played in it")
            self.run_async(
                lambda: sessions_query(db, hero, d_from, d_to, stake, site),
                self._render_cash,
            )

    def _on_export_pdf(self):
        if self._session_type == 'tournament':
            total_hands = sum(r['hand_count'] for r in self._rows)
            subtitle = (
                f"{self._hero}  ·  {self._d_from} to {self._d_to}  ·  "
                f"{len(self._rows)} tournament(s)  ·  {total_hands:,} hands")
            title, filename = "PokerForge Tournament Summary", "tournament_summary.pdf"
        else:
            total_hands = sum(s[2] for s in self._sessions)
            total_profit = sum(s[3] for s in self._sessions)
            subtitle = (
                f"{self._hero}  ·  {self._d_from} to {self._d_to}  ·  "
                f"{len(self._sessions)} session(s)  ·  {total_hands:,} hands  ·  "
                f"{self._currency}{total_profit:+,.2f}"
            )
            title, filename = "PokerForge Session Summary", "session_summary.pdf"
        export_table_to_pdf(self.table, self, title=title, subtitle=subtitle, default_filename=filename)

    def _on_tilt_report_clicked(self):
        TiltReportDialog(self._db, self._hero, self._d_from, self._d_to,
                          self._stake, self._site, parent=self).exec()

    def _on_double_click(self, index):
        if self._session_type == 'tournament':
            self._on_log_result_clicked(self._rows[index.row()])
            return
        session_date, stakes_label, hands, profit, bb100, ev_bb100, hours = self._sessions[index.row()]
        rows = hands_for_session_query(self._db, self._hero, session_date, stakes_label, self._site)
        label = f"{session_date} · {stakes_label or 'Unknown stakes'}"
        HandListDialog(rows, self._db, self._hero, label, self._currency, parent=self).exec()

    def _render_cash(self, sessions):
        currency = self._currency
        self._sessions = sessions
        if not sessions and self._db is not None and self._db.hand_count() > 0:
            self.empty_state_lbl.setText(
                "No sessions match the current Period / Stakes / Site filter — try widening it.")
            self.empty_state_lbl.show()
        else:
            self.empty_state_lbl.hide()
        self.table.setColumnCount(len(CASH_COLUMNS))
        self.table.setHorizontalHeaderLabels(CASH_COLUMNS)
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

    def _render_tournament(self, rows):
        self._rows = rows
        if not rows and self._db is not None and self._db.hand_count() > 0:
            self.empty_state_lbl.setText(
                "No tournament hands match the current Period / Site filter — try widening it.")
            self.empty_state_lbl.show()
        else:
            self.empty_state_lbl.hide()
        self.table.setColumnCount(len(TOURNAMENT_COLUMNS))
        self.table.setHorizontalHeaderLabels(TOURNAMENT_COLUMNS)
        self.table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            cur = row['currency'] or self._currency
            buy_in = row['buy_in'] or 0.0
            fee = row['fee'] or 0.0
            is_logged = row['payout'] is not None
            date_str = (row['last_played_at'] or "")[:10]
            finish_text = str(row['finish_position']) if row['finish_position'] else "—"
            payout_text = f"{cur}{row['payout']:,.2f}" if is_logged else "—"
            roi_text, roi_color = "—", None
            if is_logged and (buy_in + fee) > 0:
                roi = 100.0 * (row['payout'] - buy_in - fee) / (buy_in + fee)
                roi_text = f"{roi:+.0f}%"
                roi_color = GREEN if roi >= 0 else RED

            vals = [
                (date_str, None),
                (site_label(row['source']), None),
                (row['tournament_id'], None),
                (f"{row['hand_count']:,}", None),
                (f"{cur}{buy_in:,.2f}", None),
                (str(row['field_size']) if row['field_size'] else "—", None),
                (finish_text, None),
                (payout_text, GREEN if is_logged and row['payout'] > 0 else None),
                (roi_text, roi_color),
                ("Edit ✎" if is_logged else "Log Result ›", DIM if is_logged else None),
            ]
            for c, (text, color) in enumerate(vals):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if color:
                    item.setForeground(QColor(color))
                self.table.setItem(r, c, item)
            self.table.setRowHeight(r, 32)

    def _on_log_result_clicked(self, row):
        existing = None
        if row['payout'] is not None:
            existing = (row['finish_position'], row['field_size'], row['payout'], row['currency'])
        dlg = LogTournamentResultDialog(
            row['tournament_id'], row['buy_in'], row['fee'], self._currency, existing, parent=self)
        if dlg.exec():
            finish, field, payout = dlg.result_values()
            self._db.set_tournament_result(row['tournament_id'], finish, field, payout, self._currency)
            self.refresh(self._db, self._hero, self._d_from, self._d_to, self._currency,
                         self._stake, self._site, self._session_type)
