import http.server
import socketserver
import json
import os
import mimetypes
import threading
from urllib.parse import urlparse, parse_qs
from typing import Optional, Dict, Any

from card import Card
from rules import Rules
from game_state import Phase
from game_controller import GameController
from ai_player import AIStrategy
from house_rules import HouseRules
from ai_profiles import PROFILES

PORT = 8029
HOST = "127.0.0.1"   # loopback only: no firewall prompt, and no slow IPv6 'localhost' fallback on Windows
APP_VERSION = "2.2.0"
WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")

SPEED_BUDGET = {"fast": 0.45, "normal": 1.0, "deep": 1.6}
PUBLIC_DETAIL_KEYS = {"simulations", "elapsed", "minimax_nodes", "selected", "proof"}

LOCK = threading.RLock()


def default_config() -> Dict[str, Any]:
    return {
        "mode": "human",
        "personalities": ["STRATEGIC", "AGGRESSIVE", "STRATEGIC", "DEFENSIVE"],
        "names": ["Rafi", "Nadia", "Tanvir", "Mitu"],
        "human_name": "You",
        "rules": HouseRules().to_dict(),
        "ai_speed": "normal",
    }

DEFAULT_NAMES = ["Rafi", "Nadia", "Tanvir", "Mitu"]


def clean_name(value, fallback: str) -> str:
    text = " ".join(str(value or "").split())[:16]
    return text or fallback


def clean_names(values) -> list:
    values = list(values or [])
    return [clean_name(values[i] if i < len(values) else "", DEFAULT_NAMES[i]) for i in range(4)]


CONFIG: Dict[str, Any] = default_config()


def build_controller(cfg: Dict[str, Any]) -> GameController:
    rules = HouseRules.from_dict(cfg.get("rules") or {})
    strategies = []
    for key in (cfg.get("personalities") or [])[:4]:
        try:
            strategies.append(AIStrategy(str(key).upper()))
        except ValueError:
            strategies.append(AIStrategy.STRATEGIC)
    while len(strategies) < 4:
        strategies.append(AIStrategy.STRATEGIC)
    human_seat = 0 if cfg.get("mode", "human") == "human" else None
    seed = cfg.get("seed")
    return GameController(
        human_seat=human_seat, ai_strategies=strategies, seed=seed,
        rules=rules,
        names=clean_names(cfg.get("names")), human_name=clean_name(cfg.get("human_name"), "You"), budget_scale=SPEED_BUDGET.get(cfg.get("ai_speed", "normal"), 1.0))


controller = build_controller(CONFIG)
MATCH = {"id": 1}


def players_info(ctrl: GameController):
    out = []
    for i, a in enumerate(ctrl.agents):
        human = ctrl.human_seat == i
        out.append({
            "seat": i,
            "name": a.name,
            "is_human": human,
            "team": 0 if i in (0, 2) else 1,
            "personality": None if human else a.profile.key,
            "personality_label": "Human" if human else a.profile.label,
            "tagline": "" if human else a.profile.tagline,
        })
    return out


def filtered_decisions(ctrl: GameController, limit: int = 60):
    human = ctrl.human_seat
    res = []
    for rec in ctrl.decision_log[-limit:]:
        r = dict(rec)
        if human is not None and r.get("player") != human:
            r["summary"] = r.get("public_summary") or r.get("summary")
            r["details"] = {k: v for k, v in (r.get("details") or {}).items() if k in PUBLIC_DETAIL_KEYS}
            r["private_hidden"] = True
        r.pop("public_summary", None)
        res.append(r)
    return res


def build_state_payload() -> Dict[str, Any]:
    ctrl = controller
    viewer = ctrl.human_seat if ctrl.human_seat is not None else 0
    spectator = ctrl.human_seat is None
    # AI vs AI: the spectator sees every hand. The AIs themselves only ever get masked states.
    view = ctrl.state.get_player_view(viewer, reveal_all=spectator)
    legal = []
    if ctrl.state.phase == Phase.PLAYING and ctrl.human_seat is not None and ctrl.is_human_turn():
        legal = [c.code for c in Rules.get_legal_cards(ctrl.human_seat, ctrl.state)]
    view.update({
        "legal_cards": legal,
        "is_human_turn": ctrl.is_human_turn(),
        "mode": "ai" if spectator else "human",
        "human_seat": ctrl.human_seat,
        "players": players_info(ctrl),
        "decisions": filtered_decisions(ctrl),
        "deal_id": ctrl.deal_id,
        "deal_stage": ctrl.deal_stage,
        "match_id": MATCH["id"],
        "rules": ctrl.rules.to_dict(),
        "ai_speed": CONFIG.get("ai_speed", "normal"),
        "stats": ctrl.stats,
    })
    return view


class GameRequestHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _json(self, obj, status=200, cors=False):
        data = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        if cors:
            # Lets a page served by an outdated server find this one and redirect.
            self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = urlparse(self.path).path
        try:
            if path == "/api/state":
                with LOCK:
                    self._json(build_state_payload())
            elif path == "/api/version":
                self._json({"app": "bangladesh-29", "version": APP_VERSION}, cors=True)
            elif path == "/api/stats":
                with LOCK:
                    self._json(dict(controller.stats))
            elif path == "/api/defaults":
                self._json({
                    "config": default_config(),
                    "current": CONFIG,
                    "personalities": [{"key": p.key, "label": p.label, "tagline": p.tagline} for p in PROFILES.values()],
                })
            else:
                self._serve_static(path)
        except Exception as e:  # pragma: no cover - defensive
            print(f"[ERROR GET {path}]: {e}")
            self._json({"error": str(e)}, 500)

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/api/shutdown":
            # Only the local machine may ask (used when a newer `py main.py` takes over).
            if self.client_address[0] not in ("127.0.0.1", "::1"):
                self.send_error(403, "Forbidden")
                return
            self._json({"success": True, "message": "Shutting down."})
            srv = HTTPD.get("server")
            if srv is not None:
                print("[INFO] Another copy of the game is starting; handing over.")
                threading.Thread(target=srv.shutdown, daemon=True).start()
            return
        if path != "/api/action":
            self.send_error(404, "Not Found")
            return
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8") if length else ""
        try:
            data = json.loads(body) if body else {}
        except json.JSONDecodeError:
            data = {}
        with LOCK:
            ok, msg = self._handle_action(data)
            self._json({"success": ok, "message": msg})

    def _serve_static(self, path: str):
        if path in ("/", ""):
            path = "/index.html"
        file_path = os.path.normpath(os.path.join(WEB_DIR, path.lstrip("/")))
        if not file_path.startswith(WEB_DIR) or not os.path.isfile(file_path):
            self.send_error(404, "File Not Found")
            return
        ext = os.path.splitext(file_path)[1].lower()
        # Windows' registry sometimes maps .js to text/plain; be explicit.
        mime = {".js": "application/javascript", ".css": "text/css", ".html": "text/html",
                ".svg": "image/svg+xml", ".json": "application/json"}.get(ext) or mimetypes.guess_type(file_path)[0]
        with open(file_path, "rb") as f:
            content = f.read()
        self.send_response(200)
        textual = bool(mime) and (mime.startswith("text") or mime.endswith(("javascript", "json", "svg+xml")))
        self.send_header("Content-Type", (mime or "application/octet-stream") + ("; charset=utf-8" if textual else ""))
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _handle_action(self, data: dict):
        global controller, CONFIG
        action = data.get("action")
        ctrl = controller
        try:
            if action == "new_match":
                cfg = default_config()
                incoming = data.get("config") or {}
                for k in ("mode", "personalities", "names", "human_name", "rules", "ai_speed", "seed"):
                    if k in incoming:
                        cfg[k] = incoming[k]
                controller = build_controller(cfg)
                CONFIG = cfg
                MATCH["id"] += 1
                return True, "New match started."
            if action == "bid":
                return ctrl.human_bid(data.get("bid_value"))
            if action == "pass":
                return ctrl.human_bid(None)
            if action == "single_hand":
                return ctrl.human_call_single_hand()
            if action == "single_hand_decision":
                return ctrl.human_single_hand_decision(bool(data.get("declare")))
            if action == "select_trump":
                opt = data.get("option") or data.get("card_code")
                return ctrl.human_select_trump_option(opt) if opt else (False, "No trump option given.")
            if action == "play_card":
                return ctrl.human_play_card(Card.from_str(data.get("card_code", "")))
            if action == "reveal_trump":
                return ctrl.human_reveal_trump()
            if action == "declare_pair":
                if ctrl.human_seat is None:
                    return False, "No human player."
                return ctrl.declare_pair(ctrl.human_seat)
            if action == "dismiss_marriage_popup":
                ctrl.state.marriage_popup_pending = False
                return True, "Dismissed."
            if action == "dismiss_abandoned_deal":
                if ctrl.state.deal_abandoned:
                    ctrl.start_next_deal_after_abandonment()
                return True, "Next deal."
            if action == "step":
                return True, ctrl.step().get("status", "stepped")
            if action == "step_trick":
                ctrl.step_trick()
                return True, "Stepped trick."
            if action == "clear_trick":
                ctrl.clear_completed_trick()
                return True, "Trick collected."
            if action == "next_round":
                if ctrl.state.phase == Phase.ROUND_OVER:
                    ctrl.next_round()
                return True, "Next round."
            if action in ("restart", "rematch"):
                ctrl.restart_match()
                MATCH["id"] += 1
                return True, "Match restarted."
            if action == "double":
                return ctrl.human_double(bool(data.get("double", True)))
            if action == "redouble":
                return ctrl.human_redouble(bool(data.get("redouble", True)))
            if action == "set_ai_speed":
                speed = data.get("value", "normal")
                CONFIG["ai_speed"] = speed
                for a in ctrl.agents:
                    a.set_budget_scale(SPEED_BUDGET.get(speed, 1.0))
                return True, f"AI thinking budget: {speed}."
            return False, f"Unknown action: {action}"
        except Exception as e:
            import traceback
            traceback.print_exc()
            return False, str(e)


class ThreadingServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = False


