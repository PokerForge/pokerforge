"""Parser correctness for core/ggpoker_hand_parser.py's GGPokerParser.
Sample hands below mirror the exact shapes confirmed against a real
452-file, ~150k-hand GGPoker "Rush & Cash" export (opponent hex names
changed to short stand-ins here purely for readability -- the real
export's names are equally meaningless single-hand placeholders)."""
import pytest

from core.ggpoker_hand_parser import parse_ggpoker_hand_history, parse_ggpoker_hand_history_file, GGParseError

# Header shape confirmed real (embedded in this test file already before
# tournament support existed); the action body is hand-built to match the
# same grammar the cash fixtures above use (no real full tournament hand
# body was available to verify against — see ROADMAP.md's tournament-
# support notes), just with chip-denominated (no currency symbol) amounts
# throughout, matching a real tournament export's convention.
HAND_TOURNAMENT = """\
Poker Hand #TM3456789012: Tournament #3456789012, $10+$1 Hold'em No Limit - Level5(100/200) - 2025/04/13 13:17:02
Table '3456789012 1' 6-max Seat #2 is the button
Seat 1: 448c7ca6 (15000 in chips)
Seat 2: Hero (16000 in chips)
Seat 3: 3bf08a6 (14200 in chips)
448c7ca6: posts small blind 100
Hero: posts big blind 200
*** HOLE CARDS ***
Dealt to Hero [Ah Kd]
3bf08a6: raises 400 to 400
448c7ca6: folds
Hero: calls 200
*** FLOP *** [2c 7d Kc]
Hero: checks
3bf08a6: bets 500
Hero: calls 500
*** TURN *** [2c 7d Kc] [9h]
Hero: checks
3bf08a6: checks
*** RIVER *** [2c 7d Kc 9h] [4s]
Hero: bets 900
3bf08a6: folds
Uncalled bet (900) returned to Hero
*** SHOWDOWN ***
Hero collected 2200 from pot
*** SUMMARY ***
Total pot 2200 | Rake 0
Board [2c 7d Kc 9h 4s]
"""

HAND_WALK = """\
Poker Hand #RC1000000001: Hold'em No Limit ($0.01/$0.02) - 2025/04/13 13:17:02
Table 'RushAndCash11251879' 6-max Seat #1 is the button
Seat 1: aaa11111 ($2.06 in chips)
Seat 2: bbb22222 ($1.83 in chips)
Seat 3: Hero ($2 in chips)
Seat 4: ccc33333 ($2.68 in chips)
Seat 5: ddd44444 ($3.53 in chips)
Seat 6: eee55555 ($4.94 in chips)
bbb22222: posts small blind $0.01
Hero: posts big blind $0.02
*** HOLE CARDS ***
Dealt to aaa11111
Dealt to bbb22222
Dealt to Hero [8s Ad]
Dealt to ccc33333
Dealt to ddd44444
Dealt to eee55555
ccc33333: folds
ddd44444: folds
eee55555: folds
aaa11111: folds
bbb22222: folds
Uncalled bet ($0.01) returned to Hero
*** SHOWDOWN ***
Hero collected $0.02 from pot
*** SUMMARY ***
Total pot $0.02 | Rake $0 | Jackpot $0 | Bingo $0 | Fortune $0 | Tax $0
Seat 1: aaa11111 (button) folded before Flop (didn't bet)
Seat 2: bbb22222 (small blind) folded before Flop
Seat 3: Hero (big blind) collected ($0.02)
Seat 4: ccc33333 folded before Flop (didn't bet)
Seat 5: ddd44444 folded before Flop (didn't bet)
Seat 6: eee55555 folded before Flop (didn't bet)
"""

