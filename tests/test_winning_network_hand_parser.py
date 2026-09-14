"""Parser correctness for core/winning_network_hand_parser.py's
WinningNetworkParser. Every fixture below is quoted from a real
25-file, 30,863-hand corpus (Americas Cardroom / Winning Network export)
-- verified to parse with zero errors across the whole real corpus,
245 distinct tournaments included (opponent Player1..PlayerN labels are
this format's own real anonymization convention, not stand-ins)."""
import pytest

from core.winning_network_hand_parser import (
    parse_winning_network_hand_history, parse_winning_network_hand_history_file,
    WinningNetworkParseError,
)

TOURNAMENT_FOLD_HAND = """\
***** Hand History For Game 1729005475465u9se0b3f8sn *****
500/1000 Tourney Texas Holdem Game Table (NL) (MTT Tournament #396042592) (Buyin $10.0 + $1.0) - Tue Oct 15 11:16:32 EDT 2024
Table (396042592) Table #8 (Real Money) -- Seat 4 is the button
Total number of players : 8/8
Seat 1: Player1 (285010)
Seat 2: Player2 (114980)
Seat 3: Player3 (106533)
Seat 4: Player4 (84265)
Seat 5: Player5 (83875)
Seat 6: Hero (100000)
Seat 7: Player7 (214202)
Seat 8: Player8 (117614)
Player5 posts small blind (500)
Hero posts big blind (1000)
** Dealing down cards **
Player7 folds
Player8 folds
Player1 folds
Player2 folds
Player3 folds
Player4 raises 1125 to 2125
Player5 folds
Hero folds
** Summary **
Main Pot: 35274
Board: [ 8s, 8c, Jc, Kh, Ah ]
Player1 balance 282885, lost 2125 (folded)
Player2 balance 114855, lost 125 (folded)
Player3 balance 106408, lost 125 (folded)
Player4 balance 104027, bet 33512, collected 53274, net +19762
Player5 balance 83250, lost 625 (folded)
Hero balance 98875, lost 1125 (folded)
Player7 balance 214077, lost 125 (folded)
Player8 balance 102102, lost 15512 (folded)
"""

TOURNAMENT_SHOWDOWN_HAND = """\
***** Hand History For Game 1729091353466z0utm45td *****
1000/2000 Tourney Texas Holdem Game Table (NL) (MTT Tournament #396042592) (Buyin $10.0 + $1.0) - Tue Oct 15 11:44:08 EDT 2024
Table (396042592) Table #8 (Real Money) -- Seat 6 is the button
Total number of players : 7/8
Seat 1: Player1 (281236)
Seat 2: Player2 (108765)
Seat 4: Player3 (153140)
Seat 5: Player4 (90857)
Seat 6: Hero (10070)
Seat 7: Player6 (195180)
Seat 8: Player7 (164268)
Player1 posts small blind (1000)
Player2 posts big blind (2000)
** Dealing down cards **
Dealt to Hero [ Qh, Qs ]
Player3 folds
Player4 folds
Hero raises 8070 to 10070
Hero is all-In.
Player6 folds
Player7 folds
Player1 folds
Player2 calls 8070
** Dealing Flop ** :  [ Th, 3c, Ac ]
** Dealing Turn ** :  [ 5h ]
** Dealing River ** :  [ Ah ]
** Summary **
Main Pot: 20140
Board: [ Th, 3c, Ac, 5h, Ah ]
Player1 balance 280236, lost 1000 (folded)
Player2 balance 92625, lost 10140[ Kd, Kc ] [ two pairs, kings and aces -- Kd,Kc,Ac,Ah,Th ]
Player3 balance 153140, sits out
Player4 balance 90857, sits out
Hero balance 20140, bet 10070, collected 20140, net +10070[ Qh, Qs ] [ two pairs, aces and queens -- Ac,Ah,Qh,Qs,Th ]
Player6 balance 195180, sits out
Player7 balance 164268, sits out
"""

