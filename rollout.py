# =========================================================
# rollout.py
# ULTIMATE DIRECTIONAL VERSION
# - Directional Alignment
# - Goal-Oriented Multi Jumping
# - Dynamic Weights
# - Beam Rollouts
# - Locked Goal Pieces
# - Dependency Endgame
# =========================================================

import random
import math
from collections import deque

from mcts_utils import (
    apply_move,
    undo_move,
    has_won,
)

# =====================================================
# MOVE CACHE
# =====================================================
MOVE_CACHE = {}

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
# BUILD GOAL DEPENDENCY MAP
# =====================================================
def build_goal_dependency_map(board):

    deps = {}

    all_goals = set(
        board.colour_opposites.values()
    )

    for colour in all_goals:

        goal_cells = board.axial_of_colour(
            colour
        )

        goal_cells.sort(
            key=lambda idx:
            goal_depth(board, idx),
            reverse=True
        )

        deps[colour] = {}

        for idx in goal_cells:

            deps[colour][idx] = []

            d = goal_depth(
                board,
                idx
            )

            for other in goal_cells:

                od = goal_depth(
                    board,
                    other
                )

                if od > d:

                    deps[colour][idx].append(
                        other
                    )

    return deps


# =====================================================
# DISTANCE TO GOAL
# =====================================================
def dist_to_goal(
    board,
    idx,
    colour
):

    opposite = board.colour_opposites[
        colour
    ]

    targets = board.axial_of_colour(
        opposite
    )

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
# DIRECTIONAL PROGRESS
# =====================================================
def directional_progress(
    board,
    from_idx,
    to_idx,
    colour
):

    old_d = dist_to_goal(
        board,
        from_idx,
        colour
    )

    new_d = dist_to_goal(
        board,
        to_idx,
        colour
    )

    return old_d - new_d


