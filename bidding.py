"""
Duel-style auction for 29 (the traditional "hold" auction).

  * Players are taken clockwise starting with the player after the dealer.
  * The first player (the HOLDER) opens; the next player clockwise (the CHALLENGER)
    must bid HIGHER than the current bid, or pass.
  * The holder answers each challenge by HOLDING (bidding the same number — the
    holder never needs to go higher) or by passing.
  * The duel continues until one of the two passes. Passing is final.
  * The survivor becomes (or stays) the holder and duels the next player clockwise
    who has not spoken yet. When nobody is left to challenge, the holder wins.
  * If the opener passes without bidding, the next player takes over the opening.
  * If everyone passes without a bid, the house rule decides (dealer forced / redeal).
  * Single Hand (house-rule timing "auction") may be called by whoever is to speak;
    it ends the auction immediately.

Example (P1..P4 clockwise from the dealer):
  P1 16, P2 17, P1 holds 17, P2 18, P1 pass   -> P2 holds, P3 challenges
  P3 pass                                     -> P4 challenges
  P4 19, P2 holds 19, P4 20, P2 pass          -> P4 wins at 20
"""
from typing import Optional, Tuple
from game_state import GameState, Phase

PASS = "PASS"
BID = "BID"
SINGLE = "SINGLE"

CONTINUE = "continue"
WON = "won"
ALL_PASSED = "all_passed"
SINGLE_HAND_CALLED = "single_hand"


class Auction:
    @staticmethod
    def reset(state: GameState):
        state.bid = 0
        state.target_bid = 0
        state.highest_bidder = None
        state.bidding_history = []
        state.active_bidders = [0, 1, 2, 3]
        state.passed_players = []
        state.player_bids = {0: "", 1: "", 2: "", 3: ""}
        state.last_bid_action = ""
        state.last_bid_player = None
        state.consecutive_passes = 0
        order = [(state.dealer + k) % 4 for k in (1, 2, 3, 4)]
        state.auction_holder = order[0]
        state.auction_challenger = order[1]
        state.auction_queue = order[2:]
        state.current_player = order[0]

    # ------------------------------------------------------------------ roles
    @staticmethod
    def role(state: GameState, player_id: int) -> str:
        if player_id == state.auction_holder:
            return "holder"
        if player_id == state.auction_challenger:
            return "challenger"
        return "waiting"

    @staticmethod
    def min_bid_for(state: GameState, player_id: int) -> int:
        """Lowest legal bid for this player right now."""
        if state.highest_bidder is None:
            return state.rules.min_bid
        if player_id == state.auction_holder and state.highest_bidder != player_id:
            return state.bid          # the holder may hold (match)
        return state.bid + 1          # the challenger must go higher

    @staticmethod
    def validate(state: GameState, player_id: int, action: str, value: Optional[int] = None) -> Tuple[bool, str]:
        if state.phase != Phase.BIDDING:
            return False, "The auction is not open."
        if player_id != state.current_player:
            return False, f"It is Player {state.current_player}'s turn to speak."
        if player_id in state.passed_players:
            return False, "You have already passed; passing is final for this auction."
        if action == PASS:
            return True, "Pass accepted."
        if action == SINGLE:
            sh = state.rules.single_hand
            if not (sh.enabled and sh.timing == "auction"):
                return False, "Single Hand is not available during the auction under the current house rules."
            return True, "Single Hand called."
        if action != BID:
            return False, f"Unknown auction action {action}."
        try:
            value = int(value)
        except (TypeError, ValueError):
            return False, f"Bid '{value}' is not a number."
        lo, hi = Auction.min_bid_for(state, player_id), state.rules.max_bid
        if value < lo:
            if state.highest_bidder is None:
                return False, f"The opening bid must be at least {lo}."
            if lo == state.bid:
                return False, f"You may hold at {state.bid} or bid higher."
            return False, f"You must bid higher than {state.bid}."
        if value > hi:
            return False, f"The maximum bid is {hi}."
        return True, f"Bid of {value} accepted."

    # ------------------------------------------------------------------ flow
    @staticmethod
    def _next_challenger(state: GameState) -> Optional[int]:
        while state.auction_queue:
            p = state.auction_queue.pop(0)
            if p not in state.passed_players:
                return p
        return None

    @staticmethod
    def apply(state: GameState, player_id: int, action: str, value: Optional[int], name: str) -> str:
        holder, challenger = state.auction_holder, state.auction_challenger

        if action == SINGLE:
            state.highest_bidder = player_id
            state.last_bid_action = "SINGLE"
            state.last_bid_player = player_id
            state.player_bids[player_id] = "SINGLE"
            state.bidding_history.append({"player": player_id, "bid": "SINGLE", "action": "SINGLE"})
            state.log_event(f"{name} called SINGLE HAND!", player_id=player_id, event_type="single")
            return SINGLE_HAND_CALLED

        if action == PASS:
            state.passed_players.append(player_id)
            if player_id in state.active_bidders:
                state.active_bidders.remove(player_id)
            state.player_bids[player_id] = "PASS"
            state.last_bid_action = "PASS"
            state.last_bid_player = player_id
            state.consecutive_passes += 1
            state.bidding_history.append({"player": player_id, "bid": "PASS", "action": "PASS"})
            state.log_event(f"{name} passed.", player_id=player_id, event_type="pass")

            if player_id == holder:
                # The challenger takes over as holder; the next player clockwise challenges.
                state.auction_holder = challenger
                state.auction_challenger = Auction._next_challenger(state)
                if state.auction_holder is None:
                    return ALL_PASSED if state.highest_bidder is None else WON
                if state.highest_bidder is None:
                    # Nobody has bid yet: the new holder opens.
                    state.current_player = state.auction_holder
                    if state.auction_challenger is None and state.auction_holder in state.passed_players:
                        return ALL_PASSED
                    return CONTINUE
            else:
                # The challenger passed: the holder faces the next player clockwise.
                state.auction_challenger = Auction._next_challenger(state)
                if state.highest_bidder is None and state.auction_challenger is None:
                    # Only the holder is left and has not opened yet.
                    state.current_player = state.auction_holder
                    return CONTINUE

            if state.auction_challenger is None:
                if state.highest_bidder is None:
                    return ALL_PASSED
                return WON
            state.current_player = state.auction_challenger
            return CONTINUE

        # ---- a bid
        value = int(value)
        is_open = state.highest_bidder is None
        is_hold = (not is_open) and player_id == holder and value == state.bid
        prev = state.highest_bidder
        state.bid = value
        state.target_bid = value
        state.highest_bidder = player_id
        state.last_bid_action = "OPEN" if is_open else ("HOLD" if is_hold else "RAISE")
        state.last_bid_player = player_id
        state.consecutive_passes = 0
        state.player_bids[player_id] = str(value)
        state.bidding_history.append({"player": player_id, "bid": value, "action": state.last_bid_action})
        if is_open:
            state.log_event(f"{name} opened the bidding at {value}.", player_id=player_id, event_type="bid")
        elif is_hold:
            state.log_event(f"{name} held at {value}.", player_id=player_id, event_type="bid")
        elif prev is not None and prev == GameState.get_partner(player_id):
            state.log_event(f"{name} raised over partner to {value}.", player_id=player_id, event_type="bid")
        else:
            state.log_event(f"{name} raised to {value}.", player_id=player_id, event_type="bid")

        if player_id == holder:
            if state.auction_challenger is None or value >= state.rules.max_bid:
                return WON          # nobody left to challenge, or nobody can go higher
            state.current_player = state.auction_challenger
        else:
            state.current_player = holder        # holder may hold or pass
        return CONTINUE
