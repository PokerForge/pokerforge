"""Fast, SQL-backed replacements for ui/hero_overview.py's
compute_hero_overview, ui/population_summary.py's build_population_summary,
and ui/compute_stats.py's compute_all_stats/ui/villain_graph.py's
compute_villain_graph. Same output shapes as those functions, but backed
by hand_player_stats's precomputed columns instead of live Python
recomputation — a period change (or a villain click) becomes one indexed
aggregate query instead of a full re-walk of every hand's raw actions,
which is what made "All Time" (and, to a lesser extent, EV BB/100 on a
high-volume villain) slow before."""
from datetime import date, datetime, timedelta

from ui.population_summary import PopulationRow
from ui.hero_detect import ANON_PLACEHOLDER
from database.repository import _STATS_COLS
from database.hand_loader import load_actions_and_winnings
from core.settlement import settlement_for_player

_META_COLS = {'hand_id', 'player_name', 'played_at', 'big_blind', 'profit', 'ev', 'position', 'stakes_label'}
_FLAG_COLS = [c for c in _STATS_COLS if c not in _META_COLS]

# (StreetAggregate property, values-dict key suffix) — mirrors
# ui/compute_stats.py's _STREET_KEYS exactly, so villain_stats_query
# produces the identical {stat_id: value} shape the UI already expects.
_STREET_KEYS = [
    ("cbet", "cbet_opp", "cbet"), ("folded_to_cbet", "faced_cbet_opp", "fold_cbet"),
    ("xr", "xr_opp", "xr"), ("folded_to_xr", "faced_xr_opp", "fold_xr"),
    ("donk", "donk_opp", "donk"), ("folded_to_donk", "faced_donk_opp", "fold_donk"),
    ("folded_to_bet", "face_bet_opp", "fold_bet"), ("folded_to_2bet", "face_2bet_opp", "fold_2bet"),
    ("folded_to_3bet", "face_3bet_opp", "fold_3bet_street"),
    ("float_bet", "float_opp", "float"), ("folded_to_float", "faced_float_opp", "fold_float"),
]


def _date_bounds(d_from: date, d_to: date) -> tuple[str, str]:
    return d_from.isoformat(), (d_to + timedelta(days=1)).isoformat()


def _pct(made, opp):
    return round(100.0 * made / opp, 2) if opp else None


_OVERVIEW_SQL = """
SELECT
    COUNT(*),
    SUM(vpip_pfr_opp), SUM(vpip), SUM(pfr),
    SUM(three_bet), SUM(three_bet_opp),
    SUM(folded_to_3bet), SUM(faced_3bet_opp),
    SUM(four_bet), SUM(four_bet_opp),
    SUM(folded_to_4bet), SUM(faced_4bet_opp),
    SUM(saw_flop), SUM(reached_showdown),
    SUM(CASE WHEN reached_showdown = 1 AND won_hand = 1 THEN 1 ELSE 0 END),
    SUM(CASE WHEN saw_flop = 1 AND won_hand = 1 THEN 1 ELSE 0 END),
    SUM(profit),
    SUM(CASE WHEN big_blind > 0 THEN profit / big_blind ELSE 0 END),
    SUM(CASE WHEN big_blind > 0 THEN 1 ELSE 0 END),
    SUM(CASE WHEN big_blind > 0 THEN COALESCE(ev, profit) / big_blind ELSE 0 END)
FROM hand_player_stats
WHERE player_name = ? AND played_at >= ? AND played_at < ?
"""


