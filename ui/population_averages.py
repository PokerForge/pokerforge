"""Real, computed population averages — reuses the per-villain rows
build_population_summary already produces for the Population tab (summed
across every villain rather than recomputed from scratch), so this is
essentially free. Covers VPIP/PFR/3-Bet/Fold-3-Bet/WTSD/WWSF, since those
are exactly what PopulationRow already tracks.

Stats not covered here (4-bet, squeeze, steal, and every postflop
street stat — cbet/xr/donk/float/probe etc.) still fall back to the
lo/hi midpoint approximation in ui/stat_registry.py's pop_avg(). Getting
real pooled averages for those too would mean duplicating
aggregate_postflop_stats/aggregate_steal_stats/aggregate_probe_stats'
per-hand accumulation, pooled across every villain instead of filtered to
one name — a larger follow-up, intentionally not attempted here."""


def compute_population_averages(rows: dict) -> dict:
    """rows: the dict[str, PopulationRow] from build_population_summary for
    the currently selected period. Returns POOLED percentages (total events
    / total opportunities across every villain), matching how "population
    average" is conventionally defined — not the mean of each villain's own
    percentage, which would overweight low-sample-size villains."""
    hands = vpip = pfr = tb = tb_opp = f3b = f3b_opp = wsf = sf = wtsd_num = 0
    for r in rows.values():
        hands += r.hands
        vpip += r.vpip
        pfr += r.pfr
        tb += r.three_bet
        tb_opp += r.three_bet_opp
        f3b += r.folded_to_3bet
        f3b_opp += r.faced_3bet_opp
        wsf += r.won_saw_flop
        sf += r.saw_flop
        wtsd_num += r.reached_showdown

    def pct(made, opp):
        return round(100.0 * made / opp, 1) if opp else None

    return {
        "vpip": pct(vpip, hands),
        "pfr": pct(pfr, hands),
        "three_bet": pct(tb, tb_opp),
        "fold_3bet": pct(f3b, f3b_opp),
        "wwsf": pct(wsf, sf),
        "wtsd": pct(wtsd_num, sf),
    }
