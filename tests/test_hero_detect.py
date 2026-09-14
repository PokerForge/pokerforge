"""ui/hero_detect.py's hero_hand_share() — the signal behind the first-run
"does this data actually look like yours?" sanity check — and
dominant_currency()'s fallback when there's nothing to detect from."""
from models.hand import Hand, Player
from ui.hero_detect import hero_hand_share, dominant_currency, is_anon_placeholder


def _hand(players):
    return Hand(hand_id="1", players=[Player(name=n) for n in players])


def test_hero_present_in_every_hand_is_full_share():
    hands = [_hand(["Hero", "V1"]), _hand(["Hero", "V2"])]
    assert hero_hand_share(hands, "Hero") == 1.0


def test_hero_present_in_none_of_the_hands_is_zero_share():
    hands = [_hand(["V1", "V2"]), _hand(["V3", "V4"])]
    assert hero_hand_share(hands, "Hero") == 0.0


def test_hero_present_in_some_hands_is_a_fraction():
    hands = [_hand(["Hero", "V1"]), _hand(["V2", "V3"]), _hand(["V4", "V5"]), _hand(["Hero", "V6"])]
    assert hero_hand_share(hands, "Hero") == 0.5


def test_empty_hands_list_is_zero_share_not_a_crash():
    assert hero_hand_share([], "Hero") == 0.0


def test_dominant_currency_picks_the_hero_own_most_common_currency():
    hands = [
        Hand(hand_id="1", players=[Player(name="Hero")], currency="$"),
        Hand(hand_id="2", players=[Player(name="Hero")], currency="$"),
        Hand(hand_id="3", players=[Player(name="Hero")], currency="€"),
    ]
    assert dominant_currency(hands, "Hero") == "$"


def test_dominant_currency_falls_back_to_dollar_with_no_hero_hands():
    # Nothing to detect from (empty list, or hero isn't seated in any of
    # them) — defaults to $ rather than guessing a specific region's
    # currency for a user we know nothing about yet.
    assert dominant_currency([], "Hero") == "$"
    hands = [Hand(hand_id="1", players=[Player(name="SomeoneElse")], currency="£")]
    assert dominant_currency(hands, "Hero") == "$"


def test_is_anon_placeholder_matches_ipoker_anonymous_names():
    assert is_anon_placeholder("Player 3")
    assert is_anon_placeholder("Player 27")


def test_is_anon_placeholder_does_not_match_real_names_even_hex_looking_ones():
    # GGPoker's anonymized opponents are excluded by hand.source at
    # import time (database/hand_stats_builder.py), NOT by name shape --
    # a shape-based filter would wrongly hide real, persistent usernames
    # on other sites that happen to look hex-like (confirmed against a
    # real PokerStars export: "3033453", "ed777221", "dd19761976").
    assert not is_anon_placeholder("Hero")
    assert not is_anon_placeholder("Stony87")
    assert not is_anon_placeholder("gunfluffy1595")
    assert not is_anon_placeholder("448c7ca6")
    assert not is_anon_placeholder("3033453")
    assert not is_anon_placeholder("ed777221")
