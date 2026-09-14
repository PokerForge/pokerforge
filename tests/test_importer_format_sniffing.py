"""core/importer.py's _parse_txt_hands — iPoker, GGPoker, and PokerStars
all export plain `.txt` files, so the extension alone can't route to the
right parser; a real folder can (and for someone who's played on more
than one site, will) contain multiple formats side by side, so the
content-sniff must pick correctly per file rather than per directory."""
from database.repository import PokerDatabase
from core.importer import parse_directory, parse_directory_incremental

_IPOKER_HAND = """\
GAME #1: Texas Hold'em NL £0.15/£0.30 2026-09-05 20:15:00/GMT
Table UK&Ire 6-max 0.15/0.30, 1
Table Info: Size: 2
Seat 1: Hero (£30.00 in chips) DEALER
Seat 2: Villain1 (£30.00 in chips)
Hero: Post SB £0.15
Villain1: Post BB £0.30
*** HOLE CARDS ***
Dealt to Hero [SA HK]
Hero: Fold
*** SUMMARY ***
Total pot £0.30 Rake £0.00
Villain1: wins £0.30
"""

_GGPOKER_HAND = """\
Poker Hand #RC1: Hold'em No Limit ($0.01/$0.02) - 2025/04/13 13:17:02
Table 'RushAndCash1' 6-max Seat #1 is the button
Seat 1: Hero ($2 in chips)
Seat 2: aaa11111 ($2 in chips)
Hero: posts small blind $0.01
aaa11111: posts big blind $0.02
*** HOLE CARDS ***
Dealt to Hero [8s Ad]
Hero: folds
Uncalled bet ($0.01) returned to aaa11111
*** SHOWDOWN ***
aaa11111 collected $0.02 from pot
*** SUMMARY ***
Total pot $0.02 | Rake $0 | Jackpot $0 | Bingo $0 | Fortune $0 | Tax $0
Seat 1: Hero folded before Flop
Seat 2: aaa11111 collected ($0.02)
"""

_POKERSTARS_HAND = """\
PokerStars Hand #PS1:  Hold'em No Limit ($0.01/$0.02 USD) - 2024/07/14 13:16:42 WET [2024/07/14 8:16:42 ET]
Table 'Aludra' 6-max Seat #1 is the button
Seat 1: Hero ($2 in chips)
Seat 2: Villain1 ($2 in chips)
Hero: posts small blind $0.01
Villain1: posts big blind $0.02
*** HOLE CARDS ***
Dealt to Hero [8s Ad]
Hero: folds
Uncalled bet ($0.01) returned to Villain1
Villain1 collected $0.02 from pot
Villain1: doesn't show hand
*** SUMMARY ***
Total pot $0.02 | Rake $0
Seat 1: Hero folded before Flop
Seat 2: Villain1 collected ($0.02)
"""

_WINNING_NETWORK_HAND = """\
***** Hand History For Game wn1 *****
0.01/0.02 Texas Holdem Game Table (NL) - Fri May 16 18:01:39 EDT 2025
Table Aludra (Real Money) -- Seat 1 is the button
Total number of players : 2/2
Seat 1: Hero ($2)
Seat 2: Player1 ($2)
Hero posts small blind ($0.01)
Player1 posts big blind ($0.02)
** Dealing down cards **
Hero folds
** Summary **
Main Pot: $0.02
Hero balance $1.99, didn't bet (folded)
Player1 balance $2.02, bet $0, collected $0.02, net +$0.02
"""


def test_parse_directory_routes_each_txt_file_by_content_not_extension(tmp_path):
    (tmp_path / "ipoker_export.txt").write_text(_IPOKER_HAND, encoding="utf-8")
    (tmp_path / "ggpoker_export.txt").write_text(_GGPOKER_HAND, encoding="utf-8")
    (tmp_path / "pokerstars_export.txt").write_text(_POKERSTARS_HAND, encoding="utf-8")
    (tmp_path / "winning_network_export.txt").write_text(_WINNING_NETWORK_HAND, encoding="utf-8")

    hands, errors, files_seen = parse_directory(tmp_path)

    assert errors == []
    assert files_seen == 4
    sources = {h.hand_id: h.source for h in hands}
    assert sources == {"1": "ipoker", "RC1": "ggpoker", "PS1": "pokerstars", "wn1": "winning_network"}


def test_parse_directory_incremental_also_routes_by_content(tmp_path):
    (tmp_path / "ipoker_export.txt").write_text(_IPOKER_HAND, encoding="utf-8")
    (tmp_path / "ggpoker_export.txt").write_text(_GGPOKER_HAND, encoding="utf-8")
    (tmp_path / "pokerstars_export.txt").write_text(_POKERSTARS_HAND, encoding="utf-8")
    (tmp_path / "winning_network_export.txt").write_text(_WINNING_NETWORK_HAND, encoding="utf-8")
    db = PokerDatabase(tmp_path / "test.db")

    hands, errors, files_parsed, files_skipped, fingerprints = parse_directory_incremental(tmp_path, db)

    assert errors == []
    assert files_parsed == 4
    sources = {h.hand_id: h.source for h in hands}
    assert sources == {"1": "ipoker", "RC1": "ggpoker", "PS1": "pokerstars", "wn1": "winning_network"}
    db.close()
