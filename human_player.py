# =============================================================
# human_player.py — Graphical human player for Chinese Checkers
#
# Drop next to game.py / checkers_board.py / checkers_pins.py
# Run:  python human_player.py
#
# How to play:
#   1. Enter your name and the server IP when prompted
#   2. The board window opens — wait for the game to start
#   3. When it's YOUR turn the board highlights your pieces in gold
#   4. Click one of your pieces  →  legal moves appear as green dots
#   5. Click a green dot         →  move is sent to the server
#   6. Repeat until the game ends
# =============================================================

import json
import math
import socket
import threading
import time
import tkinter as tk
from tkinter import messagebox, simpledialog

# ── Server connection ──────────────────────────────────────────────────────────
HOST = "127.0.0.1"
PORT = 50555

def rpc(payload, host=None, port=None):
    h = host or HOST
    p = port or PORT
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(6.0)
        s.connect((h, p))
        s.sendall(json.dumps(payload).encode())
        data = s.recv(1_000_000)
        s.close()
        return json.loads(data.decode())
    except Exception as e:
        return {"ok": False, "error": str(e)}

# ── Board geometry ─────────────────────────────────────────────────────────────
HEX_DIRS = [(1,0),(-1,0),(0,1),(0,-1),(1,-1),(-1,1)]

COLOUR_OPPOSITES = {
    'red':'blue','blue':'red',
    'lawn green':'gray0','gray0':'lawn green',
    'yellow':'purple','purple':'yellow',
}
LABEL = {
    'red':'Red','blue':'Blue','yellow':'Yellow',
    'lawn green':'Green','purple':'Purple','gray0':'Gray',
}

def build_geometry():
    R = 4
    cells = []
    for q in range(-R, R+1):
        for r in range(-R, R+1):
            s = -q-r
            if max(abs(q),abs(r),abs(s)) <= R:
                cells.append({"q":q,"r":r,"postype":"board"})
    bases = {
        "blue":       [(1,-5),(2,-5),(3,-5),(4,-5),(2,-6),(3,-6),(4,-6),(3,-7),(4,-7),(4,-8)],
        "red":        [(-1,5),(-2,5),(-3,5),(-4,5),(-2,6),(-3,6),(-4,6),(-3,7),(-4,7),(-4,8)],
        "yellow":     [(-1,-4),(-2,-3),(-3,-2),(-4,-1),(-2,-4),(-3,-3),(-4,-2),(-3,-4),(-4,-3),(-4,-4)],
        "lawn green": [(5,-4),(5,-3),(5,-2),(5,-1),(6,-4),(6,-3),(6,-2),(7,-4),(7,-3),(8,-4)],
        "purple":     [(1,4),(2,3),(3,2),(4,1),(2,4),(3,3),(4,2),(3,4),(4,3),(4,4)],
        "gray0":      [(-5,1),(-5,2),(-5,3),(-5,4),(-6,2),(-6,3),(-6,4),(-7,3),(-7,4),(-8,4)],
    }
    for colour, coords in bases.items():
        for q,r in coords:
            cells.append({"q":q,"r":r,"postype":colour})
    cells.sort(key=lambda c:(c["r"],c["q"]))
    index_of = {(c["q"],c["r"]):i for i,c in enumerate(cells)}
    return cells, index_of

CELLS, INDEX_OF = build_geometry()

SPACING = 36
def axial_to_pixel(q, r):
    x = SPACING*(math.sqrt(3)*q + math.sqrt(3)/2*r)
    y = SPACING*(3/2*r)
    return x, y

CELL_PX = [axial_to_pixel(c["q"],c["r"]) for c in CELLS]
xs = [p[0] for p in CELL_PX]; ys = [p[1] for p in CELL_PX]
MIN_X,MAX_X,MIN_Y,MAX_Y = min(xs),max(xs),min(ys),max(ys)
MARGIN = 65
CANVAS_W = int(MAX_X-MIN_X)+2*MARGIN
CANVAS_H = int(MAX_Y-MIN_Y)+2*MARGIN+80

def screen(idx):
    x,y = CELL_PX[idx]
    return x-MIN_X+MARGIN, y-MIN_Y+MARGIN

HEX_R  = SPACING*0.54
PIN_R  = SPACING*0.38
DOT_R  = SPACING*0.24

