import math

class BoardPosition:
    def __init__(self, q, r, spacing, postype='board'):
        self.q = q
        self.r = r
        self.x = spacing * (math.sqrt(3) * q + math.sqrt(3)/2 * r)
        self.y = spacing * (3/2 * r)
        self.postype = postype # default type
        self.occupied = False

class HexBoard:
    """
    A true hexagonal board on a hex lattice (axial coordinates).
    Radius R=4 => 61 cells (1 + 3*R*(R+1)).
    """
    def __init__(self, R=4, hole_radius=18, spacing=34):
        self.R = R
        self.hole_radius = hole_radius
        self.spacing = spacing
        self.colour_opposites ={'red':'blue', 'lawn green':'gray0', 'blue':'red', 'yellow':'purple', 'purple':'yellow', 'gray0':'lawn green'}

        self.cells = []
        self.index_of = {}
        self.cartesian = []
        self._rows = []

        self._generate_hexagon()
        self._project_to_pixels()
        self._build_rows_for_ascii()

    def _generate_hexagon(self):
        R = self.R
        cells = []
        for q in range(-R, R + 1):
            for r in range(-R, R + 1):
                s = -q - r
                if max(abs(q), abs(r), abs(s)) <= R:
                    newcell = BoardPosition(q, r, self.spacing)
                    cells.append(newcell)
        base_blue   = [(1,-5),(2,-5),(3,-5),(4,-5), (2,-6),(3,-6),(4,-6), (3,-7),(4,-7), (4,-8)]
        base_red    = [(-1,5),(-2,5),(-3,5),(-4,5), (-2,6),(-3,6),(-4,6), (-3,7),(-4,7), (-4,8)]
        base_yellow = [(-1,-4),(-2,-3),(-3,-2),(-4,-1), (-2,-4),(-3,-3),(-4,-2), (-3,-4),(-4,-3),(-4,-4)]
        base_green  = [(5,-4),(5,-3),(5,-2),(5,-1), (6,-4),(6,-3),(6,-2), (7,-4),(7,-3), (8,-4)]
        base_purple = [(1,4),(2,3),(3,2),(4,1), (2,4),(3,3),(4,2), (3,4),(4,3), (4,4)]
        base_gray0  = [(-5,1),(-5,2),(-5,3),(-5,4), (-6,2),(-6,3),(-6,4), (-7,3),(-7,4), (-8,4)]
        for (q,r) in base_blue:
            newcell = BoardPosition(q, r, self.spacing, postype='blue')
            cells.append(newcell)
        for (q,r) in base_red:
            newcell = BoardPosition(q, r, self.spacing, postype='red')
            cells.append(newcell)
        for (q,r) in base_yellow:
            newcell = BoardPosition(q, r, self.spacing, postype='yellow')
            cells.append(newcell)
        for (q,r) in base_green:
            newcell = BoardPosition(q, r, self.spacing, postype='lawn green')
            cells.append(newcell)
        for (q,r) in base_purple:
            newcell = BoardPosition(q, r, self.spacing, postype='purple')
            cells.append(newcell)
        for (q,r) in base_gray0:
            newcell = BoardPosition(q, r, self.spacing, postype='gray0')
            cells.append(newcell)

        cells.sort(key=lambda t: (t.r, t.q))
        self.cells = cells
        self.index_of = {(ax.q,ax.r): i for i, ax in enumerate(cells)}

    def _project_to_pixels(self):
        cart = []
        for t in self.cells:
            cart.append((t.x, t.y))
        self.cartesian = cart

    def _build_rows_for_ascii(self):
        rows = {}
        for t in self.cells:
            rows.setdefault(t.r, []).append((t.q, t.r, t.postype))
        ordered = []
        for rr in sorted(rows.keys()):
            ordered.append(sorted(rows[rr], key=lambda x: x[0]))
        self._rows = ordered

    def print_ascii(self, pins=None, empty='·'):
        pin_map = {}
        if pins:
            for p in pins:
                q = self.cells[p.axialindex].q
                r = self.cells[p.axialindex].r
                pin_map[(q, r)] = (p.color[:1].upper() if p.color else 'X')
        max_width = max(len(row) for row in self._rows)
        for row in self._rows:
            pad = " " * (max_width - len(row))
            parts = []
            for (q, r, t) in row:
                parts.append(pin_map.get((q, r), empty if t == 'board' else t[:1].lower()))
            print(pad + " ".join(parts))

    def axial_index(self, q, r):
        return self.index_of[(q, r)]

    def axial_of_index(self, idx):
        return self.cells[idx]

    def axial_of_colour(self, colour):
        l = [(cell.q, cell.r) for cell in self.cells if cell.postype == colour]
        return [self.index_of[(q,r)] for (q,r) in l]
