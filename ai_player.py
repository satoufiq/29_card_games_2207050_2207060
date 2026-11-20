"""
AI agent for Bangladeshi 29.

Card play:   GameState(masked) → Legal moves → ISMCTS (or exact Minimax in the
             endgame) → personality Fuzzy move evaluator → blended choice.
Bidding:     Hand evaluation → Fuzzy bidding evaluator → Personality profile
             (Monte Carlo expected utility) → Bid / Hold / Pass / Single Hand.

Every decision produces a record with a short personality-flavoured summary,
a "public" summary that never mentions cards still hidden in the AI's hand,
and advanced details (fuzzy inputs/outputs, simulations, candidate scores).
Agents only ever receive masked states: they cannot see other hands.
"""
from enum import Enum
from typing import Optional, Tuple, List, Dict, Any
import random

from card import Card, Suit, Rank
from game_state import GameState
from rules import Rules
from logic_engine import PropositionalRuleValidator
from knowledge_base import PredicateKnowledgeBase
from fuzzy_system import MamdaniFuzzyBidding, MamdaniEngine
from mc_bidding import MonteCarloExpectedUtilityBidding, BidEvaluationResult
from mcts import InformationSetMCTS
from minimax import EndgameMinimax
from ai_profiles import get_profile, PersonalityProfile
from sim_engine import (sample_world, estimate_contract, estimate_contract_predeal, estimate_single_hand,
                        public_voids, trump_hypothesis_weights, known_trump_for, ALL_CARDS, POWER, POINTS)


class AIStrategy(str, Enum):
    AGGRESSIVE = "AGGRESSIVE"
    STRATEGIC = "STRATEGIC"
    DEFENSIVE = "DEFENSIVE"
    CONSERVATIVE = "DEFENSIVE"     # alias
    HYBRID = "HYBRID"              # plays with the Strategic profile
    BASELINE_RULE = "RULE_BASED"
    BASELINE_RANDOM = "RANDOM"


PERSONALITY_VOICE = {
    "AGGRESSIVE": "Aggressive AI",
    "STRATEGIC": "Strategic AI",
    "DEFENSIVE": "Defensive AI",
}


