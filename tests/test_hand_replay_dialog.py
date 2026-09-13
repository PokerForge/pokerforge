"""ui/hand_replayer.py's HandReplayDialog multi-hand navigation — added so
a range-grid cell's hands (ui/range_grid.py) can all be replayed in one
sitting via Previous/Next Hand, without breaking the single-hand case
every existing caller (Sessions, By Position, hand-list double-click)
already relies on."""
import pytest

from models.hand import Hand, Player, Action
from ui.hand_replayer import HandReplayDialog


@pytest.fixture()
def qapp():
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _hand(hand_id):
    return Hand(
        hand_id=hand_id,
        players=[Player("Hero", 1, 100.0, ["A♠", "K♠"]), Player("Villain", 2, 100.0)],
        button_seat=1, actions=[Action("PREFLOP", "Hero", "Fold", None)],
        winnings={}, board=[], small_blind=0.5, big_blind=1.0,
    )


def test_single_hand_call_has_no_navigation_row(qapp):
    dlg = HandReplayDialog(_hand("h1"), "Hero")
    assert dlg.hand_nav_label is None
    assert dlg.windowTitle() == "Hand #h1"
    assert dlg.hand == dlg.hand_list[0]
    dlg.timer.stop()


def test_multi_hand_call_shows_hand_count_label(qapp):
    hands = [_hand("h1"), _hand("h2"), _hand("h3")]
    dlg = HandReplayDialog(hands[0], "Hero", hand_list=hands, start_index=0)
    assert dlg.hand_nav_label is not None
    assert dlg.hand_nav_label.text() == "Hand 1 of 3"
    assert dlg.hand_nav_prev_btn.isEnabled() is False
    assert dlg.hand_nav_next_btn.isEnabled() is True
    dlg.timer.stop()


def test_next_hand_advances_and_updates_label(qapp):
    hands = [_hand("h1"), _hand("h2"), _hand("h3")]
    dlg = HandReplayDialog(hands[0], "Hero", hand_list=hands, start_index=0)

    dlg._go_next_hand()
    assert dlg.hand_index == 1
    assert dlg.hand is hands[1]
    assert dlg.hand_nav_label.text() == "Hand 2 of 3"
    assert dlg.windowTitle() == "Hand #h2"
    assert dlg.hand_nav_prev_btn.isEnabled() is True
    assert dlg.hand_nav_next_btn.isEnabled() is True
    dlg.timer.stop()


def test_next_hand_disabled_at_the_last_hand(qapp):
    hands = [_hand("h1"), _hand("h2")]
    dlg = HandReplayDialog(hands[0], "Hero", hand_list=hands, start_index=1)
    assert dlg.hand_nav_next_btn.isEnabled() is False
    dlg._go_next_hand()  # no-op, already at the last hand
    assert dlg.hand_index == 1
    dlg.timer.stop()


def test_previous_hand_disabled_at_the_first_hand(qapp):
    hands = [_hand("h1"), _hand("h2")]
    dlg = HandReplayDialog(hands[0], "Hero", hand_list=hands, start_index=0)
    assert dlg.hand_nav_prev_btn.isEnabled() is False
    dlg._go_prev_hand()  # no-op, already at the first hand
    assert dlg.hand_index == 0
    dlg.timer.stop()


def test_previous_hand_goes_back(qapp):
    hands = [_hand("h1"), _hand("h2"), _hand("h3")]
    dlg = HandReplayDialog(hands[0], "Hero", hand_list=hands, start_index=2)
    dlg._go_prev_hand()
    assert dlg.hand_index == 1
    assert dlg.hand is hands[1]
    dlg.timer.stop()


def test_switching_hands_replaces_the_table_widget(qapp):
    hands = [_hand("h1"), _hand("h2")]
    dlg = HandReplayDialog(hands[0], "Hero", hand_list=hands, start_index=0)
    first_table = dlg.table
    dlg._go_next_hand()
    assert dlg.table is not first_table
    dlg.timer.stop()


def test_switching_hands_resets_action_step_index(qapp):
    hands = [_hand("h1"), _hand("h2")]
    dlg = HandReplayDialog(hands[0], "Hero", hand_list=hands, start_index=0)
    dlg.idx = 5  # simulate having stepped partway through the first hand
    dlg._go_next_hand()
    assert dlg.idx == -1
    dlg.timer.stop()


def test_last_button_jumps_to_hand_end_before_advancing_to_next_hand(qapp):
    # Each test hand has exactly one replay event, so idx goes -1 -> 0.
    hands = [_hand("h1"), _hand("h2")]
    dlg = HandReplayDialog(hands[0], "Hero", hand_list=hands, start_index=0)

    dlg._go_last()  # not yet at the end of h1's own actions
    assert dlg.hand_index == 0
    assert dlg.idx == 0

    dlg._go_last()  # already at the end -> advance to the next hand
    assert dlg.hand_index == 1
    assert dlg.hand is hands[1]
    dlg.timer.stop()


def test_last_button_stays_put_at_hand_end_when_no_next_hand_exists(qapp):
    dlg = HandReplayDialog(_hand("h1"), "Hero")  # single-hand call, no hand_list
    dlg._go_last()
    assert dlg.idx == 0
    dlg._go_last()  # still at the end, but there's no next hand to advance to
    assert dlg.idx == 0
    assert dlg.hand_index == 0
    dlg.timer.stop()


def test_first_button_goes_to_previous_hand_from_a_freshly_loaded_hand(qapp):
    # A freshly-loaded hand always starts at idx=-1 (its own start), so
    # pressing "first" immediately steps back a hand rather than no-op'ing.
    hands = [_hand("h1"), _hand("h2"), _hand("h3")]
    dlg = HandReplayDialog(hands[0], "Hero", hand_list=hands, start_index=2)

    dlg._go_first()
    assert dlg.hand_index == 1
    assert dlg.hand is hands[1]
    dlg.timer.stop()


def test_first_button_stays_put_at_hand_start_when_no_previous_hand_exists(qapp):
    dlg = HandReplayDialog(_hand("h1"), "Hero")  # single-hand call, no hand_list
    dlg.idx = 0
    dlg._go_first()
    assert dlg.idx == -1
    assert dlg.hand_index == 0
    dlg.timer.stop()
