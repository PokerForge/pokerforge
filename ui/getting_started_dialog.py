"""Help > Getting Started — a plain-language glossary for the stats this
app shows everywhere (Overview, Stats, Population). Written for someone
who plays poker but hasn't necessarily used a HUD/tracker before; ranges
quoted are the same lo/hi benchmarks ui/stat_registry.py uses for its
green/orange/red color-coding, not separately invented numbers."""
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QScrollArea, QWidget, QDialogButtonBox

from ui.theme import STYLE, lbl

_GLOSSARY = [
    ("VPIP — Voluntarily Put $ In Pot",
     "How often you play a hand preflop instead of folding for free. "
     "Winning regs are typically around 22-26%. Much higher and you're "
     "likely playing too many weak hands; much lower and you're probably "
     "too easy to read (only betting when you have something)."),
    ("PFR — Preflop Raise",
     "How often you raise preflop rather than just calling. Typically "
     "17-21%. The gap between VPIP and PFR shows how often you enter a "
     "pot passively — a small gap means you're aggressive when you do "
     "play; a large one usually means too much limping/calling."),
    ("3-Bet",
     "How often you re-raise someone else's preflop raise. Typically "
     "8-10%. Too low and opponents can raise you off your blinds for "
     "free; too high and you're re-raising with hands that can't stand "
     "the heat when someone re-raises you back."),
    ("Fold to 3-Bet",
     "How often you fold when someone re-raises YOUR opening raise. "
     "Typically 50-60%. Much higher than that and observant opponents "
     "will start 3-betting you relentlessly, since they know you'll fold."),
    ("4-Bet",
     "How often you re-raise again after facing a 3-bet — a much smaller, "
     "more polarized range than your opening range."),
    ("WTSD — Went To Showdown",
     "Of the hands where you saw a flop, how often you make it all the "
     "way to showdown. Typically 26-32%. Very high usually means you're "
     "calling too much down to the river without enough of a hand."),
    ("W$SD — Won $ at Showdown",
     "Of the hands that DO reach showdown, how often you win them. "
     "Typically 50-56%. Below that consistently suggests you're reaching "
     "showdown with hands too weak to win."),
    ("WWSF — Won When Saw Flop",
     "Of the hands where you saw a flop, how often you win the pot at "
     "all — whether by showdown or by making everyone else fold. "
     "Typically 38-46%."),
    ("C-Bet — Continuation Bet",
     "How often you bet the flop after being the preflop raiser, "
     "\"continuing\" your preflop aggression regardless of whether the "
     "flop actually helped you."),
    ("Fold to C-Bet",
     "How often you fold when facing a continuation bet from the "
     "preflop raiser."),
    ("AF — Aggression Factor",
     "The ratio of your bets+raises to your calls (checks aren't "
     "counted). Higher means you tend to bet/raise rather than just call "
     "when you do get involved in a pot."),
    ("AFq — Aggression Frequency",
     "What percentage of your non-check actions are bets/raises rather "
     "than calls — the same idea as AF, expressed as a percentage instead "
     "of a ratio."),
    ("Steal Attempt",
     "How often you raise first-in from late position (CO/BTN/SB) when "
     "nobody has entered the pot yet, specifically trying to win the "
     "blinds uncontested."),
    ("Fold to Steal",
     "How often you fold your blind when facing a steal attempt from "
     "late position. Typically 55-65%."),
    ("BB/100",
     "Your win rate in big blinds per 100 hands — the standard way to "
     "measure results independent of what stakes you're playing, so a "
     "session at $1/$2 and a session at $5/$10 can be compared fairly."),
    ("EV BB/100",
     "Like BB/100, but based on your equity at all-in moments rather "
     "than what actually happened afterward — this strips out the "
     "short-term luck of who actually won a given all-in, showing your "
     "underlying edge more clearly over a small sample."),
]


class GettingStartedDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(STYLE)
        self.setWindowTitle("Getting Started")
        self.resize(640, 560)
        self.setModal(True)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(12)

        lay.addWidget(lbl(
            "PokerForge tracks every hand your poker client saves and turns it "
            "into stats across four tabs: Overview (your results over time), "
            "Sessions (a detailed hand-by-hand grid), Stats (your own game "
            "broken down by position, with auto-detected leaks), and "
            "Population (how any opponent you've played actually plays). "
            "Below is what the stats you'll see everywhere actually mean.",
            size=13))

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea{border:none;background:transparent;}")
        inner = QWidget()
        inner_lay = QVBoxLayout(inner)
        inner_lay.setSpacing(14)
        for title, body in _GLOSSARY:
            inner_lay.addWidget(lbl(title, size=13, bold=True))
            desc = lbl(body, size=12, dim=True)
            desc.setWordWrap(True)
            inner_lay.addWidget(desc)
        inner_lay.addStretch()
        scroll.setWidget(inner)
        lay.addWidget(scroll, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(self.accept)
        lay.addWidget(buttons)