class AIPlayer:
    def __init__(self, player_id: int, name: str, strategy: AIStrategy = AIStrategy.STRATEGIC,
                 mcts_sims: Optional[int] = None, endgame_threshold: Optional[int] = None,
                 seed: Optional[int] = None, budget_scale: float = 1.0):
        self.player_id = player_id
        self.name = name
        self.rng = random.Random(seed)
        self.budget_scale = budget_scale
        self._strategy = strategy
        self.profile: PersonalityProfile = get_profile(strategy.value)
        iters = mcts_sims if mcts_sims is not None else int(self.profile.mcts_iterations * budget_scale)
        self.mcts = InformationSetMCTS(simulations_per_move=max(30, iters),
                                       time_budget=self.profile.mcts_time_budget * max(0.3, budget_scale))
        self.mcts_sims = self.mcts.simulations_per_move
        self.endgame_threshold = endgame_threshold if endgame_threshold is not None else self.profile.endgame_cards
        self.preferred_trump: Optional[Suit] = None
        self.last_bid_eval: Optional[BidEvaluationResult] = None
        self.last_decision: Optional[Dict[str, Any]] = None

    # ------------------------------------------------------------ properties
    @property
    def strategy(self) -> AIStrategy:
        return self._strategy

    @strategy.setter
    def strategy(self, value: AIStrategy):
        self._strategy = value
        self.profile = get_profile(value.value)
        self.mcts.simulations_per_move = max(30, int(self.profile.mcts_iterations * self.budget_scale))
        self.mcts.time_budget = self.profile.mcts_time_budget * max(0.3, self.budget_scale)
        self.mcts_sims = self.mcts.simulations_per_move
        self.endgame_threshold = self.profile.endgame_cards

    def set_budget_scale(self, scale: float):
        self.budget_scale = max(0.2, min(2.0, scale))
        self.strategy = self._strategy

    @property
    def voice(self) -> str:
        return PERSONALITY_VOICE.get(self.profile.key, "AI")

    @property
    def is_baseline(self) -> bool:
        return self._strategy in (AIStrategy.BASELINE_RANDOM, AIStrategy.BASELINE_RULE)

    def _record(self, kind: str, action: str, summary: str, public_summary: str,
                algorithm: str, details: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        rec = {
            "player": self.player_id,
            "name": self.name,
            "personality": self.profile.key,
            "kind": kind,
            "action": action,
            "summary": summary,
            "public_summary": public_summary,
            "algorithm": algorithm,
            "details": details or {},
        }
        self.last_decision = rec
        return rec

    # ================================================================ BIDDING
    def decide_bid(self, state: GameState) -> Tuple[str, Optional[int], Dict[str, Any]]:
        """Returns (action, value, record) where action is BID, PASS or SINGLE."""
        hand = state.hands[self.player_id]
        lo = state.min_next_bid
        hi = state.rules.max_bid

        if self._strategy == AIStrategy.BASELINE_RANDOM:
            if self.rng.random() < 0.4 and lo <= min(20, hi):
                return "BID", lo, self._record("bid", f"Bid {lo}", "Random baseline bid.", "Random baseline bid.", "Random")
            return "PASS", None, self._record("bid", "Pass", "Random baseline pass.", "Random baseline pass.", "Random")
        if self._strategy == AIStrategy.BASELINE_RULE:
            rec = MamdaniFuzzyBidding.evaluate_hand(hand)["recommended_bid"]
            if rec and lo <= rec and lo <= hi:
                return "BID", lo, self._record("bid", f"Bid {lo}", "Rule-based bid.", "Rule-based bid.", "Rules")
            return "PASS", None, self._record("bid", "Pass", "Rule-based pass.", "Rule-based pass.", "Rules")

        # --- Single Hand as an auction call
        sh = state.rules.single_hand
        if sh.enabled and sh.timing == "auction" and state.player_bids.get(self.player_id) != "PASS":
            strong = sum(1 for c in hand if c.rank in (Rank.JACK, Rank.NINE))
            if strong >= 3:
                trump = None
                if sh.trump == "declarer_chooses":
                    trump = MamdaniFuzzyBidding.evaluate_hand(hand)["best_suit"]
                p_sh = estimate_single_hand(self.player_id, state, trump, sh.partner_sits_out,
                                            n=48, rng=self.rng, extra_unknown_own=8 - len(hand))
                if p_sh >= self.profile.single_hand_threshold:
                    msg = (f"{self.voice} called SINGLE HAND: simulations give a {p_sh:.0%} chance of winning every trick "
                           f"(needs {self.profile.single_hand_threshold:.0%}).")
                    return "SINGLE", None, self._record(
                        "bid", "Single Hand", msg,
                        f"{self.voice} judged its hand strong enough to win every trick alone.",
                        "Monte Carlo Single Hand estimate",
                        {"single_hand_probability": round(p_sh, 3), "threshold": self.profile.single_hand_threshold})

        ev = MonteCarloExpectedUtilityBidding.evaluate_all_bids(
            hand=hand, player_id=self.player_id, state=state, ai_strategy=self.profile.key,
            simulations_per_suit=max(24, int(36 * self.budget_scale)), rng=self.rng, profile=self.profile)
        self.last_bid_eval = ev
        self.preferred_trump = ev.trump

        fz = ev.fuzzy
        conf = fz["outputs"]["bid_confidence"]
        tp = fz["inputs"]["trump_strength"]
        hs = fz["inputs"]["hand_strength"]
        partner = GameState.get_partner(self.player_id)

        if ev.bid is None:
            if state.highest_bidder == partner:
                why = "its partner already holds the contract and its own hand adds too little to overcall"
            elif ev.max_bid is None:
                why = f"the expected contract risk was too high (P(make {lo}) = {ev.success_probability:.0%}, bar {ev.threshold:.0%})"
            else:
                why = f"its ceiling is {ev.max_bid}, below the required {lo}"
            if self.profile.key == "AGGRESSIVE":
                summary = f"{self.voice} passed — even with a high risk appetite, {why}."
            elif self.profile.key == "DEFENSIVE":
                summary = f"{self.voice} passed because {why}."
            else:
                summary = f"{self.voice} weighed the partnership's chances and passed: {why}."
            public = f"{self.voice} passed: the expected contract risk was too high for its style." \
                if state.highest_bidder != partner else f"{self.voice} passed to let its partner keep the contract."
            action, value = "PASS", None
            act_text = "Pass"
        else:
            value = ev.bid
            action = "BID"
            act_text = f"Bid {value}"
            trump_word = "strong" if tp >= 60 else ("useful" if tp >= 35 else "modest")
            if self.profile.key == "AGGRESSIVE":
                if ev.action_kind == "OPEN":
                    summary = f"{self.voice} opened at {value} to seize the initiative: {trump_word} trump potential in {ev.trump.symbol} (fuzzy confidence {conf:.0f})."
                else:
                    summary = f"{self.voice} raised to {value} because of {trump_word} trump potential — it will push up to {ev.max_bid}."
                public = f"{self.voice} {'opened at' if ev.action_kind == 'OPEN' else 'raised to'} {value}, betting on its trump potential."
            elif self.profile.key == "DEFENSIVE":
                summary = (f"{self.voice} bid {value} only after the simulations cleared its high safety bar "
                           f"(P(make) {ev.success_probability:.0%} ≥ {ev.threshold:.0%}).")
                public = f"{self.voice} bid {value}: its estimated chance of making the contract cleared its safety bar."
            else:
                summary = (f"{self.voice} estimated future trick-winning potential before {'opening' if ev.action_kind == 'OPEN' else 'raising'} to {value}: "
                           f"P(make) {ev.success_probability:.0%} with {ev.trump.value} trumps, partnership adjustment {ev.auction_adjustment:+.1f} pts.")
                public = f"{self.voice} estimated future trick-winning potential before bidding {value}."
            if ev.action_kind == "HOLD":
                act_text = f"Hold {value}"
                if self.profile.key == "AGGRESSIVE":
                    summary = f"{self.voice} held at {value} — it will keep fighting up to {ev.max_bid}."
                elif self.profile.key == "DEFENSIVE":
                    summary = f"{self.voice} held at {value}: P(make) {ev.success_probability:.0%} still clears its safety bar."
                else:
                    summary = f"{self.voice} held at {value}: P(make) {ev.success_probability:.0%}, ceiling {ev.max_bid}."
                public = f"{self.voice} held at {value}."
            if ev.action_kind == "OVER_PARTNER":
                summary += " (It took the contract over from its partner.)"
                public += " (Taking over from its partner.)"

        details = {
            "hand_strength": round(hs, 1),
            "fuzzy_inputs": fz["inputs"],
            "fuzzy_outputs": {k: fz["outputs"][k] for k in ("bid_confidence", "risk_tolerance")},
            "fuzzy_rules": fz["rules"],
            "risk": round(fz["inputs"]["risk"], 1),
            "simulations": ev.simulations,
            "success_probability": ev.success_probability,
            "probability_bar": ev.threshold,
            "ceiling": ev.max_bid,
            "best_trump": ev.trump.value if ev.trump else None,
            "auction_adjustment": ev.auction_adjustment,
            "expected_utility": ev.expected_utility,
            "pass_utility": ev.pass_utility,
            "selected": act_text,
        }
        rec = self._record("bid", act_text, summary, public, "MCEUB + Fuzzy (" + self.profile.label + " rules)", details)
        state.latest_insight = f"{self.name}: {summary}"
        return action, value, rec

    def choose_bid(self, state: GameState) -> Optional[int]:
        action, value, _ = self.decide_bid(state)
        return value if action == "BID" else None

    # ================================================================ TRUMP
    def choose_trump(self, state: GameState) -> Tuple[Optional[Suit], Optional[Card], bool]:
        hand = state.hands[self.player_id]
        point_suits = sorted({c.suit for c in hand if c.points > 0}, key=lambda s: s.value)
        if not point_suits:
            if state.rules.allow_seventh_card:
                self._record("trump", "7th card", f"{self.voice} holds no point cards, so it trusts the concealed 7th card for trump.",
                             f"{self.voice} chose the concealed 7th-card trump.", "Rule check")
                return None, None, True
            point_suits = sorted({c.suit for c in hand}, key=lambda s: s.value)

        ev = self.last_bid_eval
        scores = {}
        for s in point_suits:
            feats = MamdaniFuzzyBidding.compute_trump_potential(hand, s)
            length = sum(1 for c in hand if c.suit == s)
            p = ev.suit_evaluations.get(s, {}).get("success_probability", 0.0) if ev else 0.0
            scores[s] = p * 100 + feats * 0.4 + length * 6
        best = max(point_suits, key=lambda s: scores[s])
        card = min([c for c in hand if c.suit == best], key=lambda c: c.power)
        self.preferred_trump = best
        self._record("trump", f"Trump {best.symbol}",
                     f"{self.voice} chose {best.value} {best.symbol} as the concealed trump (best simulated contract chances and suit length).",
                     f"{self.voice} chose a concealed trump suit.", "MCEUB suit ranking",
                     {"suit_scores": {s.value: round(v, 1) for s, v in scores.items()}})
        return best, card, False

    def choose_single_hand_trump(self, state: GameState) -> Optional[Suit]:
        hand = state.hands[self.player_id]
        suits = {s: [c for c in hand if c.suit == s] for s in Suit}
        return max(Suit, key=lambda s: (len(suits[s]), sum(POWER[c] for c in suits[s])))

    # ================================================================ SINGLE HAND (after deal)
    def decide_single_hand(self, state: GameState) -> Tuple[bool, Dict[str, Any]]:
        sh = state.rules.single_hand
        hand = state.hands[self.player_id]
        if self.is_baseline:
            return False, self._record("single", "No Single Hand", "Baseline never calls Single Hand.", "", "Baseline")
        masters = sum(1 for c in hand if c.rank in (Rank.JACK, Rank.NINE))
        if masters < 4:
            rec = self._record("single", "No Single Hand",
                               f"{self.voice} declined Single Hand: too few master cards to win every trick alone.",
                               f"{self.voice} declined Single Hand.", "Hand screen", {"master_cards": masters})
            return False, rec
        trump = self.choose_single_hand_trump(state) if sh.trump == "declarer_chooses" else None
        p = estimate_single_hand(self.player_id, state, trump, sh.partner_sits_out, n=80, rng=self.rng)
        go = p >= self.profile.single_hand_threshold
        summary = (f"{self.voice} {'CALLED' if go else 'declined'} Single Hand: simulations give {p:.0%} to win all tricks "
                   f"(its bar is {self.profile.single_hand_threshold:.0%}).")
        rec = self._record("single", "Single Hand" if go else "No Single Hand", summary,
                           f"{self.voice} {'called' if go else 'declined'} Single Hand.",
                           "Monte Carlo Single Hand estimate",
                           {"single_hand_probability": round(p, 3), "threshold": self.profile.single_hand_threshold,
                            "simulations": 80})
        return go, rec

    # ================================================================ DOUBLING
    def _contract_estimate(self, state: GameState, kb: Optional[PredicateKnowledgeBase]) -> Dict[str, float]:
        """Doubling happens before the last 4 cards are dealt, so it usually sees only 4 cards."""
        n = max(24, int(40 * self.budget_scale))
        if len(state.hands[self.player_id]) < 8 and not state.completed_tricks:
            return estimate_contract_predeal(self.player_id, state, n=n, rng=self.rng)
        return estimate_contract(self.player_id, state, kb, n=n, rng=self.rng)

    def decide_double(self, state: GameState, kb: Optional[PredicateKnowledgeBase] = None) -> Tuple[bool, Dict[str, Any]]:
        est = self._contract_estimate(state, kb)
        p_fail = 1.0 - est["p_made"]
        go = p_fail >= self.profile.double_threshold
        summary = (f"{self.voice} {'DOUBLED' if go else 'did not double'}: it estimates the contract fails "
                   f"{p_fail:.0%} of the time (doubles at {self.profile.double_threshold:.0%}).")
        rec = self._record("double", "Double" if go else "No double", summary,
                           f"{self.voice} {'doubled' if go else 'declined to double'} the contract.",
                           "Monte Carlo contract estimate",
                           {"p_contract_fails": round(p_fail, 3), "simulations": est["samples"]})
        return go, rec

    def decide_redouble(self, state: GameState, kb: Optional[PredicateKnowledgeBase] = None) -> Tuple[bool, Dict[str, Any]]:
        est = self._contract_estimate(state, kb)
        p = est["p_made"]
        go = p >= self.profile.redouble_threshold
        summary = (f"{self.voice} {'REDOUBLED' if go else 'did not redouble'}: P(contract makes) ≈ {p:.0%} "
                   f"(redoubles at {self.profile.redouble_threshold:.0%}).")
        rec = self._record("double", "Redouble" if go else "No redouble", summary,
                           f"{self.voice} {'redoubled' if go else 'declined to redouble'}.",
                           "Monte Carlo contract estimate", {"p_contract_makes": round(p, 3), "simulations": est["samples"]})
        return go, rec

    # ================================================================ TRUMP REVEAL
    def should_reveal_trump(self, state: GameState, kb: Optional[PredicateKnowledgeBase] = None) -> bool:
        if state.trump_revealed or state.single_hand:
            return False
        trick = state.current_trick
        if trick is None or not trick.cards:
            return False
        hand = state.hands[self.player_id]
        lead = trick.lead_suit
        if any(c.suit == lead for c in hand):
            return False
        winner = Rules.determine_trick_winner(trick, None, False)
        if GameState.get_team(winner) == GameState.get_team(self.player_id):
            return False
        pts = trick.points
        done = len(state.completed_tricks)

        trump, known = known_trump_for(self.player_id, state, kb)
        if known and trump is not None:
            p_hold = 1.0 if any(c.suit == trump for c in hand) else 0.0
        else:
            played = {pc.card for t in state.completed_tricks for pc in t.cards} | {pc.card for pc in trick.cards}
            unseen = [c for c in ALL_CARDS if c not in played and c not in hand]
            w = trump_hypothesis_weights(self.player_id, state, unseen, public_voids(state, kb))
            tot = sum(w.values()) or 1.0
            p_hold = sum(w[s] / tot for s in Suit if any(c.suit == s for c in hand))

        bidder_team = GameState.get_team(state.highest_bidder) if state.highest_bidder is not None else None
        on_bidder_side = bidder_team == GameState.get_team(self.player_id)
        need_pts = self.profile.reveal_min_points + (1 if on_bidder_side and self.player_id != state.highest_bidder else 0)
        if self.profile.key == "AGGRESSIVE" and done >= 2:
            need_pts = min(need_pts, 0)
        go = pts >= need_pts and p_hold >= self.profile.reveal_prob_holding
        if go:
            self._record("reveal", "Call trump",
                         f"{self.voice} called for the trump: void in {lead.value}, opponents winning {pts} pts, "
                         f"P(holding a trump) ≈ {p_hold:.0%}.",
                         f"{self.voice} called for the trump to fight for a {pts}-point trick.",
                         "Belief over hidden trump", {"p_holding_trump": round(p_hold, 2), "trick_points": pts})
        return go

    # ================================================================ CARD PLAY
    def choose_card(self, state: GameState, knowledge_base: PredicateKnowledgeBase) -> Tuple[Card, str]:
        legal = Rules.get_legal_cards(self.player_id, state)
        hand = state.hands[self.player_id]
        if not legal:
            if hand:
                return hand[0], "Fallback legal card selection"
            return None, f"Player {self.player_id} has no cards left"

        if len(legal) == 1:
            _, proof = PropositionalRuleValidator.validate_card_play(self.player_id, legal[0], state)
            card = legal[0]
            self._record("play", f"Played {card}", f"{self.voice} played {card}: its only legal card.",
                         f"{self.voice} played {card}: its only legal card.", "Forced move",
                         {"selected": str(card), "proof": proof})
            return card, f"Forced move: {card} ({proof})"

        if self._strategy == AIStrategy.BASELINE_RANDOM:
            card = self.rng.choice(legal)
            self._record("play", f"Played {card}", "Random baseline.", "Random baseline.", "Random")
            return card, f"Random baseline selected {card}."
        if self._strategy == AIStrategy.BASELINE_RULE:
            card = self._rule_heuristic_card(state, legal)
            self._record("play", f"Played {card}", "Rule-based heuristic.", "Rule-based heuristic.", "Rules")
            return card, f"Rule-based heuristic selected {card}."

        features = {c: self._move_features(state, knowledge_base, c) for c in legal}
        engine = MamdaniEngine(self.profile.play_rules)
        fuzzy_eval = {c: engine.infer(features[c]["inputs"]) for c in legal}
        fz_score = {
            c: fuzzy_eval[c]["outputs"]["desirability"] / 100.0
               - self.profile.preservation_weight * (fuzzy_eval[c]["outputs"]["preservation"] / 100.0)
                 * (features[c]["inputs"]["card_value"] / 100.0)
            for c in legal
        }

        if len(hand) <= self.endgame_threshold:
            card, details, algo = self._endgame_choice(state, knowledge_base, legal, fz_score)
        else:
            card, details, algo = self._ismcts_choice(state, knowledge_base, legal, fz_score)

        sel_fz = fuzzy_eval[card]
        details.update({
            "fuzzy_inputs": sel_fz["inputs"],
            "fuzzy_outputs": {k: sel_fz["outputs"][k] for k in ("desirability", "preservation")},
            "fuzzy_rules": sel_fz["rules"],
            "selected": str(card),
            "hand_strength": round(sum(POWER[c] for c in hand) / max(1, len(hand)) / 8 * 100, 1),
            "risk": sel_fz["inputs"].get("risk"),
            "captures": bool(features[card]["i_win"]),
            "card_power": POWER[card],
            "partner_winning": features[card]["win_before_team"] == GameState.get_team(self.player_id),
        })
        summary, public = self._explain_play(state, card, features, legal)
        self._record("play", f"Played {card}", summary, public, algo, details)
        insight = f"{algo}: {summary}"
        return card, insight

    def _ismcts_choice(self, state, kb, legal, fz_score):
        effective_trump, _ = known_trump_for(self.player_id, state, kb)
        best, info = self.mcts.search(player_id=self.player_id, state=state, knowledge_base=kb,
                                      effective_trump=effective_trump, profile=self.profile,
                                      rng=self.rng, root_legal=legal)
        cands = {c["code"]: c for c in info.get("candidates", [])}
        vals = []
        for c in legal:
            cd = cands.get(c.code, {"visits": 0, "value": 0.0})
            vals.append(cd["value"])
        mean_v = sum(vals) / len(vals) if vals else 0.0
        k = 6.0
        shrunk = {}
        for c in legal:
            cd = cands.get(c.code, {"visits": 0, "value": mean_v})
            n = cd["visits"]
            shrunk[c] = (cd["value"] * n + mean_v * k) / (n + k)
        spread = max(0.08, max(shrunk.values()) - min(shrunk.values()))
        mean_fz = sum(fz_score.values()) / len(fz_score)
        wf = self.profile.fuzzy_play_weight
        combined = {c: shrunk[c] + wf * (fz_score[c] - mean_fz) * spread * 1.5 for c in legal}
        card = max(legal, key=lambda c: (combined[c], -POWER[c]))
        table = sorted(
            [{"card": str(c), "code": c.code, "visits": cands.get(c.code, {}).get("visits", 0),
              "mcts": round(shrunk[c], 3), "fuzzy": round(fz_score[c], 3), "score": round(combined[c], 3)}
             for c in legal], key=lambda r: -r["score"])
        details = {"simulations": info.get("iterations", 0), "elapsed": info.get("elapsed"),
                   "candidates": table, "fuzzy_weight": wf}
        return card, details, "SO-ISMCTS + Fuzzy"

    def _endgame_choice(self, state, kb, legal, fz_score):
        worlds, trumps = [], []
        for _ in range(8):
            h, t = sample_world(self.player_id, state, kb, self.rng, attempts=6)
            worlds.append(h)
            trumps.append(t)
        bidder = state.single_hand_declarer if state.single_hand else state.highest_bidder
        # Evaluate each candidate with exact alpha-beta over every sampled world.
        best, val, nodes = EndgameMinimax.find_best_move_multi_deal(
            player_id=self.player_id, sampled_deals=worlds, current_trick=state.current_trick,
            trump_suit=trumps[0], trump_revealed=state.trump_revealed or state.single_hand,
            current_team_points=list(state.round_points), style=self.profile.key, max_depth=16,
            target=state.target_bid or state.bid, bidder=bidder, sitting_out=state.sitting_out,
            bonus=state.rules.last_trick_bonus, done=len(state.completed_tricks),
            single_hand=state.single_hand, sampled_trumps=trumps, root_legal=legal)
        mm = dict(EndgameMinimax.last_scores)
        # Minimax is exact per sampled world; the fuzzy layer only breaks near-ties.
        combined = {c: mm.get(c, -99.0) + 0.3 * fz_score[c] for c in legal}
        best = max(legal, key=lambda c: (combined[c], -POWER[c]))
        table = sorted([{"card": str(c), "code": c.code, "minimax": round(mm.get(c, 0.0), 2),
                         "fuzzy": round(fz_score[c], 3), "score": round(combined[c], 2)} for c in legal],
                       key=lambda r: -r["score"])
        details = {"simulations": len(worlds), "minimax_nodes": nodes,
                   "expected_differential": round(mm.get(best, val), 2), "candidates": table}
        return best, details, "Endgame Minimax (α-β) over sampled deals"

    # ------------------------------------------------------------ fuzzy move features
    def _move_features(self, state: GameState, kb, card: Card) -> Dict[str, Any]:
        me = self.player_id
        my_team = GameState.get_team(me)
        hand = state.hands[me]
        trick = state.current_trick
        trump, known = known_trump_for(me, state, kb)
        revealed = state.trump_revealed or state.single_hand
        active_trump = trump if revealed else None

        played = {pc.card for t in state.completed_tricks for pc in t.cards}
        if trick:
            played |= {pc.card for pc in trick.cards}
        unseen = [c for c in ALL_CARDS if c not in played and c not in hand]
        higher_unseen = [c for c in unseen if c.suit == card.suit and POWER[c] > POWER[card]]
        is_boss = not higher_unseen

        size = state.trick_size
        n_on_table = len(trick.cards) if trick else 0
        players_after = size - n_on_table - 1

        # current_trick (before my card)
        if n_on_table == 0:
            current = 50.0
            win_before_team = None
        else:
            w = Rules.determine_trick_winner(trick, active_trump, revealed and active_trump is not None)
            win_before_team = GameState.get_team(w)
            current = 85.0 if win_before_team == my_team else 15.0

        # capture (after my card)
        i_win = False
        if n_on_table == 0:
            someone_void = bool(kb) and any((p, card.suit) in kb.void_facts for p in range(4) if p != me)
            ruff_danger = active_trump is not None and card.suit != active_trump and someone_void
            if is_boss and not ruff_danger:
                capture = 75.0
            else:
                capture = max(5.0, 45.0 - 10.0 * len(higher_unseen))
            i_win = is_boss
        else:
            t2 = trick.clone()
            t2.add_card(me, card, is_trump=(active_trump is not None and card.suit == active_trump))
            w2 = Rules.determine_trick_winner(t2, active_trump, active_trump is not None)
            i_win = (w2 == me)
            if GameState.get_team(w2) == my_team:
                if players_after == 0:
                    capture = 100.0
                else:
                    win_card = next(pc.card for pc in t2.cards if pc.player_id == w2)
                    still_higher = [c for c in unseen if c.suit == win_card.suit and POWER[c] > POWER[win_card]]
                    capture = 85.0 if not still_higher else 55.0 - 6.0 * min(5, len(still_higher))
                    if active_trump is not None and win_card.suit != active_trump:
                        capture -= 15.0
            else:
                capture = 8.0

        on_table = trick.points if trick else 0
        stake = on_table + card.points
        done = len(state.completed_tricks)
        threat = min(100.0, stake * 17.0 + (12.0 if done >= 5 else 0.0))

        value = (POWER[card] / 8.0) * 62.0 + card.points * 8.0
        if trump is not None and card.suit == trump:
            value += 22.0
        if is_boss:
            value += 8.0
        value = max(0.0, min(100.0, value))

        bidder = state.single_hand_declarer if state.single_hand else state.highest_bidder
        target = state.target_bid or state.bid or 16
        total = 29 if state.rules.last_trick_bonus else 28
        if bidder is not None:
            need = target if GameState.get_team(bidder) == my_team else (total - target + 1)
        else:
            need = 15
        progress = state.round_points[my_team] / max(1, need)
        elapsed = done / 8.0
        position = max(0.0, min(100.0, 50.0 + 60.0 * (progress - elapsed)))

        risk = min(100.0, card.points * 28.0 * (1.0 - capture / 100.0) +
                   (18.0 if (trump is not None and card.suit == trump and capture < 40) else 0.0))

        return {
            "inputs": {"current_trick": current, "capture": capture, "opponent_threat": threat,
                       "card_value": value, "team_position": position, "risk": risk},
            "is_boss": is_boss, "higher_unseen": len(higher_unseen), "stake": stake, "i_win": i_win,
            "win_before_team": win_before_team, "is_trump": trump is not None and card.suit == trump,
            "trump_active": active_trump is not None,
        }

    def _explain_play(self, state, card: Card, features, legal) -> Tuple[str, str]:
        full, pub = self._explain_play_raw(state, card, features, legal)
        fix = lambda t: t.replace(" 1 points", " 1 point")
        return fix(full), fix(pub)

    def _explain_play_raw(self, state, card: Card, features, legal) -> Tuple[str, str]:
        f = features[card]
        my_team = GameState.get_team(self.player_id)
        hand = state.hands[self.player_id]
        stronger_kept = sorted([c for c in hand if c != card and c.suit == card.suit and POWER[c] > POWER[card]],
                               key=lambda c: -POWER[c])
        leading = not state.current_trick or not state.current_trick.cards
        partner_winning = f["win_before_team"] == my_team
        captures = f["i_win"]
        key = self.profile.key
        v = self.voice

        if leading:
            if f["is_boss"] and card.points + card.power >= 8:
                full = f"{v} led {card}, a master card nobody can beat in {card.suit.value}, to cash its points."
                pub = f"{v} led {card} as a master card to cash points."
            elif f["is_trump"] and f["trump_active"]:
                full = f"{v} led trump {card} to draw the opponents' trumps."
                pub = full
            else:
                full = f"{v} led {card}, a low-value card, to keep its control cards for later."
                pub = f"{v} led {card}, keeping stronger cards for later."
                if key == "AGGRESSIVE":
                    full = f"{v} led {card} to probe the suit and force out high cards early."
                    pub = full
            return full, pub

        if partner_winning and not captures:
            if card.points > 0:
                full = f"{v} smeared {card} ({card.points} pt) onto its partner's winning trick."
            else:
                full = f"{v} played a low card ({card}) because its partner was already winning the trick."
            return full, full

        if f["is_trump"] and f["trump_active"] and captures and card.suit != state.current_trick.lead_suit:
            full = f"{v} ruffed with trump {card} to capture a {f['stake']}-point trick."
            if key == "DEFENSIVE":
                full = f"{v} spent trump {card} only because the trick was worth {f['stake']} points."
            return full, full

        if captures:
            if key == "AGGRESSIVE":
                full = f"{v} played {card} to capture the trick and grab {f['stake']} points immediately."
                pub = full
            elif stronger_kept and key == "STRATEGIC":
                full = (f"{v} won with {card} — the cheapest winning card — preserving {stronger_kept[0]} "
                        f"for a potentially more valuable trick.")
                pub = f"{v} won with {card}, the cheapest card that does the job."
            elif key == "DEFENSIVE":
                full = f"{v} took the trick with {card} to stop the opponents scoring {f['stake']} points."
                pub = full
            else:
                full = f"{v} played {card} to win the trick ({f['stake']} points at stake)."
                pub = full
            return full, pub

        # Not capturing: ducking
        if stronger_kept:
            full = f"{v} ducked with {card}, keeping {stronger_kept[0]} in reserve for a trick it can actually win."
            pub = f"{v} ducked with {card}, keeping stronger cards in reserve."
        elif card.points == 0:
            full = f"{v} discarded {card}: a worthless card, so no points are fed to the opponents."
            pub = full
        else:
            full = f"{v} gave up {card} as the least costly option."
            pub = full
        return full, pub

    # ------------------------------------------------------------ baseline heuristic
    def _rule_heuristic_card(self, state: GameState, legal_cards: List[Card]) -> Card:
        trick = state.current_trick
        if trick is None or len(trick.cards) == 0:
            aces = [c for c in legal_cards if c.rank in (Rank.JACK, Rank.ACE)]
            return aces[0] if aces else max(legal_cards, key=lambda c: c.power)
        partner = GameState.get_partner(self.player_id)
        trump = state.trump_suit if state.trump_revealed else None
        winner = Rules.determine_trick_winner(trick, trump, state.trump_revealed)
        lead = trick.lead_suit
        in_suit = [c for c in legal_cards if c.suit == lead]
        if winner == partner:
            pool = in_suit or legal_cards
            return min(pool, key=lambda c: (c.power, c.points)) if in_suit else max(pool, key=lambda c: (c.points, -c.power))
        if in_suit:
            best = max((pc.card for pc in trick.cards if pc.card.suit == lead), key=lambda c: c.power)
            winners = [c for c in in_suit if c.power > best.power]
            return min(winners, key=lambda c: c.power) if winners else min(in_suit, key=lambda c: (c.points, c.power))
        return min(legal_cards, key=lambda c: (c.points, c.power))
