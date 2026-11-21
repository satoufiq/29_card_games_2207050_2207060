from typing import List, Optional, Dict, Any, Tuple
import random
from card import Card, Suit, Rank
from deck import Deck
from game_state import GameState, Phase, Trick
from rules import Rules
from logic_engine import PropositionalRuleValidator
from knowledge_base import PredicateKnowledgeBase
from ai_player import AIPlayer, AIStrategy
from house_rules import HouseRules
from bidding import Auction, PASS, BID, SINGLE, CONTINUE, WON, ALL_PASSED, SINGLE_HAND_CALLED

DEFAULT_NAMES = ["Rafi", "Nadia", "Tanvir", "Mitu"]


class GameController:
    """
    Coordinates the game loop for Bangladeshi 29: dealing, the clockwise auction,
    trump selection, Single Hand, doubling, trick play, scoring and AI turns.
    AI agents only ever receive masked states (their own cards + public info).
    """

    def __init__(
        self,
        human_seat: Optional[int] = 0,
        ai_strategies: Optional[List[AIStrategy]] = None,
        seed: Optional[int] = None,
        biased_deal: bool = False,
        rules: Optional[HouseRules] = None,
        names: Optional[List[str]] = None,
        budget_scale: float = 1.0,
        human_name: str = "You",
    ):
        self.seed = seed
        self.rng = random.Random(seed)
        self.deck = Deck(seed=seed, biased=biased_deal)
        self.rules = rules or HouseRules()
        self.rules.validate()
        self.state = GameState(rules=self.rules)
        self.human_seat = human_seat
        self.knowledge_bases = [PredicateKnowledgeBase(viewer_id=i) for i in range(4)]
        self.decision_log: List[Dict[str, Any]] = []
        self._decision_seq = 0
        self.deal_id = 0
        self.deal_stage = 0

        if ai_strategies is None:
            ai_strategies = [AIStrategy.STRATEGIC, AIStrategy.AGGRESSIVE, AIStrategy.STRATEGIC, AIStrategy.DEFENSIVE]
        names = list(names) if names else list(DEFAULT_NAMES)

        self.agents: List[AIPlayer] = []
        for i in range(4):
            name = names[i] if i < len(names) else f"AI {i}"
            if human_seat is not None and i == human_seat:
                name = (human_name or "You").strip() or "You"
            self.agents.append(AIPlayer(player_id=i, name=name, strategy=ai_strategies[i],
                                        seed=self.rng.randint(0, 10 ** 6), budget_scale=budget_scale))

        self.stats = {
            "rounds_played": 0, "team_a_wins": 0, "team_b_wins": 0,
            "contracts_attempted": 0, "contracts_made": 0,
            "team_a_points_sum": 0, "team_b_points_sum": 0,
            "single_hands": 0, "single_hands_made": 0, "deals_abandoned": 0,
        }
        self.start_new_round()

    # ================================================================== helpers
    def _name(self, p: Optional[int]) -> str:
        if p is None:
            return "Nobody"
        return self.agents[p].name

    def _subj(self, p: Optional[int], third: str, second: str) -> str:
        """'Nadia wins' / 'You win' — verb agreement when the human keeps the name 'You'."""
        return f"{self._name(p)} {second if p is not None and self._name(p) == 'You' else third}"

    def _log_decision(self, rec: Optional[Dict[str, Any]]):
        if not rec:
            return
        self._decision_seq += 1
        rec = dict(rec)
        rec["seq"] = self._decision_seq
        rec["round"] = self.state.round_number
        rec["trick"] = len(self.state.completed_tricks) + 1
        rec["phase"] = self.state.phase.value
        self.decision_log.append(rec)
        if len(self.decision_log) > 120:
            self.decision_log = self.decision_log[-120:]
        self.state.latest_insight = rec.get("summary", "")

    def _record_round_stats(self, t0_pts: int, t1_pts: int, contract_fulfilled: bool):
        self.stats["rounds_played"] += 1
        self.stats["team_a_points_sum"] += t0_pts
        self.stats["team_b_points_sum"] += t1_pts
        bidder = self.state.single_hand_declarer if self.state.single_hand else self.state.highest_bidder
        if bidder is None:
            return
        if self.state.single_hand:
            self.stats["single_hands"] += 1
            if contract_fulfilled:
                self.stats["single_hands_made"] += 1
        else:
            self.stats["contracts_attempted"] += 1
            if contract_fulfilled:
                self.stats["contracts_made"] += 1
        bt = self.state.get_team(bidder)
        winner_team = bt if contract_fulfilled else 1 - bt
        self.stats["team_a_wins" if winner_team == 0 else "team_b_wins"] += 1

    # ================================================================== dealing
    def start_new_round(self):
        """Shuffles and deals stage 1 (4 cards each), then opens the auction."""
        s = self.state
        self.deck.cards = self.deck._create_deck()
        self.deck.shuffle()
        self.deck.first_player = (s.dealer + 1) % 4
        stage_1 = self.deck.deal_stage_one()
        self.deal_id += 1
        self.deal_stage = 1

        s.rules = self.rules
        s.game_variant = self.rules.game_variant
        s.double_redouble_enabled = self.rules.double_redouble
        s.phase = Phase.BIDDING
        s.hands = stage_1
        s.initial_hands = [[], [], [], []]
        Auction.reset(s)
        s.single_hand = False
        s.single_hand_declarer = None
        s.sitting_out = None
        s.single_hand_asked = []
        s.single_hand_turn = None
        s.single_hand_result = None
        s.pair_declared = False
        s.pair_declarer = None
        s.pair_declarer_team = None
        s.pair_adjustment = 0
        s.pair_points = 0
        s.marriage_popup_pending = False
        s.marriage_popup_info = None
        s.trump_suit = None
        s.trump_card = None
        s.trump_revealed = False
        s.trump_revealer = None
        s.trump_reveal_trick = None
        s.is_seventh_card_trump = False
        s.seventh_card = None
        s.deal_abandoned = False
        s.abandon_reason = None
        s.no_trump_points_alert = None
        s.current_trick = None
        s.completed_tricks = []
        s.last_completed_trick = None
        s.pending_trick_pause = False
        s.tricks_won = [0, 0, 0, 0]
        s.round_points = [0, 0]
        s.double_status = "NONE"
        s.doubled_by = None
        s.redoubled_by = None
        s.contract_multiplier = 1
        s.doubling_decision_player = None
        s.latest_insight = "Auction open."

        for kb in self.knowledge_bases:
            kb.played_facts.clear()
            kb.void_facts.clear()
            kb.known_trump = None

        s.log_event(
            f"Round {s.round_number}: {self._subj(s.dealer, 'deals', 'deal')}. 4 cards each — "
            f"{self._name(s.current_player)} opens the auction.", event_type="info")

        for p in range(4):
            if sum(1 for c in s.hands[p] if c.rank == Rank.JACK) == 4:
                self.abandon_deal(f"{self._subj(p, 'was', 'were')} dealt all 4 Jacks in the first 4 cards! Under authentic 29 rules, the deal is abandoned.")
                return

    def abandon_deal(self, reason: str):
        self.state.deal_abandoned = True
        self.state.abandon_reason = reason
        self.state.no_trump_points_alert = reason
        self.state.log_event(f"DEAL ABANDONED: {reason}", event_type="abandoned")
        self.stats["deals_abandoned"] = self.stats.get("deals_abandoned", 0) + 1

    def start_next_deal_after_abandonment(self):
        self.state.deal_abandoned = False
        self.state.abandon_reason = None
        self.state.no_trump_points_alert = None
        self.state.round_number += 1
        self.state.dealer = (self.state.dealer + 1) % 4
        self.start_new_round()

    def restart_match(self):
        self.state.game_points = [0, 0]
        self.state.round_history = []
        self.state.last_round_result = None
        self.state.match_winner = None
        self.state.round_number = 1
        self.state.dealer = 0
        self.state.event_log = []
        self.decision_log = []
        self.start_new_round()

    # ================================================================== turn logic
    def is_human_turn(self) -> bool:
        s = self.state
        h = self.human_seat
        if h is None or s.deal_abandoned or s.pending_trick_pause:
            return False
        if s.phase == Phase.BIDDING:
            return s.current_player == h and h not in s.passed_players
        if s.phase == Phase.TRUMP_SELECTION:
            return s.highest_bidder == h
        if s.phase == Phase.SINGLE_HAND:
            return s.single_hand_turn == h
        if s.phase == Phase.DOUBLING:
            return s.doubling_decision_player == h
        if s.phase == Phase.PLAYING:
            return s.current_player == h and h != s.sitting_out
        return False

    def step(self) -> Dict[str, Any]:
        """Advances one AI action (or reports that the human must act)."""
        s = self.state
        if s.deal_abandoned:
            return {"status": "deal_abandoned", "reason": s.abandon_reason, "phase": s.phase.value}
        if s.pending_trick_pause:
            return {"status": "pending_trick_pause", "phase": s.phase.value}
        if s.phase == Phase.GAME_OVER:
            return {"status": "game_over", "phase": s.phase.value}
        if self.is_human_turn():
            return {"status": "waiting_human", "player": self.human_seat, "phase": s.phase.value}

        if s.phase == Phase.BIDDING:
            self._ai_step_bidding()
        elif s.phase == Phase.TRUMP_SELECTION:
            self._ai_step_trump_selection()
            if s.deal_abandoned:
                return {"status": "deal_abandoned", "reason": s.abandon_reason, "phase": s.phase.value}
        elif s.phase == Phase.SINGLE_HAND:
            self._ai_step_single_hand()
        elif s.phase == Phase.DOUBLING:
            self._ai_step_doubling()
        elif s.phase == Phase.PLAYING:
            if len(s.completed_tricks) >= 8:
                self._end_round()
                return {"status": "round_over", "phase": s.phase.value}
            self._ai_step_playing()
        elif s.phase == Phase.ROUND_OVER:
            self.next_round()
        return {"status": "stepped", "phase": s.phase.value, "current_player": s.current_player}

    # ================================================================== bidding
    def human_bid(self, bid_value: Optional[int]) -> Tuple[bool, str]:
        if not self.is_human_turn() or self.state.phase != Phase.BIDDING:
            return False, "It is not your turn to bid."
        if bid_value is not None:
            try:
                bid_value = int(bid_value)
            except (TypeError, ValueError):
                return False, f"Invalid bid: {bid_value}"
        return self._apply_bid_action(self.human_seat, BID if bid_value is not None else PASS, bid_value)

    def human_call_single_hand(self) -> Tuple[bool, str]:
        s = self.state
        if s.phase == Phase.BIDDING:
            if not self.is_human_turn():
                return False, "It is not your turn."
            return self._apply_bid_action(self.human_seat, SINGLE, None)
        if s.phase == Phase.SINGLE_HAND:
            return self.human_single_hand_decision(True)
        return False, "Single Hand cannot be called now."

    def _ai_step_bidding(self):
        p = self.state.current_player
        agent = self.agents[p]
        masked = self.state.get_masked_state_for_player(p)
        action, value, rec = agent.decide_bid(masked)
        ok, msg = self._apply_bid_action(p, action, value)
        if not ok:
            # The AI must never stall the auction: fall back to a legal pass.
            self._apply_bid_action(p, PASS, None)
            rec = dict(rec or {})
            rec["summary"] = f"{agent.name} passed ({msg})."
        self._log_decision(rec)

    def _apply_bid(self, player_id: int, bid_value: Optional[int]):
        """Compatibility helper used by tests and older clients."""
        action = PASS if bid_value is None else BID
        return self._apply_bid_action(player_id, action, bid_value)

    def _apply_bid_action(self, player_id: int, action: str, value: Optional[int]) -> Tuple[bool, str]:
        s = self.state
        ok, msg = Auction.validate(s, player_id, action, value)
        if not ok:
            return False, msg
        if action == BID:
            valid, proof = PropositionalRuleValidator.validate_bid(player_id, int(value), s)
            if not valid:
                return False, proof
        outcome = Auction.apply(s, player_id, action, value, self._name(player_id))
        if outcome == WON:
            self._conclude_bidding()
        elif outcome == ALL_PASSED:
            if self.rules.all_pass_rule == "redeal":
                s.log_event("All four players passed — the cards are thrown in and redealt.", event_type="warning")
                s.dealer = (s.dealer + 1) % 4
                self.start_new_round()
            else:
                dealer = s.dealer
                s.highest_bidder = dealer
                s.bid = self.rules.min_bid
                s.target_bid = self.rules.min_bid
                s.player_bids[dealer] = f"{self.rules.min_bid}*"
                s.bidding_history.append({"player": dealer, "bid": self.rules.min_bid, "action": "FORCED"})
                s.log_event(f"All players passed — dealer {self._name(dealer)} must play at {self.rules.min_bid}.",
                            player_id=dealer, event_type="warning")
                self._conclude_bidding()
        elif outcome == SINGLE_HAND_CALLED:
            self._begin_single_hand(player_id, from_auction=True)
        return True, msg

    def _conclude_bidding(self):
        s = self.state
        s.phase = Phase.TRUMP_SELECTION
        s.current_player = s.highest_bidder
        s.log_event(f"{self._subj(s.highest_bidder, 'wins', 'win')} the auction at {s.bid} and chooses a secret trump.",
                    player_id=s.highest_bidder, event_type="success")

    # ================================================================== trump selection
    def human_select_trump_option(self, option: str) -> Tuple[bool, str]:
        s = self.state
        if not self.is_human_turn() or s.phase != Phase.TRUMP_SELECTION:
            return False, "It is not your turn to select trump."
        opt = option.strip().upper()

        if s.single_hand:
            suit = next((x for x in Suit if opt in (x.value.upper(), x.name.upper())), None)
            if suit is None:
                return False, "Choose a suit for your Single Hand trump."
            self._set_single_hand_trump(suit)
            return True, f"Single Hand trump: {suit.value} {suit.symbol}."

        if opt in ("SEVENTH_CARD", "7TH_CARD", "7TH"):
            if not self.rules.allow_seventh_card:
                return False, "The 7th-card trump is disabled in the house rules."
            s.is_seventh_card_trump = True
            s.trump_suit = None
            s.trump_card = None
            self._finish_trump_selection()
            if s.deal_abandoned:
                return True, f"Deal abandoned: {s.abandon_reason}"
            c = s.seventh_card
            if c is None:
                return True, ("7th-Card Trump set! Your 7th card will be laid face down as the secret trump "
                              "when the last four cards are dealt.")
            desc = f"{c.rank.name.title()} of {c.suit.value.title()} ({c.suit.symbol})"
            return True, f"7th-Card Trump set! Your secret trump is {desc}. Only you know it until it is revealed."

        suit = next((x for x in Suit if opt in (x.value.upper(), x.name.upper())), None)
        if suit is not None:
            s.is_seventh_card_trump = False
            s.trump_suit = suit
            hand = s.hands[self.human_seat]
            suit_cards = [c for c in hand if c.suit == suit]
            s.trump_card = min(suit_cards, key=lambda c: c.power) if suit_cards else None
            s.log_event(f"You chose {suit.value} {suit.symbol} as your secret trump.", player_id=self.human_seat)
            self._finish_trump_selection()
            if s.deal_abandoned:
                return True, f"Deal abandoned: {s.abandon_reason}"
            return True, f"Trump set to {suit.value}."
        try:
            return self.human_select_trump(Card.from_str(option))
        except Exception:
            return False, f"Invalid trump option: {option}"

    def human_select_trump(self, trump_card: Card) -> Tuple[bool, str]:
        s = self.state
        if not self.is_human_turn() or s.phase != Phase.TRUMP_SELECTION:
            return False, "It is not your turn to select trump."
        if trump_card not in s.hands[self.human_seat]:
            return False, f"{trump_card} is not in your hand."
        if s.single_hand:
            self._set_single_hand_trump(trump_card.suit)
            return True, "Single Hand trump set."
        s.is_seventh_card_trump = False
        s.trump_suit = trump_card.suit
        s.trump_card = trump_card
        s.log_event(f"You chose a secret trump card ({trump_card.suit.symbol}).", player_id=self.human_seat)
        self._finish_trump_selection()
        return True, "Trump set."

    def _ai_step_trump_selection(self):
        s = self.state
        bidder = s.highest_bidder
        agent = self.agents[bidder]
        masked = s.get_masked_state_for_player(bidder)
        if s.single_hand:
            suit = agent.choose_single_hand_trump(masked)
            self._log_decision(agent._record("trump", f"Trump {suit.symbol}",
                                             f"{agent.voice} named {suit.value} {suit.symbol} as the open Single Hand trump (its longest, strongest suit).",
                                             f"{agent.voice} named {suit.value} {suit.symbol} as trump.", "Suit length & power"))
            self._set_single_hand_trump(suit)
            return
        suit, card, seventh = agent.choose_trump(masked)
        self._log_decision(agent.last_decision)
        if seventh:
            s.is_seventh_card_trump = True
            s.trump_suit = None
            s.trump_card = None
            s.log_event(f"{agent.name} chose the 7th-card trump (kept face down on the table).", player_id=bidder, event_type="trump")
        else:
            s.is_seventh_card_trump = False
            s.trump_suit = suit
            s.trump_card = card
            s.log_event(f"{agent.name} chose a secret trump (concealed until revealed).", player_id=bidder)
        self._finish_trump_selection()

    def _finish_trump_selection(self):
        """
        Trump is set while everyone still holds 4 cards. Double / redouble happens now,
        before the remaining 4 cards are dealt; then the rest of the cards follow.
        """
        if self.rules.double_redouble and not self.state.single_hand:
            self._enter_doubling()
        else:
            self._deal_rest()

    def _enter_doubling(self):
        s = self.state
        s.phase = Phase.DOUBLING
        s.double_status = "NONE"
        s.doubled_by = None
        s.redoubled_by = None
        s.contract_multiplier = 1
        s.doubling_decision_player = (s.highest_bidder + 1) % 4
        s.current_player = s.doubling_decision_player
        s.log_event("Before the last four cards are dealt, the defenders may Double the contract (2×).",
                    player_id=s.doubling_decision_player)

    def _doubling_done(self):
        self.state.doubling_decision_player = None
        self._deal_rest()

    def _deal_rest(self):
        """Deals stage 2 (the last 4 cards each) and runs the authentic abandonment checks."""
        s = self.state
        bidder = s.highest_bidder
        if s.is_seventh_card_trump:
            s.hands, s.seventh_card = self.deck.deal_stage_two_with_seventh_card(s.hands, seventh_card_player_id=bidder)
            s.trump_suit = s.seventh_card.suit
            s.trump_card = s.seventh_card
            s.trump_revealed = False
            self.knowledge_bases[bidder].update_trump(s.trump_suit)
            if bidder == self.human_seat:
                s.log_event(f"Stage 2 dealt. Your 7th card is {s.seventh_card} — trump is {s.trump_suit.value} {s.trump_suit.symbol} (secret).", player_id=bidder)
            else:
                s.log_event(f"Stage 2 dealt. {self._name(bidder)}'s 7th card lies face down as the secret trump.", player_id=bidder)
        else:
            s.hands = self.deck.deal_stage_two(s.hands)
            self.knowledge_bases[bidder].update_trump(s.trump_suit)
            s.log_event("Stage 2 dealt — 8 cards each.", player_id=bidder)
        self.deal_stage = 2

        s.initial_hands = [list(h) for h in s.hands]
        if s.is_seventh_card_trump and s.seventh_card is not None and s.seventh_card not in s.initial_hands[bidder]:
            s.initial_hands[bidder].append(s.seventh_card)

        if self._check_deal_abandonment():
            return

        if not Rules.has_trump_points(s.hands[bidder], s.trump_suit):
            nm = self._name(bidder)
            if s.is_seventh_card_trump:
                reason = (f"Declarer {nm} set the 7th card ({s.seventh_card}) as trump but {'have' if nm == 'You' else 'has'} NO trump point cards "
                          f"(J, 9, A, 10) in hand. The deal is abandoned.")
            else:
                reason = (f"Declarer {nm} chose {s.trump_suit.value} {s.trump_suit.symbol} as trump but {'have' if nm == 'You' else 'has'} NO trump "
                          f"point cards (J, 9, A, 10) in hand. The deal is abandoned.")
            self.abandon_deal(reason)
            return

        self._after_full_deal()

    def _check_deal_abandonment(self) -> bool:
        s = self.state
        for p in range(4):
            hand = s.initial_hands[p]
            if sum(1 for c in hand if c.rank == Rank.JACK) == 4:
                self.abandon_deal(f"{self._subj(p, 'holds', 'hold')} all 4 Jacks! Under authentic 29 rules, the deal is abandoned.")
                return True
        for p in range(4):
            hand = s.initial_hands[p]
            if len(hand) >= 8 and len({c.suit for c in hand}) == 1:
                self.abandon_deal(f"{self._subj(p, 'holds', 'hold')} all cards of one type ({hand[0].suit.value})! Under authentic 29 rules, the deal is abandoned.")
                return True
        return False

    def _after_full_deal(self):
        """After 8 cards: optional Single Hand window, then play (doubling is already settled)."""
        sh = self.rules.single_hand
        s = self.state
        if sh.enabled and sh.timing == "after_deal" and not s.single_hand:
            s.phase = Phase.SINGLE_HAND
            s.single_hand_asked = []
            s.single_hand_turn = (s.dealer + 1) % 4
            s.log_event("All cards dealt. Any player may now call SINGLE HAND before the first lead.", event_type="info")
            return
        self._start_playing_phase()

    def _start_playing_phase(self):
        s = self.state
        s.phase = Phase.PLAYING
        if s.single_hand:
            lead = s.single_hand_declarer
        else:
            lead = (s.dealer + 1) % 4
        if lead == s.sitting_out:
            lead = s.next_player(lead)
        s.current_player = lead
        s.current_trick = Trick(trick_number=0, lead_player=lead, size=s.trick_size)
        s.log_event(f"Play begins — {self._name(lead)} leads to trick 1.", player_id=lead)

    def set_double_redouble_enabled(self, enabled: bool):
        self.rules.double_redouble = enabled
        self.state.double_redouble_enabled = enabled

    # ================================================================== Single Hand
    def human_single_hand_decision(self, declare: bool) -> Tuple[bool, str]:
        s = self.state
        if s.phase != Phase.SINGLE_HAND or s.single_hand_turn != self.human_seat:
            return False, "It is not your turn to decide on Single Hand."
        return self._single_hand_answer(self.human_seat, declare)

    def _ai_step_single_hand(self):
        p = self.state.single_hand_turn
        agent = self.agents[p]
        masked = self.state.get_masked_state_for_player(p)
        go, rec = agent.decide_single_hand(masked)
        if go:
            self._log_decision(rec)
        self._single_hand_answer(p, go)

    def _single_hand_answer(self, player: int, declare: bool) -> Tuple[bool, str]:
        s = self.state
        if declare:
            self._begin_single_hand(player, from_auction=False)
            return True, f"{self._name(player)} called Single Hand."
        s.single_hand_asked.append(player)
        if len(s.single_hand_asked) >= 4:
            s.single_hand_turn = None
            s.log_event("Nobody called Single Hand.", event_type="info")
            self._start_playing_phase()
        else:
            s.single_hand_turn = (player + 1) % 4
        return True, "No Single Hand."

    def _begin_single_hand(self, declarer: int, from_auction: bool):
        s = self.state
        sh = self.rules.single_hand
        # A concealed 7th card returns to its owner: Single Hand voids the secret trump.
        if s.is_seventh_card_trump and s.seventh_card is not None and s.highest_bidder is not None:
            if s.seventh_card not in s.hands[s.highest_bidder]:
                s.hands[s.highest_bidder].append(s.seventh_card)
                s.hands[s.highest_bidder] = Card.sort_cards(s.hands[s.highest_bidder])
        if s.target_bid <= 0:
            s.target_bid = s.bid if s.bid else self.rules.min_bid
        s.single_hand = True
        s.single_hand_declarer = declarer
        s.highest_bidder = declarer
        s.single_hand_turn = None
        s.sitting_out = GameState.get_partner(declarer) if sh.partner_sits_out else None
        s.is_seventh_card_trump = False
        s.seventh_card = None
        s.trump_suit = None
        s.trump_card = None
        s.trump_revealed = True
        s.double_status = "NONE"
        s.contract_multiplier = 1
        nm = self._name(declarer)
        partner_txt = (f"{self._name(GameState.get_partner(declarer))} lays their cards down and sits out."
                       if sh.partner_sits_out else "Partner keeps playing.")
        s.log_event(f"SINGLE HAND called by {nm}! Win condition: {sh.win_condition_text()}. {partner_txt}",
                    player_id=declarer, event_type="single")
        s.single_hand_result = {"declarer": declarer, "win_condition": sh.win_condition_text(),
                                "partner_sits_out": sh.partner_sits_out, "trump_rule": sh.trump}

        if from_auction:
            s.hands = self.deck.deal_stage_two(s.hands)
            self.deal_stage = 2
            s.initial_hands = [list(h) for h in s.hands]
            s.log_event("Stage 2 dealt — 8 cards each.", event_type="info")
            if self._check_deal_abandonment():
                return

        if sh.trump == "declarer_chooses":
            s.trump_revealed = False
            s.phase = Phase.TRUMP_SELECTION
            s.current_player = declarer
            return
        s.log_event("Single Hand is played with no trump.", event_type="trump")
        self._start_playing_phase()

    def _set_single_hand_trump(self, suit: Suit):
        s = self.state
        s.trump_suit = suit
        s.trump_revealed = True
        s.trump_revealer = s.single_hand_declarer
        s.trump_reveal_trick = 1
        for kb in self.knowledge_bases:
            kb.update_trump(suit)
        s.log_event(f"{self._subj(s.single_hand_declarer, 'names', 'name')} {suit.value} {suit.symbol} as the open trump for the Single Hand.",
                    player_id=s.single_hand_declarer, event_type="trump")
        self._start_playing_phase()

    # ================================================================== doubling
    def human_double(self, will_double: bool) -> Tuple[bool, str]:
        if not self.is_human_turn() or self.state.phase != Phase.DOUBLING:
            return False, "It is not your turn to double."
        if self.state.double_status != "NONE":
            return False, "The contract is already doubled."
        return self._handle_double_decision(self.human_seat, will_double)

    def human_redouble(self, will_redouble: bool) -> Tuple[bool, str]:
        if not self.is_human_turn() or self.state.phase != Phase.DOUBLING:
            return False, "It is not your turn to redouble."
        if self.state.double_status != "DOUBLED":
            return False, "The contract is not doubled."
        return self._handle_redouble_decision(self.human_seat, will_redouble)

    def _handle_double_decision(self, player_id: int, will_double: bool) -> Tuple[bool, str]:
        s = self.state
        nm = self._name(player_id)
        bidder = s.highest_bidder
        if will_double:
            s.double_status = "DOUBLED"
            s.doubled_by = player_id
            s.contract_multiplier = 2
            s.log_event(f"{nm} DOUBLED the contract! Stakes are now 2×.", player_id=player_id, event_type="double")
            s.doubling_decision_player = bidder
            s.current_player = bidder
            return True, f"{nm} doubled."
        s.log_event(f"{nm} declined to double.", player_id=player_id, event_type="pass")
        defenders = [(bidder + 1) % 4, (bidder + 3) % 4]
        if player_id == defenders[0]:
            s.doubling_decision_player = defenders[1]
            s.current_player = defenders[1]
            return True, "Other defender may double."
        self._doubling_done()
        return True, "No double — the last four cards are dealt."

    def _handle_redouble_decision(self, player_id: int, will_redouble: bool) -> Tuple[bool, str]:
        s = self.state
        nm = self._name(player_id)
        bidder = s.highest_bidder
        if will_redouble:
            s.double_status = "REDOUBLED"
            s.redoubled_by = player_id
            s.contract_multiplier = 4
            s.log_event(f"{nm} REDOUBLED! Stakes are now 4×.", player_id=player_id, event_type="redouble")
            self._doubling_done()
            return True, f"{nm} redoubled."
        s.log_event(f"{nm} declined to redouble.", player_id=player_id, event_type="pass")
        if player_id == bidder:
            s.doubling_decision_player = (bidder + 2) % 4
            s.current_player = s.doubling_decision_player
            return True, "Partner may redouble."
        self._doubling_done()
        return True, "No redouble — the contract stays at 2×."

    def _ai_step_doubling(self):
        s = self.state
        p = s.doubling_decision_player
        if p is None:
            self._doubling_done()
            return
        agent = self.agents[p]
        masked = s.get_masked_state_for_player(p)
        if s.double_status == "NONE":
            go, rec = agent.decide_double(masked, self.knowledge_bases[p])
            self._log_decision(rec)
            self._handle_double_decision(p, go)
        else:
            go, rec = agent.decide_redouble(masked, self.knowledge_bases[p])
            self._log_decision(rec)
            self._handle_redouble_decision(p, go)

    # ================================================================== play
    def human_play_card(self, card: Card) -> Tuple[bool, str]:
        s = self.state
        if s.deal_abandoned:
            return False, "The deal was abandoned."
        if s.pending_trick_pause:
            return False, "Wait for the trick to be collected."
        if not self.is_human_turn() or s.phase != Phase.PLAYING:
            return False, "It is not your turn to play."
        self._force_seventh_reveal_if_needed(self.human_seat)
        if s.deal_abandoned:
            return False, "Deal abandoned: the declarer had no trump point cards."
        valid, proof = PropositionalRuleValidator.validate_card_play(self.human_seat, card, s)
        if not valid:
            return False, proof
        self._apply_card_play(self.human_seat, card)
        return True, proof

    def human_reveal_trump(self) -> Tuple[bool, str]:
        s = self.state
        if not self.is_human_turn() or s.phase != Phase.PLAYING:
            return False, "It is not your turn."
        if not s.can_player_reveal_trump(self.human_seat):
            if s.trump_revealed:
                return False, "Trump is already revealed."
            return False, "You may only call for the trump when you cannot follow the lead suit."
        self._reveal_trump(revealer_id=self.human_seat)
        if s.deal_abandoned:
            return True, f"Trump revealed: {s.abandon_reason}"
        return True, f"Trump revealed: {s.trump_suit.value} {s.trump_suit.symbol}"

    def _force_seventh_reveal_if_needed(self, p: int):
        s = self.state
        if (s.is_seventh_card_trump and not s.trump_revealed and p == s.highest_bidder
                and len(s.hands[p]) <= 1):
            s.log_event(f"{self._subj(p, 'must', 'must')} turn up the 7th card before playing the last cards.", player_id=p)
            self._reveal_trump(revealer_id=p)

    def _ai_step_playing(self):
        s = self.state
        p = s.current_player
        if p == s.sitting_out:
            s.current_player = s.next_player(p)
            return
        if not s.hands[p]:
            return
        agent = self.agents[p]
        kb = self.knowledge_bases[p]

        if self.rules.marriage_mode == "after_trick" and s.can_player_declare_pair(p):
            self.declare_pair(p)

        self._force_seventh_reveal_if_needed(p)
        if s.deal_abandoned:
            return

        masked = s.get_masked_state_for_player(p)
        if not s.trump_revealed and s.can_player_reveal_trump(p) and agent.should_reveal_trump(masked, kb):
            self._log_decision(agent.last_decision)
            self._reveal_trump(revealer_id=p)
            if s.deal_abandoned:
                return
            masked = s.get_masked_state_for_player(p)

        card, insight = agent.choose_card(masked, kb)
        if card is None:
            return
        self._log_decision(agent.last_decision)
        s.latest_insight = insight
        self._apply_card_play(p, card)

    def _reveal_trump(self, revealer_id: int):
        s = self.state
        bidder = s.highest_bidder
        rname = self._name(revealer_id)
        if s.is_seventh_card_trump and s.seventh_card is not None:
            card7 = s.seventh_card
            s.trump_suit = card7.suit
            s.trump_card = card7
            s.trump_revealed = True
            s.trump_revealer = revealer_id
            s.trump_reveal_trick = len(s.completed_tricks) + 1
            for kb in self.knowledge_bases:
                kb.update_trump(card7.suit)
            s.log_event(f"{rname} called for the trump! The 7th card is {card7} — trump is {card7.suit.value} {card7.suit.symbol}!",
                        player_id=revealer_id, event_type="trump")
            if not Rules.has_trump_points(s.hands[bidder], card7.suit):
                self.abandon_deal(f"The 7th card is {card7}, but declarer {self._subj(bidder, 'has', 'have')} NO trump point cards "
                                  f"(J, 9, A, 10) in hand. The deal is abandoned.")
                return
            s.hands[bidder].append(card7)
            s.log_event(f"The 7th card returns to {self._name(bidder)}'s hand.", player_id=bidder)
        else:
            s.trump_revealed = True
            s.trump_revealer = revealer_id
            s.trump_reveal_trick = len(s.completed_tricks) + 1
            for kb in self.knowledge_bases:
                kb.update_trump(s.trump_suit)
            s.log_event(f"{rname} called for the trump! Trump is {s.trump_suit.value} {s.trump_suit.symbol}.",
                        player_id=revealer_id, event_type="trump")

        # Authentic rule: if the defending team held no trump at all, the deal is void.
        suit = s.trump_suit
        bt = s.get_team(bidder)
        defenders = [p for p in range(4) if s.get_team(p) != bt]
        if any(len(h) > 0 for h in s.initial_hands):
            if sum(1 for p in defenders for c in s.initial_hands[p] if c.suit == suit) == 0:
                self.abandon_deal(
                    f"Trump revealed as {suit.value} {suit.symbol}, but the opposing team (Team {chr(65 + 1 - bt)}, who did not set trump) "
                    f"had NO trump cards at the beginning of the deal! Under authentic 29 rules, the deal is abandoned.")
                return

        if self.rules.marriage_enabled and self.rules.marriage_mode == "auto":
            self._check_and_apply_marriage()

    def _apply_marriage(self, p: int):
        s = self.state
        bidder = s.highest_bidder
        bt = s.get_team(bidder)
        team = s.get_team(p)
        val = self.rules.marriage_value
        s.pair_declared = True
        s.pair_declarer = p
        s.pair_declarer_team = team
        s.pair_points = val
        old = s.target_bid
        if team == bt:
            s.target_bid = max(self.rules.min_bid, s.target_bid - val)
            msg = (f"ROYAL MARRIAGE (K & Q of {s.trump_suit.value}) held by {self._name(p)}! "
                   f"The declaring team's target drops {old} → {s.target_bid} (minimum {self.rules.min_bid}).")
        else:
            s.target_bid = min(self.rules.max_bid, s.target_bid + val)
            msg = (f"ROYAL MARRIAGE (K & Q of {s.trump_suit.value}) held by defender {self._name(p)}! "
                   f"The declaring team's target rises {old} → {s.target_bid}.")
        s.pair_adjustment = s.target_bid - old
        s.marriage_popup_pending = True
        s.marriage_popup_info = {
            "player": p, "player_name": self._name(p), "trump_suit": s.trump_suit.value,
            "trump_symbol": s.trump_suit.symbol, "team": team, "is_bidder_team": team == bt,
            "old_bid": old, "new_bid": s.target_bid, "adjustment": s.pair_adjustment, "message": msg,
        }
        s.log_event(msg, player_id=p, event_type="pair")
        return msg

    def _check_and_apply_marriage(self):
        s = self.state
        if s.deal_abandoned or not s.trump_revealed or s.trump_suit is None or s.pair_declared or s.single_hand:
            return
        if s.highest_bidder is None:
            return
        for p in range(4):
            hand = s.hands[p]
            if (any(c.suit == s.trump_suit and c.rank == Rank.KING for c in hand) and
                    any(c.suit == s.trump_suit and c.rank == Rank.QUEEN for c in hand)):
                self._apply_marriage(p)
                break

    def declare_pair(self, player_id: int) -> Tuple[bool, str]:
        s = self.state
        if not self.rules.marriage_enabled:
            return False, "Marriage is disabled in the house rules."
        if self.rules.marriage_mode == "after_trick":
            if not s.can_player_declare_pair(player_id):
                return False, "You can announce the marriage after your team wins a trick once trump is revealed."
        elif not Rules.can_declare_pair(player_id, s):
            return False, "Cannot declare the marriage now."
        return True, self._apply_marriage(player_id)

    def _apply_card_play(self, player_id: int, card: Card, insight: str = ""):
        s = self.state
        if s.pending_trick_pause or s.current_trick is None or s.current_trick.is_complete():
            return
        if card not in s.hands[player_id]:
            return
        s.hands[player_id].remove(card)
        is_trump = s.trump_revealed and s.trump_suit is not None and card.suit == s.trump_suit
        s.current_trick.add_card(player_id, card, is_trump=is_trump)
        s.log_event(f"{self._name(player_id)} played {card}.", player_id=player_id, event_type="play")
        if s.current_trick.is_complete():
            self._finish_trick()
        else:
            s.current_player = s.next_player(player_id)

    def _finish_trick(self):
        s = self.state
        trick = s.current_trick
        winner = Rules.determine_trick_winner(trick, s.trump_suit, s.trump_revealed)
        trick.winner = winner
        is_last = len(s.completed_tricks) == 7
        pts = Rules.calculate_trick_points(trick, is_last_trick=is_last, game_variant=s.game_variant)
        s.round_points[s.get_team(winner)] += pts
        s.tricks_won[winner] += 1
        s.log_event(f"{self._subj(winner, 'wins', 'win')} trick {len(s.completed_tricks) + 1} (+{pts} pts).",
                    player_id=winner, event_type="trick_win")
        for kb in self.knowledge_bases:
            kb.update_from_trick(trick)
        s.completed_tricks.append(trick)
        s.last_completed_trick = {
            "trick_number": len(s.completed_tricks),
            "winner": winner,
            "winner_name": self._name(winner),
            "points": pts,
            "cards": [{"player_id": pc.player_id, "card": pc.card.to_dict(), "is_trump": pc.is_trump} for pc in trick.cards],
        }
        s.pending_trick_pause = True
        s.current_player = winner

    def _single_hand_already_lost(self) -> bool:
        s = self.state
        if not s.single_hand:
            return False
        sh = self.rules.single_hand
        if not (sh.must_win_all_tricks or not sh.use_contract_target):
            return False
        counted = {s.single_hand_declarer}
        if s.sitting_out is None and sh.partner_tricks_count:
            counted.add(GameState.get_partner(s.single_hand_declarer))
        return any(t.winner not in counted for t in s.completed_tricks)

    def _end_round(self):
        s = self.state
        s.phase = Phase.ROUND_OVER
        s.current_trick = None
        t0, t1, made, _ = Rules.evaluate_round_score(s)
        self._record_round_stats(t0, t1, made)

    def clear_completed_trick(self):
        s = self.state
        if not s.pending_trick_pause:
            return
        s.pending_trick_pause = False
        winner = s.last_completed_trick["winner"] if s.last_completed_trick else 0
        if len(s.completed_tricks) >= 8 or self._single_hand_already_lost() or not any(s.hands[p] for p in range(4) if p != s.sitting_out):
            if self._single_hand_already_lost() and len(s.completed_tricks) < 8:
                s.log_event(f"{self._name(s.single_hand_declarer)} lost a trick — the Single Hand has failed.", event_type="failure")
            self._end_round()
        else:
            s.current_player = winner
            s.current_trick = Trick(trick_number=len(s.completed_tricks), lead_player=winner, size=s.trick_size)

    def next_round(self):
        s = self.state
        if s.phase == Phase.GAME_OVER:
            return
        s.round_number += 1
        s.dealer = (s.dealer + 1) % 4
        self.start_new_round()

    def step_trick(self) -> Dict[str, Any]:
        start = len(self.state.completed_tricks)
        for _ in range(24):
            s = self.state
            if s.deal_abandoned or s.pending_trick_pause or len(s.completed_tricks) > start:
                break
            if s.phase in (Phase.ROUND_OVER, Phase.GAME_OVER) or self.is_human_turn():
                break
            res = self.step()
            if res.get("status") in ("pending_trick_pause", "waiting_human", "deal_abandoned", "game_over"):
                break
        return {"status": "stepped_trick", "phase": self.state.phase.value}

    def play_round_synchronously(self) -> Dict[str, Any]:
        """Runs an entire round with all seats played by AI (tests / experiments)."""
        saved = self.human_seat
        self.human_seat = None
        guard = 0
        while self.state.phase not in (Phase.ROUND_OVER, Phase.GAME_OVER) and guard < 400:
            guard += 1
            if self.state.deal_abandoned:
                break
            if self.state.pending_trick_pause:
                self.clear_completed_trick()
                continue
            self.step()
        self.human_seat = saved
        s = self.state
        return {
            "round_points": list(s.round_points),
            "game_points": list(s.game_points),
            "bid": s.bid,
            "target_bid": s.target_bid,
            "bidder": s.single_hand_declarer if s.single_hand else s.highest_bidder,
            "single_hand": s.single_hand,
            "trump": s.trump_suit.value if s.trump_suit else None,
            "abandoned": s.deal_abandoned,
        }
