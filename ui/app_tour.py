"""A guided, spotlight-style first-run tour: dims the whole window except
a cutout around whatever's being explained, with a fixed callout card
(title, description, step counter, Back/Next/Skip) anchored near the
bottom of the window regardless of the target's size or position — a
target the size of a whole tab (there's no meaningfully "clever" position
to compute around something that large anyway) and a target the size of
a single button both work the same way.

Deliberately look-but-don't-touch: the overlay blocks mouse input to
everything underneath it, including the spotlighted widget itself, so a
stray click during the tour can't switch tabs or fire an action out from
under the step that's currently describing something else.

Launched automatically on first run (see ui/app_window.py's main()) and
replayable anytime via Help > Take the Tour."""
from dataclasses import dataclass
from typing import Callable, Optional

from PyQt6.QtCore import Qt, QPoint, QRect, QRectF
from PyQt6.QtGui import QPainter, QPainterPath, QColor, QPen
from PyQt6.QtWidgets import QWidget, QFrame, QVBoxLayout, QHBoxLayout, QPushButton, QApplication

from ui.theme import lbl, BG2, BORDER, GREEN


@dataclass
class TourStep:
    title: str
    text: str
    # None targets a widget to spotlight; None means a plain centered
    # message with no cutout (the welcome/wrap-up steps).
    target: Optional[Callable[[object], QWidget]] = None
    # Runs before this step is shown — typically switching to the tab/
    # sub-tab the target lives on, so it actually exists to spotlight.
    before_show: Optional[Callable[[object], None]] = None


def _show_stats_subtab(index: int):
    def _go(win):
        win.tabs.setCurrentWidget(win.tab_stats)
        win.tab_stats.sub_tabs.setCurrentIndex(index)
    return _go


def _show_tab(tab_attr: str):
    def _go(win):
        win.tabs.setCurrentWidget(getattr(win, tab_attr))
    return _go


def _select_first_villain(win):
    """Population tab + click the first row, if the pool has one — on a
    genuinely fresh install there may be no villains yet, in which case
    this leaves the detail panel on its own "Select a villain" placeholder
    rather than erroring; the tour step's target is then simply hidden
    (see TourOverlay._show_step's isHidden() check), and the step falls
    back to a plain, un-spotlit message instead of failing outright."""
    win.tabs.setCurrentWidget(win.tab_population)
    table = win.tab_population.table
    if table.rowCount() > 0:
        win.tab_population._on_select(0, 0)
        win.tab_population.detail.below_tabs.setCurrentIndex(0)  # Exploits


TOUR_STEPS = [
    TourStep(
        title="Welcome to PokerForge",
        text="A minute-long look at where everything lives — click Skip anytime, "
             "and find this tour again later under Help > Take the Tour.",
    ),
    TourStep(
        title="Filter by period and stakes",
        text="Every tab respects this bar — pick a date range (or a custom one) and "
             "a stake level, and everything below updates to match.",
        target=lambda w: w.filter_bar,
        before_show=_show_tab("tab_overview"),
    ),
    TourStep(
        title="Overview — your results over time",
        text="A cumulative results graph: Total, Showdown, Non-Showdown, and EV, "
             "in $ or BB/100. Drag the summary box anywhere on the graph.",
        target=lambda w: w.tab_overview,
        before_show=_show_tab("tab_overview"),
    ),
    TourStep(
        title="Sessions — every session you've played",
        text="Grouped by date and stakes. Double-click one for the full hand grid, "
             "or open the Tilt Report to see whether a big loss changes how you play afterward.",
        target=lambda w: w.tab_sessions,
        before_show=_show_tab("tab_sessions"),
    ),
    TourStep(
        title="Stats — your own game, by position",
        text="See exactly how you play from each seat — VPIP, PFR, 3-bet, and more, "
             "broken down position by position.",
        target=lambda w: w.tab_stats,
        before_show=_show_stats_subtab(0),
    ),
    TourStep(
        title="Leaks — PokerForge's intelligence engine",
        text="The heart of PokerForge: your biggest leaks, ranked by how much they "
             "actually cost you, plus a Study Queue that picks hands for you to review.",
        target=lambda w: w.tab_stats,
        before_show=_show_stats_subtab(1),
    ),
    TourStep(
        title="Trend — did a change actually help?",
        text="Track any stat over time, and backtest whether the periods where it "
             "moved actually lined up with better or worse results.",
        target=lambda w: w.tab_stats,
        before_show=_show_stats_subtab(2),
    ),
    TourStep(
        title="Population — everyone you've played against",
        text="Every opponent you've faced, searchable and sortable — plus pool-wide "
             "patterns across your whole showdown history under Pool Insights.",
        target=lambda w: w.tab_population,
        before_show=_show_tab("tab_population"),
    ),
    TourStep(
        title="A full profile for any villain",
        text="Click a name in the pool for their complete profile: exploit notes "
             "with a recommended strategy, players with a similar overall style, "
             "and their full stat breakdown.",
        target=lambda w: w.tab_population.detail,
        before_show=_select_first_villain,
    ),
    TourStep(
        title="Keep it up to date",
        text="New hands are picked up automatically while you play. Refresh checks "
             "right now, for anything played since PokerForge was opened.",
        target=lambda w: w.refresh_btn,
    ),
    TourStep(
        title="You're all set",
        text="Find this tour again anytime under Help > Take the Tour, and "
             "Help > Getting Started for a glossary of every stat.",
    ),
]