HAND_SHOWDOWN = """\
Poker Hand #RC1000000002: Hold'em No Limit ($0.01/$0.02) - 2025/04/13 13:17:11
Table 'RushAndCash11251957' 6-max Seat #1 is the button
Seat 1: aaa11111 ($2.26 in chips)
Seat 2: bbb22222 ($2.63 in chips)
Seat 3: ccc33333 ($1.95 in chips)
Seat 4: ddd44444 ($1.43 in chips)
Seat 5: eee55555 ($2.26 in chips)
Seat 6: Hero ($2 in chips)
bbb22222: posts small blind $0.01
ccc33333: posts big blind $0.02
*** HOLE CARDS ***
Dealt to aaa11111
Dealt to bbb22222
Dealt to ccc33333
Dealt to ddd44444
Dealt to eee55555
Dealt to Hero [Js Kh]
ddd44444: folds
eee55555: folds
Hero: raises $0.04 to $0.06
aaa11111: folds
bbb22222: calls $0.05
ccc33333: folds
*** FLOP *** [Jd 4d 3s]
bbb22222: bets $0.08
Hero: raises $0.17 to $0.25
bbb22222: calls $0.17
*** TURN *** [Jd 4d 3s] [4h]
bbb22222: checks
Hero: checks
*** RIVER *** [Jd 4d 3s 4h] [7h]
bbb22222: checks
Hero: bets $0.43
bbb22222: raises $1.89 to $2.32 and is all-in
Hero: calls $1.26
Uncalled bet ($0.63) returned to bbb22222
bbb22222: shows [3c 3d] (a full house, Threes full of Fours)
Hero: shows [Js Kh] (two pair, Jacks and Fours)
*** SHOWDOWN ***
bbb22222 collected $3.93 from pot
*** SUMMARY ***
Total pot $4.02 | Rake $0.06 | Jackpot $0.03 | Bingo $0 | Fortune $0 | Tax $0
Board [Jd 4d 3s 4h 7h]
Seat 1: aaa11111 (button) folded before Flop (didn't bet)
Seat 2: bbb22222 (small blind) showed [3c 3d] and won ($3.93) with a full house, Threes full of Fours
Seat 3: ccc33333 (big blind) folded before Flop
Seat 4: ddd44444 folded before Flop (didn't bet)
Seat 5: eee55555 folded before Flop (didn't bet)
Seat 6: Hero showed [Js Kh] and lost with two pair, Jacks and Fours
"""

HAND_ALLIN_CALL = """\
Poker Hand #RC1000000003: Hold'em No Limit ($0.01/$0.02) - 2025/04/13 13:20:00
Table 'RushAndCash11259999' 6-max Seat #1 is the button
Seat 1: Hero ($2 in chips)
Seat 2: aaa11111 ($1.5 in chips)
Seat 3: bbb22222 ($2.24 in chips)
Seat 4: ccc33333 ($2.07 in chips)
Seat 5: ddd44444 ($2.75 in chips)
Seat 6: eee55555 ($2 in chips)
aaa11111: posts small blind $0.01
bbb22222: posts big blind $0.02
*** HOLE CARDS ***
Dealt to Hero [Ac Ad]
Dealt to aaa11111
Dealt to bbb22222
Dealt to ccc33333
Dealt to ddd44444
Dealt to eee55555
ccc33333: folds
ddd44444: folds
eee55555: folds
Hero: raises $0.04 to $0.06
aaa11111: folds
bbb22222: calls $0.04
*** FLOP *** [Td Qs 3s]
bbb22222: checks
Hero: bets $0.10
bbb22222: calls $0.10
*** TURN *** [Td Qs 3s] [Jh]
bbb22222: checks
Hero: checks
*** RIVER *** [Td Qs 3s Jh] [2c]
bbb22222: bets $0.56 and is all-in
Hero: calls $0.56
bbb22222: shows [6c 6h] (a pair of Sixes)
Hero: shows [Ac Ad] (a pair of Aces)
*** SHOWDOWN ***
Hero collected $1.54 from pot
*** SUMMARY ***
Total pot $1.58 | Rake $0.04 | Jackpot $0 | Bingo $0 | Fortune $0 | Tax $0
Board [Td Qs 3s Jh 2c]
Seat 1: Hero showed [Ac Ad] and won ($1.54) with a pair of Aces
Seat 2: aaa11111 (small blind) folded before Flop
Seat 3: bbb22222 (big blind) showed [6c 6h] and lost with a pair of Sixes
Seat 4: ccc33333 folded before Flop (didn't bet)
Seat 5: ddd44444 folded before Flop (didn't bet)
Seat 6: eee55555 folded before Flop (didn't bet)
"""


def test_parses_header_fields():
    hand = parse_ggpoker_hand_history(HAND_WALK)
    assert hand.hand_id == "RC1000000001"
    assert hand.game_type == "Texas Hold'em"
    assert hand.currency == "$"
    assert hand.small_blind == 0.01
    assert hand.big_blind == 0.02
    assert hand.played_at.isoformat() == "2025-04-13T13:17:02"
    assert hand.source == "ggpoker"


