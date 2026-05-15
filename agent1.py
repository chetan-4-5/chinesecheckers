# =============================================================
# agent.py  — Improved Strategic AI Agent for Chinese Checkers
#
# Key improvements over original:
#   1. Evaluation tracks ALL opponents, not just one complement colour
#   2. Spread penalty replaced with chain-formation bonus
#   3. "Fill goal from back" — rewards landing on deepest goal cells
#   4. Home-base penalty — discourages pins sitting idle in start zone
#   5. Removed the broken move-count Gaussian (was causing premature slowdown)
#   6. Distance weight tuned to match actual server scoring formula
#   7. Move ordering improved to prefer deep-goal landings
# =============================================================

import math
import time
import copy
import random
from typing import Dict, List, Tuple, Optional

HEX_DIRS = [(1, 0), (-1, 0), (0, 1), (0, -1), (1, -1), (-1, 1)]

COLOUR_OPPOSITES = {
    'red':        'blue',
    'blue':       'red',
    'lawn green': 'gray0',
    'gray0':      'lawn green',
    'yellow':     'purple',
    'purple':     'yellow',
}

# ─────────────────────────────────────────────────────────────────────────────
# Board geometry  (identical to checkers_board.py — no Tkinter dependency)
# ─────────────────────────────────────────────────────────────────────────────

def _build_board_geometry():
    R = 4
    cells = []
    for q in range(-R, R + 1):
        for r in range(-R, R + 1):
            s = -q - r
            if max(abs(q), abs(r), abs(s)) <= R:
                cells.append({"q": q, "r": r, "postype": "board"})

    base_blue        = [(1,-5),(2,-5),(3,-5),(4,-5),(2,-6),(3,-6),(4,-6),(3,-7),(4,-7),(4,-8)]
    base_red         = [(-1,5),(-2,5),(-3,5),(-4,5),(-2,6),(-3,6),(-4,6),(-3,7),(-4,7),(-4,8)]
    base_yellow      = [(-1,-4),(-2,-3),(-3,-2),(-4,-1),(-2,-4),(-3,-3),(-4,-2),(-3,-4),(-4,-3),(-4,-4)]
    base_green       = [(5,-4),(5,-3),(5,-2),(5,-1),(6,-4),(6,-3),(6,-2),(7,-4),(7,-3),(8,-4)]
    base_purple      = [(1,4),(2,3),(3,2),(4,1),(2,4),(3,3),(4,2),(3,4),(4,3),(4,4)]
    base_gray0       = [(-5,1),(-5,2),(-5,3),(-5,4),(-6,2),(-6,3),(-6,4),(-7,3),(-7,4),(-8,4)]

    colour_bases = [
        ("blue", base_blue), ("red", base_red), ("yellow", base_yellow),
        ("lawn green", base_green), ("purple", base_purple), ("gray0", base_gray0),
    ]
    for colour, base in colour_bases:
        for (q, r) in base:
            cells.append({"q": q, "r": r, "postype": colour})

    cells.sort(key=lambda c: (c["r"], c["q"]))
    index_of = {(c["q"], c["r"]): i for i, c in enumerate(cells)}
    return cells, index_of


_CELLS, _INDEX_OF = _build_board_geometry()
_NUM_CELLS = len(_CELLS)

# Goal indices for each colour (cells of the OPPOSITE zone)
_GOAL_INDICES: Dict[str, List[int]] = {}
for _colour in COLOUR_OPPOSITES:
    _goal_colour = COLOUR_OPPOSITES[_colour]
    _GOAL_INDICES[_colour] = [
        i for i, c in enumerate(_CELLS) if c["postype"] == _goal_colour
    ]

# Home indices for each colour (their own starting zone)
_HOME_INDICES: Dict[str, List[int]] = {}
for _colour in COLOUR_OPPOSITES:
    _HOME_INDICES[_colour] = [
        i for i, c in enumerate(_CELLS) if c["postype"] == _colour
    ]

