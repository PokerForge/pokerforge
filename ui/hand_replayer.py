"""Animated hand replayer: an oval table with seats positioned
around it, hole cards revealed as the hand progresses, a running pot/board,
step-by-step or auto-play controls, and a text action log — built directly
from the already-parsed Hand/Player/Action data rather than re-parsing raw
text (the one exception is the showdown hand-description text, e.g. "Full
House, Tens full of Queens", which the site's hand history carries as free
text on the "Shows"/"Mucks" line and which nothing in models.hand stores
separately — that's pulled from Hand.raw_text with a small regex rather than
re-deriving it with a hand evaluator, since the site's own text is already
authoritative).
"""
import html
import math
import re

from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer
from PyQt6.QtGui import (
    QBrush, QColor, QFontMetrics, QLinearGradient, QPainter, QPainterPath,
    QPen, QRadialGradient,
)
from PyQt6.QtWidgets import (
    QDialog, QFrame, QGraphicsOpacityEffect,
    QHBoxLayout, QLabel, QPushButton, QTextEdit, QVBoxLayout, QWidget,
)

from core.position import assign_positions
from models.hand import Hand
from ui.theme import ACCENT2, BG3, BORDER, DIM, GREEN, RED, STYLE, TEXT, YELLOW, lbl

_STREET_BOARD_COUNT = {'FLOP': 3, 'TURN': 4, 'RIVER': 5}
_POS_COLOR = {'BTN': YELLOW, 'BTN/SB': YELLOW, 'SB': ACCENT2, 'BB': RED}

_SHOW_RE = re.compile(
    r"^(?P<name>.+?): (?:Shows|Mucks) \[(?P<c1>\w+) (?P<c2>\w+)\](?:\s+(?P<desc>.+))?$", re.MULTILINE)


def _extract_show_descriptions(raw_text: str | None) -> dict[str, str]:
    out = {}
    if not raw_text:
        return out
    for m in _SHOW_RE.finditer(raw_text):
        if m['desc']:
            out[m['name']] = m['desc'].strip()
    return out


def _fmt_bb(amount: float, big_blind: float | None) -> str:
    """Every amount — stacks, pot, and action sizes alike — is shown in big
    blinds rather than currency, which is the readable convention for a
    replayer and avoids picking a currency symbol per hand's (possibly
    mixed GBP/EUR) native stakes."""
    if not big_blind:
        return f"{amount:.2f}"
    return f"{amount / big_blind:.2f} BB"


def _action_label(action: str, amount: float | None, big_blind: float | None) -> str:
    amt = _fmt_bb(amount, big_blind) if amount is not None else None
    if action == 'Post SB':
        return f"posts small blind {amt}"
    if action == 'Post BB':
        return f"posts big blind {amt}"
    if action == 'Fold':
        return "folds"
    if action == 'Check':
        return "checks"
    if action == 'Call':
        return f"calls {amt}"
    if action == 'Bet':
        return f"bets {amt}"
    if action == 'Raise':
        return f"raises to {amt}"
    if action == 'Allin':
        return f"is all-in {amt}"
    return action


def _build_events(hand: Hand) -> list[dict]:
    """Flattens the hand into a chronological list of replay steps. Each
    action/uncalled step carries a 'delta' — the actual chips that moved
    at that step — which the dialog re-sums on every render to get the
    pot and each seat's remaining stack at that point. Action.amount for
    a Raise is the ABSOLUTE new total for that street (not the increment),
    so the per-street committed total is tracked here to recover the real
    delta, mirroring the same convention already validated in core/stats.py.
    """
    events = []
    committed: dict[str, float] = {}
    current_street = None
    for a in hand.actions:
        if a.street != current_street:
            current_street = a.street
            committed = {}
            if current_street in _STREET_BOARD_COUNT:
                n = _STREET_BOARD_COUNT[current_street]
                events.append({'kind': 'street', 'street': current_street, 'board': hand.board[:n]})

        prior = committed.get(a.player, 0.0)
        if a.action == 'Raise':
            new_total = a.amount if a.amount is not None else prior
            delta = new_total - prior
            committed[a.player] = new_total
            display_amount = new_total
        elif a.action == 'Uncalled Return':
            delta = -(a.amount or 0.0)
            committed[a.player] = prior + delta
            display_amount = a.amount
        elif a.action in ('Post SB', 'Post BB', 'Call', 'Bet', 'Allin'):
            delta = a.amount or 0.0
            committed[a.player] = prior + delta
            display_amount = a.amount
        else:  # Fold, Check
            delta = 0.0
            display_amount = None

        events.append({
            'kind': 'uncalled' if a.action == 'Uncalled Return' else 'action',
            'player': a.player, 'action': a.action, 'amount': display_amount, 'delta': delta,
        })

    show_desc = _extract_show_descriptions(hand.raw_text)
    hole_cards = {p.name: p.hole_cards for p in hand.players}
    for name, desc in show_desc.items():
        if hole_cards.get(name):
            events.append({'kind': 'show', 'player': name, 'cards': hole_cards[name], 'desc': desc})
    for name, amount in hand.winnings.items():
        if amount:
            events.append({'kind': 'win', 'player': name, 'amount': amount})
    return events


