"""
================================================================================
Parametric Timber Student Housing
     SINGLE CLUSTER  |  Multi-Courtyard  |  Habitat-'67 Aggregation
                    STANDALONE RHINO PYTHON  (v3.0)
================================================================================

ONE dense mass grows from a 3D occupancy grid with:
  ▸ Stepped pyramid profile  — wide plateau base, tapers ruggedly to top
  ▸ Multiple internal sky-courts punched through the mass (vertical voids)
  ▸ Mix of Module A (horizontal) and Module B (vertical towers)
  ▸ Habitat-'67 cantilevers: upper modules lean outward from centre
  ▸ Alternating X / Y orientation for Module A → cross-shaped clusters

MODULE DIMENSIONS (exact, as specified):
  Module A (horizontal) : 5.0m L × 3.5m W × 3.5m H
  Module B (vertical)   : 3.5m W × 3.5m D × 5.0m H  ← taller than 1 floor

AGGREGATION LOGIC:
  1. Tile the area with 3.5 × 3.5 m grid cells.
  2. Per level apply a "shrinking pyramid" mask — level 0 = full grid,
     each higher level steps back slightly inward (irregular, seeded).
  3. Punch N courtyard voids through the mass — each void is 1–2 cells wide
     and rises 1 to (max_floors-1) levels, creating Habitat-style sky-courts.
  4. Fill occupied cells with A or B, assigning B more often at upper levels
     so vertical "tower" elements poke above the horizontal mass.
  5. Apply random outward cantilever offsets (0–cant_max m) on upper levels
     so modules lean beyond the floor below (Habitat stepping).

USAGE:
  1. In Rhino: _RunPythonScript → select this file
  2. Answer prompts (press Enter for defaults shown in brackets)
  3. Geometry bakes to:
       WoSyHo::Module_A_horizontal   (sandy brown)
       WoSyHo::Module_B_vertical     (steel blue)

QUICK-START DEFAULTS (gives a good ~4-storey cluster):
  NX = 10, NY = 10, Floors = 4, Courts = 5,
  B% = 25, Cantilever = 0.8 m, Seed = 7
================================================================================
"""

import rhinoscriptsyntax as rs
import scriptcontext as sc
import Rhino.Geometry as rg
import System.Drawing as sd
import random
import math

# ═══════════════════════════════════════════════════════════════
#  MODULE & GRID CONSTANTS  (do NOT change — keeps your brief)
# ═══════════════════════════════════════════════════════════════
MOD_AL  = 5.0    # A: long side  (m)
MOD_AW  = 3.5    # A: short side (m)  ← also = grid cell size
MOD_AH  = 3.5    # A: height     (m)  ← also = 1 floor

MOD_BW  = 3.5    # B: width  (m)
MOD_BD  = 3.5    # B: depth  (m)
MOD_BH  = 5.0    # B: height (m)  ← taller than 1 level → creates terrace gap

GRID    = 3.5    # grid cell size (= module short dim)
LEVEL_H = 3.5    # floor-to-floor height


# ═══════════════════════════════════════════════════════════════
#  LAYER UTILITIES
# ═══════════════════════════════════════════════════════════════
def ensure_layer(name, color):
    parent = "WoSyHo"
    full   = parent + "::" + name
    if not rs.IsLayer(parent):
        rs.AddLayer(parent)
    if not rs.IsLayer(full):
        rs.AddLayer(full, color)
    return full


# ═══════════════════════════════════════════════════════════════
#  GEOMETRY BUILDERS
# ═══════════════════════════════════════════════════════════════
def axis_box(ox, oy, oz, lx, ly, lz):
    """Return a Brep box from lower-corner (ox,oy,oz) with extent lx,ly,lz."""
    plane = rg.Plane(rg.Point3d(ox, oy, oz), rg.Vector3d.ZAxis)
    b = rg.Box(plane,
               rg.Interval(0.0, lx),
               rg.Interval(0.0, ly),
               rg.Interval(0.0, lz))
    return b.ToBrep()


