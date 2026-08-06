# -*- coding: utf-8 -*-
"""
Parametric Timber Student Housing - v16m A-Only Four-Corner Peak Cascade + Perforation
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
 10. Selected outer-facade A modules MOVE outward as true cantilevers in a checker/rhythm pattern.

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
CORE_ANCHOR_RADIUS = 3                 # cells around core that stay solid at base
BRIDGE_BAND_MAX_THICKNESS = 2          # keep only 2 floors between top and inverted cascade

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
                                  cell_floor_counts=None):
    """
    v16k — ADAPTIVE CURVE-REACH HOURGLASS CUT.

    Correct rule:
      For each side, test whether a normal curve with strength 2.0–3.0 can
      reach the base floor within that side length.

      If it can reach base: no deletion.
      If it cannot reach base: add inverted cascade from bottom, leaving a
      2-floor bridge between the upper cascade and lower inverted cascade.

    This avoids the previous mistake where the long side was deleted simply
    because the visible elevation was still high.
    """
    base_i = int(base_floors)
    bridge = int(BRIDGE_BAND_MAX_THICKNESS)

    if is_courtyard(cx, cy, c0x, c0y, cw, ch):
        return 0

    # Keep cores and immediate landing zones solid.
    if core_cells:
        for ccx, ccy in core_cells:
            if abs(cx - ccx) <= CORE_ANCHOR_RADIUS and abs(cy - ccy) <= CORE_ANCHOR_RADIUS:
                return 0

    # Preserve structural outside corners.
    try:
        if classify_cell(cx, cy, NX, NY, c0x, c0y, cw, ch) == "outer_corner":
            return 0
    except Exception:
        pass

    cuts = []

    for side, pos, length in _side_memberships_for_full_zone(cx, cy, NX, NY, c0x, c0y, cw, ch):
        reaches = _can_side_curve_reach_base(
            side, NX, NY, peak_ne, peak_nw, peak_se, peak_sw, base_i
        )
        if reaches:
            continue

        # Side failed the curve-reach test, so create bottom inverted cascade.
        dist_left = float(pos)
        dist_right = float(length - 1 - pos)
        dist_edge = min(dist_left, dist_right)
        half_len = max(1.0, float(length - 1) * 0.5)

        # 0 at side ends, 1 at centre.
        centre_factor = max(0.0, min(1.0, dist_edge / half_len))

        # Visible bottom inverted cascade:
        # centre removes enough base floors to create the arch, then top_cap()
        # keeps only the 2-floor bridge band above it.
        target_cut = base_i + bridge + 1  # with base=2 and bridge=2, centre cut = 5 floors
        cut = int(round(float(target_cut) * centre_factor))
        cuts.append(max(0, cut))

    return max(cuts) if cuts else 0


def inverted_cascade_top_cap(cx, cy, NX, NY, c0x, c0y, cw, ch,
                              peak_ne, peak_nw, peak_se, peak_sw,
                              base_floors, core_cells=None,
                              cell_floor_counts=None):
    """
    Returns the MAX floor count this cell is allowed to have when the
    inverted cascade is active. This caps the bridge band thickness in the
    center of short sides to BRIDGE_BAND_MAX_THICKNESS floors (thin hourglass bridge band).

    Returns None for cells outside the inverted cascade zone, long sides,
    courtyard, or core-anchor zones.
    """
    bottom_cut = inverted_cascade_bottom_cut(
        cx, cy, NX, NY, c0x, c0y, cw, ch,
        peak_ne, peak_nw, peak_se, peak_sw,
        base_floors, core_cells, cell_floor_counts
    )

    if bottom_cut <= 0:
        return None

    top_cap = bottom_cut + int(BRIDGE_BAND_MAX_THICKNESS)
    return top_cap

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
    """Bake each core as one 7.5 m x 7.5 m cuboid with LOCAL required height."""
    count = 0
    for item in core_items:
        cx, cy, orient = item
        x = cx * GRID
        y = cy * GRID
        dx = 2 * GRID
        dy = 2 * GRID
        floors = int(core_floor_counts.get(item, 1))
        dz = max(1, floors) * FLOOR_H
        brep = make_box(x, y, 0, dx, dy, dz)
        bake_brep(brep, "core")
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
                  base_floors=DEFAULT_BASE):
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

                # Inverted cascade from base on SHORT sides only.
                # The top height field remains untouched; this only removes
                # bottom modules where a short-side top cascade cannot naturally
                # reach the base, creating the inverted hourglass arch.
                bottom_cut = inverted_cascade_bottom_cut(
                    cx, cy, NX, NY, c0x, c0y, cw, ch,
                    int(peak_ne_floors), int(peak_nw_floors),
                    int(peak_se_floors), int(peak_sw_floors),
                    int(base_floors), core_cells, cell_floor_counts
                )
                if level < bottom_cut:
                    continue

                top_cap = inverted_cascade_top_cap(
                    cx, cy, NX, NY, c0x, c0y, cw, ch,
                    int(peak_ne_floors), int(peak_nw_floors),
                    int(peak_se_floors), int(peak_sw_floors),
                    int(base_floors), core_cells, cell_floor_counts
                )
                if top_cap is not None and level >= top_cap:
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

                    neighbour_bottom_cut = inverted_cascade_bottom_cut(
                        nx, ny, NX, NY, c0x, c0y, cw, ch,
                        int(peak_ne_floors), int(peak_nw_floors),
                        int(peak_se_floors), int(peak_sw_floors),
                        int(base_floors), core_cells, cell_floor_counts
                    )
                    if level < neighbour_bottom_cut:
                        continue

                    neighbour_top_cap = inverted_cascade_top_cap(
                        nx, ny, NX, NY, c0x, c0y, cw, ch,
                        int(peak_ne_floors), int(peak_nw_floors),
                        int(peak_se_floors), int(peak_sw_floors),
                        int(base_floors), core_cells, cell_floor_counts
                    )
                    if neighbour_top_cap is not None and level >= neighbour_top_cap:
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

                    brep = make_box(x0 + ox, y0 + oy, level * FLOOR_H, dx_box, dy_box, FLOOR_H)

                    frac = float(level) / float(max(1, peak_floors - 1))
                    if frac < 0.33:
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
# MAIN GENERATION
# ---------------------------------------------------------------------
def generate_cluster(NX, NY, peak_ne_floors, peak_nw_floors, peak_se_floors, peak_sw_floors,
                     courtyard_size, curve_power, perforation_pct):
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
        base_floors=base_floors
    )
    counts["P1"] = 0
    counts["O1"] = 0
    counts["O2"] = 0

    # Core height follows local module heights around each core.
    core_floor_counts = local_core_floor_counts(core_items, core_cells, cell_floor_counts, NX, NY, base_floors, peak_specs=peak_specs)
    counts["CORE"] = bake_cores(core_items, core_floor_counts)

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
        # IMPORTANT: initialise Eto Dialog before setting Title/Content.
        forms.Dialog[bool].__init__(self)

        self.Title = "Timber Housing v16m - Four-corner peak control"
        self.Padding = drawing.Padding(0)
        try:
            self.BackgroundColor = ETO_BG_WARM
        except Exception:
            pass
        self.MinimumSize = drawing.Size(460, 560)
        try:
            self.ClientSize = drawing.Size(520, 610)
        except Exception:
            pass
        self.Resizable = True

        # Title panel
        title_label = make_label("Timber Housing v16m", bold=True, size=16,
                                 color=ETO_TXT_PRIM, impact=True)
        subtitle_label = make_label("A-only cascade + 4 cores + strong-drop short-side hourglass",
                                    italic=True, size=9, color=ETO_TXT_SECN)

        title_panel = forms.Panel()
        try:
            title_panel.BackgroundColor = ETO_BG_PANEL
        except Exception:
            pass
        title_panel.Padding = drawing.Padding(14, 8, 14, 8)

        title_stack = forms.StackLayout()
        title_stack.Orientation = forms.Orientation.Vertical
        title_stack.HorizontalContentAlignment = forms.HorizontalAlignment.Left
        title_stack.Spacing = 2
        add_stack_item(title_stack, title_label)
        add_stack_item(title_stack, subtitle_label)
        title_panel.Content = title_stack

        accent_top = forms.Panel()
        try:
            accent_top.BackgroundColor = ETO_ACCENT
        except Exception:
            pass
        accent_top.Size = drawing.Size(460, 3)

        # Inputs
        self.length_stepper = self._make_stepper(8, 60, DEFAULT_NX, 0, 1)
        self.depth_stepper  = self._make_stepper(8, 40, DEFAULT_NY, 0, 1)
        self.ne_stepper  = self._make_stepper(2, 20, DEFAULT_PEAK_NE, 0, 1)
        self.nw_stepper  = self._make_stepper(2, 20, DEFAULT_PEAK_NW, 0, 1)
        self.se_stepper  = self._make_stepper(2, 20, DEFAULT_PEAK_SE, 0, 1)
        self.sw_stepper  = self._make_stepper(2, 20, DEFAULT_PEAK_SW, 0, 1)
        # Base is locked by design.
        self.base_floors_fixed = DEFAULT_BASE
        self.curve_stepper  = self._make_stepper(1.0, 5.0, DEFAULT_CURVE_POWER, 1, 0.1)
        self.perforation_stepper = self._make_stepper(0, 50, DEFAULT_PERFORATION_PCT, 0, 1)

        self.courtyard_dd = self._make_dropdown(["Auto from module rows/columns"], 0)

        # Status panel
        self.status_label = make_label("", italic=True, size=8, color=ETO_TXT_SECN)
        try:
            self.status_label.Width = 430
        except Exception:
            pass

        # Wire change events
        for ctl in [self.length_stepper, self.depth_stepper, self.ne_stepper, self.nw_stepper,
                    self.se_stepper, self.sw_stepper, self.curve_stepper, self.perforation_stepper]:
            ctl.ValueChanged += self.on_change
        self.courtyard_dd.SelectedIndexChanged += self.on_change

        # Buttons
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

        # Layout
        body = forms.DynamicLayout()
        body.Padding = drawing.Padding(14, 8, 14, 8)
        body.Spacing = drawing.Size(8, 4)

        body.AddRow(make_label("FORM", bold=True, size=10, color=ETO_TXT_PRIM, impact=True))
        body.AddRow(make_label("Cluster length (cells, X):"), self.length_stepper)
        body.AddRow(make_label("Cluster depth (cells, Y):"), self.depth_stepper)
        body.AddRow(None)

        body.AddRow(make_label("CURVED CASCADE", bold=True, size=10, color=ETO_TXT_PRIM, impact=True))
        body.AddRow(make_label("NE corner floors:"), self.ne_stepper)
        body.AddRow(make_label("NW corner floors:"), self.nw_stepper)
        body.AddRow(make_label("SE corner floors:"), self.se_stepper)
        body.AddRow(make_label("SW corner floors:"), self.sw_stepper)
        body.AddRow(make_label("Base floors:"), make_label("2 locked", size=8, color=ETO_TXT_SECN))
        body.AddRow(make_label("Curve power:"), self.curve_stepper)
        body.AddRow(None)

        body.AddRow(make_label("COURTYARD + PERFORATION", bold=True, size=10, color=ETO_TXT_PRIM, impact=True))
        body.AddRow(make_label("Courtyard:"), self.courtyard_dd)
        body.AddRow(make_label("Perforation %:"), self.perforation_stepper)
        body.AddRow(make_label("Plan:"), make_label("auto courtyard + corridor loop", size=8, color=ETO_TXT_SECN))
        body.AddRow(make_label("Perf.:"), make_label("0 solid | 15 balanced | 50 porous", size=8, color=ETO_TXT_SECN))
        body.AddRow(None)

        body.AddRow(make_label("LIVE PREVIEW", bold=True, size=10, color=ETO_TXT_HILT, impact=True))
        body.AddRow(self.status_label)

        btn_layout = forms.DynamicLayout()
        btn_layout.Padding = drawing.Padding(14, 4, 14, 10)
        btn_layout.Spacing = drawing.Size(10, 0)
        btn_layout.AddRow(None, self.abort_btn, self.confirm_btn)

        accent_bot = forms.Panel()
        try:
            accent_bot.BackgroundColor = ETO_ACCENT
        except Exception:
            pass
        accent_bot.Size = drawing.Size(460, 3)

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
            self.ClientSize = drawing.Size(520, 610)
        except Exception:
            pass
        self.refresh_status()

    def _make_stepper(self, mn, mx, val, decimals=0, increment=1):
        s = forms.NumericStepper()
        s.MinValue = mn
        s.MaxValue = mx
        s.Value = val
        s.Increment = increment
        s.DecimalPlaces = decimals
        s.Width = 82
        try:
            s.BackgroundColor = ETO_BG_INPUT
        except Exception:
            pass
        return s

    def _make_dropdown(self, items, default_idx):
        dd = forms.DropDown()
        for item in items:
            dd.Items.Add(item)
        dd.SelectedIndex = default_idx
        dd.Width = 190
        try:
            dd.BackgroundColor = ETO_BG_INPUT
        except Exception:
            pass
        return dd

    def get_courtyard(self):
        return "auto"

    def get_values(self):
        ne = int(self.ne_stepper.Value)
        nw = int(self.nw_stepper.Value)
        se = int(self.se_stepper.Value)
        sw = int(self.sw_stepper.Value)
        base = DEFAULT_BASE
        peak_max = max(ne, nw, se, sw, base)
        return {
            "NX": int(self.length_stepper.Value),
            "NY": int(self.depth_stepper.Value),
            "peak_ne_floors": ne,
            "peak_nw_floors": nw,
            "peak_se_floors": se,
            "peak_sw_floors": sw,
            "peak_floors": peak_max,
            "base_floors": base,
            "courtyard_size": self.get_courtyard(),
            "curve_power": float(self.curve_stepper.Value),
            "perforation_pct": int(self.perforation_stepper.Value),
        }

    def on_change(self, sender, e):
        self.refresh_status()

    def refresh_status(self):
        try:
            v = self.get_values()
            NX = v["NX"]
            NY = v["NY"]
            peak = v["peak_floors"]
            base = v["base_floors"]
            curve = v["curve_power"]
            perforation = v["perforation_pct"]
            peak_H = peak * FLOOR_H
            base_H = base * FLOOR_H
            hochhaus = "YES" if peak_H > 22 else "no"
            cluster_W = NX * GRID
            cluster_D = NY * GRID
            peak_setback = 0.4 * peak_H
            base_setback = 0.4 * base_H

            c0x, c0y, cw, ch = courtyard_bounds(NX, NY, v["courtyard_size"])
            courtyard_W = cw * GRID
            courtyard_D = ch * GRID
            total_est = max(0, (NX * NY - cw * ch) * max(1, peak))
            est_voids = int(total_est * (float(perforation) / 100.0) * 0.5)

            self.status_label.Text = (
                "Footprint: {0}x{1} cells ({2:.1f}x{3:.1f} m)\n"
                "Max/Base: {4} fl / {6} fl  |  Curve: {8:.1f}\n"
                "NE/NW/SE/SW: {12}/{13}/{18}/{19} floors\n"
                "Perforation: {9}%  |  Est. voids: ~{17}\n"
                "Courtyard: {10:.1f}x{11:.1f} m\n"
                "Hochhaus: {14}  |  A-only + 4 cores + no cantilever"
            ).format(NX, NY, cluster_W, cluster_D,
                     peak, peak_H, base, base_H, curve, perforation,
                     courtyard_W, courtyard_D, v["peak_ne_floors"], v["peak_nw_floors"], hochhaus,
                     base_setback, peak_setback, est_voids, v["peak_se_floors"], v["peak_sw_floors"])
        except Exception as ex:
            self.status_label.Text = "Status: " + str(ex)

    def on_confirm(self, sender, e):
        self.Close(True)

    def on_abort(self, sender, e):
        self.Close(False)


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

    print("=" * 60)
    print("Timber Housing v16m - A-only Four-Corner Peak Cascade + Percentage Perforation")
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
    print("=" * 60)

    try:
        rs.EnableRedraw(False)
        counts = generate_cluster(
            v["NX"], v["NY"], v["peak_ne_floors"], v["peak_nw_floors"],
            v["peak_se_floors"], v["peak_sw_floors"],
            v["courtyard_size"], v["curve_power"], v["perforation_pct"]
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
