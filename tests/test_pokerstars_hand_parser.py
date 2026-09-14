"""Parser correctness for core/pokerstars_hand_parser.py's PokerStarsParser.
Sample hands below mirror shapes confirmed against a real 594-file,
286,554-hand export (usernames changed to short stand-ins for
readability; PokerStars keeps real, persistent usernames unlike
GGPoker's per-hand hex labels, but the specific real names in this
export aren't needed to test the parser's regex logic)."""
import pytest

from core.pokerstars_hand_parser import (
    parse_pokerstars_hand_history, parse_pokerstars_hand_history_file, PokerStarsParseError,
)

# Header shape confirmed real (embedded in this test file already before
# tournament support existed); the action body is hand-built to match the
# same grammar the cash fixtures above use (no real full tournament hand
# body was available to verify against — see ROADMAP.md's tournament-
# support notes), just with chip-denominated (no currency symbol) amounts
# throughout, matching a real tournament export's convention.
HAND_TOURNAMENT = """\
PokerStars Hand #251483293914: Tournament #3456789012, $10+$1 USD Hold'em No Limit - Level V (100/200) - 2024/07/14 13:16:42 WET [2024/07/14 8:16:42 ET]
Table '3456789012 1' 9-max Seat #3 is the button
Seat 1: aaa11111 (15000 in chips)
Seat 2: bbb22222 (14200 in chips)
Seat 3: Hero (16000 in chips)
aaa11111: posts small blind 100
bbb22222: posts big blind 200
*** HOLE CARDS ***
Dealt to Hero [Ah Kd]
Hero: raises 400 to 600
aaa11111: folds
bbb22222: calls 400
*** FLOP *** [2c 7d Kc]
bbb22222: checks
Hero: bets 800
bbb22222: folds
Uncalled bet (800) returned to Hero
Hero collected 1300 from pot
*** SUMMARY ***
Total pot 1300 | Rake 0
Board [2c 7d Kc]
Seat 1: aaa11111 (small blind) folded before Flop
Seat 2: bbb22222 (big blind) folded on the Flop
Seat 3: Hero (button) collected (1300)
"""

HAND_WALK_ZOOM = """\
PokerStars Zoom Hand #1000000001:  Hold'em No Limit ($0.05/$0.10) - 2024/07/14 13:16:42 WET [2024/07/14 8:16:42 ET]
Table 'Aludra' 6-max Seat #1 is the button
Seat 1: aaa11111 ($10.72 in chips)
Seat 2: bbb22222 ($10.86 in chips)
Seat 3: Hero ($10 in chips)
Seat 4: ccc33333 ($32.43 in chips)
Seat 5: ddd44444 ($20.67 in chips)
Seat 6: eee55555 ($24.62 in chips)
bbb22222: posts small blind $0.05
Hero: posts big blind $0.10
*** HOLE CARDS ***
Dealt to Hero [Qs 3c]
ccc33333: raises $0.15 to $0.25
ddd44444: raises $0.55 to $0.80
eee55555: folds
aaa11111: folds
bbb22222: folds
Hero: folds
ccc33333: folds
Uncalled bet ($0.55) returned to ddd44444
ddd44444 collected $0.65 from pot
ddd44444: doesn't show hand
*** SUMMARY ***
Total pot $0.65 | Rake $0
Seat 1: aaa11111 (button) folded before Flop (didn't bet)
Seat 2: bbb22222 (small blind) folded before Flop
Seat 3: Hero (big blind) folded before Flop
Seat 4: ccc33333 folded before Flop
Seat 5: ddd44444 collected ($0.65)
Seat 6: eee55555 folded before Flop (didn't bet)
"""

