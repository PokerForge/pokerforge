"""Postflop continuation-bet and check-raise analysis, per street.

Builds on the same amount conventions validated in core/stats.py (Raise =
absolute new total this street; Call/Bet/Allin = incremental). A street's
"aggressor" carries forward to the next street ONLY if the same player who
already held that status is also the one who bet/raised THIS street — a
genuine continuation. If the street checks through, OR if a different player
takes over the betting lead instead (e.g. a float/donk bet), the next
street's aggressor resets to None. This was confirmed against real PT4
output (a 364k-hand, 141-villain sample): PT4's own "CBet Turn" formula
description is literally "...given that he continuation bet the flop", and
testing this exact "chain" rule against that sample closed a real ~1-5pp gap
that two other candidate models (an aggressor that persists through any
checked-through street, and one pinned to the preflop raiser all hand) both
made WORSE, not better. This deliberately excludes "delayed c-bet" (aggressor
who checked one street then bets the next) as a separate, unbuilt stat.

Note: fold-to-check-raise is tracked per street as a whole (did *a* check-raise
happen this street, and did the original bettor fold when facing it) rather
than pairing each individual raise with its specific victim. This is exact for
the common single-check-raise case and only under/over-counts in rarer
multi-way double-check-raise spots on the same street.
"""
from dataclasses import dataclass
from models.hand import Hand
from core.stats import _is_raise_like, is_3bet_plus_pot
from core.position import has_position_on

STREETS = ('FLOP', 'TURN', 'RIVER')


@dataclass
class StreetFlags:
    reached: bool = False
    cbet_opp: bool = False
    cbet: bool = False
    faced_cbet_opp: bool = False
    folded_to_cbet: bool = False
    xr_opp: bool = False
    xr: bool = False
    faced_xr_opp: bool = False
    folded_to_xr: bool = False
    donk_opp: bool = False
    donk: bool = False
    faced_donk_opp: bool = False
    folded_to_donk: bool = False
    # Generic fold-to-bet-level: doesn't care who made the bet/raise or
    # whether they'd checked before, unlike cbet/xr/donk above. PT4's own
    # "Fold to F 2Bet" is explicitly this broader thing, not check-raise-only.
    face_bet_opp: bool = False
    folded_to_bet: bool = False
    face_2bet_opp: bool = False
    folded_to_2bet: bool = False
    face_3bet_opp: bool = False
    folded_to_3bet: bool = False
    # "Float": called the previous street's aggressor with position on them,
    # then bets when checked to on this street.
    float_opp: bool = False
    float_bet: bool = False
    faced_float_opp: bool = False
    folded_to_float: bool = False


def _preflop_last_aggressor(hand: Hand) -> str | None:
    committed: dict[str, float] = {}
    current_bet = 0.0
    last_aggressor = None
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
            last_aggressor = a.player
            current_bet = max(current_bet, committed[a.player])
    return last_aggressor


def _preflop_callers_of_last_raise(hand: Hand) -> set[str]:
    """Who called the FINAL preflop raise (i.e. whoever's still in without
    having re-raised it) — this is who's eligible to float the flop against
    that raiser. A call is reset out of this set if a later raise comes in,
    since it no longer counts as "calling the final raise"."""
    committed: dict[str, float] = {}
    current_bet = 0.0
    callers: set[str] = set()
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
            callers = set()  # a new raise invalidates prior callers of the old top raise
            current_bet = max(current_bet, committed[a.player])
        elif a.action == 'Call':
            callers.add(a.player)
    return callers


