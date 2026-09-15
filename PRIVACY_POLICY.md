# PokerForge — Privacy Policy

> **DRAFT — not legal advice.** This is a starting template based on how the
> app actually works today, written to be accurate and honest rather than
> legally exhaustive. Have a lawyer review it — especially the jurisdiction,
> liability, and any consumer-protection requirements that apply where you
> sell — before publishing or relying on it.

_Last updated: 2026-09-15_

## The short version

PokerForge runs entirely on your own computer. Your hand histories,
statistics and settings never leave your machine — there is no cloud
sync, no analytics, and no account needed to use the app.

The app makes no requests to track, profile or measure you. There are
only two requests it can make at all — a manual update check, and a
licence check if you're a paying subscriber — and neither ever includes
any of your poker data. Both are described in "Third-party services"
below. If you buy a subscription, see "If you buy a subscription" for
the limited data that involves.

## What data PokerForge stores

PokerForge reads poker hand-history files that your poker client already
saves on your computer (or that you've exported yourself), and builds a
local database of statistics from them. This includes:

- Your own hole cards, actions, and results for hands you've played
- The usernames and observable in-hand actions of other players who were
  seated in those same hands ("villains"), and statistics derived from them
- Settings you configure in the app (hero name, currency, which folders
  to watch)

All of this is stored in a single local database file on your computer, at
`%APPDATA%\SFPoker\` on Windows. **Nothing is uploaded, transmitted, or
shared with PokerForge, its developer, or any third party.**

## Data about other players

Because hand histories necessarily include other players at the table,
PokerForge's database contains other people's usernames and derived statistics
(e.g. how often they raise). This data:

- Comes only from hand histories your own poker client already gave you
- Never leaves your computer
- Is not used for any purpose other than showing you your own opponents'
  tendencies within the app

If you uninstall PokerForge, this data is not automatically deleted (see
"Deleting your data" below), since it lives separately from the installed
program files.

## Deleting your data

All app data lives in one folder: `%APPDATA%\SFPoker\`. Deleting that
folder removes your entire database, settings, and log file. Uninstalling
the app itself does not delete this folder automatically.

## Third-party services

PokerForge does not integrate with any analytics provider, crash-reporting
tool, or advertising network. Nothing about your usage is measured,
profiled or reported.

There are exactly two network requests the app can make. **Neither ever
includes hand histories, hole cards, player names, your hero identity, or
anything else about your poker activity:**

- **Help > Check for Updates** — asks whether a newer release exists.
  This happens only when you click that menu item. Nothing checks on a
  timer or at startup.
- **Licence validation** — *only if you have entered a paid licence key.*
  Once when the app starts, it asks our licence server whether that
  subscription is still active. The request contains the licence key and
  nothing else. If you have not entered a licence key, this request never
  happens and the app makes no automatic network requests whatsoever.

## If you buy a subscription

Payment is handled by **Stripe**. Your card details go directly to Stripe
and are never seen, handled or stored by PokerForge — Stripe's own
privacy policy governs how they process them.

To deliver your licence key and check it's still valid, our licence server
stores only:

- the email address you provided at checkout
- your licence key, and which Stripe subscription it belongs to
- whether that subscription is active, and the date it is paid up to

Your licence key is emailed to you using **SendGrid**, which processes
your email address in order to deliver that one message.

None of this is ever connected to your poker data. Your hands, statistics
and results stay on your own computer before, during and after a
subscription — subscribing does not upload anything, and cancelling does
not delete anything you've imported.

To have the above deleted, cancel your subscription and email
support@pokerforge.app.

## Changes to this policy

Material changes will be noted in the in-app "What's New" popup shown
after an update, and in the version history published alongside each
release.

## Contact

support@pokerforge.app