def make_A(col, row, level, orient, cx=0.0, cy=0.0):
    """
    Module A at grid cell (col, row), given floor level.

    orient 0 → long axis in X  (5.0 m × 3.5 m footprint)
    orient 1 → long axis in Y  (3.5 m × 5.0 m footprint)

    cx, cy = cantilever world-coord offsets
    """
    ox = col * GRID + cx
    oy = row * GRID + cy
    oz = level * LEVEL_H
    if orient == 0:
        return axis_box(ox, oy, oz, MOD_AL, MOD_AW, MOD_AH)
    else:
        return axis_box(ox, oy, oz, MOD_AW, MOD_AL, MOD_AH)


def make_B(col, row, level, cx=0.0, cy=0.0):
    """
    Module B (vertical tower) at grid cell (col, row), given floor level.
    Height = 5.0 m (extends 1.5 m above the next 3.5 m floor line).
    cx, cy = cantilever world-coord offsets.
    """
    ox = col * GRID + cx
    oy = row * GRID + cy
    oz = level * LEVEL_H
    return axis_box(ox, oy, oz, MOD_BW, MOD_BD, MOD_BH)


# ═══════════════════════════════════════════════════════════════
#  PYRAMID MASK  — which cells are "in" at a given level
# ═══════════════════════════════════════════════════════════════
def build_pyramid_masks(nx, ny, max_levels, rng):
    """
    Pre-compute a Boolean mask[level][col][row] using a Chebyshev-distance
    pyramid that adds seeded Gaussian noise to its edge for irregularity.

    Returns masks as a list of sets: masks[level] = set of (col,row) that
    are INSIDE the pyramid at that level.
    """
    cx = (nx - 1) * 0.5
    cy = (ny - 1) * 0.5
    base_r = min(cx, cy) * 0.97        # radius of footprint at level 0
    shrink = base_r / float(max_levels) # radius lost per level
    noise_sigma = shrink * 0.35         # irregularity at the edge

    masks = []
    for level in range(max_levels):
        allowed_r = base_r - level * shrink * 0.85
        mask = set()
        for col in range(nx):
            for row in range(ny):
                dist = max(abs(col - cx), abs(row - cy))
                jitter = rng.gauss(0.0, noise_sigma)
                if dist <= (allowed_r + jitter):
                    mask.add((col, row))
        masks.append(mask)
    return masks


