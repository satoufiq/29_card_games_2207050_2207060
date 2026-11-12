import time
import json
from typing import List, Dict, Any, Optional
from game_controller import GameController
from ai_player import AIStrategy

class TournamentEvaluator:
    """
    Automated tournament and benchmarking suite for Intelligent 29 AI agents.
    """

    @classmethod
    def run_matchup(
        cls,
        team0_strategy: AIStrategy,
        team1_strategy: AIStrategy,
        num_rounds: int = 20,
        mcts_sims: int = 40,
        base_seed: int = 100
    ) -> Dict[str, Any]:
        """
        Runs num_rounds between Team 0 (Players 0 & 2) and Team 1 (Players 1 & 3).
        Rotates dealer to eliminate dealer advantage.
        """
        team0_wins = 0
        team1_wins = 0
        team0_pts_total = 0
        team1_pts_total = 0
        bids_made = 0
        contracts_fulfilled = 0

        strategies = [
            team0_strategy,  # P0 (Team 0)
            team1_strategy,  # P1 (Team 1)
            team0_strategy,  # P2 (Team 0)
            team1_strategy   # P3 (Team 1)
        ]

        start_time = time.time()

        for r in range(num_rounds):
            seed = base_seed + r
            controller = GameController(human_seat=None, ai_strategies=strategies, seed=seed)
            controller.state.dealer = r % 4

            # Set search budget
            for agent in controller.agents:
                agent.mcts_sims = mcts_sims
                agent.mcts.simulations_per_move = mcts_sims

            res = controller.play_round_synchronously()
            t0_pts = res["round_points"][0]
            t1_pts = res["round_points"][1]
            team0_pts_total += t0_pts
            team1_pts_total += t1_pts

            bidder = res["bidder"]
            if bidder is not None:
                bids_made += 1
                bidder_team = 0 if bidder in (0, 2) else 1
                bid_val = res.get("target_bid") or res["bid"]
                if res["round_points"][bidder_team] >= bid_val:
                    contracts_fulfilled += 1

            if t0_pts > t1_pts:
                team0_wins += 1
            elif t1_pts > t0_pts:
                team1_wins += 1

        elapsed = time.time() - start_time
        avg_time_per_round = elapsed / max(1, num_rounds)

        return {
            "num_rounds": num_rounds,
            "team0_strategy": team0_strategy.value,
            "team1_strategy": team1_strategy.value,
            "team0_wins": team0_wins,
            "team1_wins": team1_wins,
            "team0_win_rate": round((team0_wins / num_rounds) * 100, 1),
            "team1_win_rate": round((team1_wins / num_rounds) * 100, 1),
            "team0_avg_pts": round(team0_pts_total / num_rounds, 1),
            "team1_avg_pts": round(team1_pts_total / num_rounds, 1),
            "contract_fulfillment_rate": round((contracts_fulfilled / max(1, bids_made)) * 100, 1),
            "elapsed_seconds": round(elapsed, 2),
            "avg_time_per_round_sec": round(avg_time_per_round, 3)
        }

    @classmethod
    def run_benchmark_suite(cls, num_rounds_per_matchup: int = 10, mcts_sims: int = 30) -> List[Dict[str, Any]]:
        """
        Runs standard academic comparisons:
        1. Strategic (MCTS+Minimax+Fuzzy) vs Random Baseline
        2. Strategic (MCTS+Minimax+Fuzzy) vs Rule-Based Baseline
        3. Aggressive vs Conservative
        """
        matchups = [
            (AIStrategy.STRATEGIC, AIStrategy.BASELINE_RANDOM),
            (AIStrategy.STRATEGIC, AIStrategy.BASELINE_RULE),
            (AIStrategy.AGGRESSIVE, AIStrategy.DEFENSIVE),
            (AIStrategy.STRATEGIC, AIStrategy.AGGRESSIVE),
            (AIStrategy.STRATEGIC, AIStrategy.DEFENSIVE)
        ]

        results = []
        for t0_strat, t1_strat in matchups:
            print(f"\n--- Tournament Matchup: Team 0 ({t0_strat.value}) vs Team 1 ({t1_strat.value}) [{num_rounds_per_matchup} rounds] ---", flush=True)
            res = cls.run_matchup(t0_strat, t1_strat, num_rounds=num_rounds_per_matchup, mcts_sims=mcts_sims)
            results.append(res)
            print(
                f"  Outcome: {t0_strat.value} {res['team0_win_rate']}% ({res['team0_wins']} wins, avg {res['team0_avg_pts']} pts) | "
                f"{t1_strat.value} {res['team1_win_rate']}% ({res['team1_wins']} wins, avg {res['team1_avg_pts']} pts) | "
                f"Contract Fulfilled: {res['contract_fulfillment_rate']}% | Time: {res['elapsed_seconds']}s",
                flush=True
            )

        return results