def analyze_postflop(hand: Hand, positions: dict[str, str] | None = None) -> dict[str, dict[str, StreetFlags]]:
    """`positions` (from core.position.assign_positions) is optional — pass
    it to also get float stats; without it, float_opp/float_bet/etc. simply
    never fire, everything else is unaffected."""
    result: dict[str, dict[str, StreetFlags]] = {s: {} for s in STREETS}
    folded: set[str] = set()
    prev_aggressor = _preflop_last_aggressor(hand)
    callers_last_street: set[str] = _preflop_callers_of_last_raise(hand)
    # PT4's plain "Float F"/"Fold to F Float" are specifically a singly-raised
    # pot stat (it has a separate "...in 3Bet Pot" variant for the rest) —
    # a 3-bet+ preflop pot never contributes float opportunities here.
    float_eligible_pot = not is_3bet_plus_pot(hand)

    for street in STREETS:
        actions = [a for a in hand.actions if a.street == street]
        if not actions:
            break  # hand ended (folded out, or both all-in with no more decisions)

        live_players = [p.name for p in hand.players if p.name not in folded]
        flags = {name: StreetFlags(reached=True) for name in live_players}
        committed = {name: 0.0 for name in live_players}
        current_bet = 0.0
        bet_level = 0
        bettor = None
        raiser2 = None  # whoever made the raise that took bet_level 1 -> 2
        raiser3 = None  # whoever made the raise that took bet_level 2 -> 3
        checked: set[str] = set()
        aggressor_this_street = None
        aggressor_acted = False  # prev_aggressor's own turn hasn't come up yet this street
        street_had_checkraise = False
        street_had_donk = False
        street_had_float = False
        callers_this_street: set[str] = set()
        decided_cbet_opp: set[str] = set()
        decided_faced_cbet: set[str] = set()
        decided_xr_opp: set[str] = set()
        decided_faced_xr: set[str] = set()
        decided_donk_opp: set[str] = set()
        decided_faced_donk: set[str] = set()
        decided_face_bet: set[str] = set()
        decided_face_2bet: set[str] = set()
        decided_face_3bet: set[str] = set()
        decided_float_opp: set[str] = set()
        decided_faced_float: set[str] = set()

        for a in actions:
            f = flags.setdefault(a.player, StreetFlags(reached=True))
            committed.setdefault(a.player, 0.0)
            # A "donk bet" can only happen strictly before the previous
            # street's aggressor gets their own turn, so lock that window
            # closed the moment the aggressor acts, before evaluating
            # anything else about this action.
            is_aggressor = a.player == prev_aggressor
            if is_aggressor:
                aggressor_acted = True
            is_float_candidate = (
                positions is not None and prev_aggressor is not None
                and float_eligible_pot
                and a.player in callers_last_street
                and has_position_on(positions, a.player, prev_aggressor)
            )

            if a.action == 'Check':
                checked.add(a.player)
                if bet_level == 0 and is_aggressor and a.player not in decided_cbet_opp:
                    f.cbet_opp = True
                    decided_cbet_opp.add(a.player)
                if bet_level == 0 and not is_aggressor and not aggressor_acted and prev_aggressor is not None and a.player not in decided_donk_opp:
                    f.donk_opp = True
                    decided_donk_opp.add(a.player)
                if bet_level == 0 and is_float_candidate and a.player not in decided_float_opp:
                    f.float_opp = True
                    decided_float_opp.add(a.player)
                continue
            if a.action == 'Uncalled Return':
                continue

            if a.action == 'Fold':
                # Opportunity/outcome checks must run before folding removes
                # this player from the hand, since a fold IS the outcome
                # these two stats are trying to detect.
                if bet_level == 0 and not is_aggressor and not aggressor_acted and prev_aggressor is not None and a.player not in decided_donk_opp:
                    f.donk_opp = True
                    decided_donk_opp.add(a.player)
                if bet_level == 0 and is_float_candidate and a.player not in decided_float_opp:
                    f.float_opp = True
                    decided_float_opp.add(a.player)
                if bet_level == 1 and bettor == prev_aggressor and not is_aggressor and a.player not in decided_faced_cbet:
                    f.faced_cbet_opp = True
                    decided_faced_cbet.add(a.player)
                    f.folded_to_cbet = True
                if is_aggressor and bet_level == 1 and street_had_donk and a.player not in decided_faced_donk:
                    f.faced_donk_opp = True
                    decided_faced_donk.add(a.player)
                    f.folded_to_donk = True
                if is_aggressor and bet_level == 1 and street_had_float and a.player not in decided_faced_float:
                    f.faced_float_opp = True
                    decided_faced_float.add(a.player)
                    f.folded_to_float = True
                if a.player == bettor and bet_level == 2 and a.player not in decided_faced_xr and street_had_checkraise:
                    f.faced_xr_opp = True
                    decided_faced_xr.add(a.player)
                    f.folded_to_xr = True
                if bet_level == 1 and a.player != bettor and a.player not in decided_face_bet:
                    f.face_bet_opp = True
                    decided_face_bet.add(a.player)
                    f.folded_to_bet = True
                if bet_level == 2 and a.player != raiser2 and a.player not in decided_face_2bet:
                    f.face_2bet_opp = True
                    decided_face_2bet.add(a.player)
                    f.folded_to_2bet = True
                if bet_level == 3 and a.player != raiser3 and a.player not in decided_face_3bet:
                    f.face_3bet_opp = True
                    decided_face_3bet.add(a.player)
                    f.folded_to_3bet = True
                folded.add(a.player)
                continue

            current_bet_before = current_bet
            if a.action == 'Raise':
                committed[a.player] = a.amount if a.amount is not None else committed[a.player]
            else:
                committed[a.player] += a.amount or 0.0
            committed_after = committed[a.player]
            raise_like = _is_raise_like(a.action, committed_after, current_bet_before)

            if bet_level == 0 and is_aggressor and a.player not in decided_cbet_opp:
                f.cbet_opp = True
                decided_cbet_opp.add(a.player)
                if a.action == 'Bet' or raise_like:
                    f.cbet = True

            if bet_level == 0 and not is_aggressor and not aggressor_acted and prev_aggressor is not None and a.player not in decided_donk_opp:
                f.donk_opp = True
                decided_donk_opp.add(a.player)
                if a.action == 'Bet':
                    f.donk = True
                    street_had_donk = True

            if bet_level == 0 and is_float_candidate and a.player not in decided_float_opp:
                f.float_opp = True
                decided_float_opp.add(a.player)
                if a.action == 'Bet':
                    f.float_bet = True
                    street_had_float = True

            if bet_level == 1 and bettor == prev_aggressor and not is_aggressor and a.player not in decided_faced_cbet:
                f.faced_cbet_opp = True
                decided_faced_cbet.add(a.player)

            if is_aggressor and bet_level == 1 and street_had_donk and a.player not in decided_faced_donk:
                f.faced_donk_opp = True
                decided_faced_donk.add(a.player)

            if is_aggressor and bet_level == 1 and street_had_float and a.player not in decided_faced_float:
                f.faced_float_opp = True
                decided_faced_float.add(a.player)

            if a.action == 'Call' and bet_level == 1:
                callers_this_street.add(a.player)

            if a.player in checked and bet_level == 1 and a.player not in decided_xr_opp:
                f.xr_opp = True
                decided_xr_opp.add(a.player)
                if raise_like:
                    f.xr = True
                    street_had_checkraise = True

            if a.player == bettor and bet_level == 2 and a.player not in decided_faced_xr and street_had_checkraise:
                f.faced_xr_opp = True
                decided_faced_xr.add(a.player)

            if bet_level == 1 and a.player != bettor and a.player not in decided_face_bet:
                f.face_bet_opp = True
                decided_face_bet.add(a.player)
            if bet_level == 2 and a.player != raiser2 and a.player not in decided_face_2bet:
                f.face_2bet_opp = True
                decided_face_2bet.add(a.player)
            if bet_level == 3 and a.player != raiser3 and a.player not in decided_face_3bet:
                f.face_3bet_opp = True
                decided_face_3bet.add(a.player)

            if bet_level == 0 and a.action == 'Bet':
                bettor = a.player
                bet_level = 1
                aggressor_this_street = a.player
                current_bet = max(current_bet, committed_after)
            elif raise_like:
                bet_level += 1
                if bet_level == 2:
                    raiser2 = a.player
                elif bet_level == 3:
                    raiser3 = a.player
                aggressor_this_street = a.player
                current_bet = max(current_bet, committed_after)

        result[street] = flags
        # Chain rule: only carry the aggressor forward if they themselves
        # continued betting this street (see module docstring). A different
        # player taking over the betting lead resets it to None, same as a
        # checked-through street.
        prev_aggressor = aggressor_this_street if aggressor_this_street == prev_aggressor else None
        callers_last_street = callers_this_street

    return result


