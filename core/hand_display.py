"""Derives the hand-history-grid columns (Facing PF Action, PF Act,
per-street Act letters, Final Hand, Winner, Winning Hand) from a parsed
Hand object.

Every rule here was verified hand-by-hand against this app's own action
log for the same hand_ids — not guessed. See the per-function notes for
the specific edge cases each one settles. `_is_raise_like` is imported
from core.stats rather than reimplemented, so an Allin is classified as a
raise/call identically to every other stat that already depends on it.
"""
from core.stats import _is_raise_like, analyze_showdown
from core.equity import best_hand_rank
from core.currency import FX_TO_USD
from models.hand import Hand

_RANK_NAME = {
    2: 'Two', 3: 'Three', 4: 'Four', 5: 'Five', 6: 'Six', 7: 'Seven', 8: 'Eight',
    9: 'Nine', 10: 'Ten', 11: 'Jack', 12: 'Queen', 13: 'King', 14: 'Ace',
}
_CATEGORY_NAME = {
    0: 'High Card', 1: 'One Pair', 2: 'Two Pair', 3: 'Three of a Kind',
    4: 'Straight', 5: 'Flush', 6: 'Full House', 7: 'Four of a Kind', 8: 'Straight Flush',
}

SITE_LABELS = {
    'ipoker': 'iPoker Network', 'grosvenor_xml': 'Grosvenor Poker',
    'pokerstars': 'PokerStars', 'ggpoker': 'GGPoker', 'winning_network': 'Winning Network',
}


def describe_hand_rank(cards: list[str]) -> str:
    """"One Pair, Nines" / "Two Pair, Aces and Tens" / "Straight, Jack
    High" / etc, from best_hand_rank's (category, *tiebreakers) tuple.
    Every branch except Full House/Four of a Kind/Straight Flush was
    verified against real hands; those three appeared in no sample hand
    and follow the same, obvious naming pattern."""
    rank = best_hand_rank(cards)
    cat = rank[0]
    name = _CATEGORY_NAME[cat]
    if cat == 1:
        return f"{name}, {_RANK_NAME[rank[1]]}s"
    if cat == 2:
        return f"{name}, {_RANK_NAME[rank[1]]}s and {_RANK_NAME[rank[2]]}s"
    if cat in (3, 7):
        return f"{name}, {_RANK_NAME[rank[1]]}s"
    if cat == 6:
        return f"{name}, {_RANK_NAME[rank[1]]}s full of {_RANK_NAME[rank[2]]}s"
    if cat in (4, 8):
        return f"{name}, {_RANK_NAME[rank[1]]} High"
    return f"{name}, {_RANK_NAME[rank[1]]} High"  # flush or high card


def final_hand_text(hand: Hand, player_name: str) -> str:
    """"(folded preflop)" / "(did not show hand)" / a real hand
    description. Two rules that are easy to get wrong: folding always
    wins regardless of showdown status, and even a hand WON without a
    real contest (everyone else folded) still reads "(did not show
    hand)", not the hero's actual holding."""
    fold_street = next((a.street for a in hand.actions
                         if a.player == player_name and a.action == 'Fold'), None)
    if fold_street:
        return f"(folded {fold_street.lower()})"
    flags = analyze_showdown(hand).get(player_name)
    if flags and flags.reached_showdown:
        player = next((p for p in hand.players if p.name == player_name), None)
        if player and len(player.hole_cards) == 2 and len(hand.board) >= 3:
            return describe_hand_rank(player.hole_cards + hand.board)
    return "(did not show hand)"


def winner_and_hand_text(hand: Hand) -> tuple[str, str]:
    """(winner_name_or_"[Split Pot]", winning_hand_text) — same
    "(did not show hand)" rule as final_hand_text, applied to whichever
    winner actually reached a real showdown with known hole cards."""
    winners = [name for name, amt in hand.winnings.items() if amt and amt > 1e-9]
    if not winners:
        return "", ""
    winner_str = winners[0] if len(winners) == 1 else "[Split Pot]"
    flags_map = analyze_showdown(hand)
    for w in winners:
        flags = flags_map.get(w)
        player = next((p for p in hand.players if p.name == w), None)
        if (flags and flags.reached_showdown and player
                and len(player.hole_cards) == 2 and len(hand.board) >= 3):
            return winner_str, describe_hand_rank(player.hole_cards + hand.board)
    return winner_str, "(did not show hand)"


_PF_LETTER = {'Fold': 'F', 'Call': 'C', 'Check': 'X', 'Raise': 'R'}


