"""Direct coverage for database/queries.py against a real SQLite database —
previously this SQL layer was only exercised indirectly through UI-level
offscreen tests. Rows are inserted straight into hand_player_stats (via
_insert_stats_row below) rather than through the full import_hands()
pipeline, which spins up a multiprocessing.Pool per call — overkill and
slow for a handful of synthetic test rows when the parsing/stat-computation
side is already covered by tests/test_stats.py."""
from datetime import date

import pytest

from database.repository import PokerDatabase, _STATS_COLS
from database.queries import (
    hero_overview_query, sessions_query, available_stakes_query,
    population_summary_query, hands_for_stat_query, hands_for_position_query,
    position_breakdown_query, population_by_position_query,
)

_DEFAULTS = {c: 0 for c in _STATS_COLS}
_DEFAULTS.update({
    "hand_id": None, "player_name": None, "played_at": None, "big_blind": None,
    "profit": 0.0, "ev": None, "position": None, "stakes_label": None,
    "vpip_pfr_opp": 1,
})


@pytest.fixture()
def db(tmp_path):
    database = PokerDatabase(tmp_path / "test.db")
    yield database
    database.close()


def _insert_stats_row(db, **overrides):
    row = {**_DEFAULTS, **overrides}
    # OR IGNORE: several players can share the same hand_id (one hands row
    # per hand, one hand_player_stats row per player in it).
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


def test_hero_overview_vpip_pfr_and_profit(db):
    _insert_stats_row(db, hand_id="h1", player_name="Hero", played_at="2026-06-01T12:00:00",
                       big_blind=0.30, profit=3.0, ev=3.0, stakes_label="£0.15/£0.30",
                       vpip=1, pfr=1)
    _insert_stats_row(db, hand_id="h2", player_name="Hero", played_at="2026-06-02T12:00:00",
                       big_blind=0.30, profit=-1.5, ev=-1.5, stakes_label="£0.15/£0.30",
                       vpip=0, pfr=0)

    values, graph = hero_overview_query(db, "Hero", date(2026, 6, 1), date(2026, 6, 30))
    assert values["hands"] == 2
    assert values["profit"] == pytest.approx(1.5)
    assert values["vpip"] == 50.0
    assert values["pfr"] == 50.0
    xs, total, *_ = graph
    assert xs == [1, 2]
    assert total[-1] == pytest.approx(1.5)


def test_hero_overview_excludes_hands_outside_the_date_range(db):
    _insert_stats_row(db, hand_id="in_range", player_name="Hero", played_at="2026-06-15T00:00:00",
                       big_blind=0.30, profit=5.0, stakes_label="£0.15/£0.30")
    _insert_stats_row(db, hand_id="before", player_name="Hero", played_at="2026-05-01T00:00:00",
                       big_blind=0.30, profit=100.0, stakes_label="£0.15/£0.30")
    _insert_stats_row(db, hand_id="after", player_name="Hero", played_at="2026-07-01T00:00:00",
                       big_blind=0.30, profit=-100.0, stakes_label="£0.15/£0.30")

    values, _ = hero_overview_query(db, "Hero", date(2026, 6, 1), date(2026, 6, 30))
    assert values["hands"] == 1
    assert values["profit"] == pytest.approx(5.0)


def test_hero_overview_filters_by_stake(db):
    _insert_stats_row(db, hand_id="low", player_name="Hero", played_at="2026-06-01T00:00:00",
                       big_blind=0.30, profit=1.0, stakes_label="£0.15/£0.30")
    _insert_stats_row(db, hand_id="high", player_name="Hero", played_at="2026-06-01T00:00:00",
                       big_blind=1.0, profit=10.0, stakes_label="£0.50/£1.00")

    values, _ = hero_overview_query(db, "Hero", date(2026, 6, 1), date(2026, 6, 30), stake="£0.50/£1.00")
    assert values["hands"] == 1
    assert values["profit"] == pytest.approx(10.0)


