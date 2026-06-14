import random

from shared.constants import COLORS
from server.core.card import Card

def build_standard_deck() -> list[Card]:
    cards: list[Card] = []
    for color in COLORS:
        cards.append(Card(color, "0"))
        for n in range(1, 10):
            cards.append(Card(color, str(n)))
            cards.append(Card(color, str(n)))
        for action in ("Skip", "Reverse", "Draw"):
            cards.append(Card(color, action))
            cards.append(Card(color, action))
    for _ in range(4):
        cards.append(Card("Wild", "Wild"))
        cards.append(Card("Wild", "Wild_Draw"))
    return cards

class Deck:

    def __init__(self, seed: int | None = None):
        self._rng = random.Random(seed)
        self.draw_pile: list[Card] = build_standard_deck()
        self.discard_pile: list[Card] = []
        self.shuffle()

    def shuffle(self) -> None:
        self._rng.shuffle(self.draw_pile)

    def draw(self) -> Card:
        if not self.draw_pile:
            self._reshuffle_from_discard()
        return self.draw_pile.pop()

    def draw_many(self, n: int) -> list[Card]:
        return [self.draw() for _ in range(n)]

    def _reshuffle_from_discard(self) -> None:
        if len(self.discard_pile) <= 1:
            self.draw_pile = build_standard_deck()
            self.shuffle()
            return
        top = self.discard_pile.pop()
        self.draw_pile = self.discard_pile
        self.discard_pile = [top]
        self.shuffle()

    def play_to_discard(self, card: Card) -> None:
        self.discard_pile.append(card)

    @property
    def top_card(self) -> Card | None:
        return self.discard_pile[-1] if self.discard_pile else None

    def draw_first_discard(self) -> Card:
        while True:
            card = self.draw()
            if not card.is_number:
                self.draw_pile.insert(0, card)
                self.shuffle()
                continue
            return card
