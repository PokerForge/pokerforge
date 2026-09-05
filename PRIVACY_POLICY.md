# SF Poker — Privacy Policy

> **DRAFT — not legal advice.** This is a starting template based on how the
> app actually works today, written to be accurate and honest rather than
> legally exhaustive. Have a lawyer review it — especially the jurisdiction,
> liability, and any consumer-protection requirements that apply where you
> sell — before publishing or relying on it.

_Last updated: [DATE]_

## The short version

SF Poker runs entirely on your own computer. It does not send your data
anywhere. There is no server, no account, no cloud sync, and no analytics —
the app has no network code at all.

## What data SF Poker stores

SF Poker reads poker hand-history files that your poker client already
saves on your computer (or that you've exported yourself), and builds a
local database of statistics from them. This includes:

- Your own hole cards, actions, and results for hands you've played
- The usernames and observable in-hand actions of other players who were
  seated in those same hands ("villains"), and statistics derived from them
- Settings you configure in the app (hero name, currency, which folders
  to watch)

All of this is stored in a single local database file on your computer, at
`%APPDATA%\SFPoker\` on Windows. **Nothing is uploaded, transmitted, or
shared with SF Poker, its developer, or any third party.**

## Data about other players

Because hand histories necessarily include other players at the table, SF
Poker's database contains other people's usernames and derived statistics
(e.g. how often they raise). This data:

- Comes only from hand histories your own poker client already gave you
- Never leaves your computer
- Is not used for any purpose other than showing you your own opponents'
  tendencies within the app

If you uninstall SF Poker, this data is not automatically deleted (see
"Deleting your data" below), since it lives separately from the installed
program files.

## Deleting your data

All app data lives in one folder: `%APPDATA%\SFPoker\`. Deleting that
folder removes your entire database, settings, and log file. Uninstalling
the app itself does not delete this folder automatically.

## Third-party services

SF Poker does not integrate with any third-party service, analytics
provider, crash-reporting tool, or advertising network. [Update this
section if that changes in a future version — e.g. if you add license-key
validation, crash reporting, or an update checker, each of those would
need to be disclosed here.]

## Changes to this policy

[Describe how you'll notify users of changes, if at all — e.g. "the
version history on the download page."]

## Contact

[Your contact email or support channel.]
