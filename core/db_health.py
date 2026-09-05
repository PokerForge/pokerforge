"""Read-only database health check — a fast sanity check ("is everything
internally consistent?"), distinct from Rebuild Stats Database, which is
the heavier fix-it hammer that actually recomputes every stat from
scratch. This never writes anything; it only reports what it finds, so
it's safe to run anytime and cheap enough to run often."""
from dataclasses import dataclass, field


@dataclass
class HealthReport:
    ok: bool
    integrity_check: str
    hand_count: int
    stats_row_count: int
    orphaned_stats_rows: int
    hands_missing_stats: int
    issues: list[str] = field(default_factory=list)


def check_database_health(db) -> HealthReport:
    integrity = db.conn.execute("PRAGMA integrity_check").fetchone()[0]
    hand_count = db.conn.execute("SELECT COUNT(*) FROM hands").fetchone()[0]
    stats_count = db.conn.execute("SELECT COUNT(*) FROM hand_player_stats").fetchone()[0]

    orphaned = db.conn.execute(
        "SELECT COUNT(*) FROM hand_player_stats hps "
        "LEFT JOIN hands h ON hps.hand_id = h.hand_id "
        "WHERE h.hand_id IS NULL"
    ).fetchone()[0]

    hands_missing_stats = db.conn.execute(
        "SELECT COUNT(*) FROM hands h "
        "WHERE NOT EXISTS (SELECT 1 FROM hand_player_stats hps WHERE hps.hand_id = h.hand_id)"
    ).fetchone()[0]

    issues = []
    if integrity != "ok":
        issues.append(f"SQLite integrity check failed: {integrity}")
    if orphaned:
        issues.append(f"{orphaned} stat row(s) reference a hand that no longer exists.")
    if hands_missing_stats:
        issues.append(f"{hands_missing_stats} hand(s) have no computed stats yet — try Rebuild Stats Database.")

    return HealthReport(
        ok=not issues, integrity_check=integrity, hand_count=hand_count,
        stats_row_count=stats_count, orphaned_stats_rows=orphaned,
        hands_missing_stats=hands_missing_stats, issues=issues,
    )
