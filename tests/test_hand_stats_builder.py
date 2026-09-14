"""database/hand_stats_builder.py's build_player_stat_rows — specifically
the GGPoker exclusion: GGPoker anonymizes every seat except the exporting
account's own (always literally "Hero", per core.ggpoker_hand_parser.
GGPOKER_HERO_LABEL) with a fresh random label every hand, so a stats row
for one of those labels can never be aggregated into a real, trackable
villain. This must be scoped to hand.source == 'ggpoker' specifically —
a real PokerStars export turned up plenty of real, persistent usernames
that happen to look exactly like GGPoker's random hex labels ("3033453",
"ed777221"), so excluding by name shape instead of by source would wrongly
hide real villains on other sites (see ui/hero_detect.py's docstring)."""
from models.hand import Hand, Player, Action
from database.hand_stats_builder import build_player_stat_rows


def _hand(players, source=None, hand_id="1"):
    return Hand(
        hand_id=hand_id, source=source, big_blind=0.10,
        players=[Player(name=n) for n in players],
        actions=[Action("PREFLOP", players[0], "Fold", None)],
    )


def test_ggpoker_hand_only_builds_a_stats_row_for_hero():
    hand = _hand(["aaa11111", "Hero", "bbb22222"], source="ggpoker")
    rows = build_player_stat_rows(hand)
    assert [r["player_name"] for r in rows] == ["Hero"]


def test_non_ggpoker_hand_builds_a_row_for_every_player():
    for source in (None, "ipoker", "pokerstars", "grosvenor_xml"):
        hand = _hand(["Hero", "Villain1", "Villain2"], source=source)
        rows = build_player_stat_rows(hand)
        assert {r["player_name"] for r in rows} == {"Hero", "Villain1", "Villain2"}, source


def test_ggpoker_hand_with_no_hero_seated_builds_no_rows():
    """Shouldn't happen in practice (every real GG export has the
    exporting account's own seat), but must not crash if it did."""
    hand = _hand(["aaa11111", "bbb22222"], source="ggpoker")
    rows = build_player_stat_rows(hand)
    assert rows == []


def test_winning_network_hand_only_builds_a_stats_row_for_hero():
    """Winning Network anonymizes opponents the exact same way GGPoker
    does (see core/winning_network_hand_parser.py's module docstring)."""
    hand = _hand(["Player1", "Hero", "Player2"], source="winning_network")
    rows = build_player_stat_rows(hand)
    assert [r["player_name"] for r in rows] == ["Hero"]


def test_ggpoker_hand_keeps_hero_row_after_alias_rename():
    """ui/hero_detect.py's normalize_hero_aliases runs before a hand ever
    reaches here and rewrites a known alias -- most commonly literally
    "Hero" itself, once the app has confirmed that's this hero's GGPoker
    identity -- to the real configured hero name. Without the `hero`
    param telling this function what that seat is NOW called, the
    GGPOKER_HERO_LABEL ('Hero') fallback can never match it again, and
    the hand silently produces zero stats rows -- not even for the hero's
    own seat. This was a real bug: it made every GGPoker/Winning Network
    hand invisible to Overview/Sessions/Stats/the Site filter once a
    "Hero" alias was registered."""
    hand = _hand(["aaa11111", "Akali8010", "bbb22222"], source="ggpoker")
    rows = build_player_stat_rows(hand, hero="Akali8010")
    assert [r["player_name"] for r in rows] == ["Akali8010"]


def test_ggpoker_hand_without_hero_param_cannot_find_a_renamed_seat():
    """Documents the fallback: omitting `hero` (e.g. a caller that hasn't
    been updated, or a hand from before any alias rename) still checks
    against the literal GGPOKER_HERO_LABEL only -- correct for a
    not-yet-renamed hand, but a renamed one like this legitimately
    produces no rows, which is exactly why every real call site now
    threads the resolved hero name through."""
    hand = _hand(["aaa11111", "Akali8010", "bbb22222"], source="ggpoker")
    rows = build_player_stat_rows(hand)
    assert rows == []


def _rake_hand(rake, hand_id="rk1"):
    """A opens, B calls, C folds preflop; A and B check the flop through.
    Rake is one shared, table-level figure -- only A and B (the ones
    still in when the flop came) should ever be credited any of it."""
    return Hand(
        hand_id=hand_id, source="ipoker", big_blind=0.10, rake=rake,
        board=["2h", "7d", "Kc"],
        players=[Player(name="A"), Player(name="B"), Player(name="C")],
        actions=[
            Action("PREFLOP", "A", "Raise", 0.30),
            Action("PREFLOP", "B", "Call", 0.30),
            Action("PREFLOP", "C", "Fold", None),
            Action("FLOP", "A", "Check", None),
            Action("FLOP", "B", "Check", None),
        ],
    )


