"""Decorative header banner — custom-painted (no external artwork): a dark
poker-felt gradient with a faint scattered suit-glyph watermark and the
"PokerForge" wordmark painted directly on top."""
import math

from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QPainter, QLinearGradient, QColor, QFont
from PyQt6.QtWidgets import QFrame

from ui.theme import BG, BG2, GREEN, TEXT, DIM, BORDER

_SUITS = ["♠", "♥", "♦", "♣"]


class HeaderBanner(QFrame):
    """Drop-in replacement for a plain QFrame header — same fixed height /
    border-bottom usage, just paints a felt-gradient + watermark background
    with the app wordmark instead of a flat color.

    `top_height` is how tall the logo/wordmark area is; the wordmark and
    watermark are always sized/positioned relative to it, not to the
    banner's actual height. When the banner is made taller than
    `top_height` (to also run behind the filter bar below it — see
    ui/app_window.py), everything past `top_height` fades to a near-opaque
    scrim so whatever's drawn on top (filter controls) stays legible
    instead of competing with the watermark pattern."""

    def __init__(self, parent=None, top_height: int = 60):
        super().__init__(parent)
        self._top_height = top_height
        self.setStyleSheet(f"QFrame {{ background:transparent; border: none; border-bottom: 1px solid {BORDER}; }}")

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        w, h = self.width(), self.height()
        th = self._top_height

        # Felt-green gradient, dark on the left fading toward the app's
        # own background color on the right so it blends into the rest
        # of the UI regardless of window width.
        grad = QLinearGradient(0, 0, w, 0)
        grad.setColorAt(0.0, QColor("#0f2e1a"))
        grad.setColorAt(0.45, QColor("#123321"))
        grad.setColorAt(1.0, QColor(BG2))
        painter.fillRect(0, 0, w, h, grad)

        # Faint scattered suit-glyph watermark.
        watermark_font = QFont("Segoe UI Symbol", int(th * 0.55))
        painter.setFont(watermark_font)
        painter.setPen(QColor(255, 255, 255, 14))
        step = int(th * 1.4)
        for i, x in enumerate(range(-step // 2, w, step)):
            suit = _SUITS[i % len(_SUITS)]
            painter.drawText(QRectF(x, -th * 0.15, step, th * 1.3),
                              Qt.AlignmentFlag.AlignCenter, suit)

        # Wordmark.
        left_pad = 24
        title_font = QFont("Segoe UI", int(th * 0.34), QFont.Weight.Bold)
        painter.setFont(title_font)
        fm = painter.fontMetrics()
        baseline_y = int(th * 0.42) + fm.ascent() // 2

        painter.setPen(QColor(TEXT))
        painter.drawText(left_pad, baseline_y, "Poker")
        poker_width = fm.horizontalAdvance("Poker")

        painter.setPen(QColor(GREEN))
        painter.drawText(left_pad + poker_width, baseline_y, "Forge")

        tagline_font = QFont("Segoe UI", int(th * 0.13))
        tagline_font.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 120)
        painter.setFont(tagline_font)
        painter.setPen(QColor(DIM))
        painter.drawText(left_pad, baseline_y + int(th * 0.28), "PLAY  •  ANALYSE  •  IMPROVE")

        # Scrim fading in below the logo area, so a filter row overlaid
        # down there (rather than sitting on its own opaque bar) stays
        # readable against the felt pattern instead of fighting it.
        if h > th:
            fade = QLinearGradient(0, 0, 0, h)
            fade.setColorAt(0.0, QColor(0, 0, 0, 0))
            fade.setColorAt(th / h, QColor(0, 0, 0, 0))
            fade.setColorAt(1.0, QColor(13, 17, 23, 235))
            painter.fillRect(0, 0, w, h, fade)

        painter.end()
        super().paintEvent(event)
