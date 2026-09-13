"""Population-wide river bet-sizing vs revealed hand strength — not one
villain's tendencies, a pattern pooled across every showdown in the
user's own database. The pot-before-the-bet reconstruction uses the same
Raise-is-a-new-total vs Call/Bet/Allin-is-a-direct-delta convention
already validated in ui/hand_replayer.py's _build_events (see that
module's own tests) — reimplemented here rather than imported, since
core/ modules stay framework-independent and don't reach into ui/."""
from core.equity import best_hand_rank

# (label, lo, hi) — ratio of river bet to the pot immediately before it.
SIZING_BUCKETS = [
    ("33-50% pot", 0.33, 0.50),
    ("50-100% pot", 0.50, 1.00),
    ("100%+ pot (overbet)", 1.00, float("inf")),
]

# best_hand_rank's category: 0=High Card ... 8=Straight Flush. Three of a
# Kind or better counts as "strong" here — a coarse, disclosed cutoff for
# a value/bluff proxy, not a claim about actual hand strength in context
# (a made straight can still be a bluff-catcher on some boards, and top
# pair can be a clear value bet on others; this is a population-wide
# pattern, not hand-by-hand analysis).
_STRONG_CATEGORY_THRESHOLD = 3


def _river_bet_and_pot_before(hand) -> tuple[str, float, float] | None:
    """Finds the LAST river bet/raise/allin action with a positive delta
    in `hand` and the pot size immediately before it fired. Returns
    (player, bet_amount, pot_before) or None if the river was checked
    through or the hand never reached it."""
    committed: dict[str, float] = {}
    pot = 0.0
    current_street = None
    last_river_bet = None
    for a in hand.actions:
        if a.street != current_street:
            current_street = a.street
            committed = {}
        prior = committed.get(a.player, 0.0)
        if a.action == 'Raise':
            new_total = a.amount if a.amount is not None else prior
            delta = new_total - prior
            committed[a.player] = new_total
        elif a.action == 'Uncalled Return':
            delta = -(a.amount or 0.0)
            committed[a.player] = prior + delta
        elif a.action in ('Post SB', 'Post BB', 'Call', 'Bet', 'Allin'):
            delta = a.amount or 0.0
            committed[a.player] = prior + delta
        else:
            delta = 0.0

        if current_street == 'RIVER' and a.action in ('Bet', 'Raise', 'Allin') and delta > 0:
            last_river_bet = (a.player, delta, pot)
        pot += delta
    return last_river_bet


def _sizing_bucket(bet: float, pot_before: float) -> str | None:
    if pot_before <= 0:
        return None
    ratio = bet / pot_before
    for label, lo, hi in SIZING_BUCKETS:
        if lo <= ratio < hi:
            return label
    return None


def classify_river_sizing_vs_strength(hands: list, exclude_player: str | None = None) -> dict:
    """`hands`: already-loaded Hand objects — the caller decides which
    ones to load (typically showdown hands only, via a DB pre-filter;
    see database.queries.showdown_hand_ids_query), since loading every
    hand in a database just to discard the ones with no river bet here
    would be wasteful. Returns {bucket_label: {"strong": n, "weak": n}}
    pooled across every hand and every player (other than
    `exclude_player`, typically hero) whose hole cards were revealed at
    showdown — a real, counted pattern from this user's own database,
    not a universal poker claim."""
    result = {label: {"strong": 0, "weak": 0} for label, _, _ in SIZING_BUCKETS}
    for hand in hands:
        river_bet = _river_bet_and_pot_before(hand)
        if river_bet is None:
            continue
        player, bet, pot_before = river_bet
        if player == exclude_player:
            continue
        bucket = _sizing_bucket(bet, pot_before)
        if bucket is None:
            continue
        p = next((pl for pl in hand.players if pl.name == player), None)
        if not p or len(p.hole_cards) != 2 or len(hand.board) < 5:
            continue
        category = best_hand_rank(p.hole_cards + hand.board)[0]
        strength = "strong" if category >= _STRONG_CATEGORY_THRESHOLD else "weak"
        result[bucket][strength] += 1
    return result