def test_hero_overview_bb100_normalizes_across_mixed_stakes(db):
    # 1 hand at 0.30 BB winning 3.0 -> +10 BB/100 hands worth
    # 1 hand at 1.00 BB winning 10.0 -> +10 BB/100 hands worth
    # Averaged as bb-units-per-hand * 100, not raw $ averaged.
    _insert_stats_row(db, hand_id="a", player_name="Hero", played_at="2026-06-01T00:00:00",
                       big_blind=0.30, profit=3.0, stakes_label="£0.15/£0.30")
    _insert_stats_row(db, hand_id="b", player_name="Hero", played_at="2026-06-01T00:00:00",
                       big_blind=1.00, profit=10.0, stakes_label="£0.50/£1.00")

    values, _ = hero_overview_query(db, "Hero", date(2026, 6, 1), date(2026, 6, 30))
    assert values["bb100"] == pytest.approx(1000.0)  # (10+10)/2 * 100


def test_sessions_query_groups_by_date_and_stakes(db):
    _insert_stats_row(db, hand_id="h1", player_name="Hero", played_at="2026-06-01T10:00:00",
                       big_blind=0.30, profit=1.0, stakes_label="£0.15/£0.30")
    _insert_stats_row(db, hand_id="h2", player_name="Hero", played_at="2026-06-01T14:00:00",
                       big_blind=0.30, profit=2.0, stakes_label="£0.15/£0.30")
    _insert_stats_row(db, hand_id="h3", player_name="Hero", played_at="2026-06-01T18:00:00",
                       big_blind=1.00, profit=5.0, stakes_label="£0.50/£1.00")

    rows = sessions_query(db, "Hero", date(2026, 6, 1), date(2026, 6, 30))
    assert len(rows) == 2  # two distinct (date, stakes) buckets


def test_available_stakes_query_returns_distinct_stakes_in_range(db):
    _insert_stats_row(db, hand_id="h1", player_name="Hero", played_at="2026-06-01T00:00:00",
                       big_blind=0.30, stakes_label="£0.15/£0.30")
    _insert_stats_row(db, hand_id="h2", player_name="Hero", played_at="2026-06-02T00:00:00",
                       big_blind=1.00, stakes_label="£0.50/£1.00")
    _insert_stats_row(db, hand_id="h3", player_name="Hero", played_at="2026-01-01T00:00:00",
                       big_blind=2.00, stakes_label="£1/£2")  # outside range

    stakes = available_stakes_query(db, "Hero", date(2026, 6, 1), date(2026, 6, 30))
    assert set(stakes) == {"£0.15/£0.30", "£0.50/£1.00"}


def test_population_summary_excludes_the_hero_and_anon_placeholders(db):
    _insert_stats_row(db, hand_id="h1", player_name="Hero", played_at="2026-06-01T00:00:00",
                       big_blind=0.30, stakes_label="£0.15/£0.30")
    _insert_stats_row(db, hand_id="h1", player_name="Villain1", played_at="2026-06-01T00:00:00",
                       big_blind=0.30, stakes_label="£0.15/£0.30", vpip=1)
    _insert_stats_row(db, hand_id="h1", player_name="Player 3", played_at="2026-06-01T00:00:00",
                       big_blind=0.30, stakes_label="£0.15/£0.30")

    rows = population_summary_query(db, "Hero", date(2026, 6, 1), date(2026, 6, 30))
    assert "Hero" not in rows
    assert "Player 3" not in rows
    assert "Villain1" in rows
    assert rows["Villain1"].vpip == 1


