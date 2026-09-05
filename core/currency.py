"""Converts every hand's money fields to USD, once, right after parsing —
not historical per-hand-date rates (today's mid-market rate is used for
all history), a simplification the user explicitly accepted when asking
for one-currency reporting across mixed GBP/EUR/USD play. Applying this
once at the Hand level means every existing stat/profit calculation
downstream (BB/100, EV, population averages, graphs, the replayer) just
works in USD with no further changes needed anywhere else in the app —
BB/100-style ratios are unaffected either way since blind and profit
scale by the same factor, but $ totals summed across hands of different
original currencies were previously being added together unconverted,
which this fixes.

Rates are real, sourced mid-market rates (xe.com / wise.com), not
invented figures: fetched 2026-09-04. They are a fixed snapshot, not
fetched live (this app makes no network calls except the manual, opt-in
Help > Check for Updates — see PRIVACY_POLICY.md), so FX_RATES_AS_OF
will drift further from "current" the longer this ships unchanged.
Surfaced in Tools > Database & Diagnostics so that's visible rather than
a silent assumption. If this is ever updated: a hand's conversion is
baked in at IMPORT time (see convert_hands_to_usd below), not
recomputed later, so changing this rate only affects hands imported
from that point on — it does NOT retroactively re-convert hands already
in someone's database, which would silently shift their historical $
totals without them asking for that."""
FX_RATES_AS_OF = "2026-09-04"
FX_TO_USD = {
    '£': 1.3524,  # GBP
    '€': 1.1603,  # EUR
    '$': 1.0,
}


def convert_hands_to_usd(hands) -> None:
    for h in hands:
        h.native_currency = h.currency
        h.native_small_blind = h.small_blind
        h.native_big_blind = h.big_blind

        rate = FX_TO_USD.get(h.currency, 1.0)
        if rate == 1.0:
            h.currency = '$'
            continue
        if h.small_blind is not None:
            h.small_blind *= rate
        if h.big_blind is not None:
            h.big_blind *= rate
        if h.total_pot is not None:
            h.total_pot *= rate
        if h.rake is not None:
            h.rake *= rate
        for p in h.players:
            if p.stack is not None:
                p.stack *= rate
        for a in h.actions:
            if a.amount is not None:
                a.amount *= rate
        h.winnings = {name: amt * rate for name, amt in h.winnings.items()}
        h.currency = '$'
