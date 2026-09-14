"""database/queries.py's free-tier stakes gating (core/licensing.py's
should_gate_by_stakes) -- currently dormant everywhere (LICENSE_ENFORCED
is False, so should_gate_by_stakes() always returns False and every one
of these queries behaves exactly as before), but must filter correctly
the moment enforcement is ever flipped on. Monkeypatches
database.queries.should_gate_by_stakes directly (the name bound in that
module's own namespace via its `from core.licensing import ...`), not
core.licensing.should_gate_by_stakes, since that's the one each query
function actually calls."""
from datetime import date

import pytest

import database.queries as q
from database.repository import PokerDatabase, _STATS_COLS
from database.queries import (
    hero_overview_query, sessions_query, villain_stats_query, tournament_list_query,
    hands_for_stat_query,
)

_DEFAULTS = {c: 0 for c in _STATS_COLS}
_DEFAULTS.update({
    "hand_id": None, "player_name": None, "played_at": None, "big_blind": None,
    "profit": 0.0, "ev": None, "position": None, "stakes_label": None, "source": None,
    "vpip_pfr_opp": 1, "session_type": "cash", "tournament_id": None,
})


@pytest.fixture()
def db(tmp_path):
    database = PokerDatabase(tmp_path / "test.db")
    yield database
    database.close()


def _insert_stats_row(db, **overrides):
    row = {**_DEFAULTS, **overrides}
    db.conn.execute(
        "INSERT OR IGNORE INTO hands (hand_id, game_type, played_at) VALUES (?, 'Texas Hold''em', ?)",
        (row["hand_id"], row["played_at"]),
    )
    cols = _STATS_COLS
    placeholders = ", ".join("?" for _ in cols)
    db.conn.execute(
        f"INSERT INTO hand_player_stats ({', '.join(cols)}) VALUES ({placeholders})",
        [row[c] for c in cols],
    )
    db.conn.commit()


@pytest.fixture()
def gated(monkeypatch):
    """Simulates LICENSE_ENFORCED=True with no valid key, without needing
    the full licensing machinery here -- these tests are about the query
    layer respecting the flag, not re-testing is_licensed() itself
    (already covered by tests/test_licensing.py)."""
    monkeypatch.setattr(q, "should_gate_by_stakes", lambda: True)


def test_gate_is_off_by_default(db):
    """Sanity check matching every OTHER test in test_queries.py, which
    already exercises these same queries with a mix of stakes and never
    monkeypatches the gate -- confirms should_gate_by_stakes() really is
    a no-op until explicitly turned on."""
    _insert_stats_row(db, hand_id="h1", player_name="Hero", played_at="2026-06-01T00:00:00",
                       big_blind=1.00, profit=5.0, stakes_label="£0.50/£1.00")
    values, _ = hero_overview_query(db, "Hero", date(2026, 6, 1), date(2026, 6, 30))
    assert values["hands"] == 1


def test_hero_overview_excludes_hands_above_the_free_tier_when_gated(db, gated):
    _insert_stats_row(db, hand_id="micro", player_name="Hero", played_at="2026-06-01T00:00:00",
                       big_blind=0.05, profit=1.0, stakes_label="£0.02/£0.05")
    _insert_stats_row(db, hand_id="high", player_name="Hero", played_at="2026-06-01T00:00:00",
                       big_blind=1.00, profit=100.0, stakes_label="£0.50/£1.00")

    values, _ = hero_overview_query(db, "Hero", date(2026, 6, 1), date(2026, 6, 30))

    assert values["hands"] == 1
    assert values["profit"] == pytest.approx(1.0)


def test_hero_overview_includes_exactly_5nl_when_gated(db, gated):
    """The free tier is inclusive of 5NL itself, not just below it."""
    _insert_stats_row(db, hand_id="five_nl", player_name="Hero", played_at="2026-06-01T00:00:00",
                       big_blind=0.05, profit=2.0, stakes_label="£0.02/£0.05")

    values, _ = hero_overview_query(db, "Hero", date(2026, 6, 1), date(2026, 6, 30))

    assert values["hands"] == 1


def test_sessions_query_excludes_high_stakes_sessions_when_gated(db, gated):
    _insert_stats_row(db, hand_id="micro", player_name="Hero", played_at="2026-06-01T00:00:00",
                       big_blind=0.05, profit=1.0, stakes_label="£0.02/£0.05")
    _insert_stats_row(db, hand_id="high", player_name="Hero", played_at="2026-06-02T00:00:00",
                       big_blind=1.00, profit=100.0, stakes_label="£0.50/£1.00")

    rows = sessions_query(db, "Hero", date(2026, 6, 1), date(2026, 6, 30))

    stakes_seen = {r[1] for r in rows}
    assert stakes_seen == {"£0.02/£0.05"}


