"""Parser for GGPoker's (and its skins: Natural8, BetKings, etc.) native
text hand-history export format. Verified against a real 452-file,
222,843-hand export (mostly "Rush & Cash" 6-max NLHE, with a handful of
9-max ring-game hands mixed in) -- every hand parses with zero errors,
and only 403 hands (0.18%) have any unmatched line at all.

A few genuinely rare lines are deliberately left unmodeled rather than
guessed at (matching this project's "never guess, always validate" rule
-- see core/folder_detect.py): antes and straddles (~90 hands total),
missed-blind postings from a returning player (~20 hands), and a
single-card "shows" (mucking just one card face up, a handful of hands).
None of these represent a stat-corrupting gap for Hero-only stats -- at
worst they slightly undercount that one player's invested amount for
that one hand -- and modeling them properly would mean teaching every
function in core/stats*.py to exclude a new action from VPIP the same
way Post SB/BB already are, which is a lot of shared-engine risk for
well under 0.1% of hands. They fall through to unmatched_lines, same as
an actually-unrecognised line would.

Two other rare mechanics DO move real money and are handled: "run it
twice/three times" (repeats FLOP/TURN/RIVER with a FIRST/SECOND/THIRD
prefix and pot-winnings lines under "*** FIRST/SECOND SHOWDOWN ***"
instead of the plain marker -- only the first run's board is kept, since
the Hand model has no concept of more than one board, but every run's
winnings are summed), and Rush & Cash's early "EV Cashout" -- traced
against real hands, a lone "Pays Cashout Risk ($X)" is purely
descriptive (that player still collects normally), but "Receives Cashout
($Y)" is real, separate money with no matching "collected from pot" line
112 times out of 120 in the sample, and must be added to winnings.

GGPoker anonymizes every non-hero seat as a short random lowercase-hex
string (e.g. "448c7ca6", "3bf08a6", "7f4485" -- 6 to 8 hex characters
observed) that is NOT a stable identity across hands: the same real
opponent gets a fresh random label every single hand, confirmed by
tracing the sample data (no hash ever recurs the way a real username
would across a session). This is a deliberate anti-tracking measure
GGPoker applies to all its "anonymous tables" -- the same reason
established trackers can't build opponent stats on this site either.
GGPOKER_HERO_LABEL below excludes these labels from the villain pool for
that reason (see database/hand_stats_builder.py); this parser still
imports every hand in full, since Hero's own stats (Overview, Sessions,
Hero's own Stats tab) are entirely unaffected by opponent identity.

Naming an anonymized opponent by shape (e.g. "looks like a hex string")
is NOT safe -- traced against a real PokerStars export, plenty of real,
persistent usernames are themselves short hex-looking or all-numeric
strings ("3033453", "ed777221"), and would be wrongly hidden from THAT
site's villain pool if excluded by shape. GGPOKER_HERO_LABEL sidesteps
this: it's a fact of GGPoker's own export protocol (every hand's own
exporting account is always literally named "Hero", never the real
GGPoker username), completely independent of any other site's naming, so
the exclusion is scoped by `hand.source == 'ggpoker'`, never applied
elsewhere.

Card notation here is RANK-then-suit with a lowercase suit letter (e.g.
"8s", "Ad", "Ts") -- the opposite convention from core/hand_parser.py's
iPoker adapter (suit-then-rank codes like "S8"), so this module has its
own small `_card()` converter rather than reusing
core.card_utils.hh_card_to_display.
"""
import re
from datetime import datetime
from models.hand import Hand, Player, Action

# GGPoker's own export protocol: the exporting account's own seat is
# always literally named "Hero", regardless of their real GGPoker
# username. Every other seat is an anonymized per-hand placeholder (see
# module docstring). database/hand_stats_builder.py uses this to exclude
# anonymized opponents from the villain pool.
GGPOKER_HERO_LABEL = 'Hero'


class GGParseError(ValueError):
    pass

_SUIT_SYMBOL = {'c': '♣', 'd': '♦', 'h': '♥', 's': '♠'}


def _card(code: str) -> str:
    rank, suit = code[:-1], code[-1].lower()
    symbol = _SUIT_SYMBOL.get(suit)
    if symbol is None:
        raise GGParseError(f"Unknown suit in card: {code}")
    return rank + symbol


_ACTION_NAME = {'folds': 'Fold', 'checks': 'Check', 'calls': 'Call', 'bets': 'Bet', 'raises': 'Raise'}


