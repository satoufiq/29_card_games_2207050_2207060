from typing import List, Tuple, Optional, Dict, Any
from card import Card, Suit, Rank

def triangular_membership(x: float, a: float, b: float, c: float) -> float:
    """Calculates membership degree for triangular fuzzy function."""
    if x <= a or x >= c:
        return 0.0
    elif a < x <= b:
        return (x - a) / (b - a) if b > a else 1.0
    else:
        return (c - x) / (c - b) if c > b else 1.0

def trapezoidal_membership(x: float, a: float, b: float, c: float, d: float) -> float:
    """Calculates membership degree for trapezoidal fuzzy function."""
    if x <= a or x >= d:
        return 0.0
    elif a < x <= b:
        return (x - a) / (b - a) if b > a else 1.0
    elif b < x <= c:
        return 1.0
    else:
        return (d - x) / (d - c) if d > c else 1.0

def _mf(spec, x: float) -> float:
    if spec[0] == "tri":
        return triangular_membership(x, spec[1], spec[2], spec[3])
    return trapezoidal_membership(x, spec[1], spec[2], spec[3], spec[4])


LOW3 = {"low": ("trap", -1, 0, 20, 45), "medium": ("tri", 25, 50, 75), "high": ("trap", 55, 80, 100, 101)}

# Linguistic variables (all on a 0-100 universe)
FUZZY_INPUTS = {
    "hand_strength": {"weak": ("trap", -1, 0, 25, 45), "medium": ("tri", 30, 50, 70), "strong": ("trap", 55, 75, 100, 101)},
    "trump_strength": dict(LOW3),
    "risk": dict(LOW3),
    "team_position": {"behind": ("trap", -1, 0, 30, 50), "equal": ("tri", 30, 50, 70), "ahead": ("trap", 50, 70, 100, 101)},
    "opponent_threat": dict(LOW3),
    "current_trick": {"losing": ("trap", -1, 0, 25, 50), "balanced": ("tri", 25, 50, 75), "winning": ("trap", 50, 75, 100, 101)},
    "capture": dict(LOW3),
    "card_value": dict(LOW3),
}

FUZZY_OUTPUTS = {
    "bid_confidence": dict(LOW3),
    "risk_tolerance": dict(LOW3),
    "desirability": {
        "poor": ("trap", -1, 0, 15, 35), "fair": ("tri", 20, 40, 60),
        "good": ("tri", 45, 65, 85), "excellent": ("trap", 70, 90, 100, 101),
    },
    "preservation": dict(LOW3),
}

_UNIVERSE = [float(x) for x in range(0, 101, 2)]
_OUTPUT_CURVES = {
    var: {term: [_mf(spec, x) for x in _UNIVERSE] for term, spec in terms.items()}
    for var, terms in FUZZY_OUTPUTS.items()
}
_DEFAULT_OUTPUT = {"bid_confidence": 50.0, "risk_tolerance": 50.0, "desirability": 50.0, "preservation": 30.0}


