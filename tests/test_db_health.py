"""core/db_health.py — must correctly flag orphaned stat rows and hands
missing their stats row, and must never write anything to the database
it's checking (it's meant to be safe to run at any time)."""
import pytest

from database.repository import PokerDatabase, _STATS_COLS
from core.db_health import check_database_health

_DEFAULTS = {c: 0 for c in _STATS_COLS}
_DEFAULTS.update({"hand_id": None, "player_name": None, "played_at": None, "vpip_pfr_opp": 1})


@pytest.fixture()
def db(tmp_path):
    database = PokerDatabase(tmp_path / "test.db")
    yield database
    database.close()


def _insert_hand_with_stats(db, hand_id):
    db.conn.execute(
        "INSERT OR IGNORE INTO hands (hand_id, game_type, played_at) VALUES (?, 'Texas Hold''em', ?)",
        (hand_id, "2026-06-01T00:00:00"),
    )
    row = {**_DEFAULTS, "hand_id": hand_id, "player_name": "Hero"}
    cols = _STATS_COLS
    db.conn.execute(
        f"INSERT INTO hand_player_stats ({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)})",
        [row[c] for c in cols],
    )
    db.conn.commit()


def test_clean_database_reports_ok(db):
    _insert_hand_with_stats(db, "h1")
    _insert_hand_with_stats(db, "h2")

    report = check_database_health(db)
    assert report.ok is True
    assert report.integrity_check == "ok"
    assert report.hand_count == 2
    assert report.stats_row_count == 2
    assert report.orphaned_stats_rows == 0
    assert report.hands_missing_stats == 0
    assert report.issues == []


def test_detects_a_hand_with_no_stats_row(db):
    _insert_hand_with_stats(db, "h1")
    # A hand row with no matching hand_player_stats row at all.
    db.conn.execute(
        "INSERT INTO hands (hand_id, game_type, played_at) VALUES ('h2', 'Texas Hold''em', ?)",
        ("2026-06-01T00:00:00",),
    )
    db.conn.commit()

    report = check_database_health(db)
    assert report.ok is False
    assert report.hands_missing_stats == 1
    assert any("no computed stats" in issue for issue in report.issues)


def test_detects_an_orphaned_stats_row(db):
    _insert_hand_with_stats(db, "h1")
    # PokerDatabase enforces the FOREIGN KEY constraint (repository.py
    # turns it on), so a normal DELETE genuinely can't orphan a stats row
    # — this can only happen from a database file that got into this
    # state some other way (e.g. edited by an older app version, or a
    # different tool). Simulate that by disabling enforcement just for
    # this one operation, matching how such a file would actually arise.
    db.conn.execute("PRAGMA foreign_keys = OFF")
    db.conn.execute("DELETE FROM hands WHERE hand_id = 'h1'")
    db.conn.commit()
    db.conn.execute("PRAGMA foreign_keys = ON")

    report = check_database_health(db)
    assert report.ok is False
    assert report.orphaned_stats_rows == 1
    assert any("no longer exists" in issue for issue in report.issues)


def test_check_never_modifies_the_database(db):
    _insert_hand_with_stats(db, "h1")
    before_hands = db.conn.execute("SELECT COUNT(*) FROM hands").fetchone()[0]
    before_stats = db.conn.execute("SELECT COUNT(*) FROM hand_player_stats").fetchone()[0]

    check_database_health(db)

    after_hands = db.conn.execute("SELECT COUNT(*) FROM hands").fetchone()[0]
    after_stats = db.conn.execute("SELECT COUNT(*) FROM hand_player_stats").fetchone()[0]
    assert (before_hands, before_stats) == (after_hands, after_stats)


def test_empty_database_is_healthy(db):
    report = check_database_health(db)
    assert report.ok is True
    assert report.hand_count == 0


def test_hand_player_stats_has_a_played_at_only_index(db):
    """Population-style queries filter by played_at across ALL players (no
    player_name in the WHERE), so they need an index that doesn't lead with
    player_name to avoid a full scan regardless of date-range width — see
    schema.sql's comment above idx_hps_played_at for the measured impact
    (a 900k-row all-time population query: ~3.6s -> ~0.5s)."""
    indexes = db.conn.execute("PRAGMA index_list(hand_player_stats)").fetchall()
    played_at_only_index = None
    for row in indexes:
        index_name = row[1]
        cols = [c[2] for c in db.conn.execute(f"PRAGMA index_info({index_name})").fetchall()]
        if cols == ["played_at"]:
            played_at_only_index = index_name
    assert played_at_only_index is not None, (
        "hand_player_stats needs an index on played_at alone (not composed "
        "with player_name) for population-wide date-range queries to seek "
        "instead of full-scanning"
    )
