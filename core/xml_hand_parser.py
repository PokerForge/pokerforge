"""Parser for Grosvenor Poker's native XML session-history format.

Each XML file is one seated session containing many <game> hands. Action
`type` codes were reverse-engineered from real data, not documentation, by
scanning all 435 sample files (30,968 hands):
  0=Fold, 1=Post SB, 2=Post BB, 3=Call, 4=Check, 5=Bet, 7=Allin, 23=Raise.
Fold vs Check (both show sum="£0") were disambiguated by checking whether the
player ever acts again in the same hand: fold never does (0/25,887), check
usually does (11,003/12,615 — the rest are checks that simply ended the hand,
e.g. checked down to showdown).

Amount conventions match the text-format parser (core/hand_parser.py): a
Raise's `sum` is the new absolute total committed this street; every other
action type's `sum` is incremental. Confirmed for Allin by summing each
player's whole-hand commitment and checking it matches their starting stack
(210/262 exact in a 150-file sample; remaining drift traced to a few
apparently-stale `chips` snapshots in some multi-game session files, not a
convention issue).

Round numbers map directly to streets — no street-transition text to parse:
round 0 = blind posting, round 1 = preflop action, 2 = flop, 3 = turn, 4 = river.
Both are folded into 'PREFLOP' to match the text-format parser's street model.

There is no separate "uncalled bet returned" action type in this format —
each player's own action sums already reflect their true, capped contribution.
"""
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime
from models.hand import Hand, Player, Action
from core.card_utils import hh_card_to_display

ROUND_STREET = {0: 'PREFLOP', 1: 'PREFLOP', 2: 'FLOP', 3: 'TURN', 4: 'RIVER'}
ACTION_TYPE = {
    '0': 'Fold', '1': 'Post SB', '2': 'Post BB', '3': 'Call',
    '4': 'Check', '5': 'Bet', '7': 'Allin', '23': 'Raise',
}


class XmlParseError(ValueError):
    pass


def _money(s: str | None):
    if s is None or s == '':
        return None
    return float(s.replace('£', '').strip())


def _parse_game(game_el, session_info: dict) -> Hand:
    gamecode = game_el.get('gamecode')
    general = game_el.find('general')
    startdate = general.findtext('startdate')
    played_at = datetime.fromisoformat(startdate) if startdate else None

    players = []
    winnings = {}
    invested = {}
    total_pot = 0.0
    rake = 0.0
    button = None
    for p in general.find('players').findall('player'):
        name = p.get('name')
        players.append(Player(name, int(p.get('seat')), _money(p.get('chips'))))
        if p.get('dealer') == '1':
            button = int(p.get('seat'))
        bet = _money(p.get('bet')) or 0.0
        invested[name] = invested.get(name, 0.0) + bet
        total_pot += bet
        win = _money(p.get('win')) or 0.0
        if win:
            winnings[name] = winnings.get(name, 0.0) + win
        rakeamount = p.get('rakeamount')
        if rakeamount:
            rake += _money(rakeamount)

    hole_cards: dict[str, list[str]] = {}
    board: list[str] = []
    actions: list[Action] = []

    for round_el in sorted(game_el.findall('round'), key=lambda r: int(r.get('no'))):
        rno = int(round_el.get('no'))
        street = ROUND_STREET.get(rno)
        if street is None:
            raise XmlParseError(f"Unknown round number {rno} in game {gamecode}")

        for cards_el in round_el.findall('cards'):
            ctype = cards_el.get('type')
            text = (cards_el.text or '').strip()
            if ctype == 'Pocket':
                codes = text.split()
                # A player can show only one card ("D7 X"); we only record a
                # hand when both cards are actually known.
                if codes and all(c != 'X' for c in codes):
                    hole_cards[cards_el.get('player')] = [hh_card_to_display(c) for c in codes]
            elif ctype in ('Flop', 'Turn', 'River'):
                board.extend(hh_card_to_display(c) for c in text.split())

        for action_el in sorted(round_el.findall('action'), key=lambda a: int(a.get('no'))):
            t = action_el.get('type')
            action_name = ACTION_TYPE.get(t)
            if action_name is None:
                raise XmlParseError(f"Unknown action type {t!r} in game {gamecode}")
            actions.append(Action(street, action_el.get('player'), action_name, _money(action_el.get('sum'))))

    for p in players:
        p.hole_cards = hole_cards.get(p.name, [])

    return Hand(
        hand_id=gamecode, game_type=session_info.get('game_type') or "Texas Hold'em",
        small_blind=session_info.get('small_blind'), big_blind=session_info.get('big_blind'),
        played_at=played_at, table_name=session_info.get('table_name'),
        table_size=session_info.get('table_size'), button_seat=button,
        players=players, board=board, actions=actions,
        total_pot=round(total_pot, 2), rake=round(rake, 2), winnings=winnings, invested=invested,
        raw_text=None, source='grosvenor_xml',
    )


def parse_session_file(path: str | Path) -> tuple[list[Hand], list[tuple[str, str]]]:
    """Returns (hands, errors). A single malformed game must not lose every
    other hand in the same session file, so each <game> is parsed in
    isolation; errors are returned as (gamecode, message) pairs."""
    path = Path(path)
    root = ET.parse(path).getroot()
    general = root.find('general')
    if general is None:
        raise XmlParseError(f"No <general> block in {path}")

    session_info = {
        'table_name': general.findtext('tablename'),
        'table_size': int(general.findtext('tablesize')) if general.findtext('tablesize') else None,
        'small_blind': _money(general.findtext('smallblind')),
        'big_blind': _money(general.findtext('bigblind')),
        'game_type': general.findtext('gametype'),
    }

    hands = []
    errors = []
    for game_el in root.findall('game'):
        try:
            hands.append(_parse_game(game_el, session_info))
        except Exception as exc:
            errors.append((game_el.get('gamecode'), str(exc)))
    return hands, errors
