"""ui/app_window.py's Site filter — added alongside the existing Period/
Stakes filter bar, with the same reach: selecting a site narrows every
tab (Overview/Sessions/Stats/Population) down to that source, and
narrows the Stakes dropdown to just that site's own stakes."""
import pytest


@pytest.fixture()
def qapp():
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _synchronous_run_async(monkeypatch):
    import ui.async_worker as worker_mod

    def _sync_run_async(self, fn, on_done, on_error=None, key="default"):
        try:
            result = fn()
        except Exception as exc:
            if on_error:
                on_error(str(exc))
            return
        on_done(result)

    monkeypatch.setattr(worker_mod.AsyncRunner, "run_async", _sync_run_async)


@pytest.fixture()
def db(tmp_path):
    from database.repository import PokerDatabase
    database = PokerDatabase(tmp_path / "test.db")
    yield database
    database.close()


def _hand(hand_id, source, played_at):
    from models.hand import Hand, Player, Action
    return Hand(
        hand_id=hand_id, source=source, played_at=played_at,
        currency="$", small_blind=0.05, big_blind=0.10,
        players=[Player("Hero", 1, 2.0), Player("Villain1", 2, 2.0)],
        actions=[Action("PREFLOP", "Hero", "Post SB", 0.05),
                 Action("PREFLOP", "Villain1", "Post BB", 0.10),
                 Action("PREFLOP", "Hero", "Fold", None)],
    )


@pytest.fixture()
def win(qapp, db):
    from datetime import datetime
    from ui.app_window import AppWindow
    # Default period on construction is "This Month" — use "now" rather
    # than a fixed date so these hands always fall inside it.
    now = datetime.now()
    db.import_hands([
        _hand("ip1", "ipoker", now),
        _hand("gg1", "ggpoker", now),
    ], ev_iterations=1)
    w = AppWindow("Hero", db, "$")
    w.winId()
    yield w
    w.close()


def test_site_dropdown_is_populated_with_friendly_labels(win):
    items = [win.site_cb.itemText(i) for i in range(win.site_cb.count())]
    assert items == ["All Sites", "GGPoker", "iPoker"]


def test_current_site_is_none_for_all_sites(win):
    win.site_cb.setCurrentText("All Sites")
    assert win._current_site() is None


def test_current_site_maps_the_friendly_label_back_to_the_raw_source(win):
    win.site_cb.setCurrentText("GGPoker")
    assert win._current_site() == "ggpoker"


def test_selecting_a_site_narrows_the_stakes_dropdown(win):
    win.stakes_cb.blockSignals(True)  # isolate: only exercise the site->stakes chain
    win.site_cb.setCurrentText("GGPoker")
    win.stakes_cb.blockSignals(False)
    win._on_site_changed()

    stakes = [win.stakes_cb.itemText(i) for i in range(win.stakes_cb.count())]
    assert stakes == ["All Stakes", "$0.05/$0.10"]


def test_apply_filters_passes_the_selected_site_to_every_tab(win, monkeypatch):
    calls = {}
    monkeypatch.setattr(win.tab_overview, "refresh", lambda *a: calls.__setitem__("overview", a))
    monkeypatch.setattr(win.tab_sessions, "refresh", lambda *a: calls.__setitem__("sessions", a))
    monkeypatch.setattr(win.tab_stats, "refresh", lambda *a: calls.__setitem__("stats", a))
    monkeypatch.setattr(win.tab_population, "refresh", lambda *a: calls.__setitem__("population", a))

    win.site_cb.setCurrentText("GGPoker")
    win._apply_filters()

    # Site is now second-to-last — the global $/T toggle (see
    # ui/game_type_toggle.py) added a trailing game_type argument after it.
    assert calls["overview"][-2] == "ggpoker"
    assert calls["sessions"][-2] == "ggpoker"
    assert calls["stats"][-2] == "ggpoker"
    assert calls["population"][-2] == "ggpoker"
    assert calls["overview"][-1] == "cash"


def test_apply_filters_passes_none_for_all_sites(win, monkeypatch):
    calls = {}
    monkeypatch.setattr(win.tab_population, "refresh", lambda *a: calls.__setitem__("population", a))

    win.site_cb.setCurrentText("All Sites")
    win._apply_filters()

    assert calls["population"][-2] is None


def test_game_type_toggle_defaults_to_cash(win):
    assert win._current_game_type() == 'cash'


def test_switching_to_tournament_passes_it_to_every_tab(win, monkeypatch):
    calls = {}
    monkeypatch.setattr(win.tab_overview, "refresh", lambda *a: calls.__setitem__("overview", a))
    monkeypatch.setattr(win.tab_sessions, "refresh", lambda *a: calls.__setitem__("sessions", a))
    monkeypatch.setattr(win.tab_stats, "refresh", lambda *a: calls.__setitem__("stats", a))
    monkeypatch.setattr(win.tab_population, "refresh", lambda *a: calls.__setitem__("population", a))

    win.game_type_toggle.set_value('tournament')
    win._apply_filters()

    assert calls["overview"][-1] == "tournament"
    assert calls["sessions"][-1] == "tournament"
    assert calls["stats"][-1] == "tournament"
    assert calls["population"][-1] == "tournament"


def test_clicking_the_toggle_reloads_stakes_for_the_new_game_type(win, monkeypatch):
    reloaded = []
    monkeypatch.setattr(win, "_reload_stakes", lambda: reloaded.append(True))

    win.game_type_toggle._buttons['tournament'].click()

    assert reloaded == [True]


@pytest.fixture()
def win_with_tournament(qapp, db):
    from datetime import datetime
    from ui.app_window import AppWindow
    from models.hand import Hand, Player, Action
    now = datetime.now()
    db.import_hands([
        _hand("ip1", "ipoker", now),
        _hand("gg1", "ggpoker", now),
        Hand(
            hand_id="t1a", source="pokerstars", played_at=now, big_blind=200.0,
            session_type="tournament", tournament_id="t1", buy_in=10.0, fee=1.0,
            players=[Player("Hero", 1, 10000.0), Player("Villain1", 2, 10000.0)],
            actions=[Action("PREFLOP", "Hero", "Post SB", 100.0),
                     Action("PREFLOP", "Villain1", "Post BB", 200.0),
                     Action("PREFLOP", "Hero", "Fold", None)],
        ),
    ], ev_iterations=1)
    w = AppWindow("Hero", db, "$")
    w.winId()
    yield w
    w.close()


def test_header_hands_label_shows_only_cash_hands_in_cash_mode(win_with_tournament):
    # 2 cash hands imported, 1 tournament hand — the header must not fold
    # the tournament hand into the count shown while in Cash mode.
    assert "2 hands loaded" in win_with_tournament.header_hands_lbl.text()


def test_header_hands_label_shows_only_tournament_hands_in_tournament_mode(win_with_tournament):
    win_with_tournament.game_type_toggle._buttons['tournament'].click()
    assert "1 hands loaded" in win_with_tournament.header_hands_lbl.text()
