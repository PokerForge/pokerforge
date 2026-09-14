"""ui/app_window.py's _maybe_prompt_new_identity_alias — catches both
directions of a real incident this project hit: GGPoker always labels
the account owner's own seat literally "Hero" (never the real GGPoker
username), so whichever of {the tracked hero, GGPoker's "Hero"} arrives
second ends up as a separate, unmerged identity unless something tells
PokerForge they're the same person (see the function's own docstring).
This must catch it BEFORE normalize_hero_aliases runs on the same batch,
so saying yes here fixes the import in progress, not just future ones."""
import pytest


@pytest.fixture()
def qapp():
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


class _FakeMessageBox:
    simulate_yes = True

    class Icon:
        Information = 1

    class ButtonRole:
        YesRole = 1
        NoRole = 2

    def __init__(self, icon, title, text, buttons=0, *, parent=None):
        # `parent` is keyword-only here on purpose, matching the real
        # QMessageBox(icon, title, text, buttons=..., parent=...) overload
        # -- a caller that passes parent positionally (landing in the
        # `buttons` slot instead) would crash against the real PyQt6
        # class with a TypeError, but silently "work" against a mock
        # that accepts anything positionally. This caught exactly that
        # bug once already (see git history) — keep it strict.
        self.text = text
        self.buttons = []
        self._clicked = None

    def addButton(self, label, role):
        btn = (label, role)
        self.buttons.append(btn)
        return btn

    def exec(self):
        # buttons[0] is always "Yes, add it", buttons[1] "Not now"
        self._clicked = self.buttons[0] if _FakeMessageBox.simulate_yes else self.buttons[1]

    def clickedButton(self):
        return self._clicked


def _hands(source, owner, count=25):
    """`count` hands, each seating `owner` (present in every one, so
    hero_hand_share(hands, owner) == 1.0 -- comfortably over the
    function's 0.8 threshold and 20-hand minimum sample)."""
    from models.hand import Hand, Player
    return [Hand(hand_id=f"{source}-{i}", source=source, players=[Player(owner)])
            for i in range(count)]


@pytest.fixture(autouse=True)
def _reset_state(qapp, monkeypatch):
    import ui.app_window as mod
    monkeypatch.setattr(mod, "QMessageBox", _FakeMessageBox)
    monkeypatch.setattr(mod, "_prompted_identity_candidates", set())
    _FakeMessageBox.simulate_yes = True
    yield


def test_prompts_and_adds_the_alias_when_accepted(monkeypatch):
    import ui.app_window as mod
    added = []
    monkeypatch.setattr(mod, "add_hero_alias", lambda name: added.append(name))
    monkeypatch.setattr(mod, "get_hero_aliases", lambda: [])
    _FakeMessageBox.simulate_yes = True

    mod._maybe_prompt_new_identity_alias(_hands("ggpoker", "Hero"), "Akali8010")

    assert added == ["Hero"]


def test_declining_does_not_add_the_alias(monkeypatch):
    import ui.app_window as mod
    added = []
    monkeypatch.setattr(mod, "add_hero_alias", lambda name: added.append(name))
    monkeypatch.setattr(mod, "get_hero_aliases", lambda: [])
    _FakeMessageBox.simulate_yes = False

    mod._maybe_prompt_new_identity_alias(_hands("ggpoker", "Hero"), "Akali8010")

    assert added == []


def test_no_prompt_when_hero_alias_already_covers_it(monkeypatch):
    import ui.app_window as mod
    monkeypatch.setattr(mod, "get_hero_aliases", lambda: ["Hero"])
    calls = []
    monkeypatch.setattr(mod, "QMessageBox", lambda *a, **k: calls.append(1) or _FakeMessageBox(*a, **k))

    mod._maybe_prompt_new_identity_alias(_hands("ggpoker", "Hero"), "Akali8010")

    assert calls == []


def test_no_prompt_when_hero_is_already_literally_hero(monkeypatch):
    import ui.app_window as mod
    monkeypatch.setattr(mod, "get_hero_aliases", lambda: [])
    calls = []
    monkeypatch.setattr(mod, "QMessageBox", lambda *a, **k: calls.append(1) or _FakeMessageBox(*a, **k))

    mod._maybe_prompt_new_identity_alias(_hands("ggpoker", "Hero"), "Hero")

    assert calls == []


