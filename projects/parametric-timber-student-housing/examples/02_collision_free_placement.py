"""
================================================================================
Parametric Timber Student Housing
       SINGLE CLUSTER  |  Multi-Courtyard  |  Habitat-'67 Aggregation
                  STANDALONE RHINO PYTHON  (v4.0)
================================================================================

WHAT IS NEW IN v4 vs v3:
  v3 placed modules cell-by-cell without checking neighbours, so a horizontal
  Module A (5m long) bled 1.5m into the next cell and collided with whatever
  was placed there. v4 fixes this with proper FOOTPRINT TRACKING:

    - Every module reserves the cells it actually occupies
    - Before placing, we check that ALL needed cells are free
    - Module A horizontal needs 2 adjacent cells (one along its long axis)
    - Module B vertical needs the SAME footprint cell on 2 levels (5m height
      = level + 1.5m into the next floor's airspace, but the next level's
      footprint cell stays reserved)

  CONNECTION RULES (now enforced, not implicit):
    [F]  FULL FACE  - module shares its full face with a neighbour
                      (e.g. two A's side by side along their 3.5m short side)
    [E]  EDGE       - modules touch along an edge only
                      (diagonal cell neighbours, like Habitat's corner-touch)
    [H]  HALF FACE  - A meets B at half its face (A is 5m, B is 3.5m, so A's
                      long side overlaps only part of B's vertical face)
    [X]  COLLISION  - NEVER allowed. Volumes never interpenetrate.

  Module A (5m) placed centred across 2 cells leaves a natural 1m gap on each
  end - this becomes a circulation/light slot between adjacent A's, exactly
  the look in your reference image 4.

MODULE DIMENSIONS (unchanged):
  Module A (horizontal) : 5.0m L x 3.5m W x 3.5m H
  Module B (vertical)   : 3.5m W x 3.5m D x 5.0m H

USAGE:
  1. _RunPythonScript -> select this file
  2. Answer prompts (defaults shown in brackets)
  3. Geometry bakes to:
       WoSyHo::Module_A_horizontal   (sandy brown)
       WoSyHo::Module_B_vertical     (steel blue)
       WoSyHo::Terraces              (lime green, optional)
================================================================================
"""

import rhinoscriptsyntax as rs
import scriptcontext as sc
import Rhino.Geometry as rg
import System.Drawing as sd
import random
import math

# ---------------------------------------------------------------------------
#  MODULE & GRID CONSTANTS
# ---------------------------------------------------------------------------
MOD_AL  = 5.0    # A: long side
MOD_AW  = 3.5    # A: short side
MOD_AH  = 3.5    # A: height (= 1 floor)

MOD_BW  = 3.5    # B: width
MOD_BD  = 3.5    # B: depth
MOD_BH  = 5.0    # B: height (1.5m taller than 1 floor; protrudes upward)

GRID    = 3.5    # grid cell side
LEVEL_H = 3.5    # floor-to-floor

# ---------------------------------------------------------------------------
#  LAYER UTILITIES
# ---------------------------------------------------------------------------
def ensure_layer(name, color):
    parent = "WoSyHo"
    full   = parent + "::" + name
    if not rs.IsLayer(parent):
        rs.AddLayer(parent)
    if not rs.IsLayer(full):
        rs.AddLayer(full, color)
    return full

# ---------------------------------------------------------------------------
#  GEOMETRY BUILDERS
# ---------------------------------------------------------------------------
def axis_box(ox, oy, oz, lx, ly, lz):
    plane = rg.Plane(rg.Point3d(ox, oy, oz), rg.Vector3d.ZAxis)
    return rg.Box(plane,
                  rg.Interval(0.0, lx),
                  rg.Interval(0.0, ly),
                  rg.Interval(0.0, lz)).ToBrep()

