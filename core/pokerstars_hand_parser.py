"""Parser for PokerStars' native text hand-history export format.

Unlike GGPoker (core/ggpoker_hand_parser.py), PokerStars keeps real
opponent usernames -- so PokerStars hands feed the FULL Intelligence
Engine (population, villain profiles, Similar Players), not just Hero's
own stats. GGPoker's own format is a close descendant of this one (same
"raises $X to $Y", "*** FLOP *** [...]", run-it-twice conventions), so
this parser shares a lot of shape with that one, but several real
differences confirmed against a 594-file, ~286k-hand real export matter
enough to call out:

- Two header shapes coexist: Zoom (fast-fold) tables have no currency
  code ("($0.05/$0.10)"), plain ring-game tables do ("($0.01/$0.02
  USD)").
- An uncontested pot has NO showdown marker at all -- "X collected $Y
  from pot" sits directly in the action stream with nothing announcing
  it, unlike GGPoker's "*** SHOWDOWN ***" which appears even for walks.
  A real showdown instead gets "*** SHOW DOWN ***" (two words).
- Multi-way all-ins name which pot money came from: "collected $X from
  main pot" / "from side pot" (GGPoker's export never distinguishes
  this).
- PokerStars has its own "cash out" feature: "X cashed out the hand for
  $Y | Cash Out Fee $Z" is real, separate money for X with no matching
  "collected from pot" line (verified against a real 3-way all-in hand:
  the side pot's rightful winner had cashed out, so the summary itself
  says "(pot not awarded as player cashed out)" and the pot went
  unclaimed by them -- $Y is their actual take, the fee is already
  reflected in it).
- A sitting-out player still gets a `Seat N: name ($0 in chips) is
  sitting out` line for hands they're not actually dealt into; matching
  core/position.py's existing "active seats vary hand-to-hand" model
  (see its docstring), these are recognised and deliberately NOT added
  to `players` -- they never act and don't occupy a real seat for
  position math that hand.
- A player can voluntarily reveal a card while folding ("folds [As Kd]",
  sometimes just one card) -- worth capturing here (unlike GGPoker) since
  a PokerStars villain's identity is real and persistent, so every extra
  known hole card is real data for that specific opponent's profile.

Every hand in the real sample parses with zero errors; only ~0.04% of
hands (mostly a single-card "shows" or a file truncated mid-write) have
any unmatched line at all. A few genuinely rare lines are deliberately
left unmodeled for the same reason as core/ggpoker_hand_parser.py's
ante/straddle: antes, and a returning player's combined "posts small &
big blinds" -- modeling them would mean teaching every function in
core/stats*.py a new action to exclude from VPIP, for well under 0.5% of
hands.
"""
import re
from datetime import datetime
from models.hand import Hand, Player, Action

class PokerStarsParseError(ValueError):
    pass

_SUIT_SYMBOL = {'c': '♣', 'd': '♦', 'h': '♥', 's': '♠'}


def _card(code: str) -> str:
    rank, suit = code[:-1], code[-1].lower()
    symbol = _SUIT_SYMBOL.get(suit)
    if symbol is None:
        raise PokerStarsParseError(f"Unknown suit in card: {code}")
    return rank + symbol


_ACTION_NAME = {'folds': 'Fold', 'checks': 'Check', 'calls': 'Call', 'bets': 'Bet', 'raises': 'Raise'}
_CUR = r"[$€£]"


