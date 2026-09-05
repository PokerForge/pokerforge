"""Best-effort detection of common poker-client hand-history folders, to
pre-fill the first-run setup wizard so a new player doesn't have to
already know where to browse to.

Only Grosvenor Poker is covered for now — its data folder layout is the
one this app has actually confirmed against real exports (see
core/xml_hand_parser.py's docstring). Guessing at PokerStars/GGPoker/
CoinPoker/ACR's folder conventions without a real confirmed example would
risk pre-filling a wrong or nonexistent path — the same "never guess,
always validate" rule this project applies to parsers applies here too;
add a site here once its parser exists and its real folder layout has
been confirmed the same way."""
import os
from pathlib import Path


def detect_grosvenor_folders() -> list[str]:
    """Grosvenor stores each local player identity as its own subfolder
    under a shared install-wide data directory — this doesn't know the
    player's username in advance, so it checks every subfolder found
    there rather than guessing one."""
    base = Path(os.environ.get("LOCALAPPDATA", "")) / "Grosvenor Poker" / "data"
    if not base.is_dir():
        return []
    found = []
    try:
        for player_dir in sorted(base.iterdir()):
            candidate = player_dir / "History" / "Data" / "Tables"
            if candidate.is_dir():
                found.append(str(candidate))
    except OSError:
        return []
    return found


def detect_known_folders() -> list[str]:
    """Every auto-detectable hand-history folder across every site this
    module knows how to look for."""
    return detect_grosvenor_folders()
