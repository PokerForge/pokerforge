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
from core.ggpoker_hand_parser import GGPOKER_HERO_LABEL
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


def build_player_stat_rows(hand: Hand, ev_iterations: int = 3000, hero: str | None = None) -> list[dict]:
    if not hand.players:
        return []

    # Which name actually IS the hero's own seat, for the GGPoker/Winning
    # Network exclusion below. `ui/hero_detect.py`'s normalize_hero_aliases
    # runs before a hand ever reaches here and rewrites a known alias (most
    # commonly literally "Hero" itself, once the app has confirmed that's
    # this hero's GGPoker/Winning Network identity) to the configured hero
    # name -- so by this point the seat GGPOKER_HERO_LABEL was meant to
    # find may no longer be spelled "Hero" at all. Passing the resolved
    # `hero` name in lets this still find the right seat after that rename;
    # `hero=None` (every call site before this was threaded through, and
    # every hand not yet past that rename) falls back to the literal label.
    hero_label = hero or GGPOKER_HERO_LABEL

    preflop = analyze_preflop(hand)
    showdown = analyze_showdown(hand)
    steal = analyze_steal(hand)
    positions = assign_positions(hand)
    postflop = analyze_postflop(hand, positions)
    probe = analyze_probe(hand)
    aggression = analyze_aggression(hand)
    invested = compute_invested(hand)

    played_at = hand.played_at.isoformat() if hand.played_at else None
    # A tournament's blind LEVEL isn't a "stake" in the cash sense (it's
    # not fixed for the session, and stakes_label() would just format the
    # chip blinds as if they were currency) -- NULL here keeps tournament
    # hands out of the Stakes dropdown and every stakes_label-keyed query.
    stake_label = None if hand.session_type == 'tournament' else stakes_label(hand)
    # Rake is taken from the WHOLE pot, not charged to any one player --
    # a hand's `hand.rake` is one shared table-level figure. Attributing
    # the full amount to every player who was merely seated (the earlier,
    # wrong version of this) massively overstates any one player's own
    # rakeback-eligible share in a multi-way pot. Real rakeback trackers
    # instead split "dealt rake" evenly across whoever was still in when
    # the flop came (folding preflop means no share of that hand's rake,
    # since rake is only ever taken once a pot is actually contested).
    flop_seers = sum(1 for p in hand.players if (showdown.get(p.name) and showdown[p.name].saw_flop))
    rows = []
    for p in hand.players:
        name = p.name
        # GGPoker and Winning Network both anonymize every seat except the
        # exporting account's own (always literally "Hero") with a fresh
        # random label every hand -- never worth a stats row, since it can
        # never be aggregated into a real, trackable villain (see
        # core/ggpoker_hand_parser.py / core/winning_network_hand_parser.py).
        if hand.source in ('ggpoker', 'winning_network') and name != hero_label:
            continue
        pf = preflop.get(name)
        sd = showdown.get(name)
        st = steal.get(name)
        is_tournament = hand.session_type == 'tournament'
        # A tournament's per-hand chip movements aren't real money until
        # the tournament itself pays out (or doesn't) -- storing them in
        # the same profit/ev columns cash queries SUM() would silently
        # blend chip counts into $ totals. Kept NULL here as a defense-in-
        # depth backstop; the real protection is the explicit
        # `session_type = 'cash'` filter on the Overview/Sessions queries.
        ev = None if is_tournament else compute_hand_ev(hand, name, iterations=ev_iterations)
        profit = None if is_tournament else hand.winnings.get(name, 0.0) - invested.get(name, 0.0)
        # Same reasoning as ev/profit above -- a tournament's buy-in fee
        # isn't per-hand cash rake, so this stays NULL for tournament
        # hands rather than letting a chip-based figure leak into the
        # Rakeback stat's SUM(rake). This player's own even share of the
        # hand's rake, or exactly 0 (not None -- the hand DID have a
        # rake figure, this player just didn't contribute to it) if they
        # folded before the flop.
        if is_tournament or hand.rake is None:
            rake = None
        elif sd and sd.saw_flop and flop_seers:
            rake = hand.rake / flop_seers
        else:
            rake = 0.0

        row = {
            'hand_id': hand.hand_id,
            'player_name': name,
            'played_at': played_at,
            'big_blind': hand.big_blind,
            'profit': profit,
            'ev': ev,
            'position': positions.get(name),
            'stakes_label': stake_label,
            'source': hand.source,
            'session_type': hand.session_type,
            'tournament_id': hand.tournament_id,
            'rake': rake,

            'vpip_pfr_opp': _b(pf is None or pf.vpip_pfr_opp),
            'vpip': _b(pf and pf.vpip), 'pfr': _b(pf and pf.pfr),
            'three_bet_opp': _b(pf and pf.three_bet_opp), 'three_bet': _b(pf and pf.three_bet),
            'faced_3bet_opp': _b(pf and pf.faced_3bet_opp), 'folded_to_3bet': _b(pf and pf.folded_to_3bet),
            'faced_3bet_as_raiser_opp': _b(pf and pf.faced_3bet_as_raiser_opp),
            'folded_to_3bet_as_raiser': _b(pf and pf.folded_to_3bet_as_raiser),
            'four_bet_opp': _b(pf and pf.four_bet_opp), 'four_bet': _b(pf and pf.four_bet),
            'faced_4bet_opp': _b(pf and pf.faced_4bet_opp), 'folded_to_4bet': _b(pf and pf.folded_to_4bet),
            'squeeze_opp': _b(pf and pf.squeeze_opp), 'squeeze': _b(pf and pf.squeeze),
            'squeeze_def_opp': _b(pf and pf.squeeze_def_opp),
            'raised_vs_squeeze': _b(pf and pf.raised_vs_squeeze),
            'folded_to_squeeze': _b(pf and pf.folded_to_squeeze),
            'folded_vs_open': _b(pf and pf.folded_vs_open),
            'limp_opp': _b(pf and pf.limp_opp), 'limp': _b(pf and pf.limp),
            'limp_call_opp': _b(pf and pf.limp_call_opp), 'limp_call': _b(pf and pf.limp_call),

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
