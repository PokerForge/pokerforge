from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional

@dataclass
class Player:
    name: str
    seat: Optional[int] = None
    stack: Optional[float] = None
    hole_cards: list[str] = field(default_factory=list)

@dataclass
class Action:
    street: str
    player: str
    action: str
    amount: Optional[float] = None

@dataclass
class Hand:
    hand_id: str
    game_type: str = "Texas Hold'em"
    currency: str = "£"
    small_blind: Optional[float] = None
    big_blind: Optional[float] = None
    # Preserved pre-conversion by core.currency.convert_hands_to_usd, so the
    # stakes label can stay in the original currency (matching PT4) even
    # though small_blind/big_blind/currency above get converted to USD for
    # BB/100 math (which must divide by a blind in the same currency as the
    # profit it's dividing).
    native_currency: Optional[str] = None
    native_small_blind: Optional[float] = None
    native_big_blind: Optional[float] = None
    played_at: Optional[datetime] = None
    table_name: Optional[str] = None
    table_size: Optional[int] = None
    button_seat: Optional[int] = None
    players: list[Player] = field(default_factory=list)
    board: list[str] = field(default_factory=list)
    actions: list[Action] = field(default_factory=list)
    total_pot: Optional[float] = None
    rake: Optional[float] = None
    winnings: dict[str, float] = field(default_factory=dict)
    invested: dict[str, float] = field(default_factory=dict)
    raw_text: Optional[str] = None
    source: Optional[str] = None
    unmatched_lines: list[str] = field(default_factory=list)
    # 'cash' or 'tournament' — a tournament's per-hand chip movements aren't
    # real money until the tournament ends, so this discriminator protects
    # every $-denominated aggregate (profit, BB/100) from silently summing
    # chip counts as dollars. tournament_id/buy_in/fee are None for cash.
    session_type: str = 'cash'
    tournament_id: Optional[str] = None
    buy_in: Optional[float] = None
    fee: Optional[float] = None

    @property
    def played_date(self) -> Optional[date]:
        return self.played_at.date() if self.played_at else None