HAND_RING_USD_SHOWDOWN = """\
PokerStars Hand #1000000002:  Hold'em No Limit ($0.01/$0.02 USD) - 2015/04/12 12:39:51 WET [2015/04/12 7:39:51 ET]
Table 'Aludra' 6-max Seat #1 is the button
Seat 1: aaa11111 ($19.20 in chips)
Seat 2: Hero ($10 in chips)
Seat 3: bbb22222 ($11.17 in chips)
Seat 4: ccc33333 ($9.85 in chips)
Seat 5: ddd44444 ($10.10 in chips)
Seat 6: eee55555 ($12.83 in chips)
Hero: posts small blind $0.01
bbb22222: posts big blind $0.02
*** HOLE CARDS ***
Dealt to Hero [5c Jh]
ccc33333: folds
ddd44444: folds
eee55555: raises $0.10 to $0.12
aaa11111: folds
Hero: folds
bbb22222: calls $0.10
*** FLOP *** [Kd Js 9h]
bbb22222: checks
eee55555: bets $0.16
bbb22222: calls $0.16
*** TURN *** [Kd Js 9h] [6d]
bbb22222: checks
eee55555: checks
*** RIVER *** [Kd Js 9h 6d] [Qs]
bbb22222: checks
eee55555: bets $1
bbb22222: calls $1
*** SHOW DOWN ***
eee55555: shows [Td As] (a straight, Ten to Ace)
bbb22222: mucks hand
eee55555 collected $2.68 from pot
*** SUMMARY ***
Total pot $2.81 | Rake $0.13
Board [Kd Js 9h 6d Qs]
Seat 1: aaa11111 (button) folded before Flop (didn't bet)
Seat 2: Hero (small blind) folded before Flop
Seat 3: bbb22222 (big blind) mucked [6h Qh]
Seat 4: ccc33333 folded before Flop (didn't bet)
Seat 5: ddd44444 folded before Flop (didn't bet)
Seat 6: eee55555 showed [Td As] and won ($2.68) with a straight, Ten to Ace
"""

HAND_RUN_TWICE_SIDE_POT = """\
PokerStars Zoom Hand #1000000003:  Hold'em No Limit ($0.05/$0.10) - 2024/07/14 13:17:00 WET [2024/07/14 8:17:00 ET]
Table 'Aludra' 6-max Seat #1 is the button
Seat 1: Hero ($10 in chips)
Seat 2: aaa11111 ($15 in chips)
Seat 3: bbb22222 ($8 in chips)
Seat 4: ccc33333 ($20 in chips)
Seat 5: ddd44444 ($9 in chips)
Seat 6: eee55555 ($14 in chips)
aaa11111: posts small blind $0.05
bbb22222: posts big blind $0.10
*** HOLE CARDS ***
Dealt to Hero [Kc Ad]
ccc33333: folds
ddd44444: folds
eee55555: folds
Hero: raises $0.15 to $0.25
aaa11111: folds
bbb22222: raises $0.75 to $1
Hero: raises $16.84 to $17.84 and is all-in
bbb22222: calls $8.55 and is all-in
Uncalled bet ($8.29) returned to Hero
*** FIRST FLOP *** [7c 7h 4h]
*** FIRST TURN *** [7c 7h 4h] [7s]
*** FIRST RIVER *** [7c 7h 4h 7s] [5h]
*** SECOND FLOP *** [3s As 4s]
*** SECOND TURN *** [3s As 4s] [6s]
*** SECOND RIVER *** [3s As 4s 6s] [6h]
*** FIRST SHOW DOWN ***
Hero: shows [Kc Ad] (three of a kind, Sevens)
bbb22222: shows [Qh Qd] (a full house, Sevens full of Queens)
bbb22222 collected $5 from main pot
*** SECOND SHOW DOWN ***
Hero: shows [Kc Ad] (two pair, Aces and Sixes)
bbb22222: shows [Qh Qd] (two pair, Queens and Sixes)
Hero collected $4.99 from main pot
*** SUMMARY ***
Total pot $9.99 Main pot $9.99. Side pot $0.00. | Rake $0.01
Hand was run twice
FIRST Board [7c 7h 4h 7s 5h]
SECOND Board [3s As 4s 6s 6h]
Seat 1: Hero showed [Kc Ad] and won ($4.99)
Seat 2: aaa11111 (small blind) folded before Flop
Seat 3: bbb22222 (big blind) showed [Qh Qd] and won ($5) with a full house
Seat 4: ccc33333 folded before Flop (didn't bet)
Seat 5: ddd44444 folded before Flop (didn't bet)
Seat 6: eee55555 folded before Flop (didn't bet)
"""

