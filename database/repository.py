from __future__ import annotations

import functools
import json
import multiprocessing as mp
import os
import sqlite3
from datetime import date
from pathlib import Path

from models.hand import Hand
from database.hand_stats_builder import build_player_stat_rows

_STATS_COLS = [
    'hand_id', 'player_name', 'played_at', 'big_blind', 'profit', 'ev', 'position', 'stakes_label',
    'vpip_pfr_opp', 'vpip', 'pfr', 'three_bet_opp', 'three_bet', 'faced_3bet_opp', 'folded_to_3bet',
    'four_bet_opp', 'four_bet', 'faced_4bet_opp', 'folded_to_4bet',
    'squeeze_opp', 'squeeze', 'squeeze_def_opp', 'raised_vs_squeeze', 'folded_to_squeeze',
    'folded_vs_open', 'saw_flop', 'reached_showdown', 'won_hand',
    'steal_opp', 'steal_att', 'steal_success', 'blind_def_opp', 'folded_to_steal',
]
for _street in ('flop', 'turn', 'river'):
    for _field in ('reached', 'cbet_opp', 'cbet', 'faced_cbet_opp', 'folded_to_cbet',
                   'xr_opp', 'xr', 'faced_xr_opp', 'folded_to_xr',
                   'donk_opp', 'donk', 'faced_donk_opp', 'folded_to_donk',
                   'face_bet_opp', 'folded_to_bet', 'face_2bet_opp', 'folded_to_2bet',
                   'face_3bet_opp', 'folded_to_3bet',
                   'float_opp', 'float_bet', 'faced_float_opp', 'folded_to_float'):
        _STATS_COLS.append(f'{_street}_{_field}')
_STATS_COLS += [
    'probe_turn_opp', 'probe_turn', 'faced_probe_turn_opp', 'folded_to_probe_turn',
    'probe_river_opp', 'probe_river', 'faced_probe_river_opp', 'folded_to_probe_river',
]
for _street in ('preflop', 'flop', 'turn', 'river'):
    _STATS_COLS += [f'{_street}_bet_raise', f'{_street}_call', f'{_street}_fold']


def _build_hand_data(hand: Hand, ev_iterations: int):
    """Picklable, module-level worker for multiprocessing — the per-hand
    stat computation is fully independent hand-to-hand (no shared state),
    which makes it a good fit for parallelizing across CPU cores, unlike
    the earlier UI-thread work that hit the GIL: this is separate
    processes doing separate CPU-bound work, not competing for one
    interpreter's bytecode execution. Returns the plain-tuple rows for
    the four tables so the main process can batch-write them — SQLite
    itself isn't used here, since concurrent writers from multiple
    processes would just contend with each other."""
    hands_row = (
        hand.hand_id, hand.source, hand.game_type, hand.currency,
        hand.small_blind, hand.big_blind,
        hand.native_currency, hand.native_small_blind, hand.native_big_blind,
        hand.played_at.isoformat() if hand.played_at else None,
        hand.table_name, hand.table_size, hand.button_seat,
        hand.total_pot, hand.rake, json.dumps(hand.board), hand.raw_text,
    )
    players_rows = [(hand.hand_id, p.name, p.seat, p.stack, json.dumps(p.hole_cards),
                      hand.winnings.get(p.name, 0.0)) for p in hand.players]
    actions_rows = [(hand.hand_id, a.street, a.player, a.action, a.amount, seq)
                     for seq, a in enumerate(hand.actions)]
    stats_rows = [[row.get(c) for c in _STATS_COLS]
                  for row in build_player_stat_rows(hand, ev_iterations=ev_iterations)]
    return hands_row, players_rows, actions_rows, stats_rows


