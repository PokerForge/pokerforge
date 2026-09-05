"""ui/hero_detect.py's hero_hand_share() — the signal behind the first-run
"does this data actually look like yours?" sanity check."""
from models.hand import Hand, Player
from ui.hero_detect import hero_hand_share


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
