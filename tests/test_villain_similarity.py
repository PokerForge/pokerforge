"""core/villain_similarity.py — a weighted-distance ranking over the
Population tab's own PopulationRow objects, so no database needed here."""
from ui.population_summary import PopulationRow
from core.villain_similarity import find_similar_villains, MIN_HANDS_FOR_SIMILARITY


def _row(name, vpip, pfr, three_bet=8.0, fold_3bet=55.0, wwsf=45.0, wtsd=28.0, hands=200):
    row = PopulationRow(name=name, hands=hands)
    row.vpip_pfr_opp = hands
    row.vpip = round(vpip / 100 * hands)
    row.pfr = round(pfr / 100 * hands)
    row.three_bet_opp = hands
    row.three_bet = round(three_bet / 100 * hands)
    row.faced_3bet_opp = hands
    row.folded_to_3bet = round(fold_3bet / 100 * hands)
    row.saw_flop = hands
    row.won_saw_flop = round(wwsf / 100 * hands)
    row.reached_showdown = round(wtsd / 100 * hands)
    return row


def test_identical_profile_scores_100_similarity():
    target = _row("Target", vpip=25, pfr=20)
    twin = _row("Twin", vpip=25, pfr=20)
    rows = {"Target": target, "Twin": twin}

    results = find_similar_villains("Target", rows)
    assert len(results) == 1
    assert results[0].name == "Twin"
    assert results[0].similarity == 100.0


def test_ranks_closer_profiles_above_further_ones():
    target = _row("Target", vpip=25, pfr=20)
    close = _row("Close", vpip=27, pfr=21)
    far = _row("Far", vpip=55, pfr=8)
    rows = {"Target": target, "Close": close, "Far": far}

    results = find_similar_villains("Target", rows)
    assert [r.name for r in results] == ["Close", "Far"]
    assert results[0].similarity > results[1].similarity


def test_excludes_the_target_itself():
    target = _row("Target", vpip=25, pfr=20)
    rows = {"Target": target}
    assert find_similar_villains("Target", rows) == []


def test_excludes_candidates_below_min_hands():
    target = _row("Target", vpip=25, pfr=20)
    thin = _row("Thin", vpip=25, pfr=20, hands=MIN_HANDS_FOR_SIMILARITY - 1)
    rows = {"Target": target, "Thin": thin}
    assert find_similar_villains("Target", rows) == []


def test_includes_candidate_exactly_at_min_hands():
    target = _row("Target", vpip=25, pfr=20)
    exact = _row("Exact", vpip=25, pfr=20, hands=MIN_HANDS_FOR_SIMILARITY)
    rows = {"Target": target, "Exact": exact}
    assert len(find_similar_villains("Target", rows)) == 1


def test_missing_dimension_is_skipped_not_counted_as_zero_difference():
    target = _row("Target", vpip=25, pfr=20)
    target.three_bet_opp = 0  # target has no 3-bet opportunities recorded at all -> three_bet_pct is None

    other = _row("Other", vpip=25, pfr=20, three_bet=50.0)  # wildly different 3-bet, if it counted
    rows = {"Target": target, "Other": other}

    results = find_similar_villains("Target", rows)
    # Should still score high — the mismatched 3-bet dimension can't be
    # compared (target has no value) so it must not drag the score down.
    assert results[0].similarity == 100.0


def test_unknown_target_name_returns_empty_list():
    rows = {"SomeoneElse": _row("SomeoneElse", vpip=25, pfr=20)}
    assert find_similar_villains("DoesNotExist", rows) == []


def test_limit_truncates_the_result_list():
    target = _row("Target", vpip=25, pfr=20)
    rows = {"Target": target}
    for i in range(10):
        rows[f"V{i}"] = _row(f"V{i}", vpip=25 + i, pfr=20)

    results = find_similar_villains("Target", rows, limit=3)
    assert len(results) == 3
