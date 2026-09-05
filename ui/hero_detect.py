"""Auto-detects the hero (the account owner) as whoever appears in the most
hands — mirrors poker_dashboard_legacy.py's SQL-based _get_hero(), just
computed from in-memory hands instead of a DB query. Avoids hardcoding a
specific username, since this needs to work for other people's hand
histories too.

Also handles known hero aliases: a player who games on more than one
username (a second account) should be treated as one identity everywhere —
excluded from the villain pool, and folded into the hero's own stats —
rather than showing up as a separate "villain" with a suspicious 0%
sample size."""
import re
from collections import Counter
from models.hand import Hand
from config.settings import get_hero_aliases

# iPoker anonymizes opponents on some table types as "Player 3", "Player 5",
# etc. These labels aren't a consistent identity across hands (a different
# real person can be "Player 3" in the next hand), so they must never be
# aggregated into the villain pool as if they were one person.
ANON_PLACEHOLDER = re.compile(r"^Player \d+$")


def detect_hero(hands: list[Hand]) -> str:
    counts = Counter()
    for h in hands:
        for p in h.players:
            counts[p.name] += 1
    return counts.most_common(1)[0][0] if counts else "Hero"


def dominant_currency(hands: list[Hand], hero: str) -> str:
    """The currency symbol to report money in — whichever currency the
    hero's own hands are mostly played in. Hero plays a small minority of
    hands (~2%) on EUR tables mixed in with mostly-GBP volume; rather than
    invent an exchange rate to combine them, money totals are reported in
    the dominant currency and the minority-currency hands are a known,
    documented rounding source rather than a silently guessed conversion."""
    counts = Counter()
    for h in hands:
        if any(p.name == hero for p in h.players):
            counts[h.currency] += 1
    return counts.most_common(1)[0][0] if counts else "£"


def normalize_hero_aliases(hands: list[Hand], primary_hero: str) -> None:
    """Rewrites any known alt-account username to the primary hero name,
    across players/actions/winnings, so every stat and villain-pool
    calculation downstream sees one unified hero identity."""
    aliases = set(get_hero_aliases()) - {primary_hero}
    if not aliases:
        return
    for h in hands:
        for p in h.players:
            if p.name in aliases:
                p.name = primary_hero
        for a in h.actions:
            if a.player in aliases:
                a.player = primary_hero
        if h.winnings:
            merged = 0.0
            hit = False
            for alias in list(h.winnings.keys()):
                if alias in aliases:
                    merged += h.winnings.pop(alias)
                    hit = True
            if hit:
                h.winnings[primary_hero] = h.winnings.get(primary_hero, 0.0) + merged
