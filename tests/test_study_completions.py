"""database/repository.py's study_completions methods — the persistence
layer behind Study Queue completion tracking. Pure DB round-trip
coverage; core/study_queue.py's test file covers the streak-day
arithmetic itself without a database."""
from datetime import date, datetime, timedelta

import pytest

from database.repository import PokerDatabase


@pytest.fixture()
def db(tmp_path):
    database = PokerDatabase(tmp_path / "test.db")
    yield database
    database.close()


def test_logged_completion_is_recent(db):
    db.log_study_completion("vpip", "SB")
    assert ("vpip", "SB") in db.get_recent_study_completions(days=7)


def test_unlogged_pair_is_not_recent(db):
    db.log_study_completion("vpip", "SB")
    assert ("three_bet", "BB") not in db.get_recent_study_completions(days=7)


def test_old_completion_falls_outside_the_recent_window(db):
    old = (datetime.now() - timedelta(days=10)).isoformat()
    db.conn.execute(
        "INSERT INTO study_completions (stat_id, position, completed_at) VALUES (?, ?, ?)",
        ("vpip", "SB", old))
    db.conn.commit()
    assert ("vpip", "SB") not in db.get_recent_study_completions(days=7)


def test_completion_dates_returns_distinct_calendar_dates(db):
    today = date.today().isoformat()
    db.conn.executemany(
        "INSERT INTO study_completions (stat_id, position, completed_at) VALUES (?, ?, ?)",
        [("vpip", "SB", f"{today}T10:00:00"), ("three_bet", "BB", f"{today}T11:00:00")])
    db.conn.commit()
    assert db.get_study_completion_dates() == [date.today()]


def test_no_completions_returns_empty(db):
    assert db.get_recent_study_completions() == set()
    assert db.get_study_completion_dates() == []
