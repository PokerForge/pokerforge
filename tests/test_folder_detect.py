"""core/folder_detect.py — must find real per-player Grosvenor folders
without needing to know the username in advance, and must never raise
just because the folder doesn't exist (the overwhelmingly common case
for anyone not using Grosvenor at all)."""
from core.folder_detect import detect_grosvenor_folders, detect_known_folders


def test_no_grosvenor_install_returns_empty_list(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert detect_grosvenor_folders() == []


def test_finds_a_single_player_folder(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    tables = tmp_path / "Grosvenor Poker" / "data" / "SomePlayer" / "History" / "Data" / "Tables"
    tables.mkdir(parents=True)

    found = detect_grosvenor_folders()
    assert found == [str(tables)]


def test_finds_multiple_player_folders_sorted(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    for name in ("Zed", "Alice"):
        (tmp_path / "Grosvenor Poker" / "data" / name / "History" / "Data" / "Tables").mkdir(parents=True)

    found = detect_grosvenor_folders()
    assert len(found) == 2
    assert found[0].endswith("Alice\\History\\Data\\Tables") or found[0].endswith("Alice/History/Data/Tables")


def test_ignores_player_folders_missing_the_tables_subpath(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    # A player folder exists, but never actually played (no History dir yet).
    (tmp_path / "Grosvenor Poker" / "data" / "NewPlayer").mkdir(parents=True)

    assert detect_grosvenor_folders() == []


def test_missing_localappdata_env_var_does_not_raise(monkeypatch):
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    assert detect_grosvenor_folders() == []


def test_detect_known_folders_currently_only_covers_grosvenor(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    tables = tmp_path / "Grosvenor Poker" / "data" / "Player" / "History" / "Data" / "Tables"
    tables.mkdir(parents=True)
    assert detect_known_folders() == [str(tables)]
