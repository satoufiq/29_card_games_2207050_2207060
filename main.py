import sys
import webbrowser
import threading
import time

def start_gui(open_browser: bool = True):
    import web_server
    print("\nStarting Intelligent 29 Cards Game...")

    def on_ready(url):
        if not open_browser:
            return
        def _open():
            time.sleep(0.8)
            webbrowser.open(url)
        threading.Thread(target=_open, daemon=True).start()

    web_server.run_server(port=web_server.PORT, on_ready=on_ready)

def run_headless_match():
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    from game_controller import GameController
    from ai_player import AIStrategy

    print("\n=== Intelligent 29 Cards Game: Headless 4-AI Match ===")
    controller = GameController(human_seat=None, seed=42)
    
    # Fast MCTS setting
    for a in controller.agents:
        a.mcts_sims = 30
        a.mcts.simulations_per_move = 30

    res = controller.play_round_synchronously()
    print("\n--- Match Completed ---")
    print(f"Contract Bid: {res['bid']} by Player {res['bidder']} (Trump: {res['trump']})")
    print(f"Team A (P0+P2) Points: {res['round_points'][0]}")
    print(f"Team B (P1+P3) Points: {res['round_points'][1]}")
    print(f"Game Points Awarded: {res['game_points']}")
    print(f"Total Tricks Played: {len(controller.state.completed_tricks)}")
    print(f"Latest AI Insight: {controller.state.latest_insight}")

def run_tournament_benchmarks():
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    from evaluation import TournamentEvaluator
    print("\n=== Intelligent 29 Cards Game: AI Tournament Benchmarks ===")
    results = TournamentEvaluator.run_benchmark_suite(num_rounds_per_matchup=10, mcts_sims=25)
    print("\nDone! See results above.")

def run_personality_report():
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    from evaluation import PersonalityReport
    PersonalityReport.run()

def start_pygame(human_mode: bool = True):
    from pygame_client.game_window import launch_pygame_app
    print("\nStarting Intelligent 29 Cards Game (desktop client)...")
    launch_pygame_app(human_mode=human_mode)

if __name__ == "__main__":
    if len(sys.argv) > 1:
        cmd = sys.argv[1].lower()
        if cmd == "gui":
            start_gui()
        elif cmd == "serve":
            start_gui(open_browser=False)
        elif cmd == "pygame":
            start_pygame(human_mode=True)
        elif cmd in ("pygame-ai", "pygame_ai"):
            start_pygame(human_mode=False)
        elif cmd == "headless":
            run_headless_match()
        elif cmd == "benchmark":
            run_tournament_benchmarks()
        elif cmd in ("personalities", "personality"):
            run_personality_report()
        else:
            print(f"Unknown command: {cmd}. Usage: py main.py [gui|serve|pygame|pygame-ai|headless|benchmark|personalities]")
    else:
        # Default launcher starts GUI
        start_gui()
