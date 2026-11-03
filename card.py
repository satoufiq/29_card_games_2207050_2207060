from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Tuple

class Suit(str, Enum):
    HEARTS = "Hearts"
    DIAMONDS = "Diamonds"
    CLUBS = "Clubs"
    SPADES = "Spades"

    @property
    def symbol(self) -> str:
        symbols = {
            Suit.HEARTS: "♥",
            Suit.DIAMONDS: "♦",
            Suit.CLUBS: "♣",
            Suit.SPADES: "♠"
        }
        return symbols[self]

    @property
    def is_red(self) -> bool:
        return self in (Suit.HEARTS, Suit.DIAMONDS)

class Rank(str, Enum):
    SEVEN = "7"
    EIGHT = "8"
    QUEEN = "Q"
    KING = "K"
    TEN = "10"
    ACE = "A"
    NINE = "9"
    JACK = "J"

    @property
    def points(self) -> int:
        """Card points in 29 game: J=3, 9=2, A=1, 10=1, K=0, Q=0, 8=0, 7=0."""
        values = {
            Rank.JACK: 3,
            Rank.NINE: 2,
            Rank.ACE: 1,
            Rank.TEN: 1,
            Rank.KING: 0,
            Rank.QUEEN: 0,
            Rank.EIGHT: 0,
            Rank.SEVEN: 0
        }
        return values[self]

    @property
    def power(self) -> int:
        """
        Trick hierarchy order (lowest to highest):
        7 < 8 < Q < K < 10 < A < 9 < J
        """
        powers = {
            Rank.SEVEN: 1,
            Rank.EIGHT: 2,
            Rank.QUEEN: 3,
            Rank.KING: 4,
            Rank.TEN: 5,
            Rank.ACE: 6,
            Rank.NINE: 7,
            Rank.JACK: 8
        }
        return powers[self]

@dataclass(frozen=True)
class Card:
    suit: Suit
    rank: Rank

    @property
    def points(self) -> int:
        return self.rank.points

    @property
    def power(self) -> int:
        return self.rank.power

    @property
    def code(self) -> str:
        return f"{self.rank.value}{self.suit.name[0]}"

    def __str__(self) -> str:
        return f"{self.rank.value}{self.suit.symbol}"

    def __repr__(self) -> str:
        return f"Card({self.rank.value} of {self.suit.value})"

    def to_dict(self) -> dict:
        return {
            "suit": self.suit.value,
            "rank": self.rank.value,
            "symbol": self.suit.symbol,
            "points": self.points,
            "power": self.power,
            "is_red": self.suit.is_red,
            "code": f"{self.rank.value}{self.suit.name[0]}"
        }

    @staticmethod
    def sort_key(card: "Card") -> Tuple[int, int, int]:
        """
        Sort key to display and organize cards in hand:
        1. Suit group (alternating colors: Spades ♠, Hearts ♥, Clubs ♣, Diamonds ♦)
        2. Points descending (-points: J=3, 9=2, A=1, 10=1, K=0, Q=0, 8=0, 7=0)
        3. Power descending (-power: A before 10, K before Q before 8 before 7)
        """
        suit_order = {
            Suit.SPADES: 0,
            Suit.HEARTS: 1,
            Suit.CLUBS: 2,
            Suit.DIAMONDS: 3
        }
        return (suit_order.get(card.suit, 0), -card.points, -card.power)

    @classmethod
    def sort_cards(cls, cards: List["Card"]) -> List["Card"]:
        """Returns cards sorted by suit and then descending by points/power."""
        return sorted(cards, key=cls.sort_key)

    def __lt__(self, other: "Card") -> bool:
        if not isinstance(other, Card):
            return NotImplemented
        return self.sort_key(self) < self.sort_key(other)

    @staticmethod
    def from_str(s: str) -> "Card":
        """Parses a card string like 'JH', '10S', '9D', 'QC'."""
        s = s.strip().upper()
        suit_char = s[-1]
        rank_str = s[:-1]
        suit_map = {
            "H": Suit.HEARTS,
            "D": Suit.DIAMONDS,
            "C": Suit.CLUBS,
            "S": Suit.SPADES
        }
        rank_map = {r.value.upper(): r for r in Rank}
        return Card(suit=suit_map[suit_char], rank=rank_map[rank_str])

