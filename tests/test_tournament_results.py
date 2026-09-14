"""database/repository.py's tournament_results methods — no hand-history
export contains a finish position or payout, so this is the persistence
layer behind the manually-entered result that actually makes ROI/ITM%
real numbers rather than just a hand count."""
import pytest

from database.repository import PokerDatabase


@pytest.fixture()
def db(tmp_path):
    database = PokerDatabase(tmp_path / "test.db")
    yield database
    database.close()


def test_set_and_get_a_tournament_result(db):
    db.set_tournament_result("396042592", finish_position=3, field_size=180, payout=45.0, currency="$")
    results = db.get_tournament_results()
    assert results["396042592"] == (3, 180, 45.0, "$")


def test_unlogged_tournament_is_absent(db):
    assert db.get_tournament_results() == {}


def test_set_is_an_upsert(db):
    db.set_tournament_result("396042592", 5, 180, 0.0, "$")
    db.set_tournament_result("396042592", 3, 180, 45.0, "$")
    results = db.get_tournament_results()
    assert results["396042592"] == (3, 180, 45.0, "$")


def test_delete_removes_a_result(db):
    db.set_tournament_result("396042592", 3, 180, 45.0, "$")
    db.delete_tournament_result("396042592")
    assert db.get_tournament_results() == {}


def test_multiple_results_are_kept_independently(db):
    db.set_tournament_result("t1", 1, 100, 500.0, "$")
    db.set_tournament_result("t2", None, None, 0.0, "$")
    results = db.get_tournament_results()
    assert results == {"t1": (1, 100, 500.0, "$"), "t2": (None, None, 0.0, "$")}