def _card_widget(card: str) -> QWidget:
    """A small playing-card face: rank stacked over the suit pip in the
    corner-index style real cards use, rather than a flat rank+suit run of
    text. No QGraphicsDropShadowEffect here — nesting multiple graphics
    effects (this + the seat's own opacity effect, several siblings deep in
    a subtree whose children get rebuilt via deleteLater()) turned out to
    silently fail to composite for some seats and not others, an unreliable
    Qt/PyQt effect-stacking issue rather than anything about the specific
    hand. Depth comes from the border/gradient alone instead.

    Style is a "gem badge" (glossy rounded-square tile, bold rank letter,
    small sparkle accent). Where the usual treatment is a flat color per
    PLAYER, which drops suit information entirely, this keeps suit info by
    using a distinct gradient per suit instead, via child-widget
    positioning (not a layout) so the rank stays exactly centered
    regardless of font size.
    """
    rank, suit = card[:-1], card[-1]
    light, dark = _CARD_GRADIENT.get(suit, _CARD_GRADIENT['♠'])
    tile = QWidget()
    tile.setFixedSize(_CARD_W, _CARD_H)
    tile.setStyleSheet(
        f"background:qlineargradient(x1:0,y1:0,x2:0.7,y2:1,stop:0 {light},stop:1 {dark});"
        f"border:1px solid rgba(0,0,0,90);border-radius:8px;")

    rank_lbl = QLabel(rank, tile)
    rank_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    rank_lbl.setGeometry(0, 0, _CARD_W, _CARD_H)
    rank_lbl.setStyleSheet("background:transparent;border:none;color:white;"
                            "font-size:28px;font-weight:800;")

    # The corner accent is the card's OWN suit glyph, not a generic sparkle —
    # color alone shouldn't be the only thing distinguishing suits.
    suit_lbl = QLabel(suit, tile)
    suit_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    suit_lbl.setGeometry(_CARD_W - 15, 2, 13, 13)
    suit_lbl.setStyleSheet("background:transparent;border:none;"
                            "color:rgba(255,255,255,210);font-size:10px;")
    return tile


class _CardBackWidget(QWidget):
    """Face-down placeholder for a player still live in the hand (dealt in,
    not yet folded or revealed) — a diamond crosshatch lattice, the closest
    of the options tried to a real casino card back. Drawn directly rather
    than styled via QSS, since a repeating diagonal pattern isn't
    expressible as a gradient."""
    def __init__(self):
        super().__init__()
        self.setFixedSize(_CARD_W, _CARD_H)
        # Without this, Qt fills the widget's full rectangular bounds with
        # an opaque background before paintEvent runs, so the small corner
        # slivers outside the rounded clip path (very visible where two
        # flush cards touch, since each one's curve pulls away right at the
        # shared edge) showed up as solid squared-off patches.
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(0, 0, _CARD_W, _CARD_H)
        path = QPainterPath()
        path.addRoundedRect(rect, 8, 8)
        painter.setClipPath(path)
        painter.fillRect(self.rect(), QColor("#1c2230"))
        painter.setPen(QPen(QColor(255, 255, 255, 35), 1))
        step = 7
        for x in range(-_CARD_H, _CARD_W + _CARD_H, step):
            painter.drawLine(x, 0, x + _CARD_H, _CARD_H)
            painter.drawLine(x, _CARD_H, x + _CARD_H, 0)
        painter.setClipping(False)
        painter.setPen(QPen(QColor(0, 0, 0, 90), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), 8, 8)


def _card_back_widget() -> QWidget:
    return _CardBackWidget()


# A real playing card is roughly 2.5:3.5 (~0.71 width/height) — the previous
# 52x52 square badge read as "kinda square" rather than card-shaped.
_CARD_W = 42
_CARD_H = 58
_CARD_SPACING = 0
_CARD_GRADIENT = {
    '♥': ('#ff6b6b', '#c62828'),
    '♦': ('#5b9dff', '#1a56c4'),
    '♣': ('#4fd17a', '#1f7a3f'),
    '♠': ('#7a8290', '#3a3f47'),
}


class _CardRow(QWidget):
    """A row of card widgets that can be cleared and repopulated in place —
    shared by each seat's hole cards and the board display. Children are
    positioned with plain move() rather than a QHBoxLayout: Qt's box layouts
    don't honor a negative setSpacing() (it silently falls back to a small
    positive default instead), which made a tight/overlapping fan of cards
    unreachable through the layout API. Sizing is computed directly from the
    known, fixed per-card dimensions for the same reason _resync_size always
    has — relying on sizeHint() after this widget has already been shown
    once is unreliable (Qt's cached value doesn't always reflect children
    added/removed a moment earlier)."""
    def __init__(self):
        super().__init__()
        self._n = 0
        self._tiles: list[QWidget] = []
        self._resync_size()

    def _clear(self):
        for tile in self._tiles:
            tile.deleteLater()
        self._tiles = []

    def _resync_size(self):
        w = self._n * _CARD_W + max(self._n - 1, 0) * _CARD_SPACING
        self.setFixedSize(w, _CARD_H if self._n else 0)

    def _lay_out(self, widgets: list[QWidget]):
        self._n = len(widgets)
        self._tiles = widgets
        self._resync_size()
        for i, w in enumerate(widgets):
            w.setParent(self)
            w.move(i * (_CARD_W + _CARD_SPACING), 0)
            w.show()

    def show_cards(self, cards: list[str]):
        self._clear()
        self._lay_out([_card_widget(c) for c in cards])

    def show_backs(self, n: int = 2):
        self._clear()
        self._lay_out([_card_back_widget() for _ in range(n)])

    def clear_cards(self):
        self._clear()
        self._n = 0
        self._resync_size()


