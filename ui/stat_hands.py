"""Maps a stat_id to the specific hands that contributed to it — the
backing logic for "click a stat to see the hands" (item 9). Reuses the
exact same per-hand flag objects the aggregate stats are built from, so
the hand list returned always matches the displayed percentage rather
than being a separate, possibly-inconsistent reimplementation.

Not every stat in STAT_REGISTRY has a lookup here — this covers the
preflop/overall stats and cbet/fold-to-cbet per street, which are the
ones most useful to drill into. Unmapped stat ids simply aren't
clickable (hands_for_stat returns an empty list)."""
from models.hand import Hand
from core.stats import analyze_preflop, analyze_showdown
from core.stats_postflop import analyze_postflop
from core.position import assign_positions


def _preflop_flag(attr):
    def check(hand, player):
        flags = analyze_preflop(hand).get(player)
        return bool(flags and getattr(flags, attr, False))
    return check


def _showdown_flag(attr):
    def check(hand, player):
        flags = analyze_showdown(hand).get(player)
        return bool(flags and getattr(flags, attr, False))
    return check


def _wwsf_check(hand, player):
    flags = analyze_showdown(hand).get(player)
    return bool(flags and flags.saw_flop and flags.won_hand)


def _wsd_check(hand, player):
    flags = analyze_showdown(hand).get(player)
    return bool(flags and flags.reached_showdown and flags.won_hand)


def _street_flag(street, attr):
    def check(hand, player):
        positions = assign_positions(hand)
        flags = analyze_postflop(hand, positions).get(street, {}).get(player)
        return bool(flags and getattr(flags, attr, False))
    return check


STAT_PREDICATES = {
    'vpip': _preflop_flag('vpip'),
    'pfr': _preflop_flag('pfr'),
    'three_bet': _preflop_flag('three_bet'),
    'fold_3bet': _preflop_flag('folded_to_3bet'),
    'four_bet': _preflop_flag('four_bet'),
    'fold_4bet': _preflop_flag('folded_to_4bet'),
    'squeeze': _preflop_flag('squeeze'),
    'raise_vs_squeeze': _preflop_flag('raised_vs_squeeze'),
    'fold_to_squeeze': _preflop_flag('folded_to_squeeze'),
    'wtsd': _showdown_flag('reached_showdown'),
    'wwsf': _wwsf_check,
    'wsd': _wsd_check,
}
for _street in ('flop', 'turn', 'river'):
    STAT_PREDICATES[f'{_street}_cbet'] = _street_flag(_street.upper(), 'cbet')
    STAT_PREDICATES[f'{_street}_fold_cbet'] = _street_flag(_street.upper(), 'folded_to_cbet')
    STAT_PREDICATES[f'{_street}_xr'] = _street_flag(_street.upper(), 'xr')
    STAT_PREDICATES[f'{_street}_donk'] = _street_flag(_street.upper(), 'donk')


def hands_for_stat(hands: list[Hand], player_name: str, stat_id: str) -> list[Hand]:
    predicate = STAT_PREDICATES.get(stat_id)
    if predicate is None:
        return []
    player_hands = [h for h in hands if player_name in {p.name for p in h.players}]
    return [h for h in player_hands if predicate(h, player_name)]
