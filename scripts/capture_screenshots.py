"""Captures a Stats sub-tab from the real app, for the website.

    PF_TAB=Study PF_OUT=study.png PF_HEIGHT=405 python scripts/capture_screenshots.py

Renders the actual widget against the real database, so the site shows
the app as it genuinely looks rather than a mockup -- the Overview
section used to be hand-drawn SVG with invented numbers.

Two things here are less obvious than they look:

  * the tab is picked by NAME, not index. The sub-tab order has already
    changed once (Study was split out of Leaks), and an index would
    silently capture the wrong page.

  * the page populates asynchronously, and its widgets exist a moment
    before Qt lays them out. Capturing on "a widget appeared" produced a
    56px-tall empty Study page; capturing on a fixed delay either fires
    early or wastes a minute. So: wait for widgets, then let the layout
    settle, then render.

Set PF_HEIGHT to roughly the page's own content height plus ~100px of
chrome -- the script prints that height, so one throwaway run tells you
what to use, and the capture then needs no cropping.
"""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, r"C:\Users\shane\SF_Poker")

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QImage

from config.paths import profile_data_dir
from config.settings import get_hero_name, get_currency_symbol
from database.repository import PokerDatabase
from ui.stats_tab import StatsTab
from ui.theme import STYLE

SCRATCH = Path(r"C:\Users\shane\AppData\Local\Temp\claude\C--Users-shane-SF-Poker\58a315f6-cda6-40ac-b3eb-0ce09f5e8cb3\scratchpad")
import os
# Which sub-tab to capture, by name, so the index can move without this
# silently grabbing the wrong page.
TAB_NAME = os.environ.get("PF_TAB", "Leaks")
OUT_NAME = os.environ.get("PF_OUT", "leaks_capture.png")
WIDTH = int(os.environ.get("PF_WIDTH", "1400"))
HEIGHT = int(os.environ.get("PF_HEIGHT", "1500"))

app = QApplication(sys.argv)
app.setStyleSheet(STYLE)

db = PokerDatabase(profile_data_dir() / "sf_poker.db")
hero = get_hero_name()
currency = get_currency_symbol()

d_from, d_to = date(2000, 1, 1), date.today()

tab = StatsTab(hero, db, currency)
tab.resize(WIDTH, HEIGHT)
tab.show()
names = [tab.sub_tabs.tabText(i).strip() for i in range(tab.sub_tabs.count())]
assert TAB_NAME in names, f"{TAB_NAME!r} not in {names}"
tab.sub_tabs.setCurrentIndex(names.index(TAB_NAME))
PAGE = tab.sub_tabs.widget(names.index(TAB_NAME))
tab.refresh(db, hero, d_from, d_to, currency, None, None, 'cash')


def ready():
    """The tab populates asynchronously, so a fixed delay either wastes
    time or fires early. Wait for the header count and for the page to
    have had real widgets added -- counting widgets rather than guessing
    at a pixel height, which silently never matched for the short Study
    Queue card."""
    if not tab.hands_lbl.text().strip():
        return False
    lay = inner.layout()
    return lay is not None and any(lay.itemAt(i).widget()
                                   for i in range(lay.count()))


inner = PAGE.widget() if hasattr(PAGE, "widget") else PAGE

attempts = {"n": 0}


def poll():
    attempts["n"] += 1
    if ready():
        print(f"widgets present after ~{attempts['n']}s; letting layout settle")
        inner.adjustSize()
        for _ in range(12):
            app.processEvents()
        QTimer.singleShot(1200, capture)
    elif attempts["n"] > 90:
        print("gave up waiting; label =", repr(tab.hands_lbl.text()))
        app.quit()
    else:
        QTimer.singleShot(1000, poll)


def capture():
        print("hands label:", tab.hands_lbl.text())
        print("page content height:", inner.sizeHint().height())
        from PyQt6.QtWidgets import QLabel
        texts = [w.text().strip() for w in inner.findChildren(QLabel) if w.text().strip()]
        print(f"labels on this page ({len(texts)}):")
        for t in texts[:8]:
            print("   ", t[:130].encode("ascii", "replace").decode())
        img = QImage(WIDTH, HEIGHT, QImage.Format.Format_ARGB32)
        tab.render(img)
        out = SCRATCH / OUT_NAME
        img.save(str(out))
        print("wrote", out)
        app.quit()


QTimer.singleShot(1500, poll)
app.exec()
