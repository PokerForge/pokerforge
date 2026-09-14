"""Display metadata for every stat the engine computes: label, category,
display kind, and a population lo/hi range for color-coding where a real
benchmark is known. Mirrors poker_dashboard_legacy.py's STAT_REGISTRY
pattern (and reuses several of its actual lo/hi values where the same
stat exists), but the ids and underlying computation are entirely our own.

kind:
  'pct'    — a percentage; color-coded green/orange/red against lo/hi if
             given, otherwise plain (no population benchmark established yet).
  'signed' — a profit-like rate (e.g. bb/100): green if >= 0, red if < 0.
  'plain'  — a bare number with no inherent "good/bad" direction (e.g. AF).
"""
STAT_CATEGORIES = ["Overall", "Preflop", "Flop", "Turn", "River"]

STAT_REGISTRY = [
    # ── Overall ──
    dict(id="bb100", label="BB/100", category="Overall", kind="signed"),
    dict(id="ev_bb100", label="EV BB/100", category="Overall", kind="signed"),
    dict(id="wtsd", label="WTSD", category="Overall", kind="pct", lo=26, hi=32),
    dict(id="wsd", label="W$SD", category="Overall", kind="pct", lo=50, hi=56),
    dict(id="wwsf", label="WWSF", category="Overall", kind="pct", lo=38, hi=46),
    dict(id="total_af", label="Total AF", category="Overall", kind="plain"),
    dict(id="total_afq", label="Total AFq", category="Overall", kind="pct"),

    # ── Preflop ──
    dict(id="vpip", label="VPIP", category="Preflop", kind="pct", lo=22, hi=26),
    dict(id="pfr", label="PFR", category="Preflop", kind="pct", lo=17, hi=21),
    dict(id="three_bet", label="3-Bet", category="Preflop", kind="pct", lo=8, hi=10),
    dict(id="fold_3bet", label="Fold 3-Bet", category="Preflop", kind="pct", lo=50, hi=60),
    dict(id="four_bet", label="4-Bet", category="Preflop", kind="pct"),
    dict(id="fold_4bet", label="Fold 4-Bet", category="Preflop", kind="pct", lo=45, hi=55),
    dict(id="squeeze", label="Squeeze", category="Preflop", kind="pct"),
    dict(id="raise_vs_squeeze", label="Raise vs Squeeze", category="Preflop", kind="pct"),
    dict(id="fold_to_squeeze", label="Fold to Squeeze", category="Preflop", kind="pct"),
    dict(id="limp", label="Limp", category="Preflop", kind="pct"),
    dict(id="limp_call", label="Limp-Call", category="Preflop", kind="pct"),
    dict(id="steal_att", label="Steal Attempt", category="Preflop", kind="pct"),
    dict(id="steal_success", label="Steal Success", category="Preflop", kind="pct"),
    dict(id="fold_to_steal", label="Fold to Steal", category="Preflop", kind="pct", lo=55, hi=65),
    dict(id="preflop_af", label="Preflop AF", category="Preflop", kind="plain"),
    dict(id="preflop_afq", label="Preflop AFq", category="Preflop", kind="pct"),
]

# (lo, hi) per street, taken from poker_dashboard_legacy.py's own STAT_REGISTRY
# where an equivalent stat existed there; None where it never had a benchmark.
_STREET_THRESHOLDS = {
    "flop":  {"cbet": (55, 65), "fold_cbet": (45, 55), "xr": (8, 12), "fold_xr": (55, 65)},
    "turn":  {"cbet": (50, 60), "fold_cbet": (45, 55), "xr": (6, 10), "fold_xr": (55, 65)},
    "river": {},
}
_STREET_STAT_TEMPLATE = [
    ("cbet", "Cbet"), ("fold_cbet", "Fold to Cbet"), ("xr", "Check-Raise"), ("fold_xr", "Fold to XR"),
    ("donk", "Donk Bet"), ("fold_donk", "Fold to Donk"), ("fold_bet", "Fold to Bet"),
    ("fold_2bet", "Fold to 2-Bet"), ("fold_3bet_street", "Fold to 3-Bet"),
    ("float", "Float"), ("fold_float", "Fold to Float"),
]

for _street, _cat in (("flop", "Flop"), ("turn", "Turn"), ("river", "River")):
    for _key, _label in _STREET_STAT_TEMPLATE:
        entry = dict(id=f"{_street}_{_key}", label=_label, category=_cat, kind="pct")
        lo_hi = _STREET_THRESHOLDS[_street].get(_key)
        if lo_hi:
            entry["lo"], entry["hi"] = lo_hi
        STAT_REGISTRY.append(entry)
    STAT_REGISTRY.append(dict(id=f"{_street}_af", label=f"{_cat} AF", category=_cat, kind="plain"))
    STAT_REGISTRY.append(dict(id=f"{_street}_afq", label=f"{_cat} AFq", category=_cat, kind="pct"))

STAT_REGISTRY.append(dict(id="turn_probe", label="Probe", category="Turn", kind="pct"))
STAT_REGISTRY.append(dict(id="turn_fold_probe", label="Fold to Probe", category="Turn", kind="pct"))
STAT_REGISTRY.append(dict(id="river_probe", label="Probe", category="River", kind="pct"))
STAT_REGISTRY.append(dict(id="river_fold_probe", label="Fold to Probe", category="River", kind="pct"))

STAT_REGISTRY_BY_ID = {s["id"]: s for s in STAT_REGISTRY}


def pop_avg(stat: dict):
    """"Pop avg" as shown in the legacy dashboard's villain profile is just
    the midpoint of a stat's lo/hi color-coding range, not a live-computed
    population average — confirmed by cross-checking the reference
    screenshot's numbers against poker_dashboard_legacy.py's own thresholds
    (e.g. VPIP's displayed "Pop avg: 24%" = (22+26)/2 exactly)."""
    lo, hi = stat.get('lo'), stat.get('hi')
    return round((lo + hi) / 2, 1) if lo is not None and hi is not None else None