def test_hands_for_stat_query_matches_the_right_condition(db):
    _insert_stats_row(db, hand_id="raised", player_name="Hero", played_at="2026-06-01T00:00:00",
                       big_blind=0.30, stakes_label="£0.15/£0.30", vpip=1, pfr=1)
    _insert_stats_row(db, hand_id="called", player_name="Hero", played_at="2026-06-01T00:00:00",
                       big_blind=0.30, stakes_label="£0.15/£0.30", vpip=1, pfr=0)

    rows = hands_for_stat_query(db, "Hero", "pfr", date(2026, 6, 1), date(2026, 6, 30))
    hand_ids = {r[0] for r in rows}
    assert hand_ids == {"raised"}


def test_hands_for_position_query_all_hands_when_position_is_none(db):
    _insert_stats_row(db, hand_id="h1", player_name="Hero", played_at="2026-06-01T00:00:00",
                       big_blind=0.30, stakes_label="£0.15/£0.30", position="BTN")
    _insert_stats_row(db, hand_id="h2", player_name="Hero", played_at="2026-06-01T00:00:00",
                       big_blind=0.30, stakes_label="£0.15/£0.30", position="BB")

    all_rows = hands_for_position_query(db, "Hero", None, date(2026, 6, 1), date(2026, 6, 30))
    btn_rows = hands_for_position_query(db, "Hero", "BTN", date(2026, 6, 1), date(2026, 6, 30))
    assert len(all_rows) == 2
    assert [r[0] for r in btn_rows] == ["h1"]


def test_hands_for_position_query_sb_includes_heads_up_btn_sb_label(db):
    _insert_stats_row(db, hand_id="h1", player_name="Hero", played_at="2026-06-01T00:00:00",
                       big_blind=0.30, stakes_label="£0.15/£0.30", position="SB")
    _insert_stats_row(db, hand_id="h2", player_name="Hero", played_at="2026-06-01T00:00:00",
                       big_blind=0.30, stakes_label="£0.15/£0.30", position="BTN/SB")
    _insert_stats_row(db, hand_id="h3", player_name="Hero", played_at="2026-06-01T00:00:00",
                       big_blind=0.30, stakes_label="£0.15/£0.30", position="BB")

    rows = hands_for_position_query(db, "Hero", "SB", date(2026, 6, 1), date(2026, 6, 30))
    assert {r[0] for r in rows} == {"h1", "h2"}


def test_population_by_position_query_excludes_hero_and_pools_others(db):
    # Hero's own BTN hand must not count toward the population average.
    _insert_stats_row(db, hand_id="h1", player_name="Hero", played_at="2026-06-01T00:00:00",
                       big_blind=0.30, stakes_label="£0.15/£0.30", position="BTN",
                       vpip=1, vpip_pfr_opp=1)
    _insert_stats_row(db, hand_id="h1", player_name="Villain1", played_at="2026-06-01T00:00:00",
                       big_blind=0.30, stakes_label="£0.15/£0.30", position="BB",
                       vpip=1, vpip_pfr_opp=1)
    _insert_stats_row(db, hand_id="h2", player_name="Villain2", played_at="2026-06-02T00:00:00",
                       big_blind=0.30, stakes_label="£0.15/£0.30", position="BTN",
                       vpip=1, vpip_pfr_opp=1)
    _insert_stats_row(db, hand_id="h3", player_name="Villain3", played_at="2026-06-03T00:00:00",
                       big_blind=0.30, stakes_label="£0.15/£0.30", position="BTN",
                       vpip=0, vpip_pfr_opp=1)

    result = population_by_position_query(db, "Hero", date(2026, 6, 1), date(2026, 6, 30))

    btn_values, btn_hands, btn_opp = result["BTN"]
    assert btn_hands == 2  # Villain2 + Villain3 only, NOT Hero's own BTN hand
    assert btn_values["vpip"] == 50.0  # 1 of 2 — Hero's own BTN vpip=1 hand is correctly excluded


