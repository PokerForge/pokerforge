"""Hero's own overview: profit graph (total/showdown/non-showdown) and the
top-line stat row, for the Overview tab. Reuses the exact same validated
functions as the villain browser — hero is just another player_name.

Note: "Profit" sums raw amounts across whatever currency each hand was
in (mostly GBP; a small fraction of hands are EUR — no exchange-rate
conversion is applied). BB/100 is unaffected since it's computed per-hand
as profit/that hand's own big_blind, a same-currency ratio either way.
"""
from datetime import datetime, date
from models.hand import Hand
from core.stats import compute_invested, analyze_showdown
from core.ev import compute_hand_ev
from ui.compute_stats import compute_all_stats, EV_HAND_LIMIT
from ui.stakes import stakes_label

OVERVIEW_STATS = [
    ("Hands", "hands", "int"),
    ("Profit", "profit", "money"),
    ("BB/100", "bb100", "signed"),
    ("EV BB/100", "ev_bb100", "signed"),
    ("VPIP %", "vpip", "pct", 22, 26),
    ("PFR %", "pfr", "pct", 17, 21),
    ("3-Bet %", "three_bet", "pct", 8, 10),
    ("Fold 3-Bet %", "fold_3bet", "pct", 50, 60),
    ("4-Bet %", "four_bet", "pct"),
    ("Fold 4-Bet %", "fold_4bet", "pct", 45, 55),
    ("WTSD %", "wtsd", "pct", 26, 32),
    ("WWSF %", "wwsf", "pct", 38, 46),
    ("W$SD %", "wsd", "pct", 50, 56),
]


def _in_range(hand: Hand, d_from: date, d_to: date) -> bool:
    d = hand.played_date
    return d is not None and d_from <= d <= d_to


def compute_hero_overview(hands: list[Hand], hero: str, d_from: date, d_to: date, stake: str | None = None):
    """Returns (stat_values: dict, graph: (xs, total, showdown, non_showdown))."""
    filtered = [h for h in hands if hero in {p.name for p in h.players} and _in_range(h, d_from, d_to)
                and (stake is None or stakes_label(h) == stake)]
    filtered.sort(key=lambda h: h.played_at or datetime.min)

    values, hand_count, _ = compute_all_stats(filtered, hero)
    values["hands"] = hand_count

    # See EV_HAND_LIMIT in ui/compute_stats.py — an EV line needs a Monte
    # Carlo equity run per all-in hand found, which is fine for a normal
    # period but too slow to add on top of an already-slow "All Time" pass
    # across a quarter million hands.
    compute_ev_line = len(filtered) <= EV_HAND_LIMIT

    total_profit = 0.0
    xs, total, showdown, non_showdown, ev_line = [], [], [], [], []
    running_total = running_sd = running_nonsd = running_ev = 0.0
    for i, h in enumerate(filtered, 1):
        invested_amt = compute_invested(h).get(hero, 0.0)
        profit = h.winnings.get(hero, 0.0) - invested_amt
        total_profit += profit
        sd = analyze_showdown(h).get(hero)
        if sd and sd.reached_showdown:
            running_sd += profit
        else:
            running_nonsd += profit
        running_total += profit
        xs.append(i)
        total.append(running_total)
        showdown.append(running_sd)
        non_showdown.append(running_nonsd)
        if compute_ev_line:
            ev = compute_hand_ev(h, hero, iterations=50)
            running_ev += ev if ev is not None else profit
            ev_line.append(running_ev)
    values["profit"] = total_profit

    return values, (xs, total, showdown, non_showdown, ev_line if compute_ev_line else None)
