"""ui/main_window.py's VillainDetail — "Similar Players" card wiring.
Calls _render_villain directly with hand-built minimal data rather than
going through show_villain's real async DB queries — the query layer
itself is covered by tests/test_queries.py and the similarity ranking by
tests/test_villain_similarity.py; this just checks the two are wired
together correctly."""
import pytest

from ui.population_summary import PopulationRow


@pytest.fixture()
def qapp():
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _row(name, vpip, pfr, hands=200):
    row = PopulationRow(name=name, hands=hands)
    row.vpip_pfr_opp = hands
    row.vpip = round(vpip / 100 * hands)
    row.pfr = round(pfr / 100 * hands)
    return row


def _empty_result():
    values, hand_count, vs_open, opp_counts = {}, 0, {}, {}
    graph = ([], [], [], [], [], [], [], [], [], [], [])
    return (values, hand_count, vs_open, opp_counts), (graph, 0.0, 0.0)


@pytest.fixture()
def detail(qapp, tmp_path):
    from database.repository import PokerDatabase
    from ui.main_window import VillainDetail
    db = PokerDatabase(tmp_path / "test.db")
    d = VillainDetail("Hero", db, "£")
    yield d
    db.close()


def test_similar_players_card_appears_when_a_similar_villain_exists(detail):
    from PyQt6.QtWidgets import QLabel
    detail._all_rows = {
        "Target": _row("Target", vpip=25, pfr=20),
        "Twin": _row("Twin", vpip=26, pfr=21),
    }
    detail._render_villain("Target", _empty_result())

    all_text = " ".join(l.text() for l in detail.below.parentWidget().findChildren(QLabel))
    assert "SIMILAR PLAYERS" in all_text
    assert "Twin" in all_text


def test_no_similar_players_card_when_none_qualify(detail):
    from PyQt6.QtWidgets import QLabel
    detail._all_rows = {"Target": _row("Target", vpip=25, pfr=20)}  # only the target itself
    detail._render_villain("Target", _empty_result())

    all_text = " ".join(l.text() for l in detail.below.parentWidget().findChildren(QLabel))
    assert "SIMILAR PLAYERS" not in all_text


def test_no_similar_players_card_for_a_group_view(detail):
    from PyQt6.QtWidgets import QLabel
    detail._all_rows = {
        "Target": _row("Target", vpip=25, pfr=20),
        "Twin": _row("Twin", vpip=26, pfr=21),
    }
    detail._render_villain("Some Group", _empty_result(), is_group=True)

    all_text = " ".join(l.text() for l in detail.below.parentWidget().findChildren(QLabel))
    assert "SIMILAR PLAYERS" not in all_text


def test_clicking_a_similar_player_calls_show_villain_with_current_filters(detail, monkeypatch):
    calls = []
    monkeypatch.setattr(detail, "show_villain", lambda *a, **k: calls.append((a, k)))
    detail._current_d_from, detail._current_d_to, detail._current_stake = "2026-01-01", "2026-06-01", "£0.05/£0.10"
    detail._pop_averages = {"vpip": 24.0}
    detail._all_rows = {"Twin": _row("Twin", vpip=25, pfr=20)}

    detail._on_similar_player_clicked("Twin")

    assert calls == [(("Twin", "2026-01-01", "2026-06-01", "£0.05/£0.10", {"vpip": 24.0},
                        {"Twin": detail._all_rows["Twin"]}), {})]
