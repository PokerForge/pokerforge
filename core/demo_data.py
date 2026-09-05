"""Generates synthetic hand histories for evaluation/demo purposes — lets
SF Poker be tried, screenshotted, or demoed without needing anyone's real
poker data. Hands are built as Hand objects directly (not run through a
hand-history-file parser, since there's no real file to parse), then
imported through the same PokerDatabase.import_hands() pipeline real
hands go through — so the stat engine, once it sees them, can't tell the
difference.

Poker logic here is deliberately simplified (folds/calls/raises are
randomly weighted, showdown winners are picked at random rather than by
real hand strength) — this is for a plausible-looking, varied evaluation
dataset, not a statistically faithful poker simulation. What it must get
right is structural validity: every action sequence has to be something
core/stats.py's analyze_preflop/analyze_showdown/compute_invested can
process the same way they process a real parsed hand."""
import random
from datetime import datetime, timedelta

from models.hand import Hand, Player, Action

DEMO_HERO = "DemoHero"
_VILLAIN_NAMES = [
    "TightTom", "LooseLucy", "ManiacMike", "NitNancy", "RegularRay",
    "FishFrank", "SharkSam", "CallingCarl", "AggroAmy", "PassivePat",
]
_SEATS = [1, 3, 5, 6, 8, 10]
_STAKES = [(0.05, 0.10), (0.10, 0.20), (0.25, 0.50)]


def _simulate_street(rng, order, folded, current_bet, committed, street, actions,
                      open_prob, cap_raises=3):
    """One betting round. `order` is the acting order for this street;
    `folded` is mutated in place. Returns True if 2+ players are still in
    after this street (hand continues), False if only one remains."""
    raises = 0
    acted_since_last_raise = set()
    bet_open = False
    while True:
        progressed = False
        for name in order:
            if name in folded:
                continue
            live = [n for n in order if n not in folded]
            if len(live) < 2:
                return False
            if name in acted_since_last_raise:
                continue
            progressed = True
            acted_since_last_raise.add(name)

            if not bet_open:
                if rng.random() < open_prob:
                    amt = round(current_bet * rng.choice([2.0, 2.2, 2.5]), 2) if current_bet else round(rng.uniform(0.5, 1.0), 2)
                    committed[name] = committed.get(name, 0.0) + amt
                    current_bet = committed[name]
                    actions.append(Action(street, name, "Bet" if street != "PREFLOP" else "Raise", amt))
                    bet_open = True
                    acted_since_last_raise = {name}
                else:
                    actions.append(Action(street, name, "Check" if street != "PREFLOP" else "Fold", None))
                    if street == "PREFLOP":
                        folded.add(name)
            else:
                roll = rng.random()
                to_call = current_bet - committed.get(name, 0.0)
                if roll < 0.55:
                    folded.add(name)
                    actions.append(Action(street, name, "Fold", None))
                elif roll < 0.9 or raises >= cap_raises:
                    committed[name] = committed.get(name, 0.0) + to_call
                    actions.append(Action(street, name, "Call", round(to_call, 2)))
                else:
                    new_total = round(current_bet * 2.0, 2)
                    committed[name] = new_total
                    actions.append(Action(street, name, "Raise", new_total))
                    current_bet = new_total
                    raises += 1
                    acted_since_last_raise = {name}
        if not progressed:
            break
    return len([n for n in order if n not in folded]) >= 2


def _generate_one_hand(rng, index, played_at) -> Hand:
    sb, bb = rng.choice(_STAKES)
    names = [DEMO_HERO] + rng.sample(_VILLAIN_NAMES, 5)
    rng.shuffle(names)
    players = [Player(name=n, seat=s, stack=round(rng.uniform(80, 150), 2)) for n, s in zip(names, _SEATS)]
    button_seat = rng.choice(_SEATS)

    btn_idx = _SEATS.index(button_seat)
    order = _SEATS[btn_idx:] + _SEATS[:btn_idx]
    seat_to_name = {p.seat: p.name for p in players}
    sb_seat, bb_seat = order[1], order[2]
    preflop_order = order[3:] + order[:3]  # UTG-equivalent first, blinds last

    actions = []
    committed = {}
    folded = set()

    committed[seat_to_name[sb_seat]] = sb
    actions.append(Action("PREFLOP", seat_to_name[sb_seat], "Post SB", sb))
    committed[seat_to_name[bb_seat]] = bb
    actions.append(Action("PREFLOP", seat_to_name[bb_seat], "Post BB", bb))

    order_names = [seat_to_name[s] for s in preflop_order]
    continues = _simulate_street(rng, order_names, folded, bb, committed, "PREFLOP",
                                  actions, open_prob=0.35)

    board = []
    if continues:
        deck_ranks = "23456789TJQKA"
        deck_suits = "♠♥♦♣"
        board = [rng.choice(deck_ranks) + rng.choice(deck_suits) for _ in range(3)]
        live_order = [n for n in order_names if n not in folded]
        continues = _simulate_street(rng, live_order, folded, 0.0, committed, "FLOP",
                                      actions, open_prob=0.5)
        if continues:
            board.append(rng.choice(deck_ranks) + rng.choice(deck_suits))
            live_order = [n for n in live_order if n not in folded]
            continues = _simulate_street(rng, live_order, folded, 0.0, committed, "TURN",
                                          actions, open_prob=0.5)
            if continues:
                board.append(rng.choice(deck_ranks) + rng.choice(deck_suits))
                live_order = [n for n in live_order if n not in folded]
                _simulate_street(rng, live_order, folded, 0.0, committed, "RIVER",
                                  actions, open_prob=0.5)

    survivors = [n for n in [p.name for p in players] if n not in folded]
    winner = rng.choice(survivors) if survivors else seat_to_name[bb_seat]
    total_pot = round(sum(committed.values()), 2)
    rake = round(min(total_pot * 0.05, 3.0), 2)
    winnings = {winner: round(total_pot - rake, 2)}

    return Hand(
        hand_id=f"demo-{index}", game_type="Texas Hold'em", currency="£",
        small_blind=sb, big_blind=bb, played_at=played_at,
        table_name="Demo Table", table_size=6, button_seat=button_seat,
        players=players, board=board, actions=actions,
        total_pot=total_pot, rake=rake, winnings=winnings, source="demo",
    )


def generate_demo_hands(n: int = 3000, seed: int = 42) -> list[Hand]:
    rng = random.Random(seed)
    start = datetime(2026, 1, 1, 18, 0)
    hands = []
    played_at = start
    for i in range(n):
        played_at += timedelta(minutes=rng.randint(2, 6))
        if rng.random() < 0.05:  # occasional gap between sessions
            played_at += timedelta(days=rng.randint(1, 4))
        hands.append(_generate_one_hand(rng, i, played_at))
    return hands
