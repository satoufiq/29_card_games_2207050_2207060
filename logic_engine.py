from typing import Tuple, List, Optional
from card import Card, Suit
from game_state import GameState

class PropositionalRuleValidator:
    """
    Propositional Logic Engine:
    Validates game moves against formal propositional formulas and outputs
    logical proof traces for AI explanations.
    
    Propositions:
      InHand(p, c): Card c is present in player p's hand.
      LeadPresent(s): The current trick has a designated lead suit s.
      HoldsLeadSuit(p, s): Player p holds at least one card of suit s.
      FollowsLeadSuit(c, s): Chosen card c has suit s.
      TrumpRevealed: Global state indicating trump is exposed.
      HoldsTrump(p, t): Player p holds at least one card of trump suit t.
      PlaysTrump(c, t): Chosen card c is of trump suit t.
    """

    @classmethod
    def validate_card_play(cls, player_id: int, card: Card, state: GameState) -> Tuple[bool, str]:
        hand = state.hands[player_id]
        
        # Proposition 1: InHand(p, c)
        in_hand = card in hand
        if not in_hand:
            return False, f"RuleViolation(¬InHand): Player {player_id} does not possess {card}."

        # Case 1: Trick is empty (Leading)
        if state.current_trick is None or len(state.current_trick.cards) == 0:
            return True, f"Valid(Lead): First card of trick. Any card in hand may be led ({card})."

        lead_suit = state.current_trick.lead_suit
        holds_lead_suit = any(c.suit == lead_suit for c in hand)
        follows_lead_suit = (card.suit == lead_suit)

        # Propositional Constraint: HoldsLeadSuit(p, s) => FollowsLeadSuit(c, s)
        if holds_lead_suit:
            if follows_lead_suit:
                return True, f"Valid(FollowSuit): HoldsLeadSuit({lead_suit.value}) ∧ FollowsLeadSuit({card}) satisfies suit-following constraint."
            else:
                return False, f"RuleViolation(Reneging): HoldsLeadSuit({lead_suit.value}) is TRUE, but chosen card {card} violates FollowSuit."

        # Case 2: Player is void in lead suit: ¬HoldsLeadSuit(p, s)
        # In authentic 28/29, player is never forced to play trump when void in lead suit.
        # They can play trump (to cut/ruff) OR discard any off-suit card (slough).
        if state.trump_revealed and state.trump_suit is not None and card.suit == state.trump_suit:
            return True, f"Valid(TrumpCut): ¬HoldsLeadSuit({lead_suit.value}) ∧ TrumpRevealed ∧ PlaysTrump({card}) cuts/ruffs the trick."

        return True, f"Valid(Discard): ¬HoldsLeadSuit({lead_suit.value}) allows playing off-suit card ({card}) as discard/slough."

    @classmethod
    def validate_bid(cls, player_id: int, bid_value: Optional[int], state: GameState) -> Tuple[bool, str]:
        """
        Validates bidding propositions (duel auction):
          Pass                                -> always valid unless already passed
          InRange(b)                          -> min_bid <= b <= max_bid
          Opening ∧ InRange(b)                -> valid
          Holder(p) ∧ b >= CurrentBid         -> valid (the holder may hold)
          Challenger(p) ∧ b > CurrentBid      -> valid (the challenger must go higher)
          Passed(p)                           -> no further calls (passing is final)
        Turn order is enforced separately by bidding.Auction.
        """
        if player_id in state.passed_players:
            return False, "RuleViolation(AlreadyPassed): Passing is final; this player cannot re-enter the auction."

        if bid_value is None:
            return True, f"Valid(Pass): Player {player_id} passed."

        min_allowed = state.rules.min_bid
        max_allowed = state.rules.max_bid
        if not (min_allowed <= bid_value <= max_allowed):
            return False, f"RuleViolation(BidRange): Bid {bid_value} outside legal range [{min_allowed}, {max_allowed}]."

        if state.highest_bidder is None:
            return True, f"Valid(OpenBid): Opening bid of {bid_value} is legal."

        is_holder = (player_id == getattr(state, "auction_holder", None) and state.highest_bidder != player_id)
        if bid_value == state.bid and is_holder:
            return True, f"Valid(Hold): Holder(p{player_id}) ∧ Bid = CurrentBid({state.bid}) — the holder may hold."
        if bid_value <= state.bid:
            return False, f"RuleViolation(InsufficientBid): Bid {bid_value} must exceed the current bid of {state.bid}."

        return True, f"Valid(RaiseBid): Bid {bid_value} raises the current bid of {state.bid}."
