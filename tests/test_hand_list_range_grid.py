"""ui/hand_list_dialog.py's position filter + range-grid toggle — added
alongside the existing PT4-style hand list so a villain's revealed hole
cards can be viewed as a heatmap, filtered to one position at a time
(mixing positions into one "range" wouldn't mean anything). Uses
monkeypatched load_hands_bulk rather than a real database/import
pipeline — HandListPanel's own DB access is fully isolated to that one
call, so this keeps the test fast and focused on the filter/toggle logic
itself."""
import pytest

from models.hand import Hand, Player, Action


@pytest.fixture()
def qapp():
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _hand(hand_id, button_seat, hero_seat, hero_cards):
    other_seats = [s for s in (1, 2, 3) if s != hero_seat]
    players = [Player("Hero", hero_seat, 100.0, hero_cards)]
    for i, seat in enumerate(other_seats):
        players.append(Player(f"Villain{i}", seat, 100.0))
    return Hand(
        hand_id=hand_id, players=players, button_seat=button_seat,
        actions=[Action("PREFLOP", "Hero", "Fold", None)],
        winnings={}, board=[], big_blind=1.0,
    )


@pytest.fixture()
def three_hands():
    # 3-handed: seats [1,2,3], button_seat=1 -> seat1=BTN, seat2=SB, seat3=BB.
    return {
        "h1": _hand("h1", button_seat=1, hero_seat=1, hero_cards=["A♠", "K♠"]),   # Hero at BTN
        "h2": _hand("h2", button_seat=1, hero_seat=1, hero_cards=["Q♦", "Q♣"]),   # Hero at BTN
        "h3": _hand("h3", button_seat=1, hero_seat=2, hero_cards=["7♣", "2♦"]),   # Hero at SB
    }


@pytest.fixture()
def panel(qapp, monkeypatch, three_hands):
    import ui.hand_list_dialog as mod
    monkeypatch.setattr(mod, "load_hands_bulk", lambda db, ids: three_hands)
    rows = [
        ("h1", "2026-01-01T00:00:00", "£0.05/£0.10", 5.0, None),
        ("h2", "2026-01-01T00:05:00", "£0.05/£0.10", -2.0, None),
        ("h3", "2026-01-01T00:10:00", "£0.05/£0.10", 1.0, None),
    ]
    return mod.HandListPanel(rows, db=None, subject_name="Hero", stat_label="3-Bet")


def test_position_filter_has_all_positions_plus_distinct_positions_found(panel):
    items = [panel.position_filter.itemText(i) for i in range(panel.position_filter.count())]
    assert items[0] == "All Positions"
    assert set(items[1:]) == {"BTN", "SB"}


def test_range_button_hidden_until_a_specific_position_is_selected(panel):
    assert panel.range_btn.isHidden() is True
    panel.position_filter.setCurrentText("BTN")
    assert panel.range_btn.isHidden() is False
    panel.position_filter.setCurrentText("All Positions")
    assert panel.range_btn.isHidden() is True


def test_selecting_a_position_hides_non_matching_rows(panel):
    panel.position_filter.setCurrentText("BTN")
    hidden = [panel.table.isRowHidden(r) for r in range(panel.table.rowCount())]
    # Rows are sorted by played_at DESCENDING: row0=h3 (SB), row1=h2 (BTN),
    # row2=h1 (BTN) -> only row 0 (h3) should be hidden.
    assert hidden == [True, False, False]


def test_selecting_all_positions_shows_every_row_again(panel):
    panel.position_filter.setCurrentText("BTN")
    panel.position_filter.setCurrentText("All Positions")
    hidden = [panel.table.isRowHidden(r) for r in range(panel.table.rowCount())]
    assert hidden == [False, False, False]


def test_range_toggle_opens_a_popup_built_from_visible_rows_only(panel):
    from ui.range_grid import RangeGridWidget
    panel.position_filter.setCurrentText("BTN")
    panel._on_range_toggle_clicked()
    assert panel._range_popup is not None

    # Both BTN hands have known hole cards (h1: AKs, h2: QQ) -> both show
    # up in the grid, and the SB-only hand (h3: 72o) must NOT appear.
    grid_widget = panel._range_popup.findChild(RangeGridWidget)
    assert grid_widget is not None
    assert grid_widget.cells["AKs"].toolTip() == "AKs — seen 1x"
    assert grid_widget.cells["QQ"].toolTip() == "QQ — seen 1x"
    assert grid_widget.cells["72o"].toolTip() == "72o"  # not seen in this filtered view
    panel._close_range_popup()


def test_range_toggle_click_again_closes_the_popup(panel):
    panel.position_filter.setCurrentText("BTN")
    panel._on_range_toggle_clicked()
    assert panel._range_popup is not None
    panel._on_range_toggle_clicked()
    assert panel._range_popup is None


def test_switching_position_filter_closes_an_open_popup(panel):
    panel.position_filter.setCurrentText("BTN")
    panel._on_range_toggle_clicked()
    assert panel._range_popup is not None
    panel.position_filter.setCurrentText("SB")
    assert panel._range_popup is None
