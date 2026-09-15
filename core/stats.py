"""Preflop statistical analysis over parsed Hand objects.

Amount conventions (confirmed against real iPoker hand histories):
  - Post SB/BB, Call, Bet, Allin: `amount` is the money ADDED by this action.
  - Raise: `amount` is the new TOTAL committed by that player this street (raise-to).
An `Allin` only counts as a raise if the resulting total exceeds the street's
current bet-to-call; otherwise it's a capped/all-in call. `Raise` is always a
real raise, even when it happens to use the player's whole stack.
"""
from dataclasses import dataclass
from models.hand import Hand

VOLUNTARY = {'Call', 'Bet', 'Raise', 'Allin'}


def compute_invested(hand: Hand) -> dict[str, float]:
    """Total amount each player put into the pot this hand, derived purely
    from the validated action log rather than any format-specific pot/bet
    field (the Grosvenor XML format's own `bet=`/`win=` attributes turned
    out not to mean what they first appeared to, so this avoids relying on
    that or any other source-specific accounting).

    Critically, this format does NOT print an explicit "Uncalled bet
    returned" line for the extremely common case of a raise that simply
    goes uncalled because everyone folds — it just silently excludes that
    excess from both `Total pot` and `wins`. Confirmed by tracing real
    hands: a raiser's stated pot share only ever matches their action-log
    total once the standard poker side-pot rule is applied — the largest
    contributor's total is capped down to the second-largest contributor's
    total, with the difference returned uncalled. This one rule also
    correctly subsumes the cases where an explicit "Uncalled Return" line
    IS present (applying it there is a harmless no-op).
    """
    invested: dict[str, float] = {}
    street = None
    committed: dict[str, float] = {}

    def _flush():
        for p, amt in committed.items():
            invested[p] = invested.get(p, 0.0) + amt

    for a in hand.actions:
        if a.street != street:
            _flush()
            committed = {}
            street = a.street
        if a.action in ('Fold', 'Check'):
            continue
        if a.action == 'Uncalled Return':
            committed[a.player] = committed.get(a.player, 0.0) - (a.amount or 0.0)
            continue
        if a.action == 'Raise':
            committed[a.player] = a.amount if a.amount is not None else committed.get(a.player, 0.0)
        else:  # Post SB/BB, Call, Bet, Allin -- all incremental
            committed[a.player] = committed.get(a.player, 0.0) + (a.amount or 0.0)
    _flush()

    if len(invested) >= 2:
        ranked = sorted(invested.values(), reverse=True)
        if ranked[0] > ranked[1]:
            top_player = max(invested, key=invested.get)
            invested[top_player] = ranked[1]
    return invested


@dataclass
class PlayerHandFlags:
    # True unless this player is the BB and "walked" (won uncontested with
    # zero preflop actions of their own) — the VPIP/PFR denominator is
    # "Number of Hands - Number of Walks", since a walked BB never had a
    # decision to make.
    vpip_pfr_opp: bool = True
    vpip: bool = False
    pfr: bool = False
    three_bet_opp: bool = False
    three_bet: bool = False
    faced_3bet_opp: bool = False
    folded_to_3bet: bool = False
    # Narrower than the two above: restricted to the player's OWN open
    # getting re-raised (vs. "faced_3bet_opp", which also counts e.g. a
    # blind cold-folding to someone else's open+3bet before ever entering
    # the pot). This is the population that actually supports "3-bet them
    # relentlessly" — see ui/player_classify.py.
    faced_3bet_as_raiser_opp: bool = False
    folded_to_3bet_as_raiser: bool = False
    four_bet_opp: bool = False
    four_bet: bool = False
    faced_4bet_opp: bool = False
    folded_to_4bet: bool = False
    squeeze_opp: bool = False
    squeeze: bool = False
    squeeze_def_opp: bool = False
    raised_vs_squeeze: bool = False
    folded_to_squeeze: bool = False
    folded_vs_open: bool = False
    limp_opp: bool = False
    limp: bool = False
    limp_call_opp: bool = False
    limp_call: bool = False