HAND_CASH_OUT = """\
PokerStars Zoom Hand #1000000004:  Hold'em No Limit ($0.05/$0.10) - 2024/07/14 13:18:00 WET [2024/07/14 8:18:00 ET]
Table 'Aludra' 6-max Seat #1 is the button
Seat 1: Hero ($10 in chips)
Seat 2: aaa11111 ($10 in chips)
Seat 3: bbb22222 ($30 in chips)
Seat 4: ccc33333 ($10 in chips)
Seat 5: ddd44444 ($10 in chips)
Seat 6: eee55555 ($10 in chips)
aaa11111: posts small blind $0.05
bbb22222: posts big blind $0.10
*** HOLE CARDS ***
Dealt to Hero [Tc Ac]
ccc33333: folds
ddd44444: folds
eee55555: folds
Hero: raises $0.15 to $0.25
aaa11111: raises $0.40 to $0.65
bbb22222: calls $0.55
Hero: calls $0.40
*** FLOP *** [6d Kc 3c]
aaa11111: bets $1
bbb22222: raises $2 to $3
Hero: calls $3
aaa11111: calls $2
*** TURN *** [6d Kc 3c] [9h]
*** RIVER *** [6d Kc 3c 9h] [2s]
*** SHOW DOWN ***
aaa11111: shows [6c Jc] (a pair of Sixes)
Hero: shows [Tc Ac] (high card Ace)
bbb22222: shows [Kd 7d] (a pair of Kings)
bbb22222 collected $19.92 from main pot
aaa11111 cashed out the hand for $6.89 | Cash Out Fee $0.14
*** SUMMARY ***
Total pot $29.74 Main pot $19.92. Side pot $8.48. | Rake $1.34
Board [6d Kc 3c 9h 2s]
Seat 1: Hero showed [Tc Ac] and lost with high card Ace
Seat 2: aaa11111 showed [6c Jc] and won ($8.48) with a pair of Sixes (pot not awarded as player cashed out)
Seat 3: bbb22222 (big blind) showed [Kd 7d] and won ($19.92) with a pair of Kings
Seat 4: ccc33333 folded before Flop (didn't bet)
Seat 5: ddd44444 folded before Flop (didn't bet)
Seat 6: eee55555 folded before Flop (didn't bet)
"""


def test_parses_zoom_header_with_no_currency_code():
    hand = parse_pokerstars_hand_history(HAND_WALK_ZOOM)
    assert hand.hand_id == "1000000001"
    assert hand.game_type == "Texas Hold'em"
    assert hand.currency == "$"
    assert hand.small_blind == 0.05
    assert hand.big_blind == 0.10
    assert hand.played_at.isoformat() == "2024-07-14T13:16:42"
    assert hand.source == "pokerstars"


def test_actual_posted_blind_amount_overrides_a_corrupted_header_stake():
    """No mismatch found in a real PokerStars sample, but
    core.ggpoker_hand_parser's near-identical format DID have real,
    confirmed cases of a corrupted header stakes field -- applying the
    same defense here too, since a posted-blind action amount is real
    money moving and can't be wrong the way a text field occasionally is."""
    corrupted = HAND_WALK_ZOOM.replace(
        "PokerStars Zoom Hand #1000000001:  Hold'em No Limit ($0.05/$0.10)",
        "PokerStars Zoom Hand #1000000001:  Hold'em No Limit ($9.11/$0.10)")
    hand = parse_pokerstars_hand_history(corrupted)
    assert hand.small_blind == 0.05  # from "bbb22222: posts small blind $0.05", not the header
    assert hand.big_blind == 0.10


def test_parses_ring_header_with_a_currency_code_suffix():
    hand = parse_pokerstars_hand_history(HAND_RING_USD_SHOWDOWN)
    assert hand.hand_id == "1000000002"
    assert hand.currency == "$"
    assert hand.small_blind == 0.01
    assert hand.big_blind == 0.02


