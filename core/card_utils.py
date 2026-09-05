RANKS = ['2','3','4','5','6','7','8','9','T','J','Q','K','A']
SUITS = ['♣','♦','♥','♠']
HH_SUIT_MAP = {'C':'♣','D':'♦','H':'♥','S':'♠'}


def decode_card(code: int | None) -> str | None:
    if not code:
        return None
    idx = code - 1
    if idx < 0 or idx >= 52:
        raise ValueError(f"Invalid card code: {code}")
    return RANKS[idx % 13] + SUITS[idx // 13]


def hh_card_to_display(code: str | None) -> str | None:
    if not code:
        return None
    suit = HH_SUIT_MAP.get(code[0])
    if suit is None:
        raise ValueError(f"Unknown suit in card: {code}")
    rank = 'T' if code[1:] == '10' else code[1:]
    if rank not in RANKS:
        raise ValueError(f"Unknown rank in card: {code}")
    return rank + suit


def decode_board(*codes: int | None) -> list[str]:
    return [c for code in codes if (c := decode_card(code))]
