"""ui/stats_tab.py's "Your Study Queue" card — built on a real StatsTab
instance, same approach as test_stats_tab_cross_leaks.py. The card's
"Study N Hands" button opens the replayer loaded with that leak's own
recent hands, reusing hands_for_stat_query + load_hands_bulk + the
existing multi-hand HandReplayDialog."""
import pytest

from core.leak_finder import LeakEntry


@pytest.fixture()
def qapp():
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def stats_tab(qapp, tmp_path):
    from database.repository import PokerDatabase
    from ui.stats_tab import StatsTab
    db = PokerDatabase(tmp_path / "test.db")
    tab = StatsTab("Hero", db, "£")
    tab._current_d_from = "2026-06-01"
    tab._current_d_to = "2026-06-30"
    tab._current_stake = None
    yield tab
    db.close()


def _leak(stat_id="vpip", position="BB", stat_label="VPIP", sample=120, score=1000.0):
    return LeakEntry(position=position, stat_id=stat_id, stat_label=stat_label,
                      hero_rate=40.0, population_rate=25.0, sample=sample, score=score)


def test_card_shows_a_priority_row_per_queue_entry(stats_tab):
    from PyQt6.QtWidgets import QLabel
    queue = [_leak(stat_id="vpip", stat_label="VPIP"), _leak(stat_id="three_bet", stat_label="3-Bet")]
    card = stats_tab._build_study_queue_card(queue)
    all_text = " ".join(l.text() for l in card.findChildren(QLabel))
    assert "Priority 1" in all_text and "Priority 2" in all_text
    assert "VPIP — BB" in all_text
    assert "3-Bet — BB" in all_text


def test_study_button_caption_caps_at_hands_per_session(stats_tab):
    from ui.stats_tab import HANDS_PER_STUDY_SESSION
    from PyQt6.QtWidgets import QPushButton
    queue = [_leak(sample=HANDS_PER_STUDY_SESSION + 50)]
    card = stats_tab._build_study_queue_card(queue)
    buttons = [b.text() for b in card.findChildren(QPushButton)]
    assert f"Study {HANDS_PER_STUDY_SESSION} Hands" in buttons


def test_study_button_caption_uses_actual_sample_when_smaller(stats_tab):
    from ui.stats_tab import HANDS_PER_STUDY_SESSION
    from PyQt6.QtWidgets import QPushButton
    queue = [_leak(sample=5)]
    card = stats_tab._build_study_queue_card(queue)
    buttons = [b.text() for b in card.findChildren(QPushButton)]
    assert "Study 5 Hands" in buttons


def test_clicking_study_opens_the_replayer_with_recent_hands_capped(stats_tab, monkeypatch):
    import ui.stats_tab as mod
    from ui.stats_tab import HANDS_PER_STUDY_SESSION

    rows = [(f"h{i}", f"2026-06-{i+1:02d}T00:00:00", "£0.05/£0.10", 1.0, None)
            for i in range(HANDS_PER_STUDY_SESSION + 10)]
    monkeypatch.setattr(mod, "hands_for_stat_query", lambda *a, **k: rows)
    monkeypatch.setattr(mod, "load_hands_bulk", lambda db, ids: {hid: f"HAND-{hid}" for hid in ids})

    opened = {}

    class _FakeDialog:
        def __init__(self, hand, subject_name, parent=None, hand_list=None, start_index=0):
            opened['hand'] = hand
            opened['hand_list'] = hand_list
            opened['start_index'] = start_index

        def exec(self):
            opened['exec_called'] = True

    monkeypatch.setattr(mod, "HandReplayDialog", _FakeDialog)

    stats_tab._on_study_leak_clicked(_leak(stat_id="vpip", position="BB"))

    assert opened['exec_called'] is True
    assert len(opened['hand_list']) == HANDS_PER_STUDY_SESSION
    # Most recent hands first (highest day number, since rows are 1..N+10).
    assert opened['hand_list'][0] == f"HAND-h{HANDS_PER_STUDY_SESSION + 9}"


def test_clicking_study_passes_stat_id_and_position_to_the_query(stats_tab, monkeypatch):
    import ui.stats_tab as mod
    calls = []
    monkeypatch.setattr(mod, "hands_for_stat_query",
                         lambda db, hero, stat_id, d_from, d_to, stake, position=None:
                             calls.append((stat_id, position)) or [])
    monkeypatch.setattr(mod, "load_hands_bulk", lambda db, ids: {})

    stats_tab._on_study_leak_clicked(_leak(stat_id="fold_3bet", position="CO"))

    assert calls == [("fold_3bet", "CO")]


def test_clicking_study_with_no_resolvable_hands_does_nothing(stats_tab, monkeypatch):
    import ui.stats_tab as mod
    calls = []
    monkeypatch.setattr(mod, "hands_for_stat_query", lambda *a, **k: [("h1", "2026-06-01T00:00:00", None, 1.0, None)])
    monkeypatch.setattr(mod, "load_hands_bulk", lambda db, ids: {})
    monkeypatch.setattr(mod, "HandReplayDialog", lambda *a, **k: calls.append(True))

    stats_tab._on_study_leak_clicked(_leak())

    assert calls == []