def hero_overview_query(db, hero: str, d_from: date, d_to: date, stake: str | None = None):
    """Returns (values, graph) matching compute_hero_overview's shape."""
    lo, hi = _date_bounds(d_from, d_to)
    params = [hero, lo, hi]
    sql = _OVERVIEW_SQL
    if stake:
        sql += " AND stakes_label = ?"
        params.append(stake)

    row = db.conn.execute(sql, params).fetchone()
    (hands, vpip_pfr_opp, vpip, pfr, three_bet, three_bet_opp, folded_to_3bet, faced_3bet_opp,
     four_bet, four_bet_opp, folded_to_4bet, faced_4bet_opp,
     saw_flop, reached_showdown, won_showdown, won_saw_flop,
     total_profit, bb_sum, bb_hands, ev_bb_sum) = row

    values = {
        'hands': hands or 0,
        'profit': total_profit or 0.0,
        'bb100': round(100.0 * bb_sum / bb_hands, 2) if bb_hands else None,
        'ev_bb100': round(100.0 * ev_bb_sum / bb_hands, 2) if bb_hands else None,
        'vpip': _pct(vpip, vpip_pfr_opp), 'pfr': _pct(pfr, vpip_pfr_opp),
        'three_bet': _pct(three_bet, three_bet_opp), 'fold_3bet': _pct(folded_to_3bet, faced_3bet_opp),
        'four_bet': _pct(four_bet, four_bet_opp), 'fold_4bet': _pct(folded_to_4bet, faced_4bet_opp),
        'wtsd': _pct(reached_showdown, saw_flop), 'wwsf': _pct(won_saw_flop, saw_flop),
        'wsd': _pct(won_showdown, reached_showdown),
    }

    graph_sql = ("SELECT profit, ev, reached_showdown, big_blind FROM hand_player_stats "
                 "WHERE player_name = ? AND played_at >= ? AND played_at < ?")
    graph_params = [hero, lo, hi]
    if stake:
        graph_sql += " AND stakes_label = ?"
        graph_params.append(stake)
    graph_sql += " ORDER BY played_at"

    # BB-normalized lines are a SECOND running sum, not a rescale of the $
    # one — each hand is divided by ITS OWN big_blind before accumulating
    # (same approach as the bb100 stat), so hands from different stakes mix
    # correctly instead of one $1 hand and one $5 hand counting equally.
    xs, total, showdown, non_showdown, ev_line = [], [], [], [], []
    total_bb, showdown_bb, non_showdown_bb, ev_bb_line = [], [], [], []
    running_total = running_sd = running_nonsd = running_ev = 0.0
    running_total_bb = running_sd_bb = running_nonsd_bb = running_ev_bb = 0.0
    for i, (profit, ev, reached_sd, big_blind) in enumerate(db.conn.execute(graph_sql, graph_params), 1):
        ev_val = ev if ev is not None else profit
        bb = profit / big_blind if big_blind else 0.0
        ev_bb = ev_val / big_blind if big_blind else 0.0
        running_total += profit
        running_ev += ev_val
        running_total_bb += bb
        running_ev_bb += ev_bb
        if reached_sd:
            running_sd += profit
            running_sd_bb += bb
        else:
            running_nonsd += profit
            running_nonsd_bb += bb
        xs.append(i)
        total.append(running_total)
        showdown.append(running_sd)
        non_showdown.append(running_nonsd)
        ev_line.append(running_ev)
        total_bb.append(running_total_bb)
        showdown_bb.append(running_sd_bb)
        non_showdown_bb.append(running_nonsd_bb)
        ev_bb_line.append(running_ev_bb)

    return values, (xs, total, showdown, non_showdown, ev_line, total_bb, showdown_bb, non_showdown_bb, ev_bb_line)


def sessions_query(db, hero: str, d_from: date, d_to: date, stake: str | None = None):
    """One row per (calendar day, stakes) group hero played — matches
    poker_dashboard_legacy.py's calc_sessions() grouping exactly (a
    session is a date+stakes bucket, not a real time-gap-detected sitting,
    so two sittings at the same stakes on the same day merge into one
    row — same simplification the legacy tool made). Returns rows newest
    first as (date_str, stakes_label, hands, profit, bb100, ev_bb100, hours)."""
    lo, hi = _date_bounds(d_from, d_to)
    params = [hero, lo, hi]
    sql = """
        SELECT date(played_at), stakes_label, COUNT(*), SUM(profit),
            SUM(CASE WHEN big_blind > 0 THEN profit / big_blind ELSE 0 END),
            SUM(CASE WHEN big_blind > 0 THEN COALESCE(ev, profit) / big_blind ELSE 0 END),
            SUM(CASE WHEN big_blind > 0 THEN 1 ELSE 0 END),
            MIN(played_at), MAX(played_at)
        FROM hand_player_stats
        WHERE player_name = ? AND played_at >= ? AND played_at < ?
    """
    if stake:
        sql += " AND stakes_label = ?"
        params.append(stake)
    sql += " GROUP BY date(played_at), stakes_label ORDER BY date(played_at) DESC, stakes_label DESC"

    rows = []
    for d, stakes_label, hands, profit, bb_sum, ev_bb_sum, bb_hands, min_ts, max_ts in db.conn.execute(sql, params):
        bb100 = round(100.0 * bb_sum / bb_hands, 2) if bb_hands else 0.0
        ev_bb100 = round(100.0 * ev_bb_sum / bb_hands, 2) if bb_hands else 0.0
        if min_ts and max_ts and max_ts > min_ts:
            hours = round((datetime.fromisoformat(max_ts) - datetime.fromisoformat(min_ts))
                          .total_seconds() / 3600, 2)
        else:
            hours = 0.0
        rows.append((d, stakes_label, hands, round(profit, 2), bb100, ev_bb100, hours))
    return rows


