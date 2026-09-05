-- Raw hand data (kept for the hand replayer and for re-deriving anything
-- not yet promoted into hand_player_stats below).
CREATE TABLE IF NOT EXISTS hands (
    hand_id TEXT PRIMARY KEY,
    source TEXT,
    game_type TEXT NOT NULL,
    currency TEXT,
    small_blind REAL,
    big_blind REAL,
    native_currency TEXT,
    native_small_blind REAL,
    native_big_blind REAL,
    played_at TEXT,
    table_name TEXT,
    table_size INTEGER,
    button_seat INTEGER,
    total_pot REAL,
    rake REAL,
    board TEXT,
    raw_text TEXT,
    imported_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS hand_players (
    hand_id TEXT NOT NULL,
    player_name TEXT NOT NULL,
    seat INTEGER,
    stack REAL,
    hole_cards TEXT,
    winnings REAL NOT NULL DEFAULT 0,
    invested REAL NOT NULL DEFAULT 0,
    PRIMARY KEY (hand_id, player_name),
    FOREIGN KEY (hand_id) REFERENCES hands(hand_id)
);

CREATE TABLE IF NOT EXISTS actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    hand_id TEXT NOT NULL,
    street TEXT NOT NULL,
    player_name TEXT NOT NULL,
    action TEXT NOT NULL,
    amount REAL,
    sequence_no INTEGER NOT NULL,
    FOREIGN KEY (hand_id) REFERENCES hands(hand_id)
);

-- One row per (hand, player) with every stat flag already computed by the
-- existing, validated analyzer functions (core/stats.py, stats_postflop.py,
-- stats_probe.py, stats_position.py) at import time. This is the whole
-- point of the database: a period change becomes "SELECT SUM(...) WHERE
-- player=? AND played_at BETWEEN ? AND ?" against indexed columns, instead
-- of re-walking every hand's raw actions from scratch on every query.
CREATE TABLE IF NOT EXISTS hand_player_stats (
    hand_id TEXT NOT NULL,
    player_name TEXT NOT NULL,
    played_at TEXT,
    big_blind REAL,
    profit REAL,
    ev REAL,             -- NULL unless this was a computable all-in spot
    position TEXT,
    stakes_label TEXT,   -- native-currency label, e.g. "£0.02/£0.04" — denormalized from hands so stake filtering needs no join

    -- Preflop (core.stats.PlayerHandFlags)
    -- vpip_pfr_opp: 0 only for a BB who "walked" (won uncontested with zero
    -- preflop actions of their own) — PT4 excludes those hands from VPIP/PFR's
    -- denominator entirely ("Number of Hands - Number of Walks"), since the
    -- player never had a decision to make.
    vpip_pfr_opp INTEGER DEFAULT 1,
    vpip INTEGER, pfr INTEGER,
    three_bet_opp INTEGER, three_bet INTEGER,
    faced_3bet_opp INTEGER, folded_to_3bet INTEGER,
    four_bet_opp INTEGER, four_bet INTEGER,
    faced_4bet_opp INTEGER, folded_to_4bet INTEGER,
    squeeze_opp INTEGER, squeeze INTEGER,
    squeeze_def_opp INTEGER, raised_vs_squeeze INTEGER, folded_to_squeeze INTEGER,
    folded_vs_open INTEGER,

    -- Showdown (core.stats.ShowdownFlags)
    saw_flop INTEGER, reached_showdown INTEGER, won_hand INTEGER,

    -- Steal (core.stats_position.StealFlags)
    steal_opp INTEGER, steal_att INTEGER, steal_success INTEGER,
    blind_def_opp INTEGER, folded_to_steal INTEGER,

    -- Postflop per street (core.stats_postflop.StreetFlags), flop/turn/river
    flop_reached INTEGER, flop_cbet_opp INTEGER, flop_cbet INTEGER,
    flop_faced_cbet_opp INTEGER, flop_folded_to_cbet INTEGER,
    flop_xr_opp INTEGER, flop_xr INTEGER, flop_faced_xr_opp INTEGER, flop_folded_to_xr INTEGER,
    flop_donk_opp INTEGER, flop_donk INTEGER, flop_faced_donk_opp INTEGER, flop_folded_to_donk INTEGER,
    flop_face_bet_opp INTEGER, flop_folded_to_bet INTEGER,
    flop_face_2bet_opp INTEGER, flop_folded_to_2bet INTEGER,
    flop_face_3bet_opp INTEGER, flop_folded_to_3bet INTEGER,
    flop_float_opp INTEGER, flop_float_bet INTEGER, flop_faced_float_opp INTEGER, flop_folded_to_float INTEGER,

    turn_reached INTEGER, turn_cbet_opp INTEGER, turn_cbet INTEGER,
    turn_faced_cbet_opp INTEGER, turn_folded_to_cbet INTEGER,
    turn_xr_opp INTEGER, turn_xr INTEGER, turn_faced_xr_opp INTEGER, turn_folded_to_xr INTEGER,
    turn_donk_opp INTEGER, turn_donk INTEGER, turn_faced_donk_opp INTEGER, turn_folded_to_donk INTEGER,
    turn_face_bet_opp INTEGER, turn_folded_to_bet INTEGER,
    turn_face_2bet_opp INTEGER, turn_folded_to_2bet INTEGER,
    turn_face_3bet_opp INTEGER, turn_folded_to_3bet INTEGER,
    turn_float_opp INTEGER, turn_float_bet INTEGER, turn_faced_float_opp INTEGER, turn_folded_to_float INTEGER,

    river_reached INTEGER, river_cbet_opp INTEGER, river_cbet INTEGER,
    river_faced_cbet_opp INTEGER, river_folded_to_cbet INTEGER,
    river_xr_opp INTEGER, river_xr INTEGER, river_faced_xr_opp INTEGER, river_folded_to_xr INTEGER,
    river_donk_opp INTEGER, river_donk INTEGER, river_faced_donk_opp INTEGER, river_folded_to_donk INTEGER,
    river_face_bet_opp INTEGER, river_folded_to_bet INTEGER,
    river_face_2bet_opp INTEGER, river_folded_to_2bet INTEGER,
    river_face_3bet_opp INTEGER, river_folded_to_3bet INTEGER,
    river_float_opp INTEGER, river_float_bet INTEGER, river_faced_float_opp INTEGER, river_folded_to_float INTEGER,

    -- Probe (core.stats_probe.ProbeFlags)
    probe_turn_opp INTEGER, probe_turn INTEGER, faced_probe_turn_opp INTEGER, folded_to_probe_turn INTEGER,
    probe_river_opp INTEGER, probe_river INTEGER, faced_probe_river_opp INTEGER, folded_to_probe_river INTEGER,

    -- Aggression counts (core.stats.AggressionCounts), per street + total
    preflop_bet_raise INTEGER, preflop_call INTEGER, preflop_fold INTEGER,
    flop_bet_raise INTEGER, flop_call INTEGER, flop_fold INTEGER,
    turn_bet_raise INTEGER, turn_call INTEGER, turn_fold INTEGER,
    river_bet_raise INTEGER, river_call INTEGER, river_fold INTEGER,

    PRIMARY KEY (hand_id, player_name),
    FOREIGN KEY (hand_id) REFERENCES hands(hand_id)
);

