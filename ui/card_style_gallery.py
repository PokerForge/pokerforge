"""Saved card-rendering style options, kept for future reuse — NOT imported
by the active hand replayer (see ui/hand_replayer.py, which currently uses
its own "gem badge" style). The user asked to keep "Big single glyph"
specifically for when SF Poker's platform gets built out for commercial use,
so it lives here as a ready-to-reuse function rather than only existing in
chat history.

Each function takes a card string ("A♠", "T♥", ...) and returns a QWidget
sized to itself — drop into any QHBoxLayout/QVBoxLayout as-is.
"""
from PyQt6.QtWidgets import QLabel

_SUIT_COLOR = {'♥': '#d1242f', '♦': '#0969da', '♣': '#1a7f37', '♠': '#1f2328'}


def big_single_glyph(card: str, size: int = 40) -> QLabel:
    """Rank and suit on one line, bold and large — the simplest, most
    legible-at-a-glance style tried during the replayer's visual design
    pass. Flat white card face, no gradient/shadow."""
    from PyQt6.QtCore import Qt
    rank, suit = card[:-1], card[-1]
    color = _SUIT_COLOR.get(suit, '#1f2328')
    w = QLabel(f"{rank}{suit}")
    w.setAlignment(Qt.AlignmentFlag.AlignCenter)
    w.setFixedSize(size, int(size * 1.35))
    w.setStyleSheet(
        "background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #ffffff,stop:1 #e2e2e6);"
        f"border:1px solid #8f8f94;border-bottom:2px solid #6f6f75;border-radius:6px;"
        f"color:{color};font-size:{int(size * 0.45)}px;font-weight:800;")
    return w