def test_actual_posted_blind_amount_overrides_a_corrupted_header_stake():
    """Confirmed against a real 222,843-hand import: 8 hands (0.004%) had
    a header stake that didn't match what was actually posted -- one
    even missing its decimal point outright ("$005/$0.1" instead of
    "$0.05/$0.1"). The posted-blind action amount is real money moving
    and can't be wrong the way a text field occasionally is, so it wins."""
    corrupted = HAND_WALK.replace(
        "Poker Hand #RC1000000001: Hold'em No Limit ($0.01/$0.02)",
        "Poker Hand #RC1000000001: Hold'em No Limit ($9.11/$0.02)")
    hand = parse_ggpoker_hand_history(corrupted)
    assert hand.small_blind == 0.01  # from "bbb22222: posts small blind $0.01", not the header
    assert hand.big_blind == 0.02


def test_parses_table_seats_and_button():
    hand = parse_ggpoker_hand_history(HAND_WALK)
    assert hand.table_name == "RushAndCash11251879"
    assert hand.table_size == 6
    assert hand.button_seat == 1
    seats = {p.name: p.seat for p in hand.players}
    assert seats["Hero"] == 3
    stacks = {p.name: p.stack for p in hand.players}
    assert stacks["Hero"] == 2.0


def test_euro_denominated_table_is_recognised_not_defaulted_to_dollar():
    euro_hand = HAND_WALK.replace("$", "€")
    hand = parse_ggpoker_hand_history(euro_hand)
    assert hand.currency == "€"


def test_dealt_without_cards_leaves_opponent_hole_cards_empty():
    hand = parse_ggpoker_hand_history(HAND_WALK)
    hero = next(p for p in hand.players if p.name == "Hero")
    villain = next(p for p in hand.players if p.name == "aaa11111")
    assert hero.hole_cards == ["8♠", "A♦"]
    assert villain.hole_cards == []


def test_walk_produces_uncalled_return_and_winnings():
    hand = parse_ggpoker_hand_history(HAND_WALK)
    actions = [(a.street, a.player, a.action, a.amount) for a in hand.actions]
    assert ("PREFLOP", "bbb22222", "Post SB", 0.01) in actions
    assert ("PREFLOP", "Hero", "Post BB", 0.02) in actions
    assert ("PREFLOP", "Hero", "Uncalled Return", 0.01) in actions
    assert hand.winnings == {"Hero": 0.02}
    assert hand.total_pot == 0.02
    assert hand.rake == 0.0


def test_raise_amount_is_the_new_total_not_the_increment():
    """Matches the app-wide Raise convention (core/stats.py docstring):
    `amount` is the new TOTAL committed this street, not the incremental
    raise size -- GGPoker's "raises $X to $Y" syntax hands us both, and
    Y (the total) is what must be stored."""
    hand = parse_ggpoker_hand_history(HAND_SHOWDOWN)
    hero_raise = next(a for a in hand.actions if a.player == "Hero" and a.street == "PREFLOP" and a.action == "Raise")
    assert hero_raise.amount == 0.06


def test_board_built_incrementally_across_streets():
    hand = parse_ggpoker_hand_history(HAND_SHOWDOWN)
    assert hand.board == ["J♦", "4♦", "3♠", "4♥", "7♥"]


def test_shows_lines_populate_hole_cards_for_both_players():
    hand = parse_ggpoker_hand_history(HAND_SHOWDOWN)
    hero = next(p for p in hand.players if p.name == "Hero")
    villain = next(p for p in hand.players if p.name == "bbb22222")
    assert hero.hole_cards == ["J♠", "K♥"]
    assert villain.hole_cards == ["3♣", "3♦"]


def test_all_in_raise_is_recorded_as_a_plain_raise():
    """An all-in that raises the action (GGPoker's own "raises ... to ...
    and is all-in" verb) is unambiguous -- unlike iPoker's generic
    "Allin" label, GGPoker already tells us it's a raise, so it should
    just be stored as 'Raise' (per core/stats.py: "Raise is always a
    real raise, even when it happens to use the player's whole stack")."""
    hand = parse_ggpoker_hand_history(HAND_SHOWDOWN)
    shove = next(a for a in hand.actions
                 if a.player == "bbb22222" and a.street == "RIVER" and a.action == "Raise")
    assert shove.amount == 2.32


def test_all_in_call_is_recorded_as_a_plain_call():
    hand = parse_ggpoker_hand_history(HAND_ALLIN_CALL)
    shove = next(a for a in hand.actions if a.player == "bbb22222" and a.street == "RIVER")
    assert shove.action == "Bet"
    assert shove.amount == 0.56
    hero_call = next(a for a in hand.actions if a.player == "Hero" and a.street == "RIVER")
    assert hero_call.action == "Call"
    assert hero_call.amount == 0.56


