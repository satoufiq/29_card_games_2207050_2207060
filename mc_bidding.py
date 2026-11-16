"""
Monte Carlo Expected-Utility Bidding (MCEUB) with a personality fuzzy layer.

  Hand Evaluation  -> Fuzzy Bidding Evaluator -> Personality Profile -> Bid or Pass

1. Hand features (high-card strength, trump potential, uncertainty) from the
   4-input Mamdani hand evaluator.
2. Common Random Numbers: N full deals consistent with the 4 known cards are
   sampled once and reused for every candidate trump suit and bid level.
3. Each deal is played out with the shared partnership-aware rollout policy.
4. Auction information shifts the point distribution: a partner's bid suggests
   extra strength, an opponent's bid suggests strength against us. Each
   personality weighs this differently.
5. The personality's fuzzy rule base turns hand features + auction context into
   bid confidence and risk tolerance, which move the probability bar.
6. EU(b) = p(b)·W − (1 − p(b))·|L|·risk_aversion is compared with EU(pass);
   the highest acceptable level is the AI's ceiling for this auction.
"""
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional, Any
import random
from card import Card, Suit, Rank
from game_state import GameState
from fuzzy_system import MamdaniFuzzyBidding, MamdaniEngine
from ai_profiles import get_profile, PersonalityProfile
from sim_engine import SimState, heuristic_card, ALL_CARDS


DECLARER_EDGE = 1.0   # card points; see calibration note in evaluate_all_bids


def holder_make_probability(bid: int) -> float:
    """Base rate that whoever holds a contract at `bid` makes it (from full-game calibration runs)."""
    return max(0.25, min(0.85, 0.74 - 0.065 * (bid - 16)))


@dataclass
class BidEvaluationResult:
    bid: Optional[int]
    trump: Optional[Suit]
    expected_utility: float
    success_probability: float
    simulations: int
    pass_utility: float
    confidence: float
    reasoning: str
    suit_evaluations: Dict[Suit, Dict[str, Any]] = field(default_factory=dict)
    max_bid: Optional[int] = None
    threshold: float = 0.5
    fuzzy: Dict[str, Any] = field(default_factory=dict)
    auction_adjustment: float = 0.0
    action_kind: str = "PASS"
    public_summary: str = ""


