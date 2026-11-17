"""
Single-Observer Information Set Monte Carlo Tree Search (SO-ISMCTS) for 29.

Each iteration:
  1. Determinize: sample a full deal (and, if still hidden, a trump suit) that
     is consistent with everything the searching player knows.
  2. Select: walk one shared tree, considering only moves that are legal in
     this determinization (UCB1 with availability counts).
  3. Expand one untried move.
  4. Roll out to the end of the deal with a partnership-aware policy.
  5. Back-propagate: nodes for the searcher's team receive the personality
     utility; opponent nodes receive a neutral utility for their own team.
The searcher never reads other players' real cards.
"""
import math
import random
import time
from typing import Dict, List, Optional, Tuple, Any

from card import Card, Suit, Rank
from game_state import GameState
from rules import Rules
from ai_profiles import PersonalityProfile, get_profile
from sim_engine import (sample_world, build_sim, rollout, contract_made, neutral_team_value,
                        team_of, POWER, POINTS)


class ISNode:
    __slots__ = ("move", "parent", "player", "children", "visits", "value", "avail")

    def __init__(self, move: Optional[Card], parent: Optional["ISNode"], player: int):
        self.move = move
        self.parent = parent
        self.player = player
        self.children: Dict[Card, "ISNode"] = {}
        self.visits = 0
        self.value = 0.0
        self.avail = 1


def utility_from_parts(profile: PersonalityProfile, round_pts: List[int], target: int,
                       bidder_team: Optional[int], my_team: int, made: Optional[bool] = None,
                       wasted: bool = False, fed: bool = False, immediate: int = 0) -> float:
    """Personality utility in [0, 1] for the searcher's team."""
    my, opp = round_pts[my_team], round_pts[1 - my_team]
    total = max(1, my + opp)
    share = my / total
    if bidder_team is None:
        good = my > opp
    else:
        if made is None:
            made = round_pts[bidder_team] >= target
        good = made if my_team == bidder_team else not made
    cw = profile.contract_weight
    val = (1.0 - cw) * share + cw * (1.0 if good else 0.0)
    val += profile.immediate_points_weight * immediate
    if profile.key == "AGGRESSIVE" and good and bidder_team is not None:
        need = target if my_team == bidder_team else (29 - target)
        if my - need >= 2:
            val += 0.05   # loves a convincing win
    val -= profile.denial_weight * (opp / total)
    if wasted:
        val -= profile.waste_penalty
    if fed:
        val -= profile.waste_penalty * 0.6
    return max(0.0, min(1.0, val))


