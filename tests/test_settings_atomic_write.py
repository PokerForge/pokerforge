"""config/settings.py's save_settings — must write atomically (temp file
+ os.replace) so a crash mid-write can never leave settings.json
truncated or half-written, and load_settings must tolerate a genuinely
corrupt file gracefully (falls back to defaults) rather than crashing
the whole app on startup."""
import json

import pytest

import config.settings as settings_mod


@pytest.fixture(autouse=True)
def _isolated_settings(tmp_path, monkeypatch):
    monkeypatch.setattr(settings_mod, "SETTINGS_PATH", tmp_path / "settings.json")


def test_save_settings_does_not_leave_a_temp_file_behind():
    settings_mod.save_settings({"hero_name": "Test"})
    tmp_path = settings_mod.SETTINGS_PATH.with_suffix(".json.tmp")
    assert not tmp_path.exists()
    assert settings_mod.SETTINGS_PATH.exists()


def test_a_write_that_fails_partway_through_never_truncates_the_real_file(monkeypatch, tmp_path):
    """Simulates a crash between writing the temp file and the atomic
    rename — os.replace() itself must be the only thing that can make the
    new content visible, so failing before that point must leave the
    previous, still-valid settings.json completely untouched."""
    settings_mod.save_settings({"hero_name": "OriginalGoodData"})
    original_bytes = settings_mod.SETTINGS_PATH.read_bytes()

    def _boom(*a, **k):
        raise OSError("simulated crash during os.replace")

    monkeypatch.setattr(settings_mod.os, "replace", _boom)
    with pytest.raises(OSError):
        settings_mod.save_settings({"hero_name": "NewDataThatNeverLands"})

    # The real file must be exactly what it was before the failed save —
    # not truncated, not partially overwritten.
    assert settings_mod.SETTINGS_PATH.read_bytes() == original_bytes
    assert settings_mod.load_settings()["hero_name"] == "OriginalGoodData"


def test_load_settings_tolerates_a_corrupt_file():
    settings_mod.SETTINGS_PATH.write_text("{not valid json", encoding="utf-8")
    result = settings_mod.load_settings()
    assert result["hero_name"] is None  # falls back to defaults, doesn't raise


def test_save_then_load_roundtrips_correctly():
    settings_mod.save_settings({**settings_mod._DEFAULTS, "hero_name": "RoundTrip"})
    assert settings_mod.load_settings()["hero_name"] == "RoundTrip"