def test_walk_with_no_showdown_marker_still_captures_winnings():
    """PokerStars has no marker at all before "collected from pot" on an
    uncontested pot -- unlike GGPoker's "*** SHOWDOWN ***", which appears
    even for a walk."""
    hand = parse_pokerstars_hand_history(HAND_WALK_ZOOM)
    assert hand.winnings == {"ddd44444": 0.65}
    assert hand.unmatched_lines == []


def test_table_seats_and_button():
    hand = parse_pokerstars_hand_history(HAND_WALK_ZOOM)
    assert hand.table_name == "Aludra"
    assert hand.table_size == 6
    assert hand.button_seat == 1
    hero = next(p for p in hand.players if p.name == "Hero")
    assert hero.seat == 3
    assert hero.stack == 10.0


def test_dealt_only_appears_for_hero_others_get_no_line():
    hand = parse_pokerstars_hand_history(HAND_WALK_ZOOM)
    hero = next(p for p in hand.players if p.name == "Hero")
    villain = next(p for p in hand.players if p.name == "aaa11111")
    assert hero.hole_cards == ["Q♠", "3♣"]
    assert villain.hole_cards == []


def test_raise_amount_is_the_new_total_not_the_increment():
    hand = parse_pokerstars_hand_history(HAND_RING_USD_SHOWDOWN)
    raise_action = next(a for a in hand.actions if a.player == "eee55555" and a.street == "PREFLOP")
    assert raise_action.action == "Raise"
    assert raise_action.amount == 0.12


def test_board_built_incrementally_across_streets():
    hand = parse_pokerstars_hand_history(HAND_RING_USD_SHOWDOWN)
    assert hand.board == ["K♦", "J♠", "9♥", "6♦", "Q♠"]


def test_shows_and_mucks_hand_at_showdown():
    hand = parse_pokerstars_hand_history(HAND_RING_USD_SHOWDOWN)
    winner = next(p for p in hand.players if p.name == "eee55555")
    muck = next(p for p in hand.players if p.name == "bbb22222")
    assert winner.hole_cards == ["T♦", "A♠"]
    assert muck.hole_cards == []  # "mucks hand" never reveals cards mid-action
    assert hand.winnings == {"eee55555": 2.68}


def test_all_in_raise_is_recorded_as_a_plain_raise():
    hand = parse_pokerstars_hand_history(HAND_RUN_TWICE_SIDE_POT)
    shove = next(a for a in hand.actions
                 if a.player == "Hero" and a.street == "PREFLOP" and a.action == "Raise" and a.amount == 17.84)
    assert shove is not None


def test_run_it_twice_sums_winnings_from_both_boards_and_keeps_only_the_first_board():
    hand = parse_pokerstars_hand_history(HAND_RUN_TWICE_SIDE_POT)
    assert hand.winnings == {"bbb22222": pytest.approx(5.0), "Hero": pytest.approx(4.99)}
    assert hand.board == ["7♣", "7♥", "4♥", "7♠", "5♥"]
    assert hand.unmatched_lines == []


def test_collected_from_main_pot_is_recognised():
    hand = parse_pokerstars_hand_history(HAND_CASH_OUT)
    assert hand.winnings["bbb22222"] == pytest.approx(19.92)


def test_cashed_out_is_added_to_winnings_with_no_matching_collected_line():
    """Traced against a real hand: the cashed-out player's rightful side
    pot share is explicitly NOT awarded to them ("pot not awarded as
    player cashed out") -- their real money is the cashed-out amount,
    which has no "collected from pot" line of its own."""
    hand = parse_pokerstars_hand_history(HAND_CASH_OUT)
    assert hand.winnings == {"bbb22222": pytest.approx(19.92), "aaa11111": pytest.approx(6.89)}
    assert hand.unmatched_lines == []


def test_sitting_out_seat_line_is_recognised_and_excluded_from_players():
    text = HAND_WALK_ZOOM.replace(
        "Seat 6: eee55555 ($24.62 in chips)",
        "Seat 6: eee55555 ($0 in chips) is sitting out")
    hand = parse_pokerstars_hand_history(text)
    assert "eee55555" not in [p.name for p in hand.players]
    assert hand.unmatched_lines == []


