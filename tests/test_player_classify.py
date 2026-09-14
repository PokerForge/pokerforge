"""ui/player_classify.py's classify_player/generate_leaks/generate_hero_leaks
— pure functions of stat-value dicts, no DB or Qt needed."""
from ui.player_classify import classify_player, generate_leaks, generate_hero_leaks, MIN_LEAK_SAMPLE


def test_classify_player_returns_unknown_for_no_data():
    label, _color = classify_player(None, None, None, None)
    assert label == "Unknown"


def test_classify_player_labels_a_loose_passive_calling_station():
    label, _color = classify_player(vpip=45, pfr=15, threebet=3, wtsd=30)
    assert "Calling Station" in label


def test_generate_leaks_with_no_values_returns_empty():
    assert generate_leaks({}) == []


def test_generate_leaks_flags_extremely_loose_vpip_with_a_leak_id():
    leaks = generate_leaks({"vpip": 45.0})
    assert len(leaks) == 1
    icon, title, advice, leak_id = leaks[0]
    assert title == "Extremely loose preflop"
    assert leak_id == "vpip_loose"


def test_generate_leaks_falls_back_to_no_leaks_message_when_nothing_flags():
    leaks = generate_leaks({"vpip": 24.0, "three_bet": 8.0, "fold_3bet_as_raiser": 55.0})
    assert len(leaks) == 1
    icon, title, advice, leak_id = leaks[0]
    assert title == "No major leaks detected"
    assert leak_id is None


def test_generate_leaks_without_opp_counts_does_not_gate_by_sample():
    # No opp_counts passed at all -> the one caller that doesn't have it
    # computed still gets leaks, matching the old ungated behavior.
    leaks = generate_leaks({"vpip": 45.0})
    assert any(l[3] == "vpip_loose" for l in leaks)


def test_generate_leaks_skips_a_stat_below_the_minimum_sample():
    leaks = generate_leaks({"vpip": 45.0}, opp_counts={"vpip": MIN_LEAK_SAMPLE - 1})
    assert leaks == [("\U0001f7e2", "No major leaks detected",
                       "This appears to be a solid player on the current sample. Play closer to GTO vs them.",
                       None)]


def test_generate_leaks_includes_a_stat_exactly_at_the_minimum_sample():
    leaks = generate_leaks({"vpip": 45.0}, opp_counts={"vpip": MIN_LEAK_SAMPLE})
    assert any(l[3] == "vpip_loose" for l in leaks)


def test_generate_leaks_covers_every_branch_with_a_valid_leak_id():
    from database.queries import LEAK_HAND_CONDITIONS
    cases = [
        {"three_bet": 2.0}, {"three_bet": 5.0}, {"fold_3bet_as_raiser": 80.0}, {"fold_3bet_as_raiser": 65.0},
        {"fold_3bet_as_raiser": 20.0}, {"four_bet": 20.0}, {"fold_4bet": 70.0}, {"flop_fold_cbet": 70.0},
        {"flop_fold_cbet": 55.0}, {"flop_fold_cbet": 20.0}, {"wtsd": 40.0}, {"wtsd": 32.0},
        {"wtsd": 15.0}, {"wsd": 30.0}, {"vpip": 45.0}, {"vpip": 35.0},
    ]
    for values in cases:
        leaks = generate_leaks(values)
        assert len(leaks) == 1, values
        leak_id = leaks[0][3]
        assert leak_id in LEAK_HAND_CONDITIONS, (values, leak_id)


def test_generate_hero_leaks_still_works_unchanged():
    leaks = generate_hero_leaks({"vpip": 45.0, "pfr": 10.0}, opp_counts={"vpip": 50})
    assert any(l[3] == "vpip_loose" for l in leaks)