class PersonalityReport:
    """
    Evidence that the three personalities behave differently.

    Part 1 — controlled bidding: every personality sees the SAME random opening
    hands, so differences come only from the personality.
    Part 2 — full deals with mixed tables: bidding and card-play tendencies
    gathered from the decision log of each seat.
    """

    PERSONALITIES = ["AGGRESSIVE", "STRATEGIC", "DEFENSIVE"]

    @classmethod
    def bidding_experiment(cls, num_hands: int = 60, sims: int = 24, seed: int = 2024) -> Dict[str, Dict[str, float]]:
        import random
        from card import Card, Suit, Rank
        from game_state import GameState
        from mc_bidding import MonteCarloExpectedUtilityBidding
        from ai_profiles import get_profile

        rng = random.Random(seed)
        deck = [Card(s, r) for s in Suit for r in Rank]
        hands = [rng.sample(deck, 4) for _ in range(num_hands)]
        out = {}
        for key in cls.PERSONALITIES:
            prof = get_profile(key)
            bids = 0
            ceilings = []
            for i, hand in enumerate(hands):
                st = GameState()
                st.dealer = 3
                res = MonteCarloExpectedUtilityBidding.evaluate_all_bids(
                    hand, 0, st, ai_strategy=key, simulations_per_suit=sims,
                    rng=random.Random(seed + i), profile=prof)
                if res.bid is not None:
                    bids += 1
                    ceilings.append(res.max_bid)
            out[key] = {
                "open_rate": round(bids / num_hands, 3),
                "avg_ceiling": round(sum(ceilings) / len(ceilings), 2) if ceilings else 0.0,
                "max_ceiling": max(ceilings) if ceilings else 0,
            }
        return out

    @classmethod
    def table_experiment(cls, num_deals: int = 8, budget_scale: float = 0.35, seed: int = 500) -> Dict[str, Dict[str, float]]:
        from collections import defaultdict
        agg = defaultdict(lambda: defaultdict(float))
        rotations = [
            ["AGGRESSIVE", "STRATEGIC", "DEFENSIVE", "STRATEGIC"],
            ["DEFENSIVE", "AGGRESSIVE", "STRATEGIC", "AGGRESSIVE"],
            ["STRATEGIC", "DEFENSIVE", "AGGRESSIVE", "DEFENSIVE"],
        ]
        for d in range(num_deals):
            seats = rotations[d % len(rotations)]
            ctrl = GameController(human_seat=None, seed=seed + d,
                                  ai_strategies=[AIStrategy(s) for s in seats], budget_scale=budget_scale)
            ctrl.state.dealer = d % 4
            ctrl.start_new_round()
            ctrl.play_round_synchronously()
            for rec in ctrl.decision_log:
                key = rec["personality"]
                a = agg[key]
                det = rec.get("details") or {}
                if rec["kind"] == "bid":
                    a["bid_decisions"] += 1
                    if rec["action"].startswith(("Bid", "Hold")):
                        a["bids"] += 1
                        a["bid_sum"] += int(rec["action"].split()[1])
                    if rec["action"] == "Single Hand":
                        a["single_hands"] += 1
                elif rec["kind"] == "play" and rec["algorithm"] != "Forced move":
                    a["plays"] += 1
                    if det.get("captures"):
                        a["captures"] += 1
                    if det.get("card_power", 0) >= 6:
                        a["high_cards"] += 1
                    if det.get("partner_winning") and not det.get("captures") and det.get("card_power", 9) <= 4:
                        a["low_on_partner"] += 1
                    if det.get("partner_winning"):
                        a["partner_winning"] += 1
                elif rec["kind"] == "reveal":
                    a["trump_calls"] += 1
                elif rec["kind"] == "double" and rec["action"] in ("Double", "Redouble"):
                    a["doubles"] += 1
        report = {}
        for key in cls.PERSONALITIES:
            a = agg[key]
            plays = max(1.0, a["plays"])
            report[key] = {
                "bid_rate": round(a["bids"] / max(1.0, a["bid_decisions"]), 3),
                "avg_bid": round(a["bid_sum"] / a["bids"], 2) if a["bids"] else 0.0,
                "capture_rate": round(a["captures"] / plays, 3),
                "high_card_rate": round(a["high_cards"] / plays, 3),
                "low_card_when_partner_wins": round(a["low_on_partner"] / max(1.0, a["partner_winning"]), 3),
                "trump_calls": int(a["trump_calls"]),
                "doubles": int(a["doubles"]),
                "free_choices": int(a["plays"]),
            }
        return report

    @classmethod
    def run(cls, num_hands: int = 60, num_deals: int = 8):
        print("\n=== Personality comparison 1: identical opening hands (bidding only) ===", flush=True)
        bid = cls.bidding_experiment(num_hands=num_hands)
        print(f"{'Personality':<12} {'opens':>7} {'avg ceiling':>12} {'max ceiling':>12}")
        for k, v in bid.items():
            print(f"{k:<12} {v['open_rate']:>7.0%} {v['avg_ceiling']:>12} {v['max_ceiling']:>12}")
        print(f"\n=== Personality comparison 2: {num_deals} full deals at mixed tables ===", flush=True)
        table = cls.table_experiment(num_deals=num_deals)
        cols = ["bid_rate", "avg_bid", "capture_rate", "high_card_rate", "low_card_when_partner_wins", "trump_calls", "doubles"]
        print(f"{'Personality':<12} " + " ".join(f"{c[:14]:>15}" for c in cols))
        for k, v in table.items():
            print(f"{k:<12} " + " ".join(f"{v[c]:>15}" for c in cols))
        return {"bidding": bid, "table": table}


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    rounds = int(sys.argv[1]) if len(sys.argv) > 1 else 6
    sims = int(sys.argv[2]) if len(sys.argv) > 2 else 20
    print(f"=== Intelligent 29: AI Evaluation Suite ({rounds} rounds/matchup, {sims} sims/move) ===", flush=True)
    results = TournamentEvaluator.run_benchmark_suite(num_rounds_per_matchup=rounds, mcts_sims=sims)
    print("\n=== Final Benchmark Summary ===", flush=True)
    print(json.dumps(results, indent=2))
