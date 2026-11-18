"""
Endgame Minimax with Alpha-Beta pruning.

Used when only a few cards remain: at that point the remaining play can be
searched exactly. Because hidden cards are unknown, the search runs on several
sampled deals (from the searcher's information set) and averages the minimax
value of each candidate card, instead of trusting a single guessed deal.
The leaf value is the point differential plus a large bonus for the
contract (or Single Hand) result, so the search plays for the target.
"""
from typing import List, Optional, Tuple, Dict
from card import Card, Suit
from game_state import Trick
from sim_engine import SimState, team_of, POWER, POINTS, contract_made

CONTRACT_BONUS = 12.0


class EndgameMinimax:

    @classmethod
    def find_best_move(cls, player_id, hands, current_trick, trump_suit, trump_revealed,
                       current_team_points, max_depth: int = 12):
        return cls.find_best_move_multi_deal(player_id, [hands], current_trick, trump_suit, trump_revealed,
                                             current_team_points, style="STRATEGIC", max_depth=max_depth)

    @classmethod
    def find_best_move_multi_deal(
        cls,
        player_id: int,
        sampled_deals: List[List[List[Card]]],
        current_trick: Optional[Trick],
        trump_suit: Optional[Suit],
        trump_revealed: bool,
        current_team_points: List[int],
        style: str = "STRATEGIC",
        max_depth: int = 16,
        target: Optional[int] = None,
        bidder: Optional[int] = None,
        sitting_out: Optional[int] = None,
        bonus: bool = False,
        done: Optional[int] = None,
        single_hand: bool = False,
        sampled_trumps: Optional[List[Optional[Suit]]] = None,
        root_legal: Optional[List[Card]] = None,
    ) -> Tuple[Card, float, int]:
        if not sampled_deals:
            raise ValueError("No sampled deals provided for the endgame solver.")

        trick_cards = [(pc.player_id, pc.card) for pc in current_trick.cards] if current_trick else []
        first_sim = cls._make_sim(sampled_deals[0], trick_cards, player_id, trump_suit, trump_revealed,
                                  sitting_out, current_team_points, bonus, done, bidder, target, single_hand)
        legal = list(root_legal) if root_legal else first_sim.legal(player_id)
        if not legal:
            hand = sampled_deals[0][player_id]
            return (hand[0] if hand else None), 0.0, 0
        if len(legal) == 1:
            return legal[0], 0.0, 1

        my_team = team_of(player_id)
        totals: Dict[Card, float] = {c: 0.0 for c in legal}
        nodes = [0]
        for i, deal in enumerate(sampled_deals):
            trump = sampled_trumps[i] if sampled_trumps else trump_suit
            base = cls._make_sim(deal, trick_cards, player_id, trump, trump_revealed, sitting_out,
                                 current_team_points, bonus, done, bidder, target, single_hand)
            for c in legal:
                if c not in base.hands[player_id]:
                    base.hands[player_id].append(c)
            for card in legal:
                sim = base.clone()
                sim.play(card, allow_reveal=trump_revealed)
                val = cls._alphabeta(sim, my_team, -1e9, 1e9, 1, max_depth, nodes)
                if sim.trick_log:
                    w, tp = sim.trick_log[0]
                    if style == "AGGRESSIVE" and team_of(w) == my_team:
                        val += 0.4 * tp
                    elif style == "DEFENSIVE" and team_of(w) != my_team:
                        val -= 0.5 * POINTS[card]
                totals[card] += val

        n = max(1, len(sampled_deals))
        avg = {c: totals[c] / n for c in legal}
        cls.last_scores = avg
        best = max(legal, key=lambda c: (avg[c], -POWER[c]))
        return best, round(avg[best], 2), nodes[0]

    last_scores: Dict[Card, float] = {}

    @staticmethod
    def _make_sim(deal, trick_cards, player_id, trump, revealed, sitting_out, pts, bonus, done,
                  bidder, target, single_hand) -> SimState:
        hands = [list(h) for h in deal]
        if done is None:
            done = 8 - len(hands[player_id])
        played = set()
        return SimState(hands=hands, trick=list(trick_cards), current=player_id, trump=trump,
                        revealed=revealed or single_hand, sitting_out=sitting_out, pts=list(pts),
                        tricks_won=[0, 0, 0, 0], done=done, bonus=bonus, played=played,
                        bidder=bidder, target=target or 0, single_hand=single_hand)

    @classmethod
    def _leaf(cls, sim: SimState, my_team: int) -> float:
        val = float(sim.pts[my_team] - sim.pts[1 - my_team])
        if sim.bidder is not None and (sim.target or sim.single_hand):
            made = contract_made(sim)
            good = made if my_team == team_of(sim.bidder) else not made
            val += CONTRACT_BONUS if good else -CONTRACT_BONUS
        return val

    @classmethod
    def _alphabeta(cls, sim: SimState, my_team: int, alpha: float, beta: float,
                   depth: int, max_depth: int, nodes: List[int]) -> float:
        nodes[0] += 1
        if sim.is_terminal() or depth >= max_depth or not sim.hands[sim.current]:
            return cls._leaf(sim, my_team)
        p = sim.current
        moves = sim.legal(p)
        # Move ordering: strong cards first improves pruning.
        moves.sort(key=lambda c: -POWER[c])
        maximizing = team_of(p) == my_team
        if maximizing:
            best = -1e9
            for m in moves:
                child = sim.clone()
                child.play(m)
                v = cls._alphabeta(child, my_team, alpha, beta, depth + 1, max_depth, nodes)
                if v > best:
                    best = v
                if best > alpha:
                    alpha = best
                if beta <= alpha:
                    break
            return best
        best = 1e9
        for m in moves:
            child = sim.clone()
            child.play(m)
            v = cls._alphabeta(child, my_team, alpha, beta, depth + 1, max_depth, nodes)
            if v < best:
                best = v
            if best < beta:
                beta = best
            if beta <= alpha:
                break
        return best
