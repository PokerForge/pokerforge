"""Coverage for core/xml_hand_parser.py — Grosvenor's proprietary XML
session format, reverse-engineered from real exports (see the module's own
docstring for how the action-type/round-number mappings were derived).
Nothing here was documented by the vendor, so a schema assumption drifting
silently is the realistic failure mode this guards against."""
import pytest

from core.xml_hand_parser import parse_session_file, XmlParseError

SESSION_TEMPLATE = """<?xml version="1.0"?>
<session>
  <general>
    <tablename>UK&amp;Ire 6-max 0.15/0.30</tablename>
    <tablesize>2</tablesize>
    <smallblind>0.15</smallblind>
    <bigblind>0.30</bigblind>
    <gametype>Holdem NL</gametype>
  </general>
  {games}
</session>
"""

GOOD_GAME = """
<game gamecode="555111">
  <general>
    <startdate>2026-09-05T20:00:00</startdate>
    <players>
      <player name="Hero" seat="1" chips="30.00" dealer="1" bet="0.90" win="0.45" />
      <player name="Villain" seat="2" chips="29.70" bet="0.15" />
    </players>
  </general>
  <round no="0">
    <action no="1" type="1" player="Villain" sum="0.15" />
    <action no="2" type="2" player="Hero" sum="0.30" />
  </round>
  <round no="1">
    <cards type="Pocket" player="Hero">SA HK</cards>
    <action no="3" type="23" player="Hero" sum="0.90" />
    <action no="4" type="0" player="Villain" sum="0.00" />
  </round>
</game>
"""

GAME_WITH_FLOP = """
<game gamecode="555222">
  <general>
    <startdate>2026-09-05T20:05:00</startdate>
    <players>
      <player name="Hero" seat="1" chips="29.10" dealer="1" bet="0.45" win="0" />
      <player name="Villain" seat="2" chips="30.90" bet="0.45" win="0.85" rakeamount="0.05" />
    </players>
  </general>
  <round no="1">
    <action no="1" type="3" player="Hero" sum="0.30" />
    <action no="2" type="4" player="Villain" sum="0.00" />
  </round>
  <round no="2">
    <cards type="Flop">SK D5 H2</cards>
    <action no="3" type="5" player="Villain" sum="0.15" />
    <action no="4" type="3" player="Hero" sum="0.15" />
  </round>
</game>
"""

BAD_ROUND_GAME = """
<game gamecode="555999">
  <general>
    <startdate>2026-09-05T20:10:00</startdate>
    <players>
      <player name="Hero" seat="1" chips="30.00" dealer="1" />
      <player name="Villain" seat="2" chips="30.00" />
    </players>
  </general>
  <round no="99">
    <action no="1" type="0" player="Villain" sum="0.00" />
  </round>
</game>
"""

BAD_ACTION_TYPE_GAME = """
<game gamecode="555888">
  <general>
    <startdate>2026-09-05T20:15:00</startdate>
    <players>
      <player name="Hero" seat="1" chips="30.00" dealer="1" />
      <player name="Villain" seat="2" chips="30.00" />
    </players>
  </general>
  <round no="1">
    <action no="1" type="999" player="Villain" sum="0.00" />
  </round>
</game>
"""


def _write(tmp_path, games_xml):
    path = tmp_path / "session.xml"
    path.write_text(SESSION_TEMPLATE.format(games=games_xml), encoding="utf-8")
    return path


def test_parses_session_level_info_onto_each_hand(tmp_path):
    hands, errors = parse_session_file(_write(tmp_path, GOOD_GAME))
    assert errors == []
    hand = hands[0]
    assert hand.hand_id == "555111"
    assert hand.table_name == "UK&Ire 6-max 0.15/0.30"
    assert hand.table_size == 2
    assert hand.small_blind == 0.15
    assert hand.big_blind == 0.30
    assert hand.source == "grosvenor_xml"


def test_parses_players_seats_button_and_money(tmp_path):
    hands, _ = parse_session_file(_write(tmp_path, GOOD_GAME))
    hand = hands[0]
    assert hand.button_seat == 1
    seats = {p.name: p.seat for p in hand.players}
    assert seats == {"Hero": 1, "Villain": 2}
    assert hand.winnings == {"Hero": 0.45}
    assert hand.total_pot == pytest.approx(1.05)  # 0.90 (Hero's bet) + 0.15 (Villain's)


def test_parses_hole_cards_only_when_both_known(tmp_path):
    hands, _ = parse_session_file(_write(tmp_path, GOOD_GAME))
    hero = next(p for p in hands[0].players if p.name == "Hero")
    villain = next(p for p in hands[0].players if p.name == "Villain")
    assert hero.hole_cards == ["A♠", "K♥"]
    assert villain.hole_cards == []  # never dealt/shown in this fixture


def test_action_types_and_rounds_map_to_the_right_street_and_name(tmp_path):
    hands, _ = parse_session_file(_write(tmp_path, GOOD_GAME))
    actions = [(a.street, a.player, a.action, a.amount) for a in hands[0].actions]
    assert actions == [
        ("PREFLOP", "Villain", "Post SB", 0.15),
        ("PREFLOP", "Hero", "Post BB", 0.30),
        ("PREFLOP", "Hero", "Raise", 0.90),
        ("PREFLOP", "Villain", "Fold", 0.00),
    ]


def test_flop_round_maps_to_flop_street_and_board(tmp_path):
    hands, _ = parse_session_file(_write(tmp_path, GAME_WITH_FLOP))
    hand = hands[0]
    assert hand.board == ["K♠", "5♦", "2♥"]
    flop_actions = [(a.player, a.action) for a in hand.actions if a.street == "FLOP"]
    assert flop_actions == [("Villain", "Bet"), ("Hero", "Call")]
    assert hand.rake == pytest.approx(0.05)


def test_unknown_round_number_raises_and_is_isolated(tmp_path):
    hands, errors = parse_session_file(_write(tmp_path, GOOD_GAME + BAD_ROUND_GAME))
    assert [h.hand_id for h in hands] == ["555111"]
    assert len(errors) == 1
    assert errors[0][0] == "555999"


def test_unknown_action_type_raises_and_is_isolated(tmp_path):
    hands, errors = parse_session_file(_write(tmp_path, GOOD_GAME + BAD_ACTION_TYPE_GAME))
    assert [h.hand_id for h in hands] == ["555111"]
    assert len(errors) == 1
    assert errors[0][0] == "555888"


def test_missing_general_block_raises(tmp_path):
    path = tmp_path / "broken.xml"
    path.write_text("<session><game gamecode=\"1\"></game></session>", encoding="utf-8")
    with pytest.raises(XmlParseError):
        parse_session_file(path)