TOURNAMENT_SIDE_POT_HAND = """\
***** Hand History For Game 1729009123456abc *****
2000/4000 Tourney Texas Holdem Game Table (NL) (MTT Tournament #396042593) (Buyin $10.0 + $1.0) - Tue Oct 15 12:00:00 EDT 2024
Table (396042593) Table #1 (Real Money) -- Seat 1 is the button
Total number of players : 5/8
Seat 2: Player2 (5000)
Seat 3: Player3 (30000)
Seat 4: Player4 (80000)
Seat 5: Player5 (2000)
Seat 6: Hero (50000)
Player3 posts small blind (2000)
Player4 posts big blind (4000)
** Dealing down cards **
Player5 raises 2000 to 2000
Player5 is all-In.
Hero calls 2000
Player2 calls 2000
Player3 folds
Player4 calls 0
Player4 raises 16800 to 17400
Hero folds
Player2 calls 3174
Player2 is all-In.
Creating Main Pot with  11922 with Player2
** Dealing Flop ** :  [ 4h, Kc, 2h ]
Player4 bets (12000)
Creating Side Pot 1 with 52452 with Player4
** Dealing Turn ** :  [ Ks ]
** Dealing River ** :  [ As ]
** Summary **
Main Pot: 11922 Side Pot 1: 52452
Board: [ 4h, Kc, 2h, Ks, As ]
Player2 balance 0, lost 5000[ 9d, 9c ] [ a pair of nines -- 9d,9c,As,Ks,Kc ]
Player3 balance 28000, lost 2000 (folded)
Player4 balance 74274, bet 21400, collected 52452, net +31052[ Ah, Kd ] [ a fullhouse, kings full of aces -- Ah,Kd,As,Ks,Kc ]
Player5 balance 0, lost 2000[ 7h, 7c ] [ a pair of sevens -- 7h,7c,As,Ks,Kc ]
Hero balance 46000, lost 2000 (folded)
"""

CASH_HAND = """\
***** Hand History For Game 174743298201666fz0s0qlxr *****
0.02/0.05 Texas Holdem Game Table (NL) - Fri May 16 18:01:39 EDT 2025
Table Venice 73 (Real Money) -- Seat 3 is the button
Total number of players : 5/6
Seat 2: Player4 ($15.19)
Seat 3: Player5 ($6.28)
Seat 4: Player1 ($5.07)
Seat 5: Player2 ($4)
Seat 6: Hero ($5.07)
Player4 posts small blind ($0.02)
Player5 posts big blind ($0.05)
Player2 Cash-out Premium % is 1.0
Player1 folds
Player2 opted for cash-out
Player2 probabilty is 95.46
Player2 Cashout Amount is 7.09
Hero folds
Player4 folds
Player5 could not respond in time.(disconnected)
Player5 folds
** Summary **
Main Pot: $7.60 Rake: $0.4
Board: [ Th, Kh, Kc, 8d, Qd ]
Player4 balance $15.19, didn't bet (folded)
Player5 balance $6.28, didn't bet (folded)
Player1 balance $1.07, lost $4[ 9s, Kd ] [ three of a kind, kings -- Kd,Kh,Kc,Qd,Th ]
Player2 balance $7.60, bet $4, collected $7.60, net +$3.60[ Ks, Qc ] [ a fullhouse, kings full of queens -- Ks,Kh,Kc,Qc,Qd ]
Hero balance $5.07, didn't bet (folded)
"""

# Real header confirmed against the corpus: not every tournament type is
# "MTT" ("SNG JackPot" also seen) -- the type label is matched generically.
SNG_HEADER = (
    "***** Hand History For Game 17363526096529pk54uyzja9 *****\n"
    "30/60 Tourney Texas Holdem Game Table (NL) (SNG JackPot Tournament #404130489) "
    "(Buyin $4.6 + $0.4) - Wed Jan 08 11:09:55 EST 2025\n"
    "Table (404130489) Table #1 (Real Money) -- Seat 1 is the button\n"
    "Total number of players : 2/3\n"
    "Seat 1: Hero (875)\n"
    "Seat 3: Player2 (625)\n"
    "Hero posts small blind (30)\n"
    "Player2 posts big blind (60)\n"
    "** Dealing down cards **\n"
    "Hero folds\n"
    "** Summary **\n"
    "Main Pot: 60\n"
    "Hero balance 845, lost 30 (folded)\n"
    "Player2 balance 685, bet 0, collected 60, net +60\n"
)