@dataclass
class StreetAggregate:
    reached: int = 0
    cbet_opp: int = 0
    cbet: int = 0
    faced_cbet_opp: int = 0
    folded_to_cbet: int = 0
    xr_opp: int = 0
    xr: int = 0
    faced_xr_opp: int = 0
    folded_to_xr: int = 0
    donk_opp: int = 0
    donk: int = 0
    faced_donk_opp: int = 0
    folded_to_donk: int = 0
    face_bet_opp: int = 0
    folded_to_bet: int = 0
    face_2bet_opp: int = 0
    folded_to_2bet: int = 0
    face_3bet_opp: int = 0
    folded_to_3bet: int = 0
    float_opp: int = 0
    float_bet: int = 0
    faced_float_opp: int = 0
    folded_to_float: int = 0

    @staticmethod
    def _pct(made: int, opp: int):
        return round(100.0 * made / opp, 2) if opp else None

    @property
    def cbet_pct(self): return self._pct(self.cbet, self.cbet_opp)

    @property
    def fold_to_cbet_pct(self): return self._pct(self.folded_to_cbet, self.faced_cbet_opp)

    @property
    def xr_pct(self): return self._pct(self.xr, self.xr_opp)

    @property
    def fold_to_xr_pct(self): return self._pct(self.folded_to_xr, self.faced_xr_opp)

    @property
    def donk_pct(self): return self._pct(self.donk, self.donk_opp)

    @property
    def fold_to_donk_pct(self): return self._pct(self.folded_to_donk, self.faced_donk_opp)

    @property
    def fold_to_bet_pct(self): return self._pct(self.folded_to_bet, self.face_bet_opp)

    @property
    def fold_to_2bet_pct(self): return self._pct(self.folded_to_2bet, self.face_2bet_opp)

    @property
    def fold_to_3bet_pct(self): return self._pct(self.folded_to_3bet, self.face_3bet_opp)

    @property
    def float_pct(self): return self._pct(self.float_bet, self.float_opp)

    @property
    def fold_to_float_pct(self): return self._pct(self.folded_to_float, self.faced_float_opp)


