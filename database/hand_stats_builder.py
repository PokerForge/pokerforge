"""Builds one hand_player_stats row per player for a single Hand, by
running the existing, already-validated per-hand analyzer functions
exactly once each. This is the only place stat logic is "re-implemented"
for the database — and it isn't really: it just flattens the same
analyzer outputs the live in-memory code already trusted into columns,
so the database's numbers are guaranteed to match what the app already
computes correctly.
"""
from models.hand import Hand
from core.stats import (
    analyze_preflop, analyze_showdown, analyze_aggression, compute_invested,
)
from core.stats_postflop import analyze_postflop
from core.stats_probe import analyze_probe
from core.stats_position import analyze_steal
from core.position import assign_positions
from core.ev import compute_hand_ev
from ui.stakes import stakes_label

_STREET_FLAG_FIELDS = [
    'reached', 'cbet_opp', 'cbet', 'faced_cbet_opp', 'folded_to_cbet',
    'xr_opp', 'xr', 'faced_xr_opp', 'folded_to_xr',
    'donk_opp', 'donk', 'faced_donk_opp', 'folded_to_donk',
    'face_bet_opp', 'folded_to_bet', 'face_2bet_opp', 'folded_to_2bet',
    'face_3bet_opp', 'folded_to_3bet',
    'float_opp', 'float_bet', 'faced_float_opp', 'folded_to_float',
]


def _b(v):
    return int(bool(v))


def build_player_stat_rows(hand: Hand, ev_iterations: int = 3000) -> list[dict]:
    if not hand.players:
        return []

    preflop = analyze_preflop(hand)
    showdown = analyze_showdown(hand)
    steal = analyze_steal(hand)
    positions = assign_positions(hand)
    postflop = analyze_postflop(hand, positions)
    probe = analyze_probe(hand)
    aggression = analyze_aggression(hand)
    invested = compute_invested(hand)

    played_at = hand.played_at.isoformat() if hand.played_at else None
    stake_label = stakes_label(hand)
    rows = []
    for p in hand.players:
        name = p.name
        pf = preflop.get(name)
        sd = showdown.get(name)
        st = steal.get(name)
        ev = compute_hand_ev(hand, name, iterations=ev_iterations)
        profit = hand.winnings.get(name, 0.0) - invested.get(name, 0.0)

        row = {
            'hand_id': hand.hand_id,
            'player_name': name,
            'played_at': played_at,
            'big_blind': hand.big_blind,
            'profit': profit,
            'ev': ev,
            'position': positions.get(name),
            'stakes_label': stake_label,

            'vpip_pfr_opp': _b(pf is None or pf.vpip_pfr_opp),
            'vpip': _b(pf and pf.vpip), 'pfr': _b(pf and pf.pfr),
            'three_bet_opp': _b(pf and pf.three_bet_opp), 'three_bet': _b(pf and pf.three_bet),
            'faced_3bet_opp': _b(pf and pf.faced_3bet_opp), 'folded_to_3bet': _b(pf and pf.folded_to_3bet),
            'four_bet_opp': _b(pf and pf.four_bet_opp), 'four_bet': _b(pf and pf.four_bet),
            'faced_4bet_opp': _b(pf and pf.faced_4bet_opp), 'folded_to_4bet': _b(pf and pf.folded_to_4bet),
            'squeeze_opp': _b(pf and pf.squeeze_opp), 'squeeze': _b(pf and pf.squeeze),
            'squeeze_def_opp': _b(pf and pf.squeeze_def_opp),
            'raised_vs_squeeze': _b(pf and pf.raised_vs_squeeze),
            'folded_to_squeeze': _b(pf and pf.folded_to_squeeze),
            'folded_vs_open': _b(pf and pf.folded_vs_open),

            'saw_flop': _b(sd and sd.saw_flop), 'reached_showdown': _b(sd and sd.reached_showdown),
            'won_hand': _b(sd and sd.won_hand),

            'steal_opp': _b(st and st.steal_opp), 'steal_att': _b(st and st.steal_att),
            'steal_success': _b(st and st.steal_success),
            'blind_def_opp': _b(st and st.blind_def_opp), 'folded_to_steal': _b(st and st.folded_to_steal),
        }

        for street in ('flop', 'turn', 'river'):
            flags = postflop.get(street.upper(), {}).get(name)
            for field in _STREET_FLAG_FIELDS:
                row[f'{street}_{field}'] = _b(flags and getattr(flags, field, False))

        pr = probe.get(name)
        row.update({
            'probe_turn_opp': _b(pr and pr.probe_turn_opp), 'probe_turn': _b(pr and pr.probe_turn),
            'faced_probe_turn_opp': _b(pr and pr.faced_probe_turn_opp),
            'folded_to_probe_turn': _b(pr and pr.folded_to_probe_turn),
            'probe_river_opp': _b(pr and pr.probe_river_opp), 'probe_river': _b(pr and pr.probe_river),
            'faced_probe_river_opp': _b(pr and pr.faced_probe_river_opp),
            'folded_to_probe_river': _b(pr and pr.folded_to_probe_river),
        })

        for street in ('preflop', 'flop', 'turn', 'river'):
            counts = aggression.get(street.upper(), {}).get(name)
            row[f'{street}_bet_raise'] = counts.bet_raise if counts else 0
            row[f'{street}_call'] = counts.call if counts else 0
            row[f'{street}_fold'] = counts.fold if counts else 0

        rows.append(row)
    return rows
