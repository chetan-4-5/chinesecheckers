# =============================================================
# MODERN CHINESE CHECKERS VIEWER
# Responsive + Animated + Modern UI
#
# Features:
# ✔ Responsive scaling
# ✔ Smooth animations
# ✔ Modern dark UI
# ✔ Glow effects
# ✔ Better status bar
# ✔ High DPI support
# ✔ Adaptive board size
# ✔ Smooth rendering loop
# ✔ Works on any laptop resolution
# =============================================================

import json
import math
import socket
import threading
import time
import tkinter as tk

# =============================================================
# SERVER
# =============================================================

HOST = "127.0.0.1"
PORT = 50555


def rpc(payload):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(4.0)
        s.connect((HOST, PORT))
        s.sendall(json.dumps(payload).encode())
        data = s.recv(1_000_000)
        s.close()
        return json.loads(data.decode())
    except Exception as e:
        return {"ok": False, "error": str(e)}


# =============================================================
# BOARD GEOMETRY
# =============================================================

def build_geometry():
    R = 4
    cells = []

    for q in range(-R, R + 1):
        for r in range(-R, R + 1):
            s = -q - r
            if max(abs(q), abs(r), abs(s)) <= R:
                cells.append({"q": q, "r": r, "postype": "board"})

    bases = {
        "blue": [(1, -5), (2, -5), (3, -5), (4, -5),
                 (2, -6), (3, -6), (4, -6),
                 (3, -7), (4, -7),
                 (4, -8)],

        "red": [(-1, 5), (-2, 5), (-3, 5), (-4, 5),
                (-2, 6), (-3, 6), (-4, 6),
                (-3, 7), (-4, 7),
                (-4, 8)],

        "yellow": [(-1, -4), (-2, -3), (-3, -2), (-4, -1),
                   (-2, -4), (-3, -3), (-4, -2),
                   (-3, -4), (-4, -3),
                   (-4, -4)],

        "lawn green": [(5, -4), (5, -3), (5, -2), (5, -1),
                       (6, -4), (6, -3), (6, -2),
                       (7, -4), (7, -3),
                       (8, -4)],

        "purple": [(1, 4), (2, 3), (3, 2), (4, 1),
                   (2, 4), (3, 3), (4, 2),
                   (3, 4), (4, 3),
                   (4, 4)],

        "gray0": [(-5, 1), (-5, 2), (-5, 3), (-5, 4),
                  (-6, 2), (-6, 3), (-6, 4),
                  (-7, 3), (-7, 4),
                  (-8, 4)],
    }

    for colour, coords in bases.items():
        for q, r in coords:
            cells.append({"q": q, "r": r, "postype": colour})

    cells.sort(key=lambda c: (c["r"], c["q"]))
    return cells


CELLS = build_geometry()

# =============================================================
# COLORS
# =============================================================

BG = "#16181D"
PANEL = "#1F232B"
TEXT = "#E8EAF0"
MUTED = "#9097A5"

ZONE_FILL = {
    "blue": "#243C5A",
    "red": "#5A2A2A",
    "yellow": "#5A4A1F",
    "lawn green": "#294A29",
    "purple": "#3E315B",
    "gray0": "#444444",
    "board": "#2A2F38",
}

PIN_FILL = {
    "blue": "#4DA3FF",
    "red": "#FF5A5A",
    "yellow": "#FFB84D",
    "lawn green": "#7DDE5A",
    "purple": "#B48DFF",
    "gray0": "#D4D4D4",
}

PIN_OUTLINE = {
    "blue": "#A9D3FF",
    "red": "#FFC4C4",
    "yellow": "#FFE2AA",
    "lawn green": "#D4FFC4",
    "purple": "#E2D1FF",
    "gray0": "#FFFFFF",
}

LABEL_COLOUR = {
    "blue": "Blue",
    "red": "Red",
    "yellow": "Yellow",
    "lawn green": "Green",
    "purple": "Purple",
    "gray0": "Gray",
}


# =============================================================
# VIEWER
# =============================================================

