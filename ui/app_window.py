"""PokerForge — the real application shell: header, period/stakes filter bar,
and tabs (Overview, Sessions, Stats, Population), matching the visual
structure of the original dashboard.

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
from ui.game_type_toggle import GameTypeToggle
from ui.async_worker import AsyncRunner
from ui.hero_detect import detect_hero, normalize_hero_aliases, dominant_currency, hero_hand_share
from ui.hand_history_dirs_dialog import HandHistoryDirsDialog
from ui.hero_setup_dialog import HeroSetupDialog
from ui.profile_dialog import ProfileDialog, restart_app
from ui.settings_dialog import SettingsDialog
from ui.license_dialog import LicenseDialog
from core.licensing import activate_key, refresh_license_status
from ui.getting_started_dialog import GettingStartedDialog
from ui.app_tour import TourOverlay
from ui.diagnostics_dialog import DiagnosticsDialog
from ui.whats_new_dialog import WhatsNewDialog
from core.changelog import get_changelog_entry
from ui.live_watcher import LiveFolderWatcher
from config.profiles import get_active_display_name
from core.currency import convert_hands_to_usd
from database.repository import PokerDatabase
from database.queries import available_stakes_query, available_sites_query
from ui.sites import site_label, site_value
from config.settings import (
    get_hero_name, set_hero_name, get_currency_symbol, set_currency_symbol,
    get_hand_history_dirs, set_hand_history_dirs,
    get_last_seen_version, set_last_seen_version,
    get_live_auto_refresh_enabled,
    get_last_auto_backup_date, set_last_auto_backup_date,
    get_hero_aliases, add_hero_alias,
    get_license_key, set_license_key,
)
from core.ggpoker_hand_parser import GGPOKER_HERO_LABEL

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
        # (path, message) pairs already surfaced this session by the live
        # watcher/Refresh path — see _notify_ongoing_scan_errors. A file
        # that keeps failing to parse never gets its fingerprint marked
        # imported, so without this it would re-trigger the same warning
        # on every single poll/click instead of just once.
        self._warned_scan_errors: set[tuple[str, str]] = set()
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
        # bake in: hero + how many hands are loaded. The banner is made
        # tall enough to also run behind the filter bar below it (rather
        # than the filter bar sitting on its own flat strip), with the
        # controls down there floating on the felt pattern the same way
        # e.g. Linear/Notion run a toolbar over a hero band — see
        # ui/header_banner.py for the fade that keeps that legible.
        _FILTER_BAR_HEIGHT = 52
        # Tall enough for the logo to read at 65px with real padding
        # either side; the banner scales its logo and wordmark from this.
        _LOGO_ROW_HEIGHT = 76
        header = HeaderBanner(top_height=_LOGO_ROW_HEIGHT)
        self.header = header
        header.setFixedHeight(_LOGO_ROW_HEIGHT + _FILTER_BAR_HEIGHT)
        header_lay = QVBoxLayout(header)
        header_lay.setContentsMargins(0, 0, 0, 0)
        header_lay.setSpacing(0)

        top_row = QWidget()
        top_row.setStyleSheet("background: transparent;")
        top_row.setFixedHeight(_LOGO_ROW_HEIGHT)
        hl = QHBoxLayout(top_row)
        hl.setContentsMargins(24, 0, 24, 0)
        hl.addStretch()
        self.folder_warning_lbl = lbl("", size=12, color="#f85149")
        self.folder_warning_lbl.setToolTip("File > Manage Hand History Folders to fix this")
        self.folder_warning_lbl.hide()
        hl.addWidget(self.folder_warning_lbl)
        hl.addSpacing(12)
        # Placeholder — matches the toggle's default ('cash'); corrected
        # for real once _apply_filters runs below via _on_period_changed.
        self.header_hands_lbl = lbl(f"Hero: {hero}  |  {db.hand_count(session_type='cash'):,} hands loaded", size=12, color="white")
        hl.addWidget(self.header_hands_lbl)
        header_lay.addWidget(top_row)

        # Filter bar — floats transparently over the banner's bottom fade
        # instead of its own opaque strip (a plain QWidget/QFrame would
        # otherwise paint the global stylesheet's flat background and hide
        # the banner underneath, hence the explicit transparent style).
        fbar = QWidget()
        self.filter_bar = fbar
        fbar.setStyleSheet("background: transparent;")
        fbar.setFixedHeight(_FILTER_BAR_HEIGHT)
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
        fl.addSpacing(8)
        fl.addWidget(lbl("Site", dim=True))
        self.site_cb = QComboBox()
        self.site_cb.addItem("All Sites")
        self.site_cb.currentTextChanged.connect(self._on_site_changed)
        fl.addWidget(self.site_cb)
        fl.addSpacing(8)
        # Global Cash/Tournament switch — Overview/Sessions/Stats/Population
        # all show different content depending on this, not a separate
        # Tournaments tab (see ui/game_type_toggle.py for why). Labeled like
        # every other filter here so it doesn't read as a stray switch.
        fl.addWidget(lbl("Game", dim=True))
        self.game_type_toggle = GameTypeToggle()
        self.game_type_toggle.changed.connect(self._on_game_type_changed)
        fl.addWidget(self.game_type_toggle)
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
        header_lay.addWidget(fbar)
        main_lay.addWidget(header)

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
        # Shown above the tabs (not per-tab) whenever the database is
        # genuinely empty — every individual tab otherwise renders as a
        # blank chart or a table full of "—" dashes with no explanation,
        # which reads as broken rather than "nothing imported yet" to
        # someone who just installed the app.
        self.no_hands_banner = QFrame()
        self.no_hands_banner.setStyleSheet(
            f"background:{BG2};border:1px solid {BORDER};border-radius:6px;")
        nb_lay = QHBoxLayout(self.no_hands_banner)
        nb_lay.setContentsMargins(16, 10, 16, 10)
        nb_lay.addWidget(lbl(
            "No hands imported yet — new hands are picked up automatically once you "
            "play, or check where PokerForge is looking.", dim=True))
        nb_lay.addStretch()
        no_hands_manage_btn = QPushButton("Manage Folders...")
        no_hands_manage_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        no_hands_manage_btn.clicked.connect(self._on_manage_folders_clicked)
        nb_lay.addWidget(no_hands_manage_btn)
        self.no_hands_banner.hide()

        wrap = QWidget()
        wl = QVBoxLayout(wrap)
        wl.setContentsMargins(16, 12, 16, 16)
        wl.setSpacing(12)
        wl.addWidget(self.no_hands_banner)
        wl.addWidget(self.tabs)
        main_lay.addWidget(wrap)

        QShortcut(QKeySequence("Ctrl+R"), self, activated=self._on_refresh_clicked)

        self._live_watcher = LiveFolderWatcher(self)
        self._live_watcher.changed.connect(self._on_live_files_changed)
        self._apply_live_watch_setting()

        self._update_folder_warning()
        self._update_no_hands_banner()
        self._on_period_changed()
        self._maybe_refresh_license_status()

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
        new_count, errors = _import_new_hands(self, self.db, self.hero, dialog_threshold=15)
        self._apply_live_watch_setting()  # picks up any new files/subfolders that appeared
        if new_count:
            self._update_folder_warning()
            self._update_no_hands_banner()
            self._apply_filters()
        _notify_ongoing_scan_errors(errors, self._warned_scan_errors)

    def _update_folder_warning(self):
        missing = missing_configured_folders(get_hand_history_dirs())
        if missing:
            noun = "folder" if len(missing) == 1 else "folders"
            self.folder_warning_lbl.setText(f"⚠ {len(missing)} hand-history {noun} not found")
            self.folder_warning_lbl.show()
        else:
            self.folder_warning_lbl.hide()

    def _update_no_hands_banner(self):
        self.no_hands_banner.setVisible(self.db.hand_count() == 0)

    def _on_period_changed(self):
        """Period changed — the set of sites (and, once that's back, the
        set of stakes) worth offering depends on the period (no point
        listing a stake — or a site — from 2019 while viewing "This
        Month"), so rebuild both dropdowns before re-filtering the tabs.
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
            lambda: available_sites_query(self.db, self.hero, d_from, d_to),
            self._on_sites_loaded,
        )

    def _current_date_range(self):
        if self.period_cb.currentText() == CUSTOM_RANGE_LABEL and self._custom_range:
            return self._custom_range
        return date_range(self.period_cb.currentText())

    def _current_site(self):
        text = self.site_cb.currentText()
        return None if text in ("", "All Sites") else site_value(text)

    def _current_game_type(self) -> str:
        return self.game_type_toggle.value()

    def _on_game_type_changed(self, _value):
        # Stakes never apply to tournament hands (their `stakes_label` is
        # always NULL — see database/hand_stats_builder.py), so reloading
        # the Stakes dropdown for the new game type naturally comes back
        # empty in Tournament mode, no special-casing needed here.
        self._reload_stakes()

    def _on_sites_loaded(self, sources):
        prev = self.site_cb.currentText()
        self.site_cb.blockSignals(True)
        self.site_cb.clear()
        self.site_cb.addItem("All Sites")
        self.site_cb.addItems(site_label(s) for s in sources)
        idx = self.site_cb.findText(prev)
        self.site_cb.setCurrentIndex(idx if idx >= 0 else 0)
        self.site_cb.blockSignals(False)
        self._reload_stakes()

    def _on_site_changed(self, _text=None):
        self._reload_stakes()

    def _reload_stakes(self):
        """The set of stakes worth offering also depends on which site is
        selected (no point listing a GGPoker-only stake while "iPoker" is
        picked) — reloaded on both a period change and a site change,
        with _apply_filters running only once that's settled."""
        d_from, d_to = self._current_date_range()
        site = self._current_site()
        game_type = self._current_game_type()
        self.run_async(
            lambda: available_stakes_query(self.db, self.hero, d_from, d_to, site, game_type),
            self._on_stakes_loaded,
        )

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

    def _update_header_hands_label(self, game_type: str):
        # Scoped to the current $/T mode — otherwise this always shows the
        # combined cash+tournament total, which reads as wrong while
        # looking at (say) Tournament mode with only a handful of
        # tournaments logged.
        count = self.db.hand_count(session_type=game_type)
        self.header_hands_lbl.setText(f"Hero: {self.hero}  |  {count:,} hands loaded")

    def _apply_filters(self):
        d_from, d_to = self._current_date_range()
        self.info_lbl.setText(f"{d_from} → {d_to}")
        stake = self.stakes_cb.currentText()
        stake = None if stake in ("", "All Stakes") else stake
        site = self._current_site()
        game_type = self._current_game_type()
        self._update_header_hands_label(game_type)
        self.tab_overview.refresh(self.db, self.hero, d_from, d_to, self.currency, stake, site, game_type)
        self.tab_sessions.refresh(self.db, self.hero, d_from, d_to, self.currency, stake, site, game_type)
        self.tab_stats.refresh(self.db, self.hero, d_from, d_to, self.currency, stake, site, game_type)
        self.tab_population.refresh(d_from, d_to, stake, site, game_type)

    def _on_refresh_clicked(self):
        """Manual re-check of the watched folders, for new hands played
        since the app was launched — the automatic check only runs once,
        at startup, so this covers a session that's stayed open while you
        kept playing."""
        self.refresh_btn.setEnabled(False)
        self.refresh_btn.setText("Checking…")
        QApplication.processEvents()
        try:
            _, errors = _import_new_hands(self, self.db, self.hero)
        finally:
            self.refresh_btn.setEnabled(True)
            self.refresh_btn.setText("↻ Refresh")
        self._update_folder_warning()
        self._update_no_hands_banner()
        self._apply_filters()
        self._apply_live_watch_setting()
        _notify_ongoing_scan_errors(errors, self._warned_scan_errors)

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
        self._apply_filters()  # picks up a changed Rakeback % immediately, no restart needed

    def _on_enter_license_key_clicked(self):
        # LicenseDialog verifies the signature before letting Ok through,
        # so an accepted dialog means a genuine licence. activate_key is
        # checked anyway rather than assumed -- it's the function that
        # decides, and a silent no-op here would be invisible.
        dlg = LicenseDialog(current_key=get_license_key(), parent=self)
        if dlg.exec():
            if not activate_key(dlg.entered_key() or ""):
                QMessageBox.warning(self, "License", "That licence key couldn't be verified.")
                return
            # Display-time stakes gating (database/queries.py) reads
            # is_licensed()/should_gate_by_stakes() fresh on every query,
            # so a newly-entered licence takes effect immediately -- no
            # restart, no re-import. The expiry is signed into the token,
            # so this holds even with no connection.
            self._apply_filters()
            QMessageBox.information(self, "License", "License key saved — thanks for supporting PokerForge!")
            self.run_async(refresh_license_status, self._on_license_status_refreshed, key="license_status")

    def _maybe_refresh_license_status(self):
        # The one exception to this app's "no network calls unless you
        # ask" stance -- and even then, only for someone who's already
        # entered a paid key (see core/licensing.py's module docstring).
        # A free-tier user who never enters a key causes zero network
        # calls, exactly as before. refresh_license_status() itself is
        # additionally a no-op unless LICENSE_ENFORCED and a server URL
        # are actually configured, so this is silent today either way.
        if get_license_key():
            self.run_async(refresh_license_status, self._on_license_status_refreshed, key="license_status")

    def _on_license_status_refreshed(self, reached_server: bool):
        if reached_server:
            # A lapsed subscription (or a freshly renewed one) takes
            # effect immediately -- same reasoning as entering a key.
            self._apply_filters()

    def _on_getting_started_clicked(self):
        GettingStartedDialog(parent=self).exec()

    def _on_take_tour_clicked(self):
        # Kept alive on self — a local variable would be garbage collected
        # (and its Qt widgets destroyed under it) the moment this method
        # returns, well before the tour itself finishes.
        self._tour = TourOverlay(self)
        self._tour.start()

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

        n = self.db.rebuild_hand_player_stats(ev_iterations=500, on_progress=on_progress, hero=self.hero)
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
            "position_table_stat_ids": None, "overall_stat_ids": None, "trend_stat_ids": None,
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
        _open_bug_report_email()

    def _build_menu_bar(self):
        file_menu = self.menuBar().addMenu("&File")
        file_menu.addAction("Manage Hand History Folders...", self._on_manage_folders_clicked)
        file_menu.addAction("Switch Profile...", self._on_switch_profile_clicked)
        file_menu.addAction("Settings...", self._on_settings_clicked)
        file_menu.addAction("Enter License Key...", self._on_enter_license_key_clicked)
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
        help_menu.addAction("Take the Tour...", self._on_take_tour_clicked)
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


