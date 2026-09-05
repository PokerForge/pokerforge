"""SF Poker — the real application shell: header, period/stakes filter bar,
and tabs (Overview, Sessions, Stats, Population), matching the visual
structure of the original PT4-based dashboard.

Hand histories are parsed once into memory (for the villain-profile and
hand-replayer paths, which still work directly over Hand objects), then
imported into a SQLite database (database/repository.py) with every stat
flag precomputed at import time (database/hand_stats_builder.py). Overview
and Population queries go through that database (database/queries.py) —
an indexed aggregate query — instead of re-walking raw hand actions on
every period/stakes change, which is what made "All Time" slow before.

Sessions and Stats tabs are placeholders for now — Overview and Population
are the two built out first since they're the most valuable/emblematic.
"""
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from datetime import date

from PyQt6.QtCore import Qt, QDate
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QFrame, QTabWidget, QComboBox, QProgressDialog, QPushButton,
    QDialog, QDateEdit, QMessageBox,
)

from core.importer import parse_directory_incremental
from core.logging_setup import configure_logging, install_crash_handler
from config.version import APP_VERSION
from core.update_checker import check_for_update
from config.paths import profile_data_dir, resource_dir
from ui.theme import STYLE, BG, BG2, GREEN, BORDER, lbl
from ui.header_banner import HeaderBanner
from ui.date_utils import PERIODS, date_range, CUSTOM_RANGE_LABEL
from ui.overview_tab import OverviewTab
from ui.sessions_tab import SessionsTab
from ui.stats_tab import StatsTab
from ui.population_tab import PopulationTab
from ui.async_worker import AsyncRunner
from ui.hero_detect import detect_hero, normalize_hero_aliases, dominant_currency
from ui.hand_history_dirs_dialog import HandHistoryDirsDialog
from ui.hero_setup_dialog import HeroSetupDialog
from ui.profile_dialog import ProfileDialog
from ui.getting_started_dialog import GettingStartedDialog
from config.profiles import get_active_display_name
from core.currency import convert_hands_to_usd
from database.repository import PokerDatabase
from database.queries import available_stakes_query
from config.settings import (
    get_hero_name, set_hero_name, get_currency_symbol, set_currency_symbol,
    get_hand_history_dirs, set_hand_history_dirs,
)

DB_PATH = profile_data_dir() / "sf_poker.db"
logger = logging.getLogger(__name__)