def facing_and_pf_act(hand: Hand, player_name: str) -> tuple[str, str]:
    """(Facing PF Action, PF Act) — validated hand-by-hand against real
    hands: "Unopened Pot" (no calls/raises reached this seat yet),
    "1 Limper"/"2+ Limpers" (that many callers, no raise yet), "1 Raiser"
    (facing exactly one raise), "1 Raise & Caller(s)" (that raise has
    already been called by someone else too), "{N}Bet Cold" for 2+ raises
    before this player has voluntarily acted (a real 3Bet Cold and, by the
    same generalization, 4Bet Cold+ — not present in the validation
    sample but the obvious extension of the confirmed pattern), and
    "All players fold" when the player never gets a decision at all (a
    walked big blind) — PF Act is then "". PF Act itself is the player's
    own action letters in order (e.g. "RF" = raised, then folded to a
    re-raise), letting a squeeze/4bet-and-fold read correctly without
    being a special case.
    """
    committed: dict[str, float] = {}
    current_bet = 0.0
    raise_count = 0
    limper_count = 0
    caller_since_raise = False
    player_acted = False
    facing_label = None
    pf_act_chars: list[str] = []

    for a in hand.actions:
        if a.street != 'PREFLOP':
            continue
        if a.player == player_name:
            if a.action in ('Post SB', 'Post BB'):
                committed[a.player] = committed.get(a.player, 0.0) + (a.amount or 0.0)
                current_bet = max(current_bet, committed[a.player])
                continue
            if not player_acted:
                if raise_count == 0:
                    if limper_count == 0:
                        facing_label = "Unopened Pot"
                    elif limper_count == 1:
                        facing_label = "1 Limper"
                    else:
                        facing_label = "2+ Limpers"
                elif raise_count == 1:
                    facing_label = "1 Raise & Caller(s)" if caller_since_raise else "1 Raiser"
                else:
                    # raise_count 2 (open + one re-raise) is a 3-bet in
                    # standard terminology — confirmed against the export
                    # ("3Bet Cold" for exactly this case); N raises before
                    # this seat is an (N+1)-bet by the same counting.
                    facing_label = f"{raise_count + 1}Bet Cold"
                player_acted = True

            current_bet_before = current_bet
            if a.action == 'Raise':
                committed[a.player] = a.amount if a.amount is not None else committed.get(a.player, 0.0)
            elif a.action != 'Fold':
                committed[a.player] = committed.get(a.player, 0.0) + (a.amount or 0.0)
            if a.action == 'Allin':
                pf_act_chars.append('R' if _is_raise_like('Allin', committed[a.player], current_bet_before) else 'C')
            else:
                pf_act_chars.append(_PF_LETTER.get(a.action, ''))
            if _is_raise_like(a.action, committed.get(a.player, 0.0), current_bet_before):
                raise_count += 1
                caller_since_raise = False
                current_bet = max(current_bet, committed[a.player])
            elif a.action == 'Call':
                if raise_count == 0:
                    limper_count += 1
                else:
                    caller_since_raise = True
            continue

        # Someone else's action — only affects the counts leading up to
        # this player's own decision point(s).
        if a.action in ('Fold', 'Check'):
            continue
        current_bet_before = current_bet
        if a.action == 'Raise':
            committed[a.player] = a.amount if a.amount is not None else committed.get(a.player, 0.0)
        else:  # Post SB/BB, Call, Allin
            committed[a.player] = committed.get(a.player, 0.0) + (a.amount or 0.0)
        if a.action in ('Post SB', 'Post BB'):
            current_bet = max(current_bet, committed[a.player])
            continue
        if _is_raise_like(a.action, committed[a.player], current_bet_before):
            raise_count += 1
            caller_since_raise = False
        elif a.action == 'Call':
            if raise_count == 0:
                limper_count += 1
            else:
                caller_since_raise = True
        current_bet = max(current_bet, committed[a.player])

    if not player_acted:
        return "All players fold", ""
    return facing_label, ''.join(pf_act_chars)


def postflop_act(hand: Hand, player_name: str, street: str) -> str:
    """Hero's action-letter sequence for one postflop street (FLOP/TURN/
    RIVER) — "" if that street was never dealt, a single letter
    (X/B/C/F/R) if the player's one action closed it, or two letters when
    they check first and must respond again after a later bet on the same
    street (e.g. "XF", "XC" — both confirmed in the validation export)."""
    if not any(a.street == street for a in hand.actions):
        return ""
    committed: dict[str, float] = {}
    current_bet = 0.0
    letters: list[str] = []
    for a in hand.actions:
        if a.street != street:
            continue
        if a.player != player_name:
            if a.action in ('Fold', 'Check'):
                continue
            if a.action == 'Raise':
                committed[a.player] = a.amount if a.amount is not None else committed.get(a.player, 0.0)
            else:
                committed[a.player] = committed.get(a.player, 0.0) + (a.amount or 0.0)
            current_bet = max(current_bet, committed[a.player])
            continue

        current_bet_before = current_bet
        if a.action == 'Check':
            letters.append('X')
            continue
        if a.action == 'Fold':
            letters.append('F')
            continue
        if a.action == 'Raise':
            committed[a.player] = a.amount if a.amount is not None else committed.get(a.player, 0.0)
            letters.append('R')
        elif a.action == 'Allin':
            new_total = committed.get(a.player, 0.0) + (a.amount or 0.0)
            letters.append('R' if _is_raise_like('Allin', new_total, current_bet_before) else 'C')
            committed[a.player] = new_total
        else:  # Bet, Call
            committed[a.player] = committed.get(a.player, 0.0) + (a.amount or 0.0)
            letters.append('B' if a.action == 'Bet' else 'C')
        current_bet = max(current_bet, committed[a.player])
    return ''.join(letters)


def to_native(usd_amount: float, native_currency: str | None) -> float:
    """Reverses core.currency.convert_hands_to_usd's fixed-rate multiply —
    exact (not an approximation) since the same constant rate is used both
    ways and native_currency records which one was applied."""
    if usd_amount is None:
        return 0.0
    rate = FX_TO_USD.get(native_currency, 1.0)
    return usd_amount / rate if rate else usd_amount
