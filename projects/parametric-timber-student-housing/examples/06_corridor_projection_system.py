# -*- coding: utf-8 -*-
"""
Parametric Timber Student Housing - v20 projection v04, smart corridor projection fix
=========================================================

Purpose:
  First-stage massing/aggregation only.
  central 2-room + 1-corridor + 2-room ring logic, NO terrace plates, NO C module.

Locked modules:
  A = 7.50 x 3.75 x 3.75 m  horizontal module, 1 floor, 2 grid cells
  B = 3.75 x 3.75 x 7.50 m  vertical module, 2 floors, 1 grid cell

New v13 logic:
  1. Curved height field instead of linear diagonal ramp.
  2. Peak floors are honoured exactly; user controls NE/NW/SE/SW corner heights separately.
  3. Base can be reduced to 2 floors for stronger curve.
  4. Two proportional parametric opening sizes only:
       O1 = 1 cell x 1 floor
       O2 = 2 cells x 1 floor, same footprint length as A
  5. Openings are deterministic and rhythmic, not random.
  6. Openings are only in cascade/middle zone; peak zone is protected.
  7. Plan grammar is locked: 2 room cells + 1 corridor void + 2 room cells on all four sides.
  8. Four-corner height field: NE/NW/SE/SW slopes merge by strongest peak influence.
  9. Four service cores: 1 cell x 3 cells = 3.75 x 11.25 m, baked as local-height boxes.
 10. Selected exposed outer-facade A modules MOVE outward, including short-face modules.

Run in Rhino:
  _RunPythonScript -> choose this .py file
"""

import math
import System
import System.Drawing as sd
import Rhino
import Rhino.Geometry as rg
import Rhino.DocObjects as rd
import rhinoscriptsyntax as rs
import scriptcontext as sc
import Eto.Forms as forms
import Eto.Drawing as drawing

# ---------------------------------------------------------------------
# CONSTANTS
# ---------------------------------------------------------------------
GRID = 3.75
FLOOR_H = 3.75

# Module dimensions
A_CELLS = 2       # A spans 2 grid cells in plan
B_FLOORS = 2      # B spans 2 floors vertically


# First detailing thickness logic
MODULE_WALL_T = 0.09       # 90 mm CLT shell for A modules, pushed inside
CORRIDOR_SLAB_T = 0.09     # 90 mm corridor floor slab
CORE_WALL_T = 0.12         # 120 mm core walls, pushed inside

# Plan grammar: two module cells + one corridor cell + two module cells
ROOM_BAND_CELLS = 2
CORRIDOR_CELLS = 1
RING_DEPTH_CELLS = ROOM_BAND_CELLS + CORRIDOR_CELLS + ROOM_BAND_CELLS  # 5

# Default design values
DEFAULT_NX = 24
DEFAULT_NY = 16
DEFAULT_PEAK_NE = 12
DEFAULT_PEAK_NW = 2
DEFAULT_PEAK_SE = 2
DEFAULT_PEAK_SW = 2
DEFAULT_BASE = 2
DEFAULT_CURVE_POWER = 2.8
DEFAULT_PERFORATION_PCT = 15  # 0 solid, 15 balanced/reference, 30 aggressive, 50 porous

# Perforation tuning: reference-measured density logic.
# The user input is average density; this gradient makes lower floors mostly solid
# and upper/cascade/peak areas more perforated, like the reference image.
PERFORATION_PROTECT_PLINTH = 2   # ground + floor 1 always solid
PERFORATION_PROTECT_CAP = 1      # very top local floor always solid
PERFORATION_GRADIENT = [
    (0.00, 0.05),
    (0.30, 0.40),
    (0.60, 1.20),
    (1.00, 2.00),
]

# Height-field tuning for TRUE base floors.
# Smaller value = faster falloff from peaks, so low/base zones actually appear.
HEIGHT_RADIUS_FACTOR = 0.50

# Compact zone around each selected peak that is forced to exact peak height.
# Keep small to avoid bulky tower caps.
PEAK_PLATEAU_T = 0.08
# Compact square tower cap around each core so the peak floor is not only a visible green shaft.
# 5x5 cells gives enough cells for A-only modules to wrap around the 1x3 core without overlap.
PEAK_CAP_CELLS = 5
# Stronger silhouette tuning: the slope falls from the edge of the corner cap, not from a single point.
SLOPE_RADIUS_FACTOR = 0.55
SLOPE_POWER_BOOST = 1.85

# Facade cantilever tuning.
# IMPORTANT: these are real module translations, not stretched facade projections.
# 1.5 m = half-step, 3.0 m = max cantilever.
CANTILEVER_HALF = 0.0
CANTILEVER_FULL = 0.0
CANTILEVER_MAX = 0.0

# Optional second-stage facade projection. Default is OFF, so existing massing
# stays untouched unless the user explicitly chooses a projection option.
PROJECTION_MODE_SKIP = "skip"
PROJECTION_MODE_PARAMETRIC = "parametric"
PROJECTION_MODE_CHECKER = "checker"
PROJECTION_DEFAULT_SHORT_MAX = 2.00  # max outward move when exposed face is module short side
PROJECTION_DEFAULT_LONG_MAX  = 1.00  # max outward move when exposed face is module long side

# Habitat-67 half-overlap stacking for perpendicular A modules.
# Always ON. This does NOT move or project modules; it only skips some
# outer-facade A pairs on odd floors to create brick-like openings.
STAGGER_PROTECT_PLINTH = 1
STAGGER_PROTECT_CAP = 1
STAGGER_KEEP_PERCENT = 70  # kept for compatibility
INTERLOCK_SHIFT = GRID * 0.5  # 1.875 m half-cell facade bond; stays inside footprint

# Extended logical facade opening types.
# Type 1/2 are the existing single-pair and interlock void behaviours.
# Type 3 = two neighbouring facade pairs omitted on the same floor.
# Type 4 = diagonal/L-shaped two-floor void, shifted by one pair so the modules
# above still half-bear on adjacent modules rather than forming a weak vertical shaft.
OPENING_TYPE3_FACTOR = 0.12  # safer: Type 3 is a rare supported single-pair opening
OPENING_TYPE4_FACTOR = 0.10  # safer: Type 4 is a rare diagonal single-pair opening

# Inverted cascade from base on short sides only.
# This removes bottom modules near the centre of short outer facades,
# creating an hourglass elevation profile while keeping the top cascade intact.
INVERTED_CASCADE_SLOPE = 2.5           # cells per floor of cut (mirrors top)
CORE_ANCHOR_RADIUS = 2                 # cells around core that stay solid at base
BRIDGE_BAND_MAX_THICKNESS = 3          # keep only 3 floors between top and inverted cascade
INVERTED_ARCH_MAX_CUT = 6              # (unused by mirror logic, kept for ref)
INVERTED_ARCH_POWER   = 2.2            # (unused by mirror logic, kept for ref)
INVERTED_BRIDGE_FLOORS = 2             # floors left between top cascade and inverted cut

CURVE_REACH_MIN_STRENGTH = 2.0      # steepest acceptable curve strength for side-reach test
CURVE_REACH_MAX_STRENGTH = 3.0      # softest acceptable curve strength for side-reach test
CURVE_REACH_SAFETY = 0.95           # full-side reach tolerance; prevents long-side false deletion
NO_INVERT_WHEN_SIDE_AT_LEAST = 24  # if side length is 24+ cells, normal cascade is allowed to resolve to base

# Layers
LAYERS = {
    "A_low":       ("WoSyHo_A_low",       sd.Color.FromArgb(220, 160, 80)),
    "A_mid":       ("WoSyHo_A_mid",       sd.Color.FromArgb(210, 130, 60)),
    "A_high":      ("WoSyHo_A_high",      sd.Color.FromArgb(190, 100, 40)),
    "A_cant":      ("WoSyHo_A_cantilever", sd.Color.FromArgb(230, 145, 65)),
    "B":           ("WoSyHo_B_vertical",  sd.Color.FromArgb(70, 105, 175)),
    "core":        ("WoSyHo_Core_1p5A",    sd.Color.FromArgb(50, 180, 80)),
    "openings":    ("WoSyHo_Openings",    sd.Color.FromArgb(180, 35, 35)),
    "courtyard":   ("WoSyHo_Courtyard",   sd.Color.FromArgb(120, 120, 120)),
    "corridor":    ("WoSyHo_Corridor_Void_Guide", sd.Color.FromArgb(60, 60, 60)),
    "corridor_slab": ("WoSyHo_Corridor_Floor_Slabs", sd.Color.FromArgb(145, 145, 135)),
    "corridor_bridge": ("WoSyHo_Corridor_Projection_Bridges", sd.Color.FromArgb(165, 165, 150)),
    "core_wall":   ("WoSyHo_Core_120mm_Walls", sd.Color.FromArgb(35, 145, 65)),
    "setback":     ("WoSyHo_Setback",     sd.Color.FromArgb(190, 20, 20)),
}


# Eto dialog colors (kept from v12 dialog API style)
ETO_BG_WARM   = drawing.Color.FromArgb(245, 245, 245)
ETO_BG_PANEL  = drawing.Color.FromArgb(210, 210, 210)
ETO_BG_INPUT  = drawing.Color.FromArgb(192, 192, 192)
ETO_TXT_PRIM  = drawing.Color.FromArgb(128, 0, 2)
ETO_TXT_SECN  = drawing.Color.FromArgb(100, 0, 4)
ETO_TXT_HILT  = drawing.Color.FromArgb(165, 8, 2)
ETO_CONFIRM   = drawing.Color.FromArgb(140, 0, 0)
ETO_ABORT     = drawing.Color.FromArgb(72, 0, 0)
ETO_ACCENT    = drawing.Color.FromArgb(175, 20, 15)
ETO_WHITE     = drawing.Color.FromArgb(255, 255, 255)

# ---------------------------------------------------------------------
# RHINO HELPERS
# ---------------------------------------------------------------------
def find_layer_index(layer_name):
    """Return Rhino layer index safely across Rhino/Eto/Python versions.

    Some Rhino builds return a Layer object from FindName(), while others use
    integer indexes from Find()/FindByFullPath(). The previous version compared
    a Layer/None directly with 0, which caused: `>= not supported between ...`.
    """
    # Preferred RhinoCommon method for full/simple layer paths.
    try:
        idx = sc.doc.Layers.FindByFullPath(layer_name, -1)
        if isinstance(idx, int) and idx >= 0:
            return idx
    except Exception:
        pass

    # Older/simple RhinoCommon method.
    try:
        idx = sc.doc.Layers.Find(layer_name, True)
        if isinstance(idx, int) and idx >= 0:
            return idx
    except Exception:
        pass

    # FindName may return a Layer object, not an index.
    try:
        layer = sc.doc.Layers.FindName(layer_name)
        if layer is not None:
            try:
                return int(layer.Index)
            except Exception:
                pass
    except Exception:
        pass

    return -1


def ensure_layer(layer_name, color):
    idx = find_layer_index(layer_name)
    if idx >= 0:
        return idx

    layer = rd.Layer()
    layer.Name = layer_name
    layer.Color = color
    try:
        idx = sc.doc.Layers.Add(layer)
        return idx
    except Exception as ex:
        print("Layer creation failed for {0}: {1}".format(layer_name, ex))
        return -1


def init_layers():
    for _, (name, color) in LAYERS.items():
        ensure_layer(name, color)


def layer_index(key):
    name, _ = LAYERS[key]
    return find_layer_index(name)


def make_box(x, y, z, dx, dy, dz):
    bb = rg.BoundingBox(rg.Point3d(x, y, z), rg.Point3d(x + dx, y + dy, z + dz))
    return rg.Box(bb).ToBrep()


def bake_brep(brep, layer_key):
    if brep is None:
        return None
    attr = rd.ObjectAttributes()
    li = layer_index(layer_key)
    if li >= 0:
        attr.LayerIndex = li
    return sc.doc.Objects.AddBrep(brep, attr)


def bake_curve(curve, layer_key):
    if curve is None:
        return None
    attr = rd.ObjectAttributes()
    li = layer_index(layer_key)
    if li >= 0:
        attr.LayerIndex = li
    return sc.doc.Objects.AddCurve(curve, attr)


def add_text(text, pt, height=1.1):
    try:
        rs.AddText(text, pt, height=height)
    except Exception:
        print(text)

# ---------------------------------------------------------------------
# BASIC GEOMETRY / PLAN HELPERS
# ---------------------------------------------------------------------
def is_in_cluster(cx, cy, NX, NY):
    return 0 <= cx < NX and 0 <= cy < NY


