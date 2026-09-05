"""Visual theme, reused as-is from poker_dashboard_legacy.py's established
color palette and layout language rather than inventing a new one."""
import math

import pyqtgraph as pg
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel

# Applies to every plot in the app (module-level pyqtgraph config) — without
# this, lines render aliased/"chunky" rather than smooth.
pg.setConfigOptions(antialias=True)

BG      = "#0d1117"
BG2     = "#161b22"
BG3     = "#21262d"
ACCENT  = "#1f6feb"
ACCENT2 = "#388bfd"
GREEN   = "#3fb950"
RED     = "#f85149"
ORANGE  = "#d29922"
YELLOW  = "#e3b341"
TEXT    = "#e6edf3"
DIM     = "#8b949e"
BORDER  = "#30363d"

STYLE = f"""
QMainWindow, QWidget {{ background:{BG}; color:{TEXT}; font-family:'Segoe UI',Arial; font-size:13px; }}
QTabWidget::pane {{ border:1px solid {BORDER}; background:{BG2}; border-radius:6px; }}
QTabBar::tab {{ background:{BG3}; color:{DIM}; padding:10px 24px; border:1px solid {BORDER};
    border-bottom:none; border-radius:6px 6px 0 0; margin-right:2px; font-size:13px; font-weight:500; }}
QTabBar::tab:selected {{ background:{BG2}; color:{TEXT}; border-bottom:2px solid {ACCENT}; }}
QTabBar::tab:hover:!selected {{ background:{BG2}; color:{TEXT}; }}
QComboBox {{ background:{BG3}; color:{TEXT}; border:1px solid {BORDER}; border-radius:6px;
    padding:6px 12px; font-size:13px; min-width:130px; }}
QComboBox::drop-down {{ border:none; width:24px; }}
QComboBox QAbstractItemView {{ background:{BG3}; color:{TEXT}; border:1px solid {BORDER};
    selection-background-color:{ACCENT}; }}
QPushButton {{ background:{ACCENT}; color:white; border:none; border-radius:6px;
    padding:8px 20px; font-size:13px; font-weight:600; }}
QPushButton:hover {{ background:{ACCENT2}; }}
QListWidget {{ background:{BG2}; color:{TEXT}; border:1px solid {BORDER}; border-radius:6px; }}
QListWidget::item {{ padding:8px 10px; border-bottom:1px solid {BORDER}; }}
QListWidget::item:selected {{ background:{ACCENT}; color:white; }}
QTableWidget {{ background:{BG2}; color:{TEXT}; border:1px solid {BORDER}; border-radius:6px;
    gridline-color:{BORDER}; font-size:12px; alternate-background-color:{BG3}; }}
QTableWidget::item {{ padding:6px 12px; border-bottom:1px solid {BORDER}; }}
QTableWidget::item:selected {{ background:{ACCENT}; color:white; }}
QHeaderView::section {{ background:{BG3}; color:{DIM}; border:none; border-bottom:1px solid {BORDER};
    padding:8px 12px; font-size:12px; font-weight:600; }}
QScrollBar:vertical {{ background:{BG}; width:8px; border-radius:4px; }}
QScrollBar::handle:vertical {{ background:{BORDER}; border-radius:4px; min-height:30px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height:0px; }}
QFrame#card {{ background:{BG2}; border:1px solid {BORDER}; border-radius:8px; }}
QLineEdit {{ background:{BG3}; color:{TEXT}; border:1px solid {BORDER}; border-radius:6px;
    padding:6px 12px; font-size:13px; }}
QTextEdit {{ background:{BG3}; color:{TEXT}; border:1px solid {BORDER}; border-radius:6px;
    padding:8px; font-size:12px; }}
QSplitter::handle {{ background:{BORDER}; }}
"""


def hand_axis_ticks(total):
    """Tick list for a pyqtgraph bottom 'Hands' axis that always ends on the
    period's real hand count, rather than pyqtgraph's auto-picked round
    number (e.g. 500 instead of the actual 540) — matches PT4's graphs,
    which label the axis end with the exact hand total."""
    if total <= 0:
        return [[(0, "0")]]
    raw_step = max(total / 5, 1)
    magnitude = 10 ** math.floor(math.log10(raw_step))
    step = magnitude
    for m in (1, 2, 5, 10):
        step = m * magnitude
        if step >= raw_step:
            break
    step = int(step)
    ticks = list(range(0, total, step))
    if not ticks or ticks[-1] != total:
        ticks.append(total)
    return [[(t, f"{t:,}") for t in ticks]]


def lbl(text, size=13, color=TEXT, bold=False, dim=False):
    l = QLabel(text)
    # QLabel's default AutoText mode auto-detects and renders HTML-like
    # content as rich text — and a lot of what this app displays (player
    # names, table names) comes straight out of a hand-history file, which
    # could in principle be one someone else handed you. Plain text always,
    # so a crafted name can't render as fake bold/formatted UI.
    l.setTextFormat(Qt.TextFormat.PlainText)
    c = DIM if dim else color
    w = "700" if bold else "400"
    l.setStyleSheet(f"color:{c};font-size:{size}px;font-weight:{w};background:transparent;border:none;")
    return l