# ── Colours ────────────────────────────────────────────────────────────────────
ZONE_FILL    = {"blue":"#DCEEFB","red":"#FDDEDE","yellow":"#FEF3D0",
                "lawn green":"#E4F4CE","purple":"#EAE8FD","gray0":"#EDEDEB","board":"#F5F3EE"}
ZONE_OUTLINE = {"blue":"#9DC8F0","red":"#F5AAAA","yellow":"#F5D87A",
                "lawn green":"#A8D878","purple":"#B8B4EF","gray0":"#CBCBC8","board":"#D0CEC8"}
PIN_FILL     = {"blue":"#3A8FDE","red":"#E04848","yellow":"#F0A020",
                "lawn green":"#5FA020","purple":"#7C76DC","gray0":"#888884"}
PIN_OUTLINE  = {"blue":"#1C5FA5","red":"#A82C2C","yellow":"#B87018",
                "lawn green":"#3A6E10","purple":"#4E49B5","gray0":"#555552"}

def hex_corners(cx, cy, r):
    pts = []
    for i in range(6):
        a = math.pi/6 + i*math.pi/3
        pts += [cx+r*math.cos(a), cy+r*math.sin(a)]
    return pts

def hit_test(mx, my):
    best, best_d = None, HEX_R*1.1
    for i in range(len(CELLS)):
        sx,sy = screen(i)
        d = math.hypot(mx-sx, my-sy)
        if d < best_d:
            best_d = d; best = i
    return best

