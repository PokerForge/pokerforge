# Changelog

All notable changes to PokerForge are documented here. Version numbers
follow `config/version.py`'s `APP_VERSION`; the "notes" field in a future
Help > Check for Updates manifest would draw from whatever's newest here.

## [1.0.0-beta.3] — 2026-09-15

A new look, and groundwork under the hood.

### New identity

- PokerForge has a proper logo — a chip mark that now appears in the
  app header, the taskbar, the installer, and on the website.
- Windows caches shortcut icons, so an existing desktop shortcut may
  keep showing the old icon for a while. A fresh install won't.

### Under the hood

- Licence keys are now cryptographically signed rather than
  checksummed, so a key can be trusted offline and can't be forged by
  editing a settings file. Nothing is enforced yet — the app remains
  free and unrestricted during the beta.
- Internal housekeeping: removed a long-superseded prototype and a
  quantity of stale documentation. No stat, formula or calculation
  changed — verified by comparing the compiled code before and after.

## [1.0.0-beta.2] — 2026-09-15

More rooms, tournaments, and rakeback — plus PokerForge Intelligence,
which goes beyond raw stats to tell you what's actually costing you
money and what to do about it.

### More poker rooms

- **PokerStars**, **GGPoker** and **Winning Network / Americas
  Cardroom** hand histories are now parsed natively, alongside the
  existing iPoker and Grosvenor support — verified against real
  exports of 286,554, 222,843 and 30,863 hands respectively.
- Note that GGPoker and Winning Network anonymise opponents in their
  own exports, so hands from those rooms build your own stats rather
  than opponent profiles.

### Tournaments

- A global **$ / T toggle** in the filter bar switches Overview,
  Sessions, Stats and Population between cash and tournament play —
  the same mode switch PT4 and Hold'em Manager use — rather than
  isolating tournaments in a separate tab.
- Tournament mode gives Overview a results summary (Tournaments,
  Logged, ROI, ITM, Avg Finish, Profit) and a cumulative profit graph,
  and turns Sessions into a results table.
- Because no hand-history format records your finish position or
  payout, results are entered manually per tournament; summaries
  report "X of Y logged" rather than treating unlogged tournaments
  as $0.

### Rakeback

- Enter your rakeback deal in Settings and PokerForge tracks what
  you've actually earned over any date range — shown as its own stat
  card and as a "Profit & Rakeback" line on the Overview graph.
- Rake is attributed per player across those who saw the flop, rather
  than crediting every seated player with the whole pot's rake.

### Fixes

- **GGPoker hands were missing from every stat.** Hero-identity
  normalisation renamed the room's placeholder name before stats were
  built, so no rows were ever stored. All affected hands are restored
  by a Rebuild Stats Database run (Tools menu).
- **A villain's "over-folds to 3-bets" exploit listed irrelevant
  hands** — it counted cold folds from the blinds facing someone
  else's 3-bet. It now only counts players 3-bet off their own open,
  which is what the advice actually assumes.

### PokerForge Intelligence

- **Leaks by Position** (Stats > Leaks) — ranks your biggest deviations
  from your own imported population, by position, weighted by how much
  each one actually costs you (deviation × sample size) rather than
  deviation alone. A category filter (Preflop Opens / 3-Bet & 4-Bet /
  Steal Defense / Postflop / Showdown) and a per-stat cap keep one
  dominant leak from crowding out everything else. Click any leak to
  see the hands behind it.
- **Study Queue** (Stats > Leaks, above the leak list) — a short,
  prioritized "work through these" plan: up to 3 genuinely different
  leaks, each with a "Study N Hands" button that opens the replayer
  loaded with your own recent hands for it.
- **Villain Exploit Notes** — now gated on sample size (no more notes
  built from a handful of hands) and clickable straight to example
  hands, matching the quality bar of your own leaks.
- **Similar Players** (villain profile) — instantly see who else in
  your pool plays like the villain you're looking at.
- **Pool Insights** (Population tab) — population-wide patterns, like
  river bet-sizing versus revealed hand strength, mined across your
  whole showdown history.
- **Tilt Report** (Sessions tab) — does your VPIP shift in the 30
  minutes after a 30bb+ loss, compared to your own baseline?
- **Backtest Deviations** (Stats > Trend) — for any stat you're
  tracking, splits your own history into the periods where it ran high
  or low versus your average, and shows what your bb/100 actually
  looked like in each — a correlation, never claimed as causal.
- The villain profile is now organized as Exploits / Similar Players /
  Stats tabs instead of one long scroll, leading with the most
  actionable view.
- The hand replayer's Range Grid heatmap now works for "All Positions"
  too (previously required filtering to one position first), and the
  transport's ⏮/⏭ buttons advance to the previous/next hand once
  they're already at the start/end of the current one.
- Fixed a real layout bug where the pot label could overlap a seat's
  info pill in the hand replayer.

## [1.0.0-beta.1] — 2026-09-13

First early-access build. Highlights:

- Overview, Sessions, Stats, and Population tabs, each validated against
  real hand-history exports.
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
- Live auto-refresh: a folder watcher imports new hands automatically
  while the app stays open (Settings > "Automatically check for new
  hands while the app is open" to turn it off).
- An automatic, silent database snapshot before each day's first import
  — a safety net separate from Tools > Backup My Data, kept alongside
  the last two.
- Atomic settings.json writes, so a crash mid-save can no longer leave
  a truncated/corrupt settings file behind.
- A progress dialog for the initial hand-history file scan on a large
  first run, instead of a window that looks frozen.
- Sessions tab gained "Export to PDF..." — a printable summary for
  tax/accounting-style records, alongside the existing CSV export.
- Database & Diagnostics now shows the exchange-rate snapshot date used
  for $ conversion (see core/currency.py's `FX_RATES_AS_OF`).
- Any stat's hand list (villain profile drill-downs, By Position) can
  now be filtered by position, revealing a "Range Grid" button — a 13x13
  heatmap of hole cards actually seen for the filtered hands. Clearly
  labeled as "N of M hands shown," not a claim about someone's true
  range, since folded hands are never revealed by the site. Clicking a
  cell replays every hand behind it, with Previous/Next Hand navigation
  in the replayer for stepping through more than one.
- 221 automated tests covering the stat engine, both parsers, the SQL
  query layer, and the surrounding infrastructure.

### Known limitations
- Only Grosvenor and iPoker Network formats are supported today.
- No code signing yet (see README's "If Windows warns you").
- No license-key or payment infrastructure yet — the scaffolding exists
  (core/licensing.py) but is inert until a pricing model is decided.
