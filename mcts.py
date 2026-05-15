# =========================================================
# mcts.py
# COMPLETE UPDATED FAST COMPETITION VERSION
# =========================================================

import time
import random
import math

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
    goal_blocking_penalty
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

        self.tt = {}

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

            if pins_by_colour[self.colours[i]]:
                return self.colours[i]

        return current

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
    # JUMP POTENTIAL
    # =====================================================
    def jump_potential(self, pin):

        current = pin.axialindex

        reachable = set()

        stack = [current]

        while stack:

            idx = stack.pop(-1)

            if idx in reachable:
                continue

            reachable.add(idx)

            pin.axialindex = idx

            for nxt in pin.getPossibleMoves():

                dist = move_distance(
                    self.board,
                    idx,
                    nxt
                )

                if dist >= 2:
                    stack.append(nxt)

        pin.axialindex = current

        return len(reachable)

    # =====================================================
    # MOVE SCORE
    # =====================================================
    def strategic_move_score(
        self,
        pin,
        to_idx,
        colour,
    ):

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

        mobility = len(pin.getPossibleMoves())

        center = self.center_score(to_idx)

        jump_future = self.jump_potential(pin)

        score = 0.0

        # MASSIVE JUMP REWARD
        score += jump_len * 140.0

        # forward progress
        score += progress * 45.0

        # mobility
        score += mobility * 8.0

        # center lanes
        score += center * 10.0

        # future chains
        score += jump_future * 15.0

        goal = self.board.colour_opposites[colour]

        if self.board.cells[to_idx].postype == goal:

            depth = goal_depth(
                self.board,
                to_idx
            )

            # deep fill reward
            score += depth * 120.0

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

        remaining_pieces = sum(
            len(v)
            for v in pins_by_colour.values()
        )

        # FAST adaptive thinking
        if remaining_pieces > 40:
            self.time_limit = 0.20

        elif remaining_pieces > 20:
            self.time_limit = 0.45

        else:
            self.time_limit = 0.90

        max_iters = 900

        root = MCTSNode(root_player)

        self.root = root

        end_time = time.time() + self.time_limit

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
                    key=lambda item: item[1].uct(1.8)
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

                pins = pins_by_colour[node.player]

                for pid, pin in enumerate(pins):

                    old_d = dist_to_goal(
                        self.board,
                        pin.axialindex,
                        node.player
                    )

                    for to_idx in pin.getPossibleMoves():

                        new_d = dist_to_goal(
                            self.board,
                            to_idx,
                            node.player
                        )

                        progress = old_d - new_d

                        # prune terrible backward moves
                        if progress < -1:
                            continue

                        score = (
                            self.strategic_move_score(
                                pin,
                                to_idx,
                                node.player
                            )
                        )

                        node.untried_moves.append(
                            (
                                score,
                                pid,
                                to_idx
                            )
                        )

                random.shuffle(node.untried_moves)

                node.untried_moves.sort(
                    reverse=True,
                    key=lambda x: x[0]
                )

                # progressive widening
                node.untried_moves = (
                    node.untried_moves[:10]
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

                result = self.tt[state_hash]

            else:

                result = rollout(
                    self.board,
                    pins_by_colour,
                    root_player,
                    self.colours
                )

                self.tt[state_hash] = result

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

            for pid_str, targets in legal_moves.items():

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
            key=lambda item: item[1].visits
        )

        return pid, to_idx