class SeatWidget(QWidget):
    """A floating name/stack pill with its cards shown ABOVE it once
    revealed — a badge hovering over the seat, rather than tucked inside
    a bordered card alongside the name.

    Cards and pill are positioned manually (not via a QVBoxLayout) because
    Qt's box layouts don't honor negative setSpacing() — it silently falls
    back to a default positive gap — so overlapping the cards onto the
    pill's top edge needs direct move()/geometry control instead."""
    # Gap (px) between the cards' bottom edge and the pill's top edge — 0
    # means they sit flush, touching with no overlap and no visible gap.
    PILL_OVERLAP = 0

    def __init__(self, name: str, stack: float, big_blind: float | None, position: str | None, is_hero: bool):
        super().__init__()
        self.big_blind = big_blind
        self.setFixedSize(176, 124)

        self.pill = QFrame(self)
        self.pill.setObjectName("pill")
        self._base_style = (
            f"QFrame#pill{{background:rgba(20,22,26,200);border:1.5px solid rgba(255,255,255,25);"
            f"border-radius:9px;}}")
        self.pill.setStyleSheet(self._base_style)

        lay = QVBoxLayout(self.pill)
        lay.setContentsMargins(9, 6, 9, 6)
        lay.setSpacing(1)

        top = QHBoxLayout()
        top.setSpacing(4)
        name_color = ACCENT2 if is_hero else TEXT
        name_lbl = QLabel()
        # Plain text, not Qt's default AutoText — `name` comes straight out
        # of a hand-history file, and a crafted name shouldn't be able to
        # render as fake bold/formatted UI (see ui/theme.py's lbl() for the
        # same fix on every other name label in the app).
        name_lbl.setTextFormat(Qt.TextFormat.PlainText)
        name_lbl.setStyleSheet(f"background:transparent;border:none;font-size:12px;"
                                f"font-weight:700;color:{name_color};")
        name_lbl.setFixedWidth(104)
        metrics = QFontMetrics(name_lbl.font())
        name_lbl.setText(metrics.elidedText(name, Qt.TextElideMode.ElideRight, 104))
        name_lbl.setToolTip(html.escape(name))
        top.addWidget(name_lbl)
        if position:
            pc = _POS_COLOR.get(position, DIM)
            pos_lbl = QLabel(position)
            pos_lbl.setStyleSheet(f"background:transparent;border:1px solid {pc};border-radius:4px;"
                                   f"color:{pc};font-size:9px;font-weight:700;padding:0px 4px;")
            top.addWidget(pos_lbl)
        top.addStretch()
        lay.addLayout(top)

        self.stack_lbl = QLabel(_fmt_bb(stack, big_blind))
        self.stack_lbl.setStyleSheet(f"background:transparent;border:none;color:{DIM};font-size:11px;")
        lay.addWidget(self.stack_lbl)

        self.status_lbl = QLabel("")
        self.status_lbl.setStyleSheet(f"background:transparent;border:none;color:{DIM};font-size:11px;")
        lay.addWidget(self.status_lbl)

        # Read once, right after building the pill's contents and before it
        # is ever shown — sizeHint() is only unreliable once a widget has
        # already been displayed and its layout mutated afterward.
        pill_h = self.pill.sizeHint().height()
        self.pill_height = pill_h
        self.pill.setFixedSize(176, pill_h)
        self.pill.move(0, self.height() - pill_h)

        # No face-down placeholders — nothing is shown for a seat until it
        # actually reveals cards at showdown, rather than a generic card back.
        self.cards = _CardRow()
        self.cards.setParent(self)
        self._reposition_cards()

        self._opacity = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._opacity)

    def _reposition_cards(self):
        cards_bottom = (self.height() - self.pill_height) + self.PILL_OVERLAP
        cards_top = cards_bottom - self.cards.height()
        cx = (self.width() - self.cards.width()) // 2
        self.cards.move(cx, cards_top)

    def set_stack(self, amount: float):
        self.stack_lbl.setText(_fmt_bb(amount, self.big_blind))

    def set_active(self, active: bool):
        border = f"2px solid {ACCENT2}" if active else "1.5px solid rgba(255,255,255,25)"
        self.pill.setStyleSheet(
            f"QFrame#pill{{background:rgba(20,22,26,200);border:{border};border-radius:9px;}}")

    def set_folded(self, folded: bool):
        self._opacity.setOpacity(0.4 if folded else 1.0)

    def set_status(self, text: str, color: str | None = None):
        self.status_lbl.setText(text)
        self.status_lbl.setStyleSheet(f"background:transparent;border:none;color:{color or DIM};font-size:11px;")

    def set_winner(self, amount: float):
        self.pill.setStyleSheet(
            f"QFrame#pill{{background:rgba(20,22,26,200);border:2px solid {GREEN};border-radius:9px;}}")
        self.set_status(f"wins {_fmt_bb(amount, self.big_blind)}", GREEN)

    def show_cards(self, cards: list[str]):
        self.cards.show_cards(cards)
        self._reposition_cards()

    def show_backs(self):
        self.cards.show_backs(2)
        self._reposition_cards()

    def clear_cards(self):
        self.cards.clear_cards()
        self._reposition_cards()