def _is_raise_like(action: str, committed_after: float, current_bet_before: float) -> bool:
    if action == 'Raise':
        return True
    if action == 'Allin':
        return committed_after > current_bet_before + 1e-9
    return False


def _preflop_opener(hand: Hand) -> str | None:
    """Who made the first preflop raise, if any."""
    committed: dict[str, float] = {}
    current_bet = 0.0
    for a in hand.actions:
        if a.street != 'PREFLOP':
            continue
        if a.action in ('Post SB', 'Post BB'):
            committed[a.player] = committed.get(a.player, 0.0) + (a.amount or 0.0)
            current_bet = max(current_bet, committed[a.player])
            continue
        if a.action in ('Fold', 'Check', 'Uncalled Return'):
            continue
        current_bet_before = current_bet
        if a.action == 'Raise':
            committed[a.player] = a.amount if a.amount is not None else committed.get(a.player, 0.0)
        else:
            committed[a.player] = committed.get(a.player, 0.0) + (a.amount or 0.0)
        if _is_raise_like(a.action, committed[a.player], current_bet_before):
            return a.player
        current_bet = max(current_bet, committed[a.player])
    return None


def is_3bet_plus_pot(hand: Hand) -> bool:
    """Did preflop see at least a 3-bet (two or more raises)? Lets any
    existing postflop stat be re-aggregated split by this, with no new
    per-action tracking needed — just filter which hands go into the
    aggregate (e.g. "CBet Flop in 3Bet+ Pot")."""
    committed: dict[str, float] = {}
    current_bet = 0.0
    raise_count = 0
    for a in hand.actions:
        if a.street != 'PREFLOP':
            continue
        if a.action in ('Post SB', 'Post BB'):
            committed[a.player] = committed.get(a.player, 0.0) + (a.amount or 0.0)
            current_bet = max(current_bet, committed[a.player])
            continue
        if a.action in ('Fold', 'Check', 'Uncalled Return'):
            continue
        current_bet_before = current_bet
        if a.action == 'Raise':
            committed[a.player] = a.amount if a.amount is not None else committed.get(a.player, 0.0)
        else:
            committed[a.player] = committed.get(a.player, 0.0) + (a.amount or 0.0)
        if _is_raise_like(a.action, committed[a.player], current_bet_before):
            raise_count += 1
            current_bet = max(current_bet, committed[a.player])
    return raise_count >= 2


