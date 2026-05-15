class MoveRecord:
    def __init__(self, pin, old_idx):
        self.pin = pin
        self.old_idx = old_idx

def apply_move(pin, to_idx):
    board = pin.board
    old = pin.axialindex
    board.cells[old].occupied = False
    pin.axialindex = to_idx
    board.cells[to_idx].occupied = True
    return MoveRecord(pin, old)

def undo_move(rec):
    pin = rec.pin
    board = pin.board
    board.cells[pin.axialindex].occupied = False
    pin.axialindex = rec.old_idx
    board.cells[rec.old_idx].occupied = True

def has_won(board, pins, colour):
    goal = board.colour_opposites[colour]
    return all(board.cells[p.axialindex].postype == goal for p in pins)

def hash_position(pins_by_colour):
    items = []
    for colour in sorted(pins_by_colour):
        positions = sorted(pin.axialindex for pin in pins_by_colour[colour])
        for idx in positions:
            items.append((colour, idx))
    return tuple(items)