# (max_bb, layer_count, color) — bet size in big blinds picks both how
# many chips are in the stack and their color, the way a real chip stack
# gets taller and switches denominations for a bigger bet rather than
# always being one same-looking chip.
_CHIP_TIERS = [
    (0.75, 1, "#e8e8ec"),   # white — small blind
    (1.5, 1, "#3fae52"),    # green — big blind
    (4.0, 2, "#2f6fd1"),    # blue — opens/RFI
    (10.0, 3, "#2b2d31"),   # black — 3-bets/cbets
    (25.0, 4, "#8a4fd1"),   # purple — 4-bets/big bets
    (float('inf'), 5, "#d13f3f"),  # red — huge bets/all-ins
]
_CHIP_DISC = 15
_CHIP_STACK_OFFSET = 4


def _chip_tier(bb_amount: float) -> tuple[int, str]:
    for max_bb, count, color in _CHIP_TIERS:
        if bb_amount < max_bb:
            return count, color
    return _CHIP_TIERS[-1][1], _CHIP_TIERS[-1][2]


def _chip_disc(color: str) -> QLabel:
    """One chip, edge striped like a real casino chip (alternating color/
    white wedges) rather than a flat-filled circle."""
    d = QLabel()
    d.setFixedSize(_CHIP_DISC, _CHIP_DISC)
    d.setStyleSheet(
        f"background:qconicalgradient(cx:0.5,cy:0.5,angle:0,"
        f"stop:0 {color},stop:0.12 white,stop:0.25 {color},stop:0.37 white,"
        f"stop:0.5 {color},stop:0.62 white,stop:0.75 {color},stop:0.87 white,stop:1 {color});"
        f"border:1.5px solid rgba(0,0,0,150);border-radius:{_CHIP_DISC // 2}px;")
    return d


class ChipStack(QWidget):
    """N overlapping chip discs stacked with a vertical offset, positioned
    directly (not via a layout) since they're meant to overlap."""
    def __init__(self):
        super().__init__()
        self._discs: list[QLabel] = []
        self._set_count_color(1, _CHIP_TIERS[0][2])

    def _set_count_color(self, count: int, color: str):
        for d in self._discs:
            d.deleteLater()
        self._discs = []
        height = _CHIP_DISC + _CHIP_STACK_OFFSET * (count - 1)
        self.setFixedSize(_CHIP_DISC, height)
        for i in range(count):
            d = _chip_disc(color)
            d.setParent(self)
            d.move(0, height - _CHIP_DISC - i * _CHIP_STACK_OFFSET)
            d.show()
            self._discs.append(d)


class BetChip(QWidget):
    """A poker-chip stack + amount, shown on the felt between a player's
    seat and the pot for their CURRENT STREET's total commitment — the same
    "chips out in front of you" convention, separate from the
    pill's own running stack total. Sizes itself explicitly (like
    _CardRow) rather than via layout sizeHint(), for the same reason."""
    def __init__(self):
        super().__init__()
        self._lay = QHBoxLayout(self)
        self._lay.setContentsMargins(0, 0, 0, 0)
        self._lay.setSpacing(4)
        self.stack = ChipStack()
        self._lay.addWidget(self.stack, alignment=Qt.AlignmentFlag.AlignBottom)
        self.label = QLabel()
        self.label.setStyleSheet("background:transparent;border:none;color:#f2f2f2;"
                                  "font-size:11px;font-weight:700;")
        self._lay.addWidget(self.label, alignment=Qt.AlignmentFlag.AlignBottom)
        self.hide()

    def set_amount(self, text: str, bb_amount: float):
        count, color = _chip_tier(bb_amount)
        self.stack._set_count_color(count, color)
        self.label.setText(text)
        metrics = QFontMetrics(self.label.font())
        text_w = metrics.horizontalAdvance(text) + 2
        self.label.setFixedWidth(text_w)
        self.label.setFixedHeight(_CHIP_DISC)
        self.setFixedSize(_CHIP_DISC + 4 + text_w, self.stack.height())
        self.show()

    def clear(self):
        self.hide()