class InformationSetMCTS:
    def __init__(self, simulations_per_move: int = 300, determinizations_count: int = 0,
                 time_budget: float = 1.0):
        self.simulations_per_move = simulations_per_move
        self.determinizations_count = determinizations_count  # kept for API compatibility
        self.time_budget = time_budget

    # ------------------------------------------------------------------ utility
    def _evaluate_style_utility(self, round_pts, target_bid, bidder_team, my_team,
                                wasted_honor, fed_points_to_opp, style) -> float:
        return utility_from_parts(get_profile(style), round_pts, target_bid, bidder_team, my_team,
                                  wasted=wasted_honor, fed=fed_points_to_opp)

    @staticmethod
    def _sim_utility(sim, profile: PersonalityProfile, my_team: int, root_move: Card) -> float:
        wasted = fed = False
        immediate = 0
        if sim.trick_log:
            w, tp = sim.trick_log[0]
            if team_of(w) == my_team:
                immediate = tp
            else:
                wasted = POWER[root_move] >= 6 or (sim.revealed and sim.trump is not None and root_move.suit is sim.trump)
                fed = POINTS[root_move] > 0
        bidder_team = team_of(sim.bidder) if sim.bidder is not None else None
        made = contract_made(sim) if sim.bidder is not None else None
        return utility_from_parts(profile, sim.pts, sim.target, bidder_team, my_team, made=made,
                                  wasted=wasted, fed=fed, immediate=immediate)

    # ------------------------------------------------------------------ search
    def search(self, player_id: int, state: GameState, knowledge_base=None,
               effective_trump: Optional[Suit] = None, known_extra: Optional[List[Card]] = None,
               style: str = "STRATEGIC", rng: Optional[random.Random] = None,
               profile: Optional[PersonalityProfile] = None,
               root_legal: Optional[List[Card]] = None) -> Tuple[Card, Dict[str, Any]]:
        rng = rng or random.Random()
        profile = profile or get_profile(style)
        legal = list(root_legal) if root_legal else Rules.get_legal_cards(player_id, state)
        if not legal:
            hand = state.hands[player_id]
            if hand:
                return hand[0], {"visits": 1, "score": 0.5, "reason": "Fallback card", "candidates": [], "iterations": 0}
            return None, {"visits": 0, "score": 0.0, "reason": "No cards remaining", "candidates": [], "iterations": 0}
        if len(legal) == 1:
            return legal[0], {"visits": 1, "score": 0.5, "iterations": 0,
                              "reason": f"Only one legal card: {legal[0]}.",
                              "candidates": [{"card": str(legal[0]), "code": legal[0].code, "visits": 1, "value": 0.5}]}

        my_team = team_of(player_id)
        root = ISNode(None, None, -1)
        root_no_reveal = not state.trump_revealed
        c_param = profile.uct_c
        t0 = time.perf_counter()
        iterations = 0
        legal_set = set(legal)

        while iterations < self.simulations_per_move:
            if iterations >= 40 and (time.perf_counter() - t0) > self.time_budget:
                break
            hands, trump = sample_world(player_id, state, knowledge_base, rng, attempts=6)
            sim = build_sim(player_id, state, hands, trump)
            sim.current = player_id   # the searcher is always the player to move at the root
            # Sampled hand for the searcher must contain the real legal cards.
            if not legal_set.issubset(set(sim.hands[player_id])):
                sim.hands[player_id] = list(set(sim.hands[player_id]) | legal_set)

            node = root
            first = True
            root_move = None
            while not sim.is_terminal():
                p = sim.current
                if not sim.hands[p]:
                    break
                moves = legal if first else sim.legal(p)
                untried = []
                for m in moves:
                    ch = node.children.get(m)
                    if ch is None:
                        untried.append(m)
                    else:
                        ch.avail += 1
                allow = not (first and root_no_reveal)
                if untried:
                    m = rng.choice(untried)
                    sim.play(m, allow_reveal=allow)
                    child = ISNode(m, node, p)
                    node.children[m] = child
                    node = child
                    if first:
                        root_move = m
                    break
                best, best_ucb = None, -1e9
                for m in moves:
                    ch = node.children[m]
                    ucb = ch.value / ch.visits + c_param * math.sqrt(math.log(ch.avail) / ch.visits)
                    if ucb > best_ucb:
                        best, best_ucb = ch, ucb
                sim.play(best.move, allow_reveal=allow)
                if first:
                    root_move = best.move
                node = best
                first = False

            rollout(sim, rng)
            if root_move is None:
                break
            u_mine = self._sim_utility(sim, profile, my_team, root_move)
            u_team = [neutral_team_value(sim, 0), neutral_team_value(sim, 1)]
            while node is not None and node is not root:
                t = team_of(node.player)
                node.visits += 1
                node.value += u_mine if t == my_team else u_team[t]
                node = node.parent
            root.visits += 1
            iterations += 1

        candidates = []
        for m in legal:
            ch = root.children.get(m)
            v = ch.visits if ch else 0
            val = (ch.value / ch.visits) if (ch and ch.visits) else 0.0
            candidates.append({"card": str(m), "code": m.code, "visits": v, "value": round(val, 3)})
        candidates.sort(key=lambda c: (-c["visits"], -c["value"]))
        best_code = candidates[0]["code"]
        best_card = next(m for m in legal if m.code == best_code)
        elapsed = time.perf_counter() - t0
        reason = (f"SO-ISMCTS ran {iterations} determinized iterations in {elapsed:.2f}s; "
                  f"{best_card} was visited most ({candidates[0]['visits']} visits, value {candidates[0]['value']:.2f}).")
        return best_card, {
            "visits": candidates[0]["visits"],
            "score": candidates[0]["value"],
            "reason": reason,
            "candidates": candidates,
            "iterations": iterations,
            "elapsed": round(elapsed, 3),
        }