# Tracks candidate names already prompted-for (accepted OR declined) —
# not just a single "shown once" flag, since one batch can legitimately
# surface more than one new identity at once (see docstring below), and
# each distinct candidate deserves its own one-time answer rather than
# the first one seen suppressing every other one for the rest of the
# session.
_prompted_identity_candidates: set[str] = set()
# Matches this project's existing "don't read anything into a tiny
# sample" convention (see e.g. ui/tilt_report_dialog.py's MIN_SAMPLE,
# ui/player_classify.py's MIN_LEAK_SAMPLE).
_NEW_IDENTITY_MIN_SAMPLE = 20
# A real account owner's own hand-history export has them seated in
# essentially every hand (confirmed empirically well above this in real
# exports across every supported site); a villain who happens to recur
# a lot in a small batch falls well short of it.
_NEW_IDENTITY_MIN_SHARE = 0.8
# Sources whose own export protocol always labels the exporting account's
# seat literally "Hero" (see core.ggpoker_hand_parser.GGPOKER_HERO_LABEL /
# core.winning_network_hand_parser.WINNING_NETWORK_HERO_LABEL) rather than
# the player's real username on that site.
ANONYMIZING_HERO_SOURCES = {'ggpoker', 'winning_network'}


def _maybe_prompt_new_identity_alias(hands, hero: str, parent=None) -> None:
    """Catches BOTH directions of a real incident this project hit:
    GGPoker always labels the account owner's own seat literally "Hero"
    (core.ggpoker_hand_parser.GGPOKER_HERO_LABEL), never the player's
    real GGPoker username -- so importing GGPoker hands into a profile
    whose tracked hero is already a different site's username left
    222,843 real hands silently excluded from Hero's own stats until
    this existed. But the reverse order breaks exactly the same way: if
    GGPoker hands are imported FIRST (establishing "Hero" as the tracked
    identity, correctly, since it's genuinely the only name in that
    data), a real-username site imported afterward is the one that ends
    up unmerged instead.

    Checked PER SOURCE, not over the whole batch as one pool — a
    first-time setup that points at two sites' folders at once produces
    ONE combined first-run batch, and neither site's own ~100%-of-its-
    own-hands hero label would individually cross a share threshold
    measured against the OTHER site's hands mixed in (e.g. 222,843 GG
    hands is only ~44% of a batch that also has 286,554 PokerStars
    hands, even though "Hero" is in 100% of the GG portion) — grouping
    by source first restores that ~100% signal within each site's own
    hands regardless of how the sites' volumes compare to each other.

    Neither direction, nor the multi-source-at-once case, is GGPoker-
    specific in principle — any two sites where the same person uses
    different usernames would hit this — so the detection itself is
    generic: whoever appears in nearly every hand of one source's
    portion of a newly-arriving batch, if that's not already the tracked
    hero or a known alias, is almost certainly the same person under a
    different name. Catching this at the moment the new hands are about
    to be written for the first time means no one ever needs the kind of
    one-off database correction that incident required: if the player
    says yes here, normalize_hero_aliases (called right after) picks up
    the freshly-saved alias in this exact same pass, before a single row
    is written under the wrong identity."""
    known = {hero} | set(get_hero_aliases())
    by_source: dict = {}
    for h in hands:
        by_source.setdefault(h.source, []).append(h)

    for source, source_hands in by_source.items():
        if len(source_hands) < _NEW_IDENTITY_MIN_SAMPLE:
            continue
        candidate = detect_hero(source_hands)
        if candidate in known or candidate in _prompted_identity_candidates:
            continue
        if hero_hand_share(source_hands, candidate) < _NEW_IDENTITY_MIN_SHARE:
            continue
        _prompted_identity_candidates.add(candidate)

        # GGPoker and Winning Network both always label the exporting
        # account's own seat literally "Hero", never the real username —
        # same underlying cause, so the same explanation applies to
        # either, just naming whichever site this batch is actually from.
        if candidate == GGPOKER_HERO_LABEL and source in ANONYMIZING_HERO_SOURCES:
            explanation = (
                f"{site_label(source)} hand histories always label your own seat as \"Hero\" "
                f"rather than your real {site_label(source)} username, so PokerForge can't "
                f"tell on its own that these hands are yours ({hero}'s) unless it's told.")
        else:
            explanation = (
                f"These hands are mostly played by \"{candidate}\" — if that's you under a "
                f"different username on another site, PokerForge can't tell on its own that "
                f"it's the same person as {hero} unless it's told.")

        msg = QMessageBox(
            QMessageBox.Icon.Information, "New player identity detected",
            f"{explanation}\n\n"
            f"Add \"{candidate}\" as an alias for {hero} now, so these hands are counted "
            f"correctly from the start?",
            parent=parent if isinstance(parent, QWidget) else None)
        yes_btn = msg.addButton("Yes, add it", QMessageBox.ButtonRole.YesRole)
        msg.addButton("Not now", QMessageBox.ButtonRole.NoRole)
        msg.exec()
        if msg.clickedButton() is yes_btn:
            add_hero_alias(candidate)
            known.add(candidate)


