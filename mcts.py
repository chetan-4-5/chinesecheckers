# mcts.py

import time
import random
import math

from mcts_node import MCTSNode
from mcts_utils import apply_move, undo_move
from rollout import (
    rollout,
    dist_to_goal,
    goal_depth,
    move_distance,
)


class MCTS:

    def __init__(self, board, colours, time_limit=3.0):

        self.board = board
        self.colours = colours
        self.time_limit = time_limit

        self.root = None

    # ─────────────────────────────────────────────
    # Next active player
    # ─────────────────────────────────────────────
    def next_player(self, current, pins_by_colour):

        i = self.colours.index(current)

        for _ in self.colours:

            i = (i + 1) % len(self.colours)

            if pins_by_colour[self.colours[i]]:
                return self.colours[i]

        return current

    # ─────────────────────────────────────────────
    # Rear-most priority
    # Humans move stranded marbles first
    # ─────────────────────────────────────────────
    def rear_priority(self, idx, colour):

        return dist_to_goal(
            self.board,
            idx,
            colour
        )

    # ─────────────────────────────────────────────
    # Human strategic move score
    # ─────────────────────────────────────────────
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

        rear_score = self.rear_priority(
            from_idx,
            colour
        )

        mobility = len(pin.getPossibleMoves())

        score = 0.0

        # HUGE jump preference
        score += jump_len * 50.0

        # rear marbles first
        score += rear_score * 15.0

        # forward progress
        score += progress * 20.0

        # mobility matters
        score += mobility * 5.0

        goal = self.board.colour_opposites[colour]

        # target triangle reward
        if self.board.cells[to_idx].postype == goal:

            score += 80.0

            score += (
                goal_depth(
                    self.board,
                    to_idx
                ) * 40.0
            )

        return score

    # ─────────────────────────────────────────────
    # Search
    # ─────────────────────────────────────────────
    def search(
        self,
        pins_by_colour,
        root_player,
        legal_moves
    ):

        max_iters = 4000

        iterations = 0

        root = MCTSNode(root_player)

        self.root = root

        end_time = time.time() + self.time_limit

        # ─────────────────────────────────────────
        # MAIN LOOP
        # ─────────────────────────────────────────
        while (
            time.time() < end_time
            and iterations < max_iters
        ):

            iterations += 1

            node = root

            history = []

            # ─────────────────────────────────────
            # SELECTION
            # ─────────────────────────────────────
            while (
                node.children
                and node.untried_moves == []
            ):

                node = max(
                    node.children.values(),
                    key=lambda n: n.uct()
                )

            # ─────────────────────────────────────
            # EXPANSION
            # ─────────────────────────────────────
            if node.untried_moves is None:

                node.untried_moves = []

                pins = pins_by_colour[node.player]

                remaining = sum(
                    len(v)
                    for v in pins_by_colour.values()
                )

                for pid, pin in enumerate(pins):

                    cell = self.board.cells[
                        pin.axialindex
                    ]

                    old_d = dist_to_goal(
                        self.board,
                        pin.axialindex,
                        node.player
                    )

                    for to_idx in pin.getPossibleMoves():

                        new_cell = self.board.cells[
                            to_idx
                        ]

                        # ─────────────────
                        # prevent useless
                        # goal drifting
                        # ─────────────────
                        goal = self.board.colour_opposites[
                            node.player
                        ]

                        if (
                            cell.postype == goal
                            and new_cell.postype == goal
                        ):

                            old_depth = goal_depth(
                                self.board,
                                pin.axialindex
                            )

                            new_depth = goal_depth(
                                self.board,
                                to_idx
                            )

                            # only deeper moves
                            if new_depth <= old_depth:
                                continue

                        new_d = dist_to_goal(
                            self.board,
                            to_idx,
                            node.player
                        )

                        progress = old_d - new_d

                        allow = False

                        # forward / neutral
                        if progress >= 0:
                            allow = True

                        # controlled backward
                        elif (
                            remaining <= 10
                            and progress >= -1
                        ):
                            allow = True

                        if allow:

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
                                    pin,
                                    to_idx
                                )
                            )

                random.shuffle(node.untried_moves)

                node.untried_moves.sort(
                    reverse=True,
                    key=lambda x: x[0]
                )

            # dead-end
            if (
                not node.untried_moves
                and not node.children
            ):
                break

            # ─────────────────────────────────────
            # EXPAND
            # ─────────────────────────────────────
            if node.untried_moves:

                (
                    _,
                    pid,
                    pin,
                    to_idx
                ) = node.untried_moves.pop(0)

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

            # ─────────────────────────────────────
            # SIMULATION
            # ─────────────────────────────────────
            result = rollout(
                self.board,
                pins_by_colour,
                root_player,
                self.colours
            )

            # ─────────────────────────────────────
            # UNDO
            # ─────────────────────────────────────
            for rec in reversed(history):
                undo_move(rec)

            # ─────────────────────────────────────
            # BACKPROP
            # ─────────────────────────────────────
            while node:

                node.visits += 1

                node.value += result

                node = node.parent

        # ─────────────────────────────────────────
        # FINAL MOVE
        # ─────────────────────────────────────────
        if not root.children:

            for pid_str, targets in legal_moves.items():

                if targets:
                    return (
                        int(pid_str),
                        targets[0]
                    )

            return None, None

        (
            pid,
            to_idx
        ), best_child = max(
            root.children.items(),
            key=lambda item: item[1].visits
        )

        # safety validation
        if (
            str(pid) not in legal_moves
            or to_idx not in legal_moves[str(pid)]
        ):

            for pid_str, targets in legal_moves.items():

                if targets:
                    return (
                        int(pid_str),
                        targets[0]
                    )

        self.root = best_child
        self.root.parent = None

        return pid, to_idx