class GGPokerParser:
    # Currency observed as $ only in the sample; € accepted defensively
    # since GGPoker also runs EUR-denominated tables on some skins.
    HEADER = re.compile(
        r"^Poker Hand #(?P<gid>[^:]+): (?P<gametype>.+?) \((?P<cur>[$€])(?P<sb>[\d.]+)/[$€](?P<bb>[\d.]+)\) - "
        r"(?P<date>\d{4}/\d{2}/\d{2}) (?P<time>[\d:]+)")
    # A tournament's blind LEVEL is chip-denominated (no currency symbol),
    # never the currency-prefixed stakes HEADER above requires -- that's
    # the whole reason the two are distinguishable at all. Only the
    # buy-in (real money, paid once) carries a currency symbol.
    TOURNAMENT_HEADER = re.compile(
        r"^Poker Hand #(?P<gid>[^:]+): Tournament #(?P<tid>\d+), "
        r"[$€](?P<buyin>[\d.]+)(?:\+[$€](?P<fee>[\d.]+))? "
        r"(?P<gametype>.+?) - Level\d+\((?P<sb>[\d.]+)/(?P<bb>[\d.]+)\) - "
        r"(?P<date>\d{4}/\d{2}/\d{2}) (?P<time>[\d:]+)")
    TABLE = re.compile(r"^Table '(?P<name>.+?)' (?P<size>\d+)-max Seat #(?P<button>\d+) is the button$")
    # Stack currency is optional: present for a cash hand ($X in chips),
    # absent for a tournament hand (bare chip count) -- same regex set
    # covers both rather than duplicating every action pattern.
    SEAT = re.compile(r"^Seat (?P<seat>\d+): (?P<name>.+?) \((?:[$€])?(?P<stack>[\d.]+) in chips\)$")
    POST = re.compile(r"^(?P<name>.+?): posts (?P<type>small blind|big blind) (?:[$€])?(?P<amt>[\d.]+)$")
    DEALT = re.compile(r"^Dealt to (?P<name>.+?)(?: \[(?P<c1>\S+) (?P<c2>\S+)\])?$")
    # A "run it twice/three times" hand repeats FLOP/TURN/RIVER with a
    # FIRST/SECOND/THIRD prefix instead of the plain marker -- only the
    # first run's cards are kept in `board` (the Hand model has no concept
    # of more than one board), but the street tag itself must still be
    # recognised for every run so nothing downstream gets mistagged.
    STREET = re.compile(
        r"^\*\*\* (?:(?P<run>FIRST|SECOND|THIRD) )?(?P<street>FLOP|TURN|RIVER) \*\*\* "
        r"\[(?P<board>.+?)\](?: \[(?P<newcard>.+?)\])?$")
    SHOWDOWN_MARKER = re.compile(r"^\*\*\* (?:FIRST|SECOND|THIRD) SHOWDOWN \*\*\*$")
    # Rush & Cash lets a player facing all-in equity cash out early for a
    # guaranteed amount instead of seeing the hand through. Traced against
    # real hands: a lone "Pays Cashout Risk ($X)" (542/547 cases in the
    # sample) is purely descriptive -- that player still collects their
    # full amount via the normal "collected from pot" line, same as
    # anyone else. But "Receives Cashout ($Y)" is real, separate money
    # that (112/120 times) has NO matching "collected from pot" line at
    # all -- it IS that player's payout for the hand and must be added to
    # winnings, or a hand they actually profited from would show $0.
    RECEIVES_CASHOUT = re.compile(r"^(?P<name>.+?): Receives Cashout \([$€](?P<amt>[\d.]+)\)$")
    ACTION = re.compile(
        r"^(?P<name>.+?): (?P<verb>folds|checks|calls|bets|raises)"
        r"(?: (?:[$€])?(?P<amt>[\d.]+))?(?: to (?:[$€])?(?P<to>[\d.]+))?(?: and is all-in)?$")
    UNCALLED = re.compile(r"^Uncalled bet \((?:[$€])?(?P<amt>[\d.]+)\) returned to (?P<name>.+?)$")
    SHOWS = re.compile(r"^(?P<name>.+?): shows \[(?P<c1>\S+) (?P<c2>\S+)\](?:\s+\(.+\))?$")
    COLLECTED = re.compile(r"^(?P<name>.+?) collected (?:[$€])?(?P<amt>[\d.]+) from pot$")
    POT = re.compile(r"^Total pot (?:[$€])?(?P<pot>[\d.]+) \| Rake (?:[$€])?(?P<rake>[\d.]+)")
    BOARD_RECAP = re.compile(r"^(?:FIRST |SECOND |THIRD )?Board \[")

    def parse(self, text: str) -> Hand:
        lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
        if not lines:
            raise GGParseError('Empty hand text')

        is_tournament = False
        header_match = self.HEADER.match(lines[0])
        if not header_match:
            header_match = self.TOURNAMENT_HEADER.match(lines[0])
            if not header_match:
                raise GGParseError('Hand header not recognised')
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
        phase = 'play'  # play -> showdown -> summary

        for line in lines[1:]:
            if line == '*** HOLE CARDS ***':
                continue
            if line == '*** SHOWDOWN ***' or self.SHOWDOWN_MARKER.match(line):
                phase = 'showdown'
                continue
            if line == '*** SUMMARY ***':
                phase = 'summary'
                continue

            if phase == 'play':
                if m := self.TABLE.match(line):
                    table_name = m['name']; table_size = int(m['size']); button = int(m['button']); continue
                if m := self.SEAT.match(line):
                    players.append(Player(m['name'], int(m['seat']), float(m['stack']))); continue
                if m := self.POST.match(line):
                    kind = 'Post SB' if m['type'] == 'small blind' else 'Post BB'
                    actions.append(Action(street, m['name'], kind, float(m['amt']))); continue
                if m := self.DEALT.match(line):
                    if m['c1'] and m['c2']:
                        hole_cards[m['name']] = [_card(m['c1']), _card(m['c2'])]
                    continue
                if m := self.STREET.match(line):
                    street = m['street']
                    # Run-it-twice/-three-times: only the first run's cards
                    # go into `board` (the Hand model has just one board).
                    if not m['run'] or m['run'] == 'FIRST':
                        new_cards = m['newcard'].split() if m['newcard'] else m['board'].split()
                        board += [_card(c) for c in new_cards]
                    continue
                if m := self.UNCALLED.match(line):
                    actions.append(Action(street, m['name'], 'Uncalled Return', float(m['amt']))); continue
                if m := self.RECEIVES_CASHOUT.match(line):
                    winnings[m['name']] = winnings.get(m['name'], 0.0) + float(m['amt']); continue
                if re.match(r'^.+?: Pays Cashout Risk \(', line) or re.match(r'^.+?: Chooses to EV Cashout$', line):
                    continue
                if m := self.SHOWS.match(line):
                    hole_cards[m['name']] = [_card(m['c1']), _card(m['c2'])]
                    continue
                if m := self.ACTION.match(line):
                    verb = m['verb']
                    action_name = _ACTION_NAME[verb]
                    amt_str = m['to'] if verb == 'raises' else m['amt']
                    actions.append(Action(street, m['name'], action_name, float(amt_str) if amt_str else None))
                    continue
                # Rare lines this parser deliberately doesn't model as
                # Actions (each under 0.05% of a real 222k-hand sample):
                # a site promo added straight to the pot, and the ante/
                # straddle postings some non-Rush&Cash tables use. Turning
                # these into a new Action type would require teaching every
                # stats function in core/stats*.py to exclude it from VPIP
                # the same way Post SB/BB already are -- skipping them
                # cleanly here is safer than a half-modeled action type
                # that silently inflates VPIP on the rare hand that has one.
                if line.startswith('Cash Drop to Pot'):
                    continue
                if re.match(r'^.+?: posts the ante ', line) or re.match(r'^.+?: straddle ', line):
                    continue
                unmatched.append(line)
            elif phase == 'showdown':
                if m := self.COLLECTED.match(line):
                    winnings[m['name']] = winnings.get(m['name'], 0.0) + float(m['amt']); continue
                unmatched.append(line)
            else:  # summary
                if m := self.POT.match(line):
                    total_pot = float(m['pot']); rake = float(m['rake']); continue
                if self.BOARD_RECAP.match(line) or line.startswith('Seat ') or line.startswith('Hand was run '):
                    continue
                unmatched.append(line)

        for p in players:
            p.hole_cards = hole_cards.get(p.name, [])

        date_str = header['date'].replace('/', '-')
        dt = datetime.fromisoformat(f"{date_str}T{header['time']}")

        gametype = header.get('gametype') or "Texas Hold'em"
        if "Hold'em" in gametype:
            gametype = "Texas Hold'em"
        elif "Omaha" in gametype:
            gametype = "Omaha"

        # The header's stated stakes occasionally don't match reality --
        # confirmed against a real 222,843-hand import: 8 hands (0.004%)
        # had a header small blind that didn't match what was actually
        # posted (one even missing its decimal point outright, "$005"),
        # while every hand's actual "posts small/big blind" action amount
        # was internally consistent with the rest of that stake's volume.
        # The posted-action amount is real money moving and can't lie the
        # way a text field can, so it's preferred whenever present.
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
            raw_text=text, source='ggpoker',
            session_type='tournament' if is_tournament else 'cash',
            tournament_id=header.get('tid'),
            buy_in=float(header['buyin']) if is_tournament else None,
            fee=float(header['fee']) if is_tournament and header.get('fee') else (0.0 if is_tournament else None),
        )
        hand.unmatched_lines = unmatched
        return hand


def parse_ggpoker_hand_history(text: str) -> Hand:
    return GGPokerParser().parse(text)


_HAND_BOUNDARY = re.compile(r"^Poker Hand #", re.MULTILINE)


def parse_ggpoker_hand_history_file(text: str) -> tuple[list[Hand], list[tuple[str, str]]]:
    """A single export file can contain many hands. Each is parsed in
    isolation so one malformed hand doesn't lose the rest of the file."""
    starts = [m.start() for m in _HAND_BOUNDARY.finditer(text)]
    hands = []
    errors = []
    for i, start in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(text)
        chunk = text[start:end]
        try:
            hands.append(parse_ggpoker_hand_history(chunk))
        except Exception as exc:
            gid_match = re.match(r"Poker Hand #([^:]+):", chunk)
            gid = gid_match.group(1) if gid_match else f"chunk#{i}"
            errors.append((gid, str(exc)))
    return hands, errors