def test_summary_seat_and_board_recap_lines_are_ignored_not_unmatched():
    hand = parse_ggpoker_hand_history(HAND_SHOWDOWN)
    assert hand.unmatched_lines == []


HAND_RUN_TWICE = """\
Poker Hand #RC1000000004: Hold'em No Limit ($0.02/$0.05) - 2026/07/09 14:20:00
Table 'NLHYellow76' 6-max Seat #3 is the button
Seat 1: aaa11111 ($5.33 in chips)
Seat 2: bbb22222 ($11.91 in chips)
Seat 3: ccc33333 ($12.92 in chips)
Seat 4: Hero ($5 in chips)
Seat 5: ddd44444 ($9.21 in chips)
Seat 6: eee55555 ($5.53 in chips)
ddd44444: posts small blind $0.02
eee55555: posts big blind $0.05
*** HOLE CARDS ***
Dealt to aaa11111
Dealt to bbb22222
Dealt to ccc33333
Dealt to Hero [Qc Qh]
Dealt to ddd44444
Dealt to eee55555
eee55555: raises $0.06 to $0.11
aaa11111: folds
bbb22222: raises $0.26 to $0.37
ccc33333: folds
Hero: raises $0.68 to $1.05
ddd44444: folds
eee55555: folds
bbb22222: raises $5.85 to $6.9 and is all-in
Hero: calls $4.35 and is all-in
Uncalled bet ($1.5) returned to bbb22222
bbb22222: shows [Ks Ah]
Hero: shows [Qc Qh]
*** FIRST FLOP *** [7c 7h 5s]
*** FIRST TURN *** [7c 7h 5s] [Kc]
*** FIRST RIVER *** [7c 7h 5s Kc] [5c]
*** SECOND FLOP *** [Td 9h 7s]
*** SECOND TURN *** [Td 9h 7s] [Qd]
*** SECOND RIVER *** [Td 9h 7s Qd] [Jc]
*** FIRST SHOWDOWN ***
bbb22222 collected $5.21 from pot
*** SECOND SHOWDOWN ***
bbb22222 collected $5.2 from pot
*** SUMMARY ***
Total pot $10.96 | Rake $0.5 | Jackpot $0.05 | Bingo $0 | Fortune $0 | Tax $0
Hand was run two times
FIRST Board [7c 7h 5s Kc 5c]
SECOND Board [Td 9h 7s Qd Jc]
Seat 1: aaa11111 folded before Flop (didn't bet)
Seat 2: bbb22222 showed [Ks Ah] and won ($5.21) with two pair, Kings and Sevens, and won ($5.2) with a straight, Ace to Ten
Seat 3: ccc33333 (button) folded before Flop (didn't bet)
Seat 4: Hero (small blind) showed [Qc Qh] and lost with two pair, Queens and Sevens, and lost with three of a kind, Queens
Seat 5: ddd44444 (big blind) folded before Flop
Seat 6: eee55555 folded before Flop
"""

HAND_EV_CASHOUT = """\
Poker Hand #RC1000000005: Hold'em No Limit ($0.05/$0.10) - 2026/07/09 15:00:00
Table 'NLHRed12' 6-max Seat #1 is the button
Seat 1: Hero ($10 in chips)
Seat 2: aaa11111 ($10 in chips)
Seat 3: bbb22222 ($10 in chips)
Seat 4: ccc33333 ($10 in chips)
Seat 5: ddd44444 ($10 in chips)
Seat 6: eee55555 ($10 in chips)
aaa11111: posts small blind $0.05
bbb22222: posts big blind $0.10
*** HOLE CARDS ***
Dealt to Hero [Ad Qd]
Dealt to aaa11111
Dealt to bbb22222
Dealt to ccc33333
Dealt to ddd44444
Dealt to eee55555
ccc33333: raises $0.10 to $0.15
ddd44444: folds
eee55555: folds
Hero: calls $0.15
aaa11111: folds
bbb22222: raises $0.29 to $0.44
ccc33333: calls $0.29
Hero: calls $0.29
*** FLOP *** [As 8s 2d]
bbb22222: checks
ccc33333: bets $0.46
Hero: raises $1.10 to $1.56
bbb22222: folds
ccc33333: calls $1.07
*** TURN *** [As 8s 2d] [4d]
ccc33333: Chooses to EV Cashout
*** RIVER *** [As 8s 2d 4d] [Ts]
ccc33333: Receives Cashout ($0.9)
*** SHOWDOWN ***
Hero collected $3.88 from pot
*** SUMMARY ***
Total pot $3.97 | Rake $0.06 | Jackpot $0.03 | Bingo $0 | Fortune $0 | Tax $0
Board [As 8s 2d 4d Ts]
Seat 1: Hero showed [Ad Qd] and won ($3.88) with a pair of Aces
Seat 2: aaa11111 (small blind) folded before Flop
Seat 3: bbb22222 (big blind) folded before Flop
Seat 4: ccc33333 showed [Jd Qd] and lost with Ace high, EV Cashout ($0)
Seat 5: ddd44444 folded before Flop (didn't bet)
Seat 6: eee55555 folded before Flop (didn't bet)
"""


