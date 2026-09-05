"""Multi-profile registry — lets more than one hero identity share one
install (a shared family PC, or someone tracking two genuinely separate
poker accounts) without mixing their hands, settings, or stats together.

Switching profiles takes effect on the next launch, not live in place —
the database connection, hero name, and currency are all wired into
long-lived objects created once at startup (see ui/app_window.py's
main()), so restarting the process (which the Switch Profile dialog
offers to do for you) is far simpler and safer than hot-swapping all of
that mid-session.

The default profile's data deliberately stays exactly where every
existing install already has it — see config.paths.profile_data_dir()
— so installs from before multi-profile support existed keep working
with zero migration."""
import json
import re

from config.paths import app_data_dir

REGISTRY_PATH = app_data_dir() / "profiles.json"
DEFAULT_PROFILE_ID = "default"
DEFAULT_DISPLAY_NAME = "Default"


def _load_registry() -> dict:
    if REGISTRY_PATH.exists():
        try:
            data = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
            if DEFAULT_PROFILE_ID in data.get("profiles", {}):
                return data
        except (json.JSONDecodeError, OSError):
            pass
    return {
        "active": DEFAULT_PROFILE_ID,
        "profiles": {DEFAULT_PROFILE_ID: {"display_name": DEFAULT_DISPLAY_NAME}},
    }


def _save_registry(reg: dict):
    REGISTRY_PATH.write_text(json.dumps(reg, indent=2), encoding="utf-8")


def list_profiles() -> list[tuple[str, str]]:
    """Returns [(profile_id, display_name), ...], default profile first."""
    reg = _load_registry()
    ids = [DEFAULT_PROFILE_ID] + sorted(p for p in reg["profiles"] if p != DEFAULT_PROFILE_ID)
    return [(pid, reg["profiles"][pid].get("display_name", pid)) for pid in ids]


def get_active_profile_id() -> str:
    return _load_registry().get("active", DEFAULT_PROFILE_ID)


def get_active_display_name() -> str:
    reg = _load_registry()
    active = reg.get("active", DEFAULT_PROFILE_ID)
    return reg["profiles"].get(active, {}).get("display_name", active)


def set_active_profile(profile_id: str):
    reg = _load_registry()
    if profile_id not in reg["profiles"]:
        raise ValueError(f"Unknown profile: {profile_id}")
    reg["active"] = profile_id
    _save_registry(reg)


def _slugify(display_name: str, existing: set[str]) -> str:
    base = re.sub(r"[^a-z0-9]+", "_", display_name.strip().lower()).strip("_") or "profile"
    slug = base
    n = 2
    while slug in existing:
        slug = f"{base}_{n}"
        n += 1
    return slug


def create_profile(display_name: str) -> str:
    """Creates a new, empty profile and returns its id. Does not switch to
    it — call set_active_profile() separately if that's wanted."""
    display_name = display_name.strip()
    if not display_name:
        raise ValueError("Profile name can't be empty.")
    reg = _load_registry()
    profile_id = _slugify(display_name, existing=set(reg["profiles"]))
    reg["profiles"][profile_id] = {"display_name": display_name}
    _save_registry(reg)
    return profile_id


def delete_profile(profile_id: str):
    """Removes a profile from the registry only — never deletes its data
    folder, so nothing is destroyed by a misclick; the folder (see
    config.paths.profile_data_dir) can be removed manually if truly
    wanted."""
    if profile_id == DEFAULT_PROFILE_ID:
        raise ValueError("Can't delete the default profile.")
    reg = _load_registry()
    reg["profiles"].pop(profile_id, None)
    if reg.get("active") == profile_id:
        reg["active"] = DEFAULT_PROFILE_ID
    _save_registry(reg)