class PokerDatabase:
    """SQLite repository backing SF Poker's stats — hand_player_stats holds
    every stat flag precomputed once at import time, so every UI query is a
    fast indexed aggregate query rather than a Python re-walk of raw hand
    actions (see database/hand_stats_builder.py for how rows are built)."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False: queries run from AsyncRunner's background
        # QThread, but only ever read after the one-time synchronous import
        # completes on the main thread — no concurrent writer to race with.
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.execute("PRAGMA foreign_keys = ON")
        self._init_schema()

    def _init_schema(self) -> None:
        schema = Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")
        self.conn.executescript(schema)
        self._migrate_schema()
        self.conn.commit()

    def _migrate_schema(self) -> None:
        """CREATE TABLE IF NOT EXISTS in schema.sql doesn't add new columns to
        an already-existing table, so new hand_player_stats columns need an
        explicit ALTER TABLE for databases created before they existed."""
        cols = {row[1] for row in self.conn.execute("PRAGMA table_info(hand_player_stats)")}
        if 'vpip_pfr_opp' not in cols:
            self.conn.execute(
                "ALTER TABLE hand_player_stats ADD COLUMN vpip_pfr_opp INTEGER DEFAULT 1"
            )

    def close(self) -> None:
        self.conn.close()

    def existing_hand_ids(self) -> set[str]:
        return {row[0] for row in self.conn.execute("SELECT hand_id FROM hands")}

    def hand_count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM hands").fetchone()[0]

    def get_file_fingerprints(self) -> dict[str, tuple[float, int]]:
        """{file_path: (mtime, size)} for every file already fully
        imported — one query instead of one per file."""
        return {path: (mtime, size) for path, mtime, size in
                self.conn.execute("SELECT file_path, mtime, size FROM imported_files")}

    def mark_files_imported(self, fingerprints: list[tuple[str, float, int]]) -> None:
        self.conn.executemany(
            "INSERT OR REPLACE INTO imported_files (file_path, mtime, size) VALUES (?, ?, ?)",
            fingerprints)
        self.conn.commit()

    _HANDS_SQL = """INSERT OR IGNORE INTO hands
        (hand_id, source, game_type, currency, small_blind, big_blind,
         native_currency, native_small_blind, native_big_blind,
         played_at, table_name, table_size, button_seat, total_pot, rake,
         board, raw_text)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""
    _PLAYERS_SQL = """INSERT OR IGNORE INTO hand_players
        (hand_id, player_name, seat, stack, hole_cards, winnings)
        VALUES (?, ?, ?, ?, ?, ?)"""
    _ACTIONS_SQL = """INSERT INTO actions
        (hand_id, street, player_name, action, amount, sequence_no)
        VALUES (?, ?, ?, ?, ?, ?)"""

    def import_hands(self, hands: list[Hand], ev_iterations: int = 3000,
                      on_progress=None, batch_size: int = 500, workers: int | None = None) -> int:
        """Imports any hands not already present. `on_progress(done, total)`
        is called periodically if given.

        The per-hand stat computation (database/hand_stats_builder.py) is
        independent hand-to-hand, so it's spread across a multiprocessing
        Pool — each worker process computes plain-tuple rows for a hand and
        sends them back; only the main process ever touches SQLite, since
        concurrent writers from multiple processes would just contend with
        each other rather than helping. Writes are batched with
        executemany() rather than one execute() per row — individually
        inserting a hand's ~1 hands-row + up to 9 hand_players-rows + ~20-30
        actions-rows + up to 9 hand_player_stats-rows (30-50 separate
        statements per hand) added far more overhead than the actual stat
        computation itself."""
        existing = self.existing_hand_ids()
        todo = [h for h in hands if h.hand_id not in existing]
        cur = self.conn.cursor()
        placeholders = ', '.join('?' for _ in _STATS_COLS)
        col_list = ', '.join(_STATS_COLS)
        insert_stats_sql = f"INSERT OR REPLACE INTO hand_player_stats ({col_list}) VALUES ({placeholders})"

        hands_rows, players_rows, actions_rows, stats_rows = [], [], [], []

        def flush():
            if hands_rows:
                cur.executemany(self._HANDS_SQL, hands_rows)
            if players_rows:
                cur.executemany(self._PLAYERS_SQL, players_rows)
            if actions_rows:
                cur.executemany(self._ACTIONS_SQL, actions_rows)
            if stats_rows:
                cur.executemany(insert_stats_sql, stats_rows)
            self.conn.commit()
            hands_rows.clear(); players_rows.clear(); actions_rows.clear(); stats_rows.clear()

        if not todo:
            if on_progress:
                on_progress(0, 0)
            return 0

        workers = workers or max(1, (os.cpu_count() or 2) - 1)
        worker_fn = functools.partial(_build_hand_data, ev_iterations=ev_iterations)
        done = 0
        with mp.Pool(processes=workers) as pool:
            for hr, prs, ars, srs in pool.imap_unordered(worker_fn, todo, chunksize=25):
                hands_rows.append(hr)
                players_rows.extend(prs)
                actions_rows.extend(ars)
                stats_rows.extend(srs)
                done += 1
                if done % batch_size == 0:
                    flush()
                    if on_progress:
                        on_progress(done, len(todo))
        flush()
        if on_progress:
            on_progress(len(todo), len(todo))
        return len(todo)

    def _load_all_hands(self) -> list[Hand]:
        """Reconstructs every Hand already stored, from the raw tables —
        bulk-fetched and grouped in three queries rather than one query
        per hand, so this stays fast even at 279k+ hands. Used to rebuild
        hand_player_stats from a corrected formula without re-parsing the
        original hand-history text files."""
        from datetime import datetime
        from models.hand import Player, Action

        players_by_hand: dict[str, list[Player]] = {}
        winnings_by_hand: dict[str, dict[str, float]] = {}
        for hand_id, name, seat, stack, hole_cards, winnings in self.conn.execute(
                "SELECT hand_id, player_name, seat, stack, hole_cards, winnings FROM hand_players"):
            players_by_hand.setdefault(hand_id, []).append(
                Player(name=name, seat=seat, stack=stack,
                       hole_cards=json.loads(hole_cards) if hole_cards else []))
            winnings_by_hand.setdefault(hand_id, {})[name] = winnings

        actions_by_hand: dict[str, list[Action]] = {}
        for hand_id, street, player, action, amount in self.conn.execute(
                "SELECT hand_id, street, player_name, action, amount FROM actions ORDER BY hand_id, sequence_no"):
            actions_by_hand.setdefault(hand_id, []).append(
                Action(street=street, player=player, action=action, amount=amount))

        hands = []
        for row in self.conn.execute(
                "SELECT hand_id, source, game_type, currency, small_blind, big_blind, "
                "native_currency, native_small_blind, native_big_blind, played_at, "
                "table_name, table_size, button_seat, total_pot, rake, board, raw_text FROM hands"):
            (hand_id, source, game_type, currency, small_blind, big_blind,
             native_currency, native_small_blind, native_big_blind, played_at,
             table_name, table_size, button_seat, total_pot, rake, board, raw_text) = row
            hands.append(Hand(
                hand_id=hand_id, source=source, game_type=game_type, currency=currency,
                small_blind=small_blind, big_blind=big_blind,
                native_currency=native_currency, native_small_blind=native_small_blind,
                native_big_blind=native_big_blind,
                played_at=datetime.fromisoformat(played_at) if played_at else None,
                table_name=table_name, table_size=table_size, button_seat=button_seat,
                players=players_by_hand.get(hand_id, []), board=json.loads(board) if board else [],
                actions=actions_by_hand.get(hand_id, []), total_pot=total_pot, rake=rake,
                winnings=winnings_by_hand.get(hand_id, {}), raw_text=raw_text,
            ))
        return hands

    def rebuild_hand_player_stats(self, ev_iterations: int = 500, on_progress=None,
                                    batch_size: int = 500, workers: int | None = None) -> int:
        """Recomputes hand_player_stats for every hand already stored, from
        the raw hands/hand_players/actions tables — for when a stat
        formula in core/stats.py (or elsewhere in the analyzer chain)
        changes and existing precomputed rows need to be refreshed,
        without re-parsing the original hand-history files (which haven't
        changed) or re-detecting hero/currency (also unchanged)."""
        hands = self._load_all_hands()
        cur = self.conn.cursor()
        placeholders = ', '.join('?' for _ in _STATS_COLS)
        col_list = ', '.join(_STATS_COLS)
        insert_stats_sql = f"INSERT OR REPLACE INTO hand_player_stats ({col_list}) VALUES ({placeholders})"

        cur.execute("DELETE FROM hand_player_stats")
        self.conn.commit()

        stats_rows = []

        def flush():
            if stats_rows:
                cur.executemany(insert_stats_sql, stats_rows)
            self.conn.commit()
            stats_rows.clear()

        workers = workers or max(1, (os.cpu_count() or 2) - 1)
        worker_fn = functools.partial(_build_hand_data, ev_iterations=ev_iterations)
        done = 0
        with mp.Pool(processes=workers) as pool:
            for _hr, _prs, _ars, srs in pool.imap_unordered(worker_fn, hands, chunksize=25):
                stats_rows.extend(srs)
                done += 1
                if done % batch_size == 0:
                    flush()
                    if on_progress:
                        on_progress(done, len(hands))
        flush()
        if on_progress:
            on_progress(len(hands), len(hands))
        return len(hands)