def analyze_preflop(hand: Hand) -> dict[str, PlayerHandFlags]:
    """Preflop raise-level tracking, generalized one level further than
    3-bet: a "4-bet opportunity" turns out to be exactly the same
    population as "faced a 3-bet" (flg_p_4bet_opp AND flg_p_3bet_def_opp)
    — whoever defends against a 3-bet already has the option to 4-bet,
    fold, or call, so no separate tracking is needed for the opportunity
    itself, only for whether their response was a raise.

    "Faced a 3-bet"/"faced a 4-bet" apply to ANY active player whose
    decision point is the first time they see that raise level live — not
    just the original opener/3-bettor. That breadth is deliberate and was
    checked against real hand counts: plain "Fold to PF 3Bet" / "4Bet PF"
    have to include players who never opened or called before facing the
    re-raise cold (e.g. blinds acting after an open+3-bet already happened
    before their turn), which is a large fraction of the real
    opportunities. The narrower "...After Raise" variant restricted to the
    opener is a different, more specific stat this function doesn't
    compute.
    """
    flags: dict[str, PlayerHandFlags] = {p.name: PlayerHandFlags() for p in hand.players}
    committed: dict[str, float] = {p.name: 0.0 for p in hand.players}
    current_bet = 0.0
    raise_level = 0
    opener = None
    called_since_open = False   # has anyone called while exactly one raise was live
    callers_since_open: set = set()
    squeezer = None             # who made a 3-bet that specifically followed a call (a "squeeze")
    decided_3bet_opp = set()
    decided_faced_3bet = set()
    decided_faced_4bet = set()
    decided_squeeze_opp = set()
    decided_squeeze_def = set()
    decided_first_action = set()  # who has already had their first preflop decision
    limped_players: set = set()   # players whose first decision was a limp
    decided_limp_call = set()
    bb_player = None
    bb_acted = False   # any action beyond posting the blind = a genuine decision

    for a in hand.actions:
        if a.street != 'PREFLOP':
            continue
        f = flags.setdefault(a.player, PlayerHandFlags())
        committed.setdefault(a.player, 0.0)

        if a.action == 'Post BB':
            bb_player = a.player
        if a.action in ('Post SB', 'Post BB'):
            committed[a.player] += a.amount or 0.0
            current_bet = max(current_bet, committed[a.player])
            continue
        if a.player == bb_player:
            bb_acted = True
        if a.action == 'Check':
            continue
        if a.action == 'Uncalled Return':
            continue

        # Limp: a player's first preflop decision, taken before anyone has
        # raised, is a Call (i.e. just matching the big blind rather than
        # raising or folding) — includes the SB completing, which is the
        # same thing by another name. Limp-Call: having limped, the next
        # time this player faces a live raise (someone opened over the
        # limp), did they call it? Both fold-to and re-raise-after-limping
        # are tracked implicitly (limp_call_opp true, limp_call false).
        if raise_level == 0 and a.player not in decided_first_action:
            decided_first_action.add(a.player)
            f.limp_opp = True
            if a.action == 'Call':
                f.limp = True
                limped_players.add(a.player)
        elif a.player in limped_players and a.player not in decided_limp_call and raise_level >= 1:
            f.limp_call_opp = True
            decided_limp_call.add(a.player)
            if a.action == 'Call':
                f.limp_call = True

        if a.action == 'Fold':
            # Opportunity/outcome checks must run before folding is treated
            # as a no-op, since folding IS the outcome fold-to-Nbet detects
            # (and "faced a raise, folded" is still a real Nbet opportunity).
            if raise_level == 1 and a.player not in decided_3bet_opp:
                f.three_bet_opp = True
                f.folded_vs_open = True
                decided_3bet_opp.add(a.player)
                if called_since_open and a.player not in decided_squeeze_opp:
                    f.squeeze_opp = True
                    decided_squeeze_opp.add(a.player)
            if raise_level == 2 and a.player not in decided_faced_3bet:
                f.faced_3bet_opp = True
                decided_faced_3bet.add(a.player)
                f.folded_to_3bet = True
                f.four_bet_opp = True  # same population/decision point as faced_3bet_opp
                if a.player == opener:
                    f.faced_3bet_as_raiser_opp = True
                    f.folded_to_3bet_as_raiser = True
            if raise_level >= 3 and a.player not in decided_faced_4bet:
                f.faced_4bet_opp = True
                decided_faced_4bet.add(a.player)
                f.folded_to_4bet = True
            if (a.player == opener or a.player in callers_since_open) and raise_level == 2 \
                    and squeezer is not None and a.player not in decided_squeeze_def:
                f.squeeze_def_opp = True
                decided_squeeze_def.add(a.player)
                f.folded_to_squeeze = True
            continue

        if a.action in VOLUNTARY:
            f.vpip = True

        current_bet_before = current_bet
        if a.action == 'Raise':
            committed[a.player] = a.amount if a.amount is not None else committed[a.player]
        else:
            committed[a.player] += a.amount or 0.0
        committed_after = committed[a.player]
        raise_like = _is_raise_like(a.action, committed_after, current_bet_before)

        # 3-bet opportunity: this player's first decision while exactly one
        # raise is live ahead of them (i.e. they face the open, not a cold 4-bet).
        if raise_level == 1 and a.player not in decided_3bet_opp:
            f.three_bet_opp = True
            decided_3bet_opp.add(a.player)
            if raise_like:
                f.three_bet = True
            # A squeeze is specifically a 3-bet that follows a call of the
            # open (not just a direct re-raise) — a subset of 3-bet.
            if called_since_open and a.player not in decided_squeeze_opp:
                f.squeeze_opp = True
                decided_squeeze_opp.add(a.player)
                if raise_like:
                    f.squeeze = True

        if a.action == 'Call' and raise_level == 1:
            called_since_open = True
            callers_since_open.add(a.player)

        # Fold-to-3-bet / 4-bet-opportunity: the first time ANY active
        # player's decision point occurs while facing exactly one re-raise
        # (a live 3-bet) — not restricted to the original opener. Confirmed
        # against real hand data: plain "Fold to PF 3Bet" / "4Bet PF" count
        # this broadly (including players who never opened or called before
        # facing the 3-bet cold, e.g. blinds acting after an open+3bet
        # already happened). The narrower "...After Raise" stat for the
        # opener-only case is a different, more specific number.
        if raise_level == 2 and a.player not in decided_faced_3bet:
            f.faced_3bet_opp = True
            decided_faced_3bet.add(a.player)
            f.four_bet_opp = True
            if a.player == opener:
                f.faced_3bet_as_raiser_opp = True
            if a.action == 'Fold':
                f.folded_to_3bet = True
                if a.player == opener:
                    f.folded_to_3bet_as_raiser = True
            elif raise_like:
                f.four_bet = True

        # Fold-to-4-bet: "Fold to PF 4Bet+" covers a
        # player's first decision while facing a 4-bet OR HIGHER (a cold
        # 5-bet, 6-bet, etc. counts too if that's the first time they face
        # such a raise), not only an exact 4-bet.
        if raise_level >= 3 and a.player not in decided_faced_4bet:
            f.faced_4bet_opp = True
            decided_faced_4bet.add(a.player)
            if a.action == 'Fold':
                f.folded_to_4bet = True

        # Squeeze defense: either the original opener, or one of the callers
        # of the open, facing the specific 3-bet that followed a call.
        if (a.player == opener or a.player in callers_since_open) and raise_level == 2 \
                and squeezer is not None and a.player not in decided_squeeze_def:
            f.squeeze_def_opp = True
            decided_squeeze_def.add(a.player)
            if raise_like:
                f.raised_vs_squeeze = True

        if raise_like:
            f.pfr = True
            if raise_level == 1 and called_since_open:
                squeezer = a.player
            raise_level += 1
            if raise_level == 1:
                opener = a.player
            current_bet = max(current_bet, committed_after)

    if bb_player is not None and not bb_acted:
        flags[bb_player].vpip_pfr_opp = False

    return flags


