"""core/range_grid.py — hand-notation conversion and grid layout for the
villain hand-range heatmap. Getting the suited/offsuit/pair distinction
and the higher-rank-first ordering wrong here would mislabel every cell
in the grid, so this is worth pinning down precisely."""
from core.range_grid import hand_notation, grid_layout, tally_hands, RANKS


def test_pair_notation():
    assert hand_notation("A♠", "A♦") == "AA"
    assert hand_notation("2♣", "2♥") == "22"


def test_suited_notation_higher_rank_first():
    assert hand_notation("K♦", "A♦") == "AKs"
    assert hand_notation("A♦", "K♦") == "AKs"  # order of args shouldn't matter


def test_offsuit_notation_higher_rank_first():
    assert hand_notation("K♦", "A♠") == "AKo"
    assert hand_notation("A♠", "K♦") == "AKo"


def test_low_cards_offsuit_and_suited():
    assert hand_notation("7♣", "2♦") == "72o"
    assert hand_notation("7♣", "2♣") == "72s"


def test_grid_layout_is_13x13():
    grid = grid_layout()
    assert len(grid) == 13
    assert all(len(row) == 13 for row in grid)


def test_grid_diagonal_is_pairs():
    grid = grid_layout()
    for i, rank in enumerate(RANKS):
        assert grid[i][i] == f"{rank}{rank}"


def test_grid_upper_triangle_is_suited_lower_is_offsuit():
    grid = grid_layout()
    # row 0 = A, col 1 = K -> above diagonal -> suited
    assert grid[0][1] == "AKs"
    # row 1 = K, col 0 = A -> below diagonal -> offsuit
    assert grid[1][0] == "AKo"


def test_grid_corners_match_known_hands():
    grid = grid_layout()
    assert grid[0][0] == "AA"       # top-left: best pair
    assert grid[12][12] == "22"     # bottom-right: worst pair
    assert grid[0][12] == "A2s"     # top-right: A2 suited
    assert grid[12][0] == "A2o"     # bottom-left: A2 offsuit


def test_tally_hands_counts_each_notation():
    pairs = [("A♠", "A♦"), ("K♦", "A♦"), ("A♦", "K♦"), ("7♣", "2♦")]
    counts = tally_hands(pairs)
    assert counts == {"AA": 1, "AKs": 2, "72o": 1}


def test_tally_hands_empty_list_returns_empty_dict():
    assert tally_hands([]) == {}
