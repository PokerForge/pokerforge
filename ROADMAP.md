# Roadmap

Ideas and requests that have come up but aren't built yet — tracked here
so they don't get lost between sessions. Nothing here is committed to a
particular order or timeframe; pull items into an actual release when
they're ready to be worked on.

## UI / Appearance

- **Light theme option** — a Dark/Light toggle in Settings. Not a small
  toggle: every color in `ui/theme.py` is a hardcoded hex constant
  imported directly into dozens of UI files, so this needs the whole
  palette turned into a real swappable theme, every file switched to
  reading from whichever theme is active instead of a fixed import, and
  the graph colors (pyqtgraph) given the same treatment. Requiring an
  app restart to apply (rather than live-switching every open widget)
  is the realistic first version.

## Intelligence Engine extensions

- ~~**Monthly Performance Report**~~ — **Done.** Overview tab > "Monthly
  Report..." button (`ui/monthly_report_dialog.py`): headline stats with
  a delta vs the previous month, that month's biggest leak
  (`core/leak_finder.find_leaks`), and the stat that moved closest to
  the population average since last month (`find_biggest_improvement`).
  Prev/Next month navigation; disabled past the current calendar month.
- ~~**Study Queue completion tracking**~~ — **Done.** Each priority row
  in the Study Queue card has a "Mark Studied" button
  (`ui/stats_tab.py`); completions persist in a new `study_completions`
  table (`database/repository.py`'s `log_study_completion`/
  `get_recent_study_completions`/`get_study_completion_dates`). A
  studied leak shows "✓ Studied" for 7 days (`STUDIED_RECENTLY_DAYS` in
  `core/study_queue.py`) before it can nag again if still unresolved,
  and the card header shows a consecutive-day streak
  (`compute_streak_days`) that stays alive until a full day is missed.
- **Session Review** — a per-session summary + hand-tagging view, opened
  from a session row in the Sessions tab (today double-clicking one just
  opens its plain hand list via `HandListDialog`). Two parts:
  - **Summary card**: that session's own VPIP/PFR/3-bet/etc. next to the
    player's own baseline (not the population average — this is "was
    this session typical for me", not a leak-finding tool, which
    `core/leak_finder.py` already covers), plus its biggest pots
    won/lost. Tilt Report (`ui/tilt_report_dialog.py`) already computes
    one slice of this — VPIP shift after a 30bb+ loss — so this should
    absorb/link to that rather than duplicate it.
  - **Hand tagging**: mark specific hands within the session "review
    later" with a note, and revisit them as a queue — the same
    completion-tracking pattern Study Queue already established
    (`database/repository.py`'s `log_study_completion`/
    `get_recent_study_completions`, `core/study_queue.py`), scoped to a
    session's own hands instead of a leak's illustrative ones.
