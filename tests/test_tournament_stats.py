from core.tournament_stats import compute_tournament_summary, compute_tournament_graph


def _row(tid, buy_in=10.0, fee=1.0, finish_position=None, payout=None, first_played_at='2026-06-01T00:00:00'):
    return {
        'tournament_id': tid, 'source': 'pokerstars', 'buy_in': buy_in, 'fee': fee,
        'hand_count': 50, 'first_played_at': first_played_at, 'last_played_at': '2026-06-01T01:00:00',
        'finish_position': finish_position, 'field_size': 100, 'payout': payout, 'currency': '$',
    }


def test_no_tournaments_at_all():
    summary = compute_tournament_summary([])
    assert summary.total_tournaments == 0
    assert summary.logged_count == 0
    assert summary.roi_pct is None


def test_tournaments_played_but_none_logged():
    rows = [_row("t1"), _row("t2")]
    summary = compute_tournament_summary(rows)
    assert summary.total_tournaments == 2
    assert summary.logged_count == 0
    assert summary.roi_pct is None
    assert summary.itm_pct is None
    assert summary.avg_finish is None
    assert summary.total_profit is None


def test_roi_and_itm_computed_only_over_logged_tournaments():
    rows = [
        _row("t1", buy_in=10.0, fee=1.0, finish_position=1, payout=100.0),  # logged, cashed
        _row("t2", buy_in=10.0, fee=1.0, finish_position=50, payout=0.0),   # logged, busted
        _row("t3"),  # unlogged -- must not affect the totals
    ]
    summary = compute_tournament_summary(rows)
    assert summary.total_tournaments == 3
    assert summary.logged_count == 2
    # cost = (10+1)*2 = 22, payout = 100+0 = 100, profit = 78
    assert summary.total_profit == 78.0
    assert summary.roi_pct == round(100.0 * 78.0 / 22.0, 1)
    assert summary.itm_pct == 50.0  # 1 of 2 logged tournaments cashed
    assert summary.avg_finish == 25.5  # (1 + 50) / 2


def test_a_zero_payout_still_counts_as_logged_not_unlogged():
    """The whole point of storing payout=None only for unlogged rows --
    a real logged min-cash-less bust (payout 0.0) must still count
    toward logged_count/ITM%, not be silently treated as unlogged."""
    rows = [_row("t1", finish_position=80, payout=0.0)]
    summary = compute_tournament_summary(rows)
    assert summary.logged_count == 1
    assert summary.itm_pct == 0.0


def test_logged_tournament_with_no_finish_position_is_excluded_from_avg_finish_only():
    rows = [_row("t1", finish_position=None, payout=50.0)]
    summary = compute_tournament_summary(rows)
    assert summary.logged_count == 1
    assert summary.avg_finish is None
    assert summary.total_profit is not None


def test_graph_is_empty_when_nothing_is_logged():
    xs, ys = compute_tournament_graph([_row("t1"), _row("t2")])
    assert xs == [] and ys == []


def test_graph_skips_unlogged_tournaments_entirely():
    """An unlogged tournament isn't plotted as $0 -- that would understate
    a real loss (the buy-in was still spent) or hide a real win."""
    rows = [
        _row("t1", buy_in=10, fee=1, payout=50.0, first_played_at='2026-06-01T00:00:00'),
        _row("t2", first_played_at='2026-06-02T00:00:00'),  # unlogged
        _row("t3", buy_in=10, fee=1, payout=0.0, first_played_at='2026-06-03T00:00:00'),
    ]
    xs, ys = compute_tournament_graph(rows)
    assert xs == [1, 2]
    assert ys == [39.0, 28.0]  # t1: 50-11=+39; t3: +39-11=+28


def test_graph_orders_chronologically_not_by_input_order():
    rows = [
        _row("later", buy_in=10, fee=0, payout=20.0, first_played_at='2026-06-05T00:00:00'),
        _row("earlier", buy_in=10, fee=0, payout=0.0, first_played_at='2026-06-01T00:00:00'),
    ]
    xs, ys = compute_tournament_graph(rows)
    assert ys == [-10.0, 0.0]  # earlier (bust, -10) first, then later (+20-10 net) added on top