def pct_trend_query(db, hero: str, d_from: date, d_to: date, stat_ids: list[str],
                      stake: str | None = None, interval_days: int = 7):
    """One check-in point per `interval_days`-long slice of [d_from, d_to]
    — each slice's OWN rate for every stat in `stat_ids`, not a
    cumulative/running average, so a change made partway through the
    range actually shows up instead of getting diluted by everything
    played before it. Reuses _villain_stats_from_where's exact,
    already-validated formulas once per slice rather than a new
    hand-rolled aggregation (same approach position_breakdown_query
    takes, just sliced by date instead of by position).
    Returns (bucket_starts, {stat_id: [values_or_None...]}, hand_counts)."""
    bucket_starts: list[str] = []
    hand_counts: list[int] = []
    series: dict[str, list[float | None]] = {sid: [] for sid in stat_ids}

    cur = d_from
    while cur <= d_to:
        bucket_end = min(cur + timedelta(days=interval_days - 1), d_to)
        lo, hi = _date_bounds(cur, bucket_end)
        where = ["player_name = ?", "played_at >= ?", "played_at < ?"]
        params = [hero, lo, hi]
        if stake:
            where.append("stakes_label = ?")
            params.append(stake)
        values, hand_count, _, _ = _villain_stats_from_where(db, " AND ".join(where), params)

        bucket_starts.append(cur.isoformat())
        hand_counts.append(hand_count)
        for sid in stat_ids:
            series[sid].append(values.get(sid))
        cur = bucket_end + timedelta(days=1)

    return bucket_starts, series, hand_counts


def hands_for_session_query(db, hero: str, session_date: str, stakes_label: str | None):
    """Every hand in one (date, stakes) session row from sessions_query —
    same (hand_id, played_at, stakes_label, profit, ev) shape
    hands_for_stat_query returns, so it drops straight into
    HandListDialog for the double-click-to-replay flow."""
    where = ["player_name = ?", "date(played_at) = ?"]
    params = [hero, session_date]
    if stakes_label is None:
        where.append("stakes_label IS NULL")
    else:
        where.append("stakes_label = ?")
        params.append(stakes_label)
    return db.conn.execute(
        f"SELECT hand_id, played_at, stakes_label, profit, ev FROM hand_player_stats "
        f"WHERE {' AND '.join(where)} ORDER BY played_at",
        params).fetchall()


_POPULATION_SQL = """
SELECT player_name, COUNT(*),
    SUM(vpip_pfr_opp), SUM(vpip), SUM(pfr), SUM(three_bet), SUM(three_bet_opp),
    SUM(folded_to_3bet), SUM(faced_3bet_opp),
    SUM(saw_flop), SUM(reached_showdown),
    SUM(CASE WHEN saw_flop = 1 AND won_hand = 1 THEN 1 ELSE 0 END),
    SUM(profit)
FROM hand_player_stats
WHERE played_at >= ? AND played_at < ? AND player_name != ?
"""


def population_summary_query(db, hero: str, d_from: date, d_to: date, stake: str | None = None):
    lo, hi = _date_bounds(d_from, d_to)
    params = [lo, hi, hero]
    sql = _POPULATION_SQL
    if stake:
        sql += " AND stakes_label = ?"
        params.append(stake)
    sql += " GROUP BY player_name"

    result: dict[str, PopulationRow] = {}
    for (name, hands, vpip_pfr_opp, vpip, pfr, tb, tb_opp, f3b, f3b_opp, saw_flop, rsd, wsf, total_profit) in db.conn.execute(sql, params):
        if ANON_PLACEHOLDER.match(name):
            continue
        row = PopulationRow(name)
        row.hands = hands
        row.vpip_pfr_opp = vpip_pfr_opp or 0
        row.vpip, row.pfr = vpip or 0, pfr or 0
        row.three_bet, row.three_bet_opp = tb or 0, tb_opp or 0
        row.folded_to_3bet, row.faced_3bet_opp = f3b or 0, f3b_opp or 0
        row.saw_flop, row.reached_showdown = saw_flop or 0, rsd or 0
        row.won_saw_flop = wsf or 0
        row.total_profit = total_profit or 0.0
        result[name] = row
    return result


def hero_vpip_sequence_query(db, hero: str, d_from: date, d_to: date, stake: str | None = None):
    """(played_at, profit, big_blind, vpip, vpip_pfr_opp) for every one of
    hero's hands in the period, ordered by played_at — the backing data
    for core.tilt_correlation, which needs to walk hands in sequence to
    find what happened shortly after a big loss. Scoped to VPIP only for
    now (the most fundamental "playing too loose" signal); the same
    shape would extend to another stat by selecting its own made/
    opportunity columns instead."""
    lo, hi = _date_bounds(d_from, d_to)
    where = ["player_name = ?", "played_at >= ?", "played_at < ?"]
    params = [hero, lo, hi]
    if stake:
        where.append("stakes_label = ?")
        params.append(stake)
    sql = (f"SELECT played_at, profit, big_blind, vpip, vpip_pfr_opp FROM hand_player_stats "
           f"WHERE {' AND '.join(where)} ORDER BY played_at")
    return db.conn.execute(sql, params).fetchall()


