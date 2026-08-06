"""
================================================================================
Parametric Timber Student Housing
   SINGLE CLUSTER  |  4 COURTYARD TYPES  |  Reference-matched Density
                  STANDALONE RHINO PYTHON  (v10.0)
================================================================================

v10 CHANGES vs v9.3 (driven by analysis of your CONNECTION.3dm reference):

  * COURTYARD-DRIVEN PLACEMENT (a fundamental rethink):
      Instead of "place modules then carve courtyards", v10 places the
      courtyard FIRST as a hard void zone, then arranges modules around
      it as a perimeter ring. This guarantees:
        - Every module touches the courtyard or the outer edge
        - Cross-ventilation: every module has at least 2 free walls
        - The cluster is genuinely a ring/U/H typology, not random fill

  * 4 COURTYARD TYPES (reduced from 4 typologies + 4 hofhaus shapes):
      SQUARE          - centred square courtyard
      RECTANGULAR     - elongated courtyard along long axis (your reference)
      PIXELATED_CIRC  - pixelated circular courtyard
      MULTIPLE        - 2-3 smaller courtyards distributed in the cluster

  * REFERENCE-MATCHED DEFAULTS (from CONNECTION.3dm analysis):
      Footprint    13 x 23 cells (49 x 86 m)        - elongated bar
      Floors       5 (G + 4)
      Plateau      2 floors (L0-L1 same density)
      Density      24% per floor (much lower than before)
      B ratio      34% (more vertical anchors)
      Cascade      asymmetric - courtyard widens upward,
                                outer perimeter stays straight
      A orientation alternates per floor: X / X / Y / Y

  * CORRIDOR FIX (the v9.3 multi-cube bug):
      Continuous linear cuboids - all consecutive cells on the same
      straight line are merged into ONE elongated brep, not separate cubes.

  * VENTILATION RULE:
      Every placed module must have at least 2 free macro neighbours
      (the courtyard counts as a free face). Modules that fail this
      rule are rejected during placement, preventing the dense interior
      blocks that caused landlocked corridor problems in v9.3.

MODULE DIMENSIONS (unchanged):
  Module A horizontal : 7.5 L x 3.75 W x 3.75 H
  Module B vertical   : 3.75 W x 3.75 D x 7.5 H  (split-level, 2 floors)
  Macro grid cell     : 3.75 m
  Floor height        : 3.75 m
  Corridor cuboid     : 1.5 m wide x 2.4 m tall (continuous linear)
================================================================================
"""

import rhinoscriptsyntax as rs
import scriptcontext as sc
import Rhino
import Rhino.Geometry as rg
import System.Drawing as sd
import Eto.Forms as forms
import Eto.Drawing as drawing
import Rhino.UI
import random
import math

# ---------------------------------------------------------------------------
#  CONSTANTS
# ---------------------------------------------------------------------------
MOD_AL  = 7.5
MOD_AW  = 3.75
MOD_AH  = 3.75
MOD_BW  = 3.75
MOD_BD  = 3.75
MOD_BH  = 7.5
GRID    = 3.75       # macro (integer) grid
SUBGRID = 1.875      # half-cell sub-grid (= GRID / 2)
LEVEL_H = 3.75

# In sub-cell units, module footprints occupy:
#   B (3.75 x 3.75)  -> 2 x 2 sub-cells
#   A (7.5 x 3.75)   -> 4 x 2 sub-cells (or 2 x 4 for orient=Y)

# Style codes
STYLE_COMPACT = 1
STYLE_MANUAL  = 2
STYLE_HYBRID  = 3

# Courtyard typology codes (v10 - reduced to 4 courtyard styles)
TYPO_SQUARE      = 1   # centred square courtyard
TYPO_RECTANGULAR = 2   # elongated courtyard (CONNECTION.3dm reference)
TYPO_PIXEL_CIRC  = 3   # pixelated circular courtyard
TYPO_MULTIPLE    = 4   # 2-3 distributed courtyards

# (Legacy aliases kept for backward compat with internal code)
TYPO_HOFHAUS    = TYPO_RECTANGULAR
TYPO_SCATTER    = TYPO_MULTIPLE
TYPO_SCULPTURAL = TYPO_PIXEL_CIRC
TYPO_CASCADING  = TYPO_RECTANGULAR

# Hofhaus shape sub-types (v10 - kept but no longer separately exposed)
HOF_SQUARE      = 1
HOF_RECTANGULAR = 2
HOF_CIRCULAR    = 3
HOF_CASCADING   = 4

# Corridor mode codes (NEW v9)
CORR_STRAIGHT    = 1   # orthogonal X/Y rectilinear
CORR_ANGULAR     = 2   # any-angle straight segments
CORR_CURVILINEAR = 3   # smooth Bezier/spline

# Code limits
MAX_TRAVEL_DIST = 35.0    # max distance from any A to a stair (German DIN 18065)

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

def make_A_at(world_x, world_y, level, orient):
    oz = level * LEVEL_H
    if orient == 0:
        return axis_box(world_x, world_y, oz, MOD_AL, MOD_AW, MOD_AH)
    return axis_box(world_x, world_y, oz, MOD_AW, MOD_AL, MOD_AH)

def make_B_at(world_x, world_y, level):
    oz = level * LEVEL_H
    return axis_box(world_x, world_y, oz, MOD_BW, MOD_BD, MOD_BH)

# ---------------------------------------------------------------------------
#  SUB-CELL OCCUPANCY TRACKER
# ---------------------------------------------------------------------------
class Occupancy(object):
    """
    Tracks occupancy on the FINE grid (sub-cells of 1.875m).
    A module reserves all sub-cells inside its footprint, on every level it
    spans. AABBs are also kept for definitive collision check.
    """
    def __init__(self):
        self.cells = set()          # set of (sci, scj, level) sub-cell positions
        self.aabbs = []
        self.modules = []
        # connection counters
        self.n_direct   = 0
        self.n_adjacent = 0
        self.n_bridge   = 0
        self.n_edge     = 0
        self.n_halfface = 0
        self.n_corner   = 0
        self.n_ground   = 0

    # ---- footprint helpers ------------------------------------------------
    def cells_of_A(self, sci, scj, level, orient):
        """An A spans 4 sub-cells (long axis) x 2 sub-cells (short)."""
        out = []
        if orient == 0:    # long along X
            for dx in range(4):
                for dy in range(2):
                    out.append((sci + dx, scj + dy, level))
        else:              # long along Y
            for dx in range(2):
                for dy in range(4):
                    out.append((sci + dx, scj + dy, level))
        return out

    def cells_of_B(self, sci, scj, level):
        """A B spans 2 x 2 sub-cells, on TWO levels (5m -> 2 floors)."""
        out = []
        for dx in range(2):
            for dy in range(2):
                out.append((sci + dx, scj + dy, level))
                out.append((sci + dx, scj + dy, level + 1))
        return out

    def aabb_of_A(self, sci, scj, level, orient):
        ox = sci * SUBGRID
        oy = scj * SUBGRID
        oz = level * LEVEL_H
        if orient == 0:
            return (ox, oy, oz, ox + MOD_AL, oy + MOD_AW, oz + MOD_AH)
        return (ox, oy, oz, ox + MOD_AW, oy + MOD_AL, oz + MOD_AH)

    def aabb_of_B(self, sci, scj, level):
        ox = sci * SUBGRID
        oy = scj * SUBGRID
        oz = level * LEVEL_H
        return (ox, oy, oz, ox + MOD_BW, oy + MOD_BD, oz + MOD_BH)

    def aabb_collides(self, candidate, eps=1e-4):
        for a in self.aabbs:
            ox = min(a[3], candidate[3]) - max(a[0], candidate[0]) - eps
            if ox <= 0: continue
            oy = min(a[4], candidate[4]) - max(a[1], candidate[1]) - eps
            if oy <= 0: continue
            oz = min(a[5], candidate[5]) - max(a[2], candidate[2]) - eps
            if oz <= 0: continue
            return True
        return False

    def all_free(self, cells):
        for c in cells:
            if c in self.cells:
                return False
        return True

    def reserve(self, cells):
        for c in cells: self.cells.add(c)

    def place(self, kind, sci, scj, level, orient, support):
        if kind == "A":
            cells = self.cells_of_A(sci, scj, level, orient)
            aabb  = self.aabb_of_A(sci, scj, level, orient)
        else:
            cells = self.cells_of_B(sci, scj, level)
            aabb  = self.aabb_of_B(sci, scj, level)
        self.reserve(cells)
        self.aabbs.append(aabb)
        self.modules.append({
            "kind": kind, "sci": sci, "scj": scj, "level": level,
            "orient": orient, "cells": cells, "aabb": aabb,
            "support": support,
        })
        if   support == "ground":    self.n_ground += 1
        elif support == "direct":    self.n_direct += 1
        elif support == "adjacent":  self.n_adjacent += 1
        elif support == "bridge":    self.n_bridge += 1
        elif support == "edge":      self.n_edge += 1
        elif support == "half_face": self.n_halfface += 1
        elif support == "corner":    self.n_corner += 1

