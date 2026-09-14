"""Small persisted settings store — user-editable config that shouldn't be
hardcoded in source (this app is meant to be used by more than one person,
each with their own hero identity/aliases and display preferences)."""
import json
import os

from config.paths import profile_data_dir

SETTINGS_PATH = profile_data_dir() / "settings.json"

_DEFAULTS = {
    "hero_aliases": [],
    "hero_name": None,
    "currency_symbol": None,
    "position_table_stat_ids": None,
    "overall_stat_ids": None,
    "rakeback_pct": None,
    "trend_stat_ids": None,
    "trend_interval_days": 14,
    "hand_history_dirs": [],
    "last_seen_version": None,
    "license_key": None,
    "license_expires_at": None,
    "license_last_checked_at": None,
    "live_auto_refresh_enabled": True,
    "last_auto_backup_date": None,
}


def load_settings() -> dict:
    if SETTINGS_PATH.exists():
        try:
            data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            data = {}
    else:
        data = {}
    return {**_DEFAULTS, **data}


def save_settings(settings: dict):
    """Writes via a temp file + os.replace() rather than a direct
    write_text() — the direct version truncates the file to zero bytes
    before writing the new content, so a crash, power loss, or forced
    quit at exactly the wrong moment (settings are saved surprisingly
    often: every hero-alias addition, every filter tweak in some dialogs)
    would leave a corrupt/empty settings.json behind. os.replace() is
    atomic on both Windows and POSIX — the old file stays intact and
    fully readable right up until the new one is completely written."""
    tmp_path = SETTINGS_PATH.with_suffix(SETTINGS_PATH.suffix + ".tmp")
    tmp_path.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    os.replace(tmp_path, SETTINGS_PATH)


def get_hero_aliases() -> list[str]:
    return load_settings().get("hero_aliases", [])


def add_hero_alias(name: str):
    settings = load_settings()
    aliases = set(settings.get("hero_aliases", []))
    aliases.add(name)
    settings["hero_aliases"] = sorted(aliases)
    save_settings(settings)


def set_hero_aliases(names: list[str]):
    """Bulk replace, for SettingsDialog's alias editor — saves the whole
    list once on Save rather than one call per add/remove edit made
    while the dialog was open."""
    settings = load_settings()
    settings["hero_aliases"] = sorted(set(names))
    save_settings(settings)


def get_hero_name() -> str | None:
    """The hero identity, detected once (whichever name appears in the
    most hands) and persisted here — incremental startup only parses new
    hand-history files, so there usually isn't a full dataset in memory
    to re-detect this from on every launch."""
    return load_settings().get("hero_name")


def set_hero_name(name: str):
    settings = load_settings()
    settings["hero_name"] = name
    save_settings(settings)


def get_currency_symbol() -> str | None:
    """The reporting currency symbol, detected once (hero's dominant
    native currency) and persisted for the same reason as hero_name."""
    return load_settings().get("currency_symbol")


def set_currency_symbol(symbol: str):
    settings = load_settings()
    settings["currency_symbol"] = symbol
    save_settings(settings)


def get_position_table_stat_ids() -> list[str] | None:
    """Which STAT_REGISTRY stat ids to show as columns in the Stats tab's
    By Position table — None means "use the built-in default set" (see
    ui/stats_tab.py's POSITION_DEFAULT_STAT_IDS), only set once the user
    customizes it via the Customise button."""
    return load_settings().get("position_table_stat_ids")


def set_position_table_stat_ids(stat_ids: list[str]):
    settings = load_settings()
    settings["position_table_stat_ids"] = stat_ids
    save_settings(settings)


def get_overall_stat_ids() -> list[str] | None:
    """Which STAT_REGISTRY stat ids to show as cards on the Stats tab's
    Overall tab (across its Overall/Preflop/Flop/Turn/River categories) —
    None means "show all of them" (the built-in default, matching this
    tab's behavior before it was made customizable), only set once the
    user customizes it via the Customise button."""
    return load_settings().get("overall_stat_ids")


def set_overall_stat_ids(stat_ids: list[str]):
    settings = load_settings()
    settings["overall_stat_ids"] = stat_ids
    save_settings(settings)


