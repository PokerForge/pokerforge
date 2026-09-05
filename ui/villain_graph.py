"""Villain profile graph data: the villain's own results (total/showdown/
non-showdown), plus the hero's own profit specifically in the hands they
shared with this villain (the "Purple = Your profit vs them" line from the
legacy dashboard). Both are computed over the same hand set — every hand in
our data includes the hero by construction (hand histories only cover hands
the account owner played), so "hands with this villain" already means
"hands where hero and villain both played"."""
from datetime import datetime
from models.hand import Hand
from core.stats import compute_invested, analyze_showdown


def compute_villain_graph(hands: list[Hand], hero: str, villain: str):
    """Returns (graph, villain_total_profit, hero_profit_vs_villain) where
    graph = (xs, villain_total, villain_showdown, villain_nonshowdown, hero_vs)."""
    shared = [h for h in hands if villain in {p.name for p in h.players}]
    shared.sort(key=lambda h: h.played_at or datetime.min)

    xs, v_total, v_sd, v_nonsd, hero_vs = [], [], [], [], []
    running_v_total = running_v_sd = running_v_nonsd = running_hero = 0.0
    for i, h in enumerate(shared, 1):
        invested = compute_invested(h)
        v_profit = h.winnings.get(villain, 0.0) - invested.get(villain, 0.0)
        hero_profit = h.winnings.get(hero, 0.0) - invested.get(hero, 0.0)

        sd = analyze_showdown(h).get(villain)
        running_v_total += v_profit
        if sd and sd.reached_showdown:
            running_v_sd += v_profit
        else:
            running_v_nonsd += v_profit
        running_hero += hero_profit

        xs.append(i)
        v_total.append(running_v_total)
        v_sd.append(running_v_sd)
        v_nonsd.append(running_v_nonsd)
        hero_vs.append(running_hero)

    graph = (xs, v_total, v_sd, v_nonsd, hero_vs)
    return graph, running_v_total, running_hero
