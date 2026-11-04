from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Dict, Any
from card import Card, Suit, Rank
from house_rules import HouseRules


class Phase(str, Enum):
    DEALING_1 = "DEALING_1"
    BIDDING = "BIDDING"
    TRUMP_SELECTION = "TRUMP_SELECTION"
    SINGLE_HAND = "SINGLE_HAND"        # after-deal window where a Single Hand may be called
    DOUBLING = "DOUBLING"
    DEALING_2 = "DEALING_2"
    PLAYING = "PLAYING"
    ROUND_OVER = "ROUND_OVER"
    GAME_OVER = "GAME_OVER"


@dataclass
class PlayedCard:
    player_id: int
    card: Card
    is_trump: bool = False


@dataclass
class Trick:
    trick_number: int  # 0 to 7
    lead_player: int
    cards: List[PlayedCard] = field(default_factory=list)
    winner: Optional[int] = None
    points: int = 0
    size: int = 4      # 3 when a Single Hand partner sits out

    @property
    def lead_suit(self) -> Optional[Suit]:
        if self.cards:
            return self.cards[0].card.suit
        return None

    def add_card(self, player_id: int, card: Card, is_trump: bool = False):
        self.cards.append(PlayedCard(player_id=player_id, card=card, is_trump=is_trump))
        self.points += card.points

    def is_complete(self) -> bool:
        return len(self.cards) >= self.size

    def clone(self) -> "Trick":
        t = Trick(trick_number=self.trick_number, lead_player=self.lead_player, size=self.size)
        for pc in self.cards:
            t.add_card(pc.player_id, pc.card, is_trump=pc.is_trump)
        t.winner = self.winner
        return t


