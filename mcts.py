# =========================================================
# mcts.py
# ULTIMATE DIRECTIONAL VERSION
# - Directional Alignment
# - Forward Chain Optimization
# - Beam Search
# - Dynamic Weights
# - Endgame Solver
# - Move Cache
# =========================================================

import time
import random
import math
from collections import deque

from mcts_node import MCTSNode

from mcts_utils import (
    apply_move,
    undo_move,
    has_won,
    hash_position
)

from rollout import (
    rollout,
    dist_to_goal,
    goal_depth,
    move_distance,
    build_goal_dependency_map,
    goal_fill_allowed,
    goal_blocking_penalty,
    pin_is_locked
)


class MCTS:

    def __init__(
        self,
        board,
        colours,
        time_limit=0.4
    ):

        self.board = board
        self.colours = colours
        self.time_limit = time_limit

        self.root = None

        # =================================================
        # TRANSPOSITION TABLE
        # =================================================
        self.tt = {}

        # =================================================
        # MOVE CACHE
        # =================================================
        self.move_cache = {}

        # =================================================
        # GOAL DEPENDENCIES
        # =================================================
        self.goal_deps = (
            build_goal_dependency_map(
                self.board
            )
        )

        self.pins_by_colour = None

    # =====================================================
    # NEXT PLAYER
    # =====================================================
    def next_player(
        self,
        current,
        pins_by_colour
    ):

        i = self.colours.index(current)

        for _ in self.colours:

            i = (i + 1) % len(self.colours)

            if pins_by_colour[
                self.colours[i]
            ]:
                return self.colours[i]

        return current

    # =====================================================
    # GAME PHASE
    # =====================================================
    def game_phase(
        self,
        colour
    ):

        pins = self.pins_by_colour[colour]

        goal = self.board.colour_opposites[
            colour
        ]

        in_goal = sum(
            1
            for p in pins
            if (
                self.board.cells[
                    p.axialindex
                ].postype
                == goal
            )
        )

        if in_goal <= 2:
            return "opening"

        elif in_goal <= 7:
            return "midgame"

        return "endgame"

    # =====================================================
    # CENTER SCORE
    # =====================================================
    def center_score(self, idx):

        cell = self.board.cells[idx]

        q = cell.q
        r = cell.r
        s = -q - r

        return -max(
            abs(q),
            abs(r),
            abs(s)
        )

    # =====================================================
    # CACHED MOVES
    # =====================================================
    def cached_moves(self, pin):

        state_key = (
            pin.axialindex,
            tuple(
                c.occupied
                for c in self.board.cells
            )
        )

        if state_key in self.move_cache:
            return self.move_cache[state_key]

        moves = pin.getPossibleMoves()

        self.move_cache[state_key] = moves

        return moves

    # =====================================================
    # DIRECTIONAL PROGRESS
    # =====================================================
    def directional_progress(
        self,
        from_idx,
        to_idx,
        colour
    ):

        old_d = dist_to_goal(
            self.board,
            from_idx,
            colour
        )

        new_d = dist_to_goal(
            self.board,
            to_idx,
            colour
        )

        return old_d - new_d

    # =====================================================
    # TARGET CENTER
    # =====================================================
    def goal_center(
        self,
        colour
    ):

        goal = self.board.colour_opposites[
            colour
        ]

        cells = self.board.axial_of_colour(
            goal
        )

        qsum = 0
        rsum = 0

        for idx in cells:

            c = self.board.cells[idx]

            qsum += c.q
            rsum += c.r

        n = len(cells)

        return (
            qsum / n,
            rsum / n
        )

    # =====================================================
    # DIRECTIONAL ALIGNMENT
    # =====================================================
    def directional_alignment(
        self,
        from_idx,
        to_idx,
        colour
    ):

        from_cell = self.board.cells[
            from_idx
        ]

        to_cell = self.board.cells[
            to_idx
        ]

        tq, tr = self.goal_center(
            colour
        )

        # move vector
        mv_q = to_cell.q - from_cell.q
        mv_r = to_cell.r - from_cell.r

        # target vector
        tv_q = tq - from_cell.q
        tv_r = tr - from_cell.r

        move_mag = math.sqrt(
            mv_q * mv_q +
            mv_r * mv_r
        )

        target_mag = math.sqrt(
            tv_q * tv_q +
            tv_r * tv_r
        )

        if move_mag == 0:
            return 0.0

        if target_mag == 0:
            return 1.0

        dot = (
            mv_q * tv_q +
            mv_r * tv_r
        )

        cosine = dot / (
            move_mag *
            target_mag
        )

        return max(0.0, cosine)

    # =====================================================
    # FUTURE JUMP POTENTIAL
    # =====================================================
    def jump_potential(self, pin):

        current = pin.axialindex

        reachable = set()

        stack = deque()

        stack.append(
            (current, 0)
        )

        best_depth = 0

        while stack:

            idx, depth = stack.pop()

            if idx in reachable:
                continue

            reachable.add(idx)

            best_depth = max(
                best_depth,
                depth
            )

            pin.axialindex = idx

            for nxt in self.cached_moves(pin):

                dist = move_distance(
                    self.board,
                    idx,
                    nxt
                )

                if dist >= 2:

                    stack.append(
                        (
                            nxt,
                            depth + 1
                        )
                    )

        pin.axialindex = current

        return (
            len(reachable)
            + best_depth * 3
        )

    # =====================================================
    # ENDGAME SOLVER
    # =====================================================
    def endgame_move(
        self,
        colour
    ):

        pins = self.pins_by_colour[colour]

        outside = []

        goal = self.board.colour_opposites[
            colour
        ]

        for pin in pins:

            if (
                self.board.cells[
                    pin.axialindex
                ].postype
                != goal
            ):
                outside.append(pin)

        if len(outside) > 3:
            return None

        best = None
        best_score = -1e9

        for pin in pins:

            if pin_is_locked(
                self.board,
                pin,
                pins,
                colour,
                self.goal_deps
            ):
                continue

            for to_idx in self.cached_moves(pin):

                score = (
                    self.strategic_move_score(
                        pin,
                        to_idx,
                        colour
                    )
                )

                if score > best_score:

                    best_score = score

                    best = (
                        pin.id,
                        to_idx
                    )

        return best

    # =====================================================
    # MOVE SCORE
    # =====================================================
    def strategic_move_score(
        self,
        pin,
        to_idx,
        colour,
    ):

        phase = self.game_phase(
            colour
        )

        from_idx = pin.axialindex

        old_d = dist_to_goal(
            self.board,
            from_idx,
            colour
        )

        new_d = dist_to_goal(
            self.board,
            to_idx,
            colour
        )

        progress = old_d - new_d

        jump_len = move_distance(
            self.board,
            from_idx,
            to_idx
        )

        alignment = self.directional_alignment(
            from_idx,
            to_idx,
            colour
        )

        mobility = len(
            self.cached_moves(pin)
        )

        center = self.center_score(
            to_idx
        )

        jump_future = self.jump_potential(
            pin
        )

        # =================================================
        # DIRECTIONAL JUMP VALUE
        # =================================================
        effective_jump = (
            jump_len *
            max(0.2, progress) *
            (0.5 + alignment)
        )

        # =================================================
        # DYNAMIC WEIGHTS
        # =================================================
        if phase == "opening":

            jump_w = 120
            prog_w = 35
            center_w = 25
            future_w = 20

        elif phase == "midgame":

            jump_w = 170
            prog_w = 55
            center_w = 10
            future_w = 30

        else:

            jump_w = 80
            prog_w = 80
            center_w = 0
            future_w = 10

        score = 0.0

        # =================================================
        # DYNAMIC SCORING
        # =================================================
        score += effective_jump * jump_w

        score += progress * prog_w

        score += mobility * 8.0

        score += center * center_w

        score += jump_future * future_w

        # =================================================
        # BACKWARD PUNISHMENT
        # =================================================
        if progress < 0:
            score += progress * 200

        goal = self.board.colour_opposites[
            colour
        ]

        # =================================================
        # GOAL TRIANGLE
        # =================================================
        if (
            self.board.cells[to_idx].postype
            == goal
        ):

            depth = goal_depth(
                self.board,
                to_idx
            )

            score += depth * 120.0

            if not goal_fill_allowed(
                self.board,
                self.pins_by_colour[colour],
                colour,
                to_idx,
                self.goal_deps
            ):

                score -= 200

        return score

    # =====================================================
    # SEARCH
    # =====================================================
    def search(
        self,
        pins_by_colour,
        root_player,
        legal_moves
    ):

        self.pins_by_colour = (
            pins_by_colour
        )

        # =================================================
        # ENDGAME SOLVER
        # =================================================
        endgame = self.endgame_move(
            root_player
        )

        if endgame is not None:
            return endgame

        remaining_pieces = sum(
            len(v)
            for v in pins_by_colour.values()
        )

        # =================================================
        # ADAPTIVE TIME
        # =================================================
        if remaining_pieces > 40:
            self.time_limit = 0.20

        elif remaining_pieces > 20:
            self.time_limit = 0.45

        else:
            self.time_limit = 0.90

        max_iters = 900

        root = MCTSNode(root_player)

        self.root = root

        end_time = (
            time.time()
            + self.time_limit
        )

        iterations = 0

        while (
            time.time() < end_time
            and iterations < max_iters
        ):

            iterations += 1

            node = root

            history = []

            # =================================================
            # SELECTION
            # =================================================
            while (
                node.children
                and node.untried_moves == []
            ):

                move, next_node = max(
                    node.children.items(),
                    key=lambda item:
                    item[1].uct(1.8)
                )

                pid, to_idx = move

                pin = pins_by_colour[
                    node.player
                ][pid]

                rec = apply_move(
                    pin,
                    to_idx
                )

                history.append(rec)

                node = next_node

            # =================================================
            # EXPANSION
            # =================================================
            if node.untried_moves is None:

                node.untried_moves = []

                pins = pins_by_colour[
                    node.player
                ]

                candidate_moves = []

                for pid, pin in enumerate(pins):

                    if pin_is_locked(
                        self.board,
                        pin,
                        pins,
                        node.player,
                        self.goal_deps
                    ):
                        continue

                    old_d = dist_to_goal(
                        self.board,
                        pin.axialindex,
                        node.player
                    )

                    for to_idx in (
                        self.cached_moves(pin)
                    ):

                        new_d = dist_to_goal(
                            self.board,
                            to_idx,
                            node.player
                        )

                        progress = (
                            old_d - new_d
                        )

                        # strongly prune backwards
                        if progress < -1:
                            continue

                        score = (
                            self
                            .strategic_move_score(
                                pin,
                                to_idx,
                                node.player
                            )
                        )

                        candidate_moves.append(
                            (
                                score,
                                pid,
                                to_idx
                            )
                        )

                # =================================================
                # BEAM SEARCH
                # =================================================
                candidate_moves.sort(
                    reverse=True,
                    key=lambda x: x[0]
                )

                node.untried_moves = (
                    candidate_moves[:8]
                )

            # =================================================
            # EXPAND
            # =================================================
            if node.untried_moves:

                (
                    _,
                    pid,
                    to_idx
                ) = node.untried_moves.pop(0)

                pin = pins_by_colour[
                    node.player
                ][pid]

                rec = apply_move(
                    pin,
                    to_idx
                )

                history.append(rec)

                next_p = self.next_player(
                    node.player,
                    pins_by_colour
                )

                child = MCTSNode(
                    next_p,
                    node
                )

                node.children[
                    (pid, to_idx)
                ] = child

                node = child

            # =================================================
            # TRANSPOSITION TABLE
            # =================================================
            state_hash = hash_position(
                pins_by_colour
            )

            if state_hash in self.tt:

                result = self.tt[
                    state_hash
                ]

            else:

                result = rollout(
                    self.board,
                    pins_by_colour,
                    root_player,
                    self.colours
                )

                self.tt[
                    state_hash
                ] = result

            # =================================================
            # UNDO
            # =================================================
            for rec in reversed(history):
                undo_move(rec)

            # =================================================
            # BACKPROP
            # =================================================
            while node:

                node.visits += 1

                node.value += result

                node = node.parent

        # =====================================================
        # FALLBACK
        # =====================================================
        if not root.children:

            for (
                pid_str,
                targets
            ) in legal_moves.items():

                if targets:

                    return (
                        int(pid_str),
                        targets[0]
                    )

            return None, None

        # =====================================================
        # BEST MOVE
        # =====================================================
        (
            pid,
            to_idx
        ), best_child = max(
            root.children.items(),
            key=lambda item:
            item[1].visits
        )

        return pid, to_idx