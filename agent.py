from checkers_board import HexBoard
from checkers_pins import Pin
from mcts import MCTS


class ChineseCheckersAgent:
    def __init__(self, my_colour):
        self.board = HexBoard()
        self.my_colour = my_colour

        # All possible colours known to the board
        self.colours = list(self.board.colour_opposites.keys())

        # MCTS engine
        self.mcts = MCTS(self.board, self.colours, time_limit=1.5)

    def choose_move(self, state, legal_moves):
        """
        Decide the best move using MCTS.
        legal_moves are used only for final validation / fallback.
        """

        # ───── Reset board occupancy ─────
        for cell in self.board.cells:
            cell.occupied = False

        # ───── Rebuild pins from server state ─────
        # IMPORTANT: include ALL colours, even inactive ones
        pins_by_colour = {c: [] for c in self.colours}

        for colour, indices in state["pins"].items():
            for i, idx in enumerate(indices):
                pins_by_colour[colour].append(
                    Pin(self.board, idx, i, colour)
                )

        # ───── Run MCTS ─────
        pin_id, to_idx = self.mcts.search(
            pins_by_colour,
            self.my_colour,
            legal_moves
        )

        # ───── Absolute safety fallback (should almost never trigger) ─────
        if pin_id is None or str(pin_id) not in legal_moves or to_idx not in legal_moves[str(pin_id)]:
            for pid_str, targets in legal_moves.items():
                if targets:
                    return pid_str, targets[0]

        return str(pin_id), to_idx