# -*- coding: utf-8 -*-
"""
Parametric Timber Student Housing - v12 Cascading Ring Tower Configurator
=================================================

DETERMINISTIC, RULE-BASED. NO RANDOMNESS.

Closed/open ring building with courtyard, height cascades diagonally
from a chosen peak corner to the opposite low corner.

USER INPUTS (8):
  1. Cluster length (X cells)
  2. Cluster depth  (Y cells)
  3. Peak floors (high corner)
  4. Base floors (low corner)
  5. Peak corner (NE/NW/SE/SW)
  6. Courtyard size (Small/Medium/Large)
  7. Cascade sharpness (Sharp 1:1 / Medium 1:2 / Gentle 1:3)
  8. Ring type (Closed / Open low side)

RULES (Valley/MVRDV NEXT methodology):
  R1 - Closed ring with central courtyard preserved
  R2 - Manhattan distance from peak corner determines cell height
  R3 - floor_count = peak_floors - distance // sharpness, clamped to base
  R4 - Module placement: A perimeter, B corners, C accents
  R5 - Setback per cell based on local height (0.4 H)
  R6 - Roof terraces automatic on cascade steps
  R7 - Stair cores: 2 in podium + 2 in peak region (Hochhaus rule)
  R8 - Orthogonal yellow corridor 1.5 m wide per floor

MODULES (3 types, no others):
  A: 7.50 x 3.75 x 3.75   horizontal studio, 1 floor
  B: 3.75 x 3.75 x 7.50   vertical maisonette, 2 floors
  C: 3.75 x 7.50 x 7.50   double maisonette, 2 floors

Run in Rhino: _RunPythonScript -> wosyho_v12.py -> fill dialog -> GENERATE
"""

import Rhino
import rhinoscriptsyntax as rs
import scriptcontext as sc
import Rhino.Geometry as rg
import System.Drawing as sd
import Eto.Forms as forms
import Eto.Drawing as drawing

# =====================================================================
# CONSTANTS
# =====================================================================
GRID = 3.75
FLOOR_H = 3.75

CORRIDOR_W = 1.5
CORRIDOR_H = 2.4

# Eto colors (red/grey/black palette)
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

# =====================================================================
# LAYERS
# =====================================================================
LAYERS = {
    "A_low":     ("WoSyHo::A_horizontal_low",   sd.Color.FromArgb(220, 160, 80)),
    "A_mid":     ("WoSyHo::A_horizontal_mid",   sd.Color.FromArgb(210, 130, 60)),
    "A_high":    ("WoSyHo::A_horizontal_peak",  sd.Color.FromArgb(190, 100, 40)),
    "B":         ("WoSyHo::B_vertical",         sd.Color.FromArgb(80, 110, 170)),
    "C":         ("WoSyHo::C_double",           sd.Color.FromArgb(150, 90, 130)),
    "core":      ("WoSyHo::Stair_Cores",        sd.Color.FromArgb(50, 180, 80)),
    "corridor":  ("WoSyHo::Corridors",          sd.Color.FromArgb(245, 200, 30)),
    "terrace":   ("WoSyHo::Roof_Terraces",      sd.Color.FromArgb(110, 180, 110)),
    "setback":   ("WoSyHo::Setback_Lines",      sd.Color.FromArgb(160, 30, 30)),
    "courtyard": ("WoSyHo::Courtyard",          sd.Color.FromArgb(100, 100, 100)),
}

def ensure_layer(name, color):
    idx = sc.doc.Layers.FindByFullPath(name, -1)
    if idx < 0:
        lyr = Rhino.DocObjects.Layer()
        lyr.Name = name
        lyr.Color = color
        idx = sc.doc.Layers.Add(lyr)
    return idx

def init_layers():
    for key in LAYERS:
        name, color = LAYERS[key]
        ensure_layer(name, color)

def lidx(key):
    name, _ = LAYERS[key]
    return sc.doc.Layers.FindByFullPath(name, -1)

# =====================================================================
# GEOMETRY HELPERS
# =====================================================================
def make_box(x, y, z, dx, dy, dz):
    pt0 = rg.Point3d(x, y, z)
    pt1 = rg.Point3d(x + dx, y + dy, z + dz)
    return rg.Box(rg.BoundingBox(pt0, pt1)).ToBrep()

def bake_brep(brep, layer_key):
    if brep is None:
        return None
    attrs = Rhino.DocObjects.ObjectAttributes()
    li = lidx(layer_key)
    if li >= 0:
        attrs.LayerIndex = li
    return sc.doc.Objects.AddBrep(brep, attrs)

