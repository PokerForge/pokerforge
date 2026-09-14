"""ui/log_tournament_result_dialog.py's LogTournamentResultDialog — the
manual entry form for a tournament's finish position/field size/payout,
since no hand-history export contains any of these."""
import pytest

from ui.log_tournament_result_dialog import LogTournamentResultDialog


@pytest.fixture()
def qapp():
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_blank_dialog_returns_none_for_unset_positions(qapp):
    dlg = LogTournamentResultDialog("t1", buy_in=10.0, fee=1.0, currency="$")
    assert dlg.result_values() == (None, None, 0.0)


def test_entered_values_are_returned(qapp):
    dlg = LogTournamentResultDialog("t1", buy_in=10.0, fee=1.0, currency="$")
    dlg.finish_spin.setValue(3)
    dlg.field_spin.setValue(180)
    dlg.payout_spin.setValue(45.5)
    assert dlg.result_values() == (3, 180, 45.5)


def test_existing_result_prefills_the_form(qapp):
    dlg = LogTournamentResultDialog("t1", buy_in=10.0, fee=1.0, currency="$",
                                     existing=(2, 90, 25.0, "$"))
    assert dlg.result_values() == (2, 90, 25.0)


def test_no_buy_in_shows_a_dash_not_a_crash(qapp):
    dlg = LogTournamentResultDialog("t1", buy_in=None, fee=None, currency="$")
    assert dlg.result_values() == (None, None, 0.0)