def _import_new_hands(app_or_window, db, hero, dialog_threshold: int = 1) -> tuple[int, list[tuple[str, str]]]:
    """Checks the watched folders for new/changed files and imports
    whatever new hands they contain — shared by the startup check (main()),
    the Refresh button (AppWindow._on_refresh_clicked()), and the live
    folder watcher (AppWindow._on_live_files_changed()), so all three stay
    in sync rather than drifting into slightly different pipelines.

    Returns (new_hand_count, errors) — unlike the first-run scan, callers
    here don't show `errors` directly; see _notify_ongoing_scan_errors for
    why (a persistently-broken file never gets marked imported, so it
    would otherwise re-report on every single poll/click).

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
        return 0, errors

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

    _maybe_prompt_new_identity_alias(hands, hero, parent=app_or_window)
    normalize_hero_aliases(hands, hero)
    convert_hands_to_usd(hands)

    t0 = time.time()
    if len(hands) < dialog_threshold:
        db.import_hands(hands, ev_iterations=500, hero=hero)
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

        db.import_hands(hands, ev_iterations=500, on_progress=on_progress, hero=hero)
        progress.setValue(len(hands))
    db.mark_files_imported(fingerprints)
    logger.info("Imported %d new hand(s) in %.1fs", len(hands), time.time() - t0)
    return len(hands), errors


def _open_bug_report_email(extra_body: str = ""):
    import urllib.parse
    subject = urllib.parse.quote("PokerForge Bug Report")
    body = urllib.parse.quote(
        "Describe the issue:\n\n\n"
        "---\n"
        f"App version: {APP_VERSION}\n"
        f"Log file: {LOG_PATH}\n"
        "(Please attach the log file above if possible.)"
        + (f"\n\n{extra_body}" if extra_body else "")
    )
    to = SUPPORT_EMAIL or ""
    QDesktopServices.openUrl(QUrl(f"mailto:{to}?subject={subject}&body={body}"))


def _is_known_limitation(message: str) -> bool:
    """True for a hand a parser deliberately refuses to import because of
    a documented, by-design gap (currently: tournament hands — see
    core/pokerstars_hand_parser.py and core/ggpoker_hand_parser.py) rather
    than an actual bug. These should never prompt someone to file a bug
    report for entirely expected behavior."""
    return "not supported yet" in message


def _notify_ongoing_scan_errors(errors: list[tuple[str, str]], warned: set[tuple[str, str]]) -> None:
    """The Refresh button and live folder watcher's counterpart to
    _prompt_first_run_scan_issues — same underlying problem (a file that
    fails to parse never gets its fingerprint marked imported, so it's
    re-parsed, and re-fails, on every future scan) but a much quieter
    response, for two reasons this function exists separately rather than
    just calling that one:

    - `warned` (AppWindow._warned_scan_errors) is mutated to remember
      every (path, message) already surfaced this session, so a broken
      file the live watcher polls every few seconds doesn't pop the same
      dialog over and over — only genuinely NEW failures (a different
      file, or the same file failing with a different message after being
      re-saved) get shown.
    - Known-limitation errors (tournament hands — see
      _is_known_limitation) are silently absorbed here, not shown at all:
      first-run already explained that gap once, and repeating it
      indefinitely every time a tournament file happens to still be
      sitting in a watched folder would just be nagging."""
    new_errors = [(p, m) for p, m in errors if (p, m) not in warned]
    if not new_errors:
        return
    warned.update(new_errors)

    real_errors = [(p, m) for p, m in new_errors if not _is_known_limitation(m)]
    if not real_errors:
        return  # only known-limitation skips — already explained at first run, stay quiet

    first_path, first_message = real_errors[0]
    msg = QMessageBox(
        QMessageBox.Icon.Warning, "Couldn't read a hand-history file",
        f"PokerForge found {len(real_errors)} file(s) it couldn't read while checking for "
        f"new hands — this usually means the file format isn't fully supported yet.\n\n"
        f"First error:\n{first_path}\n{first_message}\n\n"
        "Reporting this would help get it fixed. This won't be shown again for the same "
        "file unless it changes.")
    report_btn = msg.addButton("Report a Bug...", QMessageBox.ButtonRole.ActionRole)
    msg.addButton("OK", QMessageBox.ButtonRole.AcceptRole)
    msg.exec()
    if msg.clickedButton() is report_btn:
        error_list = "\n".join(f"{p}: {m}" for p, m in real_errors[:10])
        _open_bug_report_email(f"Files that failed to parse ({len(real_errors)} total):\n{error_list}")


def _prompt_first_run_scan_issues(dirs, hands, errors):
    """Called once, right after the first-run scan, before hero
    detection — covers every outcome of that scan:

    - Real parse errors get a Warning-level message with a "Report a
      Bug..." button, REGARDLESS of whether other files parsed fine — a
      partial failure is just as real a bug as a total one, and silently
      importing what did work while saying nothing about what didn't
      would hide it just as effectively as the old "zero hands = nothing
      to worry about" message this replaces.
    - Known-limitation skips (see _is_known_limitation) get a calm,
      Information-level message instead, with no bug-report button —
      these are expected, documented gaps (tournament hands, for now),
      not something broken.
    - No errors and no hands found gets the reassuring "haven't played
      yet" message, with a "Manage Folders..." button to fix the
      selection immediately (saved for next launch, not re-scanned
      inline here, to avoid duplicating the scan/import/progress-dialog
      machinery a second time in the same run).
    - Hands found and no errors — the normal case — shows nothing."""
    real_errors = [(p, m) for p, m in errors if not _is_known_limitation(m)]
    limitation_errors = [(p, m) for p, m in errors if _is_known_limitation(m)]

    if real_errors:
        first_path, first_message = real_errors[0]
        success_note = (f" It did successfully import {len(hands):,} hand(s) from your "
                         "other files." if hands else "")
        skipped_note = (f" (Separately, {len(limitation_errors)} hand(s) were skipped as a "
                         "known, not-yet-supported format — not a bug, see below.)"
                         if limitation_errors else "")
        msg = QMessageBox(
            QMessageBox.Icon.Warning, "Couldn't read some hand-history files",
            f"PokerForge found {len(real_errors)} file(s) in your folder(s) but couldn't "
            f"read {'it' if len(real_errors) == 1 else 'any of them'} — this usually means "
            f"the file format isn't fully supported yet.{success_note}{skipped_note}\n\n"
            f"First error:\n{first_path}\n{first_message}\n\n"
            "Reporting this would help get it fixed.")
        report_btn = msg.addButton("Report a Bug...", QMessageBox.ButtonRole.ActionRole)
        msg.addButton("OK", QMessageBox.ButtonRole.AcceptRole)
        msg.exec()
        if msg.clickedButton() is report_btn:
            error_list = "\n".join(f"{p}: {m}" for p, m in real_errors[:10])
            _open_bug_report_email(f"Files that failed to parse ({len(real_errors)} total):\n{error_list}")
        return

    if limitation_errors:
        _, first_message = limitation_errors[0]
        success_note = (f" Everything else — {len(hands):,} hand(s) — imported normally."
                         if hands else "")
        QMessageBox.information(
            None, "Some hands were skipped",
            f"PokerForge found {len(limitation_errors)} hand(s) that aren't supported "
            f"yet ({first_message}).{success_note}\n\n"
            "This isn't a bug — see the Roadmap for what's planned.")
        return

    if hands:
        return

    msg = QMessageBox(
        QMessageBox.Icon.Information, "No hands found yet",
        "PokerForge scanned the folder(s) you chose but didn't find any "
        "hand-history files yet.\n\nIf you haven't played a hand yet, "
        "there's nothing to do — new hands are picked up automatically "
        "once you play. If this looks wrong, you can check which "
        "folder(s) PokerForge is watching.")
    manage_btn = msg.addButton("Manage Folders...", QMessageBox.ButtonRole.ActionRole)
    msg.addButton("OK", QMessageBox.ButtonRole.AcceptRole)
    msg.exec()
    if msg.clickedButton() is manage_btn:
        folders_dlg = HandHistoryDirsDialog(dirs, first_run=False)
        if folders_dlg.exec():
            set_hand_history_dirs(folders_dlg.selected_dirs())
            QMessageBox.information(
                None, "PokerForge",
                "Saved. PokerForge will scan these folders the next time it starts.")


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
        _prompt_first_run_scan_issues(dirs, hands, errors)
        # Hero identity is a global property of the whole history (whoever
        # appears in the most hands) — only trustworthy to detect when
        # this batch actually IS the whole history, i.e. a fresh database
        # where nothing has been imported yet, so `hands` is everything.
        detected_hero = detect_hero(hands)
        detected_currency = dominant_currency(hands, detected_hero) if hands else "$"
        if hands:
            # Let the player correct a wrong guess before it's locked in —
            # nothing else here can undo a bad auto-detection later.
            share = hero_hand_share(hands, detected_hero)
            confirm = HeroSetupDialog(detected_hero, detected_currency, hero_share=share)
            confirm.exec()
            hero = confirm.selected_hero() or detected_hero
            currency = confirm.selected_currency() or detected_currency
        else:
            # Nothing to detect from yet — a meaningless "Hero" placeholder,
            # already explained (or not, if genuinely nothing was wrong) by
            # _prompt_first_run_scan_issues above.
            hero, currency = detected_hero, detected_currency
        set_hero_name(hero)
        set_currency_symbol(currency)
        logger.info("Detected hero: %s, currency: %s", hero, currency)

    if hands:
        _maybe_prompt_new_identity_alias(hands, hero)
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
        db.import_hands(hands, ev_iterations=500, on_progress=on_progress, hero=hero)
        db.mark_files_imported(fingerprints)
        logger.info("Database ready in %.1fs", time.time() - t0)
        progress.setValue(len(hands))

    win = AppWindow(hero, db, currency)
    if icon_path.exists():
        win.setWindowIcon(QIcon(str(icon_path)))
    win.show()

    if first_run:
        # Both need a real, shown AppWindow to attach to/spotlight widgets
        # on — GettingStartedDialog first (a static glossary reference,
        # closed when read), then the interactive tour walks the actual UI.
        GettingStartedDialog(parent=win).exec()
        win._tour = TourOverlay(win)
        win._tour.start()

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
