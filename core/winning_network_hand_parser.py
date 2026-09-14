"""Parser for the Winning Network's (Americas Cardroom/Black Chip Poker/
etc.) native text hand-history export format. Verified against a real
25-file, 30,863-hand corpus (245 distinct tournaments, plus real cash
hands from the same account) — every header/action/summary shape below
is quoted from that real data, not guessed, and every one of those
30,863 hands parses with zero errors.

Distinctive shape, compared to the other three parsers in this project:

- Cash and tournament hands share the SAME format, distinguished only by
  the second header line: a tournament hand's line inserts "Tourney"
  before "Texas Holdem" and a "(MTT Tournament #N) (Buyin $X + $Y)"
  segment; a cash hand's line has neither. Stakes/stack/bet amounts are
  bare chip integers for a tournament, `$`-prefixed decimals for cash —
  HEADER's regex groups are the same either way, just with an optional
  leading `$` on every amount.
- Card notation is rank-then-suit lowercase ("Ts", "Kc", "8s") — the same
  convention as core/ggpoker_hand_parser.py, so this module's `_card()`
  is identical in shape to that one (kept as its own copy rather than a
  shared import, matching that module's own stated convention).
- Hero identification: the exporting account's own seat is always
  literally "Hero"; every opponent is an anonymized "Player1".."PlayerN"
  RE-NUMBERED BY SEAT ORDER EVERY HAND (confirmed: the same real person
  gets a different PlayerN label from one hand to the next once anyone
  at the table busts/leaves and seat numbering shifts) — the exact same
  non-identity-tracking shape as core.ggpoker_hand_parser.GGPOKER_HERO_LABEL,
  so these hands are excluded from the villain pool the same way
  (database/hand_stats_builder.py, scoped by `hand.source == 'winning_network'`).
- No "Uncalled bet returned" line exists anywhere in this format, even
  though a raise that goes uncalled is common — core.stats.compute_invested
  already handles this generically (it caps the largest total-invested
  player down to the second-largest, which is correct with or without an
  explicit return line — see that function's own docstring, written for
  core/hand_parser.py's iPoker adapter, which has the identical gap), so
  nothing extra is needed here.
- A handful of real, rare mechanics are recognised but deliberately not
  modeled as Actions or winnings (matching this project's "never guess"
  rule — see core/ggpoker_hand_parser.py's own module docstring for the
  same policy applied to GGPoker's ante/straddle/cashout gaps): antes,
  a disconnected player's auto-fold notice (the fold itself is still a
  real, separately-printed Fold action), and cash tables' "cash-out"
  feature lines (Cash-out Premium/probabilty/Cashout Amount) — whether
  a WPN cashout is separate real money the way GGPoker's is wasn't
  confirmed against a real example showing the accompanying summary
  accounting, so it's left unmodeled rather than guessed at.
"""
import re
from datetime import datetime
from models.hand import Hand, Player, Action

# The exporting account's own seat is always literally "Hero" in this
# format's own export protocol, never the real Winning Network username
# -- same convention as GGPoker (see module docstring and
# core.ggpoker_hand_parser.GGPOKER_HERO_LABEL).
WINNING_NETWORK_HERO_LABEL = 'Hero'


class WinningNetworkParseError(ValueError):
    pass


_SUIT_SYMBOL = {'c': '♣', 'd': '♦', 'h': '♥', 's': '♠'}


def _card(code: str) -> str:
    rank, suit = code[:-1], code[-1].lower()
    symbol = _SUIT_SYMBOL.get(suit)
    if symbol is None:
        raise WinningNetworkParseError(f"Unknown suit in card: {code}")
    return rank + symbol


def _cards(inner: str) -> list[str]:
    """Cards inside a "[ Ts, Kc ]"-style bracket are comma-space
    separated (unlike GGPoker/PokerStars' plain-space-separated board
    lists), so this splits on ", " rather than whitespace."""
    return [_card(c) for c in inner.split(', ')]


