"""ui/hand_replayer.py's _build_events — the pure data-transformation step
that turns a Hand's actions into the deltas the replay dialog sums for
its running pot/stack display. A Raise's Action.amount is the ABSOLUTE
new total for that street, while Call/Bet/Allin/Post amounts are direct
contributions — mixing these up would show a wrong pot size or wrong
remaining stack throughout an entire replayed hand, all-in or not.

Note: hand.winnings is already a {player: total} dict by the time it
reaches here (see core/hand_parser.py / core/xml_hand_parser.py, both of
which sum multiple "wins" lines into one total per player), so there is
exactly one 'win' event per player in _build_events's output — the
"summed across multiple pots" case is validated at the parser level
(tests/test_hand_parser.py), not achievable here by construction."""
import pytest

from models.hand import Hand, Player, Action
from ui.hand_replayer import _build_events


def _hand(actions, winnings=None, board=None):
    return Hand(
        hand_id="1", players=[Player("Hero", 1, 100.0), Player("Villain", 2, 100.0)],
        actions=actions, winnings=winnings or {}, board=board or [],
        big_blind=1.0,
    )


def test_raise_amount_is_treated_as_new_total_not_a_delta():
    """A Raise to 10 after already having 2 committed this street must
    contribute a delta of 8, not 10 — otherwise every raised pot would be
    overstated by whatever was already in front of the raiser."""
    hand = _hand([
        Action("PREFLOP", "Hero", "Bet", 2.0),
        Action("PREFLOP", "Hero", "Raise", 10.0),  # raises TO 10 total, not BY 10
    ])
    events = _build_events(hand)
    action_events = [e for e in events if e['kind'] == 'action']
    assert action_events[0]['delta'] == 2.0
    assert action_events[1]['delta'] == 8.0


def test_allin_amount_is_a_direct_delta_not_a_new_total():
    """Unlike Raise, an Allin's amount is what actually moved — a
    short-stacked player going all-in for their remaining 19.5 after
    already committing 0.5 (the SB) must show a delta of 19.5, not treat
    19.5 as some "new total" needing further arithmetic against the SB."""
    hand = _hand([
        Action("PREFLOP", "Villain", "Post SB", 0.5),
        Action("PREFLOP", "Villain", "Allin", 19.5),
    ])
    events = _build_events(hand)
    action_events = [e for e in events if e['kind'] == 'action']
    assert action_events[0]['delta'] == 0.5
    assert action_events[1]['delta'] == 19.5


def test_uncalled_return_is_a_negative_delta():
    """An uncalled bet returned to the raiser must SHRINK the pot (and
    restore their stack) — a positive or zero delta here would leave
    chips that were never actually contested still counted in the pot."""
    hand = _hand([
        Action("PREFLOP", "Hero", "Bet", 5.0),
        Action("PREFLOP", "Hero", "Uncalled Return", 5.0),
    ])
    events = _build_events(hand)
    uncalled = [e for e in events if e['kind'] == 'uncalled']
    assert len(uncalled) == 1
    assert uncalled[0]['delta'] == -5.0


def test_three_way_allin_pot_total_matches_sum_of_all_contributions():
    """A 3-way all-in (the shape a side pot forms from) must still sum to
    the right total pot — the replayer displays one running total rather
    than separate main/side pots, but that total must be exactly right,
    since core/settlement.py's own docstring already discloses that
    per-VILLAIN attribution (not the total) is where side-pot nuance is
    approximated, not the total itself."""
    hand = _hand([
        Action("PREFLOP", "Villain", "Post SB", 0.5),
        Action("PREFLOP", "Hero", "Post BB", 1.0),
        Action("PREFLOP", "Hero", "Raise", 100.0),
        Action("PREFLOP", "Villain", "Allin", 19.5),
    ], winnings={"Hero": 21.0})
    events = _build_events(hand)
    total_delta = sum(e['delta'] for e in events if e['kind'] in ('action', 'uncalled'))
    assert total_delta == pytest.approx(0.5 + 100.0 + 19.5)


def test_multiple_actions_reset_committed_at_each_new_street():
    """A player who bets 5 on the flop then bets 5 again on the turn must
    show a delta of 5 both times, not have the turn bet computed against
    a stale "already committed 5" from the flop."""
    hand = _hand([
        Action("FLOP", "Hero", "Bet", 5.0),
        Action("TURN", "Hero", "Bet", 5.0),
    ], board=["A♠", "K♦", "2♥", "3♣"])
    events = _build_events(hand)
    action_events = [e for e in events if e['kind'] == 'action']
    assert [e['delta'] for e in action_events] == [5.0, 5.0]


def test_win_event_amount_matches_hand_winnings_total():
    hand = _hand([Action("PREFLOP", "Hero", "Post BB", 1.0)], winnings={"Hero": 29.5})
    events = _build_events(hand)
    win_events = [e for e in events if e['kind'] == 'win']
    assert len(win_events) == 1
    assert win_events[0]['player'] == "Hero"
    assert win_events[0]['amount'] == 29.5
