# =========================================================
# rollout.py
# COMPLETE UPDATED FAST COMPETITION VERSION
# =========================================================

import random
import math

from mcts_utils import (
    apply_move,
    undo_move,
    has_won,
)

# =====================================================
# GOAL DEPTH
# =====================================================
def goal_depth(board, idx):

    cell = board.cells[idx]

    colour = cell.postype

    q = cell.q
    r = cell.r

    if colour == "blue":
        return -r

    elif colour == "red":
        return r

    elif colour == "yellow":
        return -q

    elif colour == "purple":
        return q

    elif colour == "lawn green":
        return q - r

    elif colour == "gray0":
        return r - q

    return 0


# =====================================================
# BLOCKING PENALTY
# =====================================================
def goal_blocking_penalty(
    board,
    pins,
    colour
):

    goal = board.colour_opposites[colour]

    penalty = 0

    occupied = set(
        p.axialindex
        for p in pins
    )

    for idx in occupied:

        cell = board.cells[idx]

        if cell.postype != goal:
            continue

        depth = goal_depth(
            board,
            idx
        )

        # shallow entrance blocks
        if depth <= 8:

            behind_empty = False

            for other in board.axial_of_colour(goal):

                if other in occupied:
                    continue

                other_depth = goal_depth(
                    board,
                    other
                )

                if other_depth > depth:
                    behind_empty = True
                    break

            if behind_empty:
                penalty += 250

    return penalty


# =====================================================
# HEX DISTANCE
# =====================================================
def move_distance(
    board,
    a_idx,
    b_idx
):

    a = board.cells[a_idx]
    b = board.cells[b_idx]

    aq, ar = a.q, a.r
    as_ = -aq - ar

    bq, br = b.q, b.r
    bs = -bq - br

    return max(
        abs(aq - bq),
        abs(ar - br),
        abs(as_ - bs)
    )


# =====================================================
# DISTANCE TO GOAL
# =====================================================
def dist_to_goal(
    board,
    idx,
    colour
):

    opposite = board.colour_opposites[colour]

    targets = board.axial_of_colour(opposite)

    cq = board.cells[idx].q
    cr = board.cells[idx].r
    cs = -cq - cr

    best = float("inf")

    for tidx in targets:

        tgt = board.cells[tidx]

        tq, tr = tgt.q, tgt.r
        ts = -tq - tr

        d = max(
            abs(cq - tq),
            abs(cr - tr),
            abs(cs - ts)
        )

        best = min(best, d)

    return best


# =====================================================
# SOFTMAX PICK
# =====================================================
def softmax_pick(
    moves,
    temperature=0.35
):

    scores = [m[0] for m in moves]

    mx = max(scores)

    weights = [
        math.exp((s - mx) / temperature)
        for s in scores
    ]

    total = sum(weights)

    r = random.random() * total

    upto = 0

    for w, move in zip(weights, moves):

        upto += w

        if upto >= r:
            return move

    return moves[0]


# =====================================================
# ROLLOUT MOVE SCORE
# =====================================================
def rollout_move_score(
    board,
    pin,
    to_idx,
    colour,
):

    old_d = dist_to_goal(
        board,
        pin.axialindex,
        colour
    )

    new_d = dist_to_goal(
        board,
        to_idx,
        colour
    )

    progress = old_d - new_d

    jump_len = move_distance(
        board,
        pin.axialindex,
        to_idx
    )

    score = 0.0

    # VERY aggressive jumps
    score += jump_len * 120.0

    # forward progress
    score += progress * 45.0

    goal = board.colour_opposites[colour]

    if board.cells[to_idx].postype == goal:

        depth = goal_depth(
            board,
            to_idx
        )

        # deep fill first
        score += depth * 100.0

    return score


# =====================================================
# ROLLOUT
# =====================================================
def rollout(
    board,
    pins_by_colour,
    start_player,
    colours
):

    history = []

    player = start_player

    # FAST rollout
    max_depth = 30

    for _ in range(max_depth):

        pins = pins_by_colour[player]

        moves = []

        for pin in pins:

            for to_idx in pin.getPossibleMoves():

                score = rollout_move_score(
                    board,
                    pin,
                    to_idx,
                    player
                )

                moves.append(
                    (
                        score,
                        pin,
                        to_idx
                    )
                )

        if not moves:
            break

        _, pin, to_idx = softmax_pick(moves)

        rec = apply_move(
            pin,
            to_idx
        )

        history.append(rec)

        if has_won(
            board,
            pins,
            player
        ):
            break

        # next player
        i = colours.index(player)

        for _ in colours:

            i = (i + 1) % len(colours)

            if pins_by_colour[colours[i]]:
                player = colours[i]
                break

    # =====================================================
    # FINAL EVALUATION
    # =====================================================
    score = 0.0

    for colour, pins in pins_by_colour.items():

        mult = (
            1.0
            if colour == start_player
            else -0.7
        )

        for pin in pins:

            d = dist_to_goal(
                board,
                pin.axialindex,
                colour
            )

            score += mult * (-d * 20)

            if (
                board.cells[
                    pin.axialindex
                ].postype
                ==
                board.colour_opposites[colour]
            ):
                score += mult * 250

    # anti self-blocking
    score -= goal_blocking_penalty(
        board,
        pins_by_colour[start_player],
        start_player
    )

    # win bonus
    if has_won(
        board,
        pins_by_colour[start_player],
        start_player
    ):
        score += 50000

    # undo rollout
    for rec in reversed(history):
        undo_move(rec)

    return score