@dataclass
class ShowdownFlags:
    saw_flop: bool = False
    reached_showdown: bool = False
    won_hand: bool = False


def analyze_showdown(hand: Hand) -> dict[str, ShowdownFlags]:
    """Per-player saw-flop / reached-showdown / won-hand flags.

    A showdown happened iff 2+ players never folded anywhere in the hand
    (including players who ran out the board all-in with no further
    actions) — if only one non-folder remains, they won uncontested and
    there was no showdown. "Saw flop" requires the player not to have
    folded preflop AND the hand to have actually reached a flop (an empty
    board means everyone else folded before any flop was dealt at all).
    """
    preflop_folders = {a.player for a in hand.actions if a.street == 'PREFLOP' and a.action == 'Fold'}
    all_folders = {a.player for a in hand.actions if a.action == 'Fold'}
    non_folders = {p.name for p in hand.players if p.name not in all_folders}
    showdown_players = non_folders if len(non_folders) >= 2 else set()

    result = {}
    for p in hand.players:
        result[p.name] = ShowdownFlags(
            saw_flop=p.name not in preflop_folders and bool(hand.board),
            reached_showdown=p.name in showdown_players,
            won_hand=hand.winnings.get(p.name, 0.0) > 0,
        )
    return result


@dataclass
class Aggregate:
    hands: int = 0
    vpip_pfr_opp: int = 0
    vpip: int = 0
    pfr: int = 0
    three_bet_opp: int = 0
    three_bet: int = 0
    faced_3bet_opp: int = 0
    folded_to_3bet: int = 0
    four_bet_opp: int = 0
    four_bet: int = 0
    faced_4bet_opp: int = 0
    folded_to_4bet: int = 0
    squeeze_opp: int = 0
    squeeze: int = 0
    squeeze_def_opp: int = 0
    raised_vs_squeeze: int = 0
    folded_to_squeeze: int = 0
    saw_flop: int = 0
    reached_showdown: int = 0
    won_showdown: int = 0
    won_saw_flop: int = 0
    bb_hands: int = 0
    bb_sum: float = 0.0

    @staticmethod
    def _pct(made: int, opp: int):
        return round(100.0 * made / opp, 2) if opp else None

    @property
    def vpip_pct(self): return self._pct(self.vpip, self.vpip_pfr_opp)

    @property
    def pfr_pct(self): return self._pct(self.pfr, self.vpip_pfr_opp)

    @property
    def three_bet_pct(self): return self._pct(self.three_bet, self.three_bet_opp)

    @property
    def fold_to_3bet_pct(self): return self._pct(self.folded_to_3bet, self.faced_3bet_opp)

    @property
    def four_bet_pct(self): return self._pct(self.four_bet, self.four_bet_opp)

    @property
    def fold_to_4bet_pct(self): return self._pct(self.folded_to_4bet, self.faced_4bet_opp)

    @property
    def squeeze_pct(self): return self._pct(self.squeeze, self.squeeze_opp)

    @property
    def raise_vs_squeeze_pct(self): return self._pct(self.raised_vs_squeeze, self.squeeze_def_opp)

    @property
    def fold_to_squeeze_pct(self): return self._pct(self.folded_to_squeeze, self.squeeze_def_opp)

    @property
    def wtsd_pct(self): return self._pct(self.reached_showdown, self.saw_flop)

    @property
    def wsd_pct(self): return self._pct(self.won_showdown, self.reached_showdown)

    @property
    def wwsf_pct(self): return self._pct(self.won_saw_flop, self.saw_flop)

    @property
    def bb100(self):
        return round(100.0 * self.bb_sum / self.bb_hands, 2) if self.bb_hands else None


