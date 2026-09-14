"""database/repository.py's PokerDatabase._migrate_schema — specifically
the `source` column added to hand_player_stats for the Site filter.
Unlike vpip_pfr_opp (which can only default to 1, not be re-derived
without a full stats rebuild), `source` is fully and correctly
backfillable from the hands table in one pass, so an existing user's
database should have a working Site filter immediately after an update,
not only after the next Rebuild Stats Database run."""
from database.repository import PokerDatabase


def test_source_column_is_added_and_backfilled_for_an_existing_database(tmp_path):
    db_path = tmp_path / "existing.db"

    # A real database, built with the CURRENT schema (source included),
    # standing in for "a user's database from just before this update" by
    # dropping the one column this migration is responsible for adding
    # back — modern SQLite supports DROP COLUMN directly, which is far
    # more representative of a real prior schema than hand-building a
    # stripped-down table (schema.sql's CREATE INDEX statements need
    # every other column already present, same as any real database).
    db = PokerDatabase(db_path)
    db.conn.execute(
        "INSERT INTO hands (hand_id, source, game_type, played_at) VALUES "
        "('h1', 'ggpoker', 'Texas Hold''em', '2026-06-01T00:00:00')")
    db.conn.execute(
        "INSERT INTO hand_player_stats (hand_id, player_name, played_at, profit, source) VALUES "
        "('h1', 'Hero', '2026-06-01T00:00:00', 5.0, 'ggpoker')")
    db.conn.commit()
    db.conn.execute("ALTER TABLE hand_player_stats DROP COLUMN source")
    db.conn.commit()
    db.close()

    db = PokerDatabase(db_path)  # re-open -> triggers _init_schema -> _migrate_schema again

    cols = {row[1] for row in db.conn.execute("PRAGMA table_info(hand_player_stats)")}
    assert 'source' in cols

    source = db.conn.execute(
        "SELECT source FROM hand_player_stats WHERE hand_id = 'h1' AND player_name = 'Hero'"
    ).fetchone()[0]
    assert source == 'ggpoker'  # backfilled from hands.source, not left NULL
    db.close()


def test_migration_is_a_no_op_on_a_brand_new_database(tmp_path):
    """A fresh database already has the source column from schema.sql —
    _migrate_schema's ALTER TABLE must not run (and fail) against it."""
    db = PokerDatabase(tmp_path / "fresh.db")
    cols = {row[1] for row in db.conn.execute("PRAGMA table_info(hand_player_stats)")}
    assert 'source' in cols
    db.close()


def test_limp_columns_are_added_for_an_existing_database(tmp_path):
    """Unlike source, the Limp/Limp-Call columns can't be backfilled from
    any other stored column — an existing row just reads as 0/0 (a blank
    stat) until the next Rebuild Stats Database run recomputes it from
    the raw actions."""
    db_path = tmp_path / "existing.db"
    db = PokerDatabase(db_path)
    for col in ('limp_opp', 'limp', 'limp_call_opp', 'limp_call'):
        db.conn.execute(f"ALTER TABLE hand_player_stats DROP COLUMN {col}")
    db.conn.commit()
    db.close()

    db = PokerDatabase(db_path)  # re-open -> triggers _init_schema -> _migrate_schema again

    cols = {row[1] for row in db.conn.execute("PRAGMA table_info(hand_player_stats)")}
    assert {'limp_opp', 'limp', 'limp_call_opp', 'limp_call'} <= cols
    db.close()


