"""Groups villains by overall stat profile instead of leaving the user to
sort one column at a time — useful once a population runs into the
thousands. This is a simple weighted distance across the same handful of
percentages already shown in the Population tab's villain list
(ui/population_summary.py's PopulationRow), not a machine-learning
model: every dimension is a real, already-computed percentage, and
"similarity" is just how close two players are across all of them at
once, converted to a 0-100 scale for readability."""
from dataclasses import dataclass

# Weights reflect how distinguishing/reliable each dimension actually is:
# VPIP/PFR describe a player's fundamental looseness and aggression and
# are available from hand 1; 3-bet is more situational and needs more
# hands to mean anything; fold-to-3-bet is a level further removed
# still; WWSF/WTSD only exist for hands that reached a flop/showdown, so
# they're built on the smallest, noisiest sample of the six.
DIMENSION_WEIGHTS = {
    "vpip_pct": 1.5, "pfr_pct": 1.5, "three_bet_pct": 1.0,
    "fold_3bet_pct": 0.75, "wwsf_pct": 0.5, "wtsd_pct": 0.5,
}
MIN_HANDS_FOR_SIMILARITY = 30

# Converts an average weighted percentage-point difference into a 0-100
# similarity score — a documented, tunable heuristic, not a statistically
# derived constant. 2 points of average deviation costs 4 similarity
# points; anything averaging 50+ points apart (players who disagree on
# nearly everything) floors out at 0 rather than going negative.
_DEVIATION_TO_SIMILARITY_SCALE = 2.0


@dataclass
class SimilarPlayer:
    name: str
    similarity: float  # 0-100; 100 = identical on every measured dimension
    hands: int


def find_similar_villains(target_name: str, all_rows: dict, limit: int = 5,
                           min_hands: int = MIN_HANDS_FOR_SIMILARITY) -> list["SimilarPlayer"]:
    """Ranks every other villain in `all_rows` (a {name: PopulationRow}
    dict — exactly what database.queries.population_summary_query
    returns) by similarity to `target_name`. A candidate below
    `min_hands` is skipped entirely — a player with 12 hands doesn't
    have a real stat profile to compare against yet, and including them
    would just inject noise into the ranking. A DIMENSION missing on
    either side (not enough hands for that specific stat) is skipped
    for that pair rather than counted as "0 difference," which would
    flatter a comparison built mostly on absent data."""
    target_row = all_rows.get(target_name)
    if target_row is None:
        return []

    candidates = []
    for name, row in all_rows.items():
        if name == target_name or row.hands < min_hands:
            continue
        total_weight = 0.0
        weighted_diff = 0.0
        for dim, weight in DIMENSION_WEIGHTS.items():
            target_val = getattr(target_row, dim)
            other_val = getattr(row, dim)
            if target_val is None or other_val is None:
                continue
            weighted_diff += weight * abs(target_val - other_val)
            total_weight += weight
        if total_weight == 0:
            continue
        avg_diff = weighted_diff / total_weight
        similarity = max(0.0, 100.0 - avg_diff * _DEVIATION_TO_SIMILARITY_SCALE)
        candidates.append(SimilarPlayer(name=name, similarity=round(similarity, 1), hands=row.hands))

    candidates.sort(key=lambda c: c.similarity, reverse=True)
    return candidates[:limit]