# ── Main game window ───────────────────────────────────────────────────────────
class HumanPlayer:
    POLL_MS = 400

    def __init__(self, root, host, port, player_name):
        self.root        = root
        self.host        = host
        self.port        = port
        self.name        = player_name
        self.game_id     = None
        self.player_id   = None
        self.my_colour   = None
        self.state       = None
        self.last_move_count = -1

        # Interaction state
        self.selected_pin_id  = None   # str key into legal_moves
        self.selected_cell    = None   # board cell index of selected pin
        self.legal_moves_map  = {}     # {pin_id_str: [to_cell, ...]}
        self.highlight_cells  = []     # legal destination cells to draw

        root.title("Chinese Checkers — Human Player")
        root.configure(bg="#2A2A28")
        root.resizable(False, False)

        # Top status bar
        top = tk.Frame(root, bg="#2A2A28")
        top.pack(fill="x", padx=10, pady=(10,4))
        self.status_var = tk.StringVar(value="Joining game…")
        self.turn_var   = tk.StringVar(value="")
        tk.Label(top, textvariable=self.status_var,
                 bg="#2A2A28", fg="#E0DDD8", font=("Helvetica",13,"bold")).pack(side="left")
        tk.Label(top, textvariable=self.turn_var,
                 bg="#2A2A28", fg="#AECBEF", font=("Helvetica",11)).pack(side="left", padx=12)

        # Canvas
        self.canvas = tk.Canvas(root, width=CANVAS_W, height=CANVAS_H,
                                bg="#2A2A28", highlightthickness=0)
        self.canvas.pack(padx=8, pady=4)
        self.canvas.bind("<Button-1>", self._on_click)
        self.canvas.bind("<Motion>",   self._on_hover)

        # Bottom info bar
        bot = tk.Frame(root, bg="#2A2A28")
        bot.pack(fill="x", padx=10, pady=(0,8))
        self.hint_var = tk.StringVar(value="")
        self.move_var = tk.StringVar(value="")
        tk.Label(bot, textvariable=self.hint_var,
                 bg="#2A2A28", fg="#F0A020", font=("Helvetica",10)).pack(side="left")
        tk.Label(bot, textvariable=self.move_var,
                 bg="#2A2A28", fg="#888884", font=("Helvetica",10)).pack(side="right")

        self._draw_board_bg()
        self._join()

    # ── RPC (non-blocking wrapper) ─────────────────────────────────────────────
    def _rpc_async(self, payload, callback):
        def worker():
            resp = rpc(payload, self.host, self.port)
            self.root.after(0, lambda: callback(resp))
        threading.Thread(target=worker, daemon=True).start()

    # ── Board background (static) ──────────────────────────────────────────────
    def _draw_board_bg(self):
        self.canvas.delete("bg")
        for i, cell in enumerate(CELLS):
            sx,sy = screen(i)
            pts = hex_corners(sx, sy, HEX_R)
            pt  = cell["postype"]
            self.canvas.create_polygon(pts,
                fill=ZONE_FILL.get(pt, ZONE_FILL["board"]),
                outline=ZONE_OUTLINE.get(pt, ZONE_OUTLINE["board"]),
                width=1, tags="bg")
        self.canvas.tag_lower("bg")

    # ── Join flow ──────────────────────────────────────────────────────────────
    def _join(self):
        self._rpc_async({"op":"join","player_name":self.name}, self._on_join)

    def _on_join(self, resp):
        if not resp.get("ok"):
            messagebox.showerror("Join failed", resp.get("error","?"))
            self.root.destroy(); return
        self.game_id   = resp["game_id"]
        self.player_id = resp["player_id"]
        self.my_colour = resp["colour"]
        col_label = LABEL.get(self.my_colour, self.my_colour)
        goal_label = LABEL.get(COLOUR_OPPOSITES.get(self.my_colour,""), "?")
        self.status_var.set(f"You are {col_label}  →  goal: {goal_label}")
        self.hint_var.set("Waiting for other players to join…")
        self._wait_ready()

    def _wait_ready(self):
        self._rpc_async({"op":"get_state","game_id":self.game_id}, self._on_wait_ready)

    def _on_wait_ready(self, resp):
        if not resp.get("ok"):
            self.root.after(800, self._wait_ready); return
        status = resp["state"].get("status","")
        if status in ("READY_TO_START","PLAYING"):
            self.hint_var.set("All players joined! Sending START…")
            self._rpc_async(
                {"op":"start","game_id":self.game_id,"player_id":self.player_id},
                lambda _: self._poll()
            )
        else:
            self.root.after(600, self._wait_ready)

    # ── Main poll loop ─────────────────────────────────────────────────────────
    def _poll(self):
        self._rpc_async({"op":"get_state","game_id":self.game_id}, self._on_state)

    def _on_state(self, resp):
        if not resp.get("ok"):
            self.hint_var.set(f"Server error: {resp.get('error')}")
            self.root.after(1000, self._poll); return

        state = resp["state"]
        self.state = state
        status     = state.get("status","")
        move_count = state.get("move_count",0)
        cur_colour = state.get("current_turn_colour")
        last_move  = state.get("last_move")

        # Show last move made
        if move_count != self.last_move_count and last_move:
            by  = last_move.get("by","?")
            col = LABEL.get(last_move.get("colour",""), last_move.get("colour","?"))
            frm = last_move.get("from","?")
            to  = last_move.get("to","?")
            ms  = last_move.get("move_ms",0)
            marker = " ← you" if last_move.get("colour") == self.my_colour else ""
            self.move_var.set(f"Last: {by}({col}) {frm}→{to} [{ms:.0f}ms]{marker}")
            self.last_move_count = move_count
            # Clear selection when a move just happened
            self._clear_selection()

        self.move_var.set(f"Move #{move_count}  |  " + self.move_var.get().split("|")[-1].strip()
                          if "|" not in self.move_var.get() else self.move_var.get())

        self._redraw_pins(state.get("pins",{}), last_move, move_count)

        if status == "FINISHED":
            self._show_finish(state); return

        if status == "PLAYING":
            if cur_colour == self.my_colour:
                self.turn_var.set("⭐ YOUR TURN")
                self.hint_var.set("Click one of your pieces")
                self._fetch_legal_moves()
            else:
                who = next((p["name"] for p in state.get("players",[])
                            if p["colour"]==cur_colour), cur_colour)
                self.turn_var.set(f"⏳ Waiting for {who}…")
                self.hint_var.set("")
                self.legal_moves_map = {}
                self._clear_selection()
                self.root.after(self.POLL_MS, self._poll)
        else:
            self.root.after(800, self._poll)

    # ── Legal moves ────────────────────────────────────────────────────────────
    def _fetch_legal_moves(self):
        self._rpc_async(
            {"op":"get_legal_moves","game_id":self.game_id,"player_id":self.player_id},
            self._on_legal_moves
        )

    def _on_legal_moves(self, resp):
        if not resp.get("ok"):
            self.root.after(self.POLL_MS, self._poll); return
        self.legal_moves_map = resp.get("legal_moves", {})

    # ── Click handler ──────────────────────────────────────────────────────────
    def _on_click(self, event):
        if self.state is None: return
        if self.state.get("current_turn_colour") != self.my_colour: return
        if self.state.get("status") != "PLAYING": return

        mx = self.canvas.canvasx(event.x)
        my = self.canvas.canvasy(event.y)
        idx = hit_test(mx, my)
        if idx is None: return

        # Clicked a legal destination → send move
        if idx in self.highlight_cells and self.selected_pin_id is not None:
            self._send_move(self.selected_pin_id, idx)
            return

        # Clicked one of my own pins → select it
        pins = self.state.get("pins", {})
        my_cells = pins.get(self.my_colour, [])
        if idx in my_cells:
            pin_list_idx = my_cells.index(idx)
            pid_str = str(pin_list_idx)
            if pid_str in self.legal_moves_map:
                self.selected_pin_id = pid_str
                self.selected_cell   = idx
                self.highlight_cells = self.legal_moves_map[pid_str]
                n = len(self.highlight_cells)
                self.hint_var.set(f"Pin selected — {n} move{'s' if n!=1 else ''} available. Click a green dot.")
                self._redraw_pins(pins, self.state.get("last_move"), self.state.get("move_count",0))
            else:
                self.hint_var.set("That piece has no legal moves right now.")
            return

        # Clicked empty space → deselect
        self._clear_selection()
        self._redraw_pins(pins, self.state.get("last_move"), self.state.get("move_count",0))

    def _on_hover(self, event):
        if self.state is None: return
        mx = self.canvas.canvasx(event.x)
        my = self.canvas.canvasy(event.y)
        idx = hit_test(mx, my)
        pins = self.state.get("pins", {})
        my_cells = pins.get(self.my_colour, [])
        is_my_turn = self.state.get("current_turn_colour") == self.my_colour
        if is_my_turn and (idx in my_cells or idx in self.highlight_cells):
            self.canvas.config(cursor="hand2")
        else:
            self.canvas.config(cursor="")

    def _clear_selection(self):
        self.selected_pin_id = None
        self.selected_cell   = None
        self.highlight_cells = []

    # ── Send move ──────────────────────────────────────────────────────────────
    def _send_move(self, pin_id_str, to_cell):
        self.hint_var.set("Sending move…")
        self._clear_selection()
        self._rpc_async(
            {"op":"move","game_id":self.game_id,"player_id":self.player_id,
             "pin_id":pin_id_str,"to_index":to_cell},
            self._on_move_resp
        )

    def _on_move_resp(self, resp):
        if not resp.get("ok"):
            self.hint_var.set(f"Move rejected: {resp.get('error','?')}")
        else:
            s = resp.get("status","")
            if s == "WIN":
                messagebox.showinfo("🏆 You Win!", resp.get("msg","You win!"))
            elif s == "DRAW":
                messagebox.showinfo("Draw", resp.get("msg","Draw!"))
        self.root.after(self.POLL_MS, self._poll)

    # ── Draw ───────────────────────────────────────────────────────────────────
    def _redraw_pins(self, pins, last_move, move_count):
        self.canvas.delete("pin")
        self.canvas.delete("dot")
        self.canvas.delete("flash")

        is_my_turn = (self.state and
                      self.state.get("current_turn_colour") == self.my_colour and
                      self.state.get("status") == "PLAYING")

        # Flash ring on last move
        for key in ["from","to"]:
            idx = last_move.get(key) if last_move else None
            if idx is not None and 0 <= idx < len(CELLS):
                sx,sy = screen(idx)
                self.canvas.create_oval(
                    sx-HEX_R*0.74, sy-HEX_R*0.74,
                    sx+HEX_R*0.74, sy+HEX_R*0.74,
                    outline="#FFD700", fill="", width=2.5, tags="flash"
                )

        # Green dots for legal destinations
        for idx in self.highlight_cells:
            sx,sy = screen(idx)
            self.canvas.create_oval(
                sx-DOT_R, sy-DOT_R, sx+DOT_R, sy+DOT_R,
                fill="#1DB874", outline="#0F7A4D", width=1.5, tags="dot"
            )

        # Draw all pins
        for colour, indices in pins.items():
            pf = PIN_FILL.get(colour,"#888")
            po = PIN_OUTLINE.get(colour,"#444")
            for ci in indices:
                if not (0 <= ci < len(CELLS)): continue
                sx,sy = screen(ci)
                is_selected   = (ci == self.selected_cell)
                is_mine       = (colour == self.my_colour)
                is_my_movable = (is_my_turn and is_mine and
                                 str(pins[colour].index(ci)) in self.legal_moves_map)

                r = PIN_R * (1.12 if is_selected else 1.0)

                # Glow ring for selectable pieces on your turn
                if is_my_movable and not is_selected:
                    self.canvas.create_oval(
                        sx-r*1.38, sy-r*1.38, sx+r*1.38, sy+r*1.38,
                        fill="", outline="#FFD700", width=2, tags="pin"
                    )

                self.canvas.create_oval(
                    sx-r, sy-r, sx+r, sy+r,
                    fill=pf,
                    outline="#FFFFFF" if is_selected else po,
                    width=2.5 if is_selected else 1.5,
                    tags="pin"
                )
                # Shine dot
                self.canvas.create_oval(
                    sx-r*0.35, sy-r*0.52, sx+r*0.12, sy-r*0.08,
                    fill="white", outline="", tags="pin"
                )

    # ── Game over ──────────────────────────────────────────────────────────────
    def _show_finish(self, state):
        self.turn_var.set("GAME OVER")
        self.hint_var.set("")
        players = state.get("players",[])
        cx,cy = CANVAS_W//2, (CANVAS_H-80)//2
        bw = 270; bh = 28+22*max(len(players),1)
        self.canvas.create_rectangle(cx-bw,cy-bh,cx+bw,cy+bh,
            fill="#1A1A18", outline="#FFD700", width=2, tags="pin")
        lines = ["  GAME OVER  "]
        for p in sorted(players, key=lambda x:-(x.get("score") or {}).get("final_score",0)):
            sc = p.get("score") or {}
            tag = " ← YOU" if p["colour"]==self.my_colour else ""
            lines.append(f"{p['name']} ({LABEL.get(p['colour'],p['colour'])})  "
                         f"{sc.get('final_score',0):.0f} pts{tag}")
        self.canvas.create_text(cx,cy, text="\n".join(lines),
            fill="#F0EDE8", font=("Helvetica",12,"bold"), justify="center", tags="pin")


