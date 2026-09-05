"""One-time backfill: recompute hand_player_stats.position for every
existing row using the corrected core.position.assign_positions() (the
4-handed UTG->CO fix) — position is precomputed at import time, so fixing
the source function alone only affects hands imported from now on."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.paths import app_data_dir
from database.repository import PokerDatabase
from core.position import assign_positions
from models.hand import Hand, Player

DB_PATH = app_data_dir() / "sf_poker.db"


def main():
    db = PokerDatabase(DB_PATH)
    conn = db.conn

    button_by_hand = dict(conn.execute("SELECT hand_id, button_seat FROM hands"))
    print(f"Loaded {len(button_by_hand):,} hands' button seats", flush=True)

    players_by_hand: dict[str, list[tuple[str, int]]] = {}
    for hand_id, name, seat in conn.execute("SELECT hand_id, player_name, seat FROM hand_players"):
        players_by_hand.setdefault(hand_id, []).append((name, seat))
    print(f"Loaded seats for {len(players_by_hand):,} hands", flush=True)

    current_positions = dict(
        ((hand_id, player_name), position)
        for hand_id, player_name, position in conn.execute(
            "SELECT hand_id, player_name, position FROM hand_player_stats"))
    print(f"Loaded {len(current_positions):,} current position rows", flush=True)

    updates = []
    for hand_id, button_seat in button_by_hand.items():
        players = players_by_hand.get(hand_id)
        if not players or button_seat is None:
            continue
        fake_hand = Hand(
            hand_id=hand_id, button_seat=button_seat,
            players=[Player(name=n, seat=s) for n, s in players],
        )
        new_positions = assign_positions(fake_hand)
        for player_name, new_pos in new_positions.items():
            old_pos = current_positions.get((hand_id, player_name))
            if old_pos != new_pos:
                updates.append((new_pos, hand_id, player_name))

    print(f"{len(updates):,} rows need a position update", flush=True)
    if updates:
        conn.executemany(
            "UPDATE hand_player_stats SET position = ? WHERE hand_id = ? AND player_name = ?",
            updates)
        conn.commit()
        print("Committed.", flush=True)


if __name__ == "__main__":
    main()