class _TourCallout(QFrame):
    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("card")
        self.setFixedWidth(440)
        self.setStyleSheet(
            f"QFrame#card{{background:{BG2};border:1px solid {BORDER};border-radius:10px;}}")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 16)
        lay.setSpacing(8)

        self.step_lbl = lbl("", size=11, dim=True)
        lay.addWidget(self.step_lbl)
        self.title_lbl = lbl("", size=15, bold=True)
        self.title_lbl.setWordWrap(True)
        lay.addWidget(self.title_lbl)
        self.text_lbl = lbl("", size=12, dim=True)
        self.text_lbl.setWordWrap(True)
        lay.addWidget(self.text_lbl)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        self.skip_btn = QPushButton("Skip")
        self.skip_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_row.addWidget(self.skip_btn)
        btn_row.addStretch()
        self.back_btn = QPushButton("Back")
        self.back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        # The app-wide stylesheet has no QPushButton:disabled rule, so a
        # disabled Back on step 1 would otherwise look just as clickable
        # as an enabled one — worth a local override here specifically,
        # since clicking a "dead" button in the middle of a guided tour
        # reads as broken in a way it wouldn't elsewhere in the app.
        self.back_btn.setStyleSheet("QPushButton:disabled{color:#6e7681;}")
        btn_row.addWidget(self.back_btn)
        self.next_btn = QPushButton("Next")
        self.next_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.next_btn.setStyleSheet(
            f"QPushButton{{background:{GREEN};color:#05130a;font-weight:700;"
            f"border:none;border-radius:5px;padding:6px 16px;}}")
        btn_row.addWidget(self.next_btn)
        lay.addLayout(btn_row)

    def set_content(self, index: int, total: int, title: str, text: str, is_last: bool):
        self.step_lbl.setText(f"STEP {index + 1} OF {total}")
        self.title_lbl.setText(title)
        self.text_lbl.setText(text)
        self.back_btn.setEnabled(index > 0)
        self.next_btn.setText("Finish" if is_last else "Next")
        self.adjustSize()


class TourOverlay(QWidget):
    """One overlay instance per tour run — call start(), then discard it
    (finish()/skip both hide and schedule deleteLater)."""

    _SPOTLIGHT_MARGIN = 8
    _SPOTLIGHT_RADIUS = 10

    def __init__(self, window):
        super().__init__(window.centralWidget())
        self.window_ = window
        self._steps = []
        self._index = 0
        self._target_rect = QRect()
        self.on_finished = None

        self.callout = _TourCallout(self)
        self.callout.next_btn.clicked.connect(self._next)
        self.callout.back_btn.clicked.connect(self._back)
        self.callout.skip_btn.clicked.connect(self.finish)

    def start(self, steps=None):
        self._steps = steps if steps is not None else TOUR_STEPS
        self._index = 0
        self.setGeometry(self.window_.centralWidget().rect())
        self.show()
        self.raise_()
        self._show_step()

    def _show_step(self):
        step = self._steps[self._index]
        if step.before_show:
            step.before_show(self.window_)
        # Let the tab switch this step just triggered actually lay out
        # before measuring where its target widget ended up.
        QApplication.processEvents()

        target = step.target(self.window_) if step.target else None
        # isHidden() (an explicit per-widget flag QTabWidget toggles when
        # switching pages) rather than isVisible() (which additionally
        # requires the top-level window itself to be shown) — before_show
        # above has already made the real target current if it's on a
        # different tab, and isVisible() would report every target as
        # invisible during a test that never calls window.show().
        if target is not None and not target.isHidden():
            # mapTo (not mapToGlobal/mapFromGlobal) — this overlay is a
            # direct child of centralWidget() positioned at its (0, 0), so
            # mapping the target to that same shared ancestor lands
            # directly in the overlay's own coordinate space, without
            # ever depending on the top-level window's actual on-screen
            # position (undefined for a window that's never been shown,
            # which produced a badly-offset cutout rect here before).
            central = self.window_.centralWidget()
            top_left = target.mapTo(central, QPoint(0, 0))
            self._target_rect = QRect(top_left, target.size())
        else:
            self._target_rect = QRect()

        self.callout.set_content(
            self._index, len(self._steps), step.title, step.text,
            is_last=(self._index == len(self._steps) - 1))
        self._position_callout()
        self.update()

    def _position_callout(self):
        self.callout.adjustSize()
        cw, ch = self.callout.width(), self.callout.height()
        x = (self.width() - cw) // 2
        y = self.height() - ch - 40
        self.callout.move(max(12, x), max(12, y))

    def _next(self):
        if self._index < len(self._steps) - 1:
            self._index += 1
            self._show_step()
        else:
            self.finish()

    def _back(self):
        if self._index > 0:
            self._index -= 1
            self._show_step()

    def finish(self):
        self.hide()
        callback = self.on_finished
        self.deleteLater()
        if callback:
            callback()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_callout()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        overlay_path = QPainterPath()
        overlay_path.addRect(QRectF(self.rect()))
        if not self._target_rect.isNull():
            hole = self._target_rect.adjusted(
                -self._SPOTLIGHT_MARGIN, -self._SPOTLIGHT_MARGIN,
                self._SPOTLIGHT_MARGIN, self._SPOTLIGHT_MARGIN)
            cutout = QPainterPath()
            cutout.addRoundedRect(QRectF(hole), self._SPOTLIGHT_RADIUS, self._SPOTLIGHT_RADIUS)
            overlay_path = overlay_path.subtracted(cutout)
            painter.setPen(QPen(QColor(GREEN), 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(QRectF(hole), self._SPOTLIGHT_RADIUS, self._SPOTLIGHT_RADIUS)

        painter.fillPath(overlay_path, QColor(5, 8, 12, 195))

    def mousePressEvent(self, event):
        # Look-but-don't-touch: swallow every click on the dimmed area
        # (and on the spotlighted widget itself) except the callout's own
        # buttons, which are separate child widgets and get their events
        # first regardless.
        event.accept()