_ACTION_NAME = {'folds': 'Fold', 'checks': 'Check', 'calls': 'Call', 'bets': 'Bet', 'raises': 'Raise'}
_MONTH = {m: i + 1 for i, m in enumerate(
    ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'])}


class WinningNetworkParser:
    # sb/bb/buyin/fee amounts all optionally `$`-prefixed: bare chip
    # counts for a tournament, currency-decimal for cash. The timezone
    # abbreviation (EDT/WET/...) is matched but not captured -- this
    # project already treats hand timestamps as naive/local elsewhere
    # (see core/pokerstars_hand_parser.py, which drops its own bracketed
    # second timestamp the same way).
    # The tournament-type label before "Tournament #" varies (confirmed
    # real values: "MTT", "SNG JackPot") -- matched generically rather
    # than enumerated, since the tournament id/buy-in/fee that follow are
    # all that's actually needed.
    HEADER = re.compile(
        r"^\$?(?P<sb>[\d.]+)/\$?(?P<bb>[\d.]+) "
        r"(?:Tourney )?Texas Holdem Game Table \(NL\)"
        r"(?: \(.+? Tournament #(?P<tid>\d+)\) \(Buyin \$(?P<buyin>[\d.]+)(?: \+ \$(?P<fee>[\d.]+))?\))?"
        r" - \w+ (?P<month>\w+) (?P<day>\d+) (?P<time>[\d:]+) \w+ (?P<year>\d+)$")
    TABLE = re.compile(r"^Table (?P<name>.+?) \(Real Money\) -- Seat (?P<button>\d+) is the button$")
    SEAT = re.compile(r"^Seat (?P<seat>\d+): (?P<name>.+?) \(\$?(?P<stack>[\d.]+)\)$")
    POST = re.compile(r"^(?P<name>.+?) posts (?P<type>small blind|big blind) \(\$?(?P<amt>[\d.]+)\)$")
    ANTE = re.compile(r"^(?P<name>.+?) posts ante \(\$?[\d.]+\)$")
    DEALT = re.compile(r"^Dealt to (?P<name>.+?)(?: \[ (?P<cards>.+?) \])?$")
    STREET = re.compile(r"^\*\* Dealing (?P<street>Flop|Turn|River) \*\*\s*:\s*\[ (?P<cards>.+?) \]$")
    ACTION = re.compile(
        r"^(?P<name>.+?) (?P<verb>folds|checks|calls|bets|raises)"
        r"(?: \(?\$?(?P<amt>[\d.]+)\)?)?(?: to \$?(?P<to>[\d.]+))?\s*$")
    # Purely informational -- the Summary block's own "bet <n>, collected
    # <n>" line is what winnings/pot totals are actually derived from.
    POT_CREATION = re.compile(r"^Creating (?:Main Pot|Side Pot \d+) with")
    DISCONNECTED = re.compile(r"^.+? could not respond in time\.\(disconnected\)$")
    ALL_IN_MARKER = re.compile(r"^.+? is all-[Ii]n\.$")
    # Cash tables' early-cashout feature -- see module docstring for why
    # this is recognised-and-skipped rather than modeled as winnings.
    CASHOUT_LINE = re.compile(
        r"^.+? (?:Cash-out Premium % is|opted for cash-out|probabilty is|Cashout Amount is)")
    SUMMARY_MARKER = '** Summary **'
    POT_LINE = re.compile(r"^Main Pot: ")
    POT_AMOUNT = re.compile(r"(?:Main Pot|Side Pot \d+): \$?([\d.]+)")
    RAKE = re.compile(r"Rake: \$([\d.]+)")
    BOARD_LINE = re.compile(r"^Board: \[ (?P<cards>.+?) \]$")
    BALANCE_FOLDED = re.compile(r"^(?P<name>.+?) balance \$?[\d.]+, (?:lost \$?[\d.]+|didn't bet) \(folded\)$")
    BALANCE_SITS_OUT = re.compile(r"^(?P<name>.+?) balance \$?[\d.]+, sits out$")
    BALANCE_WON = re.compile(
        r"^(?P<name>.+?) balance \$?[\d.]+, bet \$?[\d.]+, collected \$?(?P<amt>[\d.]+), net \+\$?[\d.]+"
        r"(?:\[ (?P<cards>.+?) \] \[ .+? \])?$")
    BALANCE_LOST = re.compile(
        r"^(?P<name>.+?) balance \$?[\d.]+, lost \$?[\d.]+\[ (?P<cards>.+?) \] \[ .+? \]$")

    def parse(self, text: str) -> Hand:
        lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
        if len(lines) < 2:
            raise WinningNetworkParseError('Empty hand text')

        hid_match = re.match(r"^\*\*\*\*\* Hand History For Game (?P<hid>[a-z0-9]+) \*\*\*\*\*$", lines[0])
        if not hid_match:
            raise WinningNetworkParseError('Hand header not recognised')
        header_match = self.HEADER.match(lines[1])
        if not header_match:
            raise WinningNetworkParseError('Stakes/date header line not recognised')
        header = header_match.groupdict()
        is_tournament = header.get('tid') is not None

        players = []
        hole_cards = {}
        actions = []
        board = []
        total_pot = rake = None
        button = None
        table_name = None
        street = 'PREFLOP'
        winnings = {}
        unmatched = []
        phase = 'play'  # play -> summary

        for line in lines[2:]:
            if line == '** Dealing down cards **' or self.ALL_IN_MARKER.match(line):
                continue
            if line == self.SUMMARY_MARKER:
                phase = 'summary'
                continue
            if self.POT_CREATION.match(line) or self.DISCONNECTED.match(line) or self.CASHOUT_LINE.match(line):
                continue

            if phase == 'play':
                if m := self.TABLE.match(line):
                    table_name = m['name']; button = int(m['button']); continue
                if m := self.SEAT.match(line):
                    players.append(Player(m['name'], int(m['seat']), float(m['stack']))); continue
                if line.startswith('Total number of players'):
                    continue
                if m := self.POST.match(line):
                    kind = 'Post SB' if m['type'] == 'small blind' else 'Post BB'
                    actions.append(Action(street, m['name'], kind, float(m['amt']))); continue
                if self.ANTE.match(line):
                    continue
                if m := self.DEALT.match(line):
                    if m['cards']:
                        hole_cards[m['name']] = _cards(m['cards'])
                    continue
                if m := self.STREET.match(line):
                    street = m['street'].upper()
                    board.extend(_cards(m['cards']))
                    continue
                if m := self.ACTION.match(line):
                    verb = m['verb']
                    action_name = _ACTION_NAME[verb]
                    amt_str = m['to'] if verb == 'raises' else m['amt']
                    actions.append(Action(street, m['name'], action_name, float(amt_str) if amt_str else None))
                    continue
                unmatched.append(line)
            else:  # summary
                if self.POT_LINE.match(line):
                    total_pot = sum(float(a) for a in self.POT_AMOUNT.findall(line))
                    rake_match = self.RAKE.search(line)
                    if rake_match:
                        rake = float(rake_match.group(1))
                    continue
                if m := self.BOARD_LINE.match(line):
                    if not board:
                        board = _cards(m['cards'])
                    continue
                if self.BALANCE_FOLDED.match(line) or self.BALANCE_SITS_OUT.match(line):
                    continue
                if m := self.BALANCE_WON.match(line):
                    winnings[m['name']] = winnings.get(m['name'], 0.0) + float(m['amt'])
                    if m['cards']:
                        hole_cards[m['name']] = _cards(m['cards'])
                    continue
                if m := self.BALANCE_LOST.match(line):
                    hole_cards[m['name']] = _cards(m['cards'])
                    continue
                unmatched.append(line)

        for p in players:
            p.hole_cards = hole_cards.get(p.name, [])

        month = _MONTH.get(header['month'], 1)
        dt = datetime(int(header['year']), month, int(header['day']),
                      *(int(x) for x in header['time'].split(':')))

        hand = Hand(
            hand_id=hid_match['hid'], game_type="Texas Hold'em",
            currency='$',  # every real sample in this format is USD-denominated
            small_blind=float(header['sb']), big_blind=float(header['bb']), played_at=dt,
            table_name=table_name, button_seat=button, board=board, actions=actions,
            total_pot=total_pot, rake=rake, winnings=winnings,
            raw_text=text, source='winning_network',
            players=players,
            session_type='tournament' if is_tournament else 'cash',
            tournament_id=header.get('tid'),
            buy_in=float(header['buyin']) if is_tournament else None,
            fee=float(header['fee']) if is_tournament and header.get('fee') else (0.0 if is_tournament else None),
        )
        hand.unmatched_lines = unmatched
        return hand


def parse_winning_network_hand_history(text: str) -> Hand:
    return WinningNetworkParser().parse(text)


_HAND_BOUNDARY = re.compile(r"^\*\*\*\*\* Hand History For Game ", re.MULTILINE)


def parse_winning_network_hand_history_file(text: str) -> tuple[list[Hand], list[tuple[str, str]]]:
    """A single export file can contain many hands. Each is parsed in
    isolation so one malformed hand doesn't lose the rest of the file."""
    starts = [m.start() for m in _HAND_BOUNDARY.finditer(text)]
    hands = []
    errors = []
    for i, start in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(text)
        chunk = text[start:end]
        try:
            hands.append(parse_winning_network_hand_history(chunk))
        except Exception as exc:
            gid_match = re.match(r"\*\*\*\*\* Hand History For Game (?P<hid>[a-z0-9]+) \*\*\*\*\*", chunk)
            gid = gid_match['hid'] if gid_match else f"chunk#{i}"
            errors.append((gid, str(exc)))
    return hands, errors