def showdown_hand_ids_query(db, hero: str, d_from: date, d_to: date, stake: str | None = None,
                              limit: int | None = 5000) -> list[str]:
    """Hand ids where some player OTHER than hero reached showdown — the
    cheap pre-filter for core.river_sizing.classify_river_sizing_vs_strength,
    which needs full Hand objects (raw actions, hole cards) that only
    exist for a small fraction of hands. Loading every hand in the
    database just to discard the ones that never reached a river bet
    would be wasteful; this narrows to the (usually 15-20%) of hands
    that could possibly qualify before any Python-side hand loading
    happens. `limit` caps how many hand ids come back — a full-database
    population sizing pass is meant to be a periodic, on-demand report
    (Population tab's Pool Insights), not a live-refreshing query, so an
    unbounded pass over a very large database isn't worth the latency
    for one more precision point; None removes the cap entirely."""
    lo, hi = _date_bounds(d_from, d_to)
    where = ["reached_showdown = 1", "player_name != ?", "played_at >= ?", "played_at < ?"]
    params = [hero, lo, hi]
    if stake:
        where.append("stakes_label = ?")
        params.append(stake)
    sql = f"SELECT DISTINCT hand_id FROM hand_player_stats WHERE {' AND '.join(where)}"
    if limit is not None:
        sql += " LIMIT ?"
        params.append(limit)
    return [r[0] for r in db.conn.execute(sql, params)]


def available_stakes_query(db, hero: str, d_from: date, d_to: date) -> list[str]:
    lo, hi = _date_bounds(d_from, d_to)
    rows = db.conn.execute(
        "SELECT DISTINCT stakes_label, big_blind FROM hand_player_stats "
        "WHERE player_name = ? AND played_at >= ? AND played_at < ?",
        [hero, lo, hi]).fetchall()
    seen = {label: (bb or 0) for label, bb in rows if label}
    return [label for label, _ in sorted(seen.items(), key=lambda kv: kv[1])]


def villain_stats_query(db, player_name: str, d_from: date | None = None, d_to: date | None = None,
                          stake: str | None = None):
    """Returns (values, hand_count, vs_open, opp_counts) matching
    compute_all_stats's shape exactly — vs_open is always {} since that
    section was removed from the villain profile display and was never
    wired into the database (see ui/main_window.py's _render_villain).
    opp_counts is the opportunity-count denominator behind each
    percentage in `values`, for sample-size display."""
    where = ["player_name = ?"]
    params = [player_name]
    if d_from and d_to:
        lo, hi = _date_bounds(d_from, d_to)
        where += ["played_at >= ?", "played_at < ?"]
        params += [lo, hi]
    if stake:
        where.append("stakes_label = ?")
        params.append(stake)
    return _villain_stats_from_where(db, " AND ".join(where), params)


def position_breakdown_query(db, player_name: str, d_from: date | None = None, d_to: date | None = None,
                               stake: str | None = None):
    """Per-position breakdown for the Stats tab — same "first pass" stat
    set as villain_stats_query, computed once per position rather than as
    a new hand-rolled aggregation, so every number is produced by the
    exact same already-validated formula as the overall totals (only the
    WHERE clause changes). Returns {position: (values, hand_count,
    opp_counts)}, ordered by whatever position strings are actually
    present in the data.

    Heads-up hands are stored as the distinct label 'BTN/SB' (needed
    elsewhere — core.position's postflop acting-order logic treats it
    like a button, not a small blind, since it acts LAST postflop) but
    are folded into the 'SB' bucket here, matching a real PT4 by-position
    export: SB's hand count only reconciled once 'BTN/SB' hands were
    added to it (confirmed, not guessed — see core/position.py's
    POSITION_LABELS comment for the sibling fix this same export drove)."""
    where = ["player_name = ?"]
    params = [player_name]
    if d_from and d_to:
        lo, hi = _date_bounds(d_from, d_to)
        where += ["played_at >= ?", "played_at < ?"]
        params += [lo, hi]
    if stake:
        where.append("stakes_label = ?")
        params.append(stake)
    base_where = " AND ".join(where)

    raw_positions = {r[0] for r in db.conn.execute(
        f"SELECT DISTINCT position FROM hand_player_stats WHERE {base_where} AND position IS NOT NULL",
        params)}
    display_positions = {'SB' if p == 'BTN/SB' else p for p in raw_positions}

    result = {}
    for pos in display_positions:
        if pos == 'SB':
            condition, extra_params = "position IN ('SB', 'BTN/SB')", []
        else:
            condition, extra_params = "position = ?", [pos]
        values, hand_count, _, opp_counts = _villain_stats_from_where(
            db, base_where + " AND " + condition, params + extra_params)
        result[pos] = (values, hand_count, opp_counts)
    return result


