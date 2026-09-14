"""ui/population_summary.py's build_population_summary — same GGPoker
exclusion as database/hand_stats_builder.py (see its test file's
docstring for the full reasoning): scoped by hand.source, not by name
shape, since real usernames on other sites can coincidentally look
exactly like GGPoker's random per-hand hex labels."""
from models.hand import Hand, Player, Action
from ui.population_summary import build_population_summary


def _hand(players, source=None, hand_id="1"):
    return Hand(
        hand_id=hand_id, source=source,
        players=[Player(name=n) for n in players],
        actions=[Action("PREFLOP", players[0], "Fold", None)],
    )


def test_ggpoker_hand_contributes_no_villains():
    hands = [_hand(["Hero", "aaa11111", "bbb22222"], source="ggpoker")]
    rows = build_population_summary(hands, hero="Hero")
    assert rows == {}


def test_non_ggpoker_hand_contributes_real_villains_even_hex_looking_ones():
    hands = [_hand(["Hero", "Villain1", "3033453"], source="pokerstars")]
    rows = build_population_summary(hands, hero="Hero")
    assert set(rows) == {"Villain1", "3033453"}


def test_ipoker_player_n_placeholder_is_still_excluded():
    hands = [_hand(["Hero", "Player 3"], source="ipoker")]
    rows = build_population_summary(hands, hero="Hero")
    assert rows == {}
