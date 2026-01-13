# src/common/rules.py

from typing import List
from .cards import Card

def card_value(card: Card) -> int:
    # Ace = 1 (simplified), 2-10 = face value, J/Q/K = 10
    if card.rank == 1:
        return 11
    if 2 <= card.rank <= 10:
        return card.rank
    return 10

def hand_value(hand: List[Card]) -> int:
    return sum(card_value(c) for c in hand)

def is_bust(hand: List[Card]) -> bool:
    return hand_value(hand) > 21

def dealer_should_hit(hand: List[Card]) -> bool:
    return hand_value(hand) < 17