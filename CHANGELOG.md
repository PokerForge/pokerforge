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
- 110 automated tests covering the stat engine, both parsers, the SQL
  query layer, and the surrounding infrastructure.

### Known limitations
- Only Grosvenor and iPoker Network formats are supported today.
- No code signing yet (see README's "If Windows warns you").
- No license-key or payment infrastructure yet.