def test_run_it_twice_sums_winnings_from_both_boards_and_keeps_only_the_first_board():
    hand = parse_ggpoker_hand_history(HAND_RUN_TWICE)
    assert hand.winnings == {"bbb22222": pytest.approx(10.41)}
    assert hand.board == ["7♣", "7♥", "5♠", "K♣", "5♣"]
    assert hand.unmatched_lines == []


def test_run_it_twice_still_tags_preflop_actions_correctly():
    hand = parse_ggpoker_hand_history(HAND_RUN_TWICE)
    hero_raise = next(a for a in hand.actions if a.player == "Hero" and a.action == "Raise")
    assert hero_raise.street == "PREFLOP"


def test_receives_cashout_is_added_to_winnings_even_with_no_collected_line():
    """Traced against real hands: "Receives Cashout" is real money with
    no matching "collected from pot" line most of the time -- dropping it
    would silently zero out a player's actual payout for that hand."""
    hand = parse_ggpoker_hand_history(HAND_EV_CASHOUT)
    assert hand.winnings == {"Hero": pytest.approx(3.88), "ccc33333": pytest.approx(0.9)}
    assert hand.unmatched_lines == []


def test_unrecognised_text_raises_parse_error():
    with pytest.raises(GGParseError):
        parse_ggpoker_hand_history("this is not a hand history at all")


def test_tournament_hand_is_parsed_and_flagged_as_a_tournament():
    """A tournament header's blind-level segment has no currency symbol,
    so it can never satisfy HEADER's cash-stakes group -- that mutual
    exclusivity is exactly what makes TOURNAMENT_HEADER reliable to fall
    back to. session_type/tournament_id/buy_in/fee let every downstream
    cash aggregate (bb100, profit) exclude these hands rather than
    silently summing chip counts as dollars."""
    hand = parse_ggpoker_hand_history(HAND_TOURNAMENT)
    assert hand.session_type == 'tournament'
    assert hand.tournament_id == '3456789012'
    assert hand.buy_in == 10.0
    assert hand.fee == 1.0
    assert hand.small_blind == 100.0 and hand.big_blind == 200.0
    assert hand.winnings == {'Hero': 2200.0}
    assert hand.unmatched_lines == []


def test_tournament_hand_with_no_stated_fee_defaults_fee_to_zero():
    freezeout = HAND_TOURNAMENT.replace("$10+$1 ", "$10 ")
    hand = parse_ggpoker_hand_history(freezeout)
    assert hand.session_type == 'tournament'
    assert hand.buy_in == 10.0
    assert hand.fee == 0.0


def test_cash_hand_is_not_flagged_as_a_tournament():
    hand = parse_ggpoker_hand_history(HAND_WALK)
    assert hand.session_type == 'cash'
    assert hand.tournament_id is None
    assert hand.buy_in is None
    assert hand.fee is None


def test_parse_hand_history_file_splits_multiple_hands():
    hands, errors = parse_ggpoker_hand_history_file(HAND_WALK + "\n" + HAND_SHOWDOWN)
    assert errors == []
    assert [h.hand_id for h in hands] == ["RC1000000001", "RC1000000002"]


def test_parse_hand_history_file_isolates_one_bad_hand():
    garbage = "Poker Hand #RCBAD: not a real hand at all\nnonsense line\n"
    hands, errors = parse_ggpoker_hand_history_file(HAND_WALK + "\n" + garbage + "\n" + HAND_SHOWDOWN)
    assert [h.hand_id for h in hands] == ["RC1000000001", "RC1000000002"]
    assert len(errors) == 1
    assert errors[0][0] == "RCBAD"
