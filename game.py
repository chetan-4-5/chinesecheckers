# ==========================================================
# game.py — SERVER  (unchanged from professor's version)
# Run this on ONE machine.  python game.py
# Then run player.py on each player's machine.
# ==========================================================

import os
import json
import uuid
import time
import socket
import threading
from datetime import datetime
from typing import Dict, List, Optional, Any
import math
import random

from checkers_board import HexBoard
from checkers_pins import Pin

def ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def log_path(game_id: str) -> str:
    os.makedirs("games", exist_ok=True)
    return os.path.join("games", f"game_{game_id}.log")

def write_log(game_id: str, msg: str):
    with open(log_path(game_id), "a", encoding="utf-8") as f:
        f.write(f"[{ts()}] {msg}\n")

def safe_json(obj: Any) -> str:
    try:
        return json.dumps(obj)
    except Exception as e:
        return json.dumps({"ok": False, "error": f"json-encode-failed: {e}"})

COLOUR_ORDER   = ['red', 'lawn green', 'yellow', 'blue', 'gray0', 'purple']
PRIMARY_COLOURS = ['red', 'lawn green', 'yellow']
random.shuffle(PRIMARY_COLOURS)
COMPLEMENT = {'red': 'blue', 'lawn green': 'gray0', 'yellow': 'purple'}
MAX_PLAYERS = 6

# ── CHANGE THESE TO MATCH YOUR PROFESSOR'S FINAL VALUES ──────────────────────
TURN_TIMEOUT_SEC   = 10
GAME_TIME_LIMIT_SEC = 400
# ─────────────────────────────────────────────────────────────────────────────

class Player:
    def __init__(self, pid: str, name: str, colour: str):
        self.player_id = pid
        self.name = name
        self.colour = colour
        self.ready = False
        self.status = "PLAYING"
        self.move_count = 0
        self.time_taken_sec = 0.0

