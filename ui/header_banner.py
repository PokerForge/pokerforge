"""Decorative header banner — a dark poker-felt gradient with a faint
scattered suit-glyph watermark, the app logo, and the "PokerForge"
wordmark painted on top."""
from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QPainter, QLinearGradient, QColor, QFont, QPixmap
from PyQt6.QtWidgets import QFrame

from config.paths import resource_dir
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

    # Logo height as a fraction of the logo row, chosen so the chip's
    # diameter reads as the same optical weight as the wordmark block
    # beside it (title cap-top down to tagline baseline). Going much
    # past this pushes the chip out of the row and into the scrim below,
    # and makes "PokerForge" look like the secondary element.
    LOGO_SCALE = 0.86

    def __init__(self, parent=None, top_height: int = 60):
        super().__init__(parent)
        self._top_height = top_height
        self.setStyleSheet(f"QFrame {{ background:transparent; border: none; border-bottom: 1px solid {BORDER}; }}")

    def _logo(self, size: int):
        """The logo scaled to `size`, cached per size and per display
        scaling. Returns None if the asset is missing, so the banner
        still draws.

        Both details matter for how this looks. Qt's default pixmap
        scaling is fast rather than smooth, which visibly mangles fine
        detail like the monogram; and on a display running at 125% or
        150% a logical size of 72px needs proportionally more real
        pixels, or it renders soft. Scaling once here — smoothly, at the
        true device resolution — avoids both."""
        ratio = self.devicePixelRatioF()
        key = (size, round(ratio, 2))
        cache = getattr(self, "_logo_cache", None)
        if cache is None:
            cache = self._logo_cache = {}
        if key not in cache:
            if not hasattr(self, "_logo_source"):
                path = resource_dir() / "assets" / "pf_logo.png"
                source = QPixmap(str(path)) if path.exists() else QPixmap()
                self._logo_source = None if source.isNull() else source
            source = self._logo_source
            if source is None:
                cache[key] = None
            else:
                pixels = max(1, round(size * ratio))
                scaled = source.scaled(pixels, pixels,
                                       Qt.AspectRatioMode.KeepAspectRatio,
                                       Qt.TransformationMode.SmoothTransformation)
                scaled.setDevicePixelRatio(ratio)
                cache[key] = scaled
        return cache[key]

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

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

        # Logo, then the wordmark beside it. The logo is optional: if the
        # asset can't be found the wordmark simply starts at the left
        # padding as it used to, rather than leaving a gap.
        left_pad = 24
        size = int(th * self.LOGO_SCALE)
        logo = self._logo(size)
        text_x = left_pad
        if logo is not None:
            # Nudged below the row's midpoint on purpose. The tagline
            # hangs under the title, so the wordmark's visual centre
            # (~y48 in a 76px row) sits well below the row's own (~y38),
            # and a logo centred on the row alone reads as riding high
            # next to it. Matching the text exactly would push the chip
            # past the row, so this splits the difference.
            painter.drawPixmap(left_pad, (th - size) // 2 + 4, logo)
            text_x = left_pad + size + 12

        title_font = QFont("Segoe UI", int(th * 0.34), QFont.Weight.Bold)
        painter.setFont(title_font)
        fm = painter.fontMetrics()
        baseline_y = int(th * 0.42) + fm.ascent() // 2

        painter.setPen(QColor(TEXT))
        painter.drawText(text_x, baseline_y, "Poker")
        poker_width = fm.horizontalAdvance("Poker")

        painter.setPen(QColor(GREEN))
        painter.drawText(text_x + poker_width, baseline_y, "Forge")

        tagline_font = QFont("Segoe UI", int(th * 0.13))
        tagline_font.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 120)
        painter.setFont(tagline_font)
        painter.setPen(QColor(DIM))
        painter.drawText(text_x, baseline_y + int(th * 0.28), "PLAY  •  ANALYSE  •  IMPROVE")

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