# Pre-compute goal depth for each goal cell (hex distance to the "corner tip")
# Deeper cells (far corner) score higher — we want to fill those first.
def _goal_depth(colour: str, cell_idx: int) -> int:
    """How deep is this cell inside the goal zone? Tip of triangle = highest."""
    goal_colour = COLOUR_OPPOSITES[colour]
    if _CELLS[cell_idx]["postype"] != goal_colour:
        return 0
    # Distance from this goal cell to the nearest board cell — deeper = larger
    min_dist_to_board = 10**9
    c = _CELLS[cell_idx]
    for i, oc in enumerate(_CELLS):
        if oc["postype"] == "board":
            dq = abs(c["q"] - oc["q"])
            dr = abs(c["r"] - oc["r"])
            ds = abs((-c["q"] - c["r"]) - (-oc["q"] - oc["r"]))
            min_dist_to_board = min(min_dist_to_board, max(dq, dr, ds))
    return min_dist_to_board

_GOAL_DEPTH: Dict[str, Dict[int, int]] = {}
for _colour in COLOUR_OPPOSITES:
    _GOAL_DEPTH[_colour] = {
        i: _goal_depth(_colour, i) for i in _GOAL_INDICES[_colour]
    }

# Neighbours lookup
_NEIGHBOURS: List[List[int]] = []
for _i, _c in enumerate(_CELLS):
    _nbrs = []
    for _dq, _dr in HEX_DIRS:
        _ni = _INDEX_OF.get((_c["q"] + _dq, _c["r"] + _dr))
        if _ni is not None:
            _nbrs.append(_ni)
    _NEIGHBOURS.append(_nbrs)


def _hex_dist(a_idx: int, b_idx: int) -> int:
    a, b = _CELLS[a_idx], _CELLS[b_idx]
    dq = abs(a["q"] - b["q"])
    dr = abs(a["r"] - b["r"])
    ds = abs((-a["q"] - a["r"]) - (-b["q"] - b["r"]))
    return max(dq, dr, ds)


def _hex_dist_to_nearest_goal(cell_idx: int, goal_indices: List[int]) -> int:
    best = 10**9
    for gi in goal_indices:
        best = min(best, _hex_dist(cell_idx, gi))
    return best


# ─────────────────────────────────────────────────────────────────────────────
# BoardSnapshot
# ─────────────────────────────────────────────────────────────────────────────

class BoardSnapshot:
    __slots__ = ("pins", "occupied")

    def __init__(self, pins: Dict[str, List[int]], occupied: set):
        self.pins = pins
        self.occupied = occupied

    @staticmethod
    def from_json_state(state: dict) -> "BoardSnapshot":
        pins_raw = state.get("pins", {})
        pins = {colour: list(indices) for colour, indices in pins_raw.items()}
        occupied = set()
        for indices in pins.values():
            occupied.update(indices)
        return BoardSnapshot(pins, occupied)

    def copy(self) -> "BoardSnapshot":
        return BoardSnapshot({c: list(v) for c, v in self.pins.items()}, set(self.occupied))

    def apply_move(self, colour: str, pin_list_idx: int,
                   from_cell: int, to_cell: int) -> "BoardSnapshot":
        new_pins = {c: list(v) for c, v in self.pins.items()}
        new_occ = set(self.occupied)
        new_occ.discard(from_cell)
        new_occ.add(to_cell)
        new_pins[colour][pin_list_idx] = to_cell
        return BoardSnapshot(new_pins, new_occ)

    def legal_moves_for_colour(self, colour: str) -> List[Tuple[int, int, int]]:
        moves = []
        for pin_idx, from_cell in enumerate(self.pins.get(colour, [])):
            for to_cell in self._possible_moves(from_cell):
                moves.append((pin_idx, from_cell, to_cell))
        return moves

    def _possible_moves(self, start_idx: int) -> List[int]:
        occupied = self.occupied
        possible = set()
        for ni in _NEIGHBOURS[start_idx]:
            if ni not in occupied:
                possible.add(ni)
        visited = {start_idx}
        stack = [start_idx]
        while stack:
            cur = stack.pop()
            cq, cr = _CELLS[cur]["q"], _CELLS[cur]["r"]
            for dq, dr in HEX_DIRS:
                adj  = _INDEX_OF.get((cq + dq,      cr + dr))
                land = _INDEX_OF.get((cq + 2*dq,    cr + 2*dr))
                if adj is None or land is None:
                    continue
                if adj in occupied and land not in occupied and land not in visited:
                    possible.add(land)
                    visited.add(land)
                    stack.append(land)
        return list(possible)


