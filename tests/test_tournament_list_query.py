"""database/queries.py's tournament_list_query — the backing data for
ui/tournaments_tab.py's results table. Built via a real db.import_hands()
pass (not hand-inserted rows) since it needs both `hands` (buy_in/fee)
and `hand_player_stats` (session_type/tournament_id) populated
consistently, the way the real import pipeline actually produces them."""
from datetime import date, datetime, timedelta

import pytest

from database.repository import PokerDatabase
from database.queries import tournament_list_query
from models.hand import Hand, Player, Action


@pytest.fixture()
def db(tmp_path):
    database = PokerDatabase(tmp_path / "test.db")
    yield database
    database.close()


def _tournament_hand(hand_id, tournament_id, played_at, source="pokerstars", buy_in=10.0, fee=1.0, hero_wins=True):
    return Hand(
        hand_id=hand_id, source=source, big_blind=200.0, played_at=played_at,
        session_type="tournament", tournament_id=tournament_id, buy_in=buy_in, fee=fee,
        players=[Player("Hero", 1, 10000.0), Player("Villain1", 2, 10000.0)],
        actions=[Action("PREFLOP", "Hero", "Post SB", 100.0), Action("PREFLOP", "Villain1", "Post BB", 200.0),
                 Action("PREFLOP", "Hero", "Raise", 600.0), Action("PREFLOP", "Villain1", "Fold", None)],
        winnings={"Hero": 300.0} if hero_wins else {},
    )


def _cash_hand(hand_id, played_at):
    return Hand(
        hand_id=hand_id, source="pokerstars", big_blind=0.10, played_at=played_at, session_type="cash",
        players=[Player("Hero", 1, 2.0), Player("Villain1", 2, 2.0)],
        actions=[Action("PREFLOP", "Hero", "Post SB", 0.05), Action("PREFLOP", "Villain1", "Post BB", 0.10),
                 Action("PREFLOP", "Hero", "Fold", None)],
    )


def test_returns_one_row_per_distinct_tournament(db):
    base = datetime(2026, 6, 1)
    db.import_hands([
        _tournament_hand("h1", "t1", base),
        _tournament_hand("h2", "t1", base + timedelta(minutes=5)),
        _tournament_hand("h3", "t2", base + timedelta(hours=1)),
    ], ev_iterations=1)

    rows = tournament_list_query(db, "Hero", date(2026, 6, 1), date(2026, 6, 30))

    by_id = {r['tournament_id']: r for r in rows}
    assert set(by_id) == {"t1", "t2"}
    assert by_id["t1"]["hand_count"] == 2
    assert by_id["t2"]["hand_count"] == 1
    assert by_id["t1"]["buy_in"] == 10.0 and by_id["t1"]["fee"] == 1.0
    assert by_id["t1"]["source"] == "pokerstars"


def test_excludes_cash_hands(db):
    db.import_hands([_cash_hand("c1", datetime(2026, 6, 1))], ev_iterations=1)
    rows = tournament_list_query(db, "Hero", date(2026, 6, 1), date(2026, 6, 30))
    assert rows == []


def test_unlogged_tournament_has_none_result_fields(db):
    db.import_hands([_tournament_hand("h1", "t1", datetime(2026, 6, 1))], ev_iterations=1)
    rows = tournament_list_query(db, "Hero", date(2026, 6, 1), date(2026, 6, 30))
    assert rows[0]['finish_position'] is None
    assert rows[0]['payout'] is None


def test_logged_result_is_included(db):
    db.import_hands([_tournament_hand("h1", "t1", datetime(2026, 6, 1))], ev_iterations=1)
    db.set_tournament_result("t1", finish_position=2, field_size=90, payout=45.0, currency="$")

    rows = tournament_list_query(db, "Hero", date(2026, 6, 1), date(2026, 6, 30))

    assert rows[0]['finish_position'] == 2
    assert rows[0]['field_size'] == 90
    assert rows[0]['payout'] == 45.0
    assert rows[0]['currency'] == "$"


def test_filters_by_site(db):
    db.import_hands([
        _tournament_hand("h1", "t1", datetime(2026, 6, 1), source="pokerstars"),
        _tournament_hand("h2", "t2", datetime(2026, 6, 2), source="winning_network"),
    ], ev_iterations=1)

    rows = tournament_list_query(db, "Hero", date(2026, 6, 1), date(2026, 6, 30), site="winning_network")

    assert [r['tournament_id'] for r in rows] == ["t2"]


def test_rows_sorted_by_most_recent_first(db):
    db.import_hands([
        _tournament_hand("h1", "t1", datetime(2026, 6, 1)),
        _tournament_hand("h2", "t2", datetime(2026, 6, 15)),
    ], ev_iterations=1)

    rows = tournament_list_query(db, "Hero", date(2026, 6, 1), date(2026, 6, 30))

    assert [r['tournament_id'] for r in rows] == ["t2", "t1"]