class Game:
    def __init__(self):
        self.game_id = str(uuid.uuid4())
        self.board = HexBoard()
        self.players: List[Player] = []
        self.pins_by_colour: Dict[str, List[Pin]] = {}
        self.status = "AVAILABLE"
        self.created_ts = ts()
        self.joined_primary_index = 0
        self.lock_joining = False
        self.total_start_ns = None
        self.turn_started_ns = None
        self.turn_order: List[str] = []
        self.current_turn_index = 0
        self.move_count = 0
        self.move_times_ms: List[float] = []
        self.last_move = None
        self.turn_timeout_notice = None
        self.scores: Dict[str, Dict[str, float]] = {}

    def assign_colour(self) -> Optional[str]:
        n = len(self.players) + 1
        if n > MAX_PLAYERS:
            return None
        if n % 2 == 1:
            if self.joined_primary_index >= len(PRIMARY_COLOURS):
                return None
            return PRIMARY_COLOURS[self.joined_primary_index]
        else:
            primary = PRIMARY_COLOURS[self.joined_primary_index]
            self.joined_primary_index += 1
            return COMPLEMENT[primary]

    def init_pins(self, colour: str):
        if colour in self.pins_by_colour:
            return
        idxs = self.board.axial_of_colour(colour)[:10]
        self.pins_by_colour[colour] = [
            Pin(self.board, idxs[i], id=i, color=colour)
            for i in range(len(idxs))
        ]

    def compute_turn_order(self):
        present = [p.colour for p in self.players]
        first = present[0]
        if first in COLOUR_ORDER:
            idx = COLOUR_ORDER.index(first)
            rotated = COLOUR_ORDER[idx:] + COLOUR_ORDER[:idx]
        else:
            rotated = COLOUR_ORDER[:]
        self.turn_order = [c for c in rotated if c in present]
        self.current_turn_index = 0

    def current_turn_colour(self):
        if self.status != "PLAYING":
            return None
        if not self.turn_order:
            return None
        return self.turn_order[self.current_turn_index]

    def advance_turn(self):
        if self.turn_order:
            self.current_turn_index = (self.current_turn_index + 1) % len(self.turn_order)
            self.turn_started_ns = time.perf_counter_ns()

    def ensure_time_limits(self):
        if self.total_start_ns:
            elapsed = (time.perf_counter_ns() - self.total_start_ns) / 1e9
            if elapsed > GAME_TIME_LIMIT_SEC:
                self.status = "FINISHED"
                self.turn_timeout_notice = "GAME TIME LIMIT REACHED."
                self.compute_scores()
                write_log(self.game_id, self.turn_timeout_notice)
                return
        if self.status == "PLAYING" and self.turn_started_ns:
            turn_elapsed = (time.perf_counter_ns() - self.turn_started_ns) / 1e9
            if turn_elapsed > TURN_TIMEOUT_SEC:
                colour = self.current_turn_colour()
                self.turn_timeout_notice = (
                    f"Player with colour {colour} exceeded {TURN_TIMEOUT_SEC}s "
                    f"at move {self.move_count}. Turn skipped."
                )
                self.compute_scores()
                write_log(self.game_id, f"TURN TIMEOUT: {self.turn_timeout_notice}")
                self.advance_turn()

    def check_player_status(self, colour: str) -> str:
        opposite = self.board.colour_opposites[colour]
        pins = self.pins_by_colour[colour]
        if all(self.board.cells[p.axialindex].postype == opposite for p in pins):
            return "WIN"
        if all(len(p.getPossibleMoves()) == 0 for p in pins):
            return "DRAW"
        return "PLAYING"

    def compute_scores(self):
        def axial_dist(a, b):
            dq = abs(a.q - b.q)
            dr = abs(a.r - b.r)
            ds = abs((-a.q - a.r) - (-b.q - b.r))
            return max(dq, dr, ds)

        for pl in self.players:
            colour = pl.colour
            pins   = self.pins_by_colour[colour]
            opposite = self.board.colour_opposites[colour]

            time_score = max(0.0, 100.0 - pl.time_taken_sec) if pl.time_taken_sec > 0 else 0

            move_score_func = lambda x: math.exp(-((x - 45) ** 2) /
                                                 (2 * ((4 if x < 45 else 18) ** 2)))
            move_score = move_score_func(pl.move_count) if pl.move_count > 0 else 0

            pins_in_goal = sum(
                1 for p in pins
                if self.board.cells[p.axialindex].postype == opposite
            )
            pin_goal_score = pins_in_goal * 100.0

            target_idxs  = self.board.axial_of_colour(opposite)
            target_cells = [self.board.cells[i] for i in target_idxs]
            total_dist = 0
            for p in pins:
                if self.board.cells[p.axialindex].postype != opposite:
                    best = min(axial_dist(self.board.cells[p.axialindex], tgt)
                               for tgt in target_cells)
                    total_dist += best
            distance_score = max(0.0, 200.0 - total_dist) if pl.move_count > 0 else 0

            final_score = time_score + move_score + pin_goal_score + distance_score

            self.scores[pl.player_id] = {
                "final_score": final_score,
                "time_score": time_score,
                "move_score": move_score,
                "pin_goal_score": pin_goal_score,
                "distance_score": distance_score,
                "moves": pl.move_count,
                "pins_in_goal": pins_in_goal,
                "total_distance": total_dist,
                "time_taken_sec": pl.time_taken_sec,
            }

            write_log(
                self.game_id,
                f"SCORE {pl.name} ({colour}): Final={final_score:.1f}, "
                f"Time={time_score:.1f}, Moves({pl.move_count})={move_score:.1f}, "
                f"Pins({pins_in_goal})={pin_goal_score:.1f}, Dist={distance_score:.1f}"
            )

    def to_public_state(self) -> Dict[str, Any]:
        return {
            "game_id": self.game_id,
            "status": self.status,
            "players": [
                {
                    "player_id": pl.player_id,
                    "name": pl.name,
                    "colour": pl.colour,
                    "ready": pl.ready,
                    "status": pl.status,
                    "score": self.scores.get(pl.player_id),
                }
                for pl in self.players
            ],
            "pins": {
                colour: [p.axialindex for p in pins]
                for colour, pins in self.pins_by_colour.items()
            },
            "move_count": self.move_count,
            "current_turn_colour": self.current_turn_colour(),
            "turn_order": self.turn_order,
            "last_move": self.last_move,
            "turn_timeout_notice": self.turn_timeout_notice,
        }