# ---------------------------------------------------------------------------- single entry point
# `py main.py` must always end with exactly one, current game server. Any copy of this game
# already running on the game ports (including older versions) is shut down and replaced.

def _http_json(url: str, timeout: float = 0.8, data: Optional[bytes] = None):
    import urllib.request
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"} if data else {})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _port_busy(port: int) -> bool:
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.3)
        return probe.connect_ex((HOST, port)) == 0


def identify_game_server(port: int) -> Optional[str]:
    """Version string if a copy of this game answers on `port` ('legacy' for the first version), else None."""
    try:
        v = _http_json(f"http://{HOST}:{port}/api/version")
        if v.get("app") == "bangladesh-29":
            return str(v.get("version"))
    except Exception:
        pass
    try:
        st = _http_json(f"http://{HOST}:{port}/api/state")
        if isinstance(st, dict) and "phase" in st and "round_number" in st:
            return "legacy"
    except Exception:
        pass
    return None


def _listening_pid(port: int) -> Optional[int]:
    import subprocess
    try:
        if os.name == "nt":
            out = subprocess.run(["netstat", "-ano", "-p", "TCP"], capture_output=True, text=True, timeout=8).stdout
            for line in out.splitlines():
                parts = line.split()
                if len(parts) >= 5 and parts[3].upper() == "LISTENING" and parts[1].rsplit(":", 1)[-1] == str(port):
                    return int(parts[4])
        else:
            out = subprocess.run(["lsof", "-t", f"-iTCP:{port}", "-sTCP:LISTEN"], capture_output=True, text=True, timeout=8).stdout
            return int(out.split()[0]) if out.split() else None
    except Exception:
        return None
    return None


def _command_line(pid: int) -> str:
    import subprocess
    try:
        if os.name == "nt":
            cmd = f"(Get-CimInstance Win32_Process -Filter 'ProcessId={pid}').CommandLine"
            return subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, text=True, timeout=15).stdout.strip()
        return subprocess.run(["ps", "-o", "args=", "-p", str(pid)], capture_output=True, text=True, timeout=8).stdout.strip()
    except Exception:
        return ""


def stop_game_server(port: int, version: str) -> bool:
    """Shuts down a copy of this game listening on `port`. Returns True when the port is free."""
    import time
    asked = False
    if version != "legacy":
        try:
            asked = bool(_http_json(f"http://{HOST}:{port}/api/shutdown", data=b"{}").get("success"))
        except Exception:
            asked = False
    if asked:
        for _ in range(15):
            if not _port_busy(port):
                return True
            time.sleep(0.2)
    if _port_busy(port):
        pid = _listening_pid(port)
        if pid and pid != os.getpid():
            cmdline = _command_line(pid).lower()
            if "main.py" in cmdline or "web_server.py" in cmdline:
                import signal
                import subprocess
                if os.name == "nt":
                    subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True, timeout=10)
                else:
                    os.kill(pid, signal.SIGTERM)
                print(f"[INFO] Stopped an older copy of the game on port {port} (process {pid}).")
            else:
                print(f"[WARNING] Port {port} is held by process {pid}, which does not look like this game; leaving it alone.")
                return False
    for _ in range(30):
        if not _port_busy(port):
            return True
        time.sleep(0.2)
    return not _port_busy(port)


def prepare_single_server(port: int = PORT, extra_ports: int = 6) -> Optional[str]:
    """
    Makes sure exactly one current server will exist. Returns the URL of a current server that
    is already running on the main port (to reuse), otherwise None after freeing the port.
    """
    for p in range(port, port + extra_ports):
        if not _port_busy(p):
            continue
        version = identify_game_server(p)
        if version is None:
            continue
        if p == port and version == APP_VERSION:
            continue          # reuse below
        print(f"[INFO] Replacing a {'previous' if version != APP_VERSION else 'duplicate'} copy of the game on port {p}...")
        stop_game_server(p, version)
    if identify_game_server(port) == APP_VERSION:
        return f"http://{HOST}:{port}"
    return None


HTTPD = {"server": None}


def run_server(port=PORT, on_ready=None):
    """The single entry point's server: one current game server, normally on port 8029."""
    existing = prepare_single_server(port)
    if existing:
        print(f"\n[INFO] Intelligent 29 Cards Game is already running at {existing}")
        if on_ready:
            on_ready(existing)
        return
    target = port
    httpd = None
    for _ in range(6):
        if _port_busy(target):
            print(f"[INFO] Port {target} is used by another program. Trying {target + 1}...")
            target += 1
            continue
        try:
            httpd = ThreadingServer((HOST, target), GameRequestHandler)
            break
        except OSError:
            print(f"[INFO] Port {target} is busy. Trying {target + 1}...")
            target += 1
    if httpd is None:
        print(f"[ERROR] Could not bind to port {port} or the next ports.")
        return
    with httpd:
        url = f"http://{HOST}:{target}"
        print("============================================================")
        print(" Intelligent 29 Cards Game")
        print(f" Open: {url}")
        print("============================================================")
        HTTPD["server"] = httpd
        if on_ready:
            on_ready(url)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down server.")
        print("[INFO] Server stopped.")


if __name__ == "__main__":
    run_server()
