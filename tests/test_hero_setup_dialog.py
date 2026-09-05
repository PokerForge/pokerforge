"""ui/hero_setup_dialog.py's low-hero-share warning — must appear when the
detected identity looks implausible and must stay silent otherwise,
without ever blocking the user from proceeding either way (it's a
warning, not a hard stop)."""
import pytest


@pytest.fixture()
def qapp():
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _find_warning_label(dlg):
    from PyQt6.QtWidgets import QLabel
    return [w for w in dlg.findChildren(QLabel) if "doesn't look like" in w.text()]


def test_no_warning_when_share_is_high(qapp):
    from ui.hero_setup_dialog import HeroSetupDialog
    dlg = HeroSetupDialog("RealHero", "£", hero_share=0.98)
    assert _find_warning_label(dlg) == []


def test_warning_shown_when_share_is_low(qapp):
    from ui.hero_setup_dialog import HeroSetupDialog
    dlg = HeroSetupDialog("MaybeNotHero", "£", hero_share=0.1)
    labels = _find_warning_label(dlg)
    assert len(labels) == 1
    assert "MaybeNotHero" in labels[0].text()
    assert "10%" in labels[0].text()


def test_no_warning_when_share_not_provided(qapp):
    from ui.hero_setup_dialog import HeroSetupDialog
    dlg = HeroSetupDialog("SomeHero", "£")
    assert _find_warning_label(dlg) == []


def test_warning_does_not_block_confirming(qapp):
    from ui.hero_setup_dialog import HeroSetupDialog
    dlg = HeroSetupDialog("MaybeNotHero", "£", hero_share=0.1)
    dlg.accept()
    assert dlg.result() == 1
    assert dlg.selected_hero() == "MaybeNotHero"