class CustomRangeDialog(QDialog):
    """Small From/To date picker — each QDateEdit's setCalendarPopup(True)
    gives the "small calendar pops up" picking experience directly, no
    custom calendar widget needed."""

    def __init__(self, d_from: date, d_to: date, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select Date Range")
        self.setStyleSheet(STYLE)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(14)

        from_row = QHBoxLayout()
        from_row.addWidget(lbl("From", dim=True))
        self.from_edit = QDateEdit(QDate(d_from.year, d_from.month, d_from.day))
        self.from_edit.setCalendarPopup(True)
        self.from_edit.setDisplayFormat("yyyy-MM-dd")
        from_row.addWidget(self.from_edit, 1)
        lay.addLayout(from_row)

        to_row = QHBoxLayout()
        to_row.addWidget(lbl("To", dim=True))
        self.to_edit = QDateEdit(QDate(d_to.year, d_to.month, d_to.day))
        self.to_edit.setCalendarPopup(True)
        self.to_edit.setDisplayFormat("yyyy-MM-dd")
        self.to_edit.setMaximumDate(QDate.currentDate())
        to_row.addWidget(self.to_edit, 1)
        lay.addLayout(to_row)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        ok_btn = QPushButton("OK")
        ok_btn.clicked.connect(self.accept)
        btn_row.addWidget(ok_btn)
        lay.addLayout(btn_row)

    def selected_range(self) -> tuple[date, date]:
        f, t = self.from_edit.date(), self.to_edit.date()
        d_from = date(f.year(), f.month(), f.day())
        d_to = date(t.year(), t.month(), t.day())
        return (d_from, d_to) if d_from <= d_to else (d_to, d_from)


class PlaceholderTab(QWidget):
    def __init__(self, name):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.addStretch()
        text = lbl(f"{name} — coming soon", size=14, dim=True)
        text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(text)
        lay.addStretch()


class AppWindow(QMainWindow, AsyncRunner):
    def __init__(self, hero, db, currency="£"):
        super().__init__()
        self._init_async()
        self.hero = hero
        self.db = db
        self.currency = currency
        self._custom_range = None
        self._last_period_text = "This Month"
        active_profile = get_active_display_name()
        # Only clutters the title once multi-profile is actually in use —
        # a single-profile install looks exactly as it always has.
        title = "SF Poker" if active_profile == "Default" else f"SF Poker — {active_profile}"
        self.setWindowTitle(title)
        self.setMinimumSize(1300, 800)
        self.resize(1680, 1000)
        self._build_menu_bar()

        central = QWidget()
        self.setCentralWidget(central)
        main_lay = QVBoxLayout(central)
        main_lay.setContentsMargins(0, 0, 0, 0)
        main_lay.setSpacing(0)

        # Header — the banner artwork already has its own "SF POKER" logo,
        # so this row just overlays the one piece of real data it can't
        # bake in: hero + how many hands are loaded.
        header = HeaderBanner()
        header.setFixedHeight(60)
        hl = QHBoxLayout(header)
        hl.setContentsMargins(24, 0, 24, 0)
        hl.addStretch()
        self.header_hands_lbl = lbl(f"Hero: {hero}  |  {db.hand_count():,} hands loaded", size=12, color="white")
        hl.addWidget(self.header_hands_lbl)
        main_lay.addWidget(header)

        # Filter bar
        fbar = QFrame()
        fbar.setStyleSheet(f"background:{BG};border-bottom:1px solid {BORDER};")
        fbar.setFixedHeight(52)
        fl = QHBoxLayout(fbar)
        fl.setContentsMargins(24, 0, 24, 0)
        fl.setSpacing(12)
        fl.addWidget(lbl("Period", dim=True))
        self.period_cb = QComboBox()
        self.period_cb.addItems(PERIODS + [CUSTOM_RANGE_LABEL])
        self.period_cb.setCurrentText("This Month")
        # activated (not currentTextChanged) fires on every user pick,
        # even re-picking the item that's already selected — needed so
        # choosing "Custom Range..." again re-opens the calendar to
        # adjust it, rather than only working the first time.
        self.period_cb.activated.connect(self._on_period_changed)
        fl.addWidget(self.period_cb)
        fl.addSpacing(8)
        fl.addWidget(lbl("Stakes", dim=True))
        self.stakes_cb = QComboBox()
        self.stakes_cb.addItem("All Stakes")
        self.stakes_cb.currentTextChanged.connect(self._apply_filters)
        fl.addWidget(self.stakes_cb)
        fl.addStretch()
        self.info_lbl = lbl("", dim=True)
        fl.addWidget(self.info_lbl)
        fl.addSpacing(12)
        self.refresh_btn = QPushButton("↻ Refresh")
        self.refresh_btn.setFixedHeight(28)
        self.refresh_btn.setStyleSheet(
            f"QPushButton {{ background:{BG2}; border:1px solid {BORDER}; border-radius:4px; padding:0 12px; }}"
            f"QPushButton:hover {{ border-color:{GREEN}; }}"
            f"QPushButton:disabled {{ color:#888; }}"
        )
        self.refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.refresh_btn.clicked.connect(self._on_refresh_clicked)
        fl.addWidget(self.refresh_btn)
        main_lay.addWidget(fbar)

        # Tabs
        self.tabs = QTabWidget()
        self.tab_overview = OverviewTab()
        self.tab_sessions = SessionsTab()
        self.tab_stats = StatsTab(hero, db, currency)
        self.tab_population = PopulationTab(hero, db, currency)
        self.tabs.addTab(self.tab_overview, "  Overview  ")
        self.tabs.addTab(self.tab_sessions, "  Sessions  ")
        self.tabs.addTab(self.tab_stats, "  Stats  ")
        self.tabs.addTab(self.tab_population, "  Population  ")
        wrap = QWidget()
        wl = QVBoxLayout(wrap)
        wl.setContentsMargins(16, 12, 16, 16)
        wl.addWidget(self.tabs)
        main_lay.addWidget(wrap)

        self._on_period_changed()

    def _on_period_changed(self):
        """Period changed — the set of stakes worth offering depends on the
        period (no point listing a stake from 2019 while viewing "This
        Month"), so rebuild the dropdown before re-filtering the tabs.
        Runs off the UI thread like everything else that touches the
        database — this one's fast (well under a second even at "All
        Time"), but there's no reason for any DB call to block painting."""
        if self.period_cb.currentText() == CUSTOM_RANGE_LABEL:
            default_from, default_to = self._custom_range or date_range("This Month")
            dlg = CustomRangeDialog(default_from, default_to, parent=self)
            if dlg.exec():
                self._custom_range = dlg.selected_range()
            else:
                # Cancelled — revert to whatever period was active before,
                # without re-entering this handler (setCurrentText alone
                # doesn't fire `activated`, only real user picks do).
                self.period_cb.setCurrentText(self._last_period_text)
                return
        self._last_period_text = self.period_cb.currentText()

        d_from, d_to = self._current_date_range()
        self.run_async(
            lambda: available_stakes_query(self.db, self.hero, d_from, d_to),
            self._on_stakes_loaded,
        )

    def _current_date_range(self):
        if self.period_cb.currentText() == CUSTOM_RANGE_LABEL and self._custom_range:
            return self._custom_range
        return date_range(self.period_cb.currentText())

    def _on_stakes_loaded(self, stakes):
        prev = self.stakes_cb.currentText()
        self.stakes_cb.blockSignals(True)
        self.stakes_cb.clear()
        self.stakes_cb.addItem("All Stakes")
        self.stakes_cb.addItems(stakes)
        idx = self.stakes_cb.findText(prev)
        self.stakes_cb.setCurrentIndex(idx if idx >= 0 else 0)
        self.stakes_cb.blockSignals(False)
        self._apply_filters()

    def _apply_filters(self):
        d_from, d_to = self._current_date_range()
        self.info_lbl.setText(f"{d_from} → {d_to}")
        stake = self.stakes_cb.currentText()
        stake = None if stake in ("", "All Stakes") else stake
        self.tab_overview.refresh(self.db, self.hero, d_from, d_to, self.currency, stake)
        self.tab_sessions.refresh(self.db, self.hero, d_from, d_to, self.currency, stake)
        self.tab_stats.refresh(self.db, self.hero, d_from, d_to, self.currency, stake)
        self.tab_population.refresh(d_from, d_to, stake)

    def _on_refresh_clicked(self):
        """Manual re-check of the watched folders, for new hands played
        since the app was launched — the automatic check only runs once,
        at startup, so this covers a session that's stayed open while you
        kept playing."""
        self.refresh_btn.setEnabled(False)
        self.refresh_btn.setText("Checking…")
        QApplication.processEvents()
        try:
            _import_new_hands(self, self.db, self.hero)
        finally:
            self.refresh_btn.setEnabled(True)
            self.refresh_btn.setText("↻ Refresh")
        self.header_hands_lbl.setText(f"Hero: {self.hero}  |  {self.db.hand_count():,} hands loaded")
        self._apply_filters()

    def _on_manage_folders_clicked(self):
        dlg = HandHistoryDirsDialog(get_hand_history_dirs(), first_run=False, parent=self)
        if not dlg.exec():
            return
        set_hand_history_dirs(dlg.selected_dirs())
        self._on_refresh_clicked()

    def _on_switch_profile_clicked(self):
        ProfileDialog(parent=self).exec()

    def _on_getting_started_clicked(self):
        GettingStartedDialog(parent=self).exec()

    def _build_menu_bar(self):
        file_menu = self.menuBar().addMenu("&File")
        file_menu.addAction("Manage Hand History Folders...", self._on_manage_folders_clicked)
        file_menu.addAction("Switch Profile...", self._on_switch_profile_clicked)
        file_menu.addSeparator()
        file_menu.addAction("Exit", self.close)

        help_menu = self.menuBar().addMenu("&Help")
        help_menu.addAction("Getting Started...", self._on_getting_started_clicked)
        help_menu.addSeparator()
        help_menu.addAction("Check for Updates...", self._on_check_updates_clicked)
        help_menu.addAction("About SF Poker...", self._on_about_clicked)

    def _on_about_clicked(self):
        QMessageBox.about(
            self, "About SF Poker",
            f"<h3>SF Poker</h3>"
            f"<p>Version {APP_VERSION}</p>"
            f"<p>A personal poker-stats tracker and hand-history analyzer.</p>"
        )

    def _on_check_updates_clicked(self):
        # Only ever runs when the user explicitly asks — see
        # core/update_checker.py's docstring for why that matters here.
        self.run_async(check_for_update, self._on_update_check_result, key="update_check")

    def _on_update_check_result(self, result):
        if not result.checked:
            QMessageBox.information(self, "Check for Updates",
                                     result.error or "Couldn't check for updates right now.")
            return
        if result.update_available:
            msg = f"A new version ({result.latest_version}) is available — you have {APP_VERSION}."
            if result.notes:
                msg += f"\n\n{result.notes}"
            if result.download_url:
                msg += f"\n\n{result.download_url}"
            QMessageBox.information(self, "Update Available", msg)
        else:
            QMessageBox.information(self, "Check for Updates", "You're up to date.")


def _import_new_hands(app_or_window, db, hero) -> int:
    """Checks the watched folders for new/changed files and imports
    whatever new hands they contain — shared by the startup check (main())
    and the Refresh button (AppWindow._on_refresh_clicked()), so both stay
    in sync rather than drifting into two slightly different pipelines."""
    dirs = get_hand_history_dirs()
    logger.info("Checking hand history files...")
    hands, errors, files_parsed, files_skipped, fingerprints = parse_directory_incremental(dirs, db)
    logger.info("Parsed %d new/changed file(s), skipped %d already-imported file(s) "
                "— %d new hand(s) found (%d errors)", files_parsed, files_skipped, len(hands), len(errors))

    if not hands:
        return 0

    normalize_hero_aliases(hands, hero)
    convert_hands_to_usd(hands)

    progress = QProgressDialog(
        f"Building stats database — {len(hands):,} new hand(s)...",
        None, 0, len(hands), app_or_window if isinstance(app_or_window, QWidget) else None)
    progress.setWindowTitle("SF Poker")
    progress.setMinimumDuration(0)
    progress.setWindowModality(Qt.WindowModality.WindowModal)
    progress.setValue(0)

    def on_progress(done, total):
        progress.setValue(done)
        QApplication.processEvents()

    t0 = time.time()
    db.import_hands(hands, ev_iterations=500, on_progress=on_progress)
    db.mark_files_imported(fingerprints)
    logger.info("Imported %d new hand(s) in %.1fs", len(hands), time.time() - t0)
    progress.setValue(len(hands))
    return len(hands)


def main():
    # stdout is block-buffered (not line-buffered) when not attached to a
    # real terminal, so these prints otherwise never appear if the process
    # is killed/backgrounded before it happens to flush on its own.
    configure_logging()
    install_crash_handler()
    if sys.platform == "win32":
        # Without a distinct App User Model ID, Windows groups this process
        # under python.exe/pythonw.exe's own taskbar identity and shows its
        # icon instead of ours, no matter what QIcon is set below.
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("SFPoker.App")

    app = QApplication(sys.argv)
    app.setStyleSheet(STYLE)
    icon_path = resource_dir() / "assets" / "app_icon_chip.ico"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
    db = PokerDatabase(DB_PATH)

    dirs = get_hand_history_dirs()
    if not dirs:
        # Fresh install (or every folder was removed) — nothing to scan
        # until the player tells us where their hand histories live.
        wizard = HandHistoryDirsDialog([], first_run=True)
        wizard.exec()
        dirs = wizard.selected_dirs()
        set_hand_history_dirs(dirs)

    logger.info("Checking hand history files...")
    hands, errors, files_parsed, files_skipped, fingerprints = parse_directory_incremental(dirs, db)
    logger.info("Parsed %d new/changed file(s), skipped %d already-imported file(s) "
                "— %d new hand(s) found (%d errors)", files_parsed, files_skipped, len(hands), len(errors))

    hero = get_hero_name()
    currency = get_currency_symbol()
    first_run = hero is None
    if first_run:
        # Hero identity is a global property of the whole history (whoever
        # appears in the most hands) — only trustworthy to detect when
        # this batch actually IS the whole history, i.e. a fresh database
        # where nothing has been imported yet, so `hands` is everything.
        detected_hero = detect_hero(hands)
        detected_currency = dominant_currency(hands, detected_hero) if hands else "£"
        if hands:
            # Let the player correct a wrong guess before it's locked in —
            # nothing else here can undo a bad auto-detection later.
            confirm = HeroSetupDialog(detected_hero, detected_currency)
            confirm.exec()
            hero = confirm.selected_hero() or detected_hero
            currency = confirm.selected_currency() or detected_currency
        else:
            hero, currency = detected_hero, detected_currency
        set_hero_name(hero)
        set_currency_symbol(currency)
        logger.info("Detected hero: %s, currency: %s", hero, currency)

    if hands:
        normalize_hero_aliases(hands, hero)
        convert_hands_to_usd(hands)

    if hands:
        progress = QProgressDialog(
            f"Building stats database — {len(hands):,} new hand(s) (one-time per batch; instant next launch)...",
            None, 0, len(hands))
        progress.setWindowTitle("SF Poker — Setting up")
        progress.setMinimumDuration(0)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setValue(0)

        def on_progress(done, total):
            progress.setValue(done)
            app.processEvents()
            logger.debug("...%d/%d hands processed", done, total)

        logger.info("Building stats database (%d new hands)...", len(hands))
        t0 = time.time()
        # 500 Monte Carlo iterations per all-in hand rather than 3000 — the
        # earlier correctness check (comparing this DB path against the
        # existing trusted Python implementation) showed aggregate EV
        # stats are robust to iteration count; only individual-hand
        # precision drops, and this is a one-time bulk import, not a
        # per-hand precision tool.
        db.import_hands(hands, ev_iterations=500, on_progress=on_progress)
        db.mark_files_imported(fingerprints)
        logger.info("Database ready in %.1fs", time.time() - t0)
        progress.setValue(len(hands))

    win = AppWindow(hero, db, currency)
    if icon_path.exists():
        win.setWindowIcon(QIcon(str(icon_path)))
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    # A startup exception here (or any later exception from inside a Qt
    # slot while the app is running) is caught by the sys.excepthook
    # install_crash_handler() set up inside main() — logged with a full
    # traceback and shown to the user as a short message, not raw
    # PyInstaller crash-dialog text.
    main()
