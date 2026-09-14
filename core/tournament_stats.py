"""Pure aggregation over database.queries.tournament_list_query's rows —
ROI%/ITM%/avg finish/total profit are only meaningful across tournaments
the player has actually logged a result for (no hand-history export
contains a finish position or payout), so this is careful to compute
against that subset and report how many are still missing, rather than
silently understating the numbers as if the unlogged tournaments simply
didn't happen.
"""
from dataclasses import dataclass


def _is_logged(row: dict) -> bool:
    """A tournament_list_query row that's never been logged always has
    payout=None (see that function's docstring); once logged, payout is
    always a real float (0.0 minimum) even for a min-cash-less bust."""
    return row['payout'] is not None


@dataclass
class TournamentSummary:
    total_tournaments: int
    logged_count: int
    roi_pct: float | None
    itm_pct: float | None
    avg_finish: float | None
    total_profit: float | None


def compute_tournament_summary(rows: list[dict]) -> TournamentSummary:
    logged = [r for r in rows if _is_logged(r)]
    total_tournaments = len(rows)
    logged_count = len(logged)

    if not logged:
        return TournamentSummary(total_tournaments, logged_count, None, None, None, None)

    total_cost = sum((r['buy_in'] or 0.0) + (r['fee'] or 0.0) for r in logged)
    total_payout = sum(r['payout'] or 0.0 for r in logged)
    total_profit = total_payout - total_cost
    roi_pct = round(100.0 * total_profit / total_cost, 1) if total_cost else None

    itm_count = sum(1 for r in logged if (r['payout'] or 0.0) > 0)
    itm_pct = round(100.0 * itm_count / logged_count, 1)

    finishes = [r['finish_position'] for r in logged if r['finish_position'] is not None]
    avg_finish = round(sum(finishes) / len(finishes), 1) if finishes else None

    return TournamentSummary(total_tournaments, logged_count, roi_pct, itm_pct, avg_finish, round(total_profit, 2))


def compute_tournament_graph(rows: list[dict]) -> tuple[list[int], list[float]]:
    """The tournament equivalent of Overview's cash profit graph — a
    single cumulative-$-profit line, since a tournament's result is one
    number (buy-in vs. payout), not a per-street showdown/non-showdown
    split. Only *logged* tournaments have a real profit to plot (see
    module docstring); unlogged ones are skipped entirely rather than
    plotted as $0, which would understate a real loss (the buy-in was
    still spent) or hide a real win. `xs` is tournament count in
    chronological order (mirrors Overview's own "hand count" x-axis,
    not calendar dates), matching db.queries.tournament_list_query's
    `first_played_at` for ordering."""
    logged = sorted((r for r in rows if _is_logged(r)), key=lambda r: r['first_played_at'] or '')
    xs: list[int] = []
    cumulative: list[float] = []
    running = 0.0
    for i, r in enumerate(logged, 1):
        cost = (r['buy_in'] or 0.0) + (r['fee'] or 0.0)
        running += (r['payout'] or 0.0) - cost
        xs.append(i)
        cumulative.append(round(running, 2))
    return xs, cumulative
