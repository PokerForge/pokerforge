"""ui/app_tour.py's TourOverlay — a spotlight-style guided tour driven by
a real AppWindow (cheap to construct; run_async is monkeypatched
synchronous so nothing races a background QThread). Covers navigation
bounds, target resolution (including the no-target "plain message"
steps), before_show tab-switching, and Help menu / first-run wiring."""
import pytest

from ui.app_tour import TourStep, TourOverlay, TOUR_STEPS


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


@pytest.fixture()
def win(qapp, db):
    from ui.app_window import AppWindow
    w = AppWindow("Hero", db, "$")
    w.winId()  # forces a native handle so mapToGlobal() resolves without ever showing the window
    yield w
    w.close()


def test_tour_steps_all_have_title_and_text():
    for step in TOUR_STEPS:
        assert step.title
        assert step.text


def test_start_shows_the_first_step(win):
    tour = TourOverlay(win)
    tour.start()
    assert tour._index == 0
    assert tour.callout.title_lbl.text() == TOUR_STEPS[0].title
    assert tour.isHidden() is False


def test_next_advances_and_back_is_enabled_after_the_first_step(win):
    tour = TourOverlay(win)
    tour.start()
    tour._next()
    assert tour._index == 1
    assert tour.callout.back_btn.isEnabled() is True


def test_back_from_step_zero_does_nothing(win):
    tour = TourOverlay(win)
    tour.start()
    tour._back()
    assert tour._index == 0


def test_next_on_the_last_step_finishes_instead_of_advancing(win):
    tour = TourOverlay(win)
    tour.start()
    tour._index = len(TOUR_STEPS) - 1
    tour._show_step()
    finished = []
    tour.on_finished = lambda: finished.append(True)
    tour._next()
    assert finished == [True]
    assert tour.isHidden() is True


def test_skip_calls_finish_and_hides(win):
    tour = TourOverlay(win)
    tour.start()
    finished = []
    tour.on_finished = lambda: finished.append(True)
    tour.callout.skip_btn.click()
    assert finished == [True]
    assert tour.isHidden() is True


def test_no_target_step_produces_an_empty_target_rect(win):
    step = TourStep(title="Intro", text="Hello")
    tour = TourOverlay(win)
    tour.start(steps=[step])
    assert tour._target_rect.isNull()


def test_real_target_step_resolves_a_nonempty_rect(win):
    step = TourStep(title="Refresh", text="Checks for new hands", target=lambda w: w.refresh_btn)
    tour = TourOverlay(win)
    tour.start(steps=[step])
    assert not tour._target_rect.isNull()
    assert tour._target_rect.width() > 0
    assert tour._target_rect.height() > 0


def test_target_rect_matches_mapping_through_the_shared_centralwidget_ancestor(win):
    # Locks in mapTo(centralWidget(), ...) rather than mapToGlobal/
    # mapFromGlobal — the latter depends on the top-level window's real
    # on-screen position, which is undefined for a window that's never
    # been shown (confirmed by hand: it produced a badly-offset rect
    # here, even though widget geometry itself was internally
    # consistent). This assertion holds regardless of whether Qt has
    # activated real layout geometry yet, since it's checking the
    # TRANSFORM is correct, not that the underlying geometry is final.
    from PyQt6.QtCore import QPoint, QRect
    step = TourStep(title="Refresh", text="...", target=lambda w: w.refresh_btn)
    tour = TourOverlay(win)
    tour.start(steps=[step])

    expected_top_left = win.refresh_btn.mapTo(win.centralWidget(), QPoint(0, 0))
    expected = QRect(expected_top_left, win.refresh_btn.size())
    assert tour._target_rect == expected


def test_before_show_switches_tabs(win):
    win.tabs.setCurrentWidget(win.tab_overview)
    step = TourStep(
        title="Sessions", text="...", target=lambda w: w.tab_sessions,
        before_show=lambda w: w.tabs.setCurrentWidget(w.tab_sessions))
    tour = TourOverlay(win)
    tour.start(steps=[step])
    assert win.tabs.currentWidget() is win.tab_sessions


def test_leaks_step_switches_to_the_leaks_sub_tab(win):
    from ui.app_tour import _show_stats_subtab
    step = TourStep(title="Leaks", text="...", target=lambda w: w.tab_stats,
                     before_show=_show_stats_subtab(1))
    tour = TourOverlay(win)
    tour.start(steps=[step])
    assert win.tabs.currentWidget() is win.tab_stats
    assert win.tab_stats.sub_tabs.currentIndex() == 1


def test_take_the_tour_menu_action_starts_a_tour(win):
    win._on_take_tour_clicked()
    assert win._tour is not None
    assert win._tour.isHidden() is False
