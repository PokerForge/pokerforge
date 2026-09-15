"""Proportional pairwise pot settlement — for a single hand, how much one
specific player (typically hero) won or lost specifically to/from each
OTHER player at the table, rather than just crediting/blaming whoever
happened to be dealt into the hand for the player's entire hand result.

The rule: each net winner's gain is distributed across net losers in
proportion to each loser's own net loss (and symmetrically, each net
loser's loss is distributed across net winners in proportion to their
gains). This is exact for any hand with a single pot — the overwhelming
majority of hands, since a side pot only forms when a player is all-in for
less than everyone else can still wager. For a hand WITH a side pot, this
can misattribute a modest amount between two remaining players if one of
them is a net winner overall despite being a net loser in an
already-decided earlier pot layer (true side-pot reconstruction would need
to replay exact contribution caps and per-layer winners, which isn't
cleanly recoverable from the hand-history data available). That's a
disclosed, bounded approximation, not a silent one.

Confirmed against real per-opponent results: replacing the previous
"attribute the whole hand's profit to any villain who was dealt in" logic
with this fixed the cases where that produced numbers with the wrong sign.
"""
from models.hand import Action, Hand
from core.stats import compute_invested


def settlement_for_player(actions: list[Action], winnings: dict[str, float],
                            player: str) -> dict[str, float]:
    """Returns {other_player: amount} for one hand — how much `player` won
    (positive) or lost (negative) specifically against each other player
    who had a nonzero net result in that hand. Players who broke even
    (folded without further net cost beyond blinds already returned, or
    otherwise ended up exactly where they started) don't appear, since
    there's nothing to settle with them."""
    invested = compute_invested(Hand(hand_id='', actions=actions))
    names = set(invested) | set(winnings)
    net = {n: winnings.get(n, 0.0) - invested.get(n, 0.0) for n in names}
    player_net = net.get(player, 0.0)
    if abs(player_net) < 1e-9:
        return {}

    if player_net > 0:
        total_losses = sum(-v for v in net.values() if v < 0)
        if total_losses <= 1e-9:
            return {}
        return {n: player_net * (-v / total_losses)
                for n, v in net.items() if n != player and v < 0}
    else:
        total_wins = sum(v for v in net.values() if v > 0)
        if total_wins <= 1e-9:
            return {}
        player_loss = -player_net
        return {n: -(player_loss * v / total_wins)
                for n, v in net.items() if n != player and v > 0}
