# Changelog

All notable changes to PokerForge are documented here. Version numbers
follow `config/version.py`'s `APP_VERSION`; the "notes" field in a future
Help > Check for Updates manifest would draw from whatever's newest here.

## [1.0.0] — Unreleased

Initial commercial-readiness pass. Highlights:

- Overview, Sessions, Stats, and Population tabs, each validated against
  real PT4 exports.
- Grosvenor Poker (XML) and iPoker Network (text) hand-history support.
- Multi-profile support (File > Switch Profile).
- CSV export for hand lists, By Position, Sessions, and the villain pool.
- Backup/Restore and a Database & Diagnostics panel (Tools menu).
- A Getting Started glossary and Report a Bug link (Help menu).
- Auto-detection of Grosvenor's hand-history folder on first run.
- Single-instance enforcement, a global crash handler, and structured
  logging throughout.
- A standalone Windows installer (per-user, no admin/UAC prompt) built
  with PyInstaller + Inno Setup.
- A "What's New" popup after an update, sourced straight from this file.
- Help > Check for Updates can now read GitHub's own Releases API
  (config/version.py's `GITHUB_REPO`), not just a static manifest URL.
- Database & Diagnostics gained "View Log File" and "Copy Diagnostic
  Info" buttons, for a support conversation that starts from a pasted
  block instead of "where do I even look."
- Added an index for population-wide date-range queries — cut an
  all-time Population tab query from ~3.6s to ~0.5s on a 900k-row
  database (see schema.sql's `idx_hps_played_at`).
- Continuous integration (GitHub Actions) runs the full test suite on
  every push.
- 152 automated tests covering the stat engine, both parsers, the SQL
  query layer, and the surrounding infrastructure.

### Known limitations
- Only Grosvenor and iPoker Network formats are supported today.
- No code signing yet (see README's "If Windows warns you").
- No license-key or payment infrastructure yet — the scaffolding exists
  (core/licensing.py) but is inert until a pricing model is decided.