def bake_curve(curve, layer_key):
    if curve is None:
        return None
    attrs = Rhino.DocObjects.ObjectAttributes()
    li = lidx(layer_key)
    if li >= 0:
        attrs.LayerIndex = li
    return sc.doc.Objects.AddCurve(curve, attrs)

# =====================================================================
# COURTYARD GEOMETRY
# =====================================================================
def courtyard_bounds(NX, NY, size):
    if size == "small":
        cw = max(4, NX // 4)
        ch = max(3, NY // 4)
    elif size == "medium":
        cw = max(6, NX // 3)
        ch = max(4, NY // 3)
    else:  # large
        cw = max(8, NX // 2)
        ch = max(6, NY // 2)
    cx0 = (NX - cw) // 2
    cy0 = (NY - ch) // 2
    return cx0, cy0, cw, ch

def is_courtyard(cx, cy, c0x, c0y, cw, ch):
    return c0x <= cx < c0x + cw and c0y <= cy < c0y + ch

def is_in_cluster(cx, cy, NX, NY):
    return 0 <= cx < NX and 0 <= cy < NY

# =====================================================================
# CASCADE RULE
# =====================================================================
def cascade_floor_count(cx, cy, NX, NY, peak_corner, peak_floors, base_floors, sharpness):
    if peak_corner == "NE":
        dx = (NX - 1) - cx
        dy = (NY - 1) - cy
    elif peak_corner == "NW":
        dx = cx
        dy = (NY - 1) - cy
    elif peak_corner == "SE":
        dx = (NX - 1) - cx
        dy = cy
    else:  # SW
        dx = cx
        dy = cy
    
    distance = dx + dy
    drop = distance // sharpness
    floor_count = peak_floors - drop
    
    if floor_count < base_floors:
        floor_count = base_floors
    if floor_count < 0:
        floor_count = 0
    return floor_count

def apply_open_ring(cx, cy, fc, NX, NY, peak_corner, base_floors, ring_type):
    """If open ring + at low corner zone, set fc=0 to create gateway."""
    if ring_type != "open":
        return fc
    if fc > base_floors:
        return fc
    # Compute distance for the low corner test
    if peak_corner == "NE":
        dx = (NX - 1) - cx
        dy = (NY - 1) - cy
    elif peak_corner == "NW":
        dx = cx
        dy = (NY - 1) - cy
    elif peak_corner == "SE":
        dx = (NX - 1) - cx
        dy = cy
    else:
        dx = cx
        dy = cy
    max_dist = (NX - 1) + (NY - 1)
    if dx + dy >= max_dist - 1:
        return 0  # gateway opening
    return fc

# =====================================================================
# STAIR CORES
# =====================================================================
def get_stair_core_positions(NX, NY, peak_corner, c0x, c0y, cw, ch):
    """Return list of (cx, cy) tuples for 4 stair cores."""
    cores = []
    
    # 2 cores in peak quadrant
    if peak_corner == "NE":
        cores.append((NX - 2, NY - 2))
        cores.append((NX - 3, NY - 3))
    elif peak_corner == "NW":
        cores.append((1, NY - 2))
        cores.append((2, NY - 3))
    elif peak_corner == "SE":
        cores.append((NX - 2, 1))
        cores.append((NX - 3, 2))
    else:  # SW
        cores.append((1, 1))
        cores.append((2, 2))
    
    # 2 cores in opposite zone (for podium escape)
    mid_x = NX // 2
    mid_y = NY // 2
    
    if peak_corner == "NE":
        cores.append((max(1, c0x - 1), mid_y))
        cores.append((mid_x, max(1, c0y - 1)))
    elif peak_corner == "NW":
        cores.append((min(NX-2, c0x + cw), mid_y))
        cores.append((mid_x, max(1, c0y - 1)))
    elif peak_corner == "SE":
        cores.append((max(1, c0x - 1), mid_y))
        cores.append((mid_x, min(NY-2, c0y + ch)))
    else:  # SW
        cores.append((min(NX-2, c0x + cw), mid_y))
        cores.append((mid_x, min(NY-2, c0y + ch)))
    
    # Filter valid positions
    valid_cores = []
    for cx, cy in cores:
        if not is_in_cluster(cx, cy, NX, NY):
            continue
        if is_courtyard(cx, cy, c0x, c0y, cw, ch):
            continue
        valid_cores.append((cx, cy))
    return valid_cores

# =====================================================================
# RING CELL CLASSIFICATION
# =====================================================================
def classify_ring_cell(cx, cy, NX, NY, c0x, c0y, cw, ch):
    """Returns a label describing the cell's position in the ring."""
    # Outer corners
    if cx == 0 and cy == 0: return 'outer_corner_sw'
    if cx == NX-1 and cy == 0: return 'outer_corner_se'
    if cx == 0 and cy == NY-1: return 'outer_corner_nw'
    if cx == NX-1 and cy == NY-1: return 'outer_corner_ne'
    
    # Outer edges
    if cy == 0: return 'outer_long_s'
    if cy == NY-1: return 'outer_long_n'
    if cx == 0: return 'outer_short_w'
    if cx == NX-1: return 'outer_short_e'
    
    # Inner edges (1 cell outside courtyard)
    if cy == c0y - 1 and c0x <= cx < c0x + cw: return 'inner_s'
    if cy == c0y + ch and c0x <= cx < c0x + cw: return 'inner_n'
    if cx == c0x - 1 and c0y <= cy < c0y + ch: return 'inner_w'
    if cx == c0x + cw and c0y <= cy < c0y + ch: return 'inner_e'
    
    # Inner corners
    if cx == c0x - 1 and cy == c0y - 1: return 'inner_corner'
    if cx == c0x + cw and cy == c0y - 1: return 'inner_corner'
    if cx == c0x - 1 and cy == c0y + ch: return 'inner_corner'
    if cx == c0x + cw and cy == c0y + ch: return 'inner_corner'
    
    return 'middle'

# =====================================================================
# MODULE PLACEMENT
# =====================================================================
def place_module(cx, cy, level, floor_count, ring_class, is_core, NX, NY,
                 placed_cells, cell_floor_counts):
    """
    Decide module type at (cx, cy, level).
    Returns (kind, brep, footprint_cells) or (None, None, []).
    Deterministic.
    """
    if (cx, cy) in placed_cells:
        return (None, None, [])
    
    x = cx * GRID
    y = cy * GRID
    z = level * FLOOR_H
    
    # CORE: stair tower, single cell, full floor
    if is_core:
        return ('CORE', make_box(x, y, z, GRID, GRID, FLOOR_H), [(cx, cy)])
    
    # OUTER CORNERS: B vertical (2-floor maisonette)
    if ring_class.startswith('outer_corner_'):
        # B = 2 floors; only place on even levels where there's another floor above
        if level % 2 == 0 and level + 1 < floor_count:
            return ('B', make_box(x, y, z, GRID, GRID, FLOOR_H * 2), [(cx, cy)])
        elif level % 2 == 0:
            # Odd remainder — single floor A
            return ('A_single', make_box(x, y, z, GRID, GRID, FLOOR_H), [(cx, cy)])
        else:
            return (None, None, [])  # already covered by B below
    
    # INNER CORNERS: B vertical
    if ring_class == 'inner_corner':
        if level % 2 == 0 and level + 1 < floor_count:
            return ('B', make_box(x, y, z, GRID, GRID, FLOOR_H * 2), [(cx, cy)])
        elif level % 2 == 0:
            return ('A_single', make_box(x, y, z, GRID, GRID, FLOOR_H), [(cx, cy)])
        else:
            return (None, None, [])
    
    # OUTER LONG (north/south face): A horizontal in X
    if ring_class in ('outer_long_n', 'outer_long_s'):
        # Try to span 2 cells in X. Check cx+1 has same floor_count level available.
        if cx + 1 < NX:
            nfc = cell_floor_counts.get((cx + 1, cy), 0)
            if nfc > level and (cx + 1, cy) not in placed_cells:
                neighbor_class = classify_ring_cell(cx + 1, cy, NX, NY,
                                                    *get_courtyard_for_classify())
                # Only pair if cx is at even position relative to start of edge
                # Use simple rule: pair if cx is even
                if cx % 2 == 0:
                    return ('A', make_box(x, y, z, 2 * GRID, GRID, FLOOR_H),
                            [(cx, cy), (cx + 1, cy)])
        # Fallback: single A
        return ('A_single', make_box(x, y, z, GRID, GRID, FLOOR_H), [(cx, cy)])
    
    # OUTER SHORT (east/west face): A horizontal in Y
    if ring_class in ('outer_short_e', 'outer_short_w'):
        if cy + 1 < NY:
            nfc = cell_floor_counts.get((cx, cy + 1), 0)
            if nfc > level and (cx, cy + 1) not in placed_cells:
                if cy % 2 == 0:
                    return ('A', make_box(x, y, z, GRID, 2 * GRID, FLOOR_H),
                            [(cx, cy), (cx, cy + 1)])
        return ('A_single', make_box(x, y, z, GRID, GRID, FLOOR_H), [(cx, cy)])
    
    # INNER N/S (facing courtyard): A horizontal in X — TOP floor gets C accent
    if ring_class in ('inner_n', 'inner_s'):
        # If at top of stack, place C (double maisonette penthouse)
        if level == floor_count - 2 and level + 1 < floor_count and cx + 1 < NX:
            nfc = cell_floor_counts.get((cx + 1, cy), 0)
            if nfc > level + 1 and (cx + 1, cy) not in placed_cells and cx % 2 == 0:
                return ('C', make_box(x, y, z, GRID, GRID, FLOOR_H * 2), [(cx, cy)])
        # Default A pair
        if cx + 1 < NX:
            nfc = cell_floor_counts.get((cx + 1, cy), 0)
            if nfc > level and (cx + 1, cy) not in placed_cells:
                if cx % 2 == 0:
                    return ('A', make_box(x, y, z, 2 * GRID, GRID, FLOOR_H),
                            [(cx, cy), (cx + 1, cy)])
        return ('A_single', make_box(x, y, z, GRID, GRID, FLOOR_H), [(cx, cy)])
    
    # INNER E/W (facing courtyard): A horizontal in Y
    if ring_class in ('inner_e', 'inner_w'):
        if level == floor_count - 2 and level + 1 < floor_count and cy + 1 < NY:
            nfc = cell_floor_counts.get((cx, cy + 1), 0)
            if nfc > level + 1 and (cx, cy + 1) not in placed_cells and cy % 2 == 0:
                return ('C', make_box(x, y, z, GRID, GRID, FLOOR_H * 2), [(cx, cy)])
        if cy + 1 < NY:
            nfc = cell_floor_counts.get((cx, cy + 1), 0)
            if nfc > level and (cx, cy + 1) not in placed_cells:
                if cy % 2 == 0:
                    return ('A', make_box(x, y, z, GRID, 2 * GRID, FLOOR_H),
                            [(cx, cy), (cx, cy + 1)])
        return ('A_single', make_box(x, y, z, GRID, GRID, FLOOR_H), [(cx, cy)])
    
    # Middle (thick ring filler)
    return ('A_single', make_box(x, y, z, GRID, GRID, FLOOR_H), [(cx, cy)])

# Used inside classify call — set by outer scope
_COURTYARD_CACHE = (0, 0, 0, 0)
def set_courtyard_cache(c0x, c0y, cw, ch):
    global _COURTYARD_CACHE
    _COURTYARD_CACHE = (c0x, c0y, cw, ch)

def get_courtyard_for_classify():
    return _COURTYARD_CACHE

# =====================================================================
# CORRIDOR
# =====================================================================
def make_corridor_segment(x1, y1, x2, y2, z):
    if abs(x2 - x1) > abs(y2 - y1):
        x_min = min(x1, x2)
        x_max = max(x1, x2)
        y_c = (y1 + y2) / 2.0
        return make_box(x_min, y_c - CORRIDOR_W / 2.0, z + 0.05,
                        x_max - x_min, CORRIDOR_W, CORRIDOR_H)
    else:
        y_min = min(y1, y2)
        y_max = max(y1, y2)
        x_c = (x1 + x2) / 2.0
        return make_box(x_c - CORRIDOR_W / 2.0, y_min, z + 0.05,
                        CORRIDOR_W, y_max - y_min, CORRIDOR_H)

def generate_corridor_for_floor(level, NX, NY, c0x, c0y, cw, ch, active_cells):
    """Orthogonal corridor running along inner ring at this level."""
    z = level * FLOOR_H
    segments = []
    
    if not active_cells:
        return segments
    
    inset = GRID * 0.5
    x_west  = c0x * GRID - inset
    x_east  = (c0x + cw) * GRID + inset
    y_south = c0y * GRID - inset
    y_north = (c0y + ch) * GRID + inset
    
    has_south = any((c0x - 1 <= cx <= c0x + cw) and cy == c0y - 1
                    for cx, cy in active_cells)
    has_north = any((c0x - 1 <= cx <= c0x + cw) and cy == c0y + ch
                    for cx, cy in active_cells)
    has_west = any((c0y - 1 <= cy <= c0y + ch) and cx == c0x - 1
                   for cx, cy in active_cells)
    has_east = any((c0y - 1 <= cy <= c0y + ch) and cx == c0x + cw
                   for cx, cy in active_cells)
    
    if has_south:
        segments.append(make_corridor_segment(x_west, y_south, x_east, y_south, z))
    if has_north:
        segments.append(make_corridor_segment(x_west, y_north, x_east, y_north, z))
    if has_west:
        segments.append(make_corridor_segment(x_west, y_south, x_west, y_north, z))
    if has_east:
        segments.append(make_corridor_segment(x_east, y_south, x_east, y_north, z))
    
    return segments

# =====================================================================
# TERRACES
# =====================================================================
def generate_terraces(NX, NY, c0x, c0y, cw, ch, cell_floor_counts):
    """Find roofs of cells that have a taller neighbor → terrace footprint."""
    terraces = []
    for cx in range(NX):
        for cy in range(NY):
            if is_courtyard(cx, cy, c0x, c0y, cw, ch):
                continue
            fc = cell_floor_counts.get((cx, cy), 0)
            if fc == 0:
                continue
            # Check 4 neighbors
            for ncx, ncy in [(cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)]:
                if not is_in_cluster(ncx, ncy, NX, NY):
                    continue
                if is_courtyard(ncx, ncy, c0x, c0y, cw, ch):
                    continue
                nfc = cell_floor_counts.get((ncx, ncy), 0)
                if nfc > fc:
                    # Neighbor is taller → mark a terrace on top of THIS cell
                    x = cx * GRID
                    y = cy * GRID
                    z = fc * FLOOR_H
                    terraces.append(make_box(x + 0.15, y + 0.15, z,
                                             GRID - 0.3, GRID - 0.3, 0.10))
                    break
    return terraces

# =====================================================================
# SETBACK LINES
# =====================================================================
def draw_setback_lines(NX, NY, peak_floors):
    podium_W = NX * GRID
    podium_H = NY * GRID
    
    SB_PODIUM = 6.0
    prop_pts = [
        rg.Point3d(-SB_PODIUM, -SB_PODIUM, 0),
        rg.Point3d(podium_W + SB_PODIUM, -SB_PODIUM, 0),
        rg.Point3d(podium_W + SB_PODIUM, podium_H + SB_PODIUM, 0),
        rg.Point3d(-SB_PODIUM, podium_H + SB_PODIUM, 0),
        rg.Point3d(-SB_PODIUM, -SB_PODIUM, 0)
    ]
    bake_curve(rg.PolylineCurve(prop_pts), "setback")
    
    cluster_pts = [
        rg.Point3d(0, 0, 0),
        rg.Point3d(podium_W, 0, 0),
        rg.Point3d(podium_W, podium_H, 0),
        rg.Point3d(0, podium_H, 0),
        rg.Point3d(0, 0, 0)
    ]
    bake_curve(rg.PolylineCurve(cluster_pts), "courtyard")
    
    peak_H = peak_floors * FLOOR_H
    SB_TOWER = 0.4 * peak_H
    extra = SB_TOWER - SB_PODIUM
    if extra > 0:
        z_peak = peak_floors * FLOOR_H
        tow_pts = [
            rg.Point3d(extra, extra, z_peak),
            rg.Point3d(podium_W - extra, extra, z_peak),
            rg.Point3d(podium_W - extra, podium_H - extra, z_peak),
            rg.Point3d(extra, podium_H - extra, z_peak),
            rg.Point3d(extra, extra, z_peak)
        ]
        bake_curve(rg.PolylineCurve(tow_pts), "setback")

# =====================================================================
# MAIN GENERATE
# =====================================================================
def generate_cluster(NX, NY, peak_floors, base_floors, peak_corner,
                     courtyard_size, sharpness, ring_type):
    init_layers()
    
    # Courtyard
    c0x, c0y, cw, ch = courtyard_bounds(NX, NY, courtyard_size)
    set_courtyard_cache(c0x, c0y, cw, ch)
    
    # Floor counts per cell
    cell_floor_counts = {}
    for cx in range(NX):
        for cy in range(NY):
            if is_courtyard(cx, cy, c0x, c0y, cw, ch):
                cell_floor_counts[(cx, cy)] = 0
                continue
            fc = cascade_floor_count(cx, cy, NX, NY, peak_corner,
                                     peak_floors, base_floors, sharpness)
            fc = apply_open_ring(cx, cy, fc, NX, NY, peak_corner,
                                 base_floors, ring_type)
            cell_floor_counts[(cx, cy)] = fc
    
    # Stair cores
    cores = set(get_stair_core_positions(NX, NY, peak_corner, c0x, c0y, cw, ch))
    
    counts = {"A": 0, "A_single": 0, "B": 0, "C": 0, "CORE": 0,
              "CORRIDOR": 0, "TERRACE": 0}
    
    # Place modules level by level
    for level in range(peak_floors):
        placed_cells = set()
        active_cells = set()
        
        for cy in range(NY):
            for cx in range(NX):
                if is_courtyard(cx, cy, c0x, c0y, cw, ch):
                    continue
                fc = cell_floor_counts.get((cx, cy), 0)
                if level >= fc:
                    continue
                active_cells.add((cx, cy))
                
                if (cx, cy) in placed_cells:
                    continue
                
                ring_class = classify_ring_cell(cx, cy, NX, NY, c0x, c0y, cw, ch)
                is_core = (cx, cy) in cores
                
                kind, brep, footprint = place_module(
                    cx, cy, level, fc, ring_class, is_core,
                    NX, NY, placed_cells, cell_floor_counts
                )
                if brep is None:
                    continue
                
                for fc_cell in footprint:
                    placed_cells.add(fc_cell)
                    active_cells.add(fc_cell)
                
                # Choose layer
                if kind == "CORE":
                    layer_key = "core"
                elif kind == "B":
                    layer_key = "B"
                elif kind == "C":
                    layer_key = "C"
                else:
                    # A or A_single — color by height
                    if peak_floors > 1:
                        frac = float(level) / float(peak_floors - 1)
                    else:
                        frac = 0.0
                    if frac < 0.33:
                        layer_key = "A_low"
                    elif frac < 0.66:
                        layer_key = "A_mid"
                    else:
                        layer_key = "A_high"
                
                bake_brep(brep, layer_key)
                counts[kind] = counts.get(kind, 0) + 1
        
        # Corridor for this level
        if active_cells:
            for seg in generate_corridor_for_floor(level, NX, NY, c0x, c0y, cw, ch, active_cells):
                bake_brep(seg, "corridor")
                counts["CORRIDOR"] += 1
    
    # Terraces
    for tb in generate_terraces(NX, NY, c0x, c0y, cw, ch, cell_floor_counts):
        bake_brep(tb, "terrace")
        counts["TERRACE"] += 1
    
    # Setback lines
    draw_setback_lines(NX, NY, peak_floors)
    
    return counts, cell_floor_counts

# =====================================================================
# ETO DIALOG
# =====================================================================
def make_label(text, bold=False, size=None, color=None, italic=False, impact=False):
    lbl = forms.Label()
    lbl.Text = text
    if color is not None:
        lbl.TextColor = color
    
    # FontStyle.None is reserved Python keyword - use getattr
    style = getattr(drawing.FontStyle, 'None')
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
        lbl.Font = drawing.Font(font_name, size or 10, style)
    except:
        try:
            lbl.Font = drawing.Font("Arial", size or 10, style)
        except:
            pass
    return lbl


class WoSyHoV12Dialog(forms.Dialog[bool]):
    def __init__(self):
        self.Title = "Timber Housing v12 - Cascading Ring Tower"
        self.Padding = drawing.Padding(0)
        try:
            self.BackgroundColor = ETO_BG_WARM
        except:
            pass
        self.MinimumSize = drawing.Size(460, 660)
        self.Resizable = False
        
        # Title
        title_label = make_label("Timber Housing v12", bold=True, size=18,
                                 color=ETO_TXT_PRIM, impact=True)
        subtitle_label = make_label("cascading ring tower configurator",
                                    italic=True, size=10, color=ETO_TXT_SECN)
        
        title_panel = forms.Panel()
        try:
            title_panel.BackgroundColor = ETO_BG_PANEL
        except:
            pass
        title_panel.Padding = drawing.Padding(20, 14, 20, 12)
        title_stack = forms.StackLayout()
        title_stack.Orientation = forms.Orientation.Vertical
        title_stack.HorizontalContentAlignment = forms.HorizontalAlignment.Left
        title_stack.Spacing = 2
        title_stack.Items.Add(title_label)
        title_stack.Items.Add(subtitle_label)
        title_panel.Content = title_stack
        
        accent_top = forms.Panel()
        try:
            accent_top.BackgroundColor = ETO_ACCENT
        except:
            pass
        accent_top.Size = drawing.Size(460, 4)
        
        # Inputs
        self.length_stepper = self._make_stepper(14, 30, 22)
        self.depth_stepper  = self._make_stepper(10, 18, 14)
        self.peak_stepper   = self._make_stepper(8, 15, 13)
        self.base_stepper   = self._make_stepper(2, 5, 2)
        
        self.corner_dd = self._make_dropdown(
            ["North-East (NE)", "North-West (NW)", "South-East (SE)", "South-West (SW)"], 0)
        self.courtyard_dd = self._make_dropdown(["Small", "Medium", "Large"], 1)
        self.sharpness_dd = self._make_dropdown(
            ["Sharp (1:1)", "Medium (1:2)", "Gentle (1:3)"], 1)
        self.ring_dd = self._make_dropdown(
            ["Closed (full ring)", "Open (low side opens to ground)"], 0)
        
        # Status panel
        self.status_label = make_label("", italic=True, size=9, color=ETO_TXT_SECN)
        
        # Wire change events
        self.length_stepper.ValueChanged += self.on_change
        self.depth_stepper.ValueChanged += self.on_change
        self.peak_stepper.ValueChanged += self.on_change
        self.base_stepper.ValueChanged += self.on_change
        self.corner_dd.SelectedIndexChanged += self.on_change
        self.courtyard_dd.SelectedIndexChanged += self.on_change
        self.sharpness_dd.SelectedIndexChanged += self.on_change
        self.ring_dd.SelectedIndexChanged += self.on_change
        
        # Buttons
        self.confirm_btn = forms.Button()
        self.confirm_btn.Text = "GENERATE"
        self.confirm_btn.Size = drawing.Size(170, 42)
        try:
            self.confirm_btn.BackgroundColor = ETO_CONFIRM
            self.confirm_btn.TextColor = ETO_WHITE
            self.confirm_btn.Font = drawing.Font("Impact", 12, drawing.FontStyle.Bold)
        except:
            pass
        self.confirm_btn.Click += self.on_confirm
        
        self.abort_btn = forms.Button()
        self.abort_btn.Text = "Cancel"
        self.abort_btn.Size = drawing.Size(110, 42)
        try:
            self.abort_btn.BackgroundColor = ETO_ABORT
            self.abort_btn.TextColor = ETO_WHITE
            self.abort_btn.Font = drawing.Font("Georgia", 10, drawing.FontStyle.Italic)
        except:
            pass
        self.abort_btn.Click += self.on_abort
        
        # Layout
        body = forms.DynamicLayout()
        body.Padding = drawing.Padding(20, 12, 20, 12)
        body.Spacing = drawing.Size(10, 8)
        
        body.AddRow(make_label("FORM", bold=True, size=10, color=ETO_TXT_PRIM, impact=True))
        body.AddRow(make_label("Cluster length (cells, X):"), self.length_stepper)
        body.AddRow(make_label("Cluster depth (cells, Y):"), self.depth_stepper)
        body.AddRow(None)
        body.AddRow(make_label("CASCADE", bold=True, size=10, color=ETO_TXT_PRIM, impact=True))
        body.AddRow(make_label("Peak floors (high corner):"), self.peak_stepper)
        body.AddRow(make_label("Base floors (low corner):"), self.base_stepper)
        body.AddRow(make_label("Peak corner:"), self.corner_dd)
        body.AddRow(make_label("Cascade sharpness:"), self.sharpness_dd)
        body.AddRow(None)
        body.AddRow(make_label("COURTYARD", bold=True, size=10, color=ETO_TXT_PRIM, impact=True))
        body.AddRow(make_label("Size:"), self.courtyard_dd)
        body.AddRow(make_label("Ring type:"), self.ring_dd)
        body.AddRow(None)
        body.AddRow(make_label("LIVE PREVIEW", bold=True, size=10, color=ETO_TXT_HILT, impact=True))
        body.AddRow(self.status_label)
        
        btn_layout = forms.DynamicLayout()
        btn_layout.Padding = drawing.Padding(20, 6, 20, 18)
        btn_layout.Spacing = drawing.Size(10, 0)
        btn_layout.AddRow(None, self.abort_btn, self.confirm_btn)
        
        accent_bot = forms.Panel()
        try:
            accent_bot.BackgroundColor = ETO_ACCENT
        except:
            pass
        accent_bot.Size = drawing.Size(460, 4)
        
        root = forms.StackLayout()
        root.Orientation = forms.Orientation.Vertical
        root.HorizontalContentAlignment = forms.HorizontalAlignment.Stretch
        root.Spacing = 0
        root.Items.Add(title_panel)
        root.Items.Add(accent_top)
        root.Items.Add(body)
        root.Items.Add(accent_bot)
        root.Items.Add(btn_layout)
        
        self.Content = root
        self.refresh_status()
    
    def _make_stepper(self, mn, mx, val):
        s = forms.NumericStepper()
        s.MinValue = mn
        s.MaxValue = mx
        s.Value = val
        s.Increment = 1
        s.DecimalPlaces = 0
        s.Width = 90
        try:
            s.BackgroundColor = ETO_BG_INPUT
        except:
            pass
        return s
    
    def _make_dropdown(self, items, default_idx):
        dd = forms.DropDown()
        for item in items:
            dd.Items.Add(item)
        dd.SelectedIndex = default_idx
        dd.Width = 220
        try:
            dd.BackgroundColor = ETO_BG_INPUT
        except:
            pass
        return dd
    
    def get_corner(self):
        return ["NE", "NW", "SE", "SW"][self.corner_dd.SelectedIndex]
    
    def get_courtyard(self):
        return ["small", "medium", "large"][self.courtyard_dd.SelectedIndex]
    
    def get_sharpness(self):
        return [1, 2, 3][self.sharpness_dd.SelectedIndex]
    
    def get_ring_type(self):
        return ["closed", "open"][self.ring_dd.SelectedIndex]
    
    def on_change(self, sender, e):
        self.refresh_status()
    
    def refresh_status(self):
        try:
            NX = int(self.length_stepper.Value)
            NY = int(self.depth_stepper.Value)
            peak = int(self.peak_stepper.Value)
            base = int(self.base_stepper.Value)
            corner = self.get_corner()
            courtyard = self.get_courtyard()
            sharpness = self.get_sharpness()
            ring = self.get_ring_type()
            
            peak_H = peak * 3.75
            base_H = base * 3.75
            hochhaus = "YES" if peak_H > 22 else "no"
            
            cluster_W = NX * 3.75
            cluster_D = NY * 3.75
            
            max_dist = (NX - 1) + (NY - 1)
            avg_drop = max_dist / (2.0 * sharpness)
            avg_floors = peak - avg_drop
            if avg_floors < base:
                avg_floors = base
            est_perimeter_cells = (2 * NX + 2 * NY - 4)
            # Account for ring (1 cell thick)
            est_modules_per_floor = est_perimeter_cells
            est_total = int(avg_floors * est_modules_per_floor * 0.6)  # rough
            
            self.status_label.Text = (
                "Footprint: {0} x {1} cells = {2:.1f} x {3:.1f} m\n"
                "Heights: peak {4} fl ({5:.1f} m) / base {6} fl ({7:.1f} m)\n"
                "Hochhaus rules (>22 m): {8}\n"
                "Peak corner: {9}  |  Ring: {10}\n"
                "Cascade 1:{11}  |  Courtyard: {12}\n"
                "Setbacks: 6 m podium / {13:.1f} m at peak\n"
                "Estimated total units: ~{14}"
            ).format(NX, NY, cluster_W, cluster_D,
                     peak, peak_H, base, base_H, hochhaus,
                     corner, ring, sharpness, courtyard,
                     0.4 * peak_H, est_total)
        except Exception as ex:
            self.status_label.Text = "Status: " + str(ex)
    
    def on_confirm(self, sender, e):
        self.Close(True)
    
    def on_abort(self, sender, e):
        self.Close(False)


# =====================================================================
# MAIN
# =====================================================================
def main():
    dlg = WoSyHoV12Dialog()
    try:
        result = dlg.ShowModal(Rhino.UI.RhinoEtoApp.MainWindowForDocument(sc.doc))
    except:
        try:
            result = dlg.ShowModal(Rhino.UI.RhinoEtoApp.MainWindow)
        except:
            result = dlg.ShowModal()
    
    if not result:
        print("Cancelled.")
        return
    
    NX = int(dlg.length_stepper.Value)
    NY = int(dlg.depth_stepper.Value)
    peak = int(dlg.peak_stepper.Value)
    base = int(dlg.base_stepper.Value)
    corner = dlg.get_corner()
    courtyard = dlg.get_courtyard()
    sharpness = dlg.get_sharpness()
    ring_type = dlg.get_ring_type()
    
    print("=" * 60)
    print("Timber Housing v12 - Cascading Ring Tower")
    print("=" * 60)
    print("Cluster:       {0} x {1} cells ({2:.1f} x {3:.1f} m)".format(NX, NY, NX*3.75, NY*3.75))
    print("Peak floors:   {0} ({1:.2f} m)".format(peak, peak*3.75))
    print("Base floors:   {0} ({1:.2f} m)".format(base, base*3.75))
    print("Peak corner:   {0}".format(corner))
    print("Courtyard:     {0}".format(courtyard))
    print("Sharpness:     1:{0}".format(sharpness))
    print("Ring type:     {0}".format(ring_type))
    print("Hochhaus:      {0}".format("YES (>22 m)" if peak*3.75 > 22 else "no"))
    print("=" * 60)
    
    counts, cell_fc = generate_cluster(NX, NY, peak, base, corner,
                                        courtyard, sharpness, ring_type)
    
    total_habitable = counts["A"] + counts["A_single"] + counts["B"] + counts["C"]
    print("Placement summary:")
    print("  A horizontal (2-cell):  {0}".format(counts["A"]))
    print("  A single (1-cell):      {0}".format(counts["A_single"]))
    print("  B vertical maisonette:  {0}".format(counts["B"]))
    print("  C double maisonette:    {0}".format(counts["C"]))
    print("  Stair cores:            {0}".format(counts["CORE"]))
    print("  Corridor segments:      {0}".format(counts["CORRIDOR"]))
    print("  Roof terraces:          {0}".format(counts["TERRACE"]))
    print("  TOTAL habitable units:  {0}".format(total_habitable))
    print("=" * 60)
    
    sc.doc.Views.Redraw()
    return counts


if __name__ == "__main__":
    main()