# =====================================================
# TARGET CENTER
# =====================================================
def goal_center(
    board,
    colour
):

    goal = board.colour_opposites[
        colour
    ]

    cells = board.axial_of_colour(
        goal
    )

    qsum = 0
    rsum = 0

    for idx in cells:

        c = board.cells[idx]

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
    board,
    from_idx,
    to_idx,
    colour
):

    from_cell = board.cells[
        from_idx
    ]

    to_cell = board.cells[
        to_idx
    ]

    tq, tr = goal_center(
        board,
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
# CACHED MOVES
# =====================================================
def cached_moves(
    board,
    pin
):

    state_key = (
        pin.axialindex,
        tuple(
            c.occupied
            for c in board.cells
        )
    )

    if state_key in MOVE_CACHE:
        return MOVE_CACHE[state_key]

    moves = pin.getPossibleMoves()

    MOVE_CACHE[state_key] = moves

    return moves


# =====================================================
# GOAL FILL VALIDATION
# =====================================================
def goal_fill_allowed(
    board,
    pins,
    colour,
    idx,
    deps
):

    goal = board.colour_opposites[
        colour
    ]

    if (
        board.cells[idx].postype
        != goal
    ):
        return True

    occupied = set(
        p.axialindex
        for p in pins
    )

    for parent in deps[goal][idx]:

        if parent not in occupied:
            return False

    return True


# =====================================================
# UPWARD GOAL MOVE
# =====================================================
def has_upward_goal_move(
    board,
    pin,
    colour
):

    current_depth = goal_depth(
        board,
        pin.axialindex
    )

    goal = board.colour_opposites[
        colour
    ]

    for nxt in cached_moves(
        board,
        pin
    ):

        if (
            board.cells[nxt].postype
            != goal
        ):
            continue

        nd = goal_depth(
            board,
            nxt
        )

        if nd > current_depth:
            return True

    return False


# =====================================================
# LOCKED PIN CHECK
# =====================================================
def pin_is_locked(
    board,
    pin,
    pins,
    colour,
    deps
):

    idx = pin.axialindex

    goal = board.colour_opposites[
        colour
    ]

    if (
        board.cells[idx].postype
        != goal
    ):
        return False

    occupied = set(
        p.axialindex
        for p in pins
    )

    for parent in deps[goal][idx]:

        if parent not in occupied:
            return False

    if has_upward_goal_move(
        board,
        pin,
        colour
    ):
        return False

    return True


# =====================================================
# GAME PHASE
# =====================================================
def game_phase(
    board,
    pins_by_colour,
    colour
):

    pins = pins_by_colour[colour]

    goal = board.colour_opposites[
        colour
    ]

    in_goal = sum(
        1
        for p in pins
        if (
            board.cells[
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
# FUTURE JUMP POTENTIAL
# =====================================================
def jump_potential(
    board,
    pin
):

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

        for nxt in cached_moves(
            board,
            pin
        ):

            dist = move_distance(
                board,
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
# SOFTMAX PICK
# =====================================================
def softmax_pick(
    moves,
    temperature=0.35
):

    scores = [m[0] for m in moves]

    mx = max(scores)

    weights = [
        math.exp(
            (s - mx)
            / temperature
        )
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
    deps,
    pins_by_colour
):

    phase = game_phase(
        board,
        pins_by_colour,
        colour
    )

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

    alignment = directional_alignment(
        board,
        pin.axialindex,
        to_idx,
        colour
    )

    jump_future = jump_potential(
        board,
        pin
    )

    # =================================================
    # DIRECTIONAL EFFECTIVE JUMP
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

        jump_w = 110
        prog_w = 35
        future_w = 25

    elif phase == "midgame":

        jump_w = 170
        prog_w = 55
        future_w = 35

    else:

        jump_w = 70
        prog_w = 80
        future_w = 10

    score = 0.0

    score += effective_jump * jump_w

    score += progress * prog_w

    score += jump_future * future_w

    # backward punishment
    if progress < 0:
        score += progress * 200

    goal = board.colour_opposites[
        colour
    ]

    # =================================================
    # GOAL TRIANGLE
    # =================================================
    if (
        board.cells[to_idx].postype
        == goal
    ):

        depth = goal_depth(
            board,
            to_idx
        )

        score += depth * 100.0

        if not goal_fill_allowed(
            board,
            pins_by_colour[colour],
            colour,
            to_idx,
            deps
        ):

            score -= 200

    return score


# =====================================================
# GOAL BLOCKING PENALTY
# =====================================================
def goal_blocking_penalty(
    board,
    pins,
    colour
):

    goal = board.colour_opposites[
        colour
    ]

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

    deps = build_goal_dependency_map(
        board
    )

    max_depth = 30

    for _ in range(max_depth):

        pins = pins_by_colour[player]

        candidate_moves = []

        for pin in pins:

            if pin_is_locked(
                board,
                pin,
                pins,
                player,
                deps
            ):
                continue

            for to_idx in cached_moves(
                board,
                pin
            ):

                score = rollout_move_score(
                    board,
                    pin,
                    to_idx,
                    player,
                    deps,
                    pins_by_colour
                )

                candidate_moves.append(
                    (
                        score,
                        pin,
                        to_idx
                    )
                )

        if not candidate_moves:
            break

        # beam pruning
        candidate_moves.sort(
            reverse=True,
            key=lambda x: x[0]
        )

        candidate_moves = (
            candidate_moves[:8]
        )

        _, pin, to_idx = (
            softmax_pick(
                candidate_moves
            )
        )

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

            i = (
                i + 1
            ) % len(colours)

            if pins_by_colour[
                colours[i]
            ]:

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

            score += mult * (
                -d * 20
            )

            if (
                board.cells[
                    pin.axialindex
                ].postype
                ==
                board.colour_opposites[
                    colour
                ]
            ):

                score += mult * 250

    score -= goal_blocking_penalty(
        board,
        pins_by_colour[start_player],
        start_player
    )

    if has_won(
        board,
        pins_by_colour[start_player],
        start_player
    ):

        score += 50000

    # undo
    for rec in reversed(history):
        undo_move(rec)

    return score