# ─────────────────────────────────────────────────────────────────────────────
# Evaluation
# ─────────────────────────────────────────────────────────────────────────────

def _pins_in_goal(colour: str, board: BoardSnapshot) -> int:
    goal_colour = COLOUR_OPPOSITES[colour]
    return sum(1 for ci in board.pins.get(colour, [])
               if _CELLS[ci]["postype"] == goal_colour)

def _is_win(colour: str, board: BoardSnapshot) -> bool:
    n = len(board.pins.get(colour, []))
    return n > 0 and _pins_in_goal(colour, board) == n

def _total_distance_to_goal(colour: str, board: BoardSnapshot) -> float:
    goals = _GOAL_INDICES[colour]
    return sum(_hex_dist_to_nearest_goal(ci, goals) for ci in board.pins.get(colour, []))

def _pins_still_home(colour: str, board: BoardSnapshot) -> int:
    """Count pins still sitting in their own starting triangle."""
    home = set(_HOME_INDICES[colour])
    return sum(1 for ci in board.pins.get(colour, []) if ci in home)

def _chain_bonus(colour: str, board: BoardSnapshot) -> float:
    """
    Reward having pieces spread in a line toward the goal (hop chain).
    We measure this as: for each non-goal pin, does it have a neighbour
    that is occupied (by anyone)? A denser network of hop-over bridges
    means faster multi-hop traversal for future moves.
    """
    goal_colour = COLOUR_OPPOSITES[colour]
    occupied = board.occupied
    bonus = 0.0
    for ci in board.pins.get(colour, []):
        if _CELLS[ci]["postype"] == goal_colour:
            continue
        for ni in _NEIGHBOURS[ci]:
            if ni in occupied:
                bonus += 1.0
                break
    return bonus

def _deepest_goal_score(colour: str, board: BoardSnapshot) -> float:
    """
    Reward pins that are deep inside the goal triangle.
    Filling the tip of the triangle first is optimal (avoids blocking).
    """
    depth_map = _GOAL_DEPTH[colour]
    total = 0.0
    for ci in board.pins.get(colour, []):
        total += depth_map.get(ci, 0) * 15.0
    return total

def _evaluate(board: BoardSnapshot, my_colour: str,
              all_colours: List[str], my_move_count: int) -> float:
    """
    Multi-component evaluation. Higher = better for my_colour.

    Components:
      pin_score      : 100 per pin in goal (dominant — just win)
      depth_score    : reward deep goal cells (fill from back)
      dist_score     : get closer to goal; block opponents
      chain_bonus    : reward hop-chain formation
      home_penalty   : penalise pins still sitting in start zone
      opp_penalty    : penalise strongest opponent's progress
    """
    if _is_win(my_colour, board):
        return 100_000.0

    # Check if any opponent has won
    for c in all_colours:
        if c != my_colour and _is_win(c, board):
            return -100_000.0

    my_in_goal  = _pins_in_goal(my_colour, board)
    my_dist     = _total_distance_to_goal(my_colour, board)

    pin_score   = my_in_goal * 100.0
    depth_score = _deepest_goal_score(my_colour, board)
    dist_score  = (200.0 - my_dist) * 2.0      # mirrors server distance_score weight

    chain       = _chain_bonus(my_colour, board) * 3.0
    home_pen    = _pins_still_home(my_colour, board) * -12.0   # nudge pieces out early

    # Opponent pressure: track the BEST opponent (closest to winning)
    opp_penalty = 0.0
    for c in all_colours:
        if c == my_colour:
            continue
        opp_dist    = _total_distance_to_goal(c, board)
        opp_in_goal = _pins_in_goal(c, board)
        # Penalise us proportional to how well they're doing
        opp_penalty -= opp_in_goal * 80.0
        opp_penalty -= (200.0 - opp_dist) * 1.0

    return pin_score + depth_score + dist_score + chain + home_pen + opp_penalty


# ─────────────────────────────────────────────────────────────────────────────
# Move ordering
# ─────────────────────────────────────────────────────────────────────────────