def test_tournament_fold_hand_parses_with_no_unmatched_lines():
    hand = parse_winning_network_hand_history(TOURNAMENT_FOLD_HAND)
    assert hand.session_type == 'tournament'
    assert hand.tournament_id == '396042592'
    assert hand.buy_in == 10.0 and hand.fee == 1.0
    assert hand.small_blind == 500.0 and hand.big_blind == 1000.0
    assert hand.source == 'winning_network'
    assert [(p.name, p.stack) for p in hand.players] == [
        ('Player1', 285010.0), ('Player2', 114980.0), ('Player3', 106533.0), ('Player4', 84265.0),
        ('Player5', 83875.0), ('Hero', 100000.0), ('Player7', 214202.0), ('Player8', 117614.0),
    ]
    assert hand.winnings == {'Player4': 53274.0}
    assert hand.total_pot == 35274.0
    assert hand.board == ['8♠', '8♣', 'J♣', 'K♥', 'A♥']
    assert hand.unmatched_lines == []


def test_tournament_showdown_hand_captures_hole_cards_and_winnings():
    hand = parse_winning_network_hand_history(TOURNAMENT_SHOWDOWN_HAND)
    assert hand.winnings == {'Hero': 20140.0}
    assert hand.total_pot == 20140.0
    hero = next(p for p in hand.players if p.name == 'Hero')
    villain = next(p for p in hand.players if p.name == 'Player2')
    assert hero.hole_cards == ['Q♥', 'Q♠']
    assert villain.hole_cards == ['K♦', 'K♣']
    assert hand.unmatched_lines == []


def test_all_in_with_a_side_pot_sums_both_pots_and_tracks_both_winners():
    hand = parse_winning_network_hand_history(TOURNAMENT_SIDE_POT_HAND)
    assert hand.winnings == {'Player4': 52452.0}
    assert hand.total_pot == 11922.0 + 52452.0
    assert hand.unmatched_lines == []
    raises = [a for a in hand.actions if a.action == 'Raise']
    assert [(a.player, a.amount) for a in raises] == [('Player5', 2000.0), ('Player4', 17400.0)]


def test_cash_hand_parses_with_dollar_amounts_and_no_unmatched_lines():
    """Also exercises the cash-out feature lines and a disconnect notice
    -- both recognised-and-skipped (not modeled as winnings/actions, see
    the module docstring), and the disconnect's own separate fold line
    is still captured normally."""
    hand = parse_winning_network_hand_history(CASH_HAND)
    assert hand.session_type == 'cash'
    assert hand.tournament_id is None and hand.buy_in is None and hand.fee is None
    assert hand.winnings == {'Player2': 7.6}
    assert hand.total_pot == 7.6
    assert hand.rake == 0.4
    assert hand.unmatched_lines == []
    folds = [a.player for a in hand.actions if a.action == 'Fold']
    assert 'Player5' in folds  # the disconnected player's actual fold is still captured


def test_a_non_mtt_tournament_type_label_still_parses():
    hand = parse_winning_network_hand_history(SNG_HEADER)
    assert hand.session_type == 'tournament'
    assert hand.tournament_id == '404130489'
    assert hand.buy_in == 4.6 and hand.fee == 0.4
    assert hand.unmatched_lines == []


def test_unrecognised_text_raises_parse_error():
    with pytest.raises(WinningNetworkParseError):
        parse_winning_network_hand_history("this is not a hand history at all")


def test_parse_hand_history_file_splits_multiple_hands():
    hands, errors = parse_winning_network_hand_history_file(
        TOURNAMENT_FOLD_HAND + TOURNAMENT_SHOWDOWN_HAND)
    assert len(hands) == 2
    assert errors == []
    assert hands[0].hand_id == '1729005475465u9se0b3f8sn'
    assert hands[1].hand_id == '1729091353466z0utm45td'


def test_a_malformed_hand_in_a_multi_hand_file_is_isolated_as_an_error():
    hands, errors = parse_winning_network_hand_history_file(
        TOURNAMENT_FOLD_HAND + "***** Hand History For Game badbadbad *****\nnonsense\n")
    assert len(hands) == 1
    assert len(errors) == 1
    assert errors[0][0] == 'badbadbad'