class MamdaniEngine:
    """
    Generic Mamdani fuzzy inference: min/max rule evaluation, max aggregation,
    centroid defuzzification. Each AI personality supplies its own rule base.
    """

    def __init__(self, rules):
        self.rules = rules

    @staticmethod
    def fuzzify(inputs: Dict[str, float]) -> Dict[str, Dict[str, float]]:
        out = {}
        for var, x in inputs.items():
            terms = FUZZY_INPUTS.get(var)
            if terms is None:
                continue
            x = max(0.0, min(100.0, float(x)))
            out[var] = {t: round(_mf(spec, x), 3) for t, spec in terms.items()}
        return out

    def infer(self, inputs: Dict[str, float]) -> Dict[str, Any]:
        memberships = self.fuzzify(inputs)
        activation: Dict[str, Dict[str, float]] = {}
        fired = []
        for antecedents, op, (out_var, out_term), weight in self.rules:
            degrees = []
            for var, term in antecedents.items():
                degrees.append(memberships.get(var, {}).get(term, 0.0))
            if not degrees:
                continue
            strength = (min(degrees) if op == "and" else max(degrees)) * weight
            if strength <= 0.0:
                continue
            slot = activation.setdefault(out_var, {})
            slot[out_term] = max(slot.get(out_term, 0.0), strength)
            fired.append((strength, antecedents, op, out_var, out_term))

        outputs: Dict[str, float] = {}
        for out_var in FUZZY_OUTPUTS:
            terms = activation.get(out_var)
            if not terms:
                outputs[out_var] = _DEFAULT_OUTPUT[out_var]
                continue
            num = den = 0.0
            curves = _OUTPUT_CURVES[out_var]
            for i, x in enumerate(_UNIVERSE):
                mu = 0.0
                for term, strength in terms.items():
                    v = curves[term][i]
                    if v > strength:
                        v = strength
                    if v > mu:
                        mu = v
                num += mu * x
                den += mu
            outputs[out_var] = round(num / den, 1) if den > 0 else _DEFAULT_OUTPUT[out_var]

        fired.sort(key=lambda f: -f[0])
        top_rules = [
            f"IF {(' ' + op.upper() + ' ').join(f'{v} is {t}' for v, t in ante.items())} THEN {ov} is {ot} ({s:.2f})"
            for s, ante, op, ov, ot in fired[:4]
        ]
        return {"inputs": {k: round(float(v), 1) for k, v in inputs.items()},
                "memberships": memberships, "outputs": outputs, "rules": top_rules}


