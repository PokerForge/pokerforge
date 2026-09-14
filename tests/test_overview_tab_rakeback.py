"""ui/overview_tab.py's Rakeback stat card — applies the user's own
configured rakeback % (Settings...) to the total rake in whatever hands
the current filter matches (values['rake'], summed by hero_overview_query).
Not configured (None) reads as "—", same convention every other stat card
here already uses for a missing value."""
import pytest


@pytest.fixture()
def qapp():
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def tab(qapp):
    from ui.overview_tab import OverviewTab
    t = OverviewTab()
    t._currency = "£"
    return t


_EMPTY_GRAPH = ([], [], [], [], [], [], [], [], [], [], [])


def test_rakeback_shows_dash_when_not_configured(tab, monkeypatch):
    import ui.overview_tab as mod
    monkeypatch.setattr(mod, "get_rakeback_pct", lambda: None)

    tab._render_cash(({"hands": 10, "rake": 20.0}, _EMPTY_GRAPH))

    assert tab.cards["rakeback"].text() == "—"


def test_rakeback_computes_amount_when_configured(tab, monkeypatch):
    import ui.overview_tab as mod
    monkeypatch.setattr(mod, "get_rakeback_pct", lambda: 30)

    tab._render_cash(({"hands": 10, "rake": 20.0}, _EMPTY_GRAPH))

    assert tab.cards["rakeback"].text() == "£+6.00"


def test_rakeback_is_zero_pounds_not_a_dash_when_explicitly_set_to_zero_percent(tab, monkeypatch):
    """0% is a real, deliberately-configured deal, not "unset" -- must
    read as £0.00, not fall back to the same "—" a None (never
    configured) value shows."""
    import ui.overview_tab as mod
    monkeypatch.setattr(mod, "get_rakeback_pct", lambda: 0)

    tab._render_cash(({"hands": 10, "rake": 20.0}, _EMPTY_GRAPH))

    assert tab.cards["rakeback"].text() == "£+0.00"


def test_rakeback_handles_a_period_with_no_rake_at_all(tab, monkeypatch):
    import ui.overview_tab as mod
    monkeypatch.setattr(mod, "get_rakeback_pct", lambda: 30)

    tab._render_cash(({"hands": 0, "rake": 0.0}, _EMPTY_GRAPH))

    assert tab.cards["rakeback"].text() == "£+0.00"


def test_profit_rakeback_shows_dash_when_not_configured(tab, monkeypatch):
    import ui.overview_tab as mod
    monkeypatch.setattr(mod, "get_rakeback_pct", lambda: None)

    tab._render_cash(({"hands": 10, "profit": 5.0, "rake": 20.0}, _EMPTY_GRAPH))

    assert tab.cards["profit_rakeback"].text() == "—"


def test_profit_rakeback_adds_rakeback_on_top_of_profit(tab, monkeypatch):
    import ui.overview_tab as mod
    monkeypatch.setattr(mod, "get_rakeback_pct", lambda: 30)

    tab._render_cash(({"hands": 10, "profit": -10.0, "rake": 20.0}, _EMPTY_GRAPH))

    # rakeback = 20.0 * 0.30 = 6.00; profit + rakeback = -10.0 + 6.00 = -4.00
    assert tab.cards["profit_rakeback"].text() == "£-4.00"


_SAMPLE_GRAPH = (
    [1, 2, 3],           # xs
    [1.0, 3.0, 2.0],      # total ($)
    [1.0, 3.0, 2.0],      # sd
    [0.0, 0.0, 0.0],      # nonsd
    [1.0, 3.0, 2.0],      # ev_line
    [10.0, 30.0, 20.0],   # total_bb
    [10.0, 30.0, 20.0],   # sd_bb
    [0.0, 0.0, 0.0],      # nonsd_bb
    [10.0, 30.0, 20.0],   # ev_bb_line
    [0.1, 0.3, 0.6],      # rake_line (cumulative)
    [1.0, 3.0, 6.0],      # rake_bb_line (cumulative)
)


def test_profit_rakeback_line_has_no_data_when_not_configured(tab, monkeypatch):
    import ui.overview_tab as mod
    monkeypatch.setattr(mod, "get_rakeback_pct", lambda: None)

    tab._render_cash(({"hands": 3, "profit": 2.0, "rake": 0.6}, _SAMPLE_GRAPH))

    xs, ys = tab.c_pr.getData()
    # pyqtgraph's setData([], []) reports back as (None, None), not ([], [])
    assert xs is None or len(xs) == 0


def test_profit_rakeback_line_matches_cumulative_profit_plus_scaled_rake(tab, monkeypatch):
    import ui.overview_tab as mod
    monkeypatch.setattr(mod, "get_rakeback_pct", lambda: 30)

    tab._render_cash(({"hands": 3, "profit": 2.0, "rake": 0.6}, _SAMPLE_GRAPH))

    xs, ys = tab.c_pr.getData()
    # total[i] + rake_line[i] * 0.30, at each of the 3 points
    expected = [1.0 + 0.1 * 0.3, 3.0 + 0.3 * 0.3, 2.0 + 0.6 * 0.3]
    assert list(xs) == [1, 2, 3]
    for actual, exp in zip(ys, expected):
        assert round(actual, 4) == round(exp, 4)
