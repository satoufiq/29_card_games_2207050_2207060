"""
Personality profiles for the three 29 AI players.

All personalities share one architecture and the same legal-move generator.
They differ in: bidding risk tolerance, how they read partner/opponent bids,
the fuzzy rule bases used for bidding and card play, the weights that blend
ISMCTS values with fuzzy desirability, the ISMCTS terminal utility, search
budget, and trump-reveal / doubling / Single Hand thresholds.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

# A fuzzy rule: (antecedents, operator, (output_variable, term), weight)
Rule = Tuple[Dict[str, str], str, Tuple[str, str], float]


@dataclass
class PersonalityProfile:
    key: str
    label: str
    tagline: str

    # ---- bidding ----
    min_success_prob: float          # minimum P(make contract) before committing to a bid level
    risk_aversion: float             # multiplier on the loss payoff in EU(b) = pW - (1-p)L
    partner_overcall_margin: int     # extra points of headroom needed to bid over own partner
    opponent_bid_respect: float      # how much an opponent's bid lowers our expected points
    partner_bid_trust: float         # how much partner's bid raises our expected points
    raise_step: int                  # how far to raise over the current bid when competing
    opening_jump: int                # how far above the minimum to open with a strong hand
    single_hand_threshold: float     # P(win every trick) required to call Single Hand
    compete_floor: float             # minimum P(make) when outbidding an opponent's contract
    bid_margin: float                # extra EU required over passing (negative = eager)
    fuzzy_bid_weight: float          # how strongly fuzzy bid confidence shifts the probability bar

    # ---- card play ----
    mcts_iterations: int
    mcts_time_budget: float          # seconds
    uct_c: float
    fuzzy_play_weight: float         # weight of fuzzy desirability vs ISMCTS value
    preservation_weight: float       # penalty weight for spending valuable cards
    immediate_points_weight: float   # utility bonus for points captured in the current trick
    denial_weight: float             # utility bonus for keeping opponent points low
    waste_penalty: float             # utility penalty for losing a trick with a high card
    contract_weight: float           # weight of contract made/defeated in utility
    endgame_cards: int               # cards in hand at which exact minimax takes over

    # ---- other decisions ----
    reveal_min_points: int           # trick points needed before calling for trump
    reveal_prob_holding: float       # minimum P(I hold a trump) before calling for trump
    double_threshold: float          # P(contract fails) needed for a defender to double
    redouble_threshold: float        # P(contract makes) needed for the declarer side to redouble

    bid_rules: List[Rule] = field(default_factory=list)
    play_rules: List[Rule] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Fuzzy rule bases
#
# Bidding inputs (0-100): hand_strength, trump_strength, risk, team_position, opponent_threat
# Bidding outputs:        bid_confidence (low/medium/high), risk_tolerance (low/medium/high)
#
# Play inputs (0-100): current_trick (losing/balanced/winning, before my card)
#                      capture (low/medium/high: chance my card wins/keeps the trick for us)
#                      opponent_threat (low/medium/high: points at stake + opponent pressure)
#                      card_value (low/medium/high: how precious the card is for later)
#                      team_position (behind/equal/ahead vs. our goal this deal)
#                      risk (low/medium/high: chance of feeding points to the opponents)
# Play outputs:        desirability (poor/fair/good/excellent), preservation (low/medium/high)
# ---------------------------------------------------------------------------

AGGRESSIVE_BID_RULES: List[Rule] = [
    ({"hand_strength": "strong"}, "and", ("bid_confidence", "high"), 1.0),
    ({"trump_strength": "high"}, "and", ("bid_confidence", "high"), 1.0),
    ({"hand_strength": "medium", "trump_strength": "medium"}, "and", ("bid_confidence", "high"), 0.8),
    ({"hand_strength": "medium"}, "and", ("bid_confidence", "medium"), 1.0),
    ({"hand_strength": "weak", "trump_strength": "low"}, "and", ("bid_confidence", "low"), 1.0),
    ({"opponent_threat": "high", "trump_strength": "medium"}, "and", ("bid_confidence", "medium"), 0.9),
    ({"risk": "high"}, "and", ("risk_tolerance", "medium"), 1.0),
    ({"risk": "medium"}, "and", ("risk_tolerance", "high"), 1.0),
    ({"risk": "low"}, "and", ("risk_tolerance", "high"), 1.0),
    ({"team_position": "behind"}, "and", ("risk_tolerance", "high"), 1.0),
]

STRATEGIC_BID_RULES: List[Rule] = [
    ({"hand_strength": "strong", "trump_strength": "high"}, "and", ("bid_confidence", "high"), 1.0),
    ({"hand_strength": "strong", "trump_strength": "medium"}, "and", ("bid_confidence", "high"), 0.8),
    ({"hand_strength": "medium", "trump_strength": "high"}, "and", ("bid_confidence", "high"), 0.7),
    ({"hand_strength": "medium", "trump_strength": "medium"}, "and", ("bid_confidence", "medium"), 1.0),
    ({"hand_strength": "weak"}, "or", ("bid_confidence", "low"), 1.0),
    ({"trump_strength": "low"}, "and", ("bid_confidence", "low"), 0.8),
    ({"risk": "high"}, "and", ("risk_tolerance", "low"), 1.0),
    ({"risk": "medium"}, "and", ("risk_tolerance", "medium"), 1.0),
    ({"risk": "low"}, "and", ("risk_tolerance", "high"), 1.0),
    ({"team_position": "behind", "risk": "medium"}, "and", ("risk_tolerance", "high"), 0.7),
    ({"team_position": "ahead"}, "and", ("risk_tolerance", "low"), 0.6),
]

DEFENSIVE_BID_RULES: List[Rule] = [
    ({"hand_strength": "strong", "trump_strength": "high"}, "and", ("bid_confidence", "high"), 1.0),
    ({"hand_strength": "strong", "trump_strength": "medium"}, "and", ("bid_confidence", "medium"), 1.0),
    ({"hand_strength": "medium", "trump_strength": "high"}, "and", ("bid_confidence", "medium"), 1.0),
    ({"hand_strength": "medium", "trump_strength": "medium"}, "and", ("bid_confidence", "low"), 0.8),
    ({"hand_strength": "weak"}, "or", ("bid_confidence", "low"), 1.0),
    ({"trump_strength": "low"}, "or", ("bid_confidence", "low"), 1.0),
    ({"opponent_threat": "high"}, "and", ("bid_confidence", "low"), 0.6),
    ({"risk": "high"}, "or", ("risk_tolerance", "low"), 1.0),
    ({"risk": "medium"}, "and", ("risk_tolerance", "low"), 0.8),
    ({"risk": "low"}, "and", ("risk_tolerance", "medium"), 1.0),
    ({"team_position": "ahead"}, "and", ("risk_tolerance", "low"), 1.0),
]

AGGRESSIVE_PLAY_RULES: List[Rule] = [
    ({"capture": "high", "opponent_threat": "high"}, "and", ("desirability", "excellent"), 1.0),
    ({"capture": "high"}, "and", ("desirability", "good"), 1.0),
    ({"capture": "medium", "card_value": "high"}, "and", ("desirability", "good"), 0.8),
    ({"current_trick": "losing", "capture": "low"}, "and", ("desirability", "poor"), 0.8),
    ({"capture": "low", "card_value": "low"}, "and", ("desirability", "fair"), 1.0),
    ({"capture": "low", "risk": "high"}, "and", ("desirability", "poor"), 1.0),
    ({"current_trick": "winning", "capture": "high", "risk": "low"}, "and", ("desirability", "good"), 0.7),
    ({"card_value": "high", "opponent_threat": "low", "capture": "low"}, "and", ("preservation", "high"), 0.8),
    ({"card_value": "high", "capture": "high"}, "and", ("preservation", "low"), 1.0),
    ({"card_value": "medium"}, "and", ("preservation", "low"), 1.0),
    ({"card_value": "low"}, "and", ("preservation", "low"), 1.0),
]

STRATEGIC_PLAY_RULES: List[Rule] = [
    ({"capture": "high", "opponent_threat": "high"}, "and", ("desirability", "excellent"), 1.0),
    ({"capture": "high", "opponent_threat": "medium"}, "and", ("desirability", "good"), 1.0),
    ({"capture": "high", "opponent_threat": "low", "card_value": "high"}, "and", ("desirability", "fair"), 1.0),
    ({"current_trick": "winning", "card_value": "low", "risk": "low"}, "and", ("desirability", "good"), 1.0),
    ({"current_trick": "winning", "card_value": "high", "capture": "medium"}, "and", ("desirability", "poor"), 0.8),
    ({"current_trick": "losing", "capture": "low", "card_value": "low"}, "and", ("desirability", "good"), 0.9),
    ({"current_trick": "losing", "capture": "low", "card_value": "high"}, "and", ("desirability", "poor"), 1.0),
    ({"risk": "high"}, "and", ("desirability", "poor"), 0.9),
    ({"team_position": "behind", "capture": "high"}, "and", ("desirability", "excellent"), 0.7),
    ({"card_value": "high", "opponent_threat": "low"}, "and", ("preservation", "high"), 1.0),
    ({"card_value": "high", "opponent_threat": "high", "capture": "high"}, "and", ("preservation", "low"), 1.0),
    ({"card_value": "medium", "opponent_threat": "low"}, "and", ("preservation", "medium"), 1.0),
    ({"card_value": "low"}, "and", ("preservation", "low"), 1.0),
]

DEFENSIVE_PLAY_RULES: List[Rule] = [
    ({"current_trick": "winning", "card_value": "low"}, "and", ("desirability", "excellent"), 1.0),
    ({"current_trick": "winning", "card_value": "high"}, "and", ("desirability", "poor"), 1.0),
    ({"current_trick": "losing", "capture": "high", "opponent_threat": "high"}, "and", ("desirability", "excellent"), 1.0),
    ({"current_trick": "losing", "capture": "high", "opponent_threat": "medium"}, "and", ("desirability", "good"), 1.0),
    ({"current_trick": "losing", "capture": "low", "risk": "low"}, "and", ("desirability", "good"), 1.0),
    ({"risk": "high"}, "or", ("desirability", "poor"), 1.0),
    ({"capture": "high", "opponent_threat": "low", "card_value": "high"}, "and", ("desirability", "poor"), 0.9),
    ({"current_trick": "balanced", "card_value": "low"}, "and", ("desirability", "good"), 0.8),
    ({"card_value": "high"}, "and", ("preservation", "high"), 1.0),
    ({"card_value": "medium"}, "and", ("preservation", "medium"), 1.0),
    ({"card_value": "high", "opponent_threat": "high", "capture": "high"}, "and", ("preservation", "medium"), 1.0),
    ({"card_value": "low"}, "and", ("preservation", "low"), 1.0),
]


AGGRESSIVE = PersonalityProfile(
    key="AGGRESSIVE", label="Aggressive", tagline="High risk, high reward",
    min_success_prob=0.36, risk_aversion=0.80, partner_overcall_margin=1, compete_floor=0.24, bid_margin=-0.06,
    opponent_bid_respect=0.15, partner_bid_trust=0.55, raise_step=1, opening_jump=2,
    single_hand_threshold=0.55, fuzzy_bid_weight=0.12,
    mcts_iterations=900, mcts_time_budget=0.6, uct_c=0.9,
    fuzzy_play_weight=0.32, preservation_weight=0.35, immediate_points_weight=0.045,
    denial_weight=0.0, waste_penalty=0.02, contract_weight=0.30, endgame_cards=2,
    reveal_min_points=0, reveal_prob_holding=0.25,
    double_threshold=0.60, redouble_threshold=0.64,
    bid_rules=AGGRESSIVE_BID_RULES, play_rules=AGGRESSIVE_PLAY_RULES,
)

STRATEGIC = PersonalityProfile(
    key="STRATEGIC", label="Strategic", tagline="Calculated and adaptive",
    min_success_prob=0.45, risk_aversion=1.0, partner_overcall_margin=2, compete_floor=0.32, bid_margin=0.0,
    opponent_bid_respect=0.35, partner_bid_trust=0.45, raise_step=1, opening_jump=0,
    single_hand_threshold=0.78, fuzzy_bid_weight=0.08,
    mcts_iterations=1600, mcts_time_budget=1.0, uct_c=1.2,
    fuzzy_play_weight=0.14, preservation_weight=0.55, immediate_points_weight=0.0,
    denial_weight=0.05, waste_penalty=0.06, contract_weight=0.32, endgame_cards=3,
    reveal_min_points=1, reveal_prob_holding=0.45,
    double_threshold=0.70, redouble_threshold=0.76,
    bid_rules=STRATEGIC_BID_RULES, play_rules=STRATEGIC_PLAY_RULES,
)

DEFENSIVE = PersonalityProfile(
    key="DEFENSIVE", label="Defensive", tagline="Conservative and risk-averse",
    min_success_prob=0.55, risk_aversion=1.25, partner_overcall_margin=3, compete_floor=0.42, bid_margin=0.08,
    opponent_bid_respect=0.55, partner_bid_trust=0.30, raise_step=1, opening_jump=0,
    single_hand_threshold=0.93, fuzzy_bid_weight=0.10,
    mcts_iterations=1200, mcts_time_budget=0.8, uct_c=1.4,
    fuzzy_play_weight=0.30, preservation_weight=0.85, immediate_points_weight=0.0,
    denial_weight=0.16, waste_penalty=0.12, contract_weight=0.30, endgame_cards=2,
    reveal_min_points=2, reveal_prob_holding=0.60,
    double_threshold=0.80, redouble_threshold=0.86,
    bid_rules=DEFENSIVE_BID_RULES, play_rules=DEFENSIVE_PLAY_RULES,
)

PROFILES: Dict[str, PersonalityProfile] = {
    "AGGRESSIVE": AGGRESSIVE,
    "STRATEGIC": STRATEGIC,
    "DEFENSIVE": DEFENSIVE,
}


def get_profile(key: str) -> PersonalityProfile:
    key = (key or "STRATEGIC").upper()
    if key == "CONSERVATIVE":
        key = "DEFENSIVE"
    return PROFILES.get(key, STRATEGIC)