def population_by_position_query(db, hero: str, d_from: date | None = None, d_to: date | None = None,
                                   stake: str | None = None):
    """Same shape and same underlying formula as position_breakdown_query,
    but pooled across every OTHER player instead of hero — lets a leak
    search compare "your 3-bet% from the CO" against "the pool's 3-bet%
    from the CO" instead of only against one flat overall population
    number (see core/leak_finder.py, which is what actually consumes
    this). Deliberately duplicated rather than sharing a helper with
    position_breakdown_query — the WHERE clause differs by exactly one
    condition (!= vs =), and that's a small enough difference that a
    shared abstraction would obscure more than it saves."""
    where = ["player_name != ?"]
    params = [hero]
    if d_from and d_to:
        lo, hi = _date_bounds(d_from, d_to)
        where += ["played_at >= ?", "played_at < ?"]
        params += [lo, hi]
    if stake:
        where.append("stakes_label = ?")
        params.append(stake)
    base_where = " AND ".join(where)

    raw_positions = {r[0] for r in db.conn.execute(
        f"SELECT DISTINCT position FROM hand_player_stats WHERE {base_where} AND position IS NOT NULL",
        params)}
    display_positions = {'SB' if p == 'BTN/SB' else p for p in raw_positions}

    result = {}
    for pos in display_positions:
        if pos == 'SB':
            condition, extra_params = "position IN ('SB', 'BTN/SB')", []
        else:
            condition, extra_params = "position = ?", [pos]
        values, hand_count, _, opp_counts = _villain_stats_from_where(
            db, base_where + " AND " + condition, params + extra_params)
        result[pos] = (values, hand_count, opp_counts)
    return result


def villain_group_stats_query(db, names: list[str], d_from: date | None = None, d_to: date | None = None,
                                stake: str | None = None):
    """Same shape as villain_stats_query, but pooled across a GROUP of
    villains (e.g. everyone currently tagged "Fish") — summed raw counts
    across every one of them, not an average of each villain's own
    percentage, matching the same pooled-stats convention this app's
    accuracy work already established (see the VPIP/PFR/3-bet fixes)."""
    if not names:
        return {}, 0, {}, {}
    placeholders = ",".join("?" for _ in names)
    where = [f"player_name IN ({placeholders})"]
    params = list(names)
    if d_from and d_to:
        lo, hi = _date_bounds(d_from, d_to)
        where += ["played_at >= ?", "played_at < ?"]
        params += [lo, hi]
    if stake:
        where.append("stakes_label = ?")
        params.append(stake)
    return _villain_stats_from_where(db, " AND ".join(where), params)


