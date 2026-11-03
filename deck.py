import random
from typing import List, Tuple, Optional, Dict
from card import Card, Suit, Rank

class Deck:
    def __init__(self, seed: Optional[int] = None, biased: bool = False):
        self.seed = seed
        # Unseeded games use the operating system's randomness; seeds keep tests reproducible.
        self.rng = random.Random(seed) if seed is not None else random.SystemRandom()
        self.biased = biased
        self.first_player = 1   # who receives the first card (player after the dealer, clockwise)
        self.cards: List[Card] = self._create_deck()
        self.shuffle()

    def _create_deck(self) -> List[Card]:
        cards = []
        for suit in Suit:
            for rank in Rank:
                cards.append(Card(suit=suit, rank=rank))
        return cards

    def shuffle(self, biased: Optional[bool] = None):
        use_bias = self.biased if biased is None else biased
        if use_bias:
            self._biased_shuffle()
        else:
            self.rng.shuffle(self.cards)

    def _biased_shuffle(self):
        """
        Action deal / Clump shuffle:
        Simulates authentic physical card play where cards are gathered from previous tricks
        (grouped by suits) and shuffled via multiple imperfect riffles and cuts.
        Produces realistic suit clustering and voids without artificially guaranteeing that
        all players get all types/suits of cards. Allows natural variance, such as 4 Jacks,
        single-suit hands, and complete voids in opponent teams.
        """
        deck_cards: List[Card] = []
        suits = list(Suit)
        self.rng.shuffle(suits)
        for s in suits:
            suit_cards = [Card(s, r) for r in Rank]
            self.rng.shuffle(suit_cards)
            deck_cards.extend(suit_cards)

        def riffle(d: List[Card]) -> List[Card]:
            cut = self.rng.randint(13, 19)
            left = list(d[:cut])
            right = list(d[cut:])
            out: List[Card] = []
            while left or right:
                p_left = len(left) / (len(left) + len(right))
                side = left if self.rng.random() < p_left else right
                k = min(len(side), self.rng.choices([1, 2, 3, 4], weights=[3, 3, 2, 1])[0])
                out.extend(side[:k])
                del side[:k]
            return out

        # 3 riffle shuffles simulate action/clump shuffling
        for _ in range(3):
            deck_cards = riffle(deck_cards)

        # Authentic cut
        cut_point = self.rng.randint(4, 28)
        self.cards = deck_cards[cut_point:] + deck_cards[:cut_point]

    def _order(self) -> List[int]:
        """Clockwise dealing order starting with first_player."""
        return [(self.first_player + k) % 4 for k in range(4)]

    def deal_stage_one(self) -> List[List[Card]]:
        """
        Deals 4 cards to each player, one card at a time, clockwise from first_player.
        Returned hands are sorted by suit and points.
        """
        if len(self.cards) < 32:
            self.cards = self._create_deck()
            self.shuffle()
        hands = [[], [], [], []]
        for _ in range(4):
            for p in self._order():
                hands[p].append(self.cards.pop(0))
        return [Card.sort_cards(h) for h in hands]

    def deal_stage_two(self, existing_hands: List[List[Card]]) -> List[List[Card]]:
        """Deals the remaining 4 cards each, one at a time, clockwise."""
        for _ in range(4):
            for p in self._order():
                existing_hands[p].append(self.cards.pop(0))
        return [Card.sort_cards(h) for h in existing_hands]

    def deal_stage_two_with_seventh_card(
        self, existing_hands: List[List[Card]], seventh_card_player_id: Optional[int] = None
    ) -> Tuple[List[List[Card]], Optional[Card]]:
        """
        Deals the remaining 4 cards each, one at a time, clockwise. The bidder's 7th card
        overall (their 3rd card of this stage) is set aside face down as the trump card.
        """
        seventh_card: Optional[Card] = None
        for rnd in range(4):
            for p in self._order():
                c = self.cards.pop(0)
                if p == seventh_card_player_id and rnd == 2:
                    seventh_card = c
                else:
                    existing_hands[p].append(c)
        sorted_hands = [Card.sort_cards(h) for h in existing_hands]
        return sorted_hands, seventh_card

    def deal_full(self) -> Tuple[List[List[Card]], List[List[Card]]]:
        """
        Helper returning (stage_1_hands, full_8_card_hands).
        """
        self.cards = self._create_deck()
        self.shuffle()
        stage_1 = self.deal_stage_one()
        stage_2_existing = [list(h) for h in stage_1]
        full_hands = self.deal_stage_two(stage_2_existing)
        return stage_1, full_hands

    def remaining_count(self) -> int:
        return len(self.cards)

