"""Player-type classification and exploit-note generation, ported from
poker_dashboard_legacy.py's classify_player()/generate_leaks() — pure
functions of stat values, adapted to our own stat-value dict's key names."""
from ui.theme import DIM, ACCENT2, GREEN, ORANGE, RED


def classify_player(vpip, pfr, threebet, wtsd):
    if vpip is None:
        return "Unknown", DIM
    aggr = pfr / vpip * 100 if vpip else 0
    if vpip < 15:                          return "Nit \U0001f9ca", "#88c0d0"
    if vpip < 22 and aggr > 70:            return "Tight Reg \U0001f3af", ACCENT2
    if 22 <= vpip <= 28 and aggr >= 65:    return "Winning Reg ⚡", GREEN
    if vpip > 35 and aggr < 50:            return "Calling Station \U0001f4de", ORANGE
    if vpip > 30 and pfr > 25:             return "LAG \U0001f525", RED
    if vpip > 30:                          return "Fish \U0001f41f", "#f08c00"
    if vpip > 28 and aggr < 55:            return "Passive Reg \U0001f634", DIM
    return "Reg \U0001f0cf", ACCENT2


MIN_LEAK_SAMPLE = 20


def generate_leaks(values: dict, opp_counts: dict | None = None) -> list[tuple[str, str, str, str | None]]:
    """`values` uses our own stat ids (see ui/stat_registry.py), e.g.
    'three_bet' not legacy's 'threebet', 'flop_fold_cbet' not 'fold_fcbet'.

    `opp_counts` gates each note behind MIN_LEAK_SAMPLE opportunities —
    same reasoning as generate_hero_leaks below: an "exploit" asserted
    from a handful of hands is noise, not a finding, and this app has
    otherwise been careful not to claim more than the sample supports.
    Omitting opp_counts entirely (the default) skips gating, for the one
    caller that doesn't have it computed.

    Each entry's 4th element is a leak_id into database.queries.
    LEAK_HAND_CONDITIONS, the same lookup generate_hero_leaks's entries
    use — the underlying hand conditions ("this player VPIP'd", "folded
    to a 3-bet") don't depend on which player they're being read for."""
    opp_counts = opp_counts or {}
    leaks = []
    if not values:
        return leaks

    def enough(stat_id):
        return opp_counts.get(stat_id, MIN_LEAK_SAMPLE) >= MIN_LEAK_SAMPLE

    vpip = values.get('vpip')
    pfr = values.get('pfr')
    tb = values.get('three_bet')
    # Narrower than the plain "fold_3bet" percentage shown in Stats/
    # Population — restricted to hands where THIS PLAYER opened and got
    # re-raised, since "3-Bet them relentlessly" only follows from how
    # they react when their own raise is challenged, not from folds to a
    # pot someone else already raised-and-3-bet before they ever acted.
    f3 = values.get('fold_3bet_as_raiser')
    fb = values.get('four_bet')
    f4 = values.get('fold_4bet')
    wtsd = values.get('wtsd')
    wsd = values.get('wsd')
    fcbet = values.get('flop_fold_cbet')

    if tb is not None and enough('three_bet'):
        if tb < 4:
            leaks.append(("\U0001f534", "Extremely low 3-Bet",
                           "Their 3-bets are always premium hands. Fold everything but AA/KK/AK vs their 3-bets.",
                           "three_bet_low"))
        elif tb < 7:
            leaks.append(("\U0001f7e0", "Low 3-Bet",
                           "Steal aggressively — they rarely push back preflop.", "three_bet_low"))

    if f3 is not None and enough('fold_3bet_as_raiser'):
        if f3 > 70:
            leaks.append(("\U0001f534", "Over-folds to 3-Bets",
                           "3-Bet them relentlessly from any position. They give up too easily.", "fold_3bet_high"))
        elif f3 > 60:
            leaks.append(("\U0001f7e0", "Folds too much to 3-Bets",
                           "Increase 3-bet frequency — they're not defending enough.", "fold_3bet_high"))
        elif f3 < 40:
            leaks.append(("\U0001f535", "Defends vs 3-Bets well",
                           "Tighten your 3-bet range — only 3-bet for value vs this player.", "fold_3bet_good"))

    if fb is not None and enough('four_bet') and fb > 12:
        leaks.append(("\U0001f534", "Over-4-Bets",
                       "They're bluffing 4-bets — call wider or 5-bet shove with your bluff catchers.",
                       "four_bet_high"))

    if f4 is not None and enough('fold_4bet') and f4 > 65:
        leaks.append(("\U0001f534", "Folds to 4-Bets",
                       "4-Bet bluff them frequently — they can't handle the pressure.", "fold_4bet_high"))

    if fcbet is not None and enough('flop_fold_cbet'):
        if fcbet > 60:
            leaks.append(("\U0001f534", "Folds to Cbets",
                           "Cbet wide vs this player — they give up too often on the flop.", "fold_cbet_high"))
        elif fcbet > 50:
            leaks.append(("\U0001f7e0", "Above average fold to Cbet",
                           "Slightly increase c-bet frequency vs this player.", "fold_cbet_high"))
        elif fcbet < 35:
            leaks.append(("\U0001f535", "Calls Cbets wide",
                           "Only c-bet for value — they float too much. Check back marginal hands.",
                           "fold_cbet_low"))

    if wtsd is not None and enough('wtsd'):
        if wtsd > 36:
            leaks.append(("\U0001f534", "Goes to showdown too often",
                           "Value bet relentlessly — they can't fold. Never bluff this player.", "wtsd_high"))
        elif wtsd > 30:
            leaks.append(("\U0001f7e0", "Slightly high WTSD",
                           "Lean towards value bets. Bluffs are less profitable vs this player.", "wtsd_high"))
        elif wtsd < 22:
            leaks.append(("\U0001f534", "Over-folds on later streets",
                           "Bluff rivers and turns — they give up too easily postflop.", "wtsd_low"))

    if wsd is not None and enough('wsd') and wsd < 45:
        leaks.append(("\U0001f534", "Loses at showdown",
                       "They go to showdown with weak hands — bluff catch and thin value bet.", "wsd_low"))

    if vpip is not None and enough('vpip'):
        if vpip > 40:
            leaks.append(("\U0001f534", "Extremely loose preflop",
                           "They play too many hands — their range is weak. Value bet thinly.", "vpip_loose"))
        elif vpip > 30:
            leaks.append(("\U0001f7e0", "Loose preflop",
                           "Their range is wider than average — exploit with strong hands.", "vpip_loose"))

    if not leaks:
        leaks.append(("\U0001f7e2", "No major leaks detected",
                       "This appears to be a solid player on the current sample. Play closer to GTO vs them.",
                       None))

    return leaks


