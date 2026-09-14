"""Display names for a hand's `source` field — the internal values each
parser stamps on every Hand (core/hand_parser.py, core/xml_hand_parser.py,
core/pokerstars_hand_parser.py, core/ggpoker_hand_parser.py) are plumbing
names, not something to show a user in a filter dropdown."""

SITE_LABELS = {
    'ipoker': 'iPoker',
    'grosvenor_xml': 'Grosvenor',
    'pokerstars': 'PokerStars',
    'ggpoker': 'GGPoker',
    'winning_network': 'Winning Network',
}


def site_label(source: str) -> str:
    """Falls back to the raw value itself for anything not in the map
    above (an older/unrecognised source) rather than hiding it."""
    return SITE_LABELS.get(source, source)


_LABEL_TO_SOURCE = {v: k for k, v in SITE_LABELS.items()}


def site_value(label: str) -> str:
    """Reverses site_label() for the filter combobox — a label with no
    known mapping (shouldn't happen, but see site_label's own fallback)
    is assumed to already be the raw value."""
    return _LABEL_TO_SOURCE.get(label, label)
