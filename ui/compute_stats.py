"""Flattens every aggregate_* function's output into one {stat_id: value}
dict keyed to match ui/stat_registry.py, for a single villain."""
from models.hand import Hand
from core.stats import aggregate_player_stats, aggregate_aggression_stats, compute_invested
from core.stats_postflop import aggregate_postflop_stats
from core.stats_position import aggregate_steal_stats, aggregate_3bet_and_fold_vs_open_by_position
from core.stats_probe import aggregate_probe_stats
from core.position import assign_positions
from core.ev import compute_hand_ev

EV_HAND_LIMIT = 50_000

_STREET_KEYS = [
    ("cbet_pct", "cbet"), ("fold_to_cbet_pct", "fold_cbet"),
    ("xr_pct", "xr"), ("fold_to_xr_pct", "fold_xr"),
    ("donk_pct", "donk"), ("fold_to_donk_pct", "fold_donk"),
    ("fold_to_bet_pct", "fold_bet"), ("fold_to_2bet_pct", "fold_2bet"),
    ("fold_to_3bet_pct", "fold_3bet_street"),
    ("float_pct", "float"), ("fold_to_float_pct", "fold_float"),
]


def compute_all_stats(hands: list[Hand], player_name: str):
    """Returns (values: dict[str, float|None], hand_count: int, vs_open: dict).

    Filters to this player's hands ONCE up front. Every aggregate_* function
    already re-checks membership per hand internally, but without this
    pre-filter each of the ~8 calls below independently scans the ENTIRE
    dataset (244,739 hands) just to find the ~500-5,000 that matter — that
    was an 8x-plus, tens-of-seconds-per-click cost that made the UI freeze.
    """
    player_hands = [h for h in hands if player_name in {p.name for p in h.players}]

    agg = aggregate_player_stats(player_hands, player_name)
    af = aggregate_aggression_stats(player_hands, player_name)
    steal = aggregate_steal_stats(player_hands, player_name)
    probe = aggregate_probe_stats(player_hands, player_name)
    vs_open = aggregate_3bet_and_fold_vs_open_by_position(player_hands, player_name)

    # All-in EV needs a Monte Carlo equity run for every genuine all-in hand
    # found, which is cheap for a normal villain (a few seconds even at the
    # single biggest villain's ~22k hands) but would add 30-60+ seconds on
    # top of an already-slow "All Time" hero computation across a quarter
    # million hands — reintroducing the exact freeze already fixed earlier.
    # Skip it past this threshold rather than silently making that worse.
    ev_bb100 = None
    if len(player_hands) <= EV_HAND_LIMIT:
        ev_bb_sum, ev_bb_hands = 0.0, 0
        for h in player_hands:
            if not h.big_blind:
                continue
            ev = compute_hand_ev(h, player_name, iterations=50)
            if ev is None:
                invested = compute_invested(h)
                ev = h.winnings.get(player_name, 0.0) - invested.get(player_name, 0.0)
            ev_bb_sum += ev / h.big_blind
            ev_bb_hands += 1
        ev_bb100 = round(100.0 * ev_bb_sum / ev_bb_hands, 2) if ev_bb_hands else None

    values = {
        "bb100": agg.bb100,
        "ev_bb100": ev_bb100,
        "wtsd": agg.wtsd_pct, "wsd": agg.wsd_pct, "wwsf": agg.wwsf_pct,
        "total_af": af["TOTAL"].af, "total_afq": af["TOTAL"].afq_pct,
        "vpip": agg.vpip_pct, "pfr": agg.pfr_pct,
        "three_bet": agg.three_bet_pct, "fold_3bet": agg.fold_to_3bet_pct,
        "four_bet": agg.four_bet_pct, "fold_4bet": agg.fold_to_4bet_pct,
        "squeeze": agg.squeeze_pct, "raise_vs_squeeze": agg.raise_vs_squeeze_pct,
        "fold_to_squeeze": agg.fold_to_squeeze_pct,
        "steal_att": steal.steal_att_pct, "steal_success": steal.steal_success_pct,
        "fold_to_steal": steal.fold_to_steal_pct,
        "preflop_af": af["PREFLOP"].af, "preflop_afq": af["PREFLOP"].afq_pct,
    }

    for street in ("FLOP", "TURN", "RIVER"):
        street_lc = street.lower()
        sagg = aggregate_postflop_stats(player_hands, player_name, street, positions_fn=assign_positions)
        for prop, key in _STREET_KEYS:
            values[f"{street_lc}_{key}"] = getattr(sagg, prop)
        street_af = af[street]
        values[f"{street_lc}_af"] = street_af.af
        values[f"{street_lc}_afq"] = street_af.afq_pct

    values["turn_probe"] = probe.probe_turn_pct
    values["turn_fold_probe"] = probe.fold_to_probe_turn_pct
    values["river_probe"] = probe.probe_river_pct
    values["river_fold_probe"] = probe.fold_to_probe_river_pct

    return values, agg.hands, vs_open