class Session:
    def __init__(self):
        self.games: Dict[str, Game] = {}
        self.session_games: List[str] = []
        self.lock = threading.RLock()

    def create_game(self) -> str:
        with self.lock:
            g = Game()
            self.games[g.game_id] = g
            self.session_games.append(g.game_id)
            write_log(g.game_id, "GAME CREATED")
            return g.game_id

    def pick_available_game(self) -> Optional[Game]:
        for gid in self.session_games:
            g = self.games[gid]
            if not g.lock_joining and len(g.players) < MAX_PLAYERS:
                if g.status in ("waiting for other player", "AVAILABLE", "READY_TO_START"):
                    return g
        return None

    def join_request(self, player_name: str) -> Dict[str, Any]:
        with self.lock:
            g = self.pick_available_game()
            if not g:
                return {"ok": False, "error": "No available game. Ask admin to Create."}
            colour = g.assign_colour()
            if not colour:
                return {"ok": False, "error": "Game full"}
            pid = str(uuid.uuid4())
            pl = Player(pid, player_name, colour)
            g.players.append(pl)
            g.init_pins(colour)
            if len(g.players) == 1:
                g.status = "waiting for other player"
            else:
                g.status = "READY_TO_START"
            write_log(g.game_id, f"PLAYER JOINED: {player_name} as {colour}")
            return {
                "ok": True,
                "game_id": g.game_id,
                "player_id": pid,
                "colour": colour,
                "status": g.status,
            }

    def mark_start_ready(self, game_id: str, player_id: str) -> Dict[str, Any]:
        with self.lock:
            g = self.games.get(game_id)
            if not g:
                return {"ok": False, "error": "Game not found"}
            pl = next((p for p in g.players if p.player_id == player_id), None)
            if not pl:
                return {"ok": False, "error": "Player not in game"}
            pl.ready = True
            if all(p.ready for p in g.players) and len(g.players) >= 2:
                g.status = "PLAYING"
                g.compute_turn_order()
                g.lock_joining = True
                g.total_start_ns   = time.perf_counter_ns()
                g.turn_started_ns  = time.perf_counter_ns()
                write_log(game_id, f"GAME STARTED — turn order: {g.turn_order}")
            return {"ok": True, "status": g.status}

    def get_state(self, game_id: str) -> Dict[str, Any]:
        with self.lock:
            g = self.games.get(game_id)
            if not g:
                return {"ok": False, "error": "Game not found"}
            g.ensure_time_limits()
            return {"ok": True, "state": g.to_public_state()}

    def get_legal_moves(self, game_id: str, player_id: str) -> Dict[str, Any]:
        with self.lock:
            g = self.games.get(game_id)
            if not g:
                return {"ok": False, "error": "Game not found"}
            pl = next((p for p in g.players if p.player_id == player_id), None)
            if not pl:
                return {"ok": False, "error": "Player not in game"}
            pins = g.pins_by_colour.get(pl.colour, [])
            legal = {}
            for pin in pins:
                legal[str(pin.id)] = pin.getPossibleMoves()
            return {"ok": True, "legal_moves": legal}

    def make_move(self, game_id: str, player_id: str,
                  pin_id: str, to_index: int) -> Dict[str, Any]:
        with self.lock:
            g = self.games.get(game_id)
            if not g:
                return {"ok": False, "error": "Game not found"}
            if g.status != "PLAYING":
                return {"ok": False, "error": f"Game status is {g.status}"}

            pl = next((p for p in g.players if p.player_id == player_id), None)
            if not pl:
                return {"ok": False, "error": "Player not in game"}
            if g.current_turn_colour() != pl.colour:
                return {"ok": False, "error": "Not your turn"}

            pins = g.pins_by_colour.get(pl.colour, [])
            pin_obj = next((p for p in pins if str(p.id) == str(pin_id)), None)
            if not pin_obj:
                return {"ok": False, "error": f"Pin {pin_id} not found"}

            legal = pin_obj.getPossibleMoves()
            if int(to_index) not in legal:
                return {"ok": False, "error": f"Illegal move: {to_index} not in {legal}"}

            move_start_ns = time.perf_counter_ns()
            from_idx = pin_obj.axialindex
            pin_obj.placePin(int(to_index))

            elapsed_ms = (time.perf_counter_ns() - move_start_ns) / 1e6
            turn_time  = (time.perf_counter_ns() - g.turn_started_ns) / 1e9

            g.move_count += 1
            g.move_times_ms.append(elapsed_ms)
            pl.move_count += 1
            pl.time_taken_sec += turn_time

            g.last_move = {
                "by": pl.name,
                "colour": pl.colour,
                "from": from_idx,
                "to": int(to_index),
                "move_ms": elapsed_ms,
            }
            write_log(game_id,
                      f"MOVE {pl.name} ({pl.colour}): {from_idx}→{to_index} [{elapsed_ms:.1f}ms]")

            status = g.check_player_status(pl.colour)
            if status == "WIN":
                g.status = "FINISHED"
                g.compute_scores()
                write_log(game_id, f"WIN: {pl.name} ({pl.colour})")
                return {"ok": True, "status": "WIN", "msg": f"{pl.name} wins!"}
            if status == "DRAW":
                g.status = "FINISHED"
                g.compute_scores()
                write_log(game_id, f"DRAW: {pl.name} ({pl.colour})")
                return {"ok": True, "status": "DRAW", "msg": "Draw!"}

            g.advance_turn()
            return {"ok": True, "status": "OK"}

    def list_games(self) -> List[Dict[str, Any]]:
        with self.lock:
            result = []
            for gid in self.session_games:
                g = self.games[gid]
                result.append({
                    "game_id": gid,
                    "status": g.status,
                    "players": [{"name": p.name, "colour": p.colour} for p in g.players],
                    "created": g.created_ts,
                })
            return result