# ═══════════════════════════════════════════════════════════════
#  COURTYARD VOID GENERATOR
# ═══════════════════════════════════════════════════════════════
def punch_courtyards(nx, ny, max_levels, n_courts, rng):
    """
    Scatter N courtyard voids across the grid interior.
    Each void is a 1×1 or 1×2 or 2×1 cell patch punched from level 0
    to a random height (at least half the max_floors).

    Returns a frozenset of (col, row, level) cells to keep VOID.
    """
    margin = max(1, min(nx, ny) // 6)
    voids  = set()

    # Distribute courtyard seeds by dividing the interior into a sub-grid
    cols_spread = max(1, int(math.ceil(math.sqrt(n_courts * nx / float(max(ny, 1))))))
    rows_spread = max(1, int(math.ceil(n_courts / float(cols_spread))))
    zone_w = (nx - 2 * margin) / float(max(cols_spread, 1))
    zone_h = (ny - 2 * margin) / float(max(rows_spread, 1))

    placed = 0
    for ci in range(cols_spread):
        for ri in range(rows_spread):
            if placed >= n_courts:
                break
            # Seed position inside zone with some jitter
            base_c = int(margin + zone_w * (ci + 0.2 + rng.random() * 0.6))
            base_r = int(margin + zone_h * (ri + 0.2 + rng.random() * 0.6))
            base_c = max(margin, min(nx - margin - 1, base_c))
            base_r = max(margin, min(ny - margin - 1, base_r))

            # Courtyard footprint: 1–2 × 1–2 cells
            w = rng.randint(1, min(2, nx - base_c - margin))
            d = rng.randint(1, min(2, ny - base_r - margin))

            # Height: at least half the building, not full height
            z_max = rng.randint(max(1, max_levels // 2), max(1, max_levels - 1))

            for lv in range(z_max):
                for c in range(base_c, min(base_c + w, nx)):
                    for r in range(base_r, min(base_r + d, ny)):
                        voids.add((c, r, lv))
            placed += 1

    return frozenset(voids)


# ═══════════════════════════════════════════════════════════════
#  DENSITY FUNCTION — fill probability per cell
# ═══════════════════════════════════════════════════════════════
def cell_fill_prob(col, row, nx, ny, level, max_levels):
    """
    High density at base / centre, lower at top / edges.
    Returns a probability in [0.0, 1.0].
    """
    cx = (nx - 1) * 0.5
    cy = (ny - 1) * 0.5
    dist = math.sqrt((col - cx) ** 2 + (row - cy) ** 2)
    max_d = math.sqrt(cx ** 2 + cy ** 2) + 0.001

    radial   = 1.0 - 0.30 * (dist / max_d)            # edge slightly sparser
    vertical = 1.0 - 0.45 * (level / float(max(max_levels - 1, 1)))  # top sparser
    return max(0.0, radial * vertical)


# ═══════════════════════════════════════════════════════════════
#  CANTILEVER OFFSETS  — Habitat stepping
# ═══════════════════════════════════════════════════════════════
def cantilever_offset(col, row, nx, ny, level, cant_max, rng):
    """
    Upper-level modules lean OUTWARD from the grid centre (Habitat logic).
    Returns (world_offset_x, world_offset_y).
    Ground floor always returns (0, 0).
    """
    if level == 0 or cant_max <= 0.01:
        return 0.0, 0.0

    # Probability increases with level
    prob = 0.12 + level * 0.12
    if rng.random() > min(prob, 0.55):
        return 0.0, 0.0

    cx = (nx - 1) * 0.5
    cy = (ny - 1) * 0.5
    dx = col - cx
    dy = row - cy
    mag = math.sqrt(dx * dx + dy * dy) + 1e-6

    offset = rng.uniform(GRID * 0.10, cant_max)
    return (dx / mag) * offset, (dy / mag) * offset


# ═══════════════════════════════════════════════════════════════
#  MAIN CLUSTER GENERATOR
# ═══════════════════════════════════════════════════════════════
def generate_cluster(nx, ny, max_levels, n_courts, b_ratio, cant_max, seed):
    """
    Build the single dense cluster.

    Returns:
        list_A  — list of Module-A Breps
        list_B  — list of Module-B Breps
        stats   — dict with placement counts
    """
    rng = random.Random(seed)

    # Pre-compute masks
    masks  = build_pyramid_masks(nx, ny, max_levels, rng)
    voids  = punch_courtyards(nx, ny, max_levels, n_courts, rng)

    list_A = []
    list_B = []

    for level in range(max_levels):
        mask = masks[level]
        for col in range(nx):
            for row in range(ny):
                key = (col, row, level)

                # 1. Inside pyramid?
                if (col, row) not in mask:
                    continue

                # 2. Void (courtyard)?
                if key in voids:
                    continue

                # 3. Density roll
                prob = cell_fill_prob(col, row, nx, ny, level, max_levels)
                if rng.random() > prob:
                    continue

                # 4. Cantilever offset
                ocx, ocy = cantilever_offset(col, row, nx, ny, level, cant_max, rng)

                # 5. Module type: B grows more frequent at upper levels
                #    (vertical towers poke up through the mass)
                lv_norm = level / float(max(max_levels - 1, 1))
                b_prob  = b_ratio * (0.35 + 1.3 * lv_norm)
                b_prob  = min(b_prob, 0.50)

                if rng.random() < b_prob:
                    list_B.append(make_B(col, row, level, ocx, ocy))
                else:
                    # Module A: random orientation for cross / L-shape variety
                    orient = rng.randint(0, 1)
                    list_A.append(make_A(col, row, level, orient, ocx, ocy))

    stats = {
        "A": len(list_A),
        "B": len(list_B),
        "total": len(list_A) + len(list_B),
        "footprint_x": nx * GRID,
        "footprint_y": ny * GRID,
        "max_height": max_levels * LEVEL_H,
    }
    return list_A, list_B, stats


# ═══════════════════════════════════════════════════════════════
#  ENTRY POINT
# ═══════════════════════════════════════════════════════════════
def main():
    print("=" * 62)
    print("  WoSyHo  —  Single Cluster Aggregator  v3.0")
    print("  Module A : 5.0L × 3.5W × 3.5H m  (horizontal)")
    print("  Module B : 3.5W × 3.5D × 5.0H m  (vertical tower)")
    print("=" * 62)

    nx      = rs.GetInteger(
                "Grid columns NX  [each column = 3.5 m]",
                number=10, minimum=4, maximum=24)
    ny      = rs.GetInteger(
                "Grid rows NY  [each row = 3.5 m]",
                number=10, minimum=4, maximum=24)
    floors  = rs.GetInteger(
                "Number of floors  [3 / 4 / 5]",
                number=4,  minimum=3, maximum=5)
    courts  = rs.GetInteger(
                "Number of internal sky-courts / voids  [3–8 recommended]",
                number=5,  minimum=0, maximum=14)
    b_pct   = rs.GetInteger(
                "Vertical B-module percentage  [15–40 %]",
                number=25, minimum=5, maximum=50)
    cant    = rs.GetReal(
                "Max cantilever offset in metres  [0.0 – 1.5 m]",
                number=0.8, minimum=0.0, maximum=2.0)
    seed    = rs.GetInteger(
                "Random seed  [change for different layout]",
                number=7)

    if None in (nx, ny, floors, courts, b_pct, cant, seed):
        print("Cancelled."); return

    # ── Generate ────────────────────────────────────────────────
    list_A, list_B, stats = generate_cluster(
        nx, ny, floors, courts,
        b_pct / 100.0, cant, seed
    )

    if stats["total"] == 0:
        print("No modules generated. Try larger NX/NY or fewer courtyards.")
        return

    # ── Layers ──────────────────────────────────────────────────
    L_A = ensure_layer("Module_A_horizontal", sd.Color.SandyBrown)
    L_B = ensure_layer("Module_B_vertical",   sd.Color.SteelBlue)

    # ── Bake ────────────────────────────────────────────────────
    rs.CurrentLayer(L_A)
    for brep in list_A:
        sc.doc.Objects.AddBrep(brep)

    rs.CurrentLayer(L_B)
    for brep in list_B:
        sc.doc.Objects.AddBrep(brep)

    sc.doc.Views.Redraw()

    # ── Report ──────────────────────────────────────────────────
    print("\n  ✓  Cluster generated")
    print("     Module A (horizontal) : {:>4}  units".format(stats["A"]))
    print("     Module B (vertical)   : {:>4}  units".format(stats["B"]))
    print("     ─────────────────────────────────")
    print("     Total modules         : {:>4}  units".format(stats["total"]))
    print("     Approx footprint      : {:.0f} m × {:.0f} m".format(
          stats["footprint_x"], stats["footprint_y"]))
    print("     Max height            : {:.1f} m  ({} floors × 3.5 m)".format(
          stats["max_height"], floors))
    print("\n  Layers:")
    print("     WoSyHo::Module_A_horizontal  (sandy brown)")
    print("     WoSyHo::Module_B_vertical    (steel blue)")
    print("=" * 62)


if __name__ == "__main__":
    main()
