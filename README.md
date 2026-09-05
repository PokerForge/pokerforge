# PokerForge

A personal poker hand-history tracker and stats analyzer (PyQt6 desktop
app), in the same spirit as PokerTracker/Hold'em Manager: import your own
hand histories, see your results over time, break your own game down by
position and street, study your leaks, and look up how any opponent you've
played against actually plays.

## Features

- **Overview** — a PT4-style cumulative results graph (Total / Showdown /
  Non-Showdown / EV, in $ or BB/100), with a draggable summary box and
  one-click copy to clipboard.
- **Sessions** — every session grouped by date and stakes, drilling down
  to a full PT4-style hand grid, drilling further into a hand replayer.
- **Stats** — your own game broken down by position, an auto-generated
  "Your Leaks" section gated on sample size, and a trend view showing
  whether a stat is actually moving over time.
- **Population** — a sortable villain pool with search/filter, and a full
  stat profile for any opponent (or any group of opponents by player
  type).
- **CSV export** — hand lists, By Position, the Sessions list, and the
  villain pool can all be exported.
- **Multiple profiles** — File > Switch Profile, for a shared computer or
  tracking two accounts as separate identities. Switching takes effect on
  restart; see `config/profiles.py`.
- **Backup & restore** — Tools > Backup My Data / Restore from Backup, a
  single zip covering the database and settings for the active profile.
- **Getting Started guide** — Help menu, a plain-language glossary for
  every stat shown throughout the app.

## Supported hand-history formats

- Grosvenor Poker's native XML session export
- iPoker Network text exports

Adding another site means writing and validating a new parser (see
`core/hand_parser.py` and `core/xml_hand_parser.py` for the existing two,
and `tests/test_hand_parser.py` / `tests/test_xml_hand_parser.py` for how
they're tested) — there's no generic parser today.

## Running from source

```bash
pip install -r requirements.txt
python main.py
```

On first launch, a setup wizard asks for the folder(s) your poker
client saves hand histories to, then confirms the auto-detected hero
username and currency (both editable if the guess is wrong). Everything
after that — settings, the database, and the log file — lives in
`%APPDATA%\SFPoker\`, independent of wherever the app itself is installed
or run from.

## Running the tests

```bash
pip install -r requirements-dev.txt
pytest
```

Coverage focuses on the parts most likely to silently break something a
user would never notice: the preflop stat engine (VPIP/PFR/3-bet/4-bet/
squeeze), position assignment (which already shipped one real bug once —
see `core/position.py`'s docstring), and both hand-history parsers.

## Building a standalone Windows build

```
build.bat            # PyInstaller -> dist\PokerForge\ (no Python needed to run it)
build_installer.bat  # also wraps that into installer_output\PokerForge-Setup-*.exe (Inno Setup)
```

The installer installs per-user (no admin/UAC prompt needed) and never
touches `%APPDATA%\SFPoker\` on install/upgrade; uninstalling offers an
opt-in (defaults to No) prompt to also delete that data.

### If Windows warns you about the installer

The installer isn't code-signed yet, so Windows SmartScreen will show an
"Unrecognized app" / "unknown publisher" warning the first time it runs —
this is expected, not a sign of anything wrong. It happens because the
`.exe` isn't signed with a paid code-signing certificate, which is a
separate step (see "Known limitations" below), not because of anything
the app does. To proceed anyway: click **More info**, then **Run anyway**.
This warning goes away once the build is signed.

## Project layout

- `core/` — hand-history parsing, the stat engine, position logic,
  equity/EV calculation. Framework-independent; this is what the tests
  in `tests/` cover.
- `database/` — SQLite schema, the importer, and the aggregate queries
  the UI runs against precomputed per-hand stats.
- `ui/` — the PyQt6 app itself.
- `config/` — persisted settings, app-data/resource path resolution,
  version number.
- `models/` — the `Hand`/`Player`/`Action` dataclasses everything else
  is built on.

## Known limitations / not yet built

- Only two poker-site formats are supported (see above).
- No license-key or payment infrastructure yet.
- No code signing on the Windows build yet — see "If Windows warns you"
  above.
- Help > Check for Updates is fully built but inert until a real update
  manifest is hosted somewhere (see `config/version.py`'s
  `UPDATE_MANIFEST_URL`).
- Help > Report a Bug opens a blank-recipient mailto: until a real
  support address is set (see `config/version.py`'s `SUPPORT_EMAIL`).
- `PRIVACY_POLICY.md` and `TERMS_OF_USE.md` are drafts — have them
  reviewed before relying on them commercially.