# ════════════════════════════════════════════════════════════════════════
# TCP Server
# ════════════════════════════════════════════════════════════════════════

HOST = "0.0.0.0"
PORT = 50555

session = Session()


def handle_client(conn: socket.socket, addr):
    try:
        data = conn.recv(1_000_000)
        if not data:
            return
        try:
            payload = json.loads(data.decode("utf-8"))
        except Exception:
            conn.sendall(safe_json({"ok": False, "error": "bad-json"}).encode())
            return

        op = payload.get("op", "")

        if op == "join":
            resp = session.join_request(payload.get("player_name", ""))
        elif op == "start":
            resp = session.mark_start_ready(payload["game_id"], payload["player_id"])
        elif op == "get_state":
            resp = session.get_state(payload["game_id"])
        elif op == "get_legal_moves":
            resp = session.get_legal_moves(payload["game_id"], payload["player_id"])
        elif op == "move":
            resp = session.make_move(
                payload["game_id"], payload["player_id"],
                payload["pin_id"], payload["to_index"]
            )
        elif op == "status":
            resp = {"ok": True, "games": session.list_games()}
        else:
            resp = {"ok": False, "error": f"Unknown op: {op}"}

        conn.sendall(safe_json(resp).encode("utf-8"))
    except Exception as e:
        try:
            conn.sendall(safe_json({"ok": False, "error": str(e)}).encode())
        except Exception:
            pass
    finally:
        conn.close()


def admin_console():
    print("Server commands: create | status | quit")
    while True:
        try:
            cmd = input("> ").strip().lower()
        except EOFError:
            break
        if cmd == "create":
            gid = session.create_game()
            print(f"Game created: {gid}")
        elif cmd == "status":
            games = session.list_games()
            if not games:
                print("No games in session.")
            for g in games:
                print(f"  [{g['status']}] {g['game_id'][:8]}... — "
                      f"{[p['name']+'/'+p['colour'] for p in g['players']]}")
        elif cmd in ("quit", "exit", "q"):
            print("Shutting down.")
            os._exit(0)
        else:
            print("Unknown command.")


def main():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((HOST, PORT))
    srv.listen(16)
    print(f"=== Chinese Checkers Server ===")
    print(f"Listening on {HOST}:{PORT}")
    print(f"Turn timeout : {TURN_TIMEOUT_SEC}s   Game limit: {GAME_TIME_LIMIT_SEC}s")
    print()

    def accept_loop():
        while True:
            try:
                conn, addr = srv.accept()
                t = threading.Thread(target=handle_client, args=(conn, addr), daemon=True)
                t.start()
            except Exception:
                pass

    threading.Thread(target=accept_loop, daemon=True).start()
    admin_console()


if __name__ == "__main__":
    main()
