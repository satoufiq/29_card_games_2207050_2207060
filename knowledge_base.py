from typing import Set, Dict, List, Tuple, Optional
import random
from card import Card, Suit
from game_state import GameState, Trick

class PredicateKnowledgeBase:
    """
    Predicate Logic Knowledge Representation:
    Tracks ground facts and infers constraints regarding hidden information:
      - HasCard(p, c) [Ground truth for viewer's own hand]
      - Played(p, c, trick_no)
      - Lead(p, suit, trick_no)
      - VoidInSuit(p, s) [Inferred constraint when p reneges on lead suit]
      - PossibleHolders(c) [Candidate set of players who could hold card c]
    """

    def __init__(self, viewer_id: int):
        self.viewer_id = viewer_id
        # Facts: sets of tuples
        self.played_facts: Set[Tuple[int, Card, int]] = set()  # (player, card, trick)
        self.void_facts: Set[Tuple[int, Suit]] = set()          # (player, suit)
        self.known_trump: Optional[Suit] = None
        
        # All 32 cards
        from card import Rank
        self.all_cards: Set[Card] = {Card(suit=s, rank=r) for s in Suit for r in Rank}

    def update_from_trick(self, trick: Trick):
        """
        Observes a trick's cards and infers VoidInSuit predicates.
        """
        lead_suit = trick.lead_suit
        for i, played in enumerate(trick.cards):
            self.played_facts.add((played.player_id, played.card, trick.trick_number))
            
            # If not leading and played a different suit, infer VoidInSuit(player, lead_suit)
            if i > 0 and lead_suit is not None and played.card.suit != lead_suit:
                self.void_facts.add((played.player_id, lead_suit))

    def update_trump(self, trump_suit: Suit):
        self.known_trump = trump_suit

    def is_player_void(self, player_id: int, suit: Suit) -> bool:
        return (player_id, suit) in self.void_facts

    def get_played_cards(self) -> Set[Card]:
        return {c for (_, c, _) in self.played_facts}

    def get_unseen_cards(
        self,
        own_hand: List[Card],
        current_trick: Optional[Trick] = None,
        known_extra: Optional[List[Card]] = None
    ) -> Set[Card]:
        """
        Cards that the viewer does not possess and have not yet been played.
        Strictly excludes cards currently in the active trick on the table.
        """
        played = self.get_played_cards()
        if current_trick and current_trick.cards:
            played = played | {pc.card for pc in current_trick.cards}
        own_set = set(own_hand)
        if known_extra:
            own_set = own_set | set(known_extra)
        return self.all_cards - played - own_set

    def sample_plausible_opponent_hands(
        self,
        viewer_id: int,
        own_hand: List[Card],
        hand_sizes: List[int],
        current_trick: Optional[Trick] = None,
        known_extra: Optional[List[Card]] = None,
        rng: Optional[random.Random] = None
    ) -> List[List[Card]]:
        """
        Determinization: Samples a plausible card assignment to the other 3 players,
        strictly from imperfect information without peeking into opponent hands:
          1. Only draws from cards genuinely unseen by viewer_id.
          2. Hand sizes match actual remaining counts.
          3. Respects known VoidInSuit facts from observation.
          4. Samples cards with true randomness to prevent deterministic biases.
        """
        if rng is None:
            rng = random.Random()

        unseen = list(self.get_unseen_cards(own_hand, current_trick=current_trick, known_extra=known_extra))
        rng.shuffle(unseen)

        # Target players are the other 3 players
        other_players = [p for p in range(4) if p != viewer_id]
        sampled_hands: Dict[int, List[Card]] = {p: [] for p in range(4)}
        sampled_hands[viewer_id] = list(own_hand)

        remaining_unseen = list(unseen)

        # Distribute cards respecting void constraints
        # Most constrained players (most void facts) are allocated first
        def void_count(p: int) -> int:
            return sum(1 for (pl, _) in self.void_facts if pl == p)

        sorted_others = sorted(other_players, key=void_count, reverse=True)

        for p in sorted_others:
            needed = hand_sizes[p]
            eligible = [c for c in remaining_unseen if not self.is_player_void(p, c.suit)]
            
            # If not enough strictly eligible cards, soft fallback to remaining unseen
            if len(eligible) < needed:
                eligible = list(remaining_unseen)
                
            rng.shuffle(eligible)
            selected = eligible[:needed]
            sampled_hands[p].extend(selected)
            for c in selected:
                if c in remaining_unseen:
                    remaining_unseen.remove(c)

        # Fill any remainder if needed
        for p in other_players:
            while len(sampled_hands[p]) < hand_sizes[p] and remaining_unseen:
                sampled_hands[p].append(remaining_unseen.pop(0))

        return [sampled_hands[p] for p in range(4)]

    def get_inference_summary(self) -> str:
        """Returns human-readable text of inferred predicate facts for AI insight."""
        if not self.void_facts:
            return "No opponent voids detected yet."
        void_strs = [f"Player {p} void in {s.value}" for (p, s) in sorted(self.void_facts)]
        return "Inferred: " + "; ".join(void_strs)