class Viewer:

    def __init__(self, root, game_id):

        self.root = root
        self.game_id = game_id

        screen_w = root.winfo_screenwidth()
        screen_h = root.winfo_screenheight()

        self.W = min(1400, screen_w - 100)
        self.H = min(950, screen_h - 100)

        root.geometry(f"{self.W}x{self.H}")
        root.configure(bg=BG)

        root.title("Chinese Checkers — Modern Viewer")

        self.canvas = tk.Canvas(
            root,
            bg=BG,
            highlightthickness=0
        )
        self.canvas.pack(fill="both", expand=True)

        self.status = tk.Label(
            root,
            text="Connecting...",
            bg=PANEL,
            fg=TEXT,
            font=("Segoe UI", 12, "bold"),
            pady=10
        )
        self.status.pack(fill="x")

        self.center_x = self.W // 2
        self.center_y = self.H // 2 - 40

        self.scale = min(self.W, self.H) / 28

        self.pin_positions = {}
        self.target_positions = {}

        self.state = None

        self._calculate_positions()

        self._poll()

        self.animate()

    # =========================================================

    def axial_to_pixel(self, q, r):

        x = self.scale * (math.sqrt(3) * q + math.sqrt(3) / 2 * r)
        y = self.scale * (1.5 * r)

        return (
            self.center_x + x,
            self.center_y + y
        )

    # =========================================================

    def _calculate_positions(self):

        self.positions = []

        for cell in CELLS:
            x, y = self.axial_to_pixel(cell["q"], cell["r"])
            self.positions.append((x, y))

    # =========================================================

    def hex_points(self, cx, cy, r):

        pts = []

        for i in range(6):
            angle = math.pi / 6 + i * math.pi / 3
            pts.extend([
                cx + r * math.cos(angle),
                cy + r * math.sin(angle)
            ])

        return pts

    # =========================================================

    def draw_board(self):

        self.canvas.delete("board")

        radius = self.scale * 0.58

        for i, cell in enumerate(CELLS):

            x, y = self.positions[i]

            pts = self.hex_points(x, y, radius)

            fill = ZONE_FILL.get(cell["postype"], "#333")

            self.canvas.create_polygon(
                pts,
                fill=fill,
                outline="#3A404D",
                width=2,
                smooth=True,
                tags="board"
            )

    # =========================================================

    def draw_pins(self):

        self.canvas.delete("pins")

        if not self.state:
            return

        pins = self.state.get("pins", {})

        radius = self.scale * 0.42

        for colour, indexes in pins.items():

            for idx in indexes:

                tx, ty = self.positions[idx]

                key = f"{colour}_{idx}"

                if key not in self.pin_positions:
                    self.pin_positions[key] = [tx, ty]

                px, py = self.pin_positions[key]

                # Smooth interpolation
                px += (tx - px) * 0.18
                py += (ty - py) * 0.18

                self.pin_positions[key] = [px, py]

                # Glow
                self.canvas.create_oval(
                    px - radius * 1.35,
                    py - radius * 1.35,
                    px + radius * 1.35,
                    py + radius * 1.35,
                    fill="",
                    outline=PIN_FILL[colour],
                    width=2,
                    tags="pins"
                )

                # Main pin
                self.canvas.create_oval(
                    px - radius,
                    py - radius,
                    px + radius,
                    py + radius,
                    fill=PIN_FILL[colour],
                    outline=PIN_OUTLINE[colour],
                    width=3,
                    tags="pins"
                )

                # Shine
                self.canvas.create_oval(
                    px - radius * 0.45,
                    py - radius * 0.6,
                    px - radius * 0.05,
                    py - radius * 0.2,
                    fill="white",
                    outline="",
                    tags="pins"
                )

    # =========================================================

    def animate(self):

        self.draw_board()
        self.draw_pins()

        self.root.after(16, self.animate)

    # =========================================================

    def _poll(self):

        def fetch():
            resp = rpc({
                "op": "get_state",
                "game_id": self.game_id
            })

            self.root.after(0, lambda: self._on_state(resp))

        threading.Thread(target=fetch, daemon=True).start()

    # =========================================================

    def _on_state(self, resp):

        if not resp.get("ok"):
            self.status.config(
                text=f"Server Error : {resp.get('error')}"
            )

            self.root.after(1000, self._poll)
            return

        self.state = resp["state"]

        move_count = self.state.get("move_count", 0)

        turn = self.state.get("current_turn_colour", "")

        turn_label = LABEL_COLOUR.get(turn, turn)

        status = self.state.get("status", "")

        self.status.config(
            text=f"Status : {status}     |     Turn : {turn_label}     |     Moves : {move_count}"
        )

        self.root.after(500, self._poll)


# =============================================================
# GAME PICKER
# =============================================================

class GamePicker:

    def __init__(self, root):

        self.root = root

        root.geometry("850x500")
        root.configure(bg=BG)

        root.title("Chinese Checkers — Game Picker")

        title = tk.Label(
            root,
            text="Chinese Checkers Live Viewer",
            bg=BG,
            fg=TEXT,
            font=("Segoe UI", 22, "bold")
        )
        title.pack(pady=25)

        self.listbox = tk.Listbox(
            root,
            bg=PANEL,
            fg=TEXT,
            font=("Consolas", 12),
            selectbackground="#4DA3FF",
            relief="flat",
            borderwidth=0,
            height=14
        )

        self.listbox.pack(
            fill="both",
            expand=True,
            padx=30,
            pady=20
        )

        controls = tk.Frame(root, bg=BG)
        controls.pack(pady=10)

        refresh_btn = tk.Button(
            controls,
            text="Refresh",
            bg="#3B4252",
            fg="white",
            relief="flat",
            font=("Segoe UI", 11, "bold"),
            padx=20,
            pady=10,
            command=self.refresh
        )

        refresh_btn.pack(side="left", padx=10)

        open_btn = tk.Button(
            controls,
            text="Watch Game",
            bg="#4DA3FF",
            fg="white",
            relief="flat",
            font=("Segoe UI", 11, "bold"),
            padx=20,
            pady=10,
            command=self.open_game
        )

        open_btn.pack(side="left", padx=10)

        self.games = []

        self.refresh()

    # =========================================================

    def refresh(self):

        self.listbox.delete(0, tk.END)

        resp = rpc({"op": "status"})

        if not resp.get("ok"):
            return

        self.games = resp.get("games", [])

        for game in self.games:

            gid = game["game_id"]

            status = game["status"]

            players = ", ".join(
                f"{p['name']} ({LABEL_COLOUR.get(p['colour'], p['colour'])})"
                for p in game["players"]
            )

            line = f"{gid[:10]}...   [{status}]   {players}"

            self.listbox.insert(tk.END, line)

    # =========================================================

    def open_game(self):

        sel = self.listbox.curselection()

        if not sel:
            return

        game = self.games[sel[0]]

        game_id = game["game_id"]

        win = tk.Toplevel(self.root)

        Viewer(win, game_id)


# =============================================================
# MAIN
# =============================================================

def main():

    root = tk.Tk()

    try:
        root.call('tk', 'scaling', 1.5)
    except:
        pass

    GamePicker(root)

    root.mainloop()


if __name__ == "__main__":
    main()