"""Monthly Performance Report — headline stats for one calendar month,
each with a delta vs the previous month, plus that month's biggest leak
and biggest improvement (core/leak_finder.py). Pure aggregation over
already-queried data; the DB queries themselves live in
ui/monthly_report_dialog.py, same split as this app's other on-demand
reports (Pool Insights, Tilt Report, Backtest Deviations)."""
from dataclasses import dataclass

from core.leak_finder import find_leaks, find_biggest_improvement, LeakEntry, ImprovementEntry

# (values key, display label, suffix) — suffix is purely cosmetic
# (formatting happens in the UI layer); None means "no unit" (a plain
# count) or "$" is applied by the UI's own currency symbol instead.
HEADLINE_STATS = [
    ("hands", "Hands", None),
    ("profit", "Profit", "money"),
    ("bb100", "BB/100", None),
    ("vpip", "VPIP", "%"),
    ("pfr", "PFR", "%"),
    ("wtsd", "WTSD", "%"),
    ("wsd", "W$SD", "%"),
]


@dataclass
class HeadlineStat:
    key: str
    label: str
    value: float | None
    previous_value: float | None
    suffix: str | None = None

    @property
    def delta(self) -> float | None:
        if self.value is None or self.previous_value is None:
            return None
        return round(self.value - self.previous_value, 2)


@dataclass
class MonthlyReport:
    year: int
    month: int
    headline: list[HeadlineStat]
    biggest_leak: LeakEntry | None
    biggest_improvement: ImprovementEntry | None
    has_previous_month_data: bool


def build_monthly_report(
        year: int, month: int,
        current_overview: dict, previous_overview: dict | None,
        current_by_position: dict, previous_by_position: dict | None,
        current_pop_by_position: dict, previous_pop_by_position: dict | None,
) -> MonthlyReport:
    """`current_overview`/`previous_overview` are hero_overview_query's
    `values` dict; the `_by_position` dicts are position_breakdown_query
    (hero) / population_by_position_query (pool) shape, or None/empty
    when the previous month has no hero hands at all (a brand-new
    player's very first tracked month, or a month with a gap in play)."""
    headline = [
        HeadlineStat(
            key=key, label=label, value=current_overview.get(key),
            previous_value=(previous_overview or {}).get(key), suffix=suffix,
        )
        for key, label, suffix in HEADLINE_STATS
    ]

    leaks = find_leaks(current_by_position, current_pop_by_position)
    biggest_leak = leaks[0] if leaks else None

    biggest_improvement = None
    has_previous = bool(previous_overview and previous_overview.get('hands'))
    if has_previous and previous_by_position and previous_pop_by_position:
        biggest_improvement = find_biggest_improvement(
            current_by_position, previous_by_position,
            current_pop_by_position, previous_pop_by_position)

    return MonthlyReport(
        year=year, month=month, headline=headline,
        biggest_leak=biggest_leak, biggest_improvement=biggest_improvement,
        has_previous_month_data=has_previous,
    )
