"""core/importer.py's parse_directory_incremental — a truncated/malformed
file (the exact shape a hand-history file being actively written to by a
live poker client can be caught in) must not lose data from OTHER files
in the same batch, and critically must NOT be marked as imported, so the
next scan retries it and picks up the hands once the write completes.
This retry-on-failure behavior is what makes it safe to later add a live
file-watcher that re-scans on every filesystem change without needing any
extra "was this actually a torn write" detection of its own."""
from database.repository import PokerDatabase
from core.importer import parse_directory_incremental

_GOOD_XML = """<session>
<general><tablename>T1</tablename><tablesize>6</tablesize>
<smallblind>0.05</smallblind><bigblind>0.10</bigblind><gametype>Holdem NL</gametype></general>
<game gamecode="1">
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

# Simulates a client caught mid-write: the file is cut off before the
# closing tags — genuinely invalid XML, not just an odd hand.
_TRUNCATED_XML = """<session>
<general><tablename>T1</tablename><tablesize>6</tablesize>
<smallblind>0.05</smallblind><bigblind>0.10</bigblind><gametype>Holdem NL</gametype></general>
<game gamecode="1">
  <general>
    <startdate>2026-01-01T00:00:00</startdate>
    <players>
      <player name="Hero" seat="1" chips="10.00" bet="0.05" win="0.15" />
      <player name="Villain" seat="2" chips="9.90" bet="0.10" />
    </players>
  </general>
  <round no="0">"""


def _db(tmp_path):
    return PokerDatabase(tmp_path / "test.db")


def test_truncated_xml_file_does_not_lose_other_files_in_the_batch(tmp_path):
    db = _db(tmp_path)
    (tmp_path / "good.xml").write_text(_GOOD_XML, encoding="utf-8")
    (tmp_path / "broken.xml").write_text(_TRUNCATED_XML, encoding="utf-8")

    hands, errors, files_parsed, files_skipped, fingerprints = parse_directory_incremental(tmp_path, db)

    assert len(hands) == 1
    assert hands[0].hand_id == "1"
    assert any("broken.xml" in path for path, _ in errors)
    db.close()


def test_a_file_that_failed_to_parse_is_not_marked_imported(tmp_path):
    """The whole point: a failed file gets no fingerprint recorded, so
    get_file_fingerprints() won't contain it and the next scan retries it
    from scratch instead of treating "failed once" as "done forever.\""""
    db = _db(tmp_path)
    (tmp_path / "broken.xml").write_text(_TRUNCATED_XML, encoding="utf-8")

    _, _, _, _, fingerprints = parse_directory_incremental(tmp_path, db)
    db.mark_files_imported(fingerprints)

    known = db.get_file_fingerprints()
    assert not any("broken.xml" in path for path in known)
    db.close()


def test_a_torn_write_self_heals_once_the_file_is_completed(tmp_path):
    """Models exactly what a live file-watcher would trigger: scan #1
    catches the file mid-write (truncated) and finds nothing; the poker
    client finishes writing; scan #2 (same file, now complete, so a
    different (mtime, size) fingerprint) picks up the hand that was
    missed the first time — no restart, no manual fix needed."""
    db = _db(tmp_path)
    path = tmp_path / "live.xml"

    path.write_text(_TRUNCATED_XML, encoding="utf-8")
    hands_1, errors_1, _, _, fps_1 = parse_directory_incremental(tmp_path, db)
    db.mark_files_imported(fps_1)
    assert hands_1 == []
    assert len(errors_1) == 1

    # Simulate the client finishing the write a moment later — content
    # AND mtime/size both change, so the fingerprint no longer matches.
    import time
    time.sleep(0.01)
    path.write_text(_GOOD_XML, encoding="utf-8")
    hands_2, errors_2, files_parsed_2, files_skipped_2, fps_2 = parse_directory_incremental(tmp_path, db)

    assert files_skipped_2 == 0  # the fingerprint changed, so it's re-read, not skipped
    assert len(hands_2) == 1
    assert hands_2[0].hand_id == "1"
    assert errors_2 == []
    db.close()