# ── Login dialog ───────────────────────────────────────────────────────────────
class LoginDialog:
    def __init__(self, root):
        self.root = root
        self.result = None
        root.title("Join Game")
        root.configure(bg="#2A2A28")
        root.resizable(False, False)

        tk.Label(root, text="Chinese Checkers", bg="#2A2A28", fg="#E0DDD8",
                 font=("Helvetica",16,"bold")).grid(row=0,column=0,columnspan=2,pady=(20,4),padx=30)
        tk.Label(root, text="Human Player", bg="#2A2A28", fg="#888884",
                 font=("Helvetica",10)).grid(row=1,column=0,columnspan=2,pady=(0,16))

        for i,(label,default) in enumerate([
            ("Your name:",    "Human"),
            ("Server IP:",    "127.0.0.1"),
            ("Server port:",  str(PORT)),
        ]):
            tk.Label(root, text=label, bg="#2A2A28", fg="#C8C5C0",
                     font=("Helvetica",11)).grid(row=i+2,column=0,sticky="e",padx=(20,8),pady=4)
            e = tk.Entry(root, bg="#1E1E1C", fg="#E0DDD8", insertbackground="#E0DDD8",
                         font=("Helvetica",11), width=22, relief="flat")
            e.insert(0, default)
            e.grid(row=i+2, column=1, sticky="w", padx=(0,20), pady=4)
            setattr(self, f"entry_{i}", e)

        tk.Button(root, text="Join Game ▶", command=self._submit,
                  bg="#3A5F8A", fg="#FFFFFF", relief="flat",
                  font=("Helvetica",11,"bold"), padx=16, pady=6
                  ).grid(row=5,column=0,columnspan=2,pady=(16,20))

        root.bind("<Return>", lambda _: self._submit())
        self.entry_0.focus()

    def _submit(self):
        name = self.entry_0.get().strip()
        host = self.entry_1.get().strip()
        port = self.entry_2.get().strip()
        if not name:
            messagebox.showwarning("Missing", "Please enter your name."); return
        try:
            port = int(port)
        except ValueError:
            messagebox.showwarning("Bad port", "Port must be a number."); return
        self.result = (name, host, port)
        self.root.destroy()


# ── Entry point ────────────────────────────────────────────────────────────────
def main():
    # Login screen
    login_root = tk.Tk()
    dlg = LoginDialog(login_root)
    login_root.mainloop()
    if dlg.result is None:
        return
    name, host, port = dlg.result

    # Main game window
    game_root = tk.Tk()
    HumanPlayer(game_root, host, port, name)
    game_root.mainloop()

if __name__ == "__main__":
    main()