def get_rakeback_pct() -> float | None:
    """The user's own rakeback deal, as a percentage (e.g. 30 for 30%) —
    None means not configured, in which case the Overview tab's Rakeback
    stat card shows "—" rather than a misleading $0.00."""
    return load_settings().get("rakeback_pct")


def set_rakeback_pct(pct: float | None):
    settings = load_settings()
    settings["rakeback_pct"] = pct
    save_settings(settings)


def get_trend_stat_ids() -> list[str] | None:
    """Which STAT_REGISTRY stat ids the Trend tab plots — None means "use
    the built-in default" (see ui/stats_tab.py's TREND_DEFAULT_STAT_IDS)."""
    return load_settings().get("trend_stat_ids")


def set_trend_stat_ids(stat_ids: list[str]):
    settings = load_settings()
    settings["trend_stat_ids"] = stat_ids
    save_settings(settings)


def get_hand_history_dirs() -> list[str]:
    """Folders watched for hand-history files (parsed at startup and on
    Refresh) — set via the Manage Folders dialog rather than hardcoded, so
    each install points at its own player's poker client/export folders."""
    return load_settings().get("hand_history_dirs", [])


def set_hand_history_dirs(dirs: list[str]):
    settings = load_settings()
    settings["hand_history_dirs"] = dirs
    save_settings(settings)


def get_trend_interval_days() -> int:
    """The check-in interval (in days) the Trend tab buckets by — e.g. 7
    for weekly, 14 for every-two-weeks, 30 for monthly."""
    return load_settings().get("trend_interval_days", 14)


def set_trend_interval_days(days: int):
    settings = load_settings()
    settings["trend_interval_days"] = days
    save_settings(settings)


def get_last_seen_version() -> str | None:
    """The APP_VERSION this profile last launched with — None for a
    profile that predates this setting, or a genuinely first-ever launch.
    Drives the "What's new" popup: it's shown only when this doesn't match
    the running version (see ui/app_window.py's main())."""
    return load_settings().get("last_seen_version")


def set_last_seen_version(version: str):
    settings = load_settings()
    settings["last_seen_version"] = version
    save_settings(settings)


def get_license_key() -> str | None:
    """See core/licensing.py — unused while LICENSE_ENFORCED is False."""
    return load_settings().get("license_key")


def set_license_key(key: str | None):
    settings = load_settings()
    settings["license_key"] = key
    save_settings(settings)


def get_license_expires_at() -> str | None:
    """See core/licensing.py::refresh_license_status — the subscription's
    paid-through date (ISO, YYYY-MM-DD) as of the last successful check
    against the license server, or a provisional value set the moment a
    key is first entered (core/licensing.py::activate_key). None means
    never checked and no key entered yet."""
    return load_settings().get("license_expires_at")


def set_license_expires_at(expires_at: str | None):
    settings = load_settings()
    settings["license_expires_at"] = expires_at
    save_settings(settings)


def get_license_last_checked_at() -> str | None:
    """ISO date this profile last successfully reached the license server
    — informational only (not itself part of the licensing decision, see
    core/licensing.py::is_licensed)."""
    return load_settings().get("license_last_checked_at")


def set_license_last_checked_at(checked_at: str | None):
    settings = load_settings()
    settings["license_last_checked_at"] = checked_at
    save_settings(settings)


def get_live_auto_refresh_enabled() -> bool:
    """Whether AppWindow's LiveFolderWatcher (ui/live_watcher.py) should
    watch the configured hand-history folders and import new hands
    automatically while the app stays open — on by default, with an
    off switch in Settings in case it's ever disruptive for someone's
    setup (e.g. a network drive that fires spurious change events)."""
    return load_settings().get("live_auto_refresh_enabled", True)


def set_live_auto_refresh_enabled(enabled: bool):
    settings = load_settings()
    settings["live_auto_refresh_enabled"] = enabled
    save_settings(settings)


def get_last_auto_backup_date() -> str | None:
    """See core/backup.py's create_auto_backup_if_due — the date (ISO
    string) an automatic safety-net snapshot was last taken, so it only
    happens once per calendar day."""
    return load_settings().get("last_auto_backup_date")


def set_last_auto_backup_date(date_str: str):
    settings = load_settings()
    settings["last_auto_backup_date"] = date_str
    save_settings(settings)