def _move_score_for_ordering(colour: str, from_cell: int, to_cell: int) -> float:
    """Higher = try this move first in alpha-beta."""
    goal_colour = COLOUR_OPPOSITES[colour]
    goals = _GOAL_INDICES[colour]
    depth_map = _GOAL_DEPTH[colour]

    # Best: land on a deep goal cell
    if _CELLS[to_cell]["postype"] == goal_colour:
        return 2000.0 + depth_map.get(to_cell, 0) * 100.0

    # Leave home base urgently
    home = set(_HOME_INDICES[colour])
    home_bonus = 30.0 if from_cell in home else 0.0

    dist_before = _hex_dist_to_nearest_goal(from_cell, goals)
    dist_after  = _hex_dist_to_nearest_goal(to_cell,   goals)
    advance     = dist_before - dist_after

    # Hop distance proxy
    c_from, c_to = _CELLS[from_cell], _CELLS[to_cell]
    hex_travel = max(
        abs(c_from["q"] - c_to["q"]),
        abs(c_from["r"] - c_to["r"]),
        abs((-c_from["q"] - c_from["r"]) - (-c_to["q"] - c_to["r"]))
    )
    hop_bonus = 8.0 if hex_travel > 1 else 0.0

    return advance * 10.0 + hop_bonus + home_bonus


# ─────────────────────────────────────────────────────────────────────────────
# Alpha-Beta Search
# ─────────────────────────────────────────────────────────────────────────────

class _Searcher:
    def __init__(self, my_colour: str, all_colours: List[str], time_limit: float):
        self.my_colour   = my_colour
        self.all_colours = all_colours
        self.opp_colour  = COLOUR_OPPOSITES.get(my_colour, "")
        self.time_limit  = time_limit
        self.start_time  = 0.0
        self.my_move_count = 0

    def _time_left(self) -> float:
        return self.time_limit - (time.perf_counter() - self.start_time)

    def search(self, board: BoardSnapshot, my_move_count: int,
               server_legal_moves: Dict[str, List[int]]) -> Tuple[str, int]:
        self.start_time    = time.perf_counter()
        self.my_move_count = my_move_count

        # Build candidate list from server-validated legal moves
        candidates = []
        for pid_str, to_list in server_legal_moves.items():
            if not to_list:
                continue
            try:
                pin_list_idx = int(pid_str)
            except ValueError:
                pin_list_idx = 0
            my_cells = board.pins.get(self.my_colour, [])
            if pin_list_idx >= len(my_cells):
                continue
            from_cell = my_cells[pin_list_idx]
            for to_cell in to_list:
                candidates.append((pid_str, pin_list_idx, from_cell, to_cell))

        if not candidates:
            k = list(server_legal_moves.keys())[0]
            return k, server_legal_moves[k][0]

        # Sort best-first
        candidates.sort(
            key=lambda x: _move_score_for_ordering(self.my_colour, x[2], x[3]),
            reverse=True
        )

        best_move = (candidates[0][0], candidates[0][3])

        for depth in range(1, 8):
            if self._time_left() < 0.15:
                break
            result = self._root_search(board, candidates, depth)
            if result is not None:
                best_move = result
            if self._time_left() < 0.10:
                break

        return best_move

    def _root_search(self, board, candidates, depth):
        alpha, beta = -math.inf, math.inf
        best_val, best_move = -math.inf, None

        for pid_str, pin_list_idx, from_cell, to_cell in candidates:
            if self._time_left() < 0.05:
                break
            child = board.apply_move(self.my_colour, pin_list_idx, from_cell, to_cell)
            val   = self._alphabeta(child, depth - 1, alpha, beta, False)
            if val > best_val:
                best_val  = val
                best_move = (pid_str, to_cell)
            alpha = max(alpha, best_val)

        return best_move

    def _alphabeta(self, board, depth, alpha, beta, is_my_turn):
        if _is_win(self.my_colour, board):
            return 100_000.0
        for c in self.all_colours:
            if c != self.my_colour and _is_win(c, board):
                return -100_000.0

        if depth == 0 or self._time_left() < 0.02:
            return _evaluate(board, self.my_colour, self.all_colours, self.my_move_count)

        if is_my_turn:
            moves = board.legal_moves_for_colour(self.my_colour)
            if not moves:
                return _evaluate(board, self.my_colour, self.all_colours, self.my_move_count)
            moves.sort(
                key=lambda m: _move_score_for_ordering(self.my_colour, m[1], m[2]),
                reverse=True
            )
            value = -math.inf
            for pin_idx, from_cell, to_cell in moves:
                child = board.apply_move(self.my_colour, pin_idx, from_cell, to_cell)
                value = max(value, self._alphabeta(child, depth - 1, alpha, beta, False))
                alpha = max(alpha, value)
                if value >= beta:
                    break
            return value

        else:
            # Minimise against our complement opponent (most direct threat)
            moves = board.legal_moves_for_colour(self.opp_colour)
            if not moves:
                return _evaluate(board, self.my_colour, self.all_colours, self.my_move_count)
            moves.sort(
                key=lambda m: _move_score_for_ordering(self.opp_colour, m[1], m[2]),
                reverse=True
            )
            value = math.inf
            for pin_idx, from_cell, to_cell in moves:
                child = board.apply_move(self.opp_colour, pin_idx, from_cell, to_cell)
                value = min(value, self._alphabeta(child, depth - 1, alpha, beta, True))
                beta = min(beta, value)
                if value <= alpha:
                    break
            return value


