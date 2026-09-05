"""PokerForge — the real application shell: header, period/stakes filter bar,
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
import json
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from datetime import date

from PyQt6.QtCore import Qt, QDate, QUrl
from PyQt6.QtGui import QIcon, QDesktopServices, QShortcut, QKeySequence
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QFrame, QTabWidget, QComboBox, QProgressDialog, QPushButton,
    QDialog, QDateEdit, QMessageBox, QFileDialog,
)

from core.importer import parse_directory_incremental, missing_configured_folders
from core.logging_setup import configure_logging, install_crash_handler, LOG_PATH
from core.single_instance import acquire_single_instance_lock
from config.version import APP_VERSION, SUPPORT_EMAIL
from core.update_checker import check_for_update
from core.backup import create_backup, restore_backup, create_auto_backup_if_due
from core.db_health import check_database_health
from config.paths import profile_data_dir, resource_dir
from ui.theme import STYLE, BG, BG2, GREEN, BORDER, lbl
from ui.header_banner import HeaderBanner
from ui.date_utils import PERIODS, date_range, CUSTOM_RANGE_LABEL
from ui.overview_tab import OverviewTab
from ui.sessions_tab import SessionsTab
from ui.stats_tab import StatsTab
from ui.population_tab import PopulationTab
from ui.async_worker import AsyncRunner
from ui.hero_detect import detect_hero, normalize_hero_aliases, dominant_currency, hero_hand_share
from ui.hand_history_dirs_dialog import HandHistoryDirsDialog
from ui.hero_setup_dialog import HeroSetupDialog
from ui.profile_dialog import ProfileDialog, restart_app
from ui.settings_dialog import SettingsDialog
from ui.getting_started_dialog import GettingStartedDialog
from ui.diagnostics_dialog import DiagnosticsDialog
from ui.whats_new_dialog import WhatsNewDialog
from core.changelog import get_changelog_entry
from ui.live_watcher import LiveFolderWatcher
from config.profiles import get_active_display_name
from core.currency import convert_hands_to_usd
from database.repository import PokerDatabase
from database.queries import available_stakes_query
from config.settings import (
    get_hero_name, set_hero_name, get_currency_symbol, set_currency_symbol,
    get_hand_history_dirs, set_hand_history_dirs,
    get_last_seen_version, set_last_seen_version,
    get_live_auto_refresh_enabled,
    get_last_auto_backup_date, set_last_auto_backup_date,
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
        title = "PokerForge" if active_profile == "Default" else f"PokerForge — {active_profile}"
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
        self.folder_warning_lbl = lbl("", size=12, color="#f85149")
        self.folder_warning_lbl.setToolTip("File > Manage Hand History Folders to fix this")
        self.folder_warning_lbl.hide()
        hl.addWidget(self.folder_warning_lbl)
        hl.addSpacing(12)
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
        self.refresh_btn.setToolTip("Refresh (Ctrl+R)")
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

        QShortcut(QKeySequence("Ctrl+R"), self, activated=self._on_refresh_clicked)

        self._live_watcher = LiveFolderWatcher(self)
        self._live_watcher.changed.connect(self._on_live_files_changed)
        self._apply_live_watch_setting()

        self._update_folder_warning()
        self._on_period_changed()

    def _apply_live_watch_setting(self):
        """(Re)syncs the live folder watcher with the current setting and
        configured folders — called at startup, after Settings closes
        (the auto-refresh checkbox takes effect immediately, no restart),
        and after Manage Folders changes which directories are watched."""
        if get_live_auto_refresh_enabled():
            self._live_watcher.watch(get_hand_history_dirs())
        else:
            self._live_watcher.watch([])

    def _on_live_files_changed(self):
        """Debounced callback from the live folder watcher — same import
        pipeline as the Refresh button, just triggered automatically by a
        filesystem change instead of a click. Runs synchronously on the
        main thread, same as the manual Refresh path (see
        database/repository.py's PokerDatabase docstring on why writes
        only ever happen there — introducing a second, concurrent writer
        from a background thread would break that invariant). Measured
        overhead for a small live-play batch is ~150ms regardless of
        whether it's 1 or 10 hands (dominated by fixed multiprocessing
        pool startup cost), so a brief main-thread pause here is an
        acceptable trade for not risking a corrupted database."""
        new_count = _import_new_hands(self, self.db, self.hero, dialog_threshold=15)
        self._apply_live_watch_setting()  # picks up any new files/subfolders that appeared
        if new_count:
            self.header_hands_lbl.setText(f"Hero: {self.hero}  |  {self.db.hand_count():,} hands loaded")
            self._update_folder_warning()
            self._apply_filters()

    def _update_folder_warning(self):
        missing = missing_configured_folders(get_hand_history_dirs())
        if missing:
            noun = "folder" if len(missing) == 1 else "folders"
            self.folder_warning_lbl.setText(f"⚠ {len(missing)} hand-history {noun} not found")
            self.folder_warning_lbl.show()
        else:
            self.folder_warning_lbl.hide()

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
        self._update_folder_warning()
        self._apply_filters()
        self._apply_live_watch_setting()

    def _on_manage_folders_clicked(self):
        dlg = HandHistoryDirsDialog(get_hand_history_dirs(), first_run=False, parent=self)
        if not dlg.exec():
            return
        set_hand_history_dirs(dlg.selected_dirs())
        self._on_refresh_clicked()

    def _on_switch_profile_clicked(self):
        ProfileDialog(parent=self).exec()

    def _on_settings_clicked(self):
        SettingsDialog(parent=self).exec()
        self._apply_live_watch_setting()

    def _on_getting_started_clicked(self):
        GettingStartedDialog(parent=self).exec()

    def _on_backup_clicked(self):
        default_name = f"PokerForge Backup {date.today().isoformat()}.zip"
        path, _ = QFileDialog.getSaveFileName(self, "Backup My Data", default_name, "Zip Files (*.zip)")
        if not path:
            return
        try:
            create_backup(self.db.conn, profile_data_dir(), Path(path))
        except Exception as exc:
            logger.exception("Backup failed")
            QMessageBox.warning(self, "Backup Failed", f"Couldn't create the backup:\n{exc}")
            return
        QMessageBox.information(self, "Backup Complete", f"Your data was backed up to:\n{path}")

    def _on_restore_clicked(self):
        path, _ = QFileDialog.getOpenFileName(self, "Restore from Backup", "", "Zip Files (*.zip)")
        if not path:
            return
        reply = QMessageBox.warning(
            self, "Restore from Backup",
            "This replaces your current hands, stats, and settings for this profile with "
            "whatever's in the backup. This cannot be undone.\n\n"
            "PokerForge will restart afterward. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            self.db.close()
            restore_backup(Path(path), profile_data_dir())
        except Exception as exc:
            logger.exception("Restore failed")
            QMessageBox.critical(self, "Restore Failed", f"Couldn't restore the backup:\n{exc}")
            return
        restart_app()

    def _on_verify_health_clicked(self):
        report = check_database_health(self.db)
        if report.ok:
            QMessageBox.information(
                self, "Database Health",
                f"Everything checks out — {report.hand_count:,} hands, "
                f"{report.stats_row_count:,} stat rows, integrity check passed.")
        else:
            QMessageBox.warning(
                self, "Database Health",
                "Found some issues:\n\n" + "\n".join(f"• {issue}" for issue in report.issues))

    def _on_rebuild_stats_clicked(self):
        reply = QMessageBox.question(
            self, "Rebuild Stats Database",
            "This recomputes every stat from your already-imported hands — useful if numbers "
            "look wrong after an update. It doesn't re-import or delete any hands, but can take "
            "a few minutes for a large database. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        total = self.db.hand_count()
        progress = QProgressDialog(f"Rebuilding stats for {total:,} hands...", None, 0, total, self)
        progress.setWindowTitle("PokerForge")
        progress.setMinimumDuration(0)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setValue(0)

        def on_progress(done, _total):
            progress.setValue(done)
            QApplication.processEvents()

        n = self.db.rebuild_hand_player_stats(ev_iterations=500, on_progress=on_progress)
        progress.setValue(total)
        QMessageBox.information(self, "Rebuild Complete", f"Rebuilt stats for {n:,} hands.")
        self._apply_filters()

    def _on_diagnostics_clicked(self):
        DiagnosticsDialog(self.db, parent=self).exec()

    def _on_load_demo_data_clicked(self):
        from config.profiles import list_profiles, create_profile, set_active_profile

        existing = {name: pid for pid, name in list_profiles()}
        demo_id = existing.get("Demo")

        if demo_id:
            reply = QMessageBox.question(
                self, "Load Demo Data",
                "A Demo profile already exists. Regenerate it with fresh sample data "
                "(replacing what's there), or just switch to it as-is?\n\n"
                "Yes = regenerate, No = switch without changing it.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                | QMessageBox.StandardButton.Cancel,
            )
            if reply == QMessageBox.StandardButton.Cancel:
                return
            regenerate = reply == QMessageBox.StandardButton.Yes
        else:
            reply = QMessageBox.question(
                self, "Load Demo Data",
                "This creates a new \"Demo\" profile with synthetic hand histories, so "
                "you can try PokerForge without needing your own data. It won't affect "
                "your real profile. Continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
            demo_id = create_profile("Demo")
            regenerate = True

        if regenerate:
            self._populate_demo_profile(demo_id)

        set_active_profile(demo_id)
        QMessageBox.information(self, "Load Demo Data",
                                 "PokerForge needs to restart to switch to the Demo profile.")
        restart_app()

    def _populate_demo_profile(self, demo_id: str):
        from core.demo_data import generate_demo_hands, DEMO_HERO

        demo_dir = profile_data_dir(demo_id)
        db_path = demo_dir / "sf_poker.db"
        if db_path.exists():
            db_path.unlink()
        (demo_dir / "settings.json").write_text(json.dumps({
            "hero_aliases": [], "hero_name": DEMO_HERO, "currency_symbol": "£",
            "position_table_stat_ids": None, "trend_stat_ids": None,
            "trend_interval_days": 14, "hand_history_dirs": [],
        }, indent=2), encoding="utf-8")

        progress = QProgressDialog("Generating demo data...", None, 0, 0, self)
        progress.setWindowTitle("PokerForge")
        progress.setMinimumDuration(0)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.show()
        QApplication.processEvents()
        try:
            hands = generate_demo_hands()
            demo_db = PokerDatabase(db_path)
            try:
                demo_db.import_hands(hands, ev_iterations=100)
            finally:
                demo_db.close()
        finally:
            progress.close()

    def _on_report_bug_clicked(self):
        import urllib.parse
        subject = urllib.parse.quote("PokerForge Bug Report")
        body = urllib.parse.quote(
            "Describe the issue:\n\n\n"
            "---\n"
            f"App version: {APP_VERSION}\n"
            f"Log file: {LOG_PATH}\n"
            "(Please attach the log file above if possible.)"
        )
        to = SUPPORT_EMAIL or ""
        QDesktopServices.openUrl(QUrl(f"mailto:{to}?subject={subject}&body={body}"))

    def _build_menu_bar(self):
        file_menu = self.menuBar().addMenu("&File")
        file_menu.addAction("Manage Hand History Folders...", self._on_manage_folders_clicked)
        file_menu.addAction("Switch Profile...", self._on_switch_profile_clicked)
        file_menu.addAction("Settings...", self._on_settings_clicked)
        file_menu.addSeparator()
        file_menu.addAction("Exit", self.close)

        tools_menu = self.menuBar().addMenu("&Tools")
        tools_menu.addAction("Backup My Data...", self._on_backup_clicked)
        tools_menu.addAction("Restore from Backup...", self._on_restore_clicked)
        tools_menu.addSeparator()
        tools_menu.addAction("Verify Database Health...", self._on_verify_health_clicked)
        tools_menu.addAction("Rebuild Stats Database...", self._on_rebuild_stats_clicked)
        tools_menu.addAction("Database && Diagnostics...", self._on_diagnostics_clicked)
        tools_menu.addSeparator()
        tools_menu.addAction("Load Demo Data...", self._on_load_demo_data_clicked)

        help_menu = self.menuBar().addMenu("&Help")
        help_menu.addAction("Getting Started...", self._on_getting_started_clicked)
        help_menu.addSeparator()
        help_menu.addAction("Report a Bug...", self._on_report_bug_clicked)
        help_menu.addAction("Check for Updates...", self._on_check_updates_clicked)
        help_menu.addAction("About PokerForge...", self._on_about_clicked)

    def _on_about_clicked(self):
        QMessageBox.about(
            self, "About PokerForge",
            f"<h3>PokerForge</h3>"
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


def _import_new_hands(app_or_window, db, hero, dialog_threshold: int = 1) -> int:
    """Checks the watched folders for new/changed files and imports
    whatever new hands they contain — shared by the startup check (main()),
    the Refresh button (AppWindow._on_refresh_clicked()), and the live
    folder watcher (AppWindow._on_live_files_changed()), so all three stay
    in sync rather than drifting into slightly different pipelines.

    `dialog_threshold` skips the modal progress dialog for a batch smaller
    than this many hands — measured at ~150ms regardless of batch size for
    up to ~10 hands (fixed multiprocessing pool startup cost dominates),
    so popping a dialog for a single new hand during live play would just
    flash uselessly. The live watcher passes a higher threshold than the
    default of 1 (which keeps the dialog for every manual Refresh/startup
    call, matching prior behavior exactly)."""
    dirs = get_hand_history_dirs()
    logger.info("Checking hand history files...")
    hands, errors, files_parsed, files_skipped, fingerprints = parse_directory_incremental(dirs, db)
    logger.info("Parsed %d new/changed file(s), skipped %d already-imported file(s) "
                "— %d new hand(s) found (%d errors)", files_parsed, files_skipped, len(hands), len(errors))

    if not hands:
        return 0

    # A silent, automatic safety net taken right before today's first
    # write — at most once per day, so this doesn't add overhead to the
    # live folder watcher's frequent small imports (see
    # core/backup.py's create_auto_backup_if_due).
    try:
        new_date = create_auto_backup_if_due(
            db.conn, db.db_path.parent, date.today().isoformat(), get_last_auto_backup_date())
        if new_date:
            set_last_auto_backup_date(new_date)
    except Exception:
        logger.exception("Automatic pre-import backup failed — continuing with the import anyway")

    normalize_hero_aliases(hands, hero)
    convert_hands_to_usd(hands)

    t0 = time.time()
    if len(hands) < dialog_threshold:
        db.import_hands(hands, ev_iterations=500)
    else:
        progress = QProgressDialog(
            f"Building stats database — {len(hands):,} new hand(s)...",
            None, 0, len(hands), app_or_window if isinstance(app_or_window, QWidget) else None)
        progress.setWindowTitle("PokerForge")
        progress.setMinimumDuration(0)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setValue(0)

        def on_progress(done, total):
            progress.setValue(done)
            QApplication.processEvents()

        db.import_hands(hands, ev_iterations=500, on_progress=on_progress)
        progress.setValue(len(hands))
    db.mark_files_imported(fingerprints)
    logger.info("Imported %d new hand(s) in %.1fs", len(hands), time.time() - t0)
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
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("PokerForge.App")

    app = QApplication(sys.argv)
    app.setStyleSheet(STYLE)
    icon_path = resource_dir() / "assets" / "app_icon_chip.ico"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    instance_lock = acquire_single_instance_lock()
    if instance_lock is None:
        # A second launch (e.g. double-clicking the desktop shortcut
        # twice) would otherwise open a second process against the same
        # SQLite database — refuse cleanly instead of risking a confusing
        # "database is locked" error later.
        QMessageBox.information(None, "PokerForge", "PokerForge is already running.")
        return

    db = PokerDatabase(DB_PATH)

    dirs = get_hand_history_dirs()
    if not dirs and get_hero_name() is None:
        # Genuinely nothing set up yet (no folders AND no hero identity) —
        # a profile that already has a hero (e.g. Load Demo Data, or a
        # real profile someone intentionally cleared all folders from
        # while keeping its already-imported data) has nothing to fix
        # here, even though its folder list also happens to be empty.
        wizard = HandHistoryDirsDialog([], first_run=True)
        wizard.exec()
        dirs = wizard.selected_dirs()
        set_hand_history_dirs(dirs)

    logger.info("Checking hand history files...")
    scan_progress = QProgressDialog("Scanning hand-history files...", None, 0, 0)
    scan_progress.setWindowTitle("PokerForge")
    scan_progress.setWindowModality(Qt.WindowModality.WindowModal)
    # Only appears if the scan actually takes a moment (a first run against
    # a folder with thousands of existing files) — a normal relaunch,
    # where almost everything is already-imported and quickly skipped,
    # never shows this at all.
    scan_progress.setMinimumDuration(500)

    def on_startup_scan_progress(done, total):
        if scan_progress.maximum() != total:
            scan_progress.setMaximum(total)
        scan_progress.setValue(done)
        app.processEvents()

    hands, errors, files_parsed, files_skipped, fingerprints = parse_directory_incremental(
        dirs, db, on_progress=on_startup_scan_progress)
    scan_progress.close()
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
            share = hero_hand_share(hands, detected_hero)
            confirm = HeroSetupDialog(detected_hero, detected_currency, hero_share=share)
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
        progress.setWindowTitle("PokerForge — Setting up")
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

    last_seen_version = get_last_seen_version()
    if last_seen_version != APP_VERSION:
        # Skip the popup on a genuinely first-ever launch (nothing "new"
        # to announce over — that's what the Getting Started guide and
        # first-run wizard are for) but still record the version, so
        # upgrading later from this point on shows What's New as expected.
        changelog_body = get_changelog_entry(APP_VERSION)
        if last_seen_version is not None and changelog_body:
            WhatsNewDialog(APP_VERSION, changelog_body, parent=win).exec()
        set_last_seen_version(APP_VERSION)

    sys.exit(app.exec())


if __name__ == "__main__":
    # A startup exception here (or any later exception from inside a Qt
    # slot while the app is running) is caught by the sys.excepthook
    # install_crash_handler() set up inside main() — logged with a full
    # traceback and shown to the user as a short message, not raw
    # PyInstaller crash-dialog text.
    main()