- **Per-hand coaching in the replayer** — annotate hands as they're
  replayed ("this looked like a standard fold, but your continue
  frequency here is above average", etc). The biggest lift of the
  bunch: needs a real hand-strength/board-texture classifier, not just
  the aggregate stats the rest of the Intelligence Engine relies on.
- **GTO deviation comparison** — compare a player's frequencies against
  solver-derived baselines rather than population averages. Lowest
  priority: real solver output is expensive to produce/license, and
  presenting it wrong risks looking authoritative when it isn't.

## From the original feedback pass

Three "quick win" ideas from an early to-do list review. All three are
now done:

- ~~Missed-3-bet-opportunities display~~ — turned out to already be
  covered by the Intelligence Engine's "Low 3-Bet" leak (`ui/player_classify.py`),
  which drills down to exactly these hands via the existing
  `three_bet_opp = 1 AND three_bet = 0` condition
  (`database/queries.py`'s `LEAK_HAND_CONDITIONS['three_bet_low']`) —
  no separate feature needed.
- ~~Fixing the cramped graph layout~~ — **Done.** The floating stats box
  on the Overview tab's graph (`ui/graph_overlay.py`'s
  `DraggableStatsBox`) used to sit at a fixed spot regardless of the
  data, so a strong, consistent trend from hand 1 (a big up- or
  downswing) ran straight through it every time. It now defaults to
  whichever vertical half of the left edge the line ISN'T occupying
  near the start (`suggest_stats_box_prefer_bottom`), re-evaluated on
  every refresh — unless the user has actually dragged it themselves,
  which is remembered and left alone.
- ~~A Limp / Limp-Call stat~~ — **Done.** New "Limp" (voluntarily
  called preflop before anyone raised — includes the SB completing) and
  "Limp-Call" (called a raise after limping, given the chance to) stats
  in the Preflop category (`core/stats.py`'s `PlayerHandFlags.limp_opp`/
  `limp`/`limp_call_opp`/`limp_call`), wired through the same
  hand_player_stats/STAT_REGISTRY pipeline as every other stat.
  Existing databases need a Rebuild Stats Database run (Tools menu) to
  populate these for hands imported before this update — like
  `vpip_pfr_opp`, they can't be backfilled from any other stored
  column.

## Known follow-ups

- ~~The live folder watcher and manual Refresh button silently swallow
  hand-parsing errors~~ — **Done.** `_notify_ongoing_scan_errors` in
  `ui/app_window.py` now shows the same Warning + "Report a Bug..."
  dialog the first-run scan does, but tracks every (file, message)
  already shown this session (`AppWindow._warned_scan_errors`) so a
  persistently-broken file (which never gets its fingerprint marked
  imported) warns once, not on every poll/click — and known-limitation
  errors (tournament hands) stay silent here entirely, since first-run
  already explained those once.
- **Broader hand-history format support** — Grosvenor, iPoker Network,
  PokerStars (`core/pokerstars_hand_parser.py`, verified against a real
  594-file/286,554-hand export — full population/villain support, real
  usernames), GGPoker (`core/ggpoker_hand_parser.py`, verified against a
  real 452-file/222,843-hand export), and Winning Network / Americas
  Cardroom (`core/winning_network_hand_parser.py`, verified against a
  real 25-file/30,863-hand export — 245 tournaments, cash and
  tournament hands both handled) are supported now. Other rooms
  (partypoker, etc.) use their own formats and would each need their
  own parser. Note GGPoker's and Winning Network's own opponent
  anonymization means their hands only ever feed Hero-side stats — see
  the README's GGPoker note.
- ~~**Per-tab empty states for a zero-hand filter**~~ — **Done.**
  Overview, Sessions, and Stats (both the By Position table and the
  Leaks sub-tab) now show "No hands match the current Period / Stakes
  / Site filter — try widening it." when the active filter matches
  zero hands but the account isn't actually empty
  (`db.hand_count() > 0`) — distinct from the totally-empty-database
  case, which the top banner already covers. Population tab's existing
  GGPoker-anonymization explanation got the same treatment
  (`hero_hand_sources_query` now respects the Stakes/Site filters too,
  not just Period).
- ~~**Tournament support**~~ — **Done.** PokerStars and GGPoker now
  parse real tournament hands (`session_type='tournament'`,
  `tournament_id`/`buy_in`/`fee` extracted from the header) instead of
  rejecting them. Rather than a separate tab, a global **$ / T** toggle
  (`ui/game_type_toggle.py`) sits in the filter bar next to Stakes and
  switches what Overview/Sessions/Stats/Population show — the same
  cash/tournament mode switch PT4/Hold'em Manager use. In Tournament
  mode, Overview shows a results summary (Tournaments/Logged/ROI/ITM/
  Avg Finish/Profit cards) plus a cumulative-profit graph, and Sessions
  shows the tournament results table (Date/Site/Tournament/Buy-in/
  Field/Finish/Payout/ROI, double-click to log a result) in place of
  their cash content. Overview/Sessions' cash content stays permanently
  cash-only at the query layer (`session_type = 'cash'` hardcoded in
  `hero_overview_query`/`sessions_query`/the villain-graph queries) so
  a tournament hand can never silently blend chip counts into a $
  total — the toggle only switches which page is visible, it never
  makes those specific queries game-type-aware. Stats and Population
  take the toggle's value straight through to their existing
  `session_type` query param, since VPIP/PFR/etc. are action-based and
  equally valid for either. **No hand-history export (in any format)
  contains a finish position or payout** — only the hand-by-hand action log — so real
  ROI/ITM% needed a manual entry form
  (`ui/log_tournament_result_dialog.py`, persisted in the new
  `tournament_results` table); a tournament shows as "Log Result" until
  its result is entered, and the summary cards report "X of Y logged"
  rather than silently treating unlogged tournaments as $0.
  **iPoker and Grosvenor XML tournament parsing was deliberately NOT
  built** — unlike PokerStars/GGPoker (real header samples existed) and
  Winning Network (a full real corpus existed), no real iPoker or
  Grosvenor tournament sample was available to verify against; guessing
  at the format risked silently misclassifying a real hand. A tournament
  hand in either format still fails the same way it always has (a
  generic parse error, never silently imported as cash) — revisit once
  a real sample surfaces.

## Business / Site

- **Pricing page + accounts + Stripe** — no pricing/account
  infrastructure exists yet; deliberately deferred until there's an
  actual paid tier worth putting behind it.

  **Plan for the free-now-paid-later transition:** give everyone full
  access now to build momentum, then gate features (not data) later.
  All app data is local-only (SQLite under `%APPDATA%\SFPoker`,
  untouched by installer updates), so an app update alone can never
  wipe or lock a user out of hands they've already imported — any
  future paywall has to be a deliberate feature gate, not a side effect
  of data storage.

  - Keep basic tracking (Overview, Sessions, core Stats) free forever
    as the funnel; gate only the Intelligence Engine features (Study
    Queue, Exploit Reports, villain profiles, tilt/deviation
    backtesting) behind the paid tier.
  - **Grandfather early users**: anyone who installs before the
    paywall cutoff date keeps the Intelligence Engine features
    unlocked permanently. Costs some conversion revenue from early
    adopters, but they're the ones building word-of-mouth during the
    momentum-building phase, and locking them out later would burn
    that goodwill right when it matters most.
  - Never gate on data presence/deletion — only on feature visibility.
    Wiping or hiding a user's own already-imported data behind a
    paywall would contradict `PRIVACY_POLICY.md`'s local-only-data
    promise and reads uncomfortably close to hostile/ransomware-style
    behavior.
  - Cheap prep to do now (low cost, avoids a retrofit later): add a
    single local `is_pro_unlocked() -> bool` seam that the premium
    features call, hardcoded to `True` for now. When accounts/Stripe
    exist, flip that one function to a real license/grandfather check
    instead of adding gating logic across the whole app at once.
- **Blog/SEO content** — no urgency, but worth having eventually for
  organic discovery.

## On hold

- **Code signing** — paused pending choosing/buying a certificate.
  Recommendation from research: SSL.com OV certificate + a YubiKey
  hardware token (~$508 first year, ~$129/year after) — cheapest option
  for the same trust level, and it slots directly into what's already
  built. `build_installer.bat` is already wired up and ready: set
  `POKERFORGE_CERT_THUMBPRINT` (or `POKERFORGE_CERT_PFX` +
  `POKERFORGE_CERT_PASSWORD`) once a certificate exists — no further
  code changes needed.