@dataclass
class GameState:
    # Game setup & round metadata
    round_number: int = 1
    phase: Phase = Phase.DEALING_1
    dealer: int = 0
    current_player: int = 1
    rules: HouseRules = field(default_factory=HouseRules)

    # Player hands (each list contains cards currently in player's hand)
    hands: List[List[Card]] = field(default_factory=lambda: [[], [], [], []])
    # Full hands after stage-2 dealing (used by the authentic abandonment rules)
    initial_hands: List[List[Card]] = field(default_factory=lambda: [[], [], [], []])

    # Auction (clockwise, passing is final)
    bid: int = 0
    target_bid: int = 0
    highest_bidder: Optional[int] = None
    bidding_history: List[Dict[str, Any]] = field(default_factory=list)
    active_bidders: List[int] = field(default_factory=lambda: [0, 1, 2, 3])
    passed_players: List[int] = field(default_factory=list)
    last_bid_action: str = ""  # "OPEN", "RAISE", "PASS", "SINGLE"
    last_bid_player: Optional[int] = None
    player_bids: Dict[int, str] = field(default_factory=lambda: {0: "", 1: "", 2: "", 3: ""})
    consecutive_passes: int = 0
    # Duel auction: the holder may hold (match); the challenger must go higher.
    auction_holder: Optional[int] = None
    auction_challenger: Optional[int] = None
    auction_queue: List[int] = field(default_factory=list)

    # Single Hand
    single_hand: bool = False
    single_hand_declarer: Optional[int] = None
    sitting_out: Optional[int] = None           # partner who lays down their cards
    single_hand_asked: List[int] = field(default_factory=list)
    single_hand_turn: Optional[int] = None      # player being asked in the after-deal window
    single_hand_result: Optional[Dict[str, Any]] = None

    # Trump state
    trump_suit: Optional[Suit] = None
    trump_card: Optional[Card] = None
    trump_revealed: bool = False
    trump_revealer: Optional[int] = None
    trump_reveal_trick: Optional[int] = None
    is_seventh_card_trump: bool = False
    seventh_card: Optional[Card] = None
    deal_abandoned: bool = False
    abandon_reason: Optional[str] = None
    no_trump_points_alert: Optional[str] = None
    game_variant: str = "28"
    pair_points: int = 0

    # Tricks
    current_trick: Optional[Trick] = None
    completed_tricks: List[Trick] = field(default_factory=list)
    last_completed_trick: Optional[Dict[str, Any]] = None
    pending_trick_pause: bool = False
    tricks_won: List[int] = field(default_factory=lambda: [0, 0, 0, 0])

    # Scoring. Team 0 = Players 0 & 2, Team 1 = Players 1 & 3
    round_points: List[int] = field(default_factory=lambda: [0, 0])
    game_points: List[int] = field(default_factory=lambda: [0, 0])
    round_history: List[Dict[str, Any]] = field(default_factory=list)
    last_round_result: Optional[Dict[str, Any]] = None
    match_winner: Optional[int] = None

    # Double & Redouble
    double_redouble_enabled: bool = True
    double_status: str = "NONE"
    doubled_by: Optional[int] = None
    redoubled_by: Optional[int] = None
    contract_multiplier: int = 1
    doubling_decision_player: Optional[int] = None

    # Royal marriage (K + Q of trump)
    pair_declared: bool = False
    pair_declarer: Optional[int] = None
    pair_declarer_team: Optional[int] = None
    pair_adjustment: int = 0
    marriage_popup_pending: bool = False
    marriage_popup_info: Optional[Dict[str, Any]] = None

    event_log: List[Dict[str, Any]] = field(default_factory=list)
    latest_insight: str = "Awaiting opening bids..."

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def get_team(player_id: int) -> int:
        """Players 0 and 2 are Team 0 (Team A); 1 and 3 are Team 1 (Team B)."""
        return 0 if player_id in (0, 2) else 1

    @staticmethod
    def get_partner(player_id: int) -> int:
        return (player_id + 2) % 4

    def next_player(self, player_id: int) -> int:
        """Next seat in play order, skipping a partner who sits out a Single Hand."""
        nxt = (player_id + 1) % 4
        if self.sitting_out is not None and nxt == self.sitting_out:
            nxt = (nxt + 1) % 4
        return nxt

    @property
    def trick_size(self) -> int:
        return 3 if self.sitting_out is not None else 4

    @property
    def min_next_bid(self) -> int:
        """Lowest legal bid for the player to speak (the holder may hold at the current bid)."""
        if self.highest_bidder is None:
            return self.rules.min_bid
        if self.current_player == self.auction_holder and self.highest_bidder != self.current_player:
            return self.bid
        return self.bid + 1

    @property
    def can_hold(self) -> bool:
        return (self.phase == Phase.BIDDING and self.highest_bidder is not None
                and self.current_player == self.auction_holder and self.highest_bidder != self.current_player)

    def can_ditto(self, player_id: int) -> bool:
        """Matching a bid is not part of the clockwise auction; kept for API compatibility."""
        return False

    def log_event(self, text: str, player_id: Optional[int] = None, event_type: str = "info"):
        self.event_log.append({
            "id": len(self.event_log),
            "text": text,
            "player_id": player_id,
            "type": event_type,
            "round": self.round_number,
            "trick": len(self.completed_tricks) + 1 if self.phase == Phase.PLAYING else 0
        })

    def can_player_reveal_trump(self, viewer_id: int) -> bool:
        if self.trump_revealed or self.single_hand or self.phase != Phase.PLAYING:
            return False
        if self.current_player != viewer_id:
            return False
        if self.current_trick and len(self.current_trick.cards) > 0:
            lead_suit = self.current_trick.lead_suit
            if lead_suit and not any(c.suit == lead_suit for c in self.hands[viewer_id]):
                return True
        return False

    def can_player_declare_pair(self, viewer_id: int) -> bool:
        if not self.rules.marriage_enabled or self.rules.marriage_mode != "after_trick":
            return False
        if not self.trump_revealed or self.trump_suit is None or self.pair_declared or self.single_hand:
            return False
        hand = self.hands[viewer_id]
        has_k = any(c.suit == self.trump_suit and c.rank == Rank.KING for c in hand)
        has_q = any(c.suit == self.trump_suit and c.rank == Rank.QUEEN for c in hand)
        if not (has_k and has_q):
            return False
        team = self.get_team(viewer_id)
        reveal_idx = (self.trump_reveal_trick or 1) - 1
        return any(
            t.winner is not None and self.get_team(t.winner) == team
            for t in self.completed_tricks[reveal_idx:]
        )

    def get_player_view(self, viewer_id: int, reveal_all: bool = False) -> Dict[str, Any]:
        """
        A JSON view of the game for one seat. Opponent hands are hidden (only counts),
        and an unrevealed trump is only shown to the bidder.
        reveal_all is used by the AI-vs-AI spectator view only.
        """
        is_bidder = (self.highest_bidder == viewer_id)
        show_trump = self.trump_revealed or is_bidder or reveal_all

        def trick_view(t: Optional[Trick]):
            if t is None:
                return None
            return {
                "trick_number": t.trick_number,
                "lead_player": t.lead_player,
                "size": t.size,
                "cards": [
                    {"player_id": pc.player_id, "card": pc.card.to_dict(), "is_trump": pc.is_trump}
                    for pc in t.cards
                ],
                "points": t.points
            }

        view = {
            "round_number": self.round_number,
            "phase": self.phase.value,
            "viewer_id": viewer_id,
            "current_player": self.current_player,
            "dealer": self.dealer,
            "hand": [c.to_dict() for c in Card.sort_cards(self.hands[viewer_id])],
            "card_counts": [len(h) for h in self.hands],
            "bid": self.bid if self.highest_bidder is not None else 0,
            "target_bid": self.target_bid if self.highest_bidder is not None else 0,
            "min_next_bid": self.min_next_bid,
            "can_hold": self.can_hold,
            "auction_holder": self.auction_holder,
            "auction_challenger": self.auction_challenger,
            "max_bid": self.rules.max_bid,
            "highest_bidder": self.highest_bidder,
            "highest_bidder_team": self.get_team(self.highest_bidder) if self.highest_bidder is not None else None,
            "trump_revealed": self.trump_revealed,
            "trump_suit": self.trump_suit.value if (show_trump and self.trump_suit) else None,
            "trump_symbol": self.trump_suit.symbol if (show_trump and self.trump_suit) else None,
            "trump_hidden": (self.trump_suit is not None or self.is_seventh_card_trump) and not self.trump_revealed and not self.single_hand,
            "is_seventh_card_trump": self.is_seventh_card_trump,
            "seventh_card_concealed": (self.is_seventh_card_trump and not self.trump_revealed),
            "seventh_card": self.seventh_card.to_dict() if (show_trump and self.seventh_card) else None,
            "deal_abandoned": self.deal_abandoned,
            "abandon_reason": self.abandon_reason,
            "can_reveal_trump": self.can_player_reveal_trump(viewer_id),
            "can_declare_pair": self.can_player_declare_pair(viewer_id),
            "pair_declared": self.pair_declared,
            "pair_declarer": self.pair_declarer,
            "pair_declarer_team": self.pair_declarer_team,
            "pair_adjustment": self.pair_adjustment,
            "marriage_popup_pending": self.marriage_popup_pending,
            "marriage_popup_info": self.marriage_popup_info,
            "current_trick": trick_view(self.current_trick),
            "completed_tricks_count": len(self.completed_tricks),
            "last_completed_trick": self.last_completed_trick,
            "pending_trick_pause": self.pending_trick_pause,
            "tricks_won": list(self.tricks_won),
            "round_points": list(self.round_points),
            "game_points": list(self.game_points),
            "match_target": self.rules.match_target,
            "player_bids": dict(self.player_bids),
            "passed_players": list(self.passed_players),
            "last_bid_action": self.last_bid_action,
            "bidding_history": list(self.bidding_history),
            "single_hand": self.single_hand,
            "single_hand_declarer": self.single_hand_declarer,
            "sitting_out": self.sitting_out,
            "single_hand_turn": self.single_hand_turn,
            "single_hand_result": self.single_hand_result,
            "can_call_single_hand": self.can_call_single_hand(viewer_id),
            "game_variant": self.game_variant,
            "latest_insight": self.latest_insight,
            "recent_events": self.event_log[-40:],
            "double_redouble_enabled": self.double_redouble_enabled,
            "double_status": self.double_status,
            "doubled_by": self.doubled_by,
            "redoubled_by": self.redoubled_by,
            "contract_multiplier": self.contract_multiplier,
            "doubling_decision_player": self.doubling_decision_player,
            "can_human_double": (
                self.phase == Phase.DOUBLING and
                self.doubling_decision_player == viewer_id and
                self.double_status == "NONE" and
                self.highest_bidder is not None and
                self.get_team(viewer_id) != self.get_team(self.highest_bidder)
            ),
            "can_human_redouble": (
                self.phase == Phase.DOUBLING and
                self.doubling_decision_player == viewer_id and
                self.double_status == "DOUBLED" and
                self.highest_bidder is not None and
                self.get_team(viewer_id) == self.get_team(self.highest_bidder)
            ),
            "completed_tricks": [
                {
                    "trick_number": t.trick_number,
                    "winner": t.winner,
                    "points": t.points,
                    "cards": [{"player_id": pc.player_id, "card": pc.card.code} for pc in t.cards]
                }
                for t in self.completed_tricks
            ],
            "round_history": list(self.round_history),
            "last_round_result": self.last_round_result,
            "match_winner": self.match_winner,
        }
        if reveal_all:
            view["all_hands"] = [[c.to_dict() for c in Card.sort_cards(h)] for h in self.hands]
        return view

    def can_call_single_hand(self, player_id: int) -> bool:
        sh = self.rules.single_hand
        if not sh.enabled or self.single_hand:
            return False
        if sh.timing == "auction":
            return (
                self.phase == Phase.BIDDING and
                self.current_player == player_id and
                player_id not in self.passed_players
            )
        return self.phase == Phase.SINGLE_HAND and self.single_hand_turn == player_id

    def get_masked_state_for_player(self, viewer_id: int) -> "GameState":
        """
        Imperfect-information copy of the state for one seat:
        other hands are empty lists and an unrevealed trump is hidden unless the
        viewer is the bidder. AI agents only ever receive this view.
        """
        is_bidder = (self.highest_bidder == viewer_id)
        show_trump = self.trump_revealed or is_bidder

        masked_hands = [[] for _ in range(4)]
        masked_hands[viewer_id] = list(self.hands[viewer_id])
        masked_initial = [[] for _ in range(4)]
        if self.initial_hands and len(self.initial_hands) == 4:
            masked_initial[viewer_id] = list(self.initial_hands[viewer_id])

        ms = GameState(
            round_number=self.round_number,
            phase=self.phase,
            dealer=self.dealer,
            current_player=self.current_player,
            rules=self.rules,
            hands=masked_hands,
            initial_hands=masked_initial,
            bid=self.bid,
            target_bid=self.target_bid,
            highest_bidder=self.highest_bidder,
            bidding_history=list(self.bidding_history),
            active_bidders=list(self.active_bidders),
            passed_players=list(self.passed_players),
            last_bid_action=self.last_bid_action,
            last_bid_player=self.last_bid_player,
            player_bids=dict(self.player_bids),
            consecutive_passes=self.consecutive_passes,
            auction_holder=self.auction_holder,
            auction_challenger=self.auction_challenger,
            auction_queue=list(self.auction_queue),
            single_hand=self.single_hand,
            single_hand_declarer=self.single_hand_declarer,
            sitting_out=self.sitting_out,
            single_hand_asked=list(self.single_hand_asked),
            single_hand_turn=self.single_hand_turn,
            double_redouble_enabled=self.double_redouble_enabled,
            double_status=self.double_status,
            doubled_by=self.doubled_by,
            redoubled_by=self.redoubled_by,
            contract_multiplier=self.contract_multiplier,
            doubling_decision_player=self.doubling_decision_player,
            trump_suit=self.trump_suit if show_trump else None,
            trump_card=self.trump_card if show_trump else None,
            trump_revealed=self.trump_revealed,
            trump_revealer=self.trump_revealer,
            trump_reveal_trick=self.trump_reveal_trick,
            is_seventh_card_trump=self.is_seventh_card_trump,
            seventh_card=self.seventh_card if show_trump else None,
            deal_abandoned=self.deal_abandoned,
            abandon_reason=self.abandon_reason,
            no_trump_points_alert=self.no_trump_points_alert,
            game_variant=self.game_variant,
            current_trick=self.current_trick.clone() if self.current_trick else None,
            completed_tricks=list(self.completed_tricks),
            last_completed_trick=self.last_completed_trick,
            pending_trick_pause=self.pending_trick_pause,
            tricks_won=list(self.tricks_won),
            round_points=list(self.round_points),
            game_points=list(self.game_points),
            pair_declared=self.pair_declared,
            pair_declarer=self.pair_declarer,
            pair_declarer_team=self.pair_declarer_team,
            pair_adjustment=self.pair_adjustment,
            pair_points=self.pair_points,
            event_log=[],
            latest_insight=self.latest_insight
        )
        # Public information: how many cards everyone still holds.
        ms.public_hand_sizes = [len(h) for h in self.hands]
        return ms

    def hand_sizes(self) -> List[int]:
        """Card counts; works on masked states too (they carry public_hand_sizes)."""
        sizes = getattr(self, "public_hand_sizes", None)
        if sizes is not None:
            return list(sizes)
        return [len(h) for h in self.hands]
