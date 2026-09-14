"""Lightweight single-pass population summary for the villain LIST (not the
full 63-stat profile, which is only computed on-demand when a villain is
selected — see ui/compute_stats.py). Calling the full per-player aggregate
functions once per villain to build a list of hundreds of villains would
re-scan the whole dataset hundreds of times; this does one pass instead,
reusing analyze_preflop/analyze_showdown's per-hand result across every
player in that hand.

Validated against a real PT4 villain-pool export (villainreport.csv, 7,407
villains): 9 spot-checked villains matched hand counts exactly in 7/9 cases
(the other 2 differed only by hands played after the CSV was exported —
more data, not a discrepancy), and every VPIP/PFR/3-Bet/Fold-to-3-Bet/WWSF
stat matched to within 0.01-0.15 percentage points, several exact to 2
decimals.
"""
from dataclasses import dataclass
from models.hand import Hand
from core.stats import analyze_preflop, analyze_showdown, compute_invested
from core.ggpoker_hand_parser import GGPOKER_HERO_LABEL
from ui.hero_detect import is_anon_placeholder


@dataclass
class PopulationRow:
    name: str
    hands: int = 0
    vpip_pfr_opp: int = 0
    vpip: int = 0
    pfr: int = 0
    three_bet_opp: int = 0
    three_bet: int = 0
    faced_3bet_opp: int = 0
    folded_to_3bet: int = 0
    reached_showdown: int = 0
    saw_flop: int = 0
    won_saw_flop: int = 0
    total_profit: float = 0.0

    @staticmethod
    def _pct(made, opp):
        return round(100.0 * made / opp, 2) if opp else None

    @property
    def vpip_pct(self): return self._pct(self.vpip, self.vpip_pfr_opp)

    @property
    def pfr_pct(self): return self._pct(self.pfr, self.vpip_pfr_opp)

    @property
    def three_bet_pct(self): return self._pct(self.three_bet, self.three_bet_opp)

    @property
    def fold_3bet_pct(self): return self._pct(self.folded_to_3bet, self.faced_3bet_opp)

    @property
    def wwsf_pct(self): return self._pct(self.won_saw_flop, self.saw_flop)

    @property
    def wtsd_pct(self): return self._pct(self.reached_showdown, self.saw_flop)


def build_population_summary(hands: list[Hand], hero: str) -> dict[str, PopulationRow]:
    rows: dict[str, PopulationRow] = {}
    for hand in hands:
        preflop = analyze_preflop(hand)
        showdown = analyze_showdown(hand)
        invested = compute_invested(hand)

        for p in hand.players:
            if p.name == hero or is_anon_placeholder(p.name):
                continue
            # GGPoker and Winning Network both anonymize every seat except
            # the exporting account's own (always literally "Hero") --
            # never a real, trackable villain. Scoped by source, not name
            # shape (see ui/hero_detect.py's ANON_PLACEHOLDER docstring for
            # why).
            if hand.source in ('ggpoker', 'winning_network') and p.name != GGPOKER_HERO_LABEL:
                continue
            row = rows.setdefault(p.name, PopulationRow(p.name))
            row.hands += 1
            pf = preflop.get(p.name)
            if pf:
                row.vpip_pfr_opp += pf.vpip_pfr_opp
                row.vpip += pf.vpip
                row.pfr += pf.pfr
                row.three_bet_opp += pf.three_bet_opp
                row.three_bet += pf.three_bet
                row.faced_3bet_opp += pf.faced_3bet_opp
                row.folded_to_3bet += pf.folded_to_3bet
            sd = showdown.get(p.name)
            if sd:
                row.saw_flop += sd.saw_flop
                row.reached_showdown += sd.reached_showdown
                row.won_saw_flop += sd.saw_flop and sd.won_hand
            row.total_profit += hand.winnings.get(p.name, 0.0) - invested.get(p.name, 0.0)

    return rows