def _villain_stats_from_where(db, where_sql: str, params: list):
    sum_clause = ", ".join(f"SUM({c})" for c in _FLAG_COLS)
    sql = f"""SELECT COUNT(*), {sum_clause},
        SUM(CASE WHEN reached_showdown = 1 AND won_hand = 1 THEN 1 ELSE 0 END),
        SUM(CASE WHEN saw_flop = 1 AND won_hand = 1 THEN 1 ELSE 0 END),
        SUM(CASE WHEN big_blind > 0 THEN profit / big_blind ELSE 0 END),
        SUM(CASE WHEN big_blind > 0 THEN 1 ELSE 0 END),
        SUM(CASE WHEN big_blind > 0 THEN COALESCE(ev, profit) / big_blind ELSE 0 END),
        SUM(profit)
        FROM hand_player_stats WHERE {where_sql}"""
    row = db.conn.execute(sql, params).fetchone()

    hand_count = row[0] or 0
    n = len(_FLAG_COLS)
    f = {col: (v or 0) for col, v in zip(_FLAG_COLS, row[1:1 + n])}
    won_showdown, won_saw_flop, bb_sum, bb_hands, ev_bb_sum, profit_sum = (v or 0 for v in row[1 + n:1 + n + 6])

    values = {
        "profit": profit_sum,
        "bb_per_hand": round(bb_sum / bb_hands, 4) if bb_hands else None,
        "bb100": round(100.0 * bb_sum / bb_hands, 2) if bb_hands else None,
        "ev_bb100": round(100.0 * ev_bb_sum / bb_hands, 2) if bb_hands else None,
        "wtsd": _pct(f['reached_showdown'], f['saw_flop']),
        "wsd": _pct(won_showdown, f['reached_showdown']),
        "wwsf": _pct(won_saw_flop, f['saw_flop']),
        "total_af": (round((f['flop_bet_raise'] + f['turn_bet_raise'] + f['river_bet_raise'])
                     / (f['flop_call'] + f['turn_call'] + f['river_call']), 2)
                     if (f['flop_call'] + f['turn_call'] + f['river_call']) else None),
        "total_afq": _pct(f['flop_bet_raise'] + f['turn_bet_raise'] + f['river_bet_raise'],
                           f['flop_bet_raise'] + f['turn_bet_raise'] + f['river_bet_raise']
                           + f['flop_call'] + f['turn_call'] + f['river_call']
                           + f['flop_fold'] + f['turn_fold'] + f['river_fold']),
        "vpip": _pct(f['vpip'], f['vpip_pfr_opp']), "pfr": _pct(f['pfr'], f['vpip_pfr_opp']),
        "three_bet": _pct(f['three_bet'], f['three_bet_opp']),
        "fold_3bet": _pct(f['folded_to_3bet'], f['faced_3bet_opp']),
        "four_bet": _pct(f['four_bet'], f['four_bet_opp']),
        "fold_4bet": _pct(f['folded_to_4bet'], f['faced_4bet_opp']),
        "squeeze": _pct(f['squeeze'], f['squeeze_opp']),
        "raise_vs_squeeze": _pct(f['raised_vs_squeeze'], f['squeeze_def_opp']),
        "fold_to_squeeze": _pct(f['folded_to_squeeze'], f['squeeze_def_opp']),
        "steal_att": _pct(f['steal_att'], f['steal_opp']),
        "steal_success": _pct(f['steal_success'], f['steal_att']),
        "fold_to_steal": _pct(f['folded_to_steal'], f['blind_def_opp']),
        "preflop_af": round(f['preflop_bet_raise'] / f['preflop_call'], 2) if f['preflop_call'] else None,
        "preflop_afq": _pct(f['preflop_bet_raise'], f['preflop_bet_raise'] + f['preflop_call'] + f['preflop_fold']),
    }

    for street in ("flop", "turn", "river"):
        for made_key, opp_key, out_key in _STREET_KEYS:
            values[f"{street}_{out_key}"] = _pct(f[f"{street}_{made_key}"], f[f"{street}_{opp_key}"])
        bet_raise, call, fold = f[f"{street}_bet_raise"], f[f"{street}_call"], f[f"{street}_fold"]
        values[f"{street}_af"] = round(bet_raise / call, 2) if call else None
        values[f"{street}_afq"] = _pct(bet_raise, bet_raise + call + fold)

    values["turn_probe"] = _pct(f['probe_turn'], f['probe_turn_opp'])
    values["turn_fold_probe"] = _pct(f['folded_to_probe_turn'], f['faced_probe_turn_opp'])
    values["river_probe"] = _pct(f['probe_river'], f['probe_river_opp'])
    values["river_fold_probe"] = _pct(f['folded_to_probe_river'], f['faced_probe_river_opp'])

    # The opportunity count behind each percentage — same denominator each
    # _pct() call above used — so a display can flag "5.87% on 12 hands"
    # as too small a sample to read anything into, instead of just
    # showing the raw (possibly noisy) percentage on its own.
    opp_counts = {
        "vpip": f['vpip_pfr_opp'], "pfr": f['vpip_pfr_opp'],
        "three_bet": f['three_bet_opp'], "fold_3bet": f['faced_3bet_opp'],
        "four_bet": f['four_bet_opp'], "fold_4bet": f['faced_4bet_opp'],
        "squeeze": f['squeeze_opp'], "raise_vs_squeeze": f['squeeze_def_opp'],
        "fold_to_squeeze": f['squeeze_def_opp'],
        "steal_att": f['steal_opp'], "steal_success": f['steal_att'],
        "fold_to_steal": f['blind_def_opp'],
        "wtsd": f['saw_flop'], "wsd": f['reached_showdown'], "wwsf": f['saw_flop'],
        "preflop_afq": f['preflop_bet_raise'] + f['preflop_call'] + f['preflop_fold'],
    }
    for street in ("flop", "turn", "river"):
        for made_key, opp_key, out_key in _STREET_KEYS:
            opp_counts[f"{street}_{out_key}"] = f[f"{street}_{opp_key}"]
        opp_counts[f"{street}_afq"] = (f[f"{street}_bet_raise"] + f[f"{street}_call"] + f[f"{street}_fold"])
    opp_counts["turn_probe"] = f['probe_turn_opp']
    opp_counts["turn_fold_probe"] = f['faced_probe_turn_opp']
    opp_counts["river_probe"] = f['probe_river_opp']
    opp_counts["river_fold_probe"] = f['faced_probe_river_opp']

    return values, hand_count, {}, opp_counts


def villain_graph_query(db, hero: str, villain: str, d_from: date | None = None, d_to: date | None = None):
    """Returns (graph, v_profit, hero_vs_profit) matching
    ui/villain_graph.py's compute_villain_graph — villain's own running
    total/showdown/non-showdown profit, plus hero's running profit in the
    same hands. Every hand includes hero by construction (hand histories
    only cover hands the account owner played), so "hands with this
    villain" already means "hands where hero and villain both played" —
    no extra join needed, just two independently-filtered fetches over
    the same date range."""
    where = ["player_name = ?"]
    params = [villain]
    if d_from and d_to:
        lo, hi = _date_bounds(d_from, d_to)
        where += ["played_at >= ?", "played_at < ?"]
        params += [lo, hi]
    return _villain_graph_from_where(db, hero, " AND ".join(where), params)


def villain_group_graph_query(db, hero: str, names: list[str], d_from: date | None = None,
                                d_to: date | None = None):
    """Same shape as villain_graph_query, but pooled across a GROUP of
    villains — each pooled villain's own profit is summed independently
    (so the "combined villain profit" line is a genuine total of everyone's
    results), but hero's own profit in a hand is only ever counted ONCE per
    hand even if two pooled villains both sat in it, since hero didn't win
    or lose that hand twice."""
    if not names:
        return ([], [], [], [], [], [], [], [], [], [], []), 0.0, 0.0
    placeholders = ",".join("?" for _ in names)
    where = [f"player_name IN ({placeholders})"]
    params = list(names)
    if d_from and d_to:
        lo, hi = _date_bounds(d_from, d_to)
        where += ["played_at >= ?", "played_at < ?"]
        params += [lo, hi]
    return _villain_graph_from_where(db, hero, " AND ".join(where), params)


