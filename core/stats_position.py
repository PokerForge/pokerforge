"""Position-dependent preflop stats — steal attempts and blind defense.

Built on top of core/position.py's seat-derived position labels (validated
against real blind-post ground truth: 100% match on SB, 244738/244739 on BB
across the full 244,739-hand dataset) and the same raise-tracking convention
already proven in core/stats.py's analyze_preflop.

Definitions follow PT4's own formulas (docs/pt4_stat_raw_decode.txt):
  - Steal opportunity: player is in a steal position (CO/BTN/SB) and is the
    first to voluntarily act (everyone before them folded — no limps, no
    raises yet).
  - Steal success: the steal attempt goes completely uncontested — the
    raiser never faces a re-raise and never sees a flop (someone calling
    counts as resistance even if the raiser later wins the hand).
  - Fold to steal: a blind (SB or BB, when not the raiser) facing exactly
    that one steal-position raise with no one else having called in
    between, folds.
Heads-up (2-handed) is excluded from steal stats — with only BTN/SB and BB,
"stealing" isn't a distinct concept from simply opening.
"""
from dataclasses import dataclass
from models.hand import Hand
from core.position import assign_positions
from core.stats import _is_raise_like, _preflop_opener, analyze_preflop

STEAL_POSITIONS = {'BTN', 'CO', 'SB'}


@dataclass
class StealFlags:
    steal_opp: bool = False
    steal_att: bool = False
    steal_success: bool = False
    blind_def_opp: bool = False
    folded_to_steal: bool = False


def analyze_steal(hand: Hand) -> dict[str, StealFlags]:
    positions = assign_positions(hand)
    if not positions or any(p == 'BTN/SB' for p in positions.values()):
        return {}  # heads-up, or an unhandled seat configuration

    flags: dict[str, StealFlags] = {p.name: StealFlags() for p in hand.players}
    committed: dict[str, float] = {p.name: 0.0 for p in hand.players}
    current_bet = 0.0
    raise_level = 0
    # A limp, a flat-call of the steal, or any prior voluntary money-in
    # action disqualifies a "clean" steal/defend spot. Folds do NOT count
    # here — being folded to is exactly what a steal opportunity requires.
    anyone_called = False
    stealer = None          # who made the sole raise while raise_level was 0
    stealer_pos = None
    stealer_faced_raise = False

    for a in hand.actions:
        if a.street != 'PREFLOP':
            continue
        f = flags.setdefault(a.player, StealFlags())
        committed.setdefault(a.player, 0.0)
        pos = positions.get(a.player)

        if a.action in ('Post SB', 'Post BB'):
            committed[a.player] += a.amount or 0.0
            current_bet = max(current_bet, committed[a.player])
            continue
        if a.action == 'Uncalled Return':
            continue

        if a.action == 'Fold':
            if raise_level == 0 and not anyone_called and pos in STEAL_POSITIONS:
                f.steal_opp = True
            if raise_level == 1 and pos in ('SB', 'BB') and a.player != stealer and not anyone_called \
                    and stealer_pos in STEAL_POSITIONS:
                f.blind_def_opp = True
                f.folded_to_steal = True
            continue

        current_bet_before = current_bet
        if a.action == 'Raise':
            committed[a.player] = a.amount if a.amount is not None else committed[a.player]
        else:
            committed[a.player] += a.amount or 0.0
        committed_after = committed[a.player]
        raise_like = _is_raise_like(a.action, committed_after, current_bet_before)

        if raise_level == 0 and not anyone_called and pos in STEAL_POSITIONS:
            f.steal_opp = True
            if raise_like:
                f.steal_att = True

        if raise_level == 1 and pos in ('SB', 'BB') and a.player != stealer and not anyone_called \
                and stealer_pos in STEAL_POSITIONS:
            f.blind_def_opp = True

        if a.action == 'Call':
            anyone_called = True

        if raise_like:
            if raise_level == 1:
                stealer_faced_raise = True
            raise_level += 1
            if raise_level == 1:
                stealer = a.player
                stealer_pos = pos
            current_bet = max(current_bet, committed_after)

    # "Steal success" needs the raiser to have faced zero resistance at all:
    # no re-raise, and no call that carried the hand to a flop. Checking the
    # board (not FLOP-street actions) also correctly covers an all-in runout
    # with no further actions, which would otherwise look like "no flop".
    saw_flop = len(hand.board) >= 3
    if stealer is not None:
        sf = flags[stealer]
        if sf.steal_att and not stealer_faced_raise and not saw_flop:
            sf.steal_success = True
    return flags


@dataclass
class StealAggregate:
    steal_opp: int = 0
    steal_att: int = 0
    steal_success: int = 0
    blind_def_opp: int = 0
    folded_to_steal: int = 0

    @staticmethod
    def _pct(made: int, opp: int):
        return round(100.0 * made / opp, 2) if opp else None

    @property
    def steal_att_pct(self): return self._pct(self.steal_att, self.steal_opp)

    @property
    def steal_success_pct(self): return self._pct(self.steal_success, self.steal_att)

    @property
    def fold_to_steal_pct(self): return self._pct(self.folded_to_steal, self.blind_def_opp)


def aggregate_steal_stats(hands: list[Hand], player_name: str) -> StealAggregate:
    agg = StealAggregate()
    for hand in hands:
        flags = analyze_steal(hand).get(player_name)
        if not flags:
            continue
        agg.steal_opp += flags.steal_opp
        agg.steal_att += flags.steal_att
        agg.steal_success += flags.steal_success
        agg.blind_def_opp += flags.blind_def_opp
        agg.folded_to_steal += flags.folded_to_steal
    return agg


@dataclass
class VsOpenAggregate:
    three_bet_opp: int = 0
    three_bet: int = 0
    folded_vs_open: int = 0

    @staticmethod
    def _pct(made: int, opp: int):
        return round(100.0 * made / opp, 2) if opp else None

    @property
    def three_bet_pct(self): return self._pct(self.three_bet, self.three_bet_opp)

    @property
    def fold_pct(self): return self._pct(self.folded_vs_open, self.three_bet_opp)


def aggregate_3bet_and_fold_vs_open_by_position(hands: list[Hand], player_name: str) -> dict[str, VsOpenAggregate]:
    """For each hand where `player_name` faced a single open raise preflop,
    buckets their 3-bet/fold response by the OPENER's position (e.g. "how
    often do I 3-bet/fold when the button opens"). Heads-up hands get their
    own 'BTN/SB' bucket, since that's a real, distinct opener there."""
    result: dict[str, VsOpenAggregate] = {}
    for hand in hands:
        positions = assign_positions(hand)
        if not positions:
            continue
        flags = analyze_preflop(hand).get(player_name)
        if not flags or not flags.three_bet_opp:
            continue
        opener = _preflop_opener(hand)
        opener_pos = positions.get(opener)
        if opener_pos is None:
            continue
        agg = result.setdefault(opener_pos, VsOpenAggregate())
        agg.three_bet_opp += 1
        agg.three_bet += flags.three_bet
        agg.folded_vs_open += flags.folded_vs_open
    return result