def test_villain_stats_query_excludes_high_stakes_hands_when_gated(db, gated):
    """Gating applies uniformly across the whole app, not just hero's own
    tabs -- a villain's stats are also scoped to the free-tier stake
    ceiling once the gate is on."""
    _insert_stats_row(db, hand_id="micro", player_name="Villain1", played_at="2026-06-01T00:00:00",
                       big_blind=0.05, vpip=1, vpip_pfr_opp=1, session_type="cash")
    _insert_stats_row(db, hand_id="high", player_name="Villain1", played_at="2026-06-02T00:00:00",
                       big_blind=1.00, vpip=0, vpip_pfr_opp=1, session_type="cash")

    values, hand_count, _, _ = villain_stats_query(
        db, "Villain1", date(2026, 6, 1), date(2026, 6, 30), session_type="cash")

    assert hand_count == 1
    assert values["vpip"] == 100.0


def test_hands_for_stat_query_excludes_high_stakes_hands_when_gated(db, gated):
    _insert_stats_row(db, hand_id="micro", player_name="Hero", played_at="2026-06-01T00:00:00",
                       big_blind=0.05, vpip=1, session_type="cash")
    _insert_stats_row(db, hand_id="high", player_name="Hero", played_at="2026-06-02T00:00:00",
                       big_blind=1.00, vpip=1, session_type="cash")

    rows = hands_for_stat_query(db, "Hero", "vpip", date(2026, 6, 1), date(2026, 6, 30),
                                  session_type="cash")

    assert [r[0] for r in rows] == ["micro"]


def _insert_tournament_hand(db, hand_id, buy_in, played_at="2026-06-01T00:00:00"):
    db.conn.execute(
        "INSERT INTO hands (hand_id, game_type, played_at, session_type, tournament_id, buy_in) "
        "VALUES (?, 'Texas Hold''em', ?, 'tournament', ?, ?)",
        (hand_id, played_at, hand_id, buy_in))
    row = {**_DEFAULTS, "hand_id": hand_id, "player_name": "Hero", "played_at": played_at,
           "session_type": "tournament", "tournament_id": hand_id, "profit": None, "ev": None}
    cols = _STATS_COLS
    placeholders = ", ".join("?" for _ in cols)
    db.conn.execute(
        f"INSERT INTO hand_player_stats ({', '.join(cols)}) VALUES ({placeholders})",
        [row[c] for c in cols])
    db.conn.commit()


def test_tournament_list_query_excludes_buyins_above_the_free_tier_when_gated(db, gated):
    _insert_tournament_hand(db, "cheap", buy_in=4.0)
    _insert_tournament_hand(db, "expensive", buy_in=50.0)

    rows = tournament_list_query(db, "Hero", date(2026, 6, 1), date(2026, 6, 30))

    assert [r["tournament_id"] for r in rows] == ["cheap"]


def test_tournament_list_query_includes_exactly_five_dollars_when_gated(db, gated):
    _insert_tournament_hand(db, "exactly_five", buy_in=5.0)

    rows = tournament_list_query(db, "Hero", date(2026, 6, 1), date(2026, 6, 30))

    assert [r["tournament_id"] for r in rows] == ["exactly_five"]


def test_tournament_list_query_does_not_exclude_an_unknown_buy_in_when_gated(db, gated):
    """An unlogged/unparsed buy-in isn't proven to exceed the free tier,
    so it isn't excluded -- matching this project's "never guess" rule."""
    db.conn.execute(
        "INSERT INTO hands (hand_id, game_type, played_at, session_type, tournament_id, buy_in) "
        "VALUES ('unknown', 'Texas Hold''em', '2026-06-01T00:00:00', 'tournament', 'unknown', NULL)")
    row = {**_DEFAULTS, "hand_id": "unknown", "player_name": "Hero", "played_at": "2026-06-01T00:00:00",
           "session_type": "tournament", "tournament_id": "unknown", "profit": None, "ev": None}
    cols = _STATS_COLS
    placeholders = ", ".join("?" for _ in cols)
    db.conn.execute(
        f"INSERT INTO hand_player_stats ({', '.join(cols)}) VALUES ({placeholders})",
        [row[c] for c in cols])
    db.conn.commit()

    rows = tournament_list_query(db, "Hero", date(2026, 6, 1), date(2026, 6, 30))

    assert [r["tournament_id"] for r in rows] == ["unknown"]