def _villain_graph_from_where(db, hero: str, where_sql: str, params: list):
    # player_name is needed per-row now (not just hand_id) so a hand with
    # two POOLED group members can be settled against EACH of them
    # separately, rather than needing to dedupe hero's result per hand the
    # way the old "attribute the whole hand" approach had to.
    v_rows = db.conn.execute(
        f"SELECT hand_id, player_name, profit, reached_showdown, big_blind, ev FROM hand_player_stats "
        f"WHERE {where_sql} ORDER BY played_at, hand_id",
        params).fetchall()

    # "Vs Me" is a real per-hand pot settlement (core.settlement) rather
    # than crediting/blaming a villain for hero's ENTIRE hand result just
    # for being dealt in — that previous approach produced numbers with the
    # wrong sign for most villains, confirmed against a real PT4
    # per-opponent export. Settlement needs each hand's actions/winnings
    # replayed, so those are bulk-loaded once for exactly the hands
    # involved here (not the whole database).
    unique_hand_ids = list(dict.fromkeys(r[0] for r in v_rows))
    hand_data = load_actions_and_winnings(db, unique_hand_ids)
    hero_settlement_by_hand = {
        hid: settlement_for_player(*hand_data.get(hid, ([], {})), hero)
        for hid in unique_hand_ids
    }

    # BB-normalized lines are a second running sum (each hand divided by
    # ITS OWN big_blind before accumulating), same approach as bb100 — not
    # a rescale of the $ total — so hands from different stakes mix
    # correctly. ev is already computed per player row at import time
    # (core.ev, via hand_stats_builder), same column hero's own EV line
    # reads, just keyed to the villain's name here instead of hero's.
    xs, v_total, v_sd, v_nonsd, v_ev, hero_vs = [], [], [], [], [], []
    v_total_bb, v_sd_bb, v_nonsd_bb, v_ev_bb, hero_vs_bb = [], [], [], [], []
    running_v = running_sd = running_nonsd = running_ev = running_hero = 0.0
    running_v_bb = running_sd_bb = running_nonsd_bb = running_ev_bb = running_hero_bb = 0.0
    for i, (hand_id, villain_name, profit, reached_sd, big_blind, ev) in enumerate(v_rows, 1):
        ev_val = ev if ev is not None else profit
        bb = profit / big_blind if big_blind else 0.0
        ev_bb = ev_val / big_blind if big_blind else 0.0
        hero_settle = hero_settlement_by_hand.get(hand_id, {}).get(villain_name, 0.0)
        hero_settle_bb = hero_settle / big_blind if big_blind else 0.0

        running_v += profit
        running_ev += ev_val
        running_v_bb += bb
        running_ev_bb += ev_bb
        if reached_sd:
            running_sd += profit
            running_sd_bb += bb
        else:
            running_nonsd += profit
            running_nonsd_bb += bb
        running_hero += hero_settle
        running_hero_bb += hero_settle_bb

        xs.append(i)
        v_total.append(running_v)
        v_sd.append(running_sd)
        v_nonsd.append(running_nonsd)
        v_ev.append(running_ev)
        hero_vs.append(running_hero)
        v_total_bb.append(running_v_bb)
        v_sd_bb.append(running_sd_bb)
        v_nonsd_bb.append(running_nonsd_bb)
        v_ev_bb.append(running_ev_bb)
        hero_vs_bb.append(running_hero_bb)

    return (xs, v_total, v_sd, v_nonsd, v_ev, hero_vs,
            v_total_bb, v_sd_bb, v_nonsd_bb, v_ev_bb, hero_vs_bb), running_v, running_hero


# stat_id -> SQL condition selecting the hands that "made" that stat —
# the DB-backed replacement for ui/stat_hands.py's STAT_PREDICATES. Same
# coverage (not every stat in STAT_REGISTRY is wired up), but reading a
# precomputed column is now just a WHERE clause instead of re-deriving
# the flag from raw actions.
STAT_COLUMN_CONDITIONS = {
    'vpip': 'vpip = 1',
    'pfr': 'pfr = 1',
    'three_bet': 'three_bet = 1',
    'fold_3bet': 'folded_to_3bet = 1',
    'four_bet': 'four_bet = 1',
    'fold_4bet': 'folded_to_4bet = 1',
    'squeeze': 'squeeze = 1',
    'raise_vs_squeeze': 'raised_vs_squeeze = 1',
    'fold_to_squeeze': 'folded_to_squeeze = 1',
    'fold_to_steal': 'folded_to_steal = 1',
    'wtsd': 'reached_showdown = 1',
    'wwsf': 'saw_flop = 1 AND won_hand = 1',
    'wsd': 'reached_showdown = 1 AND won_hand = 1',
}
for _street in ('flop', 'turn', 'river'):
    STAT_COLUMN_CONDITIONS[f'{_street}_cbet'] = f'{_street}_cbet = 1'
    STAT_COLUMN_CONDITIONS[f'{_street}_fold_cbet'] = f'{_street}_folded_to_cbet = 1'
    STAT_COLUMN_CONDITIONS[f'{_street}_xr'] = f'{_street}_xr = 1'
    STAT_COLUMN_CONDITIONS[f'{_street}_donk'] = f'{_street}_donk = 1'