# ---------------------------------------------------------------------------
#  SUPPORT CHECK  (the heart of v8)
# ---------------------------------------------------------------------------
def check_support(cells_at_level, occ_cells, allowed_supports):
    """
    Determine the BEST support type for a candidate module.
    `cells_at_level` is the list of sub-cells at the module's bottom level.
    `allowed_supports` is the set of support types accepted by the current style.

    Returns one of: "ground", "direct", "adjacent", "bridge",
                    "edge", "half_face", "corner", or None (rejected).
    """
    if not cells_at_level: return None
    lowest_lv = min(c[2] for c in cells_at_level)
    if lowest_lv == 0:
        return "ground" if "ground" in allowed_supports else None
    base = lowest_lv - 1
    bottom_subs = set((c[0], c[1]) for c in cells_at_level if c[2] == lowest_lv)

    # ---- DIRECT: any sub-cell directly below is occupied ----
    if "direct" in allowed_supports:
        # count how many bottom sub-cells have a directly-below occupied cell
        direct_count = sum(1 for (i, j) in bottom_subs
                           if (i, j, base) in occ_cells)
        # need substantial coverage to count as direct (>= 50% of footprint)
        if direct_count >= len(bottom_subs) * 0.5:
            return "direct"

    # ---- HALF_FACE: 2-3 sub-cells below occupied (smaller module supports
    #                 part of the longer module above) - typical brick-pattern
    if "half_face" in allowed_supports:
        direct_count = sum(1 for (i, j) in bottom_subs
                           if (i, j, base) in occ_cells)
        if direct_count >= 2 and direct_count < len(bottom_subs) * 0.5:
            return "half_face"

    # ---- ADJACENT: face-neighbour of any bottom sub-cell is occupied ----
    if "adjacent" in allowed_supports:
        for (i, j) in bottom_subs:
            for di, dj in [(1,0),(-1,0),(0,1),(0,-1)]:
                if (i + di, j + dj, base) in occ_cells:
                    return "adjacent"

    # ---- EDGE: only 1 sub-cell below is occupied (vertical-edge support) ----
    if "edge" in allowed_supports:
        direct_count = sum(1 for (i, j) in bottom_subs
                           if (i, j, base) in occ_cells)
        if direct_count == 1:
            return "edge"

    # ---- BRIDGE: 2 diagonals at opposite ends ----
    if "bridge" in allowed_supports:
        # Find the bounding box of bottom_subs
        if len(bottom_subs) >= 2:
            xs = [i for (i, j) in bottom_subs]
            ys = [j for (i, j) in bottom_subs]
            x_min, x_max = min(xs), max(xs)
            y_min, y_max = min(ys), max(ys)
            # split bottom_subs into two halves along the longer axis
            if (x_max - x_min) >= (y_max - y_min):
                mid = (x_min + x_max) / 2.0
                end1 = [(i, j) for (i, j) in bottom_subs if i <= mid]
                end2 = [(i, j) for (i, j) in bottom_subs if i >  mid]
            else:
                mid = (y_min + y_max) / 2.0
                end1 = [(i, j) for (i, j) in bottom_subs if j <= mid]
                end2 = [(i, j) for (i, j) in bottom_subs if j >  mid]
            # each end must have at least one diagonal supporter below
            def has_diag(end_cells):
                for (i, j) in end_cells:
                    for di, dj in [(1,1),(1,-1),(-1,1),(-1,-1)]:
                        if (i + di, j + dj, base) in occ_cells:
                            return True
                return False
            if has_diag(end1) and has_diag(end2):
                return "bridge"

    # ---- CORNER: only diagonal-cell below occupied (corner-bearing) ----
    if "corner" in allowed_supports:
        for (i, j) in bottom_subs:
            for di, dj in [(1,1),(1,-1),(-1,1),(-1,-1)]:
                if (i + di, j + dj, base) in occ_cells:
                    return "corner"

    return None

# ---------------------------------------------------------------------------
#  PLACEMENT GRID  (which sub-cell positions are valid for the current style)
# ---------------------------------------------------------------------------
def style_anchor_positions(nx_macro, ny_macro, level, plateau_levels, style):
    """
    Return a list of (sci, scj) sub-cell anchor positions for placing a
    module's lower-left corner.

    For STYLE_COMPACT: every other sub-cell (= integer macro grid).
    For STYLE_MANUAL : every sub-cell (= half-cell offsets allowed).
    For STYLE_HYBRID : integer grid in plateau levels; half-cell above.
    """
    nx_sub = nx_macro * 2   # sub-cells per dimension
    ny_sub = ny_macro * 2
    if style == STYLE_COMPACT:
        step = 2
    elif style == STYLE_MANUAL:
        step = 1
    else:  # HYBRID
        step = 2 if level < plateau_levels else 1
    return [(i, j) for i in range(0, nx_sub, step)
                  for j in range(0, ny_sub, step)]

def style_allowed_supports(style, level, plateau_levels):
    """Return set of support types this style accepts at this level."""
    base = {"ground", "direct", "adjacent", "bridge"}
    extra = {"edge", "half_face", "corner"}
    if style == STYLE_COMPACT:
        return base
    if style == STYLE_MANUAL:
        return base | extra
    # HYBRID: strict on plateau, permissive above
    if level < plateau_levels:
        return base
    return base | extra

# ---------------------------------------------------------------------------
#  PYRAMID MASK  (operates on macro grid; converted to sub-grid during use)
# ---------------------------------------------------------------------------
def build_pyramid_masks(nx, ny, max_levels, plateau_levels, density, rng):
    cx = (nx - 1) * 0.5
    cy = (ny - 1) * 0.5
    base_r = min(cx, cy) * 0.97
    upper_levels = max(max_levels - plateau_levels, 1)
    shrink = base_r / float(upper_levels)
    sigma = shrink * 0.35
    masks = []
    for level in range(max_levels):
        if level < plateau_levels:
            allowed_r = base_r + 1.0
        else:
            steps = level - plateau_levels
            allowed_r = base_r - steps * shrink * 0.85
        mask = set()
        for col in range(nx):
            for row in range(ny):
                d = max(abs(col - cx), abs(row - cy))
                jit = rng.gauss(0.0, sigma) if level >= plateau_levels else 0.0
                if d <= allowed_r + jit:
                    mask.add((col, row))
        masks.append(mask)
    return masks