def aggregate_player_stats(hands: list[Hand], player_name: str) -> Aggregate:
    agg = Aggregate()
    for hand in hands:
        if player_name not in {p.name for p in hand.players}:
            continue
        flags = analyze_preflop(hand).get(player_name)
        if not flags:
            continue
        agg.hands += 1
        agg.vpip_pfr_opp += flags.vpip_pfr_opp
        agg.vpip += flags.vpip
        agg.pfr += flags.pfr
        agg.three_bet_opp += flags.three_bet_opp
        agg.three_bet += flags.three_bet
        agg.faced_3bet_opp += flags.faced_3bet_opp
        agg.folded_to_3bet += flags.folded_to_3bet
        agg.four_bet_opp += flags.four_bet_opp
        agg.four_bet += flags.four_bet
        agg.faced_4bet_opp += flags.faced_4bet_opp
        agg.folded_to_4bet += flags.folded_to_4bet
        agg.squeeze_opp += flags.squeeze_opp
        agg.squeeze += flags.squeeze
        agg.squeeze_def_opp += flags.squeeze_def_opp
        agg.raised_vs_squeeze += flags.raised_vs_squeeze
        agg.folded_to_squeeze += flags.folded_to_squeeze

        sd = analyze_showdown(hand).get(player_name)
        if sd:
            agg.saw_flop += sd.saw_flop
            agg.reached_showdown += sd.reached_showdown
            agg.won_showdown += sd.reached_showdown and sd.won_hand
            agg.won_saw_flop += sd.saw_flop and sd.won_hand

        # Convert this hand's profit to bb-units *before* averaging, not
        # after — averaging raw £ profit across hands played at different
        # stakes silently skews the result (this exact bug was found and
        # fixed once already in the legacy dashboard).
        if hand.big_blind:
            invested = compute_invested(hand).get(player_name, 0.0)
            profit = hand.winnings.get(player_name, 0.0) - invested
            agg.bb_sum += profit / hand.big_blind
            agg.bb_hands += 1
    return agg


