"""core/river_sizing.py — population-wide river bet-sizing vs revealed
hand strength. Hand-crafted Hand/Player/Action objects (no database
needed — the DB-side hand_id pre-filter is covered separately in
tests/test_queries.py)."""
from models.hand import Hand, Player, Action
from core.river_sizing import classify_river_sizing_vs_strength, _river_bet_and_pot_before, _sizing_bucket


def _showdown_hand(hand_id, river_bettor, river_bet_amount, pot_before_river,
                    bettor_cards, board):
    """Builds a hand with: preflop action that puts `pot_before_river`
    in the middle, then a single river bet of `river_bet_amount` by
    `river_bettor`."""
    actions = [
        Action("PREFLOP", "Hero", "Post BB", pot_before_river),
        Action("RIVER", river_bettor, "Bet", river_bet_amount),
    ]
    return Hand(
        hand_id=hand_id,
        players=[Player("Hero", 1, 100.0, []), Player(river_bettor, 2, 100.0, bettor_cards)],
        actions=actions, board=board, big_blind=1.0,
    )


def test_river_bet_and_pot_before_finds_the_right_bet_and_pot():
    hand = _showdown_hand("h1", "Villain", 10.0, 20.0, ["A♠", "A♦"], ["K♣", "Q♦", "J♥", "2♠", "3♣"])
    result = _river_bet_and_pot_before(hand)
    assert result == ("Villain", 10.0, 20.0)


def test_no_river_bet_returns_none():
    hand = Hand(
        hand_id="h1", players=[Player("Hero", 1, 100.0, [])],
        actions=[Action("PREFLOP", "Hero", "Post BB", 1.0), Action("RIVER", "Hero", "Check", None)],
        board=[], big_blind=1.0,
    )
    assert _river_bet_and_pot_before(hand) is None


def test_sizing_bucket_boundaries():
    assert _sizing_bucket(33.0, 100.0) == "33-50% pot"
    assert _sizing_bucket(50.0, 100.0) == "50-100% pot"
    assert _sizing_bucket(49.9, 100.0) == "33-50% pot"
    assert _sizing_bucket(100.0, 100.0) == "100%+ pot (overbet)"
    assert _sizing_bucket(20.0, 100.0) is None  # below the smallest bucket
    assert _sizing_bucket(10.0, 0.0) is None  # no pot to divide by


def test_classifies_a_strong_hand_correctly():
    # Trips or better -> "strong". Board KQJ23, hole AA -> no trips, just
    # a pair of aces -> "weak" by this threshold; use a real trips hand
    # instead: hole AK, board AAQ23 -> trip aces.
    hand = _showdown_hand("h1", "Villain", 66.0, 100.0, ["A♠", "K♦"],
                           ["A♥", "A♣", "Q♦", "2♠", "3♣"])
    result = classify_river_sizing_vs_strength([hand])
    assert result["50-100% pot"] == {"strong": 1, "weak": 0}


def test_classifies_a_weak_hand_correctly():
    hand = _showdown_hand("h1", "Villain", 66.0, 100.0, ["7♠", "2♦"],
                           ["A♥", "K♣", "Q♦", "J♠", "3♣"])  # ace-high, nothing
    result = classify_river_sizing_vs_strength([hand])
    assert result["50-100% pot"] == {"strong": 0, "weak": 1}


def test_excludes_the_named_player():
    hand = _showdown_hand("h1", "Hero", 66.0, 100.0, ["A♠", "A♦"], ["K♣", "Q♦", "J♥", "2♠", "3♣"])
    result = classify_river_sizing_vs_strength([hand], exclude_player="Hero")
    assert result == {label: {"strong": 0, "weak": 0} for label in
                       ("33-50% pot", "50-100% pot", "100%+ pot (overbet)")}


def test_skips_hands_where_hole_cards_were_never_revealed():
    hand = _showdown_hand("h1", "Villain", 66.0, 100.0, [], ["K♣", "Q♦", "J♥", "2♠", "3♣"])
    result = classify_river_sizing_vs_strength([hand])
    assert all(v == {"strong": 0, "weak": 0} for v in result.values())


def test_pools_across_multiple_hands_in_the_same_bucket():
    hands = [
        _showdown_hand("h1", "Villain", 66.0, 100.0, ["A♠", "A♦"], ["K♣", "Q♦", "J♥", "A♣", "3♣"]),  # trips -> strong
        _showdown_hand("h2", "Villain", 70.0, 100.0, ["7♠", "2♦"], ["A♥", "K♣", "Q♦", "J♠", "3♣"]),  # air -> weak
    ]
    result = classify_river_sizing_vs_strength(hands)
    assert result["50-100% pot"] == {"strong": 1, "weak": 1}