def test_population_by_position_query_folds_heads_up_btn_sb_into_sb(db):
    _insert_stats_row(db, hand_id="h1", player_name="Hero", played_at="2026-06-01T00:00:00",
                       big_blind=0.30, stakes_label="£0.15/£0.30", position="BB")
    _insert_stats_row(db, hand_id="h1", player_name="Villain1", played_at="2026-06-01T00:00:00",
                       big_blind=0.30, stakes_label="£0.15/£0.30", position="BTN/SB",
                       vpip=1, vpip_pfr_opp=1)
    _insert_stats_row(db, hand_id="h2", player_name="Villain2", played_at="2026-06-02T00:00:00",
                       big_blind=0.30, stakes_label="£0.15/£0.30", position="SB",
                       vpip=0, vpip_pfr_opp=1)

    result = population_by_position_query(db, "Hero", date(2026, 6, 1), date(2026, 6, 30))

    assert "BTN/SB" not in result
    sb_values, sb_hands, sb_opp = result["SB"]
    assert sb_hands == 2


def test_population_by_position_matches_hero_query_shape_for_the_same_data(db):
    """Same underlying formula as position_breakdown_query — swapping which
    side of the WHERE clause gets the player name shouldn't change the
    computed values for an otherwise-identical row."""
    _insert_stats_row(db, hand_id="h1", player_name="Hero", played_at="2026-06-01T00:00:00",
                       big_blind=0.30, stakes_label="£0.15/£0.30", position="CO",
                       three_bet=1, three_bet_opp=1)

    hero_result = position_breakdown_query(db, "Hero", date(2026, 6, 1), date(2026, 6, 30))
    pop_result = population_by_position_query(db, "SomeoneElse", date(2026, 6, 1), date(2026, 6, 30))

    assert hero_result["CO"][0]["three_bet"] == pop_result["CO"][0]["three_bet"] == 100.0


def test_hands_for_stat_query_supports_fold_to_steal(db):
    _insert_stats_row(db, hand_id="h1", player_name="Hero", played_at="2026-06-01T00:00:00",
                       big_blind=0.30, stakes_label="£0.15/£0.30", folded_to_steal=1)
    _insert_stats_row(db, hand_id="h2", player_name="Hero", played_at="2026-06-01T00:00:00",
                       big_blind=0.30, stakes_label="£0.15/£0.30", folded_to_steal=0)

    rows = hands_for_stat_query(db, "Hero", "fold_to_steal", date(2026, 6, 1), date(2026, 6, 30))
    assert {r[0] for r in rows} == {"h1"}


def test_showdown_hand_ids_query_finds_hands_where_a_non_hero_reached_showdown(db):
    from database.queries import showdown_hand_ids_query
    _insert_stats_row(db, hand_id="h1", player_name="Hero", played_at="2026-06-01T00:00:00",
                       big_blind=0.30, stakes_label="£0.15/£0.30", reached_showdown=0)
    _insert_stats_row(db, hand_id="h1", player_name="Villain1", played_at="2026-06-01T00:00:00",
                       big_blind=0.30, stakes_label="£0.15/£0.30", reached_showdown=1)
    _insert_stats_row(db, hand_id="h2", player_name="Hero", played_at="2026-06-02T00:00:00",
                       big_blind=0.30, stakes_label="£0.15/£0.30", reached_showdown=1)  # only hero showed down

    hand_ids = showdown_hand_ids_query(db, "Hero", date(2026, 6, 1), date(2026, 6, 30))
    assert hand_ids == ["h1"]


def test_showdown_hand_ids_query_respects_the_limit(db):
    from database.queries import showdown_hand_ids_query
    for i in range(5):
        _insert_stats_row(db, hand_id=f"h{i}", player_name="Villain1", played_at="2026-06-01T00:00:00",
                           big_blind=0.30, stakes_label="£0.15/£0.30", reached_showdown=1)

    hand_ids = showdown_hand_ids_query(db, "Hero", date(2026, 6, 1), date(2026, 6, 30), limit=2)
    assert len(hand_ids) == 2