def test_rake_is_split_evenly_among_players_who_saw_the_flop():
    rows = build_player_stat_rows(_rake_hand(rake=1.50))
    by_name = {r["player_name"]: r["rake"] for r in rows}
    assert round(by_name["A"], 2) == 0.75
    assert round(by_name["B"], 2) == 0.75


def test_folding_preflop_gets_zero_rake_not_none():
    """Zero, not None -- the hand DID have a recorded rake figure, this
    player just never contributed to the pot it was taken from."""
    rows = build_player_stat_rows(_rake_hand(rake=1.50))
    by_name = {r["player_name"]: r["rake"] for r in rows}
    assert by_name["C"] == 0.0


def test_rake_is_none_when_the_hand_has_no_rake_recorded():
    rows = build_player_stat_rows(_rake_hand(rake=None))
    assert all(r["rake"] is None for r in rows)


def _tournament_hand(players, hand_id="t1"):
    return Hand(
        hand_id=hand_id, source="pokerstars", big_blind=200.0,
        session_type="tournament", tournament_id="12345", buy_in=10.0, fee=1.0,
        players=[Player(name=n) for n in players],
        actions=[Action("PREFLOP", players[0], "Fold", None)],
        winnings={players[0]: 500.0},
    )


def test_tournament_hand_rake_stays_none_regardless_of_flop():
    """Tournament hands never populate hand.rake in the first place (a
    buy-in fee, tracked separately, isn't per-hand cash rake) -- confirm
    the defensive NULL-out still applies even if it somehow were set."""
    hand = _tournament_hand(["A", "B"])
    hand.rake = 5.0
    rows = build_player_stat_rows(hand)
    assert all(r["rake"] is None for r in rows)


def test_import_hands_threads_hero_through_to_ggpoker_exclusion(tmp_path):
    """End-to-end regression for the bug above, through the real
    PokerDatabase.import_hands path (not just build_player_stat_rows
    directly) -- a GGPoker hand whose seat has already been renamed (the
    same state ui/hero_detect.py's normalize_hero_aliases leaves it in)
    must still get a hand_player_stats row once `hero` is passed."""
    from database.repository import PokerDatabase
    db = PokerDatabase(tmp_path / "test.db")
    hand = _hand(["aaa11111", "Akali8010", "bbb22222"], source="ggpoker")
    db.import_hands([hand], ev_iterations=1, hero="Akali8010")

    rows = db.conn.execute(
        "SELECT player_name FROM hand_player_stats WHERE hand_id = ?", (hand.hand_id,)).fetchall()
    assert [r[0] for r in rows] == ["Akali8010"]
    db.close()


def test_rebuild_hand_player_stats_threads_hero_through_too(tmp_path):
    from database.repository import PokerDatabase
    db = PokerDatabase(tmp_path / "test.db")
    hand = _hand(["aaa11111", "Akali8010", "bbb22222"], source="ggpoker")
    db.import_hands([hand], ev_iterations=1, hero="Akali8010")

    db.rebuild_hand_player_stats(ev_iterations=1, hero="Akali8010")

    rows = db.conn.execute(
        "SELECT player_name FROM hand_player_stats WHERE hand_id = ?", (hand.hand_id,)).fetchall()
    assert [r[0] for r in rows] == ["Akali8010"]
    db.close()


def test_tournament_hand_nulls_profit_and_ev():
    """A tournament's per-hand chip movements aren't real money until the
    tournament itself pays out -- profit/ev stay NULL rather than
    silently blending chip counts into the same columns cash queries
    SUM() for $ totals (see database/queries.py's session_type='cash'
    guards, the actual protection this backstops)."""
    hand = _tournament_hand(["Hero", "Villain1"])
    rows = build_player_stat_rows(hand)
    hero_row = next(r for r in rows if r["player_name"] == "Hero")
    assert hero_row["profit"] is None
    assert hero_row["ev"] is None
    assert hero_row["session_type"] == "tournament"
    assert hero_row["tournament_id"] == "12345"


def test_tournament_hand_has_no_stakes_label():
    """A tournament's blind LEVEL isn't a cash "stake" -- NULL keeps
    tournament hands out of the Stakes dropdown and every
    stakes_label-keyed query."""
    hand = _tournament_hand(["Hero", "Villain1"])
    rows = build_player_stat_rows(hand)
    assert all(r["stakes_label"] is None for r in rows)


def test_cash_hand_still_computes_profit_and_ev():
    hand = Hand(
        hand_id="c1", source="pokerstars", big_blind=0.10, session_type="cash",
        players=[Player(name=n) for n in ("Hero", "Villain1")],
        actions=[Action("PREFLOP", "Hero", "Fold", None)],
        winnings={"Hero": 0.20},
    )
    rows = build_player_stat_rows(hand)
    hero_row = next(r for r in rows if r["player_name"] == "Hero")
    assert hero_row["profit"] == 0.20
    assert hero_row["session_type"] == "cash"
    assert hero_row["tournament_id"] is None
