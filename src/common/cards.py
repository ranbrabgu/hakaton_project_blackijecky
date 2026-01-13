# src/common/cards.py

import random
from dataclasses import dataclass
from typing import List, Tuple

SUITS = ["H", "D", "C", "S"]  # must match protocol encoding
RANKS = list(range(1, 14))   # 1..13 (Ace..King in some mapping)


@dataclass(frozen=True)
class Card:
    rank: int  # 1..13
    suit: str  # "H","D","C","S"


class Deck:
    def __init__(self) -> None:
        self._cards: List[Card] = [Card(r, s) for s in SUITS for r in RANKS]
        random.shuffle(self._cards)

    def draw(self) -> Card:
        if not self._cards:
            # reshuffle if empty (simple)
            self.__init__()
        return self._cards.pop()