def courtyard_bounds(NX, NY, size_name=None):
    """Return an AUTOMATIC courtyard from the locked plan grammar.

    Gowthaman correction v13l:
      The user should not decide courtyard size independently anymore.
      The courtyard is derived from the module rows/columns.

    Locked cross-section on EVERY side:
      2 module cells + 1 corridor cell + 2 module cells + COURTYARD

    Therefore:
      ring depth each side = 5 cells
      courtyard width  = NX - 10 cells
      courtyard depth  = NY - 10 cells

    This prevents the old dense plan where extra module rows appeared.
    """
    d = RING_DEPTH_CELLS  # 2 room + 1 corridor + 2 room = 5 cells

    # Normal case: exact grammar on all sides.
    if NX >= 2 * d + 2 and NY >= 2 * d + 2:
        c0x = d
        c0y = d
        cw = NX - 2 * d
        ch = NY - 2 * d
        return c0x, c0y, cw, ch

    # Safety fallback for very small test footprints.
    safe_x = max(1, min(d, (NX - 2) // 2))
    safe_y = max(1, min(d, (NY - 2) // 2))
    c0x = safe_x
    c0y = safe_y
    cw = max(2, NX - 2 * safe_x)
    ch = max(2, NY - 2 * safe_y)
    return c0x, c0y, cw, ch

def is_courtyard(cx, cy, c0x, c0y, cw, ch):
    return c0x <= cx < c0x + cw and c0y <= cy < c0y + ch

def corridor_and_module_cells(NX, NY, c0x, c0y, cw, ch):
    """Return (module_cells, corridor_cells) for the locked 5-cell ring.

    This is the core plan grammar Gowthaman corrected:
      OUTSIDE / outer edge
      2 module cells
      1 corridor cell
      2 module cells
      COURTYARD / centre void

    The corridor is a CLOSED RECTANGULAR LOOP, not four loose lines, so it
    does not overshoot at corners. The courtyard is already automatic from
    courtyard_bounds(): c0x/c0y/cw/ch.

    Example for NX=30, NY=16:
      west/east/south/north ring depth = 5 cells
      courtyard = 20 x 6 cells
      corridor rectangle uses the centre cell of each 5-cell side.

    Returns:
      module_cells   = all buildable room/module cells in the 5-cell ring,
                       excluding the 1-cell corridor loop and courtyard.
      corridor_cells = the closed rectangular 1-cell-wide corridor loop.
    """
    module_cells = set()
    corridor_cells = set()

    d = RING_DEPTH_CELLS          # 5 cells total side depth
    rb = ROOM_BAND_CELLS          # 2 module cells each side of corridor

    # Corridor centre lines inside the 5-cell ring.
    # For normal auto-courtyard: c0x=c0y=5, so west/south corridor = 2.
    west_corr_x  = c0x - rb - 1
    east_corr_x  = c0x + cw + rb
    south_corr_y = c0y - rb - 1
    north_corr_y = c0y + ch + rb

    # Clip for very small fallback footprints.
    west_corr_x  = max(0, min(NX - 1, west_corr_x))
    east_corr_x  = max(0, min(NX - 1, east_corr_x))
    south_corr_y = max(0, min(NY - 1, south_corr_y))
    north_corr_y = max(0, min(NY - 1, north_corr_y))

    if west_corr_x > east_corr_x:
        west_corr_x, east_corr_x = east_corr_x, west_corr_x
    if south_corr_y > north_corr_y:
        south_corr_y, north_corr_y = north_corr_y, south_corr_y

    # Closed corridor rectangle: no overshooting beyond these four corners.
    for x in range(west_corr_x, east_corr_x + 1):
        corridor_cells.add((x, south_corr_y))
        corridor_cells.add((x, north_corr_y))
    for y in range(south_corr_y, north_corr_y + 1):
        corridor_cells.add((west_corr_x, y))
        corridor_cells.add((east_corr_x, y))

    # Buildable 5-cell ring around the automatic courtyard.
    # Everything deeper than 5 cells is courtyard/void; nothing extra is filled.
    for cx in range(NX):
        for cy in range(NY):
            if is_courtyard(cx, cy, c0x, c0y, cw, ch):
                continue

            # Cell belongs to the locked ring if it is within 5 cells of the
            # courtyard on at least one side, while still inside the model.
            in_west_band  = (c0x - d) <= cx < c0x and (c0y - d) <= cy < (c0y + ch + d)
            in_east_band  = (c0x + cw) <= cx < (c0x + cw + d) and (c0y - d) <= cy < (c0y + ch + d)
            in_south_band = (c0y - d) <= cy < c0y and (c0x - d) <= cx < (c0x + cw + d)
            in_north_band = (c0y + ch) <= cy < (c0y + ch + d) and (c0x - d) <= cx < (c0x + cw + d)

            if not (in_west_band or in_east_band or in_south_band or in_north_band):
                continue

            if (cx, cy) in corridor_cells:
                continue

            module_cells.add((cx, cy))

    return module_cells, corridor_cells


def classify_cell(cx, cy, NX, NY, c0x, c0y, cw, ch):
    """Classify cell by edge position. Used for A orientation and B accents."""
    if cx == 0 and cy == 0: return "outer_corner"
    if cx == NX - 1 and cy == 0: return "outer_corner"
    if cx == 0 and cy == NY - 1: return "outer_corner"
    if cx == NX - 1 and cy == NY - 1: return "outer_corner"

    if cy == 0 or cy == NY - 1: return "outer_long"
    if cx == 0 or cx == NX - 1: return "outer_short"

    if cy == c0y - 1 and c0x <= cx < c0x + cw: return "inner_long"
    if cy == c0y + ch and c0x <= cx < c0x + cw: return "inner_long"
    if cx == c0x - 1 and c0y <= cy < c0y + ch: return "inner_short"
    if cx == c0x + cw and c0y <= cy < c0y + ch: return "inner_short"

    if (cx in (c0x - 1, c0x + cw)) and (cy in (c0y - 1, c0y + ch)):
        return "inner_corner"

    return "middle"




_SIDE_PROFILE_CACHE = {}

def _side_name_and_axis_data(side, NX, NY):
    """
    Return side length and axis direction.
    Position always runs:
      N/S along X
      E/W along Y
    """
    if side in ("N", "S"):
        return int(NX)
    return int(NY)


def _facade_profile_for_side(side, NX, NY, c0x, c0y, cw, ch,
                             cell_floor_counts, core_cells=None):
    """
    Read the ACTUAL generated elevation silhouette for one side.

    This is the key fix:
    We do not guess from the plot dimension alone.
    We do not use a fixed curve strength alone.
    We read the actual module height profile after the main cascade field
    has been generated.

    For each position along the side, we read the visible outer facade strip
    and take the MAX height. MAX gives the visible silhouette of that side.
    """
    core_cells = core_cells or set()
    d = RING_DEPTH_CELLS
    profile = {}

    if side == "N":
        # outside north facade strip
        y0 = max(0, NY - d)
        y1 = NY
        for x in range(NX):
            hs = []
            for y in range(y0, y1):
                cell = (x, y)
                if cell in core_cells:
                    continue
                if is_courtyard(x, y, c0x, c0y, cw, ch):
                    continue
                fc = int(cell_floor_counts.get(cell, 0))
                if fc > 0:
                    hs.append(fc)
            if hs:
                profile[x] = max(hs)

    elif side == "S":
        y0 = 0
        y1 = min(NY, d)
        for x in range(NX):
            hs = []
            for y in range(y0, y1):
                cell = (x, y)
                if cell in core_cells:
                    continue
                if is_courtyard(x, y, c0x, c0y, cw, ch):
                    continue
                fc = int(cell_floor_counts.get(cell, 0))
                if fc > 0:
                    hs.append(fc)
            if hs:
                profile[x] = max(hs)

    elif side == "E":
        x0 = max(0, NX - d)
        x1 = NX
        for y in range(NY):
            hs = []
            for x in range(x0, x1):
                cell = (x, y)
                if cell in core_cells:
                    continue
                if is_courtyard(x, y, c0x, c0y, cw, ch):
                    continue
                fc = int(cell_floor_counts.get(cell, 0))
                if fc > 0:
                    hs.append(fc)
            if hs:
                profile[y] = max(hs)

    elif side == "W":
        x0 = 0
        x1 = min(NX, d)
        for y in range(NY):
            hs = []
            for x in range(x0, x1):
                cell = (x, y)
                if cell in core_cells:
                    continue
                if is_courtyard(x, y, c0x, c0y, cw, ch):
                    continue
                fc = int(cell_floor_counts.get(cell, 0))
                if fc > 0:
                    hs.append(fc)
            if hs:
                profile[y] = max(hs)

    return profile


def _side_needs_inverted_cascade(side, NX, NY, c0x, c0y, cw, ch,
                                  cell_floor_counts, base_floors,
                                  core_cells=None):
    """
    Decide from the actual side elevation.

    A side needs inverted cascade if the CENTER of its actual facade silhouette
    is still above the base floor. That means the normal top cascade could not
    descend to the base on that side.

    If the center is already at base, no deletion is needed.
    """
    if cell_floor_counts is None:
        return False, {}

    key = (side, int(NX), int(NY), int(c0x), int(c0y), int(cw), int(ch),
           int(base_floors), id(cell_floor_counts))
    if key in _SIDE_PROFILE_CACHE:
        return _SIDE_PROFILE_CACHE[key]

    base_i = int(base_floors)
    profile = _facade_profile_for_side(
        side, NX, NY, c0x, c0y, cw, ch, cell_floor_counts, core_cells
    )

    if not profile:
        result = (False, profile)
        _SIDE_PROFILE_CACHE[key] = result
        return result

    length = _side_name_and_axis_data(side, NX, NY)

    # Read central 30 percent of the side elevation.
    mid0 = int(round((length - 1) * 0.35))
    mid1 = int(round((length - 1) * 0.65))
    centre_positions = [p for p in range(mid0, mid1 + 1) if p in profile]

    if not centre_positions:
        result = (False, profile)
        _SIDE_PROFILE_CACHE[key] = result
        return result

    centre_min = min(profile[p] for p in centre_positions)

    # This is the user's rule:
    # If the cascade has not come down to the base floor at the centre,
    # then we add the inverted cascade from below.
    needs = centre_min > base_i

    result = (needs, profile)
    _SIDE_PROFILE_CACHE[key] = result
    return result


def _side_memberships_for_full_zone(cx, cy, NX, NY, c0x, c0y, cw, ch):
    """
    Side zones for deletion.
    These are full side zones, not just a thin strip, so the inverted cut
    removes modules on both sides of the corridor where required.
    """
    sides = []

    if cy >= c0y + ch:
        sides.append(("N", cx, NX))
    if cy < c0y:
        sides.append(("S", cx, NX))
    if cx >= c0x + cw:
        sides.append(("E", cy, NY))
    if cx < c0x:
        sides.append(("W", cy, NY))

    return sides


def _side_data(side, NX, NY, peak_ne, peak_nw, peak_se, peak_sw):
    """
    Return side length and the two corner peak values for that side.
    Position direction:
      N/S: x direction
      E/W: y direction
    """
    if side == "N":
        return int(NX), int(peak_nw), int(peak_ne)
    if side == "S":
        return int(NX), int(peak_sw), int(peak_se)
    if side == "E":
        return int(NY), int(peak_se), int(peak_ne)
    if side == "W":
        return int(NY), int(peak_sw), int(peak_nw)
    return 0, 0, 0


def _can_side_curve_reach_base(side, NX, NY,
                               peak_ne, peak_nw, peak_se, peak_sw,
                               base_floors):
    """
    ADAPTIVE CURVE-REACH TEST.

    This is the corrected decision logic.

    We do NOT say "delete because the visible elevation is high".
    We ask: can a normal curve cascade, using a reasonable curve strength
    between 2.0 and 3.0, reach the base floor on this side?

    If yes, no inverted cascade.
    If no, inverted cascade is required.

    Side length controls the decision:
      - long sides such as 24 or 30 cells normally pass
      - short sides such as 16 cells with high peaks may fail
      - 16x16 can fail on both directions
    """
    base_i = int(base_floors)
    side_length, peak_a, peak_b = _side_data(
        side, NX, NY, peak_ne, peak_nw, peak_se, peak_sw
    )
    if side_length <= 0:
        return True

    drop_a = max(0, int(peak_a) - base_i)
    drop_b = max(0, int(peak_b) - base_i)

    # If both corners are already base, it reaches base by definition.
    if drop_a <= 0 and drop_b <= 0:
        return True

    # Stronger corrected reach test:
    # If the side is long enough (24+ cells), let the normal cascade solve it.
    # This prevents deleting the long side where the cascade can go down.
    if int(side_length) >= int(NO_INVERT_WHEN_SIDE_AT_LEAST):
        return True

    # For shorter sides, test against the steepest acceptable curve strength.
    # If the selected peak/drop cannot resolve in that short length, then the
    # side needs the inverted bottom cascade.
    controlling_drop = max(drop_a, drop_b)
    required_run = float(controlling_drop) * float(CURVE_REACH_MIN_STRENGTH)
    available_run = float(side_length)

    return available_run >= required_run * float(CURVE_REACH_SAFETY)


def _side_memberships_for_full_zone(cx, cy, NX, NY, c0x, c0y, cw, ch):
    """
    Full side zones. The cut affects the whole side zone, not only the corridor
    strip, so both sides of the corridor can be deleted when needed.
    """
    sides = []
    if cy >= c0y + ch:
        sides.append(("N", cx, NX))
    if cy < c0y:
        sides.append(("S", cx, NX))
    if cx >= c0x + cw:
        sides.append(("E", cy, NY))
    if cx < c0x:
        sides.append(("W", cy, NY))
    return sides


def inverted_cascade_bottom_cut(cx, cy, NX, NY, c0x, c0y, cw, ch,
                                  peak_ne, peak_nw, peak_se, peak_sw,
                                  base_floors, core_cells=None,
                                  cell_floor_counts=None,
                                  hourglass_sides=None,
                                  corridor_cells=None):
    """
    v17 FINAL — CLEAN ARCH IN A STRICT BOUNDING RECTANGLE.

    For each ticked side, the cut zone is an explicit rectangle:
       - depth axis  = the full room band of that side (inner ring -> outer wall)
       - length axis = strictly BETWEEN the two cores (corridor corners)
    No dominant-side guessing -> no diagonal leak past the cores.

    Inside that rectangle the cut is a CLEAN parabolic arch:
       0 floors removed at each core, INVERTED_ARCH_MAX_CUT at the centre.
    The arch shape is fixed geometry (does NOT follow the jagged cascade),
    so the bottom edge is a smooth curve, not wavy.
    """
    if hourglass_sides is None or len(hourglass_sides) == 0:
        return 0
    if not corridor_cells:
        return 0

    base_i = int(base_floors)

    if is_courtyard(cx, cy, c0x, c0y, cw, ch):
        return 0

    if core_cells:
        for ccx, ccy in core_cells:
            if abs(cx - ccx) <= CORE_ANCHOR_RADIUS and abs(cy - ccy) <= CORE_ANCHOR_RADIUS:
                return 0

    b = corridor_bounds_from_cells(corridor_cells)
    if b is None:
        return 0
    corr_west, corr_east, corr_south, corr_north = b

    d = RING_DEPTH_CELLS

    # Build the explicit cut rectangle for whichever ticked side this cell is in.
    # Depth band limits (perpendicular to the side) + length limits (between cores).
    matched_side = None
    pos = None
    core_lo = core_hi = None

    # NORTH band: cy in [c0y+ch, c0y+ch+d-1]; length axis = X between W/E cores
    if "N" in hourglass_sides and (c0y + ch) <= cy < (c0y + ch + d):
        matched_side = "N"; pos = cx; core_lo = corr_west;  core_hi = corr_east
    # SOUTH band: cy in [c0y-d, c0y-1]
    elif "S" in hourglass_sides and (c0y - d) <= cy < c0y:
        matched_side = "S"; pos = cx; core_lo = corr_west;  core_hi = corr_east
    # EAST band: cx in [c0x+cw, c0x+cw+d-1]; length axis = Y between S/N cores
    elif "E" in hourglass_sides and (c0x + cw) <= cx < (c0x + cw + d):
        matched_side = "E"; pos = cy; core_lo = corr_south; core_hi = corr_north
    # WEST band: cx in [c0x-d, c0x-1]
    elif "W" in hourglass_sides and (c0x - d) <= cx < c0x:
        matched_side = "W"; pos = cy; core_lo = corr_south; core_hi = corr_north

    if matched_side is None:
        return 0

    # STRICT rectangle: must be strictly between the two cores on the length axis.
    if pos <= core_lo or pos >= core_hi:
        return 0

    # MIRROR THE UPPER CASCADE, LEAVING 2 FLOORS BETWEEN.
    # The upper cascade has a curve along this side (tall near cores/peaks,
    # dipping toward the centre). The inverted cut draws the SAME curve from
    # below, leaving exactly 'bridge' floors in between -> hourglass pinch.
    #
    #   cut(position) = upper_cascade_height(position) - bridge
    #
    # SKIP RULE: where the upper cascade has already come down to the base
    # (height <= base + bridge), there is nothing to mirror -> cut <= 0 -> skip.
    #
    # The cut must be the SAME across the full depth band (inner -> outer) so
    # the opening is a clean slab in plan, not deeper at the outer edge.
    # -> use the MAX cascade height across the depth band at this position.
    bridge = INVERTED_BRIDGE_FLOORS

    if cell_floor_counts:
        depth_heights = []
        if matched_side in ("N", "S"):
            yr = range(c0y + ch, c0y + ch + d) if matched_side == "N" else range(c0y - d, c0y)
            for yy in yr:
                if not is_courtyard(cx, yy, c0x, c0y, cw, ch):
                    depth_heights.append(int(cell_floor_counts.get((cx, yy), base_i)))
        else:
            xr = range(c0x + cw, c0x + cw + d) if matched_side == "E" else range(c0x - d, c0x)
            for xx in xr:
                if not is_courtyard(xx, cy, c0x, c0y, cw, ch):
                    depth_heights.append(int(cell_floor_counts.get((xx, cy), base_i)))
        col_h = max(depth_heights) if depth_heights else base_i
    else:
        col_h = base_i
    col_h = max(base_i, col_h)

    cut = col_h - bridge
    if cut <= 0:
        return 0   # cascade already at base here -> skip

    return cut


def inverted_cascade_top_cap(cx, cy, NX, NY, c0x, c0y, cw, ch,
                              peak_ne, peak_nw, peak_se, peak_sw,
                              base_floors, core_cells=None,
                              cell_floor_counts=None,
                              hourglass_sides=None):
    """
    v17 final — DISABLED.
    The inverted cascade is now a clean ARCH cut into the BASE only.
    The top cascade above the arch is left completely untouched, so there
    is no top cap. Always returns None.
    """
    return None




def is_horizontal_side_cell(cx, cy, c0x, c0y, cw, ch):
    """Cells in north/south arms should receive A modules along X."""
    d = RING_DEPTH_CELLS
    return ((c0y - d) <= cy < c0y or (c0y + ch) <= cy < (c0y + ch + d)) and \
           ((c0x - d) <= cx < (c0x + cw + d))


def is_vertical_side_cell(cx, cy, c0x, c0y, cw, ch):
    """Cells in east/west arms should receive A modules along Y."""
    d = RING_DEPTH_CELLS
    return ((c0x - d) <= cx < c0x or (c0x + cw) <= cx < (c0x + cw + d)) and \
           ((c0y - d) <= cy < (c0y + ch + d))

_PEAK_OVERRIDE = None
_MAXD_OVERRIDE = None
_PEAK_DATA = []  # list of (px, py, peak_floors, max_distance, corner_name)
_PEAK_CAP_DATA = []  # list of (set(cells), peak_floors, max_distance, corner_name)

def peak_point(NX, NY, peak_corner):
    pc = (peak_corner or "NE").upper()
    if pc == "NW": return 0, NY - 1
    if pc == "SE": return NX - 1, 0
    if pc == "SW": return 0, 0
    return NX - 1, NY - 1  # NE default



def corner_cap_cells(corner, NX, NY, size=None):
    """Return a TRUE CORNER peak cap.

    This fixes the issue Gowthaman marked:
      - The top tower must read as a complete square/cube of modules.
      - The green core should stay at the corridor-corner side of that cube.
      - The cap is therefore anchored to the OUTER plot corner, not centred on
        the core. This keeps the peak "corner-most" and avoids the bad exposed
        core/cut top.
    """
    if size is None:
        size = PEAK_CAP_CELLS
    size = max(3, int(size))
    c = (corner or "NE").upper().strip()
    cells = set()

    if c == "NE":
        xs = range(max(0, NX - size), NX)
        ys = range(max(0, NY - size), NY)
    elif c == "NW":
        xs = range(0, min(NX, size))
        ys = range(max(0, NY - size), NY)
    elif c == "SE":
        xs = range(max(0, NX - size), NX)
        ys = range(0, min(NY, size))
    else:  # SW
        xs = range(0, min(NX, size))
        ys = range(0, min(NY, size))

    for x in xs:
        for y in ys:
            cells.add((x, y))
    return cells


def set_peak_cap_data(cap_specs, module_cells):
    """Store cap-based peak data for the height field.

    cap_specs = [(cap_cells, floors, corner), ...]
    The slope now measures distance from the nearest cell of the square cap.
    This gives a stronger, more architectural curve than measuring from only
    one peak point.
    """
    global _PEAK_CAP_DATA
    _PEAK_CAP_DATA = []
    module_cells = set(module_cells or [])
    for cap_cells, floors, corner in cap_specs:
        cap_cells = set(cap_cells or [])
        try:
            floors_i = int(floors)
        except Exception:
            continue
        if floors_i <= 0 or not cap_cells:
            continue
        maxd = 1.0
        if module_cells:
            vals = []
            for mc in module_cells:
                d = min([math.sqrt((mc[0]-cc[0])**2 + (mc[1]-cc[1])**2) for cc in cap_cells] or [1.0])
                vals.append(d)
            maxd = max(vals or [1.0])
        _PEAK_CAP_DATA.append((cap_cells, floors_i, float(maxd), corner))

def setup_peak_data(module_cells, NX, NY, peak_specs):
    """Snap each chosen peak corner to the nearest ACTIVE module cell.

    peak_specs = [(corner, floors), (corner, floors)]
    This prevents the selected peak height from disappearing because the plot
    corner may be corridor/courtyard/empty.
    """
    global _PEAK_DATA, _PEAK_OVERRIDE, _MAXD_OVERRIDE
    _PEAK_DATA = []
    _PEAK_OVERRIDE = None
    _MAXD_OVERRIDE = None

    if not module_cells:
        return

    used_cells = set()
    for corner, floors in peak_specs:
        # Peak 2 is optional. Skip it when the dialog returns None/NO/OFF
        # or when its floor count is 0. This keeps the original single-peak
        # behaviour clean and avoids a hidden second slope.
        if corner is None:
            continue
        corner_txt = str(corner).upper().strip()
        if corner_txt in ("", "NONE", "NO", "OFF"):
            continue
        try:
            floors_i = int(floors)
        except Exception:
            continue
        if floors_i <= 0:
            continue

        desired_px, desired_py = peak_point(NX, NY, corner_txt)
        # Prefer a different active cell for the second peak if possible.
        candidates = [c for c in module_cells if c not in used_cells] or list(module_cells)
        actual_peak = min(candidates, key=lambda c: (c[0] - desired_px) ** 2 + (c[1] - desired_py) ** 2)
        used_cells.add(actual_peak)
        maxd = max([math.sqrt((c[0] - actual_peak[0]) ** 2 + (c[1] - actual_peak[1]) ** 2) for c in module_cells] or [1.0])
        _PEAK_DATA.append((actual_peak[0], actual_peak[1], floors_i, float(maxd), corner_txt))

    # Backwards-compatible primary peak = tallest selected peak.
    if _PEAK_DATA:
        primary = max(_PEAK_DATA, key=lambda p: p[2])
        _PEAK_OVERRIDE = (primary[0], primary[1])
        _MAXD_OVERRIDE = primary[3]


def normalized_distance_from_peak(cx, cy, NX, NY, peak_corner):
    """Return distance to the nearest ACTIVE peak, normalized 0..1.

    Opening and B-accent logic uses this nearest-peak distance, so both peaks
    receive protected/high zones instead of only the first peak.
    """
    global _PEAK_DATA, _PEAK_OVERRIDE, _MAXD_OVERRIDE

    if _PEAK_DATA:
        vals = []
        for px, py, pf, maxd, corner in _PEAK_DATA:
            dx = float(cx - px)
            dy = float(cy - py)
            d = math.sqrt(dx * dx + dy * dy)
            vals.append(d / max(0.001, float(maxd)))
        return max(0.0, min(1.0, min(vals)))

    if _PEAK_OVERRIDE is not None:
        px, py = _PEAK_OVERRIDE
    else:
        px, py = peak_point(NX, NY, peak_corner)
    dx = float(cx - px)
    dy = float(cy - py)
    d = math.sqrt(dx * dx + dy * dy)
    if _MAXD_OVERRIDE is not None and _MAXD_OVERRIDE > 0:
        maxd = float(_MAXD_OVERRIDE)
    else:
        maxd = math.sqrt(float((NX - 1) ** 2 + (NY - 1) ** 2))
    if maxd <= 0:
        return 0.0
    return max(0.0, min(1.0, d / maxd))

# ---------------------------------------------------------------------
# CURVED HEIGHT FIELD
# ---------------------------------------------------------------------
def curved_floor_count(cx, cy, NX, NY, peak1_corner, peak_floors, base_floors, curve_power):
    """Curved two-peak height field with TRUE base-floor falloff.

    Earlier versions normalised each peak by the farthest active module cell.
    With two tall peaks this made almost the entire ring stay high, so selecting
    base_floors = 1 still produced a bulky 5-8 floor mass.

    This version uses a shorter influence radius for each peak. Beyond that
    radius, cells return to base_floors. The selected peak cell is still forced
    to the exact peak height.
    """
    global _PEAK_DATA

    base_i = int(base_floors)

    # v13q: cap-based height field. The curve falls from the edge of a
    # corner-most square cap, so the top stays complete and the valley gets
    # a stronger concave profile.
    global _PEAK_CAP_DATA
    if _PEAK_CAP_DATA:
        best = base_i
        for cap_cells, pfloors, maxd, corner in _PEAK_CAP_DATA:
            pf_i = int(pfloors)
            if (cx, cy) in cap_cells:
                floors = pf_i
            else:
                d = min([math.sqrt((cx-cc[0])**2 + (cy-cc[1])**2) for cc in cap_cells] or [maxd])
                radius = max(1.0, float(maxd) * SLOPE_RADIUS_FACTOR)
                t = max(0.0, min(1.0, d / radius))
                # boosted power = stronger drop; not a soft bulky mound.
                pwr = max(1.0, float(curve_power) + SLOPE_POWER_BOOST)
                curve = max(0.0, 1.0 - t) ** pwr
                floors = int(math.floor(base_i + (pf_i - base_i) * curve))
            floors = max(base_i, min(pf_i, int(floors)))
            if floors > best:
                best = floors
        return best

    if _PEAK_DATA:
        best = base_i
        for px, py, pfloors, maxd, corner in _PEAK_DATA:
            pf_i = int(pfloors)
            dx = float(cx - px)
            dy = float(cy - py)
            d = math.sqrt(dx * dx + dy * dy)

            # Shorter radius = steeper falloff and real low base zones.
            # Do not normalise to the full plot diagonal.
            radius = max(1.0, float(maxd) * HEIGHT_RADIUS_FACTOR)
            t = max(0.0, min(1.0, d / radius))

            # Keep only a compact tower cap at full height.
            if t <= PEAK_PLATEAU_T:
                floors = pf_i
            else:
                curve = max(0.0, 1.0 - t) ** float(curve_power)
                floors = int(math.floor(base_i + (pf_i - base_i) * curve))

            floors = max(base_i, min(pf_i, int(floors)))
            if floors > best:
                best = floors
        return best

    # Fallback single peak behaviour.
    t = normalized_distance_from_peak(cx, cy, NX, NY, peak1_corner)
    # Apply same radius correction in fallback using the normalised value.
    # t is already 0..1 to farthest cell, so re-map it to a shorter radius.
    t = max(0.0, min(1.0, t / HEIGHT_RADIUS_FACTOR))
    if t <= PEAK_PLATEAU_T:
        return int(peak_floors)
    curve = max(0.0, 1.0 - t) ** float(curve_power)
    floors = int(math.floor(base_i + (int(peak_floors) - base_i) * curve))
    floors = max(base_i, min(int(peak_floors), floors))
    return floors


# ---------------------------------------------------------------------
# CORE LOGIC: 2x2 INNER-BLOCK CORES = 7.5 m x 7.5 m
# ---------------------------------------------------------------------
def corridor_bounds_from_cells(corridor_cells):
    """Return west, east, south, north corridor cell coordinates."""
    if not corridor_cells:
        return None
    xs = [c[0] for c in corridor_cells]
    ys = [c[1] for c in corridor_cells]
    return min(xs), max(xs), min(ys), max(ys)


def core_cells_for_item(cx, cy, orient=None):
    """Core footprint cells. New v14m core = 2x2 cells = 7.5 m x 7.5 m.

    The core replaces the two perpendicular A-module positions at each
    inner block corner. It is a single square service core and no longer
    uses the old 1x3 bar logic.
    """
    return [(cx, cy), (cx + 1, cy), (cx, cy + 1), (cx + 1, cy + 1)]


def core_access_clearance_cells_for_item(cx, cy, orient, NX, NY):
    """No extra clearance deletion. The corridor loop itself gives access."""
    return set()


def core_passage_cells_for_item(cx, cy, orient, NX, NY, corridor_cells=None):
    """No extra passage deletion for the new 2x2 inner-corner cores.

    The 2x2 core sits in the non-ventilated inner block corner module zone,
    beside the corridor junction. The corridor remains the fixed rectangular
    loop, so only the core footprint is reserved.
    """
    return set()


def _clip_core_origin(cx, cy, orient, NX, NY):
    """Keep 2x2 core footprint inside model grid."""
    cx = max(0, min(NX - 2, cx))
    cy = max(0, min(NY - 2, cy))
    return cx, cy


def _core_at_corner(corner, west, east, south, north, NX, NY):
    """Place one 2x2 core at each inner block corner.

    Gowthaman v14m correction:
      - Delete old 1x3 bar cores.
      - Use the perfect positions marked in plan: the two A-module cells at
        each inner block corner, which have poor ventilation and do not
        disturb the room rows.
      - Core size = 7.5 m x 7.5 m = 2 cells x 2 cells.
      - The corridor rectangle remains unchanged and wraps beside the core.
    """
    c = (corner or "NE").upper()
    orient = "SQ"

    # Corridor rectangle bounds. Core is placed just inside the corridor loop,
    # replacing the 2x2 inner module corner blocks.
    if c == "NW":
        cx, cy = west + 1, north - 2
    elif c == "NE":
        cx, cy = east - 2, north - 2
    elif c == "SW":
        cx, cy = west + 1, south + 1
    else:  # SE
        cx, cy = east - 2, south + 1

    cx, cy = _clip_core_origin(cx, cy, orient, NX, NY)
    return (cx, cy, orient)

def opposite_corner(corner):
    c = (corner or "NE").upper()
    return {"NE": "SW", "SW": "NE", "NW": "SE", "SE": "NW"}.get(c, "SW")


def get_core_positions(NX, NY, corridor_cells, peak1_corner=None):
    """Return FOUR core items, one at each corridor corner.

    Gowthaman correction v13s:
      - Keep the same good corner-core position from v13r.
      - But do it at ALL FOUR corridor corners, not only at the peak corner
        and the diagonal corner.
      - Each core is still 3.75 m x 11.25 m = 1 cell x 3 cells.
      - Height is NOT globally peak_floors anymore; it is calculated later from
        the local floors it must serve.
    """
    b = corridor_bounds_from_cells(corridor_cells)
    if b is None:
        return []
    west, east, south, north = b

    # Order peak-side first only for readability/debugging; all four are used.
    pc = (peak1_corner or "NE").upper()
    corners = [pc] if pc in ("NE", "NW", "SE", "SW") else []
    for c in ("NE", "NW", "SE", "SW"):
        if c not in corners:
            corners.append(c)

    cores = []
    used = set()
    for corner in corners:
        item = _core_at_corner(corner, west, east, south, north, NX, NY)
        cells = [c for c in core_cells_for_item(*item) if is_in_cluster(c[0], c[1], NX, NY)]
        # Avoid duplicate overlap if the footprint is very small.
        if any(c in used for c in cells):
            continue
        used.update(cells)
        cores.append(item)
    return cores


def _core_corridor_probe_cells_for_item(item, core_cells, cell_floor_counts, NX, NY):
    """Cells used only for core-height calculation.

    v14o core-height correction:
      The 2x2 core is not only serving the modules that physically touch the
      green core. It also serves the module band on the OTHER side of the
      corridor directly connected to that core corner.

    Therefore, for every corridor cell touching the core footprint, probe the
    cells across that corridor line. This catches the taller modules connected
    through the corridor without scanning the entire corridor arm.

    This changes ONLY the green core height. It does not move, delete, rotate,
    or add any A modules.
    """
    core_set = set(core_cells or [])
    cells = [c for c in core_cells_for_item(*item) if is_in_cluster(c[0], c[1], NX, NY)]
    probes = set()

    # 1) Keep old stable local behaviour: the cells directly surrounding core.
    for x, y in cells:
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                nx, ny = x + dx, y + dy
                if is_in_cluster(nx, ny, NX, NY):
                    probes.add((nx, ny))

    # 2) Add the opposite side of the corridor, but only locally.
    # A cell with floor_count == 0 beside the core is treated as possible corridor/void.
    # From that corridor cell, look one and two cells further in the same direction.
    # This reaches the opposite room band served by the same corridor corner.
    dirs = [(1,0), (-1,0), (0,1), (0,-1)]
    for x, y in cells:
        for dx, dy in dirs:
            cx, cy = x + dx, y + dy
            if not is_in_cluster(cx, cy, NX, NY):
                continue

            # Only use this direction if the immediate neighbour is a non-module void/corridor
            # or a very low/empty cell. This avoids scanning through solid room blocks.
            if int(cell_floor_counts.get((cx, cy), 0)) > 0 and (cx, cy) not in core_set:
                continue

            # Across corridor: first and second cells beyond the corridor line.
            for step in (1, 2):
                ax, ay = cx + dx * step, cy + dy * step
                if is_in_cluster(ax, ay, NX, NY):
                    probes.add((ax, ay))

            # Also sample one cell left/right along the corridor direction, so a 2x2 core
            # catches the complete local corridor junction instead of only a single grid line.
            if dx != 0:
                side_offsets = [(0, -1), (0, 1)]
            else:
                side_offsets = [(-1, 0), (1, 0)]
            for sx, sy in side_offsets:
                for step in (1, 2):
                    ax, ay = cx + dx * step + sx, cy + dy * step + sy
                    if is_in_cluster(ax, ay, NX, NY):
                        probes.add((ax, ay))

    return probes


def local_core_floor_counts(core_items, core_cells, cell_floor_counts, NX, NY, base_floors, peak_specs=None):
    """Each 2x2 core rises to the user-selected PEAK HEIGHT of its nearest corner.

    Gowthaman v14q correction:
      - No adjacent-cell probing.
      - No corridor-arm scanning.
      - No local cascade reading.
      - The NE core height = NE user peak floors, NW core = NW peak floors,
        SE core = SE peak floors, SW core = SW peak floors.

    This makes the core logic deterministic, clear, and jury-defensible.
    The 2x2 core position and all module/opening/interlock logic are unchanged.
    """
    result = {}

    peak_lookup = {}
    if peak_specs:
        for corner, floors in peak_specs:
            corner_key = str(corner).upper().strip()
            try:
                peak_lookup[corner_key] = int(floors)
            except Exception:
                pass

    cx_center = NX / 2.0
    cy_center = NY / 2.0
    base_i = int(base_floors)

    for item in core_items:
        footprint = [c for c in core_cells_for_item(*item) if is_in_cluster(c[0], c[1], NX, NY)]
        if not footprint:
            continue

        # Use the average footprint centre, not only the anchor cell, so a 2x2 core
        # is assigned reliably to its quadrant/corner.
        avg_x = sum(c[0] for c in footprint) / float(len(footprint))
        avg_y = sum(c[1] for c in footprint) / float(len(footprint))

        is_east = avg_x >= cx_center
        is_north = avg_y >= cy_center

        if is_north and is_east:
            corner = "NE"
        elif is_north and not is_east:
            corner = "NW"
        elif (not is_north) and is_east:
            corner = "SE"
        else:
            corner = "SW"

        core_height = peak_lookup.get(corner, base_i)
        if core_height < base_i:
            core_height = base_i

        result[item] = int(core_height)

    return result

def bake_cores(core_items, core_floor_counts):
    """Bake each core as a 120 mm wall shell, not a solid block.

    v20 detailing correction:
      - Core outer footprint stays 7.50 m x 7.50 m.
      - Core wall thickness = CORE_WALL_T = 0.12 m.
      - Inner clear core becomes 7.26 m x 7.26 m.
      - Internal stair/lift layout is intentionally not modelled here.
    """
    count = 0
    t = float(CORE_WALL_T)
    for item in core_items:
        cx, cy, orient = item
        x = cx * GRID
        y = cy * GRID
        dx = 2 * GRID
        dy = 2 * GRID
        floors = int(core_floor_counts.get(item, 1))
        dz = max(1, floors) * FLOOR_H

        # Four wall bars. East/west use dy - 2t so corners do not overlap.
        walls = [
            make_box(x,          y,          0, dx, t,  dz),              # south wall
            make_box(x,          y + dy - t, 0, dx, t,  dz),              # north wall
            make_box(x,          y + t,      0, t,  dy - 2*t, dz),        # west wall
            make_box(x + dx - t, y + t,      0, t,  dy - 2*t, dz),        # east wall
        ]
        for brep in walls:
            bake_brep(brep, "core_wall")
        count += 1
    return count


def _merge_corridor_cells_to_rects(cells):
    """Merge same-level corridor cells into clean rectangular runs.

    This keeps corridor floors readable as clean slabs instead of hundreds of
    isolated 3.75 x 3.75 plates. It first makes horizontal runs, then merges
    identical runs vertically.
    """
    cells = set(cells or [])
    if not cells:
        return []

    # Horizontal runs per row.
    row_runs = {}
    ys = sorted(set(y for x, y in cells))
    for y in ys:
        xs = sorted(x for x, yy in cells if yy == y)
        runs = []
        if xs:
            start = prev = xs[0]
            for x in xs[1:]:
                if x == prev + 1:
                    prev = x
                else:
                    runs.append((start, prev))
                    start = prev = x
            runs.append((start, prev))
        row_runs[y] = runs

    # Merge vertically when same x-span repeats on adjacent rows.
    rects = []
    used = set()
    for y in ys:
        for run in row_runs.get(y, []):
            if (y, run) in used:
                continue
            y0 = y1 = y
            used.add((y, run))
            yy = y + 1
            while yy in row_runs and run in row_runs[yy]:
                used.add((yy, run))
                y1 = yy
                yy += 1
            rects.append((run[0], y0, run[1], y1))
    return rects


def corridor_cell_active_at_level(c, level, cell_floor_counts, core_cells=None):
    """Corridor exists only where it serves RESIDENTIAL MODULES at that floor.

    v20/v04 correction:
      The previous version returned True whenever a corridor cell touched a
      core. Since core height follows the nearest peak, it created floating
      corridor slabs at high levels around tall cores even where no rooms
      existed. That is what Gowthaman marked.

    Correct rule:
      A corridor floor plate appears on a given floor only when at least one
      adjacent room/module cell still exists on that floor. Core cells alone
      do NOT extend the corridor upward.
    """
    x, y = c
    core_cells = core_cells or set()
    for dx, dy in ((1,0), (-1,0), (0,1), (0,-1)):
        nb = (x + dx, y + dy)
        if nb in core_cells:
            continue
        if int(cell_floor_counts.get(nb, 0)) > int(level):
            return True
    return False


def bake_projection_corridor_bridge(original_rect, projected_rect, level, proj_depth):
    """Bake a 90 mm walkable connector slab when a module projects outward.

    Projection moves the room module away from the original corridor-side
    footprint. Without a connector slab, the user cannot walk from corridor
    into the projected room. This function creates the swept floor area between
    the original footprint and the projected footprint.

    It is only called for projected modules and does not alter module geometry.
    """
    if abs(float(proj_depth)) <= 0.001:
        return 0

    ox0, oy0, ox1, oy1 = original_rect
    px0, py0, px1, py1 = projected_rect

    x0 = min(ox0, px0)
    y0 = min(oy0, py0)
    x1 = max(ox1, px1)
    y1 = max(oy1, py1)

    # Avoid zero-area accidents.
    if (x1 - x0) <= 0.001 or (y1 - y0) <= 0.001:
        return 0

    z = int(level) * FLOOR_H
    brep = make_box(x0, y0, z, x1 - x0, y1 - y0, CORRIDOR_SLAB_T)
    bake_brep(brep, "corridor_bridge")
    return 1


def bake_corridor_slabs(corridor_cells, cell_floor_counts, core_cells, peak_floors):
    """Bake 90 mm corridor floor slabs on every floor where modules exist.

    The slab is placed at each floor level as a walkable surface:
      slab size per merged rectangle = grid footprint x CORRIDOR_SLAB_T

    It is based on adjacent module/core height per floor, so each corridor arm
    naturally cascades and ends at the last module it serves.
    """
    count = 0
    corridor_cells = set(corridor_cells or [])
    core_cells = set(core_cells or [])

    for level in range(int(peak_floors)):
        active = set()
        for c in corridor_cells:
            if corridor_cell_active_at_level(c, level, cell_floor_counts, core_cells):
                active.add(c)

        for x0, y0, x1, y1 in _merge_corridor_cells_to_rects(active):
            x = x0 * GRID
            y = y0 * GRID
            dx = (x1 - x0 + 1) * GRID
            dy = (y1 - y0 + 1) * GRID
            z = level * FLOOR_H
            brep = make_box(x, y, z, dx, dy, CORRIDOR_SLAB_T)
            bake_brep(brep, "corridor_slab")
            count += 1

    return count


def peak_cap_cells_for_item(cx, cy, orient, NX, NY, size=None):
    """Return a compact square of cells around a 1x3 core.

    Gowthaman correction v13q:
      The visible top floor should read as a complete modular tower cap, not
      as a green service core sticking out of an incomplete cube.

    Logic:
      - Core footprint stays 1 cell x 3 cells = 3.75 x 11.25 m.
      - Around it, create a square cap zone, default 5x5 cells.
      - Core cells are excluded from module placement.
      - Cap cells are forced to the local peak height and protected from
        opening cuts, so A modules can wrap the core at the top.
      - Nothing is baked here; this only modifies the height/module masks.
    """
    if size is None:
        size = PEAK_CAP_CELLS
    size = max(3, int(size))
    if size % 2 == 0:
        size += 1

    core = core_cells_for_item(cx, cy, orient)
    xs = [c[0] for c in core]
    ys = [c[1] for c in core]
    cx_mid = int(round((min(xs) + max(xs)) / 2.0))
    cy_mid = int(round((min(ys) + max(ys)) / 2.0))

    half = size // 2
    ox = cx_mid - half
    oy = cy_mid - half

    # Clip the square back inside the cluster while keeping its size when possible.
    ox = max(0, min(NX - size, ox)) if NX >= size else 0
    oy = max(0, min(NY - size, oy)) if NY >= size else 0

    cells = set()
    core_set = set(core)
    for ix in range(ox, min(NX, ox + size)):
        for iy in range(oy, min(NY, oy + size)):
            if (ix, iy) in core_set:
                continue
            cells.add((ix, iy))
    return cells

# ---------------------------------------------------------------------
# PARAMETRIC OPENINGS: TWO SIZES ONLY
# ---------------------------------------------------------------------
def preferred_opening_axis(cx, cy, NX, NY, c0x, c0y, cw, ch):
    """Return axis for a 2-cell opening: 'X' or 'Y'."""
    cl = classify_cell(cx, cy, NX, NY, c0x, c0y, cw, ch)
    if cl in ("outer_long", "inner_long"):
        return "X"
    if cl in ("outer_short", "inner_short"):
        return "Y"
    # middle: follow longer plot direction
    return "X" if NX >= NY else "Y"


def opening_allowed_zone(cx, cy, level, fc, NX, NY, peak_corner, peak_floors, base_floors):
    """Protect tower peak, ground/base stability, and very top cells."""
    if level <= 0:
        return False
    if fc <= base_floors + 1:
        return False
    if level >= fc - 1:
        return False

    t = normalized_distance_from_peak(cx, cy, NX, NY, peak_corner)

    # Protect compact high peak zone: keep it strong, no medium cuts near apex.
    if t < 0.18 and level > int(0.45 * peak_floors):
        return False

    # Openings mainly in cascade zone, not far flat base and not tight apex.
    if t < 0.16 or t > 0.78:
        return False

    # Use middle floors more than bottom/top.
    vertical_ratio = float(level) / float(max(1, peak_floors - 1))
    if vertical_ratio < 0.14 or vertical_ratio > 0.78:
        return False

    return True


def is_structural_keep_cell(cx, cy, level):
    """
    Deterministic support rhythm.
    These cells are never carved, so the model does not become completely perforated.
    """
    if level <= 1:
        return True
    # Leave vertical ribs every 4 cells in either direction.
    if cx % 4 == 0 and level % 2 == 0:
        return True
    if cy % 4 == 0 and level % 3 == 0:
        return True
    return False


def build_opening_mask(NX, NY, c0x, c0y, cw, ch, cell_floor_counts,
                       peak_corner, peak_floors, base_floors, strength,
                       core_cells=None):
    """
    Create deterministic opening mask.

    Opening types:
      O1 = 1 cell x 1 floor
      O2 = 2 cells x 1 floor, same length as A module

    They are not baked as geometry; they remove candidate cells before A/B placement.
    """
    mask = set()
    opening_boxes = []  # for optional red outline/reference curves if needed later
    core_cells = core_cells or set()

    if strength <= 0:
        return mask, opening_boxes

    # Period controls density. Lower = more holes.
    if strength == 1:
        small_period = 11
        medium_period = 13
    elif strength == 3:
        small_period = 6
        medium_period = 8
    else:
        small_period = 8
        medium_period = 10

    # Work level-by-level so 2-cell openings can reserve both cells.
    for level in range(peak_floors):
        reserved_this_level = set()
        for cy in range(NY):
            for cx in range(NX):
                if is_courtyard(cx, cy, c0x, c0y, cw, ch):
                    continue
                if (cx, cy) in core_cells or (cx, cy) in core_passage_cells or (cx, cy) in corridor_cells:
                    continue
                if (cx, cy, level) in mask or (cx, cy) in reserved_this_level:
                    continue

                fc = cell_floor_counts.get((cx, cy), 0)
                if level >= fc:
                    continue

                if not opening_allowed_zone(cx, cy, level, fc, NX, NY, peak_corner, peak_floors, base_floors):
                    continue
                if is_structural_keep_cell(cx, cy, level):
                    continue

                t = normalized_distance_from_peak(cx, cy, NX, NY, peak_corner)
                vertical_ratio = float(level) / float(max(1, peak_floors - 1))

                # Medium openings in the main cascade band. They steepen the silhouette.
                # This is a deterministic shifted rhythm, not random.
                medium_zone = (0.26 <= t <= 0.66) and (0.22 <= vertical_ratio <= 0.68)
                medium_seed = (cx * 2 + cy * 3 + level * 5) % medium_period == 0

                if medium_zone and medium_seed:
                    axis = preferred_opening_axis(cx, cy, NX, NY, c0x, c0y, cw, ch)
                    neighbours = [(1, 0), (-1, 0)] if axis == "X" else [(0, 1), (0, -1)]
                    made = False
                    for dx, dy in neighbours:
                        nx, ny = cx + dx, cy + dy
                        if not is_in_cluster(nx, ny, NX, NY):
                            continue
                        if is_courtyard(nx, ny, c0x, c0y, cw, ch):
                            continue
                        if (nx, ny) in core_cells:
                            continue
                        if (nx, ny, level) in mask or (nx, ny) in reserved_this_level:
                            continue
                        nfc = cell_floor_counts.get((nx, ny), 0)
                        if level >= nfc:
                            continue
                        if is_structural_keep_cell(nx, ny, level):
                            continue
                        # create O2 = 2-cell opening
                        mask.add((cx, cy, level))
                        mask.add((nx, ny, level))
                        reserved_this_level.add((cx, cy))
                        reserved_this_level.add((nx, ny))
                        opening_boxes.append((cx, cy, level, nx, ny, "O2"))
                        made = True
                        break
                    if made:
                        continue

                # Small openings: lighter, used around the middle/lower cascade.
                small_zone = (0.22 <= t <= 0.74) and (0.16 <= vertical_ratio <= 0.58)
                small_seed = (cx * 5 + cy * 2 + level * 3) % small_period == 0
                if small_zone and small_seed:
                    mask.add((cx, cy, level))
                    reserved_this_level.add((cx, cy))
                    opening_boxes.append((cx, cy, level, cx, cy, "O1"))

    return mask, opening_boxes



def height_perforation_factor(level, peak_floors):
    """Return multiplier (0.05 to 2.0) based on vertical position."""
    if peak_floors <= 1:
        return 0.0
    frac = float(level) / float(max(1, peak_floors - 1))
    for i in range(len(PERFORATION_GRADIENT) - 1):
        f0, m0 = PERFORATION_GRADIENT[i]
        f1, m1 = PERFORATION_GRADIENT[i + 1]
        if f0 <= frac <= f1:
            t = (frac - f0) / (f1 - f0) if f1 > f0 else 0.0
            return m0 + t * (m1 - m0)
    return PERFORATION_GRADIENT[-1][1]


def is_perforation_void(cx, cy, level, NX, NY, c0x, c0y, cw, ch,
                        cell_floor_counts, peak_floors, base_floors,
                        core_cells, core_passage_cells, corridor_cells,
                        perforation_pct):
    """Return True when this cell/floor is removed as a controlled façade void.

    The percentage is an average density. Actual density is height-weighted:
    lower levels stay solid, upper/cascade/peak levels get more voids.
    Voids only happen on outer façade cells, never in the courtyard band,
    corridor, cores, core passages, or outer corner anchors.
    """
    if perforation_pct <= 0:
        return False

    p = (cx, cy)
    fc = cell_floor_counts.get(p, 0)
    if fc <= 0 or level >= fc:
        return False

    # Protect plinth and the local top cap.
    if level < PERFORATION_PROTECT_PLINTH:
        return False
    if level >= fc - PERFORATION_PROTECT_CAP:
        return False

    core_cells = core_cells or set()
    core_passage_cells = core_passage_cells or set()
    corridor_cells = corridor_cells or set()

    if p in core_cells or p in core_passage_cells or p in corridor_cells:
        return False

    # Only outer facade, not courtyard-facing inner band.
    cl = classify_cell(cx, cy, NX, NY, c0x, c0y, cw, ch)
    if cl in ("inner_long", "inner_short", "inner_corner"):
        return False
    if cl == "outer_corner":
        return False

    avg_density = max(0.0, min(50.0, float(perforation_pct))) / 100.0
    height_mult = height_perforation_factor(level, peak_floors)
    local_density = min(0.5, avg_density * height_mult)

    # Deterministic hash = repeatable, not random.
    h = (cx * 73 + cy * 137 + level * 257) % 1000
    threshold = int(local_density * 1000)
    if h >= threshold:
        return False

    # No vertical stack of voids in the same cell.
    if level + 1 < fc:
        h_above = (cx * 73 + cy * 137 + (level + 1) * 257) % 1000
        if h_above < threshold:
            return False
    if level > 0:
        h_below = (cx * 73 + cy * 137 + (level - 1) * 257) % 1000
        if h_below < threshold:
            return False

    # No three-wide horizontal void bands.
    h_left = (((cx - 1) * 73 + cy * 137 + level * 257) % 1000) < threshold
    h_right = (((cx + 1) * 73 + cy * 137 + level * 257) % 1000) < threshold
    if h_left and h_right:
        return False

    return True


def build_perforation_mask(NX, NY, c0x, c0y, cw, ch, cell_floor_counts,
                           peak_floors, base_floors, core_cells,
                           core_passage_cells, corridor_cells,
                           perforation_pct):
    """Create a 1-cell-deep façade perforation mask from percentage input."""
    mask = set()
    opening_boxes = []
    if perforation_pct <= 0:
        return mask, opening_boxes
    for level in range(int(peak_floors)):
        for cy in range(NY):
            for cx in range(NX):
                if is_perforation_void(cx, cy, level, NX, NY, c0x, c0y, cw, ch,
                                       cell_floor_counts, peak_floors, base_floors,
                                       core_cells, core_passage_cells, corridor_cells,
                                       perforation_pct):
                    mask.add((cx, cy, level))
                    opening_boxes.append((cx, cy, level, cx, cy, "P1"))
    return mask, opening_boxes

# ---------------------------------------------------------------------
# MODULE PLACEMENT
# ---------------------------------------------------------------------
def cell_active(cx, cy, level, cell_floor_counts, opening_mask, occupied_3d):
    if level >= cell_floor_counts.get((cx, cy), 0):
        return False
    if (cx, cy, level) in opening_mask:
        return False
    if (cx, cy, level) in occupied_3d:
        return False
    return True


def can_place_A(cx, cy, nx, ny, level, placed_2d, cell_floor_counts, opening_mask, occupied_3d):
    if (cx, cy) in placed_2d or (nx, ny) in placed_2d:
        return False
    if not cell_active(cx, cy, level, cell_floor_counts, opening_mask, occupied_3d):
        return False
    if not cell_active(nx, ny, level, cell_floor_counts, opening_mask, occupied_3d):
        return False
    return True


def can_place_B(cx, cy, level, placed_2d, cell_floor_counts, opening_mask, occupied_3d):
    if level % 2 != 0:
        return False
    if (cx, cy) in placed_2d:
        return False
    if not cell_active(cx, cy, level, cell_floor_counts, opening_mask, occupied_3d):
        return False
    if not cell_active(cx, cy, level + 1, cell_floor_counts, opening_mask, occupied_3d):
        return False
    return True


def _add_unique_direction(dirs, item):
    """Small helper for deterministic direction priority lists."""
    if item not in dirs:
        dirs.append(item)


def A_directions_for_cell(cx, cy, NX, NY, c0x, c0y, cw, ch):
    """Ventilated perpendicular A-module orientation only.

    A = 7.50 x 3.75 m and must span the 2-cell room band between
    corridor and facade/courtyard. The short end touches the corridor and
    the opposite short end touches the facade/courtyard.

    No parallel fallback is used here, because parallel modules reduce
    ventilation and break the room-corridor logic.
    """
    dirs = []

    d = RING_DEPTH_CELLS
    rb = ROOM_BAND_CELLS

    west_corr_x  = max(0, min(NX - 1, c0x - rb - 1))
    east_corr_x  = max(0, min(NX - 1, c0x + cw + rb))
    south_corr_y = max(0, min(NY - 1, c0y - rb - 1))
    north_corr_y = max(0, min(NY - 1, c0y + ch + rb))

    # SOUTH/NORTH arms: corridor runs along X, so rooms run in Y.
    if (c0x - d) <= cx < (c0x + cw + d):
        if (c0y - d) <= cy < c0y:
            if cy == south_corr_y - 1:
                _add_unique_direction(dirs, (0, -1))
            elif cy == south_corr_y - 2:
                _add_unique_direction(dirs, (0, 1))
            elif cy == south_corr_y + 1:
                _add_unique_direction(dirs, (0, 1))
            elif cy == south_corr_y + 2:
                _add_unique_direction(dirs, (0, -1))
        if (c0y + ch) <= cy < (c0y + ch + d):
            if cy == north_corr_y - 1:
                _add_unique_direction(dirs, (0, -1))
            elif cy == north_corr_y - 2:
                _add_unique_direction(dirs, (0, 1))
            elif cy == north_corr_y + 1:
                _add_unique_direction(dirs, (0, 1))
            elif cy == north_corr_y + 2:
                _add_unique_direction(dirs, (0, -1))

    # WEST/EAST arms: corridor runs along Y, so rooms run in X.
    if (c0y - d) <= cy < (c0y + ch + d):
        if (c0x - d) <= cx < c0x:
            if cx == west_corr_x - 1:
                _add_unique_direction(dirs, (-1, 0))
            elif cx == west_corr_x - 2:
                _add_unique_direction(dirs, (1, 0))
            elif cx == west_corr_x + 1:
                _add_unique_direction(dirs, (1, 0))
            elif cx == west_corr_x + 2:
                _add_unique_direction(dirs, (-1, 0))
        if (c0x + cw) <= cx < (c0x + cw + d):
            if cx == east_corr_x - 1:
                _add_unique_direction(dirs, (-1, 0))
            elif cx == east_corr_x - 2:
                _add_unique_direction(dirs, (1, 0))
            elif cx == east_corr_x + 1:
                _add_unique_direction(dirs, (1, 0))
            elif cx == east_corr_x + 2:
                _add_unique_direction(dirs, (-1, 0))

    return dirs

def facade_side_for_A_pair(cx, cy, nx, ny, NX, NY, c0x, c0y, cw, ch):
    """Return outer facade side for an A module pair, or None.

    Only OUTER facade modules are allowed to cantilever in this first step.
    Courtyard-facing modules are not moved yet.

    sides returned: 'N', 'S', 'E', 'W'
    """
    cells = [(cx, cy), (nx, ny)]
    d = RING_DEPTH_CELLS
    rb = ROOM_BAND_CELLS

    west_corr_x  = max(0, min(NX - 1, c0x - rb - 1))
    east_corr_x  = max(0, min(NX - 1, c0x + cw + rb))
    south_corr_y = max(0, min(NY - 1, c0y - rb - 1))
    north_corr_y = max(0, min(NY - 1, c0y + ch + rb))

    # Outer bands only: two cells outside each corridor line.
    # South outer band is below the south corridor.
    if all((c0x - d) <= x < (c0x + cw + d) for x, y in cells):
        if all(y in (south_corr_y - 1, south_corr_y - 2) for x, y in cells):
            return 'S'
        if all(y in (north_corr_y + 1, north_corr_y + 2) for x, y in cells):
            return 'N'

    # West/East outer bands.
    if all((c0y - d) <= y < (c0y + ch + d) for x, y in cells):
        if all(x in (west_corr_x - 1, west_corr_x - 2) for x, y in cells):
            return 'W'
        if all(x in (east_corr_x + 1, east_corr_x + 2) for x, y in cells):
            return 'E'

    return None




def is_outer_facade_perpendicular_pair(cx, cy, nx, ny, NX, NY, c0x, c0y, cw, ch):
    """True only for A pairs on the OUTER facade band.

    This keeps the inner courtyard wall and corridor side clean. The A module
    remains perpendicular to the corridor; this function only identifies the
    outer skin pairs where facade interlock/perforation may happen.
    """
    return facade_side_for_A_pair(cx, cy, nx, ny, NX, NY, c0x, c0y, cw, ch) is not None


def _pair_anchor(cx, cy, nx, ny, side):
    """Stable pair index for deterministic facade rhythm on all four sides."""
    if side in ('N', 'S'):
        return min(cx, nx), min(cy, ny)
    if side in ('E', 'W'):
        return min(cy, ny), min(cx, nx)
    return min(cx, nx), min(cy, ny)


def should_skip_pair_for_stage1_interlock(cx, cy, nx, ny, level, NX, NY, c0x, c0y, cw, ch,
                                          core_cells, core_passage_cells, corridor_cells,
                                          peak_floors):
    """Deprecated v14g skip logic.

    In v14h, Stage 1 is no longer random pair deletion. The two facade
    connection types are produced by half-cell in-plane offsets:
      Type 1 = direct vertical stacking, no offset.
      Type 2 = half-cell shifted stacking, still inside the rectangular footprint.

    Pair deletion is now reserved only for the Perforation % slider.
    Therefore this function always returns False. It remains only so older
    calls do not break if referenced elsewhere.
    """
    return False


def _rects_overlap(a, b, tol=1e-6):
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    return not (ax1 <= bx0 + tol or bx1 <= ax0 + tol or ay1 <= by0 + tol or by1 <= ay0 + tol)


def _rect_inside_cluster(rect, NX, NY, tol=1e-6):
    x0, y0, x1, y1 = rect
    return x0 >= -tol and y0 >= -tol and x1 <= NX * GRID + tol and y1 <= NY * GRID + tol


def _cell_rect(cx, cy):
    """Plan rectangle for one 3.75 m grid cell.

    Used as a physical collision guard. Logical cell checks are not enough
    after Type 2 facade interlock, because a shifted A module can start from
    legal cells but slide into a core/corridor/passage footprint.
    """
    return (cx * GRID, cy * GRID, (cx + 1) * GRID, (cy + 1) * GRID)


def _build_reserved_rects(core_cells=None, core_passage_cells=None, corridor_cells=None):
    """Physical no-overlap rectangles for cores, passages, and corridor.

    Only these reserved footprints are protected. Adjacent A modules are NOT
    deleted unless their final shifted rectangle actually overlaps one of
    these cells. This keeps the corridor/core logic clean without over-clearing
    the plan around the cores.
    """
    reserved = set(core_cells or set()) | set(core_passage_cells or set()) | set(corridor_cells or set())
    return [_cell_rect(cx, cy) for (cx, cy) in reserved]


def _rect_overlaps_any(rect, rects):
    return any(_rects_overlap(rect, r) for r in rects)


def _interlock_candidate_vectors(side, cx, cy, nx, ny, NX, NY):
    """Return half-cell tangent shifts for Type 2 facade bonding.

    The shift is parallel to the facade, not outward. It therefore creates a
    Habitat-like elevation bond without projection/cantilever. We try the
    primary direction first, then the opposite direction if it would leave the
    rectangle or overlap another already baked module.
    """
    if side in ('N', 'S'):
        anchor = min(cx, nx)
        # Bias toward the centre of the facade row so the shift stays in the rectangle.
        if anchor < (NX - 1) / 2.0:
            return [(INTERLOCK_SHIFT, 0.0), (-INTERLOCK_SHIFT, 0.0)]
        return [(-INTERLOCK_SHIFT, 0.0), (INTERLOCK_SHIFT, 0.0)]
    if side in ('E', 'W'):
        anchor = min(cy, ny)
        if anchor < (NY - 1) / 2.0:
            return [(0.0, INTERLOCK_SHIFT), (0.0, -INTERLOCK_SHIFT)]
        return [(0.0, -INTERLOCK_SHIFT), (0.0, INTERLOCK_SHIFT)]
    return [(0.0, 0.0)]


def facade_interlock_offset_for_A_pair(cx, cy, nx, ny, level, NX, NY, c0x, c0y, cw, ch,
                                       core_cells, core_passage_cells, corridor_cells,
                                       peak_floors, x0, y0, dx_box, dy_box, placed_rects):
    """Stage 1 facade interlock: Type 1 + Type 2 connections.

    Type 1: direct vertical stacking, no offset.
    Type 2: half-cell in-plane shift parallel to the outer facade.

    Critical guarantees:
      - A modules remain perpendicular to the corridor.
      - No projection outside the cluster rectangle.
      - No outward cantilever.
      - Cores/corridors/passages and corner anchors stay clean.
      - If a Type 2 shift would overlap a same-floor module, it falls back to
        Type 1 instead of creating bad geometry.
    """
    if level % 2 == 0:
        return (0.0, 0.0, 'T1')
    if level < STAGGER_PROTECT_PLINTH:
        return (0.0, 0.0, 'T1')
    if level >= peak_floors - STAGGER_PROTECT_CAP:
        return (0.0, 0.0, 'T1')

    cells = [(cx, cy), (nx, ny)]
    forbid = set(core_cells or set()) | set(core_passage_cells or set()) | set(corridor_cells or set())
    if any(p in forbid for p in cells):
        return (0.0, 0.0, 'T1')

    classes = [classify_cell(px, py, NX, NY, c0x, c0y, cw, ch) for px, py in cells]
    if 'outer_corner' in classes or 'inner_corner' in classes:
        return (0.0, 0.0, 'T1')

    side = facade_side_for_A_pair(cx, cy, nx, ny, NX, NY, c0x, c0y, cw, ch)
    if side is None:
        return (0.0, 0.0, 'T1')

    # Deterministic mixture: roughly half the odd-floor facade pairs use Type 2.
    ax, ay = _pair_anchor(cx, cy, nx, ny, side)
    h = (ax * 61 + ay * 149 + level * 211) % 100
    if h < 50:
        return (0.0, 0.0, 'T1')

    for ox, oy in _interlock_candidate_vectors(side, cx, cy, nx, ny, NX, NY):
        rect = (x0 + ox, y0 + oy, x0 + ox + dx_box, y0 + oy + dy_box)
        if not _rect_inside_cluster(rect, NX, NY):
            continue
        if any(_rects_overlap(rect, pr) for pr in placed_rects):
            continue
        return (ox, oy, 'T2')

    # v14i correction: if this pair was selected for Type 2 but cannot shift
    # without overlapping an already placed module, DO NOT force it back to
    # Type 1. Leave it empty. This is the manual cleanup Gowthaman showed:
    # overlapping facade blocks are deleted, while valid Type 1 and Type 2
    # connections remain readable.
    return (0.0, 0.0, 'SKIP_OVERLAP')



def _facade_pair_sequence(side, cx, cy, nx, ny):
    """Return the along-facade index for a perpendicular A pair."""
    if side in ('N', 'S'):
        return min(cx, nx)
    if side in ('E', 'W'):
        return min(cy, ny)
    return min(cx, nx)


def _facade_side_code(side):
    if side == 'N': return 11
    if side == 'S': return 23
    if side == 'E': return 37
    if side == 'W': return 41
    return 0


def _opening_hash(seq, level, side_code, salt=0):
    """Deterministic 0..999 rhythm value for repeatable facade openings."""
    return (seq * 83 + level * 277 + side_code * 31 + salt * 101) % 1000


def _raw_opening_candidate(seq, level, side_code, threshold, salt):
    """Low-level deterministic test used only for neighbour safety checks."""
    if threshold <= 0:
        return False
    return _opening_hash(seq, level, side_code, salt) < threshold


def _type1_single_opening(seq, level, side_code, threshold):
    """Type 1 = one clean A-pair opening."""
    return _raw_opening_candidate(seq, level, side_code, threshold, 1)


def _type3_supported_single_opening(seq, level, side_code, threshold):
    """Type 3 = wider-looking supported opening, but still only one A-pair removed.

    Earlier v14j removed two neighbouring A-pairs on the same floor. That made
    large holes and floating-looking modules. This corrected Type 3 uses the
    same visual family from Gowthaman's sketch, but it removes only the current
    A-pair and relies on adjacent placed pairs to keep the brick-stacking logic.
    """
    if threshold <= 0:
        return False
    if seq % 4 not in (1,):
        return False
    return _raw_opening_candidate(seq, level, side_code, threshold, 3)


def _type4_diagonal_supported_opening(seq, level, side_code, threshold):
    """Type 4 = diagonal/L rhythm, but no vertical shaft and no same-floor big void.

    The opening is a single pair at this floor. The diagonal reading comes from
    the deterministic rule alternating with the floor above/below; neighbour
    checks in should_skip_pair_for_stage2_perforation prevent a floating module
    or a two/three-pair hole.
    """
    if threshold <= 0 or level < 1:
        return False
    if (seq + level) % 5 not in (2,):
        return False
    return _raw_opening_candidate(seq, level, side_code, threshold, 4)


def pair_perforation_factor(level, peak_floors):
    """Use the same vertical gradient as the perforation slider, but at pair level."""
    return height_perforation_factor(level, peak_floors)


def _protected_pair(cx, cy, nx, ny, NX, NY, c0x, c0y, cw, ch,
                    core_cells, core_passage_cells, corridor_cells):
    """True when this A-pair must never be removed by facade perforation."""
    cells = [(cx, cy), (nx, ny)]
    forbid = set(core_cells or set()) | set(core_passage_cells or set()) | set(corridor_cells or set())
    if any(p in forbid for p in cells):
        return True
    classes = [classify_cell(px, py, NX, NY, c0x, c0y, cw, ch) for px, py in cells]
    # Corners are structural anchors; never perforate them.
    if 'outer_corner' in classes or 'inner_corner' in classes:
        return True
    return False


def _safe_predicted_opening(seq, level, side_code, t1, t3, t4):
    """Predict whether the same logic would make an opening at a neighbour.

    This is used only for safety; it deliberately mirrors the three opening
    families without needing the neighbour's full module coordinates.
    """
    if level < 0:
        return False
    return (_type1_single_opening(seq, level, side_code, t1) or
            _type3_supported_single_opening(seq, level, side_code, t3) or
            _type4_diagonal_supported_opening(seq, level, side_code, t4))


def should_skip_pair_for_stage2_perforation(cx, cy, nx, ny, level, NX, NY, c0x, c0y, cw, ch,
                                            cell_floor_counts, peak_floors, base_floors,
                                            core_cells, core_passage_cells, corridor_cells,
                                            perforation_pct):
    """Stage 2: support-aware facade openings at whole A-pair level.

    v14k correction:
      - No huge two-pair holes.
      - No vertical shaft of voids.
      - No floating-looking module above an unsupported void.
      - Type 1, Type 3 and Type 4 are distributed as single-pair openings.
      - Adjacent modules remain, so every opening still reads as part of the
        Habitat/brick-stacking logic.
    """
    if perforation_pct <= 0:
        return False

    fc = min(cell_floor_counts.get((cx, cy), 0), cell_floor_counts.get((nx, ny), 0))
    if fc <= 0 or level >= fc:
        return False

    # Solid plinth and solid local cap.
    if level < PERFORATION_PROTECT_PLINTH:
        return False
    if level >= fc - PERFORATION_PROTECT_CAP:
        return False

    if _protected_pair(cx, cy, nx, ny, NX, NY, c0x, c0y, cw, ch,
                       core_cells, core_passage_cells, corridor_cells):
        return False

    side = facade_side_for_A_pair(cx, cy, nx, ny, NX, NY, c0x, c0y, cw, ch)
    if side is None:
        return False

    avg_density = max(0.0, min(50.0, float(perforation_pct))) / 100.0
    height_mult = pair_perforation_factor(level, peak_floors)
    # Cap local density to keep the structural rhythm serious.
    local_density = min(0.28, avg_density * height_mult)
    if local_density <= 0.0:
        return False

    seq = _facade_pair_sequence(side, cx, cy, nx, ny)
    side_code = _facade_side_code(side)

    # Spread the total density over the three opening families.
    threshold_type1 = int(local_density * 0.58 * 1000)
    threshold_type3 = int(local_density * OPENING_TYPE3_FACTOR * 1000)
    threshold_type4 = int(local_density * OPENING_TYPE4_FACTOR * 1000)

    type1 = _type1_single_opening(seq, level, side_code, threshold_type1)
    type3 = _type3_supported_single_opening(seq, level, side_code, threshold_type3)
    type4 = _type4_diagonal_supported_opening(seq, level, side_code, threshold_type4)

    if not (type1 or type3 or type4):
        return False

    # ------------------------------------------------------------------
    # STRONGER SUPPORT + SCATTERING CHECKS (v14r safety)
    # ------------------------------------------------------------------

    # RULE A: No adjacent same-floor voids (seq-1, seq+1) -> no 2-pair holes
    if _safe_predicted_opening(seq - 1, level, side_code,
                               threshold_type1, threshold_type3, threshold_type4):
        return False
    if _safe_predicted_opening(seq + 1, level, side_code,
                               threshold_type1, threshold_type3, threshold_type4):
        return False

    # RULE B: Minimum scatter distance — no void within 2 pairs on same floor
    if _safe_predicted_opening(seq - 2, level, side_code,
                               threshold_type1, threshold_type3, threshold_type4):
        return False
    if _safe_predicted_opening(seq + 2, level, side_code,
                               threshold_type1, threshold_type3, threshold_type4):
        return False

    # RULE C: No vertical neighbor void (level-1, level+1) -> no 2-floor stacks
    if _safe_predicted_opening(seq, level - 1, side_code,
                               threshold_type1, threshold_type3, threshold_type4):
        return False
    if level + 1 < fc and _safe_predicted_opening(seq, level + 1, side_code,
                                                  threshold_type1, threshold_type3, threshold_type4):
        return False

    # RULE D: Minimum vertical scatter — no void within 2 floors above/below
    if level >= 2 and _safe_predicted_opening(seq, level - 2, side_code,
                                               threshold_type1, threshold_type3, threshold_type4):
        return False
    if level + 2 < fc and _safe_predicted_opening(seq, level + 2, side_code,
                                                  threshold_type1, threshold_type3, threshold_type4):
        return False

    # RULE E: Anti-floating — module ABOVE this void must have at least one
    # solid adjacent pair on its own floor. If both adjacent pairs above are
    # predicted voids, the module between would read as floating.
    if level + 1 < fc:
        left_above_void = _safe_predicted_opening(seq - 1, level + 1, side_code,
                                                   threshold_type1, threshold_type3, threshold_type4)
        right_above_void = _safe_predicted_opening(seq + 1, level + 1, side_code,
                                                    threshold_type1, threshold_type3, threshold_type4)
        if left_above_void and right_above_void:
            return False

    # RULE F: Anti-floating below — reject conditions that could create
    # unsupported L/bridge readings around the void.
    if level >= 1:
        left_below_void = _safe_predicted_opening(seq - 1, level - 1, side_code,
                                                   threshold_type1, threshold_type3, threshold_type4)
        right_below_void = _safe_predicted_opening(seq + 1, level - 1, side_code,
                                                    threshold_type1, threshold_type3, threshold_type4)
        if left_below_void and right_below_void:
            return False

    # RULE G: Diagonal corner check — prevent L-shaped 3-pair holes where
    # current void plus both diagonal voids above/below form a weak opening.
    if level >= 1:
        if _safe_predicted_opening(seq - 1, level - 1, side_code,
                                    threshold_type1, threshold_type3, threshold_type4):
            if _safe_predicted_opening(seq + 1, level - 1, side_code,
                                        threshold_type1, threshold_type3, threshold_type4):
                return False
    if level + 1 < fc:
        if _safe_predicted_opening(seq - 1, level + 1, side_code,
                                    threshold_type1, threshold_type3, threshold_type4):
            if _safe_predicted_opening(seq + 1, level + 1, side_code,
                                        threshold_type1, threshold_type3, threshold_type4):
                return False

    return True

def cantilever_vector_for_side(side, depth):
    """Outward XY vector for a real moved/cantilevered module."""
    if side == 'N':
        return (0.0, depth)
    if side == 'S':
        return (0.0, -depth)
    if side == 'E':
        return (depth, 0.0)
    if side == 'W':
        return (-depth, 0.0)
    return (0.0, 0.0)


def cantilever_depth_for_A(cx, cy, nx, ny, level, NX, NY, c0x, c0y, cw, ch,
                           peak_floors, cell_floor_counts, core_cells):
    """Checkerboard/rhythm cantilever logic for outer facade A modules.

    This is NOT a facade extrusion. The whole 7.5 x 3.75 x 3.75 A module is
    translated outward by 0 / 1.5 / 3.0 m, while its logical grid cells remain
    reserved for corridor access and collision logic.

    Design rules:
      - only outer facade modules move in this first step
      - no cantilever from core cells
      - no cantilever on the ground/base floor, so the base stays stable
      - stronger near peak/cascade zones, lighter in low zones
      - deterministic checker rhythm: alternating blocks like the reference
    """
    side = facade_side_for_A_pair(cx, cy, nx, ny, NX, NY, c0x, c0y, cw, ch)
    if side is None:
        return (0.0, 0.0, 0.0)

    if (cx, cy) in core_cells or (nx, ny) in core_cells:
        return (0.0, 0.0, 0.0)

    # Keep first floor unshifted; cantilevers start above stable plinth.
    if level <= 0:
        return (0.0, 0.0, 0.0)

    # Use local height to avoid pushing modules that are already in very low areas.
    local_h = min(cell_floor_counts.get((cx, cy), 0), cell_floor_counts.get((nx, ny), 0))
    if local_h < 3:
        return (0.0, 0.0, 0.0)

    # Height factor. Top/cascade zones get more movement.
    frac = float(level) / float(max(1, peak_floors - 1))

    # One stable checker seed based on module anchor and floor.
    ax = min(cx, nx)
    ay = min(cy, ny)
    checker = (ax + ay + level) % 4
    checker2 = (2 * ax + ay + 3 * level) % 7

    depth = 0.0

    # Peak/top half: stronger checkerboard, alternating 3 m and 1.5 m.
    if frac >= 0.62:
        if checker in (0,):
            depth = CANTILEVER_FULL
        elif checker in (2,):
            depth = CANTILEVER_HALF
    # Middle cascade: more scattered half/full moves.
    elif frac >= 0.32:
        if checker2 in (0, 3):
            depth = CANTILEVER_HALF
        elif checker2 == 5:
            depth = CANTILEVER_FULL
    # Low zone: very occasional half-step only.
    else:
        if checker2 == 1 and local_h >= 5:
            depth = CANTILEVER_HALF

    # Clamp to the agreed maximum.
    depth = min(depth, CANTILEVER_MAX)
    ox, oy = cantilever_vector_for_side(side, depth)
    return (ox, oy, depth)




def outermost_facade_side_for_A_pair(cx, cy, nx, ny, NX, NY, c0x, c0y, cw, ch):
    """Return the OUTERMOST exposed facade side for an A module pair, or None.

    v20 projection correction:
    The previous version only detected modules whose BOTH grid cells sat on
    the same outer row/column. That caught modules oriented parallel to the
    facade, but missed modules whose SHORT face is exposed on the facade
    (example: an X-oriented A at the east/west edge, occupying x=NX-2 and
    x=NX-1). Those are exactly the small-face modules Gowthaman marked.

    Correct rule:
      - If any A-pair touches the outside boundary, that boundary face is
        exposed and can be projected.
      - Projection still moves the whole A module outward as one module.
      - Corner modules are protected later by is_outer_corner_A_pair().
      - Inner/corridor/courtyard rows are still ignored because they do not
        touch the outside boundary.

    Priority is deterministic. In a true outer corner overlap the later corner
    protection keeps it fixed anyway.
    """
    xs = [int(cx), int(nx)]
    ys = [int(cy), int(ny)]

    touches_N = max(ys) >= NY - 1
    touches_S = min(ys) <= 0
    touches_E = max(xs) >= NX - 1
    touches_W = min(xs) <= 0

    # Prefer the side with the larger outward contact. For normal A-pairs this
    # is unambiguous; for corner cases, corner protection will stop movement.
    if touches_N:
        return 'N'
    if touches_S:
        return 'S'
    if touches_E:
        return 'E'
    if touches_W:
        return 'W'

    return None


def is_outer_corner_A_pair(cx, cy, nx, ny, NX, NY, side):
    """Protect corner modules on every floor.

    A corner module is the first or last A pair at the end of an outer facade
    row. These remain fixed so the building keeps a clean structural corner.
    """
    if side in ('N', 'S'):
        xs = [cx, nx]
        return min(xs) <= 1 or max(xs) >= NX - 2
    if side in ('E', 'W'):
        ys = [cy, ny]
        return min(ys) <= 1 or max(ys) >= NY - 2
    return False


def exposed_face_type_for_A_pair(cx, cy, nx, ny, side):
    """Return 'long' or 'short' for the exposed facade face of this A module.

    A module orientation:
      X-oriented A: long faces are N/S, short faces are E/W.
      Y-oriented A: long faces are E/W, short faces are N/S.
    """
    orient = 'X' if cy == ny else 'Y'
    if orient == 'X':
        return 'long' if side in ('N', 'S') else 'short'
    return 'long' if side in ('E', 'W') else 'short'


def projection_depth_for_A_pair(cx, cy, nx, ny, level, side, face_type, projection_options):
    """Return projection depth in metres for the optional facade projection.

    mode='parametric': deterministic smooth/rhythmic values between 0 and max.
    mode='checker': alternating modules move to the full selected max.
    mode='skip': no movement.
    """
    if not projection_options:
        return 0.0

    mode = str(projection_options.get('mode', PROJECTION_MODE_SKIP)).lower()
    if mode == PROJECTION_MODE_SKIP:
        return 0.0

    max_depth = float(projection_options.get('short_max' if face_type == 'short' else 'long_max', 0.0))
    if max_depth <= 0.0:
        return 0.0

    ax = min(cx, nx)
    ay = min(cy, ny)
    side_seed = {'N': 1, 'S': 3, 'E': 5, 'W': 7}.get(side, 0)

    if mode == PROJECTION_MODE_CHECKER:
        return max_depth if ((ax + ay + level + side_seed) % 2 == 0) else 0.0

    if mode == PROJECTION_MODE_PARAMETRIC:
        # Deterministic pseudo-random projection between 0 and the selected max.
        # This gives the "random parametric 0..2m / 0..1m" facade texture while
        # staying repeatable every time the same model is generated.
        seed = (ax * 73856093) ^ (ay * 19349663) ^ (level * 83492791) ^ (side_seed * 2654435761)
        seed = abs(seed) % 1000
        value = float(seed) / 999.0  # 0.0 .. 1.0

        # Slightly soften the extremes so the facade does not become noisy.
        value = value * value * (3.0 - 2.0 * value)  # smoothstep
        return max_depth * value

    return 0.0


def facade_projection_offset_for_A_pair(cx, cy, nx, ny, level, NX, NY, c0x, c0y, cw, ch,
                                        core_cells, corridor_cells, projection_options):
    """Optional second-stage module projection, independent from cascade logic.

    It moves only the outermost facade row outward, away from the corridor.
    Corner modules, cores, corridor cells, and non-outer-row modules are not
    moved. Defaults to zero movement when projection_options['mode']='skip'.
    """
    if not projection_options or projection_options.get('mode', PROJECTION_MODE_SKIP) == PROJECTION_MODE_SKIP:
        return (0.0, 0.0, 0.0, None, None)

    side = outermost_facade_side_for_A_pair(cx, cy, nx, ny, NX, NY, c0x, c0y, cw, ch)
    if side is None:
        return (0.0, 0.0, 0.0, None, None)

    if is_outer_corner_A_pair(cx, cy, nx, ny, NX, NY, side):
        return (0.0, 0.0, 0.0, side, None)

    forbidden = set(core_cells or set()) | set(corridor_cells or set())
    if (cx, cy) in forbidden or (nx, ny) in forbidden:
        return (0.0, 0.0, 0.0, side, None)

    face_type = exposed_face_type_for_A_pair(cx, cy, nx, ny, side)
    depth = projection_depth_for_A_pair(cx, cy, nx, ny, level, side, face_type, projection_options)
    depth = max(0.0, min(depth, PROJECTION_DEFAULT_SHORT_MAX if face_type == 'short' else PROJECTION_DEFAULT_LONG_MAX))

    px, py = cantilever_vector_for_side(side, depth)
    return (px, py, depth, side, face_type)


def should_prefer_B(cx, cy, level, NX, NY, c0x, c0y, cw, ch, peak_corner, peak_floors):
    """
    Use B as controlled vertical accents, not as continuous blue stripes.
    """
    if level % 2 != 0:
        return False

    cl = classify_cell(cx, cy, NX, NY, c0x, c0y, cw, ch)
    t = normalized_distance_from_peak(cx, cy, NX, NY, peak_corner)

    # Corners and near-peak vertical accents.
    if cl in ("outer_corner", "inner_corner"):
        return True

    # Near peak: occasional vertical units, but not too dense.
    if t < 0.32 and (cx + 2 * cy + level) % 7 == 0:
        return True

    # Main cascade: rare B accents only.
    if 0.32 <= t <= 0.62 and (2 * cx + cy + level) % 11 == 0:
        return True

    return False


def place_modules(NX, NY, c0x, c0y, cw, ch, cell_floor_counts, opening_mask,
                  peak_corner, peak_floors, core_cells=None,
                  core_passage_cells=None, corridor_cells=None,
                  perforation_pct=0,
                  peak_ne_floors=0, peak_nw_floors=0,
                  peak_se_floors=0, peak_sw_floors=0,
                  base_floors=DEFAULT_BASE,
                  hourglass_sides=None,
                  manual_deletions=None,
                  projection_options=None):
    """
    A-ONLY VERSION.

    Keeps the full v13h logic exactly the same: corridor ring, courtyard,
    optional second peak, curved height field, openings, and 1.5A cores.

    Only change:
      - No B residential modules are generated.
      - No 3.75 x 3.75 x 3.75 filler cube is generated.
      - If a single cell cannot join with a neighbour to form A, it stays empty.

    Allowed residential module:
      A = 7.50 x 3.75 x 3.75 m
    """
    counts = {"A": 0, "B": 0, "O1": 0, "O2": 0, "CORE": 0}
    occupied_3d = set()
    core_cells = core_cells or set()
    core_passage_cells = core_passage_cells or set()
    corridor_cells = corridor_cells or set()
    manual_deletions = manual_deletions or set()
    projection_options = projection_options or {"mode": PROJECTION_MODE_SKIP,
                                                "short_max": 0.0,
                                                "long_max": 0.0}

    # v14l safety guard: no A module may physically overlap cores,
    # core passage cells, or the corridor loop after Type 2 facade interlock.
    # This is a physical rectangle check, not just a logical cell check.
    reserved_rects = _build_reserved_rects(core_cells, core_passage_cells, corridor_cells)

    for level in range(peak_floors):
        placed_2d = set()
        placed_rects = []
        for cy in range(NY):
            for cx in range(NX):
                if is_courtyard(cx, cy, c0x, c0y, cw, ch):
                    continue
                if (cx, cy) in core_cells or (cx, cy) in core_passage_cells or (cx, cy) in corridor_cells:
                    continue
                if not cell_active(cx, cy, level, cell_floor_counts, opening_mask, occupied_3d):
                    continue
                if (cx, cy) in placed_2d:
                    continue

                # MANUAL DELETION — user removed this (cell, floor) in elevation editor
                if (cx, cy, level) in manual_deletions:
                    continue

                # A module only: always true 7.5 x 3.75 x 3.75, no single filler.
                for dx, dy in A_directions_for_cell(cx, cy, NX, NY, c0x, c0y, cw, ch):
                    nx, ny = cx + dx, cy + dy
                    if not is_in_cluster(nx, ny, NX, NY):
                        continue
                    if is_courtyard(nx, ny, c0x, c0y, cw, ch):
                        continue
                    if (nx, ny) in core_cells or (nx, ny) in core_passage_cells or (nx, ny) in corridor_cells:
                        continue

                    # MANUAL DELETION for the neighbour cell of the A-pair
                    if (nx, ny, level) in manual_deletions:
                        continue

                    # Stage 1 is handled later as a Type 1/Type 2 facade offset.
                    # It does NOT delete modules and it does NOT project outside the footprint.

                    # Stage 2: carefully reintroduce perforation at A-pair level.
                    # This avoids cutting half modules and keeps all facades coherent.
                    if should_skip_pair_for_stage2_perforation(cx, cy, nx, ny, level, NX, NY, c0x, c0y, cw, ch,
                                                              cell_floor_counts, peak_floors, 0,
                                                              core_cells, core_passage_cells, corridor_cells,
                                                              perforation_pct):
                        continue

                    if not can_place_A(cx, cy, nx, ny, level, placed_2d, cell_floor_counts, opening_mask, occupied_3d):
                        continue

                    x0 = min(cx, nx) * GRID
                    y0 = min(cy, ny) * GRID
                    dx_box = GRID * (abs(dx) + 1)
                    dy_box = GRID * (abs(dy) + 1)

                    # Stage 1 facade interlock: keep the module perpendicular to the corridor,
                    # but alternate between Type 1 direct stacking and Type 2 half-cell in-plane
                    # stacking. This is NOT projection/cantilever; it stays inside the rectangle.
                    ox, oy, connection_type = facade_interlock_offset_for_A_pair(
                        cx, cy, nx, ny, level, NX, NY, c0x, c0y, cw, ch,
                        core_cells, core_passage_cells, corridor_cells,
                        peak_floors, x0, y0, dx_box, dy_box, placed_rects
                    )

                    if connection_type == 'SKIP_OVERLAP':
                        continue

                    final_rect = (x0 + ox, y0 + oy, x0 + ox + dx_box, y0 + oy + dy_box)

                    # v14l correction: Type 2 interlock must never slide into a
                    # core, core-passage, or corridor footprint. If Type 2 collides
                    # with a reserved zone, first try Type 1 in the original cells.
                    # If Type 1 is also blocked, delete the pair.
                    if _rect_overlaps_any(final_rect, reserved_rects):
                        if connection_type == 'T2':
                            ox, oy, connection_type = 0.0, 0.0, 'T1_SAFE_FALLBACK'
                            final_rect = (x0, y0, x0 + dx_box, y0 + dy_box)
                        if _rect_overlaps_any(final_rect, reserved_rects):
                            continue

                    # Never allow two A modules on the same floor to physically
                    # overlap after Type 1 / Type 2 facade interlock. If this pair
                    # still collides, leave a clean void instead of producing bad geometry.
                    if _rect_overlaps_any(final_rect, placed_rects):
                        continue

                    # Optional second-stage facade projection.
                    # This is deliberately applied AFTER the existing footprint/corridor/core
                    # safety checks, so all previous massing logic remains untouched.
                    px, py, proj_depth, proj_side, proj_face_type = facade_projection_offset_for_A_pair(
                        cx, cy, nx, ny, level, NX, NY, c0x, c0y, cw, ch,
                        core_cells, corridor_cells, projection_options
                    )

                    # Projection-aware corridor connector:
                    # original_rect = where the module would have been before optional outward projection.
                    # projected_rect = where the module is finally placed.
                    # The connector slab fills the access gap created by projection.
                    original_rect_for_bridge = (x0 + ox, y0 + oy, x0 + ox + dx_box, y0 + oy + dy_box)
                    projected_rect_for_bridge = (x0 + ox + px, y0 + oy + py,
                                                 x0 + ox + px + dx_box, y0 + oy + py + dy_box)
                    if proj_depth > 0.001:
                        bake_projection_corridor_bridge(original_rect_for_bridge,
                                                        projected_rect_for_bridge,
                                                        level,
                                                        proj_depth)

                    brep = make_box(x0 + ox + px, y0 + oy + py, level * FLOOR_H, dx_box, dy_box, FLOOR_H)

                    frac = float(level) / float(max(1, peak_floors - 1))
                    if proj_depth > 0.001:
                        layer = "A_cant"
                    elif frac < 0.33:
                        layer = "A_low"
                    elif frac < 0.66:
                        layer = "A_mid"
                    else:
                        layer = "A_high"
                    bake_brep(brep, layer)
                    placed_rects.append((x0 + ox, y0 + oy, x0 + ox + dx_box, y0 + oy + dy_box))
                    placed_2d.add((cx, cy))
                    placed_2d.add((nx, ny))
                    counts["A"] += 1
                    break

                # IMPORTANT: leftover single cells are deliberately left empty.
                # This preserves the two-cell A module rule and removes B entirely.

    return counts

# ---------------------------------------------------------------------
# DRAWING AIDS
# ---------------------------------------------------------------------
def draw_plan_guides(NX, NY, c0x, c0y, cw, ch, peak_floors, base_floors, corridor_cells=None, core_cells=None):
    W = NX * GRID
    D = NY * GRID

    # Cluster outline
    poly = rg.Polyline([
        rg.Point3d(0, 0, 0),
        rg.Point3d(W, 0, 0),
        rg.Point3d(W, D, 0),
        rg.Point3d(0, D, 0),
        rg.Point3d(0, 0, 0)
    ])
    bake_curve(rg.PolylineCurve(poly), "courtyard")

    # Courtyard outline
    x0 = c0x * GRID
    y0 = c0y * GRID
    x1 = (c0x + cw) * GRID
    y1 = (c0y + ch) * GRID
    cpoly = rg.Polyline([
        rg.Point3d(x0, y0, 0),
        rg.Point3d(x1, y0, 0),
        rg.Point3d(x1, y1, 0),
        rg.Point3d(x0, y1, 0),
        rg.Point3d(x0, y0, 0)
    ])
    bake_curve(rg.PolylineCurve(cpoly), "courtyard")

    # Corridor void guide: one-cell-wide central loop. Baked only as plan curves,
    # not as bulky white corridor geometry. Core cells are omitted from the guide
    # because the core now replaces that corridor-corner segment.
    core_cells = core_cells or set()
    if corridor_cells:
        for (cx, cy) in corridor_cells:
            if (cx, cy) in core_cells:
                continue
            x = cx * GRID
            y = cy * GRID
            pl = rg.Polyline([
                rg.Point3d(x, y, 0.02),
                rg.Point3d(x + GRID, y, 0.02),
                rg.Point3d(x + GRID, y + GRID, 0.02),
                rg.Point3d(x, y + GRID, 0.02),
                rg.Point3d(x, y, 0.02)
            ])
            bake_curve(rg.PolylineCurve(pl), "corridor")

    # Indicative setback/property line: podium/base and peak line.
    # This is only a visual guide, not final code compliance.
    base_setback = 0.4 * base_floors * FLOOR_H
    peak_setback = 0.4 * peak_floors * FLOOR_H
    prop = rg.Polyline([
        rg.Point3d(-base_setback, -base_setback, 0),
        rg.Point3d(W + base_setback, -base_setback, 0),
        rg.Point3d(W + base_setback, D + base_setback, 0),
        rg.Point3d(-base_setback, D + base_setback, 0),
        rg.Point3d(-base_setback, -base_setback, 0)
    ])
    bake_curve(rg.PolylineCurve(prop), "setback")

    peak = rg.Polyline([
        rg.Point3d(peak_setback, peak_setback, peak_floors * FLOOR_H),
        rg.Point3d(W - peak_setback, peak_setback, peak_floors * FLOOR_H),
        rg.Point3d(W - peak_setback, D - peak_setback, peak_floors * FLOOR_H),
        rg.Point3d(peak_setback, D - peak_setback, peak_floors * FLOOR_H),
        rg.Point3d(peak_setback, peak_setback, peak_floors * FLOOR_H)
    ])
    bake_curve(rg.PolylineCurve(peak), "setback")

# ---------------------------------------------------------------------
# MANUAL ELEVATION DELETION
# ---------------------------------------------------------------------
def build_side_elevation(side, NX, NY, c0x, c0y, cw, ch,
                         cell_floor_counts, peak_floors, corridor_cells):
    """
    Build the elevation grid for one side.

    Returns:
      positions : ordered list of along-side coordinates (the visible columns)
      max_floor : tallest column in this elevation
      col_cells : dict { position : { floor : [ (cx,cy), ... ] } }
                  maps a visible (column, floor) cell to the real plan cells
                  it represents across the full depth band of that side.
    """
    d = RING_DEPTH_CELLS
    corr = corridor_bounds_from_cells(corridor_cells)
    if corr is None:
        return [], 0, {}
    corr_west, corr_east, corr_south, corr_north = corr

    if side in ("N", "S"):
        positions = list(range(NX))
        if side == "N":
            depth_range = range(c0y + ch, c0y + ch + d)
        else:
            depth_range = range(c0y - d, c0y)
        def cells_at(pos):
            return [(pos, yy) for yy in depth_range
                    if is_in_cluster(pos, yy, NX, NY)]
    else:  # E or W
        positions = list(range(NY))
        if side == "E":
            depth_range = range(c0x + cw, c0x + cw + d)
        else:
            depth_range = range(c0x - d, c0x)
        def cells_at(pos):
            return [(xx, pos) for xx in depth_range
                    if is_in_cluster(xx, pos, NX, NY)]

    col_cells = {}
    max_floor = 0
    for pos in positions:
        real_cells = cells_at(pos)
        # height at this column = max cascade height across the depth band
        col_h = 0
        for (rx, ry) in real_cells:
            h = int(cell_floor_counts.get((rx, ry), 0))
            if h > col_h:
                col_h = h
        if col_h <= 0:
            continue
        if col_h > max_floor:
            max_floor = col_h
        floors = {}
        for f in range(col_h):
            floors[f] = list(real_cells)
        col_cells[pos] = floors

    return positions, max_floor, col_cells


class ElevationDeleteDialog(forms.Dialog[bool]):
    """
    Interactive elevation editor for ONE side.

    Shows the side as a grid of toggle buttons (columns = positions along the
    side, rows = floors). Filled buttons = modules that exist. The user clicks
    buttons to mark them for deletion (turns red). Clicking again restores.

    Returns True (Apply) or False (Skip this side). The set of deleted real
    plan-cells-per-floor is collected in self.deleted (a set of (cx,cy,floor)).
    """
    def __init__(self, side, positions, max_floor, col_cells):
        super(ElevationDeleteDialog, self).__init__()
        self.side = side
        self.col_cells = col_cells
        self.deleted = set()          # (cx, cy, floor)
        self._btn_state = {}          # (pos, floor) -> bool deleted
        self._buttons = {}            # (pos, floor) -> Eto Button

        side_names = {"N": "NORTH", "S": "SOUTH", "E": "EAST", "W": "WEST"}
        self.Title = "Delete modules - {0} elevation".format(side_names.get(side, side))
        self.Resizable = True

        cols = [p for p in positions if p in col_cells]
        # Build a vertical stack: top floor first (so it reads like an elevation)
        grid = forms.DynamicLayout()
        grid.Padding = drawing.Padding(6)
        grid.Spacing = drawing.Size(1, 1)

        CELL = 18  # button size px

        for f in range(max_floor - 1, -1, -1):
            row_widgets = []
            # floor label
            flbl = make_label("F{0}".format(f), size=7, color=ETO_TXT_SECN)
            try:
                flbl.Width = 24
            except Exception:
                pass
            row_widgets.append(flbl)
            for pos in cols:
                floors = col_cells.get(pos, {})
                if f in floors:
                    b = forms.Button()
                    b.Text = ""
                    try:
                        b.MinimumSize = drawing.Size(CELL, CELL)
                        b.Size = drawing.Size(CELL, CELL)
                        b.BackgroundColor = drawing.Color.FromArgb(200, 140, 60)
                    except Exception:
                        pass
                    self._buttons[(pos, f)] = b
                    self._btn_state[(pos, f)] = False
                    # bind click
                    def make_handler(pp, ff):
                        def handler(sender, e):
                            self._toggle(pp, ff)
                        return handler
                    b.Click += make_handler(pos, f)
                    row_widgets.append(b)
                else:
                    spacer = forms.Panel()
                    try:
                        spacer.Size = drawing.Size(CELL, CELL)
                    except Exception:
                        pass
                    row_widgets.append(spacer)
            grid.AddRow(*row_widgets)

        # bottom axis label row
        axis_widgets = [make_label("", size=7)]
        for pos in cols:
            axis_widgets.append(make_label("", size=6))
        grid.AddRow(*axis_widgets)

        # Scrollable in case the elevation is large
        scroll = forms.Scrollable()
        scroll.Content = grid
        try:
            scroll.Border = getattr(forms.BorderType, "None")
        except Exception:
            pass

        # Instruction + buttons
        instr = make_label(
            "Click modules to mark them for deletion (orange -> red). "
            "Click again to restore. Then Apply, or Skip this side.",
            size=8, color=ETO_TXT_SECN)

        self.apply_btn = forms.Button()
        self.apply_btn.Text = "Apply deletions"
        self.apply_btn.Click += self._on_apply
        self.skip_btn = forms.Button()
        self.skip_btn.Text = "Skip this side"
        self.skip_btn.Click += self._on_skip
        self.clear_btn = forms.Button()
        self.clear_btn.Text = "Clear all"
        self.clear_btn.Click += self._on_clear

        btnrow = forms.DynamicLayout()
        btnrow.Padding = drawing.Padding(6)
        btnrow.Spacing = drawing.Size(8, 0)
        btnrow.AddRow(self.clear_btn, None, self.skip_btn, self.apply_btn)

        root = forms.DynamicLayout()
        root.AddRow(instr)
        root.AddRow(scroll)
        root.AddRow(btnrow)
        self.Content = root

        try:
            self.ClientSize = drawing.Size(
                min(1100, max(400, 40 + len(cols) * (CELL + 1))),
                min(700, max(300, 90 + max_floor * (CELL + 1))))
        except Exception:
            pass

    def _toggle(self, pos, f):
        cur = not self._btn_state.get((pos, f), False)
        self._btn_state[(pos, f)] = cur
        b = self._buttons.get((pos, f))
        if b is not None:
            try:
                b.BackgroundColor = (drawing.Color.FromArgb(210, 50, 50) if cur
                                     else drawing.Color.FromArgb(200, 140, 60))
            except Exception:
                pass

    def _collect(self):
        self.deleted = set()
        for (pos, f), is_del in self._btn_state.items():
            if not is_del:
                continue
            for (cx, cy) in self.col_cells.get(pos, {}).get(f, []):
                self.deleted.add((cx, cy, f))

    def _on_apply(self, sender, e):
        self._collect()
        self.Close(True)

    def _on_skip(self, sender, e):
        self.deleted = set()
        self.Close(False)

    def _on_clear(self, sender, e):
        for key in list(self._btn_state.keys()):
            self._btn_state[key] = False
            b = self._buttons.get(key)
            if b is not None:
                try:
                    b.BackgroundColor = drawing.Color.FromArgb(200, 140, 60)
                except Exception:
                    pass


def run_elevation_editors(hourglass_sides, NX, NY, c0x, c0y, cw, ch,
                          cell_floor_counts, peak_floors, corridor_cells):
    """
    For each user-selected side, show the elevation editor.
    User can delete modules, then Apply (keep deletions) or Skip.
    Returns the combined set of (cx, cy, floor) to delete.
    """
    manual_deletions = set()
    if not hourglass_sides:
        return manual_deletions

    for side in hourglass_sides:
        positions, max_floor, col_cells = build_side_elevation(
            side, NX, NY, c0x, c0y, cw, ch,
            cell_floor_counts, peak_floors, corridor_cells)
        if not col_cells or max_floor <= 0:
            continue
        dlg = ElevationDeleteDialog(side, positions, max_floor, col_cells)
        try:
            ok = dlg.ShowModal(Rhino.UI.RhinoEtoApp.MainWindow)
        except Exception:
            try:
                ok = dlg.ShowModal()
            except Exception:
                ok = False
        if ok:
            manual_deletions.update(dlg.deleted)
    return manual_deletions


# ---------------------------------------------------------------------
# MAIN GENERATION
# ---------------------------------------------------------------------
def generate_cluster(NX, NY, peak_ne_floors, peak_nw_floors, peak_se_floors, peak_sw_floors,
                     courtyard_size, curve_power, perforation_pct,
                     hourglass_sides=None,
                     projection_options=None):
    """v14b: core logic from the flat study + curved cascade restored.

    What is intentionally OFF in this version:
      - no checkerboard/cantilever movement
      - no façade projection

    What is ON:
      - A-only ventilated module orientation
      - automatic courtyard / 5-cell ring grammar
      - closed corridor loop
      - 4 local-height cores from the stable core-study version
      - curved cascade height field
      - core heights calculated from the local floors they connect to
    """
    init_layers()
    base_floors = DEFAULT_BASE
    peak_specs = [("NE", int(peak_ne_floors)), ("NW", int(peak_nw_floors)), ("SE", int(peak_se_floors)), ("SW", int(peak_sw_floors))]
    peak_floors = max([int(base_floors)] + [int(f) for _, f in peak_specs])

    c0x, c0y, cw, ch = courtyard_bounds(NX, NY, courtyard_size)

    # Locked plan grammar: only the 5-cell ring is buildable.
    # Cross-section on all four sides = 2 module cells + 1 corridor void + 2 module cells.
    module_cells, corridor_cells = corridor_and_module_cells(NX, NY, c0x, c0y, cw, ch)

    # Keep the working v14a core logic: four cores, shifted/placed at the corridor corners.
    # Core footprint stays empty; only minimal core-passage cells are added to the corridor.
    core_items = get_core_positions(NX, NY, corridor_cells, "NE")
    core_cells = set()
    core_passage_cells = set()

    for item in core_items:
        for cc in core_cells_for_item(*item):
            if is_in_cluster(cc[0], cc[1], NX, NY):
                core_cells.add(cc)
                # Keep core cells in the active set for peak snapping / local height probing,
                # but they are skipped during residential A-module placement.
                module_cells.add(cc)

        # Minimal through-passage only. No broad lobby deletion.
        core_passage_cells.update(core_passage_cells_for_item(item[0], item[1], item[2], NX, NY, corridor_cells))

    core_passage_cells.difference_update(corridor_cells)
    core_passage_cells.difference_update(core_cells)

    # Treat passage cells as corridor/void on every floor.
    module_cells.difference_update(core_passage_cells)
    corridor_cells.update(core_passage_cells)

    # Corner peak cap: keep the peak as a complete square/cube of A modules,
    # but do not bake over core cells. This gives the top a complete tower reading.
    peak_cap_cells = set()
    cap_specs = []
    for corner, floors in peak_specs:
        if corner is None:
            continue
        corner_txt = str(corner).upper().strip()
        if corner_txt in ("", "NONE", "NO", "OFF"):
            continue
        try:
            floors_i = int(floors)
        except Exception:
            continue
        if floors_i <= 0:
            continue

        cap = set()
        for pc in corner_cap_cells(corner_txt, NX, NY, PEAK_CAP_CELLS):
            if not is_in_cluster(pc[0], pc[1], NX, NY):
                continue
            if is_courtyard(pc[0], pc[1], c0x, c0y, cw, ch):
                continue
            if pc in corridor_cells or pc in core_passage_cells:
                continue
            cap.add(pc)
            peak_cap_cells.add(pc)
            module_cells.add(pc)
        cap_specs.append((cap, floors_i, corner_txt))

    # Store cap/peak data before calculating the curved height field.
    set_peak_cap_data(cap_specs, module_cells)
    setup_peak_data(module_cells, NX, NY, peak_specs)

    # Curved cascade restored: only active module/core cells get height.
    # Courtyard, corridor and passage cells remain empty.
    cell_floor_counts = {}
    reserved_void = set(corridor_cells).union(core_passage_cells)
    for cx in range(NX):
        for cy in range(NY):
            p = (cx, cy)
            if p in reserved_void:
                cell_floor_counts[p] = 0
            elif p in module_cells or p in core_cells:
                cell_floor_counts[p] = curved_floor_count(
                    cx, cy, NX, NY, "NE", peak_floors, base_floors, curve_power
                )
            else:
                cell_floor_counts[p] = 0

    # Force chosen cap areas to their own selected peak height, excluding core/corridor cells.
    for cap, floors_i, corner_txt in cap_specs:
        for cc in cap:
            if cc not in core_cells and cc not in reserved_void:
                cell_floor_counts[cc] = max(cell_floor_counts.get(cc, 0), int(floors_i))

    # Stage 2 perforation is handled at A-pair level inside place_modules.
    # Keep the cell-level opening mask empty so we never cut half of an A module.
    opening_mask, opening_boxes = set(), []

    # MANUAL ELEVATION DELETION — for each user-selected side, show an
    # interactive elevation editor and collect the modules to delete.
    manual_deletions = run_elevation_editors(
        hourglass_sides, NX, NY, c0x, c0y, cw, ch,
        cell_floor_counts, peak_floors, corridor_cells)

    # Skip only actual core and passage/corridor cells during module placement.
    # Stage 1 interlock + Stage 2 perforation are handled as PAIR skips, not projection.
    counts = place_modules(
        NX, NY, c0x, c0y, cw, ch, cell_floor_counts, opening_mask,
        "NE", peak_floors, core_cells, core_passage_cells, corridor_cells,
        perforation_pct,
        peak_ne_floors=peak_ne_floors,
        peak_nw_floors=peak_nw_floors,
        peak_se_floors=peak_se_floors,
        peak_sw_floors=peak_sw_floors,
        base_floors=base_floors,
        hourglass_sides=hourglass_sides if hourglass_sides else [],
        manual_deletions=manual_deletions,
        projection_options=projection_options or {"mode": PROJECTION_MODE_SKIP,
                                                  "short_max": 0.0,
                                                  "long_max": 0.0}
    )
    counts["P1"] = 0
    counts["O1"] = 0
    counts["O2"] = 0

    # Core height follows local module heights around each core.
    core_floor_counts = local_core_floor_counts(core_items, core_cells, cell_floor_counts, NX, NY, base_floors, peak_specs=peak_specs)
    counts["CORE"] = bake_cores(core_items, core_floor_counts)

    # First detailing pass: corridor floors as clean 90 mm slabs on all active floors.
    # This is based on the final height field, so the corridor stops where the cascade ends.
    counts["CORRIDOR_SLAB"] = bake_corridor_slabs(corridor_cells, cell_floor_counts, core_cells, peak_floors)

    counts["O1"] = 0
    counts["O2"] = 0

    draw_plan_guides(NX, NY, c0x, c0y, cw, ch, peak_floors, base_floors, corridor_cells, core_cells)

    txt = (
        "Timber Housing v14t FOUR-CORNER PEAK FIELD + INVERTED BRIDGE-BAND CASCADE\n"
        "A-only modules | four-corner curve | support-aware openings | short-side inverted base cascade | core height = nearest corner peak\n"
        "Grid: %.2f m | NE:%d NW:%d SE:%d SW:%d | Base:%d | Curve: %.2f\n"
        "A=%d | CORE=%d | Core heights follow local connected floors."
        % (GRID, peak_ne_floors, peak_nw_floors, peak_se_floors, peak_sw_floors, base_floors, curve_power, counts.get("A", 0), counts.get("CORE", 0))
    )
    add_text(txt, rg.Point3d(0, -10 * GRID, 0), 1.2)

    sc.doc.Views.Redraw()
    return counts

# ---------------------------------------------------------------------
# ETO DIALOG UI - kept from v12 style, updated for v13 curved openings
# ---------------------------------------------------------------------
def make_label(text, bold=False, size=None, color=None, italic=False, impact=False):
    lbl = forms.Label()
    lbl.Text = text
    if color is not None:
        try:
            lbl.TextColor = color
        except Exception:
            pass

    # Rhino/Eto versions differ: some do NOT expose FontStyle.None.
    # Only pass style when required.
    style = None
    if bold and italic:
        style = drawing.FontStyle.Bold | drawing.FontStyle.Italic
    elif bold:
        style = drawing.FontStyle.Bold
    elif italic:
        style = drawing.FontStyle.Italic

    font_name = "Arial"
    if italic:
        font_name = "Georgia"
    elif impact:
        font_name = "Impact"

    try:
        if style is None:
            lbl.Font = drawing.Font(font_name, size or 10)
        else:
            lbl.Font = drawing.Font(font_name, size or 10, style)
    except Exception:
        try:
            if style is None:
                lbl.Font = drawing.Font("Arial", size or 10)
            else:
                lbl.Font = drawing.Font("Arial", size or 10, style)
        except Exception:
            pass
    return lbl


def add_stack_item(layout, control, expand=False):
    """Rhino/Eto-safe StackLayout insertion.
    Some Rhino 8 Eto builds require StackLayoutItem instead of direct Controls.
    """
    try:
        item = forms.StackLayoutItem()
        item.Control = control
        item.Expand = expand
        layout.Items.Add(item)
    except Exception:
        try:
            layout.Items.Add(forms.StackLayoutItem(control, expand))
        except Exception:
            layout.Items.Add(control)


class WoSyHoV13Dialog(forms.Dialog[bool]):
    def __init__(self):
        forms.Dialog[bool].__init__(self)

        self.Title = "Timber Housing v17 - Four-corner peak control"
        self.Padding = drawing.Padding(0)
        try:
            self.BackgroundColor = ETO_BG_WARM
        except Exception:
            pass
        self.MinimumSize = drawing.Size(860, 480)
        try:
            self.ClientSize = drawing.Size(960, 560)
        except Exception:
            pass
        self.Resizable = True

        # ── Title panel ──────────────────────────────────────────────────
        title_label = make_label("Timber Housing v17", bold=True, size=16,
                                 color=ETO_TXT_PRIM, impact=True)
        subtitle_label = make_label(
            "A-only cascade + 4 cores + user-selected hourglass sides",
            italic=True, size=9, color=ETO_TXT_SECN)
        title_panel = forms.Panel()
        try:
            title_panel.BackgroundColor = ETO_BG_PANEL
        except Exception:
            pass
        title_panel.Padding = drawing.Padding(14, 8, 14, 8)
        ts = forms.StackLayout()
        ts.Orientation = forms.Orientation.Vertical
        ts.HorizontalContentAlignment = forms.HorizontalAlignment.Left
        ts.Spacing = 2
        add_stack_item(ts, title_label)
        add_stack_item(ts, subtitle_label)
        title_panel.Content = ts

        accent_top = forms.Panel()
        try:
            accent_top.BackgroundColor = ETO_ACCENT
        except Exception:
            pass
        accent_top.Size = drawing.Size(960, 3)

        # ── Helper: make a labelled slider row ────────────────────────────
        # Returns (slider, value_label)
        def make_slider_row(mn, mx, val, decimals=0):
            sl = forms.Slider()
            sl.MinValue = int(mn)
            sl.MaxValue = int(mx)
            sl.Value    = int(val)
            sl.Width    = 200
            vl = make_label(str(int(val)), size=9, color=ETO_TXT_SECN)
            vl.Width = 24
            return sl, vl

        # ── FORM sliders ──────────────────────────────────────────────────
        self.length_sl, self.length_vl = make_slider_row(8, 60, DEFAULT_NX)
        self.depth_sl,  self.depth_vl  = make_slider_row(8, 40, DEFAULT_NY)

        # ── PEAK sliders (2-20) ───────────────────────────────────────────
        self.ne_sl, self.ne_vl = make_slider_row(2, 20, DEFAULT_PEAK_NE)
        self.nw_sl, self.nw_vl = make_slider_row(2, 20, DEFAULT_PEAK_NW)
        self.se_sl, self.se_vl = make_slider_row(2, 20, DEFAULT_PEAK_SE)
        self.sw_sl, self.sw_vl = make_slider_row(2, 20, DEFAULT_PEAK_SW)

        # Curve power × 10 so Slider (integer) can express 1.0–5.0 in 0.1 steps
        self.curve_sl, self.curve_vl = make_slider_row(10, 50, int(DEFAULT_CURVE_POWER * 10))
        self.curve_vl.Text = "{:.1f}".format(DEFAULT_CURVE_POWER)

        # Perforation 0-50
        self.perf_sl, self.perf_vl = make_slider_row(0, 50, DEFAULT_PERFORATION_PCT)

        # Base is locked
        self.base_floors_fixed = DEFAULT_BASE

        # Courtyard dropdown (kept for compatibility)
        self.courtyard_dd = self._make_dropdown(["Auto from module rows/columns"], 0)

        # ── INVERTED CASCADE checkboxes (4 sides) ─────────────────────────
        def make_cb(text):
            cb = forms.CheckBox()
            cb.Text = text
            cb.Checked = False
            try:
                cb.TextColor = ETO_TXT_SECN
            except Exception:
                pass
            cb.CheckedChanged += self.on_change
            return cb

        self.cb_north = make_cb("North  (top side)")
        self.cb_south = make_cb("South  (bottom side)")
        self.cb_east  = make_cb("East   (right side)")
        self.cb_west  = make_cb("West   (left side)")

        # ── Elevation preview: ImageView updated on every change ──────────
        # Uses drawing.Bitmap drawn with Eto Graphics — no Drawable, no Paint events
        self._img_view = forms.ImageView()
        self._img_view.Width  = 620
        self._img_view.Height = 420
        try:
            self._img_view.BackgroundColor = drawing.Color.FromArgb(30, 30, 30)
        except Exception:
            pass

        # ── Status / preview label ────────────────────────────────────────
        self.status_label = make_label("", italic=True, size=8, color=ETO_TXT_SECN)
        try:
            self.status_label.Width = 500
        except Exception:
            pass

        # ── Wire slider change events ──────────────────────────────────────
        all_sliders = [self.length_sl, self.depth_sl,
                       self.ne_sl, self.nw_sl, self.se_sl, self.sw_sl,
                       self.curve_sl, self.perf_sl]
        for sl in all_sliders:
            sl.ValueChanged += self.on_change
        self.courtyard_dd.SelectedIndexChanged += self.on_change

        # ── Buttons ───────────────────────────────────────────────────────
        self.confirm_btn = forms.Button()
        self.confirm_btn.Text = "GENERATE"
        self.confirm_btn.Size = drawing.Size(130, 34)
        try:
            self.confirm_btn.BackgroundColor = ETO_CONFIRM
            self.confirm_btn.TextColor = ETO_WHITE
            self.confirm_btn.Font = drawing.Font("Impact", 12, drawing.FontStyle.Bold)
        except Exception:
            pass
        self.confirm_btn.Click += self.on_confirm

        self.abort_btn = forms.Button()
        self.abort_btn.Text = "Cancel"
        self.abort_btn.Size = drawing.Size(90, 34)
        try:
            self.abort_btn.BackgroundColor = ETO_ABORT
            self.abort_btn.TextColor = ETO_WHITE
            self.abort_btn.Font = drawing.Font("Georgia", 10, drawing.FontStyle.Italic)
        except Exception:
            pass
        self.abort_btn.Click += self.on_abort

        # ── LANDSCAPE LAYOUT: left column = controls, right = preview ────

        # ---- LEFT COLUMN: StackLayout vertical, each row is a horizontal StackLayout
        # This is the ONLY Eto layout that actually respects fixed child widths.
        LBL_W = 100   # label column width px
        SL_W  = 190   # slider width px
        VL_W  = 28    # value label width px

        def _lbl(txt):
            lb = make_label(txt, size=8)
            try: lb.Width = LBL_W
            except Exception: pass
            return lb

        def _hrow(*widgets):
            """One horizontal StackLayout row."""
            row = forms.StackLayout()
            row.Orientation = forms.Orientation.Horizontal
            row.Spacing = 4
            row.VerticalContentAlignment = forms.VerticalAlignment.Center
            for w in widgets:
                item = forms.StackLayoutItem(w)
                row.Items.Add(item)
            return row

        def sl_row(lbl_text, sl, vl):
            return _hrow(_lbl(lbl_text), sl, vl)

        def _sect(txt):
            return make_label(txt, bold=True, size=9,
                              color=ETO_TXT_PRIM, impact=True)

        # Build the left column as a vertical StackLayout
        left = forms.StackLayout()
        left.Orientation = forms.Orientation.Vertical
        left.Spacing = 3
        left.Padding = drawing.Padding(8, 6, 4, 6)

        def add(w):
            left.Items.Add(forms.StackLayoutItem(w))

        add(_sect("FORM"))
        add(sl_row("Length (X):", self.length_sl, self.length_vl))
        add(sl_row("Depth  (Y):", self.depth_sl,  self.depth_vl))
        add(_hrow(make_label("")))   # spacer

        add(_sect("CURVED CASCADE"))
        add(sl_row("NE floors:", self.ne_sl, self.ne_vl))
        add(sl_row("NW floors:", self.nw_sl, self.nw_vl))
        add(sl_row("SE floors:", self.se_sl, self.se_vl))
        add(sl_row("SW floors:", self.sw_sl, self.sw_vl))
        add(_hrow(_lbl("Base:"),
                  make_label("2 locked", size=8, color=ETO_TXT_SECN)))
        add(sl_row("Curve power:", self.curve_sl, self.curve_vl))
        add(_hrow(make_label("")))

        add(_sect("COURTYARD + PERFORATION"))
        add(_hrow(_lbl("Courtyard:"), self.courtyard_dd))
        add(sl_row("Perforation %:", self.perf_sl, self.perf_vl))
        add(_hrow(make_label("")))

        add(_sect("INVERTED CASCADE"))
        add(make_label("Tick sides cascade can't reach base:",
                       size=8, color=ETO_TXT_SECN))
        add(_hrow(self.cb_north, self.cb_south))
        add(_hrow(self.cb_east,  self.cb_west))
        add(_hrow(make_label("")))
        add(self.status_label)

        # ---- RIGHT COLUMN: preview ----------------------------------------
        right = forms.StackLayout()
        right.Orientation = forms.Orientation.Vertical
        right.Spacing = 4
        right.Padding = drawing.Padding(6, 6, 10, 6)

        def radd(w):
            right.Items.Add(forms.StackLayoutItem(w))

        radd(make_label("LIVE PREVIEW — 4 ELEVATIONS",
                        bold=True, size=9,
                        color=ETO_TXT_HILT, impact=True))
        radd(make_label(
            u"N / S / W / E update with sliders.  [HG] = hourglass ticked.",
            size=7, color=ETO_TXT_SECN))
        radd(self._img_view)

        # ---- MAIN BODY: left | right --------------------------------------
        body = forms.StackLayout()
        body.Orientation = forms.Orientation.Horizontal
        body.Spacing = 0
        body.Padding = drawing.Padding(0)

        # Wrap left in a fixed-width panel
        left_panel = forms.Panel()
        left_panel.Content = left
        try:
            left_panel.Width = 360
        except Exception:
            pass

        left_item = forms.StackLayoutItem(left_panel)
        right_item = forms.StackLayoutItem(right, True)   # True = expand to fill
        body.Items.Add(left_item)
        body.Items.Add(right_item)

        # Buttons
        btn_layout = forms.DynamicLayout()
        btn_layout.Padding = drawing.Padding(14, 4, 14, 10)
        btn_layout.Spacing = drawing.Size(10, 0)
        btn_layout.AddRow(None, self.abort_btn, self.confirm_btn)

        accent_bot = forms.Panel()
        try:
            accent_bot.BackgroundColor = ETO_ACCENT
        except Exception:
            pass
        accent_bot.Size = drawing.Size(900, 3)

        root = forms.StackLayout()
        root.Orientation = forms.Orientation.Vertical
        root.HorizontalContentAlignment = forms.HorizontalAlignment.Stretch
        root.Spacing = 0
        add_stack_item(root, title_panel)
        add_stack_item(root, accent_top)
        add_stack_item(root, body, expand=True)
        add_stack_item(root, accent_bot)
        add_stack_item(root, btn_layout)

        self.Content = root
        try:
            self.ClientSize = drawing.Size(960, 560)
        except Exception:
            pass
        self.refresh_status()

    def _make_dropdown(self, items, default_idx):
        dd = forms.DropDown()
        for item in items:
            dd.Items.Add(item)
        dd.SelectedIndex = default_idx
        dd.Width = 150
        try:
            dd.BackgroundColor = ETO_BG_INPUT
        except Exception:
            pass
        return dd

    def get_courtyard(self):
        return "auto"

    def get_values(self):
        ne = int(self.ne_sl.Value)
        nw = int(self.nw_sl.Value)
        se = int(self.se_sl.Value)
        sw = int(self.sw_sl.Value)
        base = DEFAULT_BASE
        peak_max = max(ne, nw, se, sw, base)
        curve = float(self.curve_sl.Value) / 10.0
        hourglass_sides = []
        if self.cb_north.Checked: hourglass_sides.append("N")
        if self.cb_south.Checked: hourglass_sides.append("S")
        if self.cb_east.Checked:  hourglass_sides.append("E")
        if self.cb_west.Checked:  hourglass_sides.append("W")
        return {
            "NX": int(self.length_sl.Value),
            "NY": int(self.depth_sl.Value),
            "peak_ne_floors": ne,
            "peak_nw_floors": nw,
            "peak_se_floors": se,
            "peak_sw_floors": sw,
            "peak_floors": peak_max,
            "base_floors": base,
            "courtyard_size": self.get_courtyard(),
            "curve_power": curve,
            "perforation_pct": int(self.perf_sl.Value),
            "hourglass_sides": hourglass_sides,
        }

    def on_change(self, sender, e):
        # Update value labels for every slider
        try:
            self.length_vl.Text = str(int(self.length_sl.Value))
            self.depth_vl.Text  = str(int(self.depth_sl.Value))
            self.ne_vl.Text = str(int(self.ne_sl.Value))
            self.nw_vl.Text = str(int(self.nw_sl.Value))
            self.se_vl.Text = str(int(self.se_sl.Value))
            self.sw_vl.Text = str(int(self.sw_sl.Value))
            self.curve_vl.Text = "{:.1f}".format(float(self.curve_sl.Value) / 10.0)
            self.perf_vl.Text  = str(int(self.perf_sl.Value))
        except Exception:
            pass
        self.refresh_status()

    def _side_bar(self, side, NX, NY, ne, nw, se, sw, base, curve, hg_sides):
        """
        Return a short ASCII elevation bar string for one side.
        Max ~30 chars wide. Zero Rhino/Eto drawing calls.
        """
        base_i  = int(base)
        SLOPE_R  = 0.55
        PWR_BOOST = 1.85
        pwr = max(1.0, float(curve) + PWR_BOOST)

        if side == "N":
            pl, pr, cols = int(nw), int(ne), NX
        elif side == "S":
            pl, pr, cols = int(sw), int(se), NX
        elif side == "W":
            pl, pr, cols = int(sw), int(nw), NY
        else:
            pl, pr, cols = int(se), int(ne), NY

        peak_max = max(pl, pr, base_i, 1)
        bar_w    = min(28, cols)

        chars = []
        for i in range(bar_w):
            t = float(i) / max(1, bar_w - 1)
            pos = t * (cols - 1)
            tl = min(1.0, (pos / max(1, cols - 1)) / SLOPE_R)
            tr = min(1.0, ((cols - 1 - pos) / max(1, cols - 1)) / SLOPE_R)
            hl = base_i + int((pl - base_i) * max(0.0, 1.0 - tl) ** pwr) if pl > base_i else base_i
            hr = base_i + int((pr - base_i) * max(0.0, 1.0 - tr) ** pwr) if pr > base_i else base_i
            h  = max(base_i, max(hl, hr))

            if side in hg_sides:
                bridge = 2
                half   = max(1, bar_w // 2)
                dist   = min(i, bar_w - 1 - i)
                cf     = min(1.0, dist / float(half))
                cut    = int(round((base_i + bridge + 1) * cf))
                top    = cut + bridge
                h      = max(0, min(top, h) - cut)

            frac = float(h) / float(peak_max)
            if h <= 0:
                chars.append(u"_")
            elif frac < 0.25:
                chars.append(u"\u2581")
            elif frac < 0.45:
                chars.append(u"\u2583")
            elif frac < 0.65:
                chars.append(u"\u2585")
            elif frac < 0.85:
                chars.append(u"\u2587")
            else:
                chars.append(u"\u2588")

        needs_hg = self._side_needs_hourglass(side, NX, NY, ne, nw, se, sw, base)
        hg_tick  = u" [ticked]" if side in hg_sides else (u" \u26a0 suggest" if needs_hg else u"")
        return u"{0}: {1}{2}".format(side, u"".join(chars), hg_tick)

    def _side_needs_hourglass(self, side, NX, NY, ne, nw, se, sw, base):
        """True when the two corner cascades can't reach base in the middle."""
        base_i = int(base)
        SLOPE  = 2.5
        if side == "N":
            pl, pr, length = int(nw), int(ne), NX
        elif side == "S":
            pl, pr, length = int(sw), int(se), NX
        elif side == "W":
            pl, pr, length = int(sw), int(nw), NY
        else:
            pl, pr, length = int(se), int(ne), NY
        left_reach  = max(0, pl - base_i) * SLOPE
        right_reach = max(0, pr - base_i) * SLOPE
        return length < (left_reach + right_reach)

    def _update_elevation_preview(self, v):
        """
        Draw 4 proportional elevation silhouettes with clear labels.
        Labels use filled coloured backgrounds so they're visible in Rhino Eto.
        """
        try:
            W, H = 620, 420
            bmp = drawing.Bitmap(W, H, drawing.PixelFormat.Format32bppRgba)
            g   = drawing.Graphics(bmp)

            NX, NY = v["NX"], v["NY"]
            ne, nw = v["peak_ne_floors"], v["peak_nw_floors"]
            se, sw = v["peak_se_floors"], v["peak_sw_floors"]
            base   = v["base_floors"]
            curve  = v["curve_power"]
            hg     = v["hourglass_sides"]
            GRID_M = 3.75

            peak_max = max(ne, nw, se, sw, base, 1)

            # Background
            g.FillRectangle(
                drawing.SolidBrush(drawing.Color.FromArgb(22, 22, 22)),
                drawing.RectangleF(0.0, 0.0, float(W), float(H)))

            PAD     = 6
            total_w = W - 3 * PAD
            total_h = H - 3 * PAD

            # Panel widths proportional to NX vs NY
            ratio = float(NX) / float(NX + NY)
            w_ns  = max(100, int(total_w * ratio))
            w_ew  = max(80,  total_w - w_ns)
            h_top = total_h // 2
            h_bot = total_h - h_top

            x_ns  = PAD
            x_ew  = PAD + w_ns + PAD
            y_top = PAD
            y_bot = PAD + h_top + PAD

            # (side, ox, oy, vpw, vph, side_name, axis_txt, left_corner, right_corner)
            panels = [
                ("N", x_ns, y_top, w_ns, h_top,
                 "NORTH",  "X axis: {0} cells = {1:.0f}m".format(NX, NX*GRID_M),
                 "NW={0}fl".format(nw), "NE={0}fl".format(ne)),
                ("S", x_ns, y_bot, w_ns, h_bot,
                 "SOUTH",  "X axis: {0} cells = {1:.0f}m".format(NX, NX*GRID_M),
                 "SW={0}fl".format(sw), "SE={0}fl".format(se)),
                ("E", x_ew, y_top, w_ew, h_top,
                 "EAST",   "Y axis: {0} cells = {1:.0f}m".format(NY, NY*GRID_M),
                 "SE={0}fl".format(se), "NE={0}fl".format(ne)),
                ("W", x_ew, y_bot, w_ew, h_bot,
                 "WEST",   "Y axis: {0} cells = {1:.0f}m".format(NY, NY*GRID_M),
                 "SW={0}fl".format(sw), "NW={0}fl".format(nw)),
            ]

            # Colour palette
            C_FRAME    = drawing.Color.FromArgb(38, 38, 38)
            C_BASE_LN  = drawing.Color.FromArgb(60, 160, 210)
            C_TICK     = drawing.Color.FromArgb(80,  80,  80)
            C_BAR_NORM_LO = drawing.Color.FromArgb(180, 80, 10)
            C_BAR_NORM_HI = drawing.Color.FromArgb(255, 160, 20)
            C_BAR_HG_LO   = drawing.Color.FromArgb(40, 100, 190)
            C_BAR_HG_HI   = drawing.Color.FromArgb(100, 180, 255)

            # Side-label header colours
            SIDE_COLORS = {
                "N": drawing.Color.FromArgb(180, 40, 40),
                "S": drawing.Color.FromArgb(40, 140, 60),
                "E": drawing.Color.FromArgb(40, 80, 180),
                "W": drawing.Color.FromArgb(140, 80, 20),
            }

            HEADER_H  = 28   # tall enough to be very visible
            FOOTER_H  = 18
            SCALE_W   = 28

            # Try to get a font that definitely works in Rhino Eto
            try:
                font_hdr  = drawing.SystemFonts.Bold(10)
            except Exception:
                try:
                    font_hdr = drawing.Font(drawing.SystemFont.Bold, 10.0)
                except Exception:
                    font_hdr = drawing.Font("Arial", 9)
            try:
                font_sm = drawing.SystemFonts.Default(7)
            except Exception:
                try:
                    font_sm = drawing.Font(drawing.SystemFont.Default, 7.0)
                except Exception:
                    font_sm = drawing.Font("Arial", 7)

            for side, ox, oy, vpw, vph, side_name, axis_txt, lcorner, rcorner in panels:
                # Panel background
                g.FillRectangle(drawing.SolidBrush(C_FRAME),
                                drawing.RectangleF(float(ox), float(oy),
                                                   float(vpw), float(vph)))

                # ── HEADER: big coloured bar — colour alone identifies the side ──
                hg_active = side in hg
                hdr_col = (drawing.Color.FromArgb(30, 100, 180)
                           if hg_active else SIDE_COLORS[side])
                # Draw header rectangle
                g.FillRectangle(drawing.SolidBrush(hdr_col),
                                drawing.RectangleF(float(ox), float(oy),
                                                   float(vpw), float(HEADER_H)))

                # Direction indicator: draw a small solid square with first letter
                # as a thick coloured block — guaranteed visible
                letter_size = HEADER_H - 4
                g.FillRectangle(
                    drawing.SolidBrush(drawing.Color.FromArgb(255, 255, 255)),
                    drawing.RectangleF(float(ox + 2), float(oy + 2),
                                       float(letter_size), float(letter_size)))
                # Black letter on white square
                try:
                    g.DrawText(side,
                               font_hdr,
                               drawing.SolidBrush(drawing.Color.FromArgb(0, 0, 0)),
                               drawing.PointF(float(ox + 4), float(oy + 3)))
                except Exception:
                    pass

                # Full name after the white box
                hg_sfx = " [HOURGLASS]" if hg_active else (
                    " ?" if self._side_needs_hourglass(
                        side, NX, NY, ne, nw, se, sw, base) else "")
                try:
                    g.DrawText(side_name + hg_sfx,
                               font_hdr,
                               drawing.SolidBrush(drawing.Color.FromArgb(255, 255, 255)),
                               drawing.PointF(float(ox + letter_size + 6),
                                              float(oy + 4)))
                except Exception:
                    pass

                # ── FOOTER: dark bar with axis dimension ─────────────────
                fy = float(oy + vph - FOOTER_H)
                g.FillRectangle(
                    drawing.SolidBrush(drawing.Color.FromArgb(45, 45, 45)),
                    drawing.RectangleF(float(ox), fy,
                                       float(vpw), float(FOOTER_H)))
                try:
                    g.DrawText(axis_txt,
                               font_sm,
                               drawing.SolidBrush(drawing.Color.FromArgb(220, 220, 220)),
                               drawing.PointF(float(ox + SCALE_W + 2), fy + 3.0))
                except Exception:
                    pass

                # ── CORNER PEAK LABELS ───────────────────────────────────
                # Small yellow pills at left and right ends just above footer
                pill_y = fy - 14.0
                # left corner
                g.FillRectangle(
                    drawing.SolidBrush(drawing.Color.FromArgb(100, 80, 0)),
                    drawing.RectangleF(float(ox + SCALE_W), pill_y, 38.0, 12.0))
                try:
                    g.DrawText(lcorner, font_sm,
                               drawing.SolidBrush(drawing.Color.FromArgb(255, 230, 80)),
                               drawing.PointF(float(ox + SCALE_W + 1), pill_y + 1.0))
                except Exception:
                    pass
                # right corner
                g.FillRectangle(
                    drawing.SolidBrush(drawing.Color.FromArgb(100, 80, 0)),
                    drawing.RectangleF(float(ox + vpw - 40), pill_y, 38.0, 12.0))
                try:
                    g.DrawText(rcorner, font_sm,
                               drawing.SolidBrush(drawing.Color.FromArgb(255, 230, 80)),
                               drawing.PointF(float(ox + vpw - 39), pill_y + 1.0))
                except Exception:
                    pass

                # ── BAR DRAWING AREA ──────────────────────────────────────
                bar_x0    = float(ox + SCALE_W)
                bar_y0    = float(oy + HEADER_H + 1)
                bar_w_tot = float(vpw - SCALE_W)
                bar_h_tot = float(vph - HEADER_H - FOOTER_H - 14)
                if bar_h_tot < 4 or bar_w_tot < 4:
                    continue

                profile = self._fast_elevation_profile(
                    side, NX, NY, ne, nw, se, sw, base, curve, hg)
                cols = len(profile)
                if cols == 0:
                    continue

                bw = bar_w_tot / float(cols)

                for i, (h, is_cut) in enumerate(profile):
                    if h <= 0:
                        continue
                    bx = bar_x0 + i * bw
                    bh = max(1.0, float(h) / float(peak_max) * bar_h_tot)
                    by = bar_y0 + bar_h_tot - bh
                    frac = float(h) / float(peak_max)

                    if is_cut:
                        r = int(C_BAR_HG_LO.R  + (C_BAR_HG_HI.R  - C_BAR_HG_LO.R)  * frac)
                        gg= int(C_BAR_HG_LO.G  + (C_BAR_HG_HI.G  - C_BAR_HG_LO.G)  * frac)
                        b = int(C_BAR_HG_LO.B  + (C_BAR_HG_HI.B  - C_BAR_HG_LO.B)  * frac)
                    else:
                        r = int(C_BAR_NORM_LO.R + (C_BAR_NORM_HI.R - C_BAR_NORM_LO.R) * frac)
                        gg= int(C_BAR_NORM_LO.G + (C_BAR_NORM_HI.G - C_BAR_NORM_LO.G) * frac)
                        b = int(C_BAR_NORM_LO.B + (C_BAR_NORM_HI.B - C_BAR_NORM_LO.B) * frac)

                    g.FillRectangle(
                        drawing.SolidBrush(drawing.Color.FromArgb(
                            max(0,min(255,r)), max(0,min(255,gg)), max(0,min(255,b)))),
                        drawing.RectangleF(bx, by, max(0.5, bw - 0.5), bh))

                # Base floor line
                base_y = bar_y0 + bar_h_tot - (float(base) / float(peak_max) * bar_h_tot)
                g.DrawLine(drawing.Pen(C_BASE_LN, 1.5),
                           drawing.PointF(bar_x0, base_y),
                           drawing.PointF(bar_x0 + bar_w_tot, base_y))

                # ── FLOOR SCALE strip (left) ──────────────────────────────
                tick_step = max(1, peak_max // 5)
                for fl in range(0, peak_max + 1, tick_step):
                    ty = bar_y0 + bar_h_tot - (float(fl) / float(peak_max) * bar_h_tot)
                    g.DrawLine(drawing.Pen(C_TICK, 1.0),
                               drawing.PointF(float(ox), ty),
                               drawing.PointF(float(ox + SCALE_W - 1), ty))
                    try:
                        g.DrawText(str(fl),
                                   font_sm,
                                   drawing.SolidBrush(drawing.Color.FromArgb(120,120,120)),
                                   drawing.PointF(float(ox + 1), ty - 6.0))
                    except Exception:
                        pass

                # Panel border
                g.DrawRectangle(
                    drawing.Pen(drawing.Color.FromArgb(80, 80, 80), 1.0),
                    drawing.RectangleF(float(ox), float(oy),
                                       float(vpw), float(vph)))

            # Centre dividers
            mid_x = float(PAD + w_ns + PAD // 2)
            mid_y = float(PAD + h_top + PAD // 2)
            g.DrawLine(drawing.Pen(drawing.Color.FromArgb(60, 60, 60), 2.0),
                       drawing.PointF(mid_x, float(PAD)),
                       drawing.PointF(mid_x, float(H - PAD)))
            g.DrawLine(drawing.Pen(drawing.Color.FromArgb(60, 60, 60), 2.0),
                       drawing.PointF(float(PAD), mid_y),
                       drawing.PointF(float(W - PAD), mid_y))

            g.Dispose()
            self._img_view.Image = bmp

        except Exception:
            pass  # never crash


    def _fast_elevation_profile(self, side, NX, NY, ne, nw, se, sw,
                                 base, curve, hg_sides):
        """Returns list of (height, is_cut) per column — pure arithmetic."""
        base_i   = int(base)
        SLOPE_R  = 0.55
        PWR_BOOST = 1.85
        pwr = max(1.0, float(curve) + PWR_BOOST)

        if side == "N":
            pl, pr, cols = int(nw), int(ne), NX
        elif side == "S":
            pl, pr, cols = int(sw), int(se), NX
        elif side == "W":
            pl, pr, cols = int(sw), int(nw), NY
        else:
            pl, pr, cols = int(se), int(ne), NY

        result = []
        for i in range(cols):
            pos = float(i) / max(1, cols - 1)
            tl  = min(1.0, pos / SLOPE_R)
            tr  = min(1.0, (1.0 - pos) / SLOPE_R)
            hl  = base_i + int((pl - base_i) * max(0.0, 1.0 - tl) ** pwr) if pl > base_i else base_i
            hr  = base_i + int((pr - base_i) * max(0.0, 1.0 - tr) ** pwr) if pr > base_i else base_i
            h   = max(base_i, max(hl, hr))

            is_cut = False
            if side in hg_sides:
                bridge = 2
                half   = max(1, cols // 2)
                dist   = min(i, cols - 1 - i)
                cf     = min(1.0, dist / float(half))
                cut    = int(round((base_i + bridge + 1) * cf))
                top    = cut + bridge
                lo, hi = cut, min(top, h)
                h      = max(0, hi - lo)
                is_cut = True

            result.append((h, is_cut))
        return result





        """
        Build a 1-line ASCII elevation sketch for one side.
        Returns a string like  'N:  ████░░░░████  (L-shape, 24 cells)'
        Also returns a flag: needs_hourglass = True if cascade cannot reach base.
        """
        base_i = int(base)
        if side == "N":
            pl, pr = int(nw), int(ne)
            length = NX
        elif side == "S":
            pl, pr = int(sw), int(se)
            length = NX
        elif side == "E":
            pl, pr = int(se), int(ne)
            length = NY
        else:  # W
            pl, pr = int(sw), int(nw)
            length = NY

        left_reach  = max(0, pl - base_i) * slope
        right_reach = max(0, pr - base_i) * slope
        combined    = left_reach + right_reach
        needs_hg    = (length < combined)

        # Draw a simple bar representing cascade height across the side
        bar_w = min(20, length)
        chars = []
        for i in range(bar_w):
            t = float(i) / max(1, bar_w - 1)
            pos = t * (length - 1)
            # Cascade from left corner
            left_h  = max(base_i, pl  - int(pos / slope))
            # Cascade from right corner
            right_h = max(base_i, pr  - int((length - 1 - pos) / slope))
            h = max(left_h, right_h)
            if h <= base_i + 1:
                chars.append(u"\u2591")   # light block (base level)
            elif h <= base_i + 4:
                chars.append(u"\u2593")   # dark block (mid)
            else:
                chars.append(u"\u2588")   # full block (peak)

        bar = u"".join(chars)
        note = u" \u26a0 needs hourglass" if needs_hg else u" \u2713 cascade reaches base"
        return u"{0}: {1}{2}".format(side, bar, note)

    def refresh_status(self):
        try:
            v = self.get_values()
            NX, NY = v["NX"], v["NY"]
            ne, nw = v["peak_ne_floors"], v["peak_nw_floors"]
            se, sw = v["peak_se_floors"], v["peak_sw_floors"]
            base   = v["base_floors"]
            curve  = v["curve_power"]
            perf   = v["perforation_pct"]
            peak   = v["peak_floors"]
            peak_H = peak * FLOOR_H
            hochhaus = "YES" if peak_H > 22 else "no"
            cluster_W = NX * GRID
            cluster_D = NY * GRID

            c0x, c0y, cw, ch = courtyard_bounds(NX, NY, v["courtyard_size"])
            courtyard_W = cw * GRID
            courtyard_D = ch * GRID
            est_voids = int((NX * NY - cw * ch) * peak * (perf / 100.0) * 0.5)

            # Update elevation preview bitmap
            try:
                self._update_elevation_preview(v)
            except Exception:
                pass

            hourglass_sides = v["hourglass_sides"]
            hg_str = (", ".join(hourglass_sides)) if hourglass_sides else "none"

            self.status_label.Text = (
                u"Footprint: {nx}x{ny} cells ({clw:.0f}x{cld:.0f} m)  |  Hochhaus: {hh}\n"
                u"NE/NW/SE/SW: {ne}/{nw}/{se}/{sw} fl  |  Curve: {cv:.1f}\n"
                u"Courtyard: {ctw:.0f}x{ctd:.0f} m  |  Perf: {pf}%  Est. voids: ~{ev}\n"
                u"Hourglass sides: {hg}"
            ).format(
                nx=NX, ny=NY, clw=cluster_W, cld=cluster_D, hh=hochhaus,
                ne=ne, nw=nw, se=se, sw=sw, cv=curve,
                ctw=courtyard_W, ctd=courtyard_D, pf=perf, ev=est_voids,
                hg=hg_str
            )
        except Exception as ex:
            self.status_label.Text = "Status: " + str(ex)

    def on_confirm(self, sender, e):
        self.Close(True)

    def on_abort(self, sender, e):
        self.Close(False)



# ---------------------------------------------------------------------
# OPTIONAL FACADE PROJECTION DIALOG
# ---------------------------------------------------------------------
class WoSyHoProjectionDialog(forms.Dialog[bool]):
    """Second optional dialog for facade projection only.

    This does not affect cascade, perforation, cores, corridor, or manual
    deletion logic. Default mode is Skip.
    """
    def __init__(self):
        forms.Dialog[bool].__init__(self)
        self.Title = "Timber Housing optional facade projection"
        self.Padding = drawing.Padding(12)
        self.Resizable = False
        try:
            self.ClientSize = drawing.Size(460, 280)
        except Exception:
            pass

        title = make_label("Optional facade projection", bold=True, size=13,
                           color=ETO_TXT_PRIM, impact=True)
        info = make_label(
            "Applies only to the outermost exposed facade row.\n"
            "Corner modules stay fixed on all floors. You can skip this step.",
            size=8, color=ETO_TXT_SECN)

        self.mode_dd = forms.DropDown()
        self.mode_dd.Items.Add("Skip projection")
        self.mode_dd.Items.Add("Option 1 - Parametric varied projection")
        self.mode_dd.Items.Add("Option 2 - Checkerboard full projection")
        self.mode_dd.SelectedIndex = 0
        self.mode_dd.Width = 260

        def make_slider(max_cm, value_cm):
            sl = forms.Slider()
            sl.MinValue = 0
            sl.MaxValue = int(max_cm)
            sl.Value = int(value_cm)
            sl.Width = 240
            vl = make_label("{0:.2f} m".format(float(value_cm) / 100.0), size=8, color=ETO_TXT_SECN)
            try:
                vl.Width = 60
            except Exception:
                pass
            return sl, vl

        self.short_sl, self.short_vl = make_slider(200, 200)
        self.long_sl,  self.long_vl  = make_slider(100, 100)
        self.short_sl.ValueChanged += self.on_change
        self.long_sl.ValueChanged += self.on_change
        self.mode_dd.SelectedIndexChanged += self.on_change

        def row(label, *items):
            r = forms.StackLayout()
            r.Orientation = forms.Orientation.Horizontal
            r.Spacing = 8
            r.VerticalContentAlignment = forms.VerticalAlignment.Center
            lb = make_label(label, size=8)
            try: lb.Width = 130
            except Exception: pass
            r.Items.Add(forms.StackLayoutItem(lb))
            for it in items:
                r.Items.Add(forms.StackLayoutItem(it))
            return r

        self.status = make_label("Mode: skip. No modules will move.", size=8, color=ETO_TXT_SECN)

        self.ok_btn = forms.Button(); self.ok_btn.Text = "Continue"
        self.skip_btn = forms.Button(); self.skip_btn.Text = "Skip"
        self.ok_btn.Click += self.on_ok
        self.skip_btn.Click += self.on_skip

        buttons = forms.DynamicLayout()
        buttons.Spacing = drawing.Size(8, 0)
        buttons.AddRow(None, self.skip_btn, self.ok_btn)

        root = forms.StackLayout()
        root.Orientation = forms.Orientation.Vertical
        root.Spacing = 8
        root.Items.Add(forms.StackLayoutItem(title))
        root.Items.Add(forms.StackLayoutItem(info))
        root.Items.Add(forms.StackLayoutItem(row("Projection mode:", self.mode_dd)))
        root.Items.Add(forms.StackLayoutItem(row("Short-face max:", self.short_sl, self.short_vl)))
        root.Items.Add(forms.StackLayoutItem(row("Long-face max:", self.long_sl, self.long_vl)))
        root.Items.Add(forms.StackLayoutItem(self.status))
        root.Items.Add(forms.StackLayoutItem(buttons))
        self.Content = root
        self.on_change(None, None)

    def on_change(self, sender, e):
        try:
            self.short_vl.Text = "{0:.2f} m".format(float(self.short_sl.Value) / 100.0)
            self.long_vl.Text = "{0:.2f} m".format(float(self.long_sl.Value) / 100.0)
            modes = ["skip", "parametric", "checker"]
            mode = modes[max(0, int(self.mode_dd.SelectedIndex))]
            if mode == "skip":
                self.status.Text = "Mode: skip. No modules will move."
            elif mode == "parametric":
                self.status.Text = "Parametric: modules vary between 0 and selected max."
            else:
                self.status.Text = "Checkerboard: alternating eligible modules move to selected max."
        except Exception:
            pass

    def get_values(self):
        idx = max(0, int(self.mode_dd.SelectedIndex))
        modes = [PROJECTION_MODE_SKIP, PROJECTION_MODE_PARAMETRIC, PROJECTION_MODE_CHECKER]
        return {
            "mode": modes[idx] if idx < len(modes) else PROJECTION_MODE_SKIP,
            "short_max": float(self.short_sl.Value) / 100.0,
            "long_max": float(self.long_sl.Value) / 100.0,
        }

    def on_ok(self, sender, e):
        self.Close(True)

    def on_skip(self, sender, e):
        self.mode_dd.SelectedIndex = 0
        self.Close(True)


# ---------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------
def main():
    dlg = WoSyHoV13Dialog()
    try:
        result = dlg.ShowModal(Rhino.UI.RhinoEtoApp.MainWindowForDocument(sc.doc))
    except Exception:
        try:
            result = dlg.ShowModal(Rhino.UI.RhinoEtoApp.MainWindow)
        except Exception:
            result = dlg.ShowModal()

    if not result:
        print("Cancelled.")
        return

    v = dlg.get_values()

    # Optional second-stage facade projection dialog.
    # Default is skip, so all existing massing behaviour is preserved unless selected.
    projection_options = {"mode": PROJECTION_MODE_SKIP, "short_max": 0.0, "long_max": 0.0}
    try:
        pdlg = WoSyHoProjectionDialog()
        try:
            presult = pdlg.ShowModal(Rhino.UI.RhinoEtoApp.MainWindowForDocument(sc.doc))
        except Exception:
            try:
                presult = pdlg.ShowModal(Rhino.UI.RhinoEtoApp.MainWindow)
            except Exception:
                presult = pdlg.ShowModal()
        if presult:
            projection_options = pdlg.get_values()
    except Exception as ex:
        print("Projection dialog skipped: {0}".format(ex))

    print("=" * 60)
    print("Timber Housing v20 - A-only Cascade + Optional Facade Projection")
    print("=" * 60)
    print("Cluster:          {0} x {1} cells ({2:.1f} x {3:.1f} m)".format(
        v["NX"], v["NY"], v["NX"] * GRID, v["NY"] * GRID))
    print("NE corner floors: {0} ({1:.2f} m)".format(v["peak_ne_floors"], v["peak_ne_floors"] * FLOOR_H))
    print("NW corner floors: {0} ({1:.2f} m)".format(v["peak_nw_floors"], v["peak_nw_floors"] * FLOOR_H))
    print("SE corner floors: {0} ({1:.2f} m)".format(v["peak_se_floors"], v["peak_se_floors"] * FLOOR_H))
    print("SW corner floors: {0} ({1:.2f} m)".format(v["peak_sw_floors"], v["peak_sw_floors"] * FLOOR_H))
    print("Base floors:      {0} ({1:.2f} m)".format(v["base_floors"], v["base_floors"] * FLOOR_H))
    print("Courtyard:        {0}".format(v["courtyard_size"]))
    print("Curve power:      {0:.2f}".format(v["curve_power"]))
    print("Perforation:      {0}%".format(v["perforation_pct"]))
    print("Modules:          A ONLY only. No C. Corridor void loop locked in plan.")
    print("Hochhaus:         {0}".format("YES (>22 m)" if v["peak_floors"] * FLOOR_H > 22 else "no"))
    print("Hourglass sides:  {0}".format(v.get("hourglass_sides", [])))
    print("Projection mode:  {0} | short max: {1:.2f} m | long max: {2:.2f} m".format(
        projection_options.get("mode", PROJECTION_MODE_SKIP),
        projection_options.get("short_max", 0.0),
        projection_options.get("long_max", 0.0)))
    print("=" * 60)

    try:
        rs.EnableRedraw(False)
        counts = generate_cluster(
            v["NX"], v["NY"], v["peak_ne_floors"], v["peak_nw_floors"],
            v["peak_se_floors"], v["peak_sw_floors"],
            v["courtyard_size"], v["curve_power"], v["perforation_pct"],
            hourglass_sides=v.get("hourglass_sides", []),
            projection_options=projection_options
        )
    finally:
        rs.EnableRedraw(True)
        sc.doc.Views.Redraw()

    print("Placement summary:")
    print("  A horizontal modules: {0}".format(counts.get("A", 0)))
    print("  B vertical modules:   {0} (disabled in A-only mode)".format(counts.get("B", 0)))
    print("  Perforation voids:    {0}".format(counts.get("P1", counts.get("O1", 0))))
    print("=" * 60)
    return counts


if __name__ == "__main__":
    main()
