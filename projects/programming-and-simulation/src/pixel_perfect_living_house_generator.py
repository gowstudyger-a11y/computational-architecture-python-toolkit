# =============================================================================
# ARCH_MODEL_staircase_optionA_v43-1.py
# Parametric Architectural Building Generator — Staircase Option A, v43-1
# =============================================================================
# Institution : TH-OWL (Technische Hochschule Ostwestfalen-Lippe)
# Platform    : McNeel Rhinoceros 8  +  Python 2/3 Script (RhinoScriptSyntax)
# Dependencies: rhinoscriptsyntax, scriptcontext, Rhino.Geometry,
#               Eto.Forms, Eto.Drawing, System.Drawing
#
# PURPOSE
# -------
# Fully parametric 3-D building model generator executed from inside the Rhino
# scripting environment.  The script walks the user through a sequence of
# interactive dialogs and automatically constructs:
#   • Site / plot boundary and road geometry
#   • Structural grid, columns and plinth beams (timber / CLT)
#   • Multi-floor CLT floor build-up (structural layer → insulation → membrane
#     → screed → parkett), per floor
#   • Wall panels with a 5-layer build-up (cladding → wind barrier →
#     insulation → vapour barrier → plasterboard)
#   • Façade wall extrusions and vertical volume extrusions
#   • Façade subdivision: glass windows, Schüco doors, glass balustrades
#   • Timber louver screens (parametric density)
#   • Compound perimeter wall with vehicular + pedestrian gate openings
#   • Site filling, grass top, vehicular ramp and pedestrian entry steps
#   • GF perimeter threshold step
#   • Double-leaf wooden main entrance door (auto-placed on north wall)
#   • Internal UC-shaped staircase per floor (DIN 18065, Option A layout)
#   • Rhino material assignments for Shaded / Rendered display
#   • Custom Eto GUI dialogs (sliders, list boxes, radio buttons)
#
# EXECUTION
# ---------
# Open Rhino 8 → RunPythonScript → select this file.
# All user inputs are collected via GUI dialogs; no command-line input needed.
#
# COORDINATE SYSTEM
# -----------------
# Origin (0, 0, 0) = centre of the plot at finished-floor level (GF = Z 0).
# X = plot length direction, Y = plot width direction, Z = vertical.
#
# VERSION NOTES  v43-1
# --------------------
# • Internal UC staircase (Option A) fully replaces the previous open-string
#   stair; shaft cell auto-detected from the column grid.
# • Wireframe display is enforced during the full generation run and released
#   at completion to protect viewport performance.
# • Material system migrated to Rhino.DocObjects.Material for Shaded/Rendered
#   colour fidelity (no existing geometry logic changed).
# =============================================================================


import rhinoscriptsyntax as rs; import scriptcontext as sc
import Rhino; import Rhino.Geometry as rg
import Rhino.UI; import time
import pprint; import math
import System; import Eto
import Eto.Forms as forms; import Eto.Drawing as drawing

# ── MATERIAL SYSTEM (v43) ─────────────────────────────────────────────────────
# Uses Rhino.DocObjects.Material so colours appear in SHADED + RENDERED modes.
# Each helper creates the material once (by name), then reuses it.
# _apply_material() assigns it to any Rhino object ID.
# No existing logic is changed — only new calls are added after object creation.

def _get_or_add_material(name, diffuse_rgb, shine=0.0, transparency=0.0, reflectivity=0.0):
    """Return the material-table index for a named material, creating it if needed."""
    try:
        import System.Drawing as _sd
        for i in range(sc.doc.Materials.Count):
            m = sc.doc.Materials[i]
            if m is not None and m.Name == name:
                return i
        idx = sc.doc.Materials.Add()
        mat = sc.doc.Materials[idx]
        mat.Name = name
        r, g, b = diffuse_rgb
        col = _sd.Color.FromArgb(r, g, b)
        mat.DiffuseColor  = col
        mat.SpecularColor = _sd.Color.FromArgb(255, 255, 255)
        mat.Shine         = float(shine)
        mat.Transparency  = float(transparency)
        mat.Reflectivity  = float(reflectivity)
        mat.CommitChanges()
        return idx
    except Exception:
        return None

def _apply_material(obj_id, mat_idx):
    """Assign a material-table index to a Rhino object so it shows colour in Shaded mode."""
    try:
        if obj_id is None or mat_idx is None:
            return
        obj = sc.doc.Objects.Find(obj_id)
        if obj:
            obj.Attributes.MaterialIndex  = mat_idx
            obj.Attributes.MaterialSource = Rhino.DocObjects.ObjectMaterialSource.MaterialFromObject
            obj.CommitChanges()
    except Exception:
        pass

# ── Named material getters (each calls _get_or_add_material once and reuses) ──
def _mat_timber():
    return _get_or_add_material("MAT_Timber",       (160, 100,  45), shine=0.08)
def _mat_timber_dark():
    return _get_or_add_material("MAT_Timber_Dark",  ( 90,  55,  20), shine=0.06)
def _mat_aluminium():
    return _get_or_add_material("MAT_Aluminium",    (190, 195, 200), shine=0.85, reflectivity=0.45)
def _mat_glass():
    return _get_or_add_material("MAT_Glass",        (180, 225, 235), shine=0.92, transparency=0.70, reflectivity=0.15)
def _mat_concrete():
    return _get_or_add_material("MAT_Concrete",     (180, 175, 168), shine=0.02)
def _mat_insulation():
    return _get_or_add_material("MAT_Insulation",   (240, 220, 140), shine=0.0)
def _mat_screed():
    return _get_or_add_material("MAT_Screed",       (210, 205, 198), shine=0.03)
def _mat_membrane():
    return _get_or_add_material("MAT_Membrane",     ( 60,  60,  65), shine=0.05)
def _mat_parkett():
    return _get_or_add_material("MAT_Parkett",      (184, 120,  16), shine=0.18)
def _mat_facade_paint():
    return _get_or_add_material("MAT_Facade_Paint", (240, 236, 228), shine=0.04)
def _mat_soil():
    return _get_or_add_material("MAT_Soil",         ( 85,  55,  30), shine=0.0)
def _mat_grass():
    return _get_or_add_material("MAT_Grass",        ( 80, 140,  60), shine=0.0)
def _mat_compound_wall():
    return _get_or_add_material("MAT_Compound_Wall",(220, 215, 205), shine=0.03)
def _mat_stone_step():
    return _get_or_add_material("MAT_Stone_Step",   (155, 150, 145), shine=0.06)
def _mat_louver_fin():
    return _get_or_add_material("MAT_Louver_Fin",   (160, 100,  45), shine=0.08)
def _mat_louver_bar():
    return _get_or_add_material("MAT_Louver_Bar",   (130,  80,  30), shine=0.06)
def _mat_stair_tread():
    return _get_or_add_material("MAT_Stair_Tread",  (160, 100,  45), shine=0.08)
def _mat_stair_landing():
    return _get_or_add_material("MAT_Stair_Landing",(180, 175, 168), shine=0.02)
def _mat_stair_stringer():
    return _get_or_add_material("MAT_Stair_Stringer",(140, 140, 145), shine=0.25)
def _mat_stair_handrail():
    return _get_or_add_material("MAT_Stair_Handrail",(190, 195, 200), shine=0.85, reflectivity=0.40)
# ── END MATERIAL SYSTEM ────────────────────────────────────────────────────────

# ── Wireframe enforcement state ───────────────────────────────────────────────
# Set to a DisplayModeDescription by main() at startup; cleared to None at end.
_ACTIVE_WF_DM = [None]   # list-box so it's mutable from nested scopes

def _enforce_wireframe():
    """Re-apply wireframe to every viewport if generation is still running.
    Called after every major Redraw so a mid-run user switch is overridden."""
    dm = _ACTIVE_WF_DM[0]
    if dm is None:
        return
    try:
        for _v in sc.doc.Views:
            try:
                _v.ActiveViewport.DisplayMode = dm
            except Exception:
                pass
        sc.doc.Views.Redraw()
    except Exception:
        pass

def initialize_building_data():
    Building = {
        "name": "Parametric Building",
        "location": "TH-OWL",
        "plot": {
            "length": 0.0, "width": 0.0, "setback": 0.0,
            "boundary": None, "north_side": None, "north_direction": None,
        },
        "road": { "width": 15.0, "extension": 20.0, "boundary": None, },
        "compound": {"north_side": None, "openings": [], "wall_height": 2.0, "wall_thickness": 0.20, "site_fill_height": 0.30},
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
            "wall_extrusion_footprints": [],
        },
        "purlins": {
            "n_per_cell":    2,        # default, recalculated from gs
            "spacing":       0.0,      # m, bay spacing between purlins
            "section_width": 0.10,     # m
            "section_depth": 0.32,     # m
            "section_name":  "PURLIN", # updated during generation
            "ids_per_floor": [],       # Rhino object IDs per floor
        },
        "staircase": {
            "cell":     None,
            "n_risers": 0,
            "riser_h":  0.0,
            "tread_d":  0.0,
            "stair_w":  1.00,
            "ids":      [],
        }
    }
    return Building
def _delete_layer_tree(root_layer_name):
    """Delete all objects on a layer and its sublayers, then remove the layers."""
    try:
        if not rs.IsLayer(root_layer_name):
            return
        child_layers = []
        try:
            all_layers = rs.LayerNames() or []
            prefix = root_layer_name + "::"
            child_layers = [ln for ln in all_layers if ln == root_layer_name or ln.startswith(prefix)]
        except Exception:
            child_layers = [root_layer_name]
        for ln in sorted(child_layers, key=lambda s: s.count("::"), reverse=True):
            try:
                objs = rs.ObjectsByLayer(ln)
                if objs:
                    rs.DeleteObjects(objs)
            except Exception:
                pass
            try:
                rs.DeleteLayer(ln)
            except Exception:
                pass
    except Exception:
        pass
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
    layers_to_clear.append("Glass_Windows")
    layers_to_clear.append("Glass_Doors")
    layers_to_clear.append("Glass_Window_Sills")
    layers_to_clear.append("Balustrade_Glass")
    layers_to_clear.append("Balustrade_Handrail")
    layers_to_clear.append("Balustrade_Channel")
    layers_to_clear.append("Facade_Louvers")
    layers_to_clear.append("Facade_Louvers_Bar")
    layers_to_clear.append("Compound_Wall")
    layers_to_clear.append("Compound_Gate_Louvers")
    layers_to_clear.append("Compound_Gate_Louvers_Bar")
    layers_to_clear.append("Site_Filling")
    layers_to_clear.append("Site_Filling_Grass")
    layers_to_clear.append("Compound_Entry_Steps")
    layers_to_clear.append("Compound_Entry_Ramp")
    layers_to_clear.append("Main_Entrance_Door")
    layers_to_clear.append("GF_Perimeter_Steps")
    _delete_layer_tree("Staircase")
    _FLOOR_SUB = ["CLT_Structural", "Insulation", "Membrane", "Screed", "Parkett"]
    _WALL_SUB  = ["Ext_Cladding", "Wind_Barrier", "Insulation", "Vapour_Barrier", "Plasterboard"]
    for suffix in _WALL_SUB:
        sub_ln = "Wall_Panels_-1::{}".format(suffix)
        if rs.IsLayer(sub_ln):
            objs = rs.ObjectsByLayer(sub_ln)
            if objs:
                rs.DeleteObjects(objs)
            try:
                rs.DeleteLayer(sub_ln)
            except Exception:
                pass
    for i in range(20):
        for suffix in _FLOOR_SUB:
            sub_ln = "Floor_Panels_{}::{}".format(i, suffix)
            if rs.IsLayer(sub_ln):
                objs = rs.ObjectsByLayer(sub_ln)
                if objs:
                    rs.DeleteObjects(objs)
                try:
                    rs.DeleteLayer(sub_ln)
                except Exception:
                    pass
        for suffix in _WALL_SUB:
            sub_ln = "Wall_Panels_{}::{}".format(i, suffix)
            if rs.IsLayer(sub_ln):
                objs = rs.ObjectsByLayer(sub_ln)
                if objs:
                    rs.DeleteObjects(objs)
                try:
                    rs.DeleteLayer(sub_ln)
                except Exception:
                    pass
        layers_to_clear.append("Floor_Panels_{}".format(i))
        layers_to_clear.append("Clipping_Plane_{}".format(i))
        layers_to_clear.append("Wall_Panels_{}".format(i))
    for layer_name in layers_to_clear:
        if rs.IsLayer(layer_name):
            objs = rs.ObjectsByLayer(layer_name)
            if objs:
                rs.DeleteObjects(objs)
            try:
                rs.DeleteLayer(layer_name)
            except Exception:
                pass
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
    return drawing.Color(float(r) / 255.0, float(g) / 255.0, float(b) / 255.0, 1.0)
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
        try:
            ctrl.ItemTextColor = col
        except:
            pass
def darken_color(rgb, factor=0.22):
    """Return a much darker version of an (r,g,b) tuple.
    NOTE:
    - factor is still in (0,1) like before, but we apply a stronger curve so dialog surfaces
      can go *very* dark while keeping a subtle hue (more contrast with text).
    - This keeps existing call-sites unchanged (they typically pass 0.22).; """
    f = max(0.0, min(1.0, float(factor)))
    f = f * f; lift = 4
    return (max(0, min(255, int(rgb[0] * f) + lift)),
            max(0, min(255, int(rgb[1] * f) + lift)),
            max(0, min(255, int(rgb[2] * f) + lift)))
def soften_color(rgb, lift=35):
    """Slightly lift a dark color for borders/separators."""
    return (max(0, min(255, int(rgb[0] + lift))),
            max(0, min(255, int(rgb[1] + lift))),
            max(0, min(255, int(rgb[2] + lift))))
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
_BODY_TEXT_DARK     = BH_WHITE; _BODY_TEXT_MED      = BH_WHITE
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
    """Add a closed polygon to an Eto.Drawing.GraphicsPath in a Rhino-safe way.; Eto's GraphicsPath API differs across Rhino/Eto versions (some builds do NOT expose AddPolygon).
    We therefore try several methods to ensure compatibility.; """
    if pts is None:
        return
    pts_list = list(pts)
    if len(pts_list) < 2:
        return
    try:
        gp.AddPolygon(pts_list)
        return
    except Exception:
        pass
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
        return
def _draw_human(g, x, y, s=1.0, color_rgb=ICON_INK_LIGHT):
    r = 2.5 * s
    g.FillEllipse(_icon_brush(color_rgb), x - r, y - r, r * 2, r * 2)
    arm_r = 1.5 * s; offset = 5.0 * s
    g.FillEllipse(_icon_brush(color_rgb, 180), x - offset - arm_r, y - arm_r, arm_r * 2, arm_r * 2)
    g.FillEllipse(_icon_brush(color_rgb, 180), x + offset - arm_r, y - arm_r, arm_r * 2, arm_r * 2)
    g.DrawLine(_icon_pen(color_rgb, 1), x - r, y, x - offset, y)
    g.DrawLine(_icon_pen(color_rgb, 1), x + r, y, x + offset, y)
    g.FillEllipse(_icon_brush(color_rgb, 180), x - arm_r, y + offset - arm_r, arm_r * 2, arm_r * 2)
    g.DrawLine(_icon_pen(color_rgb, 1), x, y + r, x, y + offset)
def _draw_ground(g, size):
    pad = 3
    r = drawing.RectangleF(pad, pad, size - pad * 2, size - pad * 2)
    g.FillRectangle(_icon_brush(ICON_INK_DARK, 255), r)
    grid_pen = _icon_pen(BH_MID_GREY, 1)
    for i in range(8, size - 4, 8):
        g.DrawLine(grid_pen, pad, i, size - pad, i)
        g.DrawLine(grid_pen, i, pad, i, size - pad)
    g.DrawRectangle(_icon_pen(BH_WHITE, 1), r)
def _draw_isometric_block(g, x, y, w, h, depth, face_rgb=None, side_rgb=None, top_rgb=None):
    face_rgb = face_rgb or BH_RED; side_rgb = side_rgb or BH_RED_DARK
    top_rgb  = top_rgb  or BH_WHITE
    g.FillRectangle(_icon_brush(face_rgb), x, y, w, h)
    side = drawing.GraphicsPath()
    _gp_add_polygon(side, [
        drawing.PointF(x + w, y),
        drawing.PointF(x + w + depth, y - depth * 0.6),
        drawing.PointF(x + w + depth, y + h - depth * 0.6),
        drawing.PointF(x + w, y + h),
    ])
    g.FillPath(_icon_brush(side_rgb), side)
    top = drawing.GraphicsPath()
    _gp_add_polygon(top, [
        drawing.PointF(x, y),
        drawing.PointF(x + depth, y - depth * 0.6),
        drawing.PointF(x + w + depth, y - depth * 0.6),
        drawing.PointF(x + w, y),
    ])
    g.FillPath(_icon_brush(top_rgb), top)
    ink = _icon_pen(BH_BLACK, 2)
    g.DrawRectangle(ink, drawing.RectangleF(x, y, w, h))
def _draw_crane(g, x, y, size):
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
        g.DrawRectangle(drawing.Pen(make_color(*BH_WHITE), 0.8), drawing.RectangleF(6*s, 40*s, 32*s, 4*s))
        g.FillRectangle(_icon_brush(BH_RED, 20), drawing.RectangleF(6*s, 32*s, 32*s, 8*s))
        g.DrawRectangle(pen_main, drawing.RectangleF(6*s, 32*s, 32*s, 8*s))
        g.FillRectangle(_icon_brush(BH_RED, 30), drawing.RectangleF(6*s, 24*s, 26*s, 8*s))
        g.DrawRectangle(pen_main, drawing.RectangleF(6*s, 24*s, 26*s, 8*s))
        g.FillRectangle(_icon_brush(BH_RED, 40), drawing.RectangleF(6*s, 16*s, 20*s, 8*s))
        g.DrawRectangle(pen_main, drawing.RectangleF(6*s, 16*s, 20*s, 8*s))
        g.FillRectangle(_icon_brush(BH_RED, 50), drawing.RectangleF(6*s, 8*s, 14*s, 8*s))
        g.DrawRectangle(pen_main, drawing.RectangleF(6*s, 8*s, 14*s, 8*s))
        g.DrawLine(_icon_pen(BH_WHITE, 2), int(6*s), int(8*s), int(20*s), int(8*s))
        lbl_font = drawing.Font(drawing.FontFamily("Arial"), 4, drawing.FontStyle.Bold)
        g.DrawText(lbl_font, make_color(*BH_WHITE), int(18*s), int(35*s), "G")
        g.DrawText(lbl_font, make_color(*BH_WHITE), int(16*s), int(27*s), "1")
        g.DrawText(lbl_font, make_color(*BH_WHITE), int(13*s), int(19*s), "2")
        g.DrawText(lbl_font, make_color(*BH_WHITE), int(10*s), int(11*s), "3")
        g.DrawLine(_icon_pen(BH_WHITE, 1), int(4*s), int(45*s), int(40*s), int(45*s))
        for hx in range(5, 38, 3):
            g.DrawLine(_icon_pen(BH_WHITE, 0.3), int((hx+2)*s), int(47*s), int(hx*s), int(45*s))
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
        for cx in [9, 22, 35]:
            x = cx * s
            g.DrawRectangle(_icon_pen(BH_WHITE, 1.2), drawing.RectangleF(x, 6*s, 5*s, 34*s))
        for by in [6, 16, 26]:
            y = by * s
            g.FillRectangle(_icon_brush(BH_RED, 30), drawing.RectangleF(9*s, y, 31*s, 3*s))
            g.DrawRectangle(_icon_pen(BH_WHITE, 1.2), drawing.RectangleF(9*s, y, 31*s, 3*s))
        for cx in [11, 24, 37]:
            x = cx * s
            g.DrawLine(pen_grain, x, 8*s, x, 38*s)
        g.DrawLine(_icon_pen(BH_WHITE, 1.2), 4*s, 42*s, 44*s, 42*s)
        for hx in range(6, 42, 4):
            g.DrawLine(_icon_pen(BH_WHITE, 0.4), (hx+2)*s, 44*s, hx*s, 42*s)
        for cx in [9, 22, 35]:
            x = (cx + 2.5) * s
            tri = drawing.GraphicsPath()
            _gp_add_polygon(tri, [
                drawing.PointF(x, 42*s),
                drawing.PointF(x - 3*s, 46*s),
                drawing.PointF(x + 3*s, 46*s)])
            g.DrawPath(_icon_pen(BH_WHITE, 0.8), tri)
        g.DrawLine(pen_thin, 14*s, 3*s, 22*s, 3*s)
        g.DrawLine(pen_thin, 14*s, 2*s, 14*s, 4*s)
        g.DrawLine(pen_thin, 22*s, 2*s, 22*s, 4*s)
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
        slab_top = drawing.GraphicsPath()
        _gp_add_polygon(slab_top, [
            drawing.PointF(24*s, 8*s), drawing.PointF(44*s, 20*s),
            drawing.PointF(24*s, 32*s), drawing.PointF(4*s, 20*s)])
        g.FillPath(_icon_brush(BH_RED, 20), slab_top)
        g.DrawPath(pen, slab_top)
        side_l = drawing.GraphicsPath()
        _gp_add_polygon(side_l, [
            drawing.PointF(4*s, 20*s), drawing.PointF(4*s, 24*s),
            drawing.PointF(24*s, 36*s), drawing.PointF(24*s, 32*s)])
        g.FillPath(_icon_brush(BH_RED, 10), side_l)
        g.DrawPath(_icon_pen(BH_WHITE, 0.8), side_l)
        side_r = drawing.GraphicsPath()
        _gp_add_polygon(side_r, [
            drawing.PointF(24*s, 32*s), drawing.PointF(24*s, 36*s),
            drawing.PointF(44*s, 24*s), drawing.PointF(44*s, 20*s)])
        g.FillPath(_icon_brush(BH_RED, 8), side_r)
        g.DrawPath(_icon_pen(BH_WHITE, 0.8), side_r)
        for i in range(1, 5):
            x1 = (4 + i*5) * s; y1 = (20 - i*3) * s
            x2 = (4 + i*5 + 20) * s; y2 = (20 - i*3 + 12) * s
            g.DrawLine(pen_grid, x1, y1, x2, y2)
        for i in range(1, 5):
            x1 = (4 + i*5) * s; y1 = (20 + i*3) * s
            x2 = (4 + i*5 + 20) * s; y2 = (20 + i*3 - 12) * s
            g.DrawLine(pen_grid, x1, y1, x2, y2)
        for pt in [(14,14),(24,20),(34,14),(14,26),(24,20),(34,26),(19,17),(29,17),(19,23),(29,23)]:
            g.FillEllipse(_icon_brush(BH_WHITE), int(pt[0]*s)-1, int(pt[1]*s)-1, 3, 3)
        g.DrawLine(pen_dim, int(4*s), int(38*s), int(14*s), int(38*s))
        g.DrawLine(pen_dim, int(30*s), int(38*s), int(44*s), int(38*s))
        g.DrawLine(pen_dim, int(4*s), int(37*s), int(4*s), int(39*s))
        g.DrawLine(pen_dim, int(44*s), int(37*s), int(44*s), int(39*s))
        lbl = drawing.Font(drawing.FontFamily("Arial"), 3, drawing.FontStyle.Bold)
        g.DrawText(lbl, make_color(*BH_ORANGE), int(15*s), int(36*s), "(m)")
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
        g.FillRectangle(_icon_brush(BH_RED, 20), drawing.RectangleF(4*s, 34*s, 34*s, 8*s))
        g.DrawRectangle(pen, drawing.RectangleF(4*s, 34*s, 34*s, 8*s))
        for vx in [11, 18, 25, 31]:
            g.DrawLine(pen_div, int(vx*s), int(34*s), int(vx*s), int(42*s))
        g.FillRectangle(_icon_brush(BH_RED, 28), drawing.RectangleF(4*s, 25*s, 27*s, 8*s))
        g.DrawRectangle(pen, drawing.RectangleF(4*s, 25*s, 27*s, 8*s))
        for vx in [11, 18, 25]:
            g.DrawLine(pen_div, int(vx*s), int(25*s), int(vx*s), int(33*s))
        g.FillRectangle(_icon_brush(BH_RED, 36), drawing.RectangleF(4*s, 16*s, 20*s, 8*s))
        g.DrawRectangle(pen, drawing.RectangleF(4*s, 16*s, 20*s, 8*s))
        for vx in [11, 18]:
            g.DrawLine(pen_div, int(vx*s), int(16*s), int(vx*s), int(24*s))
        g.FillRectangle(_icon_brush(BH_RED, 44), drawing.RectangleF(4*s, 8*s, 13*s, 7*s))
        g.DrawRectangle(pen, drawing.RectangleF(4*s, 8*s, 13*s, 7*s))
        g.DrawLine(pen_div, int(11*s), int(8*s), int(11*s), int(15*s))
        g.DrawText(lbl, make_color(*BH_WHITE), int(39*s), int(36*s), "G")
        g.DrawText(lbl, make_color(*BH_WHITE), int(32*s), int(27*s), "1")
        g.DrawText(lbl, make_color(*BH_WHITE), int(25*s), int(18*s), "2")
        g.DrawText(lbl, make_color(*BH_WHITE), int(18*s), int(9*s), "3")
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
        g.DrawLine(_icon_pen(BH_WHITE, 1), int(2*s), int(44*s), int(44*s), int(44*s))
        for hx in range(3, 42, 3):
            g.DrawLine(_icon_pen(BH_WHITE, 0.3), int((hx+2)*s), int(46*s), int(hx*s), int(44*s))
    finally:
        g.Dispose()
    return bmp

def _icon_variant_door(size=48):
    """Main entrance door icon: double-leaf wooden door with frame, handle bars, and arch top."""
    bmp = drawing.Bitmap(size, size, drawing.PixelFormat.Format32bppRgba)
    g = drawing.Graphics(bmp)
    try:
        g.AntiAlias = True
        g.FillRectangle(_icon_brush(BH_BLACK), 0, 0, size, size)
        s = size / 48.0
        pen      = _icon_pen(BH_WHITE,  1.4)
        pen_thin = _icon_pen(BH_WHITE,  0.7)
        pen_gold = _icon_pen(BH_ORANGE, 1.0)
        # Outer frame
        g.FillRectangle(_icon_brush(BH_RED, 60), drawing.RectangleF(6*s, 6*s, 36*s, 38*s))
        g.DrawRectangle(pen, drawing.RectangleF(6*s, 6*s, 36*s, 38*s))
        # Centre mullion
        g.DrawLine(pen, int(24*s), int(6*s), int(24*s), int(44*s))
        # Left leaf frame inner
        g.DrawRectangle(pen_thin, drawing.RectangleF(9*s, 9*s, 12*s, 32*s))
        # Left leaf panel
        g.FillRectangle(_icon_brush(BH_RED, 90), drawing.RectangleF(11*s, 12*s, 8*s, 12*s))
        g.DrawRectangle(pen_thin, drawing.RectangleF(11*s, 12*s, 8*s, 12*s))
        g.FillRectangle(_icon_brush(BH_RED, 90), drawing.RectangleF(11*s, 26*s, 8*s, 12*s))
        g.DrawRectangle(pen_thin, drawing.RectangleF(11*s, 26*s, 8*s, 12*s))
        # Right leaf frame inner
        g.DrawRectangle(pen_thin, drawing.RectangleF(27*s, 9*s, 12*s, 32*s))
        # Right leaf panel
        g.FillRectangle(_icon_brush(BH_RED, 90), drawing.RectangleF(29*s, 12*s, 8*s, 12*s))
        g.DrawRectangle(pen_thin, drawing.RectangleF(29*s, 12*s, 8*s, 12*s))
        g.FillRectangle(_icon_brush(BH_RED, 90), drawing.RectangleF(29*s, 26*s, 8*s, 12*s))
        g.DrawRectangle(pen_thin, drawing.RectangleF(29*s, 26*s, 8*s, 12*s))
        # Left handle bar (vertical, gold)
        g.DrawLine(pen_gold, int(20*s), int(19*s), int(20*s), int(29*s))
        g.DrawLine(pen_gold, int(19*s), int(19*s), int(21*s), int(19*s))
        g.DrawLine(pen_gold, int(19*s), int(29*s), int(21*s), int(29*s))
        # Right handle bar (vertical, gold)
        g.DrawLine(pen_gold, int(28*s), int(19*s), int(28*s), int(29*s))
        g.DrawLine(pen_gold, int(27*s), int(19*s), int(29*s), int(19*s))
        g.DrawLine(pen_gold, int(27*s), int(29*s), int(29*s), int(29*s))
        # Ground line
        g.DrawLine(_icon_pen(BH_WHITE, 1), int(2*s), int(44*s), int(46*s), int(44*s))
        # Steps
        g.DrawLine(_icon_pen(BH_WHITE, 0.8), int(4*s), int(44*s), int(44*s), int(44*s))
        g.DrawLine(_icon_pen(BH_WHITE, 0.5), int(8*s), int(46*s), int(40*s), int(46*s))
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
        g.FillRectangle(_icon_brush(BH_RED, 25), drawing.RectangleF(20*s, 6*s, 3*s, 32*s))
        g.DrawRectangle(_icon_pen(BH_WHITE, 1), drawing.RectangleF(20*s, 6*s, 3*s, 32*s))
        for fy in [38, 30, 22, 14, 6]:
            g.DrawLine(pen, int(6*s), int(fy*s), int(20*s), int(fy*s))
        g.FillRectangle(_icon_brush(BH_RED, 40), drawing.RectangleF(23*s, 22*s, 6*s, 8*s))
        g.DrawRectangle(_icon_pen(BH_WHITE, 1), drawing.RectangleF(23*s, 22*s, 6*s, 8*s))
        g.FillRectangle(_icon_brush(BH_RED, 40), drawing.RectangleF(23*s, 6*s, 6*s, 8*s))
        g.DrawRectangle(_icon_pen(BH_WHITE, 1), drawing.RectangleF(23*s, 6*s, 6*s, 8*s))
        ar1 = drawing.GraphicsPath()
        _gp_add_polygon(ar1, [drawing.PointF(29*s,26*s), drawing.PointF(27*s,25*s), drawing.PointF(27*s,27*s)])
        g.FillPath(_icon_brush(BH_WHITE), ar1)
        g.DrawLine(pen_thin, int(24*s), int(26*s), int(28*s), int(26*s))
        ar2 = drawing.GraphicsPath()
        _gp_add_polygon(ar2, [drawing.PointF(29*s,10*s), drawing.PointF(27*s,9*s), drawing.PointF(27*s,11*s)])
        g.FillPath(_icon_brush(BH_WHITE), ar2)
        g.DrawLine(pen_thin, int(24*s), int(10*s), int(28*s), int(10*s))
        g.DrawText(lbl, make_color(*BH_WHITE), int(3*s), int(33*s), "G")
        g.DrawText(lbl, make_color(*BH_WHITE), int(3*s), int(25*s), "1")
        g.DrawText(lbl, make_color(*BH_WHITE), int(3*s), int(17*s), "2")
        g.DrawText(lbl, make_color(*BH_WHITE), int(3*s), int(9*s), "3")
        g.DrawLine(pen_dim, int(23*s), int(4*s), int(26*s), int(4*s))
        g.DrawLine(pen_dim, int(28*s), int(4*s), int(29*s), int(4*s))
        g.DrawLine(pen_dim, int(23*s), int(3*s), int(23*s), int(5*s))
        g.DrawLine(pen_dim, int(29*s), int(3*s), int(29*s), int(5*s))
        g.DrawText(lbl_sm, make_color(*BH_ORANGE), int(26*s), int(2*s), "(m)")
        g.DrawLine(_icon_pen(BH_WHITE, 1.5), int(4*s), int(40*s), int(32*s), int(40*s))
        for hx in range(5, 30, 2):
            g.DrawLine(_icon_pen(BH_WHITE, 0.3), int((hx+1)*s), int(42*s), int(hx*s), int(40*s))
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
        slab = drawing.GraphicsPath()
        _gp_add_polygon(slab, [
            drawing.PointF(24*s, 36*s), drawing.PointF(44*s, 28*s),
            drawing.PointF(24*s, 20*s), drawing.PointF(4*s, 28*s)])
        g.FillPath(_icon_brush(BH_RED, 10), slab)
        g.DrawPath(pen, slab)
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
        for i in range(1, 4):
            x1 = (4 + i*5) * s; y1 = (28 - i*2) * s
            x2 = (4 + i*5 + 20) * s; y2 = (28 - i*2 + 8) * s
            g.DrawLine(pen_thin, x1, y1, x2, y2)
        for i in range(1, 4):
            x1 = (4 + i*5) * s; y1 = (28 + i*2) * s
            x2 = (4 + i*5 + 20) * s; y2 = (28 + i*2 - 8) * s
            g.DrawLine(pen_thin, x1, y1, x2, y2)
        for pts in [
            [(9*s,26*s),(14*s,24*s),(14*s,12*s),(9*s,14*s)],
            [(14*s,24*s),(19*s,26*s),(19*s,14*s),(14*s,12*s)],
            [(9*s,14*s),(14*s,12*s),(19*s,14*s),(14*s,16*s)]
        ]:
            gp = drawing.GraphicsPath()
            _gp_add_polygon(gp, [drawing.PointF(*p) for p in pts])
            g.FillPath(_icon_brush(BH_RED, 30), gp)
            g.DrawPath(_icon_pen(BH_WHITE, 0.6), gp)
        g.FillRectangle(_icon_brush(BH_BLACK), drawing.RectangleF(10*s, 17*s, 3*s, 9*s))
        for pts in [
            [(29*s,30*s),(34*s,28*s),(34*s,16*s),(29*s,18*s)],
            [(34*s,28*s),(39*s,30*s),(39*s,18*s),(34*s,16*s)],
            [(29*s,18*s),(34*s,16*s),(39*s,18*s),(34*s,20*s)]
        ]:
            gp = drawing.GraphicsPath()
            _gp_add_polygon(gp, [drawing.PointF(*p) for p in pts])
            g.FillPath(_icon_brush(BH_RED, 30), gp)
            g.DrawPath(_icon_pen(BH_WHITE, 0.6), gp)
        g.FillRectangle(_icon_brush(BH_BLACK), drawing.RectangleF(30*s, 21*s, 3*s, 9*s))
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
        g.DrawLine(_icon_pen(BH_WHITE, 1), int(44*s), int(30*s), int(44*s), int(14*s))
        zt = drawing.GraphicsPath()
        _gp_add_polygon(zt, [drawing.PointF(44*s,14*s), drawing.PointF(43*s,16*s), drawing.PointF(45*s,16*s)])
        g.FillPath(_icon_brush(BH_WHITE), zt)
        g.DrawText(lbl, make_color(*BH_WHITE), int(45*s), int(20*s), "Z")
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
        g.DrawEllipse(_icon_pen(BH_WHITE, 2), cx - r, cy - r, r*2, r*2)
        north = drawing.GraphicsPath()
        _gp_add_polygon(north, [
            drawing.PointF(cx, cy - r + 2),
            drawing.PointF(cx - 6, cy - 4),
            drawing.PointF(cx + 6, cy - 4),
        ])
        g.FillPath(_icon_brush(BH_RED), north)
        south = drawing.GraphicsPath()
        _gp_add_polygon(south, [
            drawing.PointF(cx, cy + r - 2),
            drawing.PointF(cx - 5, cy + 4),
            drawing.PointF(cx + 5, cy + 4),
        ])
        g.FillPath(_icon_brush(BH_WHITE), south)
        g.DrawLine(_icon_pen(BH_ORANGE, 2), cx - r + 4, cy, cx + r - 4, cy)
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
        g.DrawRectangle(pen_main, drawing.RectangleF(10, 10, 24, 28))
        g.FillRectangle(brush_fill, drawing.RectangleF(14, 14, 16, 20))
        g.DrawRectangle(pen_dash, drawing.RectangleF(14, 14, 16, 20))
        g.DrawEllipse(pen_thin, drawing.RectangleF(36, 2, 10, 10))
        north = drawing.GraphicsPath()
        _gp_add_polygon(north, [
            drawing.PointF(41, 3),
            drawing.PointF(38, 9),
            drawing.PointF(44, 9),
        ])
        g.FillPath(_icon_brush(BH_RED), north)
        n_font = drawing.Font(drawing.FontFamily("Arial"), 4, drawing.FontStyle.Bold)
        g.DrawText(n_font, make_color(*BH_WHITE), 39, 11, "N")
        g.DrawLine(pen_thin, 10, 42, 16, 42)     # left segment
        g.DrawLine(pen_thin, 28, 42, 34, 42)     # right segment
        g.DrawLine(pen_thin, 10, 40, 10, 44)     # left tick
        g.DrawLine(pen_thin, 34, 40, 34, 44)     # right tick
        h_left = drawing.GraphicsPath()
        _gp_add_polygon(h_left, [
            drawing.PointF(10, 42), drawing.PointF(13, 40.5), drawing.PointF(13, 43.5)])
        g.FillPath(_icon_brush(BH_WHITE), h_left)
        h_right = drawing.GraphicsPath()
        _gp_add_polygon(h_right, [
            drawing.PointF(34, 42), drawing.PointF(31, 40.5), drawing.PointF(31, 43.5)])
        g.FillPath(_icon_brush(BH_WHITE), h_right)
        lbl_font = drawing.Font(drawing.FontFamily("Arial"), 3.5, drawing.FontStyle.Bold)
        lbl_font_sm = drawing.Font(drawing.FontFamily("Arial"), 3, drawing.FontStyle.Italic)
        g.DrawText(lbl_font, make_color(*BH_WHITE), 16, 39, "LENGTH")
        g.DrawText(lbl_font_sm, make_color(*BH_WHITE), 19, 43, "(m)")
        g.DrawLine(pen_thin, 5, 10, 5, 18)       # top segment
        g.DrawLine(pen_thin, 5, 30, 5, 38)       # bottom segment
        g.DrawLine(pen_thin, 3, 10, 7, 10)       # top tick
        g.DrawLine(pen_thin, 3, 38, 7, 38)       # bottom tick
        v_top = drawing.GraphicsPath()
        _gp_add_polygon(v_top, [
            drawing.PointF(5, 10), drawing.PointF(3.5, 13), drawing.PointF(6.5, 13)])
        g.FillPath(_icon_brush(BH_WHITE), v_top)
        v_bot = drawing.GraphicsPath()
        _gp_add_polygon(v_bot, [
            drawing.PointF(5, 38), drawing.PointF(3.5, 35), drawing.PointF(6.5, 35)])
        g.FillPath(_icon_brush(BH_WHITE), v_bot)
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
        slab = drawing.GraphicsPath()
        _gp_add_polygon(slab, [
            drawing.PointF(6*s, 30*s), drawing.PointF(24*s, 22*s),
            drawing.PointF(42*s, 30*s), drawing.PointF(24*s, 38*s)])
        g.FillPath(_icon_brush(BH_RED, 18), slab)
        g.DrawPath(pen, slab)
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
        g.DrawLine(pen_thin, int(15*s), int(26*s), int(33*s), int(34*s))
        g.DrawLine(pen_thin, int(15*s), int(34*s), int(33*s), int(26*s))
        bw = drawing.GraphicsPath()
        _gp_add_polygon(bw, [
            drawing.PointF(6*s,30*s), drawing.PointF(6*s,10*s),
            drawing.PointF(24*s,4*s), drawing.PointF(24*s,22*s)])
        g.FillPath(_icon_brush(BH_RED, 12), bw)
        g.DrawPath(pen, bw)
        g.DrawLine(pen_thin, int(12*s), int(24*s), int(12*s), int(8*s))
        g.DrawLine(pen_thin, int(18*s), int(20*s), int(18*s), int(6*s))
        sw = drawing.GraphicsPath()
        _gp_add_polygon(sw, [
            drawing.PointF(24*s,22*s), drawing.PointF(24*s,4*s),
            drawing.PointF(42*s,10*s), drawing.PointF(42*s,30*s)])
        g.FillPath(_icon_brush(BH_RED, 8), sw)
        g.DrawPath(pen, sw)
        g.DrawLine(pen_thin, int(30*s), int(20*s), int(30*s), int(6*s))
        g.DrawLine(pen_thin, int(36*s), int(24*s), int(36*s), int(8*s))
        g.DrawLine(_icon_pen(BH_ORANGE, 0.5), int(16*s), int(34*s), int(8*s), int(40*s))
        g.FillEllipse(_icon_brush(BH_ORANGE), int(16*s)-1, int(34*s)-1, 2, 2)
        g.DrawText(lbl, make_color(*BH_ORANGE), int(2*s), int(40*s), "FLOOR")
        g.DrawLine(_icon_pen(BH_ORANGE, 0.5), int(10*s), int(16*s), int(2*s), int(12*s))
        g.FillEllipse(_icon_brush(BH_ORANGE), int(10*s)-1, int(16*s)-1, 2, 2)
        g.DrawText(lbl, make_color(*BH_ORANGE), int(0*s), int(8*s), "WALL")
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
        for cx in [6, 14, 22, 30, 38]:
            g.DrawLine(_icon_pen(BH_WHITE, 0.6), int(cx*s), int(34*s), int(cx*s), int(8*s) if cx >= 30 else int(22*s) if cx >= 22 else int(28*s))
        g.DrawLine(pen, int(4*s), int(34*s), int(42*s), int(34*s))
        g.DrawLine(pen, int(4*s), int(28*s), int(42*s), int(28*s))
        g.DrawLine(_icon_pen(BH_WHITE, 1), int(20*s), int(22*s), int(42*s), int(22*s))
        g.DrawLine(_icon_pen(BH_WHITE, 1), int(28*s), int(16*s), int(42*s), int(16*s))
        g.DrawLine(_icon_pen(BH_WHITE, 1), int(28*s), int(8*s), int(42*s), int(8*s))
        for (px, py, pw, ph) in [(6,28,7,6),(14,28,7,6),(22,28,7,6),(30,28,7,6),
                                  (22,22,7,6),(30,22,7,6),(30,16,7,6),(30,8,7,8),(38,8,4,8)]:
            g.FillRectangle(_icon_brush(BH_RED, 25), drawing.RectangleF(px*s, py*s, pw*s, ph*s))
            g.DrawRectangle(_icon_pen(BH_WHITE, 0.4), drawing.RectangleF(px*s, py*s, pw*s, ph*s))
            g.DrawLine(_icon_pen(BH_WHITE, 0.2), int((px+pw/3)*s), int(py*s), int((px+pw/3)*s), int((py+ph)*s))
            g.DrawLine(_icon_pen(BH_WHITE, 0.2), int((px+2*pw/3)*s), int(py*s), int((px+2*pw/3)*s), int((py+ph)*s))
        for (gx, gy, gw, gh) in [(6,28,2,6),(22,22,2,6),(32,16,2,6),(38,8,2,8)]:
            g.DrawLine(_icon_pen(BH_WHITE, 0.3), int(gx*s), int(gy*s), int((gx+gw)*s), int((gy+gh)*s))
        g.FillRectangle(_icon_brush(BH_RED, 35), drawing.RectangleF(8*s, 22*s, 5*s, 6*s))
        g.DrawRectangle(_icon_pen(BH_WHITE, 0.5), drawing.RectangleF(8*s, 22*s, 5*s, 6*s))
        g.FillRectangle(_icon_brush(BH_BLACK), drawing.RectangleF(9*s, 24*s, 3*s, 4*s))
        g.DrawLine(_icon_pen(BH_WHITE, 1.5), int(2*s), int(36*s), int(44*s), int(36*s))
        for hx in range(3, 42, 2):
            g.DrawLine(_icon_pen(BH_WHITE, 0.2), int((hx+1)*s), int(38*s), int(hx*s), int(36*s))
        lbl = drawing.Font(drawing.FontFamily("Arial"), 2.5, drawing.FontStyle.Bold)
        g.DrawText(lbl, make_color(*BH_ORANGE), int(2*s), int(30*s), "G")
        g.DrawText(lbl, make_color(*BH_ORANGE), int(18*s), int(24*s), "1")
        g.DrawText(lbl, make_color(*BH_ORANGE), int(26*s), int(10*s), "3")
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
        for i in range(4):
            g.DrawLine(pen, int((4+i*3)*s), int(4*s), int((4+i*3)*s), int(12*s))
        g.DrawLine(pen_thin, int(3*s), int(10*s), int(14*s), int(5*s))
        g.DrawText(lbl, make_color(*BH_ORANGE), int(16*s), int(5*s), "25")
        for i in range(4):
            g.DrawLine(pen, int((4+i*3)*s), int(15*s), int((4+i*3)*s), int(23*s))
        g.DrawLine(pen_thin, int(3*s), int(21*s), int(14*s), int(16*s))
        g.DrawLine(pen, int(16*s), int(15*s), int(16*s), int(23*s))
        g.DrawLine(pen, int(19*s), int(15*s), int(19*s), int(23*s))
        g.DrawText(lbl, make_color(*BH_ORANGE), int(22*s), int(16*s), "32")
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
        g.FillRectangle(_icon_brush(BH_RED, 25), drawing.RectangleF(2*s, 4*s, 8*s, 18*s))
        g.DrawRectangle(_icon_pen(BH_WHITE, 1), drawing.RectangleF(2*s, 4*s, 8*s, 18*s))
        g.DrawLine(_icon_pen(BH_WHITE, 0.8), int(11*s), int(13*s), int(14*s), int(13*s))
        ar = drawing.GraphicsPath()
        _gp_add_polygon(ar, [drawing.PointF(14*s,13*s), drawing.PointF(13*s,12*s), drawing.PointF(13*s,14*s)])
        g.FillPath(_icon_brush(BH_WHITE), ar)
        for i in range(3):
            x = (16 + i*4) * s
            a = 20 if i == 1 else 15
            g.FillRectangle(_icon_brush(BH_RED, a), drawing.RectangleF(x, 4*s, 3.5*s, 18*s))
            g.DrawRectangle(_icon_pen(BH_WHITE, 0.6), drawing.RectangleF(x, 4*s, 3.5*s, 18*s))
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
        g.DrawRectangle(_icon_pen(BH_WHITE, 1), drawing.RectangleF(3*s, 3*s, 22*s, 20*s))
        g.DrawLine(_icon_pen(BH_WHITE, 0.6), int(14*s), int(3*s), int(14*s), int(23*s))
        g.DrawLine(_icon_pen(BH_WHITE, 0.6), int(3*s), int(13*s), int(25*s), int(13*s))
        g.DrawLine(_icon_pen(BH_WHITE, 0.3), int(7*s), int(3*s), int(7*s), int(23*s))
        g.DrawLine(_icon_pen(BH_WHITE, 0.3), int(10*s), int(3*s), int(10*s), int(23*s))
        g.DrawLine(_icon_pen(BH_WHITE, 0.3), int(18*s), int(3*s), int(18*s), int(23*s))
        g.DrawLine(_icon_pen(BH_WHITE, 0.3), int(21*s), int(3*s), int(21*s), int(23*s))
        g.DrawRectangle(_icon_pen(BH_WHITE, 0.8), drawing.RectangleF(4*s, 4*s, 3*s, 9*s))
        g.DrawRectangle(_icon_pen(BH_WHITE, 0.3), drawing.RectangleF(4.5*s, 4.5*s, 2*s, 8*s))
        g.DrawLine(_icon_pen(BH_WHITE, 0.2), int(4.5*s), int(4.5*s), int(6.5*s), int(12.5*s))
        g.DrawRectangle(_icon_pen(BH_WHITE, 0.8), drawing.RectangleF(18*s, 4*s, 3*s, 9*s))
        g.DrawRectangle(_icon_pen(BH_WHITE, 0.3), drawing.RectangleF(18.5*s, 4.5*s, 2*s, 8*s))
        g.DrawLine(_icon_pen(BH_WHITE, 0.2), int(18.5*s), int(4.5*s), int(20.5*s), int(12.5*s))
        g.DrawRectangle(_icon_pen(BH_WHITE, 0.8), drawing.RectangleF(7*s, 14*s, 3*s, 9*s))
        g.DrawRectangle(_icon_pen(BH_WHITE, 0.3), drawing.RectangleF(7.5*s, 14.5*s, 2*s, 8*s))
        g.DrawLine(_icon_pen(BH_WHITE, 0.2), int(7.5*s), int(14.5*s), int(9.5*s), int(22.5*s))
        g.DrawRectangle(_icon_pen(BH_WHITE, 0.8), drawing.RectangleF(21*s, 14*s, 3*s, 9*s))
        g.DrawRectangle(_icon_pen(BH_WHITE, 0.3), drawing.RectangleF(21.5*s, 14.5*s, 2*s, 8*s))
        g.DrawLine(_icon_pen(BH_WHITE, 0.2), int(21.5*s), int(14.5*s), int(23.5*s), int(22.5*s))
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
        g.FillRectangle(_icon_brush(BH_RED, 20), drawing.RectangleF(10*s, 6*s, 3*s, 32*s))
        g.DrawRectangle(_icon_pen(BH_WHITE, 0.8), drawing.RectangleF(10*s, 6*s, 3*s, 32*s))
        for fy in [38, 28, 18, 8]:
            g.DrawLine(pen_thin, int(4*s), int(fy*s), int(10*s), int(fy*s))
        g.FillRectangle(_icon_brush(BH_RED, 40), drawing.RectangleF(13*s, 18*s, 5*s, 10*s))
        g.DrawRectangle(_icon_pen(BH_WHITE, 0.6), drawing.RectangleF(13*s, 18*s, 5*s, 10*s))
        g.DrawLine(_icon_pen(BH_WHITE, 0.6), int(14*s), int(23*s), int(17*s), int(23*s))
        ar = drawing.GraphicsPath()
        _gp_add_polygon(ar, [drawing.PointF(17*s,23*s), drawing.PointF(16*s,22*s), drawing.PointF(16*s,24*s)])
        g.FillPath(_icon_brush(BH_WHITE), ar)
        slab = drawing.GraphicsPath()
        _gp_add_polygon(slab, [
            drawing.PointF(34*s, 30*s), drawing.PointF(44*s, 26*s),
            drawing.PointF(34*s, 22*s), drawing.PointF(24*s, 26*s)])
        g.FillPath(_icon_brush(BH_RED, 10), slab)
        g.DrawPath(_icon_pen(BH_WHITE, 0.8), slab)
        for pts in [
            [(29*s,24*s),(34*s,22*s),(34*s,12*s),(29*s,14*s)],
            [(34*s,22*s),(39*s,24*s),(39*s,14*s),(34*s,12*s)],
            [(29*s,14*s),(34*s,12*s),(39*s,14*s),(34*s,16*s)]
        ]:
            gp = drawing.GraphicsPath()
            _gp_add_polygon(gp, [drawing.PointF(*p) for p in pts])
            g.FillPath(_icon_brush(BH_RED, 30), gp)
            g.DrawPath(_icon_pen(BH_WHITE, 0.5), gp)
        g.FillRectangle(_icon_brush(BH_BLACK), drawing.RectangleF(30*s, 17*s, 3*s, 7*s))
        g.DrawLine(_icon_pen(BH_WHITE, 0.8), int(44*s), int(28*s), int(44*s), int(14*s))
        za = drawing.GraphicsPath()
        _gp_add_polygon(za, [drawing.PointF(44*s,14*s), drawing.PointF(43*s,16*s), drawing.PointF(45*s,16*s)])
        g.FillPath(_icon_brush(BH_WHITE), za)
        g.DrawLine(_icon_pen(BH_MID_GREY, 0.4), int(22*s), int(4*s), int(22*s), int(40*s))
        lbl = drawing.Font(drawing.FontFamily("Arial"), 2.5, drawing.FontStyle.Bold)
        g.DrawText(lbl, make_color(*BH_ORANGE), int(5*s), int(40*s), "S1")
        g.DrawText(lbl, make_color(*BH_ORANGE), int(32*s), int(34*s), "S2")
        g.DrawLine(_icon_pen(BH_WHITE, 1), int(2*s), int(42*s), int(46*s), int(42*s))
        for hx in range(3, 44, 2):
            g.DrawLine(_icon_pen(BH_WHITE, 0.2), int((hx+1)*s), int(44*s), int(hx*s), int(42*s))
    finally:
        g.Dispose()
    return bmp
def get_arch_dialog_icon(title_text, size=42):
    """Return an architectural vector icon bitmap for a dialog heading.; The choice is based on the dialog title/heading text.
    """
    t = (title_text or "").upper()
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
    if "ENTRANCE" in t or "DOOR" in t:
        return _icon_variant_door(size)
    if "ORIENTATION" in t:
        return _icon_variant_orientation(size)
    if "FLOORS" in t or "LEVEL" in t:
        return _icon_variant_building(size)
    if "PLOT" in t or "ROAD" in t or "SETBACK" in t:
        return _icon_variant_crane(size)
    return _icon_variant_building(size)
_SLIDER_BODY_TEXT   = BH_WHITE       # white — all body text
_SLIDER_TICK_TEXT   = BH_WHITE       # white — tick numbers
_SLIDER_RANGE_TEXT  = BH_WHITE       # white — min/max labels
_SLIDER_SELECTED_FG = BH_RED         # dark red — "Selected:" highlight only
_SLIDER_SELECTED_BG = BH_BLACK_LIFT  # near-black — selected row background
class VibrantSliderDialog(forms.Dialog[bool]):
    def __init__(self, title_text, message_text, labels, default_label, icon_emoji, header_color, bg_color, values_list, unit_text):
        super(VibrantSliderDialog, self).__init__()
        self.BackgroundColor = make_color(*BH_BLACK)
        self.selected_value = None; self.values_list = values_list
        self.unit_text = unit_text; self.labels = labels
        self.Title = str(title_text)
        self.Padding = drawing.Padding(0)
        self.Resizable = False
        self.MinimumSize = drawing.Size(560, 480)
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
        body_panel = forms.Panel()
        body_panel.BackgroundColor = make_color(*dialog_body_bg_rgb())
        body_panel.Padding = drawing.Padding(24, 18, 24, 18)
        message_label = forms.Label()
        message_label.Text = str(message_text)
        message_label.Font = drawing.Font(drawing.FontFamily("Georgia"), 11, drawing.FontStyle.Bold)
        message_label.TextColor = make_color(*_SLIDER_BODY_TEXT)
        message_label.Wrap = forms.WrapMode.Word
        separator = forms.Panel()
        separator.BackgroundColor = make_color(*DIALOG_ACCENT_BLUE)
        separator.Height = 4
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
        self.slider = forms.Slider()
        self.slider.MinValue = 0
        self.slider.MaxValue = len(values_list) - 1
        self.slider.SnapToTick = True; self.slider.TickFrequency = 1
        self.slider.Orientation = forms.Orientation.Horizontal; self.slider.Width = 480
        default_index = 0
        for i in range(len(values_list)):
            val = values_list[i]
            check_label = "{} {}".format(int(val) if val == int(val) else val, unit_text)
            if check_label == str(default_label):
                default_index = i
                break
        self.slider.Value = default_index; self.slider.ValueChanged += self.on_slider_changed
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
        initial_val = values_list[default_index]
        initial_display = "{} {}".format(int(initial_val) if initial_val == int(initial_val) else initial_val, unit_text)
        self.selection_label = forms.Label()
        self.selection_label.Text = "Selected:  {}".format(initial_display)
        self.selection_label.Font = drawing.Font(drawing.FontFamily("Impact"), 16, drawing.FontStyle.Bold)
        self.selection_label.TextColor = make_color(*_SLIDER_SELECTED_FG)
        self.selection_label.TextAlignment = forms.TextAlignment.Center
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
class PlotDimensionsDialog(forms.Dialog[bool]):
    """Single dialog with two sliders: Plot Length and Plot Width."""
    def __init__(self, values_list, default_val, unit_text):
        super(PlotDimensionsDialog, self).__init__()
        self.BackgroundColor = make_color(*BH_BLACK)
        self.selected_length = None; self.selected_width = None
        self.values_list = values_list; self.unit_text = unit_text
        self.Title = "PLOT DIMENSIONS"
        self.Padding = drawing.Padding(0)
        self.Resizable = False
        self.MinimumSize = drawing.Size(560, 620)
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
        body_panel = forms.Panel()
        body_panel.BackgroundColor = make_color(*dialog_body_bg_rgb())
        body_panel.Padding = drawing.Padding(24, 18, 24, 18)
        default_index = 0
        for i, v in enumerate(values_list):
            if v == default_val:
                default_index = i
                break
        def make_slider_block(label_text):
            """Returns (block_layout, slider_widget, selection_label_widget)."""
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
            for v in values_list:
                tl = forms.Label()
                tl.Text = str(int(v)) if v == int(v) else str(v)
                tl.Font = drawing.Font(drawing.FontFamily("Arial Narrow"), 10, drawing.FontStyle.Bold)
                tl.TextColor = make_color(*_SLIDER_TICK_TEXT)
                tl.TextAlignment = forms.TextAlignment.Center
                tick_row.Cells.Add(forms.TableCell(tl, True))
            tick_layout.Rows.Add(tick_row)
            slider = forms.Slider()
            slider.MinValue = 0
            slider.MaxValue = len(values_list) - 1
            slider.SnapToTick = True; slider.TickFrequency = 1
            slider.Orientation = forms.Orientation.Horizontal; slider.Width = 480
            slider.Value = default_index
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
        self.length_slider.ValueChanged += self.on_length_changed; self.width_slider.ValueChanged  += self.on_width_changed
        divider = forms.Panel()
        divider.BackgroundColor = make_color(*BH_MID_GREY)
        divider.Height = 2
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
        self.selected_length = None; self.selected_width  = None
        self.Close(False)
class PlotSetupDialog(forms.Dialog[bool]):
    """Single dialog: two dimension sliders (Length, Width) + one setback listbox."""
    def __init__(self, dim_values, dim_default, dim_unit, setback_values, setback_default, setback_unit):
        super(PlotSetupDialog, self).__init__()
        self.BackgroundColor = make_color(*BH_BLACK)
        self.selected_length  = None; self.selected_width   = None
        self.selected_setback = None; self.dim_values    = dim_values
        self.dim_unit      = dim_unit; self.setback_values = setback_values
        self.setback_unit   = setback_unit; self.Title = "PLOT SETUP"
        self.Padding = drawing.Padding(0)
        self.Resizable = False
        self.MinimumSize = drawing.Size(560, 820)
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
        body_panel = forms.Panel()
        body_panel.BackgroundColor = make_color(*dialog_body_bg_rgb())
        body_panel.Padding = drawing.Padding(24, 18, 24, 18)
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
            slider.SnapToTick = True; slider.TickFrequency = 1
            slider.Orientation = forms.Orientation.Horizontal; slider.Width = 480
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
        self.length_slider.ValueChanged += self.on_length_changed; self.width_slider.ValueChanged  += self.on_width_changed
        div1 = forms.Panel()
        div1.BackgroundColor = make_color(*BH_MID_GREY)
        div1.Height = 2
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
        self.setback_list.SelectedIndex = setback_default_index; self.setback_list.SelectedIndexChanged += self.on_setback_changed
        self.setback_sel_label = forms.Label()
        self.setback_sel_label.Text = "Selected:  {}".format(setback_default_label)
        self.setback_sel_label.Font = drawing.Font(drawing.FontFamily("Impact"), 14, drawing.FontStyle.Bold)
        self.setback_sel_label.TextColor = make_color(*_SLIDER_SELECTED_FG)
        self.setback_sel_label.TextAlignment = forms.TextAlignment.Center
        div2 = forms.Panel()
        div2.BackgroundColor = make_color(*BH_MID_GREY)
        div2.Height = 2
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
        self.selected_length  = None; self.selected_width   = None
        self.selected_setback = None
        self.Close(False)
def _icon_param_grid_spacing(size=28):
    """Grid spacing: grid lines with intersection dots and dimension arrow."""
    bmp = drawing.Bitmap(size, size, drawing.PixelFormat.Format32bppRgba)
    g = drawing.Graphics(bmp)
    try:
        g.AntiAlias = True
        g.FillRectangle(_icon_brush(BH_BLACK), 0, 0, size, size)
        s = size / 28.0
        pen = _icon_pen(BH_WHITE, 0.8)
        for v in [7, 14, 21]:
            g.DrawLine(pen, int(v*s), int(3*s), int(v*s), int(25*s))
            g.DrawLine(pen, int(3*s), int(v*s), int(25*s), int(v*s))
        for gx in [7, 14, 21]:
            for gy in [7, 14, 21]:
                g.FillEllipse(_icon_brush(BH_RED), int(gx*s)-2, int(gy*s)-2, 4, 4)
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
        g.DrawRectangle(_icon_pen(BH_WHITE, 1.5), drawing.RectangleF(7*s, 4*s, 14*s, 20*s))
        for gx in [10, 14, 18]:
            g.DrawLine(_icon_pen(BH_WHITE, 0.3), int(gx*s), int(5*s), int(gx*s), int(23*s))
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
        g.DrawRectangle(_icon_pen(BH_WHITE, 1.5), drawing.RectangleF(9*s, 3*s, 8*s, 19*s))
        g.DrawLine(_icon_pen(BH_WHITE, 0.3), int(12*s), int(4*s), int(12*s), int(21*s))
        g.DrawLine(_icon_pen(BH_WHITE, 0.3), int(15*s), int(4*s), int(15*s), int(21*s))
        g.DrawLine(_icon_pen(BH_WHITE, 1), int(3*s), int(22*s), int(25*s), int(22*s))
        for hx in range(5, 24, 3):
            g.DrawLine(_icon_pen(BH_WHITE, 0.3), int((hx+2)*s), int(24*s), int(hx*s), int(22*s))
        g.DrawLine(_icon_pen(BH_WHITE, 1), int(4*s), int(3*s), int(22*s), int(3*s))
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
        g.DrawRectangle(_icon_pen(BH_WHITE, 1), drawing.RectangleF(3*s, 5*s, 4*s, 16*s))
        g.DrawRectangle(_icon_pen(BH_WHITE, 1), drawing.RectangleF(21*s, 5*s, 4*s, 16*s))
        g.FillRectangle(_icon_brush(BH_RED, 30), drawing.RectangleF(3*s, 5*s, 22*s, 5*s))
        g.DrawRectangle(_icon_pen(BH_WHITE, 1.5), drawing.RectangleF(3*s, 5*s, 22*s, 5*s))
        g.DrawLine(_icon_pen(BH_WHITE, 0.3), int(5*s), int(7*s), int(23*s), int(7*s))
        g.DrawLine(_icon_pen(BH_WHITE, 0.3), int(5*s), int(9*s), int(23*s), int(9*s))
        g.DrawLine(_icon_pen(BH_ORANGE, 0.8), int(1*s), int(5*s), int(1*s), int(10*s))
        g.DrawLine(_icon_pen(BH_ORANGE, 0.5), int(0*s), int(5*s), int(2*s), int(5*s))
        g.DrawLine(_icon_pen(BH_ORANGE, 0.5), int(0*s), int(10*s), int(2*s), int(10*s))
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
        g.DrawRectangle(_icon_pen(BH_WHITE, 1.2), drawing.RectangleF(10*s, 4*s, 5*s, 18*s))
        g.DrawLine(_icon_pen(BH_WHITE, 0.3), int(12*s), int(5*s), int(12*s), int(21*s))
        g.FillRectangle(_icon_brush(BH_RED, 30), drawing.RectangleF(10*s, 4*s, 5*s, 3*s))
        g.DrawRectangle(_icon_pen(BH_WHITE, 1.2), drawing.RectangleF(10*s, 4*s, 5*s, 3*s))
        g.FillRectangle(_icon_brush(BH_RED, 15), drawing.RectangleF(2*s, 4*s, 8*s, 3*s))
        g.DrawRectangle(_icon_pen(BH_WHITE, 0.8), drawing.RectangleF(2*s, 4*s, 8*s, 3*s))
        g.FillRectangle(_icon_brush(BH_RED, 15), drawing.RectangleF(15*s, 4*s, 11*s, 3*s))
        g.DrawRectangle(_icon_pen(BH_WHITE, 0.8), drawing.RectangleF(15*s, 4*s, 11*s, 3*s))
        g.DrawLine(_icon_pen(BH_ORANGE, 0.8), int(2*s), int(10*s), int(10*s), int(10*s))
        g.DrawLine(_icon_pen(BH_ORANGE, 0.8), int(15*s), int(10*s), int(26*s), int(10*s))
        pen_dash = drawing.Pen(make_color(*BH_WHITE), 0.4)
        try:
            pen_dash.DashStyle = drawing.DashStyle.Dash
        except:
            pass
        g.DrawLine(pen_dash, int(2*s), int(7*s), int(2*s), int(22*s))
        g.DrawLine(pen_dash, int(26*s), int(7*s), int(26*s), int(22*s))
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
        body_panel = forms.Panel()
        body_panel.BackgroundColor = make_color(*dialog_body_bg_rgb())
        body_panel.Padding = drawing.Padding(28, 18, 28, 18)
        def make_row(param_name, value_text, note_text=None, icon_bmp=None):
            row_panel = forms.Panel()
            row_panel.BackgroundColor = make_color(*BH_BLACK_LIFT)
            row_panel.Padding = drawing.Padding(14, 12, 14, 12)
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
            name_col_layout = forms.TableLayout()
            name_col_layout.Spacing = drawing.Size(0, 2)
            if icon_view is not None:
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
                             "{:.2f} m".format(column_height),
                             "Fixed at 0.26 m — standard basement plinth for this model",
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
        div_main = forms.Panel()
        div_main.BackgroundColor = make_color(*DIALOG_ACCENT_BLUE)
        div_main.Height = 3
        boundary_lbl = forms.Label()
        boundary_lbl.Text = "Select building boundary from grid points"
        boundary_lbl.Font = drawing.Font(drawing.FontFamily("Impact"), 16, drawing.FontStyle.Bold)
        boundary_lbl.TextColor = make_color(*BH_WHITE)
        boundary_lbl.TextAlignment = forms.TextAlignment.Center; boundary_lbl.Wrap = forms.WrapMode.Word
        boundary_sub = forms.Label()
        boundary_sub.Text = "Click on the red grid points in the viewport to define your building outline. Close the polyline to finish."
        boundary_sub.Font = drawing.Font(drawing.FontFamily("Georgia"), 10, drawing.FontStyle.Italic)
        boundary_sub.TextColor = make_color(*BH_OFF_WHITE)
        boundary_sub.TextAlignment = forms.TextAlignment.Center; boundary_sub.Wrap = forms.WrapMode.Word
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
        self.list_box.SelectedIndex = default_index; self.list_box.SelectedIndexChanged += self.on_list_changed
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
class FloorCountDialog(forms.Dialog[bool]):
    def __init__(self):
        super(FloorCountDialog, self).__init__()
        self.BackgroundColor = make_color(*BH_BLACK)
        self.selected_upper_floors = 0; self.selected_floor_height = 3.0
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
        div_height = forms.Panel()
        div_height.BackgroundColor = make_color(*DIALOG_ACCENT_ORANGE)
        div_height.Height = 3
        height_title = forms.Label()
        height_title.Text = "FLOOR HEIGHT (applies to ALL floors + roof)"
        height_title.Font = drawing.Font(drawing.FontFamily("Georgia"), 10, drawing.FontStyle.Bold)
        height_title.TextColor = make_color(*BH_OFF_WHITE)
        self._height_values = [3.0, 3.5, 4.0, 4.5]
        tick_layout = forms.TableLayout()
        tick_layout.Spacing = drawing.Size(0, 0)
        tick_row = forms.TableRow()
        for v in self._height_values:
            tl = forms.Label()
            tl.Text = "{:.1f}".format(v) if v != int(v) else "{:.0f}".format(v)
            tl.Font = drawing.Font(drawing.FontFamily("Arial Narrow"), 10, drawing.FontStyle.Bold)
            tl.TextColor = make_color(*_SLIDER_TICK_TEXT)
            tl.TextAlignment = forms.TextAlignment.Center
            tick_row.Cells.Add(forms.TableCell(tl, True))
        tick_layout.Rows.Add(tick_row)
        self.height_slider = forms.Slider()
        self.height_slider.MinValue = 0
        self.height_slider.MaxValue = len(self._height_values) - 1
        self.height_slider.SnapToTick = True; self.height_slider.TickFrequency = 1
        self.height_slider.Orientation = forms.Orientation.Horizontal; self.height_slider.Value = 0
        self.height_slider.ValueChanged += self.on_height_changed
        min_lbl = forms.Label()
        min_lbl.Text = "3 metres"
        min_lbl.Font = drawing.Font(drawing.FontFamily("Arial Narrow"), 10, drawing.FontStyle.Bold)
        min_lbl.TextColor = make_color(*_SLIDER_RANGE_TEXT)
        max_lbl = forms.Label()
        max_lbl.Text = "4.5 metres"
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
    """Single combined dialog shown ONCE for both floor panels and wall panels.; Replaces the two separate FloorPanelsStartDialog / WallPanelsStartDialog popups.
    User sees all info at once and confirms with a single START button.; .confirmed is True when START is clicked, False when ABORT is clicked.
    """
    def __init__(self, num_floors):
        super(PanelGenerationDialog, self).__init__()
        self.BackgroundColor = make_color(*BH_BLACK)
        self.confirmed = False; self.Title = "PANEL GENERATION"
        self.Padding = drawing.Padding(0)
        self.Resizable = False
        self.MinimumSize = drawing.Size(540, 560)
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
        bp = forms.Panel()
        bp.BackgroundColor = make_color(*dialog_body_bg_rgb())
        bp.Padding = drawing.Padding(24, 18, 24, 18)
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
        sep_mid = forms.Panel()
        sep_mid.BackgroundColor = make_color(*BH_MID_GREY)
        sep_mid.Height = 3
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
        sep_btn = forms.Panel()
        sep_btn.BackgroundColor = make_color(*BH_RED)
        sep_btn.Height = 4
        start_btn = forms.Button()
        start_btn.Text = "  > START GENERATING PANELS  "
        start_btn.Font = drawing.Font(drawing.FontFamily("Impact"), 13, drawing.FontStyle.Bold)
        start_btn.BackgroundColor = make_color(*BH_RED)
        start_btn.TextColor = make_color(*BH_PURE_WHITE)
        start_btn.Size = drawing.Size(380, 52)
        start_btn.Click += self.on_start
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
class FloorPanelsStartDialog(PanelGenerationDialog):
    def __init__(self, num_floors):
        super(FloorPanelsStartDialog, self).__init__(num_floors)
class WallPanelsStartDialog(PanelGenerationDialog):
    def __init__(self, num_floors):
        super(WallPanelsStartDialog, self).__init__(num_floors)
class PanelDeletionDialog(forms.Dialog[bool]):
    """Legacy stub — no longer shown per-floor."""
    def __init__(self, floor_label, num_panels):
        super(PanelDeletionDialog, self).__init__()
        self.user_choice = "keep_all"
    def on_select(self, s, e): pass
    def on_keep(self, s, e):   pass
    def on_cancel(self, s, e): pass
class WallPanelDeletionDialog(forms.Dialog[bool]):
    def __init__(self, floor_label, num_panels):
        super(WallPanelDeletionDialog, self).__init__()
        self.user_choice = "keep_all"
    def on_select(self, s, e): pass
    def on_keep(self, s, e):   pass
    def on_cancel(self, s, e): pass
class ElevationExtrusionDialog(forms.Dialog[bool]):
    """Single combined dialog for Elevation Steps 1 & 2.; Layout
    ------; Header (icon + title "ELEVATION EXTRUSION")
    ── STEP 1 block ──────────────────────────────────
      Label: step description; Checkbox: [x] Generate wall arch extrusions  (default ON)
    ── divider ───────────────────────────────────────; ── STEP 2 block ──────────────────────────────────
      Label: step description; Checkbox: [x] Generate vertical arch extrusions (default ON)
    ── divider ───────────────────────────────────────; Buttons: [> GENERATE BOTH]   [SKIP ALL]   [ABORT]
    """
    def __init__(self):
        super(ElevationExtrusionDialog, self).__init__()
        self.BackgroundColor = make_color(*BH_BLACK)
        self.Title = "ELEVATION EXTRUSION"
        self.Padding = drawing.Padding(0)
        self.Resizable = False
        self.MinimumSize = drawing.Size(580, 640)
        self.wall_choice     = "skip"; self.vertical_choice = "skip"
        self.user_cancelled  = False
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
        bp = forms.Panel()
        bp.BackgroundColor = make_color(*dialog_body_bg_rgb())
        bp.Padding = drawing.Padding(26, 18, 26, 18)
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
        self.cb_wall.Text = "  Generate wall arch extrusions"; self.cb_wall.Checked = True
        self.cb_wall.Font = drawing.Font(drawing.FontFamily("Georgia"), 11, drawing.FontStyle.Bold)
        try_set_control_colors(self.cb_wall, text_rgb=BH_WHITE)
        sep1 = forms.Panel()
        sep1.BackgroundColor = make_color(*BH_AMBER)
        sep1.Height = 3
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
        self.cb_vertical.Text = "  Generate vertical arch extrusions"; self.cb_vertical.Checked = True
        self.cb_vertical.Font = drawing.Font(drawing.FontFamily("Georgia"), 11, drawing.FontStyle.Bold)
        try_set_control_colors(self.cb_vertical, text_rgb=BH_WHITE)
        sep2 = forms.Panel()
        sep2.BackgroundColor = make_color(*BH_MID_GREY)
        sep2.Height = 3
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
        ml = forms.TableLayout()
        ml.Spacing = drawing.Size(0, 0)
        ml.Rows.Add(forms.TableRow(forms.TableCell(hp, True)))
        ml.Rows.Add(forms.TableRow(forms.TableCell(bp, True)))
        self.Content = ml
    def on_generate(self, s, e):
        self.wall_choice     = "generate" if self.cb_wall.Checked     else "skip"; self.vertical_choice = "proceed"  if self.cb_vertical.Checked else "skip"
        self.Close(True)
    def on_skip_all(self, s, e):
        self.wall_choice     = "skip"; self.vertical_choice = "skip"
        self.Close(True)
    def on_cancel(self, s, e):
        self.user_cancelled  = True; self.wall_choice     = "skip"
        self.vertical_choice = "skip"
        self.Close(False)
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
class ArchOrientationDialog(forms.Dialog[bool]):
    def __init__(self):
        super(ArchOrientationDialog, self).__init__()
        self.BackgroundColor = make_color(*BH_BLACK)
        self.orientation = "NS"; self.Title = "ARCH ORIENTATION"
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
                cx = x1; step_x = grid_spacing if x2 > x1 else -grid_spacing
                while abs(cx - x2) > 0.01:
                    cx = round(cx + step_x, 4)
                    path.append((cx, y1))
                cy = y1; step_y = grid_spacing if y2 > y1 else -grid_spacing
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
    x1, y1 = c1; x2, y2 = c2
    path = []
    cx, cy = x1, y1; step_x = grid_spacing if x2 > cx else -grid_spacing
    while abs(cx - x2) > 0.01:
        cx = round(cx + step_x, 4)
        path.append((cx, cy))
    step_y = grid_spacing if y2 > cy else -grid_spacing
    while abs(cy - y2) > 0.01:
        cy = round(cy + step_y, 4)
        path.append((cx, cy))
    return path
def ensure_floor_connectivity(selected_coords, grid_spacing, z_level=0, valid_positions=None):
    """Ensure column selections form a connected graph.; Bridge points added automatically are ONLY placed at positions that exist
    in *valid_positions* — i.e. actual beam intersection points on this floor.; If valid_positions is None (legacy call) the old unconstrained behaviour is
    preserved so nothing outside this function breaks.; Parameters
    ----------; selected_coords  : list of (x, y, z) tuples — user-selected column positions
    grid_spacing     : float — grid module size; z_level          : float — Z height for new points
    valid_positions  : set of (x, y) tuples (rounded to 4 dp) representing every
                       beam intersection available on this floor.  Auto-added; bridge points are restricted to this set.
    """
    if not selected_coords:
        return selected_coords, []
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
    while True:
        components = find_connected_components(current_coords, grid_spacing)
        if len(components) <= 1:
            break
        print("\n  CONNECTIVITY WARNING: Disconnected islands detected!")
        existing_positions = set((round(c[0], 4), round(c[1], 4)) for c in current_coords)
        min_path_len = float('inf')
        best_path = []
        for i in range(len(components)):
            for j in range(i + 1, len(components)):
                path = find_shortest_connection_between_components(
                    components[i], components[j], grid_spacing)
                if len(path) < min_path_len:
                    min_path_len = len(path)
                    best_path = path
        added_any = False
        for pos in best_path:
            p_rnd = (round(pos[0], 4), round(pos[1], 4))
            if p_rnd not in existing_positions and _can_add(p_rnd[0], p_rnd[1]):
                existing_positions.add(p_rnd)
                current_coords.append((p_rnd[0], p_rnd[1], z_level))
                all_added.append((p_rnd[0], p_rnd[1], z_level))
                added_any = True
        if not added_any:
            bridged = False
            if allowed is not None:
                min_pair_dist = float('inf')
                ci_best, cj_best = 0, 1
                for i in range(len(components)):
                    for j in range(i + 1, len(components)):
                        for p1 in components[i]:
                            for p2 in components[j]:
                                d = abs(p1[0]-p2[0]) + abs(p1[1]-p2[1])
                                if d < min_pair_dist:
                                    min_pair_dist = d; ci_best, cj_best = i, j
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
def is_point_within_plot(point, plot_length, plot_width, tolerance=0.01):
    x, y = point[0], point[1]
    return -plot_length / 2.0 - tolerance <= x <= plot_length / 2.0 + tolerance and \
           -plot_width / 2.0 - tolerance <= y <= plot_width / 2.0 + tolerance
def is_snapped_point_valid_grid(snapped_point, plot_length, plot_width, grid_spacing, tolerance=0.01):
    x, y = snapped_point[0], snapped_point[1]
    return -plot_length / 2.0 - tolerance <= x <= plot_length / 2.0 + tolerance and \
           -plot_width / 2.0 - tolerance <= y <= plot_width / 2.0 + tolerance
def snap_point_to_grid(point, grid_spacing, eff_length, eff_width):
    x, y = point[0], point[1]
    z = point[2] if len(point) > 2 else 0
    origin_x = -eff_length / 2.0; origin_y = -eff_width / 2.0
    grid_x = round((x - origin_x) / grid_spacing) * grid_spacing + origin_x
    grid_y = round((y - origin_y) / grid_spacing) * grid_spacing + origin_y
    return (round(grid_x, 4), round(grid_y, 4), round(z, 4))
def _cleanup_rectilinear_points(points):
    if not points:
        return []
    cleaned = [points[0]]
    for pt in points[1:]:
        if abs(pt[0] - cleaned[-1][0]) < 0.01 and abs(pt[1] - cleaned[-1][1]) < 0.01:
            continue
        cleaned.append(pt)
    changed = True
    while changed and len(cleaned) >= 3:
        changed = False
        out = [cleaned[0]]
        for i in range(1, len(cleaned) - 1):
            a, b, c = out[-1], cleaned[i], cleaned[i + 1]
            same_x = abs(a[0] - b[0]) < 0.01 and abs(b[0] - c[0]) < 0.01
            same_y = abs(a[1] - b[1]) < 0.01 and abs(b[1] - c[1]) < 0.01
            if same_x or same_y:
                changed = True
                continue
            out.append(b)
        out.append(cleaned[-1])
        cleaned = out
    return cleaned

def _seg_intersects_2d(a, b, c, d):
    def orient(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    def on_seg(p, q, r):
        return min(p[0], r[0]) - 0.01 <= q[0] <= max(p[0], r[0]) + 0.01 and min(p[1], r[1]) - 0.01 <= q[1] <= max(p[1], r[1]) + 0.01
    o1 = orient(a, b, c); o2 = orient(a, b, d); o3 = orient(c, d, a); o4 = orient(c, d, b)
    if abs(o1) < 0.01 and on_seg(a, c, b): return True
    if abs(o2) < 0.01 and on_seg(a, d, b): return True
    if abs(o3) < 0.01 and on_seg(c, a, d): return True
    if abs(o4) < 0.01 and on_seg(c, b, d): return True
    return (o1 > 0) != (o2 > 0) and (o3 > 0) != (o4 > 0)


def _is_simple_closed_rectilinear(points):
    if not points or len(points) < 4:
        return False
    pts = _cleanup_rectilinear_points(points)
    if len(pts) < 4:
        return False
    if abs(pts[0][0] - pts[-1][0]) > 0.01 or abs(pts[0][1] - pts[-1][1]) > 0.01:
        return False
    segs = [(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]
    for i, (a, b) in enumerate(segs):
        if abs(a[0] - b[0]) > 0.01 and abs(a[1] - b[1]) > 0.01:
            return False
        for j, (c, d) in enumerate(segs):
            if j <= i + 1:
                continue
            if i == 0 and j == len(segs) - 1:
                continue
            if _seg_intersects_2d(a, b, c, d):
                return False
    return True


def _poly_area_2d(points):
    if not points or len(points) < 4:
        return 0.0
    area = 0.0
    for i in range(len(points) - 1):
        x1, y1 = points[i][0], points[i][1]
        x2, y2 = points[i + 1][0], points[i + 1][1]
        area += x1 * y2 - x2 * y1
    return abs(area) * 0.5


def _build_closure_candidate(points, grid_spacing, order="xy"):
    if not points or len(points) < 2:
        return points
    first, last = points[0], points[-1]
    if abs(first[0] - last[0]) < 0.01 and abs(first[1] - last[1]) < 0.01:
        return _cleanup_rectilinear_points(points)
    x1, y1 = round(last[0], 4), round(last[1], 4)
    x2, y2 = round(first[0], 4), round(first[1], 4)
    z = last[2] if len(last) > 2 else 0
    closing_points = []
    if order == "xy":
        curr_x = x1; step_x = grid_spacing if x2 > x1 else -grid_spacing
        while abs(curr_x - x2) > 0.01:
            curr_x = round(curr_x + step_x, 4)
            closing_points.append((curr_x, y1, z))
        curr_y = y1; step_y = grid_spacing if y2 > y1 else -grid_spacing
        while abs(curr_y - y2) > 0.01:
            curr_y = round(curr_y + step_y, 4)
            closing_points.append((x2, curr_y, z))
    else:
        curr_y = y1; step_y = grid_spacing if y2 > y1 else -grid_spacing
        while abs(curr_y - y2) > 0.01:
            curr_y = round(curr_y + step_y, 4)
            closing_points.append((x1, curr_y, z))
        curr_x = x1; step_x = grid_spacing if x2 > x1 else -grid_spacing
        while abs(curr_x - x2) > 0.01:
            curr_x = round(curr_x + step_x, 4)
            closing_points.append((curr_x, y2, z))
    result = list(points) + closing_points
    if abs(result[-1][0] - first[0]) > 0.01 or abs(result[-1][1] - first[1]) > 0.01:
        result.append(first)
    return _cleanup_rectilinear_points(result)


def close_polyline_with_90_degrees(points, grid_spacing, eff_length=None, eff_width=None):
    if not points or len(points) < 2:
        return points
    candidates = []
    for order in ("xy", "yx"):
        cand = _build_closure_candidate(points, grid_spacing, order)
        if not cand:
            continue
        simple = _is_simple_closed_rectilinear(cand)
        area = _poly_area_2d(cand)
        score = area
        if simple and eff_length is not None and eff_width is not None:
            try:
                score = len(get_grid_points_inside_polyline(cand, grid_spacing, eff_length, eff_width, points[0][2] if len(points[0]) > 2 else 0))
            except Exception:
                score = area
        candidates.append((1 if simple else 0, score, area, cand))
    if candidates:
        candidates.sort(key=lambda x: (x[0], x[1], x[2]), reverse=True)
        return candidates[0][3]
    return _build_closure_candidate(points, grid_spacing, "xy")
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
    origin_x = -eff_length / 2.0; origin_y = -eff_width / 2.0
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
    closed_points = close_polyline_with_90_degrees(drawn_points, grid_spacing, effective_length, effective_width)
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
    closed_points = close_polyline_with_90_degrees(drawn_points, grid_spacing, effective_length, effective_width)
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
    _enforce_wireframe()
    sc.doc.Views.Redraw()
    return boundary, boundary_2d, boundary_3d
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
THEME_PLOT_LENGTH = {"icon": "📐", "header": (0, 120, 60), "bg": (51, 55, 52)}
THEME_PLOT_WIDTH = {"icon": "📏", "header": (0, 100, 80), "bg": (50, 54, 52)}
THEME_GRID_SPACING = {"icon": "🔲", "header": (25, 25, 112), "bg": (50, 51, 56)}
THEME_COLUMN_WIDTH = {"icon": "🏛️", "header": (139, 69, 19), "bg": (56, 53, 50)}
THEME_BEAM_WIDTH = {"icon": "🪵", "header": (101, 67, 33), "bg": (55, 52, 49)}
THEME_GRID_EXTENSION = {"icon": "↔️", "header": (0, 100, 148), "bg": (49, 53, 56)}
THEME_FLOOR_HEIGHT = {"icon": "🏗️", "header": (180, 50, 50), "bg": (56, 51, 51)}
THEME_ROOF = {"icon": "🏠", "header": (120, 60, 20), "bg": (56, 53, 51)}
THEME_BASEMENT = {"icon": "🧱", "header": (100, 60, 30), "bg": (55, 52, 49)}
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
    _enforce_wireframe()
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
    _enforce_wireframe()
    sc.doc.Views.Redraw()
def draw_plot_dimensions(Building, north_side, plot_length, plot_width):
    layer_name = "Plot_Dimensions"
    if not rs.IsLayer(layer_name):
        rs.AddLayer(layer_name, (50, 50, 50))
    half_l, half_w = plot_length / 2.0, plot_width / 2.0
    lt = "{} m".format(int(plot_length) if plot_length == int(plot_length) else plot_length)
    wt = "{} m".format(int(plot_width)  if plot_width  == int(plot_width)  else plot_width)
    txt_h = 3.0
    tick  = 1.5    # tick mark half-length
    do    = 5.0    # dimension line offset from plot edge
    ls = "Bottom" if north_side == "Top" else ("Top" if north_side == "Bottom" else "Bottom")
    ws = "Left"   if north_side == "Right" else ("Right" if north_side == "Left" else "Left")
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
    _enforce_wireframe()
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
    _enforce_wireframe()
    rs.Redraw()
    return True
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
            best_remainder = r; best = c
    return float(best)
def auto_calc_grid_extension(setback):
    """Return beam overhang/extension beyond the column grid in metres."""; raw = setback - 0.5
    return round(max(1.0, min(2.0, raw)) * 2) / 2
def _gk_fire_minutes(total_height_m):
    """Return (Gebäudeklasse, fire_resistance_minutes) for a timber building.
    Per MBO / BauO NRW 2018 and MHolzBauRL 2024:
      GK1-3  h ≤ 7 m  → no fire requirement (0 min); GK4    7m < h ≤ 13m → hochfeuerhemmend R60 (60 min)
      GK5    13m < h ≤ 22m → feuerbeständig R90 (90 min)
    """
    if total_height_m <= 7.0:
        return 3, 0
    elif total_height_m <= 13.0:
        return 4, 60
    else:
        return 5, 90
def auto_calc_column_width(grid_spacing, num_floors=3):
    """Return the UNIFIED square section size for BOTH columns and beams.; Columns and beams share the same square dimension — the governing check
    across both elements determines the single b value.
    Governs are checked in order:
      1. Beam bending  (EC5 §6.1.6) — b³/6 ≥ M/fm,d; 2. Beam deflection L/300       — b⁴ ≥ 5qL³×12×300/(384E)
      3. Column buckling (EC5 §6.3.2) — Euler stability with kc; 4. Fire R60 column (EC5-1-2)  — b ≥ 200mm, residual ≥ 80mm (4 sides)
      5. Fire R60 beam   (EC5-1-2)  — b ≥ 160mm, residual ≥ 80mm (3 sides)
    All GL24h:  fm,g,k=24 MPa  fc,0,g,k=24 MPa  E_mean=11600 MPa  E_0,05=9400 MPa
                kmod=0.8  γ_M=1.25  β_n=0.7 mm/min
    Returns width (= depth) in metres, rounded to 20 mm.; """
    import math
    fm_d   = 24.0 * 0.8 / 1.25   # 15.36 MPa bending
    fc0gd  = 24.0 * 0.8 / 1.25   # 15.36 MPa compression parallel
    E      = 11600.0               # MPa E_mean
    E05    = 9400.0                # MPa 5th-percentile
    betac  = 0.1                   # glulam imperfection factor
    gs     = grid_spacing
    L      = gs * 1000.0           # mm span
    q      = 5.0 * gs              # N/mm (5 kN/m² × tributary width = gs)
    M_Nmm  = q * L ** 2 / 8.0     # N·mm  (q in N/mm, L in mm)
    W_req  = M_Nmm / fm_d         # mm³
    b_bend = (6.0 * W_req) ** (1.0 / 3.0)   # mm
    b_defl = (5.0 * q * L ** 3 * 12.0 * 300.0 / (384.0 * E)) ** 0.25  # mm
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
    b_gov = max(b_bend, b_defl, b_col, b_fire_col, b_fire_bm)
    b_std = math.ceil(b_gov / 20.0) * 20      # round up to 20 mm
    return round(b_std / 1000.0, 3)           # metres
def auto_calc_beam_width(grid_spacing, num_floors=3):
    """Return (width_m, depth_m) for primary beam — same square dimension as column.; Beams and columns share one square size computed by auto_calc_column_width.
    Returns a tuple (b, b) so existing callers using (width, depth) still work.; """
    b = auto_calc_column_width(grid_spacing, num_floors)
    return b, b   # square: width = depth
def calculate_wooden_beam_depth(span, beam_width, num_floors=3):
    """Return beam depth = beam_width (square section).; auto_calc_beam_width returns (b, b) for square; depth = width.
    """
    _, depth = auto_calc_beam_width(span, num_floors)
    return round(depth * 20.0) / 20.0
def get_grid_spacing(Building):
    """Calculate and store the optimal grid spacing from plot dimensions.; Called early in main() before get_column_inputs.
    """
    plot_length = Building["plot"]["length"]
    plot_width  = Building["plot"]["width"]
    Building["grid"]["spacing"] = auto_calc_grid_spacing(plot_length, plot_width)
    return True
def get_column_inputs(Building):
    """Show the StructuralAndBoundaryDialog and store column/beam sizing.; Uses unified square section (beam = column) based on EC5 + EC5-1-2.
    """
    plot_length  = Building["plot"]["length"]
    plot_width   = Building["plot"]["width"]
    grid_spacing = Building["grid"]["spacing"]
    num_floors   = Building["floors"].get("num_upper_floors", 2) + 2
    column_width = auto_calc_column_width(grid_spacing, num_floors)
    column_height = 0.26
    beam_width, _ = auto_calc_beam_width(grid_spacing, num_floors)
    grid_extension = auto_calc_grid_extension(Building["plot"].get("setback", 3.0))
    est_h = 0.26 + num_floors * 3.5
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
    _enforce_wireframe()
    rs.Redraw()
    return True
def _count_complete_grid_cells(coords, gs):
    """Count how many complete gs x gs grid cells are formed by the given coords."""
    pts_2d = set()
    for c in coords:
        pts_2d.add((round(c[0], 4), round(c[1], 4)))
    cell_count = 0
    for (px, py) in pts_2d:
        se = (round(px + gs, 4), round(py, 4))
        ne = (round(px + gs, 4), round(py + gs, 4))
        nw = (round(px, 4),      round(py + gs, 4))
        if se in pts_2d and ne in pts_2d and nw in pts_2d:
            cell_count += 1
    return cell_count
def _expand_to_minimum_cells(coords, gs, valid_grid_positions, min_cells=8):
    """Expand the user's selection bounding box outward until min_cells complete; grid cells are enclosed.  Clamped to valid plot grid.  Safety: 30-iteration cap."""
    if not coords or not valid_grid_positions:
        return list(coords)
    z_level = coords[0][2]
    tol = 0.001
    xs = [round(c[0], 4) for c in coords]
    ys = [round(c[1], 4) for c in coords]
    x_min, x_max = min(xs), max(xs)
    y_min, y_max = min(ys), max(ys)
    all_vx = [p[0] for p in valid_grid_positions]
    all_vy = [p[1] for p in valid_grid_positions]
    grid_x_min, grid_x_max = min(all_vx), max(all_vx)
    grid_y_min, grid_y_max = min(all_vy), max(all_vy)
    for iteration in range(30):
        expanded_pts = set()
        for (vx, vy) in valid_grid_positions:
            if vx >= x_min - tol and vx <= x_max + tol and \
               vy >= y_min - tol and vy <= y_max + tol:
                expanded_pts.add((round(vx, 4), round(vy, 4)))
        expanded_coords = [(px, py, z_level) for (px, py) in expanded_pts]
        n_cells = _count_complete_grid_cells(expanded_coords, gs)
        if n_cells >= min_cells:
            print("  Minimum {} grid cells reached ({} cells) after {} expansion step(s).".format(
                min_cells, n_cells, iteration))
            return expanded_coords
        if (x_min <= grid_x_min + tol and x_max >= grid_x_max - tol and
                y_min <= grid_y_min + tol and y_max >= grid_y_max - tol):
            print("  Full grid reached ({} cells). Cannot expand further.".format(n_cells))
            return expanded_coords
        x_min = max(grid_x_min, round(x_min - gs, 4))
        x_max = min(grid_x_max, round(x_max + gs, 4))
        y_min = max(grid_y_min, round(y_min - gs, 4))
        y_max = min(grid_y_max, round(y_max + gs, 4))
    expanded_pts = set()
    for (vx, vy) in valid_grid_positions:
        if vx >= x_min - tol and vx <= x_max + tol and \
           vy >= y_min - tol and vy <= y_max + tol:
            expanded_pts.add((round(vx, 4), round(vy, 4)))
    return [(px, py, z_level) for (px, py) in expanded_pts]
def select_column_points_floor1(Building):
    selected_coords = draw_selection_polyline_for_columns(Building, z_level=0)
    if not selected_coords:
        return False
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
    MIN_CELLS = 8
    n_cells = _count_complete_grid_cells(selected_coords, gs)
    print("  User selection: {} grid points, {} complete grid cells.".format(
        len(selected_coords), n_cells))
    if n_cells >= MIN_CELLS:
        print("  OK — minimum {} cells satisfied.".format(MIN_CELLS))
    else:
        print("  BELOW MINIMUM — need {} cells, have {}. Auto-expanding...".format(
            MIN_CELLS, n_cells))
        selected_coords = _expand_to_minimum_cells(
            selected_coords, gs, valid_grid_positions, MIN_CELLS)
        n_cells_new = _count_complete_grid_cells(selected_coords, gs)
        print("  After expansion: {} grid points, {} complete grid cells.".format(
            len(selected_coords), n_cells_new))
    updated_coords, added_coords = ensure_floor_connectivity(
        selected_coords, gs, z_level=0, valid_positions=valid_grid_positions)
    Building["grid"]["base_shape_is_proper_L"] = _is_proper_l_shape_selection(updated_coords, gs)
    if Building["grid"]["base_shape_is_proper_L"]:
        print("  Detected proper L-shape footprint. Applying minimum arm-thickness rule only for this shape.")
        updated_coords, _ = enforce_min_arm_thickness_for_proper_L(
            updated_coords, gs, z_level=0, valid_positions=valid_grid_positions, min_grid_lines=3)
        updated_coords, _ = repair_orphan_columns_for_l_shape(
            updated_coords, gs, z_level=0, valid_positions=valid_grid_positions)
    Building["grid"]["selected_column_points"] = []
    Building["grid"]["selected_points_per_floor"] = [[]]
    Building["grid"]["selected_coords_per_floor"] = [updated_coords]
    _enforce_wireframe()
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
                        _apply_material(column_brep, _mat_timber())
                        floor_columns.append(column_brep)
                        floor_top_points.append((x, y, z + floor_height))
            rs.DeleteObject(bottom_profile)
    Building["structure"]["columns"]["objects"].extend(floor_columns)
    Building["structure"]["columns"]["objects_per_floor"].append(floor_columns)
    Building["structure"]["columns"]["top_points_per_floor"].append(floor_top_points)
    print("  {} columns: {} at Z={:.2f} to Z={:.2f}".format(floor_label, len(floor_columns), base_z, base_z + floor_height))
    _enforce_wireframe()
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
    """Create floor beams as single continuous members including cantilever overhangs.; Each beam runs from (start - extension) to (end + extension) as ONE Brep object,
    eliminating the visible seam/gap that appears when extension is a separate piece.; Extension rule: add an overhang at a segment endpoint when there is NO column
    beyond that endpoint in the same row direction. This works correctly for both; rectangular and irregular (L-shaped, stepped) floor plans.
    Specifically:
      - Y-direction beam at fixed X, segment ss→se:
          extend at ss if (ss - grid_spacing) is not in this X-row; extend at se if (se + grid_spacing) is not in this X-row
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
    for x in x_coords:
        row_y = sorted([round(pt[1], 4) for pt in floor_top_points if abs(pt[0] - x) < tol])
        row_y_set = set(row_y)
        if not row_y:
            continue
        for ss, se in find_continuous_segments(row_y, grid_spacing, tol):
            ext_start = actual_ext if (round(ss - grid_spacing, 4) not in row_y_set) else 0.0
            ext_end   = actual_ext if (round(se + grid_spacing, 4) not in row_y_set) else 0.0
            y_from = ss - ext_start; y_to   = se + ext_end
            if abs(y_to - y_from) < tol:
                continue
            b = create_single_beam(
                rg.Point3d(x, y_from, beam_z),
                rg.Point3d(x, y_to,   beam_z),
                beam_width, beam_depth)
            if b:
                rs.ObjectLayer(b, "Wooden_Beam")
                _apply_material(b, _mat_timber())
                floor_beams.append(b)
    for y in y_coords:
        row_x = sorted([round(pt[0], 4) for pt in floor_top_points if abs(pt[1] - y) < tol])
        row_x_set = set(row_x)
        if not row_x:
            continue
        for ss, se in find_continuous_segments(row_x, grid_spacing, tol):
            ext_start = actual_ext if (round(ss - grid_spacing, 4) not in row_x_set) else 0.0
            ext_end   = actual_ext if (round(se + grid_spacing, 4) not in row_x_set) else 0.0
            x_from = ss - ext_start; x_to   = se + ext_end
            if abs(x_to - x_from) < tol:
                continue
            b = create_single_beam(
                rg.Point3d(x_from, y, beam_z),
                rg.Point3d(x_to,   y, beam_z),
                beam_width, beam_depth)
            if b:
                rs.ObjectLayer(b, "Wooden_Beam")
                _apply_material(b, _mat_timber())
                floor_beams.append(b)
    all_intersections = [
        (x, y, beam_z) for x in x_coords for y in y_coords
        if (round(x, 4), round(y, 4)) in column_positions
    ]
    Building["structure"]["plinth_beams"]["objects"].extend(floor_beams)
    Building["structure"]["plinth_beams"]["objects_per_floor"].append(floor_beams)
    Building["structure"]["plinth_beams"]["intersection_points_per_floor"].append(all_intersections)
    print("  {} beams: {} at Z={:.2f}".format(floor_label, len(floor_beams), beam_z))
    _enforce_wireframe()
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
    _enforce_wireframe()
    rs.Redraw()
    return grid_point_ids, floor_z
def select_columns_from_grid(Building, floor_label, grid_point_ids, all_intersections, z_level):
    available_points = [(pt[0], pt[1], z_level) for pt in all_intersections]
    selected_coords = select_columns_by_polyline_for_upper_floor(Building, floor_label, available_points, z_level)
    if not selected_coords:
        return []
    valid_beam_positions = set((round(pt[0], 4), round(pt[1], 4)) for pt in all_intersections)
    updated_coords, added_coords = ensure_floor_connectivity(
        selected_coords, Building["grid"]["spacing"], z_level,
        valid_positions=valid_beam_positions)
    if _is_proper_l_shape_selection(updated_coords, Building["grid"]["spacing"]):
        updated_coords, _ = enforce_min_arm_thickness_for_proper_L(
            updated_coords, Building["grid"]["spacing"], z_level,
            valid_positions=valid_beam_positions, min_grid_lines=3)
        updated_coords, _ = repair_orphan_columns_for_l_shape(
            updated_coords, Building["grid"]["spacing"], z_level,
            valid_positions=valid_beam_positions)
    Building["grid"]["selected_points_per_floor"].append([])
    Building["grid"]["selected_coords_per_floor"].append(updated_coords)
    _enforce_wireframe()
    rs.Redraw()
    return updated_coords
def cleanup_layer(layer_name):
    if rs.IsLayer(layer_name):
        objs = rs.ObjectsByLayer(layer_name)
        if objs:
            rs.DeleteObjects(objs)
        rs.DeleteLayer(layer_name)
def _cascade_seed(plot_length, plot_width, floor_num):
    """Deterministic seed — same building always gives same pixelation."""
    return int(abs(plot_length * 100 + plot_width * 37 + floor_num * 13)) % 9999
def auto_cascade_columns(previous_intersections, floor_num, grid_spacing,
                         plot_length=None, plot_width=None):
    """S'lowtecture cellular automata cascade for stepped terrace housing.
    Cell states (each 2x2 column square = one cubic room):
      B (BUILT)  — structural room, fully enclosed; G (GARDEN) — open terrace, adjacent to built zone
      E (EMPTY)  — void, no structure
    Rules (from s'lowtecture game logic):
    1. Each BUILT cell is surrounded by GARDEN/EMPTY neighbourhood cells; 2. Cascade: cells near SW perimeter become EMPTY as floor rises
    3. GARDEN cells appear at the Built/Empty boundary (terraces); 4. BUILT cells must stay connected — isolated clusters downgraded
    5. GARDEN cells must be adjacent to at least one BUILT cell; 6. Min 2×2 BUILT cells guaranteed at NE corner (deepest terrace)
    7. Pixelation notches at built boundary create informal silhouette; 8. Fully deterministic from plot dimensions
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
    cells = [['B'] * cy for _ in range(cx)]
    for cix in range(cx):
        for ciy in range(cy):
            dist_w = cix   # distance from West edge in cells
            dist_s = ciy   # distance from South edge in cells
            min_dist = min(dist_w, dist_s)
            if min_dist < floor_num - 1:
                cells[cix][ciy] = 'E'
            elif min_dist == floor_num - 1:
                cells[cix][ciy] = 'G' if pick(cix * 7 + ciy, 3) < 2 else 'E'
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
    for cix in range(cx - 2, cx):
        for ciy in range(cy - 2, cy):
            cells[cix][ciy] = 'B'
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
    for cix in range(cx):
        for ciy in range(cy):
            if cells[cix][ciy] == 'B' and (cix, ciy) not in visited_built:
                cells[cix][ciy] = 'G'
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
    built_cols = set()
    for cix in range(cx):
        for ciy in range(cy):
            if cells[cix][ciy] == 'B':
                for dix in range(2):
                    for diy in range(2):
                        built_cols.add((cix + dix, ciy + diy))
    xi_map = {round(x, 4): i for i, x in enumerate(xs)}
    yi_map = {round(y, 4): i for i, y in enumerate(ys)}
    result = []
    for pt in previous_intersections:
        ix = xi_map.get(round(pt[0], 4))
        iy = yi_map.get(round(pt[1], 4))
        if ix is not None and iy is not None and (ix, iy) in built_cols:
            result.append(pt)
    return result if result else list(previous_intersections)


def _get_complete_grid_cells_from_coords(coords, grid_spacing):
    if not coords:
        return set()
    pts = set((round(c[0],4), round(c[1],4)) for c in coords)
    gs = round(grid_spacing, 4)
    cells = set()
    for (x, y) in list(pts):
        x2 = round(x + gs, 4); y2 = round(y + gs, 4)
        if (x2, y) in pts and (x, y2) in pts and (x2, y2) in pts:
            cells.add((round(x,4), round(y,4)))
    return cells

def _is_proper_l_shape_selection(coords, grid_spacing):
    """Return True only for a clean orthogonal L footprint.
    Detects a bounding rectangle with one contiguous rectangular corner notch.
    """
    cells = _get_complete_grid_cells_from_coords(coords, grid_spacing)
    if len(cells) < 3:
        return False
    xs = sorted(set(c[0] for c in cells))
    ys = sorted(set(c[1] for c in cells))
    if len(xs) < 2 or len(ys) < 2:
        return False
    bbox = set((x, y) for x in xs for y in ys)
    missing = bbox - cells
    if not missing:
        return False
    mxs = sorted(set(m[0] for m in missing))
    mys = sorted(set(m[1] for m in missing))
    rect_missing = set((x, y) for x in mxs for y in mys)
    if missing != rect_missing:
        return False
    touch_left = abs(min(mxs) - min(xs)) < 0.001
    touch_right = abs(max(mxs) - max(xs)) < 0.001
    touch_bottom = abs(min(mys) - min(ys)) < 0.001
    touch_top = abs(max(mys) - max(ys)) < 0.001
    return ((touch_left ^ touch_right) and (touch_bottom ^ touch_top))

def enforce_min_arm_thickness_for_proper_L(coords, grid_spacing, z_level, valid_positions=None, min_grid_lines=3):
    """For a proper L-shape only, ensure each arm has at least min_grid_lines
    of column grid lines (equivalent to min_grid_lines-1 cell thickness).
    This is intentionally scoped only to the classic bbox-minus-corner L case.
    It adds the minimum cells adjacent to the notch and leaves all other shapes unchanged.
    """
    if not coords:
        return list(coords), []
    if not _is_proper_l_shape_selection(coords, grid_spacing):
        return list(coords), []
    min_cells = max(1, int(min_grid_lines) - 1)
    cells = _get_complete_grid_cells_from_coords(coords, grid_spacing)
    if not cells:
        return list(coords), []
    xs = sorted(set(c[0] for c in cells))
    ys = sorted(set(c[1] for c in cells))
    bbox = set((x, y) for x in xs for y in ys)
    missing = bbox - cells
    if not missing:
        return list(coords), []
    mxs = sorted(set(m[0] for m in missing))
    mys = sorted(set(m[1] for m in missing))
    # guard: only rectangular notch
    rect_missing = set((x, y) for x in mxs for y in mys)
    if missing != rect_missing:
        return list(coords), []

    touch_left = abs(min(mxs) - min(xs)) < 0.001
    touch_right = abs(max(mxs) - max(xs)) < 0.001
    touch_bottom = abs(min(mys) - min(ys)) < 0.001
    touch_top = abs(max(mys) - max(ys)) < 0.001

    x_to_i = {x:i for i,x in enumerate(xs)}
    y_to_i = {y:i for i,y in enumerate(ys)}
    miss_ix0, miss_ix1 = x_to_i[min(mxs)], x_to_i[max(mxs)]
    miss_iy0, miss_iy1 = y_to_i[min(mys)], y_to_i[max(mys)]
    ncols, nrows = len(xs), len(ys)

    # occupied arm thickness in cell columns / rows
    if touch_right and touch_top:       # classic L: left arm + bottom arm
        arm_x = miss_ix0
        arm_y = miss_iy0
        add_x_side, add_y_side = 'left', 'bottom'
    elif touch_left and touch_top:      # mirrored horizontally: right arm + bottom arm
        arm_x = ncols - (miss_ix1 + 1)
        arm_y = miss_iy0
        add_x_side, add_y_side = 'right', 'bottom'
    elif touch_right and touch_bottom:  # rotated: left arm + top arm
        arm_x = miss_ix0
        arm_y = nrows - (miss_iy1 + 1)
        add_x_side, add_y_side = 'left', 'top'
    elif touch_left and touch_bottom:   # rotated/mirrored: right arm + top arm
        arm_x = ncols - (miss_ix1 + 1)
        arm_y = nrows - (miss_iy1 + 1)
        add_x_side, add_y_side = 'right', 'top'
    else:
        return list(coords), []

    added_cells = set()
    # shrink notch only as much as needed to get minimum arm thickness
    need_x = max(0, min_cells - arm_x)
    need_y = max(0, min_cells - arm_y)

    for step in range(need_x):
        if add_x_side == 'left':
            xi = miss_ix0 + step
        else:
            xi = miss_ix1 - step
        if xi < 0 or xi >= ncols:
            continue
        for y in mys:
            added_cells.add((xs[xi], y))

    for step in range(need_y):
        if add_y_side == 'bottom':
            yi = miss_iy0 + step
        else:
            yi = miss_iy1 - step
        if yi < 0 or yi >= nrows:
            continue
        for x in mxs:
            added_cells.add((x, ys[yi]))

    # don't add cells outside valid plot/grid positions when converted to corners
    ptset = set((round(c[0],4), round(c[1],4)) for c in coords)
    allowed = set((round(px,4), round(py,4)) for px, py in valid_positions) if valid_positions else None
    added_pts = []
    gs = round(grid_spacing,4)
    for cx, cy in sorted(added_cells):
        corners = [
            (round(cx,4), round(cy,4)),
            (round(cx + gs,4), round(cy,4)),
            (round(cx,4), round(cy + gs,4)),
            (round(cx + gs,4), round(cy + gs,4)),
        ]
        if allowed is not None and any(c not in allowed for c in corners):
            continue
        for c in corners:
            if c not in ptset:
                ptset.add(c)
                added_pts.append((c[0], c[1], z_level))
    if added_pts:
        print("  Proper L-shape arm thickness fix added {} support column points (min {} grid lines per arm).".format(len(added_pts), min_grid_lines))
    return [(x, y, z_level) for (x, y) in sorted(ptset)], added_pts

def repair_orphan_columns_for_l_shape(coords, grid_spacing, z_level, valid_positions=None):
    """Special-case repair only for proper L-shape selections.
    Adds the minimum missing support corners needed to convert orphan columns
    into complete bays, then removes any remaining unsupported lone columns.
    This intentionally avoids global flood-filling of the whole bounding box.
    """
    if not coords:
        return list(coords), []
    if not _is_proper_l_shape_selection(coords, grid_spacing):
        return list(coords), []
    pts = set((round(c[0], 4), round(c[1], 4)) for c in coords)
    allowed = set((round(px, 4), round(py, 4)) for px, py in valid_positions) if valid_positions else None
    gs = round(grid_spacing, 4)

    def participating_points(ptset):
        parts = set()
        for (x, y) in list(ptset):
            corners = [(round(x,4), round(y,4)),
                       (round(x + gs,4), round(y,4)),
                       (round(x,4), round(y + gs,4)),
                       (round(x + gs,4), round(y + gs,4))]
            if all(c in ptset for c in corners):
                parts.update(corners)
        return parts

    added = []
    parts = participating_points(pts)
    orphans = [p for p in pts if p not in parts]
    for (x, y) in sorted(orphans):
        base_candidates = [
            (x, y),
            (round(x - gs,4), y),
            (x, round(y - gs,4)),
            (round(x - gs,4), round(y - gs,4)),
        ]
        best_missing = None
        for bx, by in base_candidates:
            corners = [(round(bx,4), round(by,4)),
                       (round(bx + gs,4), round(by,4)),
                       (round(bx,4), round(by + gs,4)),
                       (round(bx + gs,4), round(by + gs,4))]
            present_count = sum(1 for c in corners if c in pts)
            if present_count != 3 or (x, y) not in corners:
                continue
            missing = [c for c in corners if c not in pts][0]
            if allowed is not None and missing not in allowed:
                continue
            best_missing = missing
            break
        if best_missing and best_missing not in pts:
            pts.add(best_missing)
            added.append((best_missing[0], best_missing[1], z_level))

    parts = participating_points(pts)
    cleaned = [(x, y, z_level) for (x, y) in sorted(pts) if (x, y) in parts]
    if not cleaned:
        cleaned = [(x, y, z_level) for (x, y) in sorted(pts)]
    if added:
        print("  L-shape repair added {} support columns to complete orphan bays.".format(len(added)))
    removed = len(pts) - len(set((round(c[0],4), round(c[1],4)) for c in cleaned))
    if removed > 0:
        print("  L-shape repair removed {} unsupported lone columns.".format(removed))
    return cleaned, added

def enforce_closed_rooms(coords, grid_spacing, z_level, valid_positions=None):
    """Post-process: remove any column not forming a complete 2x2 closed cell.; Runs iteratively until stable. Called after ensure_floor_connectivity to
    strip out any single bridge columns it added that don't close a room.; """
    if not coords:
        return coords
    current = list(coords)
    for _ in range(len(coords)):  # max passes
        pts_set = set((round(c[0],4), round(c[1],4)) for c in current)
        participating = set()
        for (px, py) in pts_set:
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
    _enforce_wireframe()
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
    gs = Building["grid"]["spacing"]
    pl = Building["plot"]["length"]
    pw = Building["plot"]["width"]
    cascaded_intersections = auto_cascade_columns(previous_intersections, floor_num, gs, pl, pw)
    if not cascaded_intersections:
        cleanup_layer(grid_label)
        return None, None
    selected_coords = [(pt[0], pt[1], grid_z) for pt in cascaded_intersections]
    valid_beam_positions = set((round(pt[0], 4), round(pt[1], 4)) for pt in previous_intersections)
    updated_coords, _ = ensure_floor_connectivity(
        selected_coords, gs, grid_z, valid_positions=valid_beam_positions)
    if Building.get("grid", {}).get("base_shape_is_proper_L", False):
        updated_coords, _ = enforce_min_arm_thickness_for_proper_L(
            updated_coords, gs, grid_z, valid_positions=valid_beam_positions, min_grid_lines=3)
        updated_coords, _ = repair_orphan_columns_for_l_shape(
            updated_coords, gs, grid_z, valid_positions=valid_beam_positions)
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
    _enforce_wireframe()
    rs.Redraw()
    print("  {} complete — auto-cascaded inward {} m on S+W sides.".format(floor_label, gs * floor_num))
    print_section_footer()
    return floor_top_points, all_intersections
def process_roof(Building, previous_intersections):
    grid_label = "Roof_Grid"
    print_section_header("BUILDING ROOF")
    cleanup_all_temporary_geometry()
    grid_points, grid_z = generate_intersection_grid_from_floor(Building, grid_label, previous_intersections)
    num_upper = Building["floors"]["num_upper_floors"]
    gs = Building["grid"]["spacing"]
    pl = Building["plot"]["length"]
    pw = Building["plot"]["width"]
    roof_floor_num = num_upper + 1  # one more step inward than last upper floor
    cascaded_intersections = auto_cascade_columns(previous_intersections, roof_floor_num, gs, pl, pw)
    if not cascaded_intersections:
        cascaded_intersections = previous_intersections
    selected_coords = [(pt[0], pt[1], grid_z) for pt in cascaded_intersections]
    valid_beam_positions = set((round(pt[0], 4), round(pt[1], 4)) for pt in previous_intersections)
    updated_coords, _ = ensure_floor_connectivity(
        selected_coords, gs, grid_z, valid_positions=valid_beam_positions)
    if Building.get("grid", {}).get("base_shape_is_proper_L", False):
        updated_coords, _ = enforce_min_arm_thickness_for_proper_L(
            updated_coords, gs, grid_z, valid_positions=valid_beam_positions, min_grid_lines=3)
        updated_coords, _ = repair_orphan_columns_for_l_shape(
            updated_coords, gs, grid_z, valid_positions=valid_beam_positions)
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
    _enforce_wireframe()
    rs.Redraw()
    print("  ROOF complete — auto-cascaded inward {} m on S+W sides.".format(gs * roof_floor_num))
    print_section_footer()
    return roof_top_points, roof_intersections
def get_panel_cells_from_beams(Building, floor_top_points, extension, floor_index):
    if not floor_top_points:
        return []
    gs = Building["grid"]["spacing"]
    bd = Building["structure"]["plinth_beams"]["depth"]
    bz = floor_top_points[0][2]
    pz = bz + bd; tol = 0.01
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
CLT_LAYERS = [
    ("CLT_Structural", 0.080, (123, 79,  38),  "Brettsperrholz 3-layer CLT DIN EN 16351 §5.1"),
    ("Insulation",     0.020, ( 80,160, 200),  "Trittschalldaemmung EPS-T DIN 4109-33 §4.2"),
    ("Membrane",       0.005, (190,190, 190),  "Trennlage PE-Folie DIN 18560-2 §4.1"),
    ("Screed",         0.035, (210,200, 175),  "Zementestrich DIN 18560-2 §7.3"),
    ("Parkett",        0.010, (184,120,  16),  "Mehrschichtparkett DIN EN 13756"),
]
CLT_TOTAL_M = sum(t for _, t, _, _ in CLT_LAYERS)   # 0.150 m
WALL_LAYERS = [
    ("Ext_Cladding",      0.015, (160, 120,  70),  "Laerche Holzschalung DIN 68800-2"),
    ("Wind_Barrier",      0.002, (120, 180, 120),  "Diffusion-open membrane DIN 4108-7"),
    ("Insulation",        0.140, (240, 220, 100),  "MW 035 Mineralwolle GEG 2024 / DIN EN 13162"),
    ("Vapour_Barrier",    0.001, (100, 160, 220),  "PE-Folie sd>=100m DIN 4108-3"),
    ("Plasterboard",      0.012, (240, 235, 230),  "Gipskartonplatte 12mm DIN 18180"),
]
WALL_TOTAL_M = sum(t for _, t, _, _ in WALL_LAYERS)   # 0.170 m
SCHUCO_WIN_FRAME_WIDTH   = 0.050   # 50mm visible frame — AWS 75
SCHUCO_WIN_FRAME_DEPTH   = 0.075   # 75mm profile depth — AWS 75
SCHUCO_WIN_TRANSOM_H     = 0.060   # 60mm horizontal Kämpfer bar
SCHUCO_WIN_TRANSOM_RATIO = 0.40    # transom at 40% from bottom of glass zone
SCHUCO_WIN_SILL_HEIGHT   = 0.900   # 900mm Brüstung below window — LBO NRW
SCHUCO_DOOR_FRAME_WIDTH  = 0.060   # 60mm visible frame — ADS 75
SCHUCO_DOOR_FRAME_DEPTH  = 0.075   # 75mm profile depth — ADS 75
SCHUCO_WIN_GLASS_DEPTH   = 0.024   # 24mm double glazing 4/16/4 Argon — residential
SCHUCO_DOOR_GLASS_DEPTH  = 0.028   # 28mm double glazing 6/16/6 Argon — impact DIN EN 12600
SCHUCO_WIN_SASH_WIDTH    = 0.040   # 40mm openable sash frame (Flügelrahmen) — AWS 90 BS.SI+
SCHUCO_DOOR_LEAF_WIDTH   = 0.045   # 45mm door leaf frame (Türflügel) — ADS 90 PL.SI
SCHUCO_FRAME_COLOR       = (55, 55, 55)     # dark anthracite aluminium
SCHUCO_SASH_COLOR        = (70, 70, 70)     # slightly lighter — sash/leaf distinction
SCHUCO_GLASS_COLOR       = (140, 210, 235)  # transparent blue-tint glass
BALUSTRADE_GLASS_THICKNESS = 0.018   # 18mm VSG laminated safety glass
BALUSTRADE_GLASS_HEIGHT    = 1.000   # 1000mm per LBO NRW
BALUSTRADE_CHANNEL_WIDTH   = 0.040   # 40mm aluminium U-channel
BALUSTRADE_CHANNEL_HEIGHT  = 0.025   # 25mm visible above floor
BALUSTRADE_HANDRAIL_WIDTH  = 0.040   # 40mm top cap
BALUSTRADE_HANDRAIL_HEIGHT = 0.025   # 25mm top cap
BALUSTRADE_GLASS_COLOR     = (180, 225, 235)  # clear glass with light green tint
BALUSTRADE_METAL_COLOR     = (190, 195, 200)  # anodised aluminium
LOUVER_WIDTH       = 0.030   # 30mm fin width  (user specified)
LOUVER_DEPTH       = 0.030   # 30mm fin depth  (user specified)
LOUVER_SPACING     = 0.130   # 130mm fin centre-to-centre (doubled)
LOUVER_GAP         = 0.040   # 40mm clearance from outer wall face
LOUVER_BAR_HEIGHT  = 0.015   # 15mm bar thickness — clearly visible continuous line
LOUVER_BAR_DEPTH   = 0.022   # 22mm bar depth — sits behind fins
LOUVER_N_BARS      = 4       # 4 intervals = 5 bar levels (0..4) across full height
LOUVER_COLOR       = (80, 50, 20)      # dark larch fin
LOUVER_BAR_COLOR   = (160, 70, 30)    # rust-red bar — contrasting behind fins
def _trace_floor_perimeter(cells, gs):
    """Trace the outer perimeter of all floor cells into one closed (x,y) loop.; Collects only boundary edges (no cell neighbour on the outside), builds a
    directed adjacency map, then walks the chain from the bottom-left corner; until the loop closes.  Works for rectangles, L-shapes, U-shapes, stepped
    terraces — any rectilinear plan.; Returns ordered list of (x, y) tuples (Z added by caller).
    """; tol = 0.001
    panel_set = set((round(c["key"][0], 4), round(c["key"][1], 4)) for c in cells)
    boundary_edges = []
    for (cx, cy) in panel_set:
        cx2, cy2 = round(cx + gs, 4), round(cy + gs, 4)
        if (cx, round(cy - gs, 4)) not in panel_set:
            boundary_edges.append(((cx, cy),   (cx2, cy)))
        if (cx, round(cy + gs, 4)) not in panel_set:
            boundary_edges.append(((cx2, cy2), (cx, cy2)))
        if (round(cx - gs, 4), cy) not in panel_set:
            boundary_edges.append(((cx, cy2),  (cx, cy)))
        if (round(cx + gs, 4), cy) not in panel_set:
            boundary_edges.append(((cx2, cy),  (cx2, cy2)))
    if not boundary_edges:
        return []
    adj = {}
    for (a, b) in boundary_edges:
        adj.setdefault(a, []).append(b)
    start   = min(adj.keys(), key=lambda p: (round(p[1], 4), round(p[0], 4)))
    loop    = [start]
    used    = set()
    current = start
    for _ in range(len(boundary_edges) + 4):   # safety cap
        nexts = adj.get(current, [])
        moved = False
        for nxt in nexts:
            ekey = (current, nxt)
            if ekey not in used:
                used.add(ekey)
                loop.append(nxt)
                current = nxt; moved = True
                break
        if not moved:
            break
        if len(loop) > 2:
            dx = abs(loop[-1][0] - start[0])
            dy = abs(loop[-1][1] - start[1])
            if dx < tol and dy < tol:
                break
    return loop
def _extrude_perimeter_layer(loop_xy, z_bottom, thickness, layer_name, color_rgb):
    """Build one solid Brep from a closed (x,y) perimeter loop at z_bottom,; extruded UPWARD by thickness.  Adds it to the Rhino document on layer_name
    with color_rgb.  Returns the new object ID or None.
    """
    if not loop_xy or len(loop_xy) < 3:
        return None
    t = thickness
    pts = [rg.Point3d(x, y, z_bottom) for (x, y) in loop_xy]
    if pts[0].DistanceTo(pts[-1]) > 0.001:
        pts.append(rg.Point3d(pts[0].X, pts[0].Y, pts[0].Z))
    profile_obj = rs.AddPolyline(pts)
    if not profile_obj:
        return None
    profile_curve = rs.coercecurve(profile_obj)
    if not profile_curve:
        rs.DeleteObject(profile_obj)
        return None
    extrusion = rg.Extrusion.Create(profile_curve, t, True)   # +t = upward
    rs.DeleteObject(profile_obj)
    if not extrusion:
        return None
    brep = extrusion.ToBrep()
    if not brep or not brep.IsValid:
        return None
    obj_id = sc.doc.Objects.AddBrep(brep)
    if obj_id:
        if not rs.IsLayer(layer_name):
            rs.AddLayer(layer_name, color_rgb)
        rs.ObjectLayer(obj_id, layer_name)
        rs.ObjectColor(obj_id, color_rgb)
    return obj_id
def _assign_wood_material(obj_id):
    """Assign a procedural wood grain render material to the Parkett floor solid.; Creates a Rhino render material with warm oak base colour and a procedural
    wood grain texture (ring-based, Rhino built-in WoodTextureType).; Grain scale is tuned to read like Schiffsboden at architectural scale.
    Falls back to plain object colour if the render API is unavailable.; """
    try:
        import Rhino.Render as rr
        rm = rr.RenderMaterial.CreateBasicMaterial(
            Rhino.DocObjects.Material(), sc.doc)
        rm.Fields.Set("diffuse", System.Drawing.Color.FromArgb(184, 120, 16))
        rm.Fields.Set("shine",   0.18)
        try:
            wood_tex = rr.RenderContentType.NewContentFromTypeId(
                rr.ContentUuids.WoodTextureType, sc.doc)
            if wood_tex:
                wood_tex.Fields.Set("grain-color-1",
                    System.Drawing.Color.FromArgb(210, 160, 60))
                wood_tex.Fields.Set("grain-color-2",
                    System.Drawing.Color.FromArgb(140,  85, 20))
                wood_tex.Fields.Set("ring-frequency", 0.08)
                wood_tex.Fields.Set("ring-twist",     0.04)
                wood_tex.Fields.Set("noise-amount",   0.15)
                wood_tex.Fields.Set("repeat-x", 0.5)   # grain every 2m along X
                wood_tex.Fields.Set("repeat-y", 4.0)
                rm.SetChild(wood_tex,
                    rr.RenderMaterial.StandardChildSlots.Diffuse)
                rm.SetChildSlotOn(
                    rr.RenderMaterial.StandardChildSlots.Diffuse, True,
                    rr.RenderContent.ChangeContexts.Program)
                rm.SetChildSlotAmount(
                    rr.RenderMaterial.StandardChildSlots.Diffuse, 100.0,
                    rr.RenderContent.ChangeContexts.Program)
        except Exception:
            pass   # Wood texture API not available — plain colour only
        mat_idx = sc.doc.RenderMaterials.Add(rm)
        if mat_idx is not None:
            obj = sc.doc.Objects.Find(obj_id)
            if obj:
                obj.Attributes.MaterialIndex  = mat_idx
                obj.Attributes.MaterialSource = \
                    Rhino.DocObjects.ObjectMaterialSource.MaterialFromObject
                obj.CommitChanges()
    except Exception as _em:
        rs.ObjectColor(obj_id, (184, 120, 16))
        print("    [Parkett] Render API unavailable, flat colour used.")
def draw_floor_panels(Building, floor_label, cells, floor_index):
    """Draw the entire floor as 5 stacked solid layers (CLT build-up).; Layers 1-4: single perimeter solid Brep each.
    Layer 5 (Parkett): single perimeter solid + procedural wood grain; render material (Rhino WoodTexture) — no individual plank geometry.
    Bottom of Layer 1 = beam top face.  Total height = 150mm.
    Rhino sub-layers:
      Floor_Panels_N::CLT_Structural; Floor_Panels_N::Insulation
      Floor_Panels_N::Membrane; Floor_Panels_N::Screed
      Floor_Panels_N::Parkett
    """
    parent_ln = "Floor_Panels_{}".format(floor_index)
    if not rs.IsLayer(parent_ln):
        rs.AddLayer(parent_ln, (180, 140, 100))
    panel_ids     = []
    panel_cell_map = {}
    if not cells:
        return panel_ids, panel_cell_map, parent_ln
    gs    = Building["grid"]["spacing"]
    z_bot = cells[0]["corners_3d"][0][2]   # beam top face Z
    loop_xy = _trace_floor_perimeter(cells, gs)
    use_perimeter = len(loop_xy) >= 3
    if not use_perimeter:
        print("  {} — perimeter trace failed, using per-cell fallback.".format(floor_label))
    z_cursor = z_bot   # advances after each layer
    for (suffix, thickness, color, desc) in CLT_LAYERS:
        sub_ln = "{}::{}".format(parent_ln, suffix)
        if not rs.IsLayer(sub_ln):
            rs.AddLayer(sub_ln, color)
            try:
                rs.ParentLayer(sub_ln, parent_ln)
            except Exception:
                pass   # ParentLayer not critical — layer still works standalone
        if suffix == "Parkett":
            obj_id = _extrude_perimeter_layer(
                loop_xy, z_cursor, thickness, sub_ln, color)
            if obj_id:
                panel_ids.append(obj_id)
                _assign_wood_material(obj_id)
                _apply_material(obj_id, _mat_parkett())
                print("    Parkett: 1 solid + wood grain material assigned.")
        elif use_perimeter:
            obj_id = _extrude_perimeter_layer(loop_xy, z_cursor, thickness, sub_ln, color)
            if obj_id:
                panel_ids.append(obj_id)
                if suffix == "CLT_Structural":
                    _apply_material(obj_id, _mat_concrete())
                    for cell in cells:
                        panel_cell_map[str(obj_id) + "_" + str(cell["key"])] = cell["key"]
                    panel_cell_map[str(obj_id)] = cells[0]["key"]
                elif suffix == "Insulation":
                    _apply_material(obj_id, _mat_insulation())
                elif suffix == "Membrane":
                    _apply_material(obj_id, _mat_membrane())
                elif suffix == "Screed":
                    _apply_material(obj_id, _mat_screed())
        else:
            for cell in cells:
                c = cell["corners_3d"]
                profile_pts = [
                    rg.Point3d(c[0][0], c[0][1], z_cursor),
                    rg.Point3d(c[1][0], c[1][1], z_cursor),
                    rg.Point3d(c[2][0], c[2][1], z_cursor),
                    rg.Point3d(c[3][0], c[3][1], z_cursor),
                    rg.Point3d(c[0][0], c[0][1], z_cursor),
                ]
                pobj = rs.AddPolyline(profile_pts)
                if not pobj:
                    continue
                pcurve = rs.coercecurve(pobj)
                if not pcurve:
                    rs.DeleteObject(pobj)
                    continue
                ext = rg.Extrusion.Create(pcurve, thickness, True)
                rs.DeleteObject(pobj)
                if not ext:
                    continue
                brep = ext.ToBrep()
                if not brep or not brep.IsValid:
                    continue
                obj_id = sc.doc.Objects.AddBrep(brep)
                if obj_id:
                    rs.ObjectLayer(obj_id, sub_ln)
                    rs.ObjectColor(obj_id, color)
                    panel_ids.append(obj_id)
                    if suffix == "CLT_Structural":
                        _apply_material(obj_id, _mat_concrete())
                        panel_cell_map[str(obj_id)] = cell["key"]
                    elif suffix == "Insulation":
                        _apply_material(obj_id, _mat_insulation())
                    elif suffix == "Membrane":
                        _apply_material(obj_id, _mat_membrane())
                    elif suffix == "Screed":
                        _apply_material(obj_id, _mat_screed())
                    elif suffix == "Parkett":
                        _apply_material(obj_id, _mat_parkett())
        z_cursor = round(z_cursor + thickness, 6)   # advance Z for next layer
    print("  {} floor build-up complete | CLT 80mm + Insul 20mm + Memb 5mm + Screed 35mm + Parkett 10mm (wood texture) = 150mm | {} objects".format(
        floor_label, len(panel_ids)))
    _enforce_wireframe()
    sc.doc.Views.Redraw()
    return panel_ids, panel_cell_map, parent_ln
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
    _enforce_wireframe()
    sc.doc.Views.Redraw()
    return cid
def remove_clipping_plane(Building, floor_index):
    ln = "Clipping_Plane_{}".format(floor_index)
    if rs.IsLayer(ln):
        objs = rs.ObjectsByLayer(ln)
        if objs:
            rs.DeleteObjects(objs)
        rs.DeleteLayer(ln)
    _enforce_wireframe()
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
    _enforce_wireframe()
    sc.doc.Views.Redraw()
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
    max_iterations = 50; iteration = 0
    while iteration < max_iterations:
        iteration += 1; current_remaining = final_remaining | bridge_adds
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
    """Bridge/connectivity panel — solid extruded UPWARD by full CLT build-up height."""
    ln = "Floor_Panels_{}".format(floor_index)
    if not rs.IsLayer(ln):
        rs.AddLayer(ln, (180, 140, 100))
    bx, by   = cell_key
    bx2, by2 = round(bx + gs, 4), round(by + gs, 4)
    t        = CLT_TOTAL_M   # 0.150 m — full build-up upward
    profile_pts = [
        rg.Point3d(bx,  by,  panel_z), rg.Point3d(bx2, by,  panel_z),
        rg.Point3d(bx2, by2, panel_z), rg.Point3d(bx,  by2, panel_z),
        rg.Point3d(bx,  by,  panel_z),
    ]
    profile_obj = rs.AddPolyline(profile_pts)
    if not profile_obj:
        return None
    profile_curve = rs.coercecurve(profile_obj)
    if not profile_curve:
        rs.DeleteObject(profile_obj)
        return None
    extrusion = rg.Extrusion.Create(profile_curve, t, True)   # +t = upward
    rs.DeleteObject(profile_obj)
    if not extrusion:
        return None
    brep = extrusion.ToBrep()
    if not brep or not brep.IsValid:
        return None
    pb = sc.doc.Objects.AddBrep(brep)
    if pb:
        rs.ObjectLayer(pb, ln)
        rs.ObjectColor(pb, (255, 140, 0))
        return pb
    return None
def interactive_panel_deletion(Building, floor_label, panel_ids, panel_cell_map, panel_layer, floor_index, all_possible_keys, panel_z):
    """Silently keep ALL panels — no dialog, no per-floor popup, no user selection.; Called from process_floor_panels; behaviour is now fully automatic.
    """
    all_keys = set(panel_cell_map.values())
    print("  Keeping all {} panels for {} (automatic).".format(len(panel_ids), floor_label))
    Building["panels"]["panel_ids_per_floor"].append(list(panel_ids))
    Building["panels"]["panel_coords_per_floor"].append(list(all_keys))
    Building["panels"]["deleted_panels_per_floor"].append([])
PURLIN_COUNT      = 2      # fixed: 2 purlins per grid bay — 3 equal sub-bays
PURLIN_LOAD_KN_M2 = 5.0   # kN/m² ULS floor load (DL+LL factored, residential)
def auto_calc_purlin_count(grid_spacing):
    """Fixed at 2 purlins per bay — 3 equal sub-bays of gs/3.; For gs=4m: 3 bays of 1333mm, within CLT 80mm max span (DIN EN 16351).
    For gs=5m: 3 bays of 1667mm, still within 2000mm limit.; """
    return PURLIN_COUNT
def auto_calc_purlin_section(grid_spacing, n_purlins, num_floors=3):
    """GL24h SQUARE purlin sizing — PROTECTED secondary member (MHolzBauRL 2024).
    Purlins are enclosed within the floor assembly:
      - Top face covered by CLT slab (DIN EN 16351); - Bottom face covered by ceiling or intumescent coating
    => Protected exposure: structural checks govern, NOT fire (MHolzBauRL 2024).; Tributary: trib = gs / (n+1).  For n=2, gs=4m: trib=1.333m.
    Checks: Bending (EC5 §6.1.6) + Deflection L/300. Min 100mm practical.; Returns (width_m, depth_m, section_name) — square section.
    """; import math
    fm_d = 15.36           # MPa GL24h design bending strength
    E    = 11600.0         # MPa GL24h E_mean
    trib = grid_spacing / float(n_purlins + 1)
    q    = PURLIN_LOAD_KN_M2 * trib   # N/mm line load
    L    = grid_spacing * 1000.0       # mm span
    M_Nmm  = q * L ** 2 / 8.0
    b_bend = (6.0 * M_Nmm / fm_d) ** (1.0 / 3.0)
    q_sls  = 3.5 * trib   # N/mm characteristic line load for deflection
    b_defl = (5.0 * q_sls * L ** 3 * 12.0 * 300.0 / (384.0 * E)) ** 0.25
    b_sq = math.ceil(max(b_bend, b_defl, 100.0) / 20.0) * 20  # round up to 20mm
    b_m  = round(b_sq / 1000.0, 3)
    name = "PURLIN_w{:.0f}xd{:.0f}_GL24h_prot".format(b_sq, b_sq)
    return b_m, b_m, name
def draw_floor_purlins(Building, floor_label, cells, beam_z, floor_index):
    """Draw secondary purlins as solid GL24h Brep members below the CLT slab.; Z position: top of purlin = panel_z (= beam_z + primary beam depth).
    Purlins sit flush under the CLT slab, hanging downward by their depth.; Section: 120mm wide x 200mm deep — standard secondary Deckenbalken in
    German timber construction (KVH/GL24h, protected exposure per MHolzBauRL 2024).; Much lighter than the primary square beams — correct for a secondary member.
    2 purlins per cell, running parallel to X axis, spanning full grid_spacing.; Shared purlin edges between adjacent cells are deduplicated.
    """
    if not cells:
        return []
    gs  = Building["grid"]["spacing"]
    bd  = Building["structure"]["plinth_beams"]["depth"]
    n_pur = auto_calc_purlin_count(gs)
    bay   = gs / float(n_pur + 1)
    pur_width_m = 0.120   # 120 mm
    pur_depth_m = 0.200   # 200 mm
    sec_name    = "PURLIN_w120xd200_GL24h_protected"
    panel_z = beam_z + bd   # top of primary beam / bottom of CLT slab
    Building["purlins"]["n_per_cell"]    = n_pur
    Building["purlins"]["spacing"]       = round(bay, 3)
    Building["purlins"]["section_width"] = pur_width_m
    Building["purlins"]["section_depth"] = pur_depth_m
    Building["purlins"]["section_name"]  = sec_name
    layer_name = "Floor_Purlins"
    if not rs.IsLayer(layer_name):
        rs.AddLayer(layer_name, (180, 130, 70))
    pur_ids = []
    seen    = set()   # deduplicate shared edges between adjacent cells
    for cell in cells:
        cx, cy = cell["x"], cell["y"]   # SW corner of cell
        for i in range(1, n_pur + 1):
            y_pur    = round(cy + i * bay, 4)
            edge_key = (round(cx, 4), round(cx + gs, 4), y_pur)
            if edge_key in seen:
                continue
            seen.add(edge_key)
            pt1 = rg.Point3d(cx,      y_pur, panel_z)
            pt2 = rg.Point3d(cx + gs, y_pur, panel_z)
            bid = create_single_beam(pt1, pt2, pur_width_m, -pur_depth_m)
            if bid:
                rs.ObjectLayer(bid, layer_name)
                rs.ObjectColor(bid, (160, 100, 40))
                rs.ObjectName(bid, sec_name)
                pur_ids.append(bid)
    print("  {} purlins: {} Breps  ({}mm x {}mm GL24h, Z={:.2f}m)".format(
          floor_label, len(pur_ids),
          int(pur_width_m*1000), int(pur_depth_m*1000), panel_z))
    print("    Bay: {:.3f} m  |  Top at panel_z = beam_z + bd = {:.3f}m".format(
          bay, panel_z))
    Building["purlins"]["ids_per_floor"].append(pur_ids)
    _enforce_wireframe()
    sc.doc.Views.Redraw()
    return pur_ids
def process_floor_panels(Building, floor_label, floor_index, floor_top_points, extension):
    """Generate floor panels for one floor automatically — no dialogs, no view changes.; All cells with full beam support are filled. Nothing is deleted.
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
    draw_floor_purlins(Building, floor_label, cells, beam_z, floor_index)
    panel_ids, panel_cell_map, panel_layer = draw_floor_panels(Building, floor_label, cells, floor_index)
    Building["panels"]["panels_per_floor"].append(cells)
    interactive_panel_deletion(Building, floor_label, panel_ids, panel_cell_map,
                               panel_layer, floor_index, all_possible_keys, panel_z)
    print("  {} panelling complete.".format(floor_label))
    print_section_footer()
def process_all_floor_panels(Building):
    """Generate floor panels for ALL floors in one automated step.; Shows a SINGLE start dialog to the user — no per-floor popups.
    All panels are kept automatically; nothing is deleted.; """
    nf   = len(Building["structure"]["columns"]["top_points_per_floor"])
    exts = Building["structure"]["plinth_beams"]["extension_per_floor"]
    _panel_dlg = PanelGenerationDialog(num_floors=nf)
    _panel_dlg.ShowModal(Rhino.UI.RhinoEtoApp.MainWindow)
    Building["_panel_dlg"] = _panel_dlg   # stored so wall panels reuses it
    if not _panel_dlg.confirmed:
        print("  Floor panel generation cancelled by user.")
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
    _enforce_wireframe()
    rs.Redraw()
    sc_ids = len(Building["staircase"]["ids"])
    sc_cell = Building["staircase"]["cell"]
    if sc_cell:
        print("  Staircase cell: ({:.2f}, {:.2f})  |  {} objects  |  "
              "{} risers @ {:.1f} cm  |  tread {:.1f} cm".format(
              sc_cell[0], sc_cell[1], sc_ids,
              Building["staircase"]["n_risers"],
              Building["staircase"]["riser_h"] * 100,
              Building["staircase"]["tread_d"] * 100))
    tp = sum(len(p) for p in Building["panels"]["panel_ids_per_floor"])
    print_section_header("PANELLING COMPLETE")
    print("  Total floor panels generated: {}".format(tp))
    print("  Deleted: 0  (all panels kept)")
    print_section_footer()
def _ensure_staircase_layer():
    """Create the Staircase layer (dark walnut) if it does not exist."""
    if not rs.IsLayer("Staircase"):
        rs.AddLayer("Staircase", (60, 40, 20))
    sub_layers = [
        ("Staircase::Treads",    (140, 140, 140)),
        ("Staircase::Landing",   (140, 140, 140)),
        ("Staircase::Stringers", (120, 80,  30)),
        ("Staircase::Handrail",  (50,  50,  50)),
        ("Staircase::Shaft_Wall",(200, 160, 120)),
    ]
    for (ln, col) in sub_layers:
        if not rs.IsLayer(ln):
            rs.AddLayer(ln, col)
            try:
                rs.ParentLayer(ln, "Staircase")
            except Exception:
                pass

def _get_complete_cells_for_floor(coords, gs):
    """Return a sorted list of complete grid cells from column-grid coordinates."""
    if not coords:
        return []
    xy = set((round(p[0], 4), round(p[1], 4)) for p in coords)
    cells = []
    for (px, py) in sorted(xy):
        px2 = round(px + gs, 4); py2 = round(py + gs, 4)
        if ((px, py) in xy and (px2, py) in xy and
            (px, py2) in xy and (px2, py2) in xy):
            cells.append((round(px, 4), round(py, 4)))
    return sorted(set(cells))

def find_staircase_cell(Building):
    """Pick one vertically continuous stair shaft cell in the tallest common stack.
    Preference order:
      1) cell present as a complete cell through the maximum number of consecutive floors
         starting from the ground floor,
      2) rear/edge preference using the tallest-zone bounds,
      3) farther to max Y, then max X.
    Stores Building["staircase"]["cell"] and returns True/False.
    """
    coords_per_floor = Building["grid"]["selected_coords_per_floor"]
    if not coords_per_floor:
        print("  [Staircase] No floor coordinates found — cannot place stair.")
        return False
    gs = Building["grid"]["spacing"]
    floor_cells = [_get_complete_cells_for_floor(coords, gs) for coords in coords_per_floor]
    if not floor_cells or not floor_cells[0]:
        print("  [Staircase] Ground floor has no complete grid cells.")
        return False
    complete_sets = [set(cells) for cells in floor_cells]
    stack_counts = {}
    for cell in sorted(complete_sets[0]):
        count = 0
        for cset in complete_sets:
            if cell in cset:
                count += 1
            else:
                break
        if count > 0:
            stack_counts[cell] = count
    if not stack_counts:
        print("  [Staircase] No vertically continuous common cell found.")
        return False
    max_count = max(stack_counts.values())
    candidates = [c for c, n in stack_counts.items() if n == max_count]
    zone_cells = candidates[:]
    xs = [c[0] for c in zone_cells]; ys = [c[1] for c in zone_cells]
    min_x = min(xs); max_x = max(xs); min_y = min(ys); max_y = max(ys)
    def edge_score(cell):
        cx, cy = cell
        on_edge = int(cx in (min_x, max_x) or cy in (min_y, max_y))
        rearish = max(cy - min_y, cx - min_x, 0.0)
        return (on_edge, rearish, cy, cx)
    candidates.sort(key=edge_score, reverse=True)
    chosen = candidates[0]
    Building["staircase"]["cell"] = chosen
    Building["staircase"]["stack_floor_count"] = max_count
    print("  [Staircase] Shaft cell selected: ({:.2f}, {:.2f})  [common through {} floor(s)]".format(
        chosen[0], chosen[1], max_count))
    return True


def _din18065_stair_params(floor_height_m):
    """Calculate stair geometry using the project limits.
    User limits:
      riser height: 0.12 m to 0.15 m
      tread depth : 0.30 m
    Returns dict with keys: n_risers, riser_h, tread_d.
    """
    fh = floor_height_m
    min_risers = int(math.ceil(fh / 0.150))
    max_risers = int(math.floor(fh / 0.120))
    if max_risers < min_risers:
        max_risers = min_risers
    best = None
    for n in range(min_risers, max_risers + 1):
        h = fh / float(n)
        if 0.12 - 0.001 <= h <= 0.15 + 0.001:
            score = abs(h - 0.145)
            if best is None or score < best[0]:
                best = (score, n, h)
    if best is None:
        n = min_risers
        h = fh / float(n)
        h = max(0.12, min(0.15, h))
    else:
        _, n, h = best
    return {"n_risers": int(n), "riser_h": round(h, 4), "tread_d": 0.30}

def _add_box_to_layer(x0, y0, z0, dx, dy, dz, layer_name, color_rgb):
    """Create a solid box (Brep) aligned to world axes and add to layer.; Returns the Rhino object ID or None.
    dx, dy, dz may be negative (extrusion direction).; """
    pts = [
        rg.Point3d(x0,      y0,      z0),
        rg.Point3d(x0 + dx, y0,      z0),
        rg.Point3d(x0 + dx, y0 + dy, z0),
        rg.Point3d(x0,      y0 + dy, z0),
        rg.Point3d(x0,      y0,      z0),
    ]
    pobj = rs.AddPolyline(pts)
    if not pobj:
        return None
    pcurve = rs.coercecurve(pobj)
    if not pcurve:
        rs.DeleteObject(pobj)
        return None
    ext = rg.Extrusion.Create(pcurve, dz, True)
    rs.DeleteObject(pobj)
    if not ext:
        return None
    brep = ext.ToBrep()
    if not brep or not brep.IsValid:
        return None
    oid = sc.doc.Objects.AddBrep(brep)
    if oid:
        if not rs.IsLayer(layer_name):
            rs.AddLayer(layer_name, color_rgb)
        rs.ObjectLayer(oid, layer_name)
        rs.ObjectColor(oid, color_rgb)
        _ln = layer_name.split("::")[-1] if "::" in layer_name else layer_name
        if _ln in ("Treads",):
            _apply_material(oid, _mat_stair_tread())
        elif _ln in ("Landing",):
            _apply_material(oid, _mat_stair_landing())
        elif _ln in ("Shaft_Wall",):
            _apply_material(oid, _mat_facade_paint())
        elif _ln in ("Stringers",):
            _apply_material(oid, _mat_stair_stringer())
    return oid
def _add_handrail_tube(pt_a, pt_b, radius, layer_name, color_rgb):
    """Create a cylinder (handrail tube) between two 3D points.; Returns Rhino object ID or None.
    """
    try:
        pa = rg.Point3d(*pt_a)
        pb = rg.Point3d(*pt_b)
        axis = rg.Vector3d(pb - pa)
        length = axis.Length
        if length < 0.001:
            return None
        axis.Unitize()
        plane = rg.Plane(pa, axis)
        circle = rg.Circle(plane, radius)
        cyl = rg.Cylinder(circle, length)
        brep = cyl.ToBrep(True, True)
        if not brep or not brep.IsValid:
            return None
        oid = sc.doc.Objects.AddBrep(brep)
        if oid:
            rs.ObjectLayer(oid, layer_name)
            rs.ObjectColor(oid, color_rgb)
            _apply_material(oid, _mat_stair_handrail())
        return oid
    except Exception as _e:
        return None

def _add_center_stringer_beam(pt_a, pt_b, width, depth, layer_name, color_rgb):
    """Create one oriented rectangular mono-stringer beam between two 3D points."""
    try:
        pa = rg.Point3d(*pt_a)
        pb = rg.Point3d(*pt_b)
        axis = rg.Vector3d(pb - pa)
        length = axis.Length
        if length < 0.001:
            return None
        axis.Unitize()
        up = rg.Vector3d(0, 0, 1)
        side = rg.Vector3d.CrossProduct(up, axis)
        if side.Length < 0.001:
            side = rg.Vector3d(1, 0, 0)
        side.Unitize()
        plane = rg.Plane(pa, axis, side)
        box = rg.Box(
            plane,
            rg.Interval(0.0, length),
            rg.Interval(-width * 0.5, width * 0.5),
            rg.Interval(-depth, 0.0)
        )
        brep = rg.Brep.CreateFromBox(box)
        if not brep or not brep.IsValid:
            return None
        oid = sc.doc.Objects.AddBrep(brep)
        if oid:
            if not rs.IsLayer(layer_name):
                rs.AddLayer(layer_name, color_rgb)
            rs.ObjectLayer(oid, layer_name)
            rs.ObjectColor(oid, color_rgb)
            _apply_material(oid, _mat_stair_stringer())
        return oid
    except Exception:
        return None

def _add_continuous_center_stringer(path_pts, width, depth, layer_name, color_rgb):
    """Create one continuous folded mono-stringer as a single unioned solid.
    The top face of the profile stays on the supplied underside-contact path.
    Corners are softly mitered with short 45° chamfer segments so the
    stringer reads as one bent steel spine instead of a broken sweep.
    """
    try:
        if not path_pts or len(path_pts) < 2:
            return None
        tol = sc.doc.ModelAbsoluteTolerance
        pts = [rg.Point3d(*pt) for pt in path_pts]
        cleaned = [pts[0]]
        for p in pts[1:]:
            if p.DistanceTo(cleaned[-1]) > 0.001:
                cleaned.append(p)
        if len(cleaned) < 2:
            return None

        def _unit_vec(a, b):
            v = rg.Vector3d(b - a)
            if v.Length < 1e-9:
                return None
            v.Unitize()
            return v

        # Chamfer interior corners so the member bends cleanly at turns.
        chamfer = max(width * 0.9, 0.10)
        work = [cleaned[0]]
        for i in range(1, len(cleaned) - 1):
            p_prev = cleaned[i - 1]
            p = cleaned[i]
            p_next = cleaned[i + 1]
            v_in = _unit_vec(p_prev, p)
            v_out = _unit_vec(p, p_next)
            if v_in is None or v_out is None:
                continue
            seg_in = p.DistanceTo(p_prev)
            seg_out = p.DistanceTo(p_next)
            trim = min(chamfer, 0.45 * seg_in, 0.45 * seg_out)
            if trim <= 0.01:
                work.append(p)
                continue
            p_a = rg.Point3d(p)
            p_a -= v_in * trim
            p_b = rg.Point3d(p)
            p_b += v_out * trim
            if work[-1].DistanceTo(p_a) > 0.001:
                work.append(p_a)
            if work[-1].DistanceTo(p_b) > 0.001:
                work.append(p_b)
        if work[-1].DistanceTo(cleaned[-1]) > 0.001:
            work.append(cleaned[-1])
        if len(work) < 2:
            return None

        seg_breps = []
        world_up = rg.Vector3d(0, 0, 1)
        for i in range(len(work) - 1):
            pa = work[i]
            pb = work[i + 1]
            axis = rg.Vector3d(pb - pa)
            length = axis.Length
            if length < 0.01:
                continue
            axis.Unitize()
            side = rg.Vector3d.CrossProduct(world_up, axis)
            if side.Length < 0.001:
                side = rg.Vector3d.CrossProduct(axis, rg.Vector3d(1, 0, 0))
            if side.Length < 0.001:
                side = rg.Vector3d(1, 0, 0)
            side.Unitize()
            plane = rg.Plane(pa, axis, side)
            box = rg.Box(
                plane,
                rg.Interval(0.0, length),
                rg.Interval(-width * 0.5, width * 0.5),
                rg.Interval(-depth, 0.0)
            )
            brep = rg.Brep.CreateFromBox(box)
            if brep and brep.IsValid:
                seg_breps.append(brep)
        if not seg_breps:
            return None
        joined = rg.Brep.CreateBooleanUnion(seg_breps, tol)
        if joined and len(joined) > 0:
            brep = joined[0]
        else:
            brep = seg_breps[0]
            for extra in seg_breps[1:]:
                tmp = rg.Brep.CreateBooleanUnion([brep, extra], tol)
                if tmp and len(tmp) > 0:
                    brep = tmp[0]
        if not brep or not brep.IsValid:
            return None
        oid = sc.doc.Objects.AddBrep(brep)
        if oid:
            if not rs.IsLayer(layer_name):
                rs.AddLayer(layer_name, color_rgb)
            rs.ObjectLayer(oid, layer_name)
            rs.ObjectColor(oid, color_rgb)
            _apply_material(oid, _mat_stair_stringer())
        return oid
    except Exception:
        return None

def _generate_stair_run_segment(x0, y0, z0, run_dir, run_len, stair_w, n_risers, rh, td,
                                ln_trd, trd_col):
    """Create one straight stair run made of individual treads."""
    ids = []
    if n_risers <= 0:
        return ids
    for i in range(n_risers):
        bx = x0; by = y0; bz = z0 + i * rh
        if run_dir == "north":
            by = y0 + i * td
            dx, dy = stair_w, td
        elif run_dir == "south":
            by = y0 - (i + 1) * td
            dx, dy = stair_w, td
        elif run_dir == "east":
            bx = x0 + i * td
            dx, dy = td, stair_w
        else:  # west
            bx = x0 - (i + 1) * td
            dx, dy = td, stair_w
        oid = _add_box_to_layer(bx, by, bz, dx, dy, 0.030, ln_trd, trd_col)
        if oid:
            ids.append(oid)
    return ids

def _add_landing_box(x0, y0, z0, dx, dy, ln_land, land_col):
    oid = _add_box_to_layer(x0, y0, z0, dx, dy, 0.030, ln_land, land_col)
    return [oid] if oid else []

def _add_perimeter_handrail(ids, pt_a, pt_b, ln_hr, hr_col):
    oid = _add_handrail_tube(pt_a, pt_b, 0.025, ln_hr, hr_col)
    if oid:
        ids.append(oid)

def _generate_one_flight(Building, floor_idx, z_bottom_slab_top, z_top_slab_top,
                          cx, cy, gs, stair_params, flight_dir, wall_open_side):
    """Generate one floor-to-floor stair inside a single grid cell.
    Uses a clean perimeter-wrapped U/C stair solved against the actual cell box
    so every level connects exactly floor-to-floor without cumulative offsets.
    """
    ids = []
    stair_w = Building["staircase"]["stair_w"]
    n = int(stair_params["n_risers"])
    rh = stair_params["riser_h"]
    td = stair_params["tread_d"]
    col_w = Building["structure"]["columns"]["width"]
    half_c = col_w * 0.5
    cx2 = cx + gs; cy2 = cy + gs
    inner_x0 = cx + half_c; inner_x1 = cx2 - half_c
    inner_y0 = cy + half_c; inner_y1 = cy2 - half_c
    clear_x = inner_x1 - inner_x0; clear_y = inner_y1 - inner_y0
    trd_col = (140, 140, 140); land_col = (140, 140, 140)
    str_col = (120, 80, 30); hr_col = (50, 50, 50)
    ln_trd = "Staircase::Treads"; ln_land = "Staircase::Landing"
    ln_str = "Staircase::Stringers"; ln_hr = "Staircase::Handrail"

    # Available perimeter lengths inside the clear 4.66 x 4.66 shaft.
    side_h = max(0.0, clear_x - stair_w)     # bottom/top horizontal strips
    side_v = max(0.0, clear_y - 2.0 * stair_w)  # side vertical strip between landings
    cap_h = max(1, int(math.floor(side_h / td + 1e-9)))
    cap_v = max(1, int(math.floor(side_v / td + 1e-9)))

    # Search for a valid 3-run distribution that stays within the cell and keeps
    # the two horizontal runs visually balanced.
    best = None
    for n1 in range(1, cap_h + 1):
        for n2 in range(1, cap_v + 1):
            n3 = n - n1 - n2
            if n3 < 1 or n3 > cap_h:
                continue
            gap1 = side_h - n1 * td
            gap2 = side_v - n2 * td
            gap3 = side_h - n3 * td
            if gap1 < -1e-9 or gap2 < -1e-9 or gap3 < -1e-9:
                continue
            score = (abs(n1 - n3), abs(gap1 - gap3), gap1 + gap2 + gap3)
            if best is None or score < best[0]:
                best = (score, n1, n2, n3, gap1, gap2, gap3)
    if best is None:
        # Fallback to a clipped but valid distribution.
        n1 = min(cap_h, max(1, n // 3))
        n2 = min(cap_v, max(1, n // 3))
        n3 = max(1, min(cap_h, n - n1 - n2))
        gap1 = max(0.0, side_h - n1 * td)
        gap2 = max(0.0, side_v - n2 * td)
        gap3 = max(0.0, side_h - n3 * td)
    else:
        _, n1, n2, n3, gap1, gap2, gap3 = best

    z1 = z_bottom_slab_top + n1 * rh
    z2 = z1 + n2 * rh

    # Fixed absolute frame inside the cell:
    #   run 1: east along south side
    #   landing 1: south-east corner
    #   run 2: north along east side
    #   landing 2: north-east corner
    #   run 3: west along north side
    # Optional connector landings absorb leftover side lengths cleanly.
    run1_x0 = inner_x0 + gap1
    run1_y0 = inner_y0
    landing1_x0 = inner_x1 - stair_w
    landing1_y0 = inner_y0

    run2_x0 = inner_x1 - stair_w
    run2_y0 = inner_y0 + stair_w + gap2
    landing2_x0 = inner_x1 - stair_w
    landing2_y0 = inner_y1 - stair_w

    run3_x0 = inner_x1 - stair_w
    run3_y0 = inner_y1 - stair_w
    top_conn_x0 = inner_x0
    top_conn_dx = gap3

    # Optional bottom connector landing so the first run always starts from the
    # west/internal edge of the shaft instead of floating.
    if gap1 > 0.001:
        ids += _add_landing_box(inner_x0, inner_y0, z_bottom_slab_top, gap1, stair_w, ln_land, land_col)

    ids += _generate_stair_run_segment(run1_x0, run1_y0, z_bottom_slab_top, "east",
                                       n1 * td, stair_w, n1, rh, td, ln_trd, trd_col)
    ids += _add_landing_box(landing1_x0, landing1_y0, z1, stair_w, stair_w, ln_land, land_col)

    # South-to-middle connector at landing 1 elevation, then the vertical run.
    if gap2 > 0.001:
        ids += _add_landing_box(inner_x1 - stair_w, inner_y0 + stair_w, z1, stair_w, gap2, ln_land, land_col)
    ids += _generate_stair_run_segment(run2_x0, run2_y0, z1, "north",
                                       n2 * td, stair_w, n2, rh, td, ln_trd, trd_col)
    ids += _add_landing_box(landing2_x0, landing2_y0, z2, stair_w, stair_w, ln_land, land_col)

    ids += _generate_stair_run_segment(run3_x0, run3_y0, z2, "west",
                                       n3 * td, stair_w, n3, rh, td, ln_trd, trd_col)
    # Upper floor connector so the stair always reaches the next slab exactly.
    if top_conn_dx > 0.001:
        ids += _add_landing_box(top_conn_x0, inner_y1 - stair_w, z_top_slab_top, top_conn_dx, stair_w, ln_land, land_col)


    # Handrails locked to the same absolute frame.
    _add_perimeter_handrail(ids,
                            (run1_x0, inner_y0 + stair_w - 0.05, z_bottom_slab_top + 0.9),
                            (landing1_x0, inner_y0 + stair_w - 0.05, z1 + 0.9),
                            ln_hr, hr_col)
    _add_perimeter_handrail(ids,
                            (inner_x1 - 0.05, run2_y0, z1 + 0.9),
                            (inner_x1 - 0.05, inner_y1 - stair_w, z2 + 0.9),
                            ln_hr, hr_col)
    _add_perimeter_handrail(ids,
                            (inner_x1 - stair_w, inner_y1 - stair_w + 0.05, z2 + 0.9),
                            (inner_x0 + top_conn_dx, inner_y1 - stair_w + 0.05, z_top_slab_top + 0.9),
                            ln_hr, hr_col)
    return ids

def _add_stair_headroom(Building, roof_opening_z, cx, cy):
    """Add a simple headroom enclosure and roof cap above the final roof opening."""
    gs = Building["grid"]["spacing"]
    col_w = Building["structure"]["columns"]["width"]
    wall_t = max(0.08, min(0.15, col_w * 0.5))
    clear_h = 2.10
    ln_wall = "Staircase::Shaft_Wall"
    ln_land = "Staircase::Landing"
    wall_col = (200, 160, 120)
    roof_col = (140, 140, 140)
    ox0 = cx + col_w * 0.5; oy0 = cy + col_w * 0.5
    ox1 = cx + gs - col_w * 0.5; oy1 = cy + gs - col_w * 0.5
    w = ox1 - ox0; d = oy1 - oy0
    parts = [
        (ox0 - wall_t, oy0 - wall_t, roof_opening_z, wall_t, d + 2 * wall_t, clear_h),
        (ox1,          oy0 - wall_t, roof_opening_z, wall_t, d + 2 * wall_t, clear_h),
        (ox0,          oy0 - wall_t, roof_opening_z, w,      wall_t,         clear_h),
        (ox0,          oy1,          roof_opening_z, w,      wall_t,         clear_h),
    ]
    ids = []
    for x0, y0, z0, dx, dy, dz in parts:
        oid = _add_box_to_layer(x0, y0, z0, dx, dy, dz, ln_wall, wall_col)
        if oid:
            ids.append(oid)
    roof_oid = _add_box_to_layer(ox0 - wall_t, oy0 - wall_t, roof_opening_z + clear_h,
                                 w + 2 * wall_t, d + 2 * wall_t, 0.12, ln_land, roof_col)
    if roof_oid:
        ids.append(roof_oid)
    return ids

def _cut_stair_opening_from_slab(Building, floor_index, cx, cy):
    """Cut one full clear stairwell opening through the complete floor build-up in the selected grid cell."""
    gs = Building["grid"]["spacing"]
    col_w = Building["structure"]["columns"]["width"]
    half_c = col_w * 0.5; ox0 = cx + half_c; oy0 = cy + half_c
    ox1 = cx + gs - half_c; oy1 = cy + gs - half_c
    if floor_index >= len(Building["panels"]["panel_ids_per_floor"]):
        return
    panel_ids = list(Building["panels"]["panel_ids_per_floor"][floor_index])
    if not panel_ids:
        return
    cutter_z = -1000.0
    cutter_h = 2000.0
    cut_pts = [
        rg.Point3d(ox0, oy0, cutter_z), rg.Point3d(ox1, oy0, cutter_z),
        rg.Point3d(ox1, oy1, cutter_z), rg.Point3d(ox0, oy1, cutter_z),
        rg.Point3d(ox0, oy0, cutter_z),
    ]
    cut_pobj = rs.AddPolyline(cut_pts)
    if not cut_pobj:
        return
    cut_curve = rs.coercecurve(cut_pobj)
    if not cut_curve:
        rs.DeleteObject(cut_pobj)
        return
    cut_ext = rg.Extrusion.Create(cut_curve, cutter_h, True)
    rs.DeleteObject(cut_pobj)
    if not cut_ext:
        return
    cutter_brep = cut_ext.ToBrep()
    if not cutter_brep or not cutter_brep.IsValid:
        return
    ids_to_keep = []
    for pid in panel_ids:
        try:
            obj = sc.doc.Objects.Find(pid)
            if obj is None or obj.IsDeleted:
                continue
            source_geo = obj.Geometry
            source_brep = source_geo if isinstance(source_geo, rg.Brep) else rs.coercebrep(pid)
            if source_brep is None:
                ids_to_keep.append(pid)
                continue
            results = rg.Brep.CreateBooleanDifference([source_brep], [cutter_brep], 0.001)
            if results and len(results) > 0:
                layer_name = rs.ObjectLayer(pid); color = rs.ObjectColor(pid)
                rs.DeleteObject(pid)
                for res_brep in results:
                    if res_brep and res_brep.IsValid:
                        new_id = sc.doc.Objects.AddBrep(res_brep)
                        if new_id:
                            rs.ObjectLayer(new_id, layer_name)
                            rs.ObjectColor(new_id, color)
                            ids_to_keep.append(new_id)
            else:
                ids_to_keep.append(pid)
        except Exception as _ex:
            ids_to_keep.append(pid)
            print("  [Stair opening] Boolean failed for panel {}: {}".format(pid, _ex))
    Building["panels"]["panel_ids_per_floor"][floor_index] = ids_to_keep

    # Remove purlins that belong to the same stair grid on cut floors.
    # Purlins are generated as separate members per grid bay, so for the
    # staircase shaft we delete the intersecting members completely instead
    # of trimming them.
    if floor_index < len(Building["purlins"].get("ids_per_floor", [])):
        pur_ids = list(Building["purlins"]["ids_per_floor"][floor_index])
        kept_pur_ids = []
        tol = 0.001
        for pur_id in pur_ids:
            try:
                if not pur_id or not rs.IsObject(pur_id):
                    continue
                bb = rs.BoundingBox(pur_id)
                if not bb or len(bb) < 8:
                    kept_pur_ids.append(pur_id)
                    continue
                min_x = min(pt.X for pt in bb); max_x = max(pt.X for pt in bb)
                min_y = min(pt.Y for pt in bb); max_y = max(pt.Y for pt in bb)
                intersects_opening = (
                    max_x > (ox0 + tol) and min_x < (ox1 - tol) and
                    max_y > (oy0 + tol) and min_y < (oy1 - tol)
                )
                if intersects_opening:
                    rs.DeleteObject(pur_id)
                else:
                    kept_pur_ids.append(pur_id)
            except Exception as _pur_ex:
                kept_pur_ids.append(pur_id)
                print("  [Stair opening] Purlin delete failed for {}: {}".format(pur_id, _pur_ex))
        Building["purlins"]["ids_per_floor"][floor_index] = kept_pur_ids

    # IMPORTANT: do NOT remove the shaft cell from panel_coords_per_floor here.
    # The later wall/window/facade generation logic still relies on the original
    # grid occupancy data to keep the surrounding external wall panels intact.
    # Staircase is an internal cutout only; it must not erase facade decisions.
    print("  [Stair opening] Floor {}: clear opening cut at ({:.2f},{:.2f}) size {:.2f} x {:.2f}m".format(
          floor_index, cx, cy, ox1 - ox0, oy1 - oy0))

def generate_staircase(Building):
    """Main entry point — generate the complete multi-floor staircase.
    Logic:
      1. Find one vertically continuous edge/rear shaft cell in the tallest stack.
      2. Cut the shaft opening on every intermediate floor above the ground.
      3. Generate one stair per occupied floor-to-floor interval.
      4. Keep the final roof slab closed — no terrace stair / no headroom.
    """
    print_section_header("STAIRCASE GENERATION (DIN 18065)")
    if not find_staircase_cell(Building):
        print("  [Staircase] Aborted — no valid shaft cell found.")
        print_section_footer()
        return
    _ensure_staircase_layer()
    gs = Building["grid"]["spacing"]
    cx, cy = Building["staircase"]["cell"]
    floor_heights = Building["floors"]["floor_heights"]
    col_top_pts = Building["structure"]["columns"]["top_points_per_floor"]
    bd = Building["structure"]["plinth_beams"]["depth"]
    n_floors = len(col_top_pts)
    if n_floors < 2:
        print("  [Staircase] Only one floor — no staircase needed.")
        print_section_footer()
        return
    slab_tops = []
    for fi in range(n_floors):
        if col_top_pts[fi]:
            col_top_z = col_top_pts[fi][0][2]
        else:
            col_top_z = sum(floor_heights[:fi])
        slab_tops.append(col_top_z + bd + CLT_TOTAL_M)
    roof_index = n_floors - 1
    top_occupied_index = max(0, roof_index - 1)
    print("  Shaft cell       : ({:.2f}, {:.2f})".format(cx, cy))
    print("  Total floor sets : {}  (roof = floor {}, top occupied = floor {})".format(n_floors, roof_index, top_occupied_index))
    print("  Slab tops Z      : {}".format(", ".join("{:.3f}".format(z) for z in slab_tops)))
    all_stair_ids = []
    for floor_index in range(1, roof_index):
        _cut_stair_opening_from_slab(Building, floor_index, cx, cy)
    intervals = range(max(0, n_floors - 2))
    for fi in intervals:
        z_bot = slab_tops[fi]
        z_top = slab_tops[fi + 1]
        fh = z_top - z_bot
        if fh < 0.001:
            print("  [Staircase] Floor interval {} → {}: zero height, skipping.".format(fi, fi + 1))
            continue
        params = _din18065_stair_params(fh)
        Building["staircase"]["n_risers"] = params["n_risers"]
        Building["staircase"]["riser_h"] = params["riser_h"]
        Building["staircase"]["tread_d"] = params["tread_d"]
        print("  Floor {} → {}: H={:.3f}m | {} risers | h={:.1f}cm | a={:.1f}cm".format(
            fi, fi + 1, fh, params["n_risers"], params["riser_h"] * 100, params["tread_d"] * 100))
        flight_ids = _generate_one_flight(
            Building,
            floor_idx=fi,
            z_bottom_slab_top=z_bot,
            z_top_slab_top=z_top,
            cx=cx,
            cy=cy,
            gs=gs,
            stair_params=params,
            flight_dir="along_y",
            wall_open_side="south",
        )
        all_stair_ids.extend(flight_ids)
        print("  Floor {} → {}: {} stair objects generated.".format(fi, fi + 1, len(flight_ids)))
    print("  Final roof slab kept closed above floor {} — no terrace stair, no headroom.".format(top_occupied_index))
    Building["staircase"]["ids"] = all_stair_ids
    _enforce_wireframe()
    rs.Redraw()
    print("  Staircase complete. Total objects: {}".format(len(all_stair_ids)))
    print("  Stair settings: riser {:.1f}cm | tread {:.1f}cm | width {:.0f}cm".format(
        Building["staircase"]["riser_h"] * 100,
        Building["staircase"]["tread_d"] * 100,
        Building["staircase"]["stair_w"] * 100))
    print_section_footer()

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
    covered_cells = panel_set & above_set; uncovered_cells = panel_set - above_set
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
def create_wall_panel_surface(edge, base_z, panel_height, column_width=0.0, beam_depth=0.0, trim_top=True):
    """Create a wall panel surface trimmed clear of columns and beams.
    Horizontal trimming (column faces at panel ends):
      half_cw = column_width / 2 inset from each X or Y endpoint.
    Vertical trimming (beam soffit at panel top):
      When trim_top=True, z_top is reduced by beam_depth so the panel; stops at the bottom face of the upper beam (beam soffit).
      For parapet panels (trim_top=False) no top trim is applied —; there is no beam above a parapet.
    base_z = panel_z = top of lower beam (bottom of wall panel).; """
    x1, y1 = edge["x1"], edge["y1"]
    x2, y2 = edge["x2"], edge["y2"]
    half_cw = column_width / 2.0; tol     = 0.001
    dx = abs(x2 - x1)
    dy = abs(y2 - y1)
    if dx > tol and dy <= tol:
        if x2 > x1:
            x1 = x1 + half_cw; x2 = x2 - half_cw
        else:
            x1 = x1 - half_cw; x2 = x2 + half_cw
    elif dy > tol and dx <= tol:
        if y2 > y1:
            y1 = y1 + half_cw; y2 = y2 - half_cw
        else:
            y1 = y1 - half_cw; y2 = y2 + half_cw
    if abs(x2 - x1) < tol and abs(y2 - y1) < tol:
        return None
    z_bottom = base_z
    z_top = base_z + panel_height - (beam_depth if trim_top else 0.0)
    if z_top <= z_bottom + tol:
        return None
    c1 = rg.Point3d(x1, y1, z_bottom)
    c2 = rg.Point3d(x2, y2, z_bottom)
    c3 = rg.Point3d(x2, y2, z_top)
    c4 = rg.Point3d(x1, y1, z_top)
    srf = rg.NurbsSurface.CreateFromCorners(c1, c2, c3, c4)
    if srf:
        srf_id = sc.doc.Objects.AddSurface(srf)
        return srf_id
    return None
def draw_wall_panels_for_floor(Building, floor_label, floor_index, all_edges, base_z, floor_height, parapet_height, floor_panels_above, trim_top_override=None):
    gs = Building["grid"]["spacing"]
    column_width = Building["structure"]["columns"]["width"]
    beam_depth   = Building["structure"]["plinth_beams"]["depth"]
    layer_name = "Wall_Panels_{}".format(floor_index)
    if not rs.IsLayer(layer_name):
        rs.AddLayer(layer_name, (160, 180, 200))
    wall_panel_ids = []
    wall_panel_edge_map = {}
    wall_panel_info_map = {}
    full_height_count = 0; parapet_count = 0
    transition_count = 0
    for edge in all_edges:
        is_transition = edge.get("is_transition", False)
        if is_transition:
            panel_height = floor_height
            panel_color  = (140, 170, 210)
            trim_top     = True    # beam above exists at transition edge
            trim_sides   = True    # columns at ends exist — inset sides
            transition_count += 1
        else:
            has_cover_above = does_floor_above_cover_edge(edge, floor_panels_above, gs)
            if has_cover_above:
                panel_height = floor_height
                panel_color  = (180, 200, 220)
                trim_top     = True    # full-height: beam above exists
                trim_sides   = True    # columns at ends — inset sides
                full_height_count += 1
            else:
                panel_height = parapet_height
                panel_color  = (200, 180, 160)
                trim_top     = False   # parapet: no beam above — no top trim
                trim_sides   = False   # parapet: column ended below — no side trim
                parapet_count += 1
        if trim_top_override is not None:
            trim_top   = trim_top_override
            trim_sides = False   # basement skirt also has no column above it
        eff_column_width = column_width if trim_sides else 0.0
        srf_id = create_wall_panel_surface(
            edge, base_z, panel_height, eff_column_width, beam_depth, trim_top)
        if srf_id:
            rs.ObjectLayer(srf_id, layer_name)
            rs.ObjectColor(srf_id, panel_color)
            _apply_material(srf_id, _mat_facade_paint())
            wall_panel_ids.append(srf_id)
            edge_key = (round(edge["x1"], 4), round(edge["y1"], 4), round(edge["x2"], 4), round(edge["y2"], 4))
            wall_panel_edge_map[str(srf_id)] = edge_key
            wall_panel_info_map[str(srf_id)] = {
                "edge": edge, "base_z": base_z, "panel_height": panel_height,
                "floor_index": floor_index, "edge_key": edge_key
            }
    print("  {} wall panels drawn: {} full-height, {} transition, {} parapet ({}m)".format(
        floor_label, full_height_count, transition_count, parapet_count, parapet_height))
    _enforce_wireframe()
    sc.doc.Views.Redraw()
    return wall_panel_ids, wall_panel_edge_map, layer_name, wall_panel_info_map
def interactive_wall_panel_deletion(Building, floor_label, floor_index, wall_panel_ids, wall_panel_edge_map, layer_name, wall_panel_info_map):
    """Silently keep ALL wall panels — no dialog, no per-floor popup, no user selection.; Called from process_wall_panels_for_floor; behaviour is now fully automatic.
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
def process_wall_panels_for_floor(Building, floor_label, floor_index, floor_panel_keys, floor_panels_above, base_z, floor_height, parapet_height, trim_top_override=None):
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
        Building, floor_label, floor_index, all_edges, base_z, floor_height, parapet_height,
        floor_panels_above, trim_top_override=trim_top_override)
    interactive_wall_panel_deletion(Building, floor_label, floor_index,
                                     wall_panel_ids, wall_panel_edge_map, layer_name, wall_panel_info_map)
    print("  {} wall panelling complete.".format(floor_label))
    print_section_footer()
def process_all_wall_panels(Building):
    """Generate wall panels for ALL floors in one automated step.; Shows a SINGLE start dialog to the user — no per-floor popups.
    All panels are kept automatically; nothing is deleted.; """
    nf = len(Building["structure"]["columns"]["top_points_per_floor"])
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
                next_panel_z = next_beam_z + bd; floor_height = next_panel_z - panel_z
            else:
                floor_height = Building["floors"]["floor_heights"][fi + 1] if fi + 1 < len(Building["floors"]["floor_heights"]) else 3.0
        else:
            floor_height = Building["floors"]["floor_heights"][fi] if fi < len(Building["floors"]["floor_heights"]) else 3.0
        if fi == 0 and panel_z > 0.001:
            basement_skirt_height = panel_z
            process_wall_panels_for_floor(Building, "WALL PANELS BASEMENT", -1,
                                          floor_panel_keys, floor_panel_keys,
                                          0.0, basement_skirt_height, basement_skirt_height,
                                          trim_top_override=False)
        process_wall_panels_for_floor(Building, fl, fi, floor_panel_keys, floor_panels_above,
                                       panel_z, floor_height, parapet_height)
    _enforce_wireframe()
    rs.Redraw()
    tw = sum(len(w) for w in Building["wall_panels"]["wall_panel_ids_per_floor"])
    print_section_header("WALL PANELLING COMPLETE")
    print("  Total wall panels generated: {}".format(tw))
    print("  Deleted: 0  (all panels kept)")
    print_section_footer()
def get_wall_outward_direction(edge):
    """From a wall panel edge, determine the outward extrusion direction perpendicular to the wall.; Returns (dx, dy) unit direction pointing away from the cell interior.
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
    """Clamp wall arch extrusion so it stays within the outer plot boundary."""; dx, dy = direction
    half_l = plot_length / 2.0; half_w = plot_width / 2.0
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
    - Large holes (gap ~0.72) near the panel centre; - Small holes (gap ~0.25) near the panel edges
    - A gentle sine-wave ripple layered on top for organic variation; - A subtle diagonal wave so adjacent holes feel staggered in size
    Parameters; ----------
    col, row        : int — zero-based cell indices; cols, rows      : int — total grid dimensions
    Returns float gap in [0.22 .. 0.74]; """
    GAP_MAX  = 0.74   # largest hole (centre)
    GAP_MIN  = 0.22   # smallest hole (edge / corner)
    u = (col + 0.5) / cols * 2.0 - 1.0   # -1 at left,  +1 at right
    v = (row + 0.5) / rows * 2.0 - 1.0   # -1 at bottom, +1 at top
    dist = math.sqrt(u * u + v * v) / math.sqrt(2.0)
    primary = 0.5 + 0.5 * math.cos(dist * math.pi)   # 1.0 at centre, 0.0 at corner
    freq_u = math.pi * 2.5; freq_v = math.pi * 2.0
    ripple = 0.12 * math.sin(u * freq_u + v * freq_v)
    checker = 0.06 * (1 if (col + row) % 2 == 0 else -1)
    raw = primary + ripple + checker
    raw = max(0.0, min(1.0, raw))
    return GAP_MIN + raw * (GAP_MAX - GAP_MIN)
def _create_perforated_panel_mesh(corners_3d, pw, ph, color, layer_name,
                                   rows=None, cols=None):
    """Build a flat rectangular panel as a Rhino Mesh with parametric square holes.; Each cell gets an independently computed hole size via _hole_gap_for_cell(),
    producing a halftone-style gradient: large open holes at the centre fading; to small holes at the edges, with a sine-wave ripple for organic variation.
    The per-cell hole is implemented by placing the 4 hole-corner vertices at a; variable inset from the cell boundary, then omitting the centre quad.
    Parameters; ----------
    corners_3d  : list of 4 rg.Point3d  [bl, br, tr, tl]; pw, ph      : float — panel width and height in world units
    color       : (r,g,b); layer_name  : str
    rows, cols  : int — hole grid; auto if None (~1 cell per 0.35 m); Returns list of added Rhino object GUIDs (one Mesh per panel).
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
            u0 = col       / float(cols)
            u1 = (col + 1) / float(cols)
            v0 = row       / float(rows)
            v1 = (row + 1) / float(rows)
            gap  = _hole_gap_for_cell(col, row, cols, rows)
            marg = (1.0 - gap) / 2.0
            ui0 = u0 + marg * (u1 - u0)
            ui1 = u1 - marg * (u1 - u0)
            vi0 = v0 + marg * (v1 - v0)
            vi1 = v1 - marg * (v1 - v0)
            BL  = _add_v(_pt(u0,  v0))
            BR  = _add_v(_pt(u1,  v0))
            TR  = _add_v(_pt(u1,  v1))
            TL  = _add_v(_pt(u0,  v1))
            BLi = _add_v(_pt(ui0, vi0))
            BRi = _add_v(_pt(ui1, vi0))
            TRi = _add_v(_pt(ui1, vi1))
            TLi = _add_v(_pt(ui0, vi1))
            _add_quad(BL,  BR,  BRi, BLi)
            _add_quad(TLi, TRi, TR,  TL)
            _add_quad(BL,  BLi, TLi, TL)
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
    """Create an arch extrusion from a wall panel outward.; All 5 surfaces (2 side walls, far end wall, top cap, bottom slab) are built
    as perforated mesh panels with square holes punched through them.; """
    dx, dy = direction
    x1, y1 = edge["x1"], edge["y1"]
    x2, y2 = edge["x2"], edge["y2"]
    z_bottom = base_z; z_top    = base_z + wall_height
    if ext_dist < 0.01:
        return []
    created_ids = []
    COLOR_WALL = (220, 160, 100)
    fx1 = x1 + dx * ext_dist; fy1 = y1 + dy * ext_dist
    fx2 = x2 + dx * ext_dist; fy2 = y2 + dy * ext_dist
    wall_len = math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)
    side_len = math.sqrt((fx1 - x1) ** 2 + (fy1 - y1) ** 2)   # == ext_dist
    created_ids += _create_perforated_panel_mesh(
        [rg.Point3d(x1, y1, z_bottom), rg.Point3d(fx1, fy1, z_bottom),
         rg.Point3d(fx1, fy1, z_top),  rg.Point3d(x1, y1, z_top)],
        side_len, wall_height, COLOR_WALL, layer_name)
    created_ids += _create_perforated_panel_mesh(
        [rg.Point3d(x2, y2, z_bottom), rg.Point3d(fx2, fy2, z_bottom),
         rg.Point3d(fx2, fy2, z_top),  rg.Point3d(x2, y2, z_top)],
        side_len, wall_height, COLOR_WALL, layer_name)
    far_len = math.sqrt((fx2 - fx1) ** 2 + (fy2 - fy1) ** 2)
    created_ids += _create_perforated_panel_mesh(
        [rg.Point3d(fx1, fy1, z_bottom), rg.Point3d(fx2, fy2, z_bottom),
         rg.Point3d(fx2, fy2, z_top),    rg.Point3d(fx1, fy1, z_top)],
        far_len, wall_height, COLOR_WALL, layer_name)
    created_ids += _create_perforated_panel_mesh(
        [rg.Point3d(x1, y1, z_top),  rg.Point3d(x2, y2, z_top),
         rg.Point3d(fx2, fy2, z_top), rg.Point3d(fx1, fy1, z_top)],
        wall_len, side_len, COLOR_WALL, layer_name)
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
    """XY bounding box of projected volume: (x_min, y_min, x_max, y_max)."""; dx, dy = direction
    xs = [edge["x1"], edge["x2"],
          edge["x1"] + dx * depth, edge["x2"] + dx * depth]
    ys = [edge["y1"], edge["y2"],
          edge["y1"] + dy * depth, edge["y2"] + dy * depth]
    return (min(xs), min(ys), max(xs), max(ys))
def _boxes_collide_3d(fp_a, z_bot_a, z_top_a, fp_b, z_bot_b, z_top_b, tol=0.01):
    """True only when two box volumes have interior overlap in BOTH XY and Z.; Key fix: boxes on different floors (non-overlapping Z ranges) are NEVER
    in collision even if their XY footprints coincide.  This was the root; cause of upper-floor extrusions being silently skipped.
    """
    if z_top_a <= z_bot_b + tol: return False
    if z_top_b <= z_bot_a + tol: return False
    if fp_a[2] <= fp_b[0] + tol: return False
    if fp_b[2] <= fp_a[0] + tol: return False
    if fp_a[3] <= fp_b[1] + tol: return False
    if fp_b[3] <= fp_a[1] + tol: return False
    return True
def process_wall_extrusions(Building):
    """ELEVATION STEP 1: Offset-checkerboard closed-box extrusion, all floors.; Covers ALL floors except basement (floor_index == -1).
    Covers ALL four facade faces on every eligible floor.; Panel eligibility
    -----------------; A panel is eligible when panel_height equals the floor structural height,
    meaning it is a FULL-HEIGHT or TRANSITION panel — not a parapet.; Test: panel_height > parapet_height + 0.05
    Offset-checkerboard pattern; ---------------------------
    For each (floor_index, face_orientation) bucket, panels are sorted along; the face axis (X midpoint for top/bottom, Y midpoint for left/right).
    Phase alternates by floor_index:
        fi even → extrude positions 0, 2, 4 …; fi odd  → extrude positions 1, 3, 5 …
    Adjacent floors always project opposite halves → offset checkerboard.; Collision safety (3-D)
    ----------------------; Footprints are stored with their Z range (base_z, base_z + panel_height).
    Two boxes only collide when they overlap in BOTH XY and Z.; Boxes on different floors at the same XY position are NEVER in collision.
    This was the critical bug causing upper floors to be skipped.; Geometry: 5-surface closed box (2 side walls + far face + top cap + bottom slab).
    Depth: 1.5 m fixed.; """
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
    EXT_DEPTH  = 1.5; layer_name = "Wall_Extrusions"
    if not rs.IsLayer(layer_name):
        rs.AddLayer(layer_name, (220, 160, 100))
    plot_length = Building["plot"]["length"]
    plot_width  = Building["plot"]["width"]
    parapet_h   = Building["wall_panels"]["parapet_height"]
    wall_lookup = build_wall_panel_lookup(Building)
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
        if orient in ("top", "bottom"):
            axis_pos = round((edge["x1"] + edge["x2"]) / 2.0, 4)
        else:
            axis_pos = round((edge["y1"] + edge["y2"]) / 2.0, 4)
        bz = info.get("base_z", 0.0)
        buckets[(fi, orient)].append((axis_pos, bz, ph, edge, direction))
    for key in buckets:
        buckets[key].sort(key=lambda t: t[0])
    total_eligible = sum(len(v) for v in buckets.values())
    print("  Full-height panels eligible (all floors except basement): {}".format(total_eligible))
    print("  Generating offset-checkerboard closed-box extrusions (depth {:.1f} m)...".format(EXT_DEPTH))
    committed         = []
    all_extrusion_ids = []
    n_drawn = n_skip_b = n_skip_c = 0
    for (fi, orient) in sorted(buckets.keys()):
        panels = buckets[(fi, orient)]
        phase = fi % 2
        for pos_idx, (axis_pos, bz, ph, edge, direction) in enumerate(panels):
            if pos_idx % 2 != phase:
                continue   # gap position for this floor
            clamped = clamp_wall_extrusion_to_plot(
                edge, direction, EXT_DEPTH, plot_length, plot_width)
            if clamped < 0.01:
                n_skip_b += 1
                continue
            fp = _box_fp(edge, direction, clamped)
            z_bot = bz; z_top = bz + ph
            collision = False
            for (ex_fp, ex_zb, ex_zt) in committed:
                if _boxes_collide_3d(fp, z_bot, z_top, ex_fp, ex_zb, ex_zt):
                    collision = True
                    break
            if collision:
                n_skip_c += 1
                continue
            ids = create_wall_arch_extrusion(
                edge, direction, clamped, bz, ph, layer_name)
            if ids:
                all_extrusion_ids.extend(ids)
                committed.append((fp, z_bot, z_top))
                n_drawn += 1
                dl = {(0,-1):"S",(0,1):"N",(-1,0):"W",(1,0):"E"}.get(direction,"?")
                print("    [{:3d}] fl={:2d} {:6s} @{:6.1f} z={:.1f}-{:.1f}  {}  d={:.1f}m".format(
                    n_drawn, fi, orient, axis_pos, z_bot, z_top, dl, clamped))
                ex1, ey1 = edge["x1"], edge["y1"]
                ex2, ey2 = edge["x2"], edge["y2"]
                edx = abs(ex2 - ex1)
                edy = abs(ey2 - ey1)
                if edx > edy:   # N/S face — constant Y
                    ext_axis     = 'x'
                    ext_wall_pos = round((ey1 + ey2) / 2.0, 4)
                    ext_smin     = round(min(ex1, ex2), 4)
                    ext_smax     = round(max(ex1, ex2), 4)
                else:           # E/W face — constant X
                    ext_axis     = 'y'
                    ext_wall_pos = round((ex1 + ex2) / 2.0, 4)
                    ext_smin     = round(min(ey1, ey2), 4)
                    ext_smax     = round(max(ey1, ey2), 4)
                Building["elevation"]["wall_extrusion_footprints"].append(
                    (ext_axis, ext_wall_pos, ext_smin, ext_smax, z_bot, z_top))
    _enforce_wireframe()
    sc.doc.Views.Redraw()
    Building["elevation"]["wall_extrusion_ids"] = all_extrusion_ids
    pct = 100.0 * n_drawn / max(1, total_eligible)
    print("\n  Eligible panels (full-height, all floors) : {}".format(total_eligible))
    print("  Extruded (offset checkerboard)            : {} ({:.0f}%)".format(n_drawn, pct))
    if n_skip_b: print("  Skipped – plot boundary                   : {}".format(n_skip_b))
    if n_skip_c: print("  Skipped – 3D collision                    : {}".format(n_skip_c))
    print("  Box surfaces created                      : {}".format(len(all_extrusion_ids)))
    print_section_footer()
def get_uncovered_panel_keys(Building):
    """Find all floor panel keys that have NO roof/floor panel above them.; Returns dict: floor_index -> set of uncovered cell keys.
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
    """Create a rectangular arch with specified orientation.; orientation: "NS" = opens north-south (Y direction, walls on X sides)
                 "EW" = opens east-west (X direction, walls on Y sides)
    Two side walls + top cap. Front/back open.; All surfaces are built as perforated mesh panels with square holes.
    inset_offset: small inward shrink (m) so roof panels don't collide with wall panels.; """
    off = inset_offset
    cx  = panel_key[0] + off
    cy  = panel_key[1] + off
    cx2 = round(panel_key[0] + gs - off, 4)
    cy2 = round(panel_key[1] + gs - off, 4)
    z_bottom = base_z; z_top    = base_z + arch_height
    created_ids = []
    COLOR_SIDE = (180, 150, 200)
    COLOR_TOP  = (200, 180, 220)
    pw_side = round(cy2 - cy, 4) if orientation == "NS" else round(cx2 - cx, 4)
    top_w   = round(cx2 - cx, 4)
    top_d   = round(cy2 - cy, 4)
    if orientation == "NS":
        created_ids += _create_perforated_panel_mesh(
            [rg.Point3d(cx,  cy,  z_bottom), rg.Point3d(cx,  cy2, z_bottom),
             rg.Point3d(cx,  cy2, z_top),    rg.Point3d(cx,  cy,  z_top)],
            pw_side, arch_height, COLOR_SIDE, layer_name)
        created_ids += _create_perforated_panel_mesh(
            [rg.Point3d(cx2, cy,  z_bottom), rg.Point3d(cx2, cy2, z_bottom),
             rg.Point3d(cx2, cy2, z_top),    rg.Point3d(cx2, cy,  z_top)],
            pw_side, arch_height, COLOR_SIDE, layer_name)
    else:  # "EW"
        created_ids += _create_perforated_panel_mesh(
            [rg.Point3d(cx,  cy,  z_bottom), rg.Point3d(cx2, cy,  z_bottom),
             rg.Point3d(cx2, cy,  z_top),    rg.Point3d(cx,  cy,  z_top)],
            pw_side, arch_height, COLOR_SIDE, layer_name)
        created_ids += _create_perforated_panel_mesh(
            [rg.Point3d(cx,  cy2, z_bottom), rg.Point3d(cx2, cy2, z_bottom),
             rg.Point3d(cx2, cy2, z_top),    rg.Point3d(cx,  cy2, z_top)],
            pw_side, arch_height, COLOR_SIDE, layer_name)
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
                        best_dist = d; best_key = k
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
    """ELEVATION STEP 2 — Automatic vertical arch extrusion (4 m fixed height).; Reuses the shared ElevationExtrusionDialog already shown by
    process_wall_extrusions (stored in Building["_elev_dlg"]).; If the dialog has not been shown yet it shows it now.
    Algorithm; ---------
    1.  Check vertical_choice from shared dialog.; 2.  Collect all uncovered terrace panel keys with their exact Z
        (from live Rhino bounding-boxes via build_floor_panel_id_to_key_map).
    3.  Checker pattern identical to wall extrusions selects 30-40%.; 4.  All arches are exactly 4 m tall.
    5.  3-D collision guard — no surface intersections.; """
    print_section_header("ELEVATION STEP 2: VERTICAL ARCH EXTRUSION (AUTO)")
    _elev_dlg = Building.get("_elev_dlg")
    if _elev_dlg is None:
        _elev_dlg = ElevationExtrusionDialog()
        _elev_dlg.ShowModal(Rhino.UI.RhinoEtoApp.MainWindow)
        Building["_elev_dlg"] = _elev_dlg
    if _elev_dlg.vertical_choice != "proceed":
        print("  Skipping vertical arch extrusions.")
        print_section_footer()
        return
    ARCH_HEIGHT  = 4.0    # metres — fixed, no variation
    ARCH_ORIENT  = "NS"   # North-South passage (open Y faces)
    layer_name = "Vertical_Extrusions"
    if not rs.IsLayer(layer_name):
        rs.AddLayer(layer_name, (180, 150, 200))
    gs  = Building["grid"]["spacing"]
    pth = Building["panels"]["panel_thickness"]
    bd  = Building["structure"]["plinth_beams"]["depth"]
    uncovered = get_uncovered_panel_keys(Building)
    if not uncovered:
        print("  No uncovered panels found.  All panels have roof/floor above.")
        print_section_footer()
        return
    total_uncovered = sum(len(v) for v in uncovered.values())
    print("  {} uncovered (terrace) panels across {} floor(s).".format(
        total_uncovered, len(uncovered)))
    pid_to_info = build_floor_panel_id_to_key_map(Building)
    cell_z_map = {}   # (fi, cx, cy) -> panel_z  (top-of-slab Z)
    for info in pid_to_info.values():
        fi  = info["floor_index"]
        ck  = info["cell_key"]
        pz  = info["panel_z"]
        key = (fi, ck[0], ck[1])
        if key not in cell_z_map or pz < cell_z_map[key]:
            cell_z_map[key] = pz
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
    if pct > 42.0:
        checker_selected = [e for i, e in enumerate(checker_selected) if i % 4 != 0]
        n_sel = len(checker_selected)
        pct   = 100.0 * n_sel / max(1, total_uncovered)
    print("  Checker selection : {} panels  ({:.0f}% of {} uncovered)".format(
        n_sel, pct, total_uncovered))
    print("  Height            : {:.0f} m (fixed)".format(ARCH_HEIGHT))
    print("  Orientation       : NS (North-South passage)")
    committed    = []   # (footprint, z_bot, z_top)
    all_arch_ids = []
    n_created    = 0; n_collide    = 0
    for (fi, ck, bz) in checker_selected:
        fp    = _vert_arch_footprint(ck, gs)
        z_bot = bz; z_top = bz + ARCH_HEIGHT
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
    _enforce_wireframe()
    sc.doc.Views.Redraw()
    Building["elevation"]["vertical_extrusion_ids"] = all_arch_ids
    print("\n  Arches created  : {}  ({:.0f}% of uncovered panels)".format(
        n_created, 100.0 * n_created / max(1, total_uncovered)))
    if n_collide:
        print("  Skipped (collision): {}".format(n_collide))
    print("  Total surfaces  : {}".format(len(all_arch_ids)))
    print_section_footer()
ELEVATION_DIRECTIONS = [
    {"name": "NORTH", "view_cmd": "_-SetView _World _Front",  "axis": "Y", "facing": "north"},
    {"name": "EAST",  "view_cmd": "_-SetView _World _Right",  "axis": "X", "facing": "east"},
    {"name": "SOUTH", "view_cmd": "_-SetView _World _Back",   "axis": "Y", "facing": "south"},
    {"name": "WEST",  "view_cmd": "_-SetView _World _Left",   "axis": "X", "facing": "west"},
]
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
class ProjectIntroDialog(forms.Dialog[bool]):
    """Pixel Perfect Living — animated sci-fi intro slide."""
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
        self._CW   = 560; self._CH   = 160
        self._CELL = 8      # base cell size (px)
        import math, random; self._math   = math
        self._random = random; COLS = self._CW // self._CELL
        ROWS = self._CH // self._CELL
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
        self._hmap = hmap; self._COLS = COLS
        self._ROWS = ROWS
        rng = random.Random(42)
        self._cell_phase  = [[rng.random() * 6.28 for _ in range(COLS)] for _ in range(ROWS)]
        self._cell_speed  = [[0.35 + rng.random() * 0.75 for _ in range(COLS)] for _ in range(ROWS)]
        self._cell_psize  = [[rng.choice([6, 7, 8, 5]) for _ in range(COLS)] for _ in range(ROWS)]
        self._cell_pal    = [[rng.randint(0, len(self._PIX_PALETTES)-1) for _ in range(COLS)] for _ in range(ROWS)]
        self._iv = forms.ImageView()
        self._iv.Size = drawing.Size(self._CW, self._CH)
        self._iv.Image = self._make_bmp()
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
        body_panel = forms.Panel()
        body_panel.Padding = drawing.Padding(30, 16, 30, 16)
        def _tag(txt):
            l = forms.Label()
            l.Text = txt
            l.Font = drawing.Font(drawing.FontFamily("Georgia"), 8, drawing.FontStyle.Italic)
            l.TextColor = make_color(*BH_WHITE)
            return l
        def _sep(rgb):
            p = forms.Panel()
            p.BackgroundColor = make_color(*rgb)
            p.Height = 3
            return p
        def _val_box(txt, rgb, size=14):
            tb = forms.TextBox()
            tb.Text = txt
            tb.Font = drawing.Font(drawing.FontFamily("Impact"), size, drawing.FontStyle.Bold)
            tb.TextColor    = make_color(*rgb)
            tb.ReadOnly     = True; tb.ShowBorder   = False
            tb.MinimumSize  = drawing.Size(200, size * 2 + 4)
            return tb
        proj_tag = _tag("PROJECT NAME")
        proj_val = _val_box("PIXEL PERFECT LIVING",       BH_WHITE, 14)
        course_tag = _tag("COURSE")
        course_val = _val_box("PROGRAMMING AND SIMULATION", BH_WHITE, 13)
        arch_tag = _tag("PROJECT ARCHITECT")
        arch_val = _val_box("GOWTHAMAN MARIMUTHU",         BH_RED, 14)
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
        bl = forms.TableLayout()
        bl.Spacing = drawing.Size(0, 8)
        for w in [proj_tag,   proj_val,   _sep(DIALOG_ACCENT_PINK),
                  course_tag, course_val, _sep(DIALOG_ACCENT_YELLOW),
                  arch_tag,   arch_val,   _sep(DIALOG_ACCENT_BLUE),
                  btn_tl]:
            bl.Rows.Add(forms.TableRow(forms.TableCell(w, True)))
        body_panel.Content = bl
        ml = forms.TableLayout()
        ml.Spacing = drawing.Size(0, 0)
        ml.Rows.Add(forms.TableRow(forms.TableCell(header_panel, True)))
        ml.Rows.Add(forms.TableRow(forms.TableCell(strip_tl,     True)))
        ml.Rows.Add(forms.TableRow(forms.TableCell(body_panel,   True)))
        self.Content = ml
        self._timer = forms.UITimer()
        self._timer.Interval = 0.08; self._timer.Elapsed += self._on_tick
        self._timer.Start()
        self.Closed += self._on_closed
    def _make_bmp(self):
        import math, random; m   = self._math
        rng = random.Random(int(self._phase * 137.0))
        bmp = drawing.Bitmap(self._CW, self._CH,
                             drawing.PixelFormat.Format32bppRgba)
        g = drawing.Graphics(bmp)
        try:
            g.FillRectangle(
                drawing.SolidBrush(drawing.Color(245.0/255, 245.0/255, 245.0/255, 1.0)),
                drawing.RectangleF(0, 0, self._CW, self._CH))
            gpen = drawing.Pen(
                drawing.Color(210.0/255, 210.0/255, 210.0/255, 80.0/255), 0.5)
            for c in range(self._COLS + 1):
                x = c * self._CELL
                g.DrawLine(gpen, x, 0, x, self._CH)
            for r in range(self._ROWS + 1):
                y = r * self._CELL
                g.DrawLine(gpen, 0, y, self._CW, y)
            t = self._phase
            for r in range(self._ROWS):
                for c in range(self._COLS):
                    if r < self._hmap[c]:
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
                    phase  = self._cell_phase[r][c]
                    speed  = self._cell_speed[r][c]
                    breathe = 0.5 + 0.5 * m.sin(t * speed + phase)
                    tower_depth = (r - self._hmap[c]) / max(1, self._ROWS - self._hmap[c])
                    base_alpha  = 0.3 + 0.5 * tower_depth; prob = base_alpha + 0.5 * breathe
                    if rng.random() > prob:
                        continue
                    alpha_v = int(min(255, max(40,
                        (base_alpha + 0.6 * breathe) * 255)))
                    pal_idx = self._cell_pal[r][c]
                    is_accent = ((r * 3 + c * 7 + int(t * 1.5)) % 17 == 0)
                    col = self._PIX_PALETTES[pal_idx if is_accent else 0]
                    sz  = self._cell_psize[r][c]
                    off = (self._CELL - sz) // 2
                    px  = c * self._CELL + off; py  = r * self._CELL + off
                    g.FillRectangle(
                        drawing.SolidBrush(
                            drawing.Color(col[0]/255.0, col[1]/255.0, col[2]/255.0,
                                alpha_v/255.0)),
                        drawing.RectangleF(px, py, sz, sz))
                    if breathe > 0.88 and sz >= 6:
                        core = max(1, sz - 4)
                        g.FillRectangle(
                            drawing.SolidBrush(
                                drawing.Color(1.0, 1.0, 1.0,
                                    (alpha_v * 0.65) / 255.0)),
                            drawing.RectangleF(px + 2, py + 2, core, core))
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
    def _on_tick(self, sender, e):
        self._phase += 0.07; old_img = self._iv.Image
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
class FacadeSubdivisionDialog(forms.Dialog[bool]):
    """Single combined dialog shown ONCE for all 4 elevations.; Replaces the individual ElevationStartDialog, SubdivisionDirectionDialog,
    and GlassSelectionDialog popups.  The dialog is fully informational — it
    describes what will happen automatically — and asks for one confirmation:
      > START ALL FACADES   ->  user_choice = "start"; [ SKIP ALL ]          ->  user_choice = "skip"
      ABORT                 ->  user_choice = "cancel"
    Auto settings (fixed, never asked):
      Subdivision direction : VERTICAL (3 equal columns per full-height panel); Glass selection       : automatic random pattern, target 40-50% glazing
      Window frames         : Schuco AWS 75 BS.SI aluminium, inset 40 mm
    """
    def __init__(self, panel_counts):
        """panel_counts : dict {elevation_name: int}"""
        super(FacadeSubdivisionDialog, self).__init__()
        self.BackgroundColor = make_color(*BH_BLACK)
        self.user_choice = None; self.Title = "FACADE SUBDIVISION  //  ALL ELEVATIONS"
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
class ElevationStartDialog(forms.Dialog[bool]):
    def __init__(self, elevation_name, panel_count):
        super(ElevationStartDialog, self).__init__()
        self.user_choice = "start"
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
        HEADER_COLOR = BH_BLACK; SEP_COLOR    = BH_RED
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
        self.direction = "V" if self.radio_v.Checked else "H"; self.count = 3 if self.radio_3.Checked else 2
        self.Close(True)
    def on_cancel(self, s, e):
        self.Close(False)
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
        HEADER_COLOR = BH_BLACK; SEP_COLOR    = BH_RED
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
        HEADER_COLOR = BH_BLACK; SEP_COLOR    = BH_RED
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
        bldg = drawing.GraphicsPath()
        _gp_add_polygon(bldg, [
            drawing.PointF(20*s, 40*s), drawing.PointF(20*s, 24*s),
            drawing.PointF(26*s, 24*s), drawing.PointF(26*s, 18*s),
            drawing.PointF(32*s, 18*s), drawing.PointF(32*s, 12*s),
            drawing.PointF(40*s, 12*s), drawing.PointF(40*s, 18*s),
            drawing.PointF(44*s, 18*s), drawing.PointF(44*s, 40*s)])
        g.FillPath(_icon_brush(BH_RED, 20), bldg)
        g.DrawPath(_icon_pen(BH_WHITE, 1.2), bldg)
        g.DrawLine(pen_thin, int(20*s), int(32*s), int(44*s), int(32*s))
        g.DrawLine(pen_thin, int(26*s), int(24*s), int(40*s), int(24*s))
        for (wx,wy) in [(22,26),(30,26),(22,34),(34,34),(42,34),(34,20),(40,14)]:
            g.FillRectangle(_icon_brush(BH_BLACK), drawing.RectangleF(wx*s, wy*s, 2*s, 3*s))
        g.DrawEllipse(_icon_pen(BH_WHITE, 2), drawing.RectangleF(4*s, 6*s, 12*s, 12*s))
        g.DrawEllipse(_icon_pen(BH_WHITE, 1.2), drawing.RectangleF(7*s, 9*s, 6*s, 6*s))
        g.DrawLine(pen_thick, int(14*s), int(16*s), int(24*s), int(26*s))
        g.DrawLine(_icon_pen(BH_WHITE, 1.8), int(19*s), int(21*s), int(22*s), int(18*s))
        g.DrawLine(_icon_pen(BH_WHITE, 1.8), int(22*s), int(24*s), int(25*s), int(21*s))
        g.DrawLine(_icon_pen(BH_RED, 3), int(28*s), int(30*s), int(32*s), int(36*s))
        g.DrawLine(_icon_pen(BH_RED, 3), int(32*s), int(36*s), int(42*s), int(22*s))
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
        bp = forms.Panel()
        bp.BackgroundColor = make_color(*DIALOG_SURFACE_DEEP)
        bp.Padding = drawing.Padding(28, 22, 28, 22)
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
        HEADER_COLOR = BH_BLACK; SEP_COLOR    = BH_RED
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
    """Return True only if this object is a FLAT wall panel facing the given direction.; A genuine wall panel is a planar vertical surface with extent in Z and in
    exactly ONE of X or Y.  Arch-extrusion side/end walls and vertical-extrusion; walls also look like vertical surfaces, but they always have non-trivial
    extent in BOTH X and Y (they form the sides of a 3-D arch volume).; We reject any surface whose bounding box has significant depth in both
    horizontal directions — that immediately catches all extrusion geometry.; """
    bb = _get_wall_panel_bounds(srf_id)
    if not bb:
        return False
    dx = bb["x_max"] - bb["x_min"]
    dy = bb["y_max"] - bb["y_min"]
    dz = bb["z_max"] - bb["z_min"]
    FLAT = 0.02   # a genuine wall panel has one XY dim collapsing to near zero
    MIN  = 0.05   # must have meaningful extent in the other dim
    if dz < MIN:
        return False
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
    FLAT = 0.02; MIN  = 0.05
    if dx > MIN and dy <= FLAT:
        return "ns"
    if dy > MIN and dx <= FLAT:
        return "ew"
    return None
def _build_wall_panel_whitelist(Building):
    """Return a frozenset of every object ID that is a GENUINE wall panel.
    An ID qualifies only when ALL five conditions hold simultaneously:
      1. Present in Building["wall_panels"]["wall_panel_ids_per_floor"]
         (surviving after user-deletion; panels consumed by extrusion have
          already been removed from these lists by the extrusion step)
      2. Still alive in Rhino (rs.IsObject is True); 3. Lives on a layer whose name starts with "Wall_Panels_"
         (not "Wall_Extrusions", "Vertical_Extrusions", "Glass_Panels", …)
      4. NOT listed in Building["elevation"]["wall_extrusion_ids"]; 5. NOT listed in Building["elevation"]["vertical_extrusion_ids"]
    This whitelist is rebuilt fresh each iteration so that panels removed by; previous subdivision operations are automatically excluded.
    """
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
            if not rs.IsObject(pid):
                continue
            try:
                lyr = rs.ObjectLayer(pid)
                if not (lyr and lyr.startswith("Wall_Panels_")):
                    continue
            except Exception:
                continue
            if pid in wall_ext_ids or str(pid) in wall_ext_ids:
                continue
            if pid in vert_ext_ids or str(pid) in vert_ext_ids:
                continue
            whitelist.add(pid)
    return frozenset(whitelist)
def _classify_user_selection(raw_selection, whitelist, elev_facing):
    """Split a raw GetObjects result into accepted/rejected buckets.
    Returns:
        accepted  — list of IDs that are genuine wall panels facing this elevation; rejected  — list of (id, reason_str) for every ignored object
    Rejection reason strings (in priority order):
        "dead"            — object no longer exists in Rhino; "extrusion"       — on Wall_Extrusions or Vertical_Extrusions layer
        "floor_panel"     — on a Floor_Panels_N layer; "glass"           — already a glass panel
        "not_wall_panel"  — not in the Building whitelist for any other reason; "wrong_elevation" — genuine wall panel but faces a different facade
    """
    accepted = []
    rejected = []
    for pid in (raw_selection or []):
        if not rs.IsObject(pid):
            rejected.append((pid, "dead"))
            continue
        try:
            lyr = rs.ObjectLayer(pid)
        except Exception:
            lyr = ""
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
        if not _panel_faces_direction(pid, elev_facing):
            rejected.append((pid, "wrong_elevation"))
            continue
        accepted.append(pid)
    return accepted, rejected
def _get_wall_panels_for_elevation(Building, elevation_facing):
    """Collect all surviving genuine wall panel IDs that face a given elevation.; Uses the whitelist so extrusion surfaces are never included.
    """
    whitelist = _build_wall_panel_whitelist(Building)
    return [pid for pid in whitelist
            if _panel_faces_direction(pid, elevation_facing)]
def _is_full_height_panel(pid, Building):
    """Return True if a panel is a full-height panel resting on beams/columns.; Full-height panels have height > parapet_height (1m) and are not parapets.
    We check via wall_panel_info_map stored in Building.; """
    parapet_h = Building["wall_panels"]["parapet_height"]
    for fi, info_map in enumerate(Building["wall_panels"]["wall_panel_info_per_floor"]):
        ps = str(pid)
        if ps in info_map:
            info = info_map[ps]
            ph = info.get("panel_height", 0)
            return ph > parapet_h + 0.05
    bb = _get_wall_panel_bounds(pid)
    if not bb:
        return False
    h = bb["z_max"] - bb["z_min"]
    return h > parapet_h + 0.05
def subdivide_wall_panel(pid, direction, count, Building, layer_name):
    """Subdivide a wall panel surface into equal strips.; direction: 'H' (horizontal / row cuts) or 'V' (vertical / column cuts)
    count: 2 or 3; Returns list of new surface IDs (original is deleted).
    """
    bb = _get_wall_panel_bounds(pid)
    if bb is None:
        return []
    x_min, x_max = bb["x_min"], bb["x_max"]
    y_min, y_max = bb["y_min"], bb["y_max"]
    z_min, z_max = bb["z_min"], bb["z_max"]
    new_ids = []
    if direction == "H":
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
        dx = x_max - x_min; dy = y_max - y_min
        TOL = 0.01
        if dx > TOL:
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
    """Replace a wall sub-panel with a translucent glass surface.; Puts it on a 'Glass_Panels' layer, bright cyan color.
    Returns new glass surface ID or None.; """
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
            _apply_material(new_id, _mat_glass())
            _remove_panel_from_building(pid, Building)
            rs.DeleteObject(pid)
            return new_id
    return None
def _set_elevation_view(direction_info):
    """Rotate model to the appropriate elevation view."""
    cmd = direction_info["view_cmd"]
    rs.Command(cmd, False)
    rs.ZoomExtents()
    _enforce_wireframe()
    rs.Redraw()
    import time as _time
    _time.sleep(0.4)
def _get_layer_for_panel(pid, Building):
    """Return the layer name of the first floor layer that contains this panel."""
    for fi, id_list in enumerate(Building["wall_panels"]["wall_panel_ids_per_floor"]):
        if pid in id_list:
            return "Wall_Panels_{}".format(fi)
    return "Wall_Panels_0"
def _process_elevation_subdivision(Building, elev_info):
    """Fully automated subdivision + glazing + framing for one elevation.
    Steps (all automatic — no user interaction needed):
      1. Collect all full-height wall panels facing this elevation.; 2. Subdivide each one VERTICALLY into 3 equal columns.
      3. Apply a pseudo-random glass pattern:
           - Each panel gets 1 or 2 of its 3 sub-columns glazed.; - Pattern varies by column index to create visual rhythm.
           - Target 40-50% glazing ratio (above German GEG minimum).
      4. Place a Schuco AWS 75 BS.SI aluminium window frame on every
         glass sub-panel, inset 40 mm from all edges.
    Returns (total_sub_panels_created, total_glass_panels_created).; """
    import random as _random
    elev_name   = elev_info["name"]
    elev_facing = elev_info["facing"]
    _set_elevation_view(elev_info)
    _enforce_wireframe()
    sc.doc.Views.Redraw()
    facade_panels = _get_wall_panels_for_elevation(Building, elev_facing)
    print_section_header("FACADE SUBDIVISION  //  {} ELEVATION".format(elev_name))
    print("  {} genuine wall panels face the {} elevation.".format(
        len(facade_panels), elev_name))
    if not facade_panels:
        print("  No panels to process on {} elevation.".format(elev_name))
        print_section_footer()
        return 0, 0
    all_sub_panel_ids = []   # all child sub-panels created this pass
    basement_sub_ids  = set() # sub-panels from basement — no glass
    total_subdiv_ops  = 0
    seed_val = sum(ord(c) for c in elev_name) + len(facade_panels)
    rng = _random.Random(seed_val)
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
        is_basement = False
        try:
            orig_layer = rs.ObjectLayer(pid)
            if orig_layer and "Wall_Panels_-1" in orig_layer:
                is_basement = True
        except Exception:
            pass
        panel_layer = _get_layer_for_panel(pid, Building)
        new_ids = subdivide_wall_panel(pid, "V", 3, Building, panel_layer)
        all_sub_panel_ids.extend(new_ids)
        total_subdiv_ops += len(new_ids)
        if is_basement:
            for nid in new_ids:
                basement_sub_ids.add(nid)
    _enforce_wireframe()
    sc.doc.Views.Redraw()
    print("  Phase 1 complete: {} sub-panels created on {} elevation.".format(
        total_subdiv_ops, elev_name))
    if basement_sub_ids:
        print("  {} basement sub-panels excluded from glazing.".format(len(basement_sub_ids)))
    eligible_sub_panels = [
        p for p in all_sub_panel_ids
        if rs.IsObject(p) and _is_full_height_panel(p, Building)
        and p not in basement_sub_ids
    ]
    total_glass = 0
    glass_ids   = []
    if not eligible_sub_panels:
        print("  No eligible sub-panels for glazing on {} elevation.".format(elev_name))
    else:
        def _sub_sort_key(pid):
            bb = _get_wall_panel_bounds(pid)
            if bb is None:
                return (0.0, 0.0, 0.0)
            cx = (bb["x_min"] + bb["x_max"]) / 2.0
            cy = (bb["y_min"] + bb["y_max"]) / 2.0
            cz = (bb["z_min"] + bb["z_max"]) / 2.0
            return (round(cz, 2), round(cx, 2), round(cy, 2))
        sorted_subs = sorted(eligible_sub_panels, key=_sub_sort_key)
        groups = []
        i = 0
        while i < len(sorted_subs):
            groups.append(sorted_subs[i:i + 3])
            i += 3
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
        _enforce_wireframe()
        sc.doc.Views.Redraw()
        print("  Phase 2 complete: {} glass panels on {} elevation.".format(
            total_glass, elev_name))
        if total_subdiv_ops > 0:
            ratio = (float(total_glass) / float(total_subdiv_ops)) * 100.0
            print("  Glazing ratio: {:.1f}% of sub-panels glazed (GEG target: >=30%).".format(ratio))
    print_section_footer()
    return total_subdiv_ops, total_glass
def _add_frame_strip(x1, y1, z1, x2, y2, z2, layer, color):
    """Create a flat rectangular surface representing one frame member.; The strip is degenerate in the panel-normal direction (zero thickness).
    Returns new object ID or None.; """
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
def _replace_glass_with_schuco(Building):
    """Replace flat glass panel surfaces with Schüco AWS 75 BS.SI windows; or Schüco ADS 75 HD.SI doors, based on terrace adjacency.
    Classification logic:
      - DOOR: a floor panel (terrace) exists directly OUTSIDE the glass panel; - WINDOW: no floor outside → open air exterior facade
    WINDOW (Schüco AWS 75 BS.SI):
      Full height, 50mm frame all sides, 60mm horizontal transom (Kämpfer); at 40% height dividing into lower fixed + upper tilt-and-turn panes.
    DOOR (Schüco ADS 75 HD.SI):
      Full height, 60mm frame all sides, single glass pane.
    Both are full height — the only difference is the transom bar on windows.; All geometry uses rg.Brep.CreateFromBox — no direction ambiguity.
    """; GLASS_LAYER = "Glass_Panels"
    if not rs.IsLayer(GLASS_LAYER):
        print("  No Glass_Panels layer found.")
        return
    glass_objs = rs.ObjectsByLayer(GLASS_LAYER)
    if not glass_objs:
        print("  No glass panels to process.")
        return
    gs  = Building["grid"]["spacing"]
    bd  = Building["structure"]["plinth_beams"]["depth"]
    tol = 0.02; tol_min = 0.05
    for ln, clr in [("Glass_Windows",      SCHUCO_FRAME_COLOR),
                    ("Glass_Doors",         SCHUCO_FRAME_COLOR),
                    ("Glass_Window_Sills",  (180, 160, 140))]:
        if not rs.IsLayer(ln):
            rs.AddLayer(ln, clr)
    floor_z_list = []
    for fi in range(len(Building["structure"]["columns"]["top_points_per_floor"])):
        ftp = Building["structure"]["columns"]["top_points_per_floor"][fi]
        if ftp:
            floor_z_list.append((fi, ftp[0][2] + bd))
    def _get_floor_index(z_val):
        best_fi, best_d = 0, float('inf')
        for fi, pz in floor_z_list:
            d = abs(z_val - pz)
            if d < best_d:
                best_d = d; best_fi = fi
        return best_fi
    def _get_floor_keys(fi):
        if fi < len(Building["panels"]["panel_coords_per_floor"]):
            return set((round(k[0], 4), round(k[1], 4))
                       for k in Building["panels"]["panel_coords_per_floor"][fi])
        return set()
    def _point_in_any_cell(px, py, cell_keys):
        """Check if point (px, py) falls inside any gs x gs cell."""
        for (kx, ky) in cell_keys:
            if kx - 0.01 <= px <= kx + gs + 0.01 and \
               ky - 0.01 <= py <= ky + gs + 0.01:
                return True
        return False
    def _make_box(p_min, p_max, layer, color):
        """Create a solid Brep box and add to Rhino on the given layer."""
        bx = rg.BoundingBox(p_min, p_max)
        brep = rg.Brep.CreateFromBox(bx)
        if brep and brep.IsValid:
            oid = sc.doc.Objects.AddBrep(brep)
            if oid:
                rs.ObjectLayer(oid, layer)
                rs.ObjectColor(oid, color)
                if color == SCHUCO_GLASS_COLOR:
                    _apply_material(oid, _mat_glass())
                else:
                    _apply_material(oid, _mat_aluminium())
                return oid
        return None
    n_win  = 0; n_door = 0
    for pid in list(glass_objs):
        if not rs.IsObject(pid):
            continue
        bb = rs.BoundingBox(pid)
        if not bb or len(bb) < 8:
            continue
        xs_b = [p.X for p in bb]
        ys_b = [p.Y for p in bb]
        zs_b = [p.Z for p in bb]
        x_min, x_max = min(xs_b), max(xs_b)
        y_min, y_max = min(ys_b), max(ys_b)
        z_min, z_max = min(zs_b), max(zs_b)
        dx = x_max - x_min; dy = y_max - y_min
        dz = z_max - z_min
        if dz < tol_min:
            continue
        fi = _get_floor_index(z_min)
        floor_keys = _get_floor_keys(fi)
        z_min = z_min + CLT_TOTAL_M; dz = z_max - z_min
        if dz < tol_min:
            continue
        wall_type   = None; outer_pos   = 0.0
        inward_sign = 0; is_door     = False
        if dx > tol_min and dy <= tol:
            wall_type = 'x'
            outer_pos = (y_min + y_max) / 2.0
            mid_x = (x_min + x_max) / 2.0
            has_plus  = _point_in_any_cell(mid_x, outer_pos + gs * 0.5, floor_keys)
            has_minus = _point_in_any_cell(mid_x, outer_pos - gs * 0.5, floor_keys)
            if has_plus and not has_minus:
                inward_sign = 1
            elif has_minus and not has_plus:
                inward_sign = -1
            else:
                inward_sign = 1   # default
            check_x = mid_x
            check_y = outer_pos + (-inward_sign) * gs * 0.5
            is_door = _point_in_any_cell(check_x, check_y, floor_keys)
        elif dy > tol_min and dx <= tol:
            wall_type = 'y'
            outer_pos = (x_min + x_max) / 2.0
            mid_y = (y_min + y_max) / 2.0
            has_plus  = _point_in_any_cell(outer_pos + gs * 0.5, mid_y, floor_keys)
            has_minus = _point_in_any_cell(outer_pos - gs * 0.5, mid_y, floor_keys)
            if has_plus and not has_minus:
                inward_sign = 1
            elif has_minus and not has_plus:
                inward_sign = -1
            else:
                inward_sign = 1   # default
            check_x = outer_pos + (-inward_sign) * gs * 0.5
            check_y = mid_y
            is_door = _point_in_any_cell(check_x, check_y, floor_keys)
        else:
            continue
        if is_door:
            fw_size = SCHUCO_DOOR_FRAME_WIDTH   # 60mm
        else:
            fw_size = SCHUCO_WIN_FRAME_WIDTH    # 50mm
        fd = SCHUCO_WIN_FRAME_DEPTH             # 75mm (same for both)
        gd = SCHUCO_DOOR_GLASS_DEPTH if is_door else SCHUCO_WIN_GLASS_DEPTH; layer = "Glass_Doors" if is_door else "Glass_Windows"
        d_outer = outer_pos; d_inner = outer_pos + fd * inward_sign
        d_lo = min(d_outer, d_inner)
        d_hi = max(d_outer, d_inner)
        g_center = (d_outer + d_inner) / 2.0
        g_lo = g_center - gd / 2.0; g_hi = g_center + gd / 2.0
        created = False
        if is_door:
            lf = SCHUCO_DOOR_LEAF_WIDTH   # 30mm door leaf frame
            if wall_type == 'x':
                _make_box(rg.Point3d(x_min,      d_lo, z_min),
                          rg.Point3d(x_max,      d_hi, z_min + fw_size), layer, SCHUCO_FRAME_COLOR)
                _make_box(rg.Point3d(x_min,      d_lo, z_max - fw_size),
                          rg.Point3d(x_max,      d_hi, z_max),           layer, SCHUCO_FRAME_COLOR)
                _make_box(rg.Point3d(x_min,      d_lo, z_min),
                          rg.Point3d(x_min + fw_size, d_hi, z_max),      layer, SCHUCO_FRAME_COLOR)
                _make_box(rg.Point3d(x_max - fw_size, d_lo, z_min),
                          rg.Point3d(x_max,      d_hi, z_max),           layer, SCHUCO_FRAME_COLOR)
                li = x_min + fw_size;  ri = x_max - fw_size; bi = z_min + fw_size;  ti = z_max - fw_size
                _make_box(rg.Point3d(li,      d_lo, bi),
                          rg.Point3d(ri,      d_hi, bi + lf), layer, SCHUCO_SASH_COLOR)
                _make_box(rg.Point3d(li,      d_lo, ti - lf),
                          rg.Point3d(ri,      d_hi, ti),      layer, SCHUCO_SASH_COLOR)
                _make_box(rg.Point3d(li,      d_lo, bi),
                          rg.Point3d(li + lf, d_hi, ti),      layer, SCHUCO_SASH_COLOR)
                _make_box(rg.Point3d(ri - lf, d_lo, bi),
                          rg.Point3d(ri,      d_hi, ti),      layer, SCHUCO_SASH_COLOR)
                _make_box(rg.Point3d(li + lf, g_lo, bi + lf),
                          rg.Point3d(ri - lf, g_hi, ti - lf), layer, SCHUCO_GLASS_COLOR)
            else:
                _make_box(rg.Point3d(d_lo, y_min,      z_min),
                          rg.Point3d(d_hi, y_max,      z_min + fw_size), layer, SCHUCO_FRAME_COLOR)
                _make_box(rg.Point3d(d_lo, y_min,      z_max - fw_size),
                          rg.Point3d(d_hi, y_max,      z_max),           layer, SCHUCO_FRAME_COLOR)
                _make_box(rg.Point3d(d_lo, y_min,      z_min),
                          rg.Point3d(d_hi, y_min + fw_size, z_max),      layer, SCHUCO_FRAME_COLOR)
                _make_box(rg.Point3d(d_lo, y_max - fw_size, z_min),
                          rg.Point3d(d_hi, y_max,      z_max),           layer, SCHUCO_FRAME_COLOR)
                li = y_min + fw_size;  ri = y_max - fw_size; bi = z_min + fw_size;  ti = z_max - fw_size
                _make_box(rg.Point3d(d_lo, li,      bi),
                          rg.Point3d(d_hi, ri,      bi + lf), layer, SCHUCO_SASH_COLOR)
                _make_box(rg.Point3d(d_lo, li,      ti - lf),
                          rg.Point3d(d_hi, ri,      ti),      layer, SCHUCO_SASH_COLOR)
                _make_box(rg.Point3d(d_lo, li,      bi),
                          rg.Point3d(d_hi, li + lf, ti),      layer, SCHUCO_SASH_COLOR)
                _make_box(rg.Point3d(d_lo, ri - lf, bi),
                          rg.Point3d(d_hi, ri,      ti),      layer, SCHUCO_SASH_COLOR)
                _make_box(rg.Point3d(g_lo, li + lf, bi + lf),
                          rg.Point3d(g_hi, ri - lf, ti - lf), layer, SCHUCO_GLASS_COLOR)
            created = True; n_door += 1
        else:
            sf = SCHUCO_WIN_SASH_WIDTH   # 25mm sash frame
            fz_bot = z_min; fz_top = z_max
            if wall_type == 'x':
                _make_box(rg.Point3d(x_min,      d_lo, fz_bot),
                          rg.Point3d(x_max,      d_hi, fz_bot + fw_size), layer, SCHUCO_FRAME_COLOR)
                _make_box(rg.Point3d(x_min,      d_lo, fz_top - fw_size),
                          rg.Point3d(x_max,      d_hi, fz_top),           layer, SCHUCO_FRAME_COLOR)
                _make_box(rg.Point3d(x_min,      d_lo, fz_bot),
                          rg.Point3d(x_min + fw_size, d_hi, fz_top),      layer, SCHUCO_FRAME_COLOR)
                _make_box(rg.Point3d(x_max - fw_size, d_lo, fz_bot),
                          rg.Point3d(x_max,      d_hi, fz_top),           layer, SCHUCO_FRAME_COLOR)
                gl_bot = fz_bot + fw_size; gl_top = fz_top - fw_size
                gl_h   = gl_top - gl_bot; tr_z_bot = gl_bot + gl_h * SCHUCO_WIN_TRANSOM_RATIO - SCHUCO_WIN_TRANSOM_H / 2.0
                tr_z_top = tr_z_bot + SCHUCO_WIN_TRANSOM_H
                _make_box(rg.Point3d(x_min + fw_size, d_lo, tr_z_bot),
                          rg.Point3d(x_max - fw_size, d_hi, tr_z_top), layer, SCHUCO_FRAME_COLOR)
                _make_box(rg.Point3d(x_min + fw_size, g_lo, gl_bot),
                          rg.Point3d(x_max - fw_size, g_hi, tr_z_bot), layer, SCHUCO_GLASS_COLOR)
                u_li = x_min + fw_size;  u_ri = x_max - fw_size; u_bi = tr_z_top;         u_ti = gl_top
                _make_box(rg.Point3d(u_li,      d_lo, u_bi),
                          rg.Point3d(u_ri,      d_hi, u_bi + sf), layer, SCHUCO_SASH_COLOR)
                _make_box(rg.Point3d(u_li,      d_lo, u_ti - sf),
                          rg.Point3d(u_ri,      d_hi, u_ti),     layer, SCHUCO_SASH_COLOR)
                _make_box(rg.Point3d(u_li,      d_lo, u_bi),
                          rg.Point3d(u_li + sf, d_hi, u_ti),     layer, SCHUCO_SASH_COLOR)
                _make_box(rg.Point3d(u_ri - sf, d_lo, u_bi),
                          rg.Point3d(u_ri,      d_hi, u_ti),     layer, SCHUCO_SASH_COLOR)
                _make_box(rg.Point3d(u_li + sf, g_lo, u_bi + sf),
                          rg.Point3d(u_ri - sf, g_hi, u_ti - sf), layer, SCHUCO_GLASS_COLOR)
            else:  # wall_type == 'y'
                _make_box(rg.Point3d(d_lo, y_min,      fz_bot),
                          rg.Point3d(d_hi, y_max,      fz_bot + fw_size), layer, SCHUCO_FRAME_COLOR)
                _make_box(rg.Point3d(d_lo, y_min,      fz_top - fw_size),
                          rg.Point3d(d_hi, y_max,      fz_top),           layer, SCHUCO_FRAME_COLOR)
                _make_box(rg.Point3d(d_lo, y_min,      fz_bot),
                          rg.Point3d(d_hi, y_min + fw_size, fz_top),      layer, SCHUCO_FRAME_COLOR)
                _make_box(rg.Point3d(d_lo, y_max - fw_size, fz_bot),
                          rg.Point3d(d_hi, y_max,      fz_top),           layer, SCHUCO_FRAME_COLOR)
                gl_bot = fz_bot + fw_size; gl_top = fz_top - fw_size
                gl_h   = gl_top - gl_bot; tr_z_bot = gl_bot + gl_h * SCHUCO_WIN_TRANSOM_RATIO - SCHUCO_WIN_TRANSOM_H / 2.0
                tr_z_top = tr_z_bot + SCHUCO_WIN_TRANSOM_H
                _make_box(rg.Point3d(d_lo, y_min + fw_size, tr_z_bot),
                          rg.Point3d(d_hi, y_max - fw_size, tr_z_top), layer, SCHUCO_FRAME_COLOR)
                _make_box(rg.Point3d(g_lo, y_min + fw_size, gl_bot),
                          rg.Point3d(g_hi, y_max - fw_size, tr_z_bot), layer, SCHUCO_GLASS_COLOR)
                u_li = y_min + fw_size;  u_ri = y_max - fw_size; u_bi = tr_z_top;         u_ti = gl_top
                _make_box(rg.Point3d(d_lo, u_li,      u_bi),
                          rg.Point3d(d_hi, u_ri,      u_bi + sf), layer, SCHUCO_SASH_COLOR)
                _make_box(rg.Point3d(d_lo, u_li,      u_ti - sf),
                          rg.Point3d(d_hi, u_ri,      u_ti),     layer, SCHUCO_SASH_COLOR)
                _make_box(rg.Point3d(d_lo, u_li,      u_bi),
                          rg.Point3d(d_hi, u_li + sf, u_ti),     layer, SCHUCO_SASH_COLOR)
                _make_box(rg.Point3d(d_lo, u_ri - sf, u_bi),
                          rg.Point3d(d_hi, u_ri,      u_ti),     layer, SCHUCO_SASH_COLOR)
                _make_box(rg.Point3d(g_lo, u_li + sf, u_bi + sf),
                          rg.Point3d(g_hi, u_ri - sf, u_ti - sf), layer, SCHUCO_GLASS_COLOR)
            created = True; n_win += 1
        if created:
            rs.DeleteObject(pid)
    print("  Schuco replacement complete: {} windows (AWS 75) + {} doors (ADS 75)".format(
        n_win, n_door))
    _enforce_wireframe()
    sc.doc.Views.Redraw()
_cached_metal_mat_idx = [None]   # mutable list so inner function can update
_cached_glass_mat_idx = [None]
def _assign_metal_material(obj_id):
    """Assign anodised aluminium render material. Material created once, reused."""
    try:
        import Rhino.Render as rr
        if _cached_metal_mat_idx[0] is None:
            rm = rr.RenderMaterial.CreateBasicMaterial(
                Rhino.DocObjects.Material(), sc.doc)
            rm.Fields.Set("diffuse", System.Drawing.Color.FromArgb(190, 195, 200))
            rm.Fields.Set("shine",       0.85)
            rm.Fields.Set("reflectivity", 0.45)
            rm.Fields.Set("transparency", 0.0)
            _cached_metal_mat_idx[0] = sc.doc.RenderMaterials.Add(rm)
        mat_idx = _cached_metal_mat_idx[0]
        if mat_idx is not None:
            obj = sc.doc.Objects.Find(obj_id)
            if obj:
                obj.Attributes.MaterialIndex  = mat_idx
                obj.Attributes.MaterialSource = \
                    Rhino.DocObjects.ObjectMaterialSource.MaterialFromObject
                obj.CommitChanges()
    except Exception:
        pass
    _apply_material(obj_id, _mat_aluminium())
def _assign_glass_material(obj_id):
    """Assign clear glass render material. Material created once, reused."""
    try:
        import Rhino.Render as rr
        if _cached_glass_mat_idx[0] is None:
            rm = rr.RenderMaterial.CreateBasicMaterial(
                Rhino.DocObjects.Material(), sc.doc)
            rm.Fields.Set("diffuse", System.Drawing.Color.FromArgb(180, 225, 235))
            rm.Fields.Set("shine",       0.92)
            rm.Fields.Set("reflectivity", 0.15)
            rm.Fields.Set("transparency", 0.70)
            _cached_glass_mat_idx[0] = sc.doc.RenderMaterials.Add(rm)
        mat_idx = _cached_glass_mat_idx[0]
        if mat_idx is not None:
            obj = sc.doc.Objects.Find(obj_id)
            if obj:
                obj.Attributes.MaterialIndex  = mat_idx
                obj.Attributes.MaterialSource = \
                    Rhino.DocObjects.ObjectMaterialSource.MaterialFromObject
                obj.CommitChanges()
    except Exception:
        pass
    _apply_material(obj_id, _mat_glass())
def _replace_parapets_with_balustrades(Building):
    """Replace flat parapet wall surfaces with frameless glass balustrades.
    Each parapet becomes:
      1. Bottom U-channel (Bodenprofil) — 40mm W × 25mm H aluminium; 2. Glass panel (VSG 18mm) — full 1m height
      3. Top handrail cap (Handlauf) — 40mm W × 25mm H aluminium
    Metallic render materials applied to channel + handrail.; Glass render material with 70% transparency applied to glass.
    Uses floor-cell checking for inward direction (same as wall thickness).; Only processes flat vertical surfaces with height ≈ parapet_height (1m).
    """
    gs = Building["grid"]["spacing"]
    bd = Building["structure"]["plinth_beams"]["depth"]
    tol_flat = 0.02; tol_min  = 0.05
    parapet_h = Building["wall_panels"]["parapet_height"]
    gt = BALUSTRADE_GLASS_THICKNESS   # 18mm
    ch = BALUSTRADE_CHANNEL_HEIGHT    # 25mm
    cw = BALUSTRADE_CHANNEL_WIDTH     # 40mm
    hh = BALUSTRADE_HANDRAIL_HEIGHT   # 25mm
    hw = BALUSTRADE_HANDRAIL_WIDTH    # 40mm
    for ln, clr in [("Balustrade_Glass",    BALUSTRADE_GLASS_COLOR),
                    ("Balustrade_Handrail",  BALUSTRADE_METAL_COLOR),
                    ("Balustrade_Channel",   BALUSTRADE_METAL_COLOR)]:
        if not rs.IsLayer(ln):
            rs.AddLayer(ln, clr)
    floor_z_list = []
    for fi_idx in range(len(Building["structure"]["columns"]["top_points_per_floor"])):
        ftp = Building["structure"]["columns"]["top_points_per_floor"][fi_idx]
        if ftp:
            floor_z_list.append((fi_idx, ftp[0][2] + bd))
    def _get_fi(z_val):
        best_fi, best_d = 0, float('inf')
        for fi_idx, pz in floor_z_list:
            d = abs(z_val - pz)
            if d < best_d:
                best_d = d; best_fi = fi_idx
        return best_fi
    def _get_fkeys(fi_idx):
        if fi_idx < len(Building["panels"]["panel_coords_per_floor"]):
            return set((round(k[0], 4), round(k[1], 4))
                       for k in Building["panels"]["panel_coords_per_floor"][fi_idx])
        return set()
    def _has_floor_at(px, py, fkeys):
        for (kx, ky) in fkeys:
            if kx - 0.01 <= px <= kx + gs + 0.01 and \
               ky - 0.01 <= py <= ky + gs + 0.01:
                return True
        return False
    def _make_box(p_min, p_max, layer, color):
        bx = rg.BoundingBox(p_min, p_max)
        brep = rg.Brep.CreateFromBox(bx)
        if brep and brep.IsValid:
            oid = sc.doc.Objects.AddBrep(brep)
            if oid:
                rs.ObjectLayer(oid, layer)
                rs.ObjectColor(oid, color)
                if "Glass" in layer:
                    _apply_material(oid, _mat_glass())
                else:
                    _apply_material(oid, _mat_aluminium())
                return oid
        return None
    processed = 0
    for fi in range(-1, 20):
        layer_name = "Wall_Panels_{}".format(fi)
        if not rs.IsLayer(layer_name):
            continue
        objs = rs.ObjectsByLayer(layer_name)
        if not objs:
            continue
        for pid in list(objs):
            if not rs.IsObject(pid):
                continue
            bb = rs.BoundingBox(pid)
            if not bb or len(bb) < 8:
                continue
            xs = [p.X for p in bb]
            ys = [p.Y for p in bb]
            zs = [p.Z for p in bb]
            x_min, x_max = min(xs), max(xs)
            y_min, y_max = min(ys), max(ys)
            z_min, z_max = min(zs), max(zs)
            dx = x_max - x_min; dy = y_max - y_min
            dz = z_max - z_min
            if dz < 0.5 or dz > parapet_h + 0.15:
                continue
            if dx > tol_flat and dy > tol_flat:
                continue   # already thick — not a flat parapet
            w_fi = _get_fi(z_min)
            fkeys = _get_fkeys(w_fi)
            wall_type   = None; outer_pos   = 0.0
            inward_sign = 0
            if dx > tol_min and dy <= tol_flat:
                wall_type = 'x'
                outer_pos = (y_min + y_max) / 2.0
                mid_x = (x_min + x_max) / 2.0
                has_plus  = _has_floor_at(mid_x, outer_pos + gs * 0.5, fkeys)
                has_minus = _has_floor_at(mid_x, outer_pos - gs * 0.5, fkeys)
                if has_plus and not has_minus:
                    inward_sign = 1
                elif has_minus and not has_plus:
                    inward_sign = -1
                else:
                    inward_sign = 1
            elif dy > tol_min and dx <= tol_flat:
                wall_type = 'y'
                outer_pos = (x_min + x_max) / 2.0
                mid_y = (y_min + y_max) / 2.0
                has_plus  = _has_floor_at(outer_pos + gs * 0.5, mid_y, fkeys)
                has_minus = _has_floor_at(outer_pos - gs * 0.5, mid_y, fkeys)
                if has_plus and not has_minus:
                    inward_sign = 1
                elif has_minus and not has_plus:
                    inward_sign = -1
                else:
                    inward_sign = 1
            else:
                continue
            g_lo = outer_pos - gt / 2.0; g_hi = outer_pos + gt / 2.0
            c_lo = outer_pos - cw / 2.0; c_hi = outer_pos + cw / 2.0
            z_channel_bot = z_min; z_channel_top = z_min + ch
            z_glass_bot   = z_channel_top; z_glass_top   = z_max - hh
            z_handrail_bot = z_glass_top; z_handrail_top = z_max
            if wall_type == 'x':
                ext = cw / 2.0   # 20mm — aligns with Y-running channel edge
                ch_id = _make_box(
                    rg.Point3d(x_min - ext, c_lo, z_channel_bot),
                    rg.Point3d(x_max + ext, c_hi, z_channel_top),
                    "Balustrade_Channel", BALUSTRADE_METAL_COLOR)
                if ch_id:
                    _assign_metal_material(ch_id)
                gl_id = _make_box(
                    rg.Point3d(x_min, g_lo, z_glass_bot),
                    rg.Point3d(x_max, g_hi, z_glass_top),
                    "Balustrade_Glass", BALUSTRADE_GLASS_COLOR)
                if gl_id:
                    _assign_glass_material(gl_id)
                hr_id = _make_box(
                    rg.Point3d(x_min - ext, c_lo, z_handrail_bot),
                    rg.Point3d(x_max + ext, c_hi, z_handrail_top),
                    "Balustrade_Handrail", BALUSTRADE_METAL_COLOR)
                if hr_id:
                    _assign_metal_material(hr_id)
            else:  # wall_type == 'y'
                ch_id = _make_box(
                    rg.Point3d(c_lo, y_min, z_channel_bot),
                    rg.Point3d(c_hi, y_max, z_channel_top),
                    "Balustrade_Channel", BALUSTRADE_METAL_COLOR)
                if ch_id:
                    _assign_metal_material(ch_id)
                gl_id = _make_box(
                    rg.Point3d(g_lo, y_min, z_glass_bot),
                    rg.Point3d(g_hi, y_max, z_glass_top),
                    "Balustrade_Glass", BALUSTRADE_GLASS_COLOR)
                if gl_id:
                    _assign_glass_material(gl_id)
                hr_id = _make_box(
                    rg.Point3d(c_lo, y_min, z_handrail_bot),
                    rg.Point3d(c_hi, y_max, z_handrail_top),
                    "Balustrade_Handrail", BALUSTRADE_METAL_COLOR)
                if hr_id:
                    _assign_metal_material(hr_id)
            rs.DeleteObject(pid)
            processed += 1
    print("  Balustrades: {} parapets replaced (glass {}mm + channel + handrail).".format(
        processed, int(gt * 1000)))
    _enforce_wireframe()
    sc.doc.Views.Redraw()
def _add_facade_louvers(Building):
    """Facade louver screen.
    Generates facade louvers on the top-floor perimeter faces, but trims them
    locally in two situations:
      1) where projected / perforated wall extrusion panels occupy the facade,
      2) where the same facade line falls inside the internal building space of
         lower / other floors in a cascading massing.
    This keeps louvers only on truly exterior visible portions of the envelope.
    """
    gs  = Building["grid"]["spacing"]
    bd  = Building["structure"]["plinth_beams"]["depth"]
    tol = 0.02
    lw   = LOUVER_WIDTH
    ld   = LOUVER_DEPTH
    ls   = LOUVER_SPACING
    lg   = LOUVER_GAP
    bh   = LOUVER_BAR_HEIGHT
    bd_b = LOUVER_BAR_DEPTH
    nb   = LOUVER_N_BARS
    col_w  = Building["structure"]["columns"].get("width", 0.30)
    lg_eff = max(lg, col_w / 2.0 + 0.005)
    LAYER_FIN = "Facade_Louvers"
    LAYER_BAR = "Facade_Louvers_Bar"
    for lname, lcol in [(LAYER_FIN, LOUVER_COLOR), (LAYER_BAR, LOUVER_BAR_COLOR)]:
        if not rs.IsLayer(lname):
            rs.AddLayer(lname, lcol)
    nf = len(Building["structure"]["columns"]["top_points_per_floor"])
    total_h = sum(Building["floors"]["floor_heights"]) + 1.05
    def _add_box(pt_min, pt_max, layer, color):
        if pt_max.X - pt_min.X < 0.001 or pt_max.Y - pt_min.Y < 0.001 or pt_max.Z - pt_min.Z < 0.001:
            return False
        box = rg.BoundingBox(pt_min, pt_max)
        brep = rg.Brep.CreateFromBox(box)
        if brep and brep.IsValid:
            oid = sc.doc.Objects.AddBrep(brep)
            if oid:
                rs.ObjectLayer(oid, layer)
                rs.ObjectColor(oid, color)
                if layer == LAYER_FIN:
                    _apply_material(oid, _mat_louver_fin())
                elif layer == LAYER_BAR:
                    _apply_material(oid, _mat_louver_bar())
                return True
        return False
    def _merge_intervals(intervals, tol_merge=0.001):
        if not intervals:
            return []
        ints = sorted(intervals, key=lambda x: (x[0], x[1]))
        merged = [[ints[0][0], ints[0][1]]]
        for a, b in ints[1:]:
            last = merged[-1]
            if a <= last[1] + tol_merge:
                if b > last[1]:
                    last[1] = b
            else:
                merged.append([a, b])
        return [(a, b) for a, b in merged if b - a > 0.001]
    def _subtract_intervals(base_a, base_b, blocked):
        if base_b - base_a <= 0.001:
            return []
        blocked = _merge_intervals([(max(base_a, a), min(base_b, b)) for a, b in blocked if b > base_a and a < base_b])
        if not blocked:
            return [(base_a, base_b)]
        free = []
        cur = base_a
        for a, b in blocked:
            if a > cur:
                free.append((cur, a))
            cur = max(cur, b)
        if cur < base_b:
            free.append((cur, base_b))
        return [(a, b) for a, b in free if b - a > 0.01]
    FIN_SPAN_PATTERN = [
        (0, 4), (0, 2), (0, 3), (1, 2), (0, 4), (2, 2), (0, 1), (0, 3), (1, 3), (0, 2),
        (0, 4), (3, 1), (0, 3), (2, 1), (1, 2), (0, 4), (0, 1), (0, 2), (2, 2), (0, 3),
    ]
    pat_len = len(FIN_SPAN_PATTERN)
    wall_lines = {}
    top_fi_tf  = max(0, nf - 2)
    top_ftp_tf = Building["structure"]["columns"]["top_points_per_floor"][top_fi_tf] if top_fi_tf < len(Building["structure"]["columns"]["top_points_per_floor"]) else []
    if top_ftp_tf:
        tf_z_bot = 0.0
        tf_z_top = total_h + 1.0
        xs = [pt[0] for pt in top_ftp_tf]
        ys = [pt[1] for pt in top_ftp_tf]
        x_min = round(min(xs), 4); x_max = round(max(xs), 4)
        y_min = round(min(ys), 4); y_max = round(max(ys), 4)
        if tf_z_top - tf_z_bot > 0.3 and x_max - x_min > 0.05 and y_max - y_min > 0.05:
            wall_lines[('x', y_min, x_min, x_max, -1)] = (tf_z_bot, tf_z_top)
            wall_lines[('x', y_max, x_min, x_max,  1)] = (tf_z_bot, tf_z_top)
            wall_lines[('y', x_min, y_min, y_max, -1)] = (tf_z_bot, tf_z_top)
            wall_lines[('y', x_max, y_min, y_max,  1)] = (tf_z_bot, tf_z_top)
            print("  [Louvers] Top floor perimeter: 4 faces added.")
        else:
            print("  [Louvers] WARNING: skipped — invalid bbox.")
    else:
        print("  [Louvers] WARNING: top floor column data missing — skipped.")
    ext_blocks = {}
    for (ext_axis, ext_wpos, ext_smin, ext_smax, ez0, ez1) in Building["elevation"].get("wall_extrusion_footprints", []):
        fkey = (ext_axis, round(ext_wpos, 4))
        ext_blocks.setdefault(fkey, []).append((ext_smin, ext_smax, ez0, ez1))
    def _blocked_spans_at_z(blocked_rects, z_val, z_margin=0.02, s_margin=0.03):
        spans = []
        for bs, be, bz0, bz1 in blocked_rects:
            if (bz0 - z_margin) <= z_val <= (bz1 + z_margin):
                spans.append((bs - s_margin, be + s_margin))
        return _merge_intervals(spans)
    def _blocked_z_for_pos(blocked_rects, pos, pos_margin=None, z_margin=0.02):
        if pos_margin is None:
            pos_margin = max(lw * 0.55, 0.02)
        ints = []
        for bs, be, bz0, bz1 in blocked_rects:
            if (bs - pos_margin) <= pos <= (be + pos_margin):
                ints.append((bz0 - z_margin, bz1 + z_margin))
        return _merge_intervals(ints)
    def _internal_space_blocks(axis, wall_pos):
        """Return (span_min, span_max, z0, z1) blocks where this facade line sits
        inside the building space for any floor footprint, so louvers there must
        be removed. Works by checking if the line is an *internal* grid boundary
        for that floor: occupied cells exist on both sides of the line.
        """
        blocks = []
        coords_per_floor = Building.get("grid", {}).get("selected_coords_per_floor", [])
        floor_heights = Building.get("floors", {}).get("floor_heights", [])
        wall_pos_r = round(wall_pos, 4)
        for fi, coords in enumerate(coords_per_floor):
            if not coords:
                continue
            cells = _get_complete_cells_for_floor(coords, gs)
            if not cells:
                continue
            cell_set = set((round(cx, 4), round(cy, 4)) for cx, cy in cells)
            spans = []
            if axis == 'x':
                # horizontal line at y = wall_pos; internal if cells exist both below and above this line
                candidate_xs = sorted(set(round(cx, 4) for cx, cy in cell_set if round(cy + gs, 4) == wall_pos_r or round(cy, 4) == wall_pos_r))
                for cx in candidate_xs:
                    below = (round(cx, 4), round(wall_pos_r - gs, 4)) in cell_set
                    above = (round(cx, 4), round(wall_pos_r, 4)) in cell_set
                    if below and above:
                        spans.append((cx, round(cx + gs, 4)))
            else:
                # vertical line at x = wall_pos; internal if cells exist both left and right of this line
                candidate_ys = sorted(set(round(cy, 4) for cx, cy in cell_set if round(cx + gs, 4) == wall_pos_r or round(cx, 4) == wall_pos_r))
                for cy in candidate_ys:
                    left  = (round(wall_pos_r - gs, 4), round(cy, 4)) in cell_set
                    right = (round(wall_pos_r, 4), round(cy, 4)) in cell_set
                    if left and right:
                        spans.append((cy, round(cy + gs, 4)))
            spans = _merge_intervals(spans, tol_merge=0.02)
            if spans:
                z0 = coords[0][2] if len(coords[0]) > 2 else 0.0
                zh = floor_heights[fi] if fi < len(floor_heights) else 3.0
                z1 = z0 + zh
                for s0, s1 in spans:
                    blocks.append((s0, s1, z0 - 0.02, z1 + 0.02))
        return blocks
    n_fins_total = 0
    n_bars_total = 0
    for key, (full_z_bot, full_z_top) in wall_lines.items():
        axis, wall_pos, span_min, span_max, out_dir = key
        full_z_h  = full_z_top - full_z_bot
        if full_z_h < 0.3 or span_max - span_min < 0.05:
            continue
        if axis == 'x':
            back_y  = wall_pos + out_dir * lg_eff
            front_y = back_y   + out_dir * ld
            fin_y0  = min(back_y, front_y); fin_y1 = max(back_y, front_y)
            bar_y0  = min(back_y, back_y + out_dir * bd_b); bar_y1 = max(back_y, back_y + out_dir * bd_b)
        else:
            back_x  = wall_pos + out_dir * lg_eff
            front_x = back_x   + out_dir * ld
            fin_x0  = min(back_x, front_x); fin_x1 = max(back_x, front_x)
            bar_x0  = min(back_x, back_x + out_dir * bd_b); bar_x1 = max(back_x, back_x + out_dir * bd_b)
        bar_interval = full_z_h / float(nb)
        bar_zs = [full_z_bot + bi * bar_interval for bi in range(nb + 1)]
        blocked_rects = list(ext_blocks.get((axis, round(wall_pos, 4)), []))
        blocked_rects.extend(_internal_space_blocks(axis, wall_pos))
        # horizontal bars: trim where their specific Z crosses either projected panels or interior space blocks
        for bz in bar_zs:
            blocked_spans = _blocked_spans_at_z(blocked_rects, bz)
            free_segs = _subtract_intervals(span_min, span_max, blocked_spans)
            for seg_min, seg_max in free_segs:
                if axis == 'x':
                    ok = _add_box(rg.Point3d(seg_min, bar_y0, bz - bh / 2.0), rg.Point3d(seg_max, bar_y1, bz + bh / 2.0), LAYER_BAR, LOUVER_BAR_COLOR)
                else:
                    ok = _add_box(rg.Point3d(bar_x0, seg_min, bz - bh / 2.0), rg.Point3d(bar_x1, seg_max, bz + bh / 2.0), LAYER_BAR, LOUVER_BAR_COLOR)
                if ok:
                    n_bars_total += 1
        # vertical fins: keep same horizontal positions, but trim vertically where projections or interior space occur
        n_positions = max(1, int((span_max - span_min) / ls))
        for ci in range(n_positions):
            t   = (ci + 0.5) / float(n_positions)
            pos = span_min + t * (span_max - span_min)
            start_bi, n_spans = FIN_SPAN_PATTERN[ci % pat_len]
            end_bi = min(nb, start_bi + n_spans)
            if end_bi <= start_bi:
                continue
            z_fin_bot = max(bar_zs[start_bi] + bh / 2.0, full_z_bot)
            z_fin_top = min(bar_zs[end_bi]   - bh / 2.0, full_z_top)
            if z_fin_top - z_fin_bot < 0.05:
                continue
            blocked_z = _blocked_z_for_pos(blocked_rects, pos)
            free_zs = _subtract_intervals(z_fin_bot, z_fin_top, blocked_z)
            for seg_z0, seg_z1 in free_zs:
                if axis == 'x':
                    ok = _add_box(rg.Point3d(pos - lw / 2.0, fin_y0, seg_z0), rg.Point3d(pos + lw / 2.0, fin_y1, seg_z1), LAYER_FIN, LOUVER_COLOR)
                else:
                    ok = _add_box(rg.Point3d(fin_x0, pos - lw / 2.0, seg_z0), rg.Point3d(fin_x1, pos + lw / 2.0, seg_z1), LAYER_FIN, LOUVER_COLOR)
                if ok:
                    n_fins_total += 1
    print("  Facade louvers: {} fins + {} bar segments | {}x{}mm fins, {}mm c/c.".format(n_fins_total, n_bars_total, int(lw * 1000), int(ld * 1000), int(ls * 1000)))
    print("  Bar system: {} equally-spaced levels per face, trimmed at projected wall panel zones + internal-space overlaps.".format(nb + 1))
    print("  Louver stand-off: {:.1f}mm (column outer face + 5mm clearance).".format(lg_eff * 1000))
    _enforce_wireframe()
    sc.doc.Views.Redraw()



def _add_compound_wall(Building):
    """Create a 2.0m-high compound wall along the full site boundary.
    North side gets two centered openings (6m and 2m) with 1m wall between.
    Louver gates are added inside those openings using the same timber-louver
    proportions/colors as the building facade. Remaining wall segments are
    perforated with square openings at ~40% lower density than elevation panels.
    """
    pl = float(Building["plot"].get("length", 0.0) or 0.0)
    pw = float(Building["plot"].get("width", 0.0) or 0.0)
    north = Building["plot"].get("north_side", "Top")
    if pl <= 0.1 or pw <= 0.1:
        print("  [Compound wall] Skipped — plot dimensions missing.")
        return
    WALL_H = 2.0
    WALL_T = 0.20
    OPEN_A = 6.0
    OPEN_B = 2.0
    PIER_B = 1.0
    tol = 0.001
    LAYER_WALL = "Compound_Wall"
    LAYER_GATE_FIN = "Compound_Gate_Louvers"
    LAYER_GATE_BAR = "Compound_Gate_Louvers_Bar"
    for lname, lcol in [(LAYER_WALL, (205, 188, 160)), (LAYER_GATE_FIN, LOUVER_COLOR), (LAYER_GATE_BAR, LOUVER_BAR_COLOR)]:
        if not rs.IsLayer(lname):
            rs.AddLayer(lname, lcol)
    def _add_brep(brep, layer, color):
        if brep and brep.IsValid:
            oid = sc.doc.Objects.AddBrep(brep)
            if oid:
                rs.ObjectLayer(oid, layer)
                rs.ObjectColor(oid, color)
                if layer == LAYER_WALL:
                    _apply_material(oid, _mat_compound_wall())
                elif layer == LAYER_GATE_FIN:
                    _apply_material(oid, _mat_louver_fin())
                elif layer == LAYER_GATE_BAR:
                    _apply_material(oid, _mat_louver_bar())
                return oid
        return None
    def _make_box(x0, x1, y0, y1, z0, z1):
        bb = rg.BoundingBox(rg.Point3d(min(x0,x1), min(y0,y1), min(z0,z1)), rg.Point3d(max(x0,x1), max(y0,y1), max(z0,z1)))
        return rg.Brep.CreateFromBox(bb)
    def _merge_intervals(ints):
        if not ints:
            return []
        ints = sorted((min(a,b), max(a,b)) for a,b in ints)
        out = [[ints[0][0], ints[0][1]]]
        for a,b in ints[1:]:
            if a <= out[-1][1] + 1e-6:
                out[-1][1] = max(out[-1][1], b)
            else:
                out.append([a,b])
        return [(a,b) for a,b in out]
    def _subtract(base0, base1, blocked):
        blocked = _merge_intervals([(max(base0,a), min(base1,b)) for a,b in blocked if b > base0+tol and a < base1-tol])
        if not blocked:
            return [(base0, base1)]
        cur = base0; out=[]
        for a,b in blocked:
            if a > cur + tol:
                out.append((cur,a))
            cur = max(cur,b)
        if cur < base1 - tol:
            out.append((cur, base1))
        return [(a,b) for a,b in out if b-a > 0.05]
    def _perforate_segment(brep, axis, seg_len, z0, z1):
        """Square perforations through a wall segment using sparse grid (~40% fewer openings)."""
        h = z1 - z0
        if brep is None or seg_len < 0.9 or h < 0.9:
            return brep
        target = 0.58  # ≈ 40% less dense than elevation CELL_TARGET=0.35
        n_cols = max(1, int(seg_len / target))
        n_rows = max(2, int(h / target))
        cell_w = seg_len / float(n_cols)
        cell_h = h / float(n_rows)
        cutters = []
        full_thick = WALL_T + 0.10
        for row in range(n_rows):
            for col in range(n_cols):
                u0 = col / float(n_cols)
                u1 = (col + 1) / float(n_cols)
                v0 = row / float(n_rows)
                v1 = (row + 1) / float(n_rows)
                gap_frac = 0.60 * _hole_gap_for_cell(col, row, n_cols, n_rows)  # 40% less open than elevation
                gap_frac = max(0.15, min(0.70, gap_frac))
                hw = cell_w * gap_frac * 0.5
                hh = cell_h * gap_frac * 0.5
                c_s = (u0 + u1) * 0.5 * seg_len
                c_z = z0 + (v0 + v1) * 0.5 * h
                if axis == 'x':
                    x0 = c_s - hw; x1 = c_s + hw
                    y0 = -0.05;   y1 = -0.05 + full_thick
                    zc0 = c_z - hh; zc1 = c_z + hh
                    cutters.append(_make_box(x0, x1, y0, y1, zc0, zc1))
                else:
                    x0 = -0.05; x1 = -0.05 + full_thick
                    y0 = c_s - hw; y1 = c_s + hw
                    zc0 = c_z - hh; zc1 = c_z + hh
                    cutters.append(_make_box(x0, x1, y0, y1, zc0, zc1))
        diff = rg.Brep.CreateBooleanDifference([brep], cutters, 0.001)
        if diff:
            good = [b for b in diff if b and b.IsValid]
            if good:
                # choose largest remaining piece by volume
                def _vol(b):
                    amp = rg.AreaMassProperties.Compute(b)
                    if amp: return amp.Area
                    return 0.0
                return sorted(good, key=_vol, reverse=True)[0]
        return brep
    def _add_wall_segment(x0, x1, y0, y1):
        brep = _make_box(x0, x1, y0, y1, 0.0, WALL_H)
        seg_len = abs((x1-x0) if abs(x1-x0) >= abs(y1-y0) else (y1-y0))
        axis = 'x' if abs(x1-x0) >= abs(y1-y0) else 'y'
        # move to local coords for perforation boolean if wanted
        if axis == 'x':
            base = rg.Transform.Translation(-min(x0,x1), -min(y0,y1), 0)
            inv = rg.Transform.Translation(min(x0,x1), min(y0,y1), 0)
            local = brep.DuplicateBrep(); local.Transform(base)
            local = _perforate_segment(local, 'x', seg_len, 0.0, WALL_H)
            local.Transform(inv)
            brep = local
        else:
            base = rg.Transform.Translation(-min(x0,x1), -min(y0,y1), 0)
            inv = rg.Transform.Translation(min(x0,x1), min(y0,y1), 0)
            local = brep.DuplicateBrep(); local.Transform(base)
            local = _perforate_segment(local, 'y', seg_len, 0.0, WALL_H)
            local.Transform(inv)
            brep = local
        return _add_brep(brep, LAYER_WALL, (205, 188, 160))
    def _add_gate_louvers(axis, fixed_pos, seg0, seg1, out_sign):
        lw = LOUVER_WIDTH; ls = LOUVER_SPACING; ld = min(LOUVER_DEPTH, WALL_T * 0.6)
        bh = LOUVER_BAR_HEIGHT; bd_b = min(LOUVER_BAR_DEPTH, WALL_T * 0.5)
        nb = LOUVER_N_BARS
        z0=0.0; z1=WALL_H
        if axis == 'x':
            back_y = fixed_pos + out_sign * (WALL_T*0.5 - ld*0.5)
            fin_y0 = min(back_y, back_y + out_sign*ld); fin_y1 = max(back_y, back_y + out_sign*ld)
            bar_y0 = min(back_y, back_y + out_sign*bd_b); bar_y1 = max(back_y, back_y + out_sign*bd_b)
        else:
            back_x = fixed_pos + out_sign * (WALL_T*0.5 - ld*0.5)
            fin_x0 = min(back_x, back_x + out_sign*ld); fin_x1 = max(back_x, back_x + out_sign*ld)
            bar_x0 = min(back_x, back_x + out_sign*bd_b); bar_x1 = max(back_x, back_x + out_sign*bd_b)
        def _abox(pmin,pmax,layer,color):
            bb = rg.BoundingBox(pmin,pmax)
            b = rg.Brep.CreateFromBox(bb)
            return _add_brep(b, layer, color)
        # vertical fins
        n_pos = max(1, int((seg1 - seg0) / ls))
        for ci in range(n_pos):
            t = (ci + 0.5)/float(n_pos)
            pos = seg0 + t*(seg1-seg0)
            if axis == 'x':
                _abox(rg.Point3d(pos-lw/2.0, fin_y0, z0), rg.Point3d(pos+lw/2.0, fin_y1, z1), LAYER_GATE_FIN, LOUVER_COLOR)
            else:
                _abox(rg.Point3d(fin_x0, pos-lw/2.0, z0), rg.Point3d(fin_x1, pos+lw/2.0, z1), LAYER_GATE_FIN, LOUVER_COLOR)
        # horizontal bars
        interval = (z1-z0)/float(nb)
        for bi in range(nb+1):
            bz = z0 + bi*interval
            if axis == 'x':
                _abox(rg.Point3d(seg0, bar_y0, bz-bh/2.0), rg.Point3d(seg1, bar_y1, bz+bh/2.0), LAYER_GATE_BAR, LOUVER_BAR_COLOR)
            else:
                _abox(rg.Point3d(bar_x0, seg0, bz-bh/2.0), rg.Point3d(bar_x1, seg1, bz+bh/2.0), LAYER_GATE_BAR, LOUVER_BAR_COLOR)
    half_l = pl * 0.5
    half_w = pw * 0.5
    assembly = OPEN_A + PIER_B + OPEN_B
    side_len = pl if north in ('Top','Bottom') else pw
    if assembly >= side_len - 0.5:
        print("  [Compound wall] WARNING: north-side openings too wide for plot — skipping gates/openings.")
        assembly = 0.0

    def _merge_world_intervals(ints):
        return _merge_intervals([(float(a), float(b)) for a, b in ints])

    def _ground_floor_cells():
        coords_pf = Building.get("grid", {}).get("selected_coords_per_floor", []) or []
        gs_loc = float(Building.get("grid", {}).get("spacing", 0.0) or 0.0)
        if not coords_pf or gs_loc <= 0.01:
            return [], gs_loc
        coords0 = coords_pf[0] if coords_pf else []
        return _get_complete_cells_for_floor(coords0, gs_loc), gs_loc

    def _gate_clearance_depth(center):
        """Choose the north-side gate position by the REAL inward open depth behind
        the full gate assembly, not just by 1D side width. This makes the gate move
        toward the side with the maximum percentage of open space inside the plot."""
        cells, gs_loc = _ground_floor_cells()
        if assembly <= 0.0:
            return 0.0
        span0 = center - assembly * 0.5
        span1 = center + assembly * 0.5
        if not cells or gs_loc <= 0.01:
            return max(pl, pw)
        full_depth = pw if north in ('Top', 'Bottom') else pl
        hits = []
        if north == 'Bottom':
            boundary = -half_w
            for cx, cy in cells:
                x0, x1 = cx, cx + gs_loc
                if x1 <= span0 or x0 >= span1:
                    continue
                hits.append(cy - boundary)
        elif north == 'Top':
            boundary = half_w
            for cx, cy in cells:
                x0, x1 = cx, cx + gs_loc
                if x1 <= span0 or x0 >= span1:
                    continue
                hits.append(boundary - (cy + gs_loc))
        elif north == 'Left':
            boundary = -half_l
            for cx, cy in cells:
                y0, y1 = cy, cy + gs_loc
                if y1 <= span0 or y0 >= span1:
                    continue
                hits.append(cx - boundary)
        else:
            boundary = half_l
            for cx, cy in cells:
                y0, y1 = cy, cy + gs_loc
                if y1 <= span0 or y0 >= span1:
                    continue
                hits.append(boundary - (cx + gs_loc))
        if not hits:
            return full_depth
        return max(0.0, min(hits))

    def _choose_gate_center():
        base0, base1 = -side_len * 0.5, side_len * 0.5
        if assembly <= 0.0:
            return 0.0
        lo = base0 + assembly * 0.5
        hi = base1 - assembly * 0.5
        if hi <= lo:
            return 0.0
        step = 0.25
        n = int(max(1, round((hi - lo) / step)))
        best_c = 0.5 * (lo + hi)
        best_key = None
        for i in range(n + 1):
            c = lo + (hi - lo) * (float(i) / float(n))
            depth = _gate_clearance_depth(c)
            corner_clear = min(c - lo, hi - c)
            key = (depth, corner_clear)
            if best_key is None or key > best_key:
                best_key = key
                best_c = c
        return best_c

    blocked = []
    gate_center = 0.0
    if assembly > 0.0:
        gate_center = _choose_gate_center()
        a0 = gate_center - assembly * 0.5
        a1 = a0 + OPEN_A
        b0 = a1 + PIER_B
        b1 = b0 + OPEN_B
        blocked = [(a0, a1), (b0, b1)]
    # Store gate centre in Building so _add_main_entrance_door can use it
    Building.setdefault("compound", {})["gate_centre"] = gate_center
    # bottom, top, left, right wall segments
    if north in ('Top','Bottom'):
        # horizontal opening side
        north_y0, north_y1 = (half_w - WALL_T, half_w) if north == 'Top' else (-half_w, -half_w + WALL_T)
        south_y0, south_y1 = (-half_w, -half_w + WALL_T) if north == 'Top' else (half_w - WALL_T, half_w)
        # south full wall
        _add_wall_segment(-half_l, half_l, south_y0, south_y1)
        # left & right full walls
        _add_wall_segment(-half_l, -half_l + WALL_T, -half_w, half_w)
        _add_wall_segment(half_l - WALL_T, half_l, -half_w, half_w)
        # north broken wall segments + middle pier
        for s0, s1 in _subtract(-half_l, half_l, blocked):
            _add_wall_segment(s0, s1, north_y0, north_y1)
        if blocked:
            _add_wall_segment(a1, b0, north_y0, north_y1)
            out_sign = -1 if north == 'Top' else 1
            _add_gate_louvers('x', north_y0 if north == 'Top' else north_y1, a0, a1, out_sign)
            _add_gate_louvers('x', north_y0 if north == 'Top' else north_y1, b0, b1, out_sign)
    else:
        north_x0, north_x1 = (half_l - WALL_T, half_l) if north == 'Right' else (-half_l, -half_l + WALL_T)
        south_x0, south_x1 = (-half_l, -half_l + WALL_T) if north == 'Right' else (half_l - WALL_T, half_l)
        _add_wall_segment(south_x0, south_x1, -half_w, half_w)
        _add_wall_segment(-half_l, half_l, -half_w, -half_w + WALL_T)
        _add_wall_segment(-half_l, half_l, half_w - WALL_T, half_w)
        for s0, s1 in _subtract(-half_w, half_w, blocked):
            _add_wall_segment(north_x0, north_x1, s0, s1)
        if blocked:
            _add_wall_segment(north_x0, north_x1, a1, b0)
            out_sign = -1 if north == 'Right' else 1
            _add_gate_louvers('y', north_x0 if north == 'Right' else north_x1, a0, a1, out_sign)
            _add_gate_louvers('y', north_x0 if north == 'Right' else north_x1, b0, b1, out_sign)
    print("  Compound wall: 2.0m high with north openings 6m + 1m pier + 2m, placed on north side for easiest entry.")
    print("  Gate infill uses same timber louver sizes as facade screen.")
    print("  Wall perforation density reduced by ~40% compared to elevation panels.")
    # Store compound-wall / opening metadata for later site-filling + access generation
    try:
        Building.setdefault("compound", {})["north_side"] = north
        Building["compound"]["wall_height"] = WALL_H
        Building["compound"]["wall_thickness"] = WALL_T
        Building["compound"]["openings"] = []
        if blocked:
            if north in ("Top", "Bottom"):
                Building["compound"]["openings"].append({"kind": "vehicular", "axis": "x", "fixed": north_y0 if north == "Top" else north_y1, "start": a0, "end": a1, "outside_sign": (-1 if north == "Top" else 1)})
                Building["compound"]["openings"].append({"kind": "pedestrian", "axis": "x", "fixed": north_y0 if north == "Top" else north_y1, "start": b0, "end": b1, "outside_sign": (-1 if north == "Top" else 1)})
            else:
                Building["compound"]["openings"].append({"kind": "vehicular", "axis": "y", "fixed": north_x0 if north == "Right" else north_x1, "start": a0, "end": a1, "outside_sign": (-1 if north == "Right" else 1)})
                Building["compound"]["openings"].append({"kind": "pedestrian", "axis": "y", "fixed": north_x0 if north == "Right" else north_x1, "start": b0, "end": b1, "outside_sign": (-1 if north == "Right" else 1)})
    except Exception as _cw_store_err:
        print("  [Compound wall] metadata store warning:", _cw_store_err)
    _enforce_wireframe()
    sc.doc.Views.Redraw()

def _add_site_filling_and_entry_access(Building):
    """After compound wall creation, add site-filling slab over the full plot
    and create pedestrian steps + vehicular ramp at the north-side openings.
    Site filling rises UPWARD from road level 0.0 to +0.30m across the plot.
    The access steps/ramp are created OUTSIDE the plot, connecting road level
    to the raised site entry level.
    """
    pl = float(Building.get("plot", {}).get("length", 0.0) or 0.0)
    pw = float(Building.get("plot", {}).get("width", 0.0) or 0.0)
    comp = Building.get("compound", {}) or {}
    openings = comp.get("openings", []) or []
    if pl <= 0.1 or pw <= 0.1:
        return
    FILL_H = float(comp.get("site_fill_height", 0.30) or 0.30)
    half_l = pl * 0.5
    half_w = pw * 0.5
    LAYER_FILL = "Site_Filling"
    LAYER_FILL_TOP = "Site_Filling_Grass"
    LAYER_STEP = "Compound_Entry_Steps"
    LAYER_RAMP = "Compound_Entry_Ramp"
    for lname, col in [(LAYER_FILL, (164,130,92)), (LAYER_FILL_TOP, (82, 125, 56)), (LAYER_STEP, (190,190,190)), (LAYER_RAMP, (150,150,150))]:
        if not rs.IsLayer(lname):
            rs.AddLayer(lname, col)

    def _add_brep(brep, layer, color):
        if brep and brep.IsValid:
            oid = sc.doc.Objects.AddBrep(brep)
            if oid:
                rs.ObjectLayer(oid, layer)
                rs.ObjectColor(oid, color)
                if layer == LAYER_FILL:
                    _apply_material(oid, _mat_soil())
                elif layer == LAYER_FILL_TOP:
                    _apply_material(oid, _mat_grass())
                elif layer in (LAYER_STEP, LAYER_RAMP):
                    _apply_material(oid, _mat_stone_step())
                return oid
        return None
    fill_box = rg.BoundingBox(rg.Point3d(-half_l, -half_w, 0.0), rg.Point3d(half_l, half_w, FILL_H))
    _add_brep(rg.Brep.CreateFromBox(fill_box), LAYER_FILL, (164,130,92))

    # grass top cap only at z = +FILL_H
    top_rect = rg.Rectangle3d(rg.Plane(rg.Point3d(0.0, 0.0, FILL_H), rg.Vector3d.ZAxis),
                              rg.Interval(-half_l, half_l), rg.Interval(-half_w, half_w)).ToNurbsCurve()
    top_srf = rg.Brep.CreatePlanarBreps([top_rect], 0.001)
    if top_srf:
        _add_brep(top_srf[0], LAYER_FILL_TOP, (82,125,56))

    # openings: 3 steps for pedestrian, ramp for vehicular
    STEP_COUNT = 3
    step_rise = FILL_H / float(STEP_COUNT)
    step_run = 0.30
    ramp_run = 2.0
    wall_t = float(comp.get("wall_thickness", 0.20) or 0.20)

    for op in openings:
        axis = op.get("axis")
        fixed = float(op.get("fixed", 0.0))
        s0 = float(op.get("start", 0.0)); s1 = float(op.get("end", 0.0))
        out_sign = float(op.get("outside_sign", -1.0) or -1.0)

        # IMPORTANT:
        # metadata stores `fixed` on the INNER face of the north wall and
        # `outside_sign` pointing inward for the old gate-louver placement.
        # For access generation we need the ROAD side, so use the OUTER wall face
        # and reverse the direction.
        outside_dir = -out_sign
        outer_face = fixed - out_sign * wall_t

        kind = op.get("kind", "")
        if axis == 'x':
            width0, width1 = s0, s1
            if kind == 'pedestrian':
                # Steps are OUTSIDE the plot. The TOP/third step must touch the compound boundary,
                # and the lowest step must stay out toward the road.
                for i in range(STEP_COUNT):
                    z0 = i * step_rise
                    z1 = (i + 1) * step_rise
                    d0 = step_run * (STEP_COUNT - i - 1)
                    d1 = step_run * (STEP_COUNT - i)
                    seg_a = outer_face + outside_dir * d0
                    seg_b = outer_face + outside_dir * d1
                    y0 = min(seg_a, seg_b); y1 = max(seg_a, seg_b)
                    bb = rg.BoundingBox(rg.Point3d(width0, y0, z0), rg.Point3d(width1, y1, z1))
                    _add_brep(rg.Brep.CreateFromBox(bb), LAYER_STEP, (190,190,190))
            elif kind == 'vehicular':
                # Ramp is OUTSIDE the plot, from road z=0 to site z=+FILL_H
                road_edge = outer_face + outside_dir * ramp_run
                p0 = rg.Point3d(width0, road_edge, 0.0)
                p1 = rg.Point3d(width1, road_edge, 0.0)
                p2 = rg.Point3d(width1, outer_face, FILL_H)
                p3 = rg.Point3d(width0, outer_face, FILL_H)
                pln = rg.Polyline([p0, p1, p2, p3, p0]).ToNurbsCurve()
                breps = rg.Brep.CreatePlanarBreps([pln], 0.001)
                if breps:
                    _add_brep(breps[0], LAYER_RAMP, (150,150,150))
        else:  # axis == 'y'
            width0, width1 = s0, s1
            if kind == 'pedestrian':
                for i in range(STEP_COUNT):
                    z0 = i * step_rise
                    z1 = (i + 1) * step_rise
                    d0 = step_run * (STEP_COUNT - i - 1)
                    d1 = step_run * (STEP_COUNT - i)
                    seg_a = outer_face + outside_dir * d0
                    seg_b = outer_face + outside_dir * d1
                    x0 = min(seg_a, seg_b); x1 = max(seg_a, seg_b)
                    bb = rg.BoundingBox(rg.Point3d(x0, width0, z0), rg.Point3d(x1, width1, z1))
                    _add_brep(rg.Brep.CreateFromBox(bb), LAYER_STEP, (190,190,190))
            elif kind == 'vehicular':
                road_edge = outer_face + outside_dir * ramp_run
                p0 = rg.Point3d(road_edge, width0, 0.0)
                p1 = rg.Point3d(road_edge, width1, 0.0)
                p2 = rg.Point3d(outer_face, width1, FILL_H)
                p3 = rg.Point3d(outer_face, width0, FILL_H)
                pln = rg.Polyline([p0, p1, p2, p3, p0]).ToNurbsCurve()
                breps = rg.Brep.CreatePlanarBreps([pln], 0.001)
                if breps:
                    _add_brep(breps[0], LAYER_RAMP, (150,150,150))
    _enforce_wireframe()
    sc.doc.Views.Redraw()



def _add_gf_perimeter_steps(Building):
    """Add a single-step threshold around the entire GF deck perimeter.

    Connects site filling level (+0.30m) up to the GF deck entry level.
    Each outer edge of the GF footprint gets one step:
        riser  = 0.15 m  (step from site fill to this tread)
        tread  = 0.30 m  (projects outward from the beam outer face)
    The step runs continuously along each face — one merged bar per
    collinear run of outer edges, so corners are clean and there are no gaps.
    """
    gs       = float(Building.get("grid", {}).get("spacing", 0.0) or 0.0)
    FILL_H   = float(Building.get("compound", {}).get("site_fill_height", 0.30) or 0.30)
    STEP_H   = 0.15          # riser height
    TREAD_D  = 0.60          # tread depth (horizontal projection outward)
    LAYER    = "GF_Perimeter_Steps"
    COLOR    = (200, 185, 160)

    if gs <= 0.01:
        print("  [GF Steps] Skipped — grid spacing not available.")
        return

    if not rs.IsLayer(LAYER):
        rs.AddLayer(LAYER, COLOR)

    # ── GF panel keys ─────────────────────────────────────────────────────────
    panel_coords = Building.get("panels", {}).get("panel_coords_per_floor", [])
    if not panel_coords:
        print("  [GF Steps] No panel coords — skipped.")
        return
    gf_keys = panel_coords[0] if panel_coords else []
    if not gf_keys:
        print("  [GF Steps] No GF panel keys — skipped.")
        return

    # ── Beam extension beyond column grid (GF = first floor, index 0) ─────────
    exts = Building.get("structure", {}).get("plinth_beams", {}).get("extension_per_floor", [])
    ext = float(exts[0]) if exts else 0.0

    # ── Step Z extents ─────────────────────────────────────────────────────────
    z0 = FILL_H            # bottom of step = top of site fill
    z1 = FILL_H + STEP_H   # top of step

    # ── Get all outer edges of GF footprint ───────────────────────────────────
    outer_edges = get_outer_edges_from_floor_panels(gf_keys, gs)
    if not outer_edges:
        print("  [GF Steps] No outer edges found — skipped.")
        return

    # ── Group collinear edges by (orientation, fixed_coord) and merge runs ────
    # Then build one box per merged run.
    # Outer face coordinate depends on orientation + extension:
    #   "bottom" → fixed y = cy - ext (outer face is at y = cy - ext)
    #   "top"    → fixed y = cy2 + ext
    #   "left"   → fixed x = cx - ext
    #   "right"  → fixed x = cx2 + ext
    # The tread box projects OUTWARD (away from building) by TREAD_D.

    runs = {}  # (orientation, fixed_outer_coord_rounded) → list of span intervals
    for e in outer_edges:
        orient = e["orientation"]
        if orient == "bottom":
            fixed_outer = round(e["y1"], 4)
            span        = (round(e["x1"], 4), round(e["x2"], 4))
        elif orient == "top":
            fixed_outer = round(e["y1"], 4)
            span        = (round(e["x1"], 4), round(e["x2"], 4))
        elif orient == "left":
            fixed_outer = round(e["x1"], 4)
            span        = (round(e["y1"], 4), round(e["y2"], 4))
        else:  # "right"
            fixed_outer = round(e["x1"], 4)
            span        = (round(e["y1"], 4), round(e["y2"], 4))
        key = (orient, fixed_outer)
        runs.setdefault(key, []).append(span)

    # Merge overlapping / touching intervals per run
    def _merge_intervals(intervals):
        if not intervals:
            return []
        srt = sorted(intervals)
        merged = [list(srt[0])]
        for lo, hi in srt[1:]:
            if lo <= merged[-1][1] + 0.001:
                merged[-1][1] = max(merged[-1][1], hi)
            else:
                merged.append([lo, hi])
        return merged

    def _add_box(pmin, pmax):
        bb   = rg.BoundingBox(pmin, pmax)
        brep = rg.Brep.CreateFromBox(bb)
        if brep and brep.IsValid:
            oid = sc.doc.Objects.AddBrep(brep)
            if oid:
                rs.ObjectLayer(oid, LAYER)
                rs.ObjectColor(oid, COLOR)
                _apply_material(oid, _mat_stone_step())

    step_count = 0
    for (orient, fixed_outer), spans in runs.items():
        for (span_lo, span_hi) in _merge_intervals(spans):
            if orient == "bottom":
                # Outer face at y = fixed_outer; tread projects to y = fixed_outer - TREAD_D
                _add_box(rg.Point3d(span_lo, fixed_outer - TREAD_D, z0),
                         rg.Point3d(span_hi, fixed_outer,           z1))
            elif orient == "top":
                # Outer face at y = fixed_outer; tread projects to y = fixed_outer + TREAD_D
                _add_box(rg.Point3d(span_lo, fixed_outer,           z0),
                         rg.Point3d(span_hi, fixed_outer + TREAD_D, z1))
            elif orient == "left":
                # Outer face at x = fixed_outer; tread projects to x = fixed_outer - TREAD_D
                _add_box(rg.Point3d(fixed_outer - TREAD_D, span_lo, z0),
                         rg.Point3d(fixed_outer,           span_hi, z1))
            else:  # "right"
                # Outer face at x = fixed_outer; tread projects to x = fixed_outer + TREAD_D
                _add_box(rg.Point3d(fixed_outer,           span_lo, z0),
                         rg.Point3d(fixed_outer + TREAD_D, span_hi, z1))
            step_count += 1

    _enforce_wireframe()
    sc.doc.Views.Redraw()
    print("  GF perimeter step placed: {} step segments, "
          "rise={:.2f}m, tread={:.2f}m, base Z={:.2f}m".format(
          step_count, STEP_H, TREAD_D, z0))


def _add_main_entrance_door_REMOVED(Building):
    pass
def _add_main_entrance_door(Building):
    """Automatic main entrance door on the BUILDING north-facing ground-floor wall.

    Directly sweeps all layers on the north wall face using geometry (depth_fixed
    + WALL_TOTAL_M). Picks the 2 adjacent GF sub-panel slots closest to gate_centre,
    deletes everything in that span, and places a wooden double-leaf door.
    No user interaction required.
    """
    gs = float(Building.get("grid", {}).get("spacing", 0.0) or 0.0)
    if gs <= 0.01:
        print("  [Entrance door] Skipped — grid spacing not available.")
        return

    # ── Layer setup ──────────────────────────────────────────────────────────
    if not rs.IsLayer("Main_Entrance_Door"):
        rs.AddLayer("Main_Entrance_Door", (101, 67, 33))

    # ── Door colours & dimensions ─────────────────────────────────────────────
    WOOD_FRAME_COLOR  = (80,  50,  20)
    WOOD_DOOR_COLOR   = (120, 78,  35)
    WOOD_HANDLE_COLOR = (190, 155, 80)
    DOOR_FRAME_WIDTH  = 0.060
    DOOR_LEAF_FRAME   = 0.040
    HANDLE_WIDTH      = 0.018
    HANDLE_DEPTH      = 0.030
    HANDLE_HEIGHT     = 0.500
    HANDLE_Z_BTM      = 0.950

    def _add_box(pmin, pmax, color):
        bb   = rg.BoundingBox(pmin, pmax)
        brep = rg.Brep.CreateFromBox(bb)
        if brep and brep.IsValid:
            oid = sc.doc.Objects.AddBrep(brep)
            if oid:
                rs.ObjectLayer(oid, "Main_Entrance_Door")
                rs.ObjectColor(oid, color)
                if color == WOOD_HANDLE_COLOR:
                    _apply_material(oid, _mat_aluminium())
                elif color in (WOOD_FRAME_COLOR, WOOD_DOOR_COLOR):
                    _apply_material(oid, _mat_timber_dark())
                else:
                    _apply_material(oid, _mat_timber_dark())
                return oid
        return None

    # ── GF Z band ─────────────────────────────────────────────────────────────
    bd     = float(Building["structure"]["plinth_beams"].get("depth", 0.0) or 0.0)
    ftp_all = (Building.get("structure", {}).get("columns", {})
                       .get("top_points_per_floor", []) or [])
    ftp0 = ftp_all[0] if ftp_all else []
    gf_panel_z = (float(ftp0[0][2]) + bd) if ftp0 else bd
    if len(ftp_all) > 1:
        ftp1 = ftp_all[1]
        gf_top_z = (float(ftp1[0][2]) + bd) if ftp1 else gf_panel_z + float(
            (Building.get("floors", {}).get("floor_heights", [3.0]) or [3.0])[0])
    else:
        gf_top_z = gf_panel_z + float(
            (Building.get("floors", {}).get("floor_heights", [3.0]) or [3.0])[0])
    z0_door = gf_panel_z + CLT_TOTAL_M   # bottom of door (top of floor build-up)
    z1_door = gf_top_z                   # top of door (underside of ceiling)
    z_tol   = 0.60                       # generous Z tolerance for sublayer objects

    # ── North side → wall face geometry ──────────────────────────────────────
    north = Building["plot"].get("north_side", "Top")
    pl    = float(Building["plot"].get("length", 0.0) or 0.0)
    pw    = float(Building["plot"].get("width",  0.0) or 0.0)
    half_l, half_w = pl * 0.5, pw * 0.5

    # Map north_side to:
    #   wall_axis  = span direction along the north wall ("x" or "y")
    #   depth_fixed = the fixed coordinate on the depth axis (outer face)
    #   depth_inward_sign = +1 if inward is toward +depth, -1 otherwise
    if north == "Top":
        wall_axis        = "x"          # north wall runs E-W, spans in X
        depth_fixed      = half_w       # outer face at Y = +half_w
        depth_inward     = -1           # inward = -Y
        span_lo, span_hi = -half_l, half_l
    elif north == "Bottom":
        wall_axis        = "x"
        depth_fixed      = -half_w
        depth_inward     = +1
        span_lo, span_hi = -half_l, half_l
    elif north == "Right":
        wall_axis        = "y"          # north wall runs N-S, spans in Y
        depth_fixed      = half_l
        depth_inward     = -1
        span_lo, span_hi = -half_w, half_w
    else:  # Left
        wall_axis        = "y"
        depth_fixed      = -half_l
        depth_inward     = +1
        span_lo, span_hi = -half_w, half_w

    print("  [Entrance door] north_side={} wall_axis={} depth_fixed={:.2f}".format(
        north, wall_axis, depth_fixed))

    # ── Gate centre (same logic as _add_compound_wall) ────────────────────────
    # Gate assembly = OPEN_A(6m) + PIER_B(1m) + OPEN_B(2m) = 9m centred on span
    # We use 0.0 as default (plot centre) if gate info not stored in Building.
    OPEN_A   = 6.0
    PIER_B   = 1.0
    OPEN_B   = 2.0
    assembly = OPEN_A + PIER_B + OPEN_B   # 9.0 m total gate assembly width
    # The gate is centred at the midpoint of the span (plot centre along wall)
    gate_centre = Building.get("compound", {}).get("gate_centre", 0.0) or 0.0
    print("  [Entrance door] gate_centre={:.2f}".format(gate_centre))

    # ── Collect ALL ground-floor objects on the north wall face ──────────────
    SWEEP_LAYERS = (
        ["Wall_Panels_0"]
        + ["Wall_Panels_0::{}".format(s) for s in
           ["Ext_Cladding","Wind_Barrier","Insulation","Vapour_Barrier","Plasterboard"]]
        + ["Glass_Windows", "Glass_Doors",
           "Window_Frames", "Glass_Window_Sills",
           "Facade_Louvers", "Facade_Louvers_Bar"]
    )

    def _on_north_wall(bb_pts):
        """True if this object sits on the north-facing ground-floor wall."""
        # Z check — must overlap GF height band
        z_max = max(p.Z for p in bb_pts)
        z_min = min(p.Z for p in bb_pts)
        if z_max < z0_door - z_tol or z_min > z1_door + z_tol:
            return False
        # Depth check — outer face must be near depth_fixed (±WALL_TOTAL_M + glass frame)
        depth_tol = WALL_TOTAL_M + 0.15   # 170mm wall + 150mm tolerance
        if wall_axis == "x":
            obj_depth_outer = max(p.Y for p in bb_pts) if depth_inward < 0 else min(p.Y for p in bb_pts)
        else:
            obj_depth_outer = max(p.X for p in bb_pts) if depth_inward < 0 else min(p.X for p in bb_pts)
        if abs(obj_depth_outer - depth_fixed) > depth_tol:
            return False
        return True

    def _span_centre(bb_pts):
        """Centre coordinate along the wall span axis."""
        if wall_axis == "x":
            return 0.5 * (min(p.X for p in bb_pts) + max(p.X for p in bb_pts))
        else:
            return 0.5 * (min(p.Y for p in bb_pts) + max(p.Y for p in bb_pts))

    # Gather: {obj_id: (span_centre, bb_pts)}
    gf_north_objs = {}
    for ln in SWEEP_LAYERS:
        if not rs.IsLayer(ln):
            continue
        for oid in (rs.ObjectsByLayer(ln) or []):
            if oid in gf_north_objs:
                continue
            bb = rs.BoundingBox(oid)
            if not bb:
                continue
            if _on_north_wall(bb):
                gf_north_objs[oid] = (_span_centre(bb), bb)

    print("  [Entrance door] {} objects found on north GF wall".format(len(gf_north_objs)))
    if not gf_north_objs:
        print("  [Entrance door] No north-wall GF objects found — skipped.")
        return

    # ── Group objects into column slots (grid/3 sub-panel width) ─────────────
    # Sub-panels are gs/3 wide. Round each object's span-centre to the nearest
    # gs/3 slot to group all sublayers of the same column together.
    slot_w = gs / 3.0
    def _slot(sc_val):
        return round(sc_val / slot_w) * slot_w

    slots = {}   # slot_key -> list of obj_ids
    for oid, (sc_val, _) in gf_north_objs.items():
        sk = round(_slot(sc_val), 3)
        slots.setdefault(sk, []).append(oid)

    print("  [Entrance door] {} column slots on north wall: {}".format(
        len(slots), sorted(slots.keys())))

    if len(slots) < 1:
        print("  [Entrance door] No slots found — skipped.")
        return

    # ── Find 2 adjacent slots closest to gate_centre ─────────────────────────
    sorted_keys = sorted(slots.keys())

    if len(sorted_keys) == 1:
        # Only one slot available — use it (single panel door)
        best_pair = [sorted_keys[0]]
    else:
        # Score each consecutive pair by distance of pair-centre from gate_centre
        best_pair = None
        best_dist = float("inf")
        for i in range(len(sorted_keys) - 1):
            k0, k1 = sorted_keys[i], sorted_keys[i+1]
            # Must be truly adjacent (gap ≤ 1.5 * slot_w)
            if k1 - k0 > 1.5 * slot_w:
                continue
            pair_centre = 0.5 * (k0 + k1)
            dist = abs(pair_centre - gate_centre)
            if dist < best_dist:
                best_dist = dist
                best_pair = [k0, k1]

        if best_pair is None:
            # No adjacent pairs (all slots far apart) — pick single closest slot
            best_pair = [min(sorted_keys, key=lambda k: abs(k - gate_centre))]

    print("  [Entrance door] chosen slots: {}".format(best_pair))

    # ── Collect all objects in chosen slots ───────────────────────────────────
    del_ids = set()
    for sk in best_pair:
        for oid in slots.get(sk, []):
            del_ids.add(oid)

    # Also sweep for any objects in the span that might have been missed
    # (e.g. if slot rounding placed them in a different bucket)
    if best_pair:
        span_min = min(best_pair) - slot_w * 0.6
        span_max = max(best_pair) + slot_w * 0.6
        for oid, (sc_val, bb) in gf_north_objs.items():
            if span_min <= sc_val <= span_max:
                del_ids.add(oid)

    print("  [Entrance door] deleting {} objects".format(len(del_ids)))

    # ── Compute door geometry extents ─────────────────────────────────────────
    # Span: from min edge of leftmost slot to max edge of rightmost slot
    all_bb_pts = []
    for oid in del_ids:
        bb = rs.BoundingBox(oid)
        if bb:
            all_bb_pts.extend(bb)

    if not all_bb_pts:
        print("  [Entrance door] No bounding box data — skipped.")
        return

    if wall_axis == "x":
        seg0 = min(p.X for p in all_bb_pts)
        seg1 = max(p.X for p in all_bb_pts)
        # Depth: full wall extent in Y
        if depth_inward < 0:   # Top wall: inward = -Y, outer face at +Y
            d_hi = depth_fixed
            d_lo = d_hi - WALL_TOTAL_M
        else:                   # Bottom wall: inward = +Y, outer face at -Y
            d_lo = depth_fixed
            d_hi = d_lo + WALL_TOTAL_M
        out_vec = rg.Vector3d(0, float(depth_inward) * -1, 0)
    else:
        seg0 = min(p.Y for p in all_bb_pts)
        seg1 = max(p.Y for p in all_bb_pts)
        if depth_inward < 0:   # Right wall: inward = -X, outer face at +X
            d_hi = depth_fixed
            d_lo = d_hi - WALL_TOTAL_M
        else:                   # Left wall: inward = +X, outer face at -X
            d_lo = depth_fixed
            d_hi = d_lo + WALL_TOTAL_M
        out_vec = rg.Vector3d(float(depth_inward) * -1, 0, 0)

    z0 = z0_door
    z1 = z1_door

    print("  [Entrance door] span={:.3f}-{:.3f}  depth={:.3f}-{:.3f}  Z={:.3f}-{:.3f}".format(
        seg0, seg1, d_lo, d_hi, z0, z1))

    # ── Delete selected objects ───────────────────────────────────────────────
    for oid in del_ids:
        try:
            rs.DeleteObject(oid)
        except Exception:
            pass

    # ── Build wooden double-leaf entrance door ────────────────────────────────
    fw  = DOOR_FRAME_WIDTH
    lfw = DOOR_LEAF_FRAME
    gap = 0.010
    mid = 0.5 * (seg0 + seg1)
    fd  = d_hi - d_lo

    if wall_axis == "x":
        # Frame
        _add_box(rg.Point3d(seg0, d_lo, z0),       rg.Point3d(seg1, d_hi, z0+fw),     WOOD_FRAME_COLOR)
        _add_box(rg.Point3d(seg0, d_lo, z1-fw),    rg.Point3d(seg1, d_hi, z1),        WOOD_FRAME_COLOR)
        _add_box(rg.Point3d(seg0, d_lo, z0),       rg.Point3d(seg0+fw, d_hi, z1),     WOOD_FRAME_COLOR)
        _add_box(rg.Point3d(seg1-fw, d_lo, z0),    rg.Point3d(seg1, d_hi, z1),        WOOD_FRAME_COLOR)
        _add_box(rg.Point3d(mid-fw*0.5, d_lo, z0), rg.Point3d(mid+fw*0.5, d_hi, z1), WOOD_FRAME_COLOR)
        bi = z0+fw; ti = z1-fw
        # Left leaf
        li = seg0+fw; ri = mid-gap
        _add_box(rg.Point3d(li,     d_lo, bi), rg.Point3d(li+lfw, d_hi, ti),     WOOD_DOOR_COLOR)
        _add_box(rg.Point3d(ri-lfw, d_lo, bi), rg.Point3d(ri,     d_hi, ti),     WOOD_DOOR_COLOR)
        _add_box(rg.Point3d(li,     d_lo, bi), rg.Point3d(ri,     d_hi, bi+lfw), WOOD_DOOR_COLOR)
        _add_box(rg.Point3d(li, d_lo, ti-lfw), rg.Point3d(ri,     d_hi, ti),     WOOD_DOOR_COLOR)
        _add_box(rg.Point3d(li+lfw, d_lo+fd*0.20, bi+lfw),
                 rg.Point3d(ri-lfw, d_hi-fd*0.20, ti-lfw),                       WOOD_DOOR_COLOR)
        hbt = z0+HANDLE_Z_BTM; htp = hbt+HANDLE_HEIGHT
        hx_l = 0.5*(li+ri) - HANDLE_WIDTH*0.5
        hd_lo = d_hi; hd_hi = d_hi+HANDLE_DEPTH
        _add_box(rg.Point3d(hx_l, hd_lo, hbt), rg.Point3d(hx_l+HANDLE_WIDTH, hd_hi, htp), WOOD_HANDLE_COLOR)
        # Right leaf
        li = mid+gap; ri = seg1-fw
        _add_box(rg.Point3d(li,     d_lo, bi), rg.Point3d(li+lfw, d_hi, ti),     WOOD_DOOR_COLOR)
        _add_box(rg.Point3d(ri-lfw, d_lo, bi), rg.Point3d(ri,     d_hi, ti),     WOOD_DOOR_COLOR)
        _add_box(rg.Point3d(li,     d_lo, bi), rg.Point3d(ri,     d_hi, bi+lfw), WOOD_DOOR_COLOR)
        _add_box(rg.Point3d(li, d_lo, ti-lfw), rg.Point3d(ri,     d_hi, ti),     WOOD_DOOR_COLOR)
        _add_box(rg.Point3d(li+lfw, d_lo+fd*0.20, bi+lfw),
                 rg.Point3d(ri-lfw, d_hi-fd*0.20, ti-lfw),                       WOOD_DOOR_COLOR)
        hx_r = 0.5*(li+ri) - HANDLE_WIDTH*0.5
        _add_box(rg.Point3d(hx_r, hd_lo, hbt), rg.Point3d(hx_r+HANDLE_WIDTH, hd_hi, htp), WOOD_HANDLE_COLOR)

    else:  # wall_axis == "y"
        # Frame
        _add_box(rg.Point3d(d_lo, seg0, z0),       rg.Point3d(d_hi, seg1, z0+fw),     WOOD_FRAME_COLOR)
        _add_box(rg.Point3d(d_lo, seg0, z1-fw),    rg.Point3d(d_hi, seg1, z1),        WOOD_FRAME_COLOR)
        _add_box(rg.Point3d(d_lo, seg0, z0),       rg.Point3d(d_hi, seg0+fw, z1),     WOOD_FRAME_COLOR)
        _add_box(rg.Point3d(d_lo, seg1-fw, z0),    rg.Point3d(d_hi, seg1, z1),        WOOD_FRAME_COLOR)
        _add_box(rg.Point3d(d_lo, mid-fw*0.5, z0), rg.Point3d(d_hi, mid+fw*0.5, z1), WOOD_FRAME_COLOR)
        bi = z0+fw; ti = z1-fw
        # Left leaf
        li = seg0+fw; ri = mid-gap
        _add_box(rg.Point3d(d_lo, li,     bi), rg.Point3d(d_hi, li+lfw, ti),     WOOD_DOOR_COLOR)
        _add_box(rg.Point3d(d_lo, ri-lfw, bi), rg.Point3d(d_hi, ri,     ti),     WOOD_DOOR_COLOR)
        _add_box(rg.Point3d(d_lo, li,     bi), rg.Point3d(d_hi, ri,     bi+lfw), WOOD_DOOR_COLOR)
        _add_box(rg.Point3d(d_lo, li, ti-lfw), rg.Point3d(d_hi, ri,     ti),     WOOD_DOOR_COLOR)
        _add_box(rg.Point3d(d_lo+fd*0.20, li+lfw, bi+lfw),
                 rg.Point3d(d_hi-fd*0.20, ri-lfw, ti-lfw),                       WOOD_DOOR_COLOR)
        hbt = z0+HANDLE_Z_BTM; htp = hbt+HANDLE_HEIGHT
        hy_l = 0.5*(li+ri) - HANDLE_WIDTH*0.5
        hd_lo = d_hi; hd_hi = d_hi+HANDLE_DEPTH
        _add_box(rg.Point3d(hd_lo, hy_l, hbt), rg.Point3d(hd_hi, hy_l+HANDLE_WIDTH, htp), WOOD_HANDLE_COLOR)
        # Right leaf
        li = mid+gap; ri = seg1-fw
        _add_box(rg.Point3d(d_lo, li,     bi), rg.Point3d(d_hi, li+lfw, ti),     WOOD_DOOR_COLOR)
        _add_box(rg.Point3d(d_lo, ri-lfw, bi), rg.Point3d(d_hi, ri,     ti),     WOOD_DOOR_COLOR)
        _add_box(rg.Point3d(d_lo, li,     bi), rg.Point3d(d_hi, ri,     bi+lfw), WOOD_DOOR_COLOR)
        _add_box(rg.Point3d(d_lo, li, ti-lfw), rg.Point3d(d_hi, ri,     ti),     WOOD_DOOR_COLOR)
        _add_box(rg.Point3d(d_lo+fd*0.20, li+lfw, bi+lfw),
                 rg.Point3d(d_hi-fd*0.20, ri-lfw, ti-lfw),                       WOOD_DOOR_COLOR)
        hy_r = 0.5*(li+ri) - HANDLE_WIDTH*0.5
        _add_box(rg.Point3d(hd_lo, hy_r, hbt), rg.Point3d(hd_hi, hy_r+HANDLE_WIDTH, htp), WOOD_HANDLE_COLOR)

    _enforce_wireframe()
    sc.doc.Views.Redraw()
    print("  Main entrance door placed on building north wall ({} facing), "
          "span={:.2f}m, {} objects cleared.".format(
          north, seg1 - seg0, len(del_ids)))


def _thicken_wall_panels(Building):
    """Replace every flat wall panel surface with 5 solid Brep layers extruded
    INWARD, matching the WALL_LAYERS build-up (170 mm total, GEG 2024).
    Each layer gets its own Rhino sub-layer under the parent Wall_Panels_N:
        Wall_Panels_0::Ext_Cladding    (outermost, 15mm larch)
        Wall_Panels_0::Wind_Barrier    (2mm membrane)
        Wall_Panels_0::Insulation      (140mm mineral wool)
        Wall_Panels_0::Vapour_Barrier  (1mm PE foil)
        Wall_Panels_0::Plasterboard    (innermost, 12mm GKB)
    Glass panels (Glass_Panels layer) are untouched.
    Uses rg.Brep.CreateFromBox (explicit min/max corners) — no direction ambiguity.
    """
    t_total = WALL_TOTAL_M
    tol_flat = 0.02
    tol_min  = 0.05
    gs = Building["grid"]["spacing"]
    bd = Building["structure"]["plinth_beams"]["depth"]
    floor_z_list = []
    for fi_idx in range(len(Building["structure"]["columns"]["top_points_per_floor"])):
        ftp = Building["structure"]["columns"]["top_points_per_floor"][fi_idx]
        if ftp:
            floor_z_list.append((fi_idx, ftp[0][2] + bd))
    def _get_fi(z_val):
        best_fi, best_d = 0, float('inf')
        for fi_idx, pz in floor_z_list:
            d = abs(z_val - pz)
            if d < best_d:
                best_d = d
                best_fi = fi_idx
        return best_fi
    def _get_fkeys(fi_idx):
        if fi_idx < len(Building["panels"]["panel_coords_per_floor"]):
            return set((round(k[0], 4), round(k[1], 4))
                       for k in Building["panels"]["panel_coords_per_floor"][fi_idx])
        return set()
    def _has_floor_at(px, py, fkeys):
        for (kx, ky) in fkeys:
            if kx - 0.01 <= px <= kx + gs + 0.01 and \
               ky - 0.01 <= py <= ky + gs + 0.01:
                return True
        return False
    orient_lookup = {}
    for fi in range(len(Building["wall_panels"]["wall_panel_info_per_floor"])):
        info_map = Building["wall_panels"]["wall_panel_info_per_floor"][fi]
        for ps, info in info_map.items():
            orient_lookup[ps] = info["edge"].get("orientation", "")
    processed = 0
    for fi in range(-1, 20):
        layer_name = "Wall_Panels_{}".format(fi)
        if not rs.IsLayer(layer_name):
            continue
        objs = rs.ObjectsByLayer(layer_name)
        if not objs:
            continue
        for (suffix, _, color, _) in WALL_LAYERS:
            sub_ln = "{}::{}".format(layer_name, suffix)
            if not rs.IsLayer(sub_ln):
                rs.AddLayer(sub_ln, color)
                try:
                    rs.ParentLayer(sub_ln, layer_name)
                except Exception:
                    pass
        for pid in list(objs):
            if not rs.IsObject(pid):
                continue
            bb = rs.BoundingBox(pid)
            if not bb or len(bb) < 8:
                continue
            xs = [p.X for p in bb]
            ys = [p.Y for p in bb]
            zs = [p.Z for p in bb]
            x_min, x_max = min(xs), max(xs)
            y_min, y_max = min(ys), max(ys)
            z_min, z_max = min(zs), max(zs)
            dx = x_max - x_min
            dy = y_max - y_min
            dz = z_max - z_min
            if dz < tol_min:
                continue     # not a wall
            if dx > tol_flat and dy > tol_flat:
                continue     # already thick — skip
            parapet_h = Building["wall_panels"]["parapet_height"]
            if dz < parapet_h + 0.05:
                continue     # parapet (1m) — untouched
            orient = orient_lookup.get(str(pid), "")
            wall_type = None
            inward_sign = 0
            outer_pos = 0.0
            w_fi = _get_fi(z_min)
            w_fkeys = _get_fkeys(w_fi)
            if dx > tol_min and dy <= tol_flat:
                wall_type = 'x'
                outer_pos = (y_min + y_max) / 2.0
                if orient == "bottom":
                    inward_sign = 1
                elif orient == "top":
                    inward_sign = -1
                else:
                    mid_x = (x_min + x_max) / 2.0
                    has_plus  = _has_floor_at(mid_x, outer_pos + gs * 0.5, w_fkeys)
                    has_minus = _has_floor_at(mid_x, outer_pos - gs * 0.5, w_fkeys)
                    if has_plus and not has_minus:
                        inward_sign = 1
                    elif has_minus and not has_plus:
                        inward_sign = -1
                    else:
                        inward_sign = 1   # both or neither — default +Y
            elif dy > tol_min and dx <= tol_flat:
                wall_type = 'y'
                outer_pos = (x_min + x_max) / 2.0
                if orient == "left":
                    inward_sign = 1
                elif orient == "right":
                    inward_sign = -1
                else:
                    mid_y = (y_min + y_max) / 2.0
                    has_plus  = _has_floor_at(outer_pos + gs * 0.5, mid_y, w_fkeys)
                    has_minus = _has_floor_at(outer_pos - gs * 0.5, mid_y, w_fkeys)
                    if has_plus and not has_minus:
                        inward_sign = 1
                    elif has_minus and not has_plus:
                        inward_sign = -1
                    else:
                        inward_sign = 1   # both or neither — default +X
            else:
                continue
            cursor = 0.0   # cumulative offset from outer face (grows inward)
            layer_created = False
            for (suffix, layer_t, color, _desc) in WALL_LAYERS:
                start_offset = cursor
                end_offset   = cursor + layer_t
                if wall_type == 'x':
                    y_a = outer_pos + start_offset * inward_sign
                    y_b = outer_pos + end_offset   * inward_sign
                    box_min = rg.Point3d(x_min, min(y_a, y_b), z_min)
                    box_max = rg.Point3d(x_max, max(y_a, y_b), z_max)
                else:
                    x_a = outer_pos + start_offset * inward_sign
                    x_b = outer_pos + end_offset   * inward_sign
                    box_min = rg.Point3d(min(x_a, x_b), y_min, z_min)
                    box_max = rg.Point3d(max(x_a, x_b), y_max, z_max)
                box  = rg.BoundingBox(box_min, box_max)
                brep = rg.Brep.CreateFromBox(box)
                if not brep or not brep.IsValid:
                    cursor = end_offset
                    continue
                sub_ln = "{}::{}".format(layer_name, suffix)
                new_id = sc.doc.Objects.AddBrep(brep)
                if new_id:
                    rs.ObjectLayer(new_id, sub_ln)
                    rs.ObjectColor(new_id, color)
                    layer_created = True
                    if suffix == "Ext_Cladding":
                        _apply_material(new_id, _mat_louver_fin())
                    elif suffix == "Wind_Barrier":
                        _apply_material(new_id, _mat_membrane())
                    elif suffix == "Insulation":
                        _apply_material(new_id, _mat_insulation())
                    elif suffix == "Vapour_Barrier":
                        _apply_material(new_id, _mat_membrane())
                    elif suffix == "Plasterboard":
                        _apply_material(new_id, _mat_facade_paint())
                cursor = end_offset
            if layer_created:
                rs.DeleteObject(pid)
                processed += 1
    layer_desc = " + ".join(
        "{}mm {}".format(int(t * 1000), n) for n, t, _, _ in WALL_LAYERS)
    print("  Wall panels split into 5 layers: {}".format(layer_desc))
    print("  Total wall thickness: {}mm | {} panels processed.".format(
        int(t_total * 1000), processed))
    _enforce_wireframe()
    sc.doc.Views.Redraw()
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
    panel_counts = {}
    for elev_info in ELEVATION_DIRECTIONS:
        fp = _get_wall_panels_for_elevation(Building, elev_info["facing"])
        panel_counts[elev_info["name"]] = len(fp)
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
    _enforce_wireframe()
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
    for lyr in EXTRUSION_LAYERS:
        if rs.IsLayer(lyr):
            try:
                rs.LayerVisible(lyr, True)
            except Exception:
                pass
    print("  Elevation extrusion layers restored.")
    rs.Command("_-SetView _World _Perspective", False)
    rs.ZoomExtents()
    _enforce_wireframe()
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
def main():
    print_section_header("PARAMETRIC BUILDING GENERATOR")
    rs.Command("_-SetView _World _Top", False)
    _enforce_wireframe()
    rs.Redraw()
    _intro = ProjectIntroDialog()
    if not _intro.ShowModal(Rhino.UI.RhinoEtoApp.MainWindow):
        print("  [Intro] Cancelled at project introduction.  Script aborted.")
        return None
    clear_plot()
    # ── Switch ALL viewports to Wireframe for the entire generation run ────────
    try:
        _wf_dm = Rhino.Display.DisplayModeDescription.FindByName("Wireframe")
        if _wf_dm:
            _ACTIVE_WF_DM[0] = _wf_dm          # enable enforcement for entire run
            for _v in sc.doc.Views:
                try: _v.ActiveViewport.DisplayMode = _wf_dm
                except Exception: pass
            sc.doc.Views.Redraw()
            print("  [View] All viewports → Wireframe mode for generation.")
    except Exception as _dme:
        print("  [View] Could not set wireframe: {}".format(_dme))
    _cached_metal_mat_idx[0] = None   # reset material caches for re-run
    _cached_glass_mat_idx[0] = None
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
    process_all_floor_panels(Building)
    generate_staircase(Building)
    process_all_wall_panels(Building)
    process_wall_extrusions(Building)
    process_vertical_arch_extrusions(Building)
    process_facade_subdivision(Building)
    print_section_header("WALL PANEL THICKNESS (GEG 2024)")
    print("  Adding {}mm wall build-up (5 layers) to all wall panels.".format(
        int(WALL_TOTAL_M * 1000)))
    print("  Glass panels untouched.")
    _thicken_wall_panels(Building)
    print_section_footer()
    print_section_header("GLASS REPLACEMENT (SCHUCO AWS 75 / ADS 75)")
    print("  Classifying glass panels: DOOR (terrace outside) vs WINDOW (open air).")
    print("  Windows: full height + frame 50mm + transom + fixed/openable glass.")
    print("  Doors: full height + frame 60mm + single glass pane.")
    _replace_glass_with_schuco(Building)
    print_section_footer()
    print_section_header("GLASS BALUSTRADES (DIN 18008-4)")
    print("  Replacing flat parapet walls with frameless glass balustrades.")
    print("  VSG {}mm glass + aluminium channel + handrail.".format(
        int(BALUSTRADE_GLASS_THICKNESS * 1000)))
    _replace_parapets_with_balustrades(Building)
    print_section_footer()
    print_section_header("FACADE SCREEN (PARAMETRIC DENSITY)")
    if Building["floors"].get("num_upper_floors", 0) <= 0:
        print("  Ground floor only selected (G + roof) — skipping facade louvers.")
    else:
        print("  Adding vertical timber louver screen with density pattern.")
        print("  Skipping basement + terraces (except top floor) + wall extrusions.")
        _add_facade_louvers(Building)
    print_section_footer()
    print_section_header("COMPOUND WALL + GATES")
    print("  Adding 2.0m perimeter compound wall with centered north-side gate openings.")
    _add_compound_wall(Building)
    print("  Adding site filling, grass top, entry steps and vehicular ramp.")
    _add_site_filling_and_entry_access(Building)
    print("  Adding GF perimeter threshold step (rise=0.15m, tread=0.60m).")
    _add_gf_perimeter_steps(Building)
    print_section_footer()
    print_section_header("MAIN ENTRANCE DOOR (AUTOMATIC)")
    print("  Placing double wooden entrance door on north-facing ground-floor wall.")
    print("  2 sub-panels centred on compound gate opening — fully automatic.")
    _add_main_entrance_door(Building)
    print_section_footer()
    Building["floors"]["total_height"] = sum(Building["floors"]["floor_heights"])
    print("  [Final] Aligning CPlane to plot base (XY = plot bottom)...")
    try:
        pl = Building["plot"]["length"]
        pw = Building["plot"]["width"]
        origin = rg.Point3d(-pl / 2.0, -pw / 2.0, 0.0)
        x_axis = rg.Vector3d(1.0, 0.0, 0.0)
        y_axis = rg.Vector3d(0.0, 1.0, 0.0)
        plot_plane = rg.Plane(origin, x_axis, y_axis)
        for view_obj in sc.doc.Views:
            try:
                view_obj.ActiveViewport.SetConstructionPlane(plot_plane)
            except Exception:
                pass
        print("  CPlane set: origin=({:.2f},{:.2f},0)  X=world+X  Y=world+Y  Z=up".format(
              origin.X, origin.Y))
    except Exception as _ecp:
        print("  [CPlane error] {}".format(_ecp))
    print("  [Final] Setting perspective camera (looking down at plot)...")
    rs.Command("_-SetView _World _Perspective", False)
    try:
        view = sc.doc.Views.ActiveView
        if view:
            vp = view.ActiveViewport
            all_ids = [obj.Id for obj in sc.doc.Objects if not obj.IsDeleted]
            bbox = None
            if all_ids:
                bbox = sc.doc.Objects.BoundingBox(all_ids, rg.ActiveSpace.ModelSpace)
            if bbox is not None and bbox.IsValid:
                cx = (bbox.Min.X + bbox.Max.X) * 0.5
                cy = (bbox.Min.Y + bbox.Max.Y) * 0.5
                model_span = max(pl, pw, bbox.Max.Z - bbox.Min.Z)
                off = model_span * 2.5
                cam_loc = rg.Point3d(cx + off * 0.55,
                                     cy - off * 0.80,
                                     off * 0.90)      # large Z = camera high above
                target  = rg.Point3d(cx, cy, 0.0)    # aim at plot base centre
            else:
                cam_loc = rg.Point3d(60.0, -90.0, 80.0)
                target  = rg.Point3d(0.0, 0.0, 0.0)
            vp.SetCameraUp(rg.Vector3d(0.0, 0.0, 1.0), True)
            vp.SetCameraTarget(target, True)
            vp.SetCameraLocation(cam_loc, True)
            print("  Camera: loc=({:.1f},{:.1f},{:.1f})  target=({:.1f},{:.1f},{:.1f})".format(
                  cam_loc.X, cam_loc.Y, cam_loc.Z,
                  target.X,  target.Y,  target.Z))
    except Exception as _ev:
        print("  [Camera error] {}".format(_ev))
    rs.ZoomExtents()
    _enforce_wireframe()
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
    # ── Switch back to Shaded before showing the completion dialog ────────────
    try:
        _ACTIVE_WF_DM[0] = None                # stop wireframe enforcement
        _sh_dm = Rhino.Display.DisplayModeDescription.FindByName("Rendered")
        if _sh_dm:
            for _v in sc.doc.Views:
                try: _v.ActiveViewport.DisplayMode = _sh_dm
                except Exception: pass
            sc.doc.Views.Redraw()
            print("  [View] All viewports → Rendered mode (materials visible).")
    except Exception as _dme:
        print("  [View] Could not set shaded: {}".format(_dme))
    complete_dlg = BuildingCompleteDialog(Building)
    complete_dlg.ShowModal(Rhino.UI.RhinoEtoApp.MainWindow)
    return Building
if __name__ == "__main__":
    Building_data = main()