DRILLDOWN_STAT_IDS = set(STAT_COLUMN_CONDITIONS.keys())

# leak_id (from ui/player_classify.generate_hero_leaks) -> SQL condition
# for the hands that best ILLUSTRATE that leak — deliberately not always
# the same as the underlying stat's own numerator. "Low 3-Bet" is more
# useful shown as the hands you COULD have 3-bet and didn't (the missed
# opportunities), not the rare ones you did; "Low win rate at showdown"
# is more useful shown as the showdowns you lost, not the ones you won.
LEAK_HAND_CONDITIONS = {
    'vpip_loose': 'vpip = 1',
    'vpip_tight': 'vpip = 0 AND vpip_pfr_opp = 1',
    'limping': 'vpip = 1 AND pfr = 0',
    'three_bet_low': 'three_bet_opp = 1 AND three_bet = 0',
    'fold_3bet_high': 'folded_to_3bet = 1',
    'fold_3bet_good': 'faced_3bet_opp = 1',
    'four_bet_high': 'four_bet = 1',
    'fold_4bet_high': 'folded_to_4bet = 1',
    'fold_steal_high': 'folded_to_steal = 1',
    'fold_cbet_high': 'flop_folded_to_cbet = 1',
    'fold_cbet_low': 'flop_faced_cbet_opp = 1 AND flop_folded_to_cbet = 0',
    'wtsd_high': 'reached_showdown = 1',
    'wtsd_low': 'saw_flop = 1 AND reached_showdown = 0',
    'wsd_low': 'reached_showdown = 1 AND won_hand = 0',
}


def hands_for_stat_query(db, player_name: str, stat_id: str,
                           d_from: date | None = None, d_to: date | None = None, stake: str | None = None,
                           position: str | None = None):
    """Returns (hand_id, played_at, stakes_label, profit, ev) tuples for
    every hand where `player_name` "made" `stat_id` — the backing data for
    the hand-list dialog. The full hand (for replay, and for the rest of
    the dialog's PT4-style columns) is bulk-loaded lazily via
    database.hand_loader.load_hands_bulk only once the dialog opens.
    `position` optionally narrows to one seat (see position_breakdown_query
    for the 'SB' includes-heads-up-BTN/SB convention this follows)."""
    condition = STAT_COLUMN_CONDITIONS.get(stat_id)
    if condition is None:
        return []
    return _hands_matching(db, player_name, condition, d_from, d_to, stake, position)


def hands_for_leak_query(db, player_name: str, leak_id: str,
                           d_from: date | None = None, d_to: date | None = None, stake: str | None = None):
    """Same shape as hands_for_stat_query, but keyed by a leak_id from
    ui/player_classify.generate_hero_leaks (LEAK_HAND_CONDITIONS above) —
    the illustrative hand set for a leak isn't always the same condition
    as the stat's own numerator."""
    condition = LEAK_HAND_CONDITIONS.get(leak_id)
    if condition is None:
        return []
    return _hands_matching(db, player_name, condition, d_from, d_to, stake)


def hands_for_position_query(db, player_name: str, position: str | None,
                               d_from: date | None = None, d_to: date | None = None, stake: str | None = None):
    """Same shape as hands_for_stat_query, but with no stat condition at
    all — every hand `player_name` played from `position` (or every hand
    in the period if `position` is None, matching the By Position table's
    'ALL' row)."""
    return _hands_matching(db, player_name, "1=1", d_from, d_to, stake, position)


def _hands_matching(db, player_name: str, condition: str,
                      d_from: date | None, d_to: date | None, stake: str | None,
                      position: str | None = None):
    where = ["player_name = ?", condition]
    params = [player_name]
    if d_from and d_to:
        lo, hi = _date_bounds(d_from, d_to)
        where += ["played_at >= ?", "played_at < ?"]
        params += [lo, hi]
    if stake:
        where.append("stakes_label = ?")
        params.append(stake)
    if position:
        if position == 'SB':
            where.append("position IN ('SB', 'BTN/SB')")
        else:
            where.append("position = ?")
            params.append(position)
    where_sql = " AND ".join(where)
    return db.conn.execute(
        f"SELECT hand_id, played_at, stakes_label, profit, ev FROM hand_player_stats WHERE {where_sql}",
        params).fetchall()