class PokerStarsParser:
    HEADER = re.compile(
        r"^PokerStars(?: Zoom)? (?:Hand|Game) #(?P<gid>[^:]+):\s+(?P<gametype>.+?) "
        rf"\((?P<cur>{_CUR})(?P<sb>[\d.]+)/{_CUR}(?P<bb>[\d.]+)(?: [A-Z]+)?\) - "
        r"(?P<date>\d{4}/\d{2}/\d{2}) (?P<time>[\d:]+)")
    # A tournament's blind LEVEL is chip-denominated, never currency-
    # prefixed -- that's the whole reason HEADER above (which requires a
    # currency symbol) never matches a tournament hand, and is exactly
    # why the two are distinguishable at all. Only the buy-in (real
    # money, paid once) carries a currency symbol.
    TOURNAMENT_HEADER = re.compile(
        r"^PokerStars(?: Zoom)? (?:Hand|Game) #(?P<gid>[^:]+): Tournament #(?P<tid>\d+), "
        rf"{_CUR}(?P<buyin>[\d.]+)(?:\+{_CUR}(?P<fee>[\d.]+))?(?: [A-Z]+)? "
        r"(?P<gametype>.+?) - Level \S+ \((?P<sb>[\d.]+)/(?P<bb>[\d.]+)\) - "
        r"(?P<date>\d{4}/\d{2}/\d{2}) (?P<time>[\d:]+)")
    TABLE = re.compile(r"^Table '(?P<name>.+?)' (?P<size>\d+)-max Seat #(?P<button>\d+) is the button$")
    # Stack currency is optional: present for a cash hand ($X in chips),
    # absent for a tournament hand (bare chip count) -- same regex set
    # covers both rather than duplicating every action pattern.
    SEAT = re.compile(rf"^Seat (?P<seat>\d+): (?P<name>.+?) \((?:{_CUR})?(?P<stack>[\d.]+) in chips\)(?P<sitting_out> is sitting out)?$")
    POST = re.compile(
        rf"^(?P<name>.+?): posts (?P<type>small blind|big blind) (?:{_CUR})?(?P<amt>[\d.]+)(?: and is all-in)?$")
    ANTE = re.compile(rf"^(?P<name>.+?): posts the ante {_CUR}[\d.]+$")
    # A returning player makes up both blinds at once as a single combined
    # amount -- which seat/position that money belongs to is ambiguous,
    # so (like the ante above) this is deliberately left unmodeled rather
    # than mislabeling it as either Post SB or Post BB.
    COMBINED_BLINDS = re.compile(rf"^(?P<name>.+?): posts small & big blinds {_CUR}[\d.]+$")
    DEALT = re.compile(r"^Dealt to (?P<name>.+?)(?: \[(?P<c1>\S+) (?P<c2>\S+)\])?$")
    # Run it twice/three times: FLOP/TURN/RIVER repeat with a FIRST/
    # SECOND/THIRD prefix -- only the first run's cards go into `board`,
    # same convention as core/ggpoker_hand_parser.py.
    STREET = re.compile(
        r"^\*\*\* (?:(?P<run>FIRST|SECOND|THIRD) )?(?P<street>FLOP|TURN|RIVER) \*\*\* "
        r"\[(?P<board>.+?)\](?: \[(?P<newcard>.+?)\])?$")
    # "SHOW DOWN" is two words here (GGPoker's is one) -- a pure marker,
    # not a phase boundary: unlike GGPoker, an uncontested pot has NO
    # marker at all before its "collected from pot" line, so winnings
    # are recognised directly in the main action stream regardless of
    # whether this marker showed up first.
    SHOWDOWN_MARKER = re.compile(r"^\*\*\* (?:(?:FIRST|SECOND|THIRD) )?SHOW DOWN \*\*\*$")
    ACTION = re.compile(
        rf"^(?P<name>.+?): (?P<verb>folds|checks|calls|bets|raises)"
        rf"(?: (?:{_CUR})?(?P<amt>[\d.]+))?(?: to (?:{_CUR})?(?P<to>[\d.]+))?(?: and is all-in)?$")
    # A player can voluntarily reveal while folding ("folds [As Kd]", or
    # just one card, "folds [As]") -- distinct from the plain ACTION
    # regex above, which has no card group at all.
    FOLD_SHOW = re.compile(r"^(?P<name>.+?): folds \[(?P<c1>\S+)(?: (?P<c2>\S+))?\]$")
    UNCALLED = re.compile(rf"^Uncalled bet \((?:{_CUR})?(?P<amt>[\d.]+)\) returned to (?P<name>.+?)$")
    SHOWS = re.compile(r"^(?P<name>.+?): shows \[(?P<c1>\S+) (?P<c2>\S+)\](?:\s+\(.+\))?$")
    NO_SHOW = re.compile(r"^(?P<name>.+?): (?:doesn't show hand|mucks hand)$")
    COLLECTED = re.compile(rf"^(?P<name>.+?) collected (?:{_CUR})?(?P<amt>[\d.]+) from (?:main pot|side pot|pot)$")
    # Real, separate money -- see module docstring. The fee is already
    # reflected in the cashed-out amount, not a further deduction.
    CASHED_OUT = re.compile(rf"^(?P<name>.+?) cashed out the hand for {_CUR}(?P<amt>[\d.]+)(?: \|.*)?$")
    POT = re.compile(
        rf"^Total pot (?:{_CUR})?(?P<pot>[\d.]+)"
        rf"(?: Main pot (?:{_CUR})?[\d.]+\. Side pot (?:{_CUR})?[\d.]+\.)? \| Rake (?:{_CUR})?(?P<rake>[\d.]+)")
    BOARD_RECAP = re.compile(r"^(?:FIRST |SECOND |THIRD )?Board \[")
    # Table/connection housekeeping -- never a hand action, no money
    # involved, safe to skip in any phase.
    TABLE_EVENT = re.compile(
        r"^(?:.+?: sits out"
        r"|.+?: is sitting out"
        r"|.+? is (?:connected|disconnected)"
        r"|.+? has timed out(?: while (?:being )?disconnected)?"
        r"|.+? joins the table at seat #\d+"
        r"|.+? leaves the table"
        r"|.+? will be allowed to play after the button)$")

    def parse(self, text: str) -> Hand:
        lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
        if not lines:
            raise PokerStarsParseError('Empty hand text')

        is_tournament = False
        header_match = self.HEADER.match(lines[0])
        if not header_match:
            header_match = self.TOURNAMENT_HEADER.match(lines[0])
            if not header_match:
                raise PokerStarsParseError('Hand header not recognised')
            is_tournament = True
        header = header_match.groupdict()

        players = []
        hole_cards = {}
        actions = []
        board = []
        total_pot = rake = None
        button = None
        table_name = None
        table_size = None
        street = 'PREFLOP'
        winnings = {}
        unmatched = []
        phase = 'play'  # play -> summary

        for line in lines[1:]:
            if line in ('*** HOLE CARDS ***',) or self.SHOWDOWN_MARKER.match(line):
                continue
            if line == '*** SUMMARY ***':
                phase = 'summary'
                continue
            if self.TABLE_EVENT.match(line):
                continue

            if phase == 'play':
                if m := self.TABLE.match(line):
                    table_name = m['name']; table_size = int(m['size']); button = int(m['button']); continue
                if m := self.SEAT.match(line):
                    if not m['sitting_out']:
                        players.append(Player(m['name'], int(m['seat']), float(m['stack'])))
                    continue
                if m := self.POST.match(line):
                    kind = 'Post SB' if m['type'] == 'small blind' else 'Post BB'
                    actions.append(Action(street, m['name'], kind, float(m['amt']))); continue
                if self.ANTE.match(line) or self.COMBINED_BLINDS.match(line):
                    continue
                if m := self.DEALT.match(line):
                    if m['c1'] and m['c2']:
                        hole_cards[m['name']] = [_card(m['c1']), _card(m['c2'])]
                    continue
                if m := self.STREET.match(line):
                    street = m['street']
                    if not m['run'] or m['run'] == 'FIRST':
                        new_cards = m['newcard'].split() if m['newcard'] else m['board'].split()
                        board += [_card(c) for c in new_cards]
                    continue
                if m := self.UNCALLED.match(line):
                    actions.append(Action(street, m['name'], 'Uncalled Return', float(m['amt']))); continue
                if m := self.CASHED_OUT.match(line):
                    winnings[m['name']] = winnings.get(m['name'], 0.0) + float(m['amt']); continue
                if m := self.COLLECTED.match(line):
                    winnings[m['name']] = winnings.get(m['name'], 0.0) + float(m['amt']); continue
                if self.NO_SHOW.match(line):
                    continue
                if m := self.SHOWS.match(line):
                    hole_cards[m['name']] = [_card(m['c1']), _card(m['c2'])]
                    continue
                if m := self.FOLD_SHOW.match(line):
                    if m['c1'] and m['c2']:
                        hole_cards[m['name']] = [_card(m['c1']), _card(m['c2'])]
                    actions.append(Action(street, m['name'], 'Fold', None))
                    continue
                if m := self.ACTION.match(line):
                    verb = m['verb']
                    action_name = _ACTION_NAME[verb]
                    amt_str = m['to'] if verb == 'raises' else m['amt']
                    actions.append(Action(street, m['name'], action_name, float(amt_str) if amt_str else None))
                    continue
                unmatched.append(line)
            else:  # summary
                if m := self.POT.match(line):
                    total_pot = float(m['pot']); rake = float(m['rake']); continue
                if self.BOARD_RECAP.match(line) or line.startswith('Seat ') or line.startswith('Hand was run '):
                    continue
                unmatched.append(line)

        for p in players:
            p.hole_cards = hole_cards.get(p.name, [])

        # strptime, not fromisoformat: PokerStars doesn't always zero-pad
        # the hour (confirmed real example: "2025/05/20 0:00:10").
        dt = datetime.strptime(f"{header['date']} {header['time']}", "%Y/%m/%d %H:%M:%S")

        gametype = header.get('gametype') or "Texas Hold'em"
        if "Hold'em" in gametype:
            gametype = "Texas Hold'em"
        elif "Omaha" in gametype:
            gametype = "Omaha"

        # Prefer the actual posted-blind action amount over the header's
        # stated stakes when both exist -- no mismatch found in this
        # site's real sample, but core.ggpoker_hand_parser's near-
        # identical format DID have real, confirmed cases of a corrupted
        # header stakes field (see its comment), and a posted action
        # amount is real money moving, which can't be wrong the way a
        # text field occasionally is.
        small_blind = float(header['sb'])
        big_blind = float(header['bb'])
        for a in actions:
            if a.action == 'Post SB' and a.amount is not None:
                small_blind = a.amount
                break
        for a in actions:
            if a.action == 'Post BB' and a.amount is not None:
                big_blind = a.amount
                break

        hand = Hand(
            hand_id=header['gid'], game_type=gametype,
            currency=header.get('cur') or '$',
            small_blind=small_blind, big_blind=big_blind, played_at=dt,
            table_name=table_name, table_size=table_size,
            players=players, button_seat=button, board=board, actions=actions,
            total_pot=total_pot, rake=rake, winnings=winnings,
            raw_text=text, source='pokerstars',
            session_type='tournament' if is_tournament else 'cash',
            tournament_id=header.get('tid'),
            buy_in=float(header['buyin']) if is_tournament else None,
            fee=float(header['fee']) if is_tournament and header.get('fee') else (0.0 if is_tournament else None),
        )
        hand.unmatched_lines = unmatched
        return hand


def parse_pokerstars_hand_history(text: str) -> Hand:
    return PokerStarsParser().parse(text)


_HAND_BOUNDARY = re.compile(r"^PokerStars", re.MULTILINE)


def parse_pokerstars_hand_history_file(text: str) -> tuple[list[Hand], list[tuple[str, str]]]:
    """A single export file can contain many hands. Each is parsed in
    isolation so one malformed hand doesn't lose the rest of the file."""
    starts = [m.start() for m in _HAND_BOUNDARY.finditer(text)]
    hands = []
    errors = []
    for i, start in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(text)
        chunk = text[start:end]
        try:
            hands.append(parse_pokerstars_hand_history(chunk))
        except Exception as exc:
            gid_match = re.match(r"PokerStars(?: Zoom)? (?:Hand|Game) #([^:]+):", chunk)
            gid = gid_match.group(1) if gid_match else f"chunk#{i}"
            errors.append((gid, str(exc)))
    return hands, errors
