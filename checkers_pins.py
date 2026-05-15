from checkers_board import BoardPosition, HexBoard

class Pin:
    """Represents a pin placed on the board by index."""
    def __init__(self, board: HexBoard, axialindex: int, id: int, color="red"):
        self.board = board
        self.axialindex = axialindex
        self.color = color
        self.id = id
        self.board.cells[axialindex].occupied = True

    @property
    def position(self):
        """Pixel coordinates for Tkinter drawing."""
        return self.board.cartesian[self.axialindex]

    def getPossibleMoves(self):
        """
        Return a sorted list of board indices representing empty cells
        this pin can legally move to in one turn.
        """
        board = self.board
        start_idx = self.axialindex

        directions = [(1, 0), (-1, 0), (0, 1), (0, -1), (1, -1), (-1, 1)]

        def idx_of(q, r):
            return board.index_of.get((q, r), None)

        start_cell = board.cells[start_idx]
        q0, r0 = start_cell.q, start_cell.r
        possible = set()

        # Single steps
        for dq, dr in directions:
            ni = idx_of(q0 + dq, r0 + dr)
            if ni is not None and not board.cells[ni].occupied:
                possible.add(ni)

        # Multi-hop BFS
        visited = {start_idx}
        stack = [start_idx]
        while stack:
            cur = stack.pop()
            cq, cr = board.cells[cur].q, board.cells[cur].r
            for dq, dr in directions:
                aq, ar = cq + dq, cr + dr
                bq, br = cq + 2*dq, cr + 2*dr
                adj_idx  = idx_of(aq, ar)
                land_idx = idx_of(bq, br)
                if adj_idx is None or land_idx is None:
                    continue
                if board.cells[adj_idx].occupied and not board.cells[land_idx].occupied:
                    if land_idx not in visited:
                        possible.add(land_idx)
                        visited.add(land_idx)
                        stack.append(land_idx)

        return sorted(possible)

    def placePin(self, new_axialindex: int):
        """Move pin to a new index on the board."""
        if int(new_axialindex) < 0 or int(new_axialindex) >= len(self.board.cells):
            print("Pin index out of bounds for this board.")
            return False
        if self.board.cells[new_axialindex].occupied == True:
            print("Cannot place pin here; position occupied.")
            return False
        self.board.cells[self.axialindex].occupied = False
        self.axialindex = int(new_axialindex)
        self.board.cells[int(new_axialindex)].occupied = True
        print('Pin placed successfully.')
        return True