class MamdaniFuzzyBidding:
    """
    Pure Python Mamdani-style Fuzzy Inference System for 29 Bidding & Hand Evaluation.
    Implements the 4-input architecture:
      1. High-Card Strength (0-100): Weighted card points & trick-winning powers (J, 9, A, 10).
      2. Trump Potential (0-100): Ability to control tricks in candidate trump suit.
      3. Suit Support (0-100): Concentration, suit length, and off-suit entry stoppers.
      4. Uncertainty (0-100): Sensitivity to undealt cards & flat/dispersed holdings.
    """

    @classmethod
    def compute_high_card_strength(cls, hand: List[Card]) -> float:
        """
        Input 1: High-Card Strength (0-100).
        In 29, Jack (3 pts, power 8) and Nine (2 pts, power 7) are the masters,
        followed by Ace (1 pt, power 6) and Ten (1 pt, power 5).
        Max possible in 4 cards is 4 Jacks (12 pts, 32 power) -> 100.
        """
        pts = sum(c.points for c in hand)
        # Power bonus gives extra weight to J (8) and 9 (7)
        power_pts = sum(c.power for c in hand)
        # Raw score out of theoretical maximum (12*5 + 32*2 = 124)
        raw = (pts * 5.0) + (power_pts * 2.0)
        return float(min(100.0, max(0.0, (raw / 95.0) * 100.0)))

    @classmethod
    def compute_trump_potential(cls, hand: List[Card], suit: Suit) -> float:
        """
        Input 2: Trump Potential (0-100) for a candidate trump suit.
        Evaluates top honors (J, 9, A, 10) and pair holding (K + Q).
        """
        suit_cards = [c for c in hand if c.suit == suit]
        if not suit_cards:
            return 0.0

        score = 0.0
        ranks = {c.rank for c in suit_cards}
        
        if Rank.JACK in ranks:
            score += 42.0  # Master trump card
        if Rank.NINE in ranks:
            score += 28.0  # Second master trump
        if Rank.ACE in ranks:
            score += 15.0  # Third honor
        if Rank.TEN in ranks:
            score += 10.0  # Point card
        if Rank.KING in ranks:
            score += 5.0
        if Rank.QUEEN in ranks:
            score += 5.0
        
        # Royal Marriage (Pair) holding potential
        if Rank.KING in ranks and Rank.QUEEN in ranks:
            score += 10.0

        return float(min(100.0, score))

    @classmethod
    def compute_suit_support(cls, hand: List[Card], suit: Suit) -> float:
        """
        Input 3: Suit Support (0-100).
        Measures suit length (concentration) plus off-suit stoppers (Aces/Jacks)
        that provide re-entry and partner support.
        """
        count = sum(1 for c in hand if c.suit == suit)
        # Length contribution: 1->25, 2->50, 3->75, 4->100
        length_score = (count / 4.0) * 80.0

        # Off-suit stoppers (Aces, Tens, Jacks outside of candidate trump)
        off_suit_stoppers = sum(
            1 for c in hand
            if c.suit != suit and c.rank in (Rank.JACK, Rank.ACE, Rank.NINE)
        )
        stoppers_bonus = min(20.0, off_suit_stoppers * 10.0)

        return float(min(100.0, length_score + stoppers_bonus))

    @classmethod
    def compute_uncertainty(cls, hand: List[Card], suit: Suit) -> float:
        """
        Input 4: Uncertainty (0-100).
        Measures how sensitive the contract is to unknown cards.
        High when hand is dispersed (1-1-1-1), missing top trump honors,
        or low point count. Low when holding solid J+9 in long suit.
        """
        suit_cards = [c for c in hand if c.suit == suit]
        suit_ranks = {c.rank for c in suit_cards}
        
        base_uncertainty = 50.0

        # Missing both Jack and Nine in trump suit increases uncertainty
        if Rank.JACK not in suit_ranks and Rank.NINE not in suit_ranks:
            base_uncertainty += 30.0
        elif Rank.JACK in suit_ranks and Rank.NINE in suit_ranks:
            base_uncertainty -= 25.0

        # Dispersed suits (no suit with length >= 2)
        distinct_suits = len({c.suit for c in hand})
        if distinct_suits == 4:
            base_uncertainty += 20.0  # 1-1-1-1 flat hand
        elif len(suit_cards) >= 3:
            base_uncertainty -= 20.0  # strong concentration

        return float(min(100.0, max(5.0, base_uncertainty)))

    @classmethod
    def evaluate_hand(cls, hand: List[Card], is_stage_one: bool = True) -> Dict[str, Any]:
        """
        Full 4-input Fuzzy Inference Evaluation of the hand across all 4 suits.
        Returns:
            - high_card_strength (0-100)
            - best_suit (Suit)
            - trump_potential (0-100)
            - suit_support (0-100)
            - uncertainty (0-100)
            - hand_strength ("weak", "medium", "strong")
            - trump_suitability (Dict[Suit, Dict])
            - risk ("low", "medium", "high")
            - confidence (0.0 to 1.0)
            - recommended_bid (Optional[int])
        """
        hcs = cls.compute_high_card_strength(hand)
        
        # Evaluate each of the 4 suits
        suit_evals: Dict[Suit, Dict[str, Any]] = {}
        for s in Suit:
            tp = cls.compute_trump_potential(hand, s)
            ss = cls.compute_suit_support(hand, s)
            unc = cls.compute_uncertainty(hand, s)
            
            # Fuzzy Trump Suitability: Poor (0-35), Fair (30-70), Excellent (65-100)
            suitability_score = (tp * 0.55) + (ss * 0.45)
            if suitability_score >= 65:
                cat = "excellent"
            elif suitability_score >= 35:
                cat = "fair"
            else:
                cat = "poor"
            
            suit_evals[s] = {
                "suit": s,
                "trump_potential": round(tp, 1),
                "suit_support": round(ss, 1),
                "uncertainty": round(unc, 1),
                "suitability_score": round(suitability_score, 1),
                "suitability": cat
            }

        # Best trump suit is the one with the highest suitability score
        best_suit = max(Suit, key=lambda s: suit_evals[s]["suitability_score"])
        best_tp = suit_evals[best_suit]["trump_potential"]
        best_ss = suit_evals[best_suit]["suit_support"]
        best_unc = suit_evals[best_suit]["uncertainty"]

        # Fuzzification of Inputs
        # 1. High-Card Strength: Low (0-40), Med (30-70), High (60-100)
        hcs_low = trapezoidal_membership(hcs, -1, 0, 25, 45)
        hcs_med = triangular_membership(hcs, 30, 50, 70)
        hcs_high = trapezoidal_membership(hcs, 55, 75, 100, 105)

        # 2. Trump Potential: Weak (0-35), Mod (30-70), Strong (65-100)
        tp_weak = trapezoidal_membership(best_tp, -1, 0, 20, 40)
        tp_mod = triangular_membership(best_tp, 30, 55, 75)
        tp_strong = trapezoidal_membership(best_tp, 60, 80, 100, 105)

        # 3. Suit Support: Low (0-35), Med (30-70), High (65-100)
        ss_low = trapezoidal_membership(best_ss, -1, 0, 25, 45)
        ss_med = triangular_membership(best_ss, 35, 55, 75)
        ss_high = trapezoidal_membership(best_ss, 65, 85, 100, 105)

        # 4. Uncertainty: Low (0-40), Med (30-70), High (60-100)
        unc_low = trapezoidal_membership(best_unc, -1, 0, 25, 45)
        unc_high = trapezoidal_membership(best_unc, 55, 75, 100, 105)

        # Fuzzy Rules (Section 3 of Specification)
        # Rule 1: IF high-card strength is high AND trump potential is high -> Hand is strong, Bid Very High (21-24)
        r1 = min(hcs_high, tp_strong)
        # Rule 2: IF high-card strength is high AND trump potential is moderate -> Bid High (19-21)
        r2 = min(hcs_high, tp_mod)
        # Rule 3: IF trump potential is high AND suit support is high -> Excellent candidate, Bid Medium-High (18-19)
        r3 = min(tp_strong, ss_high)
        # Rule 4: IF high-card strength is medium AND uncertainty is high -> High risk, Bid Medium (17-18)
        r4 = min(hcs_med, unc_high)
        # Rule 5: IF high-card strength is medium AND trump potential is moderate -> Low Bid (16-17)
        r5 = min(hcs_med, tp_mod)
        # Rule 6: IF high-card strength is low OR trump potential is weak -> Hand is weak, Pass (<16)
        r6 = max(hcs_low, tp_weak)

        # Hand strength classification
        if r1 > 0.4 or hcs >= 65:
            hand_strength = "strong"
        elif r6 > 0.5 or hcs <= 35:
            hand_strength = "weak"
        else:
            hand_strength = "medium"

        # Risk classification
        if unc_high > 0.5 or r6 > 0.4:
            risk = "high"
        elif unc_low > 0.5 and hcs_high > 0.4:
            risk = "low"
        else:
            risk = "medium"

        # Centroid Defuzzification over candidate bid targets:
        # Pass: 14.0, Low: 16.5, Med: 17.5, MedHigh: 18.5, High: 20.5, VeryHigh: 23.0
        numerator = (
            r6 * 14.0 +
            r5 * 16.5 +
            r4 * 17.5 +
            r3 * 18.5 +
            r2 * 20.5 +
            r1 * 23.0
        )
        denominator = (r1 + r2 + r3 + r4 + r5 + r6) + 1e-6
        raw_bid_score = numerator / denominator

        # Confidence calculation (0.0 to 1.0)
        confidence = float(min(1.0, max(0.1, (1.0 - r6) * 0.75 + (hcs_high * 0.25))))

        rec_bid: Optional[int] = None
        if raw_bid_score >= 15.8:
            rec_bid = int(round(raw_bid_score))
            rec_bid = max(16, min(28, rec_bid))

        return {
            "hcp": sum(c.points for c in hand),
            "high_card_strength": round(hcs, 1),
            "best_suit": best_suit,
            "trump_potential": round(best_tp, 1),
            "suit_support": round(best_ss, 1),
            "uncertainty": round(best_unc, 1),
            "hand_strength": hand_strength,
            "risk": risk,
            "confidence": round(confidence, 2),
            "raw_bid_score": round(raw_bid_score, 2),
            "recommended_bid": rec_bid,
            "suit_evaluations": suit_evals,
            "explanation": (
                f"HCS={hcs:.0f}/100, BestTrump={best_suit.value} (TP={best_tp:.0f}, SS={best_ss:.0f}), "
                f"Strength={hand_strength}, Risk={risk}, Confidence={confidence:.0%}"
            )
        }