# ─────────────────────────────────────────────────────────────────────────────
# Public interface — drop-in replacement for original ChineseCheckersAgent
# ─────────────────────────────────────────────────────────────────────────────

class ChineseCheckersAgent:
    """
    Drop-in replacement. Usage is identical to the original:
        agent = ChineseCheckersAgent(my_colour="red")
        pin_id, to_index = agent.choose_move(state_dict, legal_moves_dict)
    """

    # Keep well under the 10s turn timeout AND the overall game time limit.
    # A short budget means many more moves get played before the clock runs out.
    TIME_BUDGET = 0.8   # seconds per move — fast enough to survive a 60s game

    def __init__(self, my_colour: str):
        self.my_colour  = my_colour
        self.move_count = 0
        self._all_colours: List[str] = list(COLOUR_OPPOSITES.keys())
        self._searcher: Optional[_Searcher] = None
        print(f"[Agent] Colour={my_colour}  Goal={COLOUR_OPPOSITES.get(my_colour,'?')}")

    def _greedy_best(self, board: BoardSnapshot,
                     legal_moves: Dict[str, List[int]]) -> Tuple[str, int]:
        """
        O(moves) greedy pick: best move by ordering heuristic alone.
        Used as instant fallback and also seeds the search.
        """
        best_score = -10**9
        best_pid, best_to = None, None
        my_cells = board.pins.get(self.my_colour, [])
        for pid_str, to_list in legal_moves.items():
            if not to_list:
                continue
            try:
                pli = int(pid_str)
            except ValueError:
                pli = 0
            if pli >= len(my_cells):
                continue
            from_cell = my_cells[pli]
            for to_cell in to_list:
                s = _move_score_for_ordering(self.my_colour, from_cell, to_cell)
                if s > best_score:
                    best_score = s
                    best_pid, best_to = pid_str, to_cell
        return best_pid, best_to

    def choose_move(self, state: dict, legal_moves: Dict[str, List[int]]) -> Tuple[str, int]:
        # Discover which colours are actually in this game
        active = list(state.get("pins", {}).keys())
        if active:
            self._all_colours = active

        if self._searcher is None or self._searcher.all_colours != self._all_colours:
            self._searcher = _Searcher(self.my_colour, self._all_colours, self.TIME_BUDGET)

        board = BoardSnapshot.from_json_state(state)

        all_moves = [(pid, ti) for pid, tlist in legal_moves.items() for ti in tlist if tlist]
        if len(all_moves) == 1:
            self.move_count += 1
            return all_moves[0]

        # Greedy instant pick — always valid even if search times out
        greedy_pid, greedy_to = self._greedy_best(board, legal_moves)

        # Try to improve with search; if clock is very tight, skip it
        try:
            pin_id_str, to_cell = self._searcher.search(board, self.move_count, legal_moves)
        except Exception:
            pin_id_str, to_cell = greedy_pid, greedy_to

        # Fall back to greedy if search returned nothing
        if pin_id_str is None:
            pin_id_str, to_cell = greedy_pid, greedy_to

        self.move_count += 1
        print(f"[Agent] move #{self.move_count}: pin={pin_id_str} → cell={to_cell}")
        return pin_id_str, to_cell