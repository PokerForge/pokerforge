"""Parser correctness for core/hand_parser.py's IPokerParser — every field
downstream (stats, position, replay) depends on this being parsed right,
so a wrong regex here fails silently rather than crashing (the per-hand
try/except in parse_hand_history_file swallows it into an error count)."""
import pytest

from core.hand_parser import parse_hand_history, parse_hand_history_file, ParseError

HAND_1 = """\
GAME #1234567890: Texas Hold'em NL £0.15/£0.30 2026-09-05 20:15:00/GMT
Table UK&Ire 6-max 0.15/0.30, 1234567890
Table Info: Size: 3
Seat 1: Hero (£30.00 in chips) DEALER
Seat 2: Villain1 (£30.00 in chips)
Seat 3: Villain2 (£30.00 in chips)
Villain1: Post SB £0.15
Villain2: Post BB £0.30
*** HOLE CARDS ***
Dealt to Hero [SA HK]
Hero: Raise £0.90
Villain1: Call £0.75
Villain2: Fold
*** FLOP *** [SK D5 H2]
Villain1: Check
Hero: Bet £1.00
Villain1: Fold
Uncalled bet (£1.00) returned to Hero
*** SUMMARY ***
Total pot £2.10 Rake £0.10
Hero: wins £2.00
"""

HAND_2 = """\
GAME #1234567891: Texas Hold'em NL £0.15/£0.30 2026-09-05 20:20:00/GMT
Table UK&Ire 6-max 0.15/0.30, 1234567891
Table Info: Size: 3
Seat 1: Hero (£29.10 in chips) DEALER
Seat 2: Villain1 (£28.35 in chips)
Seat 3: Villain2 (£30.00 in chips)
Hero: Post SB £0.15
Villain2: Post BB £0.30
*** HOLE CARDS ***
Dealt to Hero [DA DK]
Villain1: Fold
Hero: Fold
*** SUMMARY ***
Total pot £0.45 Rake £0.00
Villain2: wins £0.45
"""


def test_parses_header_fields():
    hand = parse_hand_history(HAND_1)
    assert hand.hand_id == "1234567890"
    assert hand.game_type == "Texas Hold'em"
    assert hand.currency == "£"
    assert hand.small_blind == 0.15
    assert hand.big_blind == 0.30
    assert hand.played_at.isoformat() == "2026-09-05T20:15:00"


def test_parses_table_info():
    hand = parse_hand_history(HAND_1)
    assert hand.table_name == "UK&Ire 6-max 0.15/0.30"
    assert hand.table_size == 3


def test_parses_seats_and_button():
    hand = parse_hand_history(HAND_1)
    assert hand.button_seat == 1
    seats = {p.name: p.seat for p in hand.players}
    assert seats == {"Hero": 1, "Villain1": 2, "Villain2": 3}
    stacks = {p.name: p.stack for p in hand.players}
    assert stacks == {"Hero": 30.00, "Villain1": 30.00, "Villain2": 30.00}


def test_parses_hole_cards_with_suit_and_rank_translation():
    hand = parse_hand_history(HAND_1)
    hero = next(p for p in hand.players if p.name == "Hero")
    assert hero.hole_cards == ["A♠", "K♥"]


def test_parses_board_across_streets():
    hand = parse_hand_history(HAND_1)
    assert hand.board == ["K♠", "5♦", "2♥"]


def test_parses_actions_in_order_with_correct_street_tags():
    hand = parse_hand_history(HAND_1)
    actions = [(a.street, a.player, a.action, a.amount) for a in hand.actions]
    assert actions == [
        ("PREFLOP", "Villain1", "Post SB", 0.15),
        ("PREFLOP", "Villain2", "Post BB", 0.30),
        ("PREFLOP", "Hero", "Raise", 0.90),
        ("PREFLOP", "Villain1", "Call", 0.75),
        ("PREFLOP", "Villain2", "Fold", None),
        ("FLOP", "Villain1", "Check", None),
        ("FLOP", "Hero", "Bet", 1.00),
        ("FLOP", "Villain1", "Fold", None),
        ("FLOP", "Hero", "Uncalled Return", 1.00),
    ]


def test_parses_pot_rake_and_winnings():
    hand = parse_hand_history(HAND_1)
    assert hand.total_pot == 2.10
    assert hand.rake == 0.10
    assert hand.winnings == {"Hero": 2.00}


def test_hero_can_be_the_small_blind_and_fold_preflop():
    hand = parse_hand_history(HAND_2)
    actions = [(a.street, a.player, a.action, a.amount) for a in hand.actions]
    assert ("PREFLOP", "Hero", "Post SB", 0.15) in actions
    assert ("PREFLOP", "Hero", "Fold", None) in actions
    assert hand.winnings == {"Villain2": 0.45}


def test_unrecognised_text_raises_parse_error():
    with pytest.raises(ParseError):
        parse_hand_history("this is not a hand history at all")


def test_parse_hand_history_file_splits_multiple_hands():
    hands, errors = parse_hand_history_file(HAND_1 + "\n" + HAND_2)
    assert errors == []
    assert [h.hand_id for h in hands] == ["1234567890", "1234567891"]


def test_parse_hand_history_file_isolates_one_bad_hand():
    """One malformed hand must not lose every other hand in the file."""
    garbage = "GAME #999: not a real hand at all\nnonsense line\n"
    hands, errors = parse_hand_history_file(HAND_1 + "\n" + garbage + "\n" + HAND_2)
    assert [h.hand_id for h in hands] == ["1234567890", "1234567891"]
    assert len(errors) == 1
    assert errors[0][0] == "999"


HAND_MULTIPLE_WINS_SAME_PLAYER = """\
GAME #1234567892: Texas Hold'em NL £0.15/£0.30 2026-09-05 20:25:00/GMT
Table UK&Ire 6-max 0.15/0.30, 1234567892
Table Info: Size: 3
Seat 1: Hero (£30.00 in chips) DEALER
Seat 2: Villain1 (£10.00 in chips)
Seat 3: Villain2 (£30.00 in chips)
Villain1: Post SB £0.15
Villain2: Post BB £0.30
*** HOLE CARDS ***
Dealt to Hero [SA HK]
Hero: Raise £10.00
Villain1: Allin £9.85
Villain2: Call £9.70
*** SUMMARY ***
Total pot £30.00 Rake £0.50
Hero: wins £15.00
Hero: wins £14.50
"""


def test_multiple_wins_lines_for_the_same_player_are_summed_not_overwritten():
    """A player who wins BOTH the main pot and a side pot in the same hand
    (a 3-way all-in where one player is short-stacked) produces more than
    one "PlayerX: wins ..." line for that player. This must add up to
    their true total, not just keep the last one seen.

    NOTE: this locks in the existing summing behavior (winnings.get(...)
    + amt, not an overwrite) against regression, but the exact wording
    iPoker actually uses for a real side-pot summary hasn't been
    confirmed against a real export with an actual side pot — same
    "never guess, always validate" caveat this project applies elsewhere
    (see core/folder_detect.py). If a real side-pot export ever surfaces,
    it should be checked against this assumption."""
    hand = parse_hand_history(HAND_MULTIPLE_WINS_SAME_PLAYER)
    assert hand.winnings["Hero"] == pytest.approx(29.50)
