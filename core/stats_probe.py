"""Probe bets — betting out of position on the turn or river after the fixed
preflop aggressor has checked back a street.

Deliberately independent of core/stats_postflop.py's cbet/donk/float engine:
that engine tracks a *rolling* "aggressor" that resets to None the moment a
street checks through (an intentional choice — see its docstring on "delayed
c-bet"). Probe is specifically the opposite case: the ORIGINAL preflop
aggressor checks back, and the out-of-position caller of their raise takes
the betting lead. That needs the preflop aggressor's identity to persist
across a fully-checked street, so it's tracked fresh here.

The standard definition of a probe bet:
  - Probe Turn opportunity: player called the (single) preflop raise, is out
    of position on that raiser, the flop checks through entirely (everyone
    checks — no bets), and it's their turn to act on the turn before anyone
    has bet.
  - Probe River opportunity: same player, but requires they specifically
    called a flop c-bet from the aggressor (not just checked it through),
    and then the turn also checks through entirely.
"""
from dataclasses import dataclass
from models.hand import Hand
from core.position import assign_positions, has_position_on
from core.stats_postflop import _preflop_last_aggressor, _preflop_callers_of_last_raise


@dataclass
class ProbeFlags:
    probe_turn_opp: bool = False
    probe_turn: bool = False
    faced_probe_turn_opp: bool = False
    folded_to_probe_turn: bool = False
    probe_river_opp: bool = False
    probe_river: bool = False
    faced_probe_river_opp: bool = False
    folded_to_probe_river: bool = False


def _street_actions(hand: Hand, street: str) -> list:
    return [a for a in hand.actions if a.street == street]


def _all_checked(actions: list) -> bool:
    return bool(actions) and all(a.action == 'Check' for a in actions)


def _flop_bet_and_call(hand: Hand, aggressor: str) -> tuple[bool, set]:
    """Did the aggressor c-bet the flop, and who called it?"""
    flop = _street_actions(hand, 'FLOP')
    bet_happened = False
    callers = set()
    for a in flop:
        if a.player == aggressor and a.action == 'Bet' and not bet_happened:
            bet_happened = True
        elif bet_happened and a.action == 'Call':
            callers.add(a.player)
    return bet_happened, callers


def analyze_probe(hand: Hand) -> dict[str, ProbeFlags]:
    flags: dict[str, ProbeFlags] = {p.name: ProbeFlags() for p in hand.players}
    positions = assign_positions(hand)
    if not positions:
        return flags

    aggressor = _preflop_last_aggressor(hand)
    if aggressor is None:
        return flags
    callers = _preflop_callers_of_last_raise(hand)
    oop_callers = {p for p in callers if p != aggressor and not has_position_on(positions, p, aggressor)}
    if not oop_callers:
        return flags

    # --- Probe Turn: flop checks through entirely ---
    flop_actions = _street_actions(hand, 'FLOP')
    if _all_checked(flop_actions):
        turn_actions = _street_actions(hand, 'TURN')
        bet_happened = False
        prober = None  # who made the bet that first opened turn action
        decided: set = set()
        for a in turn_actions:
            if a.player == aggressor and bet_happened and prober in oop_callers and a.player not in decided:
                flags[a.player].faced_probe_turn_opp = True
                decided.add(a.player)
                if a.action == 'Fold':
                    flags[a.player].folded_to_probe_turn = True
            if a.player in oop_callers and not bet_happened and a.player not in decided:
                f = flags[a.player]
                f.probe_turn_opp = True
                decided.add(a.player)
                if a.action == 'Bet':
                    f.probe_turn = True
                    bet_happened = True
                    prober = a.player
            elif a.action in ('Bet', 'Raise', 'Allin') and not bet_happened:
                bet_happened = True
                prober = a.player

    # --- Probe River: aggressor c-bet flop, an OOP caller called it, then
    # turn checks through entirely ---
    flop_bet, flop_callers_of_cbet = _flop_bet_and_call(hand, aggressor)
    river_oop_callers = oop_callers & flop_callers_of_cbet
    if flop_bet and river_oop_callers:
        turn_actions = _street_actions(hand, 'TURN')
        if _all_checked(turn_actions):
            river_actions = _street_actions(hand, 'RIVER')
            bet_happened = False
            prober = None
            decided: set = set()
            for a in river_actions:
                if a.player == aggressor and bet_happened and prober in river_oop_callers and a.player not in decided:
                    flags[a.player].faced_probe_river_opp = True
                    decided.add(a.player)
                    if a.action == 'Fold':
                        flags[a.player].folded_to_probe_river = True
                if a.player in river_oop_callers and not bet_happened and a.player not in decided:
                    f = flags[a.player]
                    f.probe_river_opp = True
                    decided.add(a.player)
                    if a.action == 'Bet':
                        f.probe_river = True
                        bet_happened = True
                        prober = a.player
                elif a.action in ('Bet', 'Raise', 'Allin') and not bet_happened:
                    bet_happened = True
                    prober = a.player

    return flags


@dataclass
class ProbeAggregate:
    probe_turn_opp: int = 0
    probe_turn: int = 0
    faced_probe_turn_opp: int = 0
    folded_to_probe_turn: int = 0
    probe_river_opp: int = 0
    probe_river: int = 0
    faced_probe_river_opp: int = 0
    folded_to_probe_river: int = 0

    @staticmethod
    def _pct(made: int, opp: int):
        return round(100.0 * made / opp, 2) if opp else None

    @property
    def probe_turn_pct(self): return self._pct(self.probe_turn, self.probe_turn_opp)

    @property
    def fold_to_probe_turn_pct(self): return self._pct(self.folded_to_probe_turn, self.faced_probe_turn_opp)

    @property
    def probe_river_pct(self): return self._pct(self.probe_river, self.probe_river_opp)

    @property
    def fold_to_probe_river_pct(self): return self._pct(self.folded_to_probe_river, self.faced_probe_river_opp)


def aggregate_probe_stats(hands: list[Hand], player_name: str) -> ProbeAggregate:
    agg = ProbeAggregate()
    for hand in hands:
        flags = analyze_probe(hand).get(player_name)
        if not flags:
            continue
        agg.probe_turn_opp += flags.probe_turn_opp
        agg.probe_turn += flags.probe_turn
        agg.faced_probe_turn_opp += flags.faced_probe_turn_opp
        agg.folded_to_probe_turn += flags.folded_to_probe_turn
        agg.probe_river_opp += flags.probe_river_opp
        agg.probe_river += flags.probe_river
        agg.faced_probe_river_opp += flags.faced_probe_river_opp
        agg.folded_to_probe_river += flags.folded_to_probe_river
    return agg
