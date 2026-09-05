"""Small persisted settings store — user-editable config that shouldn't be
hardcoded in source (this app is meant to be used by more than one person,
each with their own hero identity/aliases and display preferences)."""
import json

from config.paths import profile_data_dir

SETTINGS_PATH = profile_data_dir() / "settings.json"

_DEFAULTS = {
    "hero_aliases": [],
    "hero_name": None,
    "currency_symbol": None,
    "position_table_stat_ids": None,
    "trend_stat_ids": None,
    "trend_interval_days": 14,
    "hand_history_dirs": [],
    "last_seen_version": None,
    "license_key": None,
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
    SETTINGS_PATH.write_text(json.dumps(settings, indent=2), encoding="utf-8")


def get_hero_aliases() -> list[str]:
    return load_settings().get("hero_aliases", [])


def add_hero_alias(name: str):
    settings = load_settings()
    aliases = set(settings.get("hero_aliases", []))
    aliases.add(name)
    settings["hero_aliases"] = sorted(aliases)
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