@dataclass
class AggressionCounts:
    bet_raise: int = 0
    call: int = 0
    fold: int = 0

    def add(self, other: "AggressionCounts") -> "AggressionCounts":
        return AggressionCounts(self.bet_raise + other.bet_raise, self.call + other.call, self.fold + other.fold)

    @property
    def af(self):
        return round(self.bet_raise / self.call, 2) if self.call else None

    @property
    def afq_pct(self):
        denom = self.bet_raise + self.call + self.fold
        return round(100.0 * self.bet_raise / denom, 2) if denom else None


def analyze_aggression(hand: Hand) -> dict[str, dict[str, AggressionCounts]]:
    """Per-player, per-street counts of aggressive (bet/raise) vs passive
    (call) vs folding actions, feeding AF (bet+raise / call) and AFq
    (bet+raise / all non-check actions). Checks are excluded from both, per
    the standard industry definition, verified against this project's own
    hand histories."""
    result: dict[str, dict[str, AggressionCounts]] = {s: {} for s in ('PREFLOP', 'FLOP', 'TURN', 'RIVER')}
    committed: dict[tuple, float] = {}
    current_bet: dict[str, float] = {s: 0.0 for s in result}

    for a in hand.actions:
        counts = result[a.street].setdefault(a.player, AggressionCounts())
        key = (a.street, a.player)

        if a.action in ('Post SB', 'Post BB'):
            committed[key] = committed.get(key, 0.0) + (a.amount or 0.0)
            current_bet[a.street] = max(current_bet[a.street], committed[key])
            continue
        if a.action == 'Check':
            continue
        if a.action == 'Uncalled Return':
            continue
        if a.action == 'Fold':
            counts.fold += 1
            continue

        current_bet_before = current_bet[a.street]
        if a.action == 'Raise':
            committed[key] = a.amount if a.amount is not None else committed.get(key, 0.0)
        else:
            committed[key] = committed.get(key, 0.0) + (a.amount or 0.0)
        committed_after = committed[key]

        if a.action == 'Bet' or _is_raise_like(a.action, committed_after, current_bet_before):
            counts.bet_raise += 1
            current_bet[a.street] = max(current_bet[a.street], committed_after)
        else:
            counts.call += 1
    return result


def aggregate_aggression_stats(hands: list[Hand], player_name: str) -> dict[str, AggressionCounts]:
    """Returns per-street totals (PREFLOP/FLOP/TURN/RIVER) plus a 'TOTAL'
    key that's the postflop-only sum (FLOP+TURN+RIVER), matching the
    standard "Total AF"/"Total AFq" definition, which excludes preflop."""
    totals = {s: AggressionCounts() for s in ('PREFLOP', 'FLOP', 'TURN', 'RIVER')}
    for hand in hands:
        if player_name not in {p.name for p in hand.players}:
            continue
        per_street = analyze_aggression(hand)
        for street, players in per_street.items():
            c = players.get(player_name)
            if c:
                totals[street] = totals[street].add(c)
    totals['TOTAL'] = totals['FLOP'].add(totals['TURN']).add(totals['RIVER'])
    return totals