def test_no_prompt_when_batch_is_too_small(monkeypatch):
    """Below the 20-hand minimum sample — not enough evidence either way."""
    import ui.app_window as mod
    monkeypatch.setattr(mod, "get_hero_aliases", lambda: [])
    calls = []
    monkeypatch.setattr(mod, "QMessageBox", lambda *a, **k: calls.append(1) or _FakeMessageBox(*a, **k))

    mod._maybe_prompt_new_identity_alias(_hands("ggpoker", "Hero", count=5), "Akali8010")

    assert calls == []


def test_reverse_direction_a_real_username_site_after_ggpoker_established_hero(monkeypatch):
    """The scenario the fix was missing before this generalization: GG
    hands arrive first and correctly establish "Hero" as the tracked
    identity, then a real-username site (e.g. PokerStars) arrives
    afterward — its own real username must now be the one offered as
    the alias, not "Hero" again."""
    import ui.app_window as mod
    added = []
    monkeypatch.setattr(mod, "add_hero_alias", lambda name: added.append(name))
    monkeypatch.setattr(mod, "get_hero_aliases", lambda: [])

    mod._maybe_prompt_new_identity_alias(_hands("pokerstars", "Ferry2009"), "Hero")

    assert added == ["Ferry2009"]


def test_mixed_batch_checks_per_source_not_the_whole_pool(monkeypatch):
    """A first-run setup pointed at two sites' folders at once produces
    ONE combined batch — neither site's own ~100%-of-its-own-hands hero
    label would cross the share threshold measured against the OTHER
    site's hands mixed in (222,843 GG hands is only ~47% of a combined
    ~475k-hand batch, even though "Hero" is in 100% of the GG portion).
    Grouping by source first must restore that ~100% signal."""
    import ui.app_window as mod
    added = []
    monkeypatch.setattr(mod, "add_hero_alias", lambda name: added.append(name))
    monkeypatch.setattr(mod, "get_hero_aliases", lambda: [])

    # PokerStars dominates the combined batch by hand count, and is
    # chosen as hero by HeroSetupDialog upstream (not exercised here) —
    # GGPoker's "Hero" is still the minority in the combined pool.
    combined = _hands("pokerstars", "Ferry2009", count=60) + _hands("ggpoker", "Hero", count=25)

    mod._maybe_prompt_new_identity_alias(combined, "Ferry2009")

    assert added == ["Hero"]


def test_only_prompts_once_per_candidate_not_per_call(monkeypatch):
    import ui.app_window as mod
    monkeypatch.setattr(mod, "get_hero_aliases", lambda: [])
    added = []
    monkeypatch.setattr(mod, "add_hero_alias", lambda name: added.append(name))
    _FakeMessageBox.simulate_yes = False  # decline the first time

    mod._maybe_prompt_new_identity_alias(_hands("ggpoker", "Hero"), "Akali8010")
    calls = []
    monkeypatch.setattr(mod, "QMessageBox", lambda *a, **k: calls.append(1) or _FakeMessageBox(*a, **k))
    mod._maybe_prompt_new_identity_alias(_hands("ggpoker", "Hero"), "Akali8010")

    assert calls == []  # the live-watcher-firing-repeatedly case: no nagging


def test_a_different_new_candidate_still_gets_its_own_prompt(monkeypatch):
    """Declining/accepting one candidate must not silently suppress a
    DIFFERENT candidate discovered later in the same session."""
    import ui.app_window as mod
    monkeypatch.setattr(mod, "get_hero_aliases", lambda: [])
    added = []
    monkeypatch.setattr(mod, "add_hero_alias", lambda name: added.append(name))

    mod._maybe_prompt_new_identity_alias(_hands("ggpoker", "Hero"), "Akali8010")
    mod._maybe_prompt_new_identity_alias(_hands("pokerstars", "Ferry2009"), "Akali8010")

    assert added == ["Hero", "Ferry2009"]
