"""Poker hand evaluation and all-in equity calculation — the basis for the
EV (expected-value) stat/line. A hand's actual result is subject to the
variance of which cards land after money goes in; EV instead credits each
player with their mathematical win probability at the moment all money was
committed, which is the standard "luck-adjusted" line poker trackers show
alongside actual results.

Only computable when both players' hole cards are known (the hand reached
showdown) — a fold before showdown means the folder's cards are never
revealed, so there is nothing to compare equities against for that hand.
"""
import itertools
import random
from collections import Counter

RANKS = '23456789TJQKA'
RANK_VALUE = {r: i for i, r in enumerate(RANKS, start=2)}
SUITS = ['♣', '♦', '♥', '♠']
FULL_DECK = [r + s for r in RANKS for s in SUITS]


def rank_5(cards: list[str]) -> tuple:
    """Standard-poker ranking for exactly 5 cards, as a tuple that compares
    correctly (higher tuple = better hand) via normal Python comparison."""
    values = sorted((RANK_VALUE[c[0]] for c in cards), reverse=True)
    suits = [c[1] for c in cards]
    is_flush = len(set(suits)) == 1

    uniq_vals = sorted(set(values), reverse=True)
    is_straight, straight_high = False, None
    if len(uniq_vals) == 5 and uniq_vals[0] - uniq_vals[4] == 4:
        is_straight, straight_high = True, uniq_vals[0]
    elif set(values) == {14, 5, 4, 3, 2}:  # wheel: A-2-3-4-5, plays as a 5-high straight
        is_straight, straight_high = True, 5

    counts = Counter(values)
    groups = sorted(counts.items(), key=lambda kv: (-kv[1], -kv[0]))
    group_counts = [c for _, c in groups]
    group_values = [v for v, _ in groups]

    if is_straight and is_flush:
        return (8, straight_high)
    if group_counts[0] == 4:
        return (7, group_values[0], group_values[1])
    if group_counts[0] == 3 and group_counts[1] == 2:
        return (6, group_values[0], group_values[1])
    if is_flush:
        return (5, *values)
    if is_straight:
        return (4, straight_high)
    if group_counts[0] == 3:
        return (3, group_values[0], *group_values[1:])
    if group_counts[0] == 2 and group_counts[1] == 2:
        hi, lo = sorted((group_values[0], group_values[1]), reverse=True)
        return (2, hi, lo, group_values[2])
    if group_counts[0] == 2:
        return (1, group_values[0], *group_values[1:])
    return (0, *values)


def best_hand_rank(cards: list[str]) -> tuple:
    """Best 5-card ranking achievable from any number (5, 6 or 7) of cards."""
    if len(cards) == 5:
        return rank_5(cards)
    return max(rank_5(list(combo)) for combo in itertools.combinations(cards, 5))


def hand_equity(hole_a: list[str], hole_b: list[str], board: list[str],
                 iterations: int = 3000, seed=None) -> tuple[float, float]:
    """Heads-up all-in equity (ties split) for hole_a vs hole_b, with `board`
    cards already known and the remaining cards to come sampled via Monte
    Carlo. Exact enumeration would be exact but is too slow to run across
    thousands of hands in bulk (a flop all-in has C(46,2)=1035 exact
    runouts, a preflop all-in has C(48,5)=1,712,304); 3000 random runouts
    keeps error within roughly +/-1-2%, precise enough for a luck-adjustment
    stat rather than a solver-grade output — deterministic per hand (seeded
    from the cards themselves) so re-rendering a graph doesn't jitter."""
    known = set(hole_a) | set(hole_b) | set(board)
    remaining_deck = [c for c in FULL_DECK if c not in known]
    need = 5 - len(board)
    if need <= 0:
        a = best_hand_rank(hole_a + board)
        b = best_hand_rank(hole_b + board)
        return (1.0, 0.0) if a > b else (0.0, 1.0) if b > a else (0.5, 0.5)

    rng = random.Random(seed if seed is not None else hash(
        (tuple(sorted(hole_a)), tuple(sorted(hole_b)), tuple(board))))
    wins_a = wins_b = ties = 0
    for _ in range(iterations):
        runout = rng.sample(remaining_deck, need)
        full_board = board + runout
        a = best_hand_rank(hole_a + full_board)
        b = best_hand_rank(hole_b + full_board)
        if a > b:
            wins_a += 1
        elif b > a:
            wins_b += 1
        else:
            ties += 1
    total = wins_a + wins_b + ties
    return ((wins_a + ties * 0.5) / total, (wins_b + ties * 0.5) / total)