def generate_hero_leaks(values: dict, opp_counts: dict | None = None) -> list[tuple[str, str, str, str | None]]:
    """Self-facing version of generate_leaks() — same thresholds, but the
    advice is written as "what to change about your own play" rather than
    "how to exploit this tendency in someone else", since those read as
    opposite instructions for the same underlying number (e.g. a villain's
    low fold-to-cbet means "value bet them thinner"; the SAME stat being
    low for you means "you're calling too wide, tighten up").

    Any stat whose opportunity count (opp_counts) is below MIN_LEAK_SAMPLE
    is skipped entirely rather than flagged — a 3-bet% built on 8 hands
    isn't a leak, it's noise, and asserting one from it would be exactly
    the kind of guess this project has otherwise been careful to avoid.

    Each entry's 4th element is a `leak_id` for database.queries.
    LEAK_HAND_CONDITIONS — the hand list a click on this leak should show
    isn't always the stat's own raw numerator: "Low 3-Bet" is more useful
    shown as the hands you COULD have 3-bet and didn't, not the rare ones
    you did; "Low win rate at showdown" is more useful shown as the
    showdowns you lost, not the ones you won. `None` means not drillable
    (the no-leaks fallback)."""
    opp_counts = opp_counts or {}
    leaks = []
    if not values:
        return leaks

    def enough(stat_id):
        return opp_counts.get(stat_id, MIN_LEAK_SAMPLE) >= MIN_LEAK_SAMPLE

    vpip = values.get('vpip')
    pfr = values.get('pfr')
    tb = values.get('three_bet')
    # See generate_leaks above — restricted to hands where hero opened and
    # got re-raised, not cold folds to a pot someone else already
    # raised-and-3-bet before hero ever acted.
    f3 = values.get('fold_3bet_as_raiser')
    fb = values.get('four_bet')
    f4 = values.get('fold_4bet')
    fsteal = values.get('fold_to_steal')
    fcbet = values.get('flop_fold_cbet')
    wtsd = values.get('wtsd')
    wsd = values.get('wsd')

    if vpip is not None and pfr is not None and enough('vpip'):
        if vpip > 40:
            leaks.append(("\U0001f534", "Very loose preflop (VPIP)",
                           "You're voluntarily playing a lot of hands. Tighten your opening range, "
                           "especially from early position.", "vpip_loose"))
        elif vpip > 30:
            leaks.append(("\U0001f7e0", "Slightly loose preflop (VPIP)",
                           "Your range is a bit wide — trim the weaker end of it.", "vpip_loose"))
        elif vpip < 16:
            leaks.append(("\U0001f7e0", "Very tight preflop (VPIP)",
                           "You may be folding too much equity away preflop — look for profitable spots "
                           "you're passing up, especially in late position.", "vpip_tight"))
        if pfr and vpip and pfr < vpip * 0.65:
            leaks.append(("\U0001f534", "Limping too much",
                           "PFR is well below VPIP — you're entering pots passively instead of raising. "
                           "Convert limps into opens or folds.", "limping"))

    if tb is not None and enough('three_bet'):
        if tb < 4:
            leaks.append(("\U0001f534", "Extremely low 3-Bet",
                           "You're almost never applying preflop pressure. Widen your 3-bet range, "
                           "particularly as a bluff from late position/the blinds.", "three_bet_low"))
        elif tb < 7:
            leaks.append(("\U0001f7e0", "Low 3-Bet",
                           "Consider 3-betting a bit more — opponents can play back at you cheaply "
                           "knowing you rarely do.", "three_bet_low"))

    if f3 is not None and enough('fold_3bet_as_raiser'):
        if f3 > 70:
            leaks.append(("\U0001f534", "Over-folding to 3-Bets",
                           "You're an easy target for 3-bet bluffs. Defend (call or 4-bet) more often, "
                           "especially in position.", "fold_3bet_high"))
        elif f3 > 60:
            leaks.append(("\U0001f7e0", "Folding a bit too much to 3-Bets",
                           "Loosen your continuing range slightly against 3-bets.", "fold_3bet_high"))
        elif f3 < 40:
            leaks.append(("\U0001f535", "Defending well against 3-Bets",
                           "You continue against 3-bets at a healthy rate — no change needed here.",
                           "fold_3bet_good"))

    if fb is not None and enough('four_bet'):
        if fb > 12:
            leaks.append(("\U0001f7e0", "High 4-Bet frequency",
                           "Make sure your 4-bets are mostly for value, or that your bluffs are actually "
                           "getting through — over-4-betting light gets expensive against a player who calls.",
                           "four_bet_high"))

    if f4 is not None and enough('fold_4bet'):
        if f4 > 65:
            leaks.append(("\U0001f534", "Over-folding to 4-Bets",
                           "You're giving up too easily when 4-bet. Either tighten your 3-bet range so you "
                           "can stand a 4-bet, or defend a bit wider.", "fold_4bet_high"))

    if fsteal is not None and enough('fold_to_steal'):
        if fsteal > 75:
            leaks.append(("\U0001f534", "Over-folding your blinds to steals",
                           "You're giving up your blinds too easily against late-position opens. "
                           "Defend (call or 3-bet) more from the blinds.", "fold_steal_high"))

    if fcbet is not None and enough('flop_fold_cbet'):
        if fcbet > 60:
            leaks.append(("\U0001f534", "Folding too much to flop C-Bets",
                           "You're giving up too often when facing a continuation bet. Look for spots to "
                           "float or raise as a bluff, not just fold.", "fold_cbet_high"))
        elif fcbet > 50:
            leaks.append(("\U0001f7e0", "Slightly high fold to flop C-Bet",
                           "Loosen your continuing range facing c-bets a little.", "fold_cbet_high"))
        elif fcbet < 35:
            leaks.append(("\U0001f535", "Rarely folds to flop C-Bets",
                           "You're a sticky opponent to bluff — good if it's backed by a solid W$SD "
                           "below, worth checking if it isn't.", "fold_cbet_low"))

    if wtsd is not None and enough('wtsd'):
        if wtsd > 36:
            leaks.append(("\U0001f7e0", "Reaching showdown often",
                           "Check your W$SD below — if it's not comfortably above 50%, you may be "
                           "calling down too light.", "wtsd_high"))
        elif wtsd < 22:
            leaks.append(("\U0001f534", "Folding before showdown very often",
                           "You may be over-folding on the turn/river. Look for more bluff-catches and "
                           "apply pressure with your strong hands instead of just betting for value.",
                           "wtsd_low"))

    if wsd is not None and enough('wsd'):
        if wsd < 45:
            leaks.append(("\U0001f534", "Low win rate at showdown",
                           "When you do reach showdown, you're losing more often than expected — you may "
                           "be calling down with hands that are frequently second-best. Tighten your "
                           "showdown-bound range.", "wsd_low"))

    if not leaks:
        leaks.append(("\U0001f7e2", "No major leaks detected",
                       "Nothing here crosses a red-flag threshold on the current sample — keep an eye on "
                       "this as you play more hands.", None))

    return leaks
