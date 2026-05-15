# =============================================================
# player.py  — AI client (replaces the random PLAYING LOGIC)
# Drop this file into the same folder as game.py / checkers_board.py / checkers_pins.py
# =============================================================

import os
import json
import socket
import time
from typing import Dict, Any

# Import our AI agent
from agent import ChineseCheckersAgent

HOST = "127.0.0.1"   # change to server IP if playing over LAN
#127.0.0.1
#172.20.10.2
PORT = 50555

DEBUG_NET = os.getenv("DEBUG_NET", "0") not in ("0", "", "false", "False")

def debug(*args):
    if DEBUG_NET:
        print("[NET]", *args)


def rpc(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Send JSON to server and receive JSON reply."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(10.0)
    try:
        s.connect((HOST, PORT))
    except Exception as e:
        return {"ok": False, "error": f"connect-failed: {e}"}

    s.sendall(json.dumps(payload).encode("utf-8"))
    data = s.recv(1_000_000)
    s.close()

    if not data:
        return {"ok": False, "error": "no-response"}
    try:
        return json.loads(data.decode("utf-8"))
    except Exception as e:
        return {"ok": False, "error": f"bad-json: {e}"}


def render_json_board(state):
    pins = state.get("pins", {})
    print("=== BOARD STATE ===")
    for colour, indices in pins.items():
        print(f"  {colour}: {indices}")
    print("===================")


def main():
    timeout_notice_move = -1
    print("==== AI Player ====")
    name = input("Enter name: ").strip()
    if not name:
        return

    # JOIN GAME
    r = rpc({"op": "join", "player_name": name})
    if not r.get("ok"):
        print("JOIN ERROR:", r.get("error"))
        return

    game_id   = r["game_id"]
    player_id = r["player_id"]
    colour    = r["colour"]

    print(f"Joined game {game_id} as colour: {colour}")

    # ── Initialise the AI agent with our colour ──────────────────────────
    agent = ChineseCheckersAgent(my_colour=colour)
    print(f"AI Agent initialised for colour: {colour}")

    # Wait until game ready
    while True:
        st = rpc({"op": "get_state", "game_id": game_id})
        if st.get("state", {}).get("status") in ("READY_TO_START", "PLAYING"):
            break
        print("Waiting for other players...")
        time.sleep(0.5)

    input("\nPress ENTER to send START...")
    rpc({"op": "start", "game_id": game_id, "player_id": player_id})
    print("Sent START signal")

    # Wait until PLAYING
    while True:
        st = rpc({"op": "get_state", "game_id": game_id})
        if st.get("state", {}).get("status") == "PLAYING":
            break
        time.sleep(0.5)

    print("\n=== GAME STARTED ===\n")

    last_move_seen = 0

    while True:
        st = rpc({"op": "get_state", "game_id": game_id})
        if not st.get("ok"):
            print("Error:", st.get("error"))
            return

        state = st["state"]

        # Timeout messages
        if state.get("turn_timeout_notice") and timeout_notice_move < state.get("move_count", 0):
            print("⚠  TIMEOUT NOTICE:", state["turn_timeout_notice"])
            timeout_notice_move = state.get("move_count", 0)

        # Finished?
        if state["status"] == "FINISHED":
            print("\n=== GAME FINISHED ===")
            print("FINAL SCORES:")
            for pl in state["players"]:
                sc = pl.get("score")
                if sc:
                    print(
                        f"  {pl['name']} ({pl['colour']}): "
                        f"{sc['final_score']:.1f}  "
                        f"[time={sc['time_score']:.1f}, "
                        f"moves({sc['moves']})={sc['move_score']:.1f}, "
                        f"pins={sc['pin_goal_score']:.1f}, "
                        f"dist={sc['distance_score']:.1f}]"
                    )
            print("======================")
            break

        # Show last move made by anyone
        if state["move_count"] > last_move_seen:
            mv = state.get("last_move")
            if mv:
                marker = " ← OPPONENT" if mv["colour"] != colour else " ← ME"
                print(
                    f"MOVE: {mv['by']} ({mv['colour']}) "
                    f"{mv['from']}→{mv['to']}  [{mv['move_ms']:.1f}ms]{marker}"
                )
            last_move_seen = state["move_count"]

        # ── OUR TURN ────────────────────────────────────────────────────
        if state.get("current_turn_colour") == colour and state["status"] == "PLAYING":
            print("\n>>> My turn <<<")

            # ---- PLAYING LOGIC ----
            # Request legal moves from server
            legal_req = rpc({
                "op": "get_legal_moves",
                "game_id": game_id,
                "player_id": player_id
            })

            if not legal_req.get("ok"):
                print("Error requesting legal moves:", legal_req.get("error"))
                time.sleep(0.5)
                continue

            legal_moves = legal_req.get("legal_moves", {})
            # legal_moves = { "pin_id": [to_index, to_index, ...], ... }

            movable = [(pid, moves) for pid, moves in legal_moves.items() if moves]
            if not movable:
                print("No legal moves available — waiting.")
                time.sleep(0.5)
                continue

            # Ask AI agent to pick the best move
            # We give it the full game state so it can reason about position
            best_pin_id, best_to_index = agent.choose_move(state, legal_moves)

            print(f"AI chose: pin {best_pin_id} → cell {best_to_index}")
            # ---- END PLAYING LOGIC ----

            mv = rpc({
                "op": "move",
                "game_id": game_id,
                "player_id": player_id,
                "pin_id": best_pin_id,
                "to_index": best_to_index
            })

            render_json_board(state)

            if not mv.get("ok"):
                print("Move rejected:", mv.get("error"))
            else:
                if mv.get("status") == "WIN":
                    print("🏆 YOU WIN!")
                    print(mv.get("msg"))
                elif mv.get("status") == "DRAW":
                    print("DRAW")
                    print(mv.get("msg"))

        time.sleep(0.3)


if __name__ == "__main__":
    main()
