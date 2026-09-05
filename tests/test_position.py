"""Regression coverage for core/position.py — this logic already shipped
one real bug (4-handed CO mislabeled as UTG, caught by cross-checking a
PT4 export and fixed by backfilling ~35,600 DB rows). These cases pin down
every table size against the labeling PT4 was confirmed to use, so that
bug class can't come back silently."""
from models.hand import Hand, Player
from core.position import assign_positions, has_position_on


def _hand(button_seat, seats, names=None):
    names = names or [f"P{s}" for s in seats]
    return Hand(
        hand_id="1",
        button_seat=button_seat,
        players=[Player(name=n, seat=s) for n, s in zip(names, seats)],
    )


def test_heads_up_labels_are_btn_sb_and_bb():
    hand = _hand(button_seat=1, seats=[1, 6], names=["Hero", "Villain"])
    positions = assign_positions(hand)
    assert positions == {"Hero": "BTN/SB", "Villain": "BB"}


def test_three_handed_labels():
    hand = _hand(button_seat=1, seats=[1, 3, 5], names=["Hero", "V1", "V2"])
    assert assign_positions(hand) == {"Hero": "BTN", "V1": "SB", "V2": "BB"}


def test_four_handed_seat_after_bb_is_co_not_utg():
    """The specific bug: at 4-handed, the seat after BB is CO (confirmed
    against a real PT4 export), never UTG."""
    hand = _hand(button_seat=1, seats=[1, 3, 5, 6], names=["Hero", "SB", "BB", "Last"])
    positions = assign_positions(hand)
    assert positions["Last"] == "CO"
    assert "UTG" not in positions.values()


def test_five_handed_labels():
    # seats (sorted): [1,3,5,6,8], button=5 -> clockwise from button:
    # 5,6,8,1,3 zipped with [BTN,SB,BB,UTG,CO].
    hand = _hand(button_seat=5, seats=[1, 3, 5, 6, 8], names=["UTG", "CO", "BTN", "SB", "BB"])
    positions = assign_positions(hand)
    assert positions == {"BTN": "BTN", "SB": "SB", "BB": "BB", "UTG": "UTG", "CO": "CO"}


def test_six_handed_labels_wrap_around_seat_order():
    # Grosvenor's fixed 6-max seat set, per core/position.py's docstring.
    hand = _hand(button_seat=5, seats=[1, 3, 5, 6, 8, 10],
                 names=["MP", "CO", "BTN", "SB", "BB", "UTG"])
    positions = assign_positions(hand)
    assert positions == {
        "BTN": "BTN", "SB": "SB", "BB": "BB", "UTG": "UTG", "MP": "MP", "CO": "CO",
    }


def test_returns_empty_when_button_seat_missing():
    hand = _hand(button_seat=None, seats=[1, 3, 5])
    assert assign_positions(hand) == {}


def test_returns_empty_when_button_seat_not_active():
    # e.g. the button seat's occupant sat out this hand.
    hand = _hand(button_seat=99, seats=[1, 3, 5])
    assert assign_positions(hand) == {}


def test_returns_empty_for_unsupported_player_count():
    hand = _hand(button_seat=1, seats=[1, 2, 3, 4, 5, 6, 7])
    assert assign_positions(hand) == {}


def test_has_position_on_button_is_in_position_on_everyone():
    positions = {"BTN": "BTN", "SB": "SB", "BB": "BB", "UTG": "UTG", "MP": "MP", "CO": "CO"}
    for other in ("SB", "BB", "UTG", "MP", "CO"):
        assert has_position_on(positions, "BTN", other) is True
        assert has_position_on(positions, other, "BTN") is False


def test_has_position_on_sb_acts_before_bb_postflop():
    positions = {"SB": "SB", "BB": "BB"}
    assert has_position_on(positions, "SB", "BB") is False
    assert has_position_on(positions, "BB", "SB") is True


def test_has_position_on_heads_up_button_acts_last_postflop():
    """BTN/SB acts FIRST preflop but LAST postflop — the reverse of every
    other position's button-relative order, called out explicitly in
    core/position.py's _POSTFLOP_ORDER comment."""
    positions = {"BTN/SB": "BTN/SB", "BB": "BB"}
    assert has_position_on(positions, "BTN/SB", "BB") is True
    assert has_position_on(positions, "BB", "BTN/SB") is False


def test_has_position_on_unknown_player_returns_false():
    positions = {"BTN": "BTN"}
    assert has_position_on(positions, "BTN", "Ghost") is False
    assert has_position_on(positions, "Ghost", "BTN") is False
