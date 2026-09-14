"""Cross-dimensional leak-hunting — ranks hero's stat deviations from the
population by (position, stat) instead of one flat number per stat, so
the result surfaces WHERE a leak actually shows up, not just THAT one
exists somewhere in the overall average. The population side is the
real, pooled average computed from the user's own imported villain pool
(database.queries.population_by_position_query), not a fixed reference
threshold — see that function's docstring for why it mirrors
position_breakdown_query almost exactly."""
from dataclasses import dataclass

MIN_SAMPLE = 20

# The stat ids worth leak-hunting over — mirrors ui/player_classify.py's
# generate_hero_leaks coverage, since these are the stats with an
# established "more/less is better" direction and a real opportunity
# count to weight by. Not every stat belongs here (e.g. bb100 has no
# opportunity-count denominator to weight a deviation against).
LEAK_STAT_IDS = [
    "vpip", "pfr", "three_bet", "fold_3bet", "four_bet", "fold_4bet",
    "fold_to_steal", "flop_fold_cbet", "wtsd", "wsd",
]

STAT_LABELS = {
    "vpip": "VPIP", "pfr": "PFR", "three_bet": "3-Bet", "fold_3bet": "Fold to 3-Bet",
    "four_bet": "4-Bet", "fold_4bet": "Fold to 4-Bet", "fold_to_steal": "Fold to Steal",
    "flop_fold_cbet": "Fold to Flop C-Bet", "wtsd": "WTSD", "wsd": "W$SD",
}

# Groups LEAK_STAT_IDS into the categories a user would actually want to
# filter by — e.g. "am I leaking on 3-bets specifically" rather than
# whatever single stat happens to have the biggest deviation everywhere.
# Order here is display order in the filter control.
LEAK_CATEGORIES = {
    "Preflop Opens": ["vpip", "pfr"],
    "3-Bet & 4-Bet": ["three_bet", "fold_3bet", "four_bet", "fold_4bet"],
    "Steal Defense": ["fold_to_steal"],
    "Postflop": ["flop_fold_cbet"],
    "Showdown": ["wtsd", "wsd"],
}


@dataclass
class LeakEntry:
    position: str
    stat_id: str
    stat_label: str
    hero_rate: float
    population_rate: float
    sample: int
    score: float

    @property
    def deviation(self) -> float:
        return self.hero_rate - self.population_rate


def find_leaks(hero_by_position: dict, population_by_position: dict,
               min_sample: int = MIN_SAMPLE) -> list[LeakEntry]:
    """hero_by_position / population_by_position: {position: (values,
    hand_count, opp_counts)} — the exact return shape of
    database.queries' position_breakdown_query and
    population_by_position_query. Returns every (position, stat) pair
    with enough sample to trust, ranked by
    |hero_rate - population_rate| * sample — a big deviation on
    something rare isn't automatically ranked above a moderate one on
    something that comes up constantly, since the latter is worth more
    in practice."""
    entries = []
    for position, (hero_values, _hero_hands, hero_opp) in hero_by_position.items():
        pop_data = population_by_position.get(position)
        if pop_data is None:
            continue
        pop_values, _pop_hands, _pop_opp = pop_data
        for stat_id in LEAK_STAT_IDS:
            hero_rate = hero_values.get(stat_id)
            pop_rate = pop_values.get(stat_id)
            sample = hero_opp.get(stat_id) or 0
            if hero_rate is None or pop_rate is None or sample < min_sample:
                continue
            deviation = hero_rate - pop_rate
            score = round(abs(deviation) * sample, 1)
            entries.append(LeakEntry(
                position=position, stat_id=stat_id, stat_label=STAT_LABELS.get(stat_id, stat_id),
                hero_rate=hero_rate, population_rate=pop_rate, sample=sample, score=score,
            ))
    entries.sort(key=lambda e: e.score, reverse=True)
    return entries


@dataclass
class ImprovementEntry:
    position: str
    stat_id: str
    stat_label: str
    current_rate: float
    previous_rate: float
    population_rate: float
    improvement: float  # positive = the gap to the population average shrank


def find_biggest_improvement(current_by_position: dict, previous_by_position: dict,
                              current_population_by_position: dict,
                              previous_population_by_position: dict,
                              min_sample: int = MIN_SAMPLE) -> "ImprovementEntry | None":
    """"Improvement" here means the SAME (position, stat) deviation
    find_leaks scores — |hero_rate - population_rate| — got smaller from
    one period to the next, i.e. hero moved closer to the pool's own
    average. Deliberately not a fixed "more/less is always better"
    per-stat rule: whether higher or lower VPIP is "good" depends on
    whether hero was already too loose or too tight, which the
    population comparison already captures without needing a second,
    separate directionality table to keep in sync with LEAK_STAT_IDS.
    Requires enough sample in BOTH periods, on both the hero and
    population side, to trust the comparison; returns None if nothing
    both qualifies and actually improved."""
    best = None
    for position, (cur_values, _cur_hands, cur_opp) in current_by_position.items():
        prev_data = previous_by_position.get(position)
        cur_pop_data = current_population_by_position.get(position)
        prev_pop_data = previous_population_by_position.get(position)
        if not prev_data or not cur_pop_data or not prev_pop_data:
            continue
        prev_values, _prev_hands, prev_opp = prev_data
        cur_pop_values, _, _ = cur_pop_data
        prev_pop_values, _, _ = prev_pop_data
        for stat_id in LEAK_STAT_IDS:
            cur_rate = cur_values.get(stat_id)
            prev_rate = prev_values.get(stat_id)
            cur_pop_rate = cur_pop_values.get(stat_id)
            prev_pop_rate = prev_pop_values.get(stat_id)
            if None in (cur_rate, prev_rate, cur_pop_rate, prev_pop_rate):
                continue
            if (cur_opp.get(stat_id) or 0) < min_sample or (prev_opp.get(stat_id) or 0) < min_sample:
                continue
            improvement = round(abs(prev_rate - prev_pop_rate) - abs(cur_rate - cur_pop_rate), 2)
            if improvement > 0 and (best is None or improvement > best.improvement):
                best = ImprovementEntry(
                    position=position, stat_id=stat_id, stat_label=STAT_LABELS.get(stat_id, stat_id),
                    current_rate=cur_rate, previous_rate=prev_rate, population_rate=cur_pop_rate,
                    improvement=improvement,
                )
    return best


def diversify_leaks(entries: list[LeakEntry], max_per_stat: int = 2) -> list[LeakEntry]:
    """`entries` sorted by score, e.g. find_leaks's return. Keeps only the
    top `max_per_stat` entries for any one stat_id, so one dominant stat
    (typically VPIP, since it deviates by position more consistently than
    anything else) doesn't fill every slot in a short displayed list and
    crowd out other real leaks. Preserves the incoming score order."""
    counts: dict[str, int] = {}
    kept = []
    for entry in entries:
        n = counts.get(entry.stat_id, 0)
        if n >= max_per_stat:
            continue
        counts[entry.stat_id] = n + 1
        kept.append(entry)
    return kept
