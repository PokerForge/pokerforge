"""Illustrative example data for the guided tour, used only when the
real database is genuinely empty (a brand-new install, before the first
hand's been played) — every step would otherwise show an empty graph or
a table full of dashes, which doesn't give a new user any idea what the
feature actually looks like.

Reuses core.demo_data's existing synthetic-hand generator rather than
hand-crafting each tab's own internal result shape: the generated Hand
objects go through the exact same PokerDatabase.import_hands() pipeline
real hands do, so every query a tab already trusts (hero_overview_query,
sessions_query, position_breakdown_query, population_by_position_query,
pct_trend_query, villain_stats_query, ...) produces a realistic,
internally-consistent result automatically — nothing here has to
duplicate or guess at any of those shapes by hand."""
from datetime import date

from core.demo_data import generate_demo_hands, DEMO_HERO
from database.repository import PokerDatabase

EXAMPLE_HERO = DEMO_HERO
EXAMPLE_D_FROM = date(2000, 1, 1)
EXAMPLE_D_TO = date.today()
# Small and fast (well under a second to generate + import) — this only
# needs to look populated, not be a large realistic sample; the real
# "Load Demo Data" feature elsewhere in the app generates a much bigger
# batch (3000 hands) for actually trying the app, a different purpose.
_EXAMPLE_HAND_COUNT = 300


def build_example_database() -> PokerDatabase:
    db = PokerDatabase(":memory:")
    hands = generate_demo_hands(n=_EXAMPLE_HAND_COUNT)
    db.import_hands(hands, ev_iterations=100)
    return db