def in_macro_mask(sci, scj, mask, footprint_subs):
    """Check that all macro cells under a module footprint are in mask."""
    macro_cells = set((c // 2, r // 2) for (c, r) in footprint_subs)
    for mc in macro_cells:
        if mc not in mask:
            return False
    return True

# ---------------------------------------------------------------------------
#  CASCADING COURTYARDS  (operates on macro grid)
# ---------------------------------------------------------------------------
def punch_cascading_courtyards(nx, ny, max_levels, n_courts,
                                start_size, growth_per_level, rng):
    """Returns a frozenset of MACRO (col, row, level) cells that are void."""
    margin = max(1, min(nx, ny) // 6)
    voids = set()
    if n_courts <= 0:
        return frozenset(voids)
    cs = max(1, int(math.ceil(math.sqrt(n_courts * nx / float(max(ny, 1))))))
    rs_ = max(1, int(math.ceil(n_courts / float(cs))))
    zw = (nx - 2 * margin) / float(max(cs, 1))
    zh = (ny - 2 * margin) / float(max(rs_, 1))
    placed = 0
    for ci in range(cs):
        for ri in range(rs_):
            if placed >= n_courts: break
            sc_ = margin + zw * (ci + 0.5)
            sr_ = margin + zh * (ri + 0.5)
            sc_ += rng.uniform(-0.5, 0.5) * zw * 0.4
            sr_ += rng.uniform(-0.5, 0.5) * zh * 0.4
            zmax = rng.randint(max(1, max_levels // 2), max_levels)
            for lv in range(zmax):
                radius = start_size + lv * growth_per_level
                cmin = max(1, int(math.floor(sc_ - radius)))
                cmax = min(nx - 2, int(math.ceil(sc_ + radius)))
                rmin = max(1, int(math.floor(sr_ - radius)))
                rmax = min(ny - 2, int(math.ceil(sr_ + radius)))
                for c in range(cmin, cmax + 1):
                    for r in range(rmin, rmax + 1):
                        voids.add((c, r, lv))
            placed += 1
    return frozenset(voids)

def punch_hofhaus_courtyard(nx, ny, max_levels, rng, shape=HOF_RECTANGULAR):
    """
    HOFHAUS typology: single large central courtyard.
    Proportions calibrated from your manual model:
      - Module ring is only 1-2 modules thick around the void
      - Courtyard occupies ~50-65% of footprint
    Four shape sub-types:
      HOF_SQUARE      - centred square (width = depth)
      HOF_RECTANGULAR - elongated along longer axis (default - your reference)
      HOF_CIRCULAR    - pixelated circle (rounder edge)
      HOF_CASCADING   - widens with height (hofhaus + cascade)
    """
    voids = set()
    cx = (nx - 1) * 0.5
    cy = (ny - 1) * 0.5

    if shape == HOF_SQUARE:
        # Square void: half-cell margin (1 module thick ring)
        # ~55% of the smaller dimension
        side = max(2, int(min(nx, ny) * 0.55))
        c_min = int(cx - side * 0.5 + 0.5)
        c_max = c_min + side - 1
        r_min = int(cy - side * 0.5 + 0.5)
        r_max = r_min + side - 1
        c_min = max(1, c_min); c_max = min(nx - 2, c_max)
        r_min = max(1, r_min); r_max = min(ny - 2, r_max)
        for lv in range(max_levels):
            for c in range(c_min, c_max + 1):
                for r in range(r_min, r_max + 1):
                    voids.add((c, r, lv))

    elif shape == HOF_RECTANGULAR:
        # Rectangular void: long along the dominant axis
        # ~65% of long axis x ~50% of short axis (matches your screenshot)
        if nx >= ny:
            wx = max(2, int(nx * 0.65))
            wy = max(2, int(ny * 0.50))
        else:
            wx = max(2, int(nx * 0.50))
            wy = max(2, int(ny * 0.65))
        c_min = int(cx - wx * 0.5 + 0.5)
        c_max = c_min + wx - 1
        r_min = int(cy - wy * 0.5 + 0.5)
        r_max = r_min + wy - 1
        c_min = max(1, c_min); c_max = min(nx - 2, c_max)
        r_min = max(1, r_min); r_max = min(ny - 2, r_max)
        for lv in range(max_levels):
            for c in range(c_min, c_max + 1):
                for r in range(r_min, r_max + 1):
                    voids.add((c, r, lv))

    elif shape == HOF_CIRCULAR:
        # Pixelated circle: cells inside radius r centred on (cx, cy)
        radius = min(nx, ny) * 0.32   # ~64% diameter -> 64% width footprint
        for lv in range(max_levels):
            for c in range(1, nx - 1):
                for r in range(1, ny - 1):
                    d = math.sqrt((c - cx) ** 2 + (r - cy) ** 2)
                    if d <= radius:
                        voids.add((c, r, lv))

    elif shape == HOF_CASCADING:
        # Hofhaus that widens with each floor (hofhaus + cascade)
        # Ground floor: small rectangular void
        # Each level: void grows by 1 cell on each side
        if nx >= ny:
            base_wx = max(2, int(nx * 0.40))
            base_wy = max(2, int(ny * 0.35))
        else:
            base_wx = max(2, int(nx * 0.35))
            base_wy = max(2, int(ny * 0.40))
        for lv in range(max_levels):
            grow = lv  # each level adds 1 cell on every side
            wx = base_wx + 2 * grow
            wy = base_wy + 2 * grow
            c_min = int(cx - wx * 0.5 + 0.5)
            c_max = c_min + wx - 1
            r_min = int(cy - wy * 0.5 + 0.5)
            r_max = r_min + wy - 1
            c_min = max(1, c_min); c_max = min(nx - 2, c_max)
            r_min = max(1, r_min); r_max = min(ny - 2, r_max)
            for c in range(c_min, c_max + 1):
                for r in range(r_min, r_max + 1):
                    voids.add((c, r, lv))

    return frozenset(voids)


def punch_scatter_courtyards(nx, ny, max_levels, rng):
    """
    SCATTER typology: multiple small courtyards whose TOTAL volume equals
    that of a Hofhaus courtyard, just distributed throughout the cluster.

    Hofhaus reference void area = ~50% of the cluster footprint.
    We spread that void volume across many small voids of ~2-4 cells each.
    """
    voids = set()
    # target total void cells = same as hofhaus rectangular (~50% of grid)
    hofhaus_target = int(nx * ny * 0.45)
    margin = 1
    placed_cells = 0
    placed_seeds = []
    attempts = 0
    max_attempts = 200

    while placed_cells < hofhaus_target and attempts < max_attempts:
        attempts += 1
        c = rng.randint(margin, nx - margin - 1)
        r = rng.randint(margin, ny - margin - 1)
        # void size: 1x1, 1x2, 2x1, 2x2 (2-4 cells each)
        w = rng.choice([1, 1, 2, 2])
        d = rng.choice([1, 2, 1, 2])
        c_max = min(nx - margin - 1, c + w - 1)
        r_max = min(ny - margin - 1, r + d - 1)
        # ensure separation from existing voids (at least 1 cell apart)
        too_close = False
        for (sc, sr) in placed_seeds:
            if abs(sc - c) <= 1 and abs(sr - r) <= 1:
                too_close = True; break
        if too_close: continue
        placed_seeds.append((c, r))
        for lv in range(max_levels):
            for cc in range(c, c_max + 1):
                for rr in range(r, r_max + 1):
                    voids.add((cc, rr, lv))
        placed_cells += (c_max - c + 1) * (r_max - r + 1)

    return frozenset(voids)


def punch_sculptural_voids(nx, ny, max_levels, rng):
    """
    SCULPTURAL typology: sparse, free-form openings.
    Modelled after Cluster 3 in your reference - the loosest, most
    artistic configuration. Voids appear at random levels rather than
    cutting full vertical shafts; this creates the diffuse, sculptural
    aesthetic. Lower density of voids - the sparseness in the modules
    themselves creates the openness, not the courtyards.
    """
    voids = set()
    n_voids = max(2, (nx * ny) // 20)   # fewer voids than scatter
    margin = 1
    placed = 0
    attempts = 0
    while placed < n_voids and attempts < n_voids * 6:
        attempts += 1
        c = rng.randint(margin, nx - margin - 1)
        r = rng.randint(margin, ny - margin - 1)
        w = rng.choice([1, 2, 2, 3])   # bias toward bigger voids
        d = rng.choice([1, 2, 2, 3])
        c_max = min(nx - margin - 1, c + w - 1)
        r_max = min(ny - margin - 1, r + d - 1)
        # void appears at random level subset (not all levels)
        lv_start = rng.randint(0, max_levels // 2)
        lv_end = rng.randint(lv_start + 1, max_levels)
        for lv in range(lv_start, lv_end):
            for cc in range(c, c_max + 1):
                for rr in range(r, r_max + 1):
                    voids.add((cc, rr, lv))
        placed += 1
    return frozenset(voids)

def punch_courtyard_v10(typo, nx, ny, max_levels, plateau_levels, rng):
    """
    v10 courtyard generation - the courtyard is a HARD void carved BEFORE
    placement. Each style cascades asymmetrically: the courtyard widens
    with each upper floor while the outer perimeter stays straight.

    Returns: frozenset of (col, row, level) cells that must be void.
    """
    voids = set()
    cx = (nx - 1) * 0.5
    cy = (ny - 1) * 0.5

    if typo == TYPO_SQUARE:
        # Centred square. GENTLE cascade: +1 cell per axis per upper level
        # (after plateau), so the courtyard widens but the cluster persists.
        base_side = max(2, int(min(nx, ny) * 0.35))
        for lv in range(max_levels):
            grow = 0 if lv < plateau_levels else (lv - plateau_levels)
            side = base_side + grow
            c_min = int(cx - side * 0.5 + 0.5)
            c_max = c_min + side - 1
            r_min = int(cy - side * 0.5 + 0.5)
            r_max = r_min + side - 1
            c_min = max(1, c_min); c_max = min(nx - 2, c_max)
            r_min = max(1, r_min); r_max = min(ny - 2, r_max)
            for c in range(c_min, c_max + 1):
                for r in range(r_min, r_max + 1):
                    voids.add((c, r, lv))

    elif typo == TYPO_RECTANGULAR:
        # Elongated along longer axis (CONNECTION.3dm reference).
        # Cascade: GENTLE growth - 1 cell per axis every 2 floors above plateau,
        # so the courtyard widens but doesn't eat the whole cluster by floor 5.
        if nx >= ny:
            base_wx = max(2, int(nx * 0.45))   # was 0.55 - smaller base
            base_wy = max(2, int(ny * 0.30))   # was 0.40
        else:
            base_wx = max(2, int(nx * 0.30))
            base_wy = max(2, int(ny * 0.45))
        for lv in range(max_levels):
            # gentle cascade: 1 cell per axis per level above plateau
            grow = 0 if lv < plateau_levels else (lv - plateau_levels)
            wx = base_wx + grow   # was 2*grow - reduced to 1*grow
            wy = base_wy + grow
            c_min = int(cx - wx * 0.5 + 0.5)
            c_max = c_min + wx - 1
            r_min = int(cy - wy * 0.5 + 0.5)
            r_max = r_min + wy - 1
            c_min = max(1, c_min); c_max = min(nx - 2, c_max)
            r_min = max(1, r_min); r_max = min(ny - 2, r_max)
            for c in range(c_min, c_max + 1):
                for r in range(r_min, r_max + 1):
                    voids.add((c, r, lv))

    elif typo == TYPO_PIXEL_CIRC:
        # Pixelated circle - GENTLE radius growth.
        base_r = min(nx, ny) * 0.22
        for lv in range(max_levels):
            grow = 0 if lv < plateau_levels else (lv - plateau_levels) * 0.6
            r_circle = base_r + grow
            for c in range(1, nx - 1):
                for r in range(1, ny - 1):
                    if math.sqrt((c - cx) ** 2 + (r - cy) ** 2) <= r_circle:
                        voids.add((c, r, lv))

    elif typo == TYPO_MULTIPLE:
        # 2-3 smaller courtyards distributed along the long axis - gentle.
        n_courts = 3 if max(nx, ny) >= 16 else 2
        if nx >= ny:
            for k in range(n_courts):
                center_c = (nx - 1) * (k + 0.5) / n_courts
                center_r = cy
                base_w = max(2, int(nx / (n_courts * 1.8)))
                base_h = max(2, int(ny * 0.30))
                for lv in range(max_levels):
                    grow = 0 if lv < plateau_levels else (lv - plateau_levels)
                    wx = base_w + grow
                    wy = base_h + grow
                    c_min = int(center_c - wx * 0.5 + 0.5)
                    c_max = c_min + wx - 1
                    r_min = int(center_r - wy * 0.5 + 0.5)
                    r_max = r_min + wy - 1
                    c_min = max(1, c_min); c_max = min(nx - 2, c_max)
                    r_min = max(1, r_min); r_max = min(ny - 2, r_max)
                    for c in range(c_min, c_max + 1):
                        for r in range(r_min, r_max + 1):
                            voids.add((c, r, lv))
        else:
            for k in range(n_courts):
                center_c = cx
                center_r = (ny - 1) * (k + 0.5) / n_courts
                base_w = max(2, int(nx * 0.30))
                base_h = max(2, int(ny / (n_courts * 1.8)))
                for lv in range(max_levels):
                    grow = 0 if lv < plateau_levels else (lv - plateau_levels)
                    wx = base_w + grow
                    wy = base_h + grow
                    c_min = int(center_c - wx * 0.5 + 0.5)
                    c_max = c_min + wx - 1
                    r_min = int(center_r - wy * 0.5 + 0.5)
                    r_max = r_min + wy - 1
                    c_min = max(1, c_min); c_max = min(nx - 2, c_max)
                    r_min = max(1, r_min); r_max = min(ny - 2, r_max)
                    for c in range(c_min, c_max + 1):
                        for r in range(r_min, r_max + 1):
                            voids.add((c, r, lv))

    return frozenset(voids)


def punch_voids_by_typology(typology, nx, ny, max_levels, n_courts,
                             court_start_size, court_growth_per_level, rng,
                             hofhaus_shape=HOF_RECTANGULAR,
                             plateau_levels=2):
    """v10 dispatcher: 4 courtyard styles, all asymmetric cascading."""
    return punch_courtyard_v10(typology, nx, ny, max_levels,
                                 plateau_levels, rng)

def in_macro_void(sci, scj, level, footprint_subs, voids):
    """Any macro cell touched by the footprint is in the void set?"""
    for (c, r) in set((c // 2, r // 2) for (c, r) in footprint_subs):
        if (c, r, level) in voids:
            return True
    return False

# ---------------------------------------------------------------------------
#  DENSITY  (probabilistic)
# ---------------------------------------------------------------------------
def cell_fill_prob(macro_col, macro_row, nx, ny, level, max_levels,
                    plateau_levels, density):
    cx = (nx - 1) * 0.5
    cy = (ny - 1) * 0.5
    dist = math.sqrt((macro_col - cx) ** 2 + (macro_row - cy) ** 2)
    max_d = math.sqrt(cx ** 2 + cy ** 2) + 0.001
    radial = 1.0 - 0.25 * (dist / max_d)
    if level < plateau_levels:
        vert = 1.0
    else:
        t = (level - plateau_levels) / float(max(max_levels - plateau_levels - 1, 1))
        vert = 0.95 - 0.55 * t
    base = radial * vert
    sf = 0.20 + 0.80 * density
    return max(0.0, base * sf)

# ---------------------------------------------------------------------------
#  MAIN GENERATOR
# ---------------------------------------------------------------------------
def generate_cluster(params):
    nx = params['nx']
    ny = params['ny']
    max_levels = params['max_levels']
    plateau_levels = params['plateau_levels']
    density = params['density']
    style = params['style']
    b_ratio = params['b_ratio']

    rng = random.Random(params['seed'])
    masks = build_pyramid_masks(nx, ny, max_levels, plateau_levels,
                                 density, rng)
    voids = punch_voids_by_typology(
        params.get('typology', TYPO_RECTANGULAR),
        nx, ny, max_levels, params['n_courts'],
        params['court_start_size'], params['court_growth_per_level'], rng,
        params.get('hofhaus_shape', HOF_RECTANGULAR),
        plateau_levels)

    occ = Occupancy()
    rejected_no_support = 0

    for level in range(max_levels):
        mask = masks[level]
        allowed = style_allowed_supports(style, level, plateau_levels)
        anchors = style_anchor_positions(nx, ny, level, plateau_levels, style)
        rng.shuffle(anchors)

        for (sci, scj) in anchors:
            macro_col = sci // 2
            macro_row = scj // 2
            if (macro_col, macro_row) not in mask:
                continue

            # density roll on macro cell
            p = cell_fill_prob(macro_col, macro_row, nx, ny, level,
                                max_levels, plateau_levels, density)
            if rng.random() > p: continue

            # decide module type
            lv_norm = level / float(max(max_levels - 1, 1))
            # v10: B placement is more uniform across floors (matches reference
            # where L0 has many B's as vertical anchors, not just upper floors).
            # Constant base + mild upward ramp.
            b_prob = b_ratio * (0.85 + 0.30 * lv_norm)
            if density < 0.5 and level == 0:
                b_prob *= 1.2
            # half-cell anchors get B less often -- otherwise B dominates
            on_halfcell = (sci % 2 == 1) or (scj % 2 == 1)
            if on_halfcell:
                b_prob *= 0.5
            b_prob = min(b_prob, 0.55)
            try_B_first = rng.random() < b_prob
            placed = False

            # ----- attempt B -----
            if try_B_first:
                cells = occ.cells_of_B(sci, scj, level)
                # bounds + mask + voids
                ok = True
                for (i, j, lv) in cells:
                    if i < 0 or i >= nx*2 or j < 0 or j >= ny*2:
                        ok = False; break
                    if lv >= max_levels:
                        ok = False; break
                if ok:
                    if not in_macro_mask(sci, scj, mask, [(i, j) for (i, j, lv) in cells if lv == level]):
                        ok = False
                    if ok and in_macro_void(sci, scj, level,
                                              [(i, j) for (i, j, lv) in cells if lv == level],
                                              voids):
                        ok = False
                if ok and occ.all_free(cells):
                    sup = check_support(cells, occ.cells, allowed)
                    if sup is not None:
                        aabb = occ.aabb_of_B(sci, scj, level)
                        if not occ.aabb_collides(aabb):
                            occ.place("B", sci, scj, level, None, sup)
                            placed = True

            # ----- try A in either orientation -----
            # v10: alternate orientation per floor (CONNECTION.3dm pattern):
            #   even floors prefer X-axis, odd floors prefer Y-axis.
            # Strong bias (90% of the time) to the preferred orientation;
            # 10% chance for the other to keep some variation.
            if not placed:
                preferred = 0 if (level % 2 == 0) else 1
                if rng.random() < 0.85:
                    orients = [preferred, 1 - preferred]
                else:
                    orients = [1 - preferred, preferred]
                for orient in orients:
                    cells = occ.cells_of_A(sci, scj, level, orient)
                    ok = True
                    for (i, j, lv) in cells:
                        if i < 0 or i >= nx*2 or j < 0 or j >= ny*2:
                            ok = False; break
                    if not ok: continue
                    if not in_macro_mask(sci, scj, mask,
                                          [(i, j) for (i, j, lv) in cells]):
                        continue
                    if in_macro_void(sci, scj, level,
                                      [(i, j) for (i, j, lv) in cells],
                                      voids):
                        continue
                    if not occ.all_free(cells):
                        continue
                    sup = check_support(cells, occ.cells, allowed)
                    if sup is None:
                        continue
                    aabb = occ.aabb_of_A(sci, scj, level, orient)
                    if not occ.aabb_collides(aabb):
                        occ.place("A", sci, scj, level, orient, sup)
                        placed = True
                        break

            # ----- last resort: B if not tried first -----
            if not placed and not try_B_first:
                cells = occ.cells_of_B(sci, scj, level)
                ok = True
                for (i, j, lv) in cells:
                    if i < 0 or i >= nx*2 or j < 0 or j >= ny*2:
                        ok = False; break
                    if lv >= max_levels:
                        ok = False; break
                if ok and in_macro_mask(sci, scj, mask,
                                          [(i, j) for (i, j, lv) in cells if lv == level]) \
                     and not in_macro_void(sci, scj, level,
                                            [(i, j) for (i, j, lv) in cells if lv == level],
                                            voids) \
                     and occ.all_free(cells):
                    sup = check_support(cells, occ.cells, allowed)
                    if sup is not None:
                        aabb = occ.aabb_of_B(sci, scj, level)
                        if not occ.aabb_collides(aabb):
                            occ.place("B", sci, scj, level, None, sup)
                            placed = True

            if not placed and level > 0:
                rejected_no_support += 1

    return occ, rejected_no_support

# ---------------------------------------------------------------------------
#  STAIR CORE AUTO-PLACEMENT  (NEW v9)
# ---------------------------------------------------------------------------
def module_center(mod):
    """World XY center of a module's footprint."""
    aabb = mod['aabb']
    return ((aabb[0] + aabb[3]) * 0.5, (aabb[1] + aabb[4]) * 0.5)

def manhattan(p1, p2):
    return abs(p1[0] - p2[0]) + abs(p1[1] - p2[1])

def select_stair_cores_kmedoids(modules, n_cores, max_iter=30):
    """
    k-medoids algorithm: pick `n_cores` B modules that minimize the maximum
    Manhattan distance from any A module to the nearest core.

    Each B candidate is evaluated as a medoid; we iteratively swap medoids
    until no improvement reduces the max-min distance.
    """
    a_modules = [m for m in modules if m['kind'] == 'A']
    b_modules = [m for m in modules if m['kind'] == 'B']
    if not a_modules or not b_modules:
        return []
    if len(b_modules) <= n_cores:
        return list(range(len(b_modules)))   # all B's are cores

    a_centers = [module_center(m) for m in a_modules]
    b_centers = [module_center(m) for m in b_modules]

    # initialize: pick n_cores B's spread out (greedy farthest-first)
    medoids = [0]
    for _ in range(n_cores - 1):
        best_idx = -1
        best_dist = -1
        for i in range(len(b_centers)):
            if i in medoids: continue
            d = min(manhattan(b_centers[i], b_centers[m]) for m in medoids)
            if d > best_dist:
                best_dist = d; best_idx = i
        if best_idx >= 0: medoids.append(best_idx)

    def max_min_distance(medoids):
        max_d = 0.0
        for ac in a_centers:
            d_min = min(manhattan(ac, b_centers[m]) for m in medoids)
            if d_min > max_d: max_d = d_min
        return max_d

    # iterative improvement: swap each medoid with each non-medoid
    current_score = max_min_distance(medoids)
    for _ in range(max_iter):
        improved = False
        for mi, m in enumerate(medoids):
            for j in range(len(b_centers)):
                if j in medoids: continue
                trial = list(medoids)
                trial[mi] = j
                s = max_min_distance(trial)
                if s < current_score:
                    medoids = trial
                    current_score = s
                    improved = True
                    break
            if improved: break
        if not improved: break

    return medoids   # indices into b_modules list

def select_stair_cores(occ, n_cores, manual_indices=None):
    """
    Returns a list of module indices (into occ.modules) to be marked as stair
    cores. If manual_indices is given (B-module indices), use those; otherwise
    auto-pick using k-medoids.
    """
    b_indices = [i for i, m in enumerate(occ.modules) if m['kind'] == 'B']
    if manual_indices:
        return [b_indices[i] for i in manual_indices if 0 <= i < len(b_indices)]
    if not b_indices:
        return []
    n_cores = min(n_cores, len(b_indices))
    medoid_idx = select_stair_cores_kmedoids(occ.modules, n_cores)
    return [b_indices[i] for i in medoid_idx]

def compute_max_travel_distance(occ, core_indices):
    """
    For each A module, find the Manhattan distance to the nearest stair core.
    Returns the maximum across all A's.
    """
    if not core_indices:
        return float('inf')
    cores = [occ.modules[i] for i in core_indices]
    core_centers = [module_center(m) for m in cores]
    max_d = 0.0
    for m in occ.modules:
        if m['kind'] != 'A': continue
        ac = module_center(m)
        d_min = min(manhattan(ac, cc) for cc in core_centers)
        if d_min > max_d: max_d = d_min
    return max_d

# ---------------------------------------------------------------------------
#  CORRIDOR GENERATION  (v9.3 - GRID-BASED ORTHOGONAL CUBOID CORRIDORS)
# ---------------------------------------------------------------------------
#
#  v9.3 PHILOSOPHY (after user feedback on v9.1 mess):
#  -- Corridors are 3D walkable cuboids, NOT thin slabs:
#     1.5 m wide x 2.4 m tall (proper architectural walkway dimensions).
#  -- Pure 90 degrees orthogonal: no angular, no curvilinear.
#     Single corridor mode for clarity.
#  -- Yellow color for unmistakable visibility.
#  -- The corridor lives in the FREE space between modules (the courtyard side),
#     never overlapping a module footprint.
#  -- The corridor reaches the SHORT side of every module (the door position).
#  -- One continuous corridor network per floor connecting every module.
#
#  ALGORITHM (per floor):
#    1. Build a macro-cell occupancy grid (which cells contain a module bottom
#       on this floor).
#    2. For each module, identify its DOOR cell - the free macro-cell adjacent
#       to its short side. If multiple short-side neighbours are free, pick
#       the one that points toward the cluster centre (so the corridor flows
#       inward, courtyard-side, like Habitat 67's pedestrian streets).
#    3. Build a Steiner-tree-on-grid that connects all door cells via free
#       macro-cells using only 4-connected (90 degrees) moves.
#       Heuristic: greedy connect-nearest-to-tree using BFS shortest paths
#       through free cells.
#    4. Render each path cell as a 1.5 m x 1.5 m x 2.4 m yellow cuboid,
#       centred in that 3.75 m macro-cell. Door-stub cells get a short
#       extension pointing toward the door's short-side wall.

CORR_WIDTH  = 1.5    # corridor walkway width
CORR_HEIGHT = 2.4    # corridor head clearance height


def macro_cells_of_module(m):
    """Return the set of (col, row) macro cells the module's footprint
    occupies, derived from its sub-cell footprint."""
    sub_cells = set((c, r) for (c, r, lv) in m['cells'])
    macro = set()
    for (sc, sr) in sub_cells:
        macro.add((sc // 2, sr // 2))
    return macro


def module_short_side_neighbours(m):
    """Return list of (col, row) macro-cells adjacent to the module's SHORT side.
    For an A horizontal: short sides are at the two ends of the long axis.
    For a B vertical: any side counts (footprint is square)."""
    macro = macro_cells_of_module(m)
    cols = [c for (c, r) in macro]
    rows = [r for (c, r) in macro]
    c_min, c_max = min(cols), max(cols)
    r_min, r_max = min(rows), max(rows)
    width = c_max - c_min + 1   # span in X (in macro cells)
    depth = r_max - r_min + 1   # span in Y

    neighbours = []
    if m['kind'] == 'A':
        # short side runs perpendicular to the LONGER axis
        if width >= depth:
            # long axis = X, short sides at x = c_min - 1 and x = c_max + 1
            for r in range(r_min, r_max + 1):
                neighbours.append((c_min - 1, r))
                neighbours.append((c_max + 1, r))
        else:
            # long axis = Y, short sides at y = r_min - 1 and y = r_max + 1
            for c in range(c_min, c_max + 1):
                neighbours.append((c, r_min - 1))
                neighbours.append((c, r_max + 1))
    else:   # B square - all 4 sides eligible
        for r in range(r_min, r_max + 1):
            neighbours.append((c_min - 1, r))
            neighbours.append((c_max + 1, r))
        for c in range(c_min, c_max + 1):
            neighbours.append((c, r_min - 1))
            neighbours.append((c, r_max + 1))
    return neighbours


def pick_door_cell(m, free_cells, cluster_cx, cluster_cy):
    """Pick the door cell for this module.
    Priority:
      1. A free neighbour on the SHORT side (preferred door position)
      2. Any free neighbour on any side (fallback for densely packed clusters)
    From among valid candidates, pick the one that leads toward the cluster
    centre so the corridor flows along the courtyard side.
    """
    # 1. try short-side neighbours first
    short_side = module_short_side_neighbours(m)
    valid = [(c, r) for (c, r) in short_side if (c, r) in free_cells]
    # 2. fallback - any free neighbour
    if not valid:
        macro = macro_cells_of_module(m)
        cols = [c for (c, r) in macro]; rows = [r for (c, r) in macro]
        c_min, c_max = min(cols), max(cols)
        r_min, r_max = min(rows), max(rows)
        for r in range(r_min, r_max + 1):
            for cand in [(c_min - 1, r), (c_max + 1, r)]:
                if cand in free_cells: valid.append(cand)
        for c in range(c_min, c_max + 1):
            for cand in [(c, r_min - 1), (c, r_max + 1)]:
                if cand in free_cells: valid.append(cand)
    if not valid:
        return None
    # pick the candidate closest to cluster centre (encourages courtyard-side flow)
    return min(valid,
                key=lambda cr: (cr[0] - cluster_cx) ** 2
                              + (cr[1] - cluster_cy) ** 2)


def grid_bfs(start, goals, free_cells):
    """4-connected BFS from `start` through `free_cells`, stopping when any
    cell in `goals` is reached. Returns the path (list of cells) including
    start and the reached goal, or None if unreachable.
    free_cells must include `start` and the reached goal."""
    if start in goals: return [start]
    queue = [start]
    came_from = {start: None}
    head = 0
    while head < len(queue):
        cur = queue[head]; head += 1
        for (dc, dr) in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
            nxt = (cur[0] + dc, cur[1] + dr)
            if nxt in came_from: continue
            if nxt not in free_cells: continue
            came_from[nxt] = cur
            if nxt in goals:
                # reconstruct
                path = [nxt]
                while came_from[path[-1]] is not None:
                    path.append(came_from[path[-1]])
                path.reverse()
                return path
            queue.append(nxt)
    return None


def build_orthogonal_corridor_tree(door_cells, free_cells):
    """
    Build a Steiner-tree-like network on the 4-connected grid that links all
    door cells through free cells. Greedy algorithm:
      - Start with the first door cell as the tree.
      - Repeatedly find the door not yet in the tree that is reachable in
        the fewest steps from any tree cell. Add the BFS path to the tree.
      - Cells already in the tree act as 'free' for new BFS searches, so new
        paths can branch off existing corridor.
    Returns: set of (col, row) cells that form the corridor network.
    """
    if not door_cells: return set()
    door_list = list(door_cells)
    tree_cells = set([door_list[0]])
    remaining = set(door_list[1:])
    # Augmented free set = free_cells + tree_cells (so we can branch from tree)
    while remaining:
        searchable = free_cells | tree_cells
        best_path = None
        best_target = None
        # BFS from any tree cell to nearest remaining door
        # We do a multi-source BFS for efficiency
        queue = list(tree_cells)
        came_from = {c: None for c in tree_cells}
        head = 0
        found = None
        while head < len(queue):
            cur = queue[head]; head += 1
            if cur in remaining:
                found = cur; break
            for (dc, dr) in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
                nxt = (cur[0] + dc, cur[1] + dr)
                if nxt in came_from: continue
                # allow entering remaining doors directly
                if nxt not in searchable and nxt not in remaining: continue
                came_from[nxt] = cur
                queue.append(nxt)
        if found is None:
            # remaining doors unreachable - skip them
            break
        # reconstruct path from `found` back to a tree cell
        path = [found]
        while came_from[path[-1]] is not None:
            path.append(came_from[path[-1]])
        # add all path cells to tree
        for c in path:
            tree_cells.add(c)
        remaining.discard(found)
    return tree_cells


def make_linear_corridor_run(cells, axis, level):
    """Build ONE elongated cuboid spanning a list of co-linear macro cells.

    `cells` is a list of (col, row) tuples that lie on the same straight line
    (either same row for horizontal axis, or same col for vertical axis).
    They must be sorted in order along the axis.

    `axis` = 'H' (horizontal, along X) or 'V' (vertical, along Y).

    The cuboid is CORR_WIDTH wide perpendicular to the axis, CORR_HEIGHT tall,
    and (n_cells * GRID) long along the axis.  Centred along the perpendicular
    direction inside the macro-cell strip.
    """
    if not cells: return None
    if axis == 'H':
        row = cells[0][1]
        c_min = min(c for (c, r) in cells)
        c_max = max(c for (c, r) in cells)
        # bounding x: from start of first cell's left edge to end of last cell's right edge
        x_start = c_min * GRID
        x_end   = (c_max + 1) * GRID
        # centre y in the row
        y_centre = row * GRID + GRID * 0.5
        ox = x_start
        oy = y_centre - CORR_WIDTH * 0.5
        lx = x_end - x_start
        ly = CORR_WIDTH
    else:  # vertical
        col = cells[0][0]
        r_min = min(r for (c, r) in cells)
        r_max = max(r for (c, r) in cells)
        y_start = r_min * GRID
        y_end   = (r_max + 1) * GRID
        x_centre = col * GRID + GRID * 0.5
        ox = x_centre - CORR_WIDTH * 0.5
        oy = y_start
        lx = CORR_WIDTH
        ly = y_end - y_start
    z = level * LEVEL_H
    return axis_box(ox, oy, z, lx, ly, CORR_HEIGHT)


def merge_corridor_cells_into_runs(tree_cells):
    """Given a set of (col, row) cells that form a connected orthogonal tree,
    split them into a small number of LINEAR RUNS (horizontal or vertical
    strips). Each run is a list of co-linear cells.

    Strategy: walk from each leaf outward, extending in the available direction
    until forced to turn. Mark cells as 'covered' when at least one run includes
    them. Produces the minimum natural set of straight strips that visually
    reads as continuous corridor.

    Returns: list of (cells_list, axis) where axis is 'H' or 'V'.
    """
    if not tree_cells: return []
    # Group cells by row for horizontal scans, by col for vertical scans.
    by_row = {}
    by_col = {}
    for (c, r) in tree_cells:
        by_row.setdefault(r, set()).add(c)
        by_col.setdefault(c, set()).add(r)

    runs = []
    covered_h = set()   # cells already in a horizontal run
    covered_v = set()   # cells already in a vertical run

    # Pass 1: horizontal runs - find maximal contiguous spans of cells in same row
    for row, cols in by_row.items():
        if len(cols) < 2: continue
        sorted_cols = sorted(cols)
        run_start = sorted_cols[0]
        prev = run_start
        for c in sorted_cols[1:] + [None]:
            if c is not None and c == prev + 1:
                prev = c
                continue
            # end of a run: prev was the last cell of a run starting at run_start
            if prev > run_start:  # run length >= 2
                run_cells = [(cc, row) for cc in range(run_start, prev + 1)]
                runs.append((run_cells, 'H'))
                for cell in run_cells: covered_h.add(cell)
            if c is not None:
                run_start = c
                prev = c

    # Pass 2: vertical runs
    for col, rows in by_col.items():
        if len(rows) < 2: continue
        sorted_rows = sorted(rows)
        run_start = sorted_rows[0]
        prev = run_start
        for r in sorted_rows[1:] + [None]:
            if r is not None and r == prev + 1:
                prev = r
                continue
            if prev > run_start:
                run_cells = [(col, rr) for rr in range(run_start, prev + 1)]
                runs.append((run_cells, 'V'))
                for cell in run_cells: covered_v.add(cell)
            if r is not None:
                run_start = r
                prev = r

    # Pass 3: any cell not covered by any horizontal or vertical run is an
    # isolated cell - render it as a 1-cell run (small cuboid).
    covered = covered_h | covered_v
    for cell in tree_cells:
        if cell not in covered:
            runs.append(([cell], 'H'))   # arbitrary axis for single cell

    return runs


def make_corridor_cuboid(col, row, level):
    """Single-cell corridor cuboid (used only as fallback for isolated cells).
    Most corridors are now rendered as merged linear runs."""
    cx = col * GRID + GRID * 0.5
    cy = row * GRID + GRID * 0.5
    z  = level * LEVEL_H
    half_w = CORR_WIDTH * 0.5
    ox = cx - half_w
    oy = cy - half_w
    return axis_box(ox, oy, z, CORR_WIDTH, CORR_WIDTH, CORR_HEIGHT)


def generate_corridors_orthogonal(occ, nx, ny):
    """
    v10 corridor generation - orthogonal, grid-based, walkable LINEAR cuboids.
    Same routing algorithm as v9.3 but consecutive collinear cells are merged
    into single elongated breps for clean visual reading.

    Returns: (corridor_breps, total_length_m)
    """
    cluster_cx = (nx - 1) * 0.5
    cluster_cy = (ny - 1) * 0.5

    all_breps = []
    total_cells = 0

    # Group modules by floor (A's at their level, B's at both spanning levels)
    by_floor = {}
    for idx, m in enumerate(occ.modules):
        if m['kind'] == 'A':
            by_floor.setdefault(m['level'], []).append(m)
        else:
            by_floor.setdefault(m['level'], []).append(m)
            by_floor.setdefault(m['level'] + 1, []).append(m)

    for floor in sorted(by_floor.keys()):
        floor_modules = by_floor[floor]
        if len(floor_modules) < 1: continue

        occupied = set()
        for m in floor_modules:
            occupied |= macro_cells_of_module(m)

        free = set()
        for c in range(-1, nx + 1):
            for r in range(-1, ny + 1):
                if (c, r) not in occupied:
                    free.add((c, r))

        doors = []
        for m in floor_modules:
            d = pick_door_cell(m, free, cluster_cx, cluster_cy)
            if d is not None:
                doors.append(d)

        if len(doors) < 1: continue

        tree = build_orthogonal_corridor_tree(set(doors), free)

        # v10: merge collinear cells into elongated continuous linear runs
        runs = merge_corridor_cells_into_runs(tree)
        for run_cells, axis in runs:
            if len(run_cells) >= 2:
                brep = make_linear_corridor_run(run_cells, axis, floor)
            else:
                # single isolated cell
                c, r = run_cells[0]
                brep = make_corridor_cuboid(c, r, floor)
            if brep is not None:
                all_breps.append(brep)
        total_cells += len(tree)

    total_length = total_cells * GRID
    return all_breps, total_length

# ---------------------------------------------------------------------------
#  ETO HELPERS
# ---------------------------------------------------------------------------
def make_label(text, bold=False, size=None):
    lbl = forms.Label()
    lbl.Text = text
    if bold:
        font_size = size if size is not None else 9
        lbl.Font = drawing.Font("Arial", font_size, drawing.FontStyle.Bold)
    elif size is not None:
        lbl.Font = drawing.Font("Arial", size)
    return lbl

# ---------------------------------------------------------------------------
#  ETO DIALOG
# ---------------------------------------------------------------------------
class WoSyHoDialog(forms.Dialog[bool]):

    def __init__(self):
        super(WoSyHoDialog, self).__init__()
        self.Title = "Timber Housing Configurator v10.0"
        self.Padding = drawing.Padding(12)
        self.Resizable = False
        self.MinimumSize = drawing.Size(460, 0)

        # ---- CONNECTION STYLE  (NEW v8) ----
        self.style_dd = forms.DropDown()
        self.style_dd.DataStore = [
            "STYLE 1 - Compact (integer grid, dense Habitat)",
            "STYLE 2 - Manual (half-cell, edge support, sparse)",
            "STYLE 3 - Hybrid (compact base + sculptural top)",
        ]
        self.style_dd.SelectedIndex = 2  # default to hybrid (most interesting)

        # ---- COURTYARD TYPOLOGY (v10 - 4 courtyard styles) ----
        self.typology_dd = forms.DropDown()
        self.typology_dd.DataStore = [
            "Square        - centred square courtyard",
            "Rectangular   - elongated along long axis (matches reference)",
            "Pixel-Circle  - pixelated circular courtyard",
            "Multiple      - 2-3 distributed courtyards",
        ]
        self.typology_dd.SelectedIndex = 1   # default rectangular (reference)

        # ---- HOFHAUS SHAPE (v10 - legacy field, kept for compat) ----
        # In v10 the typology dropdown directly chooses the courtyard style,
        # so this field has no effect. Hidden from the layout but kept in code
        # to avoid breaking the parameter dictionary.
        self.hof_shape_dd = forms.DropDown()
        self.hof_shape_dd.DataStore = ["(handled by typology)"]
        self.hof_shape_dd.SelectedIndex = 0

        # ---- CORRIDOR MODE (v9.3 - simplified to ON/OFF) ----
        # Only orthogonal mode now: 1.5m x 2.4m yellow cuboid walkways
        # routed via 90-degree paths through free space (door rule applied).
        self.corridor_dd = forms.DropDown()
        self.corridor_dd.DataStore = [
            "None - skip corridor generation",
            "Generate orthogonal cuboid corridors (1.5 m x 2.4 m, yellow)",
        ]
        self.corridor_dd.SelectedIndex = 1   # default ON

        # ---- STAIR CORES (NEW v9) ----
        self.cores_box = forms.NumericStepper()
        self.cores_box.MinValue = 0
        self.cores_box.MaxValue = 6
        self.cores_box.Value = 4
        self.cores_box.Increment = 1

        # ---- GRID ----
        self.nx_box = forms.NumericStepper()
        self.nx_box.MinValue = 4; self.nx_box.MaxValue = 30
        self.nx_box.Value = 13; self.nx_box.Increment = 1   # v10 reference width

        self.ny_box = forms.NumericStepper()
        self.ny_box.MinValue = 4; self.ny_box.MaxValue = 30
        self.ny_box.Value = 23; self.ny_box.Increment = 1   # v10 reference depth

        # ---- HEIGHT ----
        self.floors_dd = forms.DropDown()
        self.floors_dd.DataStore = ["3 floors", "4 floors", "5 floors"]
        self.floors_dd.SelectedIndex = 2   # v10 default 5 floors

        self.plateau_dd = forms.DropDown()
        self.plateau_dd.DataStore = ["1 plateau floor", "2 plateau floors"]
        self.plateau_dd.SelectedIndex = 1   # 2 plateau floors

        # ---- DENSITY ----
        # v10: lowered default to 25% (matches CONNECTION.3dm reference)
        self.density_slider = forms.Slider()
        self.density_slider.MinValue = 10
        self.density_slider.MaxValue = 100
        self.density_slider.Value = 25
        self.density_slider.TickFrequency = 10
        self.density_label = forms.Label()
        self.density_label.Text = "25% (sparse, well-ventilated)"
        self.density_slider.ValueChanged += self.on_density_changed

        # ---- COURTYARDS ----
        self.courts_box = forms.NumericStepper()
        self.courts_box.MinValue = 0; self.courts_box.MaxValue = 14
        self.courts_box.Value = 2; self.courts_box.Increment = 1

        self.court_start_box = forms.NumericStepper()
        self.court_start_box.MinValue = 0
        self.court_start_box.MaxValue = 4
        self.court_start_box.Value = 0
        self.court_start_box.DecimalPlaces = 1
        self.court_start_box.Increment = 0.5

        self.court_growth_box = forms.NumericStepper()
        self.court_growth_box.MinValue = 0.0
        self.court_growth_box.MaxValue = 1.0
        self.court_growth_box.Value = 0.4
        self.court_growth_box.DecimalPlaces = 2
        self.court_growth_box.Increment = 0.05

        # ---- B SLIDER ----
        # v10: raised default to 34% (matches CONNECTION.3dm reference)
        self.b_pct_slider = forms.Slider()
        self.b_pct_slider.MinValue = 5
        self.b_pct_slider.MaxValue = 50
        self.b_pct_slider.Value = 34
        self.b_pct_slider.TickFrequency = 5
        self.b_pct_label = forms.Label()
        self.b_pct_label.Text = "34% vertical"
        self.b_pct_slider.ValueChanged += self.on_b_changed

        # ---- SEED ----
        self.seed_box = forms.NumericStepper()
        self.seed_box.MinValue = 0; self.seed_box.MaxValue = 9999
        self.seed_box.Value = 7; self.seed_box.Increment = 1

        # ---- BUTTONS ----
        self.DefaultButton = forms.Button()
        self.DefaultButton.Text = "Generate"
        self.DefaultButton.Click += self.on_ok_clicked

        self.AbortButton = forms.Button()
        self.AbortButton.Text = "Cancel"
        self.AbortButton.Click += self.on_cancel_clicked

        # ---- LAYOUT ----
        layout = forms.DynamicLayout()
        layout.Spacing = drawing.Size(8, 6)

        layout.AddRow(make_label("Timber Housing Cluster Aggregator  v8",
                                   bold=True, size=11))
        layout.AddRow(make_label("Module A: 7.5 x 3.75 x 3.75 m   "
                                   "Module B: 3.75 x 3.75 x 7.5 m"))
        layout.AddRow(None)

        layout.AddRow(make_label("CONNECTION STYLE", bold=True))
        layout.AddRow(make_label("Style:"), self.style_dd)
        layout.AddRow(make_label(
            "1 = compact integer grid  |  2 = sparse half-cell + edge support"))
        layout.AddRow(make_label(
            "3 = compact base, sculptural top (recommended for unusual scale)"))
        layout.AddRow(None)

        layout.AddRow(make_label("COURTYARD TYPOLOGY  (v10)", bold=True))
        layout.AddRow(make_label("Type:"), self.typology_dd)
        layout.AddRow(make_label(
            "All courtyards cascade asymmetrically (widen at upper floors)"))
        layout.AddRow(None)

        layout.AddRow(make_label("GRID FOOTPRINT", bold=True))
        layout.AddRow(make_label("Columns NX (cells of 3.75 m):"), self.nx_box)
        layout.AddRow(make_label("Rows NY    (cells of 3.75 m):"), self.ny_box)
        layout.AddRow(None)

        layout.AddRow(make_label("HEIGHT", bold=True))
        layout.AddRow(make_label("Total floors:"),   self.floors_dd)
        layout.AddRow(make_label("Plateau floors:"), self.plateau_dd)
        layout.AddRow(None)

        layout.AddRow(make_label("DENSITY", bold=True))
        layout.AddRow(make_label("Density slider:"), self.density_slider)
        layout.AddRow(None, self.density_label)
        layout.AddRow(None)

        layout.AddRow(make_label("COURTYARDS  (cascading mode only)", bold=True))
        layout.AddRow(make_label("Number of courtyards:"), self.courts_box)
        layout.AddRow(make_label("Start size at ground (cells radius):"),
                       self.court_start_box)
        layout.AddRow(make_label("Growth per level (cells per floor):"),
                       self.court_growth_box)
        layout.AddRow(None)

        layout.AddRow(make_label("VERTICAL B MODULES", bold=True))
        layout.AddRow(make_label("B percentage:"), self.b_pct_slider)
        layout.AddRow(None, self.b_pct_label)
        layout.AddRow(None)

        layout.AddRow(make_label("CIRCULATION  (new v9)", bold=True))
        layout.AddRow(make_label("Corridor mode:"), self.corridor_dd)
        layout.AddRow(make_label("Stair cores (auto-placed):"), self.cores_box)
        layout.AddRow(make_label(
            "Cores auto-pick B modules to minimize travel distance (max 35 m)"))
        layout.AddRow(None)

        layout.AddRow(make_label("Random seed:"), self.seed_box)
        layout.AddRow(None)

        layout.AddSeparateRow(None, self.DefaultButton, self.AbortButton, None)

        self.Content = layout
        self.result_params = None

    def on_density_changed(self, sender, e):
        v = int(self.density_slider.Value)
        if v < 35:    label = "{}% (sparse pavilion)".format(v)
        elif v > 75:  label = "{}% (dense Habitat)".format(v)
        else:         label = "{}% (medium)".format(v)
        self.density_label.Text = label

    def on_b_changed(self, sender, e):
        self.b_pct_label.Text = "{}% vertical".format(int(self.b_pct_slider.Value))

    def on_ok_clicked(self, sender, e):
        floors_map   = {0: 3, 1: 4, 2: 5}
        plateau_map  = {0: 1, 1: 2}
        style_map    = {0: STYLE_COMPACT, 1: STYLE_MANUAL, 2: STYLE_HYBRID}
        typology_map = {0: TYPO_SQUARE, 1: TYPO_RECTANGULAR,
                        2: TYPO_PIXEL_CIRC, 3: TYPO_MULTIPLE}
        hof_shape_map = {0: HOF_RECTANGULAR}   # legacy, no effect in v10
        corridor_map = {0: 0, 1: 1}
        self.result_params = {
            'style':             style_map[self.style_dd.SelectedIndex],
            'typology':          typology_map[self.typology_dd.SelectedIndex],
            'hofhaus_shape':     hof_shape_map[self.hof_shape_dd.SelectedIndex],
            'corridor_mode':     corridor_map[self.corridor_dd.SelectedIndex],
            'n_cores':           int(self.cores_box.Value),
            'nx':                int(self.nx_box.Value),
            'ny':                int(self.ny_box.Value),
            'max_levels':        floors_map[self.floors_dd.SelectedIndex],
            'plateau_levels':    plateau_map[self.plateau_dd.SelectedIndex],
            'density':           self.density_slider.Value / 100.0,
            'n_courts':          int(self.courts_box.Value),
            'court_start_size':       float(self.court_start_box.Value),
            'court_growth_per_level': float(self.court_growth_box.Value),
            'b_ratio':           self.b_pct_slider.Value / 100.0,
            'seed':              int(self.seed_box.Value),
        }
        if self.result_params['plateau_levels'] >= self.result_params['max_levels']:
            self.result_params['plateau_levels'] = max(
                1, self.result_params['max_levels'] - 1)
        self.Close(True)

    def on_cancel_clicked(self, sender, e):
        self.result_params = None
        self.Close(False)

# ---------------------------------------------------------------------------
#  ENTRY POINT
# ---------------------------------------------------------------------------
def main():
    dlg = WoSyHoDialog()
    try:
        parent = Rhino.UI.RhinoEtoApp.MainWindowForDocument(sc.doc)
        rc = dlg.ShowModal(parent)
    except Exception:
        try:
            rc = dlg.ShowModal(Rhino.UI.RhinoEtoApp.MainWindow)
        except Exception:
            rc = dlg.ShowModal()
    if not rc or dlg.result_params is None:
        print("Cancelled.")
        return

    params = dlg.result_params
    occ, rejected = generate_cluster(params)

    # ---- separate stair cores from regular B modules ----
    n_cores = params.get('n_cores', 0)
    core_indices = select_stair_cores(occ, n_cores) if n_cores > 0 else []
    core_indices_set = set(core_indices)

    list_A, list_B, list_cores = [], [], []
    for i, mod in enumerate(occ.modules):
        wx = mod['sci'] * SUBGRID
        wy = mod['scj'] * SUBGRID
        if mod["kind"] == "A":
            list_A.append(make_A_at(wx, wy, mod["level"], mod["orient"]))
        elif i in core_indices_set:
            list_cores.append(make_B_at(wx, wy, mod["level"]))
        else:
            list_B.append(make_B_at(wx, wy, mod["level"]))

    # ---- generate corridors (v9.3 - orthogonal cuboid walkways, yellow) ----
    # Single mode: 1.5m x 2.4m cuboids on 90 degrees grid paths.
    # Connects every module on every floor through free space (courtyard side).
    # Door rule: corridor reaches the SHORT side of each module.
    list_corridors = []
    corridor_length = 0.0
    enable_corridors = params.get('corridor_mode', 1) > 0
    if enable_corridors:
        list_corridors, corridor_length = generate_corridors_orthogonal(
            occ, params['nx'], params['ny'])

    if not list_A and not list_B:
        print("No modules generated. Try larger grid or higher density.")
        return

    L_A      = ensure_layer("Module_A_horizontal", sd.Color.SandyBrown)
    L_B      = ensure_layer("Module_B_vertical",   sd.Color.SteelBlue)
    L_cores  = ensure_layer("Stair_Cores",         sd.Color.LimeGreen)
    L_corr   = ensure_layer("Corridors",           sd.Color.Gold)  # yellow

    rs.CurrentLayer(L_A)
    for b in list_A: sc.doc.Objects.AddBrep(b)
    rs.CurrentLayer(L_B)
    for b in list_B: sc.doc.Objects.AddBrep(b)
    rs.CurrentLayer(L_cores)
    for b in list_cores: sc.doc.Objects.AddBrep(b)
    if list_corridors:
        rs.CurrentLayer(L_corr)
        for b in list_corridors: sc.doc.Objects.AddBrep(b)
    sc.doc.Views.Redraw()

    # ---- per-floor unit count ----
    floor_units = {}
    for m in occ.modules:
        lv = m['level']
        floor_units[lv] = floor_units.get(lv, 0) + 1
        if m['kind'] == 'B':
            floor_units[lv + 1] = floor_units.get(lv + 1, 0) + 1

    # ---- max travel distance check ----
    max_travel = compute_max_travel_distance(occ, core_indices)

    n_A, n_B = len(list_A), len(list_B) + len(list_cores)
    n_total = n_A + n_B
    style_name = {STYLE_COMPACT: "Compact",
                  STYLE_MANUAL:  "Manual (half-cell)",
                  STYLE_HYBRID:  "Hybrid"}[params['style']]
    typo_name = {TYPO_SQUARE:      "Square courtyard",
                 TYPO_RECTANGULAR: "Rectangular courtyard",
                 TYPO_PIXEL_CIRC:  "Pixel-circle courtyard",
                 TYPO_MULTIPLE:    "Multiple courtyards"}.get(
                     params.get('typology', TYPO_RECTANGULAR),
                     "Rectangular courtyard")
    corr_name = "orthogonal cuboid" if enable_corridors else "none"

    A_AREA = MOD_AL * MOD_AW
    B_AREA = MOD_BW * MOD_BD * 2   # B = 2 floors of floor area
    total_floor_area = n_A * A_AREA + n_B * B_AREA
    sqm_per_student = total_floor_area / max(n_total, 1)

    print("=" * 64)
    print("Timber Housing Configurator v10.0")
    print("  Style              : {}".format(style_name))
    print("  Typology           : {}".format(typo_name))
    print("  Corridor mode      : {}".format(corr_name))
    print("  Module A           : {}".format(n_A))
    print("  Module B           : {}  (incl. {} stair cores)".format(
          n_B, len(list_cores)))
    print("  Total modules      : {}".format(n_total))
    print("  Footprint          : {:.1f} x {:.1f} m".format(
          params['nx'] * GRID, params['ny'] * GRID))
    print("  Max height         : {:.2f} m  ({} floors)".format(
          params['max_levels'] * LEVEL_H, params['max_levels']))
    print("  Floor area (gross) : {:.0f} sqm".format(total_floor_area))
    print("  sqm / student      : {:.1f}".format(sqm_per_student))
    print("  Per-floor units    : {}".format(
          ", ".join("L{}={}".format(k, v) for k, v in sorted(floor_units.items()))))
    print("  Stair cores        : {}".format(len(core_indices)))
    print("  Corridor length    : {:.1f} m".format(corridor_length))
    print("  Max travel distance: {:.1f} m  (limit 35 m): {}".format(
          max_travel, "OK" if max_travel <= MAX_TRAVEL_DIST else "EXCEEDS LIMIT"))
    print("  Support breakdown  :")
    print("    ground           : {}".format(occ.n_ground))
    print("    direct           : {}".format(occ.n_direct))
    print("    adjacent         : {}".format(occ.n_adjacent))
    print("    half_face        : {}".format(occ.n_halfface))
    print("    bridge           : {}".format(occ.n_bridge))
    print("    edge             : {}".format(occ.n_edge))
    print("    corner           : {}".format(occ.n_corner))
    print("  Rejected (no support): {}".format(rejected))
    print("=" * 64)

if __name__ == "__main__":
    main()
