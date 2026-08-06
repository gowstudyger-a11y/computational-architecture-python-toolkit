import rhinoscriptsyntax as rs
import scriptcontext as sc
import Rhino
import Rhino.Geometry as rg
import Rhino.UI
import time
import pprint
import math
import System
import Eto
import Eto.Forms as forms
import Eto.Drawing as drawing
# ============================================================ BUILDING DATA STRUCTURE ============================================================
def initialize_building_data():
    Building = {
        "name": "Parametric Building",
        "location": "TH-OWL",
        "plot": {
            "length": 0.0, "width": 0.0, "setback": 0.0,
            "boundary": None, "north_side": None, "north_direction": None,
        },
        "road": { "width": 15.0, "extension": 20.0, "boundary": None, },
        "floors": {
            "num_floors": 1, "num_upper_floors": 0, "floor_heights": [],
            "total_height": 0.0, "boundaries_per_floor": [], "boundary_points_per_floor": [],
        },
        "grid": {
            "spacing": 0.0, "foundation_points": [], "selected_column_points": [],
            "selected_points_per_floor": [], "selected_coords_per_floor": [],
        },
        "structure": {
            "columns": {
                "width": 0.0, "height": 0.0, "objects": [],
                "objects_per_floor": [], "top_points_per_floor": [],
            },
            "plinth_beams": {
                "width": 0.0, "depth": 0.0, "max_cantilever": 2.0,
                "extension_per_floor": [], "objects": [],
                "objects_per_floor": [], "intersection_points_per_floor": [],
            },
        },
        "geometry": {
            "plot_boundary": None, "foundation_grid": [], "floor_grids": [],
            "floor_boundaries": [], "boundary_point_objects": [],
        },
        "panels": {
            "panel_thickness": 0.15, "panels_per_floor": [], "panel_ids_per_floor": [],
            "panel_coords_per_floor": [], "deleted_panels_per_floor": [], "clipping_planes": [],
        },
        "wall_panels": {
            "wall_panel_ids_per_floor": [],
            "wall_panel_edges_per_floor": [],
            "deleted_wall_panels_per_floor": [],
            "parapet_height": 1.0,
            "wall_panel_info_per_floor": [],
        },
        "elevation": {
            "wall_extrusion_ids": [],
            "vertical_extrusion_ids": [],
        },
        "purlins": {
            # Secondary floor beams (Unterzüge/Deckenbalken) per floor
            # Generated per panel cell before floor panels are drawn.
            # Keys: count, ids_per_floor, section_name, n_per_cell, spacing
            "n_per_cell":    2,        # default, recalculated from gs
            "spacing":       0.0,      # m, bay spacing between purlins
            "section_width": 0.10,     # m
            "section_depth": 0.32,     # m
            "section_name":  "PURLIN", # updated during generation
            "ids_per_floor": [],       # Rhino object IDs per floor
        }
    }
    return Building
# ============================================================ UTILITY FUNCTIONS ============================================================
def clear_plot():
    layers_to_clear = [
        "Outer_Plot_Boundary", "Plot_Boundary", "Foundation_Grid", "Columns",
        "Plinth_Grid", "Plot_Grid", "Floor_Grid", "Floor_Boundary", "Boundary_Points",
        "Wooden_Beam", "Selection_Polyline", "North_Indicator", "Road", "Plot_Dimensions", "Roof_Grid",
        "Wall_Extrusions", "Vertical_Extrusions",
    ]
    layers_to_clear.append("Wall_Panels_-1")  # basement skirt wall layer
    layers_to_clear.append("Glass_Panels")
    layers_to_clear.append("Window_Frames")
    layers_to_clear.append("Floor_Purlins")
    # FEM export layers (FEM_Purlins excluded - purlins sized by hand, not in global FEM)
    layers_to_clear.extend([
        "FEM_Columns", "FEM_Beams",
        "FEM_Floor_Surfaces", "FEM_Roof_Surfaces",
        "FEM_Wall_Surfaces", "FEM_Supports", "FEM_Labels",
    ])
    for i in range(20):
        layers_to_clear.append("Floor_Panels_{}".format(i))
        layers_to_clear.append("Clipping_Plane_{}".format(i))
        layers_to_clear.append("Wall_Panels_{}".format(i))
    for layer_name in layers_to_clear:
        if rs.IsLayer(layer_name):
            objs = rs.ObjectsByLayer(layer_name)
            if objs:
                rs.DeleteObjects(objs)
            rs.DeleteLayer(layer_name)


def cleanup_all_temporary_geometry():
    layers_to_cleanup = ["Boundary_Points", "Floor_Boundary", "Selection_Polyline"]
    for layer_name in layers_to_cleanup:
        if rs.IsLayer(layer_name):
            objs = rs.ObjectsByLayer(layer_name)
            if objs:
                rs.DeleteObjects(objs)
    print("  Cleaned up temporary points and lines for clear selection.")


def print_section_header(title):
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)


def print_section_footer():
    print("=" * 60 + "\n")


def make_color(r, g, b):
    # Use Eto's float Color constructor (0.0–1.0) to bypass FromArgb byte-order
    # issues observed on certain Rhino/Eto/WPF builds.
    return drawing.Color(float(r) / 255.0, float(g) / 255.0, float(b) / 255.0, 1.0)

# --- UI helper (Eto-safe) ----------------------------------------------------
# Some Rhino/Eto builds differ in which color properties controls expose.
# This helper sets Background/Text color defensively and is used across dialogs.
def try_set_control_colors(ctrl, bg_rgb=None, text_rgb=None):
    """Best-effort set of background/text colors across Eto controls (safe guards)."""
    if ctrl is None:
        return
    if bg_rgb is not None:
        try:
            ctrl.BackgroundColor = make_color(bg_rgb[0], bg_rgb[1], bg_rgb[2])
        except:
            try:
                ctrl.Background = drawing.SolidBrush(make_color(bg_rgb[0], bg_rgb[1], bg_rgb[2]))
            except:
                pass
    if text_rgb is not None:
        col = make_color(text_rgb[0], text_rgb[1], text_rgb[2])
        try:
            ctrl.TextColor = col
        except:
            pass
        try:
            ctrl.ForegroundColor = col
        except:
            pass
        # Some list-like controls use ItemTextColor in certain Eto builds
        try:
            ctrl.ItemTextColor = col
        except:
            pass



def darken_color(rgb, factor=0.22):
    """Return a much darker version of an (r,g,b) tuple.

    NOTE:
    - factor is still in (0,1) like before, but we apply a stronger curve so dialog surfaces
      can go *very* dark while keeping a subtle hue (more contrast with text).
    - This keeps existing call-sites unchanged (they typically pass 0.22).
    """
    f = max(0.0, min(1.0, float(factor)))
    # Stronger darkening curve (architectural / high-contrast)
    f = f * f
    # Tiny lift so panels don't collapse into pure black and still read as a "surface"
    lift = 4
    return (max(0, min(255, int(rgb[0] * f) + lift)),
            max(0, min(255, int(rgb[1] * f) + lift)),
            max(0, min(255, int(rgb[2] * f) + lift)))



def soften_color(rgb, lift=35):
    """Slightly lift a dark color for borders/separators."""
    return (max(0, min(255, int(rgb[0] + lift))),
            max(0, min(255, int(rgb[1] + lift))),
            max(0, min(255, int(rgb[2] + lift))))


# ============================================================ DIALOG / UI PALETTE — STRICT 3-COLOR SYSTEM ============================================================
# RULE: Dialogs now follow the third reference image only.
#   1. PAPER WHITE / LIGHT GREY — dialog backgrounds and panel surfaces
#   2. COBALT BLUE              — titles, labels, linework, icon strokes
#   3. ELECTRIC BLUE            — accents, confirm actions, selection highlights
#
# Reference: supplied cultural block drawing (white field + blue architectural linework)

# --- The three master colours ---
# Dark blood-red palette.  make_color() uses Eto's float Color constructor
# (bypasses FromArgb byte-order issues).  Values are plain human-readable RGB.
# Names are preserved so nothing else in the codebase changes.
BH_BLACK        = (245, 245, 245)   # clean white background
BH_BLACK_LIFT   = (210, 210, 210)   # obvious cool grey for inputs / list areas / info cards
BH_DARK_GREY    = (192, 192, 192)   # neutral grey for header panels & raised surfaces
BH_MID_GREY     = (165, 165, 165)   # neutral grey dividers / subtle borders
BH_WHITE        = (128,   0,   2)   # dark blood-red — primary text
BH_OFF_WHITE    = (100,   0,   4)   # darker blood-red — secondary text
BH_RED          = (140,   0,   0)   # vivid blood-red — accents / separators / CONFIRM btn
BH_RED_DARK     = ( 72,   0,   0)   # deep maroon — ABORT / cancel buttons
BH_ORANGE       = (165,   8,   2)   # bright blood-red — highlights
BH_AMBER        = (175,  20,  15)   # warm scarlet — subtitles / badges
BH_PURE_WHITE   = (255, 255, 255)   # actual white — for text on dark buttons/backgrounds

# --- Dialog palette aliases — ALL map to the three master colours ---
DIALOG_TEXT_PRIMARY   = BH_WHITE       # white
DIALOG_TEXT_SECONDARY = BH_WHITE       # white
DIALOG_TEXT_MUTED     = BH_WHITE       # white (no grey text)

DIALOG_SURFACE_DEEP   = BH_BLACK       # black
DIALOG_SURFACE_INPUT  = BH_BLACK_LIFT  # near-black
DIALOG_SURFACE_RAISED = BH_DARK_GREY   # slightly lifted black

DIALOG_ACCENT_BLUE    = BH_RED         # dark red — no blue
DIALOG_ACCENT_PINK    = BH_RED         # dark red — no pink
DIALOG_ACCENT_YELLOW  = BH_RED         # dark red — no yellow
DIALOG_ACCENT_GREEN   = BH_RED         # dark red — no green
DIALOG_ACCENT_ORANGE  = BH_RED         # dark red — no orange

DIALOG_CANCEL_BG      = BH_RED_DARK    # darker red — abort button
DIALOG_CANCEL_TEXT    = BH_PURE_WHITE  # white text on dark buttons

DIALOG_OUTLINE        = BH_RED         # dark red

# Body text — always white
_BODY_TEXT_DARK     = BH_WHITE
_BODY_TEXT_MED      = BH_WHITE
_BODY_TEXT_RADIO    = BH_WHITE
_BODY_SEL_COLOR     = BH_RED           # dark red for "Selected:" highlight
_BODY_STAT_COLOR    = BH_WHITE

def dialog_accent_rgb(header_color_rgb=None):
    """Always returns dark red — the only permitted accent colour."""
    return BH_RED

def dialog_header_bg_rgb():
    """Header: darker red header band matching the reference."""
    return BH_DARK_GREY

def dialog_body_bg_rgb():
    """Body: rich warm red body surface matching the reference."""
    return BH_BLACK
def try_set_control_colors(ctrl, bg_rgb=None, text_rgb=None):
    """Best-effort set of background/text colors across Eto controls (safe guards)."""
    if bg_rgb is not None:
        try:
            ctrl.BackgroundColor = make_color(bg_rgb[0], bg_rgb[1], bg_rgb[2])
        except:
            pass
    if text_rgb is not None:
        # Some controls expose TextColor, some ForegroundColor; we attempt both.
        try:
            ctrl.TextColor = make_color(text_rgb[0], text_rgb[1], text_rgb[2])
        except:
            try:
                ctrl.ForegroundColor = make_color(text_rgb[0], text_rgb[1], text_rgb[2])
            except:
                pass



# ============================================================ ARCHITECTURAL DIALOG ICONS (VECTOR) ============================================================
# Bauhaus geometric volumes — flat, bold, minimal
# Palette: red, dark red, white, near-black, grey, amber

ICON_RED_PRIMARY   = BH_RED          # dark red — primary icon fill
ICON_RED_DARK      = BH_RED_DARK     # darker red — shadow / side face
ICON_RED_LIGHT     = BH_WHITE        # white — highlight / top face
ICON_INK_DARK      = BH_BLACK        # black — ink base
ICON_INK_LIGHT     = BH_WHITE        # white — light ink
ICON_MUTED         = (165, 165, 165)  # neutral grey muted elements

def _icon_pen(rgb, width=2):
    return drawing.Pen(make_color(rgb[0], rgb[1], rgb[2]), width)

def _icon_brush(rgb, alpha=255):
    return drawing.SolidBrush(drawing.Color(float(rgb[0]) / 255.0, float(rgb[1]) / 255.0, float(rgb[2]) / 255.0, float(alpha) / 255.0))

def _gp_add_polygon(gp, pts):
    """Add a closed polygon to an Eto.Drawing.GraphicsPath in a Rhino-safe way.

    Eto's GraphicsPath API differs across Rhino/Eto versions (some builds do NOT expose AddPolygon).
    We therefore try several methods to ensure compatibility.
    """
    if pts is None:
        return
    # Normalize to a list
    pts_list = list(pts)
    if len(pts_list) < 2:
        return
    # Preferred (if available)
    try:
        gp.AddPolygon(pts_list)
        return
    except Exception:
        pass
    # Fallback: AddLines (close explicitly)
    try:
        closed = list(pts_list)
        if closed[0] != closed[-1]:
            closed.append(closed[0])
        gp.AddLines(closed)
        try:
            gp.CloseFigure()
        except Exception:
            pass
        return
    except Exception:
        pass
    # Fallback: add as individual line segments
    try:
        for i in range(len(pts_list)):
            a = pts_list[i]
            b = pts_list[(i + 1) % len(pts_list)]
            gp.AddLine(a, b)
        try:
            gp.CloseFigure()
        except Exception:
            pass
    except Exception:
        # If everything fails, we do nothing (better than crashing)
        return


def _draw_human(g, x, y, s=1.0, color_rgb=ICON_INK_LIGHT):
    # Sci-fi node: connected dots (like the blob/node reference image)
    # Central node
    r = 2.5 * s
    g.FillEllipse(_icon_brush(color_rgb), x - r, y - r, r * 2, r * 2)
    # Two arm nodes
    arm_r = 1.5 * s
    offset = 5.0 * s
    g.FillEllipse(_icon_brush(color_rgb, 180), x - offset - arm_r, y - arm_r, arm_r * 2, arm_r * 2)
    g.FillEllipse(_icon_brush(color_rgb, 180), x + offset - arm_r, y - arm_r, arm_r * 2, arm_r * 2)
    # Connecting lines
    g.DrawLine(_icon_pen(color_rgb, 1), x - r, y, x - offset, y)
    g.DrawLine(_icon_pen(color_rgb, 1), x + r, y, x + offset, y)
    # Bottom node
    g.FillEllipse(_icon_brush(color_rgb, 180), x - arm_r, y + offset - arm_r, arm_r * 2, arm_r * 2)
    g.DrawLine(_icon_pen(color_rgb, 1), x, y + r, x, y + offset)

def _draw_ground(g, size):
    # Bauhaus flat grid base — black field, grey grid lines
    pad = 3
    r = drawing.RectangleF(pad, pad, size - pad * 2, size - pad * 2)
    g.FillRectangle(_icon_brush(ICON_INK_DARK, 255), r)
    # Minimal grid lines (grey on black)
    grid_pen = _icon_pen(BH_MID_GREY, 1)
    for i in range(8, size - 4, 8):
        g.DrawLine(grid_pen, pad, i, size - pad, i)
        g.DrawLine(grid_pen, i, pad, i, size - pad)
    g.DrawRectangle(_icon_pen(BH_WHITE, 1), r)

def _draw_isometric_block(g, x, y, w, h, depth, face_rgb=None, side_rgb=None, top_rgb=None):
    # Bauhaus poster style: bold flat faces, thick black outlines, no gradients
    face_rgb = face_rgb or BH_RED
    side_rgb = side_rgb or BH_RED_DARK
    top_rgb  = top_rgb  or BH_WHITE
    # Front face — solid fill
    g.FillRectangle(_icon_brush(face_rgb), x, y, w, h)
    # Side face (right)
    side = drawing.GraphicsPath()
    _gp_add_polygon(side, [
        drawing.PointF(x + w, y),
        drawing.PointF(x + w + depth, y - depth * 0.6),
        drawing.PointF(x + w + depth, y + h - depth * 0.6),
        drawing.PointF(x + w, y + h),
    ])
    g.FillPath(_icon_brush(side_rgb), side)
    # Top face
    top = drawing.GraphicsPath()
    _gp_add_polygon(top, [
        drawing.PointF(x, y),
        drawing.PointF(x + depth, y - depth * 0.6),
        drawing.PointF(x + w + depth, y - depth * 0.6),
        drawing.PointF(x + w, y),
    ])
    g.FillPath(_icon_brush(top_rgb), top)
    # Bold black outline — poster style
    ink = _icon_pen(BH_BLACK, 2)
    g.DrawRectangle(ink, drawing.RectangleF(x, y, w, h))

def _draw_crane(g, x, y, size):
    # Bauhaus crane: thick black lines on black bg → use white/red
    g.DrawLine(_icon_pen(BH_WHITE, 3), x, y, x, y + size)
    g.DrawLine(_icon_pen(BH_WHITE, 3), x, y, x + size * 0.75, y)
    g.DrawLine(_icon_pen(BH_RED, 2), x + size * 0.75, y, x + size * 0.75, y + size * 0.35)
    g.FillRectangle(_icon_brush(BH_ORANGE), x - 3, y + size - 5, 6, 5)

def _icon_variant_building(size=48):
    """Stepped terrace icon: cascading floors G-1-2-3 with h(m) and H(m) dimensions."""
    bmp = drawing.Bitmap(size, size, drawing.PixelFormat.Format32bppRgba)
    g = drawing.Graphics(bmp)
    try:
        g.AntiAlias = True
        g.FillRectangle(_icon_brush(BH_BLACK), 0, 0, size, size)
        s = size / 48.0
        pen_main = _icon_pen(BH_WHITE, 1.5)
        pen_thin = _icon_pen(BH_WHITE, 0.8)
        pen_dim = _icon_pen(BH_ORANGE, 0.7)
        pen_dim_tick = _icon_pen(BH_ORANGE, 0.5)
        pen_dash = drawing.Pen(make_color(*BH_WHITE), 0.4)
        try:
            pen_dash.DashStyle = drawing.DashStyle.Dash
        except:
            pass
        # Basement (dashed)
        g.DrawRectangle(drawing.Pen(make_color(*BH_WHITE), 0.8), drawing.RectangleF(6*s, 40*s, 32*s, 4*s))
        # Ground floor (widest)
        g.FillRectangle(_icon_brush(BH_RED, 20), drawing.RectangleF(6*s, 32*s, 32*s, 8*s))
        g.DrawRectangle(pen_main, drawing.RectangleF(6*s, 32*s, 32*s, 8*s))
        # Floor 1
        g.FillRectangle(_icon_brush(BH_RED, 30), drawing.RectangleF(6*s, 24*s, 26*s, 8*s))
        g.DrawRectangle(pen_main, drawing.RectangleF(6*s, 24*s, 26*s, 8*s))
        # Floor 2
        g.FillRectangle(_icon_brush(BH_RED, 40), drawing.RectangleF(6*s, 16*s, 20*s, 8*s))
        g.DrawRectangle(pen_main, drawing.RectangleF(6*s, 16*s, 20*s, 8*s))
        # Floor 3 / top
        g.FillRectangle(_icon_brush(BH_RED, 50), drawing.RectangleF(6*s, 8*s, 14*s, 8*s))
        g.DrawRectangle(pen_main, drawing.RectangleF(6*s, 8*s, 14*s, 8*s))
        # Roof cap line
        g.DrawLine(_icon_pen(BH_WHITE, 2), int(6*s), int(8*s), int(20*s), int(8*s))
        # Floor labels
        lbl_font = drawing.Font(drawing.FontFamily("Arial"), 4, drawing.FontStyle.Bold)
        g.DrawText(lbl_font, make_color(*BH_WHITE), int(18*s), int(35*s), "G")
        g.DrawText(lbl_font, make_color(*BH_WHITE), int(16*s), int(27*s), "1")
        g.DrawText(lbl_font, make_color(*BH_WHITE), int(13*s), int(19*s), "2")
        g.DrawText(lbl_font, make_color(*BH_WHITE), int(10*s), int(11*s), "3")
        # Ground line + hatch
        g.DrawLine(_icon_pen(BH_WHITE, 1), int(4*s), int(45*s), int(40*s), int(45*s))
        for hx in range(5, 38, 3):
            g.DrawLine(_icon_pen(BH_WHITE, 0.3), int((hx+2)*s), int(47*s), int(hx*s), int(45*s))
        # Storey height dimension (left) — split with h (m)
        g.DrawLine(pen_dim, int(3*s), int(24*s), int(3*s), int(29*s))
        g.DrawLine(pen_dim, int(3*s), int(35*s), int(3*s), int(40*s))
        g.DrawLine(pen_dim_tick, int(2*s), int(24*s), int(4*s), int(24*s))
        g.DrawLine(pen_dim_tick, int(2*s), int(40*s), int(4*s), int(40*s))
        h_top = drawing.GraphicsPath()
        _gp_add_polygon(h_top, [drawing.PointF(3*s, 24*s), drawing.PointF(2*s, 26*s), drawing.PointF(4*s, 26*s)])
        g.FillPath(_icon_brush(BH_ORANGE), h_top)
        h_bot = drawing.GraphicsPath()
        _gp_add_polygon(h_bot, [drawing.PointF(3*s, 40*s), drawing.PointF(2*s, 38*s), drawing.PointF(4*s, 38*s)])
        g.FillPath(_icon_brush(BH_ORANGE), h_bot)
        lbl_sm = drawing.Font(drawing.FontFamily("Arial"), 3, drawing.FontStyle.Bold)
        g.DrawText(lbl_sm, make_color(*BH_ORANGE), int(1*s), int(30*s), "h")
        lbl_xs = drawing.Font(drawing.FontFamily("Arial"), 2.5, drawing.FontStyle.Italic)
        g.DrawText(lbl_xs, make_color(*BH_ORANGE), int(0*s), int(33*s), "(m)")
        # Total height dimension (right) — split with H (m)
        g.DrawLine(pen_dim, int(40*s), int(8*s), int(40*s), int(22*s))
        g.DrawLine(pen_dim, int(40*s), int(30*s), int(40*s), int(44*s))
        g.DrawLine(pen_dim_tick, int(39*s), int(8*s), int(41*s), int(8*s))
        g.DrawLine(pen_dim_tick, int(39*s), int(44*s), int(41*s), int(44*s))
        t_top = drawing.GraphicsPath()
        _gp_add_polygon(t_top, [drawing.PointF(40*s, 8*s), drawing.PointF(39*s, 10*s), drawing.PointF(41*s, 10*s)])
        g.FillPath(_icon_brush(BH_ORANGE), t_top)
        t_bot = drawing.GraphicsPath()
        _gp_add_polygon(t_bot, [drawing.PointF(40*s, 44*s), drawing.PointF(39*s, 42*s), drawing.PointF(41*s, 42*s)])
        g.FillPath(_icon_brush(BH_ORANGE), t_bot)
        g.DrawText(lbl_sm, make_color(*BH_ORANGE), int(42*s), int(24*s), "H")
        g.DrawText(lbl_xs, make_color(*BH_ORANGE), int(42*s), int(27*s), "(m)")
        # Terrace step dashed lines
        g.DrawLine(pen_dash, int(32*s), int(26*s), int(38*s), int(26*s))
        g.DrawLine(pen_dash, int(26*s), int(18*s), int(38*s), int(18*s))
        g.DrawLine(pen_dash, int(20*s), int(10*s), int(38*s), int(10*s))
    finally:
        g.Dispose()
    return bmp

def _icon_variant_grid(size=48):
    """Multi-storey timber frame icon: 3 columns, 3 beams, wood grain, dimensions, pin supports."""
    bmp = drawing.Bitmap(size, size, drawing.PixelFormat.Format32bppRgba)
    g = drawing.Graphics(bmp)
    try:
        g.AntiAlias = True
        g.FillRectangle(_icon_brush(BH_BLACK), 0, 0, size, size)
        pen_main = _icon_pen(BH_WHITE, 1.5)
        pen_thin = _icon_pen(BH_WHITE, 0.8)
        pen_grain = _icon_pen(BH_WHITE, 0.4)
        s = size / 48.0  # scale factor
        # 3 columns
        for cx in [9, 22, 35]:
            x = cx * s
            g.DrawRectangle(_icon_pen(BH_WHITE, 1.2), drawing.RectangleF(x, 6*s, 5*s, 34*s))
        # 3 beams
        for by in [6, 16, 26]:
            y = by * s
            g.FillRectangle(_icon_brush(BH_RED, 30), drawing.RectangleF(9*s, y, 31*s, 3*s))
            g.DrawRectangle(_icon_pen(BH_WHITE, 1.2), drawing.RectangleF(9*s, y, 31*s, 3*s))
        # Wood grain in columns (vertical wavy)
        for cx in [11, 24, 37]:
            x = cx * s
            g.DrawLine(pen_grain, x, 8*s, x, 38*s)
        # Ground line
        g.DrawLine(_icon_pen(BH_WHITE, 1.2), 4*s, 42*s, 44*s, 42*s)
        # Ground hatch
        for hx in range(6, 42, 4):
            g.DrawLine(_icon_pen(BH_WHITE, 0.4), (hx+2)*s, 44*s, hx*s, 42*s)
        # Pin supports (triangles)
        for cx in [9, 22, 35]:
            x = (cx + 2.5) * s
            tri = drawing.GraphicsPath()
            _gp_add_polygon(tri, [
                drawing.PointF(x, 42*s),
                drawing.PointF(x - 3*s, 46*s),
                drawing.PointF(x + 3*s, 46*s)])
            g.DrawPath(_icon_pen(BH_WHITE, 0.8), tri)
        # Bay span dimension (top)
        g.DrawLine(pen_thin, 14*s, 3*s, 22*s, 3*s)
        g.DrawLine(pen_thin, 14*s, 2*s, 14*s, 4*s)
        g.DrawLine(pen_thin, 22*s, 2*s, 22*s, 4*s)
        # Height dimension (right)
        g.DrawLine(pen_thin, 42*s, 6*s, 42*s, 40*s)
        g.DrawLine(pen_thin, 41*s, 6*s, 43*s, 6*s)
        g.DrawLine(pen_thin, 41*s, 40*s, 43*s, 40*s)
    finally:
        g.Dispose()
    return bmp

def _icon_variant_panels(size=48):
    """Floor panels icon: 3D isometric slab with dense grid, column dots, dimensions."""
    bmp = drawing.Bitmap(size, size, drawing.PixelFormat.Format32bppRgba)
    g = drawing.Graphics(bmp)
    try:
        g.AntiAlias = True
        g.FillRectangle(_icon_brush(BH_BLACK), 0, 0, size, size)
        s = size / 48.0
        pen = _icon_pen(BH_WHITE, 1.5)
        pen_grid = _icon_pen(BH_WHITE, 0.4)
        pen_dim = _icon_pen(BH_ORANGE, 0.6)
        # Slab top face (isometric diamond)
        slab_top = drawing.GraphicsPath()
        _gp_add_polygon(slab_top, [
            drawing.PointF(24*s, 8*s), drawing.PointF(44*s, 20*s),
            drawing.PointF(24*s, 32*s), drawing.PointF(4*s, 20*s)])
        g.FillPath(_icon_brush(BH_RED, 20), slab_top)
        g.DrawPath(pen, slab_top)
        # Slab thickness (left side)
        side_l = drawing.GraphicsPath()
        _gp_add_polygon(side_l, [
            drawing.PointF(4*s, 20*s), drawing.PointF(4*s, 24*s),
            drawing.PointF(24*s, 36*s), drawing.PointF(24*s, 32*s)])
        g.FillPath(_icon_brush(BH_RED, 10), side_l)
        g.DrawPath(_icon_pen(BH_WHITE, 0.8), side_l)
        # Slab thickness (right side)
        side_r = drawing.GraphicsPath()
        _gp_add_polygon(side_r, [
            drawing.PointF(24*s, 32*s), drawing.PointF(24*s, 36*s),
            drawing.PointF(44*s, 24*s), drawing.PointF(44*s, 20*s)])
        g.FillPath(_icon_brush(BH_RED, 8), side_r)
        g.DrawPath(_icon_pen(BH_WHITE, 0.8), side_r)
        # Dense grid lines on top face (left-right diagonals)
        for i in range(1, 5):
            x1 = (4 + i*5) * s; y1 = (20 - i*3) * s
            x2 = (4 + i*5 + 20) * s; y2 = (20 - i*3 + 12) * s
            g.DrawLine(pen_grid, x1, y1, x2, y2)
        # Dense grid lines (right-left diagonals)
        for i in range(1, 5):
            x1 = (4 + i*5) * s; y1 = (20 + i*3) * s
            x2 = (4 + i*5 + 20) * s; y2 = (20 + i*3 - 12) * s
            g.DrawLine(pen_grid, x1, y1, x2, y2)
        # Column dots at intersections
        for pt in [(14,14),(24,20),(34,14),(14,26),(24,20),(34,26),(19,17),(29,17),(19,23),(29,23)]:
            g.FillEllipse(_icon_brush(BH_WHITE), int(pt[0]*s)-1, int(pt[1]*s)-1, 3, 3)
        # Span dimension (bottom)
        g.DrawLine(pen_dim, int(4*s), int(38*s), int(14*s), int(38*s))
        g.DrawLine(pen_dim, int(30*s), int(38*s), int(44*s), int(38*s))
        g.DrawLine(pen_dim, int(4*s), int(37*s), int(4*s), int(39*s))
        g.DrawLine(pen_dim, int(44*s), int(37*s), int(44*s), int(39*s))
        lbl = drawing.Font(drawing.FontFamily("Arial"), 3, drawing.FontStyle.Bold)
        g.DrawText(lbl, make_color(*BH_ORANGE), int(15*s), int(36*s), "(m)")
        # Thickness dimension (right)
        g.DrawLine(pen_dim, int(46*s), int(20*s), int(46*s), int(24*s))
        g.DrawLine(pen_dim, int(45*s), int(20*s), int(47*s), int(20*s))
        g.DrawLine(pen_dim, int(45*s), int(24*s), int(47*s), int(24*s))
    finally:
        g.Dispose()
    return bmp

def _icon_variant_walls(size=48):
    """Wall panels icon: cascading stepped floors G-1-2-3 with vertical panel divisions and dimensions."""
    bmp = drawing.Bitmap(size, size, drawing.PixelFormat.Format32bppRgba)
    g = drawing.Graphics(bmp)
    try:
        g.AntiAlias = True
        g.FillRectangle(_icon_brush(BH_BLACK), 0, 0, size, size)
        s = size / 48.0
        pen = _icon_pen(BH_WHITE, 1.2)
        pen_div = _icon_pen(BH_WHITE, 0.5)
        pen_dim = _icon_pen(BH_ORANGE, 0.6)
        lbl = drawing.Font(drawing.FontFamily("Arial"), 3, drawing.FontStyle.Bold)
        # Ground floor wall (widest) — 5 panels
        g.FillRectangle(_icon_brush(BH_RED, 20), drawing.RectangleF(4*s, 34*s, 34*s, 8*s))
        g.DrawRectangle(pen, drawing.RectangleF(4*s, 34*s, 34*s, 8*s))
        for vx in [11, 18, 25, 31]:
            g.DrawLine(pen_div, int(vx*s), int(34*s), int(vx*s), int(42*s))
        # Floor 1 (narrower) — 4 panels, lines align
        g.FillRectangle(_icon_brush(BH_RED, 28), drawing.RectangleF(4*s, 25*s, 27*s, 8*s))
        g.DrawRectangle(pen, drawing.RectangleF(4*s, 25*s, 27*s, 8*s))
        for vx in [11, 18, 25]:
            g.DrawLine(pen_div, int(vx*s), int(25*s), int(vx*s), int(33*s))
        # Floor 2 — 3 panels
        g.FillRectangle(_icon_brush(BH_RED, 36), drawing.RectangleF(4*s, 16*s, 20*s, 8*s))
        g.DrawRectangle(pen, drawing.RectangleF(4*s, 16*s, 20*s, 8*s))
        for vx in [11, 18]:
            g.DrawLine(pen_div, int(vx*s), int(16*s), int(vx*s), int(24*s))
        # Floor 3 (narrowest) — 2 panels
        g.FillRectangle(_icon_brush(BH_RED, 44), drawing.RectangleF(4*s, 8*s, 13*s, 7*s))
        g.DrawRectangle(pen, drawing.RectangleF(4*s, 8*s, 13*s, 7*s))
        g.DrawLine(pen_div, int(11*s), int(8*s), int(11*s), int(15*s))
        # Floor labels
        g.DrawText(lbl, make_color(*BH_WHITE), int(39*s), int(36*s), "G")
        g.DrawText(lbl, make_color(*BH_WHITE), int(32*s), int(27*s), "1")
        g.DrawText(lbl, make_color(*BH_WHITE), int(25*s), int(18*s), "2")
        g.DrawText(lbl, make_color(*BH_WHITE), int(18*s), int(9*s), "3")
        # Height dimension (right) — split with h (m)
        g.DrawLine(pen_dim, int(42*s), int(8*s), int(42*s), int(18*s))
        g.DrawLine(pen_dim, int(42*s), int(28*s), int(42*s), int(42*s))
        g.DrawLine(pen_dim, int(41*s), int(8*s), int(43*s), int(8*s))
        g.DrawLine(pen_dim, int(41*s), int(42*s), int(43*s), int(42*s))
        h_top = drawing.GraphicsPath()
        _gp_add_polygon(h_top, [drawing.PointF(42*s,8*s), drawing.PointF(41*s,10*s), drawing.PointF(43*s,10*s)])
        g.FillPath(_icon_brush(BH_ORANGE), h_top)
        h_bot = drawing.GraphicsPath()
        _gp_add_polygon(h_bot, [drawing.PointF(42*s,42*s), drawing.PointF(41*s,40*s), drawing.PointF(43*s,40*s)])
        g.FillPath(_icon_brush(BH_ORANGE), h_bot)
        lbl_sm = drawing.Font(drawing.FontFamily("Arial"), 2.5, drawing.FontStyle.Bold)
        g.DrawText(lbl_sm, make_color(*BH_ORANGE), int(44*s), int(21*s), "h")
        g.DrawText(lbl_sm, make_color(*BH_ORANGE), int(43*s), int(24*s), "(m)")
        # Ground line + hatch
        g.DrawLine(_icon_pen(BH_WHITE, 1), int(2*s), int(44*s), int(44*s), int(44*s))
        for hx in range(3, 42, 3):
            g.DrawLine(_icon_pen(BH_WHITE, 0.3), int((hx+2)*s), int(46*s), int(hx*s), int(44*s))
    finally:
        g.Dispose()
    return bmp

def _icon_variant_wall_extrude(size=48):
    """Wall extrusion section: 4 floors, extrusion outward on floors 1 & 3 only, half depth, ground hatch."""
    bmp = drawing.Bitmap(size, size, drawing.PixelFormat.Format32bppRgba)
    g = drawing.Graphics(bmp)
    try:
        g.AntiAlias = True
        g.FillRectangle(_icon_brush(BH_BLACK), 0, 0, size, size)
        s = size / 48.0
        pen = _icon_pen(BH_WHITE, 1.5)
        pen_thin = _icon_pen(BH_WHITE, 0.8)
        pen_dim = _icon_pen(BH_ORANGE, 0.5)
        lbl = drawing.Font(drawing.FontFamily("Arial"), 3, drawing.FontStyle.Bold)
        lbl_sm = drawing.Font(drawing.FontFamily("Arial"), 2.5, drawing.FontStyle.Italic)
        # Wall spine (centre)
        g.FillRectangle(_icon_brush(BH_RED, 25), drawing.RectangleF(20*s, 6*s, 3*s, 32*s))
        g.DrawRectangle(_icon_pen(BH_WHITE, 1), drawing.RectangleF(20*s, 6*s, 3*s, 32*s))
        # Floor slabs — interior only (left of wall)
        for fy in [38, 30, 22, 14, 6]:
            g.DrawLine(pen, int(6*s), int(fy*s), int(20*s), int(fy*s))
        # Floor 1: extrude outward (half depth)
        g.FillRectangle(_icon_brush(BH_RED, 40), drawing.RectangleF(23*s, 22*s, 6*s, 8*s))
        g.DrawRectangle(_icon_pen(BH_WHITE, 1), drawing.RectangleF(23*s, 22*s, 6*s, 8*s))
        # Floor 3: extrude outward (half depth)
        g.FillRectangle(_icon_brush(BH_RED, 40), drawing.RectangleF(23*s, 6*s, 6*s, 8*s))
        g.DrawRectangle(_icon_pen(BH_WHITE, 1), drawing.RectangleF(23*s, 6*s, 6*s, 8*s))
        # Outward arrows
        ar1 = drawing.GraphicsPath()
        _gp_add_polygon(ar1, [drawing.PointF(29*s,26*s), drawing.PointF(27*s,25*s), drawing.PointF(27*s,27*s)])
        g.FillPath(_icon_brush(BH_WHITE), ar1)
        g.DrawLine(pen_thin, int(24*s), int(26*s), int(28*s), int(26*s))
        ar2 = drawing.GraphicsPath()
        _gp_add_polygon(ar2, [drawing.PointF(29*s,10*s), drawing.PointF(27*s,9*s), drawing.PointF(27*s,11*s)])
        g.FillPath(_icon_brush(BH_WHITE), ar2)
        g.DrawLine(pen_thin, int(24*s), int(10*s), int(28*s), int(10*s))
        # Floor labels
        g.DrawText(lbl, make_color(*BH_WHITE), int(3*s), int(33*s), "G")
        g.DrawText(lbl, make_color(*BH_WHITE), int(3*s), int(25*s), "1")
        g.DrawText(lbl, make_color(*BH_WHITE), int(3*s), int(17*s), "2")
        g.DrawText(lbl, make_color(*BH_WHITE), int(3*s), int(9*s), "3")
        # Depth dimension (top)
        g.DrawLine(pen_dim, int(23*s), int(4*s), int(26*s), int(4*s))
        g.DrawLine(pen_dim, int(28*s), int(4*s), int(29*s), int(4*s))
        g.DrawLine(pen_dim, int(23*s), int(3*s), int(23*s), int(5*s))
        g.DrawLine(pen_dim, int(29*s), int(3*s), int(29*s), int(5*s))
        g.DrawText(lbl_sm, make_color(*BH_ORANGE), int(26*s), int(2*s), "(m)")
        # Ground line + hatch
        g.DrawLine(_icon_pen(BH_WHITE, 1.5), int(4*s), int(40*s), int(32*s), int(40*s))
        for hx in range(5, 30, 2):
            g.DrawLine(_icon_pen(BH_WHITE, 0.3), int((hx+1)*s), int(42*s), int(hx*s), int(40*s))
        # Soil hatch below ground (denser)
        for hx in range(5, 30, 3):
            g.DrawLine(_icon_pen(BH_WHITE, 0.2), int(hx*s), int(42*s), int(hx*s), int(46*s))
            g.DrawLine(_icon_pen(BH_WHITE, 0.2), int((hx+1)*s), int(43*s), int((hx+2)*s), int(43*s))
    finally:
        g.Dispose()
    return bmp

def _icon_variant_vertical_extrude(size=48):
    """Vertical extrusion: single floor isometric grid, 3 boxes extruded upward 4m with passage openings."""
    bmp = drawing.Bitmap(size, size, drawing.PixelFormat.Format32bppRgba)
    g = drawing.Graphics(bmp)
    try:
        g.AntiAlias = True
        g.FillRectangle(_icon_brush(BH_BLACK), 0, 0, size, size)
        s = size / 48.0
        pen = _icon_pen(BH_WHITE, 1)
        pen_thin = _icon_pen(BH_WHITE, 0.4)
        pen_dim = _icon_pen(BH_ORANGE, 0.5)
        lbl = drawing.Font(drawing.FontFamily("Arial"), 2.5, drawing.FontStyle.Bold)
        # Floor slab (isometric)
        slab = drawing.GraphicsPath()
        _gp_add_polygon(slab, [
            drawing.PointF(24*s, 36*s), drawing.PointF(44*s, 28*s),
            drawing.PointF(24*s, 20*s), drawing.PointF(4*s, 28*s)])
        g.FillPath(_icon_brush(BH_RED, 10), slab)
        g.DrawPath(pen, slab)
        # Slab thickness
        sl = drawing.GraphicsPath()
        _gp_add_polygon(sl, [
            drawing.PointF(4*s,28*s), drawing.PointF(4*s,30*s),
            drawing.PointF(24*s,38*s), drawing.PointF(24*s,36*s)])
        g.FillPath(_icon_brush(BH_RED, 5), sl)
        g.DrawPath(_icon_pen(BH_WHITE, 0.5), sl)
        sr = drawing.GraphicsPath()
        _gp_add_polygon(sr, [
            drawing.PointF(24*s,36*s), drawing.PointF(24*s,38*s),
            drawing.PointF(44*s,30*s), drawing.PointF(44*s,28*s)])
        g.FillPath(_icon_brush(BH_RED, 4), sr)
        g.DrawPath(_icon_pen(BH_WHITE, 0.5), sr)
        # Grid lines on slab
        for i in range(1, 4):
            x1 = (4 + i*5) * s; y1 = (28 - i*2) * s
            x2 = (4 + i*5 + 20) * s; y2 = (28 - i*2 + 8) * s
            g.DrawLine(pen_thin, x1, y1, x2, y2)
        for i in range(1, 4):
            x1 = (4 + i*5) * s; y1 = (28 + i*2) * s
            x2 = (4 + i*5 + 20) * s; y2 = (28 + i*2 - 8) * s
            g.DrawLine(pen_thin, x1, y1, x2, y2)
        # Extruded box 1 (top-left, non-overlapping)
        for pts in [
            # Front face
            [(9*s,26*s),(14*s,24*s),(14*s,12*s),(9*s,14*s)],
            # Right face
            [(14*s,24*s),(19*s,26*s),(19*s,14*s),(14*s,12*s)],
            # Top face
            [(9*s,14*s),(14*s,12*s),(19*s,14*s),(14*s,16*s)]
        ]:
            gp = drawing.GraphicsPath()
            _gp_add_polygon(gp, [drawing.PointF(*p) for p in pts])
            g.FillPath(_icon_brush(BH_RED, 30), gp)
            g.DrawPath(_icon_pen(BH_WHITE, 0.6), gp)
        # Opening on front
        g.FillRectangle(_icon_brush(BH_BLACK), drawing.RectangleF(10*s, 17*s, 3*s, 9*s))
        # Extruded box 2 (bottom-right, non-overlapping)
        for pts in [
            [(29*s,30*s),(34*s,28*s),(34*s,16*s),(29*s,18*s)],
            [(34*s,28*s),(39*s,30*s),(39*s,18*s),(34*s,16*s)],
            [(29*s,18*s),(34*s,16*s),(39*s,18*s),(34*s,20*s)]
        ]:
            gp = drawing.GraphicsPath()
            _gp_add_polygon(gp, [drawing.PointF(*p) for p in pts])
            g.FillPath(_icon_brush(BH_RED, 30), gp)
            g.DrawPath(_icon_pen(BH_WHITE, 0.6), gp)
        # Opening on front
        g.FillRectangle(_icon_brush(BH_BLACK), drawing.RectangleF(30*s, 21*s, 3*s, 9*s))
        # 4m height dimension (left)
        g.DrawLine(pen_dim, int(2*s), int(14*s), int(2*s), int(18*s))
        g.DrawLine(pen_dim, int(2*s), int(24*s), int(2*s), int(28*s))
        g.DrawLine(pen_dim, int(1*s), int(14*s), int(3*s), int(14*s))
        g.DrawLine(pen_dim, int(1*s), int(28*s), int(3*s), int(28*s))
        h_t = drawing.GraphicsPath()
        _gp_add_polygon(h_t, [drawing.PointF(2*s,14*s), drawing.PointF(1*s,16*s), drawing.PointF(3*s,16*s)])
        g.FillPath(_icon_brush(BH_ORANGE), h_t)
        h_b = drawing.GraphicsPath()
        _gp_add_polygon(h_b, [drawing.PointF(2*s,28*s), drawing.PointF(1*s,26*s), drawing.PointF(3*s,26*s)])
        g.FillPath(_icon_brush(BH_ORANGE), h_b)
        g.DrawText(lbl, make_color(*BH_ORANGE), int(0*s), int(19*s), "4")
        g.DrawText(lbl, make_color(*BH_ORANGE), int(0*s), int(21*s), "(m)")
        # Z arrow (right)
        g.DrawLine(_icon_pen(BH_WHITE, 1), int(44*s), int(30*s), int(44*s), int(14*s))
        zt = drawing.GraphicsPath()
        _gp_add_polygon(zt, [drawing.PointF(44*s,14*s), drawing.PointF(43*s,16*s), drawing.PointF(45*s,16*s)])
        g.FillPath(_icon_brush(BH_WHITE), zt)
        g.DrawText(lbl, make_color(*BH_WHITE), int(45*s), int(20*s), "Z")
        # Ground line + hatch
        g.DrawLine(_icon_pen(BH_WHITE, 1), int(2*s), int(40*s), int(46*s), int(40*s))
        for hx in range(3, 44, 2):
            g.DrawLine(_icon_pen(BH_WHITE, 0.3), int((hx+1)*s), int(42*s), int(hx*s), int(40*s))
        for hx in range(3, 44, 3):
            g.DrawLine(_icon_pen(BH_WHITE, 0.2), int(hx*s), int(42*s), int(hx*s), int(46*s))
    finally:
        g.Dispose()
    return bmp

def _icon_variant_orientation(size=48):
    """Bauhaus compass icon: bold red/white cross, circular outline."""
    bmp = drawing.Bitmap(size, size, drawing.PixelFormat.Format32bppRgba)
    g = drawing.Graphics(bmp)
    try:
        g.AntiAlias = True
        g.FillRectangle(_icon_brush(BH_BLACK), 0, 0, size, size)
        cx, cy, r = size//2, size//2, size//2 - 4
        # Circle outline — white
        g.DrawEllipse(_icon_pen(BH_WHITE, 2), cx - r, cy - r, r*2, r*2)
        # N arrow — big red filled triangle
        north = drawing.GraphicsPath()
        _gp_add_polygon(north, [
            drawing.PointF(cx, cy - r + 2),
            drawing.PointF(cx - 6, cy - 4),
            drawing.PointF(cx + 6, cy - 4),
        ])
        g.FillPath(_icon_brush(BH_RED), north)
        # S arrow — white
        south = drawing.GraphicsPath()
        _gp_add_polygon(south, [
            drawing.PointF(cx, cy + r - 2),
            drawing.PointF(cx - 5, cy + 4),
            drawing.PointF(cx + 5, cy + 4),
        ])
        g.FillPath(_icon_brush(BH_WHITE), south)
        # E-W lines — orange
        g.DrawLine(_icon_pen(BH_ORANGE, 2), cx - r + 4, cy, cx + r - 4, cy)
        # Centre dot
        g.FillEllipse(_icon_brush(BH_RED), cx - 3, cy - 3, 6, 6)
    finally:
        g.Dispose()
    return bmp

def _icon_variant_crane(size=48):
    """Plot setup icon: plot boundary, north arrow (separated), split dimension lines with LENGTH/WIDTH (m)."""
    bmp = drawing.Bitmap(size, size, drawing.PixelFormat.Format32bppRgba)
    g = drawing.Graphics(bmp)
    try:
        g.AntiAlias = True
        g.FillRectangle(_icon_brush(BH_BLACK), 0, 0, size, size)
        pen_main = _icon_pen(BH_WHITE, 2)
        pen_thin = _icon_pen(BH_WHITE, 1)
        pen_dash = drawing.Pen(make_color(*BH_WHITE), 0.8)
        try:
            pen_dash.DashStyle = drawing.DashStyle.Dash
        except:
            pass
        brush_fill = _icon_brush(BH_RED, 20)
        # Plot boundary rectangle (shifted left to separate from north arrow)
        g.DrawRectangle(pen_main, drawing.RectangleF(10, 10, 24, 28))
        # Inner setback (dashed)
        g.FillRectangle(brush_fill, drawing.RectangleF(14, 14, 16, 20))
        g.DrawRectangle(pen_dash, drawing.RectangleF(14, 14, 16, 20))
        # North arrow circle (top right — clear of plot)
        g.DrawEllipse(pen_thin, drawing.RectangleF(36, 2, 10, 10))
        # North arrow triangle
        north = drawing.GraphicsPath()
        _gp_add_polygon(north, [
            drawing.PointF(41, 3),
            drawing.PointF(38, 9),
            drawing.PointF(44, 9),
        ])
        g.FillPath(_icon_brush(BH_RED), north)
        # "N" label
        n_font = drawing.Font(drawing.FontFamily("Arial"), 4, drawing.FontStyle.Bold)
        g.DrawText(n_font, make_color(*BH_WHITE), 39, 11, "N")
        # ── Horizontal dimension line (bottom) — split with LENGTH (m) ──
        g.DrawLine(pen_thin, 10, 42, 16, 42)     # left segment
        g.DrawLine(pen_thin, 28, 42, 34, 42)     # right segment
        g.DrawLine(pen_thin, 10, 40, 10, 44)     # left tick
        g.DrawLine(pen_thin, 34, 40, 34, 44)     # right tick
        # Arrow heads horizontal
        h_left = drawing.GraphicsPath()
        _gp_add_polygon(h_left, [
            drawing.PointF(10, 42), drawing.PointF(13, 40.5), drawing.PointF(13, 43.5)])
        g.FillPath(_icon_brush(BH_WHITE), h_left)
        h_right = drawing.GraphicsPath()
        _gp_add_polygon(h_right, [
            drawing.PointF(34, 42), drawing.PointF(31, 40.5), drawing.PointF(31, 43.5)])
        g.FillPath(_icon_brush(BH_WHITE), h_right)
        # LENGTH (m) labels in gap
        lbl_font = drawing.Font(drawing.FontFamily("Arial"), 3.5, drawing.FontStyle.Bold)
        lbl_font_sm = drawing.Font(drawing.FontFamily("Arial"), 3, drawing.FontStyle.Italic)
        g.DrawText(lbl_font, make_color(*BH_WHITE), 16, 39, "LENGTH")
        g.DrawText(lbl_font_sm, make_color(*BH_WHITE), 19, 43, "(m)")
        # ── Vertical dimension line (left) — split with WIDTH (m) ──
        g.DrawLine(pen_thin, 5, 10, 5, 18)       # top segment
        g.DrawLine(pen_thin, 5, 30, 5, 38)       # bottom segment
        g.DrawLine(pen_thin, 3, 10, 7, 10)       # top tick
        g.DrawLine(pen_thin, 3, 38, 7, 38)       # bottom tick
        # Arrow heads vertical
        v_top = drawing.GraphicsPath()
        _gp_add_polygon(v_top, [
            drawing.PointF(5, 10), drawing.PointF(3.5, 13), drawing.PointF(6.5, 13)])
        g.FillPath(_icon_brush(BH_WHITE), v_top)
        v_bot = drawing.GraphicsPath()
        _gp_add_polygon(v_bot, [
            drawing.PointF(5, 38), drawing.PointF(3.5, 35), drawing.PointF(6.5, 35)])
        g.FillPath(_icon_brush(BH_WHITE), v_bot)
        # WIDTH (m) labels in gap — rotated via Eto Matrix
        try:
            mtx = drawing.Matrix()
            mtx.RotateAt(-90, drawing.PointF(5, 24))
            g.MultiplyTransform(mtx)
            g.DrawText(lbl_font, make_color(*BH_WHITE), -1, 1, "WIDTH")
            g.DrawText(lbl_font_sm, make_color(*BH_WHITE), 6, 1, "(m)")
            mtx_back = drawing.Matrix()
            mtx_back.RotateAt(90, drawing.PointF(5, 24))
            g.MultiplyTransform(mtx_back)
        except:
            # Fallback — horizontal "W (m)" in the gap
            g.DrawText(lbl_font_sm, make_color(*BH_WHITE), 1, 21, "W")
            g.DrawText(lbl_font_sm, make_color(*BH_WHITE), 0, 25, "(m)")
    finally:
        g.Dispose()
    return bmp

def _icon_variant_panel_generation(size=48):
    """Panel generation heading: 3D room box with floor slab + walls, panel divisions, labels, dimensions."""
    bmp = drawing.Bitmap(size, size, drawing.PixelFormat.Format32bppRgba)
    g = drawing.Graphics(bmp)
    try:
        g.AntiAlias = True
        g.FillRectangle(_icon_brush(BH_BLACK), 0, 0, size, size)
        s = size / 48.0
        pen = _icon_pen(BH_WHITE, 1.5)
        pen_thin = _icon_pen(BH_WHITE, 0.5)
        pen_dim = _icon_pen(BH_ORANGE, 0.5)
        lbl = drawing.Font(drawing.FontFamily("Arial"), 3, drawing.FontStyle.Bold)
        # Floor slab (isometric)
        slab = drawing.GraphicsPath()
        _gp_add_polygon(slab, [
            drawing.PointF(6*s, 30*s), drawing.PointF(24*s, 22*s),
            drawing.PointF(42*s, 30*s), drawing.PointF(24*s, 38*s)])
        g.FillPath(_icon_brush(BH_RED, 18), slab)
        g.DrawPath(pen, slab)
        # Slab thickness
        sl = drawing.GraphicsPath()
        _gp_add_polygon(sl, [
            drawing.PointF(6*s,30*s), drawing.PointF(6*s,33*s),
            drawing.PointF(24*s,41*s), drawing.PointF(24*s,38*s)])
        g.FillPath(_icon_brush(BH_RED, 10), sl)
        g.DrawPath(_icon_pen(BH_WHITE, 0.6), sl)
        sr = drawing.GraphicsPath()
        _gp_add_polygon(sr, [
            drawing.PointF(24*s,38*s), drawing.PointF(24*s,41*s),
            drawing.PointF(42*s,33*s), drawing.PointF(42*s,30*s)])
        g.FillPath(_icon_brush(BH_RED, 8), sr)
        g.DrawPath(_icon_pen(BH_WHITE, 0.6), sr)
        # Grid on floor
        g.DrawLine(pen_thin, int(15*s), int(26*s), int(33*s), int(34*s))
        g.DrawLine(pen_thin, int(15*s), int(34*s), int(33*s), int(26*s))
        # Back wall (left face)
        bw = drawing.GraphicsPath()
        _gp_add_polygon(bw, [
            drawing.PointF(6*s,30*s), drawing.PointF(6*s,10*s),
            drawing.PointF(24*s,4*s), drawing.PointF(24*s,22*s)])
        g.FillPath(_icon_brush(BH_RED, 12), bw)
        g.DrawPath(pen, bw)
        # Wall panel divisions — back wall (full height)
        g.DrawLine(pen_thin, int(12*s), int(24*s), int(12*s), int(8*s))
        g.DrawLine(pen_thin, int(18*s), int(20*s), int(18*s), int(6*s))
        # Side wall (right face)
        sw = drawing.GraphicsPath()
        _gp_add_polygon(sw, [
            drawing.PointF(24*s,22*s), drawing.PointF(24*s,4*s),
            drawing.PointF(42*s,10*s), drawing.PointF(42*s,30*s)])
        g.FillPath(_icon_brush(BH_RED, 8), sw)
        g.DrawPath(pen, sw)
        # Wall panel divisions — side wall (full height)
        g.DrawLine(pen_thin, int(30*s), int(20*s), int(30*s), int(6*s))
        g.DrawLine(pen_thin, int(36*s), int(24*s), int(36*s), int(8*s))
        # FLOOR label with leader
        g.DrawLine(_icon_pen(BH_ORANGE, 0.5), int(16*s), int(34*s), int(8*s), int(40*s))
        g.FillEllipse(_icon_brush(BH_ORANGE), int(16*s)-1, int(34*s)-1, 2, 2)
        g.DrawText(lbl, make_color(*BH_ORANGE), int(2*s), int(40*s), "FLOOR")
        # WALL label with leader
        g.DrawLine(_icon_pen(BH_ORANGE, 0.5), int(10*s), int(16*s), int(2*s), int(12*s))
        g.FillEllipse(_icon_brush(BH_ORANGE), int(10*s)-1, int(16*s)-1, 2, 2)
        g.DrawText(lbl, make_color(*BH_ORANGE), int(0*s), int(8*s), "WALL")
        # Height dimension (right)
        g.DrawLine(pen_dim, int(44*s), int(10*s), int(44*s), int(18*s))
        g.DrawLine(pen_dim, int(44*s), int(24*s), int(44*s), int(30*s))
        g.DrawLine(pen_dim, int(43*s), int(10*s), int(45*s), int(10*s))
        g.DrawLine(pen_dim, int(43*s), int(30*s), int(45*s), int(30*s))
        h_t = drawing.GraphicsPath()
        _gp_add_polygon(h_t, [drawing.PointF(44*s,10*s), drawing.PointF(43*s,12*s), drawing.PointF(45*s,12*s)])
        g.FillPath(_icon_brush(BH_ORANGE), h_t)
        h_b = drawing.GraphicsPath()
        _gp_add_polygon(h_b, [drawing.PointF(44*s,30*s), drawing.PointF(43*s,28*s), drawing.PointF(45*s,28*s)])
        g.FillPath(_icon_brush(BH_ORANGE), h_b)
        lbl_xs = drawing.Font(drawing.FontFamily("Arial"), 2.5, drawing.FontStyle.Bold)
        g.DrawText(lbl_xs, make_color(*BH_ORANGE), int(45*s), int(19*s), "(m)")
    finally:
        g.Dispose()
    return bmp


def _icon_variant_facade_heading(size=48):
    """Facade subdivision heading: stepped building elevation with subdivided wall panels, glass, arches."""
    bmp = drawing.Bitmap(size, size, drawing.PixelFormat.Format32bppRgba)
    g = drawing.Graphics(bmp)
    try:
        g.AntiAlias = True
        g.FillRectangle(_icon_brush(BH_BLACK), 0, 0, size, size)
        s = size / 48.0
        pen = _icon_pen(BH_WHITE, 1.2)
        pen_thin = _icon_pen(BH_WHITE, 0.5)
        # Columns
        for cx in [6, 14, 22, 30, 38]:
            g.DrawLine(_icon_pen(BH_WHITE, 0.6), int(cx*s), int(34*s), int(cx*s), int(8*s) if cx >= 30 else int(22*s) if cx >= 22 else int(28*s))
        # Beams
        g.DrawLine(pen, int(4*s), int(34*s), int(42*s), int(34*s))
        g.DrawLine(pen, int(4*s), int(28*s), int(42*s), int(28*s))
        g.DrawLine(_icon_pen(BH_WHITE, 1), int(20*s), int(22*s), int(42*s), int(22*s))
        g.DrawLine(_icon_pen(BH_WHITE, 1), int(28*s), int(16*s), int(42*s), int(16*s))
        g.DrawLine(_icon_pen(BH_WHITE, 1), int(28*s), int(8*s), int(42*s), int(8*s))
        # Wall panels with vertical subdivisions
        for (px, py, pw, ph) in [(6,28,7,6),(14,28,7,6),(22,28,7,6),(30,28,7,6),
                                  (22,22,7,6),(30,22,7,6),(30,16,7,6),(30,8,7,8),(38,8,4,8)]:
            g.FillRectangle(_icon_brush(BH_RED, 25), drawing.RectangleF(px*s, py*s, pw*s, ph*s))
            g.DrawRectangle(_icon_pen(BH_WHITE, 0.4), drawing.RectangleF(px*s, py*s, pw*s, ph*s))
            # Sub-column lines
            g.DrawLine(_icon_pen(BH_WHITE, 0.2), int((px+pw/3)*s), int(py*s), int((px+pw/3)*s), int((py+ph)*s))
            g.DrawLine(_icon_pen(BH_WHITE, 0.2), int((px+2*pw/3)*s), int(py*s), int((px+2*pw/3)*s), int((py+ph)*s))
        # Glass panels (diagonal hatch on some sub-columns)
        for (gx, gy, gw, gh) in [(6,28,2,6),(22,22,2,6),(32,16,2,6),(38,8,2,8)]:
            g.DrawLine(_icon_pen(BH_WHITE, 0.3), int(gx*s), int(gy*s), int((gx+gw)*s), int((gy+gh)*s))
        # Arch on terrace
        g.FillRectangle(_icon_brush(BH_RED, 35), drawing.RectangleF(8*s, 22*s, 5*s, 6*s))
        g.DrawRectangle(_icon_pen(BH_WHITE, 0.5), drawing.RectangleF(8*s, 22*s, 5*s, 6*s))
        g.FillRectangle(_icon_brush(BH_BLACK), drawing.RectangleF(9*s, 24*s, 3*s, 4*s))
        # Ground + hatch
        g.DrawLine(_icon_pen(BH_WHITE, 1.5), int(2*s), int(36*s), int(44*s), int(36*s))
        for hx in range(3, 42, 2):
            g.DrawLine(_icon_pen(BH_WHITE, 0.2), int((hx+1)*s), int(38*s), int(hx*s), int(36*s))
        # Floor labels
        lbl = drawing.Font(drawing.FontFamily("Arial"), 2.5, drawing.FontStyle.Bold)
        g.DrawText(lbl, make_color(*BH_ORANGE), int(2*s), int(30*s), "G")
        g.DrawText(lbl, make_color(*BH_ORANGE), int(18*s), int(24*s), "1")
        g.DrawText(lbl, make_color(*BH_ORANGE), int(26*s), int(10*s), "3")
        # Height dimension
        g.DrawLine(_icon_pen(BH_ORANGE, 0.4), int(44*s), int(8*s), int(44*s), int(16*s))
        g.DrawLine(_icon_pen(BH_ORANGE, 0.4), int(44*s), int(26*s), int(44*s), int(36*s))
        g.DrawLine(_icon_pen(BH_ORANGE, 0.3), int(43*s), int(8*s), int(45*s), int(8*s))
        g.DrawLine(_icon_pen(BH_ORANGE, 0.3), int(43*s), int(36*s), int(45*s), int(36*s))
        lbl_xs = drawing.Font(drawing.FontFamily("Arial"), 2, drawing.FontStyle.Bold)
        g.DrawText(lbl_xs, make_color(*BH_ORANGE), int(43*s), int(19*s), "H")
        g.DrawText(lbl_xs, make_color(*BH_ORANGE), int(43*s), int(22*s), "(m)")
    finally:
        g.Dispose()
    return bmp

def _icon_sub_panel_counts(size=28):
    """Sub-icon: counting panels — tally marks with numbers."""
    bmp = drawing.Bitmap(size, size, drawing.PixelFormat.Format32bppRgba)
    g = drawing.Graphics(bmp)
    try:
        g.AntiAlias = True
        g.FillRectangle(_icon_brush(BH_BLACK), 0, 0, size, size)
        s = size / 28.0
        pen = _icon_pen(BH_WHITE, 1.2)
        pen_thin = _icon_pen(BH_WHITE, 0.8)
        lbl = drawing.Font(drawing.FontFamily("Arial"), 3, drawing.FontStyle.Bold)
        lbl_sm = drawing.Font(drawing.FontFamily("Arial"), 2.5, drawing.FontStyle.Bold)
        # Tally marks row 1 (4 vertical + 1 diagonal strike = 5)
        for i in range(4):
            g.DrawLine(pen, int((4+i*3)*s), int(4*s), int((4+i*3)*s), int(12*s))
        # Diagonal strike-through
        g.DrawLine(pen_thin, int(3*s), int(10*s), int(14*s), int(5*s))
        # Count number
        g.DrawText(lbl, make_color(*BH_ORANGE), int(16*s), int(5*s), "25")
        # Tally marks row 2 (4 vertical + 1 diagonal = 5 + extras)
        for i in range(4):
            g.DrawLine(pen, int((4+i*3)*s), int(15*s), int((4+i*3)*s), int(23*s))
        g.DrawLine(pen_thin, int(3*s), int(21*s), int(14*s), int(16*s))
        # Extra marks
        g.DrawLine(pen, int(16*s), int(15*s), int(16*s), int(23*s))
        g.DrawLine(pen, int(19*s), int(15*s), int(19*s), int(23*s))
        # Count number
        g.DrawText(lbl, make_color(*BH_ORANGE), int(22*s), int(16*s), "32")
        # Hash/count symbol (#)
        g.DrawLine(_icon_pen(BH_ORANGE, 0.6), int(22*s), int(4*s), int(22*s), int(12*s))
        g.DrawLine(_icon_pen(BH_ORANGE, 0.6), int(25*s), int(4*s), int(25*s), int(12*s))
        g.DrawLine(_icon_pen(BH_ORANGE, 0.6), int(20*s), int(6*s), int(27*s), int(6*s))
        g.DrawLine(_icon_pen(BH_ORANGE, 0.6), int(20*s), int(10*s), int(27*s), int(10*s))
    finally:
        g.Dispose()
    return bmp

def _icon_sub_panel_subdivision(size=28):
    """Sub-icon: wall panel subdivided into 3 vertical columns."""
    bmp = drawing.Bitmap(size, size, drawing.PixelFormat.Format32bppRgba)
    g = drawing.Graphics(bmp)
    try:
        g.AntiAlias = True
        g.FillRectangle(_icon_brush(BH_BLACK), 0, 0, size, size)
        s = size / 28.0
        # Original panel (left)
        g.FillRectangle(_icon_brush(BH_RED, 25), drawing.RectangleF(2*s, 4*s, 8*s, 18*s))
        g.DrawRectangle(_icon_pen(BH_WHITE, 1), drawing.RectangleF(2*s, 4*s, 8*s, 18*s))
        # Arrow
        g.DrawLine(_icon_pen(BH_WHITE, 0.8), int(11*s), int(13*s), int(14*s), int(13*s))
        ar = drawing.GraphicsPath()
        _gp_add_polygon(ar, [drawing.PointF(14*s,13*s), drawing.PointF(13*s,12*s), drawing.PointF(13*s,14*s)])
        g.FillPath(_icon_brush(BH_WHITE), ar)
        # 3 subdivided columns (right)
        for i in range(3):
            x = (16 + i*4) * s
            a = 20 if i == 1 else 15
            g.FillRectangle(_icon_brush(BH_RED, a), drawing.RectangleF(x, 4*s, 3.5*s, 18*s))
            g.DrawRectangle(_icon_pen(BH_WHITE, 0.6), drawing.RectangleF(x, 4*s, 3.5*s, 18*s))
        # x3 label
        lbl = drawing.Font(drawing.FontFamily("Arial"), 3, drawing.FontStyle.Bold)
        g.DrawText(lbl, make_color(*BH_ORANGE), int(18*s), int(23*s), "x3")
    finally:
        g.Dispose()
    return bmp

def _icon_sub_glass_windows(size=28):
    """Sub-icon: glass panel with frame and diagonal hatch."""
    bmp = drawing.Bitmap(size, size, drawing.PixelFormat.Format32bppRgba)
    g = drawing.Graphics(bmp)
    try:
        g.AntiAlias = True
        g.FillRectangle(_icon_brush(BH_BLACK), 0, 0, size, size)
        s = size / 28.0
        # Wall panel grid (2x2)
        g.DrawRectangle(_icon_pen(BH_WHITE, 1), drawing.RectangleF(3*s, 3*s, 22*s, 20*s))
        g.DrawLine(_icon_pen(BH_WHITE, 0.6), int(14*s), int(3*s), int(14*s), int(23*s))
        g.DrawLine(_icon_pen(BH_WHITE, 0.6), int(3*s), int(13*s), int(25*s), int(13*s))
        # Sub-column lines
        g.DrawLine(_icon_pen(BH_WHITE, 0.3), int(7*s), int(3*s), int(7*s), int(23*s))
        g.DrawLine(_icon_pen(BH_WHITE, 0.3), int(10*s), int(3*s), int(10*s), int(23*s))
        g.DrawLine(_icon_pen(BH_WHITE, 0.3), int(18*s), int(3*s), int(18*s), int(23*s))
        g.DrawLine(_icon_pen(BH_WHITE, 0.3), int(21*s), int(3*s), int(21*s), int(23*s))
        # Glass panel 1 (top-left col1) — frame + diagonal hatch
        g.DrawRectangle(_icon_pen(BH_WHITE, 0.8), drawing.RectangleF(4*s, 4*s, 3*s, 9*s))
        g.DrawRectangle(_icon_pen(BH_WHITE, 0.3), drawing.RectangleF(4.5*s, 4.5*s, 2*s, 8*s))
        g.DrawLine(_icon_pen(BH_WHITE, 0.2), int(4.5*s), int(4.5*s), int(6.5*s), int(12.5*s))
        # Glass panel 2 (top-right col2) — frame + hatch
        g.DrawRectangle(_icon_pen(BH_WHITE, 0.8), drawing.RectangleF(18*s, 4*s, 3*s, 9*s))
        g.DrawRectangle(_icon_pen(BH_WHITE, 0.3), drawing.RectangleF(18.5*s, 4.5*s, 2*s, 8*s))
        g.DrawLine(_icon_pen(BH_WHITE, 0.2), int(18.5*s), int(4.5*s), int(20.5*s), int(12.5*s))
        # Glass panel 3 (bottom-left col2) — frame + hatch
        g.DrawRectangle(_icon_pen(BH_WHITE, 0.8), drawing.RectangleF(7*s, 14*s, 3*s, 9*s))
        g.DrawRectangle(_icon_pen(BH_WHITE, 0.3), drawing.RectangleF(7.5*s, 14.5*s, 2*s, 8*s))
        g.DrawLine(_icon_pen(BH_WHITE, 0.2), int(7.5*s), int(14.5*s), int(9.5*s), int(22.5*s))
        # Glass panel 4 (bottom-right col3)
        g.DrawRectangle(_icon_pen(BH_WHITE, 0.8), drawing.RectangleF(21*s, 14*s, 3*s, 9*s))
        g.DrawRectangle(_icon_pen(BH_WHITE, 0.3), drawing.RectangleF(21.5*s, 14.5*s, 2*s, 8*s))
        g.DrawLine(_icon_pen(BH_WHITE, 0.2), int(21.5*s), int(14.5*s), int(23.5*s), int(22.5*s))
        # % label
        lbl = drawing.Font(drawing.FontFamily("Arial"), 2.5, drawing.FontStyle.Bold)
        g.DrawText(lbl, make_color(*BH_ORANGE), int(6*s), int(24*s), "40-50%")
    finally:
        g.Dispose()
    return bmp


def _icon_variant_elevation_heading(size=48):
    """Elevation extrusion heading: combines wall section + vertical box concept."""
    bmp = drawing.Bitmap(size, size, drawing.PixelFormat.Format32bppRgba)
    g = drawing.Graphics(bmp)
    try:
        g.AntiAlias = True
        g.FillRectangle(_icon_brush(BH_BLACK), 0, 0, size, size)
        s = size / 48.0
        pen = _icon_pen(BH_WHITE, 1.2)
        pen_thin = _icon_pen(BH_WHITE, 0.5)
        # Left half: wall section with extrusion outward
        g.FillRectangle(_icon_brush(BH_RED, 20), drawing.RectangleF(10*s, 6*s, 3*s, 32*s))
        g.DrawRectangle(_icon_pen(BH_WHITE, 0.8), drawing.RectangleF(10*s, 6*s, 3*s, 32*s))
        # Floor lines interior
        for fy in [38, 28, 18, 8]:
            g.DrawLine(pen_thin, int(4*s), int(fy*s), int(10*s), int(fy*s))
        # Extrusion on floor 1
        g.FillRectangle(_icon_brush(BH_RED, 40), drawing.RectangleF(13*s, 18*s, 5*s, 10*s))
        g.DrawRectangle(_icon_pen(BH_WHITE, 0.6), drawing.RectangleF(13*s, 18*s, 5*s, 10*s))
        # Arrow
        g.DrawLine(_icon_pen(BH_WHITE, 0.6), int(14*s), int(23*s), int(17*s), int(23*s))
        ar = drawing.GraphicsPath()
        _gp_add_polygon(ar, [drawing.PointF(17*s,23*s), drawing.PointF(16*s,22*s), drawing.PointF(16*s,24*s)])
        g.FillPath(_icon_brush(BH_WHITE), ar)
        # Right half: isometric slab with extruded box
        slab = drawing.GraphicsPath()
        _gp_add_polygon(slab, [
            drawing.PointF(34*s, 30*s), drawing.PointF(44*s, 26*s),
            drawing.PointF(34*s, 22*s), drawing.PointF(24*s, 26*s)])
        g.FillPath(_icon_brush(BH_RED, 10), slab)
        g.DrawPath(_icon_pen(BH_WHITE, 0.8), slab)
        # Extruded box on slab
        for pts in [
            [(29*s,24*s),(34*s,22*s),(34*s,12*s),(29*s,14*s)],
            [(34*s,22*s),(39*s,24*s),(39*s,14*s),(34*s,12*s)],
            [(29*s,14*s),(34*s,12*s),(39*s,14*s),(34*s,16*s)]
        ]:
            gp = drawing.GraphicsPath()
            _gp_add_polygon(gp, [drawing.PointF(*p) for p in pts])
            g.FillPath(_icon_brush(BH_RED, 30), gp)
            g.DrawPath(_icon_pen(BH_WHITE, 0.5), gp)
        # Opening
        g.FillRectangle(_icon_brush(BH_BLACK), drawing.RectangleF(30*s, 17*s, 3*s, 7*s))
        # Up arrow
        g.DrawLine(_icon_pen(BH_WHITE, 0.8), int(44*s), int(28*s), int(44*s), int(14*s))
        za = drawing.GraphicsPath()
        _gp_add_polygon(za, [drawing.PointF(44*s,14*s), drawing.PointF(43*s,16*s), drawing.PointF(45*s,16*s)])
        g.FillPath(_icon_brush(BH_WHITE), za)
        # Divider
        g.DrawLine(_icon_pen(BH_MID_GREY, 0.4), int(22*s), int(4*s), int(22*s), int(40*s))
        # Labels
        lbl = drawing.Font(drawing.FontFamily("Arial"), 2.5, drawing.FontStyle.Bold)
        g.DrawText(lbl, make_color(*BH_ORANGE), int(5*s), int(40*s), "S1")
        g.DrawText(lbl, make_color(*BH_ORANGE), int(32*s), int(34*s), "S2")
        # Ground line
        g.DrawLine(_icon_pen(BH_WHITE, 1), int(2*s), int(42*s), int(46*s), int(42*s))
        for hx in range(3, 44, 2):
            g.DrawLine(_icon_pen(BH_WHITE, 0.2), int((hx+1)*s), int(44*s), int(hx*s), int(42*s))
    finally:
        g.Dispose()
    return bmp


def get_arch_dialog_icon(title_text, size=42):
    """Return an architectural vector icon bitmap for a dialog heading.
    The choice is based on the dialog title/heading text.
    """
    t = (title_text or "").upper()
    # Keyword routing (based on headings used in this script)
    if "FACADE" in t and "SUBDIVISION" in t:
        return _icon_variant_facade_heading(size)
    if "PANEL" in t and "GENERATION" in t:
        return _icon_variant_panel_generation(size)
    if "FLOOR" in t and "PANELS" in t:
        return _icon_variant_panels(size)
    if "WALL" in t and "PANELS" in t:
        return _icon_variant_walls(size)
    if "GRID" in t or "COLUMN" in t or "FOUNDATION" in t:
        return _icon_variant_grid(size)
    if "ELEVATION" in t and "EXTRUSION" in t:
        return _icon_variant_elevation_heading(size)
    if "VERTICAL" in t and "EXTRUSION" in t:
        return _icon_variant_vertical_extrude(size)
    if "WALL" in t and "EXTRUSION" in t:
        return _icon_variant_wall_extrude(size)
    if "ORIENTATION" in t:
        return _icon_variant_orientation(size)
    if "FLOORS" in t or "LEVEL" in t:
        return _icon_variant_building(size)
    if "PLOT" in t or "ROAD" in t or "SETBACK" in t:
        return _icon_variant_crane(size)
    # Default: building icon
    return _icon_variant_building(size)


# ============================================================ DIALOG CLASS 1: HORIZONTAL SLIDER ============================================================
_SLIDER_BODY_TEXT   = BH_WHITE       # white — all body text
_SLIDER_TICK_TEXT   = BH_WHITE       # white — tick numbers
_SLIDER_RANGE_TEXT  = BH_WHITE       # white — min/max labels
_SLIDER_SELECTED_FG = BH_RED         # dark red — "Selected:" highlight only
_SLIDER_SELECTED_BG = BH_BLACK_LIFT  # near-black — selected row background

class VibrantSliderDialog(forms.Dialog[bool]):
    def __init__(self, title_text, message_text, labels, default_label, icon_emoji, header_color, bg_color, values_list, unit_text):
        super(VibrantSliderDialog, self).__init__()
        self.BackgroundColor = make_color(*BH_BLACK)
        self.selected_value = None
        self.values_list = values_list
        self.unit_text = unit_text
        self.labels = labels
        self.Title = str(title_text)
        self.Padding = drawing.Padding(0)
        self.Resizable = False
        self.MinimumSize = drawing.Size(560, 480)

        # ── Header ───────────────────────────────────────────────────────────
        header_panel = forms.Panel()
        header_panel.BackgroundColor = make_color(*dialog_header_bg_rgb())
        header_panel.Padding = drawing.Padding(20, 16, 20, 16)
        header_icon_label = forms.ImageView()
        header_icon_label.Image = get_arch_dialog_icon(str(title_text), size=48)
        header_icon_label.Size = drawing.Size(48, 48)
        header_title_label = forms.Label()
        header_title_label.Text = str(title_text)
        header_title_label.Font = drawing.Font(drawing.FontFamily("Impact"), 16, drawing.FontStyle.Bold)
        header_title_label.TextColor = make_color(*BH_WHITE)
        accent_strip = forms.Panel()
        accent_strip.BackgroundColor = make_color(*DIALOG_ACCENT_BLUE)
        accent_strip.Height = 4
        header_layout = forms.TableLayout()
        header_layout.Spacing = drawing.Size(12, 0)
        header_row = forms.TableRow()
        header_row.Cells.Add(forms.TableCell(header_icon_label, False))
        header_row.Cells.Add(forms.TableCell(header_title_label, True))
        header_layout.Rows.Add(header_row)
        header_panel.Content = header_layout

        # ── Body ─────────────────────────────────────────────────────────────
        body_panel = forms.Panel()
        body_panel.BackgroundColor = make_color(*dialog_body_bg_rgb())
        body_panel.Padding = drawing.Padding(24, 18, 24, 18)

        # Message label — dark text, visible on light system bg
        message_label = forms.Label()
        message_label.Text = str(message_text)
        message_label.Font = drawing.Font(drawing.FontFamily("Georgia"), 11, drawing.FontStyle.Bold)
        message_label.TextColor = make_color(*_SLIDER_BODY_TEXT)
        message_label.Wrap = forms.WrapMode.Word

        # Accent separator
        separator = forms.Panel()
        separator.BackgroundColor = make_color(*DIALOG_ACCENT_BLUE)
        separator.Height = 4

        # Tick labels — dark purple, clearly visible
        tick_layout = forms.TableLayout()
        tick_layout.Spacing = drawing.Size(0, 0)
        tick_row = forms.TableRow()
        for i in range(len(values_list)):
            tick_label = forms.Label()
            val = values_list[i]
            tick_label.Text = str(int(val)) if val == int(val) else str(val)
            tick_label.Font = drawing.Font(drawing.FontFamily("Arial Narrow"), 10, drawing.FontStyle.Bold)
            tick_label.TextColor = make_color(*_SLIDER_TICK_TEXT)
            tick_label.TextAlignment = forms.TextAlignment.Center
            tick_row.Cells.Add(forms.TableCell(tick_label, True))
        tick_layout.Rows.Add(tick_row)

        # Slider
        self.slider = forms.Slider()
        self.slider.MinValue = 0
        self.slider.MaxValue = len(values_list) - 1
        self.slider.SnapToTick = True
        self.slider.TickFrequency = 1
        self.slider.Orientation = forms.Orientation.Horizontal
        self.slider.Width = 480
        default_index = 0
        for i in range(len(values_list)):
            val = values_list[i]
            check_label = "{} {}".format(int(val) if val == int(val) else val, unit_text)
            if check_label == str(default_label):
                default_index = i
                break
        self.slider.Value = default_index
        self.slider.ValueChanged += self.on_slider_changed

        # Min / max range labels
        min_val = values_list[0]
        max_val = values_list[-1]
        min_text = "{} {}".format(int(min_val) if min_val == int(min_val) else min_val, unit_text)
        max_text = "{} {}".format(int(max_val) if max_val == int(max_val) else max_val, unit_text)
        min_label = forms.Label()
        min_label.Text = min_text
        min_label.Font = drawing.Font(drawing.FontFamily("Arial Narrow"), 10, drawing.FontStyle.Bold)
        min_label.TextColor = make_color(*_SLIDER_RANGE_TEXT)
        max_label = forms.Label()
        max_label.Text = max_text
        max_label.Font = drawing.Font(drawing.FontFamily("Arial Narrow"), 10, drawing.FontStyle.Bold)
        max_label.TextColor = make_color(*_SLIDER_RANGE_TEXT)
        max_label.TextAlignment = forms.TextAlignment.Right
        range_layout = forms.TableLayout()
        range_layout.Spacing = drawing.Size(0, 0)
        range_row = forms.TableRow()
        range_row.Cells.Add(forms.TableCell(min_label, False))
        range_row.Cells.Add(forms.TableCell(None, True))
        range_row.Cells.Add(forms.TableCell(max_label, False))
        range_layout.Rows.Add(range_row)

        # "Selected: X metres" — vivid magenta prefix + bold value, always visible
        initial_val = values_list[default_index]
        initial_display = "{} {}".format(int(initial_val) if initial_val == int(initial_val) else initial_val, unit_text)
        self.selection_label = forms.Label()
        self.selection_label.Text = "Selected:  {}".format(initial_display)
        self.selection_label.Font = drawing.Font(drawing.FontFamily("Impact"), 16, drawing.FontStyle.Bold)
        self.selection_label.TextColor = make_color(*_SLIDER_SELECTED_FG)
        self.selection_label.TextAlignment = forms.TextAlignment.Center

        # Buttons
        ok_button = forms.Button()
        ok_button.Text = "  CONFIRM  "
        ok_button.Font = drawing.Font(drawing.FontFamily("Impact"), 13, drawing.FontStyle.Bold)
        ok_button.BackgroundColor = make_color(*DIALOG_ACCENT_GREEN)
        ok_button.TextColor = make_color(*BH_PURE_WHITE)
        ok_button.Size = drawing.Size(190, 46)
        ok_button.Click += self.on_ok_clicked
        cancel_button = forms.Button()
        cancel_button.Text = "  ABORT  "
        cancel_button.Font = drawing.Font(drawing.FontFamily("Georgia"), 11, drawing.FontStyle.Italic)
        cancel_button.Size = drawing.Size(130, 46)
        cancel_button.BackgroundColor = make_color(*DIALOG_CANCEL_BG)
        cancel_button.TextColor = make_color(*DIALOG_CANCEL_TEXT)
        cancel_button.Click += self.on_cancel_clicked
        button_layout = forms.TableLayout()
        button_layout.Spacing = drawing.Size(16, 0)
        button_row = forms.TableRow()
        button_row.Cells.Add(forms.TableCell(None, True))
        button_row.Cells.Add(forms.TableCell(cancel_button, False))
        button_row.Cells.Add(forms.TableCell(ok_button, False))
        button_layout.Rows.Add(button_row)

        body_layout = forms.TableLayout()
        body_layout.Spacing = drawing.Size(0, 12)
        body_layout.Rows.Add(forms.TableRow(forms.TableCell(message_label, True)))
        body_layout.Rows.Add(forms.TableRow(forms.TableCell(separator, True)))
        body_layout.Rows.Add(forms.TableRow(forms.TableCell(tick_layout, True)))
        body_layout.Rows.Add(forms.TableRow(forms.TableCell(self.slider, True)))
        body_layout.Rows.Add(forms.TableRow(forms.TableCell(range_layout, True)))
        body_layout.Rows.Add(forms.TableRow(forms.TableCell(self.selection_label, True)))
        body_layout.Rows.Add(forms.TableRow(forms.TableCell(button_layout, True)))
        body_panel.Content = body_layout

        main_layout = forms.TableLayout()
        main_layout.Spacing = drawing.Size(0, 0)
        main_layout.Rows.Add(forms.TableRow(forms.TableCell(header_panel, True)))
        main_layout.Rows.Add(forms.TableRow(forms.TableCell(accent_strip, True)))
        main_layout.Rows.Add(forms.TableRow(forms.TableCell(body_panel, True)))
        self.Content = main_layout

    def on_slider_changed(self, sender, e):
        current_index = self.slider.Value
        if 0 <= current_index < len(self.values_list):
            current_val = self.values_list[current_index]
            display_text = "{} {}".format(int(current_val) if current_val == int(current_val) else current_val, self.unit_text)
            self.selection_label.Text = "Selected:  {}".format(display_text)

    def on_ok_clicked(self, sender, e):
        current_index = self.slider.Value
        if 0 <= current_index < len(self.labels):
            self.selected_value = str(self.labels[current_index])
        self.Close(True)

    def on_cancel_clicked(self, sender, e):
        self.selected_value = None
        self.Close(False)


# ============================================================ DIALOG CLASS 1b: COMBINED PLOT DIMENSIONS ============================================================
class PlotDimensionsDialog(forms.Dialog[bool]):
    """Single dialog with two sliders: Plot Length and Plot Width."""
    def __init__(self, values_list, default_val, unit_text):
        super(PlotDimensionsDialog, self).__init__()
        self.BackgroundColor = make_color(*BH_BLACK)
        self.selected_length = None
        self.selected_width = None
        self.values_list = values_list
        self.unit_text = unit_text
        self.Title = "PLOT DIMENSIONS"
        self.Padding = drawing.Padding(0)
        self.Resizable = False
        self.MinimumSize = drawing.Size(560, 620)

        # ── Header ───────────────────────────────────────────────────────────
        header_panel = forms.Panel()
        header_panel.BackgroundColor = make_color(*dialog_header_bg_rgb())
        header_panel.Padding = drawing.Padding(20, 16, 20, 16)
        header_icon = forms.ImageView()
        header_icon.Image = get_arch_dialog_icon("PLOT DIMENSIONS", size=48)
        header_icon.Size = drawing.Size(48, 48)
        header_title = forms.Label()
        header_title.Text = "PLOT DIMENSIONS"
        header_title.Font = drawing.Font(drawing.FontFamily("Impact"), 16, drawing.FontStyle.Bold)
        header_title.TextColor = make_color(*BH_WHITE)
        accent_strip = forms.Panel()
        accent_strip.BackgroundColor = make_color(*DIALOG_ACCENT_BLUE)
        accent_strip.Height = 4
        header_layout = forms.TableLayout()
        header_layout.Spacing = drawing.Size(12, 0)
        header_row = forms.TableRow()
        header_row.Cells.Add(forms.TableCell(header_icon, False))
        header_row.Cells.Add(forms.TableCell(header_title, True))
        header_layout.Rows.Add(header_row)
        header_panel.Content = header_layout

        # ── Body ─────────────────────────────────────────────────────────────
        body_panel = forms.Panel()
        body_panel.BackgroundColor = make_color(*dialog_body_bg_rgb())
        body_panel.Padding = drawing.Padding(24, 18, 24, 18)

        # Find default index
        default_index = 0
        for i, v in enumerate(values_list):
            if v == default_val:
                default_index = i
                break

        def make_slider_block(label_text):
            """Returns (block_layout, slider_widget, selection_label_widget)."""
            # Section label
            sec_label = forms.Label()
            sec_label.Text = label_text
            sec_label.Font = drawing.Font(drawing.FontFamily("Georgia"), 11, drawing.FontStyle.Bold)
            sec_label.TextColor = make_color(*_SLIDER_BODY_TEXT)

            sep = forms.Panel()
            sep.BackgroundColor = make_color(*DIALOG_ACCENT_BLUE)
            sep.Height = 3

            # Tick labels
            tick_layout = forms.TableLayout()
            tick_layout.Spacing = drawing.Size(0, 0)
            tick_row = forms.TableRow()
            for v in values_list:
                tl = forms.Label()
                tl.Text = str(int(v)) if v == int(v) else str(v)
                tl.Font = drawing.Font(drawing.FontFamily("Arial Narrow"), 10, drawing.FontStyle.Bold)
                tl.TextColor = make_color(*_SLIDER_TICK_TEXT)
                tl.TextAlignment = forms.TextAlignment.Center
                tick_row.Cells.Add(forms.TableCell(tl, True))
            tick_layout.Rows.Add(tick_row)

            # Slider
            slider = forms.Slider()
            slider.MinValue = 0
            slider.MaxValue = len(values_list) - 1
            slider.SnapToTick = True
            slider.TickFrequency = 1
            slider.Orientation = forms.Orientation.Horizontal
            slider.Width = 480
            slider.Value = default_index

            # Range labels
            min_lbl = forms.Label()
            min_lbl.Text = "{} {}".format(int(values_list[0]) if values_list[0] == int(values_list[0]) else values_list[0], unit_text)
            min_lbl.Font = drawing.Font(drawing.FontFamily("Arial Narrow"), 10, drawing.FontStyle.Bold)
            min_lbl.TextColor = make_color(*_SLIDER_RANGE_TEXT)
            max_lbl = forms.Label()
            max_lbl.Text = "{} {}".format(int(values_list[-1]) if values_list[-1] == int(values_list[-1]) else values_list[-1], unit_text)
            max_lbl.Font = drawing.Font(drawing.FontFamily("Arial Narrow"), 10, drawing.FontStyle.Bold)
            max_lbl.TextColor = make_color(*_SLIDER_RANGE_TEXT)
            max_lbl.TextAlignment = forms.TextAlignment.Right
            range_layout = forms.TableLayout()
            range_layout.Spacing = drawing.Size(0, 0)
            range_row = forms.TableRow()
            range_row.Cells.Add(forms.TableCell(min_lbl, False))
            range_row.Cells.Add(forms.TableCell(None, True))
            range_row.Cells.Add(forms.TableCell(max_lbl, False))
            range_layout.Rows.Add(range_row)

            # Selected label
            init_v = values_list[default_index]
            init_display = "{} {}".format(int(init_v) if init_v == int(init_v) else init_v, unit_text)
            sel_lbl = forms.Label()
            sel_lbl.Text = "Selected:  {}".format(init_display)
            sel_lbl.Font = drawing.Font(drawing.FontFamily("Impact"), 14, drawing.FontStyle.Bold)
            sel_lbl.TextColor = make_color(*_SLIDER_SELECTED_FG)
            sel_lbl.TextAlignment = forms.TextAlignment.Center

            block = forms.TableLayout()
            block.Spacing = drawing.Size(0, 8)
            block.Rows.Add(forms.TableRow(forms.TableCell(sec_label, True)))
            block.Rows.Add(forms.TableRow(forms.TableCell(sep, True)))
            block.Rows.Add(forms.TableRow(forms.TableCell(tick_layout, True)))
            block.Rows.Add(forms.TableRow(forms.TableCell(slider, True)))
            block.Rows.Add(forms.TableRow(forms.TableCell(range_layout, True)))
            block.Rows.Add(forms.TableRow(forms.TableCell(sel_lbl, True)))
            return block, slider, sel_lbl

        length_block, self.length_slider, self.length_sel_label = make_slider_block("Select PLOT LENGTH (20-50m)")
        width_block,  self.width_slider,  self.width_sel_label  = make_slider_block("Select PLOT WIDTH  (20-50m)")

        self.length_slider.ValueChanged += self.on_length_changed
        self.width_slider.ValueChanged  += self.on_width_changed

        # Divider between the two sliders
        divider = forms.Panel()
        divider.BackgroundColor = make_color(*BH_MID_GREY)
        divider.Height = 2

        # Buttons
        ok_button = forms.Button()
        ok_button.Text = "  CONFIRM  "
        ok_button.Font = drawing.Font(drawing.FontFamily("Impact"), 13, drawing.FontStyle.Bold)
        ok_button.BackgroundColor = make_color(*DIALOG_ACCENT_GREEN)
        ok_button.TextColor = make_color(*BH_PURE_WHITE)
        ok_button.Size = drawing.Size(190, 46)
        ok_button.Click += self.on_ok_clicked
        cancel_button = forms.Button()
        cancel_button.Text = "  ABORT  "
        cancel_button.Font = drawing.Font(drawing.FontFamily("Georgia"), 11, drawing.FontStyle.Italic)
        cancel_button.Size = drawing.Size(130, 46)
        cancel_button.BackgroundColor = make_color(*DIALOG_CANCEL_BG)
        cancel_button.TextColor = make_color(*DIALOG_CANCEL_TEXT)
        cancel_button.Click += self.on_cancel_clicked
        button_layout = forms.TableLayout()
        button_layout.Spacing = drawing.Size(16, 0)
        button_row = forms.TableRow()
        button_row.Cells.Add(forms.TableCell(None, True))
        button_row.Cells.Add(forms.TableCell(cancel_button, False))
        button_row.Cells.Add(forms.TableCell(ok_button, False))
        button_layout.Rows.Add(button_row)

        body_layout = forms.TableLayout()
        body_layout.Spacing = drawing.Size(0, 14)
        body_layout.Rows.Add(forms.TableRow(forms.TableCell(length_block, True)))
        body_layout.Rows.Add(forms.TableRow(forms.TableCell(divider, True)))
        body_layout.Rows.Add(forms.TableRow(forms.TableCell(width_block, True)))
        body_layout.Rows.Add(forms.TableRow(forms.TableCell(button_layout, True)))
        body_panel.Content = body_layout

        main_layout = forms.TableLayout()
        main_layout.Spacing = drawing.Size(0, 0)
        main_layout.Rows.Add(forms.TableRow(forms.TableCell(header_panel, True)))
        main_layout.Rows.Add(forms.TableRow(forms.TableCell(accent_strip, True)))
        main_layout.Rows.Add(forms.TableRow(forms.TableCell(body_panel, True)))
        self.Content = main_layout

    def _get_value(self, slider):
        idx = slider.Value
        if 0 <= idx < len(self.values_list):
            return self.values_list[idx]
        return self.values_list[0]

    def _format(self, v):
        return "{} {}".format(int(v) if v == int(v) else v, self.unit_text)

    def on_length_changed(self, sender, e):
        self.length_sel_label.Text = "Selected:  {}".format(self._format(self._get_value(self.length_slider)))

    def on_width_changed(self, sender, e):
        self.width_sel_label.Text = "Selected:  {}".format(self._format(self._get_value(self.width_slider)))

    def on_ok_clicked(self, sender, e):
        self.selected_length = self._get_value(self.length_slider)
        self.selected_width  = self._get_value(self.width_slider)
        self.Close(True)

    def on_cancel_clicked(self, sender, e):
        self.selected_length = None
        self.selected_width  = None
        self.Close(False)


# ============================================================ DIALOG CLASS 1c: COMBINED PLOT SETUP (Dimensions + Setback) ============================================================
class PlotSetupDialog(forms.Dialog[bool]):
    """Single dialog: two dimension sliders (Length, Width) + one setback listbox."""
    def __init__(self, dim_values, dim_default, dim_unit, setback_values, setback_default, setback_unit):
        super(PlotSetupDialog, self).__init__()
        self.BackgroundColor = make_color(*BH_BLACK)
        self.selected_length  = None
        self.selected_width   = None
        self.selected_setback = None
        self.dim_values    = dim_values
        self.dim_unit      = dim_unit
        self.setback_values = setback_values
        self.setback_unit   = setback_unit
        self.Title = "PLOT SETUP"
        self.Padding = drawing.Padding(0)
        self.Resizable = False
        self.MinimumSize = drawing.Size(560, 820)

        # ── Header ───────────────────────────────────────────────────────────
        header_panel = forms.Panel()
        header_panel.BackgroundColor = make_color(*dialog_header_bg_rgb())
        header_panel.Padding = drawing.Padding(20, 16, 20, 16)
        header_icon = forms.ImageView()
        header_icon.Image = get_arch_dialog_icon("PLOT DIMENSIONS", size=48)
        header_icon.Size = drawing.Size(48, 48)
        header_title = forms.Label()
        header_title.Text = "PLOT SETUP"
        header_title.Font = drawing.Font(drawing.FontFamily("Impact"), 16, drawing.FontStyle.Bold)
        header_title.TextColor = make_color(*BH_WHITE)
        accent_strip = forms.Panel()
        accent_strip.BackgroundColor = make_color(*DIALOG_ACCENT_BLUE)
        accent_strip.Height = 4
        header_layout = forms.TableLayout()
        header_layout.Spacing = drawing.Size(12, 0)
        header_row = forms.TableRow()
        header_row.Cells.Add(forms.TableCell(header_icon, False))
        header_row.Cells.Add(forms.TableCell(header_title, True))
        header_layout.Rows.Add(header_row)
        header_panel.Content = header_layout

        # ── Body ─────────────────────────────────────────────────────────────
        body_panel = forms.Panel()
        body_panel.BackgroundColor = make_color(*dialog_body_bg_rgb())
        body_panel.Padding = drawing.Padding(24, 18, 24, 18)

        # Find default dim index
        dim_default_index = 0
        for i, v in enumerate(dim_values):
            if v == dim_default:
                dim_default_index = i
                break

        def make_slider_block(label_text):
            sec_label = forms.Label()
            sec_label.Text = label_text
            sec_label.Font = drawing.Font(drawing.FontFamily("Georgia"), 11, drawing.FontStyle.Bold)
            sec_label.TextColor = make_color(*_SLIDER_BODY_TEXT)
            sep = forms.Panel()
            sep.BackgroundColor = make_color(*DIALOG_ACCENT_BLUE)
            sep.Height = 3
            tick_layout = forms.TableLayout()
            tick_layout.Spacing = drawing.Size(0, 0)
            tick_row = forms.TableRow()
            for v in dim_values:
                tl = forms.Label()
                tl.Text = str(int(v)) if v == int(v) else str(v)
                tl.Font = drawing.Font(drawing.FontFamily("Arial Narrow"), 10, drawing.FontStyle.Bold)
                tl.TextColor = make_color(*_SLIDER_TICK_TEXT)
                tl.TextAlignment = forms.TextAlignment.Center
                tick_row.Cells.Add(forms.TableCell(tl, True))
            tick_layout.Rows.Add(tick_row)
            slider = forms.Slider()
            slider.MinValue = 0
            slider.MaxValue = len(dim_values) - 1
            slider.SnapToTick = True
            slider.TickFrequency = 1
            slider.Orientation = forms.Orientation.Horizontal
            slider.Width = 480
            slider.Value = dim_default_index
            min_lbl = forms.Label()
            min_lbl.Text = "{} {}".format(int(dim_values[0]) if dim_values[0] == int(dim_values[0]) else dim_values[0], dim_unit)
            min_lbl.Font = drawing.Font(drawing.FontFamily("Arial Narrow"), 10, drawing.FontStyle.Bold)
            min_lbl.TextColor = make_color(*_SLIDER_RANGE_TEXT)
            max_lbl = forms.Label()
            max_lbl.Text = "{} {}".format(int(dim_values[-1]) if dim_values[-1] == int(dim_values[-1]) else dim_values[-1], dim_unit)
            max_lbl.Font = drawing.Font(drawing.FontFamily("Arial Narrow"), 10, drawing.FontStyle.Bold)
            max_lbl.TextColor = make_color(*_SLIDER_RANGE_TEXT)
            max_lbl.TextAlignment = forms.TextAlignment.Right
            range_layout = forms.TableLayout()
            range_layout.Spacing = drawing.Size(0, 0)
            range_row = forms.TableRow()
            range_row.Cells.Add(forms.TableCell(min_lbl, False))
            range_row.Cells.Add(forms.TableCell(None, True))
            range_row.Cells.Add(forms.TableCell(max_lbl, False))
            range_layout.Rows.Add(range_row)
            init_v = dim_values[dim_default_index]
            init_display = "{} {}".format(int(init_v) if init_v == int(init_v) else init_v, dim_unit)
            sel_lbl = forms.Label()
            sel_lbl.Text = "Selected:  {}".format(init_display)
            sel_lbl.Font = drawing.Font(drawing.FontFamily("Impact"), 14, drawing.FontStyle.Bold)
            sel_lbl.TextColor = make_color(*_SLIDER_SELECTED_FG)
            sel_lbl.TextAlignment = forms.TextAlignment.Center
            block = forms.TableLayout()
            block.Spacing = drawing.Size(0, 8)
            block.Rows.Add(forms.TableRow(forms.TableCell(sec_label, True)))
            block.Rows.Add(forms.TableRow(forms.TableCell(sep, True)))
            block.Rows.Add(forms.TableRow(forms.TableCell(tick_layout, True)))
            block.Rows.Add(forms.TableRow(forms.TableCell(slider, True)))
            block.Rows.Add(forms.TableRow(forms.TableCell(range_layout, True)))
            block.Rows.Add(forms.TableRow(forms.TableCell(sel_lbl, True)))
            return block, slider, sel_lbl

        length_block, self.length_slider, self.length_sel_label = make_slider_block("Select PLOT LENGTH (20-50m)")
        width_block,  self.width_slider,  self.width_sel_label  = make_slider_block("Select PLOT WIDTH  (20-50m)")
        self.length_slider.ValueChanged += self.on_length_changed
        self.width_slider.ValueChanged  += self.on_width_changed

        # Grey divider
        div1 = forms.Panel()
        div1.BackgroundColor = make_color(*BH_MID_GREY)
        div1.Height = 2

        # ── Setback section ──────────────────────────────────────────────────
        setback_sec_label = forms.Label()
        setback_sec_label.Text = "Select SETBACK DISTANCE"
        setback_sec_label.Font = drawing.Font(drawing.FontFamily("Georgia"), 11, drawing.FontStyle.Bold)
        setback_sec_label.TextColor = make_color(*_SLIDER_BODY_TEXT)
        setback_sep = forms.Panel()
        setback_sep.BackgroundColor = make_color(*DIALOG_ACCENT_BLUE)
        setback_sep.Height = 3
        setback_labels = ["{} {}".format(v, setback_unit) for v in setback_values]
        setback_default_label = "{} {}".format(setback_default, setback_unit)
        self.setback_list = forms.ListBox()
        try_set_control_colors(self.setback_list, bg_rgb=DIALOG_SURFACE_INPUT, text_rgb=DIALOG_TEXT_PRIMARY)
        self.setback_list.Font = drawing.Font(drawing.FontFamily("Impact"), 13, drawing.FontStyle.Bold)
        self.setback_list.Height = 150
        for lbl in setback_labels:
            self.setback_list.Items.Add(str(lbl))
        setback_default_index = 0
        for i, lbl in enumerate(setback_labels):
            if lbl == setback_default_label:
                setback_default_index = i
                break
        self.setback_list.SelectedIndex = setback_default_index
        self.setback_list.SelectedIndexChanged += self.on_setback_changed
        self.setback_sel_label = forms.Label()
        self.setback_sel_label.Text = "Selected:  {}".format(setback_default_label)
        self.setback_sel_label.Font = drawing.Font(drawing.FontFamily("Impact"), 14, drawing.FontStyle.Bold)
        self.setback_sel_label.TextColor = make_color(*_SLIDER_SELECTED_FG)
        self.setback_sel_label.TextAlignment = forms.TextAlignment.Center

        div2 = forms.Panel()
        div2.BackgroundColor = make_color(*BH_MID_GREY)
        div2.Height = 2

        # ── Buttons ──────────────────────────────────────────────────────────
        ok_button = forms.Button()
        ok_button.Text = "  CONFIRM  "
        ok_button.Font = drawing.Font(drawing.FontFamily("Impact"), 13, drawing.FontStyle.Bold)
        ok_button.BackgroundColor = make_color(*DIALOG_ACCENT_GREEN)
        ok_button.TextColor = make_color(*BH_PURE_WHITE)
        ok_button.Size = drawing.Size(190, 46)
        ok_button.Click += self.on_ok_clicked
        cancel_button = forms.Button()
        cancel_button.Text = "  ABORT  "
        cancel_button.Font = drawing.Font(drawing.FontFamily("Georgia"), 11, drawing.FontStyle.Italic)
        cancel_button.Size = drawing.Size(130, 46)
        cancel_button.BackgroundColor = make_color(*DIALOG_CANCEL_BG)
        cancel_button.TextColor = make_color(*DIALOG_CANCEL_TEXT)
        cancel_button.Click += self.on_cancel_clicked
        button_layout = forms.TableLayout()
        button_layout.Spacing = drawing.Size(16, 0)
        button_row = forms.TableRow()
        button_row.Cells.Add(forms.TableCell(None, True))
        button_row.Cells.Add(forms.TableCell(cancel_button, False))
        button_row.Cells.Add(forms.TableCell(ok_button, False))
        button_layout.Rows.Add(button_row)

        body_layout = forms.TableLayout()
        body_layout.Spacing = drawing.Size(0, 14)
        body_layout.Rows.Add(forms.TableRow(forms.TableCell(length_block, True)))
        body_layout.Rows.Add(forms.TableRow(forms.TableCell(div1, True)))
        body_layout.Rows.Add(forms.TableRow(forms.TableCell(width_block, True)))
        body_layout.Rows.Add(forms.TableRow(forms.TableCell(div2, True)))
        body_layout.Rows.Add(forms.TableRow(forms.TableCell(setback_sec_label, True)))
        body_layout.Rows.Add(forms.TableRow(forms.TableCell(setback_sep, True)))
        body_layout.Rows.Add(forms.TableRow(forms.TableCell(self.setback_list, True)))
        body_layout.Rows.Add(forms.TableRow(forms.TableCell(self.setback_sel_label, True)))
        body_layout.Rows.Add(forms.TableRow(forms.TableCell(button_layout, True)))
        body_panel.Content = body_layout

        main_layout = forms.TableLayout()
        main_layout.Spacing = drawing.Size(0, 0)
        main_layout.Rows.Add(forms.TableRow(forms.TableCell(header_panel, True)))
        main_layout.Rows.Add(forms.TableRow(forms.TableCell(accent_strip, True)))
        main_layout.Rows.Add(forms.TableRow(forms.TableCell(body_panel, True)))
        self.Content = main_layout

    def _dim_value(self, slider):
        idx = slider.Value
        if 0 <= idx < len(self.dim_values):
            return self.dim_values[idx]
        return self.dim_values[0]

    def _fmt_dim(self, v):
        return "{} {}".format(int(v) if v == int(v) else v, self.dim_unit)

    def on_length_changed(self, sender, e):
        self.length_sel_label.Text = "Selected:  {}".format(self._fmt_dim(self._dim_value(self.length_slider)))

    def on_width_changed(self, sender, e):
        self.width_sel_label.Text = "Selected:  {}".format(self._fmt_dim(self._dim_value(self.width_slider)))

    def on_setback_changed(self, sender, e):
        if self.setback_list.SelectedIndex >= 0:
            self.setback_sel_label.Text = "Selected:  {}".format(str(self.setback_list.Items[self.setback_list.SelectedIndex]))

    def on_ok_clicked(self, sender, e):
        self.selected_length  = self._dim_value(self.length_slider)
        self.selected_width   = self._dim_value(self.width_slider)
        if self.setback_list.SelectedIndex >= 0:
            raw = str(self.setback_list.Items[self.setback_list.SelectedIndex])
            self.selected_setback = get_number_from_label(raw)
        self.Close(True)

    def on_cancel_clicked(self, sender, e):
        self.selected_length  = None
        self.selected_width   = None
        self.selected_setback = None
        self.Close(False)


# ============================================================ DIALOG CLASS 1d: STRUCTURAL PARAMETERS + HOUSE BOUNDARY SELECTION ============================================================
# ── Small parameter row icons (28×28) for StructuralAndBoundaryDialog ──
def _icon_param_grid_spacing(size=28):
    """Grid spacing: grid lines with intersection dots and dimension arrow."""
    bmp = drawing.Bitmap(size, size, drawing.PixelFormat.Format32bppRgba)
    g = drawing.Graphics(bmp)
    try:
        g.AntiAlias = True
        g.FillRectangle(_icon_brush(BH_BLACK), 0, 0, size, size)
        s = size / 28.0
        pen = _icon_pen(BH_WHITE, 0.8)
        # Grid lines
        for v in [7, 14, 21]:
            g.DrawLine(pen, int(v*s), int(3*s), int(v*s), int(25*s))
            g.DrawLine(pen, int(3*s), int(v*s), int(25*s), int(v*s))
        # Dots
        for gx in [7, 14, 21]:
            for gy in [7, 14, 21]:
                g.FillEllipse(_icon_brush(BH_RED), int(gx*s)-2, int(gy*s)-2, 4, 4)
        # Dimension arrow top
        g.DrawLine(_icon_pen(BH_ORANGE, 1), int(7*s), int(2*s), int(14*s), int(2*s))
        g.DrawLine(_icon_pen(BH_ORANGE, 0.6), int(7*s), int(1*s), int(7*s), int(3*s))
        g.DrawLine(_icon_pen(BH_ORANGE, 0.6), int(14*s), int(1*s), int(14*s), int(3*s))
    finally:
        g.Dispose()
    return bmp

def _icon_param_column_width(size=28):
    """Column width: column cross-section with wood grain and W dimension."""
    bmp = drawing.Bitmap(size, size, drawing.PixelFormat.Format32bppRgba)
    g = drawing.Graphics(bmp)
    try:
        g.AntiAlias = True
        g.FillRectangle(_icon_brush(BH_BLACK), 0, 0, size, size)
        s = size / 28.0
        # Column rect
        g.DrawRectangle(_icon_pen(BH_WHITE, 1.5), drawing.RectangleF(7*s, 4*s, 14*s, 20*s))
        # Wood grain wavy lines
        for gx in [10, 14, 18]:
            g.DrawLine(_icon_pen(BH_WHITE, 0.3), int(gx*s), int(5*s), int(gx*s), int(23*s))
        # Width dimension top
        g.DrawLine(_icon_pen(BH_ORANGE, 0.8), int(7*s), int(2*s), int(21*s), int(2*s))
        g.DrawLine(_icon_pen(BH_ORANGE, 0.5), int(7*s), int(1*s), int(7*s), int(3*s))
        g.DrawLine(_icon_pen(BH_ORANGE, 0.5), int(21*s), int(1*s), int(21*s), int(3*s))
    finally:
        g.Dispose()
    return bmp

def _icon_param_column_height(size=28):
    """Column height: vertical column on ground with H dimension."""
    bmp = drawing.Bitmap(size, size, drawing.PixelFormat.Format32bppRgba)
    g = drawing.Graphics(bmp)
    try:
        g.AntiAlias = True
        g.FillRectangle(_icon_brush(BH_BLACK), 0, 0, size, size)
        s = size / 28.0
        # Column
        g.DrawRectangle(_icon_pen(BH_WHITE, 1.5), drawing.RectangleF(9*s, 3*s, 8*s, 19*s))
        # Wood grain
        g.DrawLine(_icon_pen(BH_WHITE, 0.3), int(12*s), int(4*s), int(12*s), int(21*s))
        g.DrawLine(_icon_pen(BH_WHITE, 0.3), int(15*s), int(4*s), int(15*s), int(21*s))
        # Ground line
        g.DrawLine(_icon_pen(BH_WHITE, 1), int(3*s), int(22*s), int(25*s), int(22*s))
        # Ground hatch
        for hx in range(5, 24, 3):
            g.DrawLine(_icon_pen(BH_WHITE, 0.3), int((hx+2)*s), int(24*s), int(hx*s), int(22*s))
        # Beam at top
        g.DrawLine(_icon_pen(BH_WHITE, 1), int(4*s), int(3*s), int(22*s), int(3*s))
        # Height dimension right
        g.DrawLine(_icon_pen(BH_ORANGE, 0.8), int(21*s), int(3*s), int(21*s), int(22*s))
        g.DrawLine(_icon_pen(BH_ORANGE, 0.5), int(20*s), int(3*s), int(22*s), int(3*s))
        g.DrawLine(_icon_pen(BH_ORANGE, 0.5), int(20*s), int(22*s), int(22*s), int(22*s))
    finally:
        g.Dispose()
    return bmp

def _icon_param_beam_width(size=28):
    """Beam width: horizontal beam between two columns with W dimension."""
    bmp = drawing.Bitmap(size, size, drawing.PixelFormat.Format32bppRgba)
    g = drawing.Graphics(bmp)
    try:
        g.AntiAlias = True
        g.FillRectangle(_icon_brush(BH_BLACK), 0, 0, size, size)
        s = size / 28.0
        # Two columns
        g.DrawRectangle(_icon_pen(BH_WHITE, 1), drawing.RectangleF(3*s, 5*s, 4*s, 16*s))
        g.DrawRectangle(_icon_pen(BH_WHITE, 1), drawing.RectangleF(21*s, 5*s, 4*s, 16*s))
        # Beam
        g.FillRectangle(_icon_brush(BH_RED, 30), drawing.RectangleF(3*s, 5*s, 22*s, 5*s))
        g.DrawRectangle(_icon_pen(BH_WHITE, 1.5), drawing.RectangleF(3*s, 5*s, 22*s, 5*s))
        # Wood grain in beam
        g.DrawLine(_icon_pen(BH_WHITE, 0.3), int(5*s), int(7*s), int(23*s), int(7*s))
        g.DrawLine(_icon_pen(BH_WHITE, 0.3), int(5*s), int(9*s), int(23*s), int(9*s))
        # Depth dimension left
        g.DrawLine(_icon_pen(BH_ORANGE, 0.8), int(1*s), int(5*s), int(1*s), int(10*s))
        g.DrawLine(_icon_pen(BH_ORANGE, 0.5), int(0*s), int(5*s), int(2*s), int(5*s))
        g.DrawLine(_icon_pen(BH_ORANGE, 0.5), int(0*s), int(10*s), int(2*s), int(10*s))
        # Ground
        g.DrawLine(_icon_pen(BH_WHITE, 0.8), int(2*s), int(22*s), int(26*s), int(22*s))
        for hx in range(3, 25, 3):
            g.DrawLine(_icon_pen(BH_WHITE, 0.3), int((hx+2)*s), int(24*s), int(hx*s), int(22*s))
    finally:
        g.Dispose()
    return bmp

def _icon_param_grid_extension(size=28):
    """Grid extension: cantilever beam extending from column."""
    bmp = drawing.Bitmap(size, size, drawing.PixelFormat.Format32bppRgba)
    g = drawing.Graphics(bmp)
    try:
        g.AntiAlias = True
        g.FillRectangle(_icon_brush(BH_BLACK), 0, 0, size, size)
        s = size / 28.0
        # Centre column
        g.DrawRectangle(_icon_pen(BH_WHITE, 1.2), drawing.RectangleF(10*s, 4*s, 5*s, 18*s))
        # Wood grain
        g.DrawLine(_icon_pen(BH_WHITE, 0.3), int(12*s), int(5*s), int(12*s), int(21*s))
        # Beam through column
        g.FillRectangle(_icon_brush(BH_RED, 30), drawing.RectangleF(10*s, 4*s, 5*s, 3*s))
        g.DrawRectangle(_icon_pen(BH_WHITE, 1.2), drawing.RectangleF(10*s, 4*s, 5*s, 3*s))
        # Left cantilever
        g.FillRectangle(_icon_brush(BH_RED, 15), drawing.RectangleF(2*s, 4*s, 8*s, 3*s))
        g.DrawRectangle(_icon_pen(BH_WHITE, 0.8), drawing.RectangleF(2*s, 4*s, 8*s, 3*s))
        # Right cantilever
        g.FillRectangle(_icon_brush(BH_RED, 15), drawing.RectangleF(15*s, 4*s, 11*s, 3*s))
        g.DrawRectangle(_icon_pen(BH_WHITE, 0.8), drawing.RectangleF(15*s, 4*s, 11*s, 3*s))
        # Extension arrows
        g.DrawLine(_icon_pen(BH_ORANGE, 0.8), int(2*s), int(10*s), int(10*s), int(10*s))
        g.DrawLine(_icon_pen(BH_ORANGE, 0.8), int(15*s), int(10*s), int(26*s), int(10*s))
        # Dashed projection lines
        pen_dash = drawing.Pen(make_color(*BH_WHITE), 0.4)
        try:
            pen_dash.DashStyle = drawing.DashStyle.Dash
        except:
            pass
        g.DrawLine(pen_dash, int(2*s), int(7*s), int(2*s), int(22*s))
        g.DrawLine(pen_dash, int(26*s), int(7*s), int(26*s), int(22*s))
        # Ground
        g.DrawLine(_icon_pen(BH_WHITE, 0.8), int(1*s), int(23*s), int(27*s), int(23*s))
        for hx in range(2, 26, 3):
            g.DrawLine(_icon_pen(BH_WHITE, 0.3), int((hx+2)*s), int(25*s), int(hx*s), int(23*s))
    finally:
        g.Dispose()
    return bmp


class StructuralAndBoundaryDialog(forms.Dialog[bool]):
    """Combined dialog: auto-calculated structural parameters (info) + boundary selection prompt."""
    def __init__(self, grid_spacing, column_width, column_height, beam_width, grid_extension, span_note):
        super(StructuralAndBoundaryDialog, self).__init__()
        self.BackgroundColor = make_color(*BH_BLACK)
        self.Title = "STRUCTURAL & DESIGN PARAMETERS"
        self.Padding = drawing.Padding(0)
        self.Resizable = False
        self.MinimumSize = drawing.Size(560, 900)

        # ── Header ───────────────────────────────────────────────────────────
        header_panel = forms.Panel()
        header_panel.BackgroundColor = make_color(*dialog_header_bg_rgb())
        header_panel.Padding = drawing.Padding(20, 16, 20, 16)
        header_icon = forms.ImageView()
        header_icon.Image = get_arch_dialog_icon("GRID COLUMN", size=48)
        header_icon.Size = drawing.Size(48, 48)
        header_title = forms.Label()
        header_title.Text = "STRUCTURAL & DESIGN PARAMETERS"
        header_title.Font = drawing.Font(drawing.FontFamily("Impact"), 16, drawing.FontStyle.Bold)
        header_title.TextColor = make_color(*BH_WHITE)
        accent_strip = forms.Panel()
        accent_strip.BackgroundColor = make_color(*DIALOG_ACCENT_BLUE)
        accent_strip.Height = 4
        header_layout = forms.TableLayout()
        header_layout.Spacing = drawing.Size(12, 0)
        header_row = forms.TableRow()
        header_row.Cells.Add(forms.TableCell(header_icon, False))
        header_row.Cells.Add(forms.TableCell(header_title, True))
        header_layout.Rows.Add(header_row)
        header_panel.Content = header_layout

        # ── Body ─────────────────────────────────────────────────────────────
        body_panel = forms.Panel()
        body_panel.BackgroundColor = make_color(*dialog_body_bg_rgb())
        body_panel.Padding = drawing.Padding(28, 18, 28, 18)

        def make_row(param_name, value_text, note_text=None, icon_bmp=None):
            row_panel = forms.Panel()
            row_panel.BackgroundColor = make_color(*BH_BLACK_LIFT)
            row_panel.Padding = drawing.Padding(14, 12, 14, 12)
            # Optional icon
            icon_view = None
            if icon_bmp is not None:
                icon_view = forms.ImageView()
                icon_view.Image = icon_bmp
                icon_view.Size = drawing.Size(28, 28)
            name_lbl = forms.Label()
            name_lbl.Text = param_name
            name_lbl.Font = drawing.Font(drawing.FontFamily("Georgia"), 10, drawing.FontStyle.Bold)
            name_lbl.TextColor = make_color(*BH_OFF_WHITE)
            badge_lbl = forms.Label()
            badge_lbl.Text = "AUTO-SELECTED"
            badge_lbl.Font = drawing.Font(drawing.FontFamily("Georgia"), 8, drawing.FontStyle.Italic)
            badge_lbl.TextColor = make_color(*BH_WHITE)
            val_lbl = forms.Label()
            val_lbl.Text = value_text
            val_lbl.Font = drawing.Font(drawing.FontFamily("Impact"), 22, drawing.FontStyle.Bold)
            val_lbl.TextColor = make_color(*BH_WHITE)
            val_lbl.TextAlignment = forms.TextAlignment.Right
            top_row_layout = forms.TableLayout()
            top_row_layout.Spacing = drawing.Size(10, 0)
            top_row = forms.TableRow()
            # Icon + name/badge column
            name_col_layout = forms.TableLayout()
            name_col_layout.Spacing = drawing.Size(0, 2)
            if icon_view is not None:
                # Icon + name on same row
                icon_name_row = forms.TableLayout()
                icon_name_row.Spacing = drawing.Size(8, 0)
                inr = forms.TableRow()
                inr.Cells.Add(forms.TableCell(icon_view, False))
                name_badge = forms.TableLayout()
                name_badge.Spacing = drawing.Size(0, 2)
                name_badge.Rows.Add(forms.TableRow(forms.TableCell(name_lbl, True)))
                name_badge.Rows.Add(forms.TableRow(forms.TableCell(badge_lbl, True)))
                inr.Cells.Add(forms.TableCell(name_badge, True))
                icon_name_row.Rows.Add(inr)
                name_col_layout.Rows.Add(forms.TableRow(forms.TableCell(icon_name_row, True)))
            else:
                name_col_layout.Rows.Add(forms.TableRow(forms.TableCell(name_lbl, True)))
                name_col_layout.Rows.Add(forms.TableRow(forms.TableCell(badge_lbl, True)))
            top_row.Cells.Add(forms.TableCell(name_col_layout, True))
            top_row.Cells.Add(forms.TableCell(val_lbl, False))
            top_row_layout.Rows.Add(top_row)
            row_layout = forms.TableLayout()
            row_layout.Spacing = drawing.Size(0, 6)
            row_layout.Rows.Add(forms.TableRow(forms.TableCell(top_row_layout, True)))
            if note_text:
                note_lbl = forms.Label()
                note_lbl.Text = note_text
                note_lbl.Font = drawing.Font(drawing.FontFamily("Arial Narrow"), 9, drawing.FontStyle.Italic)
                note_lbl.TextColor = make_color(*BH_MID_GREY)
                note_lbl.Wrap = forms.WrapMode.Word
                row_layout.Rows.Add(forms.TableRow(forms.TableCell(note_lbl, True)))
            row_panel.Content = row_layout
            return row_panel

        # Caption
        caption = forms.Label()
        caption.Text = "Auto-calculated per DIN 1052 / OWL timber code. No input required."
        caption.Font = drawing.Font(drawing.FontFamily("Georgia"), 10, drawing.FontStyle.Italic)
        caption.TextColor = make_color(*BH_OFF_WHITE)
        caption.Wrap = forms.WrapMode.Word

        sep1 = forms.Panel()
        sep1.BackgroundColor = make_color(*DIALOG_ACCENT_BLUE)
        sep1.Height = 3

        row_grid  = make_row("GRID SPACING",
                             "{:.0f} m".format(grid_spacing), span_note,
                             icon_bmp=_icon_param_grid_spacing())
        div1 = forms.Panel(); div1.BackgroundColor = make_color(*BH_DARK_GREY); div1.Height = 1
        row_col_w = make_row("COLUMN WIDTH",
                             "{} m".format(column_width),
                             "DIN 1052: span <= 3.5 m  ->  0.30 m   |   span > 3.5 m  ->  0.45 m",
                             icon_bmp=_icon_param_column_width())
        div2 = forms.Panel(); div2.BackgroundColor = make_color(*BH_DARK_GREY); div2.Height = 1
        row_col_h = make_row("BASEMENT COLUMN HEIGHT",
                             "{:.0f} m".format(column_height),
                             "Fixed at 1 m — standard basement plinth per OWL regional practice",
                             icon_bmp=_icon_param_column_height())
        div3 = forms.Panel(); div3.BackgroundColor = make_color(*BH_DARK_GREY); div3.Height = 1
        row_beam  = make_row("PLINTH BEAM WIDTH",
                             "{} m".format(beam_width),
                             "DIN 1052: matches column section — span <= 3.5 m -> 0.30 m  |  span > 3.5 m -> 0.45 m",
                             icon_bmp=_icon_param_beam_width())
        div4 = forms.Panel(); div4.BackgroundColor = make_color(*BH_DARK_GREY); div4.Height = 1
        row_ext   = make_row("GRID EXTENSION (ALL FLOORS)",
                             "{} m".format(grid_extension),
                             "Setback - 0.5 m safety margin, clamped 1.0-2.0 m — projection stays within plot boundary",
                             icon_bmp=_icon_param_grid_extension())

        # ── Boundary selection section ────────────────────────────────────────
        div_main = forms.Panel()
        div_main.BackgroundColor = make_color(*DIALOG_ACCENT_BLUE)
        div_main.Height = 3

        boundary_lbl = forms.Label()
        boundary_lbl.Text = "Select building boundary from grid points"
        boundary_lbl.Font = drawing.Font(drawing.FontFamily("Impact"), 16, drawing.FontStyle.Bold)
        boundary_lbl.TextColor = make_color(*BH_WHITE)
        boundary_lbl.TextAlignment = forms.TextAlignment.Center
        boundary_lbl.Wrap = forms.WrapMode.Word

        boundary_sub = forms.Label()
        boundary_sub.Text = "Click on the red grid points in the viewport to define your building outline. Close the polyline to finish."
        boundary_sub.Font = drawing.Font(drawing.FontFamily("Georgia"), 10, drawing.FontStyle.Italic)
        boundary_sub.TextColor = make_color(*BH_OFF_WHITE)
        boundary_sub.TextAlignment = forms.TextAlignment.Center
        boundary_sub.Wrap = forms.WrapMode.Word

        # Buttons
        ok_button = forms.Button()
        ok_button.Text = "  START SELECTION  "
        ok_button.Font = drawing.Font(drawing.FontFamily("Impact"), 13, drawing.FontStyle.Bold)
        ok_button.BackgroundColor = make_color(*DIALOG_ACCENT_GREEN)
        ok_button.TextColor = make_color(*BH_PURE_WHITE)
        ok_button.Size = drawing.Size(220, 46)
        ok_button.Click += self.on_ok_clicked
        cancel_button = forms.Button()
        cancel_button.Text = "  ABORT  "
        cancel_button.Font = drawing.Font(drawing.FontFamily("Georgia"), 11, drawing.FontStyle.Italic)
        cancel_button.Size = drawing.Size(130, 46)
        cancel_button.BackgroundColor = make_color(*DIALOG_CANCEL_BG)
        cancel_button.TextColor = make_color(*DIALOG_CANCEL_TEXT)
        cancel_button.Click += self.on_cancel_clicked
        button_layout = forms.TableLayout()
        button_layout.Spacing = drawing.Size(16, 0)
        button_row = forms.TableRow()
        button_row.Cells.Add(forms.TableCell(None, True))
        button_row.Cells.Add(forms.TableCell(cancel_button, False))
        button_row.Cells.Add(forms.TableCell(ok_button, False))
        button_layout.Rows.Add(button_row)

        body_layout = forms.TableLayout()
        body_layout.Spacing = drawing.Size(0, 10)
        body_layout.Rows.Add(forms.TableRow(forms.TableCell(caption, True)))
        body_layout.Rows.Add(forms.TableRow(forms.TableCell(sep1, True)))
        body_layout.Rows.Add(forms.TableRow(forms.TableCell(row_grid, True)))
        body_layout.Rows.Add(forms.TableRow(forms.TableCell(div1, True)))
        body_layout.Rows.Add(forms.TableRow(forms.TableCell(row_col_w, True)))
        body_layout.Rows.Add(forms.TableRow(forms.TableCell(div2, True)))
        body_layout.Rows.Add(forms.TableRow(forms.TableCell(row_col_h, True)))
        body_layout.Rows.Add(forms.TableRow(forms.TableCell(div3, True)))
        body_layout.Rows.Add(forms.TableRow(forms.TableCell(row_beam, True)))
        body_layout.Rows.Add(forms.TableRow(forms.TableCell(div4, True)))
        body_layout.Rows.Add(forms.TableRow(forms.TableCell(row_ext, True)))
        body_layout.Rows.Add(forms.TableRow(forms.TableCell(div_main, True)))
        body_layout.Rows.Add(forms.TableRow(forms.TableCell(boundary_lbl, True)))
        body_layout.Rows.Add(forms.TableRow(forms.TableCell(boundary_sub, True)))
        body_layout.Rows.Add(forms.TableRow(forms.TableCell(button_layout, True)))
        body_panel.Content = body_layout

        main_layout = forms.TableLayout()
        main_layout.Spacing = drawing.Size(0, 0)
        main_layout.Rows.Add(forms.TableRow(forms.TableCell(header_panel, True)))
        main_layout.Rows.Add(forms.TableRow(forms.TableCell(accent_strip, True)))
        main_layout.Rows.Add(forms.TableRow(forms.TableCell(body_panel, True)))
        self.Content = main_layout

    def on_ok_clicked(self, sender, e):
        self.Close(True)

    def on_cancel_clicked(self, sender, e):
        self.Close(False)

# ============================================================ DIALOG CLASS 2: VERTICAL LISTBOX ============================================================
class VibrantListDialog(forms.Dialog[bool]):
    def __init__(self, title_text, message_text, labels, default_label, icon_emoji, header_color, bg_color):
        super(VibrantListDialog, self).__init__()
        self.BackgroundColor = make_color(*BH_BLACK)
        self.selected_value = None
        self.Title = str(title_text)
        self.Padding = drawing.Padding(0)
        self.Resizable = False
        self.MinimumSize = drawing.Size(520, 560)
        header_panel = forms.Panel()
        header_panel.BackgroundColor = make_color(*dialog_header_bg_rgb())
        header_panel.Padding = drawing.Padding(20, 16, 20, 16)
        header_icon_label = forms.ImageView()
        header_icon_label.Image = get_arch_dialog_icon(str(title_text), size=48)
        header_icon_label.Size = drawing.Size(48, 48)
        header_title_label = forms.Label()
        header_title_label.Text = str(title_text)
        header_title_label.Font = drawing.Font(drawing.FontFamily("Impact"), 16, drawing.FontStyle.Bold)
        header_title_label.TextColor = make_color(*BH_WHITE)
        accent_strip = forms.Panel()
        accent_strip.BackgroundColor = make_color(*DIALOG_ACCENT_PINK)
        accent_strip.Height = 4
        header_layout = forms.TableLayout()
        header_layout.Spacing = drawing.Size(12, 0)
        header_row = forms.TableRow()
        header_row.Cells.Add(forms.TableCell(header_icon_label, False))
        header_row.Cells.Add(forms.TableCell(header_title_label, True))
        header_layout.Rows.Add(header_row)
        header_panel.Content = header_layout
        body_panel = forms.Panel()
        body_panel.BackgroundColor = make_color(*dialog_body_bg_rgb())
        body_panel.Padding = drawing.Padding(24, 18, 24, 18)
        message_label = forms.Label()
        message_label.Text = str(message_text)
        message_label.Font = drawing.Font(drawing.FontFamily("Georgia"), 11, drawing.FontStyle.Bold)
        message_label.TextColor = make_color(*DIALOG_TEXT_SECONDARY)
        message_label.Wrap = forms.WrapMode.Word
        separator = forms.Panel()
        separator.BackgroundColor = make_color(*DIALOG_ACCENT_PINK)
        separator.Height = 4
        self.list_box = forms.ListBox()
        try_set_control_colors(self.list_box, bg_rgb=DIALOG_SURFACE_INPUT, text_rgb=DIALOG_TEXT_PRIMARY)
        self.list_box.Font = drawing.Font(drawing.FontFamily("Impact"), 13, drawing.FontStyle.Bold)
        self.list_box.Height = 250
        for label in labels:
            self.list_box.Items.Add(str(label))
        default_index = 0
        for i in range(len(labels)):
            if str(labels[i]) == str(default_label):
                default_index = i
                break
        self.list_box.SelectedIndex = default_index
        self.list_box.SelectedIndexChanged += self.on_list_changed
        self.selection_label = forms.Label()
        self.selection_label.Text = "Selected:  {}".format(str(default_label))
        self.selection_label.Font = drawing.Font(drawing.FontFamily("Impact"), 14, drawing.FontStyle.Bold)
        self.selection_label.TextColor = make_color(*_BODY_SEL_COLOR)
        ok_button = forms.Button()
        ok_button.Text = "  CONFIRM  "
        ok_button.Font = drawing.Font(drawing.FontFamily("Impact"), 13, drawing.FontStyle.Bold)
        ok_button.BackgroundColor = make_color(*DIALOG_ACCENT_GREEN)
        ok_button.TextColor = make_color(*BH_PURE_WHITE)
        ok_button.Size = drawing.Size(190, 46)
        ok_button.Click += self.on_ok_clicked
        cancel_button = forms.Button()
        cancel_button.Text = "  ABORT  "
        cancel_button.Font = drawing.Font(drawing.FontFamily("Georgia"), 11, drawing.FontStyle.Italic)
        cancel_button.Size = drawing.Size(130, 46)
        cancel_button.BackgroundColor = make_color(*DIALOG_CANCEL_BG)
        cancel_button.TextColor = make_color(*DIALOG_CANCEL_TEXT)
        cancel_button.Click += self.on_cancel_clicked
        button_layout = forms.TableLayout()
        button_layout.Spacing = drawing.Size(16, 0)
        button_row = forms.TableRow()
        button_row.Cells.Add(forms.TableCell(None, True))
        button_row.Cells.Add(forms.TableCell(cancel_button, False))
        button_row.Cells.Add(forms.TableCell(ok_button, False))
        button_layout.Rows.Add(button_row)
        body_layout = forms.TableLayout()
        body_layout.Spacing = drawing.Size(0, 12)
        body_layout.Rows.Add(forms.TableRow(forms.TableCell(message_label, True)))
        body_layout.Rows.Add(forms.TableRow(forms.TableCell(separator, True)))
        body_layout.Rows.Add(forms.TableRow(forms.TableCell(self.list_box, True)))
        body_layout.Rows.Add(forms.TableRow(forms.TableCell(self.selection_label, True)))
        body_layout.Rows.Add(forms.TableRow(forms.TableCell(button_layout, True)))
        body_panel.Content = body_layout
        main_layout = forms.TableLayout()
        main_layout.Spacing = drawing.Size(0, 0)
        main_layout.Rows.Add(forms.TableRow(forms.TableCell(header_panel, True)))
        main_layout.Rows.Add(forms.TableRow(forms.TableCell(accent_strip, True)))
        main_layout.Rows.Add(forms.TableRow(forms.TableCell(body_panel, True)))
        self.Content = main_layout

    def on_list_changed(self, sender, e):
        if self.list_box.SelectedIndex >= 0:
            self.selection_label.Text = "Selected:  {}".format(str(self.list_box.Items[self.list_box.SelectedIndex]))

    def on_ok_clicked(self, sender, e):
        if self.list_box.SelectedIndex >= 0:
            self.selected_value = str(self.list_box.Items[self.list_box.SelectedIndex])
        self.Close(True)

    def on_cancel_clicked(self, sender, e):
        self.selected_value = None
        self.Close(False)


# ============================================================ CUSTOM FLOOR COUNT DIALOG ============================================================
class FloorCountDialog(forms.Dialog[bool]):
    def __init__(self):
        super(FloorCountDialog, self).__init__()
        self.BackgroundColor = make_color(*BH_BLACK)
        self.selected_upper_floors = 0
        self.selected_floor_height = 3.0
        self.Title = "NUMBER OF FLOORS & HEIGHT"
        self.Padding = drawing.Padding(0)
        self.Resizable = False
        self.MinimumSize = drawing.Size(560, 680)
        header_panel = forms.Panel()
        header_panel.BackgroundColor = make_color(*dialog_header_bg_rgb())
        header_panel.Padding = drawing.Padding(20, 16, 20, 16)
        accent_strip = forms.Panel()
        accent_strip.BackgroundColor = make_color(*DIALOG_ACCENT_ORANGE)
        accent_strip.Height = 4
        header_icon = forms.ImageView()
        header_icon.Image = get_arch_dialog_icon("NUMBER OF FLOORS", size=48)
        header_icon.Size = drawing.Size(48, 48)
        header_title = forms.Label()
        header_title.Text = "NUMBER OF FLOORS & HEIGHT"
        header_title.Font = drawing.Font(drawing.FontFamily("Impact"), 16, drawing.FontStyle.Bold)
        header_title.TextColor = make_color(*BH_WHITE)
        header_layout = forms.TableLayout()
        header_layout.Spacing = drawing.Size(12, 0)
        header_row = forms.TableRow()
        header_row.Cells.Add(forms.TableCell(header_icon, False))
        header_row.Cells.Add(forms.TableCell(header_title, True))
        header_layout.Rows.Add(header_row)
        header_panel.Content = header_layout
        body_panel = forms.Panel()
        body_panel.BackgroundColor = make_color(*dialog_body_bg_rgb())
        body_panel.Padding = drawing.Padding(24, 18, 24, 18)
        info_label = forms.Label()
        info_label.Text = ("Basement columns are complete!\nSelect how many ADDITIONAL floors above ground.\n\nEvery floor always gets a ROOF on top.\nFloor height applies to ALL floors and the roof.\nFloors cascade inward (stepped terrace concept).")
        info_label.Font = drawing.Font(drawing.FontFamily("Georgia"), 11, drawing.FontStyle.Bold)
        info_label.TextColor = make_color(*DIALOG_TEXT_SECONDARY)
        info_label.Wrap = forms.WrapMode.Word
        separator = forms.Panel()
        separator.BackgroundColor = make_color(*DIALOG_ACCENT_ORANGE)
        separator.Height = 4
        self.radio0 = forms.RadioButton()
        self.radio0.Text = "  [0]  GROUND FLOOR ONLY  //  G + ROOF"
        self.radio0.Font = drawing.Font(drawing.FontFamily("Impact"), 13, drawing.FontStyle.Bold)
        try_set_control_colors(self.radio0, bg_rgb=None, text_rgb=DIALOG_TEXT_PRIMARY)
        self.radio0.Checked = True
        self.radio1 = forms.RadioButton(self.radio0)
        self.radio1.Text = "  [1]  GROUND + LEVEL 01  //  G+1 + ROOF"
        self.radio1.Font = drawing.Font(drawing.FontFamily("Georgia"), 11, drawing.FontStyle.Italic)
        try_set_control_colors(self.radio1, bg_rgb=None, text_rgb=DIALOG_TEXT_PRIMARY)
        self.radio2 = forms.RadioButton(self.radio0)
        self.radio2.Text = "  [2]  GROUND + LEVEL 02  //  G+2 + ROOF"
        self.radio2.Font = drawing.Font(drawing.FontFamily("Georgia"), 11, drawing.FontStyle.Italic)
        try_set_control_colors(self.radio2, bg_rgb=None, text_rgb=DIALOG_TEXT_PRIMARY)
        self.radio3 = forms.RadioButton(self.radio0)
        self.radio3.Text = "  [3]  GROUND + LEVEL 03  //  G+3 + ROOF"
        self.radio3.Font = drawing.Font(drawing.FontFamily("Georgia"), 11, drawing.FontStyle.Italic)
        try_set_control_colors(self.radio3, bg_rgb=None, text_rgb=DIALOG_TEXT_PRIMARY)
        self.radio4 = forms.RadioButton(self.radio0)
        self.radio4.Text = "  [4]  GROUND + LEVEL 04  //  G+4 + ROOF"
        self.radio4.Font = drawing.Font(drawing.FontFamily("Georgia"), 11, drawing.FontStyle.Italic)
        try_set_control_colors(self.radio4, bg_rgb=None, text_rgb=DIALOG_TEXT_PRIMARY)

        # ── Floor height slider ───────────────────────────────────────────────
        div_height = forms.Panel()
        div_height.BackgroundColor = make_color(*DIALOG_ACCENT_ORANGE)
        div_height.Height = 3
        height_title = forms.Label()
        height_title.Text = "FLOOR HEIGHT (applies to ALL floors + roof)"
        height_title.Font = drawing.Font(drawing.FontFamily("Georgia"), 10, drawing.FontStyle.Bold)
        height_title.TextColor = make_color(*BH_OFF_WHITE)
        self._height_values = [3.0, 4.0, 5.0, 6.0]
        tick_layout = forms.TableLayout()
        tick_layout.Spacing = drawing.Size(0, 0)
        tick_row = forms.TableRow()
        for v in self._height_values:
            tl = forms.Label()
            tl.Text = "{:.0f}".format(v)
            tl.Font = drawing.Font(drawing.FontFamily("Arial Narrow"), 10, drawing.FontStyle.Bold)
            tl.TextColor = make_color(*_SLIDER_TICK_TEXT)
            tl.TextAlignment = forms.TextAlignment.Center
            tick_row.Cells.Add(forms.TableCell(tl, True))
        tick_layout.Rows.Add(tick_row)
        self.height_slider = forms.Slider()
        self.height_slider.MinValue = 0
        self.height_slider.MaxValue = len(self._height_values) - 1
        self.height_slider.SnapToTick = True
        self.height_slider.TickFrequency = 1
        self.height_slider.Orientation = forms.Orientation.Horizontal
        self.height_slider.Value = 0
        self.height_slider.ValueChanged += self.on_height_changed
        min_lbl = forms.Label()
        min_lbl.Text = "3 metres"
        min_lbl.Font = drawing.Font(drawing.FontFamily("Arial Narrow"), 10, drawing.FontStyle.Bold)
        min_lbl.TextColor = make_color(*_SLIDER_RANGE_TEXT)
        max_lbl = forms.Label()
        max_lbl.Text = "6 metres"
        max_lbl.Font = drawing.Font(drawing.FontFamily("Arial Narrow"), 10, drawing.FontStyle.Bold)
        max_lbl.TextColor = make_color(*_SLIDER_RANGE_TEXT)
        max_lbl.TextAlignment = forms.TextAlignment.Right
        range_layout = forms.TableLayout()
        range_layout.Spacing = drawing.Size(0, 0)
        range_row = forms.TableRow()
        range_row.Cells.Add(forms.TableCell(min_lbl, False))
        range_row.Cells.Add(forms.TableCell(None, True))
        range_row.Cells.Add(forms.TableCell(max_lbl, False))
        range_layout.Rows.Add(range_row)
        self.height_sel_label = forms.Label()
        self.height_sel_label.Text = "Selected:  3 metres"
        self.height_sel_label.Font = drawing.Font(drawing.FontFamily("Impact"), 14, drawing.FontStyle.Bold)
        self.height_sel_label.TextColor = make_color(*_SLIDER_SELECTED_FG)
        self.height_sel_label.TextAlignment = forms.TextAlignment.Center

        ok_button = forms.Button()
        ok_button.Text = "  CONFIRM  "
        ok_button.Font = drawing.Font(drawing.FontFamily("Impact"), 13, drawing.FontStyle.Bold)
        ok_button.BackgroundColor = make_color(*DIALOG_ACCENT_GREEN)
        ok_button.TextColor = make_color(*BH_PURE_WHITE)
        ok_button.Size = drawing.Size(190, 46)
        ok_button.Click += self.on_ok_clicked
        cancel_button = forms.Button()
        cancel_button.Text = "  ABORT  "
        cancel_button.Font = drawing.Font(drawing.FontFamily("Georgia"), 11, drawing.FontStyle.Italic)
        cancel_button.Size = drawing.Size(130, 46)
        cancel_button.BackgroundColor = make_color(*DIALOG_CANCEL_BG)
        cancel_button.TextColor = make_color(*DIALOG_CANCEL_TEXT)
        cancel_button.Click += self.on_cancel_clicked
        button_layout = forms.TableLayout()
        button_layout.Spacing = drawing.Size(16, 0)
        button_row = forms.TableRow()
        button_row.Cells.Add(forms.TableCell(None, True))
        button_row.Cells.Add(forms.TableCell(cancel_button, False))
        button_row.Cells.Add(forms.TableCell(ok_button, False))
        button_layout.Rows.Add(button_row)
        body_layout = forms.TableLayout()
        body_layout.Spacing = drawing.Size(0, 8)
        body_layout.Rows.Add(forms.TableRow(forms.TableCell(info_label, True)))
        body_layout.Rows.Add(forms.TableRow(forms.TableCell(separator, True)))
        body_layout.Rows.Add(forms.TableRow(forms.TableCell(self.radio0, True)))
        body_layout.Rows.Add(forms.TableRow(forms.TableCell(self.radio1, True)))
        body_layout.Rows.Add(forms.TableRow(forms.TableCell(self.radio2, True)))
        body_layout.Rows.Add(forms.TableRow(forms.TableCell(self.radio3, True)))
        body_layout.Rows.Add(forms.TableRow(forms.TableCell(self.radio4, True)))
        body_layout.Rows.Add(forms.TableRow(forms.TableCell(div_height, True)))
        body_layout.Rows.Add(forms.TableRow(forms.TableCell(height_title, True)))
        body_layout.Rows.Add(forms.TableRow(forms.TableCell(tick_layout, True)))
        body_layout.Rows.Add(forms.TableRow(forms.TableCell(self.height_slider, True)))
        body_layout.Rows.Add(forms.TableRow(forms.TableCell(range_layout, True)))
        body_layout.Rows.Add(forms.TableRow(forms.TableCell(self.height_sel_label, True)))
        body_layout.Rows.Add(forms.TableRow(forms.TableCell(button_layout, True)))
        body_panel.Content = body_layout
        main_layout = forms.TableLayout()
        main_layout.Spacing = drawing.Size(0, 0)
        main_layout.Rows.Add(forms.TableRow(forms.TableCell(header_panel, True)))
        main_layout.Rows.Add(forms.TableRow(forms.TableCell(accent_strip, True)))
        main_layout.Rows.Add(forms.TableRow(forms.TableCell(body_panel, True)))
        self.Content = main_layout

    def on_height_changed(self, sender, e):
        idx = self.height_slider.Value
        if 0 <= idx < len(self._height_values):
            v = self._height_values[idx]
            self.height_sel_label.Text = "Selected:  {:.0f} metres".format(v)

    def on_ok_clicked(self, sender, e):
        if self.radio1.Checked:   self.selected_upper_floors = 1
        elif self.radio2.Checked: self.selected_upper_floors = 2
        elif self.radio3.Checked: self.selected_upper_floors = 3
        elif self.radio4.Checked: self.selected_upper_floors = 4
        else:                     self.selected_upper_floors = 0
        idx = self.height_slider.Value
        self.selected_floor_height = self._height_values[idx] if 0 <= idx < len(self._height_values) else 3.0
        self.Close(True)

    def on_cancel_clicked(self, sender, e):
        self.selected_upper_floors = -1
        self.Close(False)


def get_additional_floors(Building):
    dialog = FloorCountDialog()
    if not dialog.ShowModal(Rhino.UI.RhinoEtoApp.MainWindow):
        return False
    if dialog.selected_upper_floors < 0:
        return False
    Building["floors"]["num_upper_floors"] = dialog.selected_upper_floors
    Building["floors"]["num_floors"] = 1 + dialog.selected_upper_floors
    # Store common floor height — used by all upper floors and roof
    Building["floors"]["common_floor_height"] = dialog.selected_floor_height
    return True


def get_upper_floor_height(Building, floor_label):
    """Use the common floor height selected once by the user — no dialog."""
    floor_height = Building["floors"].get("common_floor_height", 3.0)
    Building["floors"]["floor_heights"].append(floor_height)
    Building["floors"]["total_height"] = sum(Building["floors"]["floor_heights"])
    return floor_height


def get_roof_column_height(Building):
    """Use the common floor height selected once by the user — no dialog."""
    roof_height = Building["floors"].get("common_floor_height", 3.0)
    Building["floors"]["floor_heights"].append(roof_height)
    Building["floors"]["total_height"] = sum(Building["floors"]["floor_heights"])
    return roof_height


# ============================================================ GEOMETRY GENERATION ============================================================
def draw_outer_plot_boundary(Building):
    pl, pw = Building["plot"]["length"], Building["plot"]["width"]
    if not rs.IsLayer("Outer_Plot_Boundary"):
        rs.AddLayer("Outer_Plot_Boundary", (90, 90, 90))
    b = rs.AddPolyline([(-pl / 2, -pw / 2, 0), (pl / 2, -pw / 2, 0), (pl / 2, pw / 2, 0), (-pl / 2, pw / 2, 0), (-pl / 2, -pw / 2, 0)])
    if b:
        rs.ObjectLayer(b, "Outer_Plot_Boundary")
        rs.ObjectColor(b, (90, 90, 90))
    rs.ZoomExtents()
    rs.Redraw()


def draw_plot_boundary(Building):
    fl, fw = Building["plot"]["length"], Building["plot"]["width"]
    sb = Building["plot"].get("setback", 0.0)
    el, ew = max(0.01, fl - 2 * sb), max(0.01, fw - 2 * sb)
    if not rs.IsLayer("Plot_Boundary"):
        rs.AddLayer("Plot_Boundary", (128, 128, 128))
    p = rs.AddPolyline([(-el / 2, -ew / 2, 0), (el / 2, -ew / 2, 0), (el / 2, ew / 2, 0), (-el / 2, ew / 2, 0), (-el / 2, -ew / 2, 0)])
    if p:
        rs.ObjectLayer(p, "Plot_Boundary")
        rs.ObjectColor(p, (128, 128, 128))
        try:
            rs.ObjectLinetype(p, "Dashed")
        except:
            pass
        Building["plot"]["boundary"] = p
        Building["geometry"]["plot_boundary"] = p
    rs.ZoomExtents()
    rs.Redraw()
    return True


class PanelGenerationDialog(forms.Dialog[bool]):
    """Single combined dialog shown ONCE for both floor panels and wall panels.
    Replaces the two separate FloorPanelsStartDialog / WallPanelsStartDialog popups.
    User sees all info at once and confirms with a single START button.
    .confirmed is True when START is clicked, False when ABORT is clicked.
    """
    def __init__(self, num_floors):
        super(PanelGenerationDialog, self).__init__()
        self.BackgroundColor = make_color(*BH_BLACK)
        self.confirmed = False
        self.Title = "PANEL GENERATION"
        self.Padding = drawing.Padding(0)
        self.Resizable = False
        self.MinimumSize = drawing.Size(540, 560)
        # ── Header ──────────────────────────────────────────────────────────
        hp = forms.Panel()
        hp.BackgroundColor = make_color(*dialog_header_bg_rgb())
        hp.Padding = drawing.Padding(20, 16, 20, 16)
        hi = forms.ImageView()
        hi.Image = get_arch_dialog_icon("PANEL GENERATION", size=48)
        hi.Size = drawing.Size(48, 48)
        ht = forms.Label()
        ht.Text = "PANEL GENERATION"
        ht.Font = drawing.Font(drawing.FontFamily("Impact"), 16, drawing.FontStyle.Bold)
        ht.TextColor = make_color(*BH_WHITE)
        hs = forms.Label()
        hs.Text = "FLOOR PANELS  +  WALL PANELS  —  {} floor(s)".format(num_floors)
        hs.Font = drawing.Font(drawing.FontFamily("Georgia"), 10, drawing.FontStyle.Italic)
        hs.TextColor = make_color(*BH_AMBER)
        htxt = forms.TableLayout()
        htxt.Spacing = drawing.Size(0, 2)
        htxt.Rows.Add(forms.TableRow(forms.TableCell(ht, True)))
        htxt.Rows.Add(forms.TableRow(forms.TableCell(hs, True)))
        hl = forms.TableLayout()
        hl.Spacing = drawing.Size(12, 0)
        hr = forms.TableRow()
        hr.Cells.Add(forms.TableCell(hi, False))
        hr.Cells.Add(forms.TableCell(htxt, True))
        hl.Rows.Add(hr)
        hp.Content = hl
        # ── Body ────────────────────────────────────────────────────────────
        bp = forms.Panel()
        bp.BackgroundColor = make_color(*dialog_body_bg_rgb())
        bp.Padding = drawing.Padding(24, 18, 24, 18)
        # Floor panels section title with icon
        fp_icon = forms.ImageView()
        fp_icon.Image = _icon_variant_panels(28)
        fp_icon.Size = drawing.Size(28, 28)
        fp_title_lbl = forms.Label()
        fp_title_lbl.Text = "FLOOR PANELS"
        fp_title_lbl.Font = drawing.Font(drawing.FontFamily("Impact"), 13, drawing.FontStyle.Bold)
        fp_title_lbl.TextColor = make_color(*BH_AMBER)
        fp_title = forms.TableLayout()
        fp_title.Spacing = drawing.Size(8, 0)
        fp_tr = forms.TableRow()
        fp_tr.Cells.Add(forms.TableCell(fp_icon, False))
        fp_tr.Cells.Add(forms.TableCell(fp_title_lbl, True))
        fp_title.Rows.Add(fp_tr)
        # Floor panels description
        fp_desc = forms.Label()
        fp_desc.Text = (
            "Floor panels will be generated automatically for all {} floor(s).\n"
            "All cells with complete beam support are filled.\n"
            "No panels will be deleted \u2014 the complete structural slab\n"
            "is laid for every floor in one step."
        ).format(num_floors)
        fp_desc.Font = drawing.Font(drawing.FontFamily("Georgia"), 11, drawing.FontStyle.Italic)
        fp_desc.TextColor = make_color(*DIALOG_TEXT_SECONDARY)
        fp_desc.Wrap = forms.WrapMode.Word
        # Divider between sections
        sep_mid = forms.Panel()
        sep_mid.BackgroundColor = make_color(*BH_MID_GREY)
        sep_mid.Height = 3
        # Wall panels section title with icon
        wp_icon = forms.ImageView()
        wp_icon.Image = _icon_variant_walls(28)
        wp_icon.Size = drawing.Size(28, 28)
        wp_title_lbl = forms.Label()
        wp_title_lbl.Text = "WALL PANELS"
        wp_title_lbl.Font = drawing.Font(drawing.FontFamily("Impact"), 13, drawing.FontStyle.Bold)
        wp_title_lbl.TextColor = make_color(*BH_RED)
        wp_title = forms.TableLayout()
        wp_title.Spacing = drawing.Size(8, 0)
        wp_tr = forms.TableRow()
        wp_tr.Cells.Add(forms.TableCell(wp_icon, False))
        wp_tr.Cells.Add(forms.TableCell(wp_title_lbl, True))
        wp_title.Rows.Add(wp_tr)
        # Wall panels description
        wp_desc = forms.Label()
        wp_desc.Text = (
            "Wall panels will be generated automatically for all {} floor(s).\n"
            "Full-height walls are placed on all outer boundary edges.\n"
            "Full-height TRANSITION walls at the covered/uncovered boundary.\n"
            "1m parapet panels where no roof/floor exists above.\n"
            "No panels will be deleted \u2014 the complete wall envelope\n"
            "is built for every floor in one step."
        ).format(num_floors)
        wp_desc.Font = drawing.Font(drawing.FontFamily("Georgia"), 11, drawing.FontStyle.Italic)
        wp_desc.TextColor = make_color(*DIALOG_TEXT_SECONDARY)
        wp_desc.Wrap = forms.WrapMode.Word
        # Divider above button
        sep_btn = forms.Panel()
        sep_btn.BackgroundColor = make_color(*BH_RED)
        sep_btn.Height = 4
        # Single start button
        start_btn = forms.Button()
        start_btn.Text = "  > START GENERATING PANELS  "
        start_btn.Font = drawing.Font(drawing.FontFamily("Impact"), 13, drawing.FontStyle.Bold)
        start_btn.BackgroundColor = make_color(*BH_RED)
        start_btn.TextColor = make_color(*BH_PURE_WHITE)
        start_btn.Size = drawing.Size(380, 52)
        start_btn.Click += self.on_start
        # Abort button
        cb = forms.Button()
        cb.Text = "  ABORT  "
        cb.Font = drawing.Font(drawing.FontFamily("Georgia"), 11, drawing.FontStyle.Italic)
        cb.Size = drawing.Size(130, 46)
        cb.BackgroundColor = make_color(*DIALOG_CANCEL_BG)
        cb.TextColor = make_color(*DIALOG_CANCEL_TEXT)
        cb.Click += self.on_cancel
        bl = forms.TableLayout()
        bl.Spacing = drawing.Size(0, 12)
        bl.Rows.Add(forms.TableRow(forms.TableCell(fp_title,  True)))
        bl.Rows.Add(forms.TableRow(forms.TableCell(fp_desc,   True)))
        bl.Rows.Add(forms.TableRow(forms.TableCell(sep_mid,   True)))
        bl.Rows.Add(forms.TableRow(forms.TableCell(wp_title,  True)))
        bl.Rows.Add(forms.TableRow(forms.TableCell(wp_desc,   True)))
        bl.Rows.Add(forms.TableRow(forms.TableCell(sep_btn,   True)))
        bl.Rows.Add(forms.TableRow(forms.TableCell(start_btn, True)))
        bl.Rows.Add(forms.TableRow(forms.TableCell(cb,        True)))
        bp.Content = bl
        ml = forms.TableLayout()
        ml.Spacing = drawing.Size(0, 0)
        ml.Rows.Add(forms.TableRow(forms.TableCell(hp, True)))
        ml.Rows.Add(forms.TableRow(forms.TableCell(bp, True)))
        self.Content = ml

    def on_start(self, s, e):
        self.confirmed = True
        self.Close(True)

    def on_cancel(self, s, e):
        self.confirmed = False
        self.Close(False)


# Compatibility stubs — keep old names working if referenced anywhere else
class FloorPanelsStartDialog(PanelGenerationDialog):
    def __init__(self, num_floors):
        super(FloorPanelsStartDialog, self).__init__(num_floors)

class WallPanelsStartDialog(PanelGenerationDialog):
    def __init__(self, num_floors):
        super(WallPanelsStartDialog, self).__init__(num_floors)


# kept for backward-compatibility with any other call sites
class PanelDeletionDialog(forms.Dialog[bool]):
    """Legacy stub — no longer shown per-floor."""
    def __init__(self, floor_label, num_panels):
        super(PanelDeletionDialog, self).__init__()
        self.user_choice = "keep_all"
    def on_select(self, s, e): pass
    def on_keep(self, s, e):   pass
    def on_cancel(self, s, e): pass


# Legacy stub — no longer shown per-floor
class WallPanelDeletionDialog(forms.Dialog[bool]):
    def __init__(self, floor_label, num_panels):
        super(WallPanelDeletionDialog, self).__init__()
        self.user_choice = "keep_all"
    def on_select(self, s, e): pass
    def on_keep(self, s, e):   pass
    def on_cancel(self, s, e): pass


# ============================================================
# COMBINED ELEVATION EXTRUSION DIALOG
# Replaces the old separate WallExtrusionDialog and
# VerticalExtrusionDialog with a single unified dialog that
# controls BOTH elevation steps at once.
#
# Exposed state after close:
#   .wall_choice     — "generate" | "skip"
#   .vertical_choice — "proceed"  | "skip"
#   .user_cancelled  — True if ABORT was pressed
# ============================================================
class ElevationExtrusionDialog(forms.Dialog[bool]):
    """Single combined dialog for Elevation Steps 1 & 2.

    Layout
    ------
    Header (icon + title "ELEVATION EXTRUSION")
    ── STEP 1 block ──────────────────────────────────
      Label: step description
      Checkbox: [x] Generate wall arch extrusions  (default ON)
    ── divider ───────────────────────────────────────
    ── STEP 2 block ──────────────────────────────────
      Label: step description
      Checkbox: [x] Generate vertical arch extrusions (default ON)
    ── divider ───────────────────────────────────────
    Buttons: [> GENERATE BOTH]   [SKIP ALL]   [ABORT]
    """

    def __init__(self):
        super(ElevationExtrusionDialog, self).__init__()
        self.BackgroundColor = make_color(*BH_BLACK)
        self.Title = "ELEVATION EXTRUSION"
        self.Padding = drawing.Padding(0)
        self.Resizable = False
        self.MinimumSize = drawing.Size(580, 640)

        # Public state
        self.wall_choice     = "skip"
        self.vertical_choice = "skip"
        self.user_cancelled  = False

        # ── Header ──────────────────────────────────────────────────────────
        hp = forms.Panel()
        hp.BackgroundColor = make_color(*dialog_header_bg_rgb())
        hp.Padding = drawing.Padding(20, 14, 20, 14)

        hi = forms.ImageView()
        hi.Image = get_arch_dialog_icon("ELEVATION EXTRUSION", size=48)
        hi.Size = drawing.Size(48, 48)

        ht = forms.Label()
        ht.Text = "ELEVATION EXTRUSION"
        ht.Font = drawing.Font(drawing.FontFamily("Impact"), 18, drawing.FontStyle.Bold)
        ht.TextColor = make_color(*BH_WHITE)

        hs = forms.Label()
        hs.Text = "STEPS 1 & 2 — Wall + Vertical Arch"
        hs.Font = drawing.Font(drawing.FontFamily("Georgia"), 10, drawing.FontStyle.Italic)
        hs.TextColor = make_color(*BH_AMBER)

        htxt = forms.TableLayout()
        htxt.Spacing = drawing.Size(0, 2)
        htxt.Rows.Add(forms.TableRow(forms.TableCell(ht, True)))
        htxt.Rows.Add(forms.TableRow(forms.TableCell(hs, True)))

        hl = forms.TableLayout()
        hl.Spacing = drawing.Size(14, 0)
        hr = forms.TableRow()
        hr.Cells.Add(forms.TableCell(hi, False))
        hr.Cells.Add(forms.TableCell(htxt, True))
        hl.Rows.Add(hr)
        hp.Content = hl

        # ── Body ────────────────────────────────────────────────────────────
        bp = forms.Panel()
        bp.BackgroundColor = make_color(*dialog_body_bg_rgb())
        bp.Padding = drawing.Padding(26, 18, 26, 18)

        # --- Step 1 section -------------------------------------------------
        s1_icon = forms.ImageView()
        s1_icon.Image = _icon_variant_wall_extrude(28)
        s1_icon.Size = drawing.Size(28, 28)
        s1_lbl = forms.Label()
        s1_lbl.Text = "STEP 1 — WALL ARCH EXTRUSION"
        s1_lbl.Font = drawing.Font(drawing.FontFamily("Impact"), 13, drawing.FontStyle.Bold)
        s1_lbl.TextColor = make_color(*BH_AMBER)
        s1_title = forms.TableLayout()
        s1_title.Spacing = drawing.Size(8, 0)
        s1_tr = forms.TableRow()
        s1_tr.Cells.Add(forms.TableCell(s1_icon, False))
        s1_tr.Cells.Add(forms.TableCell(s1_lbl, True))
        s1_title.Rows.Add(s1_tr)

        s1_desc = forms.Label()
        s1_desc.Text = (
            "Closed-box checkerboard on ALL floors (except basement)\n"
            "across ALL four facade faces.  Alternating panels project\n"
            "outward per floor — no manual selection.  Depth: 1.5 m."
        )
        s1_desc.Font = drawing.Font(drawing.FontFamily("Georgia"), 10, drawing.FontStyle.Italic)
        s1_desc.TextColor = make_color(*DIALOG_TEXT_SECONDARY)
        s1_desc.Wrap = forms.WrapMode.Word

        self.cb_wall = forms.CheckBox()
        self.cb_wall.Text = "  Generate wall arch extrusions"
        self.cb_wall.Checked = True
        self.cb_wall.Font = drawing.Font(drawing.FontFamily("Georgia"), 11, drawing.FontStyle.Bold)
        try_set_control_colors(self.cb_wall, text_rgb=BH_WHITE)

        sep1 = forms.Panel()
        sep1.BackgroundColor = make_color(*BH_AMBER)
        sep1.Height = 3

        # --- Step 2 section -------------------------------------------------
        s2_icon = forms.ImageView()
        s2_icon.Image = _icon_variant_vertical_extrude(28)
        s2_icon.Size = drawing.Size(28, 28)
        s2_lbl = forms.Label()
        s2_lbl.Text = "STEP 2 — VERTICAL ARCH EXTRUSION"
        s2_lbl.Font = drawing.Font(drawing.FontFamily("Impact"), 13, drawing.FontStyle.Bold)
        s2_lbl.TextColor = make_color(*BH_RED)
        s2_title = forms.TableLayout()
        s2_title.Spacing = drawing.Size(8, 0)
        s2_tr = forms.TableRow()
        s2_tr.Cells.Add(forms.TableCell(s2_icon, False))
        s2_tr.Cells.Add(forms.TableCell(s2_lbl, True))
        s2_title.Rows.Add(s2_tr)

        s2_desc = forms.Label()
        s2_desc.Text = (
            "Auto-extrudes 30\u201340% of open terrace panels upward as\n"
            "rectangular arch portals.  Checker pattern (offset per floor)\n"
            "with collision detection.  Height: 4 m fixed.  Orientation: N\u2013S."
        )
        s2_desc.Font = drawing.Font(drawing.FontFamily("Georgia"), 10, drawing.FontStyle.Italic)
        s2_desc.TextColor = make_color(*DIALOG_TEXT_SECONDARY)
        s2_desc.Wrap = forms.WrapMode.Word

        self.cb_vertical = forms.CheckBox()
        self.cb_vertical.Text = "  Generate vertical arch extrusions"
        self.cb_vertical.Checked = True
        self.cb_vertical.Font = drawing.Font(drawing.FontFamily("Georgia"), 11, drawing.FontStyle.Bold)
        try_set_control_colors(self.cb_vertical, text_rgb=BH_WHITE)

        sep2 = forms.Panel()
        sep2.BackgroundColor = make_color(*BH_MID_GREY)
        sep2.Height = 3

        # --- Buttons --------------------------------------------------------
        gen_btn = forms.Button()
        gen_btn.Text = "  > GENERATE SELECTED  "
        gen_btn.Font = drawing.Font(drawing.FontFamily("Impact"), 13, drawing.FontStyle.Bold)
        gen_btn.BackgroundColor = make_color(*DIALOG_ACCENT_ORANGE)
        gen_btn.TextColor = make_color(*BH_PURE_WHITE)
        gen_btn.Size = drawing.Size(280, 52)
        gen_btn.Click += self.on_generate

        skip_btn = forms.Button()
        skip_btn.Text = "  [ SKIP ALL ]  "
        skip_btn.Font = drawing.Font(drawing.FontFamily("Impact"), 12, drawing.FontStyle.Bold)
        skip_btn.BackgroundColor = make_color(*DIALOG_SURFACE_RAISED)
        skip_btn.TextColor = make_color(*BH_PURE_WHITE)
        skip_btn.Size = drawing.Size(160, 52)
        skip_btn.Click += self.on_skip_all

        abort_btn = forms.Button()
        abort_btn.Text = "  ABORT  "
        abort_btn.Font = drawing.Font(drawing.FontFamily("Georgia"), 11, drawing.FontStyle.Italic)
        abort_btn.Size = drawing.Size(120, 46)
        abort_btn.BackgroundColor = make_color(*DIALOG_CANCEL_BG)
        abort_btn.TextColor = make_color(*DIALOG_CANCEL_TEXT)
        abort_btn.Click += self.on_cancel

        btn_row = forms.TableLayout()
        btn_row.Spacing = drawing.Size(12, 0)
        br = forms.TableRow()
        br.Cells.Add(forms.TableCell(gen_btn,   False))
        br.Cells.Add(forms.TableCell(skip_btn,  False))
        br.Cells.Add(forms.TableCell(None,       True))   # spacer
        br.Cells.Add(forms.TableCell(abort_btn, False))
        btn_row.Rows.Add(br)

        # --- Body layout ----------------------------------------------------
        bl = forms.TableLayout()
        bl.Spacing = drawing.Size(0, 12)
        bl.Rows.Add(forms.TableRow(forms.TableCell(s1_title,    True)))
        bl.Rows.Add(forms.TableRow(forms.TableCell(s1_desc,     True)))
        bl.Rows.Add(forms.TableRow(forms.TableCell(self.cb_wall,True)))
        bl.Rows.Add(forms.TableRow(forms.TableCell(sep1,        True)))
        bl.Rows.Add(forms.TableRow(forms.TableCell(s2_title,    True)))
        bl.Rows.Add(forms.TableRow(forms.TableCell(s2_desc,     True)))
        bl.Rows.Add(forms.TableRow(forms.TableCell(self.cb_vertical, True)))
        bl.Rows.Add(forms.TableRow(forms.TableCell(sep2,        True)))
        bl.Rows.Add(forms.TableRow(forms.TableCell(btn_row,     True)))
        bp.Content = bl

        # ── Root layout ─────────────────────────────────────────────────────
        ml = forms.TableLayout()
        ml.Spacing = drawing.Size(0, 0)
        ml.Rows.Add(forms.TableRow(forms.TableCell(hp, True)))
        ml.Rows.Add(forms.TableRow(forms.TableCell(bp, True)))
        self.Content = ml

    # ── Handlers ────────────────────────────────────────────────────────────
    def on_generate(self, s, e):
        self.wall_choice     = "generate" if self.cb_wall.Checked     else "skip"
        self.vertical_choice = "proceed"  if self.cb_vertical.Checked else "skip"
        self.Close(True)

    def on_skip_all(self, s, e):
        self.wall_choice     = "skip"
        self.vertical_choice = "skip"
        self.Close(True)

    def on_cancel(self, s, e):
        self.user_cancelled  = True
        self.wall_choice     = "skip"
        self.vertical_choice = "skip"
        self.Close(False)


# Thin compatibility shims so any other code that references
# WallExtrusionDialog or VerticalExtrusionDialog still works.
# Both simply delegate to ElevationExtrusionDialog.
class WallExtrusionDialog(ElevationExtrusionDialog):
    """Compatibility alias — use ElevationExtrusionDialog directly."""
    def __init__(self):
        super(WallExtrusionDialog, self).__init__()
    @property
    def user_choice(self):
        return self.wall_choice


class VerticalExtrusionDialog(ElevationExtrusionDialog):
    """Compatibility alias — use ElevationExtrusionDialog directly."""
    def __init__(self):
        super(VerticalExtrusionDialog, self).__init__()
    @property
    def user_choice(self):
        return self.vertical_choice


# ============================================================ ARCH ORIENTATION DIALOG ============================================================
class ArchOrientationDialog(forms.Dialog[bool]):
    def __init__(self):
        super(ArchOrientationDialog, self).__init__()
        self.BackgroundColor = make_color(*BH_BLACK)
        self.orientation = "NS"
        self.Title = "ARCH ORIENTATION"
        self.Padding = drawing.Padding(0)
        self.Resizable = False
        self.MinimumSize = drawing.Size(540, 440)
        hp = forms.Panel()
        hp.BackgroundColor = make_color(*dialog_header_bg_rgb())
        hp.Padding = drawing.Padding(20, 16, 20, 16)
        hi = forms.ImageView()
        hi.Image = get_arch_dialog_icon("VERTICAL ARCH EXTRUSION", size=48)
        hi.Size = drawing.Size(48, 48)
        ht = forms.Label()
        ht.Text = "ARCH ORIENTATION"
        ht.Font = drawing.Font(drawing.FontFamily("Impact"), 16, drawing.FontStyle.Bold)
        ht.TextColor = make_color(*BH_WHITE)
        hl = forms.TableLayout()
        hl.Spacing = drawing.Size(12, 0)
        hr = forms.TableRow()
        hr.Cells.Add(forms.TableCell(hi, False))
        hr.Cells.Add(forms.TableCell(ht, True))
        hl.Rows.Add(hr)
        hp.Content = hl
        bp = forms.Panel()
        bp.BackgroundColor = make_color(*dialog_body_bg_rgb())
        bp.Padding = drawing.Padding(24, 18, 24, 18)
        il = forms.Label()
        il.Text = "Select the passage direction for the arch.\nThe arch has open faces on the selected direction."
        il.Font = drawing.Font(drawing.FontFamily("Georgia"), 11, drawing.FontStyle.Italic)
        il.TextColor = make_color(*DIALOG_TEXT_SECONDARY)
        il.Wrap = forms.WrapMode.Word
        sep = forms.Panel()
        sep.BackgroundColor = make_color(*DIALOG_ACCENT_PINK)
        sep.Height = 4
        self.radio_ns = forms.RadioButton()
        self.radio_ns.Text = "  [N-S]  NORTH-SOUTH PASSAGE  //  OPEN:Y"
        self.radio_ns.Font = drawing.Font(drawing.FontFamily("Georgia"), 11, drawing.FontStyle.Italic)

        try_set_control_colors(self.radio_ns, bg_rgb=None, text_rgb=DIALOG_TEXT_PRIMARY)
        self.radio_ns.Checked = True
        self.radio_ew = forms.RadioButton(self.radio_ns)
        self.radio_ew.Text = "  [E-W]  EAST-WEST PASSAGE   //  OPEN:X"
        self.radio_ew.Font = drawing.Font(drawing.FontFamily("Georgia"), 11, drawing.FontStyle.Italic)

        try_set_control_colors(self.radio_ew, bg_rgb=None, text_rgb=DIALOG_TEXT_PRIMARY)
        ok_button = forms.Button()
        ok_button.Text = "  CONFIRM  "
        ok_button.Font = drawing.Font(drawing.FontFamily("Impact"), 13, drawing.FontStyle.Bold)
        ok_button.BackgroundColor = make_color(*DIALOG_ACCENT_BLUE)
        ok_button.TextColor = make_color(*BH_PURE_WHITE)
        ok_button.Size = drawing.Size(190, 46)
        ok_button.Click += self.on_ok
        cb = forms.Button()
        cb.Text = "  ABORT  "
        cb.Font = drawing.Font(drawing.FontFamily("Georgia"), 11, drawing.FontStyle.Italic)
        cb.Size = drawing.Size(130, 46)
        cb.BackgroundColor = make_color(*DIALOG_CANCEL_BG)
        cb.TextColor = make_color(*DIALOG_CANCEL_TEXT)
        cb.Click += self.on_cancel
        btn_layout = forms.TableLayout()
        btn_layout.Spacing = drawing.Size(15, 0)
        btn_row = forms.TableRow()
        btn_row.Cells.Add(forms.TableCell(None, True))
        btn_row.Cells.Add(forms.TableCell(cb, False))
        btn_row.Cells.Add(forms.TableCell(ok_button, False))
        btn_layout.Rows.Add(btn_row)
        bl = forms.TableLayout()
        bl.Spacing = drawing.Size(0, 10)
        bl.Rows.Add(forms.TableRow(forms.TableCell(il, True)))
        bl.Rows.Add(forms.TableRow(forms.TableCell(sep, True)))
        bl.Rows.Add(forms.TableRow(forms.TableCell(self.radio_ns, True)))
        bl.Rows.Add(forms.TableRow(forms.TableCell(self.radio_ew, True)))
        bl.Rows.Add(forms.TableRow(forms.TableCell(btn_layout, True)))
        bp.Content = bl
        ml = forms.TableLayout()
        ml.Spacing = drawing.Size(0, 0)
        ml.Rows.Add(forms.TableRow(forms.TableCell(hp, True)))
        ml.Rows.Add(forms.TableRow(forms.TableCell(bp, True)))
        self.Content = ml

    def on_ok(self, s, e):
        self.orientation = "EW" if self.radio_ew.Checked else "NS"
        self.Close(True)

    def on_cancel(self, s, e):
        self.orientation = None
        self.Close(False)


# ============================================================ TWO-PASS CONNECTIVITY CHECK FUNCTIONS ============================================================


def find_connected_components(column_coords, grid_spacing, tolerance=0.01):
    if not column_coords:
        return []
    positions = set()
    for coord in column_coords:
        positions.add((round(coord[0], 4), round(coord[1], 4)))
    pos_list = list(positions)
    n = len(pos_list)
    if n == 0:
        return []
    pos_to_idx = {pos: i for i, pos in enumerate(pos_list)}
    parent = list(range(n))
    def find(x):
        if parent[x] != x:
            parent[x] = find(parent[x])
        return parent[x]
    def union(x, y):
        px, py = find(x), find(y)
        if px != py:
            parent[py] = px
    for i, (x, y) in enumerate(pos_list):
        for nb in [(round(x + grid_spacing, 4), round(y, 4)),
                    (round(x - grid_spacing, 4), round(y, 4)),
                    (round(x, 4), round(y + grid_spacing, 4)),
                    (round(x, 4), round(y - grid_spacing, 4))]:
            if nb in pos_to_idx:
                union(i, pos_to_idx[nb])
    components = {}
    for i, pos in enumerate(pos_list):
        root = find(i)
        if root not in components:
            components[root] = []
        components[root].append(pos)
    return list(components.values())


def find_shortest_connection_between_components(comp1, comp2, grid_spacing):
    min_dist = float('inf')
    best_path = []
    for p1 in comp1:
        for p2 in comp2:
            x1, y1 = round(p1[0], 4), round(p1[1], 4)
            x2, y2 = round(p2[0], 4), round(p2[1], 4)
            dist = abs(x2 - x1) + abs(y2 - y1)
            if dist < min_dist:
                min_dist = dist
                path = []
                cx = x1
                step_x = grid_spacing if x2 > x1 else -grid_spacing
                while abs(cx - x2) > 0.01:
                    cx = round(cx + step_x, 4)
                    path.append((cx, y1))
                cy = y1
                step_y = grid_spacing if y2 > y1 else -grid_spacing
                while abs(cy - y2) > 0.01:
                    cy = round(cy + step_y, 4)
                    path.append((x2, cy))
                if path:
                    path.pop()
                best_path = path
    return best_path


def get_cells(coords, grid_spacing):
    cells = set()
    coords_set = set((round(c[0], 4), round(c[1], 4)) for c in coords)
    for cx, cy in coords_set:
        if (round(cx + grid_spacing, 4), cy) in coords_set and \
           (cx, round(cy + grid_spacing, 4)) in coords_set and \
           (round(cx + grid_spacing, 4), round(cy + grid_spacing, 4)) in coords_set:
            cells.add((cx, cy))
    return cells


def find_cell_components(cells, grid_spacing):
    if not cells:
        return []
    cell_list = list(cells)
    n = len(cell_list)
    parent = list(range(n))
    def find(i):
        if parent[i] == i:
            return i
        parent[i] = find(parent[i])
        return parent[i]
    def union(i, j):
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[ri] = rj
    c_idx = {c: i for i, c in enumerate(cell_list)}
    for i, (cx, cy) in enumerate(cell_list):
        for nb in [(round(cx + grid_spacing, 4), cy),
                    (round(cx - grid_spacing, 4), cy),
                    (cx, round(cy + grid_spacing, 4)),
                    (cx, round(cy - grid_spacing, 4))]:
            if nb in c_idx:
                union(i, c_idx[nb])
    comps = {}
    for i, c in enumerate(cell_list):
        root = find(i)
        if root not in comps:
            comps[root] = []
        comps[root].append(c)
    return list(comps.values())


def get_cell_path(c1, c2, grid_spacing):
    x1, y1 = c1
    x2, y2 = c2
    path = []
    cx, cy = x1, y1
    step_x = grid_spacing if x2 > cx else -grid_spacing
    while abs(cx - x2) > 0.01:
        cx = round(cx + step_x, 4)
        path.append((cx, cy))
    step_y = grid_spacing if y2 > cy else -grid_spacing
    while abs(cy - y2) > 0.01:
        cy = round(cy + step_y, 4)
        path.append((cx, cy))
    return path


def ensure_floor_connectivity(selected_coords, grid_spacing, z_level=0, valid_positions=None):
    """Ensure column selections form a connected graph.

    Bridge points added automatically are ONLY placed at positions that exist
    in *valid_positions* — i.e. actual beam intersection points on this floor.
    If valid_positions is None (legacy call) the old unconstrained behaviour is
    preserved so nothing outside this function breaks.

    Parameters
    ----------
    selected_coords  : list of (x, y, z) tuples — user-selected column positions
    grid_spacing     : float — grid module size
    z_level          : float — Z height for new points
    valid_positions  : set of (x, y) tuples (rounded to 4 dp) representing every
                       beam intersection available on this floor.  Auto-added
                       bridge points are restricted to this set.
    """
    if not selected_coords:
        return selected_coords, []

    # Build the constraint set once (normalised to 4 dp)
    if valid_positions is not None:
        allowed = set((round(px, 4), round(py, 4)) for px, py in valid_positions)
    else:
        allowed = None   # unconstrained — legacy behaviour

    def _can_add(px, py):
        """Return True if (px, py) is a legal auto-add position."""
        if allowed is None:
            return True
        return (round(px, 4), round(py, 4)) in allowed

    all_added = []
    current_coords = list(selected_coords)

    # ── Pass 1: node connectivity (each selected point reachable from others) ──
    while True:
        components = find_connected_components(current_coords, grid_spacing)
        if len(components) <= 1:
            break
        print("\n  CONNECTIVITY WARNING: Disconnected islands detected!")
        existing_positions = set((round(c[0], 4), round(c[1], 4)) for c in current_coords)

        # Find shortest bridge path among all component pairs
        min_path_len = float('inf')
        best_path = []
        for i in range(len(components)):
            for j in range(i + 1, len(components)):
                path = find_shortest_connection_between_components(
                    components[i], components[j], grid_spacing)
                if len(path) < min_path_len:
                    min_path_len = len(path)
                    best_path = path

        # Filter path to only beam-intersection positions
        added_any = False
        for pos in best_path:
            p_rnd = (round(pos[0], 4), round(pos[1], 4))
            if p_rnd not in existing_positions and _can_add(p_rnd[0], p_rnd[1]):
                existing_positions.add(p_rnd)
                current_coords.append((p_rnd[0], p_rnd[1], z_level))
                all_added.append((p_rnd[0], p_rnd[1], z_level))
                added_any = True

        if not added_any:
            # No valid beam-intersection point lies on the direct path.
            # Fall back: search the full allowed set for the nearest point that
            # actually bridges the two closest components.
            bridged = False
            if allowed is not None:
                # Find the two closest components
                min_pair_dist = float('inf')
                ci_best, cj_best = 0, 1
                for i in range(len(components)):
                    for j in range(i + 1, len(components)):
                        for p1 in components[i]:
                            for p2 in components[j]:
                                d = abs(p1[0]-p2[0]) + abs(p1[1]-p2[1])
                                if d < min_pair_dist:
                                    min_pair_dist = d
                                    ci_best, cj_best = i, j
                # Pick the candidate from allowed that minimises total distance
                # to both component sets (greedy: minimise max of distances)
                comp_i_set = set(components[ci_best])
                comp_j_set = set(components[cj_best])
                best_candidate = None
                best_score = float('inf')
                for (ax, ay) in allowed:
                    if (ax, ay) in existing_positions:
                        continue
                    di = min(abs(ax-p[0]) + abs(ay-p[1]) for p in comp_i_set)
                    dj = min(abs(ax-p[0]) + abs(ay-p[1]) for p in comp_j_set)
                    score = di + dj
                    if score < best_score:
                        best_score = score
                        best_candidate = (ax, ay)
                if best_candidate:
                    existing_positions.add(best_candidate)
                    current_coords.append((best_candidate[0], best_candidate[1], z_level))
                    all_added.append((best_candidate[0], best_candidate[1], z_level))
                    bridged = True
                    print("  Auto-bridge via nearest beam intersection at ({:.2f}, {:.2f}).".format(
                        best_candidate[0], best_candidate[1]))
            if not bridged:
                print("  WARNING: Cannot bridge disconnected components within beam intersections.")
                break   # avoid infinite loop

    # ── Pass 2: face/cell connectivity (no corner-only adjacency) ─────────────
    while True:
        cells = get_cells(current_coords, grid_spacing)
        if not cells:
            break
        cell_components = find_cell_components(cells, grid_spacing)
        if len(cell_components) <= 1:
            break
        print("\n  FACE CONNECTIVITY WARNING: Corner bottleneck detected!")
        existing_positions = set((round(c[0], 4), round(c[1], 4)) for c in current_coords)

        min_dist = float('inf')
        best_path = []
        for i in range(len(cell_components)):
            for j in range(i + 1, len(cell_components)):
                for c1 in cell_components[i]:
                    for c2 in cell_components[j]:
                        dist = abs(c1[0] - c2[0]) + abs(c1[1] - c2[1])
                        if dist < min_dist:
                            min_dist = dist
                            best_path = get_cell_path(c1, c2, grid_spacing)

        added_any = False
        for cx, cy in best_path:
            for px, py in [(cx, cy), (round(cx + grid_spacing, 4), cy),
                           (cx, round(cy + grid_spacing, 4)),
                           (round(cx + grid_spacing, 4), round(cy + grid_spacing, 4))]:
                if (px, py) not in existing_positions and _can_add(px, py):
                    existing_positions.add((px, py))
                    current_coords.append((px, py, z_level))
                    all_added.append((px, py, z_level))
                    added_any = True

        if not added_any:
            # Fallback: pick any allowed point adjacent to either cell component
            if allowed is not None:
                placed = False
                for i in range(len(cell_components)):
                    for (cx, cy) in cell_components[i]:
                        for (dx, dy) in [(grid_spacing, 0), (-grid_spacing, 0),
                                         (0, grid_spacing), (0, -grid_spacing)]:
                            candidate = (round(cx+dx, 4), round(cy+dy, 4))
                            if candidate not in existing_positions and _can_add(*candidate):
                                existing_positions.add(candidate)
                                current_coords.append((candidate[0], candidate[1], z_level))
                                all_added.append((candidate[0], candidate[1], z_level))
                                placed = True
                                break
                        if placed:
                            break
                    if placed:
                        break
            if not added_any:
                print("  WARNING: Cannot resolve face connectivity within beam intersections.")
                break   # avoid infinite loop

    if all_added:
        print("  Added {} columns to fix connectivity (beam intersections only).\n".format(len(all_added)))
    else:
        print("\n  CONNECTIVITY CHECK: Floor is fully connected.")
    return current_coords, all_added


# ============================================================ PLOT BOUNDARY VALIDATION ============================================================
def is_point_within_plot(point, plot_length, plot_width, tolerance=0.01):
    x, y = point[0], point[1]
    return -plot_length / 2.0 - tolerance <= x <= plot_length / 2.0 + tolerance and \
           -plot_width / 2.0 - tolerance <= y <= plot_width / 2.0 + tolerance


def is_snapped_point_valid_grid(snapped_point, plot_length, plot_width, grid_spacing, tolerance=0.01):
    x, y = snapped_point[0], snapped_point[1]
    return -plot_length / 2.0 - tolerance <= x <= plot_length / 2.0 + tolerance and \
           -plot_width / 2.0 - tolerance <= y <= plot_width / 2.0 + tolerance


# ============================================================ POLYLINE DRAWING SELECTION FUNCTIONS ============================================================
def snap_point_to_grid(point, grid_spacing, eff_length, eff_width):
    x, y = point[0], point[1]
    z = point[2] if len(point) > 2 else 0
    origin_x = -eff_length / 2.0
    origin_y = -eff_width / 2.0
    grid_x = round((x - origin_x) / grid_spacing) * grid_spacing + origin_x
    grid_y = round((y - origin_y) / grid_spacing) * grid_spacing + origin_y
    return (round(grid_x, 4), round(grid_y, 4), round(z, 4))


def close_polyline_with_90_degrees(points, grid_spacing):
    if not points or len(points) < 2:
        return points
    first, last = points[0], points[-1]
    if abs(first[0] - last[0]) < 0.01 and abs(first[1] - last[1]) < 0.01:
        return points
    closing_points = []
    x1, y1 = round(last[0], 4), round(last[1], 4)
    x2, y2 = round(first[0], 4), round(first[1], 4)
    z = last[2] if len(last) > 2 else 0
    curr_x = x1
    step_x = grid_spacing if x2 > x1 else -grid_spacing
    while abs(curr_x - x2) > 0.01:
        curr_x = round(curr_x + step_x, 4)
        closing_points.append((curr_x, y1, z))
    curr_y = y1
    step_y = grid_spacing if y2 > y1 else -grid_spacing
    while abs(curr_y - y2) > 0.01:
        curr_y = round(curr_y + step_y, 4)
        closing_points.append((x2, curr_y, z))
    if closing_points and abs(closing_points[-1][0] - x2) < 0.01 and abs(closing_points[-1][1] - y2) < 0.01:
        closing_points = closing_points[:-1]
    result = list(points) + closing_points
    result.append(first)
    return result


def get_grid_points_inside_polyline(polyline_points, grid_spacing, eff_length, eff_width, z_level=0):
    if not polyline_points or len(polyline_points) < 3:
        return []
    polyline_curve = rs.AddPolyline(polyline_points)
    if not polyline_curve:
        return []
    curve = rs.coercecurve(polyline_curve)
    if not curve or not curve.IsClosed:
        rs.DeleteObject(polyline_curve)
        return []
    grid_points = []
    origin_x = -eff_length / 2.0
    origin_y = -eff_width / 2.0
    num_x = int(eff_length / grid_spacing) + 1
    num_y = int(eff_width / grid_spacing) + 1
    for i in range(num_x):
        for j in range(num_y):
            x = round(i * grid_spacing + origin_x, 4)
            y = round(j * grid_spacing + origin_y, 4)
            test_pt = rg.Point3d(x, y, z_level)
            containment = curve.Contains(test_pt, rg.Plane.WorldXY, 0.001)
            if containment == rg.PointContainment.Inside or containment == rg.PointContainment.Coincident:
                grid_points.append((x, y, z_level))
    for pt in polyline_points[:-1]:
        snapped = snap_point_to_grid(pt, grid_spacing, eff_length, eff_width)
        if snapped not in grid_points:
            grid_points.append(snapped)
    rs.DeleteObject(polyline_curve)
    return grid_points


def draw_selection_polyline_for_columns(Building, z_level=0):
    grid_spacing = Building["grid"]["spacing"]
    plot_length = Building["plot"]["length"]
    plot_width = Building["plot"]["width"]
    setback = Building["plot"]["setback"]
    effective_length = max(0.01, plot_length - 2.0 * setback)
    effective_width = max(0.01, plot_width - 2.0 * setback)
    print_section_header("DRAW SELECTION POLYLINE")
    print("Draw a polyline to define the column area. Press ENTER when done.")
    print_section_footer()
    if not rs.IsLayer("Selection_Polyline"):
        rs.AddLayer("Selection_Polyline", (200, 140, 0))
    drawn_points = []
    while True:
        point = rs.GetPoint("Click grid point for selection boundary (ENTER to finish)")
        if point is None:
            break
        if not is_point_within_plot(point, effective_length, effective_width):
            continue
        snapped = snap_point_to_grid(point, grid_spacing, effective_length, effective_width)
        snapped_with_z = (snapped[0], snapped[1], z_level)
        if not is_snapped_point_valid_grid(snapped_with_z, effective_length, effective_width, grid_spacing):
            continue
        if drawn_points and abs(snapped_with_z[0] - drawn_points[-1][0]) < 0.01 and abs(snapped_with_z[1] - drawn_points[-1][1]) < 0.01:
            continue
        drawn_points.append(snapped_with_z)
        pt_id = rs.AddPoint(snapped_with_z)
        if pt_id:
            rs.ObjectLayer(pt_id, "Selection_Polyline")
            rs.ObjectColor(pt_id, (200, 140, 0))
        if len(drawn_points) > 1:
            line = rs.AddLine(drawn_points[-2], drawn_points[-1])
            if line:
                rs.ObjectLayer(line, "Selection_Polyline")
                rs.ObjectColor(line, (200, 140, 0))
        print("  Point {} at X={:.2f}, Y={:.2f}".format(len(drawn_points), snapped_with_z[0], snapped_with_z[1]))
    if len(drawn_points) < 3:
        return None
    closed_points = close_polyline_with_90_degrees(drawn_points, grid_spacing)
    inside_points = get_grid_points_inside_polyline(closed_points, grid_spacing, effective_length, effective_width, z_level)
    if rs.IsLayer("Selection_Polyline"):
        objs = rs.ObjectsByLayer("Selection_Polyline")
        if objs:
            rs.DeleteObjects(objs)
    return inside_points if inside_points else None


def select_columns_by_polyline_for_upper_floor(Building, floor_label, available_points, z_level):
    grid_spacing = Building["grid"]["spacing"]
    plot_length = Building["plot"]["length"]
    plot_width = Building["plot"]["width"]
    setback = Building["plot"]["setback"]
    effective_length = max(0.01, plot_length - 2.0 * setback)
    effective_width = max(0.01, plot_width - 2.0 * setback)
    print_section_header("DRAW SELECTION POLYLINE FOR {}".format(floor_label))
    print("Draw a polyline to define the column area. Press ENTER when done.")
    print_section_footer()
    if not rs.IsLayer("Selection_Polyline"):
        rs.AddLayer("Selection_Polyline", (200, 140, 0))
    drawn_points = []
    while True:
        point = rs.GetPoint("Click point for {} boundary (ENTER to finish)".format(floor_label))
        if point is None:
            break
        if not is_point_within_plot(point, effective_length, effective_width):
            continue
        snapped = snap_point_to_grid(point, grid_spacing, effective_length, effective_width)
        snapped_with_z = (snapped[0], snapped[1], z_level)
        if not is_snapped_point_valid_grid(snapped_with_z, effective_length, effective_width, grid_spacing):
            continue
        if drawn_points and abs(snapped_with_z[0] - drawn_points[-1][0]) < 0.01 and abs(snapped_with_z[1] - drawn_points[-1][1]) < 0.01:
            continue
        drawn_points.append(snapped_with_z)
        pt_id = rs.AddPoint(snapped_with_z)
        if pt_id:
            rs.ObjectLayer(pt_id, "Selection_Polyline")
            rs.ObjectColor(pt_id, (200, 140, 0))
        if len(drawn_points) > 1:
            line = rs.AddLine(drawn_points[-2], drawn_points[-1])
            if line:
                rs.ObjectLayer(line, "Selection_Polyline")
                rs.ObjectColor(line, (200, 140, 0))
    if len(drawn_points) < 3:
        return available_points
    closed_points = close_polyline_with_90_degrees(drawn_points, grid_spacing)
    available_set = set([(round(pt[0], 4), round(pt[1], 4)) for pt in available_points])
    inside_points = get_grid_points_inside_polyline(closed_points, grid_spacing, effective_length, effective_width, z_level)
    selected_coords = []
    for pt in inside_points:
        if (round(pt[0], 4), round(pt[1], 4)) in available_set:
            selected_coords.append((pt[0], pt[1], z_level))
    if rs.IsLayer("Selection_Polyline"):
        objs = rs.ObjectsByLayer("Selection_Polyline")
        if objs:
            rs.DeleteObjects(objs)
    return selected_coords if selected_coords else available_points


# ============================================================ BOUNDARY CREATION FUNCTIONS ============================================================
def create_rectilinear_boundary(column_top_points, z_level):
    if not column_top_points:
        return [], []
    points_2d = set()
    for pt in column_top_points:
        points_2d.add((round(pt[0], 4), round(pt[1], 4)))
    if len(points_2d) == 0:
        return [], []
    if len(points_2d) == 1:
        p = list(points_2d)[0]
        return [p, p], [(p[0], p[1], z_level), (p[0], p[1], z_level)]
    y_values = sorted(set(p[1] for p in points_2d))
    left_edge, right_edge = {}, {}
    for y in y_values:
        x_vals = [p[0] for p in points_2d if p[1] == y]
        left_edge[y] = min(x_vals)
        right_edge[y] = max(x_vals)
    path = []
    for i, y in enumerate(y_values):
        left_x = left_edge[y]
        if i == 0:
            path.append((left_x, y))
        else:
            prev_y = y_values[i - 1]
            prev_left_x = left_edge[prev_y]
            if left_x < prev_left_x:
                path.append((prev_left_x, y))
                path.append((left_x, y))
            elif left_x > prev_left_x:
                path.append((left_x, prev_y))
                path.append((left_x, y))
            else:
                path.append((left_x, y))
    top_y = y_values[-1]
    if right_edge[top_y] != left_edge[top_y]:
        path.append((right_edge[top_y], top_y))
    for i in range(len(y_values) - 2, -1, -1):
        y = y_values[i]
        right_x = right_edge[y]
        upper_y = y_values[i + 1]
        upper_right_x = right_edge[upper_y]
        if right_x > upper_right_x:
            path.append((upper_right_x, y))
            path.append((right_x, y))
        elif right_x < upper_right_x:
            path.append((right_x, upper_y))
            path.append((right_x, y))
        else:
            path.append((right_x, y))
    bottom_y = y_values[0]
    if path[-1][0] != left_edge[bottom_y]:
        path.append((left_edge[bottom_y], bottom_y))
    if path[0] != path[-1]:
        path.append(path[0])
    cleaned = [path[0]]
    for i in range(1, len(path)):
        if path[i] != path[i - 1]:
            cleaned.append(path[i])
    if cleaned[0] != cleaned[-1]:
        cleaned.append(cleaned[0])
    return cleaned, [(p[0], p[1], z_level) for p in cleaned]


def create_boundary_from_columns(Building, floor_label, column_top_points, z_level):
    if not column_top_points:
        return None, [], []
    boundary_2d, boundary_3d = create_rectilinear_boundary(column_top_points, z_level)
    if not boundary_2d or len(boundary_2d) < 3:
        return None, [], []
    if not rs.IsLayer("Boundary_Points"):
        rs.AddLayer("Boundary_Points", (0, 100, 255))
    if not rs.IsLayer("Floor_Boundary"):
        rs.AddLayer("Floor_Boundary", (0, 100, 255))
    boundary = rs.AddPolyline(boundary_3d)
    if boundary:
        rs.ObjectLayer(boundary, "Floor_Boundary")
        rs.ObjectColor(boundary, (0, 100, 255))
    Building["floors"]["boundaries_per_floor"].append(boundary)
    Building["floors"]["boundary_points_per_floor"].append(boundary_3d)
    Building["geometry"]["floor_boundaries"].append(boundary)
    sc.doc.Views.Redraw()
    return boundary, boundary_2d, boundary_3d


# ============================================================ API SLIDER FUNCTIONS ============================================================
def create_slider_values(start, end, step):
    values = []
    current = start
    while current <= end + 0.001:
        values.append(round(current, 4))
        current += step
    return values


def format_slider_labels(values, unit):
    return ["{} {}".format(int(val) if val == int(val) else val, unit) for val in values]


def get_number_from_label(label_text):
    return float(label_text.split(" ")[0])


def show_vibrant_slider(title, message, values, default_val, unit, icon_emoji, header_color, bg_color):
    labels = format_slider_labels(values, unit)
    default_label = "{} {}".format(int(default_val) if default_val == int(default_val) else default_val, unit)
    if default_label not in labels:
        default_label = labels[0]
    dialog = VibrantSliderDialog(title, message, labels, default_label, icon_emoji, header_color, bg_color, values, unit)
    dialog.ShowModal(Rhino.UI.RhinoEtoApp.MainWindow)
    if dialog.selected_value is None:
        return None
    return get_number_from_label(dialog.selected_value)


def show_vibrant_list(title, message, values, default_val, unit, icon_emoji, header_color, bg_color):
    labels = format_slider_labels(values, unit)
    default_label = "{} {}".format(int(default_val) if default_val == int(default_val) else default_val, unit)
    if default_label not in labels:
        default_label = labels[0]
    dialog = VibrantListDialog(title, message, labels, default_label, icon_emoji, header_color, bg_color)
    dialog.ShowModal(Rhino.UI.RhinoEtoApp.MainWindow)
    if dialog.selected_value is None:
        return None
    return get_number_from_label(dialog.selected_value)


# ============================================================ THEME CONFIGURATION ============================================================
THEME_PLOT_LENGTH = {"icon": "📐", "header": (0, 120, 60), "bg": (51, 55, 52)}
THEME_PLOT_WIDTH = {"icon": "📏", "header": (0, 100, 80), "bg": (50, 54, 52)}
THEME_GRID_SPACING = {"icon": "🔲", "header": (25, 25, 112), "bg": (50, 51, 56)}
THEME_COLUMN_WIDTH = {"icon": "🏛️", "header": (139, 69, 19), "bg": (56, 53, 50)}
THEME_BEAM_WIDTH = {"icon": "🪵", "header": (101, 67, 33), "bg": (55, 52, 49)}
THEME_GRID_EXTENSION = {"icon": "↔️", "header": (0, 100, 148), "bg": (49, 53, 56)}
THEME_FLOOR_HEIGHT = {"icon": "🏗️", "header": (180, 50, 50), "bg": (56, 51, 51)}
THEME_ROOF = {"icon": "🏠", "header": (120, 60, 20), "bg": (56, 53, 51)}
THEME_BASEMENT = {"icon": "🧱", "header": (100, 60, 30), "bg": (55, 52, 49)}


# ============================================================ NORTH SIDE, ROAD, DIMENSIONS ============================================================


def determine_north_side(click_point, plot_length, plot_width):
    x, y = click_point[0], click_point[1]
    half_l, half_w = plot_length / 2.0, plot_width / 2.0
    dists = {"Top": abs(y - half_w), "Bottom": abs(y + half_w), "Right": abs(x - half_l), "Left": abs(x + half_l)}
    return min(dists, key=dists.get)


def draw_north_indicator(Building, north_side, plot_length, plot_width):
    layer_name = "North_Indicator"
    if not rs.IsLayer(layer_name):
        rs.AddLayer(layer_name, (0, 80, 180))
    half_l, half_w = plot_length / 2.0, plot_width / 2.0
    configs = {
        "Top": (half_l - 3, half_w, 0, 1, 1, 0),
        "Bottom": (half_l - 3, -half_w, 0, -1, 1, 0),
        "Right": (half_l, half_w - 3, 1, 0, 0, 1),
        "Left": (-half_l, half_w - 3, -1, 0, 0, 1)
    }
    mid_x, mid_y, arrow_dx, arrow_dy, perp_dx, perp_dy = configs[north_side]
    shaft_start = (mid_x, mid_y, 0)
    shaft_end = (mid_x + arrow_dx * 3, mid_y + arrow_dy * 3, 0)
    tip = (shaft_end[0] + arrow_dx, shaft_end[1] + arrow_dy, 0)
    head_left = (shaft_end[0] + perp_dx * 0.7, shaft_end[1] + perp_dy * 0.7, 0)
    head_right = (shaft_end[0] - perp_dx * 0.7, shaft_end[1] - perp_dy * 0.7, 0)
    for obj in [rs.AddLine(shaft_start, shaft_end), rs.AddPolyline([tip, head_left, head_right, tip])]:
        if obj:
            rs.ObjectLayer(obj, layer_name)
            rs.ObjectColor(obj, (0, 80, 180))
    circle_center = (tip[0] + arrow_dx * 1.5, tip[1] + arrow_dy * 1.5, 0)
    for obj in [rs.AddCircle(circle_center, 3.0), rs.AddText("N", circle_center, 3.0, font="Arial", font_style=1, justification=131074)]:
        if obj:
            rs.ObjectLayer(obj, layer_name)
            rs.ObjectColor(obj, (0, 80, 180))
    sc.doc.Views.Redraw()


def draw_road(Building, north_side, plot_length, plot_width):
    layer_name = "Road"
    if not rs.IsLayer(layer_name):
        rs.AddLayer(layer_name, (120, 120, 120))
    half_l, half_w = plot_length / 2.0, plot_width / 2.0
    rw, re = Building["road"]["width"], Building["road"]["extension"]
    if north_side == "Top":
        corners = [(-half_l - re, half_w, 0), (half_l + re, half_w, 0), (half_l + re, half_w + rw, 0), (-half_l - re, half_w + rw, 0), (-half_l - re, half_w, 0)]
    elif north_side == "Bottom":
        corners = [(-half_l - re, -half_w, 0), (half_l + re, -half_w, 0), (half_l + re, -half_w - rw, 0), (-half_l - re, -half_w - rw, 0), (-half_l - re, -half_w, 0)]
    elif north_side == "Right":
        corners = [(half_l, -half_w - re, 0), (half_l + rw, -half_w - re, 0), (half_l + rw, half_w + re, 0), (half_l, half_w + re, 0), (half_l, -half_w - re, 0)]
    else:
        corners = [(-half_l, -half_w - re, 0), (-half_l - rw, -half_w - re, 0), (-half_l - rw, half_w + re, 0), (-half_l, half_w + re, 0), (-half_l, -half_w - re, 0)]
    road_polyline = rs.AddPolyline(corners)
    if road_polyline:
        rs.ObjectLayer(road_polyline, layer_name)
        rs.ObjectColor(road_polyline, (120, 120, 120))
        Building["road"]["boundary"] = road_polyline
    road_srf = rs.AddPlanarSrf([road_polyline])
    if road_srf:
        for srf in road_srf:
            rs.ObjectLayer(srf, layer_name)
            rs.ObjectColor(srf, (180, 180, 180))
    sc.doc.Views.Redraw()


def draw_plot_dimensions(Building, north_side, plot_length, plot_width):
    layer_name = "Plot_Dimensions"
    if not rs.IsLayer(layer_name):
        rs.AddLayer(layer_name, (50, 50, 50))
    half_l, half_w = plot_length / 2.0, plot_width / 2.0
    lt = "{} m".format(int(plot_length) if plot_length == int(plot_length) else plot_length)
    wt = "{} m".format(int(plot_width)  if plot_width  == int(plot_width)  else plot_width)

    # Text height fixed at 3.0 m for clean metre-scale visibility
    txt_h = 3.0
    tick  = 1.5    # tick mark half-length
    do    = 5.0    # dimension line offset from plot edge

    ls = "Bottom" if north_side == "Top" else ("Top" if north_side == "Bottom" else "Bottom")
    ws = "Left"   if north_side == "Right" else ("Right" if north_side == "Left" else "Left")

    # Horizontal dimension (plot length)
    dim_y  = -half_w - do if ls == "Bottom" else half_w + do
    txt_y  = dim_y + (-txt_h if ls == "Bottom" else txt_h)
    for obj in [
        rs.AddLine((-half_l, dim_y, 0), (half_l, dim_y, 0)),
        rs.AddLine((-half_l, dim_y - tick, 0), (-half_l, dim_y + tick, 0)),
        rs.AddLine(( half_l, dim_y - tick, 0), ( half_l, dim_y + tick, 0)),
        rs.AddText(lt, (0, txt_y, 0), txt_h, font="Arial", justification=131074),
    ]:
        if obj:
            rs.ObjectLayer(obj, layer_name)
            rs.ObjectColor(obj, (50, 50, 50))

    # Vertical dimension (plot width)
    dim_x  = -half_l - do if ws == "Left" else half_l + do
    txt_x  = dim_x + (-txt_h if ws == "Left" else txt_h)
    for obj in [
        rs.AddLine((dim_x, -half_w, 0), (dim_x, half_w, 0)),
        rs.AddLine((dim_x - tick, -half_w, 0), (dim_x + tick, -half_w, 0)),
        rs.AddLine((dim_x - tick,  half_w, 0), (dim_x + tick,  half_w, 0)),
        rs.AddText(wt, (txt_x, 0, 0), txt_h, font="Arial", justification=131074),
    ]:
        if obj:
            rs.ObjectLayer(obj, layer_name)
            rs.ObjectColor(obj, (50, 50, 50))
    sc.doc.Views.Redraw()


def assign_north_side(Building):
    plot_length, plot_width = Building["plot"]["length"], Building["plot"]["width"]
    click_point = rs.GetPoint("Click on a SIDE of the plot to assign as NORTH (road entry)")
    north_side = determine_north_side(click_point, plot_length, plot_width) if click_point else "Top"
    Building["plot"]["north_side"] = north_side
    Building["plot"]["north_direction"] = north_side
    draw_north_indicator(Building, north_side, plot_length, plot_width)
    draw_road(Building, north_side, plot_length, plot_width)
    draw_plot_dimensions(Building, north_side, plot_length, plot_width)
    rs.ZoomExtents()
    rs.Redraw()
    return True


# ============================================================ INPUT COLLECTION FUNCTIONS ============================================================
def get_plot_dimensions(Building):
    plot_slider_values = create_slider_values(20, 50, 5)
    setback_values = [2.0, 2.5, 3.0, 3.5, 4.0]
    dialog = PlotSetupDialog(plot_slider_values, 25, "metres", setback_values, 3.0, "metres")
    dialog.ShowModal(Rhino.UI.RhinoEtoApp.MainWindow)
    if dialog.selected_length is None or dialog.selected_width is None or dialog.selected_setback is None:
        return False
    Building["plot"]["length"]  = dialog.selected_length
    Building["plot"]["width"]   = dialog.selected_width
    Building["plot"]["setback"] = dialog.selected_setback
    return True


def get_setback_distance(Building):
    setback = show_vibrant_list("SETBACK DISTANCE", "Select setback distance:", [2.0, 2.5, 3.0, 3.5, 4.0], 3.0, "metres", "🛣️", (25, 100, 150), (230, 245, 255))
    if setback is None:
        return False
    Building["plot"]["setback"] = setback
    return True


def auto_calc_grid_spacing(plot_length, plot_width):
    shorter = min(plot_length, plot_width)
    candidates = [4, 4.5, 5]
    best = 4
    best_remainder = float("inf")
    for c in candidates:
        r = shorter % c
        if r < best_remainder:
            best_remainder = r
            best = c
    return float(best)


def auto_calc_grid_extension(setback):
    """Return beam overhang/extension beyond the column grid in metres."""
    raw = setback - 0.5
    return round(max(1.0, min(2.0, raw)) * 2) / 2


def _gk_fire_minutes(total_height_m):
    """Return (Gebäudeklasse, fire_resistance_minutes) for a timber building.

    Per MBO / BauO NRW 2018 and MHolzBauRL 2024:
      GK1-3  h ≤ 7 m  → no fire requirement (0 min)
      GK4    7m < h ≤ 13m → hochfeuerhemmend R60 (60 min)
      GK5    13m < h ≤ 22m → feuerbeständig R90 (90 min)
    """
    if total_height_m <= 7.0:
        return 3, 0
    elif total_height_m <= 13.0:
        return 4, 60
    else:
        return 5, 90


def auto_calc_column_width(grid_spacing, num_floors=3):
    """Return the UNIFIED square section size for BOTH columns and beams.

    Columns and beams share the same square dimension — the governing check
    across both elements determines the single b value.

    Governs are checked in order:
      1. Beam bending  (EC5 §6.1.6) — b³/6 ≥ M/fm,d
      2. Beam deflection L/300       — b⁴ ≥ 5qL³×12×300/(384E)
      3. Column buckling (EC5 §6.3.2) — Euler stability with kc
      4. Fire R60 column (EC5-1-2)  — b ≥ 200mm, residual ≥ 80mm (4 sides)
      5. Fire R60 beam   (EC5-1-2)  — b ≥ 160mm, residual ≥ 80mm (3 sides)

    All GL24h:  fm,g,k=24 MPa  fc,0,g,k=24 MPa  E_mean=11600 MPa  E_0,05=9400 MPa
                kmod=0.8  γ_M=1.25  β_n=0.7 mm/min

    Returns width (= depth) in metres, rounded to 20 mm.
    """
    import math
    # GL24h design values
    fm_d   = 24.0 * 0.8 / 1.25   # 15.36 MPa bending
    fc0gd  = 24.0 * 0.8 / 1.25   # 15.36 MPa compression parallel
    E      = 11600.0               # MPa E_mean
    E05    = 9400.0                # MPa 5th-percentile
    betac  = 0.1                   # glulam imperfection factor
    gs     = grid_spacing
    L      = gs * 1000.0           # mm span
    q      = 5.0 * gs              # N/mm (5 kN/m² × tributary width = gs)

    # ── 1. Beam bending (square W = b³/6) ──────────────────────────────────
    M_Nmm  = q * L ** 2 / 8.0     # N·mm  (q in N/mm, L in mm)
    W_req  = M_Nmm / fm_d         # mm³
    b_bend = (6.0 * W_req) ** (1.0 / 3.0)   # mm

    # ── 2. Beam deflection L/300 (square I = b⁴/12) ────────────────────────
    b_defl = (5.0 * q * L ** 3 * 12.0 * 300.0 / (384.0 * E)) ** 0.25  # mm

    # ── 3. Column Euler buckling ────────────────────────────────────────────
    h_storey = 3.5                             # m
    leff     = 0.7 * h_storey * 1000.0        # mm
    N_uls    = 5.0 * gs ** 2 * num_floors * 1000.0   # N

    b_col = 80.0
    for b in range(80, 600, 20):
        i   = b / math.sqrt(12.0)
        lam = leff / i
        lr  = (lam / math.pi) * math.sqrt(24.0 / E05)
        k   = 0.5 * (1.0 + betac * (lr - 0.3) + lr ** 2)
        kc  = min(1.0, 1.0 / (k + math.sqrt(max(0.0, k ** 2 - lr ** 2))))
        if kc * b ** 2 * fc0gd >= N_uls * 1.15:
            b_col = float(b)
            break

    # ── 4 & 5. Fire design (EC5-1-2 / BauO NRW 2018) ──────────────────────
    est_h   = 1.0 + num_floors * h_storey
    _, fire_min = _gk_fire_minutes(est_h)
    d_char  = 0.7 * fire_min                  # mm per side
    if fire_min >= 60:
        b_fire_col = max(200.0, 80.0 + 2.0 * d_char)   # 4-sided col, residual ≥ 80mm
        b_fire_bm  = max(160.0, 80.0 + 2.0 * d_char)   # 3-sided beam, residual ≥ 80mm
    elif fire_min >= 30:
        b_fire_col = 160.0; b_fire_bm = 120.0
    else:
        b_fire_col = 80.0;  b_fire_bm = 80.0

    # ── Governing unified dimension ─────────────────────────────────────────
    b_gov = max(b_bend, b_defl, b_col, b_fire_col, b_fire_bm)
    b_std = math.ceil(b_gov / 20.0) * 20      # round up to 20 mm
    return round(b_std / 1000.0, 3)           # metres

def auto_calc_beam_width(grid_spacing, num_floors=3):
    """Return (width_m, depth_m) for primary beam — same square dimension as column.

    Beams and columns share one square size computed by auto_calc_column_width.
    Returns a tuple (b, b) so existing callers using (width, depth) still work.
    """
    b = auto_calc_column_width(grid_spacing, num_floors)
    return b, b   # square: width = depth

def calculate_wooden_beam_depth(span, beam_width, num_floors=3):
    """Return beam depth = beam_width (square section).
    auto_calc_beam_width returns (b, b) for square; depth = width.
    """
    _, depth = auto_calc_beam_width(span, num_floors)
    return round(depth * 20.0) / 20.0


def get_grid_spacing(Building):
    """Calculate and store the optimal grid spacing from plot dimensions.
    Called early in main() before get_column_inputs.
    """
    plot_length = Building["plot"]["length"]
    plot_width  = Building["plot"]["width"]
    Building["grid"]["spacing"] = auto_calc_grid_spacing(plot_length, plot_width)
    return True


def get_column_inputs(Building):
    """Show the StructuralAndBoundaryDialog and store column/beam sizing.
    Uses unified square section (beam = column) based on EC5 + EC5-1-2.
    """
    plot_length  = Building["plot"]["length"]
    plot_width   = Building["plot"]["width"]
    grid_spacing = Building["grid"]["spacing"]
    num_floors   = Building["floors"].get("num_upper_floors", 2) + 2
    column_width = auto_calc_column_width(grid_spacing, num_floors)
    column_height = 1.0
    beam_width, _ = auto_calc_beam_width(grid_spacing, num_floors)
    grid_extension = auto_calc_grid_extension(Building["plot"].get("setback", 3.0))

    # Gebäudeklasse note for dialog
    est_h = 1.0 + num_floors * 3.5
    gk, fire_min = _gk_fire_minutes(est_h)
    fire_note = "GK{} R{}".format(gk, fire_min) if fire_min > 0 else "GK{} no fire req".format(gk)
    span_note = (
        "Grid {:.1f}m | {} | EC5+EC5-1-2 BauO NRW 2018 | "
        "Beam=Col={}x{}mm GL24h".format(
            grid_spacing, fire_note,
            int(column_width * 1000), int(column_width * 1000))
    )
    dlg = StructuralAndBoundaryDialog(
        grid_spacing, column_width, column_height, beam_width, grid_extension, span_note)
    if not dlg.ShowModal(Rhino.UI.RhinoEtoApp.MainWindow):
        return False
    Building["structure"]["columns"]["width"]  = column_width
    Building["structure"]["columns"]["height"] = column_height
    Building["floors"]["floor_heights"].append(column_height)
    return True


def get_plinth_beam_width(Building):
    grid_spacing = Building["grid"]["spacing"]
    num_floors   = Building["floors"].get("num_upper_floors", 2) + 2
    bw, bd       = auto_calc_beam_width(grid_spacing, num_floors)
    Building["structure"]["plinth_beams"]["width"] = bw
    Building["structure"]["plinth_beams"]["depth"] = bd
    return True


def get_grid_extension_for_floor(Building, floor_label):
    setback   = Building["plot"].get("setback", 3.0)
    extension = auto_calc_grid_extension(setback)
    Building["structure"]["plinth_beams"]["extension_per_floor"].append(extension)
    return extension


def get_additional_floors(Building):
    dialog = FloorCountDialog()
    dialog.ShowModal(Rhino.UI.RhinoEtoApp.MainWindow)
    if dialog.selected_upper_floors < 0:
        return False
    Building["floors"]["num_upper_floors"] = dialog.selected_upper_floors
    Building["floors"]["num_floors"] = 1 + dialog.selected_upper_floors
    return True


def get_upper_floor_height(Building, floor_label):
    floor_height = Building["floors"].get("common_floor_height", 3.0)
    Building["floors"]["floor_heights"].append(floor_height)
    Building["floors"]["total_height"] = sum(Building["floors"]["floor_heights"])
    return floor_height


def get_roof_column_height(Building):
    roof_height = Building["floors"].get("common_floor_height", 3.0)
    Building["floors"]["floor_heights"].append(roof_height)
    Building["floors"]["total_height"] = sum(Building["floors"]["floor_heights"])
    return roof_height


# ============================================================ GEOMETRY GENERATION ============================================================
def draw_outer_plot_boundary(Building):
    pl, pw = Building["plot"]["length"], Building["plot"]["width"]
    if not rs.IsLayer("Outer_Plot_Boundary"):
        rs.AddLayer("Outer_Plot_Boundary", (90, 90, 90))
    b = rs.AddPolyline([(-pl / 2, -pw / 2, 0), (pl / 2, -pw / 2, 0), (pl / 2, pw / 2, 0), (-pl / 2, pw / 2, 0), (-pl / 2, -pw / 2, 0)])
    if b:
        rs.ObjectLayer(b, "Outer_Plot_Boundary")
        rs.ObjectColor(b, (90, 90, 90))
    rs.ZoomExtents()
    rs.Redraw()


def draw_plot_boundary(Building):
    fl, fw = Building["plot"]["length"], Building["plot"]["width"]
    sb = Building["plot"].get("setback", 0.0)
    el, ew = max(0.01, fl - 2 * sb), max(0.01, fw - 2 * sb)
    if not rs.IsLayer("Plot_Boundary"):
        rs.AddLayer("Plot_Boundary", (128, 128, 128))
    p = rs.AddPolyline([(-el / 2, -ew / 2, 0), (el / 2, -ew / 2, 0), (el / 2, ew / 2, 0), (-el / 2, ew / 2, 0), (-el / 2, -ew / 2, 0)])
    if p:
        rs.ObjectLayer(p, "Plot_Boundary")
        rs.ObjectColor(p, (128, 128, 128))
        try:
            rs.ObjectLinetype(p, "Dashed")
        except:
            pass
        Building["plot"]["boundary"] = p
        Building["geometry"]["plot_boundary"] = p
    rs.ZoomExtents()
    rs.Redraw()
    return True




def generate_foundation_grid(Building):
    fl, fw = Building["plot"]["length"], Building["plot"]["width"]
    sb = Building["plot"].get("setback", 0.0)
    el, ew = max(0.01, fl - 2 * sb), max(0.01, fw - 2 * sb)
    gs = Building["grid"]["spacing"]
    nx, ny = int(el / gs) + 1, int(ew / gs) + 1
    if not rs.IsLayer("Foundation_Grid"):
        rs.AddLayer("Foundation_Grid", (255, 0, 0))
    fps = []
    ox, oy = -el / 2.0, -ew / 2.0
    for i in range(nx):
        for j in range(ny):
            x, y = round(i * gs + ox, 4), round(j * gs + oy, 4)
            pid = rs.AddPoint(x, y, 0)
            if pid:
                rs.ObjectLayer(pid, "Foundation_Grid")
                rs.ObjectColor(pid, (255, 0, 0))
                fps.append(pid)
    Building["grid"]["foundation_points"] = fps
    Building["geometry"]["foundation_grid"] = fps
    rs.ZoomExtents()
    rs.Redraw()
    return True


def select_column_points_floor1(Building):
    selected_coords = draw_selection_polyline_for_columns(Building, z_level=0)
    if not selected_coords:
        return False
    # Build the set of valid grid positions (all foundation grid intersections)
    # so auto-bridge points are confined to actual beam intersection candidates.
    gs  = Building["grid"]["spacing"]
    fl  = Building["plot"]["length"]
    fw  = Building["plot"]["width"]
    sb  = Building["plot"].get("setback", 0.0)
    el  = max(0.01, fl - 2 * sb)
    ew  = max(0.01, fw - 2 * sb)
    ox, oy = -el / 2.0, -ew / 2.0
    nx, ny = int(el / gs) + 1, int(ew / gs) + 1
    valid_grid_positions = set()
    for i in range(nx):
        for j in range(ny):
            valid_grid_positions.add((round(i * gs + ox, 4), round(j * gs + oy, 4)))
    updated_coords, added_coords = ensure_floor_connectivity(
        selected_coords, gs, z_level=0, valid_positions=valid_grid_positions)
    Building["grid"]["selected_column_points"] = []
    Building["grid"]["selected_points_per_floor"] = [[]]
    Building["grid"]["selected_coords_per_floor"] = [updated_coords]
    rs.Redraw()
    return True


def create_floor_columns(Building, floor_label, base_z, floor_height, selected_point_coords):
    column_width = Building["structure"]["columns"]["width"]
    if not rs.IsLayer("Columns"):
        rs.AddLayer("Columns", (100, 100, 100))
    floor_columns, floor_top_points = [], []
    half_width = column_width / 2.0
    for pt_coord in selected_point_coords:
        x, y, z = pt_coord[0], pt_coord[1], base_z
        bottom_corners = [(x - half_width, y - half_width, z), (x + half_width, y - half_width, z),
                          (x + half_width, y + half_width, z), (x - half_width, y + half_width, z),
                          (x - half_width, y - half_width, z)]
        bottom_profile = rs.AddPolyline(bottom_corners)
        if bottom_profile:
            profile_curve = rs.coercecurve(bottom_profile)
            if profile_curve:
                extrusion = rg.Extrusion.Create(profile_curve, floor_height, True)
                if extrusion:
                    column_brep = sc.doc.Objects.AddBrep(extrusion.ToBrep())
                    if column_brep:
                        rs.ObjectLayer(column_brep, "Columns")
                        floor_columns.append(column_brep)
                        floor_top_points.append((x, y, z + floor_height))
            rs.DeleteObject(bottom_profile)
    Building["structure"]["columns"]["objects"].extend(floor_columns)
    Building["structure"]["columns"]["objects_per_floor"].append(floor_columns)
    Building["structure"]["columns"]["top_points_per_floor"].append(floor_top_points)
    print("  {} columns: {} at Z={:.2f} to Z={:.2f}".format(floor_label, len(floor_columns), base_z, base_z + floor_height))
    sc.doc.Views.Redraw()
    return floor_top_points


def find_continuous_segments(columns_on_line, grid_spacing, tolerance=0.01):
    if not columns_on_line:
        return []
    if len(columns_on_line) == 1:
        return [(columns_on_line[0], columns_on_line[0])]
    segments = []
    seg_s = seg_e = columns_on_line[0]
    for i in range(1, len(columns_on_line)):
        if abs(columns_on_line[i] - (seg_e + grid_spacing)) < tolerance:
            seg_e = columns_on_line[i]
        else:
            segments.append((seg_s, seg_e))
            seg_s = seg_e = columns_on_line[i]
    segments.append((seg_s, seg_e))
    return segments


def create_single_beam(start_pt, end_pt, beam_width, beam_depth):
    length = start_pt.DistanceTo(end_pt)
    if length < 0.001:
        return None
    direction = rg.Vector3d(end_pt - start_pt)
    direction.Unitize()
    perp_dir = rg.Vector3d(-direction.Y, direction.X, 0)
    perp_dir.Unitize()
    hw = beam_width / 2.0
    bottom_corners = [start_pt + perp_dir * hw, start_pt - perp_dir * hw,
                      end_pt - perp_dir * hw, end_pt + perp_dir * hw,
                      start_pt + perp_dir * hw]
    bottom_profile = rs.AddPolyline(bottom_corners)
    if bottom_profile:
        profile_curve = rs.coercecurve(bottom_profile)
        if profile_curve:
            extrusion = rg.Extrusion.Create(profile_curve, beam_depth, True)
            if extrusion:
                beam_brep = sc.doc.Objects.AddBrep(extrusion.ToBrep())
                rs.DeleteObject(bottom_profile)
                return beam_brep
        rs.DeleteObject(bottom_profile)
    return None


def create_floor_beams_with_structural_logic(Building, floor_label, floor_top_points, extension):
    """Create floor beams as single continuous members including cantilever overhangs.

    Each beam runs from (start - extension) to (end + extension) as ONE Brep object,
    eliminating the visible seam/gap that appears when extension is a separate piece.

    Extension rule: add an overhang at a segment endpoint when there is NO column
    beyond that endpoint in the same row direction. This works correctly for both
    rectangular and irregular (L-shaped, stepped) floor plans.

    Specifically:
      - Y-direction beam at fixed X, segment ss→se:
          extend at ss if (ss - grid_spacing) is not in this X-row
          extend at se if (se + grid_spacing) is not in this X-row
      - X-direction beam at fixed Y: same logic for X endpoints
    """
    beam_width   = Building["structure"]["plinth_beams"]["width"]
    beam_depth   = Building["structure"]["plinth_beams"]["depth"]
    grid_spacing = Building["grid"]["spacing"]
    max_cant     = Building["structure"]["plinth_beams"]["max_cantilever"]
    if not rs.IsLayer("Wooden_Beam"):
        rs.AddLayer("Wooden_Beam", (139, 69, 19))
    if not floor_top_points:
        return [], []

    beam_z          = floor_top_points[0][2]
    actual_ext      = min(extension, max_cant)
    floor_beams     = []
    column_positions = set([(round(pt[0], 4), round(pt[1], 4)) for pt in floor_top_points])
    tol             = 0.01

    x_coords = sorted(list(set([round(pt[0], 4) for pt in floor_top_points])))
    y_coords = sorted(list(set([round(pt[1], 4) for pt in floor_top_points])))

    # ── Y-direction beams (running in Y at fixed X) ───────────────────────
    for x in x_coords:
        row_y = sorted([round(pt[1], 4) for pt in floor_top_points if abs(pt[0] - x) < tol])
        row_y_set = set(row_y)
        if not row_y:
            continue
        for ss, se in find_continuous_segments(row_y, grid_spacing, tol):
            # Extend at ss if there is no column one step before ss in this row
            ext_start = actual_ext if (round(ss - grid_spacing, 4) not in row_y_set) else 0.0
            # Extend at se if there is no column one step after se in this row
            ext_end   = actual_ext if (round(se + grid_spacing, 4) not in row_y_set) else 0.0

            y_from = ss - ext_start
            y_to   = se + ext_end

            if abs(y_to - y_from) < tol:
                continue
            b = create_single_beam(
                rg.Point3d(x, y_from, beam_z),
                rg.Point3d(x, y_to,   beam_z),
                beam_width, beam_depth)
            if b:
                rs.ObjectLayer(b, "Wooden_Beam")
                floor_beams.append(b)

    # ── X-direction beams (running in X at fixed Y) ───────────────────────
    for y in y_coords:
        row_x = sorted([round(pt[0], 4) for pt in floor_top_points if abs(pt[1] - y) < tol])
        row_x_set = set(row_x)
        if not row_x:
            continue
        for ss, se in find_continuous_segments(row_x, grid_spacing, tol):
            ext_start = actual_ext if (round(ss - grid_spacing, 4) not in row_x_set) else 0.0
            ext_end   = actual_ext if (round(se + grid_spacing, 4) not in row_x_set) else 0.0

            x_from = ss - ext_start
            x_to   = se + ext_end

            if abs(x_to - x_from) < tol:
                continue
            b = create_single_beam(
                rg.Point3d(x_from, y, beam_z),
                rg.Point3d(x_to,   y, beam_z),
                beam_width, beam_depth)
            if b:
                rs.ObjectLayer(b, "Wooden_Beam")
                floor_beams.append(b)

    all_intersections = [
        (x, y, beam_z) for x in x_coords for y in y_coords
        if (round(x, 4), round(y, 4)) in column_positions
    ]
    Building["structure"]["plinth_beams"]["objects"].extend(floor_beams)
    Building["structure"]["plinth_beams"]["objects_per_floor"].append(floor_beams)
    Building["structure"]["plinth_beams"]["intersection_points_per_floor"].append(all_intersections)
    print("  {} beams: {} at Z={:.2f}".format(floor_label, len(floor_beams), beam_z))
    sc.doc.Views.Redraw()
    return floor_beams, all_intersections


def generate_intersection_grid_from_floor(Building, grid_label, all_intersections):
    if not all_intersections:
        return [], 0
    beam_depth = Building["structure"]["plinth_beams"]["depth"]
    floor_z = all_intersections[0][2] + beam_depth
    if not rs.IsLayer(grid_label):
        rs.AddLayer(grid_label, (0, 0, 255))
    grid_point_ids = []
    for pt in all_intersections:
        pt_id = rs.AddPoint(pt[0], pt[1], floor_z)
        if pt_id:
            rs.ObjectLayer(pt_id, grid_label)
            rs.ObjectColor(pt_id, (0, 0, 255))
            grid_point_ids.append(pt_id)
    rs.Redraw()
    return grid_point_ids, floor_z


def select_columns_from_grid(Building, floor_label, grid_point_ids, all_intersections, z_level):
    available_points = [(pt[0], pt[1], z_level) for pt in all_intersections]
    selected_coords = select_columns_by_polyline_for_upper_floor(Building, floor_label, available_points, z_level)
    if not selected_coords:
        return []
    # Constrain auto-bridge points to actual beam intersections on this floor
    valid_beam_positions = set((round(pt[0], 4), round(pt[1], 4)) for pt in all_intersections)
    updated_coords, added_coords = ensure_floor_connectivity(
        selected_coords, Building["grid"]["spacing"], z_level,
        valid_positions=valid_beam_positions)
    Building["grid"]["selected_points_per_floor"].append([])
    Building["grid"]["selected_coords_per_floor"].append(updated_coords)
    rs.Redraw()
    return updated_coords


def cleanup_layer(layer_name):
    if rs.IsLayer(layer_name):
        objs = rs.ObjectsByLayer(layer_name)
        if objs:
            rs.DeleteObjects(objs)
        rs.DeleteLayer(layer_name)


# ============================================================ FLOOR PROCESSING FUNCTIONS ============================================================

def _cascade_seed(plot_length, plot_width, floor_num):
    """Deterministic seed — same building always gives same pixelation."""
    return int(abs(plot_length * 100 + plot_width * 37 + floor_num * 13)) % 9999


def auto_cascade_columns(previous_intersections, floor_num, grid_spacing,
                         plot_length=None, plot_width=None):
    """S'lowtecture cellular automata cascade for stepped terrace housing.

    Cell states (each 2x2 column square = one cubic room):
      B (BUILT)  — structural room, fully enclosed
      G (GARDEN) — open terrace, adjacent to built zone
      E (EMPTY)  — void, no structure

    Rules (from s'lowtecture game logic):
    1. Each BUILT cell is surrounded by GARDEN/EMPTY neighbourhood cells
    2. Cascade: cells near SW perimeter become EMPTY as floor rises
    3. GARDEN cells appear at the Built/Empty boundary (terraces)
    4. BUILT cells must stay connected — isolated clusters downgraded
    5. GARDEN cells must be adjacent to at least one BUILT cell
    6. Min 2×2 BUILT cells guaranteed at NE corner (deepest terrace)
    7. Pixelation notches at built boundary create informal silhouette
    8. Fully deterministic from plot dimensions
    """
    if not previous_intersections:
        return []

    xs = sorted(set(round(pt[0], 4) for pt in previous_intersections))
    ys = sorted(set(round(pt[1], 4) for pt in previous_intersections))
    nx, ny = len(xs), len(ys)
    gs = grid_spacing
    cx, cy = nx - 1, ny - 1  # cell grid dimensions

    if nx < 2 or ny < 2 or cx < 1 or cy < 1:
        return list(previous_intersections)

    pl = plot_length if plot_length else (xs[-1] - xs[0])
    pw = plot_width  if plot_width  else (ys[-1] - ys[0])
    seed = _cascade_seed(pl, pw, floor_num)

    def pick(n, mod, off=0):
        return ((seed * 31 + n * 17 + off * 7) % max(mod, 1))

    # ── 1. Initial cell states based on cascade depth ────────────────────────
    cells = [['B'] * cy for _ in range(cx)]

    for cix in range(cx):
        for ciy in range(cy):
            dist_w = cix   # distance from West edge in cells
            dist_s = ciy   # distance from South edge in cells
            min_dist = min(dist_w, dist_s)

            if min_dist < floor_num - 1:
                cells[cix][ciy] = 'E'
            elif min_dist == floor_num - 1:
                # Boundary zone: Garden or Empty (seeded variation)
                cells[cix][ciy] = 'G' if pick(cix * 7 + ciy, 3) < 2 else 'E'
            # else stays 'B'

    # ── 2. Pixelation notches at Built boundary ──────────────────────────────
    notch_budget = max(1, (cx + cy) // 3)
    notch_count = 0
    for cix in range(1, cx - 1):
        for ciy in range(1, cy - 1):
            if notch_count >= notch_budget:
                break
            if cells[cix][ciy] != 'B':
                continue
            on_boundary = any(
                0 <= cix+dx < cx and 0 <= ciy+dy < cy
                and cells[cix+dx][ciy+dy] != 'B'
                for dx, dy in [(1,0),(-1,0),(0,1),(0,-1)]
            )
            if on_boundary and pick(cix * 97 + ciy, 10) < 3:
                cells[cix][ciy] = 'G'  # terrace, not void
                notch_count += 1

    # ── 3. Guarantee minimum 2×2 BUILT zone at NE corner ────────────────────
    for cix in range(cx - 2, cx):
        for ciy in range(cy - 2, cy):
            cells[cix][ciy] = 'B'

    # ── 4. BFS: keep only BUILT cells connected to NE anchor ────────────────
    visited_built = set()
    queue = [(cx - 1, cy - 1)]
    while queue:
        c = queue.pop()
        if c in visited_built:
            continue
        visited_built.add(c)
        bx, by = c
        for dx, dy in [(1,0),(-1,0),(0,1),(0,-1)]:
            nc = (bx+dx, by+dy)
            if (0 <= nc[0] < cx and 0 <= nc[1] < cy
                    and cells[nc[0]][nc[1]] == 'B'
                    and nc not in visited_built):
                queue.append(nc)

    # Downgrade unreachable BUILT cells to GARDEN
    for cix in range(cx):
        for ciy in range(cy):
            if cells[cix][ciy] == 'B' and (cix, ciy) not in visited_built:
                cells[cix][ciy] = 'G'

    # ── 5. Garden cells must touch at least one BUILT cell ───────────────────
    for cix in range(cx):
        for ciy in range(cy):
            if cells[cix][ciy] != 'G':
                continue
            adj_built = any(
                0 <= cix+dx < cx and 0 <= ciy+dy < cy
                and cells[cix+dx][ciy+dy] == 'B'
                for dx, dy in [(1,0),(-1,0),(0,1),(0,-1)]
            )
            if not adj_built:
                cells[cix][ciy] = 'E'

    # ── 6. Collect structural column positions (BUILT cells only) ────────────
    built_cols = set()
    for cix in range(cx):
        for ciy in range(cy):
            if cells[cix][ciy] == 'B':
                for dix in range(2):
                    for diy in range(2):
                        built_cols.add((cix + dix, ciy + diy))

    # Store cell states in prev_intersections metadata (for panel system)
    # Map back to result
    xi_map = {round(x, 4): i for i, x in enumerate(xs)}
    yi_map = {round(y, 4): i for i, y in enumerate(ys)}
    result = []
    for pt in previous_intersections:
        ix = xi_map.get(round(pt[0], 4))
        iy = yi_map.get(round(pt[1], 4))
        if ix is not None and iy is not None and (ix, iy) in built_cols:
            result.append(pt)

    return result if result else list(previous_intersections)


def enforce_closed_rooms(coords, grid_spacing, z_level, valid_positions=None):
    """Post-process: remove any column not forming a complete 2x2 closed cell.
    Runs iteratively until stable. Called after ensure_floor_connectivity to
    strip out any single bridge columns it added that don't close a room.
    """
    if not coords:
        return coords

    current = list(coords)
    for _ in range(len(coords)):  # max passes
        pts_set = set((round(c[0],4), round(c[1],4)) for c in current)
        # Find all valid cells
        participating = set()
        for (px, py) in pts_set:
            # Is (px,py) the SW corner of a complete cell?
            gs = grid_spacing
            corners = [(round(px+gs,4),py), (px,round(py+gs,4)),
                       (round(px+gs,4),round(py+gs,4))]
            if all(c in pts_set for c in corners):
                for dix,diy in [(0,0),(1,0),(0,1),(1,1)]:
                    participating.add((round(px+dix*gs,4), round(py+diy*gs,4)))
        new_pts = [(x,y,z) for (x,y,z) in current
                   if (round(x,4),round(y,4)) in participating]
        if len(new_pts) == len(current):
            break  # stable
        current = new_pts

    return current if current else coords  # fallback: never return empty


def process_ground_floor(Building):
    floor_height = Building["structure"]["columns"]["height"]
    selected_coords = Building["grid"]["selected_coords_per_floor"][0]
    print_section_header("BUILDING BASEMENT")
    floor_top_points = create_floor_columns(Building, "BASEMENT", 0.0, floor_height, selected_coords)
    boundary_polyline, boundary_2d, boundary_3d = create_boundary_from_columns(Building, "BASEMENT", floor_top_points, floor_height)
    if not boundary_polyline:
        return None, None
    if rs.IsLayer("Foundation_Grid"):
        objs = rs.ObjectsByLayer("Foundation_Grid")
        if objs:
            rs.DeleteObjects(objs)
    sc.doc.Views.Redraw()
    if not get_plinth_beam_width(Building):
        return None, None
    extension = get_grid_extension_for_floor(Building, "BASEMENT")
    if extension is None:
        return None, None
    floor_beams, all_intersections = create_floor_beams_with_structural_logic(Building, "BASEMENT", floor_top_points, extension)
    cleanup_all_temporary_geometry()
    print("  BASEMENT complete.")
    print_section_footer()
    return floor_top_points, all_intersections


def process_upper_floor(Building, floor_num, previous_intersections):
    floor_label = "FLOOR {}".format(floor_num)
    grid_label = "Floor_Grid_{}".format(floor_num)
    print_section_header("BUILDING {}".format(floor_label))
    cleanup_all_temporary_geometry()
    grid_points, grid_z = generate_intersection_grid_from_floor(Building, grid_label, previous_intersections)

    # Auto-cascade: stepped terrace — no user selection needed
    gs = Building["grid"]["spacing"]
    pl = Building["plot"]["length"]
    pw = Building["plot"]["width"]
    cascaded_intersections = auto_cascade_columns(previous_intersections, floor_num, gs, pl, pw)
    if not cascaded_intersections:
        cleanup_layer(grid_label)
        return None, None

    # Re-map cascaded intersections to this floor's z level
    selected_coords = [(pt[0], pt[1], grid_z) for pt in cascaded_intersections]

    # Store for connectivity record
    valid_beam_positions = set((round(pt[0], 4), round(pt[1], 4)) for pt in previous_intersections)
    updated_coords, _ = ensure_floor_connectivity(
        selected_coords, gs, grid_z, valid_positions=valid_beam_positions)
    # Strip any bridge columns that don't form closed rooms
    updated_coords = enforce_closed_rooms(updated_coords, gs, grid_z, valid_beam_positions)
    Building["grid"]["selected_points_per_floor"].append([])
    Building["grid"]["selected_coords_per_floor"].append(updated_coords)

    floor_height = get_upper_floor_height(Building, floor_label)
    if floor_height is None:
        cleanup_layer(grid_label)
        return None, None
    floor_top_points = create_floor_columns(Building, floor_label, grid_z, floor_height, updated_coords)
    boundary_polyline, boundary_2d, boundary_3d = create_boundary_from_columns(Building, floor_label, floor_top_points, grid_z + floor_height)
    if not boundary_polyline:
        cleanup_layer(grid_label)
        return None, None
    cleanup_layer(grid_label)
    extension = get_grid_extension_for_floor(Building, floor_label)
    if extension is None:
        extension = 0
    floor_beams, all_intersections = create_floor_beams_with_structural_logic(Building, floor_label, floor_top_points, extension)
    cleanup_all_temporary_geometry()
    rs.ZoomExtents()
    rs.Redraw()
    print("  {} complete — auto-cascaded inward {} m on S+W sides.".format(floor_label, gs * floor_num))
    print_section_footer()
    return floor_top_points, all_intersections


def process_roof(Building, previous_intersections):
    grid_label = "Roof_Grid"
    print_section_header("BUILDING ROOF")
    cleanup_all_temporary_geometry()
    grid_points, grid_z = generate_intersection_grid_from_floor(Building, grid_label, previous_intersections)

    # Roof: cascade one more step beyond the topmost upper floor
    num_upper = Building["floors"]["num_upper_floors"]
    gs = Building["grid"]["spacing"]
    pl = Building["plot"]["length"]
    pw = Building["plot"]["width"]
    roof_floor_num = num_upper + 1  # one more step inward than last upper floor
    cascaded_intersections = auto_cascade_columns(previous_intersections, roof_floor_num, gs, pl, pw)
    if not cascaded_intersections:
        # Fallback: use all previous intersections
        cascaded_intersections = previous_intersections
    selected_coords = [(pt[0], pt[1], grid_z) for pt in cascaded_intersections]
    valid_beam_positions = set((round(pt[0], 4), round(pt[1], 4)) for pt in previous_intersections)
    updated_coords, _ = ensure_floor_connectivity(
        selected_coords, gs, grid_z, valid_positions=valid_beam_positions)
    # Strip any bridge columns that don't form closed rooms
    updated_coords = enforce_closed_rooms(updated_coords, gs, grid_z, valid_beam_positions)
    Building["grid"]["selected_points_per_floor"].append([])
    Building["grid"]["selected_coords_per_floor"].append(updated_coords)

    roof_height = get_roof_column_height(Building)
    if roof_height is None:
        cleanup_layer(grid_label)
        return None, None
    roof_top_points = create_floor_columns(Building, "ROOF", grid_z, roof_height, updated_coords)
    create_boundary_from_columns(Building, "ROOF", roof_top_points, grid_z + roof_height)
    cleanup_layer(grid_label)
    extension = get_grid_extension_for_floor(Building, "ROOF")
    if extension is None:
        extension = 0
    roof_beams, roof_intersections = create_floor_beams_with_structural_logic(Building, "ROOF", roof_top_points, extension)
    cleanup_all_temporary_geometry()
    rs.ZoomExtents()
    rs.Redraw()
    print("  ROOF complete — auto-cascaded inward {} m on S+W sides.".format(gs * roof_floor_num))
    print_section_footer()
    return roof_top_points, roof_intersections


# ============================================================ PANEL SYSTEM ============================================================
def get_panel_cells_from_beams(Building, floor_top_points, extension, floor_index):
    if not floor_top_points:
        return []
    gs = Building["grid"]["spacing"]
    bd = Building["structure"]["plinth_beams"]["depth"]
    bz = floor_top_points[0][2]
    pz = bz + bd
    tol = 0.01
    x_coords = sorted(list(set([round(pt[0], 4) for pt in floor_top_points])))
    y_coords = sorted(list(set([round(pt[1], 4) for pt in floor_top_points])))
    h_ranges = {}
    for y in y_coords:
        cx = sorted([round(pt[0], 4) for pt in floor_top_points if abs(pt[1] - y) < tol])
        if cx:
            h_ranges[round(y, 4)] = [(round(s - extension, 4), round(e + extension, 4)) for s, e in find_continuous_segments(cx, gs, tol)]
    v_ranges = {}
    for x in x_coords:
        cy = sorted([round(pt[1], 4) for pt in floor_top_points if abs(pt[0] - x) < tol])
        if cy:
            v_ranges[round(x, 4)] = [(round(s - extension, 4), round(e + extension, 4)) for s, e in find_continuous_segments(cy, gs, tol)]
    def edge_h(x1, x2, y):
        yr = round(y, 4)
        xmn, xmx = round(min(x1, x2), 4), round(max(x1, x2), 4)
        if yr in h_ranges:
            for mn, mx in h_ranges[yr]:
                if xmn >= mn - tol and xmx <= mx + tol:
                    return True
        return False
    def edge_v(x, y1, y2):
        xr = round(x, 4)
        ymn, ymx = round(min(y1, y2), 4), round(max(y1, y2), 4)
        if xr in v_ranges:
            for mn, mx in v_ranges[xr]:
                if ymn >= mn - tol and ymx <= mx + tol:
                    return True
        return False
    all_x, all_y = set(), set()
    for xk in v_ranges:
        for ymn, ymx in v_ranges[xk]:
            all_x.add(xk)
            yv = ymn
            while yv <= ymx + tol:
                all_y.add(round(yv, 4))
                yv = round(yv + gs, 4)
    for yk in h_ranges:
        for xmn, xmx in h_ranges[yk]:
            all_y.add(yk)
            xv = xmn
            while xv <= xmx + tol:
                all_x.add(round(xv, 4))
                xv = round(xv + gs, 4)
    cells = []
    cs = set()
    for bx in sorted(all_x):
        for by in sorted(all_y):
            bxr, byr = round(bx, 4), round(by, 4)
            bx2, by2 = round(bx + gs, 4), round(by + gs, 4)
            ck = (bxr, byr)
            if ck in cs:
                continue
            if edge_h(bxr, bx2, byr) and edge_h(bxr, bx2, by2) and edge_v(bxr, byr, by2) and edge_v(bx2, byr, by2):
                cells.append({"key": ck, "x": bxr, "y": byr, "z": pz, "size": gs,
                    "corners_3d": [(bxr, byr, pz), (bx2, byr, pz), (bx2, by2, pz), (bxr, by2, pz)]})
                cs.add(ck)
    return cells


def draw_floor_panels(Building, floor_label, cells, floor_index):
    ln = "Floor_Panels_{}".format(floor_index)
    if not rs.IsLayer(ln):
        rs.AddLayer(ln, (180, 140, 100))
    panel_ids, panel_cell_map = [], {}
    for cell in cells:
        c = cell["corners_3d"]
        z = c[0][2]
        c1 = rg.Point3d(c[0][0], c[0][1], z)
        c2 = rg.Point3d(c[1][0], c[1][1], z)
        c3 = rg.Point3d(c[2][0], c[2][1], z)
        c4 = rg.Point3d(c[3][0], c[3][1], z)
        srf = rg.NurbsSurface.CreateFromCorners(c1, c2, c3, c4)
        if srf:
            pb = sc.doc.Objects.AddSurface(srf)
            if pb:
                rs.ObjectLayer(pb, ln)
                rs.ObjectColor(pb, (210, 180, 140))
                panel_ids.append(pb)
                panel_cell_map[str(pb)] = cell["key"]
    print("  {} panels drawn: {}".format(floor_label, len(panel_ids)))
    sc.doc.Views.Redraw()
    return panel_ids, panel_cell_map, ln


def create_clipping_plane_above_floor(Building, beam_z, beam_depth, floor_index, offset=1.0):
    clip_z = beam_z + beam_depth + offset
    ln = "Clipping_Plane_{}".format(floor_index)
    if not rs.IsLayer(ln):
        rs.AddLayer(ln, (255, 0, 255))
    plane = rg.Plane(rg.Point3d(0, 0, clip_z), rg.Vector3d(0, 0, -1))
    view = sc.doc.Views.ActiveView
    if not view:
        return None
    vid = view.ActiveViewportID
    cs = max(Building["plot"]["length"], Building["plot"]["width"]) + 40
    cid = sc.doc.Objects.AddClippingPlane(plane, cs, cs, [vid])
    if cid:
        rs.ObjectLayer(cid, ln)
        Building["panels"]["clipping_planes"].append(cid)
    sc.doc.Views.Redraw()
    return cid


def remove_clipping_plane(Building, floor_index):
    ln = "Clipping_Plane_{}".format(floor_index)
    if rs.IsLayer(ln):
        objs = rs.ObjectsByLayer(ln)
        if objs:
            rs.DeleteObjects(objs)
        rs.DeleteLayer(ln)
    sc.doc.Views.Redraw()


def remove_all_clipping_planes(Building):
    for cp in Building["panels"]["clipping_planes"]:
        if rs.IsObject(cp):
            rs.DeleteObject(cp)
    Building["panels"]["clipping_planes"] = []
    for i in range(20):
        ln = "Clipping_Plane_{}".format(i)
        if rs.IsLayer(ln):
            objs = rs.ObjectsByLayer(ln)
            if objs:
                rs.DeleteObjects(objs)
            rs.DeleteLayer(ln)
    sc.doc.Views.Redraw()


# ============================================================ PANEL CONNECTIVITY ============================================================
def find_panel_face_components(panel_keys, gs):
    if not panel_keys:
        return []
    ks = list(set(panel_keys))
    n = len(ks)
    if n == 0:
        return []
    parent = list(range(n))
    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    def union(i, j):
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[ri] = rj
    ki = {k: i for i, k in enumerate(ks)}
    for i, (kx, ky) in enumerate(ks):
        for nb in [(round(kx + gs, 4), round(ky, 4)), (round(kx - gs, 4), round(ky, 4)),
                    (round(kx, 4), round(ky + gs, 4)), (round(kx, 4), round(ky - gs, 4))]:
            if nb in ki:
                union(i, ki[nb])
    comps = {}
    for i, k in enumerate(ks):
        r = find(i)
        if r not in comps:
            comps[r] = []
        comps[r].append(k)
    return list(comps.values())


def is_panel_floor_connected(panel_keys, gs):
    if len(panel_keys) <= 1:
        return True
    return len(find_panel_face_components(list(panel_keys), gs)) <= 1


def find_bridge_path_between_components(comp1, comp2, gs, all_possible_keys):
    best_path = None
    best_len = float('inf')
    for p1 in comp1:
        for p2 in comp2:
            dist = abs(p1[0] - p2[0]) + abs(p1[1] - p2[1])
            if dist >= best_len:
                continue
            path = []
            cx, cy = p1
            sx = gs if p2[0] > cx else -gs
            while abs(cx - p2[0]) > 0.01:
                cx = round(cx + sx, 4)
                k = (round(cx, 4), round(cy, 4))
                if k != p1 and k != p2:
                    path.append(k)
            sy = gs if p2[1] > cy else -gs
            while abs(cy - p2[1]) > 0.01:
                cy = round(cy + sy, 4)
                k = (round(cx, 4), round(cy, 4))
                if k != p1 and k != p2:
                    path.append(k)
            valid_path = [k for k in path if k in all_possible_keys]
            if len(valid_path) < best_len:
                best_len = len(valid_path)
                best_path = valid_path
    return best_path if best_path else []


def ensure_panel_connectivity(all_panel_keys, keys_to_delete, all_possible_keys, gs):
    remaining = set(all_panel_keys) - set(keys_to_delete)
    if not remaining:
        keep = list(all_panel_keys)[0]
        return set(keys_to_delete) - {keep}, set()
    if is_panel_floor_connected(remaining, gs):
        return set(keys_to_delete), set()
    safe_to_delete = set()
    must_keep = set()
    for key in sorted(keys_to_delete):
        test_remaining = (set(all_panel_keys) - safe_to_delete - {key}) | must_keep
        if is_panel_floor_connected(test_remaining, gs):
            safe_to_delete.add(key)
        else:
            must_keep.add(key)
            print("    Panel at ({:.1f},{:.1f}) is a bridge - cannot delete.".format(key[0], key[1]))
    final_remaining = (set(all_panel_keys) - safe_to_delete) | must_keep
    if is_panel_floor_connected(final_remaining, gs):
        return safe_to_delete, set()
    print("  Floor still disconnected. Adding bridge panels...")
    bridge_adds = set()
    all_possible_set = set(all_possible_keys)
    max_iterations = 50
    iteration = 0
    while iteration < max_iterations:
        iteration += 1
        current_remaining = final_remaining | bridge_adds
        comps = find_panel_face_components(list(current_remaining), gs)
        if len(comps) <= 1:
            break
        path = find_bridge_path_between_components(comps[0], comps[1], gs, all_possible_set)
        if not path:
            found = False
            for ci in range(len(comps)):
                for cj in range(ci + 1, len(comps)):
                    path = find_bridge_path_between_components(comps[ci], comps[cj], gs, all_possible_set)
                    if path:
                        found = True
                        break
                if found:
                    break
            if not path:
                print("  WARNING: Cannot find bridge path.")
                break
        for k in path:
            if k not in current_remaining:
                bridge_adds.add(k)
                if k in safe_to_delete:
                    safe_to_delete.remove(k)
                print("    BRIDGE PANEL added at ({:.1f},{:.1f})".format(k[0], k[1]))
    return safe_to_delete, bridge_adds


def create_bridge_panel(Building, cell_key, panel_z, gs, floor_index):
    ln = "Floor_Panels_{}".format(floor_index)
    if not rs.IsLayer(ln):
        rs.AddLayer(ln, (180, 140, 100))
    bx, by = cell_key
    bx2, by2 = round(bx + gs, 4), round(by + gs, 4)
    c1 = rg.Point3d(bx,  by,  panel_z)
    c2 = rg.Point3d(bx2, by,  panel_z)
    c3 = rg.Point3d(bx2, by2, panel_z)
    c4 = rg.Point3d(bx,  by2, panel_z)
    srf = rg.NurbsSurface.CreateFromCorners(c1, c2, c3, c4)
    if srf:
        pb = sc.doc.Objects.AddSurface(srf)
        if pb:
            rs.ObjectLayer(pb, ln)
            rs.ObjectColor(pb, (255, 140, 0))
            return pb
    return None


def interactive_panel_deletion(Building, floor_label, panel_ids, panel_cell_map, panel_layer, floor_index, all_possible_keys, panel_z):
    """Silently keep ALL panels — no dialog, no per-floor popup, no user selection.
    Called from process_floor_panels; behaviour is now fully automatic.
    """
    all_keys = set(panel_cell_map.values())
    print("  Keeping all {} panels for {} (automatic).".format(len(panel_ids), floor_label))
    Building["panels"]["panel_ids_per_floor"].append(list(panel_ids))
    Building["panels"]["panel_coords_per_floor"].append(list(all_keys))
    Building["panels"]["deleted_panels_per_floor"].append([])



# ============================================================ FLOOR PURLIN SYSTEM (EC5 / DIN EN 1995-1-1) ============================================================
# Secondary floor beams (Deckenbalken / Unterzüge) subdivide each 5×5 m panel
# into smaller bays so the floor deck can span safely.
#
# Basis: DIN EN 1995-1-1 / NA + German timber construction practice
#   Material  : GL24h glulam
#   fm,g,k    : 24 MPa   fc,0,g,k : 24 MPa   E_mean : 11 600 MPa
#   kmod      : 0.8 (KLED medium / SC1)       gamma_M : 1.25
#   fm,g,d    : 24 × 0.8 / 1.25 = 15.36 MPa
#
# Floor deck spanning between purlins (typical German practice):
#   CLT  80 mm Brettsperrholz : max bay ≤ 2.0 m
#   CLT  60 mm                : max bay ≤ 1.6 m
#   Solid timber 50 mm KVH/BSH: max bay ≤ 1.2 m
# → We use 1.67 m as default max bay (80 mm CLT, common in DE residential)
# → For gs = 5 m: 2 purlins → 3 bays of 1.67 m ✓

PURLIN_MAX_BAY_M  = 1.67   # m maximum deck span between purlins (80 mm CLT)
PURLIN_LOAD_KN_M2 = 5.0    # kN/m² ULS floor load (DL+LL factored, residential)


def auto_calc_purlin_count(grid_spacing):
    """Return number of intermediate purlins per panel cell per direction.

    Formula: n = ceil(gs / max_bay) - 1
    Minimum 1 purlin regardless of span.
    For gs = 5.0 m → ceil(5.0/1.67)-1 = ceil(2.99)-1 = 3-1 = 2 purlins.
    """
    import math
    n = int(math.ceil(grid_spacing / PURLIN_MAX_BAY_M)) - 1
    return max(1, n)


def auto_calc_purlin_section(grid_spacing, n_purlins, num_floors=3):
    """EC5 + EC5-1-2  GL24h SQUARE purlin sizing.

    Purlins are SECONDARY beams spanning the full grid_spacing but with a
    NARROWER tributary: trib = grid_spacing / (n_purlins + 1).
    Because the load per metre is smaller than the primary beam, the purlin
    section is smaller — typically 1–2 sizes below the primary beam.

    SQUARE design (b × b) from first principles:
      Bending:    b³/6 ≥ M/fm,d            (square section modulus)
      Deflection: b⁴ ≥ 5qL³×12×300/(384E) (square second moment, L/300 limit)
      Fire R60:   b ≥ 120mm (secondary), residual b–2×42 ≥ 60mm (3-sided)

    Returns (width_m, depth_m, section_name) — width = depth (square).
    """
    import math
    fm_d = 15.36          # MPa  GL24h design bending strength
    E    = 11600.0        # MPa  GL24h E_mean
    trib = grid_spacing / float(n_purlins + 1)   # m tributary per purlin
    q    = 5.0 * trib     # N/mm  (5 kN/m² × trib; 1 kN/m = 1 N/mm)
    L    = grid_spacing * 1000.0  # mm span

    # Bending — square section modulus b³/6
    M_Nmm  = q * L ** 2 / 8.0         # N·mm
    W_req  = M_Nmm / fm_d
    b_bend = (6.0 * W_req) ** (1.0 / 3.0)   # mm

    # Deflection L/300 — square I = b⁴/12
    b_defl = (5.0 * q * L ** 3 * 12.0 * 300.0 / (384.0 * E)) ** 0.25  # mm

    b_struct = max(b_bend, b_defl, 60.0)

    # Fire R60 for secondary beam (EC5-1-2): 3-sided
    #   min b = 120 mm (secondary beam at R60, EC5-1-2 Table B.2)
    #   residual b − 2×42 ≥ 60 mm  →  b ≥ 144 mm  →  use 160 mm
    est_h = 1.0 + num_floors * 3.5
    _, fire_min = _gk_fire_minutes(est_h)
    if fire_min >= 60:
        d_char  = 0.7 * 60.0
        b_fire  = max(120.0, 60.0 + 2.0 * d_char)   # residual ≥ 60mm each side
    elif fire_min >= 30:
        b_fire = 80.0
    else:
        b_fire = 60.0

    b_sq  = math.ceil(max(b_struct, b_fire) / 20.0) * 20   # round to 20mm
    b_m   = round(b_sq / 1000.0, 3)
    name  = "PURLIN_w{:.0f}xd{:.0f}_GL24h".format(b_sq, b_sq)
    return b_m, b_m, name

def draw_floor_purlins(Building, floor_label, cells, beam_z, floor_index):
    """Draw secondary purlin centerlines for all panel cells on one floor.

    Purlins run parallel to the X axis, placed at equal Y-intervals within
    each cell.  They span the full grid_spacing in X between primary beams.
    One purlin line is created per purlin per cell.

    Objects are placed on layer 'Floor_Purlins' (architectural view) and
    their names encode the GL24h cross-section for RFEM import.

    Returns list of all purlin Rhino object IDs.
    """
    if not cells:
        return []

    gs      = Building["grid"]["spacing"]
    bd      = Building["structure"]["plinth_beams"]["depth"]
    n_pur   = auto_calc_purlin_count(gs)
    b_m, d_m, sec_name = auto_calc_purlin_section(gs, n_pur)
    bay     = gs / float(n_pur + 1)
    pur_z   = beam_z   # purlins sit at beam level (top of primary beam)

    # Store sizing in Building
    Building["purlins"]["n_per_cell"]    = n_pur
    Building["purlins"]["spacing"]       = round(bay, 3)
    Building["purlins"]["section_width"] = b_m
    Building["purlins"]["section_depth"] = d_m
    Building["purlins"]["section_name"]  = sec_name

    layer_name = "Floor_Purlins"
    if not rs.IsLayer(layer_name):
        rs.AddLayer(layer_name, (180, 130, 70))   # darker wood brown

    pur_ids = []
    for cell in cells:
        cx, cy = cell["x"], cell["y"]   # bottom-left corner of cell
        for i in range(1, n_pur + 1):
            y_pur = round(cy + i * bay, 4)
            pt1   = rg.Point3d(cx,      y_pur, pur_z)
            pt2   = rg.Point3d(cx + gs, y_pur, pur_z)
            lid   = sc.doc.Objects.AddLine(rg.Line(pt1, pt2))
            if lid:
                rs.ObjectLayer(lid, layer_name)
                rs.ObjectColor(lid, (140, 90, 40))
                rs.ObjectName(lid, sec_name)
                pur_ids.append(lid)

    print("  {} purlins added: {} per cell × {} cells = {}".format(
          floor_label, n_pur, len(cells), len(pur_ids)))
    print("    Section : {} ({:.0f}×{:.0f} mm GL24h)".format(
          sec_name, b_m*1000, d_m*1000))
    print("    Bay span: {:.2f} m  (max deck span between purlins)".format(bay))

    # Store IDs per floor
    Building["purlins"]["ids_per_floor"].append(pur_ids)
    sc.doc.Views.Redraw()
    return pur_ids

def process_floor_panels(Building, floor_label, floor_index, floor_top_points, extension):
    """Generate floor panels for one floor automatically — no dialogs, no view changes.
    All cells with full beam support are filled. Nothing is deleted.
    """
    bd = Building["structure"]["plinth_beams"]["depth"]
    gs = Building["grid"]["spacing"]
    if not floor_top_points:
        return
    beam_z = floor_top_points[0][2]
    panel_z = beam_z + bd
    print_section_header("FLOOR PANELLING - {}".format(floor_label))
    cells = get_panel_cells_from_beams(Building, floor_top_points, extension, floor_index)
    if not cells:
        print("  No panel cells found for {}. Skipping.".format(floor_label))
        Building["panels"]["panels_per_floor"].append([])
        Building["panels"]["panel_ids_per_floor"].append([])
        Building["panels"]["panel_coords_per_floor"].append([])
        Building["panels"]["deleted_panels_per_floor"].append([])
        return
    print("  {} panel cells identified (all 4 edges supported).".format(len(cells)))
    all_possible_keys = set(c["key"] for c in cells)
    # ── Draw secondary purlins before floor panels ──────────────────────────
    draw_floor_purlins(Building, floor_label, cells, beam_z, floor_index)
    panel_ids, panel_cell_map, panel_layer = draw_floor_panels(Building, floor_label, cells, floor_index)
    Building["panels"]["panels_per_floor"].append(cells)
    # Keep all panels automatically — no user interaction
    interactive_panel_deletion(Building, floor_label, panel_ids, panel_cell_map,
                               panel_layer, floor_index, all_possible_keys, panel_z)
    print("  {} panelling complete.".format(floor_label))
    print_section_footer()


def process_all_floor_panels(Building):
    """Generate floor panels for ALL floors in one automated step.

    Shows a SINGLE start dialog to the user — no per-floor popups.
    All panels are kept automatically; nothing is deleted.
    """
    nf   = len(Building["structure"]["columns"]["top_points_per_floor"])
    exts = Building["structure"]["plinth_beams"]["extension_per_floor"]

    # ── Combined dialog shown ONCE for both floor + wall panels ──────────────
    _panel_dlg = PanelGenerationDialog(num_floors=nf)
    _panel_dlg.ShowModal(Rhino.UI.RhinoEtoApp.MainWindow)
    Building["_panel_dlg"] = _panel_dlg   # stored so wall panels reuses it

    if not _panel_dlg.confirmed:
        print("  Floor panel generation cancelled by user.")
        # Fill empty lists so downstream code doesn't crash
        for _ in range(nf):
            Building["panels"]["panels_per_floor"].append([])
            Building["panels"]["panel_ids_per_floor"].append([])
            Building["panels"]["panel_coords_per_floor"].append([])
            Building["panels"]["deleted_panels_per_floor"].append([])
        return

    print_section_header("FLOOR PANELLING PHASE")
    print("  Generating panels for all {} floor(s) automatically.".format(nf))
    print("  All cells with full beam support are filled — nothing deleted.")
    print_section_footer()

    # Ensure purlin ids_per_floor list is fresh for this run
    Building["purlins"]["ids_per_floor"] = []

    for fi in range(nf):
        ftp = Building["structure"]["columns"]["top_points_per_floor"][fi]
        if fi == 0:
            fl = "BASEMENT"
        elif fi == nf - 1:
            fl = "ROOF"
        else:
            fl = "FLOOR {}".format(fi)
        ext = exts[fi] if fi < len(exts) else 1.0
        process_floor_panels(Building, fl, fi, ftp, ext)

    remove_all_clipping_planes(Building)
    rs.Redraw()

    tp = sum(len(p) for p in Building["panels"]["panel_ids_per_floor"])
    print_section_header("PANELLING COMPLETE")
    print("  Total floor panels generated: {}".format(tp))
    print("  Deleted: 0  (all panels kept)")
    print_section_footer()


# ============================================================ WALL PANEL SYSTEM ============================================================
def get_outer_edges_from_floor_panels(panel_keys, gs):
    if not panel_keys:
        return []
    panel_set = set()
    for k in panel_keys:
        panel_set.add((round(k[0], 4), round(k[1], 4)))
    outer_edges = []
    for (cx, cy) in panel_set:
        cx2 = round(cx + gs, 4)
        cy2 = round(cy + gs, 4)
        if (round(cx, 4), round(cy - gs, 4)) not in panel_set:
            outer_edges.append({"x1": cx, "y1": cy, "x2": cx2, "y2": cy, "orientation": "bottom", "cell_key": (cx, cy), "is_transition": False})
        if (round(cx, 4), round(cy + gs, 4)) not in panel_set:
            outer_edges.append({"x1": cx, "y1": cy2, "x2": cx2, "y2": cy2, "orientation": "top", "cell_key": (cx, cy), "is_transition": False})
        if (round(cx - gs, 4), round(cy, 4)) not in panel_set:
            outer_edges.append({"x1": cx, "y1": cy, "x2": cx, "y2": cy2, "orientation": "left", "cell_key": (cx, cy), "is_transition": False})
        if (round(cx + gs, 4), round(cy, 4)) not in panel_set:
            outer_edges.append({"x1": cx2, "y1": cy, "x2": cx2, "y2": cy2, "orientation": "right", "cell_key": (cx, cy), "is_transition": False})
    return outer_edges


def get_transition_edges_between_covered_and_uncovered(panel_keys, floor_panels_above, gs):
    if not panel_keys:
        return []
    panel_set = set()
    for k in panel_keys:
        panel_set.add((round(k[0], 4), round(k[1], 4)))
    above_set = set()
    if floor_panels_above:
        for k in floor_panels_above:
            above_set.add((round(k[0], 4), round(k[1], 4)))
    if not above_set:
        return []
    covered_cells = panel_set & above_set
    uncovered_cells = panel_set - above_set
    if not covered_cells or not uncovered_cells:
        return []
    transition_edges = []
    seen_edges = set()
    for (cx, cy) in covered_cells:
        cx2 = round(cx + gs, 4)
        cy2 = round(cy + gs, 4)
        for nb, ek, ed in [
            ((round(cx, 4), round(cy - gs, 4)), (cx, cy, cx2, cy, "bottom"),
             {"x1": cx, "y1": cy, "x2": cx2, "y2": cy, "orientation": "bottom", "cell_key": (cx, cy), "is_transition": True}),
            ((round(cx, 4), round(cy + gs, 4)), (cx, cy2, cx2, cy2, "top"),
             {"x1": cx, "y1": cy2, "x2": cx2, "y2": cy2, "orientation": "top", "cell_key": (cx, cy), "is_transition": True}),
            ((round(cx - gs, 4), round(cy, 4)), (cx, cy, cx, cy2, "left"),
             {"x1": cx, "y1": cy, "x2": cx, "y2": cy2, "orientation": "left", "cell_key": (cx, cy), "is_transition": True}),
            ((round(cx + gs, 4), round(cy, 4)), (cx2, cy, cx2, cy2, "right"),
             {"x1": cx2, "y1": cy, "x2": cx2, "y2": cy2, "orientation": "right", "cell_key": (cx, cy), "is_transition": True})]:
            if nb in uncovered_cells and ek not in seen_edges:
                seen_edges.add(ek)
                transition_edges.append(ed)
    return transition_edges


def does_floor_above_cover_edge(edge, floor_panels_above, gs):
    if not floor_panels_above:
        return False
    above_set = set()
    for k in floor_panels_above:
        above_set.add((round(k[0], 4), round(k[1], 4)))
    cx, cy = round(edge["cell_key"][0], 4), round(edge["cell_key"][1], 4)
    if (cx, cy) in above_set:
        return True
    orient = edge["orientation"]
    if orient == "bottom":
        nb = (cx, round(cy - gs, 4))
    elif orient == "top":
        nb = (cx, round(cy + gs, 4))
    elif orient == "left":
        nb = (round(cx - gs, 4), cy)
    elif orient == "right":
        nb = (round(cx + gs, 4), cy)
    else:
        nb = None
    if nb and nb in above_set:
        return True
    return False


def create_wall_panel_surface(edge, base_z, panel_height):
    x1, y1 = edge["x1"], edge["y1"]
    x2, y2 = edge["x2"], edge["y2"]
    z_bottom = base_z
    z_top = base_z + panel_height
    c1 = rg.Point3d(x1, y1, z_bottom)
    c2 = rg.Point3d(x2, y2, z_bottom)
    c3 = rg.Point3d(x2, y2, z_top)
    c4 = rg.Point3d(x1, y1, z_top)
    srf = rg.NurbsSurface.CreateFromCorners(c1, c2, c3, c4)
    if srf:
        srf_id = sc.doc.Objects.AddSurface(srf)
        return srf_id
    return None


def draw_wall_panels_for_floor(Building, floor_label, floor_index, all_edges, base_z, floor_height, parapet_height, floor_panels_above):
    gs = Building["grid"]["spacing"]
    layer_name = "Wall_Panels_{}".format(floor_index)
    if not rs.IsLayer(layer_name):
        rs.AddLayer(layer_name, (160, 180, 200))
    wall_panel_ids = []
    wall_panel_edge_map = {}
    wall_panel_info_map = {}
    full_height_count = 0
    parapet_count = 0
    transition_count = 0
    for edge in all_edges:
        is_transition = edge.get("is_transition", False)
        if is_transition:
            panel_height = floor_height
            panel_color = (140, 170, 210)
            transition_count += 1
        else:
            has_cover_above = does_floor_above_cover_edge(edge, floor_panels_above, gs)
            if has_cover_above:
                panel_height = floor_height
                panel_color = (180, 200, 220)
                full_height_count += 1
            else:
                panel_height = parapet_height
                panel_color = (200, 180, 160)
                parapet_count += 1
        srf_id = create_wall_panel_surface(edge, base_z, panel_height)
        if srf_id:
            rs.ObjectLayer(srf_id, layer_name)
            rs.ObjectColor(srf_id, panel_color)
            wall_panel_ids.append(srf_id)
            edge_key = (round(edge["x1"], 4), round(edge["y1"], 4), round(edge["x2"], 4), round(edge["y2"], 4))
            wall_panel_edge_map[str(srf_id)] = edge_key
            wall_panel_info_map[str(srf_id)] = {
                "edge": edge, "base_z": base_z, "panel_height": panel_height,
                "floor_index": floor_index, "edge_key": edge_key
            }
    print("  {} wall panels drawn: {} full-height, {} transition, {} parapet ({}m)".format(
        floor_label, full_height_count, transition_count, parapet_count, parapet_height))
    sc.doc.Views.Redraw()
    return wall_panel_ids, wall_panel_edge_map, layer_name, wall_panel_info_map


def interactive_wall_panel_deletion(Building, floor_label, floor_index, wall_panel_ids, wall_panel_edge_map, layer_name, wall_panel_info_map):
    """Silently keep ALL wall panels — no dialog, no per-floor popup, no user selection.
    Called from process_wall_panels_for_floor; behaviour is now fully automatic.
    """
    if not wall_panel_ids:
        Building["wall_panels"]["wall_panel_ids_per_floor"].append([])
        Building["wall_panels"]["wall_panel_edges_per_floor"].append([])
        Building["wall_panels"]["deleted_wall_panels_per_floor"].append([])
        Building["wall_panels"]["wall_panel_info_per_floor"].append({})
        return
    print("  Keeping all {} wall panels for {} (automatic).".format(len(wall_panel_ids), floor_label))
    Building["wall_panels"]["wall_panel_ids_per_floor"].append(list(wall_panel_ids))
    all_edge_keys = [wall_panel_edge_map[str(pid)] for pid in wall_panel_ids if str(pid) in wall_panel_edge_map]
    Building["wall_panels"]["wall_panel_edges_per_floor"].append(all_edge_keys)
    Building["wall_panels"]["deleted_wall_panels_per_floor"].append([])
    Building["wall_panels"]["wall_panel_info_per_floor"].append(wall_panel_info_map)


def process_wall_panels_for_floor(Building, floor_label, floor_index, floor_panel_keys, floor_panels_above, base_z, floor_height, parapet_height):
    gs = Building["grid"]["spacing"]
    print_section_header("WALL PANELLING - {}".format(floor_label))
    if not floor_panel_keys:
        print("  No floor panels for {}. Skipping wall panels.".format(floor_label))
        Building["wall_panels"]["wall_panel_ids_per_floor"].append([])
        Building["wall_panels"]["wall_panel_edges_per_floor"].append([])
        Building["wall_panels"]["deleted_wall_panels_per_floor"].append([])
        Building["wall_panels"]["wall_panel_info_per_floor"].append({})
        print_section_footer()
        return
    outer_edges = get_outer_edges_from_floor_panels(floor_panel_keys, gs)
    transition_edges = get_transition_edges_between_covered_and_uncovered(floor_panel_keys, floor_panels_above, gs)
    all_edges = outer_edges + transition_edges
    if not all_edges:
        print("  No wall edges found for {}. Skipping.".format(floor_label))
        Building["wall_panels"]["wall_panel_ids_per_floor"].append([])
        Building["wall_panels"]["wall_panel_edges_per_floor"].append([])
        Building["wall_panels"]["deleted_wall_panels_per_floor"].append([])
        Building["wall_panels"]["wall_panel_info_per_floor"].append({})
        print_section_footer()
        return
    print("  {} outer boundary edges found.".format(len(outer_edges)))
    if transition_edges:
        print("  {} transition edges found (covered/uncovered boundary).".format(len(transition_edges)))
    wall_panel_ids, wall_panel_edge_map, layer_name, wall_panel_info_map = draw_wall_panels_for_floor(
        Building, floor_label, floor_index, all_edges, base_z, floor_height, parapet_height, floor_panels_above)
    # Keep all wall panels automatically — no user interaction, no view changes
    interactive_wall_panel_deletion(Building, floor_label, floor_index,
                                     wall_panel_ids, wall_panel_edge_map, layer_name, wall_panel_info_map)
    print("  {} wall panelling complete.".format(floor_label))
    print_section_footer()


def process_all_wall_panels(Building):
    """Generate wall panels for ALL floors in one automated step.

    Shows a SINGLE start dialog to the user — no per-floor popups.
    All panels are kept automatically; nothing is deleted.
    """
    nf = len(Building["structure"]["columns"]["top_points_per_floor"])

    # ── Reuse dialog already shown by process_all_floor_panels ───────────────
    # No second dialog is shown — single confirmation already collected.
    _panel_dlg = Building.get("_panel_dlg")
    if _panel_dlg is None or not _panel_dlg.confirmed:
        print("  Wall panel generation skipped.")
        return

    print_section_header("WALL PANELLING PHASE")
    print("  Generating wall panels for all {} floor(s) automatically.".format(nf))
    print("  All panels kept — nothing deleted.")
    print_section_footer()

    bd = Building["structure"]["plinth_beams"]["depth"]
    parapet_height = Building["wall_panels"]["parapet_height"]
    for fi in range(nf):
        ftp = Building["structure"]["columns"]["top_points_per_floor"][fi]
        if not ftp:
            continue
        if fi == 0:
            fl = "GROUND FLOOR"
        elif fi == nf - 1:
            fl = "ROOF"
        else:
            fl = "FLOOR {}".format(fi)
        if fi < len(Building["panels"]["panel_coords_per_floor"]):
            floor_panel_keys = Building["panels"]["panel_coords_per_floor"][fi]
        else:
            floor_panel_keys = []
        if fi + 1 < len(Building["panels"]["panel_coords_per_floor"]):
            floor_panels_above = Building["panels"]["panel_coords_per_floor"][fi + 1]
        else:
            floor_panels_above = []
        beam_z = ftp[0][2]
        panel_z = beam_z + bd
        if fi + 1 < nf:
            next_ftp = Building["structure"]["columns"]["top_points_per_floor"][fi + 1]
            if next_ftp:
                next_beam_z = next_ftp[0][2]
                next_panel_z = next_beam_z + bd
                floor_height = next_panel_z - panel_z
            else:
                floor_height = Building["floors"]["floor_heights"][fi + 1] if fi + 1 < len(Building["floors"]["floor_heights"]) else 3.0
        else:
            floor_height = Building["floors"]["floor_heights"][fi] if fi < len(Building["floors"]["floor_heights"]) else 3.0
        # ── BASEMENT SKIRT WALLS ─────────────────────────────────────────────
        if fi == 0 and panel_z > 0.001:
            basement_skirt_height = panel_z
            process_wall_panels_for_floor(Building, "WALL PANELS BASEMENT", -1,
                                          floor_panel_keys, floor_panel_keys,
                                          0.0, basement_skirt_height, basement_skirt_height)
        # ────────────────────────────────────────────────────────────────────
        process_wall_panels_for_floor(Building, fl, fi, floor_panel_keys, floor_panels_above,
                                       panel_z, floor_height, parapet_height)

    rs.Redraw()
    tw = sum(len(w) for w in Building["wall_panels"]["wall_panel_ids_per_floor"])
    print_section_header("WALL PANELLING COMPLETE")
    print("  Total wall panels generated: {}".format(tw))
    print("  Deleted: 0  (all panels kept)")
    print_section_footer()


# ============================================================ ELEVATION STEP 1: WALL ARCH EXTRUSION ============================================================
def get_wall_outward_direction(edge):
    """From a wall panel edge, determine the outward extrusion direction perpendicular to the wall.
    Returns (dx, dy) unit direction pointing away from the cell interior.
    """
    orient = edge["orientation"]
    if orient == "bottom":
        return (0, -1)
    elif orient == "top":
        return (0, 1)
    elif orient == "left":
        return (-1, 0)
    elif orient == "right":
        return (1, 0)
    return (0, 0)


def clamp_wall_extrusion_to_plot(edge, direction, ext_dist, plot_length, plot_width):
    """Clamp wall arch extrusion so it stays within the outer plot boundary."""
    dx, dy = direction
    half_l = plot_length / 2.0
    half_w = plot_width / 2.0
    x1, y1 = edge["x1"], edge["y1"]
    x2, y2 = edge["x2"], edge["y2"]
    if dx > 0:
        start_x = max(x1, x2)
        max_allowed = half_l - start_x
    elif dx < 0:
        start_x = min(x1, x2)
        max_allowed = start_x - (-half_l)
    elif dy > 0:
        start_y = max(y1, y2)
        max_allowed = half_w - start_y
    elif dy < 0:
        start_y = min(y1, y2)
        max_allowed = start_y - (-half_w)
    else:
        max_allowed = ext_dist
    max_allowed = max(0, max_allowed)
    return min(ext_dist, max_allowed)


def _hole_gap_for_cell(col, row, cols, rows):
    """Return the hole-gap ratio (0..1) for a specific cell position.

    Produces a parametric halftone-style gradient:
    - Large holes (gap ~0.72) near the panel centre
    - Small holes (gap ~0.25) near the panel edges
    - A gentle sine-wave ripple layered on top for organic variation
    - A subtle diagonal wave so adjacent holes feel staggered in size

    Parameters
    ----------
    col, row        : int — zero-based cell indices
    cols, rows      : int — total grid dimensions

    Returns float gap in [0.22 .. 0.74]
    """
    GAP_MAX  = 0.74   # largest hole (centre)
    GAP_MIN  = 0.22   # smallest hole (edge / corner)

    # Normalised position in [-1, 1]
    u = (col + 0.5) / cols * 2.0 - 1.0   # -1 at left,  +1 at right
    v = (row + 0.5) / rows * 2.0 - 1.0   # -1 at bottom, +1 at top

    # Radial distance from centre (0 = centre, 1 = corner)
    dist = math.sqrt(u * u + v * v) / math.sqrt(2.0)

    # Primary gradient: cosine fall-off (large at centre, small at edge)
    primary = 0.5 + 0.5 * math.cos(dist * math.pi)   # 1.0 at centre, 0.0 at corner

    # Ripple: diagonal sine wave (frequency scales with grid density)
    freq_u = math.pi * 2.5
    freq_v = math.pi * 2.0
    ripple = 0.12 * math.sin(u * freq_u + v * freq_v)

    # Checkerboard micro-variation: alternate cells get +/- nudge
    checker = 0.06 * (1 if (col + row) % 2 == 0 else -1)

    raw = primary + ripple + checker
    raw = max(0.0, min(1.0, raw))

    return GAP_MIN + raw * (GAP_MAX - GAP_MIN)


def _create_perforated_panel_mesh(corners_3d, pw, ph, color, layer_name,
                                   rows=None, cols=None):
    """Build a flat rectangular panel as a Rhino Mesh with parametric square holes.

    Each cell gets an independently computed hole size via _hole_gap_for_cell(),
    producing a halftone-style gradient: large open holes at the centre fading
    to small holes at the edges, with a sine-wave ripple for organic variation.

    The per-cell hole is implemented by placing the 4 hole-corner vertices at a
    variable inset from the cell boundary, then omitting the centre quad.

    Parameters
    ----------
    corners_3d  : list of 4 rg.Point3d  [bl, br, tr, tl]
    pw, ph      : float — panel width and height in world units
    color       : (r,g,b)
    layer_name  : str
    rows, cols  : int — hole grid; auto if None (~1 cell per 0.35 m)

    Returns list of added Rhino object GUIDs (one Mesh per panel).
    """
    if pw < 0.05 or ph < 0.05:
        return []

    CELL_TARGET = 0.35
    if cols is None:
        cols = max(2, int(round(pw / CELL_TARGET)))
    if rows is None:
        rows = max(2, int(round(ph / CELL_TARGET)))

    bl, br, tr, tl = corners_3d

    def _pt(u_frac, v_frac):
        b = bl + (br - bl) * u_frac
        t = tl + (tr - tl) * u_frac
        return b + (t - b) * v_frac

    # ── Per-cell mesh strategy ────────────────────────────────────────────────
    # Each cell is built as 8 quads forming a picture-frame around the hole:
    #
    #   TL--TLi--TRi--TR        TL, TR, BL, BR = cell corners
    #   |  \ |    | /  |        TLi,TRi,BLi,BRi = inset hole corners
    #   |   [hole area]|        The 4 corner triangles + 4 edge quads = 8 faces
    #   |  / |    | \  |        Centre quad (the hole) is omitted.
    #   BL--BLi--BRi--BR
    #
    # This lets each cell have a completely independent hole size (gap ratio)
    # while still producing a single manifold mesh per panel.

    mesh = rg.Mesh()

    def _add_v(pt):
        mesh.Vertices.Add(pt.X, pt.Y, pt.Z)
        return mesh.Vertices.Count - 1

    def _add_quad(a, b, c, d):
        mesh.Faces.AddFace(a, b, c, d)

    def _add_tri(a, b, c):
        mesh.Faces.AddFace(a, b, c)

    for row in range(rows):
        for col in range(cols):
            # Cell UV fractions
            u0 = col       / float(cols)
            u1 = (col + 1) / float(cols)
            v0 = row       / float(rows)
            v1 = (row + 1) / float(rows)

            # Per-cell hole gap ratio
            gap  = _hole_gap_for_cell(col, row, cols, rows)
            marg = (1.0 - gap) / 2.0

            # Inset fractions for the hole corners within this cell
            ui0 = u0 + marg * (u1 - u0)
            ui1 = u1 - marg * (u1 - u0)
            vi0 = v0 + marg * (v1 - v0)
            vi1 = v1 - marg * (v1 - v0)

            # 8 vertices: 4 cell corners + 4 hole corners
            BL  = _add_v(_pt(u0,  v0))
            BR  = _add_v(_pt(u1,  v0))
            TR  = _add_v(_pt(u1,  v1))
            TL  = _add_v(_pt(u0,  v1))
            BLi = _add_v(_pt(ui0, vi0))
            BRi = _add_v(_pt(ui1, vi0))
            TRi = _add_v(_pt(ui1, vi1))
            TLi = _add_v(_pt(ui0, vi1))

            # 8 frame faces (hole centre omitted)
            # Bottom strip
            _add_quad(BL,  BR,  BRi, BLi)
            # Top strip
            _add_quad(TLi, TRi, TR,  TL)
            # Left strip
            _add_quad(BL,  BLi, TLi, TL)
            # Right strip
            _add_quad(BRi, BR,  TR,  TRi)

    mesh.Normals.ComputeNormals()
    mesh.Compact()

    mid = sc.doc.Objects.AddMesh(mesh)
    if mid and str(mid) != '00000000-0000-0000-0000-000000000000':
        rs.ObjectLayer(mid, layer_name)
        rs.ObjectColor(mid, color)
        return [mid]
    return []


def create_wall_arch_extrusion(edge, direction, ext_dist, base_z, wall_height, layer_name):
    """Create an arch extrusion from a wall panel outward.
    All 5 surfaces (2 side walls, far end wall, top cap, bottom slab) are built
    as perforated mesh panels with square holes punched through them.
    """
    dx, dy = direction
    x1, y1 = edge["x1"], edge["y1"]
    x2, y2 = edge["x2"], edge["y2"]
    z_bottom = base_z
    z_top    = base_z + wall_height

    if ext_dist < 0.01:
        return []

    created_ids = []
    COLOR_WALL = (220, 160, 100)

    fx1 = x1 + dx * ext_dist
    fy1 = y1 + dy * ext_dist
    fx2 = x2 + dx * ext_dist
    fy2 = y2 + dy * ext_dist

    # Panel width helpers
    wall_len = math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)
    side_len = math.sqrt((fx1 - x1) ** 2 + (fy1 - y1) ** 2)   # == ext_dist

    # Side wall 1: (x1,y1,z_bot) -> (fx1,fy1,z_bot) -> (fx1,fy1,z_top) -> (x1,y1,z_top)
    created_ids += _create_perforated_panel_mesh(
        [rg.Point3d(x1, y1, z_bottom), rg.Point3d(fx1, fy1, z_bottom),
         rg.Point3d(fx1, fy1, z_top),  rg.Point3d(x1, y1, z_top)],
        side_len, wall_height, COLOR_WALL, layer_name)

    # Side wall 2
    created_ids += _create_perforated_panel_mesh(
        [rg.Point3d(x2, y2, z_bottom), rg.Point3d(fx2, fy2, z_bottom),
         rg.Point3d(fx2, fy2, z_top),  rg.Point3d(x2, y2, z_top)],
        side_len, wall_height, COLOR_WALL, layer_name)

    # Far end wall: (fx1,fy1) -> (fx2,fy2)
    far_len = math.sqrt((fx2 - fx1) ** 2 + (fy2 - fy1) ** 2)
    created_ids += _create_perforated_panel_mesh(
        [rg.Point3d(fx1, fy1, z_bottom), rg.Point3d(fx2, fy2, z_bottom),
         rg.Point3d(fx2, fy2, z_top),    rg.Point3d(fx1, fy1, z_top)],
        far_len, wall_height, COLOR_WALL, layer_name)

    # Top cap (horizontal): corners in order bl,br,tr,tl using wall direction as U
    created_ids += _create_perforated_panel_mesh(
        [rg.Point3d(x1, y1, z_top),  rg.Point3d(x2, y2, z_top),
         rg.Point3d(fx2, fy2, z_top), rg.Point3d(fx1, fy1, z_top)],
        wall_len, side_len, COLOR_WALL, layer_name)

    # Bottom slab (horizontal)
    created_ids += _create_perforated_panel_mesh(
        [rg.Point3d(x1, y1, z_bottom),  rg.Point3d(x2, y2, z_bottom),
         rg.Point3d(fx2, fy2, z_bottom), rg.Point3d(fx1, fy1, z_bottom)],
        wall_len, side_len, COLOR_WALL, layer_name)

    return created_ids




def build_wall_panel_lookup(Building):
    """Build a lookup from wall panel object IDs to their edge info across all floors."""
    lookup = {}
    for fi in range(len(Building["wall_panels"]["wall_panel_ids_per_floor"])):
        wall_ids = Building["wall_panels"]["wall_panel_ids_per_floor"][fi]
        info_map = Building["wall_panels"]["wall_panel_info_per_floor"][fi] if fi < len(Building["wall_panels"]["wall_panel_info_per_floor"]) else {}
        for pid in wall_ids:
            ps = str(pid)
            if ps in info_map:
                lookup[ps] = info_map[ps]
    return lookup


def _box_fp(edge, direction, depth):
    """XY bounding box of projected volume: (x_min, y_min, x_max, y_max)."""
    dx, dy = direction
    xs = [edge["x1"], edge["x2"],
          edge["x1"] + dx * depth, edge["x2"] + dx * depth]
    ys = [edge["y1"], edge["y2"],
          edge["y1"] + dy * depth, edge["y2"] + dy * depth]
    return (min(xs), min(ys), max(xs), max(ys))


def _boxes_collide_3d(fp_a, z_bot_a, z_top_a, fp_b, z_bot_b, z_top_b, tol=0.01):
    """True only when two box volumes have interior overlap in BOTH XY and Z.

    Key fix: boxes on different floors (non-overlapping Z ranges) are NEVER
    in collision even if their XY footprints coincide.  This was the root
    cause of upper-floor extrusions being silently skipped.
    """
    # Z overlap check first (cheap)
    if z_top_a <= z_bot_b + tol: return False
    if z_top_b <= z_bot_a + tol: return False
    # XY overlap check
    if fp_a[2] <= fp_b[0] + tol: return False
    if fp_b[2] <= fp_a[0] + tol: return False
    if fp_a[3] <= fp_b[1] + tol: return False
    if fp_b[3] <= fp_a[1] + tol: return False
    return True


def process_wall_extrusions(Building):
    """ELEVATION STEP 1: Offset-checkerboard closed-box extrusion, all floors.

    Covers ALL floors except basement (floor_index == -1).
    Covers ALL four facade faces on every eligible floor.

    Panel eligibility
    -----------------
    A panel is eligible when panel_height equals the floor structural height,
    meaning it is a FULL-HEIGHT or TRANSITION panel — not a parapet.
    Test: panel_height > parapet_height + 0.05

    Offset-checkerboard pattern
    ---------------------------
    For each (floor_index, face_orientation) bucket, panels are sorted along
    the face axis (X midpoint for top/bottom, Y midpoint for left/right).
    Phase alternates by floor_index:
        fi even → extrude positions 0, 2, 4 …
        fi odd  → extrude positions 1, 3, 5 …
    Adjacent floors always project opposite halves → offset checkerboard.

    Collision safety (3-D)
    ----------------------
    Footprints are stored with their Z range (base_z, base_z + panel_height).
    Two boxes only collide when they overlap in BOTH XY and Z.
    Boxes on different floors at the same XY position are NEVER in collision.
    This was the critical bug causing upper floors to be skipped.

    Geometry: 5-surface closed box (2 side walls + far face + top cap + bottom slab).
    Depth: 1.5 m fixed.
    """
    print_section_header("ELEVATION STEP 1: WALL EXTRUSION")

    _elev_dlg = Building.get("_elev_dlg")
    if _elev_dlg is None:
        _elev_dlg = ElevationExtrusionDialog()
        _elev_dlg.ShowModal(Rhino.UI.RhinoEtoApp.MainWindow)
        Building["_elev_dlg"] = _elev_dlg

    if _elev_dlg.wall_choice not in ("generate", "select"):
        print("  Skipping wall extrusions.")
        print_section_footer()
        return

    EXT_DEPTH  = 1.5
    layer_name = "Wall_Extrusions"
    if not rs.IsLayer(layer_name):
        rs.AddLayer(layer_name, (220, 160, 100))

    plot_length = Building["plot"]["length"]
    plot_width  = Building["plot"]["width"]
    parapet_h   = Building["wall_panels"]["parapet_height"]
    wall_lookup = build_wall_panel_lookup(Building)

    # ── Group eligible panels by (floor_index, face_orientation) ─────────────
    # Eligible: floor_index != -1  AND  panel_height > parapet_h + 0.05
    from collections import defaultdict
    buckets = defaultdict(list)

    for pid_str, info in wall_lookup.items():
        fi = info.get("floor_index", 0)
        ph = info.get("panel_height", 0.0)

        if fi == -1:                   continue   # basement skirt only — excluded
        if ph <= parapet_h + 0.05:    continue   # parapet panels — excluded

        edge = info.get("edge")
        if not edge: continue
        direction = get_wall_outward_direction(edge)
        if direction == (0, 0): continue

        orient = edge.get("orientation", "")
        # Axis sort key: X midpoint for N/S faces, Y midpoint for E/W faces
        if orient in ("top", "bottom"):
            axis_pos = round((edge["x1"] + edge["x2"]) / 2.0, 4)
        else:
            axis_pos = round((edge["y1"] + edge["y2"]) / 2.0, 4)

        bz = info.get("base_z", 0.0)
        buckets[(fi, orient)].append((axis_pos, bz, ph, edge, direction))

    # Sort every bucket along its face axis
    for key in buckets:
        buckets[key].sort(key=lambda t: t[0])

    total_eligible = sum(len(v) for v in buckets.values())
    print("  Full-height panels eligible (all floors except basement): {}".format(total_eligible))
    print("  Generating offset-checkerboard closed-box extrusions (depth {:.1f} m)...".format(EXT_DEPTH))

    # committed: list of (fp_xy, z_bot, z_top)
    committed         = []
    all_extrusion_ids = []
    n_drawn = n_skip_b = n_skip_c = 0

    for (fi, orient) in sorted(buckets.keys()):
        panels = buckets[(fi, orient)]

        # fi even → positions 0,2,4…   fi odd → positions 1,3,5…
        phase = fi % 2

        for pos_idx, (axis_pos, bz, ph, edge, direction) in enumerate(panels):
            if pos_idx % 2 != phase:
                continue   # gap position for this floor

            # Plot-boundary clamp
            clamped = clamp_wall_extrusion_to_plot(
                edge, direction, EXT_DEPTH, plot_length, plot_width)
            if clamped < 0.01:
                n_skip_b += 1
                continue

            # 3-D collision check — only skip if XY AND Z both overlap
            fp = _box_fp(edge, direction, clamped)
            z_bot = bz
            z_top = bz + ph
            collision = False
            for (ex_fp, ex_zb, ex_zt) in committed:
                if _boxes_collide_3d(fp, z_bot, z_top, ex_fp, ex_zb, ex_zt):
                    collision = True
                    break
            if collision:
                n_skip_c += 1
                continue

            # Draw 5-surface closed box
            ids = create_wall_arch_extrusion(
                edge, direction, clamped, bz, ph, layer_name)

            if ids:
                all_extrusion_ids.extend(ids)
                committed.append((fp, z_bot, z_top))
                n_drawn += 1
                dl = {(0,-1):"S",(0,1):"N",(-1,0):"W",(1,0):"E"}.get(direction,"?")
                print("    [{:3d}] fl={:2d} {:6s} @{:6.1f} z={:.1f}-{:.1f}  {}  d={:.1f}m".format(
                    n_drawn, fi, orient, axis_pos, z_bot, z_top, dl, clamped))

    sc.doc.Views.Redraw()
    Building["elevation"]["wall_extrusion_ids"] = all_extrusion_ids

    pct = 100.0 * n_drawn / max(1, total_eligible)
    print("\n  Eligible panels (full-height, all floors) : {}".format(total_eligible))
    print("  Extruded (offset checkerboard)            : {} ({:.0f}%)".format(n_drawn, pct))
    if n_skip_b: print("  Skipped – plot boundary                   : {}".format(n_skip_b))
    if n_skip_c: print("  Skipped – 3D collision                    : {}".format(n_skip_c))
    print("  Box surfaces created                      : {}".format(len(all_extrusion_ids)))
    print_section_footer()


# ============================================================ ELEVATION STEP 2: VERTICAL ARCH EXTRUSION ============================================================
def get_uncovered_panel_keys(Building):
    """Find all floor panel keys that have NO roof/floor panel above them.
    Returns dict: floor_index -> set of uncovered cell keys.
    """
    nf = len(Building["panels"]["panel_coords_per_floor"])
    uncovered = {}
    for fi in range(nf):
        panel_keys = Building["panels"]["panel_coords_per_floor"][fi]
        panel_set = set()
        for k in panel_keys:
            panel_set.add((round(k[0], 4), round(k[1], 4)))
        if fi + 1 < nf:
            above_keys = Building["panels"]["panel_coords_per_floor"][fi + 1]
            above_set = set()
            for k in above_keys:
                above_set.add((round(k[0], 4), round(k[1], 4)))
        else:
            above_set = set()
        uncovered_keys = panel_set - above_set
        if uncovered_keys:
            uncovered[fi] = uncovered_keys
    return uncovered


def create_vertical_arch_extrusion_oriented(panel_key, gs, base_z, arch_height, orientation, layer_name,
                                             inset_offset=0.05):
    """Create a rectangular arch with specified orientation.
    orientation: "NS" = opens north-south (Y direction, walls on X sides)
                 "EW" = opens east-west (X direction, walls on Y sides)
    Two side walls + top cap. Front/back open.

    All surfaces are built as perforated mesh panels with square holes.
    inset_offset: small inward shrink (m) so roof panels don't collide with wall panels.
    """
    off = inset_offset
    cx  = panel_key[0] + off
    cy  = panel_key[1] + off
    cx2 = round(panel_key[0] + gs - off, 4)
    cy2 = round(panel_key[1] + gs - off, 4)
    z_bottom = base_z
    z_top    = base_z + arch_height
    created_ids = []

    COLOR_SIDE = (180, 150, 200)
    COLOR_TOP  = (200, 180, 220)

    pw_side = round(cy2 - cy, 4) if orientation == "NS" else round(cx2 - cx, 4)
    top_w   = round(cx2 - cx, 4)
    top_d   = round(cy2 - cy, 4)

    if orientation == "NS":
        # Side walls on X = cx and X = cx2, spanning Y and Z
        created_ids += _create_perforated_panel_mesh(
            [rg.Point3d(cx,  cy,  z_bottom), rg.Point3d(cx,  cy2, z_bottom),
             rg.Point3d(cx,  cy2, z_top),    rg.Point3d(cx,  cy,  z_top)],
            pw_side, arch_height, COLOR_SIDE, layer_name)
        created_ids += _create_perforated_panel_mesh(
            [rg.Point3d(cx2, cy,  z_bottom), rg.Point3d(cx2, cy2, z_bottom),
             rg.Point3d(cx2, cy2, z_top),    rg.Point3d(cx2, cy,  z_top)],
            pw_side, arch_height, COLOR_SIDE, layer_name)
    else:  # "EW"
        # Side walls on Y = cy and Y = cy2, spanning X and Z
        created_ids += _create_perforated_panel_mesh(
            [rg.Point3d(cx,  cy,  z_bottom), rg.Point3d(cx2, cy,  z_bottom),
             rg.Point3d(cx2, cy,  z_top),    rg.Point3d(cx,  cy,  z_top)],
            pw_side, arch_height, COLOR_SIDE, layer_name)
        created_ids += _create_perforated_panel_mesh(
            [rg.Point3d(cx,  cy2, z_bottom), rg.Point3d(cx2, cy2, z_bottom),
             rg.Point3d(cx2, cy2, z_top),    rg.Point3d(cx,  cy2, z_top)],
            pw_side, arch_height, COLOR_SIDE, layer_name)

    # Top cap (horizontal)
    if top_w > 0.01 and top_d > 0.01:
        created_ids += _create_perforated_panel_mesh(
            [rg.Point3d(cx,  cy,  z_top), rg.Point3d(cx2, cy,  z_top),
             rg.Point3d(cx2, cy2, z_top), rg.Point3d(cx,  cy2, z_top)],
            top_w, top_d, COLOR_TOP, layer_name)

    return created_ids




def build_floor_panel_id_to_key_map(Building):
    """Build mapping from floor panel IDs to their cell keys."""
    pid_to_info = {}
    gs = Building["grid"]["spacing"]
    for fi in range(len(Building["panels"]["panel_ids_per_floor"])):
        panel_ids = Building["panels"]["panel_ids_per_floor"][fi]
        panel_keys = Building["panels"]["panel_coords_per_floor"][fi]
        key_set = set()
        for k in panel_keys:
            key_set.add((round(k[0], 4), round(k[1], 4)))
        for pid in panel_ids:
            if not rs.IsObject(pid):
                continue
            bb = rs.BoundingBox(pid)
            if bb:
                cx = (bb[0][0] + bb[2][0]) / 2.0
                cy = (bb[0][1] + bb[2][1]) / 2.0
                pz = bb[0][2]
                best_key = None
                best_dist = float('inf')
                for k in key_set:
                    kx, ky = k
                    d = abs(cx - (kx + gs / 2.0)) + abs(cy - (ky + gs / 2.0))
                    if d < best_dist:
                        best_dist = d
                        best_key = k
                if best_key:
                    pid_to_info[str(pid)] = {"floor_index": fi, "cell_key": best_key, "panel_z": pz}
    return pid_to_info


def _vert_arch_footprint(cell_key, gs):
    """XY bounding box of one terrace cell."""
    cx, cy = cell_key[0], cell_key[1]
    return (cx, cy, round(cx + gs, 4), round(cy + gs, 4))


def _vfp_overlap_xy(fp_a, fp_b):
    """True when two XY footprints have interior overlap (touching edges don't count)."""
    if fp_a[2] <= fp_b[0] or fp_b[2] <= fp_a[0]: return False
    if fp_a[3] <= fp_b[1] or fp_b[3] <= fp_a[1]: return False
    return True


def _vfp_collide_3d(fp_a, za0, za1, fp_b, zb0, zb1):
    """True when two arch volumes overlap in both XY and Z."""
    if za1 <= zb0 or zb1 <= za0: return False
    return _vfp_overlap_xy(fp_a, fp_b)


def process_vertical_arch_extrusions(Building):
    """ELEVATION STEP 2 — Automatic vertical arch extrusion (4 m fixed height).

    Reuses the shared ElevationExtrusionDialog already shown by
    process_wall_extrusions (stored in Building["_elev_dlg"]).
    If the dialog has not been shown yet it shows it now.

    Algorithm
    ---------
    1.  Check vertical_choice from shared dialog.
    2.  Collect all uncovered terrace panel keys with their exact Z
        (from live Rhino bounding-boxes via build_floor_panel_id_to_key_map).
    3.  Checker pattern identical to wall extrusions selects 30-40%.
    4.  All arches are exactly 4 m tall.
    5.  3-D collision guard — no surface intersections.
    """
    print_section_header("ELEVATION STEP 2: VERTICAL ARCH EXTRUSION (AUTO)")

    # ── Reuse or show combined dialog ────────────────────────────────────────
    _elev_dlg = Building.get("_elev_dlg")
    if _elev_dlg is None:
        _elev_dlg = ElevationExtrusionDialog()
        _elev_dlg.ShowModal(Rhino.UI.RhinoEtoApp.MainWindow)
        Building["_elev_dlg"] = _elev_dlg

    if _elev_dlg.vertical_choice != "proceed":
        print("  Skipping vertical arch extrusions.")
        print_section_footer()
        return

    # ── Fixed parameters ─────────────────────────────────────────────────────
    ARCH_HEIGHT  = 4.0    # metres — fixed, no variation
    ARCH_ORIENT  = "NS"   # North-South passage (open Y faces)

    layer_name = "Vertical_Extrusions"
    if not rs.IsLayer(layer_name):
        rs.AddLayer(layer_name, (180, 150, 200))

    gs  = Building["grid"]["spacing"]
    pth = Building["panels"]["panel_thickness"]
    bd  = Building["structure"]["plinth_beams"]["depth"]

    # ── Step 1: find all uncovered (terrace) panel keys ──────────────────────
    uncovered = get_uncovered_panel_keys(Building)

    if not uncovered:
        print("  No uncovered panels found.  All panels have roof/floor above.")
        print_section_footer()
        return

    total_uncovered = sum(len(v) for v in uncovered.values())
    print("  {} uncovered (terrace) panels across {} floor(s).".format(
        total_uncovered, len(uncovered)))

    # ── Step 2: resolve EXACT base_z per cell from live Rhino objects ────────
    pid_to_info = build_floor_panel_id_to_key_map(Building)

    cell_z_map = {}   # (fi, cx, cy) -> panel_z  (top-of-slab Z)
    for info in pid_to_info.values():
        fi  = info["floor_index"]
        ck  = info["cell_key"]
        pz  = info["panel_z"]
        key = (fi, ck[0], ck[1])
        if key not in cell_z_map or pz < cell_z_map[key]:
            cell_z_map[key] = pz

    # ── Step 3: sorted candidate list ────────────────────────────────────────
    candidates = []   # (fi, cell_key, arch_base_z)
    for fi, keys in sorted(uncovered.items()):
        sorted_keys = sorted(keys, key=lambda k: (round(k[1] / gs), round(k[0] / gs)))
        for ck in sorted_keys:
            lookup = (fi, ck[0], ck[1])
            if lookup in cell_z_map:
                pz = cell_z_map[lookup]
            else:
                ftp = Building["structure"]["columns"]["top_points_per_floor"]
                if fi < len(ftp) and ftp[fi]:
                    pz = ftp[fi][0][2] + bd
                else:
                    pz = sum(Building["floors"]["floor_heights"][:fi + 1])
            candidates.append((fi, ck, pz + pth))   # arch sits on top of slab

    # ── Step 4: offset-checker selection (~30-40 %) ───────────────────────────
    row_buckets = {}
    for (fi, ck, bz) in candidates:
        row_idx = int(round(ck[1] / gs))
        col_idx = int(round(ck[0] / gs))
        row_buckets.setdefault((fi, row_idx), []).append((col_idx, fi, ck, bz))

    for rb_key in row_buckets:
        row_buckets[rb_key].sort(key=lambda t: t[0])

    checker_selected = []   # (fi, cell_key, arch_base_z)
    for (fi, row_idx), cols in sorted(row_buckets.items()):
        floor_phase = fi % 2
        if row_idx % 2 != floor_phase:
            continue
        for pos_idx, (col_idx, f2, ck, bz) in enumerate(cols):
            if pos_idx % 2 == floor_phase:
                checker_selected.append((f2, ck, bz))

    n_sel = len(checker_selected)
    pct   = 100.0 * n_sel / max(1, total_uncovered)

    # Safety trim if over 42 %
    if pct > 42.0:
        checker_selected = [e for i, e in enumerate(checker_selected) if i % 4 != 0]
        n_sel = len(checker_selected)
        pct   = 100.0 * n_sel / max(1, total_uncovered)

    print("  Checker selection : {} panels  ({:.0f}% of {} uncovered)".format(
        n_sel, pct, total_uncovered))
    print("  Height            : {:.0f} m (fixed)".format(ARCH_HEIGHT))
    print("  Orientation       : NS (North-South passage)")

    # ── Step 5: extrude with 3-D collision guard ──────────────────────────────
    committed    = []   # (footprint, z_bot, z_top)
    all_arch_ids = []
    n_created    = 0
    n_collide    = 0

    for (fi, ck, bz) in checker_selected:
        fp    = _vert_arch_footprint(ck, gs)
        z_bot = bz
        z_top = bz + ARCH_HEIGHT

        collides = any(
            _vfp_collide_3d(fp, z_bot, z_top, ex_fp, ex_zb, ex_zt)
            for (ex_fp, ex_zb, ex_zt) in committed
        )

        if collides:
            n_collide += 1
            print("    SKIP fl={} @ ({:.1f},{:.1f}) — collision".format(fi, ck[0], ck[1]))
            continue

        arch_ids = create_vertical_arch_extrusion_oriented(
            ck, gs, z_bot, ARCH_HEIGHT, ARCH_ORIENT, layer_name)

        if arch_ids:
            all_arch_ids.extend(arch_ids)
            committed.append((fp, z_bot, z_top))
            n_created += 1
            print("    Arch [{:3d}] fl={} @ ({:.1f},{:.1f})  base_z={:.2f}  h=4m  surfs={}".format(
                n_created, fi, ck[0], ck[1], z_bot, len(arch_ids)))

    sc.doc.Views.Redraw()
    Building["elevation"]["vertical_extrusion_ids"] = all_arch_ids

    print("\n  Arches created  : {}  ({:.0f}% of uncovered panels)".format(
        n_created, 100.0 * n_created / max(1, total_uncovered)))
    if n_collide:
        print("  Skipped (collision): {}".format(n_collide))
    print("  Total surfaces  : {}".format(len(all_arch_ids)))
    print_section_footer()


# ============================================================ WALL PANEL SUBDIVISION SYSTEM ============================================================
# Elevation directions and their camera view commands
ELEVATION_DIRECTIONS = [
    {"name": "NORTH", "view_cmd": "_-SetView _World _Front",  "axis": "Y", "facing": "north"},
    {"name": "EAST",  "view_cmd": "_-SetView _World _Right",  "axis": "X", "facing": "east"},
    {"name": "SOUTH", "view_cmd": "_-SetView _World _Back",   "axis": "Y", "facing": "south"},
    {"name": "WEST",  "view_cmd": "_-SetView _World _Left",   "axis": "X", "facing": "west"},
]

# ── Helper: sci-fi dialog header factory ─────────────────────────────────────
def _make_scifi_header(panel, title_text, header_color_rgb, icon_key=None):
    """Populate a panel with the 3D card icon + title header row."""
    panel.BackgroundColor = make_color(*dialog_header_bg_rgb())
    panel.Padding = drawing.Padding(20, 16, 20, 16)
    iv = forms.ImageView()
    iv.Image = get_arch_dialog_icon(icon_key or title_text, size=48)
    iv.Size = drawing.Size(48, 48)
    lbl = forms.Label()
    lbl.Text = title_text
    lbl.Font = drawing.Font(drawing.FontFamily("Impact"), 16, drawing.FontStyle.Bold)
    lbl.TextColor = make_color(*BH_WHITE)
    hl = forms.TableLayout()
    hl.Spacing = drawing.Size(12, 0)
    hr = forms.TableRow()
    hr.Cells.Add(forms.TableCell(iv, False))
    hr.Cells.Add(forms.TableCell(lbl, True))
    hl.Rows.Add(hr)
    panel.Content = hl


def _make_scifi_sep(color_rgb):
    sep = forms.Panel()
    sep.BackgroundColor = make_color(*color_rgb)
    sep.Height = 4
    return sep


def _make_scifi_button(text, bg_rgb, w=320, h=48, bold=True):
    btn = forms.Button()
    btn.Text = text
    btn.Font = drawing.Font(drawing.FontFamily("Impact"), 13, drawing.FontStyle.Bold)
    btn.BackgroundColor = make_color(*bg_rgb)
    btn.TextColor = make_color(*BH_PURE_WHITE)
    btn.Size = drawing.Size(w, h)
    return btn


def _make_scifi_label(text, size=12, bold=False, color=None):
    lbl = forms.Label()
    lbl.Text = text
    lbl.Font = drawing.Font(drawing.FontFamily("Georgia"), size,
                            drawing.FontStyle.Bold if bold else drawing.FontStyle.Italic)
    lbl.TextColor = make_color(*(color or DIALOG_TEXT_PRIMARY))
    lbl.Wrap = forms.WrapMode.Word
    return lbl



# ============================================================
# PROJECT INTRODUCTION DIALOG  —  PIXEL PERFECT LIVING
# Sci-fi animated pixel-building splash screen.
# Shown once at startup, before any user input is collected.
# The header renders a live pixel-building skyline via Eto Drawing:
#   • Each cell breathes (sine-wave alpha), fades, and re-appears
#   • Multi-size pixel blocks, halftone scatter dots, accent colour bursts
#   • Colours shift through the reference-image palette:
#       cyan → magenta → gold → lime — all on deep-night indigo
# UITimer drives ~12 fps re-render; disposed automatically on close.
# ============================================================
class ProjectIntroDialog(forms.Dialog[bool]):
    """Pixel Perfect Living — animated sci-fi intro slide."""

    # ── Dark blood-red pixel palette (plain RGB, float constructor handles rendering) ──
    _PIX_PALETTES = [
        (140,   0,   0),   # vivid blood-red accent
        ( 72,   0,   0),   # deep maroon shadow
        (245, 245, 245),   # white highlight
        (218, 218, 218),   # neutral grey fill
        (128,   0,   2),   # dark blood-red linework
        (165,   8,   2),   # bright blood-red glow
    ]

    def __init__(self):
        super(ProjectIntroDialog, self).__init__()
        self.BackgroundColor = make_color(*BH_BLACK)

        self._phase   = 0.0          # animation clock
        self._timer   = None         # UITimer stored for cleanup
        self._iv      = None         # ImageView holding the live bitmap

        self.Title     = "PIXEL PERFECT LIVING  //  PROJECT INTRODUCTION"
        self.Padding   = drawing.Padding(0)
        self.Resizable = False
        self.MinimumSize = drawing.Size(560, 480)

        # ── pixel canvas constants ──────────────────────────────────────
        self._CW   = 560
        self._CH   = 160
        self._CELL = 8      # base cell size (px)

        import math, random
        self._math   = math
        self._random = random

        COLS = self._CW // self._CELL
        ROWS = self._CH // self._CELL

        # Build skyline heightmap: column → topmost filled row index
        hmap = [ROWS - 2] * COLS
        towers = [
            (0.08, 0.10, 0.85),   # (centre_x_frac, width_frac, height_frac)
            (0.22, 0.06, 0.60),
            (0.34, 0.13, 1.00),   # tallest — centre-left dominant tower
            (0.47, 0.05, 0.55),
            (0.55, 0.11, 0.90),
            (0.69, 0.06, 0.65),
            (0.79, 0.09, 0.80),
            (0.91, 0.07, 0.50),
        ]
        for cx, w, hf in towers:
            l = max(0, int((cx - w / 2) * COLS))
            r = min(COLS, int((cx + w / 2) * COLS))
            top = int((1.0 - hf) * ROWS)
            for c in range(l, r):
                if top < hmap[c]:
                    hmap[c] = top
        self._hmap = hmap
        self._COLS = COLS
        self._ROWS = ROWS

        # Pre-compute per-cell random seeds for organic variation
        rng = random.Random(42)
        self._cell_phase  = [[rng.random() * 6.28 for _ in range(COLS)] for _ in range(ROWS)]
        self._cell_speed  = [[0.35 + rng.random() * 0.75 for _ in range(COLS)] for _ in range(ROWS)]
        self._cell_psize  = [[rng.choice([6, 7, 8, 5]) for _ in range(COLS)] for _ in range(ROWS)]
        self._cell_pal    = [[rng.randint(0, len(self._PIX_PALETTES)-1) for _ in range(COLS)] for _ in range(ROWS)]

        # ── build initial bitmap & ImageView ───────────────────────────
        self._iv = forms.ImageView()
        self._iv.Size = drawing.Size(self._CW, self._CH)
        self._iv.Image = self._make_bmp()

        # ── overlay text panel (sits below canvas inside header block) ──
        tag_lbl = forms.Label()
        tag_lbl.Text = "//  INITIALISING PARAMETRIC ENGINE  //"
        tag_lbl.Font = drawing.Font(drawing.FontFamily("Impact"), 9,
                                    drawing.FontStyle.Bold)
        tag_lbl.TextColor = make_color(*BH_RED)

        title_lbl = forms.Label()
        title_lbl.Text = "PIXEL PERFECT LIVING"
        title_lbl.Font = drawing.Font(drawing.FontFamily("Impact"), 22, drawing.FontStyle.Bold)
        title_lbl.TextColor = make_color(*BH_WHITE)

        arch_lbl = forms.Label()
        arch_lbl.Text = "PROJECT ARCHITECT  //  GOWTHAMAN MARIMUTHU"
        arch_lbl.Font = drawing.Font(drawing.FontFamily("Georgia"), 10, drawing.FontStyle.Bold)
        arch_lbl.TextColor = make_color(*BH_WHITE)

        text_layout = forms.TableLayout()
        text_layout.Spacing = drawing.Size(0, 5)
        text_layout.Padding = drawing.Padding(26, 10, 26, 18)
        text_layout.Rows.Add(forms.TableRow(forms.TableCell(tag_lbl,   True)))
        text_layout.Rows.Add(forms.TableRow(forms.TableCell(title_lbl, True)))
        text_layout.Rows.Add(forms.TableRow(forms.TableCell(arch_lbl,  True)))

        text_panel = forms.Panel()
        text_panel.BackgroundColor = make_color(*BH_BLACK)
        text_panel.Content = text_layout

        header_layout = forms.TableLayout()
        header_layout.Spacing = drawing.Size(0, 0)
        header_layout.Rows.Add(forms.TableRow(forms.TableCell(self._iv,   True)))
        header_layout.Rows.Add(forms.TableRow(forms.TableCell(text_panel, True)))

        header_panel = forms.Panel()
        header_panel.BackgroundColor = make_color(*BH_BLACK)
        header_panel.Content = header_layout

        # ── accent strip — dark red / black only ─────────────────────────
        strip_tl = forms.TableLayout()
        strip_tl.Spacing = drawing.Size(0, 0)
        strip_row = forms.TableRow()
        strip_cols = [
            BH_RED,       # dark red
            BH_RED_DARK,  # darker red
            BH_RED,       # dark red
            BH_BLACK,     # black
        ]
        for sc in strip_cols:
            sp = forms.Panel()
            sp.BackgroundColor = make_color(*sc)
            sp.Height = 5
            strip_row.Cells.Add(forms.TableCell(sp, True))
        strip_tl.Rows.Add(strip_row)

        # ── BODY — minimal: 3 fields only ──────────────────────────────
        body_panel = forms.Panel()
        body_panel.Padding = drawing.Padding(30, 16, 30, 16)

        # Helper: small muted tag label
        def _tag(txt):
            l = forms.Label()
            l.Text = txt
            l.Font = drawing.Font(drawing.FontFamily("Georgia"), 8, drawing.FontStyle.Italic)
            l.TextColor = make_color(*BH_WHITE)
            return l

        # Helper: thin separator panel
        def _sep(rgb):
            p = forms.Panel()
            p.BackgroundColor = make_color(*rgb)
            p.Height = 3
            return p

        # Helper: value as a read-only TextBox — guaranteed to render in Eto
        # regardless of label-collapse bugs.
        def _val_box(txt, rgb, size=14):
            tb = forms.TextBox()
            tb.Text = txt
            tb.Font = drawing.Font(drawing.FontFamily("Impact"), size, drawing.FontStyle.Bold)
            tb.TextColor    = make_color(*rgb)
            tb.ReadOnly     = True
            tb.ShowBorder   = False
            tb.MinimumSize  = drawing.Size(200, size * 2 + 4)
            return tb

        # Row 1: PROJECT NAME
        proj_tag = _tag("PROJECT NAME")
        proj_val = _val_box("PIXEL PERFECT LIVING",       BH_WHITE, 14)

        # Row 2: COURSE
        course_tag = _tag("COURSE")
        course_val = _val_box("PROGRAMMING AND SIMULATION", BH_WHITE, 13)

        # Row 3: PROJECT ARCHITECT
        arch_tag = _tag("PROJECT ARCHITECT")
        arch_val = _val_box("GOWTHAMAN MARIMUTHU",         BH_RED, 14)

        # Buttons
        start_btn = _make_scifi_button(
            "  >>  BEGIN PROJECT  <<  ", DIALOG_ACCENT_GREEN, w=300, h=46)
        start_btn.Click += self._on_start

        cancel_btn = forms.Button()
        cancel_btn.Text = "  ABORT  "
        cancel_btn.Font = drawing.Font(drawing.FontFamily("Georgia"), 10, drawing.FontStyle.Bold)
        cancel_btn.BackgroundColor = make_color(*DIALOG_CANCEL_BG)
        cancel_btn.TextColor       = make_color(*DIALOG_CANCEL_TEXT)
        cancel_btn.Size = drawing.Size(130, 46)
        cancel_btn.Click += self._on_cancel

        btn_tl = forms.TableLayout()
        btn_tl.Spacing = drawing.Size(14, 0)
        btn_tr = forms.TableRow()
        btn_tr.Cells.Add(forms.TableCell(None,       True))
        btn_tr.Cells.Add(forms.TableCell(cancel_btn, False))
        btn_tr.Cells.Add(forms.TableCell(start_btn,  False))
        btn_tl.Rows.Add(btn_tr)

        # Final assembly — every widget explicitly in the list
        bl = forms.TableLayout()
        bl.Spacing = drawing.Size(0, 8)
        for w in [proj_tag,   proj_val,   _sep(DIALOG_ACCENT_PINK),
                  course_tag, course_val, _sep(DIALOG_ACCENT_YELLOW),
                  arch_tag,   arch_val,   _sep(DIALOG_ACCENT_BLUE),
                  btn_tl]:
            bl.Rows.Add(forms.TableRow(forms.TableCell(w, True)))
        body_panel.Content = bl

        # Master layout
        ml = forms.TableLayout()
        ml.Spacing = drawing.Size(0, 0)
        ml.Rows.Add(forms.TableRow(forms.TableCell(header_panel, True)))
        ml.Rows.Add(forms.TableRow(forms.TableCell(strip_tl,     True)))
        ml.Rows.Add(forms.TableRow(forms.TableCell(body_panel,   True)))
        self.Content = ml

        # Start animation timer
        self._timer = forms.UITimer()
        self._timer.Interval = 0.08
        self._timer.Elapsed += self._on_tick
        self._timer.Start()
        self.Closed += self._on_closed

    # ── Pixel building bitmap renderer ─────────────────────────────────
    def _make_bmp(self):
        import math, random
        m   = self._math
        rng = random.Random(int(self._phase * 137.0))

        bmp = drawing.Bitmap(self._CW, self._CH,
                             drawing.PixelFormat.Format32bppRgba)
        g = drawing.Graphics(bmp)
        try:
            # ── white background ─────────────────────────────────────────
            g.FillRectangle(
                drawing.SolidBrush(drawing.Color(245.0/255, 245.0/255, 245.0/255, 1.0)),
                drawing.RectangleF(0, 0, self._CW, self._CH))

            # ── faint grid lines ──────────────────────────────────────────
            gpen = drawing.Pen(
                drawing.Color(210.0/255, 210.0/255, 210.0/255, 80.0/255), 0.5)
            for c in range(self._COLS + 1):
                x = c * self._CELL
                g.DrawLine(gpen, x, 0, x, self._CH)
            for r in range(self._ROWS + 1):
                y = r * self._CELL
                g.DrawLine(gpen, 0, y, self._CW, y)

            # ── building pixel cells ─────────────────────────────────────
            t = self._phase
            for r in range(self._ROWS):
                for c in range(self._COLS):
                    if r < self._hmap[c]:
                        # Above skyline: sparse scatter pixels only
                        if rng.random() > 0.04:
                            continue
                        scatter_alpha = rng.randint(30, 100)
                        sc = self._PIX_PALETTES[rng.randint(0, len(self._PIX_PALETTES)-1)]
                        sz = rng.choice([1, 2, 3])
                        px = c * self._CELL + rng.randint(0, self._CELL - sz)
                        py = r * self._CELL + rng.randint(0, self._CELL - sz)
                        g.FillRectangle(
                            drawing.SolidBrush(
                                drawing.Color(sc[0]/255.0, sc[1]/255.0, sc[2]/255.0,
                                    scatter_alpha/255.0)),
                            drawing.RectangleF(px, py, sz, sz))
                        continue

                    # Building cell — organic breathing animation
                    phase  = self._cell_phase[r][c]
                    speed  = self._cell_speed[r][c]
                    breathe = 0.5 + 0.5 * m.sin(t * speed + phase)

                    # Distance from top of tower drives base opacity
                    tower_depth = (r - self._hmap[c]) / max(1, self._ROWS - self._hmap[c])
                    base_alpha  = 0.3 + 0.5 * tower_depth

                    prob = base_alpha + 0.5 * breathe
                    if rng.random() > prob:
                        continue

                    alpha_v = int(min(255, max(40,
                        (base_alpha + 0.6 * breathe) * 255)))

                    # Colour: primary cyan + accent bursts
                    pal_idx = self._cell_pal[r][c]
                    is_accent = ((r * 3 + c * 7 + int(t * 1.5)) % 17 == 0)
                    col = self._PIX_PALETTES[pal_idx if is_accent else 0]

                    # Variable pixel size for organic halftone feel
                    sz  = self._cell_psize[r][c]
                    off = (self._CELL - sz) // 2
                    px  = c * self._CELL + off
                    py  = r * self._CELL + off

                    g.FillRectangle(
                        drawing.SolidBrush(
                            drawing.Color(col[0]/255.0, col[1]/255.0, col[2]/255.0,
                                alpha_v/255.0)),
                        drawing.RectangleF(px, py, sz, sz))

                    # Bright core dot on high-breathe cells
                    if breathe > 0.88 and sz >= 6:
                        core = max(1, sz - 4)
                        g.FillRectangle(
                            drawing.SolidBrush(
                                drawing.Color(1.0, 1.0, 1.0,
                                    (alpha_v * 0.65) / 255.0)),
                            drawing.RectangleF(px + 2, py + 2, core, core))

            # ── bottom gradient fade into body (white fade) ────────────────
            steps = 30
            for i in range(steps):
                frac     = i / float(steps)
                fade_a   = frac * frac * (220.0 / 255.0)
                y_start  = self._CH * (1.0 - (steps - i) / float(steps) * 0.55)
                g.FillRectangle(
                    drawing.SolidBrush(
                        drawing.Color(245.0/255, 245.0/255, 245.0/255, fade_a)),
                    drawing.RectangleF(0, y_start,
                                       self._CW, self._CH - y_start))

            # ── top vignette (pixels dissolve at crown — white) ──────────
            for i in range(18):
                frac  = 1.0 - i / 18.0
                top_a = frac * frac * (180.0 / 255.0)
                g.FillRectangle(
                    drawing.SolidBrush(
                        drawing.Color(245.0/255, 245.0/255, 245.0/255, top_a)),
                    drawing.RectangleF(0, 0, self._CW,
                                       (18 - i) / 18.0 * self._CH * 0.22))

        finally:
            g.Dispose()
        return bmp

    # ── Timer callback ──────────────────────────────────────────────────
    def _on_tick(self, sender, e):
        self._phase += 0.07
        old_img = self._iv.Image
        self._iv.Image = self._make_bmp()
        try:
            old_img.Dispose()
        except Exception:
            pass

    def _on_closed(self, sender, e):
        if self._timer is not None:
            try:
                self._timer.Stop()
            except Exception:
                pass

    def _on_start(self, sender, e):
        self.Close(True)

    def _on_cancel(self, sender, e):
        self.Close(False)


# ── Dialog: Elevation intro / start ──────────────────────────────────────────
class FacadeSubdivisionDialog(forms.Dialog[bool]):
    """Single combined dialog shown ONCE for all 4 elevations.

    Replaces the individual ElevationStartDialog, SubdivisionDirectionDialog,
    and GlassSelectionDialog popups.  The dialog is fully informational — it
    describes what will happen automatically — and asks for one confirmation:
      > START ALL FACADES   ->  user_choice = "start"
      [ SKIP ALL ]          ->  user_choice = "skip"
      ABORT                 ->  user_choice = "cancel"

    Auto settings (fixed, never asked):
      Subdivision direction : VERTICAL (3 equal columns per full-height panel)
      Glass selection       : automatic random pattern, target 40-50% glazing
      Window frames         : Schuco AWS 75 BS.SI aluminium, inset 40 mm
    """
    def __init__(self, panel_counts):
        """panel_counts : dict {elevation_name: int}"""
        super(FacadeSubdivisionDialog, self).__init__()
        self.BackgroundColor = make_color(*BH_BLACK)
        self.user_choice = None
        self.Title = "FACADE SUBDIVISION  //  ALL ELEVATIONS"
        self.Padding = drawing.Padding(0)
        self.Resizable = False
        self.MinimumSize = drawing.Size(600, 680)

        hp = forms.Panel()
        _make_scifi_header(hp, "FACADE SUBDIVISION  //  ALL ELEVATIONS", BH_BLACK, "FACADE SUBDIVISION")

        bp = forms.Panel()
        bp.BackgroundColor = make_color(*DIALOG_SURFACE_DEEP)
        bp.Padding = drawing.Padding(28, 20, 28, 20)

        def _sec(txt, color, icon_bmp=None):
            if icon_bmp is not None:
                iv = forms.ImageView()
                iv.Image = icon_bmp
                iv.Size = drawing.Size(28, 28)
                l = forms.Label()
                l.Text = txt
                l.Font = drawing.Font(drawing.FontFamily("Impact"), 12, drawing.FontStyle.Bold)
                l.TextColor = make_color(*color)
                row = forms.TableLayout()
                row.Spacing = drawing.Size(8, 0)
                r = forms.TableRow()
                r.Cells.Add(forms.TableCell(iv, False))
                r.Cells.Add(forms.TableCell(l, True))
                row.Rows.Add(r)
                return row
            l = forms.Label()
            l.Text = txt
            l.Font = drawing.Font(drawing.FontFamily("Impact"), 12, drawing.FontStyle.Bold)
            l.TextColor = make_color(*color)
            return l

        def _bod(txt):
            l = forms.Label()
            l.Text = txt
            l.Font = drawing.Font(drawing.FontFamily("Georgia"), 10, drawing.FontStyle.Italic)
            l.TextColor = make_color(*DIALOG_TEXT_SECONDARY)
            l.Wrap = forms.WrapMode.Word
            return l

        elev_lines = ""
        for en in ["NORTH", "EAST", "SOUTH", "WEST"]:
            elev_lines += "  {:<6}  {}  wall panels\n".format(en, panel_counts.get(en, 0))

        sep = _make_scifi_sep(BH_MID_GREY)

        sb = _make_scifi_button("  > START ALL FACADES  ", BH_RED, w=420, h=48)
        sb.Click += self.on_start
        skip_b = _make_scifi_button("  [ SKIP ALL ]", DIALOG_SURFACE_RAISED, w=200, h=42, bold=False)
        skip_b.TextColor = make_color(*BH_WHITE)
        skip_b.Click += self.on_skip
        ab = _make_scifi_button("  ABORT  ", DIALOG_CANCEL_BG, w=140, h=40, bold=False)
        ab.TextColor = make_color(*DIALOG_CANCEL_TEXT)
        ab.Click += self.on_cancel

        bl = forms.TableLayout()
        bl.Spacing = drawing.Size(0, 10)
        items = [
            _sec("FACADES  —  PANEL COUNTS", BH_AMBER, icon_bmp=_icon_sub_panel_counts()),
            _bod(elev_lines.rstrip()),
            _make_scifi_sep(BH_MID_GREY),
            _sec("PANEL SUBDIVISION  (AUTO — VERTICAL x3)", BH_RED, icon_bmp=_icon_sub_panel_subdivision()),
            _bod(
                "Every full-height wall panel is subdivided VERTICALLY into\n"
                "3 EQUAL COLUMNS automatically. Direction and count are fixed.\n"
                "Parapet and transition panels are skipped."
            ),
            _make_scifi_sep(BH_MID_GREY),
            _sec("GLASS WINDOWS  (AUTO — GEG / DIN 18032)", BH_AMBER, icon_bmp=_icon_sub_glass_windows()),
            _bod(
                "Glass is assigned automatically. Target: 40-50% glazing per\n"
                "facade (above German GEG min of 30% of habitable floor area).\n\n"
                "Pattern: each full-height panel has 3 sub-columns.\n"
                "  1 or 2 sub-columns per panel become glass.\n"
                "  Sub-column selection alternates across panels to create\n"
                "  a rhythmic checkerboard pattern with visual interest.\n"
                "  Adjacent panels never share identical glazing layout."
            ),
            _make_scifi_sep(BH_RED),
            sb, skip_b, ab,
        ]
        for w in items:
            bl.Rows.Add(forms.TableRow(forms.TableCell(w, True)))
        bp.Content = bl

        ml = forms.TableLayout()
        ml.Spacing = drawing.Size(0, 0)
        ml.Rows.Add(forms.TableRow(forms.TableCell(hp, True)))
        ml.Rows.Add(forms.TableRow(forms.TableCell(bp, True)))
        self.Content = ml

    def on_start(self, s, e):
        self.user_choice = "start"
        self.Close(True)

    def on_skip(self, s, e):
        self.user_choice = "skip"
        self.Close(True)

    def on_cancel(self, s, e):
        self.user_choice = "cancel"
        self.Close(False)


# Compatibility stub — never shown, always auto-starts
class ElevationStartDialog(forms.Dialog[bool]):
    def __init__(self, elevation_name, panel_count):
        super(ElevationStartDialog, self).__init__()
        self.user_choice = "start"


# ── Dialog: Subdivision direction (H / V) ────────────────────────────────────
class SubdivisionDirectionDialog(forms.Dialog[bool]):
    """Ask the user whether to subdivide a panel Horizontally or Vertically."""
    def __init__(self, panel_index, total_panels):
        super(SubdivisionDirectionDialog, self).__init__()
        self.BackgroundColor = make_color(*BH_BLACK)
        self.direction = None        # "H" or "V"
        self.count = None            # 2 or 3
        self.Title = "SUBDIVISION  //  PANEL {} / {}".format(panel_index, total_panels)
        self.Padding = drawing.Padding(0)
        self.Resizable = False
        self.MinimumSize = drawing.Size(540, 520)

        HEADER_COLOR = BH_BLACK
        SEP_COLOR    = BH_RED

        hp = forms.Panel()
        _make_scifi_header(hp, "PANEL SUBDIVISION  //  {} / {}".format(panel_index, total_panels),
                           HEADER_COLOR, "WALL PANELS")

        bp = forms.Panel()
        bp.BackgroundColor = make_color(*DIALOG_SURFACE_DEEP)
        bp.Padding = drawing.Padding(28, 22, 28, 22)

        info = _make_scifi_label(
            "Select the DIRECTION for this panel's subdivision.\n\n"
            "[H]  HORIZONTAL  — equal rows stacked vertically\n"
            "[V]  VERTICAL    — equal columns side by side\n\n"
            "Then choose NUMBER OF EQUAL PARTS: 2 or 3.",
            size=11)

        sep = _make_scifi_sep(SEP_COLOR)

        dir_lbl = _make_scifi_label("SUBDIVISION DIRECTION:", size=10, color=DIALOG_TEXT_SECONDARY)

        self.radio_h = forms.RadioButton()
        self.radio_h.Text = "  [H]  HORIZONTAL  //  equal rows (cut along width)"
        self.radio_h.Font = drawing.Font(drawing.FontFamily("Georgia"), 11, drawing.FontStyle.Italic)
        try_set_control_colors(self.radio_h, text_rgb=DIALOG_TEXT_PRIMARY)
        self.radio_h.Checked = True

        self.radio_v = forms.RadioButton(self.radio_h)
        self.radio_v.Text = "  [V]  VERTICAL    //  equal columns (cut along height)"
        self.radio_v.Font = drawing.Font(drawing.FontFamily("Georgia"), 11, drawing.FontStyle.Italic)
        try_set_control_colors(self.radio_v, text_rgb=DIALOG_TEXT_PRIMARY)

        count_lbl = _make_scifi_label("NUMBER OF EQUAL PARTS:", size=10, color=DIALOG_TEXT_SECONDARY)

        self.radio_2 = forms.RadioButton()
        self.radio_2.Text = "  [2]  TWO equal parts"
        self.radio_2.Font = drawing.Font(drawing.FontFamily("Georgia"), 11, drawing.FontStyle.Italic)
        try_set_control_colors(self.radio_2, text_rgb=DIALOG_TEXT_PRIMARY)
        self.radio_2.Checked = True

        self.radio_3 = forms.RadioButton(self.radio_2)
        self.radio_3.Text = "  [3]  THREE equal parts"
        self.radio_3.Font = drawing.Font(drawing.FontFamily("Georgia"), 11, drawing.FontStyle.Italic)
        try_set_control_colors(self.radio_3, text_rgb=DIALOG_TEXT_PRIMARY)

        ok_btn = _make_scifi_button("  [  CONFIRM SUBDIVISION  ]  ", BH_RED, w=280, h=44)
        ok_btn.Click += self.on_ok

        ab = _make_scifi_button("  ABORT  ", DIALOG_CANCEL_BG, w=140, h=40, bold=False)
        ab.TextColor = make_color(*DIALOG_CANCEL_TEXT)
        ab.Click += self.on_cancel

        btn_row = forms.TableLayout()
        btn_row.Spacing = drawing.Size(12, 0)
        br = forms.TableRow()
        br.Cells.Add(forms.TableCell(None, True))
        br.Cells.Add(forms.TableCell(ab, False))
        br.Cells.Add(forms.TableCell(ok_btn, False))
        btn_row.Rows.Add(br)

        bl = forms.TableLayout()
        bl.Spacing = drawing.Size(0, 8)
        bl.Rows.Add(forms.TableRow(forms.TableCell(info, True)))
        bl.Rows.Add(forms.TableRow(forms.TableCell(sep, True)))
        bl.Rows.Add(forms.TableRow(forms.TableCell(dir_lbl, True)))
        bl.Rows.Add(forms.TableRow(forms.TableCell(self.radio_h, True)))
        bl.Rows.Add(forms.TableRow(forms.TableCell(self.radio_v, True)))
        bl.Rows.Add(forms.TableRow(forms.TableCell(_make_scifi_sep(BH_RED), True)))
        bl.Rows.Add(forms.TableRow(forms.TableCell(count_lbl, True)))
        bl.Rows.Add(forms.TableRow(forms.TableCell(self.radio_2, True)))
        bl.Rows.Add(forms.TableRow(forms.TableCell(self.radio_3, True)))
        bl.Rows.Add(forms.TableRow(forms.TableCell(btn_row, True)))
        bp.Content = bl

        ml = forms.TableLayout()
        ml.Spacing = drawing.Size(0, 0)
        ml.Rows.Add(forms.TableRow(forms.TableCell(hp, True)))
        ml.Rows.Add(forms.TableRow(forms.TableCell(bp, True)))
        self.Content = ml

    def on_ok(self, s, e):
        self.direction = "V" if self.radio_v.Checked else "H"
        self.count = 3 if self.radio_3.Checked else 2
        self.Close(True)

    def on_cancel(self, s, e):
        self.Close(False)


# ── Dialog: Glass selection intro ────────────────────────────────────────────
class GlassSelectionDialog(forms.Dialog[bool]):
    """Intro before user selects sub-panels for glass."""
    def __init__(self, elevation_name, subdiv_count):
        super(GlassSelectionDialog, self).__init__()
        self.BackgroundColor = make_color(*BH_BLACK)
        self.user_choice = None
        self.Title = "GLASS WINDOW SELECTION  //  {}".format(elevation_name)
        self.Padding = drawing.Padding(0)
        self.Resizable = False
        self.MinimumSize = drawing.Size(560, 460)

        HEADER_COLOR = BH_BLACK
        SEP_COLOR    = BH_RED

        hp = forms.Panel()
        _make_scifi_header(hp, "GLASS WINDOWS  //  {} FACADE".format(elevation_name),
                           HEADER_COLOR, "WALL PANELS")

        bp = forms.Panel()
        bp.BackgroundColor = make_color(*DIALOG_SURFACE_DEEP)
        bp.Padding = drawing.Padding(28, 22, 28, 22)

        note = "NOTE: Only sub-panels resting ON beams & columns\n(full-height panels) are valid glass selections.\nParapet and transition panels are IGNORED." if subdiv_count > 0 else "No panels were subdivided on this facade."

        info = _make_scifi_label(
            "{} SUBDIVIDED PANELS available for glazing.\n\n"
            "Select the sub-panels you want to assign as GLASS.\n"
            "They will be replaced with a transparent glass surface.\n\n"
            "{}\n\n"
            "Choose an option:".format(subdiv_count, note),
            size=11)

        sep = _make_scifi_sep(SEP_COLOR)

        sb = _make_scifi_button("  > SELECT GLASS PANELS", BH_RED, w=320, h=46)
        sb.Click += self.on_select

        skip_b = _make_scifi_button("  [ SKIP  //  NO GLASS ]", DIALOG_SURFACE_RAISED, w=320, h=44, bold=False)
        skip_b.TextColor = make_color(*BH_WHITE)
        skip_b.Click += self.on_skip

        ab = _make_scifi_button("  ABORT  ", DIALOG_CANCEL_BG, w=140, h=40, bold=False)
        ab.TextColor = make_color(*DIALOG_CANCEL_TEXT)
        ab.Click += self.on_cancel

        bl = forms.TableLayout()
        bl.Spacing = drawing.Size(0, 11)
        bl.Rows.Add(forms.TableRow(forms.TableCell(info, True)))
        bl.Rows.Add(forms.TableRow(forms.TableCell(sep, True)))
        bl.Rows.Add(forms.TableRow(forms.TableCell(sb, True)))
        bl.Rows.Add(forms.TableRow(forms.TableCell(skip_b, True)))
        bl.Rows.Add(forms.TableRow(forms.TableCell(ab, True)))
        bp.Content = bl

        ml = forms.TableLayout()
        ml.Spacing = drawing.Size(0, 0)
        ml.Rows.Add(forms.TableRow(forms.TableCell(hp, True)))
        ml.Rows.Add(forms.TableRow(forms.TableCell(bp, True)))
        self.Content = ml

    def on_select(self, s, e):
        self.user_choice = "select"
        self.Close(True)

    def on_skip(self, s, e):
        self.user_choice = "skip"
        self.Close(True)

    def on_cancel(self, s, e):
        self.user_choice = "cancel"
        self.Close(False)


# ── Dialog: More subdivisions? ────────────────────────────────────────────────
class ContinueSubdivisionDialog(forms.Dialog[bool]):
    """Ask the user if they want to subdivide more panels on this elevation."""
    def __init__(self, elevation_name, iteration):
        super(ContinueSubdivisionDialog, self).__init__()
        self.BackgroundColor = make_color(*BH_BLACK)
        self.user_choice = None
        self.Title = "CONTINUE SUBDIVISION  //  {}".format(elevation_name)
        self.Padding = drawing.Padding(0)
        self.Resizable = False
        self.MinimumSize = drawing.Size(520, 380)

        HEADER_COLOR = BH_BLACK
        SEP_COLOR    = BH_RED

        hp = forms.Panel()
        _make_scifi_header(hp, "CONTINUE  //  {} FACADE".format(elevation_name),
                           HEADER_COLOR, "WALL PANELS")

        bp = forms.Panel()
        bp.BackgroundColor = make_color(*DIALOG_SURFACE_DEEP)
        bp.Padding = drawing.Padding(28, 22, 28, 22)

        info = _make_scifi_label(
            "Iteration {} complete.\n\n"
            "Do you want to SELECT MORE panels to subdivide\n"
            "on the {} ELEVATION?\n\n"
            "Or FINISH subdivision and move to glass selection.".format(iteration, elevation_name),
            size=11)

        sep = _make_scifi_sep(SEP_COLOR)

        more_b = _make_scifi_button("  > SELECT MORE PANELS TO SUBDIVIDE", BH_RED_DARK, w=360, h=46)
        more_b.Click += self.on_more

        done_b = _make_scifi_button("  [  DONE  //  GO TO GLASS SELECTION  ]", BH_RED, w=360, h=44)
        done_b.Click += self.on_done

        ab = _make_scifi_button("  ABORT  ", DIALOG_CANCEL_BG, w=140, h=40, bold=False)
        ab.TextColor = make_color(*DIALOG_CANCEL_TEXT)
        ab.Click += self.on_cancel

        bl = forms.TableLayout()
        bl.Spacing = drawing.Size(0, 11)
        bl.Rows.Add(forms.TableRow(forms.TableCell(info, True)))
        bl.Rows.Add(forms.TableRow(forms.TableCell(sep, True)))
        bl.Rows.Add(forms.TableRow(forms.TableCell(more_b, True)))
        bl.Rows.Add(forms.TableRow(forms.TableCell(done_b, True)))
        bl.Rows.Add(forms.TableRow(forms.TableCell(ab, True)))
        bp.Content = bl

        ml = forms.TableLayout()
        ml.Spacing = drawing.Size(0, 0)
        ml.Rows.Add(forms.TableRow(forms.TableCell(hp, True)))
        ml.Rows.Add(forms.TableRow(forms.TableCell(bp, True)))
        self.Content = ml

    def on_more(self, s, e):
        self.user_choice = "more"
        self.Close(True)

    def on_done(self, s, e):
        self.user_choice = "done"
        self.Close(True)

    def on_cancel(self, s, e):
        self.user_choice = "cancel"
        self.Close(False)


# ── Dialog: Elevation complete summary ───────────────────────────────────────
def _icon_variant_complete(size=48):
    """Building complete icon: key + stepped building silhouette + checkmark."""
    bmp = drawing.Bitmap(size, size, drawing.PixelFormat.Format32bppRgba)
    g = drawing.Graphics(bmp)
    try:
        g.AntiAlias = True
        g.FillRectangle(_icon_brush(BH_BLACK), 0, 0, size, size)
        s = size / 48.0
        pen = _icon_pen(BH_WHITE, 1.5)
        pen_thick = _icon_pen(BH_WHITE, 2.5)
        pen_thin = _icon_pen(BH_WHITE, 0.5)
        # Building silhouette (stepped, right side background)
        bldg = drawing.GraphicsPath()
        _gp_add_polygon(bldg, [
            drawing.PointF(20*s, 40*s), drawing.PointF(20*s, 24*s),
            drawing.PointF(26*s, 24*s), drawing.PointF(26*s, 18*s),
            drawing.PointF(32*s, 18*s), drawing.PointF(32*s, 12*s),
            drawing.PointF(40*s, 12*s), drawing.PointF(40*s, 18*s),
            drawing.PointF(44*s, 18*s), drawing.PointF(44*s, 40*s)])
        g.FillPath(_icon_brush(BH_RED, 20), bldg)
        g.DrawPath(_icon_pen(BH_WHITE, 1.2), bldg)
        # Floor lines
        g.DrawLine(pen_thin, int(20*s), int(32*s), int(44*s), int(32*s))
        g.DrawLine(pen_thin, int(26*s), int(24*s), int(40*s), int(24*s))
        # Window openings
        for (wx,wy) in [(22,26),(30,26),(22,34),(34,34),(42,34),(34,20),(40,14)]:
            g.FillRectangle(_icon_brush(BH_BLACK), drawing.RectangleF(wx*s, wy*s, 2*s, 3*s))
        # Key (foreground, left side)
        # Key head circle
        g.DrawEllipse(_icon_pen(BH_WHITE, 2), drawing.RectangleF(4*s, 6*s, 12*s, 12*s))
        g.DrawEllipse(_icon_pen(BH_WHITE, 1.2), drawing.RectangleF(7*s, 9*s, 6*s, 6*s))
        # Key shaft
        g.DrawLine(pen_thick, int(14*s), int(16*s), int(24*s), int(26*s))
        # Key teeth
        g.DrawLine(_icon_pen(BH_WHITE, 1.8), int(19*s), int(21*s), int(22*s), int(18*s))
        g.DrawLine(_icon_pen(BH_WHITE, 1.8), int(22*s), int(24*s), int(25*s), int(21*s))
        # Checkmark (bold, bottom-right)
        g.DrawLine(_icon_pen(BH_RED, 3), int(28*s), int(30*s), int(32*s), int(36*s))
        g.DrawLine(_icon_pen(BH_RED, 3), int(32*s), int(36*s), int(42*s), int(22*s))
        # Ground line + hatch
        g.DrawLine(_icon_pen(BH_WHITE, 1.2), int(2*s), int(42*s), int(46*s), int(42*s))
        for hx in range(3, 44, 2):
            g.DrawLine(_icon_pen(BH_WHITE, 0.3), int((hx+1)*s), int(44*s), int(hx*s), int(42*s))
    finally:
        g.Dispose()
    return bmp


class BuildingCompleteDialog(forms.Dialog[bool]):
    """Full-screen congratulation dialog shown after all generation phases are done."""
    def __init__(self, Building):
        super(BuildingCompleteDialog, self).__init__()
        self.BackgroundColor = make_color(*BH_BLACK)
        self.Title = "BUILDING GENERATION COMPLETE"
        self.Padding = drawing.Padding(0)
        self.Resizable = False
        self.MinimumSize = drawing.Size(600, 520)

        HEADER_COLOR = BH_BLACK     # black header
        SEP_COLOR    = BH_RED       # dark red separator
        ACCENT       = BH_RED       # dark red accent text

        # ── Header ───────────────────────────────────────────────────────────
        hp = forms.Panel()
        hp.BackgroundColor = make_color(*HEADER_COLOR)
        hp.Padding = drawing.Padding(20, 16, 20, 16)

        iv = forms.ImageView()
        iv.Image = _icon_variant_complete(48)
        iv.Size = drawing.Size(48, 48)

        title_lbl = forms.Label()
        title_lbl.Text = "  BUILDING COMPLETE  //  ALL PHASES DONE"
        title_lbl.Font = drawing.Font(drawing.FontFamily("Impact"), 16, drawing.FontStyle.Bold)
        title_lbl.TextColor = make_color(*BH_WHITE)

        hl = forms.TableLayout()
        hl.Spacing = drawing.Size(12, 0)
        hr = forms.TableRow()
        hr.Cells.Add(forms.TableCell(iv, False))
        hr.Cells.Add(forms.TableCell(title_lbl, True))
        hl.Rows.Add(hr)
        hp.Content = hl

        # ── Body ─────────────────────────────────────────────────────────────
        bp = forms.Panel()
        bp.BackgroundColor = make_color(*DIALOG_SURFACE_DEEP)
        bp.Padding = drawing.Padding(28, 22, 28, 22)

        # Gather stats
        num_upper = Building["floors"].get("num_upper_floors", 0)
        total_h   = Building["floors"].get("total_height", 0.0)
        tp  = sum(len(p) for p in Building["panels"]["panel_ids_per_floor"])
        tw  = sum(len(w) for w in Building["wall_panels"]["wall_panel_ids_per_floor"])
        we  = len(Building["elevation"]["wall_extrusion_ids"])
        ve  = len(Building["elevation"]["vertical_extrusion_ids"])
        ts, tg = 0, 0
        if "facade_subdivision" in Building:
            ts = sum(Building["facade_subdivision"]["sub_panel_ids_per_elevation"].values())
            tg = sum(Building["facade_subdivision"]["glass_panel_ids_per_elevation"].values())

        congrats_lbl = forms.Label()
        congrats_lbl.Text = "CONGRATULATIONS, ARCHITECT!"
        congrats_lbl.Font = drawing.Font(drawing.FontFamily("Impact"), 16, drawing.FontStyle.Bold)
        congrats_lbl.TextColor = make_color(*ACCENT)
        congrats_lbl.TextAlignment = forms.TextAlignment.Center

        sep1 = _make_scifi_sep(SEP_COLOR)

        stats_text = "\n".join([
            "  STRUCTURE",
            "  Basement floor     :  1",
            "  Upper floors       :  {}".format(num_upper),
            "  Roof level         :  1",
            "  Total height       :  {:.2f} m".format(total_h),
            "",
            "  SURFACES",
            "  Floor panels       :  {}".format(tp),
            "  Wall panels        :  {}".format(tw),
            "  Wall extrusions    :  {}".format(we),
            "  Vertical extrusions:  {}".format(ve),
            "",
            "  FACADE",
            "  Subdivisions       :  {}".format(ts),
            "  Glass panels       :  {}".format(tg),
            "",
            "  >> YOUR BUILDING IS READY. GOOD LUCK! <<"
        ])

        stats_lbl = _make_scifi_label(stats_text, size=11)

        sep2 = _make_scifi_sep(BH_RED)

        ok_btn = _make_scifi_button("  FINISH  ", BH_RED, w=260, h=48)
        ok_btn.Click += self.on_ok

        bl = forms.TableLayout()
        bl.Spacing = drawing.Size(0, 14)
        bl.Rows.Add(forms.TableRow(forms.TableCell(congrats_lbl, True)))
        bl.Rows.Add(forms.TableRow(forms.TableCell(sep1, True)))
        bl.Rows.Add(forms.TableRow(forms.TableCell(stats_lbl, True)))
        bl.Rows.Add(forms.TableRow(forms.TableCell(sep2, True)))
        bl.Rows.Add(forms.TableRow(forms.TableCell(ok_btn, True)))
        bp.Content = bl

        ml = forms.TableLayout()
        ml.Spacing = drawing.Size(0, 0)
        ml.Rows.Add(forms.TableRow(forms.TableCell(hp, True)))
        ml.Rows.Add(forms.TableRow(forms.TableCell(bp, True)))
        self.Content = ml

    def on_ok(self, s, e):
        self.Close(True)


class ElevationCompleteDialog(forms.Dialog[bool]):
    """Shown after glass selection is done for one elevation face."""
    def __init__(self, elevation_name, subdiv_count, glass_count, next_elevation=None):
        super(ElevationCompleteDialog, self).__init__()
        self.BackgroundColor = make_color(*BH_BLACK)
        self.Title = "{} ELEVATION COMPLETE".format(elevation_name)
        self.Padding = drawing.Padding(0)
        self.Resizable = False
        self.MinimumSize = drawing.Size(560, 400)

        HEADER_COLOR = BH_BLACK
        SEP_COLOR    = BH_RED

        hp = forms.Panel()
        _make_scifi_header(hp, "{} FACADE  //  COMPLETE".format(elevation_name),
                           HEADER_COLOR, "WALL PANELS")

        bp = forms.Panel()
        bp.BackgroundColor = make_color(*DIALOG_SURFACE_DEEP)
        bp.Padding = drawing.Padding(28, 22, 28, 22)

        next_msg = "NEXT: {} ELEVATION".format(next_elevation) if next_elevation else "ALL ELEVATIONS COMPLETE"
        info = _make_scifi_label(
            "{} FACADE DONE\n\n"
            "  Subdivisions applied : {}\n"
            "  Glass panels assigned: {}\n\n"
            "{}".format(elevation_name, subdiv_count, glass_count, next_msg),
            size=12)

        sep = _make_scifi_sep(SEP_COLOR)

        ok_btn = _make_scifi_button("  CONTINUE  ", BH_RED, w=240, h=44)
        ok_btn.Click += self.on_ok

        bl = forms.TableLayout()
        bl.Spacing = drawing.Size(0, 11)
        bl.Rows.Add(forms.TableRow(forms.TableCell(info, True)))
        bl.Rows.Add(forms.TableRow(forms.TableCell(sep, True)))
        bl.Rows.Add(forms.TableRow(forms.TableCell(ok_btn, True)))
        bp.Content = bl

        ml = forms.TableLayout()
        ml.Spacing = drawing.Size(0, 0)
        ml.Rows.Add(forms.TableRow(forms.TableCell(hp, True)))
        ml.Rows.Add(forms.TableRow(forms.TableCell(bp, True)))
        self.Content = ml

    def on_ok(self, s, e):
        self.Close(True)


# ── Geometry helpers ──────────────────────────────────────────────────────────
def _get_surface_corners(srf_id):
    """Return (x1,y1,z_bot,x2,y2,z_top) for a wall panel surface."""
    try:
        brep = rs.coercebrep(srf_id)
        if brep is None:
            srf = rs.coercesurface(srf_id)
            if srf is None:
                return None
            dom_u = srf.Domain(0)
            dom_v = srf.Domain(1)
            pts = [srf.PointAt(dom_u[0], dom_v[0]),
                   srf.PointAt(dom_u[1], dom_v[0]),
                   srf.PointAt(dom_u[1], dom_v[1]),
                   srf.PointAt(dom_u[0], dom_v[1])]
        else:
            verts = list(brep.Vertices)
            pts = [v.Location for v in verts]
        if not pts:
            return None
        xs = [p.X for p in pts]
        ys = [p.Y for p in pts]
        zs = [p.Z for p in pts]
        return (min(xs), max(xs), min(ys), max(ys), min(zs), max(zs))
    except:
        return None


def _get_wall_panel_bounds(srf_id):
    """Return bounds dict for a wall panel: x_min, x_max, y_min, y_max, z_min, z_max."""
    bb = rs.BoundingBox(srf_id)
    if not bb or len(bb) < 8:
        return None
    xs = [p.X for p in bb]
    ys = [p.Y for p in bb]
    zs = [p.Z for p in bb]
    return {"x_min": min(xs), "x_max": max(xs),
            "y_min": min(ys), "y_max": max(ys),
            "z_min": min(zs), "z_max": max(zs)}


def _panel_faces_direction(srf_id, facing):
    """Return True only if this object is a FLAT wall panel facing the given direction.

    A genuine wall panel is a planar vertical surface with extent in Z and in
    exactly ONE of X or Y.  Arch-extrusion side/end walls and vertical-extrusion
    walls also look like vertical surfaces, but they always have non-trivial
    extent in BOTH X and Y (they form the sides of a 3-D arch volume).
    We reject any surface whose bounding box has significant depth in both
    horizontal directions — that immediately catches all extrusion geometry.
    """
    bb = _get_wall_panel_bounds(srf_id)
    if not bb:
        return False

    dx = bb["x_max"] - bb["x_min"]
    dy = bb["y_max"] - bb["y_min"]
    dz = bb["z_max"] - bb["z_min"]

    FLAT = 0.02   # a genuine wall panel has one XY dim collapsing to near zero
    MIN  = 0.05   # must have meaningful extent in the other dim

    # Must have vertical extent (it is a wall, not a floor/roof slab)
    if dz < MIN:
        return False

    # Reject anything with significant depth in BOTH X and Y:
    # that geometry belongs to arch extrusions, not wall panels.
    if dx > FLAT and dy > FLAT:
        return False

    is_ew_panel = (dx > MIN) and (dy <= FLAT)   # runs East-West → faces N or S
    is_ns_panel = (dy > MIN) and (dx <= FLAT)   # runs North-South → faces E or W

    if facing in ("north", "south"):
        return is_ew_panel
    if facing in ("east", "west"):
        return is_ns_panel
    return False


def _get_panel_facing_direction(srf_id):
    """Determine which cardinal direction a genuine wall panel faces (ns or ew)."""
    bb = _get_wall_panel_bounds(srf_id)
    if not bb:
        return None
    dx = bb["x_max"] - bb["x_min"]
    dy = bb["y_max"] - bb["y_min"]
    FLAT = 0.02
    MIN  = 0.05
    if dx > MIN and dy <= FLAT:
        return "ns"
    if dy > MIN and dx <= FLAT:
        return "ew"
    return None


# ── Explicit whitelist of genuine wall-panel IDs ──────────────────────────────
def _build_wall_panel_whitelist(Building):
    """Return a frozenset of every object ID that is a GENUINE wall panel.

    An ID qualifies only when ALL five conditions hold simultaneously:
      1. Present in Building["wall_panels"]["wall_panel_ids_per_floor"]
         (surviving after user-deletion; panels consumed by extrusion have
          already been removed from these lists by the extrusion step)
      2. Still alive in Rhino (rs.IsObject is True)
      3. Lives on a layer whose name starts with "Wall_Panels_"
         (not "Wall_Extrusions", "Vertical_Extrusions", "Glass_Panels", …)
      4. NOT listed in Building["elevation"]["wall_extrusion_ids"]
      5. NOT listed in Building["elevation"]["vertical_extrusion_ids"]

    This whitelist is rebuilt fresh each iteration so that panels removed by
    previous subdivision operations are automatically excluded.
    """
    # Fast exclusion sets from Building elevation data
    wall_ext_ids  = set()
    for xid in Building["elevation"].get("wall_extrusion_ids", []):
        wall_ext_ids.add(xid)
        wall_ext_ids.add(str(xid))

    vert_ext_ids  = set()
    for xid in Building["elevation"].get("vertical_extrusion_ids", []):
        vert_ext_ids.add(xid)
        vert_ext_ids.add(str(xid))

    whitelist = set()
    for fi in range(len(Building["wall_panels"]["wall_panel_ids_per_floor"])):
        for pid in Building["wall_panels"]["wall_panel_ids_per_floor"][fi]:
            # 1 — must still exist in Rhino
            if not rs.IsObject(pid):
                continue
            # 2 — must live on a Wall_Panels_N layer
            try:
                lyr = rs.ObjectLayer(pid)
                if not (lyr and lyr.startswith("Wall_Panels_")):
                    continue
            except Exception:
                continue
            # 3 — must not be a wall-arch extrusion surface
            if pid in wall_ext_ids or str(pid) in wall_ext_ids:
                continue
            # 4 — must not be a vertical-arch extrusion surface
            if pid in vert_ext_ids or str(pid) in vert_ext_ids:
                continue
            whitelist.add(pid)

    return frozenset(whitelist)


def _classify_user_selection(raw_selection, whitelist, elev_facing):
    """Split a raw GetObjects result into accepted/rejected buckets.

    Returns:
        accepted  — list of IDs that are genuine wall panels facing this elevation
        rejected  — list of (id, reason_str) for every ignored object

    Rejection reason strings (in priority order):
        "dead"            — object no longer exists in Rhino
        "extrusion"       — on Wall_Extrusions or Vertical_Extrusions layer
        "floor_panel"     — on a Floor_Panels_N layer
        "glass"           — already a glass panel
        "not_wall_panel"  — not in the Building whitelist for any other reason
        "wrong_elevation" — genuine wall panel but faces a different facade
    """
    accepted = []
    rejected = []

    for pid in (raw_selection or []):
        if not rs.IsObject(pid):
            rejected.append((pid, "dead"))
            continue

        # Determine the object's layer for diagnostic messages
        try:
            lyr = rs.ObjectLayer(pid)
        except Exception:
            lyr = ""

        # Check whitelist membership first
        if pid not in whitelist:
            if lyr and ("Wall_Extrusion" in lyr or "Vertical_Extrusion" in lyr):
                reason = "extrusion"
            elif lyr and "Floor_Panels" in lyr:
                reason = "floor_panel"
            elif lyr and "Glass" in lyr:
                reason = "glass"
            else:
                reason = "not_wall_panel"
            rejected.append((pid, reason))
            continue

        # Whitelist member — now check it faces the right elevation
        if not _panel_faces_direction(pid, elev_facing):
            rejected.append((pid, "wrong_elevation"))
            continue

        accepted.append(pid)

    return accepted, rejected


def _get_wall_panels_for_elevation(Building, elevation_facing):
    """Collect all surviving genuine wall panel IDs that face a given elevation.
    Uses the whitelist so extrusion surfaces are never included.
    """
    whitelist = _build_wall_panel_whitelist(Building)
    return [pid for pid in whitelist
            if _panel_faces_direction(pid, elevation_facing)]


def _is_full_height_panel(pid, Building):
    """Return True if a panel is a full-height panel resting on beams/columns.
    Full-height panels have height > parapet_height (1m) and are not parapets.
    We check via wall_panel_info_map stored in Building.
    """
    parapet_h = Building["wall_panels"]["parapet_height"]
    for fi, info_map in enumerate(Building["wall_panels"]["wall_panel_info_per_floor"]):
        ps = str(pid)
        if ps in info_map:
            info = info_map[ps]
            ph = info.get("panel_height", 0)
            return ph > parapet_h + 0.05
    # Fallback: measure height from bounding box
    bb = _get_wall_panel_bounds(pid)
    if not bb:
        return False
    h = bb["z_max"] - bb["z_min"]
    return h > parapet_h + 0.05


def subdivide_wall_panel(pid, direction, count, Building, layer_name):
    """Subdivide a wall panel surface into equal strips.
    direction: 'H' (horizontal / row cuts) or 'V' (vertical / column cuts)
    count: 2 or 3
    Returns list of new surface IDs (original is deleted).
    """
    bb = _get_wall_panel_bounds(pid)
    if bb is None:
        return []

    x_min, x_max = bb["x_min"], bb["x_max"]
    y_min, y_max = bb["y_min"], bb["y_max"]
    z_min, z_max = bb["z_min"], bb["z_max"]

    new_ids = []

    if direction == "H":
        # Horizontal cuts: divide height into `count` equal rows
        dz = (z_max - z_min) / float(count)
        for i in range(count):
            z1 = z_min + i * dz
            z2 = z_min + (i + 1) * dz
            c1 = rg.Point3d(x_min, y_min, z1)
            c2 = rg.Point3d(x_max, y_max, z1)
            c3 = rg.Point3d(x_max, y_max, z2)
            c4 = rg.Point3d(x_min, y_min, z2)
            srf = rg.NurbsSurface.CreateFromCorners(c1, c2, c3, c4)
            if srf:
                new_id = sc.doc.Objects.AddSurface(srf)
                if new_id:
                    rs.ObjectLayer(new_id, layer_name)
                    rs.ObjectColor(new_id, (160, 200, 230))
                    new_ids.append(new_id)

    elif direction == "V":
        # Vertical cuts: divide the panel's span direction into `count` equal columns
        # Determine which direction the panel runs
        dx = x_max - x_min
        dy = y_max - y_min
        TOL = 0.01
        if dx > TOL:
            # Panel runs East-West → split along X
            step = dx / float(count)
            for i in range(count):
                x1 = x_min + i * step
                x2 = x_min + (i + 1) * step
                c1 = rg.Point3d(x1, y_min, z_min)
                c2 = rg.Point3d(x2, y_min, z_min)
                c3 = rg.Point3d(x2, y_min, z_max)
                c4 = rg.Point3d(x1, y_min, z_max)
                srf = rg.NurbsSurface.CreateFromCorners(c1, c2, c3, c4)
                if srf:
                    new_id = sc.doc.Objects.AddSurface(srf)
                    if new_id:
                        rs.ObjectLayer(new_id, layer_name)
                        rs.ObjectColor(new_id, (160, 200, 230))
                        new_ids.append(new_id)
        else:
            # Panel runs North-South → split along Y
            step = dy / float(count)
            for i in range(count):
                y1 = y_min + i * step
                y2 = y_min + (i + 1) * step
                c1 = rg.Point3d(x_min, y1, z_min)
                c2 = rg.Point3d(x_min, y2, z_min)
                c3 = rg.Point3d(x_min, y2, z_max)
                c4 = rg.Point3d(x_min, y1, z_max)
                srf = rg.NurbsSurface.CreateFromCorners(c1, c2, c3, c4)
                if srf:
                    new_id = sc.doc.Objects.AddSurface(srf)
                    if new_id:
                        rs.ObjectLayer(new_id, layer_name)
                        rs.ObjectColor(new_id, (160, 200, 230))
                        new_ids.append(new_id)

    if new_ids:
        # Remove original panel from all Building data structures
        _remove_panel_from_building(pid, Building)
        rs.DeleteObject(pid)
        print("    Panel subdivided into {} parts ({} direction).".format(len(new_ids), direction))

    return new_ids


def _remove_panel_from_building(pid, Building):
    """Remove a panel ID from wall_panel_ids_per_floor and wall_panel_info_per_floor."""
    ps = str(pid)
    for fi in range(len(Building["wall_panels"]["wall_panel_ids_per_floor"])):
        id_list = Building["wall_panels"]["wall_panel_ids_per_floor"][fi]
        if pid in id_list:
            id_list.remove(pid)
        info_map = Building["wall_panels"]["wall_panel_info_per_floor"][fi]
        if ps in info_map:
            del info_map[ps]
        edge_list = Building["wall_panels"]["wall_panel_edges_per_floor"][fi]


def make_glass_surface(pid, Building):
    """Replace a wall sub-panel with a translucent glass surface.
    Puts it on a 'Glass_Panels' layer, bright cyan color.
    Returns new glass surface ID or None.
    """
    GLASS_LAYER = "Glass_Panels"
    if not rs.IsLayer(GLASS_LAYER):
        rs.AddLayer(GLASS_LAYER, (100, 220, 255))

    bb = _get_wall_panel_bounds(pid)
    if bb is None:
        return None

    x_min, x_max = bb["x_min"], bb["x_max"]
    y_min, y_max = bb["y_min"], bb["y_max"]
    z_min, z_max = bb["z_min"], bb["z_max"]

    c1 = rg.Point3d(x_min, y_min, z_min)
    c2 = rg.Point3d(x_max, y_max, z_min)
    c3 = rg.Point3d(x_max, y_max, z_max)
    c4 = rg.Point3d(x_min, y_min, z_max)
    srf = rg.NurbsSurface.CreateFromCorners(c1, c2, c3, c4)
    if srf:
        new_id = sc.doc.Objects.AddSurface(srf)
        if new_id:
            rs.ObjectLayer(new_id, GLASS_LAYER)
            rs.ObjectColor(new_id, (100, 220, 255))
            _remove_panel_from_building(pid, Building)
            rs.DeleteObject(pid)
            return new_id
    return None


# ── Elevation view helpers ────────────────────────────────────────────────────
def _set_elevation_view(direction_info):
    """Rotate model to the appropriate elevation view."""
    cmd = direction_info["view_cmd"]
    rs.Command(cmd, False)
    rs.ZoomExtents()
    rs.Redraw()
    import time as _time
    _time.sleep(0.4)


def _get_layer_for_panel(pid, Building):
    """Return the layer name of the first floor layer that contains this panel."""
    for fi, id_list in enumerate(Building["wall_panels"]["wall_panel_ids_per_floor"]):
        if pid in id_list:
            return "Wall_Panels_{}".format(fi)
    return "Wall_Panels_0"


# ── Per-elevation subdivision and glazing process ─────────────────────────────
def _process_elevation_subdivision(Building, elev_info):
    """Fully automated subdivision + glazing + framing for one elevation.

    Steps (all automatic — no user interaction needed):
      1. Collect all full-height wall panels facing this elevation.
      2. Subdivide each one VERTICALLY into 3 equal columns.
      3. Apply a pseudo-random glass pattern:
           - Each panel gets 1 or 2 of its 3 sub-columns glazed.
           - Pattern varies by column index to create visual rhythm.
           - Target 40-50% glazing ratio (above German GEG minimum).
      4. Place a Schuco AWS 75 BS.SI aluminium window frame on every
         glass sub-panel, inset 40 mm from all edges.

    Returns (total_sub_panels_created, total_glass_panels_created).
    """
    import random as _random

    elev_name   = elev_info["name"]
    elev_facing = elev_info["facing"]

    _set_elevation_view(elev_info)
    sc.doc.Views.Redraw()

    facade_panels = _get_wall_panels_for_elevation(Building, elev_facing)

    print_section_header("FACADE SUBDIVISION  //  {} ELEVATION".format(elev_name))
    print("  {} genuine wall panels face the {} elevation.".format(
        len(facade_panels), elev_name))

    if not facade_panels:
        print("  No panels to process on {} elevation.".format(elev_name))
        print_section_footer()
        return 0, 0

    # ── Phase 1: Auto-subdivide all full-height panels — V / 3 ───────────────
    all_sub_panel_ids = []   # all child sub-panels created this pass
    total_subdiv_ops  = 0

    # Use a seeded RNG so the pattern is reproducible per session but varies
    # per elevation (seed uses elevation name hash + panel count)
    seed_val = sum(ord(c) for c in elev_name) + len(facade_panels)
    rng = _random.Random(seed_val)

    # Sort panels spatially so the pattern is consistent regardless of
    # the order objects were added to the document
    def _panel_sort_key(pid):
        bb = _get_wall_panel_bounds(pid)
        if bb is None:
            return (0.0, 0.0)
        cx = (bb["x_min"] + bb["x_max"]) / 2.0
        cy = (bb["y_min"] + bb["y_max"]) / 2.0
        return (round(cx, 2), round(cy, 2))

    sorted_panels = sorted(facade_panels, key=_panel_sort_key)

    whitelist = _build_wall_panel_whitelist(Building)

    for col_idx, pid in enumerate(sorted_panels):
        if not rs.IsObject(pid):
            continue
        if pid not in whitelist:
            continue
        if not _is_full_height_panel(pid, Building):
            print("    Skipping parapet/transition panel {}.".format(pid))
            continue

        panel_layer = _get_layer_for_panel(pid, Building)
        new_ids = subdivide_wall_panel(pid, "V", 3, Building, panel_layer)
        all_sub_panel_ids.extend(new_ids)
        total_subdiv_ops += len(new_ids)

    sc.doc.Views.Redraw()
    print("  Phase 1 complete: {} sub-panels created on {} elevation.".format(
        total_subdiv_ops, elev_name))

    # ── Phase 2: Auto glass assignment — rhythmic pattern ────────────────────
    # Glass eligibility: must be full-height sub-panel from this pass
    eligible_sub_panels = [
        p for p in all_sub_panel_ids
        if rs.IsObject(p) and _is_full_height_panel(p, Building)
    ]

    total_glass = 0
    glass_ids   = []

    if not eligible_sub_panels:
        print("  No eligible sub-panels for glazing on {} elevation.".format(elev_name))
    else:
        # Group sub-panels into sets of 3 (each original panel -> 3 columns)
        # sorted spatially so groups are predictable
        def _sub_sort_key(pid):
            bb = _get_wall_panel_bounds(pid)
            if bb is None:
                return (0.0, 0.0, 0.0)
            cx = (bb["x_min"] + bb["x_max"]) / 2.0
            cy = (bb["y_min"] + bb["y_max"]) / 2.0
            cz = (bb["z_min"] + bb["z_max"]) / 2.0
            return (round(cz, 2), round(cx, 2), round(cy, 2))

        sorted_subs = sorted(eligible_sub_panels, key=_sub_sort_key)

        # Group into triplets (floor by floor, panel by panel)
        groups = []
        i = 0
        while i < len(sorted_subs):
            groups.append(sorted_subs[i:i + 3])
            i += 3

        # Glass pattern rules (per group / original panel):
        #   col_idx 0  -> glass sub-columns [0, 2]      (left + right)
        #   col_idx 1  -> glass sub-columns [1]          (centre only)
        #   col_idx 2  -> glass sub-columns [0, 1]       (left + centre)
        #   col_idx 3  -> glass sub-columns [1, 2]       (centre + right)
        # This creates a shifting, non-repetitive pattern while keeping
        # 33-67% of each panel glazed (average ~50%).
        GLASS_PATTERNS = [
            [0, 2],   # left + right
            [1],      # centre only
            [0, 1],   # left + centre
            [1, 2],   # centre + right
            [0],      # left only
            [2],      # right only
            [0, 1],   # left + centre
            [1, 2],   # centre + right
        ]

        for grp_idx, group in enumerate(groups):
            pattern = GLASS_PATTERNS[grp_idx % len(GLASS_PATTERNS)]
            for sub_col, pid in enumerate(group):
                if sub_col in pattern:
                    new_glass = make_glass_surface(pid, Building)
                    if new_glass:
                        glass_ids.append(new_glass)
                        total_glass += 1

        sc.doc.Views.Redraw()
        print("  Phase 2 complete: {} glass panels on {} elevation.".format(
            total_glass, elev_name))

        # Glass ratio reporting
        if total_subdiv_ops > 0:
            ratio = (float(total_glass) / float(total_subdiv_ops)) * 100.0
            print("  Glazing ratio: {:.1f}% of sub-panels glazed (GEG target: >=30%).".format(ratio))


    print_section_footer()
    return total_subdiv_ops, total_glass


def _add_frame_strip(x1, y1, z1, x2, y2, z2, layer, color):
    """Create a flat rectangular surface representing one frame member.
    The strip is degenerate in the panel-normal direction (zero thickness).
    Returns new object ID or None.
    """
    # Determine which dimension is the 'height' (Z), which is the 'width'
    # Build a planar quad from the two corners plus implied perpendicular
    try:
        c1 = rg.Point3d(x1, y1, z1)
        c2 = rg.Point3d(x2, y2, z1)
        c3 = rg.Point3d(x2, y2, z2)
        c4 = rg.Point3d(x1, y1, z2)
        srf = rg.NurbsSurface.CreateFromCorners(c1, c2, c3, c4)
        if srf:
            new_id = sc.doc.Objects.AddSurface(srf)
            if new_id:
                rs.ObjectLayer(new_id, layer)
                rs.ObjectColor(new_id, color)
                return new_id
    except Exception as e:
        print("    Frame strip error: {}".format(e))
    return None


# ── Master process: all 4 elevations ─────────────────────────────────────────
def process_facade_subdivision(Building):
    """FACADE STEP: Subdivide wall panels + assign glass + place frames for all 4 elevations.

    Shows ONE combined FacadeSubdivisionDialog then runs all elevations automatically:
      - Auto-subdivide every full-height panel VERTICALLY x3
      - Auto-assign glass using rhythmic pattern (40-50% glazing, above GEG min)
      - Auto-place Schuco AWS 75 BS.SI aluminium frames on all glass panels
    """
    print_section_header("FACADE SUBDIVISION & GLAZING PHASE")

    if "facade_subdivision" not in Building:
        Building["facade_subdivision"] = {
            "sub_panel_ids_per_elevation": {},
            "glass_panel_ids_per_elevation": {},
        }

    # Collect panel counts for the combined dialog
    panel_counts = {}
    for elev_info in ELEVATION_DIRECTIONS:
        fp = _get_wall_panels_for_elevation(Building, elev_info["facing"])
        panel_counts[elev_info["name"]] = len(fp)

    # Single combined dialog - shown ONCE for all 4 elevations
    facade_dlg = FacadeSubdivisionDialog(panel_counts)
    facade_dlg.ShowModal(Rhino.UI.RhinoEtoApp.MainWindow)

    if facade_dlg.user_choice == "cancel":
        print("  Facade subdivision aborted by user.")
        print_section_footer()
        return

    if facade_dlg.user_choice == "skip":
        print("  Facade subdivision skipped by user.")
        print_section_footer()
        return

    EXTRUSION_LAYERS = ["Wall_Extrusions", "Vertical_Extrusions"]
    for lyr in EXTRUSION_LAYERS:
        if rs.IsLayer(lyr):
            try:
                rs.LayerVisible(lyr, False)
            except Exception:
                pass
    print("  Elevation extrusion layers hidden for subdivision clarity.")

    rs.Command("_-SetView _World _Perspective", False)
    rs.ZoomExtents()
    rs.Redraw()

    total_subdiv = 0
    total_glass  = 0

    for idx, elev_info in enumerate(ELEVATION_DIRECTIONS):
        elev_name = elev_info["name"]

        subdiv_count, glass_count = _process_elevation_subdivision(Building, elev_info)

        Building["facade_subdivision"]["sub_panel_ids_per_elevation"][elev_name] = subdiv_count
        Building["facade_subdivision"]["glass_panel_ids_per_elevation"][elev_name] = glass_count

        total_subdiv += subdiv_count
        total_glass  += glass_count
        # No per-elevation popup - all run automatically

    for lyr in EXTRUSION_LAYERS:
        if rs.IsLayer(lyr):
            try:
                rs.LayerVisible(lyr, True)
            except Exception:
                pass
    print("  Elevation extrusion layers restored.")

    # ── Intermediate view reset after facade phase ──────────────────────────────
    # Briefly restore perspective so the user can see progress between phases.
    # (The definitive alignment to XY=ground happens at the very end of main().)
    rs.Command("_-SetView _World _Perspective", False)
    rs.ZoomExtents()
    rs.Redraw()

    print_section_header("FACADE SUBDIVISION COMPLETE")
    print("  Total subdivisions : {}".format(total_subdiv))
    print("  Total glass panels : {}".format(total_glass))
    for elev_info in ELEVATION_DIRECTIONS:
        en = elev_info["name"]
        sv = Building["facade_subdivision"]["sub_panel_ids_per_elevation"].get(en, 0)
        gc = Building["facade_subdivision"]["glass_panel_ids_per_elevation"].get(en, 0)
        print("  {}:  {} subdivisions,  {} glass panels".format(en, sv, gc))
    print_section_footer()


# ============================================================ PHASE 2: FEM GEOMETRY EXPORT FOR DLUBAL RFEM ============================================================
#
# Extracts the structural skeleton from the parametric Building model and
# creates clean Rhino objects on dedicated FEM_ layers.
# The resulting geometry can be exported as DXF and imported directly into
# Dlubal RFEM for structural analysis (Eurocode 5 timber frame).
#
# LAYERS PRODUCED
#   FEM_Columns        — one vertical line per column         (cyan)
#   FEM_Beams          — one horizontal line per beam segment  (yellow)
#   FEM_Floor_Surfaces — flat quad per floor panel cell        (orange)
#   FEM_Roof_Surfaces  — flat quad per roof panel cell         (red)
#   FEM_Wall_Surfaces  — flat quad per outer wall panel        (light blue)
#   FEM_Supports       — point at each column base Z=0         (green)
#
# OBJECT NAMES (used as cross-section tags in RFEM)
#   Columns : "COL_w{mm}x{mm}"     e.g. "COL_w140x140"
#   Beams   : "BEAM_w{mm}x{mm}"    e.g. "BEAM_w120x200"
#   Supports: "SUPPORT_PINNED"
#   Panels  : "FLOOR_PANEL" / "ROOF_PANEL" / "WALL_PANEL"
# ============================================================


def _fem_get_column_bottom_z(Building, floor_index):
    """Return the bottom Z of columns on floor_index.

    Floor 0 columns start at Z=0 (plinth base / ground level).
    Upper floor columns must start exactly AT the beam level of the
    floor below — NOT above it.  Using beam_z + beam_depth was wrong:
    it placed the column bottom 0.5 m above the beam, creating a
    structural gap that disconnects the frame in RFEM.

    Correct logic:
        fi == 0  ->  Z = 0.0
        fi  > 0  ->  Z = top_points_per_floor[fi-1][0][2]  (beam level)
    """
    if floor_index == 0:
        return 0.0
    prev_tops = Building["structure"]["columns"]["top_points_per_floor"][floor_index - 1]
    if not prev_tops:
        return 0.0
    # Return beam_z directly — do NOT add beam_depth
    return prev_tops[0][2]


def _fem_reconstruct_beam_segments(points_3d, tol=0.005):
    """Reconstruct individual beam segments from a flat list of junction points.

    A segment exists between two adjacent points P1 and P2 when:
      1. They share the same X or the same Y (within tol)
      2. No other junction point lies between them along that axis
      3. The distance between them does not exceed max_span (grid_spacing × 1.05)
         — this rejects false double-spans across missing columns in stepped plans

    Returns a list of ((x1,y1,z1), (x2,y2,z2)) tuples.
    """
    segments = []
    if not points_3d:
        return segments

    pts = [(round(p[0], 4), round(p[1], 4), round(p[2], 4)) for p in points_3d]

    # Derive max allowed span from point spacing (grid spacing)
    # Collect all unique X and Y coords; minimum gap between adjacent ones = grid_spacing
    all_x = sorted(set(p[0] for p in pts))
    all_y = sorted(set(p[1] for p in pts))
    x_gaps = [all_x[i+1]-all_x[i] for i in range(len(all_x)-1)] if len(all_x)>1 else [5.0]
    y_gaps = [all_y[i+1]-all_y[i] for i in range(len(all_y)-1)] if len(all_y)>1 else [5.0]
    all_gaps = x_gaps + y_gaps
    # Grid spacing = most common gap (modal gap)
    from collections import Counter
    gap_counts = Counter(round(g, 2) for g in all_gaps if g > 0.5)
    gs = gap_counts.most_common(1)[0][0] if gap_counts else 5.0
    max_span = gs * 1.05   # allow 5% tolerance, reject anything longer

    # ── X-direction beams: group by Y, varying X ─────────────────────────────
    y_groups = {}
    for (x, y, z) in pts:
        yr = round(y, 4)
        y_groups.setdefault(yr, []).append((x, y, z))

    for yr, group in y_groups.items():
        group.sort(key=lambda p: p[0])
        for i in range(len(group) - 1):
            x1, y1, z1 = group[i]
            x2, y2, z2 = group[i + 1]
            span = abs(x2 - x1)
            if span > max_span + tol:
                continue   # skip: column missing between these two, would be double-span
            no_middle = not any(
                x1 + tol < px < x2 - tol and abs(py - yr) < tol
                for (px, py, pz) in group
            )
            if no_middle:
                segments.append(((x1, y1, z1), (x2, y2, z2)))

    # ── Y-direction beams: group by X, varying Y ─────────────────────────────
    x_groups = {}
    for (x, y, z) in pts:
        xr = round(x, 4)
        x_groups.setdefault(xr, []).append((x, y, z))

    for xr, group in x_groups.items():
        group.sort(key=lambda p: p[1])
        for i in range(len(group) - 1):
            x1, y1, z1 = group[i]
            x2, y2, z2 = group[i + 1]
            span = abs(y2 - y1)
            if span > max_span + tol:
                continue   # skip: double-span across a step gap
            no_middle = not any(
                y1 + tol < py < y2 - tol and abs(px - xr) < tol
                for (px, py, pz) in group
            )
            if no_middle:
                segments.append(((x1, y1, z1), (x2, y2, z2)))

    return segments


def _fem_add_layers():
    """Create all FEM_ layers if they do not already exist."""
    layer_defs = [
        ("FEM_Columns",        (0,   220, 255)),
        ("FEM_Beams",          (255, 220,   0)),
        ("FEM_Floor_Surfaces", (255, 160,  60)),
        ("FEM_Roof_Surfaces",  (220,  60,  60)),
        ("FEM_Wall_Surfaces",  (160, 210, 255)),
        ("FEM_Supports",       (0,   255, 100)),
        ("FEM_Purlins",        (255, 160,  40)),   # orange — secondary beams
    ]
    for name, color in layer_defs:
        if not rs.IsLayer(name):
            rs.AddLayer(name, color)


# ── FEM Text Labels ──────────────────────────────────────────────────────────
def export_fem_text_labels(Building):
    """Add visible text annotations to the FEM model in the Rhino viewport.

    Creates text dot objects on a dedicated FEM_Labels layer showing:
      - Floor level Z heights (e.g. 'FL1  Z=1.00m')
      - Column cross-section name at each column base
      - Beam span at each floor level
      - Parapet height at roof level
      - Total building height annotation

    Text dots render as floating labels in all Rhino viewports and are
    exported into the DXF so they appear as text in RFEM as well.
    """
    LABEL_LAYER = "FEM_Labels"
    if not rs.IsLayer(LABEL_LAYER):
        rs.AddLayer(LABEL_LAYER, (255, 255, 255))

    col_w  = Building["structure"]["columns"]["width"]
    bm_w   = Building["structure"]["plinth_beams"]["width"]
    bm_d   = Building["structure"]["plinth_beams"]["depth"]
    gs     = Building["grid"]["spacing"]
    parapet_h = Building["wall_panels"]["parapet_height"]

    nf = len(Building["structure"]["columns"]["top_points_per_floor"])

    # Find the X/Y centroid of the building for label placement
    all_x, all_y = [], []
    for fi in range(nf):
        for (x, y, z) in Building["structure"]["columns"]["top_points_per_floor"][fi]:
            all_x.append(x); all_y.append(y)
    if not all_x:
        return
    cx = sum(all_x) / len(all_x)
    cy = sum(all_y) / len(all_y)
    x_max = max(all_x)

    label_ids = []

    # ── Floor level labels (placed to the right of the building) ─────────
    floor_names = []
    for fi in range(nf):
        tops = Building["structure"]["columns"]["top_points_per_floor"][fi]
        if not tops:
            continue
        beam_z = tops[0][2]

        if fi == 0:
            name = "PLINTH BEAM"
        elif fi == nf - 1:
            name = "ROOF BEAM"
        else:
            name = "FL{}  BEAM".format(fi)

        label_text = "{}  Z={:.2f} m".format(name, beam_z)
        label_pt   = rg.Point3d(x_max + 2.0, cy, beam_z)
        # Text dot: always visible, readable at any zoom
        dot_id = sc.doc.Objects.AddTextDot(label_text, label_pt)
        if dot_id:
            rs.ObjectLayer(dot_id, LABEL_LAYER)
            rs.ObjectColor(dot_id, (255, 255, 255))
            label_ids.append(dot_id)
        floor_names.append((beam_z, label_text))

    # ── Support level label ───────────────────────────────────────────────
    sup_label = "SUPPORTS (PINNED)  Z=0.00 m"
    sup_pt    = rg.Point3d(x_max + 2.0, cy, -0.5)
    sid = sc.doc.Objects.AddTextDot(sup_label, sup_pt)
    if sid:
        rs.ObjectLayer(sid, LABEL_LAYER)
        rs.ObjectColor(sid, (0, 255, 100))
        label_ids.append(sid)

    # ── Parapet label ─────────────────────────────────────────────────────
    if nf > 0:
        roof_tops = Building["structure"]["columns"]["top_points_per_floor"][nf - 1]
        if roof_tops:
            roof_z  = roof_tops[0][2]
            par_z   = roof_z + parapet_h
            par_lbl = "PARAPET  h={:.2f} m  TOP Z={:.2f} m".format(parapet_h, par_z)
            par_pt  = rg.Point3d(x_max + 2.0, cy, par_z)
            pid2 = sc.doc.Objects.AddTextDot(par_lbl, par_pt)
            if pid2:
                rs.ObjectLayer(pid2, LABEL_LAYER)
                rs.ObjectColor(pid2, (200, 230, 255))
                label_ids.append(pid2)

    # ── Total height label ────────────────────────────────────────────────
    tot_h = Building["floors"]["total_height"]
    th_lbl = "TOTAL HEIGHT = {:.2f} m".format(tot_h)
    th_pt  = rg.Point3d(cx, cy, tot_h + 1.0)
    thid = sc.doc.Objects.AddTextDot(th_lbl, th_pt)
    if thid:
        rs.ObjectLayer(thid, LABEL_LAYER)
        rs.ObjectColor(thid, (255, 255, 100))
        label_ids.append(thid)

    # ── Column cross-section label (one per floor level) ──────────────────
    col_name  = "COL  {:.0f}x{:.0f} mm".format(col_w*1000, col_w*1000)
    beam_name = "BEAM  {:.0f}x{:.0f} mm".format(bm_w*1000, bm_d*1000)
    gs_name   = "GRID  {:.0f} m span".format(gs)

    spec_lbl = "{}  |  {}  |  {}".format(col_name, beam_name, gs_name)
    spec_pt  = rg.Point3d(cx, cy, -2.0)
    spec_id  = sc.doc.Objects.AddTextDot(spec_lbl, spec_pt)
    if spec_id:
        rs.ObjectLayer(spec_id, LABEL_LAYER)
        rs.ObjectColor(spec_id, (255, 200, 100))
        label_ids.append(spec_id)

    sc.doc.Views.Redraw()
    print("  Text labels added : {}  -> FEM_Labels".format(len(label_ids)))
    print("  Labels visible in all Rhino viewports and exported to DXF.")
    return label_ids


# ── STEP 1: Column and beam centerlines ──────────────────────────────────────
def export_fem_lines(Building):
    """STEP 1 — Extract column and beam axis lines.

    For every floor level fi:
      • One vertical line per column:
            bottom = _fem_get_column_bottom_z(fi)
            top    = top_points_per_floor[fi][0][2]  (beam level)
      • One horizontal line per beam segment reconstructed from
            intersection_points_per_floor[fi]

    Support points (pinned bases) are placed at Z=0 for every ground-floor column.

    Object names encode the cross-section for RFEM:
        Columns  -> "COL_w{mm}x{mm}"
        Beams    -> "BEAM_w{mm}xd{mm}"
        Supports -> "SUPPORT_PINNED"
    """
    print_section_header("FEM STEP 1 — COLUMN + BEAM CENTERLINES")

    _fem_add_layers()

    # Cross-section dimensions from Building dict (convert m -> mm for name)
    col_w  = Building["structure"]["columns"]["width"]
    bm_w   = Building["structure"]["plinth_beams"]["width"]
    bm_d   = Building["structure"]["plinth_beams"]["depth"]

    col_name  = "COL_w{:.0f}x{:.0f}".format(col_w * 1000, col_w * 1000)
    beam_name = "BEAM_w{:.0f}xd{:.0f}".format(bm_w * 1000, bm_d * 1000)

    nf = len(Building["structure"]["columns"]["top_points_per_floor"])
    n_cols = 0
    n_beams = 0
    n_supports = 0

    for fi in range(nf):
        top_pts = Building["structure"]["columns"]["top_points_per_floor"][fi]
        if not top_pts:
            continue

        col_bot_z = _fem_get_column_bottom_z(Building, fi)
        beam_z    = top_pts[0][2]  # all column tops on this floor = same Z

        # ── Columns ──────────────────────────────────────────────────────────
        for (x, y, z_top) in top_pts:
            pt_bot = rg.Point3d(x, y, col_bot_z)
            pt_top = rg.Point3d(x, y, z_top)
            line_geom = rg.Line(pt_bot, pt_top)
            lid = sc.doc.Objects.AddLine(line_geom)
            if lid:
                rs.ObjectLayer(lid, "FEM_Columns")
                rs.ObjectColor(lid, (0, 220, 255))
                rs.ObjectName(lid, col_name)
                n_cols += 1

        # ── Ground-floor support points (pinned bases at Z=0) ─────────────
        if fi == 0:
            for (x, y, _) in top_pts:
                sup_pt = rg.Point3d(x, y, 0.0)
                sid = sc.doc.Objects.AddPoint(sup_pt)
                if sid:
                    rs.ObjectLayer(sid, "FEM_Supports")
                    rs.ObjectColor(sid, (0, 255, 100))
                    rs.ObjectName(sid, "SUPPORT_PINNED")
                    n_supports += 1

        # ── Beams (column-to-column spans) ───────────────────────────────────
        int_pts_all = Building["structure"]["plinth_beams"]["intersection_points_per_floor"]
        if fi < len(int_pts_all) and int_pts_all[fi]:
            segments = _fem_reconstruct_beam_segments(int_pts_all[fi])
            for (p1, p2) in segments:
                pt1 = rg.Point3d(p1[0], p1[1], p1[2])
                pt2 = rg.Point3d(p2[0], p2[1], p2[2])
                line_geom = rg.Line(pt1, pt2)
                bid = sc.doc.Objects.AddLine(line_geom)
                if bid:
                    rs.ObjectLayer(bid, "FEM_Beams")
                    rs.ObjectColor(bid, (255, 220, 0))
                    rs.ObjectName(bid, beam_name)
                    n_beams += 1

        # ── Cantilever extension beams ────────────────────────────────────────
        # Uses find_continuous_segments() on EACH row so split rows
        # (two separate column groups in the same line with a gap between them)
        # correctly get cantilevers at ALL segment endpoints, not just the
        # absolute first and last point of the row.
        ext_list = Building["structure"]["plinth_beams"].get("extension_per_floor", [])
        ext      = ext_list[fi] if fi < len(ext_list) else 0.0
        max_cant = Building["structure"]["plinth_beams"].get("max_cantilever", 2.0)
        act_ext  = min(ext, max_cant)

        if act_ext > 0.001 and top_pts:
            tol       = 0.01
            cant_name = "BEAM_CANT_w{:.0f}xd{:.0f}".format(bm_w*1000, bm_d*1000)
            gs_fem    = Building["grid"]["spacing"]  # use stored grid spacing directly

            x_coords = sorted(set(round(pt[0], 4) for pt in top_pts))
            y_coords = sorted(set(round(pt[1], 4) for pt in top_pts))

            # ── Y-direction cantilevers: iterate every X column line ──────
            for x in x_coords:
                row_y     = sorted(round(pt[1], 4) for pt in top_pts if abs(pt[0]-x) < tol)
                row_y_set = set(row_y)
                if not row_y:
                    continue
                # Break row into continuous segments (handles split rows / step gaps)
                for ss, se in find_continuous_segments(row_y, gs_fem, tol):
                    # Cant at segment start: no column one step before ss
                    if round(ss - gs_fem, 4) not in row_y_set:
                        bid = sc.doc.Objects.AddLine(
                            rg.Line(rg.Point3d(x, ss, beam_z),
                                    rg.Point3d(x, ss - act_ext, beam_z)))
                        if bid:
                            rs.ObjectLayer(bid, "FEM_Beams")
                            rs.ObjectColor(bid, (255, 180, 0))
                            rs.ObjectName(bid, cant_name)
                            n_beams += 1
                    # Cant at segment end: no column one step after se
                    if round(se + gs_fem, 4) not in row_y_set:
                        bid = sc.doc.Objects.AddLine(
                            rg.Line(rg.Point3d(x, se, beam_z),
                                    rg.Point3d(x, se + act_ext, beam_z)))
                        if bid:
                            rs.ObjectLayer(bid, "FEM_Beams")
                            rs.ObjectColor(bid, (255, 180, 0))
                            rs.ObjectName(bid, cant_name)
                            n_beams += 1

            # ── X-direction cantilevers: iterate every Y column line ──────
            for y in y_coords:
                row_x     = sorted(round(pt[0], 4) for pt in top_pts if abs(pt[1]-y) < tol)
                row_x_set = set(row_x)
                if not row_x:
                    continue
                for ss, se in find_continuous_segments(row_x, gs_fem, tol):
                    if round(ss - gs_fem, 4) not in row_x_set:
                        bid = sc.doc.Objects.AddLine(
                            rg.Line(rg.Point3d(ss, y, beam_z),
                                    rg.Point3d(ss - act_ext, y, beam_z)))
                        if bid:
                            rs.ObjectLayer(bid, "FEM_Beams")
                            rs.ObjectColor(bid, (255, 180, 0))
                            rs.ObjectName(bid, cant_name)
                            n_beams += 1
                    if round(se + gs_fem, 4) not in row_x_set:
                        bid = sc.doc.Objects.AddLine(
                            rg.Line(rg.Point3d(se, y, beam_z),
                                    rg.Point3d(se + act_ext, y, beam_z)))
                        if bid:
                            rs.ObjectLayer(bid, "FEM_Beams")
                            rs.ObjectColor(bid, (255, 180, 0))
                            rs.ObjectName(bid, cant_name)
                            n_beams += 1

    sc.doc.Views.Redraw()
    print("  Columns  : {:3d} lines  -> FEM_Columns   ({})".format(n_cols,  col_name))
    print("  Beams    : {:3d} lines  -> FEM_Beams     ({})".format(n_beams, beam_name))
    print("  Supports : {:3d} points -> FEM_Supports  (SUPPORT_PINNED)".format(n_supports))
    print_section_footer()
    return n_cols, n_beams, n_supports



# ── Purlin FEM export ─────────────────────────────────────────────────────────
def export_fem_purlins(Building):
    """Draw purlin centerlines on FEM_Purlins layer for REFERENCE only.

    IMPORTANT: FEM_Purlins is NOT exported to the DXF for RFEM import.
    Reason: purlin endpoints land at mid-span of primary beams where no
    structural node exists in the beam grid. RFEM would reject them or
    create floating members disconnected from the structure.

    Correct approach: the CLT floor shell (FEM_Floor_Surfaces) distributes
    all floor loads to the primary beams automatically. Purlins are sized
    by hand calculation (already done per EC5) and documented in the paper.

    This function draws them in Rhino for visualisation and documentation.
    Returns total number of purlin lines drawn.
    """
    _fem_add_layers()

    gs       = Building["grid"]["spacing"]
    n_pur    = Building["purlins"].get("n_per_cell", auto_calc_purlin_count(gs))
    b_m, d_m, sec_name = auto_calc_purlin_section(gs, n_pur)
    bay      = gs / float(n_pur + 1)
    n_total  = 0

    nf = len(Building["structure"]["columns"]["top_points_per_floor"])
    for fi in range(nf):
        tops = Building["structure"]["columns"]["top_points_per_floor"][fi]
        if not tops:
            continue
        beam_z = tops[0][2]
        cells  = (Building["panels"]["panels_per_floor"][fi]
                  if fi < len(Building["panels"]["panels_per_floor"]) else [])
        for cell in cells:
            cx, cy = cell["x"], cell["y"]
            for i in range(1, n_pur + 1):
                y_pur = round(cy + i * bay, 4)
                pt1   = rg.Point3d(cx,      y_pur, beam_z)
                pt2   = rg.Point3d(cx + gs, y_pur, beam_z)
                lid   = sc.doc.Objects.AddLine(rg.Line(pt1, pt2))
                if lid:
                    rs.ObjectLayer(lid, "FEM_Purlins")
                    rs.ObjectColor(lid, (255, 160, 40))
                    rs.ObjectName(lid, sec_name)
                    n_total += 1

    sc.doc.Views.Redraw()
    print("  Purlins  : {:3d} lines  -> FEM_Purlins   ({})".format(n_total, sec_name))
    print("    Bay     : {:.2f} m  |  Section: {:.0f}×{:.0f} mm GL24h".format(
          bay, b_m*1000, d_m*1000))
    return n_total


# ── STEPS 2 & 3: Floor, roof and wall panel surfaces ─────────────────────────
def _fem_make_nurbs_quad(p1, p2, p3, p4):
    """Create a planar NURBS surface from 4 corner Point3d objects.

    Vertex order: p1=bottom-left, p2=bottom-right, p3=top-right, p4=top-left.
    Returns a rg.NurbsSurface — a proper NURBS polysurface in Rhino.

    WHY NURBS INSTEAD OF MESH:
        Mesh objects display in Rhino as 'open mesh' which is visually noisy
        and structurally incorrect for FEM representation.
        NURBS surfaces display as clean planar faces with proper edge topology.

    DXF EXPORT NOTE:
        NURBS surfaces export to DXF as SPLINE entities which RFEM 6 ignores.
        The export_fem_dxf() function handles this by creating temporary meshes
        from these NURBS before writing the DXF, which are then post-processed
        from POLYFACE_MESH to 3DFACE — the format RFEM 6 can read.
        The NURBS objects in Rhino are never modified by the export process.
    """
    srf = rg.NurbsSurface.CreateFromCorners(p1, p2, p3, p4)
    return srf


def _trace_floor_boundary(outer_edges, tol=0.001):
    """Chain unordered outer boundary edges into an ordered closed polygon.

    Returns list of (x, y) tuples in order around the perimeter, or []
    if the boundary cannot be closed (degenerate floor plan).
    """
    if not outer_edges:
        return []
    from collections import defaultdict
    adj = defaultdict(list)
    for e in outer_edges:
        p1 = (round(e["x1"], 4), round(e["y1"], 4))
        p2 = (round(e["x2"], 4), round(e["y2"], 4))
        adj[p1].append((p2, id(e)))
        adj[p2].append((p1, id(e)))

    start   = list(adj.keys())[0]
    path    = [start]
    used    = set()
    current = start
    prev    = None

    for _ in range(len(outer_edges) * 2 + 4):
        neighbours = [(pt, eid) for pt, eid in adj[current] if eid not in used]
        if not neighbours:
            break
        # Prefer continuing forward (not back to prev)
        fwd = [(pt, eid) for pt, eid in neighbours if pt != prev]
        if not fwd:
            fwd = neighbours
        nxt, eid = fwd[0]
        used.add(eid)
        if nxt == start:
            break
        path.append(nxt)
        prev    = current
        current = nxt

    return path


def _triangulate_polygon_2d(poly_xy):
    """Fan-triangulate a simple polygon from its centroid.

    Works for any convex or concave polygon without holes (the standard
    L/T/stepped floor plan shapes produced by this building generator).
    Returns list of (i, j, k) index triples into poly_xy.
    """
    if len(poly_xy) < 3:
        return []
    # Compute centroid
    cx = sum(p[0] for p in poly_xy) / len(poly_xy)
    cy = sum(p[1] for p in poly_xy) / len(poly_xy)
    poly_xy = list(poly_xy) + [(cx, cy)]   # centroid = last vertex
    ci = len(poly_xy) - 1                  # centroid index
    tris = []
    n = ci   # number of boundary vertices
    for i in range(n):
        j = (i + 1) % n
        tris.append((i, j, ci))
    return tris


def export_fem_surfaces(Building):
    """STEPS 2 & 3 — Export floor, roof and wall surfaces for RFEM.

    Floor/Roof: one clean planar surface per floor level from outer boundary.
    Traces the outer perimeter of all cell keys for that floor, builds a
    closed polyline, and uses rs.AddPlanarSrf to create one single surface
    with no internal grid lines. Does NOT touch the architectural model.
    Z-CORRECTION: subtract beam_depth to bring slab to beam node level.
    """
    print_section_header("FEM STEPS 2 & 3 — FLOOR / ROOF / WALL SURFACES")
    _fem_add_layers()
    bd      = Building["structure"]["plinth_beams"]["depth"]
    nf      = len(Building["panels"]["panels_per_floor"])
    gs      = Building["grid"]["spacing"]
    n_floor = 0
    n_roof  = 0
    n_wall  = 0

    # ── Floor and roof: one NURBS surface per panel cell ───────────────────────
    # Each cell quad becomes a clean planar NURBS surface.
    # Replacing the previous single welded mesh approach — individual NURBS
    # surfaces display correctly in Rhino and allow per-panel property assignment.
    for fi in range(nf):
        cells = Building["panels"]["panels_per_floor"][fi]
        if not cells:
            continue
        is_roof    = (fi == nf - 1)
        layer_name = "FEM_Roof_Surfaces" if is_roof else "FEM_Floor_Surfaces"
        obj_color  = (220, 60, 60)        if is_roof else (255, 160, 60)
        obj_name   = "ROOF_FL{}".format(fi) if is_roof else "FLOOR_FL{}".format(fi)

        for cell in cells:
            c = cell["corners_3d"]
            z_fem = c[0][2] - bd
            p1 = rg.Point3d(float(c[0][0]), float(c[0][1]), float(z_fem))
            p2 = rg.Point3d(float(c[1][0]), float(c[1][1]), float(z_fem))
            p3 = rg.Point3d(float(c[2][0]), float(c[2][1]), float(z_fem))
            p4 = rg.Point3d(float(c[3][0]), float(c[3][1]), float(z_fem))
            nurbs = _fem_make_nurbs_quad(p1, p2, p3, p4)
            if nurbs:
                mid = sc.doc.Objects.AddSurface(nurbs)
                if mid and str(mid) != '00000000-0000-0000-0000-000000000000':
                    rs.ObjectLayer(mid, layer_name)
                    rs.ObjectColor(mid, obj_color)
                    rs.ObjectName(mid, obj_name)
                    if is_roof: n_roof += 1
                    else:       n_floor += 1

        # IMPORTANT: We do NOT use Rhino wall panel objects here.
    # After facade subdivision original wall pids were replaced by sub-panels

    # and glass surfaces. Bounding boxes of zero-thickness planar surfaces also
    # collapse (Y-extent = 0 for N/S panels), producing degenerate meshes with
    # (0,0,0) phantom vertices. Both previous approaches failed for this reason.
    #
    # CORRECT APPROACH: Use panel_coords_per_floor and the existing
    # get_outer_edges_from_floor_panels() function to find the outer boundary
    # of each floor slab, then build wall quads directly from beam Z levels.
    # No dependency on Rhino object state at all.
    #
    # Wall spans:
    #   Plinth walls : Z = 0.0          -> beam_z[0]
    #   Floor fi     : Z = beam_z[fi]   -> beam_z[fi+1]
    #   Roof parapet : Z = beam_z[-1]   -> beam_z[-1] + parapet_height

    nf_struct = len(Building["structure"]["columns"]["top_points_per_floor"])
    parapet_h = Building["wall_panels"]["parapet_height"]
    gs        = Building["grid"]["spacing"]

    # Collect beam Z level for each structural floor
    beam_z_levels = []
    for fi_s in range(nf_struct):
        tops = Building["structure"]["columns"]["top_points_per_floor"][fi_s]
        if tops:
            beam_z_levels.append(tops[0][2])

    print("  [FEM Walls] beam_z_levels = {}".format(beam_z_levels))
    print("  [FEM Walls] parapet_h     = {:.2f} m".format(parapet_h))
    print("  [FEM Walls] panel_coords floors available = {}".format(len(Building["panels"]["panel_coords_per_floor"])))

    panel_coords = Building["panels"]["panel_coords_per_floor"]

    # ── Plinth/basement walls: Z=0 -> beam_z[0] ──────────────────────────
    if beam_z_levels and panel_coords and panel_coords[0]:
        bz_bot = 0.0
        bz_top = beam_z_levels[0]
        if bz_top - bz_bot > 0.01:   # skip if plinth height is zero or negligible
            outer_edges_0 = get_outer_edges_from_floor_panels(panel_coords[0], gs)
            for edge in outer_edges_0:
                x1,y1,x2,y2 = edge["x1"],edge["y1"],edge["x2"],edge["y2"]
                p1=rg.Point3d(x1,y1,bz_bot); p2=rg.Point3d(x2,y2,bz_bot)
                p3=rg.Point3d(x2,y2,bz_top); p4=rg.Point3d(x1,y1,bz_top)
                nurbs = _fem_make_nurbs_quad(p1,p2,p3,p4)
                if nurbs:
                    mid = sc.doc.Objects.AddSurface(nurbs)
                    if mid and str(mid) != '00000000-0000-0000-0000-000000000000':
                        rs.ObjectLayer(mid,"FEM_Wall_Surfaces")
                        rs.ObjectColor(mid,(160,210,255))
                        rs.ObjectName(mid,"WALL_PLINTH")
                        n_wall += 1

    # ── Per-floor walls — exact same logic as the architectural model ────────
    # Reuses does_floor_above_cover_edge() and get_transition_edges_between_
    # covered_and_uncovered() which are already in the script and correctly
    # implement the three wall type rules:
    #
    #   FULL-HEIGHT wall : outer edge where floor ABOVE exists → height = beam_z[fi+1] - beam_z[fi]
    #   PARAPET wall     : outer edge where NO floor above      → height = parapet_h (1.0 m)
    #   TRANSITION wall  : inner edge at step boundary          → height = full storey height
    #
    # This exactly matches the stepped building logic the user designed.
    for fi_w in range(len(beam_z_levels) - 1):
        bz_bot       = beam_z_levels[fi_w]
        bz_top_full  = beam_z_levels[fi_w + 1]          # full storey top
        storey_h     = bz_top_full - bz_bot
        bz_top_prt   = round(bz_bot + parapet_h, 4)     # parapet top

        print("  [FEM Walls] Floor {:d}: Z={:.2f} -> Z={:.2f} (storey {:.2f}m) parapet->Z={:.2f}".format(
              fi_w, bz_bot, bz_top_full, storey_h, bz_top_prt))

        if fi_w >= len(panel_coords) or not panel_coords[fi_w]:
            continue

        # floor_panels_above: the set of cell keys on the next floor up
        if fi_w + 1 < len(panel_coords):
            panels_above = panel_coords[fi_w + 1]
        else:
            panels_above = []

        # Outer boundary edges of THIS floor
        outer_edges = get_outer_edges_from_floor_panels(panel_coords[fi_w], gs)
        # Transition edges (step boundaries between covered and uncovered cells)
        transition_edges = get_transition_edges_between_covered_and_uncovered(
            panel_coords[fi_w], panels_above, gs)

        n_full = 0; n_prt = 0; n_trans = 0

        for edge in outer_edges:
            covered = does_floor_above_cover_edge(edge, panels_above, gs)
            if covered:
                wall_h = storey_h
                color  = (160, 210, 255)     # cyan  — full-height
                wname  = "WALL_FULL_F{}".format(fi_w)
                n_full += 1
            else:
                wall_h = parapet_h
                color  = (200, 230, 255)     # light blue — parapet
                wname  = "WALL_PARAPET_F{}".format(fi_w)
                n_prt  += 1
            bz_top = round(bz_bot + wall_h, 4)
            x1,y1,x2,y2 = edge["x1"],edge["y1"],edge["x2"],edge["y2"]
            p1=rg.Point3d(x1,y1,bz_bot); p2=rg.Point3d(x2,y2,bz_bot)
            p3=rg.Point3d(x2,y2,bz_top); p4=rg.Point3d(x1,y1,bz_top)
            nurbs = _fem_make_nurbs_quad(p1,p2,p3,p4)
            if nurbs:
                mid = sc.doc.Objects.AddSurface(nurbs)
                if mid and str(mid) != '00000000-0000-0000-0000-000000000000':
                    rs.ObjectLayer(mid,"FEM_Wall_Surfaces")
                    rs.ObjectColor(mid,color)
                    rs.ObjectName(mid,wname)
                    n_wall += 1

        for edge in transition_edges:
            # Transition walls are always full-height (step intersection)
            x1,y1,x2,y2 = edge["x1"],edge["y1"],edge["x2"],edge["y2"]
            p1=rg.Point3d(x1,y1,bz_bot); p2=rg.Point3d(x2,y2,bz_bot)
            p3=rg.Point3d(x2,y2,bz_top_full); p4=rg.Point3d(x1,y1,bz_top_full)
            nurbs = _fem_make_nurbs_quad(p1,p2,p3,p4)
            if nurbs:
                mid = sc.doc.Objects.AddSurface(nurbs)
                if mid and str(mid) != '00000000-0000-0000-0000-000000000000':
                    rs.ObjectLayer(mid,"FEM_Wall_Surfaces")
                    rs.ObjectColor(mid,(120,180,255))   # darker blue — transition
                    rs.ObjectName(mid,"WALL_TRANS_F{}".format(fi_w))
                    n_wall  += 1
                    n_trans += 1

        print("  Floor {:d} walls: {:d} full-height  {:d} parapet({:.1f}m)  {:d} transition".format(
              fi_w, n_full, n_prt, parapet_h, n_trans))

    # ── Roof parapet only — top of building ──────────────────────────────
    # At the roof level itself, ALL edges are parapets (no floor above).
    if beam_z_levels:
        bz_bot = beam_z_levels[-1]
        bz_top = round(bz_bot + parapet_h, 4)
        if bz_top - bz_bot > 0.01:   # skip if parapet height is zero
            roof_pc_fi = len(panel_coords) - 1
            if roof_pc_fi >= 0 and panel_coords[roof_pc_fi]:
                outer_edges_r = get_outer_edges_from_floor_panels(
                    panel_coords[roof_pc_fi], gs)
                for edge in outer_edges_r:
                    x1,y1,x2,y2 = edge["x1"],edge["y1"],edge["x2"],edge["y2"]
                    p1=rg.Point3d(x1,y1,bz_bot); p2=rg.Point3d(x2,y2,bz_bot)
                    p3=rg.Point3d(x2,y2,bz_top); p4=rg.Point3d(x1,y1,bz_top)
                    nurbs = _fem_make_nurbs_quad(p1,p2,p3,p4)
                    if nurbs:
                        mid = sc.doc.Objects.AddSurface(nurbs)
                        if mid and str(mid) != '00000000-0000-0000-0000-000000000000':
                            rs.ObjectLayer(mid,"FEM_Wall_Surfaces")
                            rs.ObjectColor(mid,(200,230,255))
                            rs.ObjectName(mid,"WALL_PARAPET_ROOF")
                            n_wall += 1
            print("  Roof parapet : {:.2f} m  (Z={:.2f} -> Z={:.2f})".format(
                  parapet_h, bz_bot, bz_top))


    sc.doc.Views.Redraw()
    print("  Floor surfaces : {:3d} -> FEM_Floor_Surfaces  (NURBS planar surfaces)".format(n_floor))
    print("  Roof surfaces  : {:3d} -> FEM_Roof_Surfaces   (NURBS planar surfaces)".format(n_roof))
    print("  Wall surfaces  : {:3d} -> FEM_Wall_Surfaces   (POLYFACE MESH)".format(n_wall))
    print("  Surface Z correction applied: -beam_depth ({:.2f} m) on all slabs".format(bd))
    print_section_footer()
    return n_floor, n_roof, n_wall


# ── STEP 4: Section and load case summary ─────────────────────────────────────
def export_fem_section_summary(Building):
    """STEP 4 — Print cross-section dimensions and RFEM load case reference.

    This information must be manually entered into RFEM after DXF import.
    Printed to the Rhino console so the engineer has it immediately.
    """
    print_section_header("FEM STEP 4 — RFEM SETUP REFERENCE")

    col_w  = Building["structure"]["columns"]["width"]
    bm_w   = Building["structure"]["plinth_beams"]["width"]
    bm_d   = Building["structure"]["plinth_beams"]["depth"]
    nf     = len(Building["structure"]["columns"]["top_points_per_floor"])
    tot_h  = Building["floors"]["total_height"]
    gs     = Building["grid"]["spacing"]

    # Gebäudeklasse and fire classification
    tot_h  = Building["floors"]["total_height"]
    gk, fire_min = _gk_fire_minutes(tot_h)
    fire_desc = {0:"none (GK1-3)", 60:"R60 hochfeuerhemmend (GK4)", 90:"R90 feuerbeständig (GK5)"}

    print("  LOCATION & REGULATION  (Bielefeld, NRW)")
    print("    Bauordnung    :  BauO NRW 2018 + MHolzBauRL 2024")
    print("    Building height:  {:.2f} m  ->  Gebäudeklasse GK{}".format(tot_h, gk))
    print("    Fire resistance:  {}".format(fire_desc.get(fire_min, "R{} required".format(fire_min))))
    print("    Max floors GK{} :  {} storeys (timber post-and-beam, NRW)".format(
          gk, {3:3, 4:4, 5:7}.get(gk, 3)))
    print("")
    print("  MATERIAL")
    print("    Timber grade  :  GL24h glulam  (EN 14080 / DIN EN 1995-1-1)")
    print("    E_mean        :  11 600 MPa")
    print("    fm,g,k        :  24.0 MPa (bending)")
    print("    fc,0,g,k      :  24.0 MPa (compression parallel)")
    print("    gamma_M       :  1.25  (KLED medium, service class 1)")
    print("")
    print("  CROSS-SECTIONS  (square sections for aesthetic timber frame)")
    print("    Columns   :  {:.0f} x {:.0f} mm  [COL_w{:.0f}x{:.0f}]  GL24h".format(
        col_w*1000, col_w*1000, col_w*1000, col_w*1000))
    print("    Beams     :  {:.0f} x {:.0f} mm  [BEAM_w{:.0f}xd{:.0f}]  GL24h".format(
        bm_w*1000, bm_w*1000, bm_w*1000, bm_w*1000))
    print("")
    print("  STRUCTURE")
    print("    Floors        :  {}".format(nf))
    print("    Total height  :  {:.2f} m".format(tot_h))
    print("    Grid spacing  :  {:.2f} m".format(gs))
    print("")
    print("  SUPPORTS  (layer FEM_Supports)")
    print("    Type          :  Pinned  (Tx=Ty=Tz=0 / Mx=My=Mz=free)")
    print("")
    # Purlin sizing report
    gs_val = Building["grid"]["spacing"]
    n_p    = auto_calc_purlin_count(gs_val)
    bp, dp, sn = auto_calc_purlin_section(gs_val, n_p)
    bay_p  = gs_val / (n_p + 1)
    print("  SECONDARY BEAMS (PURLINS)  — EC5 / DIN EN 1995-1-1  [hand calc only, not in FEM]")
    print("    Count     :  {} per 5x5 m panel  ({} bays at {:.2f} m)".format(n_p, n_p+1, bay_p))
    print("    Section   :  {:.0f} x {:.0f} mm GL24h  [{}]".format(bp*1000, dp*1000, sn))
    print("    Max deck span between purlins : {:.2f} m".format(bay_p))
    print("    Deck type : CLT 80 mm / Brettsperrholz (typical DE residential)")
    print("    In RFEM   : assign FEM_Purlins as Member type Beam, GL24h")
    print("")
    print("  LOAD CASES FOR RFEM  (define after import)")
    print("    LC1  Self-weight   : automatic  gamma=5.0 kN/m3")
    print("    LC2  Snow          : DIN EN 1991-1-3  Zone 2  sk=0.85 kN/m2 on roof")
    print("    LC3  Wind          : DIN EN 1991-1-4  Zone 2  vb=25 m/s on wall surfaces")
    print("    CO1  ULS           : 1.35*LC1 + 1.5*LC2 + 0.9*LC3")
    print("    CO2  SLS rare      : 1.0*LC1  + 1.0*LC2 + 0.6*LC3")
    print_section_footer()


# ── STEP 5: DXF export ────────────────────────────────────────────────────────
def _convert_polyface_to_3dface(filename):
    """Post-process a DXF file: convert all POLYFACE_MESH entities to 3DFACE.

    WHY THIS IS NEEDED:
        Rhino exports Mesh objects to DXF as AcDbPolyFaceMesh (POLYLINE flag=64).
        RFEM 6 dropped POLYFACE_MESH import support entirely — these entities are
        silently skipped, resulting in zero surfaces imported despite them being
        present in the file.
        RFEM 6 reads 3DFACE entities correctly as shell surface geometry.
        This function rewrites every POLYFACE_MESH in-place to equivalent 3DFACE
        entities so the file imports cleanly without any change to the workflow.

    CONVERSION LOGIC:
        Each POLYFACE_MESH block in DXF consists of:
          - POLYLINE entity  (flag 70=64, stores vertex/face counts)
          - N VERTEX entities  flag 70=192  — geometry points (x,y,z)
          - M VERTEX entities  flag 70=128  — face records (indices 71-74, 1-based)
          - SEQEND
        For each face record, indices 71/72/73/74 reference the geometry vertices.
        Negative indices mean the edge is hidden — take abs() for the coordinate.
        Index 74=0 or 74=73 means triangular face (repeat third point for fourth).
        Each face record becomes one 3DFACE entity on the same layer.

    RESULT:
        101 POLYFACE_MESH blocks  →  101+ 3DFACE entities
        (one 3DFACE per quad face; triangulated floors produce multiple 3DFACEs)
    """
    try:
        # Read as binary first to sanitise any \r\r\n corruption
        # (caused by text-mode writes on Windows adding extra \r)
        with open(filename, 'rb') as f:
            raw_bytes = f.read()
        raw_bytes = raw_bytes.replace(b'\r\r\n', b'\r\n').replace(b'\r\r', b'\r')
        raw = raw_bytes.decode('utf-8', errors='replace')
    except Exception as e:
        print("  [3DFACE] Could not open file: {}".format(e))
        return False

    # Normalise line endings to \n, split into (group_code, value) pairs
    # strip() each element to remove any residual \r from Windows CRLF
    lines = [l.rstrip('\r') for l in raw.replace('\r\n', '\n').replace('\r', '\n').split('\n')]

    # Build list of (code_str, value_str) pairs — pad if odd trailing line
    pairs = []
    i = 0
    while i + 1 < len(lines):
        pairs.append((lines[i], lines[i + 1]))
        i += 2
    if i < len(lines) and lines[i].strip():
        pairs.append((lines[i], ''))

    # ── State machine: pass through all pairs, replace POLYFACE_MESH blocks ──
    output_pairs = []
    idx = 0
    total_polyface = 0
    total_3dface   = 0

    while idx < len(pairs):
        code, val = pairs[idx]

        # Detect start of a POLYFACE_MESH: group code 0, entity type POLYLINE
        if code.strip() == '0' and val.strip() == 'POLYLINE':
            # Scan ahead to collect all pairs up to and including SEQEND
            block = []
            j = idx
            while j < len(pairs):
                block.append(pairs[j])
                if pairs[j][0].strip() == '0' and pairs[j][1].strip() == 'SEQEND':
                    j += 1
                    break
                j += 1
            idx = j  # advance main index past entire block

            # Check flag 70: must be 64 (polyface mesh) to trigger conversion
            poly_flags = 0
            for c, v in block:
                if c.strip() == '70':
                    try:
                        poly_flags = int(v.strip())
                    except ValueError:
                        pass
                    break

            if poly_flags != 64:
                # Not a polyface mesh — pass through unchanged
                output_pairs.extend(block)
                continue

            total_polyface += 1

            # Extract layer name from POLYLINE header (group code 8)
            layer_name = '0'
            for c, v in block:
                if c.strip() == '8':
                    layer_name = v.strip()
                    break

            # Separate geometry vertices (flag=192) from face records (flag=128)
            # Each VERTEX sub-block starts at group code 0 / VERTEX
            geom_verts = []   # list of (x, y, z) floats — 1-indexed below
            face_records = [] # list of [i1, i2, i3, i4] int indices (1-based)

            v_idx = 0
            while v_idx < len(block):
                vc, vv = block[v_idx]
                if vc.strip() == '0' and vv.strip() == 'VERTEX':
                    # Collect this vertex sub-block
                    vblock = []
                    v_idx += 1
                    while v_idx < len(block):
                        nc, nv = block[v_idx]
                        if nc.strip() == '0':
                            break
                        vblock.append((nc, nv))
                        v_idx += 1
                    # Determine vertex type from flag 70
                    vflag = 0
                    for vc2, vv2 in vblock:
                        if vc2.strip() == '70':
                            try:
                                vflag = int(vv2.strip())
                            except ValueError:
                                pass
                            break

                    if vflag == 192:
                        # Geometry vertex — extract x(10), y(20), z(30)
                        vx = vy = vz = 0.0
                        for vc2, vv2 in vblock:
                            c2 = vc2.strip()
                            try:
                                if   c2 == '10': vx = float(vv2.strip())
                                elif c2 == '20': vy = float(vv2.strip())
                                elif c2 == '30': vz = float(vv2.strip())
                            except ValueError:
                                pass
                        geom_verts.append((vx, vy, vz))

                    elif vflag == 128:
                        # Face record — extract indices 71/72/73/74
                        fi = [0, 0, 0, 0]
                        for vc2, vv2 in vblock:
                            c2 = vc2.strip()
                            try:
                                if   c2 == '71': fi[0] = int(vv2.strip())
                                elif c2 == '72': fi[1] = int(vv2.strip())
                                elif c2 == '73': fi[2] = int(vv2.strip())
                                elif c2 == '74': fi[3] = int(vv2.strip())
                            except ValueError:
                                pass
                        face_records.append(fi)
                else:
                    v_idx += 1

            # Build 3DFACE pairs for each face record
            for fi in face_records:
                # abs() strips hidden-edge flag (negative index means hidden edge)
                # index is 1-based into geom_verts list
                def get_pt(raw_idx):
                    real_idx = abs(raw_idx) - 1
                    if 0 <= real_idx < len(geom_verts):
                        return geom_verts[real_idx]
                    return (0.0, 0.0, 0.0)

                p1 = get_pt(fi[0])
                p2 = get_pt(fi[1])
                p3 = get_pt(fi[2])
                # fi[3]==0 means triangular face — repeat p3 for fourth corner
                p4 = get_pt(fi[3]) if fi[3] != 0 else p3

                def fmt(v):
                    return '{:.6g}'.format(v)

                face_pairs = [
                    ('  0', '3DFACE'),
                    ('  8', layer_name),
                    (' 10', fmt(p1[0])), (' 20', fmt(p1[1])), (' 30', fmt(p1[2])),
                    (' 11', fmt(p2[0])), (' 21', fmt(p2[1])), (' 31', fmt(p2[2])),
                    (' 12', fmt(p3[0])), (' 22', fmt(p3[1])), (' 32', fmt(p3[2])),
                    (' 13', fmt(p4[0])), (' 23', fmt(p4[1])), (' 33', fmt(p4[2])),
                ]
                output_pairs.extend(face_pairs)
                total_3dface += 1

        else:
            output_pairs.append((code, val))
            idx += 1

    # Reconstruct file text from pairs
    result_lines = []
    for c, v in output_pairs:
        result_lines.append(c)
        result_lines.append(v)
    new_content = '\r\n'.join(result_lines) + '\r\n'

    try:
        with open(filename, 'w', encoding='utf-8', newline='') as f:
            f.write(new_content)
    except Exception as e:
        print("  [3DFACE] Could not write file: {}".format(e))
        return False

    print("  [3DFACE] Converted {} POLYFACE_MESH  ->  {} 3DFACE entities".format(
        total_polyface, total_3dface))
    return True


def _fix_dxf_units_to_metres(filename):
    """Post-process a DXF file to set $INSUNITS = 6 (Metres).

    Rhino exports DXF with $INSUNITS = 4 (Millimetres) by default, even when
    the model is in metres.  Dlubal RFEM reads this header value and scales
    all coordinates accordingly — causing the entire model to be interpreted
    as millimetres and appearing 1000x too small in RFEM.

    DXF $INSUNITS codes (group code 70):
        0 = Unitless   1 = Inches   2 = Feet
        4 = Millimetres             6 = Metres

    Fix: open the exported DXF, locate the INSUNITS group code block,
    and replace whatever unit value Rhino wrote with 6 (Metres).
    The coordinates themselves are already correct (in metres) because
    Rhino's model space is working in metres.
    """
    import re
    try:
        with open(filename, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()

        # Strategy 1: exact string match (handles both \n and \r\n endings)
        # Rhino writes one of these two forms:
        patched = False
        for old_val in ['     0','     1','     2','     4','     5','     7','     8','     9']:
            old_block = '$INSUNITS\n 70\n{}\n'.format(old_val)
            new_block = '$INSUNITS\n 70\n     6\n'
            if old_block in content:
                content = content.replace(old_block, new_block, 1)
                print("  [Units] $INSUNITS patched: {} -> 6 (Metres)".format(old_val.strip()))
                patched = True
                break
            # Also try \r\n variant
            old_block_crlf = '$INSUNITS\r\n 70\r\n{}\r\n'.format(old_val)
            new_block_crlf = '$INSUNITS\r\n 70\r\n     6\r\n'
            if old_block_crlf in content:
                content = content.replace(old_block_crlf, new_block_crlf, 1)
                print("  [Units] $INSUNITS patched (CRLF): {} -> 6 (Metres)".format(old_val.strip()))
                patched = True
                break

        # Strategy 2: regex fallback for non-standard whitespace
        if not patched:
            pattern = r'(\$INSUNITS[\r\n]+[ \t]*70[\r\n]+)([ \t]*\d+)([\r\n]+)'
            new_content, n = re.subn(
                pattern,
                lambda m: m.group(1) + '     6' + m.group(3),
                content
            )
            if n > 0:
                content = new_content
                print("  [Units] $INSUNITS patched via regex: -> 6 (Metres)  ({} match)".format(n))
                patched = True

        # Strategy 3: insert $INSUNITS if completely missing
        if not patched:
            if '$INSUNITS' not in content:
                insert = '\r\n  9\r\n$INSUNITS\r\n 70\r\n     6'
                content = content.replace('ENDSEC', insert + '\r\nENDSEC', 1)
                print("  [Units] $INSUNITS not found — inserted Metres (6) into header.")
            else:
                print("  [Units] WARNING: Could not patch $INSUNITS — patch manually.")
                print("  [Units] Open DXF in text editor, find '$INSUNITS', change value to 6.")

        with open(filename, 'w', encoding='utf-8', newline='') as f:
            f.write(content)
        return True

    except Exception as e:
        print("  [Units] WARNING: Could not patch DXF units: {}".format(e))
        print("  [Units] Manually set $INSUNITS = 6 (Metres) before RFEM import.")
        return False


def export_fem_dxf():
    """STEP 5 — Export all FEM layers to a single DXF file for RFEM import.

    Exports ALL FEM layers together in one file.
    Surface layers contain NURBS surfaces in Rhino (clean display).
    Before writing the DXF, temporary meshes are created from the NURBS
    for export purposes only — the NURBS in Rhino are never touched.

    THREE AUTOMATIC STEPS after Rhino export:
        Step A: Temporary meshes created from NURBS (export only, deleted after)
        Step B: $INSUNITS patched mm -> Metres
        Step C: POLYFACE_MESH converted to 3DFACE (RFEM 6 requirement)

    RFEM import path (single file):
        File > Import > DXF/DWG
        Length unit              = Metres
        Generate members         = ON
        Minimize tolerance       = ON
        Import 3D faces          = ON   <- 3DFACE surfaces are in the file
        Use layer identification  = ON
    """
    print_section_header("FEM STEP 5 — DXF EXPORT (ALL ELEMENTS, units: METRES)")

    MEMBER_LAYERS  = ["FEM_Columns", "FEM_Beams", "FEM_Supports", "FEM_Labels"]
    SURFACE_LAYERS = ["FEM_Floor_Surfaces", "FEM_Roof_Surfaces", "FEM_Wall_Surfaces"]

    # ── Collect member/support objects (LINE and POINT — export as-is) ────────
    member_ids = []
    for layer in MEMBER_LAYERS:
        if rs.IsLayer(layer):
            objs = rs.ObjectsByLayer(layer)
            if objs:
                member_ids.extend(objs)
                print("  Layer {:25s} -> {:4d} objects".format(layer, len(objs)))

    # ── Create temporary meshes from NURBS surface objects ────────────────────
    # NURBS surfaces export to DXF as SPLINE which RFEM cannot read.
    # Temporary single-quad meshes are created here for the DXF only.
    # They are deleted immediately after the file is written.
    temp_mesh_ids = []
    for layer in SURFACE_LAYERS:
        if not rs.IsLayer(layer):
            continue
        srf_ids = rs.ObjectsByLayer(layer)
        if not srf_ids:
            continue
        layer_mesh_count = 0
        for sid in srf_ids:
            obj = sc.doc.Objects.Find(sid)
            if obj is None:
                continue
            geom = obj.Geometry
            # Handle both NurbsSurface and Brep (joined surfaces)
            if isinstance(geom, rg.NurbsSurface):
                brep = geom.ToBrep()
            elif isinstance(geom, rg.Brep):
                brep = geom
            else:
                continue
            mp = rg.MeshingParameters(0.0)  # coarse — just need face topology
            mp.SimplePlanes = True
            meshes = rg.Mesh.CreateFromBrep(brep, mp)
            if meshes:
                for m in meshes:
                    new_id = sc.doc.Objects.AddMesh(m)
                    if new_id and str(new_id) != '00000000-0000-0000-0000-000000000000':
                        rs.ObjectLayer(new_id, layer)
                        temp_mesh_ids.append(new_id)
                        layer_mesh_count += 1
        print("  Layer {:25s} -> {:4d} NURBS -> {:4d} temp meshes".format(
              layer, len(srf_ids), layer_mesh_count))

    export_ids = member_ids + temp_mesh_ids

    if not export_ids:
        print("  No FEM geometry found. Run FEM export steps first.")
        if temp_mesh_ids:
            rs.DeleteObjects(temp_mesh_ids)
        print_section_footer()
        return False

    print("  Total objects for DXF: {}".format(len(export_ids)))

    filename = rs.SaveFileName(
        "Export FEM model as DXF (Metres) for Dlubal RFEM",
        "DXF Files (*.dxf)|*.dxf||",
        "",
        "fem_model_rfem",
        "dxf"
    )

    if not filename:
        rs.DeleteObjects(temp_mesh_ids)
        print("  Export cancelled. Temporary meshes removed.")
        print_section_footer()
        return False

    # Export via Rhino command
    rs.UnselectAllObjects()
    rs.SelectObjects(export_ids)
    rs.Command('_-Export "{}" _Enter'.format(filename), False)
    rs.UnselectAllObjects()

    # Delete temporary meshes — NURBS in Rhino remain untouched
    rs.DeleteObjects(temp_mesh_ids)
    print("  Temporary meshes deleted. NURBS surfaces preserved in Rhino.")
    print("  DXF file written: {}".format(filename))

    # Post-process B: fix $INSUNITS header mm -> Metres
    print("  [Post-process B] Patching unit header to Metres ($INSUNITS = 6)...")
    _fix_dxf_units_to_metres(filename)

    # Post-process C: convert POLYFACE_MESH -> 3DFACE
    print("  [Post-process C] Converting POLYFACE_MESH to 3DFACE entities...")
    _convert_polyface_to_3dface(filename)

    print("")
    print("  EXPORT COMPLETE — single file, all elements:")
    print("    Members  : columns + beams (LINE entities)")
    print("    Surfaces : walls + floors + roof (3DFACE entities)")
    print("    Supports : pinned nodes (POINT entities)")
    print("")
    print("  RFEM IMPORT SETTINGS:")
    print("    File > Import > DXF/DWG  ->  select fem_model_rfem.dxf")
    print("    Length unit              =  Metres")
    print("    Generate members         =  ON")
    print("    Minimize tolerance       =  ON")
    print("    Import 3D faces          =  ON")
    print("    Use layer identification =  ON")
    print_section_footer()
    return True


# ── FEM Export confirmation dialog ───────────────────────────────────────────
class FEMExportDialog(forms.Dialog[bool]):
    """Confirmation dialog shown before FEM geometry export.

    Displays a summary of the building structure and the six FEM layers
    that will be created.  User can start export or skip.
    """
    def __init__(self, Building):
        super(FEMExportDialog, self).__init__()
        self.BackgroundColor = make_color(*BH_BLACK)
        self.confirmed = False
        self.Title = "FEM GEOMETRY EXPORT  //  DLUBAL RFEM"
        self.Padding = drawing.Padding(0)
        self.Resizable = False
        self.MinimumSize = drawing.Size(580, 540)

        hp = forms.Panel()
        _make_scifi_header(hp, "FEM EXPORT  //  DLUBAL RFEM", BH_BLACK, "FLOORS")

        bp = forms.Panel()
        bp.BackgroundColor = make_color(*DIALOG_SURFACE_DEEP)
        bp.Padding = drawing.Padding(28, 20, 28, 20)

        # Gather stats for the summary
        nf     = len(Building["structure"]["columns"]["top_points_per_floor"])
        col_w  = Building["structure"]["columns"]["width"]
        bm_w   = Building["structure"]["plinth_beams"]["width"]
        bm_d   = Building["structure"]["plinth_beams"]["depth"]
        tot_h  = Building["floors"]["total_height"]
        tp     = sum(len(p) for p in Building["panels"]["panels_per_floor"])
        tw     = sum(len(w) for w in Building["wall_panels"]["wall_panel_ids_per_floor"])

        info_text = (
            "FEM geometry will be extracted from the parametric model\n"
            "and placed on dedicated RFEM-ready layers.\n\n"
            "STRUCTURE SUMMARY\n"
            "  Floors         :  {}\n"
            "  Total height   :  {:.2f} m\n"
            "  Column section :  {:.0f} x {:.0f} mm\n"
            "  Beam section   :  {:.0f} x {:.0f} mm\n"
            "  Floor panels   :  {}\n"
            "  Wall panels    :  {}\n\n"
            "LAYERS TO BE CREATED\n"
            "  FEM_Columns          — column centerlines\n"
            "  FEM_Beams            — beam centerlines\n"
            "  FEM_Floor_Surfaces   — floor slab surfaces\n"
            "  FEM_Roof_Surfaces    — roof surfaces\n"
            "  FEM_Wall_Surfaces    — wind load surfaces\n"
            "  FEM_Supports         — pinned support points\n\n"
            "A DXF save dialog will open for RFEM import."
        ).format(nf, tot_h,
                 col_w*1000, col_w*1000,
                 bm_w*1000,  bm_d*1000,
                 tp, tw)

        info_lbl = _make_scifi_label(info_text, size=10)
        sep      = _make_scifi_sep(BH_MID_GREY)

        start_btn = _make_scifi_button("  > EXPORT FEM GEOMETRY  ", BH_RED, w=400, h=48)
        start_btn.Click += self.on_start

        skip_btn = _make_scifi_button("  SKIP  ", DIALOG_CANCEL_BG, w=160, h=40, bold=False)
        skip_btn.TextColor = make_color(*DIALOG_CANCEL_TEXT)
        skip_btn.Click += self.on_skip

        bl = forms.TableLayout()
        bl.Spacing = drawing.Size(0, 12)
        bl.Rows.Add(forms.TableRow(forms.TableCell(info_lbl,   True)))
        bl.Rows.Add(forms.TableRow(forms.TableCell(sep,        True)))
        bl.Rows.Add(forms.TableRow(forms.TableCell(start_btn,  True)))
        bl.Rows.Add(forms.TableRow(forms.TableCell(skip_btn,   True)))
        bp.Content = bl

        ml = forms.TableLayout()
        ml.Spacing = drawing.Size(0, 0)
        ml.Rows.Add(forms.TableRow(forms.TableCell(hp, True)))
        ml.Rows.Add(forms.TableRow(forms.TableCell(bp, True)))
        self.Content = ml

    def on_start(self, s, e):
        self.confirmed = True
        self.Close(True)

    def on_skip(self, s, e):
        self.confirmed = False
        self.Close(False)


# ── Master FEM export orchestrator ───────────────────────────────────────────
def process_fem_export(Building):
    """Show FEM dialog then run all 5 export steps in sequence.

    Called at the end of main() after the building is fully generated.
    Steps:
        1 — Column + beam centerlines  (FEM_Columns, FEM_Beams, FEM_Supports)
        2 — Floor + roof surfaces      (FEM_Floor_Surfaces, FEM_Roof_Surfaces)
        3 — Outer wall surfaces        (FEM_Wall_Surfaces)
        4 — RFEM setup summary printed to console
        5 — DXF export dialog
    """
    fem_dlg = FEMExportDialog(Building)
    fem_dlg.ShowModal(Rhino.UI.RhinoEtoApp.MainWindow)

    if not fem_dlg.confirmed:
        print("  FEM export skipped.")
        return

    print_section_header("PHASE 2: FEM GEOMETRY EXPORT — ALL STEPS")

    # Step 1: centerlines (columns, beams, supports)
    n_cols, n_beams, n_sup = export_fem_lines(Building)

    # Step 1b: purlin centerlines (secondary floor beams)
    n_purlins = export_fem_purlins(Building)

    # Steps 2 & 3: surfaces
    n_floor, n_roof, n_wall = export_fem_surfaces(Building)

    # Text labels: floor levels, cross-sections, total height
    print_section_header("FEM TEXT LABELS")
    export_fem_text_labels(Building)

    # Step 4: console summary for RFEM setup
    export_fem_section_summary(Building)

    # Step 5: DXF export
    export_fem_dxf()

    print_section_header("FEM EXPORT COMPLETE")
    print("  Columns   : {}  |  Beams : {}  |  Supports : {}".format(n_cols, n_beams, n_sup))
    print("  Purlins   : {} lines drawn in Rhino (hand-calc only, excluded from DXF)".format(n_purlins))
    print("  Floor srf : {}  |  Roof  : {}  |  Wall srf : {}".format(n_floor, n_roof, n_wall))
    print("  All FEM geometry is on FEM_ layers in Rhino.")
    print("  Import the DXF into Dlubal RFEM to proceed.")
    print_section_footer()


# ============================================================ MAIN ============================================================
def main():
    print_section_header("PARAMETRIC BUILDING GENERATOR")
    # ── Force TOP view before drawing any geometry ────────────────────────────
    # All plot/boundary geometry lives on the XY plane (Z = 0).
    # If the active viewport is Front, Right or Perspective when the script
    # starts, the flat rectangle appears as a vertical line or edge-on shape.
    # Setting World Top first guarantees the plot always looks correct from
    # the very first drawn object, regardless of what the user had open before.
    rs.Command("_-SetView _World _Top", False)
    rs.Redraw()

    # ── PROJECT INTRODUCTION SLIDE ────────────────────────────────────────────
    # Shown before any user input or geometry.  Cancel exits cleanly.
    _intro = ProjectIntroDialog()
    if not _intro.ShowModal(Rhino.UI.RhinoEtoApp.MainWindow):
        print("  [Intro] Cancelled at project introduction.  Script aborted.")
        return None

    clear_plot()
    Building = initialize_building_data()
    if not get_plot_dimensions(Building):
        return None
    draw_outer_plot_boundary(Building)
    if not assign_north_side(Building):
        return None
    if not draw_plot_boundary(Building):
        return None
    if not get_grid_spacing(Building):
        return None
    if not generate_foundation_grid(Building):
        return None
    if not get_column_inputs(Building):
        return None
    if not select_column_points_floor1(Building):
        return None
    if not get_additional_floors(Building):
        return None
    ground_top_points, ground_intersections = process_ground_floor(Building)
    if ground_top_points is None:
        return None
    num_upper_floors = Building["floors"]["num_upper_floors"]
    previous_intersections = ground_intersections
    for floor_num in range(1, num_upper_floors + 1):
        if not previous_intersections:
            break
        floor_top_points, floor_intersections = process_upper_floor(Building, floor_num, previous_intersections)
        if floor_top_points is None:
            return None
        previous_intersections = floor_intersections
    if previous_intersections:
        roof_top_points, roof_intersections = process_roof(Building, previous_intersections)
    # Floor panels phase
    process_all_floor_panels(Building)
    # Wall panels phase
    process_all_wall_panels(Building)
    # ============================================================
    # ELEVATION PHASE
    # ============================================================
    # Step 1: Wall arch extrusion (outward from wall panels)
    process_wall_extrusions(Building)
    # Step 2: Vertical arch extrusion (upward from uncovered floor panels)
    process_vertical_arch_extrusions(Building)
    # ============================================================
    # FACADE PHASE: Wall panel subdivision + glass window assignment
    # ============================================================
    # Cycles through North -> East -> South -> West elevations.
    # For each: subdivide wall panels (H or V, 2 or 3 parts),
    # then assign glass to full-height sub-panels on beams/columns.
    process_facade_subdivision(Building)
    Building["floors"]["total_height"] = sum(Building["floors"]["floor_heights"])

    # ================================================================
    # FINAL STEP: Align CPlane to plot base + set perspective view
    # ================================================================
    # The plot rectangle is always built at Z=0 on the World XY plane
    # with corners at (±pl/2, ±pw/2, 0).  After the elevation/facade
    # phases Rhino may have rotated the active CPlane to Front/Right/
    # Left/Back, making the viewport show the model edge-on.
    #
    # Strategy (no user prompts, fully automatic):
    #   1. Derive the plot's bottom-left corner and axes directly from
    #      Building data — these are guaranteed world-XY values.
    #   2. Build a Plane whose origin = plot bottom-left corner (Z=0),
    #      X-axis = plot length direction, Y-axis = plot width direction,
    #      Z-axis = world Z (pointing up).  This IS the XY plane aligned
    #      to the bottom of the plot.
    #   3. Set that plane as the CPlane on ALL viewports so Rhino
    #      recognises XY == plot base from this moment on.
    #   4. Set the Perspective viewport camera to look DOWN at the plot
    #      from above-and-to-the-side (isometric angle) with Z-up locked.
    # ================================================================
    print("  [Final] Aligning CPlane to plot base (XY = plot bottom)...")
    try:
        pl = Building["plot"]["length"]
        pw = Building["plot"]["width"]

        # Plot bottom-left corner (world coords, always Z=0)
        origin = rg.Point3d(-pl / 2.0, -pw / 2.0, 0.0)
        # X-axis runs along the plot length (world +X)
        x_axis = rg.Vector3d(1.0, 0.0, 0.0)
        # Y-axis runs along the plot width (world +Y)
        y_axis = rg.Vector3d(0.0, 1.0, 0.0)

        # Construct the plane that matches the plot base
        plot_plane = rg.Plane(origin, x_axis, y_axis)

        # Apply this CPlane to every viewport — no command string needed
        for view_obj in sc.doc.Views:
            try:
                view_obj.ActiveViewport.SetConstructionPlane(plot_plane)
            except Exception:
                pass

        print("  CPlane set: origin=({:.2f},{:.2f},0)  X=world+X  Y=world+Y  Z=up".format(
              origin.X, origin.Y))
    except Exception as _ecp:
        print("  [CPlane error] {}".format(_ecp))

    # ── Camera: switch to Perspective and look DOWN at the plot ──────────────
    print("  [Final] Setting perspective camera (looking down at plot)...")
    rs.Command("_-SetView _World _Perspective", False)
    try:
        view = sc.doc.Views.ActiveView
        if view:
            vp = view.ActiveViewport

            # Bounding box of the complete model
            all_ids = [obj.Id for obj in sc.doc.Objects if not obj.IsDeleted]
            bbox = None
            if all_ids:
                bbox = sc.doc.Objects.BoundingBox(all_ids, rg.ActiveSpace.ModelSpace)

            if bbox is not None and bbox.IsValid:
                # Centre of the plot base (Z=0 level)
                cx = (bbox.Min.X + bbox.Max.X) * 0.5
                cy = (bbox.Min.Y + bbox.Max.Y) * 0.5
                # Use the known plot dimensions for a well-scaled offset
                # so the camera is never too close or too far
                model_span = max(pl, pw, bbox.Max.Z - bbox.Min.Z)
                off = model_span * 2.5
                # Camera sits above and to the south-west — clearly looking DOWN
                cam_loc = rg.Point3d(cx + off * 0.55,
                                     cy - off * 0.80,
                                     off * 0.90)      # large Z = camera high above
                target  = rg.Point3d(cx, cy, 0.0)    # aim at plot base centre
            else:
                cam_loc = rg.Point3d(60.0, -90.0, 80.0)
                target  = rg.Point3d(0.0, 0.0, 0.0)

            # Lock Z-up so the horizon stays flat and XY reads as the ground
            vp.SetCameraUp(rg.Vector3d(0.0, 0.0, 1.0), True)
            vp.SetCameraTarget(target, True)
            vp.SetCameraLocation(cam_loc, True)
            print("  Camera: loc=({:.1f},{:.1f},{:.1f})  target=({:.1f},{:.1f},{:.1f})".format(
                  cam_loc.X, cam_loc.Y, cam_loc.Z,
                  target.X,  target.Y,  target.Z))
    except Exception as _ev:
        print("  [Camera error] {}".format(_ev))

    rs.ZoomExtents()
    rs.Redraw()
    print_section_header("GENERATION COMPLETE!")
    print("  Basement: 1")
    if num_upper_floors > 0:
        print("  Upper Floors: {}".format(num_upper_floors))
    print("  Roof: 1")
    print("  Total height: {:.2f} m".format(Building["floors"]["total_height"]))
    print("  Beam depth: {:.2f} m".format(Building["structure"]["plinth_beams"]["depth"]))
    tp = sum(len(p) for p in Building["panels"]["panel_ids_per_floor"])
    td = sum(len(d) for d in Building["panels"]["deleted_panels_per_floor"])
    print("  Floor panels: {} remaining, {} deleted".format(tp, td))
    tw = sum(len(w) for w in Building["wall_panels"]["wall_panel_ids_per_floor"])
    twd = sum(len(d) for d in Building["wall_panels"]["deleted_wall_panels_per_floor"])
    print("  Wall panels: {} remaining, {} deleted".format(tw, twd))
    we = len(Building["elevation"]["wall_extrusion_ids"])
    ve = len(Building["elevation"]["vertical_extrusion_ids"])
    print("  Wall arch extrusion surfaces: {}".format(we))
    print("  Vertical arch surfaces: {}".format(ve))
    if "facade_subdivision" in Building:
        ts = sum(Building["facade_subdivision"]["sub_panel_ids_per_elevation"].values())
        tg = sum(Building["facade_subdivision"]["glass_panel_ids_per_elevation"].values())
        print("  Facade sub-panel subdivisions: {}".format(ts))
        print("  Glass panels assigned: {}".format(tg))
    print_section_footer()

    # ── Show congratulation dialog ────────────────────────────────────────────
    complete_dlg = BuildingCompleteDialog(Building)   
    complete_dlg.ShowModal(Rhino.UI.RhinoEtoApp.MainWindow)

    # ── PHASE 2: FEM Geometry Export ─────────────────────────────────────────
    # Runs after the building is fully generated and the user has seen the
    # completion summary.  Shows a single confirmation dialog then extracts
    # all structural centerlines, panel surfaces and support points onto
    # dedicated FEM_ layers for direct DXF import into Dlubal RFEM.
    process_fem_export(Building)

    return Building


if __name__ == "__main__":
    Building_data = main()