class TableWidget(QWidget):
    """Owns the seats AND the pot/board display, both positioned in the
    center of the oval — the conventional layout, where the pot total and the
    community cards sit inside the table graphic itself rather than below
    it as a separate row."""
    def __init__(self, hand: Hand, hero: str):
        super().__init__()
        self.big_blind = hand.big_blind
        self.setMinimumSize(640, 380)
        positions = assign_positions(hand)
        self.seat_widgets: dict[str, SeatWidget] = {}
        self.bet_chips: dict[str, BetChip] = {}
        self._angles: dict[str, float] = {}
        self._order = [p.name for p in sorted(hand.players, key=lambda p: p.seat or 0)]
        n = max(len(self._order), 1)
        for i, name in enumerate(self._order):
            self._angles[name] = math.pi / 2 + 2 * math.pi * i / n

        for p in hand.players:
            is_hero = p.name == hero
            sw = SeatWidget(p.name, p.stack or 0.0, hand.big_blind, positions.get(p.name), is_hero)
            sw.setParent(self)
            if is_hero and p.hole_cards:
                sw.show_cards(p.hole_cards)
            else:
                # Everyone seated was dealt in — show face-down until they
                # fold (cards disappear) or reveal at showdown.
                sw.show_backs()
            self.seat_widgets[p.name] = sw
            chip = BetChip()
            chip.setParent(self)
            self.bet_chips[p.name] = chip

        # Dealer button — a small marker sitting just inside whoever holds
        # the BTN (or BTN/SB heads-up) seat, as a chip-style "D".
        self.dealer_name = next((n for n, pos in positions.items() if pos in ('BTN', 'BTN/SB')), None)
        self.dealer_btn = QLabel("D")
        self.dealer_btn.setParent(self)
        self.dealer_btn.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.dealer_btn.setFixedSize(22, 22)
        self.dealer_btn.setStyleSheet(
            "background:qradialgradient(cx:0.35,cy:0.3,radius:0.9,"
            "stop:0 #fff6d8,stop:0.4 #e3b341,stop:1 #a67a1a);"
            "border:1px solid #6b5013;border-radius:11px;"
            "color:#3a2a05;font-size:11px;font-weight:800;")
        self.dealer_btn.setVisible(self.dealer_name is not None)

        self.pot_lbl = QLabel("Pot: —")
        self.pot_lbl.setParent(self)
        self.pot_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pot_lbl.setStyleSheet(f"background:transparent;border:none;color:{GREEN};"
                                    f"font-size:14px;font-weight:700;")
        # setFixedWidth alone leaves the height at Qt's default (unsized,
        # never-shown) 480px, so the AlignCenter text painted far below
        # where move() below puts the label's top-left corner — overlapping
        # whichever seat's pill happens to sit near the table's center.
        self.pot_lbl.setFixedSize(200, 24)

        self.board = _CardRow()
        self.board.setParent(self)

        self._reposition()

    def resizeEvent(self, event):
        self._reposition()
        super().resizeEvent(event)

    def _ellipse_params(self):
        w, h = max(self.width(), 640), max(self.height(), 380)
        # ry leaves enough headroom that the topmost seat's floating cards
        # (which extend ~82px above its own anchor point) never get clipped
        # by this widget's own top edge.
        return w / 2, h / 2, w / 2 - 95, h / 2 - 92

    def _reposition(self):
        cx, cy, rx, ry = self._ellipse_params()
        for name, angle in self._angles.items():
            x = cx + rx * math.cos(angle) - 88
            # The pill (the seat's real visual anchor) sits at the BOTTOM of
            # its fixed-size widget, so bias the placement up by roughly the
            # card-reveal space rather than centering the whole tall box.
            y = cy + ry * math.sin(angle) - 78
            self.seat_widgets[name].move(int(x), int(y))
        self.pot_lbl.move(int(cx - self.pot_lbl.width() / 2), int(cy - 40))
        self._reposition_board()
        self._reposition_bets()
        self._reposition_dealer_button()

    def _reposition_board(self):
        cx, cy, _, _ = self._ellipse_params()
        self.board.move(int(cx - self.board.width() / 2), int(cy - 10))

    def _reposition_bets(self):
        # Chips sit partway between each seat and the pot — close enough to
        # the seat to read as "theirs", but clearly out on the felt.
        cx, cy, rx, ry = self._ellipse_params()
        for name, angle in self._angles.items():
            sx, sy = cx + rx * math.cos(angle), cy + ry * math.sin(angle)
            bx, by = cx + (sx - cx) * 0.55, cy + (sy - cy) * 0.55
            chip = self.bet_chips[name]
            chip.move(int(bx - chip.width() / 2), int(by - chip.height() / 2))

    def _reposition_dealer_button(self):
        if self.dealer_name is None:
            return
        cx, cy, rx, ry = self._ellipse_params()
        # Offset the angle (not just pulled closer along the same radius) so
        # the button sits BESIDE the seat's own bet-chip line instead of
        # colliding with it when that seat posts/calls/raises.
        angle = self._angles[self.dealer_name] + 0.5
        sx, sy = cx + rx * math.cos(angle), cy + ry * math.sin(angle)
        bx, by = cx + (sx - cx) * 0.62, cy + (sy - cy) * 0.62
        self.dealer_btn.move(int(bx - self.dealer_btn.width() / 2), int(by - self.dealer_btn.height() / 2))

    def update_pot(self, text: str):
        self.pot_lbl.setText(text)

    def update_bets(self, committed: dict[str, float]):
        for name, chip in self.bet_chips.items():
            amount = committed.get(name, 0.0)
            if amount > 1e-9:
                bb_amount = amount / self.big_blind if self.big_blind else 0.0
                chip.set_amount(_fmt_bb(amount, self.big_blind), bb_amount)
            else:
                chip.clear()
        self._reposition_bets()

    def update_board(self, cards: list[str]):
        if cards:
            self.board.show_cards(cards)
        else:
            self.board.clear_cards()
        self._reposition_board()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        mx, my = 130, 85
        rail_rect = QRectF(mx - 16, my - 16, max(w - 2 * mx + 32, 10), max(h - 2 * my + 32, 10))
        felt_rect = QRectF(mx, my, max(w - 2 * mx, 10), max(h - 2 * my, 10))
        radius = felt_rect.height() / 2

        # Wooden rail behind the felt — a stadium shape (flat top/bottom,
        # rounded ends) rather than a plain ellipse, as a real table is.
        rail_grad = QLinearGradient(rail_rect.topLeft(), rail_rect.bottomLeft())
        rail_grad.setColorAt(0.0, QColor("#5a3a24"))
        rail_grad.setColorAt(0.5, QColor("#3d2717"))
        rail_grad.setColorAt(1.0, QColor("#2a1a0f"))
        painter.setBrush(QBrush(rail_grad))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(rail_rect, radius + 16, radius + 16)

        # Felt — a radial gradient (lighter center, darker rim) instead of a
        # flat fill, so the table reads with some depth rather than looking
        # like a solid color shape.
        felt_grad = QRadialGradient(felt_rect.center(), felt_rect.width() / 1.4)
        felt_grad.setColorAt(0.0, QColor("#2d6b3f"))
        felt_grad.setColorAt(0.7, QColor("#1f4f2d"))
        felt_grad.setColorAt(1.0, QColor("#153a20"))
        painter.setBrush(QBrush(felt_grad))
        painter.setPen(QPen(QColor("#0e2716"), 2))
        painter.drawRoundedRect(felt_rect, radius, radius)

        # A faint inner highlight ring gives the felt a subtle "lip" instead
        # of a hard single-color edge.
        inner = felt_rect.adjusted(6, 6, -6, -6)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(255, 255, 255, 18), 1.5))
        painter.drawRoundedRect(inner, inner.height() / 2, inner.height() / 2)


