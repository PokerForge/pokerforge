"""Shared overlay widgets for pyqtgraph PlotWidgets: a draggable
summary box, a camera button that copies the plot to the clipboard, and a
hover crosshair that reads off each visible curve's value at the cursor's
hand index. All positioned as real child QWidgets on top of the plot (not
pyqtgraph items), so they can use normal Qt mouse handling and styling."""
import pyqtgraph as pg
from PyQt6.QtCore import Qt, QPoint, QObject, QEvent, QTimer
from PyQt6.QtWidgets import QApplication, QFrame, QLabel, QVBoxLayout, QToolButton

from ui.theme import BG2, BORDER, TEXT, DIM


def suggest_stats_box_prefer_bottom(total_series: list[float]) -> bool:
    """Should DraggableStatsBox's default spot sit in the lower half of
    the plot (True) or the upper half (False)? The box always sits at a
    fixed pixel offset from the left edge, so what matters is only where
    the line actually is near hand 1 — not its overall range — since a
    graph that starts flat and swings wildly later would never collide
    with the box regardless of where it eventually ends up. True (the
    original fixed default) if there's no data yet to judge by."""
    if not total_series:
        return True
    lo, hi = min(total_series), max(total_series)
    if hi == lo:
        return True
    window = max(1, min(20, len(total_series) // 10))
    early_avg = sum(total_series[:window]) / window
    frac = (early_avg - lo) / (hi - lo)  # 0 = bottom of range, 1 = top
    return frac >= 0.5


class DraggableStatsBox(QFrame):
    """A small "label: value" panel that floats over a plot and can be
    dragged anywhere within it, as a movable stats box. Rows are
    added/updated by key via set_row(); a row can be hidden independently
    (e.g. when the user unchecks the curve it corresponds to) without
    disturbing the others."""

    def __init__(self, parent_plot):
        super().__init__(parent_plot)
        self._plot = parent_plot
        self.setObjectName("statsbox")
        self.setStyleSheet(f"""
            QFrame#statsbox {{
                background: rgba(22,27,34,235);
                border: 1px solid {BORDER};
                border-radius: 6px;
            }}
        """)
        self.setCursor(Qt.CursorShape.SizeAllCursor)
        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(10, 8, 10, 8)
        self._lay.setSpacing(3)
        self._rows: dict[str, QLabel] = {}
        self._row_order: list[str] = []
        self._drag_offset: QPoint | None = None
        self._positioned = False
        self._user_moved = False
        # Where the default (never-dragged) spot sits, as a fraction of
        # plot height — True keeps today's original default (a bit past
        # halfway down), False moves it up near the top. set_preferred_corner
        # switches this based on where the plotted line actually is near
        # its start, so a strong uptrend from hand 1 doesn't run straight
        # through the box every time the tab renders.
        self._prefer_bottom = True

    def set_row(self, key, text, color=TEXT):
        if key not in self._rows:
            row = QLabel()
            row.setStyleSheet(f"background:transparent;border:none;font-size:11px;color:{TEXT};")
            self._row_order.append(key)
            self._lay.addWidget(row)
            self._rows[key] = row
        row = self._rows[key]
        row.setText(text)
        row.setStyleSheet(f"background:transparent;border:none;font-size:11px;color:{color};")
        self._resize_and_place()

    def set_row_visible(self, key, visible):
        if key in self._rows:
            self._rows[key].setVisible(visible)
            self._resize_and_place()

    def set_preferred_corner(self, prefer_bottom: bool):
        """Re-aim the default (never-dragged) spot at whichever vertical
        half of the left edge the plotted line ISN'T occupying near hand
        1 — called by the chart owner once real data is known. A no-op
        once the user has actually dragged the box themselves; that
        placement is theirs to keep across future refreshes."""
        if self._user_moved or self._prefer_bottom == prefer_bottom:
            return
        self._prefer_bottom = prefer_bottom
        self._positioned = False
        self._resize_and_place()

    def _resize_and_place(self):
        self.adjustSize()
        if not self._positioned:
            # Before the plot has actually been laid out (during __init__),
            # height() is just a placeholder — wait for a real size before
            # committing to the default spot, so this doesn't lock in a
            # position computed from a near-zero height.
            if self._plot.height() > 60:
                frac = 0.55 if self._prefer_bottom else 0.06
                self.move(12, int(self._plot.height() * frac))
                self._positioned = True
            else:
                self.move(12, 12)
        else:
            # Keep it inside the plot if the plot shrank since the last drag.
            max_x = max(0, self._plot.width() - self.width())
            max_y = max(0, self._plot.height() - self.height())
            x = min(self.x(), max_x)
            y = min(self.y(), max_y)
            self.move(max(0, x), max(0, y))
        self.raise_()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            new_pos = self.mapToParent(event.position().toPoint() - self._drag_offset)
            max_x = max(0, self._plot.width() - self.width())
            max_y = max(0, self._plot.height() - self.height())
            new_pos.setX(min(max(0, new_pos.x()), max_x))
            new_pos.setY(min(max(0, new_pos.y()), max_y))
            self.move(new_pos)
            self._user_moved = True
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_offset = None
        super().mouseReleaseEvent(event)


class ScreenshotButton(QToolButton):
    """Small camera-icon button that sits in the corner of a plot and, on
    click, grabs the plot as an image and puts it straight on the system
    clipboard — so it can be pasted elsewhere without a separate
    screenshot tool."""

    def __init__(self, target_widget, parent=None):
        super().__init__(parent)
        self._target = target_widget
        self.setText("\U0001F4F7")
        self.setToolTip("Copy graph image to clipboard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(26, 26)
        self.setStyleSheet(f"""
            QToolButton {{
                background: rgba(22,27,34,200);
                border: 1px solid {BORDER};
                border-radius: 4px;
                font-size: 13px;
                padding: 0px;
                color: {TEXT};
            }}
            QToolButton:hover {{ background: {BG2}; border-color: {DIM}; }}
        """)
        self.clicked.connect(self._copy_to_clipboard)

    def _copy_to_clipboard(self):
        pixmap = self._target.grab()
        QApplication.clipboard().setPixmap(pixmap)
        original = self.text()
        self.setText("✓")
        QTimer.singleShot(900, lambda: self.setText(original))


class HoverCrosshair(QObject):
    """Hover readout: a vertical guide line plus a small tooltip
    that reports every currently-visible curve's value at the hand index
    under the cursor, updating live as the mouse moves along the graph —
    the standard graph-crosshair idea.

    `curves` is the same (name, PlotDataItem, color) list the legend
    checkboxes are built from, so a curve the user has toggled off is
    automatically skipped (checked via curve.isVisible() on every move,
    not captured once at construction time). `x_label_formatter` names
    the x position in the tooltip's first line — defaults to "Hand N"
    (the x axis every other user of this class plots), but e.g. the
    Trend tab's x axis is a sequence of check-in dates, not hand indices,
    so it supplies its own."""

    def __init__(self, plot_widget, curves, value_formatter=lambda v: f"{v:+,.2f}",
                 x_label_formatter=None, parent=None):
        super().__init__(parent)
        self._plot = plot_widget
        self._curves = curves
        self._value_formatter = value_formatter
        self._x_label_formatter = x_label_formatter or (lambda x: f"Hand {int(x):,}")

        pi = plot_widget.getPlotItem()
        self._vline = pg.InfiniteLine(
            angle=90, movable=False,
            pen=pg.mkPen(color=DIM, width=1, style=Qt.PenStyle.DashLine))
        self._vline.setVisible(False)
        pi.addItem(self._vline, ignoreBounds=True)

        self._tooltip = QLabel("", plot_widget)
        self._tooltip.setTextFormat(Qt.TextFormat.RichText)
        self._tooltip.setStyleSheet(f"""
            background: rgba(22,27,34,235); border:1px solid {BORDER}; border-radius:5px;
            padding:6px 8px; font-size:11px; color:{TEXT};
        """)
        self._tooltip.hide()

        self._proxy = pg.SignalProxy(plot_widget.scene().sigMouseMoved, rateLimit=60, slot=self._on_move)
        plot_widget.installEventFilter(self)

    def reattach(self):
        """Re-adds the crosshair's guide line to the plot — call this
        after any PlotWidget.clear() call, which removes every item
        (including ones like this added directly via addItem(), not just
        curves from .plot()) rather than just the curves a caller meant
        to replace."""
        self._plot.getPlotItem().addItem(self._vline, ignoreBounds=True)

    def eventFilter(self, obj, event):
        if obj is self._plot and event.type() == QEvent.Type.Leave:
            self._hide()
        return False

    def _on_move(self, evt):
        pos = evt[0]
        pi = self._plot.getPlotItem()
        vb = pi.vb
        if not vb.sceneBoundingRect().contains(pos):
            self._hide()
            return

        view_pos = vb.mapSceneToView(pos)
        target_x = view_pos.x()

        ref_xdata = None
        for _, curve, _ in self._curves:
            if not curve.isVisible():
                continue
            xdata = curve.xData
            if xdata is not None and len(xdata):
                ref_xdata = xdata
                break
        if ref_xdata is None:
            self._hide()
            return

        idx = int(round(target_x))
        idx = max(int(ref_xdata[0]), min(int(ref_xdata[-1]), idx))
        pos_idx = max(0, min(len(ref_xdata) - 1, idx - int(ref_xdata[0])))
        real_x = ref_xdata[pos_idx]

        lines = [self._x_label_formatter(real_x)]
        for name, curve, color in self._curves:
            if not curve.isVisible():
                continue
            ydata = curve.yData
            if ydata is None or pos_idx >= len(ydata):
                continue
            val = ydata[pos_idx]
            lines.append(f"<span style='color:{color}'>{name}: {self._value_formatter(val)}</span>")
        if len(lines) == 1:
            self._hide()
            return

        self._tooltip.setText("<br>".join(lines))
        self._tooltip.adjustSize()

        self._vline.setPos(real_x)
        self._vline.setVisible(True)

        # PlotWidget is itself the QGraphicsView, so its own mapFromScene
        # gives cursor position directly in the widget's pixel coordinates.
        widget_pt = self._plot.mapFromScene(pos)
        tx = widget_pt.x() + 16
        ty = widget_pt.y() - self._tooltip.height() - 12
        max_x = self._plot.width() - self._tooltip.width() - 4
        tx = min(max(4, tx), max(4, max_x))
        ty = max(4, ty)
        self._tooltip.move(int(tx), int(ty))
        self._tooltip.show()
        self._tooltip.raise_()

    def _hide(self):
        self._vline.setVisible(False)
        self._tooltip.hide()
