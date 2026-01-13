# cards.py
from __future__ import annotations
from dataclasses import dataclass
from typing import List, Tuple
import random

SUITS = ["♠", "♥", "♦", "♣"]
RANKS = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]
FULL_DECK: List[Tuple[str, str]] = [(r, s) for s in SUITS for r in RANKS]

@dataclass(frozen=True)
class Card:
    rank: str
    suit: str

    @property
    def is_red(self) -> bool:
        return self.suit in ("♥", "♦")

class Deck:
    def __init__(self, *, seed=None):
        self._rng = random.Random(seed)
        self.cards: List[Card] = [Card(r, s) for (r, s) in FULL_DECK]
        self.shuffle()

    def shuffle(self) -> None:
        self._rng.shuffle(self.cards)

    def take(self, n: int) -> List[Card]:
        n = max(0, min(n, len(self.cards)))
        out = self.cards[:n]
        self.cards = self.cards[n:]
        return out