def aggregate_postflop_stats(hands: list[Hand], player_name: str, street: str,
                              positions_fn=None) -> StreetAggregate:
    """`positions_fn`, if given, is called once per hand as positions_fn(hand)
    to get {player: position_label} — pass core.position.assign_positions to
    also get float stats populated."""
    agg = StreetAggregate()
    for hand in hands:
        positions = positions_fn(hand) if positions_fn else None
        flags = analyze_postflop(hand, positions).get(street, {}).get(player_name)
        if not flags:
            continue
        agg.reached += flags.reached
        agg.cbet_opp += flags.cbet_opp
        agg.cbet += flags.cbet
        agg.faced_cbet_opp += flags.faced_cbet_opp
        agg.folded_to_cbet += flags.folded_to_cbet
        agg.xr_opp += flags.xr_opp
        agg.xr += flags.xr
        agg.faced_xr_opp += flags.faced_xr_opp
        agg.folded_to_xr += flags.folded_to_xr
        agg.donk_opp += flags.donk_opp
        agg.donk += flags.donk
        agg.faced_donk_opp += flags.faced_donk_opp
        agg.folded_to_donk += flags.folded_to_donk
        agg.face_bet_opp += flags.face_bet_opp
        agg.folded_to_bet += flags.folded_to_bet
        agg.face_2bet_opp += flags.face_2bet_opp
        agg.folded_to_2bet += flags.folded_to_2bet
        agg.face_3bet_opp += flags.face_3bet_opp
        agg.folded_to_3bet += flags.folded_to_3bet
        agg.float_opp += flags.float_opp
        agg.float_bet += flags.float_bet
        agg.faced_float_opp += flags.faced_float_opp
        agg.folded_to_float += flags.folded_to_float
    return agg
