import math
from collections import defaultdict

class MCTSNode:
    def __init__(self, player, parent=None):
        self.player = player
        self.parent = parent
        self.children = {}              # (pid, to_idx) -> child
        self.untried_moves = None       # list of (pid, pin, to_idx)
        self.visits = 0
        self.value = 0.0                # scalar value (root player's reward)

    def uct(self, c=1.4):
        # Unvisited nodes are always explored first
        if self.visits == 0:
            return float("inf")

        # Root has no parent → no exploration term
        if self.parent is None or self.parent.visits == 0:
            return self.value / self.visits

        return (
            self.value / self.visits +
            c * math.sqrt(math.log(self.parent.visits) / self.visits)
        )