"""Stakes derivation and filtering. A hand's "stakes" is its currency plus
small/big blind, e.g. "£0.02/£0.04" — kept as a single label since the
same numeric blinds in a different currency are not the same stake."""
from datetime import date
from models.hand import Hand


def stakes_label(hand: Hand) -> str:
    """Stakes stay labeled in the hand's original currency (matching PT4's
    own convention: it converts the money won, not the stake identity),
    even though core.currency.convert_hands_to_usd has converted the
    hand's actual money fields to USD by the time this is called."""
    sb = hand.native_small_blind if hand.native_small_blind is not None else hand.small_blind
    bb = hand.native_big_blind if hand.native_big_blind is not None else hand.big_blind
    cur = hand.native_currency or hand.currency or "£"
    sb = sb if sb is not None else 0
    bb = bb if bb is not None else 0
    return f"{cur}{sb:.2f}/{cur}{bb:.2f}"


def available_stakes(hands: list[Hand], hero: str, d_from: date, d_to: date) -> list[str]:
    """Distinct stakes hero actually played within [d_from, d_to], sorted
    smallest big-blind first — recomputed on every period change so the
    dropdown only ever offers stakes relevant to the selected period."""
    seen: dict[str, float] = {}
    for h in hands:
        if not h.played_date or not (d_from <= h.played_date <= d_to):
            continue
        if not any(p.name == hero for p in h.players):
            continue
        seen[stakes_label(h)] = h.big_blind or 0
    return [label for label, _ in sorted(seen.items(), key=lambda kv: kv[1])]
