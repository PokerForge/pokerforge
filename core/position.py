"""Preflop position derivation from seat numbers and the button seat.

Confirmed against the full real dataset: table_size is always 6, but active
seats vary hand-to-hand (2-6 players observed) as people sit in/out. Seat
numbers are drawn from a fixed set (Grosvenor always uses {1,3,5,6,8,10} for
a 6-max table) that increases in clockwise order — the algorithm below only
relies on that monotonic-clockwise property, not the specific numbers.
"""
from models.hand import Hand

# Position labels going clockwise FROM the button, by number of active
# players. The 4-handed seat after BB was originally labeled 'UTG', but
# cross-checking a real PT4 by-position export (Statsallhandsthisyear.csv)
# against this app's own numbers showed a ~6,822-hand gap between UTG and
# CO that exactly matched the number of 4-handed hands hero played —
# PT4 calls that seat 'CO' at 4-handed, not 'UTG'. Confirmed, not guessed.
POSITION_LABELS = {
    2: ['BTN/SB', 'BB'],
    3: ['BTN', 'SB', 'BB'],
    4: ['BTN', 'SB', 'BB', 'CO'],
    5: ['BTN', 'SB', 'BB', 'UTG', 'CO'],
    6: ['BTN', 'SB', 'BB', 'UTG', 'MP', 'CO'],
}


def assign_positions(hand: Hand) -> dict[str, str]:
    """Returns {player_name: position_label} for this hand, or {} if the
    button seat or active player count don't match a known configuration."""
    if hand.button_seat is None:
        return {}
    active_seats = sorted(p.seat for p in hand.players if p.seat is not None)
    labels = POSITION_LABELS.get(len(active_seats))
    if not labels or hand.button_seat not in active_seats:
        return {}

    btn_idx = active_seats.index(hand.button_seat)
    ordered_seats = active_seats[btn_idx:] + active_seats[:btn_idx]
    seat_to_label = dict(zip(ordered_seats, labels))

    return {p.name: seat_to_label[p.seat] for p in hand.players if p.seat in seat_to_label}


# Postflop acting order (SB acts first, BTN last) — the reverse of the
# preflop order the labels above are named for. BTN/SB (heads-up) acts
# LAST postflop, same as BTN, not first like SB.
_POSTFLOP_ORDER = {'SB': 0, 'BB': 1, 'UTG': 2, 'MP': 3, 'CO': 4, 'BTN': 5, 'BTN/SB': 5}


def has_position_on(positions: dict[str, str], player: str, other: str) -> bool:
    """True if `player` acts after `other` postflop (i.e. is "in position" on them)."""
    p1, p2 = positions.get(player), positions.get(other)
    if p1 is None or p2 is None:
        return False
    return _POSTFLOP_ORDER[p1] > _POSTFLOP_ORDER[p2]