class HandReplayDialog(QDialog):
    """Replays one hand, or steps through a whole SEQUENCE of hands
    (Previous/Next Hand, distinct from the existing action-stepping
    ◀/▶ transport controls) — e.g. every hand behind one range-grid cell
    (ui/range_grid.py). `hand` is still the primary argument for the
    single-hand case every existing caller uses; pass `hand_list` (with
    `hand` as its first element) to enable the extra navigation row."""

    def __init__(self, hand: Hand, hero: str, parent=None,
                 hand_list: list[Hand] | None = None, start_index: int = 0):
        super().__init__(parent)
        self.hero = hero
        self.hand_list = hand_list if hand_list is not None else [hand]
        self.hand_index = start_index if hand_list is not None else 0
        self.idx = -1
        self.playing = False
        self.table = None

        self.setStyleSheet(STYLE)
        self.resize(980, 760)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._step_forward)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(10)

        self.hand_nav_label = None
        if len(self.hand_list) > 1:
            nav_row = QHBoxLayout()
            nav_row.setSpacing(8)
            self.hand_nav_prev_btn = QPushButton("◀ Previous Hand")
            self.hand_nav_prev_btn.clicked.connect(self._go_prev_hand)
            nav_row.addWidget(self.hand_nav_prev_btn)
            self.hand_nav_label = lbl("", size=12, bold=True)
            nav_row.addWidget(self.hand_nav_label)
            self.hand_nav_next_btn = QPushButton("Next Hand ▶")
            self.hand_nav_next_btn.clicked.connect(self._go_next_hand)
            nav_row.addWidget(self.hand_nav_next_btn)
            nav_row.addStretch()
            outer.addLayout(nav_row)

        self.header = lbl("", size=12, dim=True)
        self.header.setWordWrap(True)
        outer.addWidget(self.header)

        self._table_slot = QVBoxLayout()
        self._table_slot.setContentsMargins(0, 0, 0, 0)
        outer.addLayout(self._table_slot, 1)

        # Bottom row: log on the left, playback + street controls stacked
        # on the right — rather than the log spanning full width with
        # controls in their own row below, which wasted horizontal space.
        bottom = QHBoxLayout()
        bottom.setSpacing(12)

        # A plain light box rather than a dark QTextEdit: the action log
        # is dense reference text, and reads better on a light ground even
        # though the rest of the app is dark.
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(100)
        self.log.setStyleSheet(
            "QTextEdit{background:#f4f4f2;color:#1b1b1b;border:1px solid #8a8a86;"
            "border-radius:3px;padding:6px;font-size:12px;}")
        bottom.addWidget(self.log, 1)

        controls = QVBoxLayout()
        controls.setSpacing(6)

        media_row = QHBoxLayout()
        media_row.setSpacing(6)
        media_style = (
            "QPushButton{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #6b6f76,stop:1 #4a4d52);"
            "color:#e8e8e8;border:1px solid #34363a;border-radius:18px;font-size:14px;font-weight:600;padding:0;}"
            "QPushButton:hover{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #797d85,stop:1 #55585d);}"
            "QPushButton:pressed{background:#3d3f43;}")
        self.btn_first = QPushButton("⏮")
        self.btn_prev = QPushButton("◀")
        self.btn_playpause = QPushButton("▶")
        self.btn_next = QPushButton("▶")
        self.btn_last = QPushButton("⏭")
        for b in (self.btn_first, self.btn_prev, self.btn_playpause, self.btn_next, self.btn_last):
            b.setFixedSize(36, 36)
            b.setStyleSheet(media_style)
        self.btn_first.clicked.connect(self._go_first)
        self.btn_prev.clicked.connect(self._go_prev)
        self.btn_playpause.clicked.connect(self._toggle_play)
        self.btn_next.clicked.connect(self._go_next)
        self.btn_last.clicked.connect(self._go_last)
        if len(self.hand_list) > 1:
            self.btn_first.setToolTip("Jump to hand start — press again to go to the previous hand")
            self.btn_last.setToolTip("Jump to hand end — press again to go to the next hand")
        media_row.addStretch()
        for b in (self.btn_first, self.btn_prev, self.btn_playpause, self.btn_next, self.btn_last):
            media_row.addWidget(b)
        media_row.addStretch()
        controls.addLayout(media_row)

        street_row = QHBoxLayout()
        street_row.setSpacing(6)
        street_style = (
            "QPushButton{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #6b6f76,stop:1 #4a4d52);"
            "color:#e8e8e8;border:1px solid #34363a;border-radius:5px;font-size:12px;font-weight:700;"
            "padding:8px 4px;}"
            "QPushButton:hover{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #797d85,stop:1 #55585d);}")
        for street in ('FLOP', 'TURN', 'RIVER'):
            btn = QPushButton(street)
            btn.setStyleSheet(street_style)
            btn.clicked.connect(lambda _checked, s=street: self._jump_to_street(s))
            street_row.addWidget(btn)
        controls.addLayout(street_row)

        bottom.addLayout(controls, 1)
        outer.addLayout(bottom)

        self._load_hand(self.hand_list[self.hand_index])

    def _load_hand(self, hand: Hand):
        """Swaps in a different hand without closing/reopening the dialog
        — TableWidget is rebuilt from scratch (it's constructed around one
        specific hand's seats/players, not designed to be repointed at a
        different hand in place), everything else just resets/re-renders."""
        self._pause()
        self.hand = hand
        self.events = _build_events(hand)
        self.idx = -1

        self.setWindowTitle(f"Hand #{hand.hand_id}")
        played = hand.played_at.strftime("%Y-%m-%d %H:%M") if hand.played_at else "—"
        stake_cur = hand.native_currency or hand.currency
        sb = hand.native_small_blind if hand.native_small_blind is not None else hand.small_blind
        bb = hand.native_big_blind if hand.native_big_blind is not None else hand.big_blind
        self.header.setText(
            f"{hand.table_name or 'Table'}  ·  {stake_cur}{sb:g}/{stake_cur}{bb:g}"
            f"  ·  {played}  ·  Hand #{hand.hand_id}")

        if self.table is not None:
            self._table_slot.removeWidget(self.table)
            self.table.deleteLater()
        self.table = TableWidget(hand, self.hero)
        self._table_slot.addWidget(self.table)

        if self.hand_nav_label is not None:
            self.hand_nav_label.setText(f"Hand {self.hand_index + 1} of {len(self.hand_list)}")
            self.hand_nav_prev_btn.setEnabled(self.hand_index > 0)
            self.hand_nav_next_btn.setEnabled(self.hand_index < len(self.hand_list) - 1)

        self._render_state()
        if self.events:
            self.playing = True
            self.timer.start(1200)
            self.btn_playpause.setText("⏸")

    def _go_prev_hand(self):
        if self.hand_index > 0:
            self.hand_index -= 1
            self._load_hand(self.hand_list[self.hand_index])

    def _go_next_hand(self):
        if self.hand_index < len(self.hand_list) - 1:
            self.hand_index += 1
            self._load_hand(self.hand_list[self.hand_index])

    def _pause(self):
        self.playing = False
        self.timer.stop()
        self.btn_playpause.setText("▶")

    def _toggle_play(self):
        self.playing = not self.playing
        if self.playing:
            self.timer.start(1200)
            self.btn_playpause.setText("⏸")
        else:
            self.timer.stop()
            self.btn_playpause.setText("▶")

    def _go_first(self):
        self._pause()
        # Already at the start of this hand's actions and there's an
        # earlier hand in the list — treat a second press as "previous
        # hand" instead of a no-op, rather than requiring the separate
        # Previous/Next Hand row above for that.
        if self.idx == -1 and self.hand_index > 0:
            self._go_prev_hand()
            return
        self.idx = -1
        self._render_state()

    def _go_last(self):
        self._pause()
        if self.idx >= len(self.events) - 1 and self.hand_index < len(self.hand_list) - 1:
            self._go_next_hand()
            return
        self.idx = len(self.events) - 1
        self._render_state()

    def _go_prev(self):
        self._pause()
        if self.idx > -1:
            self.idx -= 1
            self._render_state()

    def _go_next(self):
        self._pause()
        self._step_forward()

    def _step_forward(self):
        if self.idx + 1 < len(self.events):
            self.idx += 1
            self._render_state()
        else:
            self._pause()

    def _jump_to_street(self, street: str):
        self._pause()
        for i, e in enumerate(self.events):
            if e['kind'] == 'street' and e['street'] == street:
                self.idx = i
                self._render_state()
                return

    def _render_state(self):
        pot = 0.0
        board: list[str] = []
        folded: set[str] = set()
        stacks = {p.name: (p.stack or 0.0) for p in self.hand.players}
        log_lines = []
        # Persistent per-seat state, accumulated across every event up to
        # idx (not just the current one) — a reveal or a win earlier in the
        # hand must stay visible once later events for OTHER seats render,
        # and a seat's last action stays as its status until its next one.
        shown_cards: dict[str, list[str]] = {}
        winners: dict[str, float] = {}
        last_status: dict[str, tuple[str, str]] = {}
        # Chips a player has out in front of them THIS street only (resets
        # at every street boundary, and gets swept away once the hand
        # concludes) — separate from the running pot/stack totals.
        street_committed: dict[str, float] = {}
        current = self.events[self.idx] if self.idx >= 0 else None

        for e in self.events[:self.idx + 1]:
            if e['kind'] == 'street':
                board = e['board']
                street_committed = {}
                log_lines.append(f"*** {e['street']} *** [{' '.join(board)}]")
            elif e['kind'] in ('action', 'uncalled'):
                pot_before = pot
                delta = e.get('delta', 0.0)
                pot += delta
                stacks[e['player']] = stacks.get(e['player'], 0.0) - delta
                street_committed[e['player']] = street_committed.get(e['player'], 0.0) + delta
                if e['kind'] == 'uncalled':
                    log_lines.append(f"Uncalled bet ({_fmt_bb(e['amount'], self.hand.big_blind)}) "
                                      f"returned to {e['player']}")
                else:
                    if e['action'] == 'Fold':
                        folded.add(e['player'])
                    label = _action_label(e['action'], e['amount'], self.hand.big_blind)
                    # Bet/raise sizing relative to the pot as it stood right
                    # before this action — e.g. a cbet or a 3-bet's "% pot".
                    if e['action'] in ('Bet', 'Raise') and pot_before > 1e-9:
                        pct = round(100 * delta / pot_before)
                        label += f" ({pct}% pot)"
                    log_lines.append(f"{e['player']} {label}")
                    last_status[e['player']] = (label, RED if e['action'] == 'Fold' else TEXT)
            elif e['kind'] == 'show':
                log_lines.append(f"{e['player']} shows [{' '.join(e['cards'])}] {e['desc']}")
                shown_cards[e['player']] = e['cards']
                last_status[e['player']] = (e['desc'], TEXT)
            elif e['kind'] == 'win':
                log_lines.append(f"{e['player']} wins {_fmt_bb(e['amount'], self.hand.big_blind)}")
                winners[e['player']] = winners.get(e['player'], 0.0) + e['amount']
                street_committed = {}  # chips are swept into the pot before it's awarded

        for name, sw in self.table.seat_widgets.items():
            sw.set_folded(name in folded)
            sw.set_active(bool(current and current.get('player') == name and current['kind'] == 'action'))
            sw.set_stack(stacks.get(name, 0.0))
            # Card state is fully recomputed each render (not incremental),
            # since stepping backward must bring a folded player's face-down
            # cards back rather than leaving them cleared.
            if name == self.hero:
                pass  # hero's own real cards stay visible the whole hand
            elif name in shown_cards:
                sw.show_cards(shown_cards[name])
            elif name in folded:
                sw.clear_cards()
            else:
                sw.show_backs()
            if name in winners:
                sw.set_winner(winners[name])
            elif name in last_status:
                text, color = last_status[name]
                sw.set_status(text, color)
            else:
                sw.set_status("")

        self.table.update_pot(f"Pot: {_fmt_bb(pot, self.hand.big_blind)}")
        self.table.update_board(board)
        self.table.update_bets(street_committed)
        self.log.setPlainText('\n'.join(log_lines))
        scrollbar = self.log.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
