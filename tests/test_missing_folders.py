"""core/importer.py's missing_configured_folders() — the check behind the
in-app "a hand-history folder wasn't found" warning."""
from core.importer import missing_configured_folders


def test_no_missing_folders_when_all_exist(tmp_path):
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    assert missing_configured_folders([str(a), str(b)]) == []


def test_reports_a_folder_that_does_not_exist(tmp_path):
    exists = tmp_path / "exists"
    exists.mkdir()
    missing = tmp_path / "gone"
    assert missing_configured_folders([str(exists), str(missing)]) == [str(missing)]


def test_empty_list_reports_nothing():
    assert missing_configured_folders([]) == []


def test_a_file_instead_of_a_directory_counts_as_missing(tmp_path):
    a_file = tmp_path / "not_a_folder.txt"
    a_file.write_text("hi")
    assert missing_configured_folders([str(a_file)]) == [str(a_file)]
