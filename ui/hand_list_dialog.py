"""Hand list shown when a stat card or a Sessions row is double-clicked —
every hand behind it, laid out PT4-style. Every derived column (Facing PF
Action, PF Act, F/T/R Act, Final Hand, Winner, Winning Hand) was validated
hand-by-hand against a real PT4 CSV export before this dialog was built —
see core/hand_display.py's docstrings. Double-click a row to open the
full hand in HandReplayDialog, same as before."""
from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QWidget, QLabel, QHeaderView, QPushButton, QComboBox,
)

from ui.theme import STYLE, GREEN, RED, TEXT, DIM, BORDER, lbl
from ui.hand_replayer import HandReplayDialog
from ui.csv_export import export_table_to_csv
from ui.range_grid import RangeGridPopup
from database.hand_loader import load_hands_bulk, load_hand
from core.position import assign_positions
from core.hand_display import (
    facing_and_pf_act, postflop_act, final_hand_text, winner_and_hand_text, to_native, SITE_LABELS,
)

ALL_POSITIONS_LABEL = "All Positions"

COLUMNS = [
    "Site", "Date", "Stake", "Won", "My C Won", "Final Hand", "Hole Cards",
    "Position", "Facing PF Action", "PF Act", "Flop", "F Act", "Turn", "T Act",
    "River", "R Act", "Winner", "Winning Hand", "Pot", "Pot (BB)", "Rake", "All-In Equity",
]
# Sized generously enough that nothing needs manual dragging open — widest
# real value in each column (e.g. "1 Raise & Caller(s)", "Straight, Jack
# High") was measured against this, not guessed. The card columns (Hole
# Cards/Flop/Turn/River) carry extra buffer on top of the badges' own
# footprint — see the item-padding override below for why.
COLUMN_WIDTHS = [
    110, 130, 90, 85, 85, 130, 80,
    65, 140, 55, 115, 55, 55, 55,
    55, 55, 120, 150, 85, 70, 75, 95,
]
_CARD_COLS = {6, 10, 12, 14}  # Hole Cards, Flop, Turn, River


def _pnl_color(v: float) -> str:
    """Green/red for an actual win or loss, dim for exactly zero — a
    folded-preflop-for-nothing hand isn't a "win", so it shouldn't read as
    one just because green means >= 0."""
    if abs(v) < 1e-9:
        return DIM
    return GREEN if v > 0 else RED

# Flat 4-color-deck badges for compact table cells — a smaller, simpler
# style than the replayer's gem-badge cards, which are sized for a table
# seat, not a dense grid of rows.
_SUIT_COLOR = {'♣': GREEN, '♦': "#388bfd", '♥': RED, '♠': TEXT}
_SUIT_TEXT = {'♠': "#0d1117"}


def _mini_card(card: str) -> QWidget:
    rank, suit = card[:-1], card[-1]
    bg = _SUIT_COLOR.get(suit, TEXT)
    fg = _SUIT_TEXT.get(suit, "white")
    badge = QLabel(f"{rank}{suit}")
    badge.setFixedSize(26, 20)
    badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
    badge.setStyleSheet(f"background:{bg};color:{fg};border-radius:3px;font-size:10px;font-weight:700;")
    return badge


def _card_row(cards: list[str]) -> QWidget:
    row = QWidget()
    row.setStyleSheet("background:transparent;")
    lay = QHBoxLayout(row)
    lay.setContentsMargins(2, 2, 2, 2)
    lay.setSpacing(2)
    for c in cards:
        lay.addWidget(_mini_card(c))
    lay.addStretch()
    return row


