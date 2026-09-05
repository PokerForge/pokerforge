"""Poker-site hand-history parsing layer.

The parser below is deliberately isolated from the UI. The first adapter supports
 the iPoker network hand-history format. New poker sites should be added as
 adapters without changing the rest of PokerForge.
"""
import re
from datetime import datetime
from models.hand import Hand, Player, Action
from core.card_utils import hh_card_to_display

class ParseError(ValueError):
    pass

class IPokerParser:
    # Hero plays both GBP and EUR tables, so amounts use either £ or €.
    # Older client versions logged the date as MM-DD-YYYY instead of YYYY-MM-DD.
    HEADER = re.compile(r"GAME #(?P<gid>\d+).*?(?P<gametype>Texas Hold'em|Omaha).*?(?:NL\s+)?(?P<cur>[£€])(?P<sb>[\d.]+)/[£€](?P<bb>[\d.]+)\s+(?P<date>\d{4}-\d{2}-\d{2}|\d{2}-\d{2}-\d{4})\s+(?P<time>[\d:]+)/(?P<tz>\w+)")
    SEAT = re.compile(r"Seat (?P<seat>\d+): (?P<name>.+?) \([£€](?P<stack>[\d.]+) in chips\)(?P<dealer>\s+DEALER)?")
    POST = re.compile(r"^(?P<name>.+?): Post (?P<type>SB|BB) [£€](?P<amt>[\d.]+)$")
    DEALT = re.compile(r"^Dealt to (?P<name>.+?) \[(?P<c1>\w+) (?P<c2>\w+)\]$")
    STREET = re.compile(r"^\*\*\* (?P<street>FLOP|TURN|RIVER) \*\*\* \[(?P<cards>.+?)\]$")
    ACTION = re.compile(r"^(?P<name>.+?): (?P<action>Fold|Check|Call|Bet|Raise \(NF\)|Raise|Allin)(?:\s+[£€](?P<amt>[\d.]+))?$")
    POT = re.compile(r"^Total pot [£€](?P<pot>[\d.]+)(?:\s+Rake [£€](?P<rake>[\d.]+))?$")
    REVEAL = re.compile(r"^(?P<name>.+?): (?:Shows|Mucks) \[(?P<c1>\w+) (?P<c2>\w+)\](?:\s+(?P<desc>.+))?$")
    # "Run it twice" splits a pot across two boards: "wins first/second board £X".
    WINS = re.compile(r"^(?P<name>.+?): wins(?: (?:first|second) board)? [£€](?P<amt>[\d.]+)$")
    UNCALLED = re.compile(r"^Uncalled bet \([£€](?P<amt>[\d.]+)\) returned to (?P<name>.+?)$")
    TABLE_INFO = re.compile(r"^Table Info: Size: (?P<size>\d+)")
    TABLE_NAME = re.compile(r"^Table (?P<name>.+?),\s*\d+$")

    def parse(self, text: str) -> Hand:
        lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
        header = {}
        players = []
        hole_cards = {}
        actions = []
        board = []
        total_pot = rake = None
        button = None
        street = 'PREFLOP'
        in_summary = False
        unmatched = []
        table_name = None
        table_size = None
        winnings = {}

        for line in lines:
            if line == '*** HOLE CARDS ***':
                continue
            if line == '*** SUMMARY ***':
                in_summary = True
                continue
            if not in_summary:
                if m := self.HEADER.search(line):
                    header = m.groupdict(); continue
                if m := self.SEAT.match(line):
                    players.append(Player(m['name'], int(m['seat']), float(m['stack']))); button = int(m['seat']) if m['dealer'] else button; continue
                if m := self.POST.match(line):
                    actions.append(Action(street, m['name'], f"Post {m['type']}", float(m['amt']))); continue
                if m := self.DEALT.match(line):
                    if m['c1'] != 'X' and m['c2'] != 'X':
                        hole_cards[m['name']] = [hh_card_to_display(m['c1']), hh_card_to_display(m['c2'])]
                    continue
                if m := self.STREET.match(line):
                    street = m['street']; board += [hh_card_to_display(c) for c in m['cards'].split()]; continue
                if m := self.UNCALLED.match(line):
                    actions.append(Action(street, m['name'], 'Uncalled Return', float(m['amt']))); continue
                if m := self.ACTION.match(line):
                    actions.append(Action(street, m['name'], m['action'].replace(' (NF)', ''), float(m['amt']) if m['amt'] else None)); continue
                if m := self.TABLE_INFO.match(line):
                    table_size = int(m['size']); continue
                if m := self.TABLE_NAME.match(line):
                    table_name = m['name']; continue
                if line.startswith('Table '):
                    continue
                unmatched.append(line)
            else:
                if m := self.POT.match(line):
                    total_pot = float(m['pot']); rake = float(m['rake']) if m['rake'] else 0.0; continue
                if m := self.REVEAL.match(line):
                    if m['c1'] != 'X' and m['c2'] != 'X':
                        hole_cards[m['name']] = [hh_card_to_display(m['c1']), hh_card_to_display(m['c2'])]
                    continue
                if m := self.WINS.match(line):
                    winnings[m['name']] = winnings.get(m['name'], 0.0) + float(m['amt']); continue
                unmatched.append(line)

        if not header.get('gid'):
            raise ParseError('Hand header not recognised')

        for p in players:
            p.hole_cards = hole_cards.get(p.name, [])
        dt = None
        if header.get('date') and header.get('time'):
            date_str = header['date']
            if date_str[2] == '-':  # MM-DD-YYYY (older client versions) -> YYYY-MM-DD
                mm, dd, yyyy = date_str.split('-')
                date_str = f"{yyyy}-{mm}-{dd}"
            dt = datetime.fromisoformat(f"{date_str}T{header['time']}")

        hand = Hand(
            hand_id=header['gid'], game_type=header.get('gametype', "Texas Hold'em"),
            currency=header.get('cur') or '£',
            small_blind=float(header['sb']), big_blind=float(header['bb']), played_at=dt,
            table_name=table_name, table_size=table_size,
            players=players, button_seat=button, board=board, actions=actions,
            total_pot=total_pot, rake=rake, winnings=winnings,
            raw_text=text, source='ipoker'
        )
        hand.unmatched_lines = unmatched
        return hand


def parse_hand_history(text: str) -> Hand:
    return IPokerParser().parse(text)


_HAND_BOUNDARY = re.compile(r"^GAME #", re.MULTILINE)


def parse_hand_history_file(text: str) -> tuple[list[Hand], list[tuple[str, str]]]:
    """A single export file can contain many hands. Each is parsed in
    isolation so one malformed hand doesn't lose the rest of the file."""
    starts = [m.start() for m in _HAND_BOUNDARY.finditer(text)]
    hands = []
    errors = []
    for i, start in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(text)
        chunk = text[start:end]
        try:
            hands.append(parse_hand_history(chunk))
        except Exception as exc:
            gid_match = re.match(r"GAME #(\d+)", chunk)
            gid = gid_match.group(1) if gid_match else f"chunk#{i}"
            errors.append((gid, str(exc)))
    return hands, errors
