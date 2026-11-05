from typing import List, Optional, Tuple
from card import Card, Suit, Rank
from game_state import GameState, Trick, PlayedCard, Phase

class Rules:
    @staticmethod
    def get_legal_cards(player_id: int, state: GameState) -> List[Card]:
        """
        Determines legal cards for the player in the current state.
        Enforces follow-suit rule and trump play mechanics according to 29 rules:
        - Must follow the lead suit if player holds any cards of that suit.
        - If void in lead suit, player may play ANY card (trump or off-suit discard).
        """
        hand = state.hands[player_id]
        if not hand:
            return []

        # If leading the trick (or trick is empty)
        if state.current_trick is None or len(state.current_trick.cards) == 0:
            return list(hand)

        lead_suit = state.current_trick.lead_suit
        same_suit_cards = [c for c in hand if c.suit == lead_suit]

        # Rule 1: MUST follow suit if player holds any cards of lead suit
        if same_suit_cards:
            return same_suit_cards

        # Rule 2: Void in lead suit
        # Section 12: Void-suit play: Any card may be played, including trump
        return list(hand)

    @staticmethod
    def determine_trick_winner(trick: Trick, trump_suit: Optional[Suit], trump_revealed: bool) -> int:
        """
        Calculates the winning player of a completed trick according to 29 rules:
        - If trump is revealed and one or more valid trumps were played, highest trump power wins.
        - Otherwise, highest power card of the lead suit wins.
        - Power hierarchy: J(8) > 9(7) > A(6) > 10(5) > K(4) > Q(3) > 8(2) > 7(1).
        """
        if not trick.cards:
            raise ValueError("Cannot determine winner of an empty trick")

        lead_suit = trick.lead_suit

        # Only cards played with trump power (played when trump is revealed) count as trumps
        trump_played: List[PlayedCard] = []
        if trump_revealed and trump_suit is not None:
            trump_played = [pc for pc in trick.cards if pc.is_trump or pc.card.suit == trump_suit]

        if trump_played:
            # Highest trump card wins
            best_played = max(trump_played, key=lambda pc: pc.card.power)
        else:
            # Highest lead suit card wins
            lead_cards = [pc for pc in trick.cards if pc.card.suit == lead_suit]
            best_played = max(lead_cards, key=lambda pc: pc.card.power)

        return best_played.player_id

    @staticmethod
    def calculate_trick_points(trick: Trick, is_last_trick: bool = False, game_variant: str = "28") -> int:
        """
        Calculates card points in trick:
        J=3, 9=2, A=1, 10=1, K=0, Q=0, 8=0, 7=0 (Total card points = 28).
        In authentic 28/29 without last trick bonus (variant 28), total is strictly 28.
        If variant 29 is explicitly chosen, the 8th trick gives +1 bonus.
        """
        pts = sum(pc.card.points for pc in trick.cards)
        if is_last_trick and game_variant == "29":
            pts += 1
        return pts

    @staticmethod
    def has_trump_points(hand: List[Card], trump_suit: Optional[Suit]) -> bool:
        """
        In 29, point cards are: J (3), 9 (2), A (1), 10 (1).
        K, Q, 8, 7 have 0 points.
        Returns True if hand contains at least one card of trump_suit with points > 0.
        """
        if trump_suit is None:
            return False
        return any(c.suit == trump_suit and c.points > 0 for c in hand)

    @staticmethod
    def has_pair(hand: List[Card], trump_suit: Optional[Suit]) -> bool:
        """
        Checks if the hand contains the Pair (King and Queen of the trump suit).
        """
        if trump_suit is None:
            return False
        has_k = any(c.suit == trump_suit and c.rank == Rank.KING for c in hand)
        has_q = any(c.suit == trump_suit and c.rank == Rank.QUEEN for c in hand)
        return has_k and has_q

    @staticmethod
    def can_declare_pair(player_id: int, state: GameState) -> bool:
        """
        Requirements for declaring a Pair (Section 7.1):
        1. Player must hold both King and Queen of the trump suit.
        2. Trump must already have been revealed.
        3. Player must still hold both cards in hand (neither played yet).
        4. Pair has not already been declared in this deal.
        5. The declaration occurs after the player's team has won a trick (or on turn).
        """
        if not state.trump_revealed or state.trump_suit is None:
            return False
        if state.pair_declared:
            return False
        
        # Must hold both K and Q of trump suit currently in hand
        if not Rules.has_pair(state.hands[player_id], state.trump_suit):
            return False

        return True

    @staticmethod
    def single_hand_outcome(state: GameState) -> Tuple[bool, str, int, int]:
        """
        Evaluates a Single Hand against the configured house rules.
        Returns (success, explanation, counted_tricks, counted_points).
        """
        sh = state.rules.single_hand
        decl = state.single_hand_declarer
        partner = GameState.get_partner(decl)
        counted = {decl}
        if state.sitting_out is None and sh.partner_tricks_count:
            counted.add(partner)

        n_tricks = len(state.completed_tricks)
        counted_tricks = sum(1 for t in state.completed_tricks if t.winner in counted)
        counted_points = 0
        for i, t in enumerate(state.completed_tricks):
            if t.winner in counted:
                counted_points += Rules.calculate_trick_points(
                    t, is_last_trick=(i == n_tricks - 1), game_variant=state.game_variant)

        checks = []
        success = True
        if sh.must_win_all_tricks or not sh.use_contract_target:
            ok = counted_tricks == n_tricks
            success &= ok
            checks.append(f"won {counted_tricks}/{n_tricks} tricks")
        if sh.use_contract_target:
            target = state.target_bid or state.bid or state.rules.min_bid
            ok = counted_points >= target
            success &= ok
            checks.append(f"{counted_points} points vs target {target}")
        return success, ", ".join(checks), counted_tricks, counted_points

    @staticmethod
    def evaluate_round_score(state: GameState) -> Tuple[int, int, bool, int]:
        """
        Scores a completed round.
          Normal contract: bidding team needs card points >= target.
            Made  -> bidding team +multiplier match points
            Set   -> bidding team -multiplier match points (defenders unchanged)
          Single Hand: evaluated by the configured Single Hand rules,
            +win_points / -loss_points for the declarer's team.
          Match ends at +match_target (win) or -match_target (loss).
        Returns (team0_points, team1_points, contract_fulfilled, match_points_delta).
        """
        t0_pts = state.round_points[0]
        t1_pts = state.round_points[1]

        bidder = state.single_hand_declarer if state.single_hand else state.highest_bidder
        if bidder is None:
            return t0_pts, t1_pts, False, 0

        bidder_team = state.get_team(bidder)
        before = list(state.game_points)

        if state.single_hand:
            sh = state.rules.single_hand
            fulfilled, detail, _, _ = Rules.single_hand_outcome(state)
            delta = sh.win_points if fulfilled else -sh.loss_points
            state.game_points[bidder_team] += delta
            state.log_event(
                f"Single Hand {'MADE' if fulfilled else 'FAILED'} by Team {chr(65 + bidder_team)} ({detail}). "
                f"{'+' if delta > 0 else ''}{delta} match points.",
                event_type="success" if fulfilled else "failure"
            )
            target = state.target_bid
            multiplier = abs(delta)
        else:
            target = state.target_bid if state.target_bid > 0 else state.bid
            bidder_pts = state.round_points[bidder_team]
            fulfilled = bidder_pts >= target
            multiplier = state.contract_multiplier if state.contract_multiplier in (1, 2, 4) else 1
            mult_str = f" ({state.double_status} x{multiplier})" if multiplier > 1 else ""
            delta = multiplier if fulfilled else -multiplier
            state.game_points[bidder_team] += delta
            if fulfilled:
                detail = f"{bidder_pts} ≥ target {target}"
                state.log_event(
                    f"Contract made! Team {chr(65 + bidder_team)} took {bidder_pts} points (target {target}). "
                    f"+{multiplier} match point{'s' if multiplier > 1 else ''}{mult_str}.",
                    event_type="success")
            else:
                detail = f"{bidder_pts} < target {target}"
                state.log_event(
                    f"Contract failed! Team {chr(65 + bidder_team)} took {bidder_pts} points (target {target}). "
                    f"-{multiplier} match point{'s' if multiplier > 1 else ''}{mult_str}.",
                    event_type="failure")

        result = {
            "round": state.round_number,
            "bidder": bidder,
            "bidder_team": bidder_team,
            "bid": state.bid,
            "target": target,
            "single_hand": state.single_hand,
            "trump": state.trump_suit.value if state.trump_suit else None,
            "trump_symbol": state.trump_suit.symbol if state.trump_suit else None,
            "round_points": [t0_pts, t1_pts],
            "tricks_won": list(state.tricks_won),
            "fulfilled": fulfilled,
            "detail": detail,
            "multiplier": state.contract_multiplier,
            "delta": [state.game_points[0] - before[0], state.game_points[1] - before[1]],
            "game_points": list(state.game_points),
            "marriage": state.marriage_popup_info if state.pair_declared else None,
        }
        state.last_round_result = result
        state.round_history.append(result)

        tgt = state.rules.match_target
        winner = None
        if state.game_points[0] >= tgt or state.game_points[1] <= -tgt:
            winner = 0
        elif state.game_points[1] >= tgt or state.game_points[0] <= -tgt:
            winner = 1
        if winner is not None:
            state.phase = Phase.GAME_OVER
            state.match_winner = winner
            state.log_event(f"MATCH OVER! Team {chr(65 + winner)} wins the match!", event_type="success")

        return t0_pts, t1_pts, fulfilled, multiplier
