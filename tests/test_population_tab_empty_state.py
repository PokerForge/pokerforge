"""ui/population_tab.py's empty-state message — a hand count > 0 with
zero villains almost always means every hand is from a source that
anonymizes opponents (GGPoker), which otherwise reads as a silently
broken tab rather than expected, by-design behavior."""
import pytest

from ui.population_tab import PopulationTab


@pytest.fixture()
def qapp():
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _synchronous_run_async(monkeypatch):
    import ui.async_worker as worker_mod

    def _sync_run_async(self, fn, on_done, on_error=None, key="default"):
        try:
            result = fn()
        except Exception as exc:
            if on_error:
                on_error(str(exc))
            return
        on_done(result)

    monkeypatch.setattr(worker_mod.AsyncRunner, "run_async", _sync_run_async)


@pytest.fixture()
def db(tmp_path):
    from database.repository import PokerDatabase
    database = PokerDatabase(tmp_path / "test.db")
    yield database
    database.close()


@pytest.fixture()
def tab(qapp, db):
    return PopulationTab("Hero", db, "$")


def _ggpoker_hand(hand_id):
    from datetime import datetime
    from models.hand import Hand, Player, Action
    return Hand(
        hand_id=hand_id, source="ggpoker", played_at=datetime(2020, 1, 1),
        players=[Player("Hero", 1, 2.0), Player("aaa11111", 2, 2.0)],
        actions=[Action("PREFLOP", "Hero", "Post SB", 0.01),
                 Action("PREFLOP", "aaa11111", "Post BB", 0.02),
                 Action("PREFLOP", "Hero", "Fold", None)],
    )


def _pokerstars_hand(hand_id):
    from datetime import datetime
    from models.hand import Hand, Player, Action
    return Hand(
        hand_id=hand_id, source="pokerstars", played_at=datetime(2020, 1, 1),
        players=[Player("Hero", 1, 2.0), Player("Villain1", 2, 2.0)],
        actions=[Action("PREFLOP", "Hero", "Post SB", 0.01),
                 Action("PREFLOP", "Villain1", "Post BB", 0.02),
                 Action("PREFLOP", "Hero", "Fold", None)],
    )


def test_no_hands_at_all_keeps_the_label_hidden(tab):
    from datetime import date
    tab.refresh(date(2000, 1, 1), date.today())
    assert tab.empty_state_lbl.isHidden()


def test_ggpoker_only_hands_show_the_anonymization_explanation(tab, db):
    from datetime import date
    db.import_hands([_ggpoker_hand("RC1"), _ggpoker_hand("RC2")], ev_iterations=1)

    tab.refresh(date(2000, 1, 1), date.today())

    assert tab.rows == {}
    assert not tab.empty_state_lbl.isHidden()
    assert "GGPoker" in tab.empty_state_lbl.text()


def test_non_ggpoker_hands_with_real_villains_show_no_message(tab, db):
    from datetime import date
    db.import_hands([_pokerstars_hand("PS1")], ev_iterations=1)

    tab.refresh(date(2000, 1, 1), date.today())

    assert "Villain1" in tab.rows
    assert tab.empty_state_lbl.isHidden()


def test_mixed_non_ggpoker_sources_with_no_villains_show_the_generic_message(tab):
    """Direct unit check of the branching logic itself (not worth
    constructing a real DB scenario for the rare "hands exist but every
    single opponent got excluded some other way" case)."""
    tab._on_empty_state_sources({"pokerstars": 5, "ipoker": 3})
    assert not tab.empty_state_lbl.isHidden()
    assert "GGPoker" not in tab.empty_state_lbl.text()


def test_period_filter_matching_zero_hands_shows_the_zero_filter_message(tab, db):
    """Distinct from the totally-empty-database case: the account has
    hands, but the active Period narrows them all out — a bare table with
    no explanation would look broken rather than just over-filtered."""
    from datetime import date
    db.import_hands([_pokerstars_hand("PS1")], ev_iterations=1)

    tab.refresh(date(2099, 1, 1), date(2099, 12, 31))

    assert tab.rows == {}
    assert not tab.empty_state_lbl.isHidden()
    text = tab.empty_state_lbl.text()
    assert "filter" in text.lower()
    assert "GGPoker" not in text


def test_stake_filter_matching_zero_hands_shows_the_zero_filter_message(tab, db):
    from datetime import date
    db.import_hands([_pokerstars_hand("PS1")], ev_iterations=1)

    tab.refresh(date(2000, 1, 1), date.today(), stake="$100/$200")

    assert tab.rows == {}
    assert not tab.empty_state_lbl.isHidden()
    assert "filter" in tab.empty_state_lbl.text().lower()
