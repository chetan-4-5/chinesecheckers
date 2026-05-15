# rollout.py

import random

from mcts_utils import (
    apply_move,
    undo_move,
    has_won,
)


# ─────────────────────────────────────────────
# Goal depth
# ─────────────────────────────────────────────
def goal_depth(board, idx):

    cell = board.cells[idx]

    return (
        abs(cell.q)
        + abs(cell.r)
        + abs(-cell.q - cell.r)
    )


# ─────────────────────────────────────────────
# Hex distance
# ─────────────────────────────────────────────
def move_distance(board, a_idx, b_idx):

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


# ─────────────────────────────────────────────
# Distance to target triangle
# ─────────────────────────────────────────────
def dist_to_goal(board, idx, colour):

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


# ─────────────────────────────────────────────
# Human rollout heuristic
# ─────────────────────────────────────────────
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

    mobility = len(pin.getPossibleMoves())

    score = 0.0

    # prioritize jump chains
    score += jump_len * 50.0

    # prioritize progress
    score += progress * 20.0

    # mobility
    score += mobility * 4.0

    goal = board.colour_opposites[colour]

    if board.cells[to_idx].postype == goal:

        score += 70.0

        score += (
            goal_depth(
                board,
                to_idx
            ) * 40.0
        )

    return score


# ─────────────────────────────────────────────
# Rollout simulation
# ─────────────────────────────────────────────
def rollout(
    board,
    pins_by_colour,
    start_player,
    colours
):

    history = []

    player = start_player

    remaining = sum(
        len(v)
        for v in pins_by_colour.values()
    )

    max_depth = 80 if remaining > 20 else 150

    for _ in range(max_depth):

        pins = pins_by_colour[player]

        if not pins:
            break

        moves = []

        last_rec = (
            history[-1]
            if history
            else None
        )

        for pin in pins:

            cell = board.cells[
                pin.axialindex
            ]

            old_d = dist_to_goal(
                board,
                pin.axialindex,
                player
            )

            for to_idx in pin.getPossibleMoves():

                # anti-oscillation
                if last_rec:

                    if (
                        last_rec.pin == pin
                        and last_rec.from_idx == to_idx
                    ):
                        continue

                new_cell = board.cells[to_idx]

                goal = board.colour_opposites[
                    player
                ]

                # no useless goal wandering
                if (
                    cell.postype == goal
                    and new_cell.postype == goal
                ):

                    old_depth = goal_depth(
                        board,
                        pin.axialindex
                    )

                    new_depth = goal_depth(
                        board,
                        to_idx
                    )

                    if new_depth <= old_depth:
                        continue

                new_d = dist_to_goal(
                    board,
                    to_idx,
                    player
                )

                progress = old_d - new_d

                allow = False

                if progress >= 0:
                    allow = True

                elif (
                    remaining <= 10
                    and progress >= -1
                ):
                    allow = True

                if allow:

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

        moves.sort(
            reverse=True,
            key=lambda x: x[0]
        )

        # weighted strategic selection
        top = moves[:5]

        _, pin, to_idx = random.choice(top)

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

    # ─────────────────────────────────────────
    # FINAL EVALUATION
    # ─────────────────────────────────────────
    root = start_player

    goal = board.colour_opposites[root]

    score = 0.0

    home = board.axial_of_colour(root)

    worst_piece = 0.0

    congestion = 0.0

    for pin in pins_by_colour[root]:

        idx = pin.axialindex

        d = dist_to_goal(
            board,
            idx,
            root
        )

        worst_piece = max(
            worst_piece,
            d
        )

        score -= d * 10.0

        score += (
            len(pin.getPossibleMoves())
            * 5.0
        )

        cell = board.cells[idx]

        # target triangle
        if cell.postype == goal:

            score += 100.0

            score += (
                goal_depth(
                    board,
                    idx
                ) * 50.0
            )

        # still in home
        if idx in home:
            score -= 80.0

        # congestion penalty
        if len(pin.getPossibleMoves()) <= 1:
            congestion += 20.0

    # punish stranded marbles
    score -= worst_piece * 40.0

    score -= congestion

    # winning bonus
    if has_won(
        board,
        pins_by_colour[root],
        root
    ):
        score += 10000.0

    # undo rollout
    for rec in reversed(history):
        undo_move(rec)

    return score