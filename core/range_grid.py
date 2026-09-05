"""Turns known hole-card pairs into the standard 13x13 starting-hand-grid
shape (diagonal = pairs, upper-right triangle = suited, lower-left
triangle = offsuit) for the villain-profile hand-range heatmap
(ui/range_grid.py). Pure data logic, no Qt — this only ever sees the
SUBSET of hands where hole cards are actually known (a showdown or a
voluntary show), which is usually a small, biased sample of a stat's
full hand count; callers are responsible for saying so in the UI rather
than presenting this as someone's true range."""
from core.card_utils import RANKS as _ASCENDING_RANKS

RANKS = list(reversed(_ASCENDING_RANKS))  # A, K, Q, ..., 2 — grid row/column order


def hand_notation(card1: str, card2: str) -> str:
    """Two cards in "<rank><suit>" form (e.g. "K♦", "A♠") -> standard
    notation with the higher rank first: "AA" for a pair, "AKs"/"AKo"
    for two different ranks."""
    rank1, suit1 = card1[:-1], card1[-1]
    rank2, suit2 = card2[:-1], card2[-1]
    idx1, idx2 = RANKS.index(rank1), RANKS.index(rank2)
    if idx1 > idx2:
        rank1, rank2, suit1, suit2 = rank2, rank1, suit2, suit1
    if rank1 == rank2:
        return f"{rank1}{rank2}"
    return f"{rank1}{rank2}{'s' if suit1 == suit2 else 'o'}"


def grid_layout() -> list[list[str]]:
    """13x13 grid of hand-notation labels in standard chart order —
    grid_layout()[row][col], both indexed by RANKS (row 0 = A, ...,
    row 12 = 2). Diagonal = pairs, upper-right triangle (row < col) =
    suited, lower-left triangle (row > col) = offsuit."""
    grid = []
    for i, r1 in enumerate(RANKS):
        row = []
        for j, r2 in enumerate(RANKS):
            if i == j:
                row.append(f"{r1}{r2}")
            elif i < j:
                row.append(f"{r1}{r2}s")
            else:
                row.append(f"{r2}{r1}o")
        grid.append(row)
    return grid


def tally_hands(hole_card_pairs: list[tuple[str, str]]) -> dict[str, int]:
    """{notation: count} across every pair given — e.g. two separate
    hands both holding AKs both count toward "AKs": 2."""
    counts: dict[str, int] = {}
    for card1, card2 in hole_card_pairs:
        notation = hand_notation(card1, card2)
        counts[notation] = counts.get(notation, 0) + 1
    return counts