class HandListPanel(QWidget):
    """The hand-list body (heading + PT4-style table) on its own, reusable
    both inside HandListDialog's popup and embedded directly into a page
    (see StatsTab's By Position section, which shows this inline rather
    than as a separate window)."""

    def __init__(self, rows, db, subject_name: str, stat_label: str, currency: str = "$",
                 parent=None, embedded: bool = False):
        super().__init__(parent)
        # (hand_id, played_at, stakes_label, profit, ev)
        self.rows = sorted(rows, key=lambda r: r[1] or "", reverse=True)
        self.db = db
        self.subject_name = subject_name
        self.currency = currency
        self._embedded = embedded
        self._range_popup = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        header_row = QHBoxLayout()
        header_row.addWidget(lbl(f"{stat_label.upper()}  ·  {len(self.rows)} hands  ·  double-click to replay",
                                  size=11, dim=True))
        header_row.addStretch()

        header_row.addWidget(lbl("Position", dim=True, size=11))
        self.position_filter = QComboBox()
        self.position_filter.addItem(ALL_POSITIONS_LABEL)
        self.position_filter.currentTextChanged.connect(self._on_position_filter_changed)
        header_row.addWidget(self.position_filter)

        # Only meaningful once filtered to one position — a range grid
        # mixing every position together isn't really "a range" at all.
        self.range_btn = QPushButton("▦ Range Grid")
        self.range_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.range_btn.setToolTip(
            "Shows hole cards actually seen (not this player's true range — "
            "folded hands are never revealed) for the hands currently shown")
        self.range_btn.clicked.connect(self._on_range_toggle_clicked)
        self.range_btn.hide()
        header_row.addWidget(self.range_btn)

        export_btn = QPushButton("Export to CSV...")
        export_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        export_btn.clicked.connect(self._on_export_clicked)
        header_row.addWidget(export_btn)
        lay.addLayout(header_row)

        self.table = QTableWidget()
        self.table.setColumnCount(len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.doubleClicked.connect(self._on_double_click)
        # The app-wide QTableWidget::item padding (6px top/bottom, 12px
        # left/right, from ui/theme.py's global stylesheet) gets applied
        # by Qt's stylesheet-aware style to embedded CELL WIDGETS too, not
        # just text items — it was silently shrinking every card badge
        # cell to a fraction of the real column/row size (confirmed by
        # isolating the effect: the widget's actual geometry was exactly
        # the cell rect minus that padding on each side). This local
        # override on the table itself takes precedence for it alone.
        self.table.setStyleSheet(f"QTableWidget::item {{ padding: 3px 6px; border-bottom:1px solid {BORDER}; }}")
        # Column widths MUST be set before any setCellWidget() call — a
        # cell widget is sized to whatever the column's width is at the
        # moment it's inserted, and does not get resized retroactively
        # just because the column width changes afterward (that left the
        # card badges clipped to a sliver of their real size when this
        # was done in the other order).
        for col, w in enumerate(COLUMN_WIDTHS):
            self.table.setColumnWidth(col, w)
        lay.addWidget(self.table)

        self._populate()
        self._populate_position_filter()

        if self._embedded:
            # Embedded on a page (rather than filling a modal dialog), so
            # size to its own content — capped, since a position can have
            # thousands of hands — instead of either collapsing to a
            # sliver or stretching the whole page open.
            content_h = self.table.horizontalHeader().height() + len(self.rows) * 30 + 4
            self.table.setFixedHeight(min(max(content_h, 120), 520))

    def _populate(self):
        hand_ids = [r[0] for r in self.rows]
        hands = load_hands_bulk(self.db, hand_ids)
        self.table.setRowCount(len(self.rows))
        # Parallel to self.rows, indexed by table row — position and hole
        # cards are already computed below per row for display; caching
        # them here (rather than recomputing) is what lets the position
        # filter and range-grid popup work off already-loaded data with
        # no extra hand lookups.
        self._row_positions: list[str] = []
        self._row_hole_cards: list[list[str]] = []

        for row_i, (hand_id, played_at, stakes, profit, ev) in enumerate(self.rows):
            self.table.setRowHeight(row_i, 30)
            hand = hands.get(hand_id)
            if hand is None:
                item = QTableWidgetItem("(hand data unavailable)")
                self.table.setItem(row_i, 0, item)
                self._row_positions.append("—")
                self._row_hole_cards.append([])
                continue

            native = hand.native_currency or self.currency
            native_profit = to_native(profit, native)
            native_ev = to_native(ev, native) if ev is not None else None
            pot_native = to_native(hand.total_pot, native) if hand.total_pot is not None else None
            rake_native = to_native(hand.rake, native) if hand.rake is not None else None
            bb = hand.native_big_blind or hand.big_blind

            player = next((p for p in hand.players if p.name == self.subject_name), None)
            position = assign_positions(hand).get(self.subject_name, "—")
            facing, pf_act = facing_and_pf_act(hand, self.subject_name)
            f_act = postflop_act(hand, self.subject_name, 'FLOP')
            t_act = postflop_act(hand, self.subject_name, 'TURN')
            r_act = postflop_act(hand, self.subject_name, 'RIVER')
            final_hand = final_hand_text(hand, self.subject_name)
            winner, winning_hand = winner_and_hand_text(hand)
            played = played_at[:16].replace("T", " ") if played_at else "—"
            site = SITE_LABELS.get(hand.source, hand.source or "—")

            board = hand.board
            flop_cards = board[:3] if len(board) >= 3 else []
            turn_cards = [board[3]] if len(board) >= 4 else []
            river_cards = [board[4]] if len(board) >= 5 else []
            hole_cards = player.hole_cards if player else []
            self._row_positions.append(position)
            self._row_hole_cards.append(hole_cards)

            texts = {
                0: site, 1: played, 2: stakes or "—",
                3: f"{native}{native_profit:+,.2f}",
                4: f"{self.currency}{profit:+,.2f}",
                5: final_hand,
                7: position,
                8: facing or "—",
                9: pf_act,
                11: f_act, 13: t_act, 15: r_act,
                16: winner or "—",
                17: winning_hand,
                18: f"{native}{pot_native:,.2f}" if pot_native is not None else "—",
                19: str(round(pot_native / bb)) if pot_native is not None and bb else "—",
                20: f"{native}{rake_native:,.2f}" if rake_native is not None else "—",
                21: f"{native}{native_ev:+,.2f}" if native_ev is not None else "",
            }
            colors = {
                3: _pnl_color(native_profit),
                4: _pnl_color(profit),
                21: _pnl_color(native_ev) if native_ev is not None else None,
            }
            for col, text in texts.items():
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                color = colors.get(col)
                if color:
                    item.setForeground(QColor(color))
                self.table.setItem(row_i, col, item)

            for col, cards in ((6, hole_cards), (10, flop_cards), (12, turn_cards), (14, river_cards)):
                if cards:
                    self.table.setCellWidget(row_i, col, _card_row(cards))

    def _populate_position_filter(self):
        distinct = sorted({p for p in self._row_positions if p and p != "—"})
        self.position_filter.blockSignals(True)
        self.position_filter.clear()
        self.position_filter.addItem(ALL_POSITIONS_LABEL)
        self.position_filter.addItems(distinct)
        self.position_filter.blockSignals(False)

    def _on_position_filter_changed(self, selected: str):
        self._close_range_popup()
        if selected == ALL_POSITIONS_LABEL:
            for row_i in range(self.table.rowCount()):
                self.table.setRowHidden(row_i, False)
            self.range_btn.hide()
        else:
            for row_i, position in enumerate(self._row_positions):
                self.table.setRowHidden(row_i, position != selected)
            self.range_btn.show()

    def _visible_rows(self) -> list[int]:
        return [r for r in range(self.table.rowCount()) if not self.table.isRowHidden(r)]

    def _close_range_popup(self):
        if self._range_popup is not None:
            self._range_popup.close()
            self._range_popup = None

    def _on_range_toggle_clicked(self):
        if self._range_popup is not None:
            self._close_range_popup()
            return

        visible = self._visible_rows()
        hole_card_pairs = [
            tuple(self._row_hole_cards[r]) for r in visible if len(self._row_hole_cards[r]) == 2
        ]
        popup = RangeGridPopup(hole_card_pairs, len(hole_card_pairs), len(visible), parent=self)
        pos = self.range_btn.mapToGlobal(QPoint(0, self.range_btn.height()))
        popup.move(pos)
        popup.show()
        self._range_popup = popup

    def _on_double_click(self, index):
        hand_id = self.rows[index.row()][0]
        hand = load_hand(self.db, hand_id)
        if hand is not None:
            HandReplayDialog(hand, self.subject_name, parent=self).exec()

    def _on_export_clicked(self):
        export_table_to_csv(self.table, self, default_filename="hands.csv")


class HandListDialog(QDialog):
    """Popup-window wrapper around HandListPanel — used everywhere the hand
    list is a one-off lookup (Sessions, Leaks, villain profile drill-down)
    rather than embedded inline on the page."""

    def __init__(self, rows, db, subject_name: str, stat_label: str, currency: str = "$", parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{stat_label} — {len(rows)} hands")
        self.setStyleSheet(STYLE)
        self.resize(1500, 640)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.addWidget(HandListPanel(rows, db, subject_name, stat_label, currency, parent=self))
