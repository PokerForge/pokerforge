"""All-in EV (expected value) for individual hands — detects heads-up
all-in showdown spots and compares the actual result to the mathematically
"should have won" equity share, removing the variance of which cards
happened to land. See core/equity.py for the underlying hand evaluator.

Deliberately scoped to heads-up (exactly 2 players reaching showdown) —
multi-way all-in equity is a genuinely different calculation (each
player's equity against the whole field, not one opponent) and isn't
attempted here. A hand only qualifies when both contesting players' hole
cards are known (they showed at showdown) and betting stopped before the
river (a real all-in with cards still to come) — a hand that gets checked
all the way down has no variance to remove."""
from models.hand import Hand
from core.stats import compute_invested
from core.equity import hand_equity

_STREET_ORDER = ['PREFLOP', 'FLOP', 'TURN', 'RIVER']


def _last_real_action_street(hand: Hand) -> str | None:
    """The street of the last action that represents an actual decision —
    excludes folds (a fold ends the hand, it doesn't leave cards to come)
    and blind posts/returns, which aren't betting decisions."""
    last = None
    for a in hand.actions:
        if a.action in ('Fold', 'Post SB', 'Post BB', 'Uncalled Return'):
            continue
        last = a.street
    return last


def compute_hand_ev(hand: Hand, hero: str, iterations: int = 400) -> float | None:
    """Hero's EV-adjusted profit for this hand, or None if it isn't a
    computable heads-up all-in-before-the-river spot."""
    all_folders = {a.player for a in hand.actions if a.action == 'Fold'}
    non_folders = [p for p in hand.players if p.name not in all_folders]
    if len(non_folders) != 2 or hero not in {p.name for p in non_folders}:
        return None

    hero_p = next(p for p in non_folders if p.name == hero)
    villain_p = next(p for p in non_folders if p.name != hero)
    if len(hero_p.hole_cards) != 2 or len(villain_p.hole_cards) != 2:
        return None

    last_street = _last_real_action_street(hand)
    if last_street is None or last_street == 'RIVER':
        return None  # no all-in before the river -> nothing to adjust

    board_at_allin = {
        'PREFLOP': [],
        'FLOP': hand.board[:3],
        'TURN': hand.board[:4],
    }[last_street]

    invested = compute_invested(hand)
    hero_inv = invested.get(hero, 0.0)
    contested_pot = sum(invested.values())

    hero_equity, _ = hand_equity(hero_p.hole_cards, villain_p.hole_cards, board_at_allin, iterations=iterations)
    return hero_equity * contested_pot - hero_inv
