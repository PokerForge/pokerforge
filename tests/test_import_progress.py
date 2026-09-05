"""core/importer.py's parse_directory_incremental on_progress callback —
must report every file it walks past (skipped or freshly parsed), end at
(total, total), and cost nothing extra when no callback is given at all
(the common case: every call except the one showing a startup progress
dialog for a large first-time folder)."""
from database.repository import PokerDatabase
from core.importer import parse_directory_incremental

_GAME_XML = """<session>
<general><tablename>T1</tablename><tablesize>6</tablesize>
<smallblind>0.05</smallblind><bigblind>0.10</bigblind><gametype>Holdem NL</gametype></general>
<game gamecode="{gamecode}">
  <general>
    <startdate>2026-01-01T00:00:00</startdate>
    <players>
      <player name="Hero" seat="1" chips="10.00" bet="0.05" win="0.15" />
      <player name="Villain" seat="2" chips="9.90" bet="0.10" />
    </players>
  </general>
  <round no="0">
    <action no="1" type="1" player="Hero" sum="0.05" />
    <action no="2" type="0" player="Villain" sum="0.00" />
  </round>
</game>
</session>"""


def _db(tmp_path):
    return PokerDatabase(tmp_path / "test.db")


def test_on_progress_reports_every_file_and_ends_at_total(tmp_path):
    db = _db(tmp_path)
    for i in range(5):
        (tmp_path / f"session{i}.xml").write_text(_GAME_XML.format(gamecode=i), encoding="utf-8")

    calls = []
    parse_directory_incremental(tmp_path, db, on_progress=lambda done, total: calls.append((done, total)))
    db.close()

    assert calls[0] == (0, 5)
    assert calls[-1] == (5, 5)
    assert [c[0] for c in calls] == sorted(c[0] for c in calls)  # strictly non-decreasing


def test_on_progress_counts_already_imported_files_too(tmp_path):
    """A skipped (already-imported) file must still advance the counter —
    otherwise a mostly-unchanged folder would look stuck near 0% even
    though it's actually walking through hundreds of already-known files
    quickly."""
    db = _db(tmp_path)
    path = tmp_path / "session0.xml"
    path.write_text(_GAME_XML.format(gamecode=0), encoding="utf-8")

    # First pass imports it and marks it as known.
    hands, _, _, _, fingerprints = parse_directory_incremental(tmp_path, db)
    db.mark_files_imported(fingerprints)
    assert len(hands) == 1

    # Second pass: same file, now skipped — on_progress must still see it.
    calls = []
    parse_directory_incremental(tmp_path, db, on_progress=lambda done, total: calls.append((done, total)))
    db.close()

    assert calls[-1] == (1, 1)


def test_on_progress_with_no_files_reports_zero_of_zero(tmp_path):
    db = _db(tmp_path)
    calls = []
    parse_directory_incremental(tmp_path, db, on_progress=lambda done, total: calls.append((done, total)))
    db.close()
    assert calls == [(0, 0)]


def test_no_callback_given_behaves_exactly_as_before(tmp_path):
    db = _db(tmp_path)
    (tmp_path / "session0.xml").write_text(_GAME_XML.format(gamecode=0), encoding="utf-8")
    hands, errors, files_parsed, files_skipped, fingerprints = parse_directory_incremental(tmp_path, db)
    db.close()
    assert len(hands) == 1
    assert files_parsed == 1
    assert files_skipped == 0