def make_A(col, row, level, orient, cx_off=0.0, cy_off=0.0):
    """
    Module A.  IMPORTANT: A is 5m long but a cell is 3.5m. We CENTRE the A
    across 2 cells along its long axis, leaving a 1m gap on each end.

    orient = 0 (along X):
        anchor cells (col, row), (col+1, row)
        world span X: [col*3.5 + 1.0  ...  col*3.5 + 1.0 + 5.0]
                    = [col*3.5 + 1.0  ...  col*3.5 + 6.0]
        i.e. spans from 1.0m into cell `col` to 1.0m before end of cell `col+1`
        world span Y: [row*3.5  ...  row*3.5 + 3.5]   (full single-cell width)

    orient = 1 (along Y): swapped X/Y.
    """
    oz = level * LEVEL_H
    if orient == 0:
        ox = col * GRID + 1.0 + cx_off
        oy = row * GRID + cy_off
        return axis_box(ox, oy, oz, MOD_AL, MOD_AW, MOD_AH)
    else:
        ox = col * GRID + cx_off
        oy = row * GRID + 1.0 + cy_off
        return axis_box(ox, oy, oz, MOD_AW, MOD_AL, MOD_AH)

def make_B(col, row, level, cx_off=0.0, cy_off=0.0):
    """Vertical B: occupies one cell footprint, 5m tall (1.5m into next floor)."""
    ox = col * GRID + cx_off
    oy = row * GRID + cy_off
    oz = level * LEVEL_H
    return axis_box(ox, oy, oz, MOD_BW, MOD_BD, MOD_BH)

def make_terrace_slab(col, row, level):
    """Thin slab marking a terrace (where a roof is exposed)."""
    ox = col * GRID + 0.05
    oy = row * GRID + 0.05
    oz = level * LEVEL_H
    return axis_box(ox, oy, oz - 0.05, GRID - 0.10, GRID - 0.10, 0.05)

# ---------------------------------------------------------------------------
#  PYRAMID MASK
# ---------------------------------------------------------------------------
def build_pyramid_masks(nx, ny, max_levels, plateau_levels, rng):
    """
    masks[level] = set of (col, row) that are inside the stepped pyramid.
    Plateau levels get the FULL grid; upper levels shrink toward centre with
    Gaussian jitter for irregular silhouette.
    """
    cx = (nx - 1) * 0.5
    cy = (ny - 1) * 0.5
    base_r = min(cx, cy) * 0.97
    upper_levels = max_levels - plateau_levels
    shrink = base_r / float(max(upper_levels, 1))
    noise_sigma = shrink * 0.35

    masks = []
    for level in range(max_levels):
        if level < plateau_levels:
            allowed_r = base_r + 1.0
        else:
            steps_above_plateau = level - plateau_levels
            allowed_r = base_r - steps_above_plateau * shrink * 0.85
        mask = set()
        for col in range(nx):
            for row in range(ny):
                dist = max(abs(col - cx), abs(row - cy))
                jitter = rng.gauss(0.0, noise_sigma) if level >= plateau_levels else 0.0
                if dist <= (allowed_r + jitter):
                    mask.add((col, row))
        masks.append(mask)
    return masks