class MonteCarloExpectedUtilityBidding:
    ALL_CARDS: List[Card] = ALL_CARDS

    @classmethod
    def sample_hypothetical_deals(cls, known_hand: List[Card], viewer_id: int, num_deals: int,
                                  rng: Optional[random.Random] = None) -> List[List[List[Card]]]:
        """N complete 8-card deals that contain the viewer's known cards (CRN pool)."""
        rng = rng or random.Random()
        known = set(known_hand)
        remaining = [c for c in cls.ALL_CARDS if c not in known]
        need_own = 8 - len(known_hand)
        deals = []
        for _ in range(num_deals):
            pool = list(remaining)
            rng.shuffle(pool)
            deal = [[], [], [], []]
            deal[viewer_id] = list(known_hand) + pool[:need_own]
            rest = pool[need_own:]
            others = [(viewer_id + k) % 4 for k in (1, 2, 3)]
            for i, p in enumerate(others):
                deal[p] = rest[i * 8:(i + 1) * 8]
            deals.append(deal)
        return deals

    @classmethod
    def simulate_deal_points(cls, deal: List[List[Card]], trump_suit: Suit, lead_player: int,
                             viewer_team: int, bidder: Optional[int] = None, bonus: bool = False,
                             rng: Optional[random.Random] = None) -> int:
        rng = rng or random.Random(0)
        sim = SimState(hands=[list(h) for h in deal], trick=[], current=lead_player, trump=trump_suit,
                       revealed=False, sitting_out=None, pts=[0, 0], tricks_won=[0, 0, 0, 0], done=0,
                       bonus=bonus, played=set(), bidder=bidder, target=0, single_hand=False)
        guard = 0
        while not sim.is_terminal() and guard < 40:
            sim.play(heuristic_card(sim, rng, epsilon=0.0))
            guard += 1
        return sim.pts[viewer_team]

    @classmethod
    def compute_payoffs(cls, current_game_points: List[int], viewer_team: int, match_target: int = 6) -> Tuple[float, float]:
        my_pts = current_game_points[viewer_team]
        w = 1.0
        if my_pts + 1 >= match_target:
            w = 2.5
        elif my_pts <= -(match_target - 2):
            w = 1.4
        l = -1.2
        if my_pts - 1 <= -match_target:
            l = -3.0
        return w, l

    @staticmethod
    def auction_context(state: GameState, player_id: int) -> Dict[str, Any]:
        partner = GameState.get_partner(player_id)
        partner_bid = opp_bid = 0
        partner_passed = partner in state.passed_players
        opp_passed = 0
        for h in state.bidding_history:
            if not isinstance(h.get("bid"), int):
                continue
            if h["player"] == partner:
                partner_bid = max(partner_bid, h["bid"])
            elif GameState.get_team(h["player"]) != GameState.get_team(player_id):
                opp_bid = max(opp_bid, h["bid"])
        for p in state.passed_players:
            if GameState.get_team(p) != GameState.get_team(player_id):
                opp_passed += 1
        return {"partner_bid": partner_bid, "opp_bid": opp_bid,
                "partner_passed": partner_passed, "opp_passed": opp_passed}

    @classmethod
    def evaluate_all_bids(cls, hand: List[Card], player_id: int, state: GameState,
                          ai_strategy: str = "STRATEGIC", simulations_per_suit: int = 50,
                          rng: Optional[random.Random] = None,
                          profile: Optional[PersonalityProfile] = None) -> BidEvaluationResult:
        rng = rng or random.Random()
        profile = profile or get_profile(ai_strategy)
        viewer_team = GameState.get_team(player_id)
        rules = state.rules

        # 1. Hand features
        hand_eval = MamdaniFuzzyBidding.evaluate_hand(hand, is_stage_one=True)
        suit_feats = hand_eval["suit_evaluations"]

        # 2-3. CRN deals and rollouts for each candidate trump suit
        deals = cls.sample_hypothetical_deals(hand, player_id, simulations_per_suit, rng)
        lead = (state.dealer + 1) % 4
        dist: Dict[Suit, List[int]] = {}
        for s in Suit:
            dist[s] = [cls.simulate_deal_points(d, s, lead, viewer_team, bidder=player_id,
                                                bonus=rules.last_trick_bonus, rng=rng) for d in deals]

        # 4. Auction information
        ctx = cls.auction_context(state, player_id)
        adj = 0.0
        if ctx["partner_bid"]:
            adj += profile.partner_bid_trust * 0.6 * (ctx["partner_bid"] - 15)
        elif ctx["partner_passed"]:
            adj -= profile.partner_bid_trust * 1.5
        if ctx["opp_bid"]:
            adj -= profile.opponent_bid_respect * 0.6 * (ctx["opp_bid"] - 15)
        adj += 0.5 * ctx["opp_passed"] * profile.opponent_bid_respect
        adj = max(-4.0, min(4.0, adj))
        # Calibration: full-game experiments show declarers make ~10% more contracts than the
        # rollouts predict (they choose trump and keep it hidden). Credit that edge.
        adj += DECLARER_EDGE

        def p_at(s: Suit, b: int) -> float:
            pts = dist[s]
            return sum(1 for x in pts if x + adj >= b) / len(pts)

        lo = state.min_next_bid
        hi = rules.max_bid
        eligible_suits = [s for s in Suit if any(c.suit == s and c.points > 0 for c in hand)] or list(Suit)
        best_suit = max(eligible_suits, key=lambda s: (p_at(s, max(lo, rules.min_bid)), sum(dist[s])))

        # 5. Personality fuzzy layer
        my_gp = state.game_points[viewer_team]
        opp_gp = state.game_points[1 - viewer_team]
        fuzzy_inputs = {
            "hand_strength": hand_eval["high_card_strength"],
            "trump_strength": suit_feats[best_suit]["trump_potential"],
            "risk": 0.5 * suit_feats[best_suit]["uncertainty"] + 50.0 * (1.0 - p_at(best_suit, lo)),
            "team_position": max(0.0, min(100.0, 50.0 + (my_gp - opp_gp) * 9.0)),
            "opponent_threat": max(0.0, min(100.0, (ctx["opp_bid"] - 15) * 14.0)) if ctx["opp_bid"] else 10.0,
        }
        fz = MamdaniEngine(profile.bid_rules).infer(fuzzy_inputs)
        conf = fz["outputs"]["bid_confidence"]
        risk_tol = fz["outputs"]["risk_tolerance"]
        fuzzy_shift = profile.fuzzy_bid_weight * ((conf - 50.0) / 50.0) + 0.06 * ((risk_tol - 50.0) / 50.0)

        # 6. Expected utility per bid level, compared with the real cost/benefit of passing.
        w_pay, l_pay = cls.compute_payoffs(state.game_points, viewer_team, rules.match_target)
        partner = GameState.get_partner(player_id)
        opponent_holds = state.highest_bidder is not None and state.highest_bidder != partner
        if state.highest_bidder is None:
            pass_u = 0.0
            threshold = profile.min_success_prob - fuzzy_shift
        else:
            q = holder_make_probability(state.bid)
            if state.highest_bidder == partner:
                pass_u = (2 * q - 1) * w_pay          # partner's contract is good for us
                threshold = profile.min_success_prob - fuzzy_shift
            else:
                pass_u = -(2 * q - 1) * w_pay         # conceding the contract costs us
                threshold = profile.compete_floor - fuzzy_shift
        threshold = max(0.2, min(0.92, threshold))

        max_ok = None
        levels = {}
        for b in range(rules.min_bid, hi + 1):
            p = p_at(best_suit, b)
            eu = p * w_pay + (1.0 - p) * l_pay * profile.risk_aversion
            levels[b] = (p, eu)
            if b >= lo and p >= threshold and eu >= pass_u + profile.bid_margin:
                max_ok = b

        # Decision
        bid: Optional[int] = None
        kind = "PASS"
        is_holder = state.can_hold   # duel auction: the holder may hold (match) the challenger's bid
        if max_ok is not None and lo <= hi:
            if state.highest_bidder is None:
                bid = lo
                if profile.opening_jump and max_ok >= lo + 3:
                    bid = min(max_ok, lo + profile.opening_jump)
                kind = "OPEN"
            elif state.highest_bidder == partner:
                if max_ok >= state.bid + (0 if is_holder else 1) + profile.partner_overcall_margin:
                    bid = lo
                    kind = "OVER_PARTNER"
            elif is_holder:
                bid = state.bid          # holding is enough; the holder never needs to go higher
                kind = "HOLD"
            else:
                step = profile.raise_step
                if profile.key == "AGGRESSIVE" and max_ok - state.bid >= 3:
                    step += 1
                bid = min(max_ok, state.bid + step)
                kind = "RAISE"

        show_level = bid if bid is not None else lo
        p_show, eu_show = levels.get(show_level, (0.0, -1.0)) if show_level <= hi else (0.0, -1.0)
        suit_details = {}
        for s in Suit:
            p = p_at(s, show_level) if show_level <= hi else 0.0
            suit_details[s] = {
                "suit": s.value, "symbol": s.symbol,
                "avg_simulated_points": round(sum(dist[s]) / len(dist[s]) + adj, 1),
                "success_probability": round(p, 3),
                "fuzzy_suitability": suit_feats[s]["suitability"],
            }

        reasoning = (
            f"MCEUB: {simulations_per_suit} CRN deals × 4 suits. Best trump {best_suit.value} {best_suit.symbol}; "
            f"P(make {show_level}) = {p_show:.0%}, EU = {eu_show:+.2f} vs pass {pass_u:+.2f}. "
            f"Fuzzy bid confidence {conf:.0f}/100, risk tolerance {risk_tol:.0f}/100 → probability bar {threshold:.0%}. "
            f"Ceiling: {max_ok if max_ok else 'none'}. Decision: {('BID ' + str(bid)) if bid else 'PASS'}."
        )
        return BidEvaluationResult(
            bid=bid, trump=best_suit, expected_utility=round(eu_show, 2), success_probability=round(p_show, 3),
            simulations=simulations_per_suit * 4, pass_utility=round(pass_u, 2), confidence=round(conf / 100.0, 2),
            reasoning=reasoning, suit_evaluations=suit_details, max_bid=max_ok, threshold=round(threshold, 3),
            fuzzy=fz, auction_adjustment=round(adj, 2), action_kind=kind,
        )
