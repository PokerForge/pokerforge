"""Reconstructs a full Hand object from the database's raw tables
(hands/hand_players/actions) for the hand replayer — the only place that
still needs every field of a hand (hole cards, full action log, board),
not just the precomputed stat columns hand_player_stats holds."""
import json
from datetime import datetime

from models.hand import Hand, Player, Action

_HANDS_COLS = [
    'hand_id', 'source', 'game_type', 'currency', 'small_blind', 'big_blind',
    'native_currency', 'native_small_blind', 'native_big_blind',
    'played_at', 'table_name', 'table_size', 'button_seat', 'total_pot', 'rake',
    'board', 'raw_text',
]


def load_hand(db, hand_id: str) -> Hand | None:
    row = db.conn.execute(
        f"SELECT {', '.join(_HANDS_COLS)} FROM hands WHERE hand_id = ?", [hand_id]).fetchone()
    if row is None:
        return None
    data = dict(zip(_HANDS_COLS, row))

    players = [
        Player(name=name, seat=seat, stack=stack, hole_cards=json.loads(hole_cards) if hole_cards else [])
        for name, seat, stack, hole_cards in db.conn.execute(
            "SELECT player_name, seat, stack, hole_cards FROM hand_players WHERE hand_id = ?", [hand_id])
    ]
    winnings = dict(db.conn.execute(
        "SELECT player_name, winnings FROM hand_players WHERE hand_id = ?", [hand_id]))
    actions = [
        Action(street=street, player=player, action=action, amount=amount)
        for street, player, action, amount in db.conn.execute(
            "SELECT street, player_name, action, amount FROM actions WHERE hand_id = ? ORDER BY sequence_no",
            [hand_id])
    ]

    return Hand(
        hand_id=data['hand_id'], source=data['source'], game_type=data['game_type'],
        currency=data['currency'], small_blind=data['small_blind'], big_blind=data['big_blind'],
        native_currency=data['native_currency'], native_small_blind=data['native_small_blind'],
        native_big_blind=data['native_big_blind'],
        played_at=datetime.fromisoformat(data['played_at']) if data['played_at'] else None,
        table_name=data['table_name'], table_size=data['table_size'], button_seat=data['button_seat'],
        players=players, board=json.loads(data['board']) if data['board'] else [],
        actions=actions, total_pot=data['total_pot'], rake=data['rake'], winnings=winnings,
        raw_text=data['raw_text'],
    )


def load_hands_bulk(db, hand_ids: list[str]) -> dict[str, Hand]:
    """Full Hand objects (players/actions/board included) for a batch of
    hand_ids in three queries total instead of one load_hand() call per
    hand — for a rich hand-list view that needs every field to compute its
    derived columns, not just the ones a single-hand replay needs.
    Batched at 500 to stay under SQLite's bound-parameter limit, same as
    load_actions_and_winnings."""
    result: dict[str, Hand] = {}
    if not hand_ids:
        return result
    batch_size = 500
    for i in range(0, len(hand_ids), batch_size):
        batch = hand_ids[i:i + batch_size]
        placeholders = ','.join('?' for _ in batch)

        hands_data: dict[str, dict] = {}
        for row in db.conn.execute(
                f"SELECT {', '.join(_HANDS_COLS)} FROM hands WHERE hand_id IN ({placeholders})", batch):
            data = dict(zip(_HANDS_COLS, row))
            hands_data[data['hand_id']] = data

        players_by_hand: dict[str, list[Player]] = {hid: [] for hid in batch}
        winnings_by_hand: dict[str, dict[str, float]] = {hid: {} for hid in batch}
        for hand_id, name, seat, stack, hole_cards, winnings in db.conn.execute(
                f"SELECT hand_id, player_name, seat, stack, hole_cards, winnings FROM hand_players "
                f"WHERE hand_id IN ({placeholders})", batch):
            players_by_hand[hand_id].append(Player(
                name=name, seat=seat, stack=stack,
                hole_cards=json.loads(hole_cards) if hole_cards else []))
            winnings_by_hand[hand_id][name] = winnings

        actions_by_hand: dict[str, list[Action]] = {hid: [] for hid in batch}
        for hand_id, street, player, action, amount in db.conn.execute(
                f"SELECT hand_id, street, player_name, action, amount FROM actions "
                f"WHERE hand_id IN ({placeholders}) ORDER BY hand_id, sequence_no", batch):
            actions_by_hand[hand_id].append(Action(street=street, player=player, action=action, amount=amount))

        for hid in batch:
            data = hands_data.get(hid)
            if data is None:
                continue
            result[hid] = Hand(
                hand_id=data['hand_id'], source=data['source'], game_type=data['game_type'],
                currency=data['currency'], small_blind=data['small_blind'], big_blind=data['big_blind'],
                native_currency=data['native_currency'], native_small_blind=data['native_small_blind'],
                native_big_blind=data['native_big_blind'],
                played_at=datetime.fromisoformat(data['played_at']) if data['played_at'] else None,
                table_name=data['table_name'], table_size=data['table_size'], button_seat=data['button_seat'],
                players=players_by_hand[hid], board=json.loads(data['board']) if data['board'] else [],
                actions=actions_by_hand[hid], total_pot=data['total_pot'], rake=data['rake'],
                winnings=winnings_by_hand[hid], raw_text=data['raw_text'],
            )
    return result


def load_actions_and_winnings(db, hand_ids: list[str]) -> dict[str, tuple[list[Action], dict[str, float]]]:
    """Bulk-loads just the actions + winnings for a batch of hand_ids — the
    minimal data core.settlement's pairwise pot settlement needs, skipping
    the players/board/raw_text/etc a full load_hand() would also fetch.
    Batched to stay under SQLite's bound-parameter limit for a
    high-volume villain or a large tag group."""
    result: dict[str, tuple[list[Action], dict[str, float]]] = {}
    if not hand_ids:
        return result
    batch_size = 500
    for i in range(0, len(hand_ids), batch_size):
        batch = hand_ids[i:i + batch_size]
        placeholders = ','.join('?' for _ in batch)
        actions_by_hand: dict[str, list[Action]] = {hid: [] for hid in batch}
        for hand_id, street, player, action, amount in db.conn.execute(
                f"SELECT hand_id, street, player_name, action, amount FROM actions "
                f"WHERE hand_id IN ({placeholders}) ORDER BY hand_id, sequence_no", batch):
            actions_by_hand[hand_id].append(Action(street=street, player=player, action=action, amount=amount))
        winnings_by_hand: dict[str, dict[str, float]] = {hid: {} for hid in batch}
        for hand_id, name, winnings in db.conn.execute(
                f"SELECT hand_id, player_name, winnings FROM hand_players WHERE hand_id IN ({placeholders})",
                batch):
            winnings_by_hand[hand_id][name] = winnings
        for hid in batch:
            result[hid] = (actions_by_hand[hid], winnings_by_hand[hid])
    return result