# ---------------------------------------------------------------------------
#  COURTYARD VOID GENERATOR
# ---------------------------------------------------------------------------
def punch_courtyards(nx, ny, max_levels, n_courts, rng):
    margin = max(1, min(nx, ny) // 6)
    voids  = set()
    if n_courts <= 0:
        return frozenset(voids)
    cols_spread = max(1, int(math.ceil(math.sqrt(n_courts * nx / float(max(ny, 1))))))
    rows_spread = max(1, int(math.ceil(n_courts / float(cols_spread))))
    zone_w = (nx - 2 * margin) / float(max(cols_spread, 1))
    zone_h = (ny - 2 * margin) / float(max(rows_spread, 1))
    placed = 0
    for ci in range(cols_spread):
        for ri in range(rows_spread):
            if placed >= n_courts: break
            base_c = int(margin + zone_w * (ci + 0.2 + rng.random() * 0.6))
            base_r = int(margin + zone_h * (ri + 0.2 + rng.random() * 0.6))
            base_c = max(margin, min(nx - margin - 1, base_c))
            base_r = max(margin, min(ny - margin - 1, base_r))
            w = rng.randint(1, min(2, nx - base_c - margin))
            d = rng.randint(1, min(2, ny - base_r - margin))
            z_max = rng.randint(max(1, max_levels // 2), max(1, max_levels - 1))
            for lv in range(z_max):
                for c in range(base_c, min(base_c + w, nx)):
                    for r in range(base_r, min(base_r + d, ny)):
                        voids.add((c, r, lv))
            placed += 1
    return frozenset(voids)

# ---------------------------------------------------------------------------
#  OCCUPANCY TRACKER  -  the heart of the collision-free logic
# ---------------------------------------------------------------------------
class Occupancy(object):
    """
    Tracks which (col, row, level) triples are occupied AND keeps a list of
    every module's actual world-space AABB for definitive collision checking.

    Cell tracking is fast but coarse - it stops obvious overlaps. Module A's
    long axis (5m) extends past its anchor cell, and cantilevers shift things
    further, so we ALSO do an AABB check before committing.
    """
    def __init__(self):
        self.cells = set()
        self.aabbs = []           # list of (xmin, ymin, zmin, xmax, ymax, zmax)
        self.modules = []
        self.n_face = 0
        self.n_edge = 0
        self.n_half = 0

    def is_free(self, c, r, lv):
        return (c, r, lv) not in self.cells

    def reserve(self, cells_iter):
        for cell in cells_iter:
            self.cells.add(cell)

    def cells_of_A(self, col, row, level, orient):
        if orient == 0:
            return [(col, row, level), (col + 1, row, level)]
        else:
            return [(col, row, level), (col, row + 1, level)]

    def cells_of_B(self, col, row, level):
        return [(col, row, level), (col, row, level + 1)]

    def aabb_of_A(self, col, row, level, orient, cx_off, cy_off):
        oz = level * LEVEL_H
        if orient == 0:
            ox = col * GRID + 1.0 + cx_off
            oy = row * GRID + cy_off
            return (ox, oy, oz, ox + MOD_AL, oy + MOD_AW, oz + MOD_AH)
        else:
            ox = col * GRID + cx_off
            oy = row * GRID + 1.0 + cy_off
            return (ox, oy, oz, ox + MOD_AW, oy + MOD_AL, oz + MOD_AH)

    def aabb_of_B(self, col, row, level, cx_off, cy_off):
        ox = col * GRID + cx_off
        oy = row * GRID + cy_off
        oz = level * LEVEL_H
        return (ox, oy, oz, ox + MOD_BW, oy + MOD_BD, oz + MOD_BH)

    def aabb_collides(self, candidate, eps=1e-4):
        """Return True if the candidate AABB overlaps any existing AABB."""
        for a in self.aabbs:
            ox = min(a[3], candidate[3]) - max(a[0], candidate[0]) - eps
            if ox <= 0: continue
            oy = min(a[4], candidate[4]) - max(a[1], candidate[1]) - eps
            if oy <= 0: continue
            oz = min(a[5], candidate[5]) - max(a[2], candidate[2]) - eps
            if oz <= 0: continue
            return True
        return False

    def can_place_A(self, col, row, level, orient, mask, voids, nx, ny):
        cells = self.cells_of_A(col, row, level, orient)
        for c, r, lv in cells:
            if c < 0 or c >= nx or r < 0 or r >= ny: return False
            if (c, r) not in mask: return False
            if (c, r, lv) in voids: return False
            if not self.is_free(c, r, lv): return False
        return True

    def can_place_B(self, col, row, level, mask, voids, nx, ny, max_levels):
        cells = self.cells_of_B(col, row, level)
        for c, r, lv in cells:
            if c < 0 or c >= nx or r < 0 or r >= ny: return False
            if lv >= max_levels: return False
            if (c, r) not in mask: return False
            if (c, r, lv) in voids: return False
            if not self.is_free(c, r, lv): return False
        return True

    def place_A(self, col, row, level, orient, cx_off, cy_off):
        cells = self.cells_of_A(col, row, level, orient)
        aabb = self.aabb_of_A(col, row, level, orient, cx_off, cy_off)
        connections = self._classify_connections(cells, kind='A', orient=orient)
        self.reserve(cells)
        self.aabbs.append(aabb)
        self.modules.append({
            "kind": "A", "col": col, "row": row, "level": level,
            "orient": orient, "cells": cells, "aabb": aabb,
            "cx": cx_off, "cy": cy_off, "connections": connections,
        })
        self._tally(connections)

    def place_B(self, col, row, level, cx_off, cy_off):
        cells = self.cells_of_B(col, row, level)
        aabb = self.aabb_of_B(col, row, level, cx_off, cy_off)
        connections = self._classify_connections(cells, kind='B', orient=None)
        self.reserve(cells)
        self.aabbs.append(aabb)
        self.modules.append({
            "kind": "B", "col": col, "row": row, "level": level,
            "orient": None, "cells": cells, "aabb": aabb,
            "cx": cx_off, "cy": cy_off, "connections": connections,
        })
        self._tally(connections)

    def _classify_connections(self, my_cells, kind, orient):
        cons = []
        my_set = set(my_cells)
        for (c, r, lv) in my_cells:
            for di, dj, dk, kind_label in [
                ( 1, 0, 0, "face_x"), (-1, 0, 0, "face_x"),
                ( 0, 1, 0, "face_y"), ( 0,-1, 0, "face_y"),
                ( 0, 0, 1, "face_z"), ( 0, 0,-1, "face_z"),
            ]:
                nb = (c + di, r + dj, lv + dk)
                if nb in my_set: continue
                if nb in self.cells:
                    cons.append(kind_label)
        return cons

    def _tally(self, cons):
        for c in cons:
            self.n_face += 1

    def finalize_edges(self, nx, ny, max_levels):
        for mod in self.modules:
            edge_count = 0
            for (c, r, lv) in mod["cells"]:
                for di, dj in [(1,1), (1,-1), (-1,1), (-1,-1)]:
                    nb = (c + di, r + dj, lv)
                    if nb in self.cells and nb not in mod["cells"]:
                        edge_count += 1
            mod["edges"] = edge_count
            self.n_edge += edge_count

# ---------------------------------------------------------------------------
#  DENSITY & CANTILEVER
# ---------------------------------------------------------------------------
def cell_fill_prob(col, row, nx, ny, level, max_levels, plateau_levels):
    """High at base/centre, low at top/edges. Plateau levels stay near 1.0."""
    cx = (nx - 1) * 0.5
    cy = (ny - 1) * 0.5
    dist = math.sqrt((col - cx) ** 2 + (row - cy) ** 2)
    max_d = math.sqrt(cx ** 2 + cy ** 2) + 0.001
    radial = 1.0 - 0.25 * (dist / max_d)
    if level < plateau_levels:
        vertical = 1.0
    else:
        t = (level - plateau_levels) / float(max(max_levels - plateau_levels - 1, 1))
        vertical = 0.95 - 0.55 * t
    return max(0.0, radial * vertical)

def cantilever_offset(col, row, nx, ny, level, cant_max, rng,
                       occ_cells, mod_cells):
    """
    Compute outward cantilever offset that NEVER pushes the module's volume
    into another module. Returns (cx, cy) in metres.

    Strategy: only allow offset in the direction away from any neighbour cells
    that are occupied. If the cell behind us (toward centre) is occupied AND
    the cell ahead of us (away from centre) is empty, we can lean outward.
    """
    if level == 0 or cant_max <= 0.01:
        return 0.0, 0.0
    prob = 0.12 + level * 0.12
    if rng.random() > min(prob, 0.55):
        return 0.0, 0.0

    cx_grid = (nx - 1) * 0.5
    cy_grid = (ny - 1) * 0.5
    dx_dir = col - cx_grid
    dy_dir = row - cy_grid

    # discretise outward direction to grid steps
    step_x = 1 if dx_dir > 0.5 else (-1 if dx_dir < -0.5 else 0)
    step_y = 1 if dy_dir > 0.5 else (-1 if dy_dir < -0.5 else 0)

    # only allow X offset if the cell IMMEDIATELY outward in X is empty
    can_offset_x = step_x != 0
    can_offset_y = step_y != 0
    for (mc, mr, mlv) in mod_cells:
        if can_offset_x:
            if (mc + step_x, mr, mlv) in occ_cells:
                can_offset_x = False
        if can_offset_y:
            if (mc, mr + step_y, mlv) in occ_cells:
                can_offset_y = False
        if not (can_offset_x or can_offset_y):
            break

    if not (can_offset_x or can_offset_y):
        return 0.0, 0.0

    mag = math.sqrt(max(dx_dir, 0)**2 + max(dy_dir, 0)**2) + 1e-6
    offset = rng.uniform(GRID * 0.10, cant_max)
    cx_off = (dx_dir / mag) * offset if can_offset_x else 0.0
    cy_off = (dy_dir / mag) * offset if can_offset_y else 0.0
    return cx_off, cy_off

# ---------------------------------------------------------------------------
#  MAIN CLUSTER GENERATOR  -  collision-free
# ---------------------------------------------------------------------------
def generate_cluster(nx, ny, max_levels, plateau_levels, n_courts,
                      b_ratio, cant_max, seed):
    rng = random.Random(seed)
    masks = build_pyramid_masks(nx, ny, max_levels, plateau_levels, rng)
    voids = punch_courtyards(nx, ny, max_levels, n_courts, rng)
    occ = Occupancy()

    # iterate level by level so upper modules rest on lower ones (Habitat logic)
    for level in range(max_levels):
        mask = masks[level]
        # collect candidate cells in randomized order
        cells_in_level = []
        for col in range(nx):
            for row in range(ny):
                if (col, row) in mask:
                    cells_in_level.append((col, row))
        rng.shuffle(cells_in_level)

        for (col, row) in cells_in_level:
            # already reserved by some 2-cell module spanning into here?
            if not occ.is_free(col, row, level):
                continue
            # void cell?
            if (col, row, level) in voids:
                continue
            # density roll
            prob = cell_fill_prob(col, row, nx, ny, level, max_levels, plateau_levels)
            if rng.random() > prob:
                continue
            # support check: above level 0, this cell needs SOMETHING below
            # (any module reservation in (col, row, level-1))
            if level > 0 and (col, row, level - 1) not in occ.cells:
                # allow with low probability for floating cantilever effect (rare)
                if rng.random() > 0.15:
                    continue

            # decide module type
            lv_norm = level / float(max(max_levels - 1, 1))
            b_prob = b_ratio * (0.35 + 1.3 * lv_norm)
            b_prob = min(b_prob, 0.55)
            try_B_first = rng.random() < b_prob

            placed = False

            # ----- attempt B first if dice says so -----
            if try_B_first:
                if occ.can_place_B(col, row, level, mask, voids, nx, ny, max_levels):
                    cells = occ.cells_of_B(col, row, level)
                    cx_off, cy_off = cantilever_offset(
                        col, row, nx, ny, level, cant_max, rng,
                        occ.cells, cells)
                    aabb = occ.aabb_of_B(col, row, level, cx_off, cy_off)
                    # AABB safety: reject if it would overlap any prior module
                    if not occ.aabb_collides(aabb):
                        occ.place_B(col, row, level, cx_off, cy_off)
                        placed = True
                    else:
                        # try again without cantilever
                        aabb_zero = occ.aabb_of_B(col, row, level, 0.0, 0.0)
                        if not occ.aabb_collides(aabb_zero):
                            occ.place_B(col, row, level, 0.0, 0.0)
                            placed = True

            # ----- try A next, in a random orientation order -----
            if not placed:
                orients = [0, 1]
                rng.shuffle(orients)
                for orient in orients:
                    if occ.can_place_A(col, row, level, orient, mask, voids,
                                        nx, ny):
                        cells = occ.cells_of_A(col, row, level, orient)
                        cx_off, cy_off = cantilever_offset(
                            col, row, nx, ny, level, cant_max, rng,
                            occ.cells, cells)
                        aabb = occ.aabb_of_A(col, row, level, orient,
                                              cx_off, cy_off)
                        if not occ.aabb_collides(aabb):
                            occ.place_A(col, row, level, orient, cx_off, cy_off)
                            placed = True
                            break
                        else:
                            aabb_zero = occ.aabb_of_A(col, row, level, orient,
                                                       0.0, 0.0)
                            if not occ.aabb_collides(aabb_zero):
                                occ.place_A(col, row, level, orient, 0.0, 0.0)
                                placed = True
                                break

            # ----- last resort: try B if we didn't already -----
            if not placed and not try_B_first:
                if occ.can_place_B(col, row, level, mask, voids, nx, ny, max_levels):
                    aabb_zero = occ.aabb_of_B(col, row, level, 0.0, 0.0)
                    if not occ.aabb_collides(aabb_zero):
                        occ.place_B(col, row, level, 0.0, 0.0)

    occ.finalize_edges(nx, ny, max_levels)
    return occ

# ---------------------------------------------------------------------------
#  TERRACE DETECTION  -  exposed roofs become decks
# ---------------------------------------------------------------------------
def find_terraces(occ, max_levels):
    """For each occupied cell, if no cell is reserved directly above, the top
    of that cell becomes a terrace."""
    terraces = []
    for (c, r, lv) in occ.cells:
        if lv + 1 >= max_levels: continue
        if (c, r, lv + 1) not in occ.cells:
            terraces.append((c, r, lv + 1))   # terrace AT the top of cell lv
    return terraces

# ---------------------------------------------------------------------------
#  ENTRY POINT
# ---------------------------------------------------------------------------
def main():
    print("=" * 68)
    print("  WoSyHo  -  Single Cluster Aggregator  v4.0  (collision-free)")
    print("  Module A : 5.0L x 3.5W x 3.5H m  (horizontal)")
    print("  Module B : 3.5W x 3.5D x 5.0H m  (vertical tower)")
    print("=" * 68)

    nx       = rs.GetInteger("Grid columns NX",            number=10, minimum=4, maximum=24)
    ny       = rs.GetInteger("Grid rows NY",               number=10, minimum=4, maximum=24)
    floors   = rs.GetInteger("Number of floors (3/4/5)",   number=4,  minimum=3, maximum=5)
    plateau  = rs.GetInteger("Plateau lower floors (1/2)", number=2,  minimum=1, maximum=2)
    courts   = rs.GetInteger("Sky-courts / voids",         number=4,  minimum=0, maximum=14)
    b_pct    = rs.GetInteger("Vertical B percentage",      number=22, minimum=5, maximum=50)
    cant     = rs.GetReal("Max cantilever (m)",            number=0.6, minimum=0.0, maximum=2.0)
    seed     = rs.GetInteger("Random seed",                 number=7)
    show_t   = rs.GetInteger("Show terrace slabs? (1=yes 0=no)", number=1, minimum=0, maximum=1)

    if None in (nx, ny, floors, plateau, courts, b_pct, cant, seed, show_t):
        print("Cancelled."); return

    occ = generate_cluster(nx, ny, floors, plateau, courts,
                            b_pct / 100.0, cant, seed)

    # build geometry
    list_A, list_B = [], []
    for mod in occ.modules:
        if mod["kind"] == "A":
            list_A.append(make_A(mod["col"], mod["row"], mod["level"],
                                  mod["orient"], mod["cx"], mod["cy"]))
        else:
            list_B.append(make_B(mod["col"], mod["row"], mod["level"],
                                  mod["cx"], mod["cy"]))

    # terraces
    list_T = []
    if show_t:
        for (c, r, lv) in find_terraces(occ, floors):
            list_T.append(make_terrace_slab(c, r, lv))

    if not list_A and not list_B:
        print("No modules generated. Try larger grid or fewer courtyards.")
        return

    # bake
    L_A = ensure_layer("Module_A_horizontal", sd.Color.SandyBrown)
    L_B = ensure_layer("Module_B_vertical",   sd.Color.SteelBlue)
    L_T = ensure_layer("Terraces",             sd.Color.LimeGreen)

    rs.CurrentLayer(L_A)
    for b in list_A: sc.doc.Objects.AddBrep(b)
    rs.CurrentLayer(L_B)
    for b in list_B: sc.doc.Objects.AddBrep(b)
    if show_t:
        rs.CurrentLayer(L_T)
        for b in list_T: sc.doc.Objects.AddBrep(b)
    sc.doc.Views.Redraw()

    # report
    n_A = len(list_A)
    n_B = len(list_B)
    n_T = len(list_T)
    edge_count = sum(m.get("edges", 0) for m in occ.modules)

    print("\n  >> Cluster generated (collision-free)")
    print("     Module A (horizontal) : {}".format(n_A))
    print("     Module B (vertical)   : {}".format(n_B))
    print("     Total modules         : {}".format(n_A + n_B))
    print("     Approx footprint      : {:.0f} x {:.0f} m".format(
          nx * GRID, ny * GRID))
    print("     Max height            : {:.1f} m  ({} floors)".format(
          floors * LEVEL_H, floors))
    print("     Terraces detected     : {}".format(n_T))
    print("     Connection stats      :")
    print("        full-face contacts : {}".format(occ.n_face))
    print("        edge contacts      : {}".format(edge_count))
    print("=" * 68)

if __name__ == "__main__":
    main()