def test_session_type_column_is_added_and_backfills_to_cash_for_free(tmp_path):
    """Every hand imported before tournament support existed is
    unambiguously cash -- SQLite's ADD COLUMN ... DEFAULT already reports
    that value for every pre-existing row, so this needs no separate
    UPDATE pass the way `source` above does."""
    db_path = tmp_path / "existing.db"
    db = PokerDatabase(db_path)
    db.conn.execute(
        "INSERT INTO hands (hand_id, source, game_type, played_at) VALUES "
        "('h1', 'pokerstars', 'Texas Hold''em', '2026-06-01T00:00:00')")
    db.conn.execute(
        "INSERT INTO hand_player_stats (hand_id, player_name, played_at, profit, source) VALUES "
        "('h1', 'Hero', '2026-06-01T00:00:00', 5.0, 'pokerstars')")
    db.conn.commit()
    db.conn.execute("ALTER TABLE hand_player_stats DROP COLUMN session_type")
    db.conn.execute("ALTER TABLE hand_player_stats DROP COLUMN tournament_id")
    db.conn.execute("ALTER TABLE hands DROP COLUMN session_type")
    db.conn.execute("ALTER TABLE hands DROP COLUMN tournament_id")
    db.conn.execute("ALTER TABLE hands DROP COLUMN buy_in")
    db.conn.execute("ALTER TABLE hands DROP COLUMN fee")
    db.conn.commit()
    db.close()

    db = PokerDatabase(db_path)

    hps_cols = {row[1] for row in db.conn.execute("PRAGMA table_info(hand_player_stats)")}
    hand_cols = {row[1] for row in db.conn.execute("PRAGMA table_info(hands)")}
    assert {'session_type', 'tournament_id'} <= hps_cols
    assert {'session_type', 'tournament_id', 'buy_in', 'fee'} <= hand_cols

    session_type = db.conn.execute(
        "SELECT session_type FROM hand_player_stats WHERE hand_id = 'h1'").fetchone()[0]
    assert session_type == 'cash'
    hands_session_type = db.conn.execute(
        "SELECT session_type FROM hands WHERE hand_id = 'h1'").fetchone()[0]
    assert hands_session_type == 'cash'
    db.close()


def test_fold_3bet_as_raiser_columns_are_added_for_an_existing_database(tmp_path):
    """Like the Limp/Limp-Call columns above, not backfillable from any
    other stored column — an existing row just reads as 0/0 until the
    next Rebuild Stats Database run recomputes it from the raw actions."""
    db_path = tmp_path / "existing.db"
    db = PokerDatabase(db_path)
    for col in ('faced_3bet_as_raiser_opp', 'folded_to_3bet_as_raiser'):
        db.conn.execute(f"ALTER TABLE hand_player_stats DROP COLUMN {col}")
    db.conn.commit()
    db.close()

    db = PokerDatabase(db_path)  # re-open -> triggers _init_schema -> _migrate_schema again

    cols = {row[1] for row in db.conn.execute("PRAGMA table_info(hand_player_stats)")}
    assert {'faced_3bet_as_raiser_opp', 'folded_to_3bet_as_raiser'} <= cols
    db.close()


def test_rake_column_is_added_for_an_existing_database(tmp_path):
    """NOT backfillable from hands.rake directly, unlike `source` above --
    that column is the WHOLE table's rake for a hand, not any one
    player's own share of it (see database/hand_stats_builder.py's even
    split across whoever saw the flop). Like limp_opp, an existing row
    just reads as NULL until the next Rebuild Stats Database run
    recomputes it properly from the raw actions."""
    db_path = tmp_path / "existing.db"
    db = PokerDatabase(db_path)
    db.conn.execute(
        "INSERT INTO hands (hand_id, source, game_type, played_at, rake) VALUES "
        "('h1', 'ipoker', 'Texas Hold''em', '2026-06-01T00:00:00', 0.75)")
    db.conn.execute(
        "INSERT INTO hand_player_stats (hand_id, player_name, played_at, profit, source, rake) VALUES "
        "('h1', 'Hero', '2026-06-01T00:00:00', 5.0, 'ipoker', 0.75)")
    db.conn.commit()
    db.conn.execute("ALTER TABLE hand_player_stats DROP COLUMN rake")
    db.conn.commit()
    db.close()

    db = PokerDatabase(db_path)  # re-open -> triggers _init_schema -> _migrate_schema again

    cols = {row[1] for row in db.conn.execute("PRAGMA table_info(hand_player_stats)")}
    assert 'rake' in cols

    rake = db.conn.execute(
        "SELECT rake FROM hand_player_stats WHERE hand_id = 'h1' AND player_name = 'Hero'"
    ).fetchone()[0]
    assert rake is None  # not backfilled -- needs a Rebuild Stats Database run
    db.close()


def test_tournament_results_table_exists_on_a_fresh_database(tmp_path):
    db = PokerDatabase(tmp_path / "fresh.db")
    tables = {row[0] for row in db.conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert 'tournament_results' in tables
    db.close()
