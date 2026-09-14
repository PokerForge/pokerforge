"""ui/game_type_toggle.py's GameTypeToggle — the global $/T switch that
replaced the standalone Tournaments tab."""
import pytest

from ui.game_type_toggle import GameTypeToggle


@pytest.fixture()
def qapp():
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_defaults_to_cash(qapp):
    toggle = GameTypeToggle()
    assert toggle.value() == 'cash'
    assert toggle._buttons['cash'].isChecked()
    assert not toggle._buttons['tournament'].isChecked()


def test_clicking_tournament_emits_changed_and_updates_value(qapp):
    toggle = GameTypeToggle()
    emitted = []
    toggle.changed.connect(emitted.append)

    toggle._buttons['tournament'].click()

    assert toggle.value() == 'tournament'
    assert emitted == ['tournament']


def test_clicking_the_already_active_button_does_not_emit_again(qapp):
    toggle = GameTypeToggle()
    emitted = []
    toggle.changed.connect(emitted.append)

    toggle._buttons['cash'].click()

    assert emitted == []


def test_set_value_updates_the_checked_button_without_emitting(qapp):
    toggle = GameTypeToggle()
    emitted = []
    toggle.changed.connect(emitted.append)

    toggle.set_value('tournament')

    assert toggle.value() == 'tournament'
    assert toggle._buttons['tournament'].isChecked()
    assert emitted == []
