# PokerForge

A personal poker hand-history tracker and stats analyzer (PyQt6 desktop
app), in the same spirit as PokerTracker/Hold'em Manager: import your own
hand histories, see your results over time, break your own game down by
position and street, study your leaks, and look up how any opponent you've
played against actually plays.

## Features

- **Overview** — a cumulative results graph (Total / Showdown /
  Non-Showdown / EV, in $ or BB/100), with a draggable summary box and
  one-click copy to clipboard.
- **Sessions** — every session grouped by date and stakes, drilling down
  to a full hand grid, drilling further into a hand replayer.
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
- PokerStars text exports (full villain/population support — PokerStars
  keeps real, persistent usernames; cash and tournament hands both supported)
- GGPoker (and its skins: Natural8, BetKings, etc.) text exports — cash
  and tournament hands both supported — see the note below on villain
  stats for this one
- Winning Network (Americas Cardroom, Black Chip Poker, etc.) text
  exports — cash and tournament hands both supported, same
  opponent-anonymization behavior as GGPoker, see the note below

Adding another site means writing and validating a new parser (see
`core/hand_parser.py`, `core/xml_hand_parser.py`,
`core/pokerstars_hand_parser.py`, `core/ggpoker_hand_parser.py`, and
`core/winning_network_hand_parser.py` for the existing five, and their
matching `tests/test_*.py` files for how they're tested) — there's no
generic parser today.

**Tournament support:** PokerStars, GGPoker, and Winning Network hands
are tracked separately from cash — a tournament's per-hand chip
movements aren't real money until the tournament itself pays out. Instead
of a separate tab, a global **$ / T** toggle in the filter bar (next to
Stakes) switches Overview/Sessions/Stats/Population between cash and
tournament content, the way PT4/Hold'em Manager do it. In Tournament
mode, Overview shows a results summary and cumulative-profit graph, and
Sessions shows the tournament results table. No hand-history export
contains a finish position or payout, so real ROI/ITM% needs you to log
each tournament's result yourself (a small form, opened by
double-clicking its row in Sessions) — until you do, it just shows the
hands played and buy-in. iPoker and Grosvenor tournament hands aren't
parsed yet (no real sample of either to validate a parser against) —
they're rejected with a clear error rather than silently imported as
cash.

**GGPoker/Winning Network note:** both sites anonymize every opponent as
a random label that resets on every hand (a deliberate anti-tracking
measure — the same reason other trackers can't build opponent stats on
these sites either). Hero's own stats (Overview, Sessions, Stats — both cash and
tournament modes) are unaffected and import in full; the
population/villain-profile features simply won't have any data for
these hands, since there's no stable opponent identity to build a
profile against.

Both sites also always label the account owner's own seat literally
`"Hero"`, never your real username there — so playing on one of them
and at least one other site under different usernames (or setting both
up at once on a brand-new install) would otherwise import as two
separate, unmerged identities, with that site's own volume missing from
your Overview/Sessions/Stats entirely. PokerForge detects this
generically (it's not really a GGPoker/Winning-Network-specific
problem, just the two sites guaranteed to trigger it) and offers to add
the new identity as an alias for your existing one, whichever order the
sites' hands happen to import in — accept it so every site's hands are
counted correctly from the start, rather than importing under separate,
untracked identities.

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

**For whoever's distributing this build** — two things help before
code-signing happens (neither replaces it, but both reduce how alarming
the warning looks for a new user):

- Submit each release build to Microsoft for a reputation review at
  <https://www.microsoft.com/en-us/wdsi/filesubmission> ("Software
  developer" submission type) — this doesn't remove the "unrecognized
  publisher" warning by itself, but it does clear the build of being
  mistaken for actual malware, and repeated clean submissions from the
  same publisher build reputation over time.
- SmartScreen's reputation is partly about the FILE ITSELF (a fresh
  build every release starts back at zero reputation) — an unsigned
  build that changes with every release will basically always trigger
  this on a brand new machine, no matter how long the app has existed.
  Code signing (a real certificate, not just Microsoft's own review) is
  the only way to actually skip the cold-start problem release after
  release, which is why it's still listed separately under "Known
  limitations" rather than something this step replaces.

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

- Only four poker-site formats are supported (see above).
- No license-key or payment infrastructure yet — the app is fully free
  during early access.
- No code signing on the Windows build yet — see "If Windows warns you"
  above.
- `PRIVACY_POLICY.md` and `TERMS_OF_USE.md` are drafts — have them
  reviewed before relying on them commercially.
