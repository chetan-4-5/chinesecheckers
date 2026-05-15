# =============================================================
# viewer.py — Responsive Live graphical viewer for Chinese Checkers
# Compatible with all laptop / monitor sizes
# =============================================================

import json
import math
import socket
import threading
import tkinter as tk

# ── Server connection ──────────────────────────────────────────
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


# ── Board geometry (same as checkers_board.py) ─────────────────
def build_geometry():
    R = 4
    cells = []
    for q in range(-R, R + 1):
        for r in range(-R, R + 1):
            s = -q - r
            if max(abs(q), abs(r), abs(s)) <= R:
                cells.append({"q": q, "r": r, "postype": "board"})

    bases = {
        "blue":       [(1,-5),(2,-5),(3,-5),(4,-5),(2,-6),(3,-6),(4,-6),(3,-7),(4,-7),(4,-8)],
        "red":        [(-1,5),(-2,5),(-3,5),(-4,5),(-2,6),(-3,6),(-4,6),(-3,7),(-4,7),(-4,8)],
        "yellow":     [(-1,-4),(-2,-3),(-3,-2),(-4,-1),(-2,-4),(-3,-3),(-4,-2),(-3,-4),(-4,-3),(-4,-4)],
        "lawn green": [(5,-4),(5,-3),(5,-2),(5,-1),(6,-4),(6,-3),(6,-2),(7,-4),(7,-3),(8,-4)],
        "purple":     [(1,4),(2,3),(3,2),(4,1),(2,4),(3,3),(4,2),(3,4),(4,3),(4,4)],
        "gray0":      [(-5,1),(-5,2),(-5,3),(-5,4),(-6,2),(-6,3),(-6,4),(-7,3),(-7,4),(-8,4)],
    }
    for colour, coords in bases.items():
        for q, r in coords:
            cells.append({"q": q, "r": r, "postype": colour})

    cells.sort(key=lambda c: (c["r"], c["q"]))
    return cells


CELLS = build_geometry()

ZONE_FILL = {
    "blue": "#DCEEFB", "red": "#FDDEDE", "yellow": "#FEF3D0",
    "lawn green": "#E4F4CE", "purple": "#EAE8FD",
    "gray0": "#EDEDEB", "board": "#F5F3EE"
}

ZONE_OUTLINE = {
    "blue": "#9DC8F0", "red": "#F5AAAA", "yellow": "#F5D87A",
    "lawn green": "#A8D878", "purple": "#B8B4EF",
    "gray0": "#CBCBC8", "board": "#D0CEC8"
}

PIN_FILL = {
    "blue": "#3A8FDE", "red": "#E04848",
    "yellow": "#F0A020", "lawn green": "#5FA020",
    "purple": "#7C76DC", "gray0": "#888884"
}

PIN_OUTLINE = {
    "blue": "#1C5FA5", "red": "#A82C2C",
    "yellow": "#B87018", "lawn green": "#3A6E10",
    "purple": "#4E49B5", "gray0": "#555552"
}


# ── Viewer ─────────────────────────────────────────────────────
class Viewer:
    def __init__(self, root, game_id):
        self.root = root
        self.game_id = game_id

        root.title(f"Chinese Checkers Viewer — {game_id[:8]}…")
        root.configure(bg="#2A2A28")

        self.canvas = tk.Canvas(root, bg="#2A2A28", highlightthickness=0)
        self.canvas.pack(expand=True, fill="both", padx=10, pady=10)

        self.root.bind("<Configure>", self._on_resize)
        self._compute_geometry()

        self._poll()

    # ── Geometry scaling ───────────────────────────────────────
    def _compute_geometry(self):
        w = self.canvas.winfo_width() or self.root.winfo_screenwidth()
        h = self.canvas.winfo_height() or self.root.winfo_screenheight()

        usable = min(w * 0.85, h * 0.85)
        self.spacing = max(18, usable / 32)
        self.hex_r = self.spacing * 0.54
        self.pin_r = self.spacing * 0.38

        self.cell_pixels = []
        for c in CELLS:
            x = self.spacing * (math.sqrt(3) * c["q"] + math.sqrt(3)/2 * c["r"])
            y = self.spacing * (3/2 * c["r"])
            self.cell_pixels.append((x, y))

        xs = [p[0] for p in self.cell_pixels]
        ys = [p[1] for p in self.cell_pixels]
        self.min_x, self.max_x = min(xs), max(xs)
        self.min_y, self.max_y = min(ys), max(ys)
        self.margin = self.spacing * 2

        self._draw_board()

    def _screen(self, idx):
        x, y = self.cell_pixels[idx]
        return (
            x - self.min_x + self.margin,
            y - self.min_y + self.margin
        )

    # ── Drawing ─────────────────────────────────────────────────
    def _draw_board(self):
        self.canvas.delete("all")
        for i, cell in enumerate(CELLS):
            cx, cy = self._screen(i)
            pts = []
            for k in range(6):
                a = math.pi / 6 + k * math.pi / 3
                pts += [cx + self.hex_r * math.cos(a), cy + self.hex_r * math.sin(a)]
            self.canvas.create_polygon(
                pts,
                fill=ZONE_FILL[cell["postype"]],
                outline=ZONE_OUTLINE[cell["postype"]],
                width=1
            )

    def _draw_pins(self, pins, last_move):
        for colour, indices in pins.items():
            for idx in indices:
                cx, cy = self._screen(idx)
                self.canvas.create_oval(
                    cx - self.pin_r, cy - self.pin_r,
                    cx + self.pin_r, cy + self.pin_r,
                    fill=PIN_FILL[colour],
                    outline=PIN_OUTLINE[colour],
                    width=1.5
                )

    # ── Networking ──────────────────────────────────────────────
    def _poll(self):
        def fetch():
            resp = rpc({"op": "get_state", "game_id": self.game_id})
            self.root.after(0, lambda: self._on_state(resp))
        threading.Thread(target=fetch, daemon=True).start()

    def _on_state(self, resp):
        if not resp.get("ok"):
            self.root.after(800, self._poll)
            return

        state = resp["state"]
        self._draw_board()
        self._draw_pins(state.get("pins", {}), state.get("last_move"))
        if state.get("status") != "FINISHED":
            self.root.after(500, self._poll)

    def _on_resize(self, event):
        self._compute_geometry()


# ── Game Picker ────────────────────────────────────────────────
class GamePicker:
    def __init__(self, root):
        self.root = root
        root.title("Chinese Checkers Viewer")
        root.configure(bg="#2A2A28")

        self.listbox = tk.Listbox(
            root, width=60, height=12,
            bg="#1E1E1C", fg="#D8D5D0", font=("Courier", 10)
        )
        self.listbox.pack(padx=20, pady=12)

        tk.Button(root, text="Refresh", command=self._refresh).pack(pady=4)
        tk.Button(root, text="Watch Game", command=self._open).pack(pady=4)

        self.games = []
        self._refresh()

    def _refresh(self):
        self.listbox.delete(0, tk.END)
        resp = rpc({"op": "status"})
        if not resp.get("ok"):
            return
        self.games = [g["game_id"] for g in resp.get("games", [])]
        for gid in self.games:
            self.listbox.insert(tk.END, gid[:8] + "...")

    def _open(self):
        sel = self.listbox.curselection()
        if not sel:
            return
        Viewer(tk.Toplevel(self.root), self.games[sel[0]])


def main():
    root = tk.Tk()
    GamePicker(root)
    root.mainloop()


if __name__ == "__main__":
    main()