CREATE INDEX IF NOT EXISTS idx_hands_played_at ON hands(played_at);
CREATE INDEX IF NOT EXISTS idx_hand_players_name ON hand_players(player_name);
CREATE INDEX IF NOT EXISTS idx_actions_hand ON actions(hand_id);
CREATE INDEX IF NOT EXISTS idx_hps_player_date ON hand_player_stats(player_name, played_at);
CREATE INDEX IF NOT EXISTS idx_hps_player_stake ON hand_player_stats(player_name, stakes_label);
-- Population queries filter by played_at across ALL players (no player_name
-- in the WHERE), so they can't seek through either index above (both lead
-- with player_name) — without this, SQLite falls back to scanning the
-- entire idx_hps_player_date index regardless of how narrow the date range
-- is. Measured on a synthetic 900k-row table: a "this month"-style
-- population query went from ~193ms to ~17ms, and an all-time one from
-- ~3.6s to ~0.5s.
CREATE INDEX IF NOT EXISTS idx_hps_played_at ON hand_player_stats(played_at);

-- Tracks which hand-history files have already been fully parsed and
-- imported, keyed by a cheap (mtime, size) fingerprint — lets startup
-- skip re-parsing every file's raw text on every launch (parsing was
-- ~15-20s across 1000+ files) and only touch files that are new or have
-- actually changed since last time.
CREATE TABLE IF NOT EXISTS imported_files (
    file_path TEXT PRIMARY KEY,
    mtime REAL NOT NULL,
    size INTEGER NOT NULL,
    imported_at TEXT DEFAULT CURRENT_TIMESTAMP
);