def test_table_events_are_recognised_and_ignored():
    text = HAND_WALK_ZOOM.replace(
        "ccc33333: raises $0.15 to $0.25",
        "somebody joins the table at seat #2\n"
        "somebody is disconnected\n"
        "somebody has timed out while disconnected\n"
        "somebody: sits out\n"
        "ccc33333: raises $0.15 to $0.25")
    hand = parse_pokerstars_hand_history(text)
    assert hand.unmatched_lines == []


def test_fold_with_revealed_cards_populates_hole_cards():
    text = HAND_WALK_ZOOM.replace("aaa11111: folds", "aaa11111: folds [Th 9h]")
    hand = parse_pokerstars_hand_history(text)
    villain = next(p for p in hand.players if p.name == "aaa11111")
    assert villain.hole_cards == ["T♥", "9♥"]
    fold_action = next(a for a in hand.actions if a.player == "aaa11111" and a.action == "Fold")
    assert fold_action.amount is None


def test_fold_with_a_single_revealed_card():
    text = HAND_WALK_ZOOM.replace("aaa11111: folds", "aaa11111: folds [Th]")
    hand = parse_pokerstars_hand_history(text)
    villain = next(p for p in hand.players if p.name == "aaa11111")
    assert villain.hole_cards == []  # only one card known is not stored, same as elsewhere in the app
    assert hand.unmatched_lines == []


def test_unrecognised_text_raises_parse_error():
    with pytest.raises(PokerStarsParseError):
        parse_pokerstars_hand_history("this is not a hand history at all")


def test_tournament_hand_is_parsed_and_flagged_as_a_tournament():
    """A tournament header's blind-level segment ("(100/200)") has no
    currency symbol, so it can never satisfy HEADER's cash-stakes group
    -- that mutual exclusivity is exactly what makes TOURNAMENT_HEADER
    reliable to fall back to. session_type/tournament_id/buy_in/fee let
    every downstream cash aggregate (bb100, profit) exclude these hands
    rather than silently summing chip counts as dollars."""
    hand = parse_pokerstars_hand_history(HAND_TOURNAMENT)
    assert hand.session_type == 'tournament'
    assert hand.tournament_id == '3456789012'
    assert hand.buy_in == 10.0
    assert hand.fee == 1.0
    assert hand.small_blind == 100.0 and hand.big_blind == 200.0
    assert hand.winnings == {'Hero': 1300.0}
    assert hand.unmatched_lines == []


def test_tournament_hand_with_no_stated_fee_defaults_fee_to_zero():
    freezeout = HAND_TOURNAMENT.replace("$10+$1 USD", "$10 USD")
    hand = parse_pokerstars_hand_history(freezeout)
    assert hand.session_type == 'tournament'
    assert hand.buy_in == 10.0
    assert hand.fee == 0.0


def test_cash_hand_is_not_flagged_as_a_tournament():
    hand = parse_pokerstars_hand_history(HAND_WALK_ZOOM)
    assert hand.session_type == 'cash'
    assert hand.tournament_id is None
    assert hand.buy_in is None
    assert hand.fee is None


def test_parse_hand_history_file_splits_multiple_hands():
    hands, errors = parse_pokerstars_hand_history_file(HAND_WALK_ZOOM + "\n" + HAND_RING_USD_SHOWDOWN)
    assert errors == []
    assert [h.hand_id for h in hands] == ["1000000001", "1000000002"]


def test_parse_hand_history_file_isolates_one_bad_hand():
    garbage = "PokerStars Hand #BAD: not a real hand at all\nnonsense line\n"
    hands, errors = parse_pokerstars_hand_history_file(HAND_WALK_ZOOM + "\n" + garbage + "\n" + HAND_RING_USD_SHOWDOWN)
    assert [h.hand_id for h in hands] == ["1000000001", "1000000002"]
    assert len(errors) == 1
    assert errors[0][0] == "BAD"
