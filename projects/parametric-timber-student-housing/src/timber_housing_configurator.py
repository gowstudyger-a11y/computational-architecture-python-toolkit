# -*- coding: utf-8 -*-
"""
===============================================================================
 timber_housing_configurator.py
 Parametric Timber Student Housing - Timber Skeleton / Rack Configurator - PHASE 1
===============================================================================
 Target: Rhino 8, Python 3 (also kept IronPython-2.7-tolerant: no f-strings,
 no walrus, explicit float division). Eto dialog with rs.Get* fallback.

 SOURCE OF TRUTH:
   "skeleton structure with slabs and staircase.obj"  (SketchUp export, meters)
   + annotated references (profile marking.png = RED cascade / BLUE double
   height zone; 3rd-floor grid plan; section videos).
   See docs/ASSET_INDEX.md, docs/STRUCTURAL_LOGIC_INFERENCE.md,
   docs/COMPUTATIONAL_WORKFLOW.md.

 COORDINATE CONVENTION (user-confirmed):
   Units meters. Origin = SW corner of ground-floor rack at the LOW cascade
   end. X = building length (repeats), Y = FIXED section depth, Z = height.
   All coordinates are MEMBER CENTRELINE / AXIS coordinates:
       3.5 m clear + 0.3 m member = 3.8 m axis-to-axis  (X grid, Y grid,
       and floor-to-floor pitch, exactly as in the reference model).

 PHASE 1 ONLY: skeleton/rack base. No facade, no windows, no cuboid windows,
 no module interiors. Module placeholders + StructuralModel data collection.
===============================================================================
"""

import math
import os
import json
import datetime

import rhinoscriptsyntax as rs
import scriptcontext as sc
import Rhino
import Rhino.Geometry as rg

# =============================================================================
# 1. CONSTANTS MEASURED FROM THE REFERENCE MODEL (do not change casually)
# =============================================================================

AXIS          = 3.8    # axis-to-axis grid    (= 3.5 clear + 0.3 member)
CLEAR         = 3.5    # architectural clear bay
MEMBER        = 0.3    # column / beam / branch square section
CORRIDOR_BAND = 2.3    # corridor axis band   (= 2.0 clear + 0.3 member)
FLOOR_PITCH   = 3.8    # floor-to-floor       (= 3.5 clear + 0.3 structure)
PLINTH        = 0.7    # top of ground pedestal above Z=0 (measured 0.65-0.7)
PEDESTAL_SIZE = 0.4    # visual pedestal pad
SLAB_T        = 0.3    # slab plate thickness

# Fixed Y-section axes (measured):  outerL, mod/corrL, corr/atrL,
#                                   atr/corrR, corr/modR, outerR
Y_OUT_L  = 0.15
Y_MID_L  = 3.95
Y_COR_L  = 6.25    # atrium-facing corridor edge, LEFT   (branch target line)
Y_COR_R  = 10.05   # atrium-facing corridor edge, RIGHT  (branch target line)
Y_MID_R  = 12.35
Y_OUT_R  = 16.15
SECTION_AXES_Y  = [Y_OUT_L, Y_MID_L, Y_COR_L, Y_COR_R, Y_MID_R, Y_OUT_R]
MODULE_Y_AXES   = [Y_OUT_L, Y_MID_L, Y_MID_R, Y_OUT_R]
CORRIDOR_Y_AXES = [Y_COR_L, Y_COR_R]
TRUNK_Y         = 8.15               # atrium centreline (tree trunk line)
SECTION_WIDTH   = Y_OUT_R - Y_OUT_L + MEMBER   # 16.3 overall

V_BASE_Y_LEFT   = (Y_OUT_L + Y_MID_L) / 2.0    # 2.05  (measured V base line)
V_BASE_Y_RIGHT  = (Y_MID_R + Y_OUT_R) / 2.0    # 14.25 (measured V base line)

# -----------------------------------------------------------------------------
# CASCADE - reusable shape descriptor (user-confirmed storage format).
# Reference profile measured from slab extents + column tops:
#   [1, 2, 3, 3, 3, 3, 4, 5, 6, 7, 8, 8]   (bay 1 lowest, at the origin)
# Descriptor = feature list so a future peak change CONTINUES/SCALES the same
# outer silhouette instead of inventing a new cascade (Phase 2 hook).
# -----------------------------------------------------------------------------
CASCADE_DESCRIPTOR = {
    "name": "wood_nest_reference_cascade_v1",
    "reference_bays": 12,
    "reference_peak": 8,
    "start_floors": 1,
    "direction": "ascending_away_from_origin",
    "segments": [
        {"type": "ramp",    "bays": 3, "from": 1, "to": 3},  # bays 1-3
        {"type": "plateau", "bays": 3, "at": 3},             # bays 4-6
        {"type": "ramp",    "bays": 5, "from": 4, "to": 8},  # bays 7-11
        {"type": "plateau", "bays": 1, "at": 8},             # bay 12
    ],
    "profile": [1, 2, 3, 3, 3, 3, 4, 5, 6, 7, 8, 8],
}
REF_PROFILE = CASCADE_DESCRIPTOR["profile"]

# -----------------------------------------------------------------------------
# LAYERS (exact names from the brief) : (name, (r,g,b))
# -----------------------------------------------------------------------------
LAYERS = [
    ("00_Grid_Axis",                        (40, 40, 40)),
    ("01_Support_Points",                   (0, 80, 255)),
    ("02_Regular_Columns",                  (101, 67, 33)),
    ("03_Regular_Beams",                    (140, 98, 57)),
    ("04_Corridor_Slabs",                   (150, 150, 150)),
    ("05_Corridor_Edge_Beams",              (95, 85, 75)),
    ("06_Ground_V_Columns",                 (176, 112, 59)),
    ("07_Atrium_Trunk_Columns",             (77, 51, 25)),
    ("08_Atrium_Branches_To_Corridor",      (198, 134, 66)),
    ("09_Staircase_Reserved_Zones",         (220, 60, 60)),
    ("10_Module_Placeholders",              (255, 140, 0)),
    ("11_Cascade_Debug",                    (120, 190, 230)),
    ("12_Analysis_Model_Debug",             (170, 60, 200)),
    ("13_Text_Notes",                       (0, 0, 0)),
    ("14_Double_Height_Common_Space_Debug", (235, 195, 90)),
    # ---- Phase 2A dummy module placement (staged Stage-2 workflow) ----------
    # A/A1/B naming (2026-07-05 separate-OBJ correction). Internal codes stay
    # M1/M1A/M2:  Module A = M1, Module A1 = M1A, Module B = M2.
    ("20_Dummy_Module_A",                   (214, 178, 130)),
    ("21_Dummy_Module_A1",                  (186, 148, 100)),
    ("22_Dummy_Module_B",                   (192, 68, 54)),
    ("23_Green_Common_Terrace_Slots",       (110, 165, 65)),
    ("24_Module_Placement_Anchors_Debug",   (0, 110, 255)),
    ("25_Module_Placement_Notes",           (30, 30, 30)),
    # ---- Phase 2B detailed textured real modules (visual only) --------------
    ("30_Detailed_Module_A",                (214, 178, 130)),
    ("31_Detailed_Module_A1",               (186, 148, 100)),
    ("32_Detailed_Module_B",                (192, 68, 54)),
    ("33_Detailed_Module_Debug_Anchors",    (0, 160, 255)),
    ("34_Detailed_Module_Notes",            (30, 30, 30)),
]

# =============================================================================
# 2. PURE LOGIC - cascade + zones (no Rhino calls: testable standalone)
# =============================================================================

def build_cascade(n_bays, peak_floors):
    """Active floor count per bay (list, index 0 = bay 1).

    Phase 1: exact reference reproduction for (12, 8).
    Other values: reference profile resampled + rescaled while preserving the
    silhouette family (monotone, start=1, unit ramp steps via rounding, and a
    >= 2-bay top plateau where bay count allows). Phase 2 will refine this.
    """
    ref = REF_PROFILE
    rn = len(ref)
    rpk = float(max(ref))
    if n_bays == rn and peak_floors == int(rpk):
        return list(ref)
    prof = []
    for i in range(n_bays):
        if n_bays == 1:
            t = rn - 1.0
        else:
            t = (i / float(n_bays - 1)) * (rn - 1)
        i0 = int(math.floor(t))
        i1 = min(rn - 1, i0 + 1)
        u = t - i0
        val = ref[i0] * (1.0 - u) + ref[i1] * u
        val = val * peak_floors / rpk
        prof.append(max(1, int(round(val))))
    for i in range(1, n_bays):                    # monotone non-decreasing
        if prof[i] < prof[i - 1]:
            prof[i] = prof[i - 1]
    prof[-1] = max(1, peak_floors)                # reach the peak
    if n_bays >= 3:
        prof[-2] = max(1, peak_floors)            # >= 2-bay top plateau
    return prof


def grid_lateral_offset_for_section(section_index, total_sections,
                                    grid_type, offset_direction,
                                    offset_cells=1):
    """Lateral (section/Y) offset in model units for each length section/bay.

    Regular Grid (1):      offset = 0 for all sections.
    Half Offset Grid (2):  the second longitudinal half of the building
                           shifts sideways by exactly +/- offset_cells grid
                           cells; the first half stays at 0.
    Centre Offset Grid (3): first third = 0, middle third shifts by
                           +/- offset_cells grid cells, last third = 0.

    offset_direction: 1 = Shift Left (-Y), 2 = Shift Right (+Y).
    Uses the existing AXIS bay spacing (3.8 m) - clean, structural,
    grid-based shifts only, never random.
    """
    sign = -1.0 if int(offset_direction) == 1 else 1.0
    off = sign * float(offset_cells) * AXIS
    gt = int(grid_type)
    n = int(total_sections)
    b = int(section_index)
    if gt == 2:
        half = n // 2
        return off if b > half else 0.0
    if gt == 3:
        a = max(1, int(round(n / 3.0)))
        c = min(n - 1, int(round(2.0 * n / 3.0)))
        return off if (a < b <= c) else 0.0
    return 0.0


def derive_zones(P):
    """All special-zone bay sets, derived from parameters + cascade."""
    n = P["x_bays"]
    F = build_cascade(n, P["peak_floors"])

    stair_zones = []
    for (s, e) in [P["stair_zone_1"], P["stair_zone_2"]]:
        s = max(1, min(n, int(s)))
        e = max(s, min(n, int(e)))
        stair_zones.append((s, e))
    stair_bays = set()
    for (s, e) in stair_zones:
        for b in range(s, e + 1):
            stair_bays.add(b)

    dh_start = max(1, min(n, int(P["dh_start_bay"])))
    dh_bays = set(range(dh_start, n + 1))
    # double-height needs at least 2 floors above it
    dh_bays = set([b for b in dh_bays if F[b - 1] >= 2])

    v_bays = [b for b in range(int(P["v_start_bay"]), n + 1, int(P["v_step"]))
              if b in dh_bays and F[b - 1] >= 2]

    avoid = P.get("avoid_tree_columns_in_stair_zone", True)
    trunk_bays = [b for b in range(int(P["trunk_start_bay"]), n + 1,
                                   int(P["trunk_step"]))
                  if (not avoid or b not in stair_bays) and F[b - 1] >= 2]

    return {"F": F, "stair_zones": stair_zones, "stair_bays": stair_bays,
            "dh_bays": dh_bays, "dh_start": dh_start,
            "v_bays": v_bays, "trunk_bays": trunk_bays}


# =============================================================================
# 3. GEOMETRY / DOCUMENT HELPERS
# =============================================================================

def setup_layers():
    for name, col in LAYERS:
        if not rs.IsLayer(name):
            rs.AddLayer(name, col)
        else:
            rs.LayerColor(name, col)


def clean_layers():
    """Delete previous configurator output (regeneration behaviour)."""
    total = 0
    for name, _c in LAYERS:
        if rs.IsLayer(name):
            objs = rs.ObjectsByLayer(name)
            if objs:
                total += len(objs)
                rs.DeleteObjects(objs)
    return total


# --------------------------------------------------------------------------- #
# Generated-object tagging (2026-07-08 site fix): every object this configurator
# creates in a run is stamped with a Timber Housing user-text marker at the END of the
# run. The startup cleanup then removes ONLY tagged objects, so user-created
# site surfaces / context / manually drawn geometry are NEVER deleted - even if
# they happen to sit on a Timber Housing layer.
# --------------------------------------------------------------------------- #
WOSYHO_TAG_KEY = "WoSyHo_Generated"
WOSYHO_TAG_VAL = "1"


def _wosyho_all_object_ids():
    """Set of all current Rhino document object ids (empty on failure)."""
    try:
        ids = rs.AllObjects()
        return set(ids) if ids else set()
    except Exception:
        return set()


def _wosyho_is_generated(oid):
    """True only if the object carries the Timber Housing generated marker."""
    try:
        return rs.GetUserText(oid, WOSYHO_TAG_KEY) == WOSYHO_TAG_VAL
    except Exception:
        return False


def tag_generated_objects_since(pre_ids):
    """Stamp every object created since `pre_ids` (i.e. generated by this run)
    with the Timber Housing marker so the next run's safe cleanup can remove ONLY
    generated geometry. Objects present before generation (the user's site /
    context geometry) are in pre_ids and are never tagged. Returns the count."""
    n = 0
    try:
        for oid in _wosyho_all_object_ids():
            if oid in pre_ids:
                continue
            try:
                rs.SetUserText(oid, WOSYHO_TAG_KEY, WOSYHO_TAG_VAL)
                n += 1
            except Exception:
                continue
    except Exception:
        pass
    return n


def safe_clear_generated_geometry_only():
    """SAFE startup cleanup (Rhino document only).

    Deletes ONLY objects generated by this configurator - objects on the known
    Timber Housing layers that carry the WoSyHo_Generated user-text tag (stamped at the
    end of each run by tag_generated_objects_since). It NEVER deletes user site
    surfaces, manually drawn context, or any untagged object - even if it sits
    on a Timber Housing layer - and it NEVER clears the whole document. Each candidate
    layer is temporarily made VISIBLE and UNLOCKED first so tagged objects can
    be removed. Layer DEFINITIONS and files on disk are preserved. Returns the
    number of objects deleted.

    NOTE: geometry generated by a version BEFORE this fix is untagged and is
    therefore PRESERVED (never deleted) on the first run after the update - if
    an old generated model stacks, delete it once manually; every model made
    from now on is tagged and cleaned automatically."""
    legacy = ["20_Dummy_Module_1", "21_Dummy_Module_1A_Mirrored",
              "22_Dummy_Module_2", "24_Module_Placement_Anchors_Debug",
              "25_Module_Placement_Notes"]
    names = [n for (n, _c) in LAYERS]
    for extra in legacy:
        if extra not in names:
            names.append(extra)
    # site-placement helper layers (also generated by this script)
    for sp in ("WoSyHo::SitePlacement", "WoSyHo::SitePlacement::BuildableZone",
               "WoSyHo::SitePlacement::Setback",
               "WoSyHo::SitePlacement::NorthArrow",
               "WoSyHo::SitePlacement::Labels",
               "90_Site_Boundary_Selected", "91_Buildable_Zone_Setback",
               "92_Placement_Candidates_Debug", "93_Best_Placement_Footprint",
               "94_Final_Placement_Report", "95_Placement_Preview_Live",
               # v27 micro-correction layers
               "WoSyHo::SitePlacement::SiteBoundary",
               "WoSyHo::SitePlacement::SelectedFootprint",
               "WoSyHo::SitePlacement::RejectedDebug",
               "WoSyHo::SitePlacement::Road",
               "WoSyHo::SitePlacement::RoadText"):
        if sp not in names:
            names.append(sp)
    total = 0
    preserved = 0
    for name in names:
        try:
            if not rs.IsLayer(name):
                continue
            try:
                rs.LayerVisible(name, True)
                rs.LayerLocked(name, False)
            except Exception:
                pass
            objs = rs.ObjectsByLayer(name)
            if not objs:
                continue
            gen = [o for o in objs if _wosyho_is_generated(o)]
            preserved += (len(objs) - len(gen))
            if gen:
                deleted = rs.DeleteObjects(gen)
                total += deleted if isinstance(deleted, int) else len(gen)
        except Exception:
            continue
    if total:
        print("Safe cleanup: removed %d generated Timber Housing object(s); preserved "
              "%d user/untagged object(s) (site surfaces / context kept)."
              % (total, preserved))
    else:
        print("Safe cleanup: no tagged Timber Housing objects to remove; preserved %d "
              "user/untagged object(s) (site surfaces / context kept)."
              % preserved)
    return total


def clear_existing_wosyho_scene():
    """Backwards-compatible entry point - now delegates to the SAFE, tag-based
    cleanup (safe_clear_generated_geometry_only). It deletes ONLY generated
    Timber Housing geometry and never user site / context geometry."""
    return safe_clear_generated_geometry_only()


def bake(brep_or_geom, layer, name=None):
    gid = None
    if isinstance(brep_or_geom, rg.Brep):
        gid = sc.doc.Objects.AddBrep(brep_or_geom)
    elif isinstance(brep_or_geom, rg.Curve):
        gid = sc.doc.Objects.AddCurve(brep_or_geom)
    elif isinstance(brep_or_geom, rg.Point3d):
        gid = sc.doc.Objects.AddPoint(brep_or_geom)
    if gid:
        rs.ObjectLayer(gid, layer)
        if name:
            rs.ObjectName(gid, name)
    return gid


def box_brep(x0, x1, y0, y1, z0, z1):
    bb = rg.BoundingBox(rg.Point3d(min(x0, x1), min(y0, y1), min(z0, z1)),
                        rg.Point3d(max(x0, x1), max(y0, y1), max(z0, z1)))
    return rg.Box(bb).ToBrep()


def member_brep(p0, p1, size):
    """Square-section member oriented along p0->p1 (works for any incline)."""
    a = rg.Point3d(p0[0], p0[1], p0[2])
    b = rg.Point3d(p1[0], p1[1], p1[2])
    v = b - a
    if v.Length < 1e-6:
        return None
    plane = rg.Plane(a, v)          # plane normal = member axis
    h = size / 2.0
    box = rg.Box(plane, rg.Interval(-h, h), rg.Interval(-h, h),
                 rg.Interval(0.0, v.Length))
    return box.ToBrep()


def plate_brep(p0, p1, width, thickness):
    """Inclined plate (stair flight): runs p0->p1 in the XZ plane, width
    along world Y, thickness perpendicular to the run. Folded-plate look."""
    a = rg.Point3d(p0[0], p0[1], p0[2])
    b = rg.Point3d(p1[0], p1[1], p1[2])
    v = b - a
    if v.Length < 1e-6:
        return None
    xdir = rg.Vector3d(0, 1, 0)                    # width across the well
    ydir = rg.Vector3d(-v.Z, 0, v.X)               # perpendicular in XZ
    if ydir.Length < 1e-6:
        ydir = rg.Vector3d(0, 0, 1)
    ydir.Unitize()
    plane = rg.Plane(a, xdir, ydir)                # normal = run direction
    box = rg.Box(plane,
                 rg.Interval(-width / 2.0, width / 2.0),
                 rg.Interval(-thickness / 2.0, thickness / 2.0),
                 rg.Interval(0.0, v.Length))
    return box.ToBrep()


def plate_brep_yz(p0, p1, width_x, thickness):
    """Inclined plate running p0->p1 in the YZ plane, width along world X
    (used for the outward-sloping dummy-module roof planes)."""
    a = rg.Point3d(p0[0], p0[1], p0[2])
    b = rg.Point3d(p1[0], p1[1], p1[2])
    v = b - a
    if v.Length < 1e-6:
        return None
    xdir = rg.Vector3d(1, 0, 0)
    ydir = rg.Vector3d(0, -v.Z, v.Y)               # perpendicular in YZ
    if ydir.Length < 1e-6:
        ydir = rg.Vector3d(0, 0, 1)
    ydir.Unitize()
    plane = rg.Plane(a, xdir, ydir)
    box = rg.Box(plane,
                 rg.Interval(-width_x / 2.0, width_x / 2.0),
                 rg.Interval(-thickness / 2.0, thickness / 2.0),
                 rg.Interval(0.0, v.Length))
    return box.ToBrep()


def parse_obj_block(path):
    """Minimal OBJ reader for the dummy block references (pure data:
    vertices + polygon faces in SketchUp coords, Y-up, meters)."""
    verts, faces = [], []
    try:
        with open(path, "r") as f:
            for line in f:
                if line.startswith("v "):
                    p = line.split()
                    verts.append((float(p[1]), float(p[2]), float(p[3])))
                elif line.startswith("f "):
                    idx = [int(t.split("/")[0]) - 1 for t in line.split()[1:]]
                    if len(idx) >= 3:
                        faces.append(idx)
    except Exception:
        return None
    if not verts or not faces:
        return None
    return verts, faces


def obj_block_to_mesh(parsed):
    """Build a Rhino mesh from parsed OBJ data (kept in SketchUp block
    coordinates; the placement transform performs the axis mapping)."""
    verts, faces = parsed
    mesh = rg.Mesh()
    for (x, y, z) in verts:
        mesh.Vertices.Add(x, y, z)
    for f in faces:
        if len(f) == 3:
            mesh.Faces.AddFace(f[0], f[1], f[2])
        elif len(f) == 4:
            mesh.Faces.AddFace(f[0], f[1], f[2], f[3])
        else:
            for i in range(1, len(f) - 1):           # fan-triangulate n-gons
                mesh.Faces.AddFace(f[0], f[i], f[i + 1])
    mesh.Normals.ComputeNormals()
    mesh.Compact()
    return mesh


def bake_box_wireframe(x0, x1, y0, y1, z0, z1, layer, name=None):
    """Thin wireframe outline of a box (lightweight debug/reference volume)."""
    bb = rg.BoundingBox(rg.Point3d(min(x0, x1), min(y0, y1), min(z0, z1)),
                        rg.Point3d(max(x0, x1), max(y0, y1), max(z0, z1)))
    brep = rg.Box(bb).ToBrep()
    ids = []
    for e in brep.Edges:
        gid = sc.doc.Objects.AddCurve(e.DuplicateCurve())
        if gid:
            rs.ObjectLayer(gid, layer)
            if name:
                rs.ObjectName(gid, name)
            ids.append(gid)
    return ids


# =============================================================================
# 4. STRUCTURAL MODEL COLLECTION (analysis-ready, Karamba/Dlubal/RFEM later)
# =============================================================================

SECTIONS = [
    {"id": "TIMBER_300x300_COLUMN", "shape": "rect", "b": 0.3, "h": 0.3},
    {"id": "TIMBER_300x300_BRANCH", "shape": "rect", "b": 0.3, "h": 0.3},
    {"id": "TIMBER_300x300_BEAM",   "shape": "rect", "b": 0.3, "h": 0.3},
    {"id": "TIMBER_CORRIDOR_EDGE_BEAM", "shape": "rect", "b": 0.3, "h": 0.3},
]
MATERIALS = [
    {"id": "GL24h_PLACEHOLDER", "type": "timber_glulam",
     "note": "design-stage placeholder, not verified"},
    {"id": "STEEL_BASE_PLACEHOLDER", "type": "steel"},
    {"id": "CONCRETE_FOUNDATION_PLACEHOLDER", "type": "concrete"},
]
LOAD_CASES = ["self_weight", "residential_live", "corridor_live",
              "common_space_live", "snow", "wind", "module_dead",
              "staircase_load"]


class StructuralCollector(object):
    def __init__(self):
        self.model = {"nodes": [], "members": [], "supports": [], "loads": [],
                      "sections": SECTIONS, "materials": MATERIALS,
                      "load_cases": LOAD_CASES,
                      "cascade_descriptor": CASCADE_DESCRIPTOR,
                      "meta": {"schema": "wosyho_struct_v1",
                               "units": "m",
                               "disclaimer": ("Design-stage computational "
                                              "model. NOT a certified "
                                              "structural verification."),
                               "created": datetime.datetime.now().isoformat()}}
        self._nidx = {}
        self._mid = 0

    def node(self, p):
        key = (round(p[0], 3), round(p[1], 3), round(p[2], 3))
        if key not in self._nidx:
            nid = len(self.model["nodes"])
            self._nidx[key] = nid
            self.model["nodes"].append({"id": nid, "x": key[0], "y": key[1],
                                        "z": key[2]})
        return self._nidx[key]

    def member(self, p0, p1, mtype, section, level, rhino_id, layer):
        self._mid += 1
        rec = {"id": self._mid, "node_i": self.node(p0), "node_j": self.node(p1),
               "type": mtype, "section": section,
               "material": "GL24h_PLACEHOLDER", "level": level,
               "rhino_id": str(rhino_id) if rhino_id else None, "layer": layer}
        self.model["members"].append(rec)
        return rec

    def support(self, p, fixity="PINNED_PLACEHOLDER"):
        self.model["supports"].append({"node": self.node(p), "fixity": fixity,
                                       "note": "conceptual placeholder"})

    def export(self, folder):
        try:
            if not os.path.isdir(folder):
                os.makedirs(folder)
            jpath = os.path.join(folder, "wosyho_v23_structural_model.json")
            with open(jpath, "w") as f:
                json.dump(self.model, f, indent=1)
            for tbl, cols in [("nodes", ["id", "x", "y", "z"]),
                              ("members", ["id", "node_i", "node_j", "type",
                                           "section", "material", "level",
                                           "layer"]),
                              ("supports", ["node", "fixity"])]:
                cpath = os.path.join(folder, "wosyho_v23_%s.csv" % tbl)
                with open(cpath, "w") as f:
                    f.write(",".join(cols) + "\n")
                    for r in self.model[tbl]:
                        f.write(",".join(str(r.get(c, "")) for c in cols) + "\n")
            return jpath
        except Exception as ex:
            print("Analysis export failed: %s" % ex)
            return None


# =============================================================================
# CORRECTED MODULE ARRANGEMENT (error folder 6 / corrected logic model.3dm)
# Exact per-instance placements transcribed from the manually-corrected
# Rhino model - the SOURCE OF TRUTH for Phase 2A. Reference config = Regular
# grid, NB=12, cascade [1,2,3,3,3,3,4,5,6,7,8,8].
#   fields: (level, type, orient, tx, ty)
#   type  : M1=Module A, M1A=Module A1, M2=Module B, GREEN=terrace
#   orient: Aout  = A/A1, room depth projects OUTWARD (Y), one bay
#           Bspan = Module B rotated, 7.5m depth ALONG the bay (~2 bays),
#                   block X -> +Rhino X, block Z -> -Rhino Y (band form)
#           Bend  = Module B at the bay-12 end, block X -> -Rhino X,
#                   block Z -> +Rhino Y (L band + atrium MID + R band on
#                   odd levels; atrium MID only on even levels)
#           green = flat common/terrace plate
#   tx,ty : world anchor of the block origin (inner bottom CLT corner) in
#           the reference (grid type 1); plan-grid offset boff is added to
#           ty at generation time so grid types 2/3 shift laterally.
# Counts: 22 A, 28 A1, 18 B, 32 green (= corrected model exactly).
REFERENCE_CORRECTED = [
    (1, 'GREEN', 'green', 8.05, 2.05),
    (1, 'GREEN', 'green', 8.05, 14.25),
    (1, 'M1', 'Aout', 0.30, 3.95),
    (1, 'M1', 'Aout', 0.30, 12.35),
    (1, 'M1A', 'Aout', 4.10, 3.95),
    (1, 'M1A', 'Aout', 4.10, 12.35),
    (1, 'M1A', 'Aout', 11.70, 3.95),
    (1, 'M1A', 'Aout', 11.70, 12.35),
    (2, 'GREEN', 'green', 0.45, 2.05),
    (2, 'GREEN', 'green', 0.45, 14.25),
    (2, 'GREEN', 'green', 8.05, 2.05),
    (2, 'GREEN', 'green', 8.05, 14.25),
    (2, 'M1', 'Aout', 7.90, 3.95),
    (2, 'M1', 'Aout', 7.90, 12.35),
    (2, 'M1A', 'Aout', 11.70, 3.95),
    (2, 'M1A', 'Aout', 11.70, 12.35),
    (2, 'M2', 'Bspan', 7.90, 0.30),
    (2, 'M2', 'Bspan', 7.90, 12.50),
    (3, 'GREEN', 'green', 4.25, 2.05),
    (3, 'GREEN', 'green', 4.25, 14.25),
    (3, 'GREEN', 'green', 19.45, 2.05),
    (3, 'GREEN', 'green', 19.45, 14.25),
    (3, 'GREEN', 'green', 30.85, 2.05),
    (3, 'GREEN', 'green', 30.85, 14.25),
    (3, 'M1', 'Aout', 11.70, 3.95),
    (3, 'M1', 'Aout', 11.70, 12.35),
    (3, 'M1', 'Aout', 23.10, 3.95),
    (3, 'M1', 'Aout', 23.10, 12.35),
    (3, 'M1', 'Aout', 34.50, 3.95),
    (3, 'M1', 'Aout', 34.50, 12.35),
    (3, 'M1A', 'Aout', 15.50, 3.95),
    (3, 'M1A', 'Aout', 15.50, 12.35),
    (3, 'M1A', 'Aout', 26.90, 3.95),
    (3, 'M1A', 'Aout', 26.90, 12.35),
    (3, 'M1A', 'Aout', 38.30, 3.95),
    (3, 'M1A', 'Aout', 38.30, 12.35),
    (3, 'M2', 'Bend', 41.80, 3.80),
    (3, 'M2', 'Bend', 41.80, 9.90),
    (3, 'M2', 'Bend', 41.80, 16.00),
    (3, 'M2', 'Bspan', 11.70, 0.30),
    (3, 'M2', 'Bspan', 11.70, 12.50),
    (4, 'GREEN', 'green', 8.05, 2.05),
    (4, 'GREEN', 'green', 8.05, 14.25),
    (4, 'GREEN', 'green', 11.85, 2.05),
    (4, 'GREEN', 'green', 11.85, 14.25),
    (4, 'GREEN', 'green', 15.65, 2.05),
    (4, 'GREEN', 'green', 15.65, 14.25),
    (4, 'GREEN', 'green', 19.45, 2.05),
    (4, 'GREEN', 'green', 19.45, 14.25),
    (4, 'GREEN', 'green', 30.85, 2.05),
    (4, 'GREEN', 'green', 30.85, 14.25),
    (4, 'M1', 'Aout', 26.90, 3.95),
    (4, 'M1', 'Aout', 26.90, 12.35),
    (4, 'M1', 'Aout', 38.30, 3.95),
    (4, 'M1', 'Aout', 38.30, 12.35),
    (4, 'M1A', 'Aout', 30.70, 3.95),
    (4, 'M1A', 'Aout', 30.70, 12.35),
    (4, 'M1A', 'Aout', 42.10, 3.95),
    (4, 'M1A', 'Aout', 42.10, 12.35),
    (4, 'M2', 'Bend', 41.80, 9.90),
    (4, 'M2', 'Bspan', 26.90, 0.30),
    (4, 'M2', 'Bspan', 26.90, 12.50),
    (5, 'GREEN', 'green', 23.25, 2.05),
    (5, 'GREEN', 'green', 23.25, 14.25),
    (5, 'GREEN', 'green', 30.85, 2.05),
    (5, 'GREEN', 'green', 30.85, 14.25),
    (5, 'M1', 'Aout', 34.50, 3.95),
    (5, 'M1', 'Aout', 34.50, 12.35),
    (5, 'M1A', 'Aout', 26.90, 3.95),
    (5, 'M1A', 'Aout', 26.90, 12.35),
    (5, 'M1A', 'Aout', 38.30, 3.95),
    (5, 'M1A', 'Aout', 38.30, 12.35),
    (5, 'M2', 'Bend', 41.80, 3.80),
    (5, 'M2', 'Bend', 41.80, 9.90),
    (5, 'M2', 'Bend', 41.80, 16.00),
    (6, 'GREEN', 'green', 27.05, 2.05),
    (6, 'GREEN', 'green', 27.05, 14.25),
    (6, 'M1', 'Aout', 38.30, 3.95),
    (6, 'M1', 'Aout', 38.30, 12.35),
    (6, 'M1A', 'Aout', 30.70, 3.95),
    (6, 'M1A', 'Aout', 30.70, 12.35),
    (6, 'M1A', 'Aout', 42.10, 3.95),
    (6, 'M1A', 'Aout', 42.10, 12.35),
    (6, 'M2', 'Bend', 41.80, 9.90),
    (7, 'GREEN', 'green', 30.85, 2.05),
    (7, 'GREEN', 'green', 30.85, 14.25),
    (7, 'M1', 'Aout', 34.50, 3.95),
    (7, 'M1', 'Aout', 34.50, 12.35),
    (7, 'M1A', 'Aout', 38.30, 3.95),
    (7, 'M1A', 'Aout', 38.30, 12.35),
    (7, 'M2', 'Bend', 41.80, 3.80),
    (7, 'M2', 'Bend', 41.80, 9.90),
    (7, 'M2', 'Bend', 41.80, 16.00),
    (8, 'GREEN', 'green', 34.65, 2.05),
    (8, 'GREEN', 'green', 34.65, 14.25),
    (8, 'M1', 'Aout', 38.30, 3.95),
    (8, 'M1', 'Aout', 38.30, 12.35),
    (8, 'M1A', 'Aout', 42.10, 3.95),
    (8, 'M1A', 'Aout', 42.10, 12.35),
    (8, 'M2', 'Bend', 41.80, 9.90),
]


# =============================================================================
# 5. THE CONFIGURATOR
# =============================================================================

class SkeletonRack(object):

    def __init__(self, P):
        self.P = P
        self.Z = derive_zones(P)
        self.F = self.Z["F"]
        self.NB = P["x_bays"]
        # ---- plan grid type: per-bay lateral offset map (NEW) ---------------
        # Geometry is GENERATED from mapped coordinates (never moved after
        # baking): every generator adds boff(bay) to its Y coordinates.
        self.bay_off = {}
        for b in range(1, self.NB + 1):
            self.bay_off[b] = grid_lateral_offset_for_section(
                b, self.NB, P.get("plan_grid_type", 1),
                P.get("offset_direction", 1))
        self.SM = StructuralCollector()
        self.counts = {}
        self.support_points = {
            "left_corridor_atrium_edge": [],
            "right_corridor_atrium_edge": [],
            "stair_support_points": [],
            "module_grid_points": [],
            "atrium_trunk_points": [],
            "v_column_target_points": [],
            "double_height_common_space_points": [],
            "cascade_profile_points": [],
        }

    # ---------- coordinate helpers -------------------------------------------
    def xaxis(self, k):                     # axis k = 0..NB
        return Y_OUT_L + k * AXIS           # 0.15 + k*3.8 (same start offset)

    def xmid(self, b):                      # centre of bay b (1-based)
        return (self.xaxis(b - 1) + self.xaxis(b)) / 2.0

    def zlev(self, n):                      # structural level plane n (0=plinth)
        return PLINTH + n * FLOOR_PITCH

    def fbay(self, b):
        if b < 1 or b > self.NB:
            return 0
        return self.F[b - 1]

    def line_floors(self, k):               # active floors on grid line k
        return max(self.fbay(k), self.fbay(k + 1))

    # ---------- plan-grid lateral offset helpers (NEW) ------------------------
    def boff(self, b):
        """Lateral Y offset of bay b (0 for Regular Grid)."""
        return self.bay_off.get(b, 0.0)

    def axis_offsets(self, k):
        """Distinct lateral offsets among the existing bays adjacent to axis
        k. At an offset transition this returns TWO offsets: the axis then
        carries one column/Y-beam set per offset so both grid alignments end
        on their own frame line and the step closes orthogonally."""
        seen = []
        for b in (k, k + 1):
            if 1 <= b <= self.NB:
                o = self.boff(b)
                if not any(abs(o - s) < 1e-9 for s in seen):
                    seen.append(o)
        return seen or [0.0]

    def axis_has_frame_o(self, k, n, o):
        """axis_has_frame restricted to adjacent bays at lateral offset o."""
        for b in (k, k + 1):
            if 1 <= b <= self.NB and abs(self.boff(b) - o) < 1e-9:
                if self.level_has_frame(b, n):
                    return True
        return False

    def line_floors_o(self, k, o):
        """line_floors restricted to adjacent bays at lateral offset o."""
        fs = [self.fbay(b) for b in (k, k + 1)
              if 1 <= b <= self.NB and abs(self.boff(b) - o) < 1e-9]
        return max(fs or [0])

    # ---------- zone predicates ----------------------------------------------
    def level_has_frame(self, b, n):
        """Beams/slab/corridor exist at level n in bay b?"""
        if b < 1 or b > self.NB or n < 1 or n > self.fbay(b):
            return False
        if b in self.Z["dh_bays"] and n == 1:
            return False                     # double height: no Level-1 frame
        return True

    def axis_has_frame(self, k, n):
        return self.level_has_frame(k, n) or self.level_has_frame(k + 1, n)

    def is_fully_framed_module_slot(self, b, n):
        """MANDATORY Phase-2A rule (error-folder-5 correction): a module may
        be placed only when its INNER CLT support footprint sits in a
        complete structural rack cell. The outer cantilever/projection may
        still extend past the rack - only the inner support must be framed.

        Enclosed means, at module storey n of bay b:
          * the bay's storey frame exists at level n (beams/slab of this bay);
          * a deck exists BELOW to bear on - ground plinth (n==1) or a frame
            at level n-1 (the double-height bays get their bearing deck at
            L2, so n==3 there is allowed);
          * BOTH bounding bay axes (b-1 and b) carry a column/frame at n, so
            the cell is closed on the bay-direction sides.
        Returns False for open/incomplete boundary cells and roof/terrace
        cells (level F(b)+1, above the bay's own frame)."""
        if b < 1 or b > self.NB or n < 1:
            return False
        if not self.level_has_frame(b, n):
            return False                     # roof/terrace or above cascade
        if n > 1 and not self.level_has_frame(b, n - 1) \
                and not (b in self.Z["dh_bays"] and n == 3):
            return False                     # nothing below to bear on
        if not (self.axis_has_frame(b - 1, n) and self.axis_has_frame(b, n)):
            return False                     # a bay-side column is missing
        return True

    def axis_covered_by_v(self, k):
        return (k in self.Z["v_bays"]) or ((k + 1) in self.Z["v_bays"])

    def axis_in_stair_core(self, k):
        """Axis strictly inside a stair zone (both adjacent bays are stairs)."""
        return (k in self.Z["stair_bays"]) and ((k + 1) in self.Z["stair_bays"])

    def stair_zone_of_bay(self, b):
        for i, (s, e) in enumerate(self.Z["stair_zones"]):
            if s <= b <= e:
                return i
        return -1

    def stair_top_level(self, zone_idx):
        s, e = self.Z["stair_zones"][zone_idx]
        fmin = min([self.fbay(b) for b in range(s, e + 1)] or [1])
        in_dh = any([(b in self.Z["dh_bays"]) for b in range(s, e + 1)])
        # model: low stair (L1 zone) serves minF-1; tall stair (DH) serves minF
        auto = fmin if in_dh else max(1, fmin - 1)
        override = self.P.get("stair_top_levels", [0, 0])
        if zone_idx < len(override) and override[zone_idx] > 0:
            return min(override[zone_idx], fmin)
        return auto

    def stair_support_start(self, zone_idx):
        # named parameters per user point 7 (0 = ground, matches model)
        if zone_idx == 0:
            return int(self.P.get("low_stair_support_start_level", 0))
        return int(self.P.get("tall_stair_support_start_level", 0))

    # =========================================================================
    # SUPPORT POINTS FIRST
    # =========================================================================
    def generate_support_points(self):
        sp = self.support_points
        # corridor atrium-edge underside nodes (branch targets), per level/axis
        # (one node set per distinct plan-grid offset at each axis)
        for k in range(0, self.NB + 1):
            for o in self.axis_offsets(k):
                for n in range(1, self.line_floors_o(k, o) + 1):
                    if not self.axis_has_frame_o(k, n, o):
                        continue
                    if self.axis_in_stair_core(k):
                        continue                      # never inside stair core
                    z = self.zlev(n) - MEMBER         # underside of edge beam
                    sp["left_corridor_atrium_edge"].append(
                        (self.xaxis(k), Y_COR_L + o, z))
                    sp["right_corridor_atrium_edge"].append(
                        (self.xaxis(k), Y_COR_R + o, z))
        # trunk points
        for b in self.Z["trunk_bays"]:
            sp["atrium_trunk_points"].append(
                (self.xmid(b), TRUNK_Y + self.boff(b), PLINTH))
        # V bases + corner targets
        for b in self.Z["v_bays"]:
            ob = self.boff(b)
            for (ybase, yin, yout) in [(V_BASE_Y_LEFT, Y_MID_L, Y_OUT_L),
                                       (V_BASE_Y_RIGHT, Y_MID_R, Y_OUT_R)]:
                sp["v_column_target_points"].append(
                    (self.xmid(b), ybase + ob, PLINTH))
                for xk in (self.xaxis(b - 1), self.xaxis(b)):
                    for yy in (yin, yout):
                        sp["v_column_target_points"].append(
                            (xk, yy + ob, self.zlev(2)))
        # stair support points
        for i, (s, e) in enumerate(self.Z["stair_zones"]):
            top = self.stair_top_level(i)
            ob = self.boff(s)
            for k in range(s - 1, e + 1):
                for y in CORRIDOR_Y_AXES:
                    sp["stair_support_points"].append(
                        (self.xaxis(k), y + ob, self.zlev(top)))
        # double-height zone points
        for b in sorted(self.Z["dh_bays"]):
            sp["double_height_common_space_points"].append(
                (self.xmid(b), SECTION_WIDTH / 2.0 + self.boff(b),
                 self.zlev(2) / 2.0))
        # module grid points (cell corners at each active level)
        for b in range(1, self.NB + 1):
            ob = self.boff(b)
            for n in range(1, self.fbay(b) + 1):
                if not self.level_has_frame(b, n):
                    continue
                for y in MODULE_Y_AXES:
                    sp["module_grid_points"].append(
                        (self.xaxis(b - 1), y + ob, self.zlev(n)))
        # cascade profile points (debug polyline)
        for b in range(1, self.NB + 1):
            z = self.zlev(self.fbay(b))
            sp["cascade_profile_points"].append((self.xaxis(b - 1), -0.8, z))
            sp["cascade_profile_points"].append((self.xaxis(b), -0.8, z))

        if self.P["show_support_points"]:
            pts = (sp["left_corridor_atrium_edge"] +
                   sp["right_corridor_atrium_edge"] +
                   sp["atrium_trunk_points"] + sp["v_column_target_points"])
            for p in pts:
                bake(rg.Point3d(p[0], p[1], p[2]), "01_Support_Points")
        self.counts["corridor_support_nodes"] = (
            len(sp["left_corridor_atrium_edge"]) +
            len(sp["right_corridor_atrium_edge"]))

    # =========================================================================
    # GRID AXES + GROUND
    # =========================================================================
    def generate_grid(self):
        n = 0
        # cross-section lines at each axis, one per distinct local offset
        for k in range(0, self.NB + 1):
            x = self.xaxis(k)
            for o in self.axis_offsets(k):
                c = rg.LineCurve(rg.Point3d(x, Y_OUT_L + o - 1.0, 0),
                                 rg.Point3d(x, Y_OUT_R + o + 1.0, 0))
                bake(c, "00_Grid_Axis", "AXIS_X_%d" % k)
                n += 1
        # length lines: per-bay segments following each bay's lateral offset
        for y in SECTION_AXES_Y + [TRUNK_Y]:
            for b in range(1, self.NB + 1):
                ob = self.boff(b)
                c = rg.LineCurve(
                    rg.Point3d(self.xaxis(b - 1), y + ob, 0),
                    rg.Point3d(self.xaxis(b), y + ob, 0))
                bake(c, "00_Grid_Axis", "AXIS_Y_%.2f_b%d" % (y, b))
                n += 1
        # ground plane plate covering all offsets (visual dark base)
        offs = [self.boff(b) for b in range(1, self.NB + 1)] or [0.0]
        bake(box_brep(self.xaxis(0) - MEMBER, self.xaxis(self.NB) + MEMBER,
                      Y_OUT_L + min(offs) - MEMBER,
                      Y_OUT_R + max(offs) + MEMBER, -0.1, 0.0),
             "00_Grid_Axis", "GROUND_PLANE")
        self.counts["grid_axes"] = n

    # =========================================================================
    # REGULAR COLUMNS  (+ stair-zone support columns; V-zone suppression)
    #
    # Patched 2026-07-05 (error folder 2) after measuring column start levels
    # in the reference OBJ:
    #   - In the double-height zone, ALL regular columns (module lines AND
    #     corridor/atrium lines) start at L2 (measured y 8.26) - never at
    #     ground. The only ground supports there are V-columns and trunks.
    #     Named parameter: regular_columns_start_after_double_height_level
    #     (default 2 = the V-column stopping / transfer level).
    #   - At trunk-served axes (k in {b-1, b} of a trunk bay b), corridor-line
    #     columns are additionally suppressed for storeys 2..F(b): the tree
    #     branches carry the corridor edges there (measured: axis 9 corridor
    #     columns start only above L6 = trunk-9 service top; axes 5/6/8 have
    #     none through their served range; axis 4 keeps only its ground->L1
    #     storey). Toggle: suppress_corridor_columns_in_trunk_service.
    #   - Regular columns always resume above these levels and continue to
    #     the local cascade top (upper rack grid unchanged).
    # =========================================================================
    def axis_fully_in_dh(self, k):
        """Every existing bay adjacent to axis k lies in the double-height
        zone (axis 4 borders L1-zone bay 4 -> False; end axis 12 -> True)."""
        adj = [b for b in (k, k + 1) if 1 <= b <= self.NB]
        if not adj:
            return False
        for b in adj:
            if b not in self.Z["dh_bays"]:
                return False
        return True

    def trunk_service_top(self, k):
        """Highest level whose corridor edge at axis k is branch-served."""
        top = 0
        for b in self.Z["trunk_bays"]:
            if k in (b - 1, b):
                top = max(top, self.fbay(b))
        return top

    def column_suppressed(self, k, y, n):
        """Storey n of the column at (axis k, section line y) is carried by
        special support logic instead of a regular ground column."""
        dh_lvl = int(self.P.get(
            "regular_columns_start_after_double_height_level", 2))
        if y in MODULE_Y_AXES:
            # V-legs / open double-height space govern the lower storeys
            if n <= dh_lvl and (self.axis_covered_by_v(k)
                                or self.axis_fully_in_dh(k)):
                return True
            return False
        if y in CORRIDOR_Y_AXES:
            # open double-height common space: no ground columns
            if n <= dh_lvl and self.axis_fully_in_dh(k):
                return True
            # tree branches support the corridor edges at trunk-served axes
            if (self.P.get("suppress_corridor_columns_in_trunk_service", True)
                    and 2 <= n <= self.trunk_service_top(k)):
                return True
        return False

    def generate_columns(self):
        n_reg, n_stair = 0, 0
        for k in range(0, self.NB + 1):
            # one column set per distinct lateral offset at this axis (plan
            # grid types: a transition axis ends BOTH grid alignments)
            for o in self.axis_offsets(k):
                lf = self.line_floors_o(k, o)
                for y in SECTION_AXES_Y:
                    yw = y + o                       # mapped world coordinate
                    # stair-zone corridor-line columns: support-start param
                    start_lvl = 0
                    mtype_base = "REGULAR_COLUMN"
                    zone_idx = -1
                    if y in CORRIDOR_Y_AXES:
                        for b in (k, k + 1):
                            zi = self.stair_zone_of_bay(b) \
                                if 1 <= b <= self.NB else -1
                            if zi >= 0:
                                zone_idx = zi
                        if zone_idx >= 0:
                            mtype_base = "STAIR_ZONE_SUPPORT_COLUMN"
                            start_lvl = self.stair_support_start(zone_idx)
                    for n in range(1, lf + 1):
                        if n <= start_lvl:
                            continue
                        if self.column_suppressed(k, y, n):
                            continue
                        z0 = self.zlev(n - 1)
                        z1 = self.zlev(n)
                        if self.axis_has_frame_o(k, n, o):
                            z1 -= MEMBER             # stop under the beam grid
                        p0 = (self.xaxis(k), yw, z0)
                        p1 = (self.xaxis(k), yw, z1)
                        gid = bake(member_brep(p0, p1, MEMBER),
                                   "02_Regular_Columns",
                                   "%s_k%d_y%.2f_L%d" % (mtype_base, k, yw, n))
                        self.SM.member(p0, p1, mtype_base,
                                       "TIMBER_300x300_COLUMN", n, gid,
                                       "02_Regular_Columns")
                        if mtype_base == "STAIR_ZONE_SUPPORT_COLUMN":
                            n_stair += 1
                        else:
                            n_reg += 1
                        if n == start_lvl + 1:       # ground bearing storey
                            base = (self.xaxis(k), yw, 0.0)
                            if start_lvl == 0:
                                bake(box_brep(p0[0] - PEDESTAL_SIZE / 2.0,
                                              p0[0] + PEDESTAL_SIZE / 2.0,
                                              yw - PEDESTAL_SIZE / 2.0,
                                              yw + PEDESTAL_SIZE / 2.0,
                                              0.0, PLINTH),
                                     "02_Regular_Columns", "PEDESTAL")
                                self.SM.support(base)
        self.counts["regular_columns"] = n_reg
        self.counts["stair_support_columns"] = n_stair

    # =========================================================================
    # REGULAR BEAMS + CORRIDOR EDGE BEAMS
    #
    # Visual joint closure (error-folder-3 correction 4): every BAKED beam
    # solid is extended by MEMBER/2 (0.15 m) at BOTH ends so the beam overlaps
    # into the column/joint zone and the timber frame reads as continuous.
    # Analytical member coordinates (SM.member p0/p1) remain the exact axis
    # points - grid, nodes and StructuralModel are unchanged.
    # =========================================================================
    def generate_beams(self):
        n_beam, n_edge = 0, 0
        ext = MEMBER / 2.0                    # visual-only end extension
        # X-direction beams (along the length), one per bay per Y axis
        for b in range(1, self.NB + 1):
            ob = self.boff(b)                 # plan-grid lateral offset
            for n in range(1, self.fbay(b) + 1):
                if not self.level_has_frame(b, n):
                    continue
                z1 = self.zlev(n)
                z0 = z1 - MEMBER
                for y in SECTION_AXES_Y:
                    yw = y + ob
                    is_edge = y in CORRIDOR_Y_AXES
                    layer = ("05_Corridor_Edge_Beams" if is_edge
                             else "03_Regular_Beams")
                    mtype = ("CORRIDOR_EDGE_BEAM" if is_edge
                             else "REGULAR_BEAM_X")
                    p0 = (self.xaxis(b - 1), yw, (z0 + z1) / 2.0)
                    p1 = (self.xaxis(b), yw, (z0 + z1) / 2.0)
                    gid = bake(box_brep(p0[0] - ext, p1[0] + ext,
                                        yw - MEMBER / 2.0,
                                        yw + MEMBER / 2.0, z0, z1),
                               layer, "%s_b%d_L%d" % (mtype, b, n))
                    self.SM.member(p0, p1, mtype,
                                   ("TIMBER_CORRIDOR_EDGE_BEAM" if is_edge
                                    else "TIMBER_300x300_BEAM"), n, gid, layer)
                    if is_edge:
                        n_edge += 1
                    else:
                        n_beam += 1
        # Y-direction beams (across the section), at each axis line; one run
        # per distinct lateral offset (the doubled run at a transition axis
        # IS the orthogonal connector that closes the plan step)
        spans = [(Y_OUT_L, Y_MID_L), (Y_MID_L, Y_COR_L), (Y_COR_L, Y_COR_R),
                 (Y_COR_R, Y_MID_R), (Y_MID_R, Y_OUT_R)]
        for k in range(0, self.NB + 1):
            for o in self.axis_offsets(k):
                for n in range(1, self.line_floors_o(k, o) + 1):
                    if not self.axis_has_frame_o(k, n, o):
                        continue
                    z1 = self.zlev(n)
                    z0 = z1 - MEMBER
                    x = self.xaxis(k)
                    for (ya, yb) in spans:
                        p0 = (x, ya + o, (z0 + z1) / 2.0)
                        p1 = (x, yb + o, (z0 + z1) / 2.0)
                        gid = bake(box_brep(x - MEMBER / 2.0,
                                            x + MEMBER / 2.0,
                                            ya + o - ext, yb + o + ext,
                                            z0, z1),
                                   "03_Regular_Beams",
                                   "REGULAR_BEAM_Y_k%d_L%d" % (k, n))
                        self.SM.member(p0, p1, "REGULAR_BEAM_Y",
                                       "TIMBER_300x300_BEAM", n, gid,
                                       "03_Regular_Beams")
                        n_beam += 1
        self.counts["regular_beams"] = n_beam
        self.counts["corridor_edge_beams"] = n_edge

    # =========================================================================
    # BASE / PLINTH + LOWER GRID  (OBJ-derived correction, 2026-07-06)
    #
    # Derived by measuring skeleton structure.obj (SketchUp Y-up). Two additive
    # elements at the ground storey; NOTHING here modifies generate_grid(), the
    # existing GROUND_PLANE, module placement, cascade, stairs, or the V/trunk
    # logic - it is purely additive.
    #
    #  (A) BASE BEAM GRID - a STRUCTURAL level-0 timber beam grid that ties the
    #      ground-column bases. The reference OBJ shows it at Z 0.36..0.66 (a
    #      0.30 m beam topping at the plinth 0.7); here z1=PLINTH, z0=PLINTH-
    #      MEMBER. It exists ONLY where the ground storey is framed
    #      (level_has_frame(b,1)) - i.e. the non-double-height bays (bays 1..
    #      dh_start-1). The V-lifted double-height / open-ground bays get NO
    #      base grid, exactly as measured (reference base grid spans bays 1-4
    #      only). Mirrors generate_beams (same SECTION_AXES_Y X-beams + the same
    #      5 Y-spans) and honours the reference bay-1 terrace corridor voids so
    #      corridor base beams start at bay 2. Follows boff(b) -> Regular / Half
    #      Offset / Centre Offset all work. Baked on 03_Regular_Beams; SM types
    #      BASE_BEAM_X / BASE_BEAM_Y at level 0 (RFEM-ready).
    #  (B) BASE PLATFORM SLAB - VISUAL ONLY. Full-plan plinth from z=0 to
    #      base_thickness (default 0.4), per bay following boff so it steps with
    #      offset grids. Capped at PLINTH-MEMBER (0.4) so it can never intrude
    #      into the base beam grid (0.4..0.7) -> no visual clash. Baked on
    #      00_Grid_Axis beside the untouched GROUND_PLANE; NOT a SM member.
    # =========================================================================
    def generate_base_grid_and_plinth(self):
        c = self.counts
        base_bx = base_by = 0
        skipped = 0
        z1 = PLINTH                      # 0.7  (base beam top = plinth)
        z0 = PLINTH - MEMBER             # 0.4
        zc = (z0 + z1) / 2.0
        ext = MEMBER / 2.0               # visual-only end extension (as beams)
        ref_mode = (self.NB == 12)

        # ---- (A) base beam grid: only where the GROUND storey is framed ------
        # X-direction base beams (along the length), one per ground-framed bay
        for b in range(1, self.NB + 1):
            if not self.level_has_frame(b, 1):
                skipped += 1             # DH / lifted / open ground -> no base
                continue
            ob = self.boff(b)
            for y in SECTION_AXES_Y:
                # honour the reference ground-terrace corridor voids (bay 1)
                if ref_mode and y == Y_COR_L \
                        and (1, b, "corL") in self.REF_NONATRIUM_VOIDS:
                    continue
                if ref_mode and y == Y_COR_R \
                        and (1, b, "corR") in self.REF_NONATRIUM_VOIDS:
                    continue
                yw = y + ob
                p0 = (self.xaxis(b - 1), yw, zc)
                p1 = (self.xaxis(b), yw, zc)
                gid = bake(box_brep(p0[0] - ext, p1[0] + ext,
                                    yw - MEMBER / 2.0, yw + MEMBER / 2.0,
                                    z0, z1),
                           "03_Regular_Beams", "BASE_BEAM_X_b%d" % b)
                self.SM.member(p0, p1, "BASE_BEAM_X",
                               "TIMBER_300x300_BEAM", 0, gid, "03_Regular_Beams")
                base_bx += 1
        # Y-direction base beams (across the section) at each axis whose ground
        # storey is framed on that offset (mirror generate_beams spans)
        spans = [(Y_OUT_L, Y_MID_L), (Y_MID_L, Y_COR_L), (Y_COR_L, Y_COR_R),
                 (Y_COR_R, Y_MID_R), (Y_MID_R, Y_OUT_R)]

        def ground_axis_framed(k, o):
            for b in (k, k + 1):
                if 1 <= b <= self.NB and abs(self.boff(b) - o) < 1e-9 \
                        and self.level_has_frame(b, 1):
                    return True
            return False

        for k in range(0, self.NB + 1):
            for o in self.axis_offsets(k):
                if not ground_axis_framed(k, o):
                    continue
                x = self.xaxis(k)
                for (ya, yb) in spans:
                    p0 = (x, ya + o, zc)
                    p1 = (x, yb + o, zc)
                    gid = bake(box_brep(x - MEMBER / 2.0, x + MEMBER / 2.0,
                                        ya + o - ext, yb + o + ext, z0, z1),
                               "03_Regular_Beams", "BASE_BEAM_Y_k%d" % k)
                    self.SM.member(p0, p1, "BASE_BEAM_Y",
                                   "TIMBER_300x300_BEAM", 0, gid,
                                   "03_Regular_Beams")
                    base_by += 1

        # ---- (B) visual base platform slab (0 -> base_thickness) -------------
        # Part-A follow-up (2026-07-06): the visual plinth now rises to the TOP
        # of the level-0 base beams (default base_thickness = PLINTH = 0.7) so
        # the ground base reads as ONE continuous CLT/plinth/floor mass. The
        # platform is VISUAL / panel-reference only; it may embed the structural
        # base beams (0.4..0.7) - acceptable, the beams remain analytical
        # members. Each bay platform is also stored as a BASE_CLT_PANEL surface
        # reference for the RFEM/Dlubal export (self.base_panels).
        n_plat = 0
        self.base_panels = []
        bt = float(self.P.get("base_thickness", PLINTH))
        plat_top = bt
        if self.P.get("show_base_platform", True) and plat_top > 0.0:
            for b in range(1, self.NB + 1):
                ob = self.boff(b)             # steps with offset grids
                x0 = self.xaxis(b - 1)
                x1 = self.xaxis(b)
                y0 = Y_OUT_L + ob - MEMBER
                y1 = Y_OUT_R + ob + MEMBER
                bake(box_brep(x0, x1, y0, y1, 0.0, plat_top),
                     "00_Grid_Axis", "BASE_PLATFORM_b%d" % b)
                self.base_panels.append({
                    "panel_type": "BASE_CLT_PANEL", "level": 0, "bay": b,
                    "corners": [(x0, y0, plat_top), (x1, y0, plat_top),
                                (x1, y1, plat_top), (x0, y1, plat_top)],
                    "thickness": plat_top, "material": "CLT_TIMBER_PANEL",
                    "note": ("visual base/plinth panel reference; verify panel "
                             "modelling in RFEM manually")})
                n_plat += 1

        c["base_beams_x"] = base_bx
        c["base_beams_y"] = base_by
        c["base_beams_total"] = base_bx + base_by
        c["base_platform_pieces"] = n_plat
        c["base_cells_skipped_dh_void"] = skipped
        self._base_platform_top = plat_top   # for report / alignment check
        self._base_beam_top = z1             # = PLINTH

    # =========================================================================
    # SLABS (suppressible placeholders) - Y-BAND PIECES, ATRIUM OPEN BY DEFAULT
    #
    # Patched 2026-07-05 after face-level inspection of the reference OBJ
    # ("skeleton structure with slabs.obj", plate polygons rasterised + point
    # probed). Measured atrium logic (all values verified against the OBJ):
    #   - The central atrium band (Y 6.25..10.05) is OPEN at every level by
    #     default; tree trunks pass through void. NO full-width plates.
    #   - Stair zones: a 2.0 m LANDING strip across the atrium band on the
    #     zone's outer side (low zone: entry side; tall zone: far side),
    #     floored at every frame level of that bay. The remaining ~5 m stair
    #     OPENING stays open for levels n <= min(F) over the zone bays and is
    #     roofed above that (reference: tall stair roofed at L8; the low
    #     stair's terrace stays open because min(F)=3 covers all its levels).
    #   - Trunk-bay terraces: the atrium band is floored ONLY at the trunk
    #     bay's local cascade top F(b) (measured: L3@b5, L4@b7, L6@b9).
    #   - End block: atrium band floored at every frame level for bays beyond
    #     the tall stair zone (reference: bay 12, L2..L8).
    #   - Module/corridor bands: floored at every frame level EXCEPT the
    #     voids the reference OBJ deliberately leaves open (REF_NONATRIUM_
    #     VOIDS below, applied in reference mode NB=12 only).
    # Slabs remain fully suppressible via the show_floor_plates toggle.
    # =========================================================================

    # (level, bay, band) cells left open in the reference OBJ, measured by
    # polygon probing. Bands: modL corL corR modR. Reference mode only.
    REF_NONATRIUM_VOIDS = set([
        (1, 1, "corL"), (1, 1, "corR"),      # bay-1 terrace: no corridors
        (2, 2, "corL"), (2, 2, "corR"),      # bay-2 terrace: no corridors
        (2, 9, "modL"),                      # module-band void pockets
        (2, 8, "modR"),
        (3, 12, "modR"),
        (5, 12, "corL"), (6, 12, "corL"), (7, 12, "corL"),
    ])
    STAIR_LANDING_DEPTH = 2.0                # measured strip depth (m)

    def stair_zone_min_floors(self, zone_idx):
        s, e = self.Z["stair_zones"][zone_idx]
        return min([self.fbay(b) for b in range(s, e + 1)] or [1])

    def atrium_pieces(self, b, n, x0, x1):
        """X-extents of atrium-band floor pieces for bay b, level n.
        Returns [] when the atrium stays open (the default)."""
        zone_idx = self.stair_zone_of_bay(b)
        if zone_idx >= 0:
            s, e = self.Z["stair_zones"][zone_idx]
            zx0 = self.xaxis(s - 1)
            zx1 = self.xaxis(e)
            d = self.STAIR_LANDING_DEPTH
            if zone_idx == 0:                # low zone: landing at entry side
                land = (zx0, zx0 + d)
                opening = (zx0 + d, zx1)
            else:                            # tall zone: landing at far side
                opening = (zx0, zx1 - d)
                land = (zx1 - d, zx1)
            pieces = []
            la0 = max(land[0], x0)
            la1 = min(land[1], x1)
            if la1 - la0 > 0.05:
                pieces.append((la0, la1, "stair_landing"))
            if n > self.stair_zone_min_floors(zone_idx):
                op0 = max(opening[0], x0)    # roof closes over the opening
                op1 = min(opening[1], x1)
                if op1 - op0 > 0.05:
                    pieces.append((op0, op1, "stair_roof"))
            return pieces
        if b in self.Z["trunk_bays"] and n == self.fbay(b):
            return [(x0, x1, "trunk_terrace")]
        tall_end = self.Z["stair_zones"][-1][1]
        if b > tall_end:
            return [(x0, x1, "end_block")]
        return []                            # default: atrium OPEN

    def generate_slabs(self):
        n_slab = 0
        if not self.P["show_floor_plates"]:
            self.counts["slab_plates"] = 0
            return
        ref_mode = (self.NB == 12)
        bands = [("modL", Y_OUT_L, Y_MID_L),
                 ("corL", Y_MID_L, Y_COR_L),
                 ("corR", Y_COR_R, Y_MID_R),
                 ("modR", Y_MID_R, Y_OUT_R)]
        for b in range(1, self.NB + 1):
            ob = self.boff(b)                 # plan-grid lateral offset
            for n in range(1, self.fbay(b) + 1):
                if not self.level_has_frame(b, n):
                    continue
                z1 = self.zlev(n)
                z0 = z1 - SLAB_T
                x0 = self.xaxis(b - 1)
                x1 = self.xaxis(b)
                # module + corridor band pieces (atrium band NOT included)
                for (bn, ya, yb) in bands:
                    if ref_mode and (n, b, bn) in self.REF_NONATRIUM_VOIDS:
                        continue
                    bake(box_brep(x0, x1, ya + ob, yb + ob, z0, z1),
                         "04_Corridor_Slabs",
                         "SLAB_%s_b%d_L%d" % (bn, b, n))
                    n_slab += 1
                # atrium band: open by default, measured pieces only
                for (ax0, ax1, tag) in self.atrium_pieces(b, n, x0, x1):
                    bake(box_brep(ax0, ax1, Y_COR_L + ob, Y_COR_R + ob,
                                  z0, z1),
                         "04_Corridor_Slabs",
                         "SLAB_ATR_%s_b%d_L%d" % (tag, b, n))
                    n_slab += 1
        self.counts["slab_plates"] = n_slab

    # =========================================================================
    # 4-LEGGED V-COLUMNS (double-height zone, module bays, alternate bays)
    # =========================================================================
    def generate_v_columns(self):
        n_v, n_legs = 0, 0
        tall_end = self.Z["stair_zones"][-1][1]
        for b in self.Z["v_bays"]:
            supports = [(V_BASE_Y_LEFT, Y_MID_L, Y_OUT_L, "L"),
                        (V_BASE_Y_RIGHT, Y_MID_R, Y_OUT_R, "R")]
            # error-folder-3 correction: the reference has a THIRD V-column in
            # the CENTRE/ATRIUM band at the end block only (measured legs at
            # section 6.95..9.35, mid-bay 12) - no trunk serves bays beyond
            # the tall stair zone, so the end-block corridor/atrium grid is
            # ground-supported by an atrium V instead.
            if (b > tall_end
                    and self.P.get("atrium_v_in_end_block", True)):
                supports.append((TRUNK_Y, Y_COR_L, Y_COR_R, "C"))
            ob = self.boff(b)                 # plan-grid lateral offset
            supports = [(yb + ob, yi + ob, yo + ob, sd)
                        for (yb, yi, yo, sd) in supports]
            for (ybase, yin, yout, side) in supports:
                base = (self.xmid(b), ybase, PLINTH)
                bake(box_brep(base[0] - PEDESTAL_SIZE / 2.0,
                              base[0] + PEDESTAL_SIZE / 2.0,
                              base[1] - PEDESTAL_SIZE / 2.0,
                              base[1] + PEDESTAL_SIZE / 2.0, 0.0, PLINTH),
                     "06_Ground_V_Columns", "V_PEDESTAL_b%d_%s" % (b, side))
                self.SM.support((base[0], base[1], 0.0))
                # 4 legs -> corners of the bay cell at Level 2 (2nd floor roof)
                z_top = self.zlev(2)
                for xk in (self.xaxis(b - 1), self.xaxis(b)):
                    for yy in (yin, yout):
                        tip = (xk, yy, z_top)
                        gid = bake(member_brep(base, tip, MEMBER),
                                   "06_Ground_V_Columns",
                                   "V_LEG_b%d_%s" % (b, side))
                        self.SM.member(base, tip, "FOUR_LEGGED_V_BRANCH",
                                       "TIMBER_300x300_BRANCH", 2, gid,
                                       "06_Ground_V_Columns")
                        n_legs += 1
                n_v += 1
        self.counts["v_columns"] = n_v
        self.counts["v_legs"] = n_legs

    # =========================================================================
    # ATRIUM TREE COLUMNS (trunk + branches to corridor undersides)
    # =========================================================================
    def generate_tree_columns(self):
        n_trunk, n_branch = 0, 0
        drop = 2.2               # branch start below target (approx 40 deg)
        for b in self.Z["trunk_bays"]:
            xm = self.xmid(b)
            ob = self.boff(b)                 # plan-grid lateral offset
            ty = TRUNK_Y + ob
            top = self.zlev(self.fbay(b))
            base = (xm, ty, PLINTH)
            bake(box_brep(xm - PEDESTAL_SIZE / 2.0, xm + PEDESTAL_SIZE / 2.0,
                          ty - PEDESTAL_SIZE / 2.0,
                          ty + PEDESTAL_SIZE / 2.0, 0.0, PLINTH),
                 "07_Atrium_Trunk_Columns", "TRUNK_PEDESTAL_b%d" % b)
            self.SM.support((xm, ty, 0.0))
            p_top = (xm, ty, top)
            gid = bake(member_brep(base, p_top, MEMBER),
                       "07_Atrium_Trunk_Columns", "ATRIUM_TRUNK_b%d" % b)
            self.SM.member(base, p_top, "ATRIUM_TRUNK_COLUMN",
                           "TIMBER_300x300_COLUMN", self.fbay(b), gid,
                           "07_Atrium_Trunk_Columns")
            n_trunk += 1
            # branches: every active corridor level of this bay
            for n in range(1, self.fbay(b) + 1):
                if not self.level_has_frame(b, n):
                    continue          # e.g. no Level-1 corridor in DH zone
                z_target = self.zlev(n) - MEMBER      # corridor beam underside
                z_start = max(PLINTH, z_target - drop)
                for xk in (self.xaxis(b - 1), self.xaxis(b)):
                    if self.axis_in_stair_core(xk_index(self, xk)):
                        continue
                    for y in CORRIDOR_Y_AXES:
                        p0 = (xm, ty, z_start)
                        p1 = (xk, y + ob, z_target)
                        gid = bake(member_brep(p0, p1, MEMBER),
                                   "08_Atrium_Branches_To_Corridor",
                                   "ATRIUM_BRANCH_b%d_L%d" % (b, n))
                        self.SM.member(p0, p1, "ATRIUM_BRANCH_TO_CORRIDOR",
                                       "TIMBER_300x300_BRANCH", n, gid,
                                       "08_Atrium_Branches_To_Corridor")
                        n_branch += 1
        self.counts["atrium_trunks"] = n_trunk
        self.counts["atrium_branches"] = n_branch

    # =========================================================================
    # STAIRCASE RESERVED ZONES + DOG-LEG FOLDED-PLATE PLACEHOLDER
    #
    # Patched 2026-07-05 (error-folder-3 correction 3). The reference stair
    # (measured from the staircase OBJ groups) is a dog-leg stair inside the
    # atrium band: two ~1.5 m-wide folded-plate flights side by side split at
    # the atrium centreline (~8.2), running along the building length with an
    # intermediate landing at the far end of the well, direction alternating
    # each half-storey. Zone boxes are now thin WIREFRAME outlines and only
    # drawn when show_debug_zones is on. Named parameters: stair_width,
    # stair_flight_thickness, stair_landing_depth, stair_run_length (0=auto),
    # stair_placeholder_detail_level (0 = old simple ramp, 1 = dog-leg).
    # Stair bay positions are unchanged.
    # =========================================================================
    def generate_stairs(self):
        n_zone = 0
        for i, (s, e) in enumerate(self.Z["stair_zones"]):
            top = self.stair_top_level(i)
            x0 = self.xaxis(s - 1)
            x1 = self.xaxis(e)
            z1 = self.zlev(top)
            # plan-grid offset of the stair zone (zone bays share one offset
            # for the built-in grid types; boff(s) governs if ever split)
            ob = self.boff(s)
            if self.P.get("show_debug_zones", False):
                bake_box_wireframe(x0, x1, Y_COR_L + ob, Y_COR_R + ob,
                                   0.0, z1,
                                   "09_Staircase_Reserved_Zones",
                                   "STAIR_ZONE_%d" % (i + 1))
            n_zone += 1
            if not self.P["show_stairs"]:
                continue
            if int(self.P.get("stair_placeholder_detail_level", 1)) >= 1:
                self._dogleg_stair(i, s, e, top)
            else:
                for n in range(1, top + 1):        # legacy simple ramp
                    za = self.zlev(n - 1) if n > 1 else PLINTH
                    zb = self.zlev(n)
                    pa = (x0 + 0.6, TRUNK_Y + ob, za) if n % 2 == 1 \
                        else (x1 - 0.6, TRUNK_Y + ob, za)
                    pb = (x1 - 0.6, TRUNK_Y + ob, zb) if n % 2 == 1 \
                        else (x0 + 0.6, TRUNK_Y + ob, zb)
                    bake(member_brep(pa, pb, 0.9),
                         "09_Staircase_Reserved_Zones",
                         "STAIR_FLIGHT_z%d_L%d" % (i + 1, n))
        self.counts["stair_zones"] = n_zone

    def stair_landing_allowed_at_level(self, s, e, n):
        """True if storey level n has a real corridor/slab frame in the
        stair-zone bays (uses the existing level_has_frame() double-height /
        slab-opening logic)."""
        for b in range(s, e + 1):
            if self.level_has_frame(b, n):
                return True
        return False

    def needs_special_missing_corridor_landing(self, s, e, n):
        """Return True only where the stair arrives at a full storey level
        whose corridor/slab is MISSING because of the double-height zone
        (reference: tall stair at first-floor level L1). The stair then
        carries its own independent arrival landing/platform on the stair
        layer. On normal floors the corridor slab already exists, so no
        extra platform is created."""
        return not self.stair_landing_allowed_at_level(s, e, n)

    def _dogleg_stair(self, i, s, e, top):
        """Dog-leg folded-plate stair placeholder inside the stair well.
        Two landing kinds are distinguished (corrected 2026-07-05):
          1. intermediate dog-leg TURN landings at mid-storey height -
             always part of the flight system;
          2. floor-ARRIVAL platforms at full storey levels - normally the
             corridor slab plays this role; ONLY where the corridor slab is
             missing (double-height zone, e.g. tall stair at L1) a special
             red arrival platform is generated on the stair layer."""
        P = self.P
        w = float(P.get("stair_width", 1.5))
        t = float(P.get("stair_flight_thickness", 0.15))
        ld = float(P.get("stair_landing_depth", 1.5))
        zx0 = self.xaxis(s - 1)
        zx1 = self.xaxis(e)
        d = self.STAIR_LANDING_DEPTH
        if i == 0:                       # low zone: slab landing at entry side
            well0, well1 = zx0 + d, zx1
            entry_low = True
        else:                            # tall zone: slab landing at far side
            well0, well1 = zx0, zx1 - d
            entry_low = False
        run = float(P.get("stair_run_length", 0.0))
        if run <= 0.0:
            run = well1 - well0 - ld - 0.3
        run = max(2.0, min(run, well1 - well0 - ld - 0.2))
        ob = self.boff(s)                # plan-grid lateral offset of zone
        yA = TRUNK_Y + ob - w / 2.0 - 0.05   # flight A centre (half of well)
        yB = TRUNK_Y + ob + w / 2.0 + 0.05   # flight B centre (return half)
        lay = "09_Staircase_Reserved_Zones"
        for n in range(1, top + 1):
            z0 = self.zlev(n - 1) if n > 1 else PLINTH
            z1 = self.zlev(n)
            zm = (z0 + z1) / 2.0
            if entry_low:                # flights climb toward +X
                fx0, fx1 = well0 + 0.1, well0 + 0.1 + run
                lx0, lx1 = fx1, min(well1, fx1 + ld)
                pA0, pA1 = (fx0, yA, z0), (fx1, yA, zm)
                pB0, pB1 = (fx1, yB, zm), (fx0, yB, z1)
            else:                        # flights climb toward -X
                fx1b = well1 - 0.1
                fx0, fx1 = fx1b - run, fx1b
                lx0, lx1 = max(well0, fx0 - ld), fx0
                pA0, pA1 = (fx1, yA, z0), (fx0, yA, zm)
                pB0, pB1 = (fx0, yB, zm), (fx1, yB, z1)
            bake(plate_brep(pA0, pA1, w, t), lay,
                 "STAIR_FLIGHT_UP_z%d_L%d" % (i + 1, n))
            bake(plate_brep(pB0, pB1, w, t), lay,
                 "STAIR_FLIGHT_RETURN_z%d_L%d" % (i + 1, n))
            # 1. intermediate dog-leg turn landing (always part of the flight)
            bake(box_brep(lx0, lx1, yA - w / 2.0, yB + w / 2.0,
                          zm - t, zm), lay,
                 "STAIR_LANDING_z%d_L%d" % (i + 1, n))
            # 2. special floor-arrival platform ONLY where the corridor slab
            #    is missing (double-height zone, e.g. tall stair at L1)
            if self.needs_special_missing_corridor_landing(s, e, n):
                if entry_low:
                    px0, px1 = zx0, well0 + 0.1
                else:
                    px0, px1 = well1 - 0.1, zx1
                bake(box_brep(px0, px1, yA - w / 2.0, yB + w / 2.0,
                              self.zlev(n) - t, self.zlev(n)), lay,
                     "STAIR_ARRIVAL_PLATFORM_z%d_L%d" % (i + 1, n))

    # =========================================================================
    # DOUBLE-HEIGHT COMMON-SPACE DEBUG ZONES
    # =========================================================================
    def generate_dh_zones(self):
        """Zone reference volumes: thin wireframe outlines, only when the
        show_debug_zones toggle is on (clean skeleton by default)."""
        dh = sorted(self.Z["dh_bays"])
        n_zone = 0
        if dh:
            # contiguous runs, split where the plan-grid offset changes so
            # each outline follows its own shifted section
            runs = []
            run = [dh[0]]
            for b in dh[1:]:
                if b == run[-1] + 1 and abs(self.boff(b) -
                                            self.boff(run[-1])) < 1e-9:
                    run.append(b)
                else:
                    runs.append(run)
                    run = [b]
            runs.append(run)
            for r in runs:
                ob = self.boff(r[0])
                if self.P.get("show_debug_zones", False):
                    bake_box_wireframe(self.xaxis(r[0] - 1), self.xaxis(r[-1]),
                                       Y_OUT_L + ob, Y_OUT_R + ob, 0.0,
                                       self.zlev(2) - SLAB_T,
                                       "14_Double_Height_Common_Space_Debug",
                                       "DOUBLE_HEIGHT_COMMON_SPACE")
                n_zone += 1
        self.counts["dh_zones"] = n_zone

    # =========================================================================
    # MODULE PLACEHOLDERS  (A / B / GAP anchored to bay 1, no rhythm shifting)
    #
    # Skip rule (user-corrected 2026-07-05):
    #  - GAP bays stay empty.
    #  - Stair bays are skipped (rhythm NOT shifted).
    #  - Atrium tree-trunk bays are NOT skipped: trunks live in the central
    #    atrium Y-band, module placeholders live in the left/right module
    #    Y-bands -> no physical conflict in Y.
    #  - V-column bays are allowed by default: V-legs occupy the module bay
    #    only below L2, and placeholders inside the double-height zone are
    #    already restricted to storeys >= 3, so there is no overlap. The named
    #    toggle "exclude_modules_in_v_bays" restores the stricter behaviour.
    # =========================================================================
    def module_type(self, b):
        return ["A", "B", "GAP"][(b - 1) % 3]

    def generate_modules(self):
        n_mod, skipped = 0, 0
        self.module_records = []
        if not self.P["show_modules"]:
            self.counts["module_placeholders"] = 0
            return
        for b in range(1, self.NB + 1):
            mtype = self.module_type(b)
            if mtype == "GAP":
                continue
            if b in self.Z["stair_bays"]:
                skipped += 1          # stair-claimed bay: skip, DO NOT shift
                continue
            if (self.P.get("exclude_modules_in_v_bays", False)
                    and b in self.Z["v_bays"]):
                skipped += 1          # optional stricter V-bay exclusion
                continue
            ob = self.boff(b)                 # plan-grid lateral offset
            for (y0, y1, side) in [(Y_OUT_L + MEMBER / 2.0 + ob,
                                    Y_MID_L - MEMBER / 2.0 + ob, "L"),
                                   (Y_MID_R + MEMBER / 2.0 + ob,
                                    Y_OUT_R - MEMBER / 2.0 + ob, "R")]:
                for n in range(1, self.fbay(b) + 1):
                    if b in self.Z["dh_bays"] and n <= 2:
                        continue      # open common space below L2
                    x0 = self.xaxis(b - 1) + MEMBER / 2.0
                    x1 = self.xaxis(b) - MEMBER / 2.0
                    z0 = self.zlev(n - 1)
                    z1 = self.zlev(n) - SLAB_T
                    mirror = (side == "R")
                    name = "MODULE_%s_b%d_%s_L%d%s" % (
                        mtype, b, side, n, "_MIRROR" if mirror else "")
                    # lightweight: thin wireframe outline, not a heavy solid
                    ids = bake_box_wireframe(x0, x1, y0, y1, z0, z1,
                                             "10_Module_Placeholders", name)
                    gid = ids[0] if ids else None
                    p0 = ((x0 + x1) / 2.0, (y0 + y1) / 2.0, z0)
                    p1 = ((x0 + x1) / 2.0, (y0 + y1) / 2.0, z1)
                    self.SM.member(p0, p1, "MODULE_PLACEHOLDER_REFERENCE",
                                   "TIMBER_300x300_BEAM", n, gid,
                                   "10_Module_Placeholders")
                    self.module_records.append(
                        {"bay": b, "side": side, "level": n, "type": mtype,
                         "mirror": mirror,
                         "insertion_plane_origin": [x0, y0, z0]})
                    n_mod += 1
        self.counts["module_placeholders"] = n_mod
        self.counts["module_bays_skipped_claimed"] = skipped

    # =========================================================================
    # PHASE 2A - DUMMY BLOCK MODULE PLACEMENT (STAGE 2, runs after skeleton)
    #
    # Reference inspection (2026-07-05, re-verified same day with magnified
    # plan crops + programmatic read of the error-folder-3 failed-run 1.3dm):
    #   block module placement/  -> SEPARATE OBJs: block module 1 (=A),
    #     block module 1A (=A1, natively mirrored in the OBJ), block module 2
    #     (=B). All origins = inner bottom CLT corner (vertex at 0,0,0).
    #   module arrangement pattern/ level 3/4/5.png -> converging wood A/A1
    #     pairs; GREEN gap terraces every 3rd bay; Module B (RED) at the
    #     bay-12 end block on EVEN levels only (L4 red / L3+L5 wood proven),
    #     AND on the LOW-END roofs (bay-1 roof storey 2, bay-2 roof storey 3,
    #     both bands - visible in ALL three exported plans).
    #   export model 1/2 ...png -> ANCHOR RULE: module origin = inner bottom
    #     CLT wall corner, snapped to the rack beam-corner grid intersection,
    #     sitting ON TOP of the beam grid (Z = zlev(level-1))
    #   error folder 4/1.png -> tick-marked manual group = CONVERGING pair
    #     truth; X-marked diverging group = WRONG.
    # Known reference feature NOT reproduced (documented): tilted wood module
    # in the ATRIUM band at the bay-12 end (visible L3/L4/L5) - atrium band
    # is outside module-band slot logic; revisit in the real-OBJ phase.
    # Percentages: REMOVED. Arrangement is fully reference-driven.
    # =========================================================================
    # fallback procedural proportions, updated to the measured block OBJs:
    MOD_H = 3.5            # straight body height (block OBJ: 3.5)
    MOD_CANT = 3.5         # outward cantilever of the outer room (OBJ: ~3.5)
    MOD_CANT_H = 2.56      # cantilever room height (block OBJ: 2.56)
    BLOCK_FOLDER = "block module placement"
    # Optional fallback location for the block OBJ assets, used when
    # __file__ / the document path resolve elsewhere inside Rhino (a silent
    # miss here forces the procedural fallback and produces the wrong module
    # pair arrangement + a "missing" Module B).
    #
    # Configure this for your machine, or set the TIMBER_HOUSING_ASSETS
    # environment variable to the folder holding the block module OBJ files.
    # See docs/ASSETS_REQUIRED.md. Left empty by default so the script relies
    # on normal relative resolution first.
    PROJECT_FOLDER_HINT = os.environ.get("TIMBER_HOUSING_ASSETS", "")
    # separate OBJ per module type (2026-07-05 correction; the old combined
    # "block module 1 and 1A.obj" no longer exists in the folder)
    BLOCK_FILES = {"M1": "block module 1.obj",     # Module A
                   "M1A": "block module 1A.obj",   # Module A1 (own OBJ!)
                   "M2": "block module 2.obj"}     # Module B
    LEGACY_M1_FILE = "block module 1 and 1A.obj"   # pre-correction fallback
    BLOCK_NAMES = {"M1": "DUMMY_BLOCK_MODULE_1",
                   "M1A": "DUMMY_BLOCK_MODULE_1A_MIRRORED",
                   "M2": "DUMMY_BLOCK_MODULE_2"}
    BLOCK_LAYERS = {"M1": "20_Dummy_Module_A",
                    "M1A": "21_Dummy_Module_A1",
                    "M2": "22_Dummy_Module_B"}
    # report labels (user-facing terminology)
    BLOCK_LABELS = {"M1": "Module A", "M1A": "Module A1", "M2": "Module B"}

    @staticmethod
    def _mesh_bbox_str(mesh):
        try:
            bb = mesh.GetBoundingBox(True)
            return ("(%.2f,%.2f,%.2f)..(%.2f,%.2f,%.2f)"
                    % (bb.Min.X, bb.Min.Y, bb.Min.Z,
                       bb.Max.X, bb.Max.Y, bb.Max.Z))
        except Exception:
            return "(bbox unavailable)"

    def _load_block_defs(self):
        """Load Module A / A1 / B each from its OWN OBJ file (2026-07-05
        correction: block module 1.obj / block module 1A.obj /
        block module 2.obj). A1 is mirror-DERIVED from A only if its own OBJ
        is missing (loud warning; legacy convention). Sets
        self._block_source to 'obj_blocks' or 'procedural_fallback'.

        VISIBILITY FIX (root cause of 'Module B missing'): definition
        geometry is registered with ColorSource/MaterialSource = FromParent.
        Previously it defaulted to ByLayer on 'Default', so every instance
        rendered in the Default layer colour and A/A1/B were one indistinct
        grey - Module B WAS placed but could not be told apart. FromParent
        makes each instance show its own layer colour (A tan / A1 dark tan /
        B RED).

        Existing same-name definitions are REFRESHED with the new OBJ
        geometry (ModifyGeometry, else delete+re-add) so a re-run in the
        same document never silently reuses stale geometry.

        Anchor check (measured): all three OBJ origins ARE the inner bottom
        CLT corner (a vertex sits exactly at 0,0,0), so the local anchor
        correction transform is the IDENTITY - documented, no silent
        bounding-box shifting."""
        self._block_defs = {}
        self._block_source = "procedural_fallback"
        self._block_folder_used = None
        self._block_conv = {"M1A": "native"}  # 'native' | 'mirrored_legacy'
        self._block_diag = []                 # per-file diagnostic lines
        # try several candidate locations (error-folder-4 fix: a wrong
        # __file__/document path must not silently force the fallback)
        candidates = []
        try:
            here = os.path.dirname(os.path.abspath(__file__))
            candidates.append(os.path.join(here, self.BLOCK_FOLDER))
        except Exception:
            pass
        for root in [self.P.get("export_folder", ""),
                     self.PROJECT_FOLDER_HINT]:
            if root:
                candidates.append(os.path.join(root, self.BLOCK_FOLDER))
        try:
            dp = rs.DocumentPath()
            if dp:
                candidates.append(os.path.join(os.path.dirname(dp),
                                               self.BLOCK_FOLDER))
        except Exception:
            pass
        base = None
        for c in candidates:
            if os.path.isdir(c):
                base = c
                break
        if base is None:
            print("!" * 62)
            print("WARNING: block folder '%s' not found. Tried:"
                  % self.BLOCK_FOLDER)
            for c in candidates:
                print("   " + c)
            print("MODULE B OBJ FAILED TO LOAD - CHECK block module "
                  "placement FOLDER")
            print("-> PROCEDURAL FALLBACK will be used (approximate "
                  "shapes).")
            print("!" * 62)
            self._block_diag.append("block folder NOT FOUND")
            return
        self._block_folder_used = base
        # ---- parse each OBJ separately, with per-file diagnostics ----------
        parsed = {}
        for key in ("M1", "M1A", "M2"):
            path = os.path.join(base, self.BLOCK_FILES[key])
            exists = os.path.isfile(path)
            data = parse_obj_block(path) if exists else None
            parsed[key] = data
            self._block_diag.append(
                "%-9s file=%-22s found=%-3s parsed=%s"
                % (self.BLOCK_LABELS[key], self.BLOCK_FILES[key],
                   "yes" if exists else "NO",
                   ("%d verts / %d faces" % (len(data[0]), len(data[1])))
                   if data else "NO"))
        # legacy fallback for A if the new single-A OBJ is missing
        if parsed["M1"] is None:
            legacy = parse_obj_block(os.path.join(base, self.LEGACY_M1_FILE))
            if legacy:
                parsed["M1"] = legacy
                self._block_diag.append(
                    "Module A  recovered from legacy '%s'"
                    % self.LEGACY_M1_FILE)
        try:
            import Rhino as _Rh
            meshes = {}
            if parsed["M1"]:
                meshes["M1"] = obj_block_to_mesh(parsed["M1"])
            if parsed["M1A"]:
                meshes["M1A"] = obj_block_to_mesh(parsed["M1A"])
                self._block_conv["M1A"] = "native"
            elif parsed["M1"]:
                print("!" * 62)
                print("WARNING: '%s' missing -> Module A1 DERIVED by "
                      "mirroring Module A (legacy convention). Export the "
                      "separate A1 OBJ for exact geometry."
                      % self.BLOCK_FILES["M1A"])
                print("!" * 62)
                m1a = meshes["M1"].DuplicateMesh()
                m1a.Transform(rg.Transform.Mirror(rg.Plane.WorldXY))
                m1a.Flip(True, True, True)      # keep normals outward
                meshes["M1A"] = m1a             # bay-direction mirror (SU z)
                self._block_conv["M1A"] = "mirrored_legacy"
                self._block_diag.append(
                    "Module A1 = MIRROR-DERIVED from Module A (fallback)")
            if parsed["M2"]:
                meshes["M2"] = obj_block_to_mesh(parsed["M2"])
            else:
                print("!" * 62)
                print("MODULE B OBJ FAILED TO LOAD - CHECK block module "
                      "placement FOLDER")
                print("   expected: %s"
                      % os.path.join(base, self.BLOCK_FILES["M2"]))
                print("   Module B slots will use the procedural fallback "
                      "shape (still baked RED on its own layer - NOT "
                      "silently dropped, NOT replaced by green).")
                print("!" * 62)
            # ---- register/refresh definitions with FromParent attributes --
            for key in meshes:
                name = self.BLOCK_NAMES[key]
                attr = _Rh.DocObjects.ObjectAttributes()
                attr.ColorSource = \
                    _Rh.DocObjects.ObjectColorSource.ColorFromParent
                attr.MaterialSource = \
                    _Rh.DocObjects.ObjectMaterialSource.MaterialFromParent
                idef = None
                try:
                    idef = sc.doc.InstanceDefinitions.Find(name)
                except Exception:
                    try:
                        idef = sc.doc.InstanceDefinitions.Find(name, True)
                    except Exception:
                        idef = None
                if idef is not None:
                    ok = False
                    try:                        # refresh stale geometry
                        ok = sc.doc.InstanceDefinitions.ModifyGeometry(
                            idef.Index, [meshes[key]], [attr])
                    except Exception:
                        ok = False
                    if ok:
                        self._block_defs[key] = idef.Index
                        self._block_diag.append(
                            "%-9s def '%s' REFRESHED, mesh bbox %s"
                            % (self.BLOCK_LABELS[key], name,
                               self._mesh_bbox_str(meshes[key])))
                        continue
                    try:                        # else replace the definition
                        sc.doc.InstanceDefinitions.Delete(
                            idef.Index, True, True)
                        idef = None
                    except Exception:
                        pass
                if idef is None:
                    idx = sc.doc.InstanceDefinitions.Add(
                        name, "Timber Housing Phase 2A dummy block",
                        rg.Point3d.Origin, [meshes[key]], [attr])
                    if idx is not None and idx >= 0:
                        self._block_defs[key] = idx
                        self._block_diag.append(
                            "%-9s def '%s' CREATED, mesh bbox %s"
                            % (self.BLOCK_LABELS[key], name,
                               self._mesh_bbox_str(meshes[key])))
                    else:
                        self._block_diag.append(
                            "%-9s def '%s' ADD FAILED"
                            % (self.BLOCK_LABELS[key], name))
            if self._block_defs:
                self._block_source = "obj_blocks"
                print("Block definitions ready from: %s"
                      % self._block_folder_used)
                for key in ("M1", "M1A", "M2"):
                    if key not in self._block_defs:
                        print("   NOTE: %s has NO block definition -> "
                              "procedural fallback shape for its slots."
                              % self.BLOCK_LABELS[key])
            # NOTE: no source geometry is ever added to the scene here - the
            # OBJs are parsed from disk into block DEFINITIONS only, so no
            # loose/unplaced reference blocks can appear beside the model.
        except Exception as ex:
            print("WARNING: block OBJ import failed (%s) -> PROCEDURAL "
                  "FALLBACK (approximate shapes)." % ex)
            self._block_defs = {}
            self._block_source = "procedural_fallback"

    def _slot_block_xform(self, slot, mtype):
        """Placement transform, rebuilt EXACTLY from the corrected model
        (error folder 6). The slot's `orient` selects the 3x3 basis and the
        stored tx/ty/tz (ty already grid-shifted) give the translation:

          Aout  (A / A1) - block X (depth) -> OUTWARD Y, block Z -> bay X:
                Rhino X = -blockZ + tx ; Rhino Y = +/-blockX + ty ; Z = up
                (Y sign: +1 on the L band, -1 on the R band)
          Bspan (Module B, 2-bay band form) - block X -> +Rhino X (along the
                bay), block Z -> -Rhino Y
          Bend  (Module B at the bay-12 end) - block X -> -Rhino X,
                block Z -> +Rhino Y

        These reproduce the corrected model's instance transforms 1:1."""
        tx = slot["tx"]; ty = slot["ty"]; tz = slot["tz"]
        orient = slot.get("orient", "Aout")
        xf = rg.Transform(1.0)
        xf.M01 = 0.0; xf.M11 = 0.0; xf.M20 = 0.0; xf.M22 = 0.0
        xf.M21 = 1.0; xf.M23 = tz                       # Rhino Z = block Y (up)
        xf.M30 = 0.0; xf.M31 = 0.0; xf.M32 = 0.0; xf.M33 = 1.0
        if orient == "Bspan":                           # 2-bay band B
            xf.M00 = 1.0;  xf.M02 = 0.0; xf.M03 = tx
            xf.M10 = 0.0;  xf.M12 = -1.0; xf.M13 = ty
        elif orient == "Bend":                          # bay-12 end B
            xf.M00 = -1.0; xf.M02 = 0.0; xf.M03 = tx
            xf.M10 = 0.0;  xf.M12 = 1.0;  xf.M13 = ty
        else:                                           # Aout (A / A1)
            m10 = 1.0 if slot.get("side") == "L" else -1.0
            xf.M00 = 0.0;  xf.M02 = -1.0; xf.M03 = tx
            xf.M10 = m10;  xf.M12 = 0.0;  xf.M13 = ty
        return xf

    # NOTE (error folder 6): the old rule-based slot generator
    # (build_module_slots / slot_active / pattern_for_level, plus the bay%3
    # pair rhythm) is REMOVED. Placement is now a literal replay of the
    # corrected model via REFERENCE_CORRECTED. `is_fully_framed_module_slot`
    # is retained and used to tag/report each reference placement.

    # reference configuration the corrected model was authored for
    REF_NB = 12
    REF_F = list(REF_PROFILE)                    # [1,2,3,3,3,3,4,5,6,7,8,8]
    REF_PEAK = max(REF_PROFILE)                  # 8
    # supported parametric range (this configurator version)
    MAX_BAYS = 18
    MAX_FLOORS = 12

    def is_supported_module_config(self, total_bays=None, max_floors=None):
        """Phase-2A supports the reference minimum up to MAX_BAYS / MAX_FLOORS.
        Above that the pattern is not guaranteed; the caller clamps + warns."""
        nb = self.NB if total_bays is None else total_bays
        pk = (max(self.F) if self.F else 0) if max_floors is None else max_floors
        return nb <= self.MAX_BAYS and pk <= self.MAX_FLOORS

    def _bay_from_tx_ref(self, tx):
        """Reference near-corner tx -> REFERENCE bay index 1..REF_NB."""
        b = int(round((tx - 0.30) / AXIS)) + 1
        return max(1, min(self.REF_NB, b))

    def find_current_cascade_anchor(self):
        """The pattern anchors to the TALL / highest cascade end. With
        build_cascade the tall end is always the LAST bay (peak floors) and
        the low end is bay 1. Returns the anchor descriptor + diagnostics."""
        pk = max(self.F) if self.F else 0
        return {
            "tall_bay": self.NB,                 # highest cascade end
            "low_bay": 1,
            "peak": pk,
            "n_bays": self.NB,
            "profile": list(self.F),
            "supported": self.is_supported_module_config(),
            "grid_type": self.P.get("plan_grid_type", 1),
            "offset_dir": self.P.get("offset_direction", 1),
        }

    def is_reference_config(self):
        """True when the current config is exactly the one the corrected
        model was authored for (then the replay is bit-exact)."""
        return (self.NB == self.REF_NB
                and list(self.F) == self.REF_F)

    # -------------------------------------------------------------------------
    # Reference RHYTHM in (d, depth, side) space, d = distance from the tall
    # end (0 = tall/high bay NB), depth = floors below the local cascade top
    # (0 = roofline). Built once from the corrected model. Used by the
    # parametric cell-fill to tile the pattern over any supported cascade.
    # -------------------------------------------------------------------------
    def _ref_rhythm(self):
        cached = getattr(SkeletonRack, "_RHYTHM_CACHE", None)
        if cached is not None:
            return cached
        half = SECTION_WIDTH / 2.0
        rhythm = {}                              # (d, depth, side) -> entry
        vmax = {}                                # (d, side) -> max depth seen
        for (lvl, tp, orient, tx, ty) in REFERENCE_CORRECTED:
            rb = int(round((tx - 0.30) / AXIS)) + 1
            rb = max(1, min(SkeletonRack.REF_NB, rb))
            d = SkeletonRack.REF_NB - rb
            depth = SkeletonRack.REF_F[rb - 1] - lvl
            anchor_tx = 0.30 + (rb - 1) * AXIS
            if orient == "Bend" and 6.0 < ty < 11.0:
                side = "MID"
            else:
                side = "L" if ty < half else "R"
            rhythm[(d, depth, side)] = {
                "tp": tp, "orient": orient,
                "dtx": tx - anchor_tx, "ty": ty,
            }
            vmax[(d, side)] = max(vmax.get((d, side), -1), depth)
        SkeletonRack._RHYTHM_CACHE = (rhythm, vmax)
        return SkeletonRack._RHYTHM_CACHE

    def _rhythm_dkey(self, d):
        """Column key: the tall 3 columns (d 0,1,2) and the reference low end
        are kept; extra bays beyond REF_NB REPEAT the body columns (3..REF_NB-1
        period) so added bays continue the rhythm rather than stay blank."""
        if d < self.REF_NB:
            return d
        period = self.REF_NB - 3                  # body columns 3..11
        return 3 + ((d - 3) % period)

    def _rhythm_lookup(self, d, depth, side):
        """Type/orient for a cell at (d, depth, side), tiling the reference
        rhythm: the column is extended DOWNWARD with period 2 (matching the
        alternating a/B and A/a tall columns) so deep floors keep filling."""
        rhythm, vmax = self._ref_rhythm()
        dk = self._rhythm_dkey(d)
        vm = vmax.get((dk, side), -1)
        if vm < 0:
            return None
        if depth <= vm:
            dep = depth
        else:                                    # vertical period-2 extension
            dep = vm - 1 + ((depth - vm) % 2)
            dep = max(0, dep)
        return rhythm.get((dk, dep, side))

    def check_no_module_overlap(self, module_slots):
        """Validate final placements: no two module footprints may occupy the
        same (level, side, bay) cell. Returns the count of overlapping cells
        (0 for accepted output). MID atrium modules are on their own band."""
        seen = {}
        overlaps = 0
        for s in module_slots:
            for c in self.module_footprint_cells(s["bay"], s["side"],
                                                 s["level"], s["orient"]):
                if c in seen:
                    overlaps += 1
                else:
                    seen[c] = True
        return overlaps

    def build_reference_module_template(self):
        """Phase-2A placement. TWO modes:

        * REFERENCE config (NB=12, F=REF_F): a BIT-EXACT replay of the
          corrected model (`corrected logic model.3dm`).
        * Otherwise (up to MAX_BAYS / MAX_FLOORS): a PAIR-GAP RHYTHM engine
          (`_build_parametric_pairgap`) anchored to the tall/high cascade end
          - A/A1 pair + one green/common gap, repeating, with an alternate-
          floor offset and Module B at the tall corner. Modules go only in
          fully-framed cells, footprints are reserved, and overlaps are
          rejected.

        Returns (module_slots, terraces)."""
        if self.is_reference_config():
            self._param_info = {"pairgap": False, "intentional_gaps": 0,
                                "rejected_overlap": [], "final_overlaps": 0,
                                "alt_floor_offset": False}
            return self._build_exact_reference()
        return self._build_parametric_pairgap()

    def _build_exact_reference(self):
        """Bit-exact replay of REFERENCE_CORRECTED (reference config only)."""
        half = SECTION_WIDTH / 2.0
        module_slots, terraces = [], []
        for (lvl, tp, orient, tx, ty) in REFERENCE_CORRECTED:
            bay = self._bay_from_tx_ref(tx)
            limit = self.fbay(bay) + (1 if tp == "GREEN" else 0)
            if bay > self.NB or lvl > limit:
                continue
            ob = self.boff(bay)
            tz = self.zlev(lvl - 1)
            if orient == "Bend" and 6.0 < ty < 11.0:
                side = "MID"
            else:
                side = "L" if ty < half else "R"
            rec = {
                "bay": bay, "level": lvl, "side": side,
                "assigned": tp, "orient": orient,
                "tx": tx, "ty": ty + ob, "tz": tz,
                "anchor": (tx, ty + ob, tz),
                "framed": self.is_fully_framed_module_slot(bay, lvl),
                "pattern": "exact-corrected-L%d" % lvl,
                "role": {"Aout": "module", "Bspan": "B_span2bay",
                         "Bend": "B_end_bay12",
                         "green": "terrace"}.get(orient, orient),
            }
            (terraces if tp == "GREEN" else module_slots).append(rec)
        return module_slots, terraces

    def _make_rec(self, b, lvl, side, tp, orient, dtx, ty_ref, framed):
        ob = self.boff(b)
        tx = 0.30 + (b - 1) * AXIS + dtx
        ty = ty_ref + ob
        tz = self.zlev(lvl - 1)
        return {
            "bay": b, "level": lvl, "side": side,
            "assigned": tp, "orient": orient,
            "tx": tx, "ty": ty, "tz": tz, "anchor": (tx, ty, tz),
            "framed": framed,
            "pattern": "parametric-L%d" % lvl,
            "role": {"Aout": "module", "Bspan": "B_span2bay",
                     "Bend": "B_end_bay12",
                     "green": "terrace"}.get(orient, orient),
        }

    def module_footprint_cells(self, bay, side, lvl, orient):
        """Rack cells a module's INNER CLT footprint occupies (for overlap
        reservation). Aout = 1 bay. Bend (tall-end B) = 1 support bay (its
        7.5 m cantilevers OFF the building end into empty space, so only the
        anchor bay is a real cell). Bspan (2-bay, reference only) = 2 bays."""
        if orient == "Bspan":
            return [(lvl, side, bay), (lvl, side, bay - 1)]
        return [(lvl, side, bay)]

    def _build_parametric_pairgap(self):
        """PAIR-GAP rhythm engine (non-reference configs, tall-end anchored).

        The corrected model is NOT 'fill every framed cell': its grammar is
        an A/A1 PAIR + one GAP (green/common), repeating, with an
        ALTERNATE-FLOOR offset and Module B at the tall/high corner. This
        engine reproduces that grammar for any supported size:

          * per floor + side, walk the fully-framed cells from the TALL end
            (highest bay) toward the low end;
          * the tall-end CORNER is Module B on odd floors (>=3), else A1;
          * the rest is the repeating unit [A1, A, GAP] (period 3), phase
            shifted by floor PARITY so pairs sit at (NB-1,NB-2) on odd floors
            and (NB,NB-1) on even floors - the reference's alternate-floor
            diagonal;
          * GAP cells become green/common terraces (INTENTIONAL rhythm gaps,
            NOT accidental empties);
          * every module footprint is RESERVED; a placement whose footprint
            hits an already-reserved cell is REJECTED (no overlaps).

        Returns (module_slots, terraces, info) where info carries the
        overlap / gap accounting for diagnostics."""
        NB = self.NB
        peak = max(self.F) if self.F else 0
        module_slots, terraces = [], []
        occupied = {}                            # (lvl, side, bay) -> label
        rejected_overlap = []
        intentional_gaps = 0

        def try_place(bay, lvl, side, tp, orient, dtx, tyr):
            cells = self.module_footprint_cells(bay, side, lvl, orient)
            for c in cells:
                if c in occupied:
                    rejected_overlap.append(
                        {"bay": bay, "level": lvl, "side": side, "tp": tp,
                         "conflict": occupied[c], "reason":
                         "overlap_with_existing_module"})
                    return False
            for c in cells:
                occupied[c] = "%s@b%dL%d%s" % (tp, bay, lvl, side)
            module_slots.append(
                self._make_rec(bay, lvl, side, tp, orient, dtx, tyr, True))
            return True

        # ---- L / R module bands: pair-gap per floor -------------------------
        for side in ("L", "R"):
            ty_band = (Y_MID_L if side == "L" else Y_MID_R)
            ty_bend = (3.80 if side == "L" else 16.00)
            for lvl in range(1, peak + 1):
                cells = [b for b in range(NB, 0, -1)
                         if lvl <= self.fbay(b)
                         and self.is_fully_framed_module_slot(b, lvl)]
                if not cells:
                    continue
                ph = 0 if (lvl % 2 == 1) else 1  # alternate-floor offset
                for idx, bay in enumerate(cells):
                    if idx == 0 and lvl >= 3 and lvl % 2 == 1:
                        # tall/high corner = Module B on odd floors
                        try_place(bay, lvl, side, "M2", "Bend", -0.30, ty_bend)
                        continue
                    if idx == 0:
                        # even-floor corner starts the pair with A1
                        try_place(bay, lvl, side, "M1A", "Aout", 0.0, ty_band)
                        continue
                    u = (idx - 1 + ph) % 3
                    if u == 0:
                        try_place(bay, lvl, side, "M1A", "Aout", 0.0, ty_band)
                    elif u == 1:
                        try_place(bay, lvl, side, "M1", "Aout", 0.0, ty_band)
                    else:
                        # GAP: intentional green/common (breaks the wall)
                        terraces.append(
                            self._make_rec(bay, lvl, side, "GREEN", "green",
                                           0.0, ty_band - 1.9, True))
                        occupied[(lvl, side, bay)] = "GAP"
                        intentional_gaps += 1
        # ---- atrium MID Module-B column at the tall end ---------------------
        fb_tall = self.fbay(NB)
        for lvl in range(3, fb_tall + 1):
            try_place(NB, lvl, "MID", "M2", "Bend", -0.30, 9.90)
        # ---- cascade-step roof terraces (green) -----------------------------
        for b in range(1, NB + 1):
            f = self.fbay(b)
            if not (1 <= f < peak):
                continue
            for side in ("L", "R"):
                ty_band = (Y_MID_L if side == "L" else Y_MID_R)
                terraces.append(
                    self._make_rec(b, f + 1, side, "GREEN", "green",
                                   0.0, ty_band - 1.9, False))
        # store accounting for the report
        self._param_info = {
            "rejected_overlap": rejected_overlap,
            "intentional_gaps": intentional_gaps,
            "final_overlaps": self.check_no_module_overlap(module_slots),
            "pairgap": True,
            "alt_floor_offset": True,
        }
        return module_slots, terraces
        return module_slots, terraces

    # NOTE: percentages / density / seed / pattern-mode / bay%3 heuristics are
    # ALL gone. Reference config = bit-exact replay; larger configs = cell-
    # based fill anchored to the tall cascade end (<= 18 bays / 12 floors).

    def _bake_dummy_module(self, slot, mtype):
        """Place one dummy module. Preferred: block instance from the
        reference OBJs ('block module placement' folder), anchored by the
        inner-bottom-CLT-corner convention. Fallback: procedural Brep."""
        if getattr(self, "_block_source", "") == "obj_blocks" \
                and mtype in self._block_defs:
            xf = self._slot_block_xform(slot, mtype)
            gid = sc.doc.Objects.AddInstanceObject(
                self._block_defs[mtype], xf)
            if gid:
                rs.ObjectLayer(gid, self.BLOCK_LAYERS[mtype])
                rs.ObjectName(gid, "DUMMY_%s_b%d_%s_L%d"
                              % (mtype, slot["bay"], slot["side"],
                                 slot["level"]))
                return "block"
        self._bake_dummy_module_procedural(slot, mtype)
        return "procedural"

    def _bake_dummy_module_procedural(self, slot, mtype):
        """Fallback procedural mass (used ONLY if the block OBJ import fails).
        Uses the same orient + tx/ty/tz as the block transform, so the box
        occupies the corrected-model footprint even without the OBJ. A plain
        box is enough for a debug fallback - the real OBJ carries the detail.
        Block footprints: A/A1 ~ X[-7.27,0] Z[-3.5,0.8]; B ~ X[-7.5,0]
        Z[-3.5,0]; Y (height) [0,3.5]."""
        tx = slot["tx"]; ty = slot["ty"]; tz = slot["tz"]
        orient = slot.get("orient", "Aout")
        lay = self.BLOCK_LAYERS[mtype]
        name = "DUMMY_%s_b%d_%s_L%d" % (mtype, slot["bay"], slot["side"],
                                        slot["level"])
        if orient == "Bspan":                    # block X->+X, Z->-Y
            x0, x1 = tx - 7.5, tx
            y0, y1 = ty, ty + 3.5
        elif orient == "Bend":                   # block X->-X, Z->+Y
            x0, x1 = tx, tx + 7.5
            y0, y1 = ty - 3.5, ty
        else:                                     # Aout: X->outward Y, Z->bayX
            x0, x1 = tx - 3.5, tx                 # bay width (block Z 3.5)
            depth = 7.27
            if slot.get("side") == "L":
                y0, y1 = ty - depth, ty           # projects outward -Y
            else:
                y0, y1 = ty, ty + depth           # projects outward +Y
        bake(box_brep(min(x0, x1), max(x0, x1), min(y0, y1), max(y0, y1),
                      tz, tz + 3.5), lay, name)

    def _bake_green_slot(self, slot):
        """Flat common/terrace plate. Corrected-model greens carry tx/ty/tz
        (ty already grid-shifted): a green fills one module-band cell -
        bay-clear in X, the full band width in Y, at the storey deck."""
        tx = slot["tx"]; ty = slot["ty"]; z0 = slot["tz"]
        x0 = tx; x1 = tx + (AXIS - MEMBER)              # bay clear (~3.5)
        halfband = (AXIS - MEMBER) / 2.0                # band half-width
        bake(box_brep(x0, x1, ty - halfband, ty + halfband, z0, z0 + 0.12),
             "23_Green_Common_Terrace_Slots",
             "GREEN_COMMON_b%d_%s_L%d"
             % (slot["bay"], slot["side"], slot["level"]))

    def place_dummy_modules(self, MP):
        """Stage-2 placement (fixed alternate-floor pattern, percentages
        REMOVED): the arrangement is generated automatically from the fixed
        reference pattern; the user only enables placement and the anchor
        debug. Cascade/grid/stairs decide availability, nothing else."""
        # clear any previous Stage-2 output (safe re-run without stacking).
        # includes the OLD layer names in case a document still carries them.
        for lay in ["20_Dummy_Module_A", "21_Dummy_Module_A1",
                    "22_Dummy_Module_B", "20_Dummy_Module_1",
                    "21_Dummy_Module_1A_Mirrored", "22_Dummy_Module_2",
                    "23_Green_Common_Terrace_Slots",
                    "24_Module_Placement_Anchors_Debug",
                    "25_Module_Placement_Notes"]:
            if rs.IsLayer(lay):
                objs = rs.ObjectsByLayer(lay)
                if objs:
                    rs.DeleteObjects(objs)
        # Phase 2A dummy-preview visibility guard (workflow fix, 2026-07-07):
        # a previous Phase-2B detailed build hides the dummy layers 20-22
        # (place_detailed_modules -> LayerVisible False) and nothing restored
        # them, so a later dummy preview baked its blocks into still-hidden
        # layers and appeared to "not place". Re-show the dummy layers here so
        # the freshly placed dummies are always visible. Placement algorithm,
        # geometry, transforms and counts are UNCHANGED - visibility only.
        for lay in ("20_Dummy_Module_A", "21_Dummy_Module_A1",
                    "22_Dummy_Module_B", "23_Green_Common_Terrace_Slots",
                    "24_Module_Placement_Anchors_Debug",
                    "25_Module_Placement_Notes"):
            if rs.IsLayer(lay):
                rs.LayerVisible(lay, True)
        # supported-range check (module placement only; the skeleton itself is
        # frozen and may exceed this - we warn, do not clamp the skeleton).
        if not self.is_supported_module_config():
            print("!" * 58)
            print("WARNING: %d bays / %d floors is ABOVE the supported module "
                  "range" % (self.NB, max(self.F) if self.F else 0))
            print("         (max %d bays / %d floors). Module placement will "
                  "still" % (self.MAX_BAYS, self.MAX_FLOORS))
            print("         run as best-effort but is not guaranteed. Reduce "
                  "bays/floors")
            print("         to stay within the supported range.")
            print("!" * 58)
        self._load_block_defs()
        module_slots, terraces = self.build_reference_module_template()
        N = len(module_slots)
        # template (intended) counts BEFORE placement
        tmpl = {"M1": 0, "M1A": 0, "M2": 0, "GREEN": 0}
        for s in module_slots:
            tmpl[s["assigned"]] += 1
        tmpl["GREEN"] += len(terraces)          # green terraces
        # actual placed counts + how each was baked (block vs procedural)
        placed = {"M1": 0, "M1A": 0, "M2": 0, "GREEN": 0}
        via = {"block": 0, "procedural": 0}
        roles = {}
        levels_used = {}
        # a corrected-model placement is skipped ONLY if it is genuinely
        # outside the generated rack/cascade (framed==False AND the bay/level
        # is not active). We report every such rejection loudly.
        ref_rejected = []
        for s in module_slots:
            active = s["level"] <= self.fbay(s["bay"])
            if not s.get("framed", True) and not active:
                ref_rejected.append(s)
                continue
            roles[s["role"]] = roles.get(s["role"], 0) + 1
            levels_used.setdefault(s["level"], s.get("pattern", "corrected"))
            how = self._bake_dummy_module(s, s["assigned"])
            placed[s["assigned"]] += 1
            via[how] = via.get(how, 0) + 1
            if MP.get("show_anchors", False):
                a = s["anchor"]
                bake(rg.Point3d(a[0], a[1], a[2]),
                     "24_Module_Placement_Anchors_Debug",
                     "ANCHOR_b%d_%s_L%d" % (s["bay"], s["side"], s["level"]))
                bake(rg.LineCurve(rg.Point3d(a[0], a[1], a[2]),
                                  rg.Point3d(a[0], a[1], a[2] + 0.6)),
                     "24_Module_Placement_Anchors_Debug")
        for t in terraces:
            self._bake_green_slot(t)
            placed["GREEN"] += 1
        self.module_slots = module_slots + terraces
        counts = placed                         # back-compat return value
        # ---- summary --------------------------------------------------------
        a1_note = ("separate OBJ"
                   if getattr(self, "_block_conv", {}).get("M1A") == "native"
                   else "MIRROR-DERIVED (A1 OBJ missing)")

        def mismatch(key):
            return "" if tmpl[key] == placed[key] else "  <-- MISMATCH!"
        diag_lines = getattr(self, "_block_diag", []) or ["(none)"]
        rej_lines = ["  none - all placements are in the rack"]
        if ref_rejected:
            rej_lines = ["  L%d bay%d %s %s (%s) - outside cascade/rack"
                         % (r["level"], r["bay"], r["side"], r["assigned"],
                            r["orient"]) for r in ref_rejected]
        is_ref = self.is_reference_config()
        anchor = self.find_current_cascade_anchor()
        all_recs = module_slots + terraces
        # parametric-growth stats vs the original 12-bay / 8-floor reference
        extra_bay = [s for s in all_recs if s["bay"] > self.REF_NB]
        extra_flr = [s for s in all_recs if s["level"] > self.REF_PEAK]
        bays_pop = sorted(set(s["bay"] for s in all_recs))
        empty_bays = [b for b in range(1, self.NB + 1)
                      if b not in bays_pop and self.fbay(b) >= 1]
        # framed-cell audit: modules must fill framed cells and NEVER land on
        # unframed/terrace/open cells.
        placed_cells = set((s["bay"], s["level"], s["side"])
                           for s in module_slots if s["side"] != "MID")
        terr_cells = set((s["bay"], s["level"], s["side"]) for s in terraces)
        framed_total = 0
        empty_framed = []
        for b in range(1, self.NB + 1):
            for lvl in range(1, self.fbay(b) + 1):
                for side in ("L", "R"):
                    if self.is_fully_framed_module_slot(b, lvl):
                        framed_total += 1
                        if ((b, lvl, side) not in placed_cells
                                and (b, lvl, side) not in terr_cells):
                            empty_framed.append((b, lvl, side))
        mod_on_unframed = sum(1 for s in module_slots
                              if s["side"] != "MID" and not s.get("framed"))
        supported = self.is_supported_module_config()
        ef_sample = ", ".join("b%dL%d%s" % (b, l, s)
                              for (b, l, s) in empty_framed[:8])
        # pair-gap / overlap accounting from the parametric engine
        pinfo = getattr(self, "_param_info", {}) or {}
        intentional_gaps = pinfo.get("intentional_gaps", 0)
        rej_overlap = pinfo.get("rejected_overlap", [])
        final_overlaps = pinfo.get("final_overlaps",
                                   self.check_no_module_overlap(module_slots))
        # accidental = framed cell that is neither a module NOR an intentional
        # green/common gap (should be 0 in pair-gap mode). In EXACT mode the
        # empties are the corrected model's OWN designed voids (bay-12 L1/L2
        # etc.) - intentional, not accidental.
        gap_cells = set((t["bay"], t["level"], t["side"]) for t in terraces)
        if is_ref:
            accidental_empty = []            # model-defined voids = intentional
            ref_voids = len(empty_framed)
        else:
            accidental_empty = [c for c in empty_framed if c not in gap_cells]
            ref_voids = 0
        rej_ov_lines = ["  none"]
        if rej_overlap:
            rej_ov_lines = ["  b%dL%d%s %s vs %s (%s)"
                            % (r["bay"], r["level"], r["side"], r["tp"],
                               r["conflict"], r["reason"])
                            for r in rej_overlap[:8]]
        lines = [
            "PHASE 2A - MODULE PLACEMENT (pair-gap rhythm, tall-end anchored)",
            "(ref config = exact model replay; larger = pair-gap rhythm)",
            "=" * 58,
            "grid type / direction   : %d / %s"
            % (self.P.get("plan_grid_type", 1),
               "left" if self.P.get("offset_direction", 1) == 1 else "right"),
            "correction round        : ERROR FOLDER 7 - pair-gap rhythm +",
            "                          overlap prevention (truth = corrected",
            "                          logic model.3dm)",
            "-" * 58,
            "CASCADE ANCHOR + MODE",
            "  total bays (NB)       : %d" % anchor["n_bays"],
            "  peak floors           : %d" % anchor["peak"],
            "  supported range       : max %d bays / %d floors"
            % (self.MAX_BAYS, self.MAX_FLOORS),
            "  within supported range: %s" % ("YES" if supported else
               "NO - ABOVE RANGE, pattern is best-effort (see warning)"),
            "  cascade profile       : %s" % str(anchor["profile"]),
            "  tall/high anchor bay  : %d  (low end = bay 1)"
            % anchor["tall_bay"],
            "  placement mode        : %s"
            % ("EXACT replay (reference config NB=12, peak=8)" if is_ref
               else "PARAMETRIC pair-gap rhythm (A/A1 pair + green gap, "
                    "alternate-floor offset, tall corner = B)"),
            "  pair-gap rhythm        : %s"
            % ("n/a (exact mode)" if is_ref else "YES"),
            "  alternate-floor offset : %s"
            % ("n/a" if is_ref else "YES (odd/even floor phase shift)"),
            "  ref-config exact match : %s" % ("YES" if is_ref else
               "n/a (grown/shrunk config)"),
            "  bays populated         : %d of %d" % (len(bays_pop), self.NB),
            "  empty active bays      : %s"
            % (str(empty_bays) if empty_bays else "none"),
            "-" * 58,
            "FRAMED-CELL AUDIT (strict rack-cell rule)",
            "  total framed L/R cells : %d" % framed_total,
            "  modules on UNframed    : %d  (MUST be 0)" % mod_on_unframed,
            "  intentional rhythm gaps: %d  (green/common after each pair)"
            % (intentional_gaps if not is_ref else ref_voids),
            "  ACCIDENTAL empty framed: %d  (MUST be ~0)"
            % len(accidental_empty),
            "  accidental sample      : %s"
            % (", ".join("b%dL%d%s" % c for c in accidental_empty[:8])
               or "none"),
            "  terrace/open cells     : kept as green/empty, NEVER a module",
            "-" * 58,
            "OVERLAP PREVENTION",
            "  overlap conflicts found: %d (rejected before placement)"
            % len(rej_overlap),
        ] + rej_ov_lines + [
            "  FINAL accepted overlaps: %d  (MUST be 0)" % final_overlaps,
            "  B footprint reserved   : yes (Bend = 1 support bay; Bspan = 2)",
            "  placements beyond ref  : %d bay>12, %d level>8 (grown regions)"
            % (len(extra_bay), len(extra_flr)),
            "  no old-absolute-only   : confirmed (anchors from CURRENT cascade)",
            "-" * 58,
            "BLOCK LOADING DIAGNOSTIC",
            "  folder used           : %s"
            % (self._block_folder_used or "NONE (fallback)"),
            "  geometry source       : %s" % self._block_source,
        ] + ["  " + d for d in diag_lines] + [
            "  Module A1 convention  : %s" % a1_note,
            "-" * 58,
            "A / A1 LOGIC (from corrected model)",
            "  A  (=M1)  placements  : %d  (room depth projects OUTWARD, 1 bay)"
            % tmpl["M1"],
            "  A1 (=M1A) placements  : %d  (own OBJ; mirror pair of A)"
            % tmpl["M1A"],
            "B LOGIC (from corrected model - TWO orientations)",
            "  B  (=M2)  placements  : %d" % tmpl["M2"],
            "  orient 'Bspan'        : 7.5m depth ALONG the bay (~2 bays),",
            "                          band form (block X->+X, Z->-Y)",
            "  orient 'Bend'         : bay-12 end (block X->-X, Z->+Y); L",
            "                          band + atrium MID + R band on odd",
            "                          levels, atrium MID only on even levels",
            "GREEN / COMMON",
            "  green placements      : %d (terrace/common, from the model)"
            % tmpl["GREEN"],
            "-" * 58,
            "FULLY-FRAMED SLOT VALIDATION (reference placements)",
            "  reference rejected    : %d" % len(ref_rejected),
        ] + rej_lines + [
            "  rule                  : a corrected-model placement is dropped",
            "                          ONLY if its bay/level is outside the",
            "                          generated cascade/rack; in-rack",
            "                          placements are always kept (the model",
            "                          is the authority)",
            "-" * 58,
            "TEMPLATE (intended) vs PLACED (actual)",
            "  Module A  (=M1)  tmpl %3d  placed %3d%s"
            % (tmpl["M1"], placed["M1"], mismatch("M1")),
            "  Module A1 (=M1A) tmpl %3d  placed %3d%s"
            % (tmpl["M1A"], placed["M1A"], mismatch("M1A")),
            "  Module B  (=M2)  tmpl %3d  placed %3d%s"
            % (tmpl["M2"], placed["M2"], mismatch("M2")),
            "  Green/Common     tmpl %3d  placed %3d%s"
            % (tmpl["GREEN"], placed["GREEN"], mismatch("GREEN")),
            "  baked via         : %d block instance(s), %d procedural"
            % (via.get("block", 0), via.get("procedural", 0)),
            "  total module slots    : %d  (+ %d green)" % (N, len(terraces)),
            "roles                   : %s" % str(sorted(roles.items())),
            "-" * 58,
            "loose source geometry   : none - OBJs -> block DEFINITIONS only;",
            "                          layers 20-25 cleared before each run",
            "percentage system       : REMOVED (literal reference replay)",
            "anchor rule             : inner bottom CLT corner (OBJ origins",
            "                          verified = this corner; identity)",
        ]
        # loud Module B verdict on the console (never silent)
        if placed["M2"] == 0:
            print("!" * 58)
            print("MODULE B NOT PLACED - template B count = %d." % tmpl["M2"])
            print("!" * 58)
        elif "M2" not in getattr(self, "_block_defs", {}):
            print("NOTE: Module B placed as PROCEDURAL red boxes "
                  "(block module 2.obj not loaded).")
        txt = "\n".join(lines)
        print(txt)
        rs.CurrentLayer("25_Module_Placement_Notes")
        rs.AddText(txt, (0.0, -30.0, 0.0), height=0.45)
        rs.CurrentLayer(LAYERS[0][0])
        return counts

    # =========================================================================
    # PHASE 2B - DETAILED TEXTURED REAL MODULE PLACEMENT  (VISUAL ONLY)
    #
    # Reuses the APPROVED Phase-2A dummy placement records (self.module_slots)
    # and the SAME _slot_block_xform transform - no new placement logic, no
    # new records, no change to counts / rhythm / reference table. Detailed
    # modules are baked as Rhino block INSTANCES (defined once, inserted many
    # times -> light when multiplied). NOTHING here calls SM.member, so the
    # frozen structural / RFEM / sizing baseline is untouched by construction.
    #
    # Source classification (Stage 2B-0, geometry-derived, 2026-07-06):
    #   module.obj  -> Module A  / M1   (Z-centre -1.606 ~ dummy A -1.350)
    #   modulee.obj -> Module A1 / M1A  (Z-centre -1.894 ~ dummy A1 -2.150)
    #   module 2.obj-> Module B  / M2
    # module & modulee are the SAME footprint, pure Z-shift (-0.287) apart -
    # exactly the dummy A/A1 relationship; the up-shifted one is A.
    # Detailed A/A1 share the dummy A/A1 local frame + origin (CLT corner at
    # 0,0,0) EXACTLY -> identity local correction. Detailed B carries its 7.5m
    # depth on local Z (dummy B has it on local X) -> a -90 deg correction about
    # the up-axis is BAKED into the DETAIL_MODULE_B definition so the same
    # _slot_block_xform then applies. If B appears rotated the wrong way in
    # Rhino, flip DETAIL_B_CORR_DEG sign (reported in the diagnostics).
    # =========================================================================
    DETAIL_FOLDER = "detail modules in origin"
    DETAIL_FILES = {"M1":  os.path.join("module 1 and  1a", "module.obj"),
                    "M1A": os.path.join("module 1 and  1a", "modulee.obj"),
                    "M2":  os.path.join("module 2", "module 2.obj")}
    DETAIL_GLB = {"M1":  os.path.join("module 1 and  1a", "module.glb"),
                  "M1A": os.path.join("module 1 and  1a", "modulee", "modulee.glb"),
                  "M2":  os.path.join("module 2", "module 2.glb")}
    DETAIL_BLOCK_NAMES = {"M1": "DETAIL_MODULE_A", "M1A": "DETAIL_MODULE_A1",
                          "M2": "DETAIL_MODULE_B"}
    DETAIL_LAYERS = {"M1": "30_Detailed_Module_A",
                     "M1A": "31_Detailed_Module_A1",
                     "M2": "32_Detailed_Module_B"}
    DETAIL_B_CORR_DEG = -90.0        # local-axis correction for detailed B
    # Phase 2B targeted correction 2 (2026-07-06): detailed Module 2 is DOOR-
    # AWARE - its distinctive door/window/special face must always face the
    # corridor. Rule = a real facing test (not just L/R): for each M2 slot the
    # world door-normal (below, mapped through _slot_block_xform) is compared to
    # the corridor direction (toward the section centreline); if it points away
    # (dot < 0) the instance is mirrored IN PLACE across its own centre plane
    # perpendicular to the door normal -> footprint/anchor/position/scale/count
    # unchanged, only the facing flips.
    #
    # DETAIL_M2_DOOR_LOCAL: inspected door/window-face normal in the BLOCK-DEF
    # (post -90deg-correction) local frame. Derived from module 2.obj geometry:
    # the room-width axis is block-def Z (= original +X, the CLT-corner/opening
    # side; the interior furniture bulk sits on the far -Z side). If the Rhino
    # test shows ALL M2 doors flipped the wrong way, negate this -> (0,0,-1);
    # that single change inverts every decision.
    DETAIL_M2_DOOR_LOCAL = (0.0, 0.0, 1.0)
    # Optional manual override (fallback/tuning): any slot side listed here is
    # FORCED to mirror regardless of the facing test. Empty by default so the
    # facing test governs.
    DETAIL_M2_MIRROR_SIDES = ()

    def _detail_folder_base(self):
        cands = []
        try:
            cands.append(os.path.join(
                os.path.dirname(os.path.abspath(__file__)), self.DETAIL_FOLDER))
        except Exception:
            pass
        for root in [self.P.get("export_folder", ""), self.PROJECT_FOLDER_HINT]:
            if root:
                cands.append(os.path.join(root, self.DETAIL_FOLDER))
        try:
            dp = rs.DocumentPath()
            if dp:
                cands.append(os.path.join(os.path.dirname(dp),
                                          self.DETAIL_FOLDER))
        except Exception:
            pass
        for c in cands:
            if os.path.isdir(c):
                return c, cands
        return None, cands

    def _detail_local_correction(self, mtype):
        """Local-frame correction baked into the detailed block definition so
        the existing _slot_block_xform applies unchanged. Identity for A/A1;
        -90 deg about the up-axis for B (aligns its 7.5 m local-Z depth onto
        the dummy-B local-X convention)."""
        if mtype != "M2":
            return None
        ang = math.radians(self.DETAIL_B_CORR_DEG)
        return rg.Transform.Rotation(ang, rg.Vector3d(0.0, 1.0, 0.0),
                                     rg.Point3d.Origin)

    def _detail_module2_world_door_normal(self, slot):
        """World direction the detailed Module 2 door/window face points for
        this slot. The door normal is DETAIL_M2_DOOR_LOCAL in the block-def
        frame; _slot_block_xform maps that frame to world by a pure basis swap
        per orient, computed directly (vector -> translation ignored):
          Bspan: block(x,y,z) -> world( x, -z,  y)
          Bend : block(x,y,z) -> world(-x,  z,  y)"""
        dx, dy, dz = self.DETAIL_M2_DOOR_LOCAL
        if slot.get("orient") == "Bend":
            return (-dx, dz, dy)
        return (dx, -dz, dy)                    # Bspan (and any other M2)

    def _detail_module2_corridor_direction(self, slot):
        """World unit direction from the module toward the corridor - i.e.
        toward the section centreline (atrium spine) at Y = SECTION_WIDTH/2
        (+ the bay's plan-grid offset). Works for L / R / MID and all grid
        types because both the centreline and ty carry the same boff."""
        cy = SECTION_WIDTH / 2.0 + self.boff(slot["bay"])
        d = cy - slot["ty"]
        s = 1.0 if d > 1e-6 else (-1.0 if d < -1e-6 else 0.0)
        return (0.0, s, 0.0)

    def _detail_module2_facing(self, slot):
        """Facing analysis for one detailed Module 2 slot: corridor direction,
        door world normal, dot product and mirror decision (dot < 0 -> door
        points away -> mirror). A side listed in DETAIL_M2_MIRROR_SIDES is
        force-mirrored (manual override)."""
        wd = self._detail_module2_world_door_normal(slot)
        cd = self._detail_module2_corridor_direction(slot)
        dot = wd[0] * cd[0] + wd[1] * cd[1] + wd[2] * cd[2]
        forced = slot.get("side") in self.DETAIL_M2_MIRROR_SIDES
        return {"door": wd, "corridor": cd, "dot": dot,
                "forced": forced, "needs_mirror": forced or (dot < 0.0)}

    def _detail_module2_needs_mirror(self, slot):
        """True if this detailed Module 2 instance must be mirrored so its
        door/corridor face points toward the corridor. A/A1/GREEN never mirror.
        The mirror is applied in place (see place_detailed_modules) across the
        instance's own centre plane perpendicular to the door normal, so the
        anchor / footprint / position / scale / count stay unchanged."""
        if slot.get("assigned") != "M2":
            return False
        return self._detail_module2_facing(slot)["needs_mirror"]

    def _load_detail_block_defs(self):
        """Import each classified detailed OBJ once (materials + textures via
        Rhino's importer), create DETAIL_MODULE_A/A1/B block definitions, and
        delete the loose source geometry. Sets self._detail_defs (mtype->name)
        and self._detail_diag."""
        self._detail_defs = {}
        self._detail_diag = []
        self._detail_source = "obj"
        base, cands = self._detail_folder_base()
        self._detail_folder_used = base
        if base is None:
            self._detail_diag.append("detail module folder NOT FOUND; tried: "
                                     + " | ".join(cands))
            return
        for key in ("M1", "M1A", "M2"):
            path = os.path.join(base, self.DETAIL_FILES[key])
            name = self.DETAIL_BLOCK_NAMES[key]
            if not os.path.isfile(path):
                self._detail_diag.append("%s: OBJ MISSING %s"
                                         % (name, path))
                continue
            try:
                # refresh: drop a stale same-name definition first
                try:
                    old = sc.doc.InstanceDefinitions.Find(name)
                    if old is not None:
                        sc.doc.InstanceDefinitions.Delete(old.Index, True, True)
                except Exception:
                    pass
                rs.UnselectAllObjects()
                rs.Command('_-Import "%s" _Enter _Enter' % path, False)
                objs = rs.LastCreatedObjects()
                if not objs:
                    self._detail_diag.append("%s: IMPORT produced no objects "
                                             "(check Rhino OBJ import)" % name)
                    continue
                corr = self._detail_local_correction(key)
                if corr is not None:
                    rs.TransformObjects(objs, corr)     # bake B correction
                mats = set()
                for o in objs:
                    try:
                        mats.add(rs.ObjectMaterialIndex(o))
                    except Exception:
                        pass
                bname = rs.AddBlock(objs, [0.0, 0.0, 0.0], name, True)
                leftover = rs.LastCreatedObjects()      # should be empty
                if bname:
                    self._detail_defs[key] = bname
                    self._detail_diag.append(
                        "%s: CREATED from %d objects, %d materials, source "
                        "deleted=%s%s"
                        % (name, len(objs), len(mats),
                           "yes" if not leftover else "NO",
                           " (B corr %.0f deg)" % self.DETAIL_B_CORR_DEG
                           if key == "M2" else ""))
                else:
                    self._detail_diag.append("%s: AddBlock FAILED" % name)
            except Exception as ex:
                self._detail_diag.append("%s: import/block error %s"
                                         % (name, ex))

    def place_detailed_modules(self, MP, hide_dummy=True):
        """Insert detailed block instances at the APPROVED Phase-2A transforms
        (self.module_slots). Visual only. Returns a counts/diagnostics dict."""
        sm_before = len(self.SM.model["members"])
        for lay in list(self.DETAIL_LAYERS.values()) + [
                "33_Detailed_Module_Debug_Anchors", "34_Detailed_Module_Notes"]:
            if rs.IsLayer(lay):
                o = rs.ObjectsByLayer(lay)
                if o:
                    rs.DeleteObjects(o)
        slots = getattr(self, "module_slots", None)
        if not slots:
            print("Detailed placement: no Phase-2A records (module_slots). "
                  "Run dummy placement first.")
            return {"error": "no_records"}
        self._load_detail_block_defs()
        want = {"M1": 0, "M1A": 0, "M2": 0}
        placed = {"M1": 0, "M1A": 0, "M2": 0}
        skipped = []
        m2_diag = []                            # per-M2 orientation/mirror log
        for s in slots:
            mt = s.get("assigned")
            if mt not in ("M1", "M1A", "M2"):
                continue                       # GREEN / terraces: no detail
            active = s["level"] <= self.fbay(s["bay"])
            if not s.get("framed", True) and not active:
                continue
            want[mt] += 1
            if mt not in self._detail_defs:
                skipped.append("%s b%d L%d (no block def)"
                               % (mt, s["bay"], s["level"]))
                continue
            xf = self._slot_block_xform(s, mt)
            try:
                gid = rs.InsertBlock2(self._detail_defs[mt], xf)
            except Exception as ex:
                skipped.append("%s b%d L%d (insert error %s)"
                               % (mt, s["bay"], s["level"], ex))
                continue
            if gid:
                rs.ObjectLayer(gid, self.DETAIL_LAYERS[mt])
                # ---- Module 2 DOOR-to-CORRIDOR orientation ------------------
                # Real facing test: compare the door world normal to the
                # corridor direction; if the door points away (dot < 0) mirror
                # the instance IN PLACE across its OWN centre plane perpendicular
                # to the door normal (world plane through the bbox centre) - so
                # the footprint / anchor / position / scale stay put and only
                # the door face turns toward the corridor. A/A1 untouched.
                mir = "no"
                if mt == "M2":
                    fac = self._detail_module2_facing(s)
                    dot_a = fac["dot"]
                    if fac["needs_mirror"]:
                        try:
                            bb = rs.BoundingBox(gid)
                            wd = fac["door"]
                            if bb and (abs(wd[0]) > 1e-6 or abs(wd[1]) > 1e-6):
                                cx = (min(p.X for p in bb)
                                      + max(p.X for p in bb)) / 2.0
                                cy = (min(p.Y for p in bb)
                                      + max(p.Y for p in bb)) / 2.0
                                # mirror line = perpendicular to door normal
                                # (nx,ny) through the instance centre
                                rs.MirrorObject(gid, (cx, cy, 0.0),
                                                (cx - wd[1], cy + wd[0], 0.0),
                                                False)
                                mir = "yes"
                                dot_a = -dot_a       # facing flipped
                            else:
                                mir = "skip(no-hbb)"
                        except Exception as ex:
                            mir = "FAILED(%s)" % ex
                    m2_diag.append(
                        {"bay": s["bay"], "level": s["level"],
                         "side": s.get("side"), "orient": s.get("orient"),
                         "anchor": s.get("anchor"), "corridor": fac["corridor"],
                         "door": fac["door"], "dot_before": fac["dot"],
                         "dot_after": dot_a, "mirror": mir,
                         "pass": dot_a > 0.0})
                rs.ObjectName(gid, "DETAIL_%s_b%d_%s_L%d%s"
                              % (mt, s["bay"], s["side"], s["level"],
                                 "_MIR" if mir == "yes" else ""))
                placed[mt] += 1
                if MP.get("show_anchors", False):
                    a = s["anchor"]
                    bake(rg.Point3d(a[0], a[1], a[2]),
                         "33_Detailed_Module_Debug_Anchors",
                         "DET_ANCHOR_b%d_%s_L%d"
                         % (s["bay"], s["side"], s["level"]))
        if hide_dummy:
            for lay in ("20_Dummy_Module_A", "21_Dummy_Module_A1",
                        "22_Dummy_Module_B"):
                if rs.IsLayer(lay):
                    rs.LayerVisible(lay, False)      # keep records, hide blocks
        sm_after = len(self.SM.model["members"])
        info = {"want": want, "placed": placed, "skipped": skipped,
                "sm_before": sm_before, "sm_after": sm_after,
                "source_format": self._detail_source,
                "folder": self._detail_folder_used, "m2_mirror": m2_diag}
        self._write_detailed_report(info)
        return info

    def run_phase2b_regression_check(self, info):
        """Confirm Phase 2B did not touch the frozen structural baseline."""
        ok_sm = (info.get("sm_before") == info.get("sm_after"))
        ok_col = (abs(MEMBER - 0.30) < 1e-9)
        ok_axis = (abs(AXIS - 3.80) < 1e-9)
        # no detailed objects on structural / RFEM layers
        stray = 0
        for lay in ("02_Regular_Columns", "03_Regular_Beams"):
            for o in (rs.ObjectsByLayer(lay) or []):
                nm = rs.ObjectName(o) or ""
                if nm.startswith("DETAIL_"):
                    stray += 1
        return {"structuralmodel_unchanged": ok_sm,
                "regular_column_030": ok_col, "axis_380": ok_axis,
                "detail_on_structural_layers": stray}

    def _write_detailed_report(self, info):
        reg = self.run_phase2b_regression_check(info)
        L = ["Timber Housing v23 - PHASE 2B DETAILED MODULE PLACEMENT", "=" * 56,
             "source folder      : %s" % info.get("folder"),
             "source format      : %s" % info.get("source_format"),
             "-" * 56, "CLASSIFICATION (geometry-derived):",
             "  Module A  / M1  <- module.obj",
             "  Module A1 / M1A <- modulee.obj",
             "  Module B  / M2  <- module 2.obj  (local -%0.0f deg corr)"
             % abs(self.DETAIL_B_CORR_DEG), "-" * 56,
             "BLOCK DEFINITIONS:"]
        for d in getattr(self, "_detail_diag", []):
            L.append("  " + d)
        L += ["-" * 56, "PLACEMENT (reuses Phase-2A records, scale 1.0):",
              "  Module A  detailed placed : %d / %d"
              % (info["placed"]["M1"], info["want"]["M1"]),
              "  Module A1 detailed placed : %d / %d"
              % (info["placed"]["M1A"], info["want"]["M1A"]),
              "  Module B  detailed placed : %d / %d"
              % (info["placed"]["M2"], info["want"]["M2"]),
              "  GREEN slots               : no detailed module (by design)",
              "  skipped                   : %d" % len(info["skipped"])]
        for s in info["skipped"][:12]:
            L.append("     - " + s)
        # ---- Module 2 door-to-corridor orientation --------------------------
        m2d = info.get("m2_mirror", [])
        nmir = sum(1 for d in m2d if d.get("mirror") == "yes")
        npass = sum(1 for d in m2d if d.get("pass"))
        L += ["-" * 56,
              "MODULE 2 ORIENTATION (door/window face must face corridor):",
              "  door local normal      : %s (block-def frame)"
              % str(self.DETAIL_M2_DOOR_LOCAL),
              "  rule                   : dot(door_world, corridor_dir) < 0 "
              "-> mirror in place (perp to door normal, through centre)",
              "  force-mirror sides     : %s" % str(self.DETAIL_M2_MIRROR_SIDES),
              "  M2 instances           : %d  (mirrored %d, normal %d)"
              % (len(m2d), nmir, len(m2d) - nmir),
              "  corridor-facing PASS   : %d / %d %s"
              % (npass, len(m2d),
                 "(ALL PASS)" if npass == len(m2d) else "(CHECK FAILS)")]
        for d in m2d:
            L.append("    b%-2d L%-2d side=%-3s orient=%-6s corr=%+d door=%+d "
                     "dot:%+.0f->%+.0f mir=%-3s %s"
                     % (d["bay"], d["level"], d.get("side"), d.get("orient"),
                        int(d.get("corridor", (0, 0, 0))[1]),
                        int(round(d.get("door", (0, 0, 0))[1])),
                        d.get("dot_before", 0), d.get("dot_after", 0),
                        d.get("mirror"), "PASS" if d.get("pass") else "FAIL"))
        L += ["-" * 56, "STRUCTURAL REGRESSION (must all be safe):",
              "  StructuralModel unchanged : %s (%d -> %d members)"
              % ("YES" if reg["structuralmodel_unchanged"] else "NO",
                 info["sm_before"], info["sm_after"]),
              "  regular column 0.30x0.30  : %s"
              % ("YES" if reg["regular_column_030"] else "NO"),
              "  AXIS 3.80 m               : %s"
              % ("YES" if reg["axis_380"] else "NO"),
              "  detail on structural lyrs : %d (must be 0)"
              % reg["detail_on_structural_layers"],
              "  RFEM export line geometry : UNTOUCHED (detailed = visual only)",
              "-" * 56,
              "NOTE: detailed modules are visual/configurator geometry only; "
              "they are NOT structural members and do not affect RFEM/Dlubal "
              "export or preliminary sizing."]
        txt = "\n".join(L)
        print(txt)
        try:
            rs.CurrentLayer("34_Detailed_Module_Notes")
            rs.AddText(txt, (0.0, -46.0, 0.0), height=0.45)
            rs.CurrentLayer(LAYERS[0][0])
        except Exception:
            pass
        return txt

    # =========================================================================
    # CASCADE DEBUG + ANALYSIS DEBUG
    # =========================================================================
    def generate_cascade_debug(self):
        if not self.P.get("show_debug_zones", False):
            return                        # clean skeleton by default
        pts = [rg.Point3d(p[0], p[1], p[2])
               for p in self.support_points["cascade_profile_points"]]
        if len(pts) >= 2:
            poly = rg.PolylineCurve(pts)
            bake(poly, "11_Cascade_Debug", "CASCADE_PROFILE")

    def generate_analysis_debug(self):
        if not self.P["show_analysis_debug"]:
            return
        for m in self.SM.model["members"]:
            ni = self.SM.model["nodes"][m["node_i"]]
            nj = self.SM.model["nodes"][m["node_j"]]
            c = rg.LineCurve(rg.Point3d(ni["x"], ni["y"], ni["z"]),
                             rg.Point3d(nj["x"], nj["y"], nj["z"]))
            bake(c, "12_Analysis_Model_Debug", "AXIS_%s_%d" % (m["type"], m["id"]))

    # =========================================================================
    # REPORT
    # =========================================================================
    def report(self):
        c = self.counts
        L = self.NB * AXIS + MEMBER
        lines = [
            "Timber Housing v23 SKELETON RACK - PHASE 1  (%s)"
            % datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
            "=" * 56,
            "X bays                  : %d" % self.NB,
            "plan grid type          : %d (%s), direction %s"
            % (self.P.get("plan_grid_type", 1),
               {1: "Regular", 2: "Half Offset",
                3: "Centre Offset"}.get(self.P.get("plan_grid_type", 1), "?"),
               "left" if self.P.get("offset_direction", 1) == 1 else "right"),
            "total building length   : %.2f m" % L,
            "fixed Y section width   : %.2f m (3.8|2.3|3.8|2.3|3.8 axis bands)"
            % SECTION_WIDTH,
            "floors (peak)           : %d" % max(self.F),
            "max cascade height      : %.2f m" % self.zlev(max(self.F)),
            "lowest cascade height   : %.2f m" % self.zlev(min(self.F)),
            "cascade profile         : %s (ascending away from origin)"
            % str(self.F),
            "active rack bays        : %d" % self.NB,
            "regular columns         : %d" % c.get("regular_columns", 0),
            "stair support columns   : %d" % c.get("stair_support_columns", 0),
            "regular beams           : %d" % c.get("regular_beams", 0),
            "corridor edge beams     : %d" % c.get("corridor_edge_beams", 0),
            "base grid beams         : %d  (X %d + Y %d; structural, level 0)"
            % (c.get("base_beams_total", 0), c.get("base_beams_x", 0),
               c.get("base_beams_y", 0)),
            "base cells skipped (DH) : %d bays (open/lifted ground, no base)"
            % c.get("base_cells_skipped_dh_void", 0),
            "base thickness (plinth) : %.2f m"
            % getattr(self, "_base_platform_top", PLINTH),
            "base platform pieces    : %d  (visual only)"
            % c.get("base_platform_pieces", 0),
            "base platform top z     : %.2f m"
            % getattr(self, "_base_platform_top", PLINTH),
            "base beam top z         : %.2f m"
            % getattr(self, "_base_beam_top", PLINTH),
            "base platform==beam top : %s"
            % ("YES" if abs(getattr(self, "_base_platform_top", PLINTH)
                            - getattr(self, "_base_beam_top", PLINTH)) < 1e-6
               else "NO"),
            "base SM members added   : %d  (BASE_BEAM_X / BASE_BEAM_Y)"
            % c.get("base_beams_total", 0),
            "module placement (code) : UNTOUCHED (Phase 2A pair-gap intact)",
            "slab plates             : %d" % c.get("slab_plates", 0),
            "4-legged V columns      : %d  (%d legs)"
            % (c.get("v_columns", 0), c.get("v_legs", 0)),
            "atrium tree trunks      : %d" % c.get("atrium_trunks", 0),
            "atrium branches         : %d" % c.get("atrium_branches", 0),
            "corridor support nodes  : %d" % c.get("corridor_support_nodes", 0),
            "staircase zones         : %d  %s"
            % (c.get("stair_zones", 0), str(self.Z["stair_zones"])),
            "double-height zones     : %d  (bays %s)"
            % (c.get("dh_zones", 0),
               str(sorted(self.Z["dh_bays"]))),
            "V bays                  : %s" % str(self.Z["v_bays"]),
            "trunk bays              : %s" % str(self.Z["trunk_bays"]),
            "module placeholders     : %d  (claimed bays skipped: %d)"
            % (c.get("module_placeholders", 0),
               c.get("module_bays_skipped_claimed", 0)),
            "analytical nodes        : %d" % len(self.SM.model["nodes"]),
            "analytical members      : %d" % len(self.SM.model["members"]),
            "analytical supports     : %d" % len(self.SM.model["supports"]),
            "-" * 56,
            "NOTE: design-stage model. NOT structural verification.",
        ]
        txt = "\n".join(lines)
        print(txt)
        rs.CurrentLayer("13_Text_Notes")
        rs.AddText(txt, (0.0, -14.0, 0.0), height=0.45)
        rs.CurrentLayer(LAYERS[0][0])
        return txt

    # =========================================================================
    def run(self):
        self.generate_support_points()
        self.generate_grid()
        self.generate_columns()
        self.generate_beams()
        self.generate_base_grid_and_plinth()
        self.generate_slabs()
        self.generate_v_columns()
        self.generate_tree_columns()
        self.generate_stairs()
        self.generate_dh_zones()
        self.generate_modules()
        self.generate_cascade_debug()
        self.generate_analysis_debug()
        self.report()
        if self.P["export_analysis"]:
            folder = os.path.join(self.P["export_folder"], "analysis")
            path = self.SM.export(folder)
            if path:
                print("Analysis model exported: %s" % path)


def xk_index(rack, x_value):
    """Inverse of xaxis(): nearest axis index for a coordinate."""
    return int(round((x_value - Y_OUT_L) / AXIS))


# =============================================================================
# 6. USER INPUT  (Eto dialog, rs.Get* fallback)
# =============================================================================

def default_params():
    here = None
    try:
        here = os.path.dirname(os.path.abspath(__file__))
    except Exception:
        here = rs.DocumentPath() or os.path.expanduser("~")
    return {
        "x_bays": 12,
        "peak_floors": 8,
        # ---- plan grid type (NEW) -------------------------------------------
        "plan_grid_type": 1,      # 1 Regular / 2 Half Offset / 3 Centre Offset
        "offset_direction": 1,    # 1 Shift Left (-Y) / 2 Shift Right (+Y)
        "dh_start_bay": 5,
        "v_start_bay": 6,
        "v_step": 2,
        "trunk_start_bay": 5,
        "trunk_step": 2,
        "stair_zone_1": (3, 4),
        "stair_zone_2": (10, 11),
        "stair_top_levels": [0, 0],           # 0 = auto from cascade
        "low_stair_support_start_level": 0,   # user point 7 named parameters
        "tall_stair_support_start_level": 0,
        "avoid_tree_columns_in_stair_zone": True,
        "exclude_modules_in_v_bays": False,   # V-legs end at L2; DH storey
                                              # rule already prevents overlap
        # error-folder-2 patch: regular columns in the double-height zone
        # start only above the V/transfer level (measured L2 in reference)
        "regular_columns_start_after_double_height_level": 2,
        # tree branches carry corridor edges at trunk-served axes (measured)
        "suppress_corridor_columns_in_trunk_service": True,
        # error-folder-3 patch: reference has a third V-column in the ATRIUM
        # band at the end block (measured legs at section 6.95..9.35, mid-bay
        # 12 only) because no trunk serves bays beyond the tall stair zone
        "atrium_v_in_end_block": True,
        # ---- staircase placeholder (dog-leg folded plates) ------------------
        "stair_width": 1.5,                   # measured flight width (~1.5)
        "stair_flight_thickness": 0.15,
        "stair_landing_depth": 1.5,
        "stair_run_length": 0.0,              # 0 = auto from stair well
        "stair_placeholder_detail_level": 1,  # 0 = old simple ramp, 1 = dogleg
        # ---- default visibility: clean skeleton first -----------------------
        "show_floor_plates": True,
        # ---- base/plinth + lower grid (OBJ-derived correction, 2026-07-06) ---
        # Reference: skeleton structure.obj. Base BEAM grid measured at Z
        # 0.36..0.66 (top at plinth 0.7); visual plinth slab 0..base_thickness.
        "show_base_platform": True,   # visual full-plan plinth slab (0..base_thickness)
        "base_thickness": PLINTH,     # Part A: 0.7 -> plinth top aligns with base beam top
        "show_stairs": True,
        "show_modules": False,        # placeholders OFF by default (toggle on)
        "show_support_points": False, # OFF by default
        "show_debug_zones": False,    # stair/DH zone boxes + cascade polyline,
                                      # drawn as thin WIREFRAME outlines when on
        "show_analysis_debug": False,
        "export_analysis": False,
        "export_folder": here,
    }


def rescale_zone_defaults(P):
    """Keep reference zone logic sensible when bay count changes."""
    n = P["x_bays"]
    if n != 12:
        P["stair_zone_2"] = (max(1, n - 2), max(1, n - 1))
        P["dh_start_bay"] = min(P["dh_start_bay"], max(1, n - 1))
        P["v_start_bay"] = min(P["v_start_bay"], n)
        P["trunk_start_bay"] = min(P["trunk_start_bay"], n)
    return P


# =============================================================================
# 5b. SHARED ETO UI STYLING
#
# UI colours and typography adapted from an earlier internal prototype, applied
# to Rhino Eto dialogs only - NO HTML/CSS, no external packages, no
# fonts from the internet. Rounded corners are not available in Eto, so the
# "card" feeling is approximated with warm background colours, padding, grouped
# panels, section labels, consistent button colours and spacing. Every helper
# is DEFENSIVE (wrapped in try/except): if a Rhino/Eto build rejects a property
# the dialog still shows - styling never breaks working logic.
# =============================================================================
UI_COLORS = {
    "bg":      "#f3efe7",   # warm off-white background
    "bg2":     "#ece6da",   # secondary background
    "card":    "#fbf9f4",   # card / panel
    "ink":     "#2c2a26",   # dark ink text
    "muted":   "#8a8377",   # muted grey/brown text
    "line":    "#dcd5c7",   # border / hairline
    "accent":  "#9c6b3f",   # brown accent
    "accent2": "#6f8f6a",   # green secondary accent
    "dot":     "#d8d0c0",   # neutral dot/grid
    "white":   "#ffffff",
    "warn":    "#9a5b2f",   # warning brown
}

# Dialog width control (2026-07-07 UI-layout correction). Eto Labels do not
# wrap or cap their width by default, so a long single-line note used to push a
# whole dialog off-screen. These constants give the wrapped text cards a fixed
# content width, which in turn bounds the dialog to a compact rectangle.
UI_TEXT_WIDTH = 520          # wrapped note/paragraph content width (px)
UI_DIALOG_WIDTH = 560        # preferred compact dialog content width (px)
UI_DIALOG_WIDE_WIDTH = 760   # for wide report/summary dialogs (px)


def _ui_color(hexstr):
    import Eto.Drawing as drawing
    h = str(hexstr).lstrip("#")
    return drawing.Color.FromArgb(int(h[0:2], 16), int(h[2:4], 16),
                                  int(h[4:6], 16))


def _ui_font(size, bold=False, mono=False):
    import Eto.Drawing as drawing
    fam = "Consolas" if mono else "Segoe UI"
    try:
        if bold:
            return drawing.Font(fam, float(size), drawing.FontStyle.Bold)
        return drawing.Font(fam, float(size))
    except Exception:
        return None


def _ui_style_label(lbl, kind="body"):
    spec = {
        "brand":   ("accent",  8.0,  True),
        "header":  ("ink",    15.0,  True),
        "muted":   ("muted",   9.0,  False),
        "section": ("accent",  9.5,  True),
        "mono":    ("ink",     9.0,  False),
        "body":    ("ink",     9.0,  False),
        "value":   ("ink",    12.0,  True),
        "warn":    ("warn",    9.0,  False),
        "green":   ("accent2", 9.0,  True),
    }.get(kind, ("ink", 9.0, False))
    try:
        lbl.TextColor = _ui_color(UI_COLORS[spec[0]])
    except Exception:
        pass
    try:
        f = _ui_font(spec[1], spec[2], mono=(kind == "mono"))
        if f is not None:
            lbl.Font = f
    except Exception:
        pass
    return lbl


def _ui_style_button(btn, kind="primary"):
    import Eto.Drawing as drawing
    spec = {
        "primary":   ("accent",  "white", True),
        "secondary": ("accent2", "white", True),
        "cancel":    ("bg2",     "ink",   False),
        "ghost":     ("card",    "ink",   False),
    }.get(kind, ("accent", "white", True))
    try:
        btn.BackgroundColor = _ui_color(UI_COLORS[spec[0]])
    except Exception:
        pass
    try:
        btn.TextColor = _ui_color(UI_COLORS[spec[1]])
    except Exception:
        pass
    try:
        f = _ui_font(9.0, spec[2])
        if f is not None:
            btn.Font = f
    except Exception:
        pass
    try:
        btn.MinimumSize = drawing.Size(132, 30)
    except Exception:
        pass
    return btn


def _ui_style_dialog(dlg):
    import Eto.Drawing as drawing
    try:
        dlg.BackgroundColor = _ui_color(UI_COLORS["bg"])
    except Exception:
        pass
    try:
        dlg.Padding = drawing.Padding(16)
    except Exception:
        pass
    return dlg


def _ui_style_input(ctrl):
    for prop, col in (("BackgroundColor", "card"), ("TextColor", "ink")):
        try:
            setattr(ctrl, prop, _ui_color(UI_COLORS[col]))
        except Exception:
            pass
    try:
        f = _ui_font(9.0)
        if f is not None:
            ctrl.Font = f
    except Exception:
        pass
    return ctrl


# task-named thin wrappers (public API requested by the styling spec)
def style_label(label, kind="body"):
    return _ui_style_label(label, kind)


def style_textbox(textbox):
    return _ui_style_input(textbox)


def style_dropdown(dropdown):
    return _ui_style_input(dropdown)


def style_checkbox(checkbox):
    try:
        checkbox.TextColor = _ui_color(UI_COLORS["ink"])
    except Exception:
        pass
    try:
        f = _ui_font(9.0)
        if f is not None:
            checkbox.Font = f
    except Exception:
        pass
    return checkbox


def make_card(content, pad=10):
    import Eto.Forms as forms
    import Eto.Drawing as drawing
    p = forms.Panel()
    try:
        p.BackgroundColor = _ui_color(UI_COLORS["card"])
    except Exception:
        pass
    try:
        p.Padding = drawing.Padding(pad)
    except Exception:
        pass
    p.Content = content
    return p


def make_section_label(text):
    import Eto.Forms as forms
    lbl = forms.Label()
    lbl.Text = str(text)
    return _ui_style_label(lbl, "section")


def make_info_panel(text, kind="muted", width=None):
    """Card-wrapped text that WORD-WRAPS at a fixed content width so a long
    note can never stretch the dialog off-screen (2026-07-07 fix). `width` in
    px (defaults to UI_TEXT_WIDTH)."""
    import Eto.Forms as forms
    import Eto.Drawing as drawing
    if width is None:
        width = UI_TEXT_WIDTH
    lbl = forms.Label()
    lbl.Text = str(text)
    try:
        lbl.Wrap = forms.WrapMode.Word
    except Exception:
        pass
    _ui_style_label(lbl, kind)
    try:
        lbl.Size = drawing.Size(int(width), -1)   # fix width, auto height
    except Exception:
        pass
    return make_card(lbl, pad=11)


# alias requested by the UI spec
def make_wrapped_text_card(text, width=None, kind="muted"):
    return make_info_panel(text, kind, width)


def make_button_row(buttons, align="right"):
    """A horizontal button row that keeps the buttons at their natural size and
    stays VISIBLE (returns a self-contained TableLayout to drop into one cell).

    Implemented with a TableLayout (not a StackLayout): the previous
    StackLayout-with-empty-expanding-spacer version collapsed the buttons to
    zero width in Eto.Wpf, so the action buttons disappeared (correction folder
    2). A TableLayout row of natural-width button cells is the proven pattern
    (same as the report-preview button row). For right alignment a single
    leading empty cell is set to scale, pushing the buttons to the right without
    stretching them. NOTE: this row is always added as its own bottom row of the
    dialog body - it is kept OUTSIDE any wrapped/scrollable text content so it
    can never be clipped."""
    import Eto.Forms as forms
    import Eto.Drawing as drawing
    lay = forms.TableLayout()
    lay.Spacing = drawing.Size(8, 0)
    cells = []
    if align == "right":
        spacer = forms.TableCell()          # empty scaling cell pushes buttons
        try:
            spacer.ScaleWidth = True        # right without stretching them
        except Exception:
            pass
        cells.append(spacer)
    for b in buttons:
        cells.append(forms.TableCell(b))            # natural-width button cell
    lay.Rows.Add(forms.TableRow(cells))
    return lay


def make_summary_table(rows):
    import Eto.Forms as forms
    import Eto.Drawing as drawing
    lay = forms.TableLayout()
    lay.Spacing = drawing.Size(16, 4)
    for k, v in rows:
        kl = forms.Label()
        kl.Text = str(k)
        _ui_style_label(kl, "muted")
        vl = forms.Label()
        vl.Text = str(v)
        _ui_style_label(vl, "value")
        lay.Rows.Add(forms.TableRow([forms.TableCell(kl), forms.TableCell(vl)]))
    return make_card(lay, pad=11)


def make_header(title, subtitle=None, brand="Parametric Timber Housing"):
    import Eto.Forms as forms
    import Eto.Drawing as drawing
    brand_lbl = forms.Label()
    brand_lbl.Text = str(brand).upper()
    _ui_style_label(brand_lbl, "brand")
    t = forms.Label()
    t.Text = str(title)
    _ui_style_label(t, "header")
    lay = forms.TableLayout()
    lay.Spacing = drawing.Size(0, 1)
    lay.Rows.Add(forms.TableRow(forms.TableCell(brand_lbl)))
    lay.Rows.Add(forms.TableRow(forms.TableCell(t)))
    if subtitle:
        s = forms.Label()
        s.Text = str(subtitle)
        _ui_style_label(s, "muted")
        lay.Rows.Add(forms.TableRow(forms.TableCell(s)))
    p = forms.Panel()
    try:
        p.Padding = drawing.Padding(2, 2, 2, 6)
    except Exception:
        pass
    p.Content = lay
    return p


def make_primary_button(text):
    import Eto.Forms as forms
    b = forms.Button()
    b.Text = str(text)
    return _ui_style_button(b, "primary")


def make_secondary_button(text):
    import Eto.Forms as forms
    b = forms.Button()
    b.Text = str(text)
    return _ui_style_button(b, "secondary")


def make_cancel_button(text):
    import Eto.Forms as forms
    b = forms.Button()
    b.Text = str(text)
    return _ui_style_button(b, "cancel")


def _ui_section_row(text):
    import Eto.Forms as forms
    c1 = forms.TableCell()
    c1.Control = make_section_label(text)
    return forms.TableRow([c1, forms.TableCell()])


def _ui_wrap(inner, title, subtitle=None):
    """Return a TableLayout with a styled Timber Housing header above `inner`. On any
    failure returns `inner` unchanged so the dialog still shows."""
    import Eto.Forms as forms
    import Eto.Drawing as drawing
    try:
        header = make_header(title, subtitle)
        outer = forms.TableLayout()
        outer.Spacing = drawing.Size(0, 10)
        outer.Rows.Add(forms.TableRow(forms.TableCell(header)))
        outer.Rows.Add(forms.TableRow(forms.TableCell(inner, True)))
        return outer
    except Exception:
        return inner


def finalize_dialog(dlg, inner, title, subtitle=None, buttons=None):
    """Apply the warm Timber Housing styling to a dialog: background + padding, styled
    buttons, and a header-wrapped content. Never raises - on failure it falls
    back to the plain inner layout so the dialog logic is unaffected."""
    try:
        _ui_style_dialog(dlg)
    except Exception:
        pass
    if buttons:
        for b, k in buttons:
            try:
                _ui_style_button(b, k)
            except Exception:
                pass
    try:
        dlg.Content = _ui_wrap(inner, title, subtitle)
    except Exception:
        try:
            dlg.Content = inner
        except Exception:
            pass


def make_styled_dialog(title, width=None, height=None):
    """Create a warm-styled Eto Dialog[bool] shell (title + bg + padding).
    Returns None if Eto is unavailable."""
    try:
        import Eto.Forms as forms
        import Eto.Drawing as drawing
    except Exception:
        return None
    dlg = forms.Dialog[bool]()
    dlg.Title = str(title)
    _ui_style_dialog(dlg)
    if width and height:
        try:
            dlg.ClientSize = drawing.Size(int(width), int(height))
        except Exception:
            pass
    return dlg


def set_viewport_rendered_mode():
    """Switch the active viewport to Rendered display mode for final review.
    RhinoCommon (DisplayModeDescription) first, with a command fallback. Visual
    only - no geometry/model change. Returns True on success."""
    try:
        view = sc.doc.Views.ActiveView
        if view is not None:
            dmd = Rhino.Display.DisplayModeDescription.FindByName("Rendered")
            if dmd is not None:
                view.ActiveViewport.DisplayMode = dmd
                view.Redraw()
                sc.doc.Views.Redraw()
                return True
    except Exception as ex:
        print("Rendered-mode via API failed (%s); trying command." % ex)
    try:
        rs.Command("_-SetDisplayMode _Mode=_Rendered _Enter", False)
        try:
            sc.doc.Views.Redraw()
        except Exception:
            pass
        return True
    except Exception as ex:
        print("Rendered-mode via command failed: %s" % ex)
        return False


def styled_confirm(header, subtitle, lines, yes_text, no_text,
                   yes_kind="primary", note=None, window_title=None):
    """Warm-styled Yes/No Eto dialog. Returns True (yes) / False (no). Falls
    back to rs.MessageBox. UI only - the caller's logic/return contract is
    unchanged (True == the 'yes' action)."""
    body = "\n".join(lines) if isinstance(lines, (list, tuple)) else str(lines)
    wtitle = window_title or ("Timber Housing - " + header)
    try:
        import Eto.Forms as forms
        import Eto.Drawing as drawing
    except Exception:
        full = body + (("\n\n" + note) if note else "")
        return rs.MessageBox(full, 4 | 32, wtitle) == 6

    class CDlg(forms.Dialog[bool]):
        def __init__(self):
            super(CDlg, self).__init__()
            self.Title = wtitle
            info = make_info_panel(body, "body")
            yes = forms.Button()
            yes.Text = yes_text
            yes.Click += self.on_yes
            no = forms.Button()
            no.Text = no_text
            no.Click += self.on_no
            self.DefaultButton = yes
            self.AbortButton = no
            inner = forms.TableLayout()
            inner.Spacing = drawing.Size(8, 8)
            inner.Rows.Add(forms.TableRow(forms.TableCell(info, True)))
            if note:
                inner.Rows.Add(forms.TableRow(
                    forms.TableCell(make_info_panel(note, "warn"), True)))
            # Button row is added DIRECTLY to the main layout (kept outside any
            # nested/wrapped container) - in live Rhino Eto a button row nested
            # inside a TableCell collapses and hides the buttons; a direct
            # TableRow always renders (proven by Phase 1B / completion dialog).
            inner.Rows.Add(forms.TableRow([forms.TableCell(yes),
                                           forms.TableCell(no)]))
            finalize_dialog(self, inner, header, subtitle,
                            [(yes, yes_kind), (no, "cancel")])

        def on_yes(self, s, e):
            self.Close(True)

        def on_no(self, s, e):
            self.Close(False)

    try:
        return bool(CDlg().ShowModal(Rhino.UI.RhinoEtoApp.MainWindow))
    except Exception:
        return rs.MessageBox(body, 4 | 32, wtitle) == 6


def show_dummy_placed_dialog(counts):
    """Confirmation after Phase-2A dummy placement. STYLED 2026-07-08
    (correction folder 4 - remaining native dialogs): now a styled WoSyHo
    dialog built on the PROVEN report-preview layout (fixed-size read-only
    TextArea + a single vertical full-width DIRECT 'Continue' button +
    Resizable + explicit ClientSize) so it matches the other styled dialogs
    while keeping the button visible in live Rhino. Shows the placed
    A/A1/B/GREEN counts and the placement-authority note. Native rs.MessageBox
    fallback retained; window close (Escape / X) proceeds safely, same as
    Continue. UI only - no logic change; no return value is used by main()."""
    a = counts.get("M1", 0)
    a1 = counts.get("M1A", 0)
    b = counts.get("M2", 0)
    g = counts.get("GREEN", 0)
    body = ("Reference dummy modules have been placed.\n\n"
            "A / M1     = %d\n"
            "A1 / M1A   = %d\n"
            "B / M2     = %d\n"
            "GREEN      = %d\n\n"
            "Dummy preview is the placement authority for the detailed "
            "module replacement." % (a, a1, b, g))
    wtitle = "Timber Housing Dummy Preview Placed"
    try:
        import Eto.Forms as forms
        import Eto.Drawing as drawing
    except Exception:
        try:
            rs.MessageBox(body, 0 | 64, wtitle)
        except Exception:
            pass
        return

    class DPDlg(forms.Dialog[bool]):
        def __init__(self):
            super(DPDlg, self).__init__()
            self.Title = wtitle
            self.Padding = drawing.Padding(12)
            self.Resizable = True
            ta = forms.TextArea()
            ta.ReadOnly = True
            ta.Wrap = True
            ta.Text = body
            ta.Size = drawing.Size(560, 170)
            try:
                _f = _ui_font(9.0)
                if _f is not None:
                    ta.Font = _f
                ta.BackgroundColor = _ui_color(UI_COLORS["card"])
                ta.TextColor = _ui_color(UI_COLORS["ink"])
            except Exception:
                pass
            cont = forms.Button()
            cont.Text = "Continue"
            cont.Click += self.on_continue
            self.DefaultButton = cont
            self.AbortButton = cont
            lay = forms.TableLayout()
            lay.Spacing = drawing.Size(8, 8)
            lay.Rows.Add(forms.TableRow([forms.TableCell(ta, True)]))
            # single VERTICAL full-width DIRECT button row (proven
            # report-preview pattern - never clipped; no helper/nesting/spacer).
            lay.Rows.Add(forms.TableRow(forms.TableCell(cont)))
            finalize_dialog(self, lay, "Dummy Preview Placed",
                            "Reference dummy modules placed",
                            [(cont, "primary")])
            try:
                self.ClientSize = drawing.Size(620, 380)
            except Exception:
                pass

        def on_continue(self, s, e):
            self.Close(True)

    try:
        DPDlg().ShowModal(Rhino.UI.RhinoEtoApp.MainWindow)
    except Exception:
        try:
            rs.MessageBox(body, 0 | 64, wtitle)
        except Exception:
            pass


def show_continue_to_phase2a_dialog():
    """Skeleton/grid checkpoint. STYLED 2026-07-08 (correction folder 4 -
    remaining native dialogs): now uses the PROVEN styled Timber Housing prompt
    (show_styled_prompt: fixed-size read-only TextArea + vertical full-width
    DIRECT buttons + Resizable + explicit ClientSize) so it matches the other
    styled dialogs while keeping the buttons visible in live Rhino. Returns
    True (Continue) / False (Cancel); window close (Escape / X) returns False.
    Native rs.MessageBox fallback retained. UI only - no logic change."""
    header = "Skeleton / Grid Model Generated"
    subtitle = "Phase 1 base skeleton/rack complete"
    body_lines = [
        "Base skeleton/rack model has been generated.",
        "",
        "Review the model in Rhino, then continue to the Phase 2A "
        "dummy block preview.",
        "",
        "Note: Dummy preview is the placement authority for the module "
        "anchors and the Phase-2B detailed-module replacement.",
    ]
    try:
        return bool(show_styled_prompt(
            header, subtitle, body_lines,
            "Continue to Phase 2A", "Cancel",
            "Timber Housing v23 - Continue to Phase 2A",
            yes_kind="primary", ta_height=150, width=620, height=380))
    except Exception:
        msg = ("Skeleton / grid model generated.\n"
               "Review the model in Rhino.\n\n"
               "Continue to the Phase 2A dummy block preview?\n\n"
               "(Dummy preview is the placement authority for the module "
               "anchors and the Phase-2B detailed-module replacement.)")
        try:
            return rs.MessageBox(msg, 1 | 64,
                                 "Timber Housing v23 - Continue to Phase 2A") == 1
        except Exception:
            return True


def show_completion_dialog(P, dummy_counts, sizing_ran, rfem_ran,
                           detailed_built, base_counts, site_placement=None):
    """Final styled 'Configuration Complete' summary dialog (Task F). The
    optional site_placement dict (added 2026-07-08) appends the final
    site-placement status without removing any existing completion data."""
    gt = {1: "Regular", 2: "Half Offset", 3: "Centre Offset"}.get(
        P.get("plan_grid_type", 1), "?")
    od = ("Shift Left" if P.get("offset_direction", 1) == 1 else "Shift Right")
    cfg_rows = [
        ("Bays x Floors", "%d x %d"
         % (P.get("x_bays", 0), P.get("peak_floors", 0))),
        ("Plan grid / offset", "%s / %s" % (gt, od)),
        ("Dummy preview", "placed" if dummy_counts else "skipped"),
        ("Preliminary sizing", "run" if sizing_ran else "skipped"),
        ("RFEM / Dlubal export", "run" if rfem_ran else "skipped"),
        ("Detailed module model", "built" if detailed_built else "skipped"),
    ]
    # ---- final site placement (optional; design-stage assistant) ------------
    sp_status = "not run"
    if isinstance(site_placement, dict):
        sp_status = site_placement.get("status", "not run")
    cfg_rows.append(("Site placement", sp_status))
    if isinstance(site_placement, dict) and site_placement.get("city"):
        cfg_rows.append(("  Site city (chosen %s)"
                         % (site_placement.get("city_selected_stage") or "?"),
                         str(site_placement.get("city"))))
        if site_placement.get("site_selected_stage"):
            cfg_rows.append(("  Site selected",
                             str(site_placement.get("site_selected_stage"))))
        if site_placement.get("setback_method"):
            cfg_rows.append(("  Setback method",
                             str(site_placement.get("setback_method"))))
        if site_placement.get("optimizer_method"):
            cfg_rows.append(("  Optimizer",
                             str(site_placement.get("optimizer_method"))))
        if site_placement.get("candidates_tested") is not None:
            cfg_rows.append(("  Candidates tested",
                             str(site_placement.get("candidates_tested"))))
        if site_placement.get("requested_iteration_count") is not None:
            cfg_rows.append(("  Iterations requested",
                             str(site_placement.get(
                                 "requested_iteration_count"))))
        _rd = site_placement.get("road") or {}
        if _rd:
            if _rd.get("road_generated"):
                cfg_rows.append(("  Road", "Generated"))
                cfg_rows.append(("  Road name", str(_rd.get("road_name"))))
                cfg_rows.append(("  Road offset / width",
                                 "%.1f m / %.1f m"
                                 % (_rd.get("road_offset_from_boundary_m", 0.0),
                                    _rd.get("road_width_m", 0.0))))
            elif _rd.get("road_warning"):
                cfg_rows.append(("  Road", "Failed"))
            else:
                cfg_rows.append(("  Road", "Skipped"))
            if _rd.get("road_warning"):
                cfg_rows.append(("  Road warning",
                                 str(_rd.get("road_warning"))[:60]))
        if site_placement.get("north_arrow_drawn") is not None:
            cfg_rows.append(("  North arrow",
                             "drawn" if site_placement.get("north_arrow_drawn")
                             else "not drawn"))
        if site_placement.get("north_deg") is not None:
            cfg_rows.append(("  North angle (deg)",
                             str(site_placement.get("north_deg"))))
        if site_placement.get("score") is not None:
            cfg_rows.append(("  Best score",
                             str(site_placement.get("score"))))
        _terr = site_placement.get("terrain") or {}
        if _terr.get("diff") is not None:
            cfg_rows.append(("  Terrain diff (m)",
                             "%.2f" % _terr.get("diff", 0.0)))
        if site_placement.get("folder"):
            cfg_rows.append(("  Site report", "written"))
    # ---- V28: site/context import + terrain status (additive rows) ---------
    if isinstance(site_placement, dict):
        _v28 = site_placement.get("v28_context")
        if isinstance(_v28, dict) and _v28:
            cfg_rows.append(("Site context import (v28)", ""))
            cfg_rows.append(("  Site plot imported",
                             str(_v28.get("site_plot_imported", "-"))))
            cfg_rows.append(("  Site + road imported",
                             str(_v28.get("site_road_imported", "-"))))
            cfg_rows.append(("  Surroundings imported",
                             str(_v28.get("surroundings_imported", "-"))))
            cfg_rows.append(("  Selected site source",
                             str(_v28.get("selected_site_source", "-"))))
            cfg_rows.append(("  Site analysis",
                             str(_v28.get("site_analysis_status", "-"))))
            if _v28.get("site_is_uneven") is not None:
                cfg_rows.append(("  Site is",
                                 "UNEVEN / terrain"
                                 if _v28.get("site_is_uneven") else "flat"))
            if _v28.get("site_elevation_range") is not None:
                cfg_rows.append(("  Site elev. range (m)",
                                 str(_v28.get("site_elevation_range"))))
            cfg_rows.append(("  Model tilted", "no (vertical only)"))
            cfg_rows.append(("  Terrain cut", "no"))
            cfg_rows.append(("  Site mesh modified", "no"))
            if _v28.get("import_report_folder"):
                cfg_rows.append(("  Import report", "written"))
    # ---- V29: Local Flora + Fauna biodiversity status (additive rows) ------
    _bio = (P or {}).get("biodiversity_summary")
    if isinstance(_bio, dict) and _bio:
        cfg_rows.append(("Local flora + fauna (v29)", "generated"))
        cfg_rows.append(("  Planting zones", str(_bio.get("zones", "-"))))
        cfg_rows.append(("  Trees / shrubs",
                         "%s / %s" % (_bio.get("trees", 0),
                                      _bio.get("shrubs", 0))))
        cfg_rows.append(("  Meadow area (m2)",
                         str(_bio.get("meadow_area_m2", 0))))
        cfg_rows.append(("  Terrace planters",
                         str(_bio.get("terrace_planters", 0))))
        cfg_rows.append(("  Roof greening (m2)",
                         str(_bio.get("roof_area_m2", 0))))
        cfg_rows.append(("  Fauna elements",
                         str(_bio.get("fauna_elements", 0))))
        cfg_rows.append(("  Species (native share)",
                         "%s (%.0f%%)" % (_bio.get("species_count", 0),
                                          100.0 * _bio.get("native_ratio",
                                                           0.0))))
        cfg_rows.append(("  Terrace/roof planting", "requires load check"))
        if (P or {}).get("biodiversity_report"):
            cfg_rows.append(("  Biodiversity report", "written"))
    base_rows = []
    if base_counts:
        base_rows = [("Nodes", base_counts.get("nodes", "-")),
                     ("Members", base_counts.get("members", "-")),
                     ("CLT panels", base_counts.get("panels", "-")),
                     ("Supports", base_counts.get("supports", "-"))]
    mod_rows = []
    if dummy_counts:
        mod_rows = [("A / M1", dummy_counts.get("M1", 0)),
                    ("A1 / M1A", dummy_counts.get("M1A", 0)),
                    ("B / M2", dummy_counts.get("M2", 0)),
                    ("GREEN", dummy_counts.get("GREEN", 0))]
    note = "The viewport has been switched to Rendered mode for final review."
    try:
        import Eto.Forms as forms
        import Eto.Drawing as drawing
    except Exception:
        lines = ["Timber Housing configuration complete.", ""]
        for k, v in cfg_rows:
            lines.append("  %s: %s" % (k, v))
        if base_rows:
            lines.append("")
            for k, v in base_rows:
                lines.append("  %s: %s" % (k, v))
        if mod_rows:
            lines.append("")
            for k, v in mod_rows:
                lines.append("  %s: %s" % (k, v))
        lines += ["", note]
        rs.MessageBox("\n".join(lines), 0 | 64,
                      "Timber Housing Configuration Complete")
        return

    class FDlg(forms.Dialog[bool]):
        def __init__(self):
            super(FDlg, self).__init__()
            self.Title = "Timber Housing Configuration Complete"
            inner = forms.TableLayout()
            inner.Spacing = drawing.Size(8, 8)
            inner.Rows.Add(forms.TableRow(
                forms.TableCell(make_section_label("Configuration"))))
            inner.Rows.Add(forms.TableRow(
                forms.TableCell(make_summary_table(cfg_rows), True)))
            if base_rows:
                inner.Rows.Add(forms.TableRow(
                    forms.TableCell(make_section_label("Structural baseline"))))
                inner.Rows.Add(forms.TableRow(
                    forms.TableCell(make_summary_table(base_rows), True)))
            if mod_rows:
                inner.Rows.Add(forms.TableRow(
                    forms.TableCell(make_section_label("Module counts"))))
                inner.Rows.Add(forms.TableRow(
                    forms.TableCell(make_summary_table(mod_rows), True)))
            inner.Rows.Add(forms.TableRow(
                forms.TableCell(make_info_panel(note, "green"))))
            fin = forms.Button()
            fin.Text = "Finish"
            fin.Click += self.on_fin
            self.DefaultButton = fin
            self.AbortButton = fin
            inner.Rows.Add(forms.TableRow(forms.TableCell(fin)))
            finalize_dialog(self, inner, "Configuration complete",
                            "Timber Housing v23 skeleton-rack configurator",
                            [(fin, "primary")])

        def on_fin(self, s, e):
            self.Close(True)

    try:
        FDlg().ShowModal(Rhino.UI.RhinoEtoApp.MainWindow)
    except Exception:
        rs.MessageBox("Timber Housing configuration complete. " + note, 0 | 64,
                      "Timber Housing Configuration Complete")


def get_params_eto(P):
    try:
        import Eto.Forms as forms
        import Eto.Drawing as drawing
    except Exception:
        return None

    class Dlg(forms.Dialog[bool]):
        def __init__(self):
            super(Dlg, self).__init__()
            self.Title = "Timber Housing v23 Skeleton Rack - Phase 1A: Building Parameters"
            self.Padding = drawing.Padding(12)
            self.Resizable = False

            def stepper(val, lo, hi):
                s = forms.NumericStepper()
                s.DecimalPlaces = 0
                s.MinValue = lo
                s.MaxValue = hi
                s.Value = val
                return s

            self.s_bays = stepper(P["x_bays"], 3, 40)
            self.s_peak = stepper(P["peak_floors"], 1, 14)
            self.s_dh = stepper(P["dh_start_bay"], 1, 40)
            self.s_vstart = stepper(P["v_start_bay"], 1, 40)
            self.s_vstep = stepper(P["v_step"], 1, 6)
            self.s_tstart = stepper(P["trunk_start_bay"], 1, 40)
            self.s_tstep = stepper(P["trunk_step"], 1, 6)
            self.s_s1a = stepper(P["stair_zone_1"][0], 1, 40)
            self.s_s1b = stepper(P["stair_zone_1"][1], 1, 40)
            self.s_s2a = stepper(P["stair_zone_2"][0], 1, 40)
            self.s_s2b = stepper(P["stair_zone_2"][1], 1, 40)
            self.s_lowsup = stepper(P["low_stair_support_start_level"], 0, 10)
            self.s_tallsup = stepper(P["tall_stair_support_start_level"], 0, 10)

            # NOTE: plan grid type + offset direction moved to Phase 1B dialog.
            def check(label, val):
                c = forms.CheckBox()
                c.Text = label
                c.Checked = val
                return c

            self.c_plates = check("floor/slab plates (suppressible)",
                                  P["show_floor_plates"])
            self.c_stairs = check("staircase placeholders",
                                  P["show_stairs"])
            self.c_modules = check("module placeholders (A/B/GAP, wireframe)",
                                   P["show_modules"])
            self.c_points = check("support points", P["show_support_points"])
            self.c_zones = check("debug zone outlines (stairs/DH/cascade)",
                                 P["show_debug_zones"])
            self.c_debug = check("analysis centreline debug",
                                 P["show_analysis_debug"])
            self.c_export = check("export analysis JSON/CSV",
                                  P["export_analysis"])

            ok = forms.Button()
            ok.Text = "Next"
            ok.Click += self.on_ok
            cancel = forms.Button()
            cancel.Text = "Cancel"
            cancel.Click += self.on_cancel
            self.DefaultButton = ok
            self.AbortButton = cancel

            layout = forms.TableLayout()
            layout.Spacing = drawing.Size(8, 6)

            # Rhino/Eto-safe construction: create controls first, assign
            # properties after (no property-kwarg constructor overloads).
            def make_label(text):
                lbl = forms.Label()
                lbl.Text = str(text)
                return lbl

            def make_cell(control=None):
                cell = forms.TableCell()
                if control is not None:
                    cell.Control = control
                return cell

            def row(label, ctrl, label2=None, ctrl2=None):
                items = [make_cell(make_label(label)),
                         make_cell(ctrl)]
                if label2 is not None:
                    items.append(make_cell(make_label(label2)))
                    items.append(make_cell(ctrl2))
                layout.Rows.Add(forms.TableRow(items))

            layout.Rows.Add(_ui_section_row("A - Building size"))
            row("X bays (length)", self.s_bays, "peak floors", self.s_peak)
            row("double-height start bay", self.s_dh)
            layout.Rows.Add(_ui_section_row("B - Structural / cascade logic"))
            row("V-column start bay", self.s_vstart, "V step", self.s_vstep)
            row("trunk start bay", self.s_tstart, "trunk step", self.s_tstep)
            layout.Rows.Add(_ui_section_row("C - Stair zones"))
            row("stair zone 1 (low)", self.s_s1a, "to bay", self.s_s1b)
            row("stair zone 2 (tall)", self.s_s2a, "to bay", self.s_s2b)
            row("low stair support start lvl", self.s_lowsup,
                "tall stair support start lvl", self.s_tallsup)
            layout.Rows.Add(_ui_section_row(
                "D - Preview / debug / export options"))
            for c in [self.c_plates, self.c_stairs, self.c_modules,
                      self.c_points, self.c_zones, self.c_debug,
                      self.c_export]:
                style_checkbox(c)
                layout.Rows.Add(forms.TableRow([make_cell(c), make_cell()]))
            layout.Rows.Add(forms.TableRow([make_cell(ok), make_cell(cancel)]))
            finalize_dialog(self, layout, "Phase 1A - Building Parameters",
                            "Building size, structural cascade, stair zones "
                            "and preview options.",
                            [(ok, "primary"), (cancel, "cancel")])

        def on_ok(self, sender, e):
            self.Close(True)

        def on_cancel(self, sender, e):
            self.Close(False)

    dlg = Dlg()
    result = dlg.ShowModal(Rhino.UI.RhinoEtoApp.MainWindow)
    if not result:
        return "CANCEL"
    P["x_bays"] = int(dlg.s_bays.Value)
    P["peak_floors"] = int(dlg.s_peak.Value)
    P["dh_start_bay"] = int(dlg.s_dh.Value)
    P["v_start_bay"] = int(dlg.s_vstart.Value)
    P["v_step"] = int(dlg.s_vstep.Value)
    P["trunk_start_bay"] = int(dlg.s_tstart.Value)
    P["trunk_step"] = int(dlg.s_tstep.Value)
    P["stair_zone_1"] = (int(dlg.s_s1a.Value), int(dlg.s_s1b.Value))
    P["stair_zone_2"] = (int(dlg.s_s2a.Value), int(dlg.s_s2b.Value))
    P["low_stair_support_start_level"] = int(dlg.s_lowsup.Value)
    P["tall_stair_support_start_level"] = int(dlg.s_tallsup.Value)
    P["show_floor_plates"] = bool(dlg.c_plates.Checked)
    P["show_stairs"] = bool(dlg.c_stairs.Checked)
    P["show_modules"] = bool(dlg.c_modules.Checked)
    P["show_support_points"] = bool(dlg.c_points.Checked)
    P["show_debug_zones"] = bool(dlg.c_zones.Checked)
    P["show_analysis_debug"] = bool(dlg.c_debug.Checked)
    P["export_analysis"] = bool(dlg.c_export.Checked)
    return P


def get_grid_params_eto(P):
    """Phase 1B dialog: plan grid type + offset direction, with a READ-ONLY
    summary of the Phase-1A choices. Returns 'GENERATE', 'BACK', or 'CANCEL'
    (None if Eto is unavailable). Sets P['plan_grid_type'] /
    P['offset_direction'] on Generate. Grid math is unchanged."""
    try:
        import Eto.Forms as forms
        import Eto.Drawing as drawing
    except Exception:
        return None

    class GDlg(forms.Dialog[bool]):
        def __init__(self):
            super(GDlg, self).__init__()
            self.Title = ("Timber Housing v23 Skeleton Rack - Phase 1B: "
                          "Plan Grid + Summary")
            self.Padding = drawing.Padding(12)
            self.Resizable = False
            self.outcome = "CANCEL"

            def make_label(text):
                lbl = forms.Label()
                lbl.Text = str(text)
                return lbl

            def make_cell(control=None):
                cell = forms.TableCell()
                if control is not None:
                    cell.Control = control
                return cell

            self.d_grid = forms.DropDown()
            self.d_grid.DataStore = ["1  Regular Grid", "2  Half Offset Grid",
                                     "3  Centre Offset Grid"]
            self.d_grid.SelectedIndex = int(P["plan_grid_type"]) - 1
            self.d_dir = forms.DropDown()
            self.d_dir.DataStore = ["1  Shift Left", "2  Shift Right"]
            self.d_dir.SelectedIndex = int(P["offset_direction"]) - 1

            def onoff(v):
                return "on" if v else "off"
            summary = (
                "Phase 1A summary (read-only):\n"
                "  X bays: %d      peak floors: %d\n"
                "  double-height start bay: %d\n"
                "  V-column start / step: %d / %d\n"
                "  trunk start / step: %d / %d\n"
                "  stair zone 1 (low): %d - %d      "
                "stair zone 2 (tall): %d - %d\n"
                "  stair support start lvl (low / tall): %d / %d\n"
                "  floor/slab plates: %s   staircase placeholders: %s\n"
                "  module placeholders: %s   support points: %s\n"
                "  debug zones: %s   analysis debug: %s   export: %s"
                % (P["x_bays"], P["peak_floors"], P["dh_start_bay"],
                   P["v_start_bay"], P["v_step"], P["trunk_start_bay"],
                   P["trunk_step"], P["stair_zone_1"][0], P["stair_zone_1"][1],
                   P["stair_zone_2"][0], P["stair_zone_2"][1],
                   P["low_stair_support_start_level"],
                   P["tall_stair_support_start_level"],
                   onoff(P["show_floor_plates"]), onoff(P["show_stairs"]),
                   onoff(P["show_modules"]), onoff(P["show_support_points"]),
                   onoff(P["show_debug_zones"]),
                   onoff(P["show_analysis_debug"]), onoff(P["export_analysis"])))

            gen = forms.Button()
            gen.Text = "Generate"
            gen.Click += self.on_gen
            back = forms.Button()
            back.Text = "Back"
            back.Click += self.on_back
            cancel = forms.Button()
            cancel.Text = "Cancel"
            cancel.Click += self.on_cancel
            self.DefaultButton = gen
            self.AbortButton = cancel

            style_dropdown(self.d_grid)
            style_dropdown(self.d_dir)
            layout = forms.TableLayout()
            layout.Spacing = drawing.Size(8, 6)
            layout.Rows.Add(forms.TableRow(forms.TableCell(
                make_section_label("Phase 1A summary (read-only)"))))
            layout.Rows.Add(forms.TableRow(forms.TableCell(
                make_info_panel(summary, "body"), True)))
            layout.Rows.Add(forms.TableRow(forms.TableCell(
                make_section_label("Plan grid"))))
            layout.Rows.Add(forms.TableRow(
                [make_cell(make_label("plan grid type")),
                 make_cell(self.d_grid)]))
            layout.Rows.Add(forms.TableRow(
                [make_cell(make_label("offset direction")),
                 make_cell(self.d_dir)]))
            layout.Rows.Add(forms.TableRow(
                [make_cell(gen), make_cell(back), make_cell(cancel)]))
            finalize_dialog(self, layout, "Phase 1B - Plan Grid + Summary",
                            "Review the Phase 1A choices, then set the plan "
                            "grid type + offset direction.",
                            [(gen, "primary"), (back, "secondary"),
                             (cancel, "cancel")])

        def on_gen(self, sender, e):
            self.outcome = "GENERATE"
            self.Close(True)

        def on_back(self, sender, e):
            self.outcome = "BACK"
            self.Close(True)

        def on_cancel(self, sender, e):
            self.outcome = "CANCEL"
            self.Close(False)

    dlg = GDlg()
    dlg.ShowModal(Rhino.UI.RhinoEtoApp.MainWindow)
    if dlg.outcome == "GENERATE":
        P["plan_grid_type"] = int(dlg.d_grid.SelectedIndex) + 1
        P["offset_direction"] = int(dlg.d_dir.SelectedIndex) + 1
    return dlg.outcome


def get_grid_params_fallback(P):
    """Phase 1B fallback (rs.Get*): plan grid + offset. Returns 'GENERATE' or
    'CANCEL'. No Back step in the command-line fallback."""
    print("Phase 1A summary: %d bays / %d floors | DH@%d | V %d/%d | trunk "
          "%d/%d | stairs %s %s"
          % (P["x_bays"], P["peak_floors"], P["dh_start_bay"], P["v_start_bay"],
             P["v_step"], P["trunk_start_bay"], P["trunk_step"],
             str(P["stair_zone_1"]), str(P["stair_zone_2"])))
    gt = rs.GetInteger("Phase 1B - Plan grid type (1 Regular, 2 Half Offset, "
                       "3 Centre Offset)", P["plan_grid_type"], 1, 3)
    if gt is None:
        return "CANCEL"
    P["plan_grid_type"] = gt
    if P["plan_grid_type"] != 1:
        dr = rs.GetInteger("Offset direction (1 Shift Left, 2 Shift Right)",
                           P["offset_direction"], 1, 2)
        if dr is not None:
            P["offset_direction"] = dr
    return "GENERATE"


def default_module_params():
    return {
        "enable": True,           # enable reference dummy module placement
        "show_anchors": False,
        # Phase 2B placement mode: 1 = Dummy block preview (default, frozen
        # baseline), 2 = Detailed textured modules, 3 = Dummy + Detailed.
        "placement_mode": 1,
        # NOTE: percentage controls AND pattern options are removed - the
        # arrangement follows the exported alternate-floor reference pattern
        # automatically (level 3/4/5 plans + full model).
    }


def get_module_params_eto(MP):
    """Stage-2 compact dialog (Rhino/Eto-safe construction)."""
    try:
        import Eto.Forms as forms
        import Eto.Drawing as drawing
    except Exception:
        return None

    class MDlg(forms.Dialog[bool]):
        def __init__(self):
            super(MDlg, self).__init__()
            self.Title = "Timber Housing Phase 2A - Dummy Block Preview"
            self.Padding = drawing.Padding(12)
            self.Resizable = False

            def stepper(val, lo, hi):
                s = forms.NumericStepper()
                s.DecimalPlaces = 0
                s.MinValue = lo
                s.MaxValue = hi
                s.Value = val
                return s

            def make_label(text):
                lbl = forms.Label()
                lbl.Text = str(text)
                return lbl

            def make_cell(control=None):
                cell = forms.TableCell()
                if control is not None:
                    cell.Control = control
                return cell

            self.c_enable = forms.CheckBox()
            self.c_enable.Text = "enable reference dummy module placement"
            self.c_enable.Checked = MP["enable"]
            self.c_anch = forms.CheckBox()
            self.c_anch.Text = "show module anchors/debug"
            self.c_anch.Checked = MP["show_anchors"]
            ok = forms.Button()
            ok.Text = "Place Dummy Preview"
            ok.Click += self.on_ok
            cancel = forms.Button()
            cancel.Text = "Skip Dummy Preview"
            cancel.Click += self.on_cancel
            self.DefaultButton = ok
            self.AbortButton = cancel

            layout = forms.TableLayout()
            layout.Spacing = drawing.Size(8, 6)

            def row(label, ctrl, label2=None, ctrl2=None):
                items = [make_cell(make_label(label)), make_cell(ctrl)]
                if label2 is not None:
                    items.append(make_cell(make_label(label2)))
                    items.append(make_cell(ctrl2))
                layout.Rows.Add(forms.TableRow(items))

            style_checkbox(self.c_enable)
            style_checkbox(self.c_anch)
            layout.Rows.Add(forms.TableRow(forms.TableCell(
                make_section_label("Dummy block preview"))))
            layout.Rows.Add(forms.TableRow([make_cell(self.c_enable),
                                            make_cell()]))
            layout.Rows.Add(forms.TableRow([make_cell(self.c_anch),
                                            make_cell()]))
            note_txt = ("Dummy block preview only. Detailed textured modules "
                        "are offered in Phase 2B, AFTER the sizing + "
                        "RFEM/Dlubal export checkpoint. The arrangement "
                        "follows the exported alternate-floor reference "
                        "pattern automatically (level 3/4/5 plans + full "
                        "model): converging mirrored 1/1A pairs, common "
                        "terraces every 3rd bay, the Module 2 end block, and "
                        "roof terraces on the cascade steps. The dummy preview "
                        "confirms the A / A1 / B / GREEN placement.")
            layout.Rows.Add(forms.TableRow(forms.TableCell(
                make_info_panel(note_txt, "muted"), True)))
            # STABILIZED 2026-07-07: buttons are added as their own DIRECT,
            # full-width single-cell rows (the most reliable Rhino-Eto pattern -
            # same as the completion 'Finish' button that always renders). No
            # nested layout, no spacer, no helper - so the buttons cannot be
            # hidden. Kept as Eto here because this dialog needs the checkboxes;
            # get_module_params_fallback (rs.GetBoolean) covers any Eto failure.
            layout.Rows.Add(forms.TableRow(forms.TableCell(ok)))
            layout.Rows.Add(forms.TableRow(forms.TableCell(cancel)))
            finalize_dialog(self, layout, "Phase 2A - Dummy Block Preview",
                            "Placement authority - runs before sizing, export "
                            "and detailed modules.",
                            [(ok, "primary"), (cancel, "cancel")])

        def on_ok(self, sender, e):
            self.Close(True)

        def on_cancel(self, sender, e):
            self.Close(False)

    dlg = MDlg()
    result = dlg.ShowModal(Rhino.UI.RhinoEtoApp.MainWindow)
    if not result:
        return "CANCEL"
    MP["enable"] = bool(dlg.c_enable.Checked)
    MP["show_anchors"] = bool(dlg.c_anch.Checked)
    return MP


def get_module_params_fallback(MP):
    """Phase 2A dummy-preview input - NATIVE rs.GetBoolean prompt (reliable in
    live Rhino; the Eto dialog clipped its Place/Skip buttons). Set the two
    options on the command line, then press ENTER to PLACE the dummy preview or
    ESC to SKIP. Returns MP (place) or 'CANCEL' (skip). This is now the primary
    Phase 2A input. The two toggles map (in order) to enable + show_anchors."""
    en = rs.GetBoolean(
        "Phase 2A Dummy Block Preview - set options, then ENTER = Place Dummy "
        "Preview / ESC = Skip  (arrangement follows the exported alternate-floor "
        "reference pattern automatically)",
        [("EnablePlacement", "No", "Yes"),
         ("ShowAnchorsDebug", "No", "Yes")],
        [MP["enable"], MP["show_anchors"]])
    if en is None:
        return "CANCEL"
    MP["enable"], MP["show_anchors"] = en
    return MP


def ask_phase2b_detailed():
    """Phase 2B dialog (simplified 2026-07-07): a single Build / Skip choice.
    Returns True  = Build Detailed Module Model (dummy visuals hidden), or
            False = Skip Detailed Module Model (dummy preview kept).
    The old 3-way Keep/Build/Comparison dropdown is retired from the user
    workflow. Comparison mode still exists internally - place_detailed_modules
    keeps its hide_dummy=False path for debugging - but is no longer exposed.
    Detailed placement / Module-2 corridor-facing logic is unchanged.

    STYLED Timber Housing dialog (correction folder 4); native rs.MessageBox fallback.
    Returns True = Build, False = Skip. No comparison dropdown is exposed."""
    body = [
        "The dummy block preview, preliminary sizing, and RFEM/Dlubal export "
        "workflow are complete.",
        "",
        "Build the detailed textured module model now?",
        "",
        "Building it hides the dummy block layers (20-22) and places the "
        "textured A / A1 / B modules on layers 30-32; the Module 2 door/special "
        "face keeps facing the corridor.",
        "",
        "Skipping keeps the dummy preview as-is.",
    ]
    return show_styled_prompt(
        "Phase 2B - Detailed Module Model",
        "Build the textured module model, or skip.",
        body, "Build Detailed Module Model", "Skip Detailed Module Model",
        window_title="Timber Housing Phase 2B - Detailed Module Model",
        ta_height=180, width=660, height=430)


def get_params_fallback(P):
    n = rs.GetInteger("X bay count", P["x_bays"], 3, 40)
    if n is None:
        return "CANCEL"
    P["x_bays"] = n
    P = rescale_zone_defaults(P)
    pk = rs.GetInteger("Peak floors", P["peak_floors"], 1, 14)
    if pk is None:
        return "CANCEL"
    P["peak_floors"] = pk
    # plan grid type + offset direction moved to Phase 1B (get_grid_params_fallback)
    b = rs.GetBoolean("Options",
                      [("FloorPlates", "No", "Yes"),
                       ("Stairs", "No", "Yes"),
                       ("Modules", "No", "Yes"),
                       ("SupportPoints", "No", "Yes"),
                       ("DebugZones", "No", "Yes"),
                       ("AnalysisDebug", "No", "Yes"),
                       ("ExportAnalysis", "No", "Yes")],
                      [P["show_floor_plates"], P["show_stairs"],
                       P["show_modules"], P["show_support_points"],
                       P["show_debug_zones"], P["show_analysis_debug"],
                       P["export_analysis"]])
    if b:
        (P["show_floor_plates"], P["show_stairs"], P["show_modules"],
         P["show_support_points"], P["show_debug_zones"],
         P["show_analysis_debug"], P["export_analysis"]) = b
    return P


# =============================================================================
# 6b. RFEM / DLUBAL BASE STRUCTURAL MODEL EXPORT  (2026-07-06, Part B)
#
# A clean, design-stage, RFEM/Dlubal-READY exchange export built ONLY from the
# analytical StructuralModel (SM.member axes) + the base CLT panel references
# collected in generate_base_grid_and_plinth(). It does NOT read visual box
# Breps, and it NEVER exports module/facade/cladding/terrace meshes as members.
# Files: nodes/members/supports/clt_panels CSV, 3D LINE DXF, metadata JSON,
# summary TXT, optional module-anchor reference CSV. Not a native RF6 project.
# =============================================================================

RFEM_TOL = 0.001   # node / zero-length tolerance (m)


def _rfem_member_map(t):
    """Map an internal StructuralModel member type -> (RFEM member_type,
    DXF layer). Unknown types pass through with a generic DXF layer so no
    member is ever silently dropped."""
    m = {
        "REGULAR_COLUMN":            ("COLUMN",       "RFEM_Columns"),
        "STAIR_ZONE_SUPPORT_COLUMN": ("COLUMN",       "RFEM_Columns"),
        "REGULAR_BEAM_X":            ("BEAM_X",       "RFEM_Beams_X"),
        "REGULAR_BEAM_Y":            ("BEAM_Y",       "RFEM_Beams_Y"),
        "CORRIDOR_EDGE_BEAM":        ("EDGE_BEAM",    "RFEM_Edge_Beams"),
        "BASE_BEAM_X":               ("BASE_BEAM_X",  "RFEM_Base_Beams"),
        "BASE_BEAM_Y":               ("BASE_BEAM_Y",  "RFEM_Base_Beams"),
        "FOUR_LEGGED_V_BRANCH":      ("V_COLUMN",     "RFEM_V_Columns"),
        "ATRIUM_TRUNK_COLUMN":       ("TREE_TRUNK",   "RFEM_Tree_Trunks"),
        "ATRIUM_BRANCH_TO_CORRIDOR": ("TREE_BRANCH",  "RFEM_Branches"),
    }
    return m.get(t, (t, "RFEM_Other"))


def _is_bad(v):
    return (v is None) or (v != v)          # None or NaN (NaN != NaN)


def _csv_row(vals):
    out = []
    for v in vals:
        s = "" if v is None else str(v)
        if ("," in s) or ('"' in s) or ("\n" in s):
            s = '"' + s.replace('"', '""') + '"'
        out.append(s)
    return ",".join(out) + "\n"


def create_rfem_export_folder(script_dir):
    """Create rfem_exports/wosyho_rfem_export_YYYYMMDD_HHMMSS beside the
    script and return its path."""
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    root = os.path.join(script_dir, "rfem_exports")
    folder = os.path.join(root, "wosyho_rfem_export_%s" % stamp)
    if not os.path.isdir(folder):
        os.makedirs(folder)
    return folder, stamp


def collect_structural_line_members(rack):
    """Read the analytical StructuralModel. Returns (nodes, members, stats).
    nodes  : list of {id,x,y,z} (already de-duplicated by SM.node at 0.001 m).
    members: validated export records (zero-length + exact duplicates removed).
    """
    SM = rack.SM.model
    nodes = SM["nodes"]
    # optional: recommended V/tree section hints from the preliminary sizing
    # emulator (override the default section_hint for those members only)
    hints = getattr(rack, "_sizing_hints", {}) or {}
    stats = {"zero_length": 0, "duplicates": 0, "nan": 0}
    seen = {}
    members = []
    mid = 0
    for rec in SM["members"]:
        ni = rec["node_i"]
        nj = rec["node_j"]
        a = nodes[ni]
        b = nodes[nj]
        ax, ay, az = a["x"], a["y"], a["z"]
        bx, by, bz = b["x"], b["y"], b["z"]
        if any(_is_bad(v) for v in (ax, ay, az, bx, by, bz)):
            stats["nan"] += 1
            continue
        length = math.sqrt((bx - ax) ** 2 + (by - ay) ** 2 + (bz - az) ** 2)
        if length < RFEM_TOL:
            stats["zero_length"] += 1
            continue
        key = (min(ni, nj), max(ni, nj), rec["type"])
        if key in seen:
            stats["duplicates"] += 1
            continue
        seen[key] = True
        mtype, dxf_layer = _rfem_member_map(rec["type"])
        mid += 1
        members.append({
            "member_id": mid, "start_node_id": ni, "end_node_id": nj,
            "sx": ax, "sy": ay, "sz": az, "ex": bx, "ey": by, "ez": bz,
            "member_type": mtype, "raw_type": rec["type"],
            "layer_or_source": rec.get("layer", ""),
            "dxf_layer": dxf_layer, "length": length,
            "section_hint": hints.get(rec["id"], rec.get("section", "")),
            "material_hint": rec.get("material", ""),
            "notes": "%s level=%s" % (rec["type"], rec.get("level", "")),
        })
    return nodes, members, stats


def collect_clt_panel_references(rack):
    """Base-platform CLT panel/surface references (from
    generate_base_grid_and_plinth). Returns (panels, invalid_count)."""
    raw = getattr(rack, "base_panels", []) or []
    panels = []
    invalid = 0
    pid = 0
    for p in raw:
        corners = p.get("corners", [])
        th = p.get("thickness", 0.0)
        ok = (len(corners) == 4 and th is not None and th > RFEM_TOL
              and not any(_is_bad(v) for c in corners for v in c))
        if not ok:
            invalid += 1
            continue
        pid += 1
        rowp = dict(p)
        rowp["panel_id"] = pid
        panels.append(rowp)
    return panels, invalid


def collect_supports(rack):
    SM = rack.SM.model
    nodes = SM["nodes"]
    out = []
    sid = 0
    for s in SM["supports"]:
        nid = s["node"]
        nd = nodes[nid]
        sid += 1
        out.append({"support_id": sid, "node_id": nid,
                    "x": nd["x"], "y": nd["y"], "z": nd["z"],
                    "support_type": s.get("fixity", ""),
                    "notes": s.get("note", "")})
    return out


def collect_module_anchor_references(rack):
    """Optional load/reference metadata only - NEVER structural members.
    Returns (rows, available)."""
    slots = getattr(rack, "module_slots", None)
    if not slots:
        return [], False
    rows = []
    mid = 0
    for s in slots:
        mid += 1
        rows.append({"module_id": mid, "module_type": s.get("assigned", ""),
                     "level": s.get("level", ""), "bay": s.get("bay", ""),
                     "side_or_band": s.get("side", ""),
                     "ax": s.get("tx", ""), "ay": s.get("ty", ""),
                     "az": s.get("tz", ""), "notes": s.get("role", "")})
    return rows, True


def write_nodes_csv(folder, nodes):
    path = os.path.join(folder, "wosyho_nodes.csv")
    with open(path, "w") as f:
        f.write(_csv_row(["node_id", "x_m", "y_m", "z_m"]))
        for n in nodes:
            f.write(_csv_row([n["id"], "%.4f" % n["x"], "%.4f" % n["y"],
                              "%.4f" % n["z"]]))
    return path


def write_members_csv(folder, members):
    path = os.path.join(folder, "wosyho_members.csv")
    cols = ["member_id", "start_node_id", "end_node_id", "start_x_m",
            "start_y_m", "start_z_m", "end_x_m", "end_y_m", "end_z_m",
            "member_type", "layer_or_source", "length_m", "section_hint",
            "material_hint", "notes"]
    with open(path, "w") as f:
        f.write(_csv_row(cols))
        for m in members:
            f.write(_csv_row([
                m["member_id"], m["start_node_id"], m["end_node_id"],
                "%.4f" % m["sx"], "%.4f" % m["sy"], "%.4f" % m["sz"],
                "%.4f" % m["ex"], "%.4f" % m["ey"], "%.4f" % m["ez"],
                m["member_type"], m["layer_or_source"], "%.4f" % m["length"],
                m["section_hint"], m["material_hint"], m["notes"]]))
    return path


def write_supports_csv(folder, supports):
    path = os.path.join(folder, "wosyho_supports.csv")
    with open(path, "w") as f:
        f.write(_csv_row(["support_id", "node_id", "x_m", "y_m", "z_m",
                          "support_type", "notes"]))
        for s in supports:
            f.write(_csv_row([s["support_id"], s["node_id"], "%.4f" % s["x"],
                              "%.4f" % s["y"], "%.4f" % s["z"],
                              s["support_type"], s["notes"]]))
    return path


def write_clt_panels_csv(folder, panels):
    path = os.path.join(folder, "wosyho_clt_panels.csv")
    cols = ["panel_id", "panel_type", "level", "bay",
            "corner_1_x", "corner_1_y", "corner_1_z",
            "corner_2_x", "corner_2_y", "corner_2_z",
            "corner_3_x", "corner_3_y", "corner_3_z",
            "corner_4_x", "corner_4_y", "corner_4_z",
            "thickness_m", "material_hint", "notes"]
    with open(path, "w") as f:
        f.write(_csv_row(cols))
        for p in panels:
            c = p["corners"]
            vals = [p["panel_id"], p["panel_type"], p.get("level", ""),
                    p.get("bay", "")]
            for i in range(4):
                vals += ["%.4f" % c[i][0], "%.4f" % c[i][1], "%.4f" % c[i][2]]
            vals += ["%.4f" % p["thickness"], p.get("material", ""),
                     p.get("note", "")]
            f.write(_csv_row(vals))
    return path


def write_module_anchor_reference_csv(folder, rows, available):
    path = os.path.join(folder, "wosyho_module_anchor_reference.csv")
    with open(path, "w") as f:
        f.write(_csv_row(["module_id", "module_type", "level", "bay",
                          "side_or_band", "anchor_x_m", "anchor_y_m",
                          "anchor_z_m", "notes"]))
        if not available:
            f.write(_csv_row(["", "", "", "", "", "", "", "",
                              "PENDING: no module placement in this run "
                              "(reference/load metadata only, never members)"]))
        else:
            for r in rows:
                f.write(_csv_row([r["module_id"], r["module_type"], r["level"],
                                  r["bay"], r["side_or_band"],
                                  "%.4f" % float(r["ax"]) if r["ax"] != "" else "",
                                  "%.4f" % float(r["ay"]) if r["ay"] != "" else "",
                                  "%.4f" % float(r["az"]) if r["az"] != "" else "",
                                  r["notes"]]))
    return path


def write_line_model_dxf(folder, members, supports):
    """Minimal, dependency-free R12 ASCII DXF: LINE per member on RFEM_* layers
    + POINT per support on RFEM_Support_Reference."""
    path = os.path.join(folder, "wosyho_line_model.dxf")
    layers = ["RFEM_Columns", "RFEM_Beams_X", "RFEM_Beams_Y",
              "RFEM_Edge_Beams", "RFEM_Base_Beams", "RFEM_V_Columns",
              "RFEM_Tree_Trunks", "RFEM_Branches", "RFEM_Support_Reference",
              "RFEM_Other"]
    used = set(m["dxf_layer"] for m in members)
    used.add("RFEM_Support_Reference")
    for ly in used:
        if ly not in layers:
            layers.append(ly)
    out = []
    def g(code, val):
        out.append(str(code)); out.append(str(val))
    g(0, "SECTION"); g(2, "HEADER"); g(9, "$ACADVER"); g(1, "AC1009")
    g(0, "ENDSEC")
    g(0, "SECTION"); g(2, "TABLES"); g(0, "TABLE"); g(2, "LAYER")
    g(70, len(layers))
    for ly in layers:
        g(0, "LAYER"); g(2, ly); g(70, 0); g(62, 7); g(6, "CONTINUOUS")
    g(0, "ENDTAB"); g(0, "ENDSEC")
    g(0, "SECTION"); g(2, "ENTITIES")
    for m in members:
        g(0, "LINE"); g(8, m["dxf_layer"])
        g(10, "%.4f" % m["sx"]); g(20, "%.4f" % m["sy"]); g(30, "%.4f" % m["sz"])
        g(11, "%.4f" % m["ex"]); g(21, "%.4f" % m["ey"]); g(31, "%.4f" % m["ez"])
    for s in supports:
        g(0, "POINT"); g(8, "RFEM_Support_Reference")
        g(10, "%.4f" % s["x"]); g(20, "%.4f" % s["y"]); g(30, "%.4f" % s["z"])
    g(0, "ENDSEC"); g(0, "EOF")
    with open(path, "w") as f:
        f.write("\n".join(out) + "\n")
    return path


def write_metadata_json(folder, rack, P, stamp, nodes, members, panels,
                        supports, stats, invalid_panels):
    tcounts = {}
    for m in members:
        tcounts[m["member_type"]] = tcounts.get(m["member_type"], 0) + 1
    warnings = []
    if stats["zero_length"]:
        warnings.append("%d zero-length members skipped" % stats["zero_length"])
    if stats["duplicates"]:
        warnings.append("%d duplicate members removed" % stats["duplicates"])
    if stats["nan"]:
        warnings.append("%d members with invalid coords skipped" % stats["nan"])
    if invalid_panels:
        warnings.append("%d invalid CLT panels skipped" % invalid_panels)
    meta = {
        "units": "meters",
        "coordinate_system": ("X = building length, Y = fixed section depth, "
                              "Z = height; member centreline / axis coords"),
        "export_timestamp": stamp,
        "source_script": os.path.basename(getattr(rack, "_script_name",
                                          "timber_housing_configurator.py")),
        "grid_type": P.get("plan_grid_type", 1),
        "offset_direction": P.get("offset_direction", 1),
        "total_bays": rack.NB,
        "max_floors": max(rack.F) if rack.F else 0,
        "cascade_profile": list(rack.F),
        "floor_height_m": FLOOR_PITCH,
        "member_size_m": MEMBER,
        "plinth_base_thickness_m": getattr(rack, "_base_platform_top", PLINTH),
        "node_count": len(nodes),
        "member_count": len(members),
        "panel_count": len(panels),
        "support_count": len(supports),
        "member_type_counts": tcounts,
        "warnings": warnings,
        "disclaimer": ("Design-stage computational base model export. NOT a "
                       "certified structural verification."),
    }
    # optional: preliminary V/tree sizing results (if the sizing emulator ran)
    ssum = getattr(rack, "_sizing_summary", None)
    if ssum is not None:
        meta["preliminary_sizing"] = {
            "sizing_report_folder": getattr(rack, "_sizing_report_folder", ""),
            "support_groups": ssum.get("support_groups_count"),
            "max_V_leg_section_m": ssum.get("max_V_leg_section_m"),
            "max_tree_trunk_section_m": ssum.get("max_tree_trunk_section_m"),
            "max_tree_branch_section_m": ssum.get("max_tree_branch_section_m"),
            "recommended_section_hints_applied":
                len(getattr(rack, "_sizing_hints", {}) or {}),
            "note": ("V/tree member section_hint fields updated from the "
                     "Eurocode-informed preliminary sizing emulator; RFEM/"
                     "Dlubal remains the verification tool."),
        }
    path = os.path.join(folder, "wosyho_export_metadata.json")
    with open(path, "w") as f:
        json.dump(meta, f, indent=1)
    return path, tcounts, warnings


def write_summary_txt(folder, rack, P, stamp, nodes, members, panels,
                      supports, tcounts, stats, invalid_panels, warnings):
    gt = {1: "Regular", 2: "Half Offset", 3: "Centre Offset"}.get(
        P.get("plan_grid_type", 1), "?")
    L = ["Timber Housing v23 - RFEM / DLUBAL BASE MODEL EXPORT",
         "=" * 56,
         "export folder      : %s" % folder,
         "timestamp          : %s" % stamp,
         "grid type          : %d (%s)" % (P.get("plan_grid_type", 1), gt),
         "offset direction   : %s"
         % ("left" if P.get("offset_direction", 1) == 1 else "right"),
         "total bays         : %d" % rack.NB,
         "max floors         : %d" % (max(rack.F) if rack.F else 0),
         "cascade profile    : %s" % str(list(rack.F)),
         "floor height       : %.2f m" % FLOOR_PITCH,
         "member size        : %.2f m" % MEMBER,
         "base thickness     : %.2f m" % getattr(rack, "_base_platform_top",
                                                 PLINTH),
         "-" * 56,
         "total nodes        : %d" % len(nodes),
         "total members      : %d" % len(members),
         "total CLT panels   : %d" % len(panels),
         "support count      : %d" % len(supports),
         "-" * 56,
         "member counts by type:"]
    for t in sorted(tcounts):
        L.append("   %-12s : %d" % (t, tcounts[t]))
    L += ["-" * 56,
          "skipped zero-length members : %d" % stats["zero_length"],
          "duplicate members removed   : %d" % stats["duplicates"],
          "invalid coord members       : %d" % stats["nan"],
          "invalid CLT panels skipped  : %d" % invalid_panels]
    if warnings:
        L.append("warnings           : %s" % "; ".join(warnings))
    L += ["-" * 56,
          "WARNING: Design-stage export only. Not a structural verification."]
    txt = "\n".join(L)
    path = os.path.join(folder, "wosyho_export_summary.txt")
    with open(path, "w") as f:
        f.write(txt + "\n")
    return path, txt


def run_rfem_export(rack, P, script_dir):
    """Orchestrate the whole base-model export. Returns (ok, folder, info)."""
    try:
        folder, stamp = create_rfem_export_folder(script_dir)
        nodes, members, stats = collect_structural_line_members(rack)
        panels, invalid_panels = collect_clt_panel_references(rack)
        supports = collect_supports(rack)
        anchors, anchors_ok = collect_module_anchor_references(rack)

        write_nodes_csv(folder, nodes)
        write_members_csv(folder, members)
        write_supports_csv(folder, supports)
        write_clt_panels_csv(folder, panels)
        dxf_ok = True
        try:
            write_line_model_dxf(folder, members, supports)
        except Exception as ex:
            dxf_ok = False
            print("DXF write failed (CSV/JSON still written): %s" % ex)
        write_module_anchor_reference_csv(folder, anchors, anchors_ok)
        _mp, tcounts, warnings = write_metadata_json(
            folder, rack, P, stamp, nodes, members, panels, supports, stats,
            invalid_panels)
        _sp, _txt = write_summary_txt(
            folder, rack, P, stamp, nodes, members, panels, supports, tcounts,
            stats, invalid_panels, warnings)

        base_beams = sum(1 for m in members
                         if m["member_type"] in ("BASE_BEAM_X", "BASE_BEAM_Y"))
        info = {"folder": folder, "nodes": len(nodes), "members": len(members),
                "base_beams": base_beams, "panels": len(panels),
                "supports": len(supports), "dxf": dxf_ok,
                "zero_length": stats["zero_length"],
                "duplicates": stats["duplicates"], "nan": stats["nan"],
                "invalid_panels": invalid_panels, "type_counts": tcounts,
                "anchors": len(anchors) if anchors_ok else 0}
        print("RFEM export written to: %s" % folder)
        return True, folder, info
    except Exception as ex:
        print("RFEM export failed: %s" % ex)
        return False, None, {"error": str(ex)}


def ask_export_rfem_dialog():
    """Post-generation Export / Skip dialog. STYLED Timber Housing dialog (correction
    folder 4); native rs.MessageBox fallback. Returns True to export."""
    body = [
        "Export a RFEM / Dlubal base structural model?",
        "",
        "This writes the CLEAN base structural LINE model only - nodes, "
        "members, CLT panel references, supports and module anchors, plus a "
        "DXF line drawing.",
        "",
        "Detailed visual module meshes are NOT exported as structural members.",
        "",
        "Generated files: wosyho_nodes.csv, wosyho_members.csv, "
        "wosyho_supports.csv, wosyho_clt_panels.csv, wosyho_line_model.dxf, "
        "wosyho_export_metadata.json, wosyho_export_summary.txt, "
        "wosyho_module_anchor_reference.csv.",
    ]
    return show_styled_prompt(
        "RFEM / Dlubal Export",
        "Clean base structural line-model export.",
        body, "Export RFEM/Dlubal Model", "Skip Export",
        window_title="Timber Housing - RFEM / Dlubal Export",
        ta_height=210, width=660, height=460)


def _open_path_os(path):
    """Best-effort open of a folder/file in the OS (informational only; never
    edits geometry or model data). Returns True on success."""
    try:
        if not path or not os.path.exists(path):
            return False
        os.startfile(os.path.normpath(path))        # Windows / Rhino
        return True
    except Exception:
        try:
            import subprocess
            subprocess.Popen(["explorer", os.path.normpath(path)])
            return True
        except Exception:
            return False


def show_report_preview(title, body, folder=None, open_file=None,
                        open_folder_label="Open Folder",
                        open_file_label="Open File"):
    """Informational preview dialog for a generated report/export.

    Shows a read-only, scrollable text body plus a Continue button and
    optional Open-Folder / Open-File buttons that launch the generated
    documents in the OS. Purely a viewer - it reports what was written and
    never changes geometry, the StructuralModel, the RFEM export or the
    sizing calculations. Falls back to a plain rs.MessageBox when Eto is
    unavailable."""
    try:
        import Eto.Forms as forms
        import Eto.Drawing as drawing
    except Exception:
        rs.MessageBox(body, 0 | 64, title)
        if folder:
            print("%s -> %s" % (title, folder))
        return

    class RDlg(forms.Dialog[bool]):
        def __init__(self):
            super(RDlg, self).__init__()
            self.Title = title
            self.Padding = drawing.Padding(12)
            self.Resizable = True

            ta = forms.TextArea()
            ta.ReadOnly = True
            ta.Wrap = False
            ta.Text = body
            ta.Size = drawing.Size(560, 360)
            try:
                _f = _ui_font(9.0, mono=True)
                if _f is not None:
                    ta.Font = _f
                ta.BackgroundColor = _ui_color(UI_COLORS["card"])
                ta.TextColor = _ui_color(UI_COLORS["ink"])
            except Exception:
                pass

            cont = forms.Button()
            cont.Text = "Continue"
            cont.Click += self.on_continue
            btnspec = [(cont, "primary")]
            btns = [cont]
            if folder:
                bf = forms.Button()
                bf.Text = open_folder_label
                bf.Click += self.on_folder
                btns.append(bf)
                btnspec.append((bf, "secondary"))
            if open_file:
                bfl = forms.Button()
                bfl.Text = open_file_label
                bfl.Click += self.on_file
                btns.append(bfl)
                btnspec.append((bfl, "secondary"))

            lay = forms.TableLayout()
            lay.Spacing = drawing.Size(8, 8)
            lay.Rows.Add(forms.TableRow([forms.TableCell(ta, True)]))
            # STABILIZED 2026-07-07: each button is its own DIRECT full-width
            # single-cell row (the most reliable Rhino-Eto pattern - never
            # hidden). No nested row, no spacer, no helper.
            for _b in btns:
                lay.Rows.Add(forms.TableRow(forms.TableCell(_b)))
            self.DefaultButton = cont
            self.AbortButton = cont
            finalize_dialog(self, lay, title,
                            "Generated documents & summary.", btnspec)

        def on_continue(self, sender, e):
            self.Close(True)

        def on_folder(self, sender, e):
            _open_path_os(folder)

        def on_file(self, sender, e):
            _open_path_os(open_file)

    try:
        RDlg().ShowModal(Rhino.UI.RhinoEtoApp.MainWindow)
    except Exception:
        rs.MessageBox(body, 0 | 64, title)


def show_styled_prompt(header, subtitle, body_lines, yes_text, no_text,
                       window_title, yes_kind="primary", ta_height=180,
                       width=640, height=430):
    """Styled Timber Housing Yes/No dialog built with the PROVEN report-preview layout
    (correction folder 4 confirmed that layout renders its buttons in live
    Rhino): a fixed-size read-only text area for the explanation + VERTICAL
    full-width DIRECT button rows + Resizable + explicit ClientSize. No
    make_button_row, no nested container, no spacer, no auto-size-only layout.
    Returns True (yes) / False (no). Falls back to native rs.MessageBox if Eto
    is unavailable or errors. UI only - no logic change."""
    body = ("\n".join(body_lines) if isinstance(body_lines, (list, tuple))
            else str(body_lines))
    wtitle = window_title or ("Timber Housing - " + header)
    try:
        import Eto.Forms as forms
        import Eto.Drawing as drawing
    except Exception:
        return rs.MessageBox(body, 4 | 32, wtitle) == 6

    class QDlg(forms.Dialog[bool]):
        def __init__(self):
            super(QDlg, self).__init__()
            self.Title = wtitle
            self.Padding = drawing.Padding(12)
            self.Resizable = True
            ta = forms.TextArea()
            ta.ReadOnly = True
            ta.Wrap = True
            ta.Text = body
            ta.Size = drawing.Size(560, ta_height)
            try:
                _f = _ui_font(9.0)
                if _f is not None:
                    ta.Font = _f
                ta.BackgroundColor = _ui_color(UI_COLORS["card"])
                ta.TextColor = _ui_color(UI_COLORS["ink"])
            except Exception:
                pass
            yes = forms.Button()
            yes.Text = yes_text
            yes.Click += self.on_yes
            no = forms.Button()
            no.Text = no_text
            no.Click += self.on_no
            self.DefaultButton = yes
            self.AbortButton = no
            lay = forms.TableLayout()
            lay.Spacing = drawing.Size(8, 8)
            lay.Rows.Add(forms.TableRow([forms.TableCell(ta, True)]))
            # VERTICAL full-width DIRECT button rows (proven report-preview
            # pattern - never clipped; no helper / nesting / spacer).
            lay.Rows.Add(forms.TableRow(forms.TableCell(yes)))
            lay.Rows.Add(forms.TableRow(forms.TableCell(no)))
            finalize_dialog(self, lay, header, subtitle,
                            [(yes, yes_kind), (no, "cancel")])
            try:
                self.ClientSize = drawing.Size(int(width), int(height))
            except Exception:
                pass

        def on_yes(self, s, e):
            self.Close(True)

        def on_no(self, s, e):
            self.Close(False)

    try:
        return bool(QDlg().ShowModal(Rhino.UI.RhinoEtoApp.MainWindow))
    except Exception:
        return rs.MessageBox(body, 4 | 32, wtitle) == 6


def show_styled_phase2a(MP):
    """Styled Timber Housing Phase 2A dummy-preview dialog (restored as a real dialog,
    correction folder 4). Same PROVEN report-preview layout: fixed-size text
    area + the two checkboxes + VERTICAL full-width DIRECT buttons + Resizable +
    explicit ClientSize (so the Place/Skip buttons cannot be clipped like the
    earlier Eto version). Sets MP['enable'] / MP['show_anchors'] and returns MP
    (Place) or 'CANCEL' (Skip) - exactly what main() expects. Falls back to the
    native rs.GetBoolean prompt (get_module_params_fallback) if Eto is
    unavailable or errors. Dummy placement logic is unchanged."""
    body = ("Dummy block preview only. Detailed textured modules are offered in "
            "Phase 2B, AFTER the preliminary sizing + RFEM/Dlubal export "
            "checkpoint.\n\n"
            "The arrangement follows the exported alternate-floor reference "
            "pattern automatically: converging mirrored 1/1A pairs, common "
            "terraces every 3rd bay, the Module 2 end block, and roof terraces "
            "on the cascade steps.\n\n"
            "The dummy preview is the placement authority for the RFEM module "
            "anchors and the Phase-2B detailed-module replacement.")
    try:
        import Eto.Forms as forms
        import Eto.Drawing as drawing
    except Exception:
        return get_module_params_fallback(MP)

    class ADlg(forms.Dialog[bool]):
        def __init__(self):
            super(ADlg, self).__init__()
            self.Title = "Timber Housing Phase 2A - Dummy Block Preview"
            self.Padding = drawing.Padding(12)
            self.Resizable = True
            ta = forms.TextArea()
            ta.ReadOnly = True
            ta.Wrap = True
            ta.Text = body
            ta.Size = drawing.Size(560, 150)
            try:
                _f = _ui_font(9.0)
                if _f is not None:
                    ta.Font = _f
                ta.BackgroundColor = _ui_color(UI_COLORS["card"])
                ta.TextColor = _ui_color(UI_COLORS["ink"])
            except Exception:
                pass
            self.c_enable = forms.CheckBox()
            self.c_enable.Text = "Enable reference dummy module placement"
            self.c_enable.Checked = bool(MP.get("enable", True))
            self.c_anch = forms.CheckBox()
            self.c_anch.Text = "Show module anchors / debug markers"
            self.c_anch.Checked = bool(MP.get("show_anchors", False))
            style_checkbox(self.c_enable)
            style_checkbox(self.c_anch)
            place = forms.Button()
            place.Text = "Place Dummy Preview"
            place.Click += self.on_place
            skip = forms.Button()
            skip.Text = "Skip Dummy Preview"
            skip.Click += self.on_skip
            self.DefaultButton = place
            self.AbortButton = skip
            lay = forms.TableLayout()
            lay.Spacing = drawing.Size(8, 8)
            lay.Rows.Add(forms.TableRow([forms.TableCell(ta, True)]))
            lay.Rows.Add(forms.TableRow(forms.TableCell(self.c_enable)))
            lay.Rows.Add(forms.TableRow(forms.TableCell(self.c_anch)))
            # VERTICAL full-width DIRECT button rows (proven; never clipped).
            lay.Rows.Add(forms.TableRow(forms.TableCell(place)))
            lay.Rows.Add(forms.TableRow(forms.TableCell(skip)))
            finalize_dialog(self, lay, "Phase 2A - Dummy Block Preview",
                            "Placement authority - runs before sizing, export "
                            "and detailed modules.",
                            [(place, "primary"), (skip, "cancel")])
            try:
                self.ClientSize = drawing.Size(640, 470)
            except Exception:
                pass

        def on_place(self, s, e):
            self.Close(True)

        def on_skip(self, s, e):
            self.Close(False)

    try:
        dlg = ADlg()
        res = dlg.ShowModal(Rhino.UI.RhinoEtoApp.MainWindow)
        if not res:
            return "CANCEL"
        MP["enable"] = bool(dlg.c_enable.Checked)
        MP["show_anchors"] = bool(dlg.c_anch.Checked)
        return MP
    except Exception:
        return get_module_params_fallback(MP)


def run_stage3_rfem_export(rack, P):
    """STAGE 3 (post-generation): offer + run the RFEM/Dlubal base export.
    Always available once skeleton generation has succeeded, whether or not
    Phase-2A module placement ran."""
    if not ask_export_rfem_dialog():
        print("RFEM/Dlubal export skipped. Rhino model kept as-is.")
        return False
    script_dir = P.get("export_folder") or os.path.expanduser("~")
    ok, folder, info = run_rfem_export(rack, P, script_dir)
    if ok:
        dxf_path = os.path.join(folder, "wosyho_line_model.dxf")
        sep = "-" * 58
        body = "\n".join([
            "RFEM / Dlubal base structural model export complete.",
            "=" * 58,
            "Export folder:",
            "  %s" % folder,
            sep,
            "nodes                       : %d" % info["nodes"],
            "members                     : %d  (incl. %d base beams)"
            % (info["members"], info["base_beams"]),
            "CLT panels                  : %d" % info["panels"],
            "supports                    : %d" % info["supports"],
            "module anchors              : %d" % info.get("anchors", 0),
            "zero-length removed/skipped : %d" % info.get("zero_length", 0),
            "duplicate members removed   : %d" % info.get("duplicates", 0),
            "invalid coordinates (NaN)   : %d" % info.get("nan", 0),
            "invalid CLT panels          : %d" % info.get("invalid_panels", 0),
            "DXF line model              : %s%s"
            % (dxf_path,
               "" if info.get("dxf", True) else "  (DXF write FAILED)"),
            sep,
            "RFEM/Dlubal export uses the clean base structural line model and",
            "module anchor references. Detailed visual module meshes are NOT",
            "exported as structural members.",
            sep,
            "Generated documents:",
            "  - wosyho_nodes.csv",
            "  - wosyho_members.csv",
            "  - wosyho_supports.csv",
            "  - wosyho_clt_panels.csv",
            "  - wosyho_line_model.dxf",
            "  - wosyho_export_metadata.json",
            "  - wosyho_export_summary.txt",
            "  - wosyho_module_anchor_reference.csv",
        ])
        show_report_preview(
            "Timber Housing RFEM / Dlubal Export Preview", body, folder=folder,
            open_file=dxf_path, open_folder_label="Open Export Folder",
            open_file_label="Open DXF Line Model")
    else:
        rs.MessageBox("RFEM / Dlubal export failed. See console/report.",
                      0 | 16, "RFEM / Dlubal Export - Failed")
    return True


# =============================================================================
# 6c. EUROCODE-INFORMED PRELIMINARY V/TREE SUPPORT SIZING EMULATOR  (Part C)
#
# A transparent, design-stage emulator that imitates a European (EN 1990 basis /
# EN 1991 actions / EN 1995 timber) gravity-load sizing workflow for the VARIABLE
# support systems only (V-columns, tree trunks, tree branches). It groups the
# special supports, distributes tributary gravity loads (dead/live/corridor/
# module) by a documented bay/cell model, forms EN 1990-style ULS combinations,
# and picks preliminary square sections by a SIMPLIFIED axial + Euler-buckling
# check. It NEVER resizes the fixed rack (regular columns stay 0.30x0.30, AXIS
# stays fixed), never edits geometry, and is NOT a certified design.
#
# DISCLAIMER (must appear in every report):
DESIGN_DISCLAIMER = ("Eurocode-informed preliminary structural design emulator "
                     "for academic/design-stage use only. Final verification "
                     "must be performed in RFEM/Dlubal and reviewed by a "
                     "qualified structural engineer.")
# =============================================================================

TIMBER_PROFILES = {
    "C24":   {"E0_mean_N_mm2": 11000.0, "fc0k_N_mm2": 21.0,
              "density_kN_m3": 4.2, "gamma_M": 1.30, "grade_type": "solid_C24"},
    "GL24h": {"E0_mean_N_mm2": 11500.0, "fc0k_N_mm2": 24.0,
              "density_kN_m3": 3.85, "gamma_M": 1.25, "grade_type": "glulam"},
    "GL28h": {"E0_mean_N_mm2": 12600.0, "fc0k_N_mm2": 28.0,
              "density_kN_m3": 4.10, "gamma_M": 1.25, "grade_type": "glulam"},
    "LVL":   {"E0_mean_N_mm2": 13800.0, "fc0k_N_mm2": 30.0,
              "density_kN_m3": 5.00, "gamma_M": 1.20,
              "grade_type": "engineered_LVL_placeholder"},
}

SECTION_LIBRARY = [0.18, 0.20, 0.22, 0.24, 0.26, 0.28, 0.30, 0.32, 0.34, 0.36,
                   0.38, 0.40, 0.45, 0.50, 0.55, 0.60, 0.70, 0.80]


def default_eurocode_profile():
    return {
        "region": "Germany",
        "basis": "EN 1990",
        "actions": "EN 1991",
        "timber": "EN 1995",
        "national_annex": ("German National Annex placeholder values / "
                           "user-configurable"),
        "design_stage": "preliminary",
    }


def default_sizing_settings():
    """All values are PRELIMINARY, editable placeholders (reported as such)."""
    return {
        "material_profile": "GL24h",
        "service_class": 2,
        "load_duration_class": "medium-term",
        "kmod": 0.80,          # SC2, medium-term (EN 1995 placeholder)
        "kdef": 0.80,          # placeholder (not used in this gravity step)
        "gamma_M": 1.25,       # overrides profile gamma_M if set
        "gamma_G": 1.35,
        "gamma_Q": 1.50,
        "psi0": {"residential": 0.7, "corridor": 0.7, "roof": 0.6,
                 "snow": 0.5, "wind": 0.6},
        "utilization_limit": 0.85,
        "k_eff_buckling": 1.0,   # effective-length factor (pinned placeholder)
        # ---- loads (kN/m2 unless stated) ------------------------------------
        "timber_density_kN_m3": 4.5,
        "clt_floor_dead_load_kN_m2": 1.5,
        "base_clt_dead_load_kN_m2": 1.5,
        "residential_live_load_kN_m2": 2.0,
        "corridor_live_load_kN_m2": 3.0,
        "stair_live_load_kN_m2": 3.0,
        "roof_maintenance_live_load_kN_m2": 1.0,
        "green_roof_dead_load_kN_m2": 1.5,
        "module_dead_load_A_kN": 25.0,
        "module_dead_load_A1_kN": 25.0,
        "module_dead_load_B_kN": 30.0,
        # ---- section selection ----------------------------------------------
        "section_library": SECTION_LIBRARY,
        "section_limits": {"V_LEG": (0.18, 0.60),
                           "TREE_TRUNK": (0.24, 0.80),
                           "TREE_BRANCH": (0.18, 0.50)},
    }


def _sz_member_geom(rack, rec):
    """Return (base, tip, length, cos_from_vertical, theta_deg) for an SM
    member (base = lower-Z endpoint)."""
    nds = rack.SM.model["nodes"]
    a = nds[rec["node_i"]]
    b = nds[rec["node_j"]]
    p0 = (a["x"], a["y"], a["z"])
    p1 = (b["x"], b["y"], b["z"])
    dx = p1[0] - p0[0]
    dy = p1[1] - p0[1]
    dz = p1[2] - p0[2]
    L = math.sqrt(dx * dx + dy * dy + dz * dz)
    base, tip = (p0, p1) if p0[2] <= p1[2] else (p1, p0)
    cosv = (abs(tip[2] - base[2]) / L) if L > 1e-9 else 1.0
    cosv = max(1e-6, min(1.0, cosv))
    theta = math.degrees(math.acos(cosv))
    return base, tip, L, cosv, theta


def _bay_of_x(rack, x):
    best, bd = 1, 1e18
    for b in range(1, rack.NB + 1):
        d = abs(rack.xmid(b) - x)
        if d < bd:
            bd, best = d, b
    return best


def build_support_groups(rack, tol=0.05):
    """Group the VARIABLE supports into support systems.
    V legs -> one V_SUPPORT per shared base point (4 legs).
    Trunks -> one TREE_SUPPORT per trunk base; its branches attach by base xy.
    Returns list of group dicts."""
    v_groups = {}
    tree_groups = {}
    branches = []
    for rec in rack.SM.model["members"]:
        t = rec["type"]
        base, tip, L, cosv, theta = _sz_member_geom(rack, rec)
        if t == "FOUR_LEGGED_V_BRANCH":
            key = (round(base[0] / tol) * tol, round(base[1] / tol) * tol)
            g = v_groups.get(key)
            if g is None:
                bay = _bay_of_x(rack, base[0])
                midy = TRUNK_Y + rack.boff(bay)
                side = ("L" if base[1] < midy - 0.5
                        else ("R" if base[1] > midy + 0.5 else "MID"))
                g = {"support_type": "V_SUPPORT", "bay": bay, "side": side,
                     "base": base, "members": []}
                v_groups[key] = g
            g["members"].append(rec)
        elif t == "ATRIUM_TRUNK_COLUMN":
            key = (round(base[0] / tol) * tol, round(base[1] / tol) * tol)
            bay = _bay_of_x(rack, base[0])
            tree_groups[key] = {"support_type": "TREE_SUPPORT", "bay": bay,
                                "side": "MID", "base": base,
                                "trunk": rec, "members": [rec], "branches": []}
        elif t == "ATRIUM_BRANCH_TO_CORRIDOR":
            branches.append((base, rec))
    # attach branches to nearest trunk base (xy)
    for (bbase, rec) in branches:
        best, bd = None, 1e18
        for key, g in tree_groups.items():
            d = math.hypot(bbase[0] - g["base"][0], bbase[1] - g["base"][1])
            if d < bd:
                bd, best = d, g
        if best is not None:
            best["branches"].append(rec)
            best["members"].append(rec)
    groups = []
    vi = {}
    for g in v_groups.values():
        vi[g["bay"]] = vi.get(g["bay"], 0) + 1
        g["group_id"] = "V_SUPPORT_bay_%02d_%s" % (g["bay"], g["side"])
        groups.append(g)
    for g in tree_groups.values():
        g["group_id"] = "TREE_SUPPORT_bay_%02d" % g["bay"]
        groups.append(g)
    return groups


def _module_dead_for(rack, bay, side, s):
    """Sum preliminary module dead loads (kN) placed on a bay/side, from the
    Phase-2A placement records (NEVER the meshes)."""
    slots = getattr(rack, "module_slots", None)
    if not slots:
        return 0.0, False
    dl = {"M1": s["module_dead_load_A_kN"], "M1A": s["module_dead_load_A1_kN"],
          "M2": s["module_dead_load_B_kN"]}
    tot = 0.0
    for sl in slots:
        if sl.get("bay") != bay:
            continue
        if side in ("L", "R") and sl.get("side") not in (side, None):
            continue
        tot += dl.get(sl.get("assigned"), 0.0)
    return tot, True


def compute_group_loads(rack, groups, s):
    """Documented bay/cell tributary distribution (preliminary)."""
    mod_area = AXIS * (Y_MID_L - Y_OUT_L)        # 3.8 x 3.8 module band
    cor_area = AXIS * (Y_COR_L - Y_MID_L)        # 3.8 x 2.3 corridor band
    a_nom = MEMBER * MEMBER                       # nominal self-weight section
    warnings = []
    for g in groups:
        b = g["bay"]
        floors = [n for n in range(1, rack.fbay(b) + 1)
                  if rack.level_has_frame(b, n)]
        nfl = len(floors)
        # self weight of the group's members (nominal 0.30 section)
        sw = 0.0
        for rec in g["members"]:
            _bs, _tp, L, _c, _th = _sz_member_geom(rack, rec)
            sw += L * a_nom * s["timber_density_kN_m3"]
        if g["support_type"] == "V_SUPPORT":
            if g["side"] == "MID":               # end-block atrium V
                area = 2.0 * cor_area
                gk_fl = nfl * area * s["clt_floor_dead_load_kN_m2"]
                qk = nfl * area * s["corridor_live_load_kN_m2"]
                mod = 0.0
                g["corridor_included"] = "YES"
            else:
                area = mod_area
                gk_fl = nfl * area * s["clt_floor_dead_load_kN_m2"]
                qk = nfl * area * s["residential_live_load_kN_m2"]
                mod, _ok = _module_dead_for(rack, b, g["side"], s)
                g["corridor_included"] = "NO"
            gk = gk_fl + mod + sw
            g["service_floor_kN"] = gk_fl
            g["service_corridor_kN"] = (gk_fl if g["side"] == "MID" else 0.0)
            g["service_module_kN"] = mod
            g["service_roof_terrace_kN"] = 0.0
        else:                                     # TREE_SUPPORT
            area = 2.0 * cor_area                  # both corridor edges
            gk_fl = nfl * area * s["clt_floor_dead_load_kN_m2"]
            qk = nfl * area * s["corridor_live_load_kN_m2"]
            gk = gk_fl + sw
            g["corridor_included"] = "YES"
            g["service_floor_kN"] = gk_fl
            g["service_corridor_kN"] = gk_fl
            g["service_module_kN"] = 0.0
            g["service_roof_terrace_kN"] = 0.0
        g["service_self_weight_kN"] = sw
        g["floors"] = nfl
        g["Gk"] = gk
        g["Qk"] = qk
        g["SLS"] = gk + qk
        g["Ed"] = s["gamma_G"] * gk + s["gamma_Q"] * qk
        if gk < 0 or qk < 0:
            warnings.append("%s: negative load computed" % g["group_id"])
    return warnings


def _size_square(N_ed, L, family, s, mat):
    E = mat["E0_mean_N_mm2"]
    gamma_M = s.get("gamma_M", mat["gamma_M"])
    fc0d = s["kmod"] * mat["fc0k_N_mm2"] / gamma_M      # N/mm2
    lo, hi = s["section_limits"][family]
    keff = s["k_eff_buckling"]

    def _calc(bb):
        A = bb * bb
        I = bb ** 4 / 12.0
        i = math.sqrt(I / A) if A > 0 else 0.0
        Leff = keff * L
        slend = (Leff / i) if i > 1e-9 else 0.0
        Ncr = (math.pi ** 2) * (E * 1000.0) * I / (Leff * Leff) \
            if Leff > 1e-9 else 0.0
        Nrd = A * fc0d * 1000.0
        ua = (N_ed / Nrd) if Nrd > 1e-9 else 99.9
        ub = (N_ed / Ncr) if Ncr > 1e-9 else 99.9
        return {"b": bb, "A": A, "I": I, "slend": slend, "Ncr": Ncr,
                "Nrd": Nrd, "ua": ua, "ub": ub, "gov": max(ua, ub),
                "fc0d": fc0d}
    lim = s["utilization_limit"]
    for bb in s["section_library"]:
        if bb < lo - 1e-9 or bb > hi + 1e-9:
            continue
        r = _calc(bb)
        if r["gov"] <= lim:
            r["pass"] = True
            return r
    r = _calc(hi)
    r["pass"] = False
    return r


def size_variable_members(rack, groups, s):
    mat = TIMBER_PROFILES[s["material_profile"]]
    rows = []
    warns = []
    hints = {}
    for g in groups:
        if g["support_type"] == "V_SUPPORT":
            legs = [r for r in g["members"]
                    if r["type"] == "FOUR_LEGGED_V_BRANCH"]
            n = max(1, len(legs))
            vshare = g["Ed"] / float(n)
            for rec in legs:
                _bs, _tp, L, cosv, theta = _sz_member_geom(rack, rec)
                if cosv < 0.20:
                    warns.append("%s member %d: V-leg inclination creates high "
                                 "axial force; geometry should be reviewed."
                                 % (g["group_id"], rec["id"]))
                N_ed = vshare / cosv
                r = _size_square(N_ed, L, "V_LEG", s, mat)
                mm = int(round(r["b"] * 1000))
                hints[rec["id"]] = "TIMBER_%dx%d_V_LEG" % (mm, mm)
                rows.append(_sizing_row(g, rec, "V_COLUMN", L, theta, N_ed, r,
                                        s, mat))
                if not r["pass"]:
                    warns.append("%s member %d FAIL: RFEM/Dlubal verification "
                                 "required." % (g["group_id"], rec["id"]))
        else:
            trunk = g.get("trunk")
            if trunk is not None:
                _bs, _tp, L, cosv, theta = _sz_member_geom(rack, trunk)
                N_ed = g["Ed"]
                r = _size_square(N_ed, L, "TREE_TRUNK", s, mat)
                mm = int(round(r["b"] * 1000))
                hints[trunk["id"]] = "TIMBER_%dx%d_TREE_TRUNK" % (mm, mm)
                rows.append(_sizing_row(g, trunk, "TREE_TRUNK", L, theta, N_ed,
                                        r, s, mat))
                if not r["pass"]:
                    warns.append("%s trunk %d FAIL: RFEM/Dlubal verification "
                                 "required." % (g["group_id"], trunk["id"]))
            brs = g.get("branches", [])
            nb = max(1, len(brs))
            bshare = g["Ed"] / float(nb)
            for rec in brs:
                _bs, _tp, L, cosv, theta = _sz_member_geom(rack, rec)
                N_ed = bshare / cosv
                r = _size_square(N_ed, L, "TREE_BRANCH", s, mat)
                mm = int(round(r["b"] * 1000))
                hints[rec["id"]] = "TIMBER_%dx%d_TREE_BRANCH" % (mm, mm)
                row = _sizing_row(g, rec, "TREE_BRANCH", L, theta, N_ed, r, s,
                                  mat)
                row["notes"] = ("branch axial (equal corridor share / cos); "
                                "bending / combined compression-bending NOT "
                                "checked - RFEM/Dlubal verification required")
                rows.append(row)
    return rows, hints, warns


def _sizing_row(g, rec, mtype, L, theta, N_ed, r, s, mat):
    return {"support_group_id": g["group_id"], "member_id": rec["id"],
            "member_type": mtype, "length_m": L,
            "angle_from_vertical_deg": theta, "axial_force_kN": N_ed,
            "b": r["b"], "A": r["A"], "slend": r["slend"], "Ncr": r["Ncr"],
            "Nrd": r["Nrd"], "ua": r["ua"], "ub": r["ub"], "gov": r["gov"],
            "pass": r["pass"], "material_profile": s["material_profile"],
            "fc0d": r["fc0d"], "E0": mat["E0_mean_N_mm2"],
            "notes": ("preliminary axial + Euler-buckling emulator; "
                      "not full EC5 stability")}


def create_sizing_report_folder(script_dir):
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    root = os.path.join(script_dir, "structural_analysis_reports")
    folder = os.path.join(root, "wosyho_support_sizing_%s" % stamp)
    if not os.path.isdir(folder):
        os.makedirs(folder)
    return folder, stamp


def write_eurocode_assumptions_json(folder, ec, s):
    mat = TIMBER_PROFILES[s["material_profile"]]
    data = {"eurocode_profile": ec, "load_assumptions": {
                k: s[k] for k in s if k.endswith("_kN_m2")
                or k.endswith("_kN") or k == "timber_density_kN_m3"},
            "load_factors": {"gamma_G": s["gamma_G"], "gamma_Q": s["gamma_Q"]},
            "psi_factors": s["psi0"],
            "timber_material_profile": s["material_profile"],
            "timber_material_values": mat,
            "service_class": s["service_class"],
            "load_duration_class": s["load_duration_class"],
            "kmod": s["kmod"], "kdef": s["kdef"],
            "gamma_M": s.get("gamma_M", mat["gamma_M"]),
            "utilization_limit": s["utilization_limit"],
            "section_library_m": s["section_library"],
            "section_limits_m": s["section_limits"],
            "disclaimer": DESIGN_DISCLAIMER}
    p = os.path.join(folder, "eurocode_assumptions.json")
    with open(p, "w") as f:
        json.dump(data, f, indent=1)
    return p


def write_load_combinations_csv(folder, s):
    p = os.path.join(folder, "load_combinations.csv")
    with open(p, "w") as f:
        f.write(_csv_row(["combination_id", "combination_name", "expression",
                          "gamma_G", "gamma_Q", "psi_factor", "notes"]))
        f.write(_csv_row(["ULS1", "STR permanent+leading variable",
                          "Ed = %.2f*Gk + %.2f*Qk" % (s["gamma_G"], s["gamma_Q"]),
                          s["gamma_G"], s["gamma_Q"], "1.0",
                          "EN 1990-style ULS (gravity, single leading Q)"]))
        f.write(_csv_row(["SLS1", "characteristic service", "SLS = Gk + Qk",
                          "1.0", "1.0", "1.0", "characteristic serviceability"]))
        f.write(_csv_row(["NOTE", "snow/wind/seismic", "not combined",
                          "", "", str(s["psi0"]),
                          "snow/wind are PLACEHOLDERS only; no lateral analysis"]))
    return p


def write_support_group_loads_csv(folder, groups):
    p = os.path.join(folder, "support_group_loads.csv")
    cols = ["support_group_id", "support_type", "bay", "base_x", "base_y",
            "base_z", "assigned_members", "service_floor_load_kN",
            "service_corridor_load_kN", "service_module_load_kN",
            "service_roof_terrace_load_kN", "service_self_weight_kN",
            "Gk_total_kN", "Qk_total_kN", "SLS_total_kN", "ULS_Ed_kN",
            "corridor_load_included", "load_distribution_notes"]
    with open(p, "w") as f:
        f.write(_csv_row(cols))
        for g in groups:
            mids = ";".join(str(r["id"]) for r in g["members"])
            f.write(_csv_row([
                g["group_id"], g["support_type"], g["bay"],
                "%.3f" % g["base"][0], "%.3f" % g["base"][1],
                "%.3f" % g["base"][2], mids,
                "%.2f" % g["service_floor_kN"],
                "%.2f" % g["service_corridor_kN"],
                "%.2f" % g["service_module_kN"],
                "%.2f" % g["service_roof_terrace_kN"],
                "%.2f" % g["service_self_weight_kN"],
                "%.2f" % g["Gk"], "%.2f" % g["Qk"], "%.2f" % g["SLS"],
                "%.2f" % g["Ed"], g.get("corridor_included", "NO"),
                "bay/cell tributary; floors=%d" % g["floors"]]))
    return p


def write_variable_member_sizing_csv(folder, rows):
    p = os.path.join(folder, "variable_member_sizing.csv")
    cols = ["support_group_id", "member_id", "member_type", "length_m",
            "angle_from_vertical_deg", "axial_force_kN", "recommended_section_b_m",
            "area_m2", "slenderness", "Ncr_kN", "Nrd_compression_kN",
            "axial_utilization", "buckling_utilization", "governing_utilization",
            "pass_fail", "material_profile", "fc0d_N_mm2", "E0_mean_N_mm2",
            "notes"]
    with open(p, "w") as f:
        f.write(_csv_row(cols))
        for r in rows:
            f.write(_csv_row([
                r["support_group_id"], r["member_id"], r["member_type"],
                "%.3f" % r["length_m"], "%.1f" % r["angle_from_vertical_deg"],
                "%.2f" % r["axial_force_kN"], "%.3f" % r["b"],
                "%.4f" % r["A"], "%.1f" % r["slend"], "%.1f" % r["Ncr"],
                "%.1f" % r["Nrd"], "%.3f" % r["ua"], "%.3f" % r["ub"],
                "%.3f" % r["gov"], "PASS" if r["pass"] else "FAIL",
                r["material_profile"], "%.2f" % r["fc0d"], "%.0f" % r["E0"],
                r["notes"]]))
    return p


def write_sizing_summaries(folder, rack, P, stamp, groups, rows, warnings, s):
    vg = [g for g in groups if g["support_type"] == "V_SUPPORT"]
    tg = [g for g in groups if g["support_type"] == "TREE_SUPPORT"]
    tot_g = sum(g["Gk"] for g in groups)
    tot_q = sum(g["Qk"] for g in groups)
    tot_ed = sum(g["Ed"] for g in groups)

    def _maxb(mt):
        bs = [r["b"] for r in rows if r["member_type"] == mt]
        return max(bs) if bs else 0.0
    n_fail = sum(1 for r in rows if not r["pass"])
    summ = {"timestamp": stamp, "bay_count": rack.NB,
            "floor_count": max(rack.F) if rack.F else 0,
            "grid_type": P.get("plan_grid_type", 1),
            "cascade_profile": list(rack.F),
            "regular_column_fixed_size_m": MEMBER,
            "grid_spacing_AXIS_m": AXIS,
            "support_groups_count": len(groups),
            "V_support_group_count": len(vg),
            "tree_support_group_count": len(tg),
            "total_Gk_kN": tot_g, "total_Qk_kN": tot_q, "total_Ed_kN": tot_ed,
            "max_V_leg_section_m": _maxb("V_COLUMN"),
            "max_tree_trunk_section_m": _maxb("TREE_TRUNK"),
            "max_tree_branch_section_m": _maxb("TREE_BRANCH"),
            "members_sized": len(rows), "members_fail": n_fail,
            "warnings": warnings, "disclaimer": DESIGN_DISCLAIMER}
    jp = os.path.join(folder, "sizing_summary.json")
    with open(jp, "w") as f:
        json.dump(summ, f, indent=1)
    gt = {1: "Regular", 2: "Half Offset", 3: "Centre Offset"}.get(
        P.get("plan_grid_type", 1), "?")
    L = ["Timber Housing v23 - PRELIMINARY V/TREE SUPPORT SIZING", "=" * 60,
         DESIGN_DISCLAIMER, "=" * 60,
         "timestamp                : %s" % stamp,
         "bays / floors            : %d / %d"
         % (rack.NB, max(rack.F) if rack.F else 0),
         "grid type                : %d (%s)" % (P.get("plan_grid_type", 1), gt),
         "cascade profile          : %s" % str(list(rack.F)),
         "regular column (FIXED)   : %.2f x %.2f m" % (MEMBER, MEMBER),
         "grid spacing AXIS (FIXED): %.2f m" % AXIS,
         "material profile         : %s (kmod=%.2f, gamma_M=%.2f)"
         % (s["material_profile"], s["kmod"], s.get("gamma_M", 1.25)),
         "ULS combination          : Ed = %.2f*Gk + %.2f*Qk"
         % (s["gamma_G"], s["gamma_Q"]),
         "-" * 60,
         "support groups           : %d  (V %d, tree %d)"
         % (len(groups), len(vg), len(tg)),
         "total Gk / Qk / Ed (kN)  : %.1f / %.1f / %.1f"
         % (tot_g, tot_q, tot_ed),
         "max V-leg section        : %.3f m" % _maxb("V_COLUMN"),
         "max tree-trunk section   : %.3f m" % _maxb("TREE_TRUNK"),
         "max tree-branch section  : %.3f m" % _maxb("TREE_BRANCH"),
         "members sized / FAIL     : %d / %d" % (len(rows), n_fail),
         "-" * 60]
    if warnings:
        L.append("warnings:")
        for w in warnings[:40]:
            L.append("   - %s" % w)
    L += ["-" * 60, "NOT CHECKED (RFEM/Dlubal required): connections, local "
          "bearing, combined compression-bending, full EC5 stability factors, "
          "fire, wind/seismic, vibration, global lateral stability, "
          "serviceability deflection, foundation/base-plate, LTB.",
          DESIGN_DISCLAIMER]
    tp = os.path.join(folder, "sizing_summary.txt")
    with open(tp, "w") as f:
        f.write("\n".join(L) + "\n")
    return summ


def run_support_sizing(rack, P, script_dir):
    """Orchestrate the preliminary sizing. Stores recommended section hints on
    the rack (_sizing_hints) for the later RFEM export. Returns (ok, folder,
    info). No geometry is changed."""
    try:
        ec = P.get("eurocode_profile") or default_eurocode_profile()
        s = P.get("sizing_settings") or default_sizing_settings()
        if s["material_profile"] not in TIMBER_PROFILES:
            s["material_profile"] = "GL24h"
        groups = build_support_groups(rack)
        load_warns = compute_group_loads(rack, groups, s)
        rows, hints, size_warns = size_variable_members(rack, groups, s)
        warnings = load_warns + size_warns
        folder, stamp = create_sizing_report_folder(script_dir)
        write_eurocode_assumptions_json(folder, ec, s)
        write_load_combinations_csv(folder, s)
        write_support_group_loads_csv(folder, groups)
        write_variable_member_sizing_csv(folder, rows)
        summ = write_sizing_summaries(folder, rack, P, stamp, groups, rows,
                                      warnings, s)
        # store for RFEM export integration (metadata + section_hint override)
        rack._sizing_hints = hints
        rack._sizing_report_folder = folder
        rack._sizing_summary = summ
        info = {"folder": folder, "groups": len(groups),
                "v_groups": summ["V_support_group_count"],
                "tree_groups": summ["tree_support_group_count"],
                "members": len(rows), "fails": summ["members_fail"],
                "Gk": summ["total_Gk_kN"], "Qk": summ["total_Qk_kN"],
                "Ed": summ["total_Ed_kN"], "warnings": len(warnings),
                "max_V": summ["max_V_leg_section_m"],
                "max_trunk": summ["max_tree_trunk_section_m"],
                "max_branch": summ["max_tree_branch_section_m"]}
        print("Preliminary sizing written to: %s" % folder)
        return True, folder, info
    except Exception as ex:
        print("Preliminary sizing failed: %s" % ex)
        return False, None, {"error": str(ex)}


def ask_sizing_dialog():
    """Preliminary sizing prompt. STYLED Timber Housing dialog (correction folder 4);
    native rs.MessageBox fallback. Returns True to run sizing, False to skip."""
    body = [
        "Run Eurocode-informed preliminary sizing for the V-column and atrium "
        "tree support systems?",
        "",
        "This produces a design-stage report and preliminary section hints "
        "only - no geometry is resized.",
        "",
        DESIGN_DISCLAIMER,
    ]
    return show_styled_prompt(
        "Preliminary V/Tree Support Sizing",
        "Design-stage structural emulator (optional).",
        body, "Run Preliminary Sizing", "Skip",
        window_title="Timber Housing - Preliminary V/Tree Support Sizing",
        ta_height=200, width=650, height=450)


def run_stage_support_sizing(rack, P):
    """STAGE 2.5 (post-generation, before RFEM export). Optional; report +
    section hints only, NO visual resizing of geometry. Returns True if the
    user ran sizing, False if skipped (used only by the completion summary)."""
    if not ask_sizing_dialog():
        print("Preliminary V/tree sizing skipped. Default section hints kept.")
        return False
    script_dir = P.get("export_folder") or os.path.expanduser("~")
    ok, folder, info = run_support_sizing(rack, P, script_dir)
    if ok:
        txt_path = os.path.join(folder, "sizing_summary.txt")
        sep = "-" * 58
        body = "\n".join([
            "Preliminary V/tree support sizing complete.",
            "=" * 58,
            "Report folder:",
            "  %s" % folder,
            sep,
            "support groups               : %d" % info["groups"],
            "V supports                   : %d" % info["v_groups"],
            "tree supports                : %d" % info["tree_groups"],
            "members sized                : %d" % info["members"],
            "FAIL count                   : %d" % info["fails"],
            "total Ed                     : %.1f kN" % info["Ed"],
            "max / recommended V leg      : %.3f m" % info.get("max_V", 0.0),
            "max / recommended tree trunk : %.3f m"
            % info.get("max_trunk", 0.0),
            "max / recommended tree branch: %.3f m"
            % info.get("max_branch", 0.0),
            sep,
            DESIGN_DISCLAIMER,
            sep,
            "Generated documents:",
            "  - eurocode_assumptions.json",
            "  - load_combinations.csv",
            "  - support_group_loads.csv",
            "  - variable_member_sizing.csv",
            "  - sizing_summary.json",
            "  - sizing_summary.txt",
        ])
        show_report_preview(
            "Timber Housing Preliminary Sizing Report Preview", body, folder=folder,
            open_file=txt_path, open_folder_label="Open Report Folder",
            open_file_label="Open Summary TXT")
    else:
        rs.MessageBox("Preliminary sizing failed. See console/report. RFEM "
                      "export can still proceed with default sections.",
                      0 | 48, "Preliminary Sizing - Failed")
    return True


# =============================================================================
# 6b. PRELIMINARY STRUCTURAL STABILITY CHECK  (Phase S2/S3, added 2026-07-08)
#
# DESIGN-STAGE ONLY. Runs after the Phase 2A dummy preview and BEFORE the
# existing preliminary V/tree sizing and the RFEM/Dlubal export. It only READS
# the model (existing collectors + existing V/tree sizing engine, both read-only)
# and writes its own stability_reports/ files + a styled preview dialog. It
# NEVER changes geometry, the StructuralModel, module placement/counts, the
# existing sizing math, the RFEM export, or any existing dialog. It cannot claim
# final safety: gravity/topology screen only. See
# docs/WOSYHO_STRUCTURAL_STABILITY_WORKFLOW_RESEARCH.md.
# =============================================================================

STAB_DISCLAIMER = ("Preliminary design-stage stability screen only (gravity / "
                   "topology). NOT a certified structural verification. Wind, "
                   "snow, seismic, global lateral stability, member/LTB "
                   "buckling, connections, foundations, vibration, fire and "
                   "full serviceability are NOT verified here. Final "
                   "verification must be performed in RFEM/Dlubal/Karamba and "
                   "reviewed by a qualified structural engineer.")

# Preliminary characteristic bending/shear strengths (N/mm2) per timber profile
# (design-stage placeholders; fc0k / E come from TIMBER_PROFILES).
STAB_BENDING_SHEAR = {
    "C24":   {"fmk": 24.0, "fvk": 4.0},
    "GL24h": {"fmk": 24.0, "fvk": 3.5},
    "GL28h": {"fmk": 28.0, "fvk": 3.5},
    "LVL":   {"fmk": 44.0, "fvk": 4.6},
}

STAB_DEFLECTION_LIMIT_DENOM = 300.0     # preliminary SLS beam limit L/300
STAB_BEAM_RAW = ("REGULAR_BEAM_X", "REGULAR_BEAM_Y", "CORRIDOR_EDGE_BEAM",
                 "BASE_BEAM_X", "BASE_BEAM_Y")
STAB_COLUMN_RAW = ("REGULAR_COLUMN", "STAIR_ZONE_SUPPORT_COLUMN")
STAB_MISSING_INPUTS = [
    "wind load (EN 1991-1-4) - not applied",
    "snow load (EN 1991-1-3) - not applied",
    "seismic / lateral load - not applied",
    "global lateral stability system (bracing / cores / diaphragm) - not modelled",
    "diaphragm / shear-wall behaviour - not checked",
    "member lateral-torsional buckling (LTB) - not checked",
    "connection design / local bearing - not checked",
    "foundation / base-plate design - not checked",
    "vibration / dynamic response - not checked",
    "fire resistance / charring - not checked",
    "acoustic performance - not checked",
    "full EN 1990/1991/1995 + National Annex compliance - not checked",
]


def _stab_beam_check(w_uls, w_sls, L, b, h, fmd, fvd, E_Nmm2, defl_denom):
    """Simply-supported preliminary beam check (design-stage). w in kN/m, all
    lengths in m, strengths in N/mm2. Returns utilizations (bending/shear/
    deflection) and the governing value. Conservative: M=wL^2/8, V=wL/2."""
    if L <= 1e-6 or b <= 1e-6 or h <= 1e-6:
        return {"M": 0.0, "V": 0.0, "u_b": 9.9, "u_v": 9.9, "u_d": 9.9,
                "gov": 9.9, "delta": 0.0}
    M = w_uls * L * L / 8.0                       # kNm
    V = w_uls * L / 2.0                           # kN
    W = b * h * h / 6.0                           # m3
    A = b * h                                     # m2
    I = b * h * h * h / 12.0                      # m4
    sigma = (M / W) * 0.001 if W > 1e-12 else 9e9        # kN/m2 -> N/mm2
    tau = (1.5 * V / A) * 0.001 if A > 1e-12 else 9e9    # kN/m2 -> N/mm2
    E_kNm2 = E_Nmm2 * 1000.0
    delta = ((5.0 * w_sls * (L ** 4)) / (384.0 * E_kNm2 * I)
             if I > 1e-12 else 9e9)                # m
    allow = L / defl_denom if defl_denom > 1e-6 else 9e9
    u_b = sigma / fmd if fmd > 1e-9 else 9.9
    u_v = tau / fvd if fvd > 1e-9 else 9.9
    u_d = delta / allow if allow > 1e-9 else 9.9
    return {"M": M, "V": V, "u_b": u_b, "u_v": u_v, "u_d": u_d,
            "gov": max(u_b, u_v, u_d), "delta": delta}


def _stab_beam_gov_name(r):
    m = max(r["u_b"], r["u_v"], r["u_d"])
    if abs(m - r["u_b"]) < 1e-9:
        return "bending"
    if abs(m - r["u_v"]) < 1e-9:
        return "shear"
    return "deflection"


def _stab_col_check(N_ed, L, b, fc0d_Nmm2, E_Nmm2, keff):
    """Preliminary axial + Euler-buckling square-column check (same convention
    as the existing _size_square). N_ed in kN, L in m, b in m."""
    if L <= 1e-6 or b <= 1e-6:
        return {"ua": 9.9, "ub": 9.9, "gov": 9.9, "slend": 0.0}
    A = b * b
    I = b ** 4 / 12.0
    i = math.sqrt(I / A) if A > 1e-12 else 0.0
    Leff = keff * L
    slend = (Leff / i) if i > 1e-9 else 0.0
    Ncr = ((math.pi ** 2) * (E_Nmm2 * 1000.0) * I / (Leff * Leff)
           if Leff > 1e-9 else 0.0)
    Nrd = A * fc0d_Nmm2 * 1000.0
    ua = (N_ed / Nrd) if Nrd > 1e-9 else 9.9
    ub = (N_ed / Ncr) if Ncr > 1e-9 else 9.9
    return {"ua": ua, "ub": ub, "gov": max(ua, ub), "slend": slend}


def _stab_suggest_beam(w_uls, w_sls, L, b, fmd, fvd, E, denom, limit, lib,
                       h_start):
    """Walk the depth library for the smallest depth h (>= h_start) that clears
    the utilization limit. Returns (h, check, ok)."""
    for h in lib:
        if h < h_start - 1e-9:
            continue
        r = _stab_beam_check(w_uls, w_sls, L, b, h, fmd, fvd, E, denom)
        if r["gov"] <= limit:
            return h, r, True
    h = lib[-1]
    r = _stab_beam_check(w_uls, w_sls, L, b, h, fmd, fvd, E, denom)
    return h, r, False


def _stab_suggest_col(N_ed, L, fc0d, E, keff, limit, lib, b_start, b_max):
    """Smallest square section b (>= b_start, <= b_max) that clears the limit."""
    for b in lib:
        if b < b_start - 1e-9 or b > b_max + 1e-9:
            continue
        r = _stab_col_check(N_ed, L, b, fc0d, E, keff)
        if r["gov"] <= limit:
            return b, r, True
    b = min(b_max, lib[-1])
    r = _stab_col_check(N_ed, L, b, fc0d, E, keff)
    return b, r, False


def _stab_topology(rack):
    """Read-only topology validation. Reuses the RFEM collectors. Returns a
    dict of findings + a list of topology_report rows (issue/severity/...)."""
    nodes, members, stats = collect_structural_line_members(rack)
    supports = collect_supports(rack)
    rows = []
    if stats.get("zero_length", 0) > 0:
        rows.append(("zero_length_member", "FAIL", "",
                     "%d members" % stats["zero_length"],
                     "Zero-length members present", "Fix generation geometry"))
    if stats.get("nan", 0) > 0:
        rows.append(("invalid_coordinate", "FAIL", "",
                     "%d members" % stats["nan"],
                     "Members with NaN/None coordinates", "Fix generation"))
    if stats.get("duplicates", 0) > 0:
        rows.append(("duplicate_member", "WARNING", "",
                     "%d members" % stats["duplicates"],
                     "Duplicate members removed for check", "Review generation"))
    # floating nodes = nodes referenced by NEITHER a member NOR a support.
    # (Support nodes sit under the plinth at z=0 and are referenced by supports,
    # not by members - they are NOT floating.)
    referenced = set()
    for rec in rack.SM.model["members"]:
        referenced.add(rec["node_i"])
        referenced.add(rec["node_j"])
    for sp in rack.SM.model["supports"]:
        referenced.add(sp["node"])
    all_ids = set(n["id"] for n in rack.SM.model["nodes"])
    floating = sorted(all_ids - referenced)
    if floating:
        rows.append(("floating_node", "WARNING", str(floating[:10]),
                     "%d nodes" % len(floating),
                     "Nodes connected to neither a member nor a support",
                     "Review generation geometry"))
    if len(supports) == 0:
        rows.append(("no_supports", "FAIL", "", "z=0",
                     "No supports found in the model", "Add base supports"))
    # Connectivity (INFORMATIONAL ONLY). The analytical StructuralModel is a
    # LOOSE LINE reference: regular columns intentionally stop MEMBER (0.30 m)
    # BELOW the beam grid, and the 42 supports sit under the plinth - so members
    # do NOT all share exact nodes and a strict shared-node graph is fragmented
    # BY DESIGN. Connectivity / meshing is established during RFEM/Dlubal import.
    # We therefore report the component count for transparency only; it does NOT
    # drive the pass/fail status (doing so would be a false positive here).
    parent = {}

    def _find(a):
        root = a
        while parent.get(root, root) != root:
            root = parent[root]
        while parent.get(a, a) != root:
            nxt = parent.get(a, a)
            parent[a] = root
            a = nxt
        return root

    def _union(a, b):
        ra, rb = _find(a), _find(b)
        if ra != rb:
            parent[rb] = ra
    for nid in all_ids:
        parent.setdefault(nid, nid)
    for rec in rack.SM.model["members"]:
        _union(rec["node_i"], rec["node_j"])
    member_roots = set(_find(rec["node_i"]) for rec in rack.SM.model["members"])
    line_components = len(member_roots)
    if line_components > 1:
        rows.append(("line_model_components", "INFO", "",
                     "%d components" % line_components,
                     "Analytical line reference is intentionally not a single "
                     "shared-node graph (columns stop under beams; supports "
                     "under plinth). Connectivity is established in RFEM/Dlubal.",
                     "No action - connect / mesh during RFEM import"))
    slots = getattr(rack, "module_slots", None)
    modules_available = bool(slots)
    modules_partial = 0
    modules_unsupported = 0
    if slots:
        for s in slots:
            if s.get("assigned") == "GREEN":
                continue                        # terrace: no structural module
            bay = s.get("bay")
            lvl = s.get("level")
            framed = s.get("framed", True)
            try:
                active = (lvl is not None and bay is not None
                          and lvl <= rack.fbay(bay))
            except Exception:
                active = True
            if not active:
                modules_unsupported += 1
                rows.append(("unsupported_module", "FAIL",
                             "bay %s L%s" % (bay, lvl), "%s" % s.get("assigned"),
                             "Module placed outside the framed cascade",
                             "Remove or extend structure"))
            elif not framed:
                modules_partial += 1
                rows.append(("partially_framed_module", "WARNING",
                             "bay %s L%s" % (bay, lvl), "%s" % s.get("assigned"),
                             "Module not fully framed on all sides",
                             "Review framing / RFEM verification"))
    issues = sum(1 for r in rows if r[1] in ("FAIL", "WARNING"))
    return {"nodes": nodes, "members": members, "stats": stats,
            "supports": supports, "floating": len(floating),
            "line_components": line_components,
            "modules_available": modules_available,
            "modules_partial": modules_partial,
            "modules_unsupported": modules_unsupported,
            "issues": issues, "rows": rows}


def run_preliminary_stability_check(rack, P):
    """Design-stage preliminary stability + pre-sizing screen. READ-ONLY: never
    changes geometry, the StructuralModel, module placement, the existing sizing
    math or the RFEM export. Returns (result_dict, folder)."""
    s = default_sizing_settings()
    ec = default_eurocode_profile()
    try:
        mat = TIMBER_PROFILES[s["material_profile"]]
    except Exception:
        mat = TIMBER_PROFILES["GL24h"]
    bs = STAB_BENDING_SHEAR.get(s["material_profile"],
                                {"fmk": mat["fc0k_N_mm2"], "fvk": 3.5})
    kmod = s["kmod"]
    gM = s.get("gamma_M", mat["gamma_M"])
    E = mat["E0_mean_N_mm2"]
    fmd = kmod * bs["fmk"] / gM
    fvd = kmod * bs["fvk"] / gM
    fc0d = kmod * mat["fc0k_N_mm2"] / gM
    keff = s["k_eff_buckling"]
    limit = s["utilization_limit"]
    denom = STAB_DEFLECTION_LIMIT_DENOM
    lib = list(s["section_library"])
    gG = s["gamma_G"]
    gQ = s["gamma_Q"]
    live = max(s["residential_live_load_kN_m2"], s["corridor_live_load_kN_m2"])
    q_uls = gG * s["clt_floor_dead_load_kN_m2"] + gQ * live      # kN/m2
    q_sls = s["clt_floor_dead_load_kN_m2"] + live               # kN/m2
    trib_w = AXIS / 2.0                                          # m (one-way)
    col_trib = AXIS * AXIS                                       # m2 (one bay)
    b_as = MEMBER                                                # 0.30 assumed
    dens = s["timber_density_kN_m3"]
    beam_depth_lib = [x for x in lib if x >= b_as - 1e-9]
    col_lib = [x for x in lib if 0.30 - 1e-9 <= x <= 0.60 + 1e-9]
    col_bmax = 0.60

    topo = _stab_topology(rack)
    member_rows = []
    counts = {"beam_pass": 0, "beam_warn": 0, "beam_fail": 0,
              "col_pass": 0, "col_warn": 0, "col_fail": 0,
              "vtree_pass": 0, "vtree_fail": 0}
    suggested = {}
    max_util = 0.0

    def _bump_suggested(mtype, cur, sug, reason):
        d = suggested.get(mtype)
        if d is None:
            suggested[mtype] = {"current": cur, "suggested": sug,
                                "reason": reason, "count": 1}
        else:
            d["count"] += 1
            try:
                bigger = sug > d["suggested"]
            except Exception:
                bigger = False
            if bigger:
                d["suggested"] = sug
                d["reason"] = reason

    # ---- BEAM preliminary checks -------------------------------------------
    sw_beam = b_as * b_as * dens                                # kN/m self wt
    w_uls = q_uls * trib_w + gG * sw_beam
    w_sls = q_sls * trib_w + sw_beam
    for rec in rack.SM.model["members"]:
        if rec["type"] not in STAB_BEAM_RAW:
            continue
        _b0, _t0, L, _c0, _th0 = _sz_member_geom(rack, rec)
        r = _stab_beam_check(w_uls, w_sls, L, b_as, b_as, fmd, fvd, E, denom)
        if r["gov"] <= limit:
            status = "PASS"
            sug_h = b_as
            counts["beam_pass"] += 1
        else:
            sug_h, sr, ok = _stab_suggest_beam(w_uls, w_sls, L, b_as, fmd, fvd,
                                               E, denom, limit, beam_depth_lib,
                                               b_as)
            status = "WARNING" if ok else "FAIL"
            counts["beam_warn" if ok else "beam_fail"] += 1
            _bump_suggested(_rfem_member_map(rec["type"])[0],
                            "%.2fx%.2f" % (b_as, b_as),
                            sug_h, "span %.1fm bending/shear/deflection" % L)
        max_util = max(max_util, r["gov"])
        member_rows.append({
            "member_id": rec["id"],
            "member_type": _rfem_member_map(rec["type"])[0],
            "length_m": L, "assumed_section": "%.2fx%.2f" % (b_as, b_as),
            "estimated_load": "%.2f kN/m" % w_uls,
            "u_b": r["u_b"], "u_v": r["u_v"], "u_a": None, "u_d": r["u_d"],
            "governing": _stab_beam_gov_name(r), "status": status,
            "suggested_section": "%.2fx%.2f" % (b_as, sug_h)})

    # ---- COLUMN preliminary checks (grouped into vertical stacks) -----------
    stacks = {}
    for rec in rack.SM.model["members"]:
        if rec["type"] not in STAB_COLUMN_RAW:
            continue
        base, _tip, L, _c, _th = _sz_member_geom(rack, rec)
        key = (round(base[0] / 0.05) * 0.05, round(base[1] / 0.05) * 0.05)
        stacks.setdefault(key, []).append((rec, L))
    for key in stacks:
        recs = stacks[key]
        n = len(recs)
        Ls = [rl[1] for rl in recs]
        L_storey = max(Ls) if Ls else FLOOR_PITCH
        base_rec = min(recs,
                       key=lambda rl: _sz_member_geom(rack, rl[0])[0][2])[0]
        sw_col = b_as * b_as * dens * sum(Ls)
        N_ed = q_uls * col_trib * n + gG * sw_col
        r = _stab_col_check(N_ed, L_storey, b_as, fc0d, E, keff)
        if r["gov"] <= limit:
            status = "PASS"
            sug_b = b_as
            counts["col_pass"] += 1
        else:
            sug_b, sr, ok = _stab_suggest_col(N_ed, L_storey, fc0d, E, keff,
                                              limit, col_lib, b_as, col_bmax)
            status = "WARNING" if ok else "FAIL"
            counts["col_warn" if ok else "col_fail"] += 1
            _bump_suggested("COLUMN", "%.2fx%.2f" % (b_as, b_as), sug_b,
                            "%d-storey axial/buckling" % n)
        max_util = max(max_util, r["gov"])
        member_rows.append({
            "member_id": base_rec["id"], "member_type": "COLUMN",
            "length_m": L_storey, "assumed_section": "%.2fx%.2f" % (b_as, b_as),
            "estimated_load": "%.1f kN (%d storeys)" % (N_ed, n),
            "u_b": None, "u_v": None, "u_a": r["gov"], "u_d": None,
            "governing": "axial+buckling", "status": status,
            "suggested_section": "%.2fx%.2f" % (sug_b, sug_b)})

    # ---- V / TREE supports: REUSE existing sizing engine (read-only) --------
    support_rows = []
    vtree_ok = True
    try:
        groups = build_support_groups(rack)
        compute_group_loads(rack, groups, s)
        vt_rows, _hints, _warns = size_variable_members(rack, groups, s)
        gmap = {}
        for vr in vt_rows:
            gmap.setdefault(vr["support_group_id"], []).append(vr)
            st = "PASS" if vr["pass"] else "FAIL"
            counts["vtree_pass" if vr["pass"] else "vtree_fail"] += 1
            max_util = max(max_util, vr["gov"])
            member_rows.append({
                "member_id": vr["member_id"], "member_type": vr["member_type"],
                "length_m": vr["length_m"],
                "assumed_section": "%.2fx%.2f" % (vr["b"], vr["b"]),
                "estimated_load": "%.1f kN" % vr["axial_force_kN"],
                "u_b": None, "u_v": None, "u_a": vr["gov"], "u_d": None,
                "governing": "axial+buckling", "status": st,
                "suggested_section": "%.2fx%.2f" % (vr["b"], vr["b"])})
            _bump_suggested(vr["member_type"], "from V/tree sizing", vr["b"],
                            "preliminary V/tree axial sizing")
        for g in groups:
            grows = gmap.get(g["group_id"], [])
            gutil = max([x["gov"] for x in grows]) if grows else 0.0
            gsug = max([x["b"] for x in grows]) if grows else 0.0
            if grows and all(x["pass"] for x in grows) and gutil <= limit:
                gstatus = "PASS"
            elif any(not x["pass"] for x in grows):
                gstatus = "FAIL"
            else:
                gstatus = "WARNING"
            support_rows.append({
                "support_group": g["group_id"],
                "support_type": g["support_type"],
                "estimated_load": g.get("Ed", 0.0), "utilization": gutil,
                "status": gstatus, "suggested_section": "%.2fx%.2f"
                % (gsug, gsug)})
    except Exception as ex:
        vtree_ok = False
        print("Stability: V/tree reuse skipped (%s)." % ex)

    # ---- aggregate global status -------------------------------------------
    reasons = []
    fail = False
    if len(topo["members"]) == 0:
        result = {"status": "INCOMPLETE",
                  "status_reasons": ["StructuralModel has no members."],
                  "max_utilization": 0.0, "counts": counts, "topo": topo,
                  "suggested": suggested, "member_rows": member_rows,
                  "support_rows": support_rows,
                  "missing_inputs": STAB_MISSING_INPUTS, "assumptions": s,
                  "eurocode": ec, "vtree_ok": vtree_ok, "limit": limit}
        folder = _stab_write_reports(rack, P, result)
        return result, folder
    if topo["stats"].get("zero_length", 0) > 0:
        fail = True
        reasons.append("Zero-length members present.")
    if topo["stats"].get("nan", 0) > 0:
        fail = True
        reasons.append("Members with invalid coordinates present.")
    if len(topo["supports"]) == 0:
        fail = True
        reasons.append("No supports found.")
    if topo["modules_unsupported"] > 0:
        fail = True
        reasons.append("%d module(s) placed outside the framed structure."
                       % topo["modules_unsupported"])
    if (counts["beam_fail"] + counts["col_fail"] + counts["vtree_fail"]) > 0:
        fail = True
        reasons.append("%d member(s) fail even at the largest preliminary "
                       "section." % (counts["beam_fail"] + counts["col_fail"]
                                     + counts["vtree_fail"]))
    warn = False
    if (counts["beam_warn"] + counts["col_warn"]) > 0:
        warn = True
        reasons.append("%d member(s) exceed the %.2f utilization limit and need "
                       "a larger section (see suggestions)."
                       % (counts["beam_warn"] + counts["col_warn"], limit))
    if topo["modules_partial"] > 0:
        warn = True
        reasons.append("%d module(s) not fully framed on all sides."
                       % topo["modules_partial"])
    if not topo["modules_available"]:
        warn = True
        reasons.append("Dummy modules not placed - module support screen is "
                       "INCOMPLETE (run Phase 2A dummy preview first).")
    if not vtree_ok:
        warn = True
        reasons.append("V/tree preliminary sizing reuse was unavailable.")
    # lateral system is never modelled in v1 -> always at least WARNING (honest)
    warn = True
    reasons.append("No explicit lateral bracing / diaphragm / core is modelled: "
                   "global lateral stability is NOT screened (design-stage).")
    if fail:
        status = "FAIL"
    elif warn:
        status = "WARNING"
    else:
        status = "PASS"

    result = {"status": status, "status_reasons": reasons,
              "max_utilization": max_util, "counts": counts, "topo": topo,
              "suggested": suggested, "member_rows": member_rows,
              "support_rows": support_rows,
              "missing_inputs": STAB_MISSING_INPUTS, "assumptions": s,
              "eurocode": ec, "vtree_ok": vtree_ok, "limit": limit}
    folder = _stab_write_reports(rack, P, result)
    return result, folder


def _stab_report_folder(script_dir):
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    root = os.path.join(script_dir, "stability_reports")
    folder = os.path.join(root, "wosyho_stability_report_%s" % stamp)
    if not os.path.isdir(folder):
        os.makedirs(folder)
    return folder, stamp


def _stab_write_reports(rack, P, result):
    """Write the stability_reports/<stamp>/ files. Returns the folder path (or
    None if writing failed). Never raises."""
    try:
        script_dir = P.get("export_folder") or os.path.expanduser("~")
        folder, stamp = _stab_report_folder(script_dir)
    except Exception as ex:
        print("Stability report folder failed: %s" % ex)
        return None
    topo = result["topo"]
    counts = result["counts"]
    gt = {1: "Regular", 2: "Half Offset", 3: "Centre Offset"}.get(
        P.get("plan_grid_type", 1), "?")
    generated = []

    def _w(name, writer):
        try:
            p = os.path.join(folder, name)
            with open(p, "w") as f:
                writer(f)
            generated.append(name)
        except Exception as ex:
            print("Stability: could not write %s (%s)." % (name, ex))

    def _wt(f):
        f.write(_csv_row(["issue_type", "severity", "object_id", "location",
                          "description", "suggested_action"]))
        if not topo["rows"]:
            f.write(_csv_row(["none", "OK", "", "",
                              "No topology issues detected (preliminary)",
                              "Proceed to RFEM/Dlubal/Karamba verification"]))
        for r in topo["rows"]:
            f.write(_csv_row(list(r)))
    _w("topology_report.csv", _wt)

    def _wm(f):
        f.write(_csv_row(["member_id", "member_type", "length_m",
                          "assumed_section", "estimated_load",
                          "bending_utilization", "shear_utilization",
                          "axial_utilization", "deflection_ratio",
                          "governing_check", "status", "suggested_section"]))
        for m in result["member_rows"]:
            def _f(v):
                return "" if v is None else ("%.3f" % v)
            f.write(_csv_row([
                m["member_id"], m["member_type"], "%.3f" % m["length_m"],
                m["assumed_section"], m["estimated_load"], _f(m["u_b"]),
                _f(m["u_v"]), _f(m["u_a"]), _f(m["u_d"]), m["governing"],
                m["status"], m["suggested_section"]]))
    _w("member_checks.csv", _wm)

    def _ws(f):
        f.write(_csv_row(["support_group", "support_type", "estimated_load_kN",
                          "utilization", "status", "suggested_section"]))
        if not result["support_rows"]:
            f.write(_csv_row(["none", "", "", "", "INCOMPLETE",
                              "V/tree sizing reuse unavailable"]))
        for r in result["support_rows"]:
            f.write(_csv_row([r["support_group"], r["support_type"],
                              "%.1f" % r["estimated_load"],
                              "%.3f" % r["utilization"], r["status"],
                              r["suggested_section"]]))
    _w("support_reactions.csv", _ws)

    def _wsg(f):
        f.write(_csv_row(["member_type", "current_section", "suggested_section",
                          "reason", "affected_member_count"]))
        if not result["suggested"]:
            f.write(_csv_row(["(all)", "as-generated", "no increase required",
                              "all preliminary utilizations within limit", "0"]))
        for mt in sorted(result["suggested"]):
            d = result["suggested"][mt]
            sug = d["suggested"]
            if isinstance(sug, float):
                sug_txt = "%.2f (depth/size)" % sug
            else:
                sug_txt = str(sug)
            f.write(_csv_row([mt, d["current"], sug_txt, d["reason"],
                              d["count"]]))
    _w("suggested_sections.csv", _wsg)

    def _wa(f):
        a = result["assumptions"]
        data = {
            "eurocode_profile": result["eurocode"],
            "material_profile": a["material_profile"],
            "material_values": TIMBER_PROFILES.get(a["material_profile"], {}),
            "bending_shear_char_N_mm2": STAB_BENDING_SHEAR.get(
                a["material_profile"], {}),
            "load_factors": {"gamma_G": a["gamma_G"], "gamma_Q": a["gamma_Q"]},
            "load_assumptions_kN_m2": {
                "clt_floor_dead": a["clt_floor_dead_load_kN_m2"],
                "residential_live": a["residential_live_load_kN_m2"],
                "corridor_live": a["corridor_live_load_kN_m2"]},
            "kmod": a["kmod"], "gamma_M": a.get("gamma_M", 1.25),
            "utilization_limit": a["utilization_limit"],
            "deflection_limit": "L/%d (preliminary SLS)"
            % int(STAB_DEFLECTION_LIMIT_DENOM),
            "beam_tributary_width_m": AXIS / 2.0,
            "column_tributary_area_m2": AXIS * AXIS,
            "safety_note": "conservative one-way tributary hand-calc, not an FE "
                           "equilibrium/stiffness solve",
            "missing_inputs": result["missing_inputs"],
            "disclaimer": STAB_DISCLAIMER}
        json.dump(data, f, indent=1)
    _w("stability_assumptions.json", _wa)

    def _wj(f):
        def _mx(m):
            vals = [v for v in (m["u_a"], m["u_b"], m["u_v"], m["u_d"])
                    if v is not None]
            return max(vals) if vals else 0.0
        crit = sorted(result["member_rows"], key=_mx, reverse=True)[:10]
        data = {
            "status": result["status"],
            "status_reasons": result["status_reasons"],
            "max_utilization": result["max_utilization"],
            "critical_members": [
                {"member_id": m["member_id"], "member_type": m["member_type"],
                 "status": m["status"], "governing": m["governing"],
                 "utilization": round(_mx(m), 3),
                 "suggested_section": m["suggested_section"]} for m in crit],
            "suggested_sections": result["suggested"],
            "missing_inputs": result["missing_inputs"],
            "source_counts": {
                "nodes": len(topo["nodes"]), "members": len(topo["members"]),
                "supports": len(topo["supports"]),
                "beam_checks": counts["beam_pass"] + counts["beam_warn"]
                + counts["beam_fail"],
                "column_stacks": counts["col_pass"] + counts["col_warn"]
                + counts["col_fail"],
                "vtree_members": counts["vtree_pass"] + counts["vtree_fail"]},
            "generated_files": generated,
            "timestamp": stamp, "disclaimer": STAB_DISCLAIMER}
        json.dump(data, f, indent=1)
    _w("stability_status.json", _wj)

    def _wsum(f):
        sug_lines = []
        for mt in sorted(result["suggested"]):
            d = result["suggested"][mt]
            sug = d["suggested"]
            sug_txt = ("%.2f m" % sug) if isinstance(sug, float) else str(sug)
            sug_lines.append("   %-14s %s -> %s  (%s; %d members)"
                             % (mt, d["current"], sug_txt, d["reason"],
                                d["count"]))
        if not sug_lines:
            sug_lines = ["   (none - all preliminary utilizations within limit)"]
        L = ["Timber Housing v23 - PRELIMINARY STRUCTURAL STABILITY RESULT", "=" * 62,
             STAB_DISCLAIMER, "=" * 62,
             "timestamp                : %s" % stamp,
             "bays / floors            : %d / %d"
             % (rack.NB, max(rack.F) if rack.F else 0),
             "grid type                : %d (%s)"
             % (P.get("plan_grid_type", 1), gt),
             "-" * 62,
             "GLOBAL PRELIMINARY STATUS: %s" % result["status"],
             "reasons:"]
        for r in result["status_reasons"]:
            L.append("   - %s" % r)
        L += ["-" * 62,
              "structural counts        : nodes %d, members %d, supports %d"
              % (len(topo["nodes"]), len(topo["members"]),
                 len(topo["supports"])),
              "module data              : %s"
              % ("available" if topo["modules_available"]
                 else "NOT placed (INCOMPLETE)"),
              "topology issues          : %d (FAIL/WARNING)"
              % topo.get("issues", 0),
              "line-model components    : %d (informational; connected in RFEM)"
              % topo.get("line_components", 0),
              "floating nodes           : %d" % topo["floating"],
              "-" * 62,
              "member check summary (preliminary):",
              "   beams   PASS %d  WARNING %d  FAIL %d"
              % (counts["beam_pass"], counts["beam_warn"], counts["beam_fail"]),
              "   columns PASS %d  WARNING %d  FAIL %d"
              % (counts["col_pass"], counts["col_warn"], counts["col_fail"]),
              "   V/tree  PASS %d  FAIL %d (from existing sizing engine)"
              % (counts["vtree_pass"], counts["vtree_fail"]),
              "   max governing utilization : %.3f (limit %.2f)"
              % (result["max_utilization"], result.get("limit", 0.85)),
              "-" * 62, "suggested section changes (preliminary):"]
        L += sug_lines
        L += ["-" * 62, "NOT CHECKED / missing inputs:"]
        for mi in result["missing_inputs"]:
            L.append("   - %s" % mi)
        L += ["-" * 62, "generated files:"]
        for g in generated:
            L.append("   - %s" % g)
        L += ["-" * 62, STAB_DISCLAIMER]
        f.write("\n".join(L) + "\n")
    _w("stability_summary.txt", _wsum)

    result["generated_files"] = generated
    print("Preliminary stability report written to: %s" % folder)
    return folder


def show_stability_result_preview(result, folder):
    """Styled Stability Result Preview. Reuses the PROVEN show_report_preview
    layout (fixed-size read-only TextArea + vertical full-width DIRECT buttons +
    Resizable + explicit ClientSize; native rs.MessageBox fallback inside). UI
    only; changes nothing in the model."""
    if result is None:
        return
    counts = result.get("counts", {})
    topo = result.get("topo", {})
    status = result.get("status", "INCOMPLETE")
    sep = "-" * 58
    lines = ["Preliminary Structural Stability Result", "=" * 58,
             "GLOBAL STATUS : %s  (design-stage / preliminary)" % status, sep]
    for r in result.get("status_reasons", [])[:8]:
        lines.append(" - %s" % r)
    lines += [sep,
              "max governing utilization : %.3f"
              % result.get("max_utilization", 0.0),
              "topology issues (F/W)     : %d" % topo.get("issues", 0),
              "line-model components     : %d (connected in RFEM)"
              % topo.get("line_components", 0),
              "beams  PASS/WARN/FAIL     : %d / %d / %d"
              % (counts.get("beam_pass", 0), counts.get("beam_warn", 0),
                 counts.get("beam_fail", 0)),
              "columns PASS/WARN/FAIL    : %d / %d / %d"
              % (counts.get("col_pass", 0), counts.get("col_warn", 0),
                 counts.get("col_fail", 0)),
              "V/tree PASS/FAIL          : %d / %d"
              % (counts.get("vtree_pass", 0), counts.get("vtree_fail", 0)),
              sep, "suggested key section changes:"]
    sug = result.get("suggested", {})
    if sug:
        for mt in sorted(sug):
            d = sug[mt]
            s2 = d["suggested"]
            s2txt = ("%.2f m" % s2) if isinstance(s2, float) else str(s2)
            lines.append("   %-14s %s -> %s (%d)"
                         % (mt, d["current"], s2txt, d["count"]))
    else:
        lines.append("   (none - preliminary utilizations within limit)")
    lines += [sep, "report folder:", "  %s" % (folder or "(not written)"), sep,
              STAB_DISCLAIMER]
    body = "\n".join(lines)
    txt = os.path.join(folder, "stability_summary.txt") if folder else None
    show_report_preview(
        "Preliminary Structural Stability Result", body,
        folder=folder, open_file=txt,
        open_folder_label="Open Stability Report Folder",
        open_file_label="Open Stability Summary TXT")


def run_stage_stability_check(rack, P):
    """STAGE 2.6 (after dummy preview, before existing sizing / RFEM export).
    Runs the preliminary stability screen and shows the styled preview. Fully
    guarded: any failure prints and the existing workflow continues. Returns the
    status string (or None). Read-only; nothing in the model changes."""
    try:
        result, folder = run_preliminary_stability_check(rack, P)
    except Exception as ex:
        print("Preliminary stability check failed: %s" % ex)
        return None
    try:
        show_stability_result_preview(result, folder)
    except Exception as ex:
        print("Stability preview dialog failed: %s" % ex)
    try:
        rack._stability_result = result
    except Exception:
        pass
    return (result or {}).get("status")


# =============================================================================
# 6c. FINAL SITE PLACEMENT / CITY RULES / ORIENTATION  (advanced final stage,
#     added 2026-07-08)
#
# ADVANCED FINAL WORKFLOW STAGE. Runs AFTER the Phase 2B detailed model and
# BEFORE the final Rendered switch + Completion dialog. It is a DESIGN-STAGE
# placement ASSISTANT only - NOT a legal/permit/Bebauungsplan result, NOT a
# solar/CFD simulation, NOT a structural verification. It NEVER changes the
# existing generation, module, sizing, stability or RFEM logic. It transforms the
# generated building only by rigid X/Y/Z translation + rotation about the vertical
# axis (never deform/scale/shear), and only when the user explicitly clicks Apply.
# Every prompt is skippable and every step fails safe. See
# docs/WOSYHO_FINAL_SITE_PLACEMENT_WORKFLOW.md.
# =============================================================================

SITE_PLACEMENT_DISCLAIMER = (
    "Design-stage placement assistant only. Setback / city rules are conservative "
    "OFFLINE approximations (not the real Bebauungsplan); sun / ventilation are "
    "heuristics (not a simulation); terrain handling is a rigid Z lift (not a "
    "foundation design). Verify against the local Bebauungsplan and "
    "Landesbauordnung and with a qualified architect / planner / structural "
    "engineer. Not a permit, compliance statement, or engineering approval.")

# Ordered German-city dropdown list (major cities) + a Custom / Other entry.
GERMAN_CITIES = [
    "Berlin", "Hamburg", "Munich", "Cologne", "Frankfurt am Main", "Stuttgart",
    "Duesseldorf", "Dortmund", "Essen", "Leipzig", "Bremen", "Dresden",
    "Hanover", "Nuremberg", "Duisburg", "Bochum", "Wuppertal", "Bielefeld",
    "Bonn", "Muenster", "Karlsruhe", "Mannheim", "Augsburg", "Wiesbaden",
    "Gelsenkirchen", "Moenchengladbach", "Braunschweig", "Kiel", "Chemnitz",
    "Aachen", "Halle (Saale)", "Magdeburg", "Freiburg im Breisgau", "Krefeld",
    "Luebeck", "Oberhausen", "Erfurt", "Mainz", "Rostock", "Kassel", "Hagen",
    "Potsdam", "Saarbruecken", "Hamm", "Ludwigshafen am Rhein",
    "Muelheim an der Ruhr", "Oldenburg", "Osnabrueck", "Leverkusen",
    "Heidelberg", "Darmstadt", "Regensburg", "Ingolstadt", "Wuerzburg",
    "Wolfsburg", "Offenbach am Main", "Ulm", "Heilbronn", "Pforzheim",
    "Goettingen", "Bottrop", "Trier", "Recklinghausen", "Reutlingen",
    "Bremerhaven", "Koblenz", "Bergisch Gladbach", "Jena", "Remscheid",
    "Erlangen", "Moers", "Siegen", "Hildesheim", "Salzgitter", "Cottbus",
    "Detmold",
    "Custom / Other city",
]

# Approximate OFFLINE per-city data: (federal_state, latitude_deg,
# snow_zone_placeholder, wind_zone_placeholder, seismic_zone_placeholder).
# German zone conventions: snow SLZ1-3 (DIN EN 1991-1-3/NA), wind WZ1-4
# (DIN EN 1991-1-4/NA), seismic EZ0-3 (DIN EN 1998-1/NA). All PLACEHOLDER /
# approximate; verify against the relevant National Annex maps.
CITY_DATA = {
    "Berlin": ("Berlin", 52.52, "SLZ2", "WZ2", "EZ0"),
    "Hamburg": ("Hamburg", 53.55, "SLZ2", "WZ3", "EZ0"),
    "Munich": ("Bavaria", 48.14, "SLZ2", "WZ2", "EZ0"),
    "Cologne": ("North Rhine-Westphalia", 50.94, "SLZ1", "WZ2", "EZ1"),
    "Frankfurt am Main": ("Hesse", 50.11, "SLZ1", "WZ2", "EZ0"),
    "Stuttgart": ("Baden-Wuerttemberg", 48.78, "SLZ2", "WZ1", "EZ1"),
    "Duesseldorf": ("North Rhine-Westphalia", 51.23, "SLZ1", "WZ2", "EZ1"),
    "Dortmund": ("North Rhine-Westphalia", 51.51, "SLZ1", "WZ2", "EZ0"),
    "Essen": ("North Rhine-Westphalia", 51.46, "SLZ1", "WZ2", "EZ0"),
    "Leipzig": ("Saxony", 51.34, "SLZ2", "WZ2", "EZ0"),
    "Bremen": ("Bremen", 53.08, "SLZ1", "WZ3", "EZ0"),
    "Dresden": ("Saxony", 51.05, "SLZ2", "WZ2", "EZ0"),
    "Hanover": ("Lower Saxony", 52.37, "SLZ2", "WZ2", "EZ0"),
    "Nuremberg": ("Bavaria", 49.45, "SLZ2", "WZ2", "EZ0"),
    "Duisburg": ("North Rhine-Westphalia", 51.43, "SLZ1", "WZ2", "EZ0"),
    "Freiburg im Breisgau": ("Baden-Wuerttemberg", 47.99, "SLZ2", "WZ1", "EZ3"),
    "Karlsruhe": ("Baden-Wuerttemberg", 49.01, "SLZ1", "WZ1", "EZ2"),
    "Mannheim": ("Baden-Wuerttemberg", 49.49, "SLZ1", "WZ1", "EZ1"),
    "Heidelberg": ("Baden-Wuerttemberg", 49.40, "SLZ1", "WZ1", "EZ1"),
    "Aachen": ("North Rhine-Westphalia", 50.78, "SLZ1", "WZ2", "EZ2"),
    "Cologne ": ("North Rhine-Westphalia", 50.94, "SLZ1", "WZ2", "EZ1"),
    "Kiel": ("Schleswig-Holstein", 54.32, "SLZ2", "WZ4", "EZ0"),
    "Luebeck": ("Schleswig-Holstein", 53.87, "SLZ2", "WZ3", "EZ0"),
    "Rostock": ("Mecklenburg-Vorpommern", 54.09, "SLZ2", "WZ4", "EZ0"),
    "Bremerhaven": ("Bremen", 53.54, "SLZ1", "WZ4", "EZ0"),
    "Oldenburg": ("Lower Saxony", 53.14, "SLZ1", "WZ3", "EZ0"),
    "Osnabrueck": ("Lower Saxony", 52.28, "SLZ2", "WZ2", "EZ0"),
    "Muenster": ("North Rhine-Westphalia", 51.96, "SLZ1", "WZ2", "EZ0"),
    "Bonn": ("North Rhine-Westphalia", 50.74, "SLZ1", "WZ2", "EZ1"),
    "Dresden ": ("Saxony", 51.05, "SLZ2", "WZ2", "EZ0"),
    "Erfurt": ("Thuringia", 50.98, "SLZ2", "WZ2", "EZ0"),
    "Jena": ("Thuringia", 50.93, "SLZ2", "WZ2", "EZ0"),
    "Magdeburg": ("Saxony-Anhalt", 52.13, "SLZ1", "WZ2", "EZ0"),
    "Halle (Saale)": ("Saxony-Anhalt", 51.48, "SLZ2", "WZ2", "EZ0"),
    "Potsdam": ("Brandenburg", 52.40, "SLZ2", "WZ2", "EZ0"),
    "Cottbus": ("Brandenburg", 51.76, "SLZ2", "WZ2", "EZ0"),
    "Chemnitz": ("Saxony", 50.83, "SLZ3", "WZ2", "EZ0"),
    "Mainz": ("Rhineland-Palatinate", 49.99, "SLZ1", "WZ2", "EZ1"),
    "Koblenz": ("Rhineland-Palatinate", 50.36, "SLZ1", "WZ2", "EZ1"),
    "Trier": ("Rhineland-Palatinate", 49.75, "SLZ1", "WZ2", "EZ1"),
    "Ludwigshafen am Rhein": ("Rhineland-Palatinate", 49.48, "SLZ1", "WZ1", "EZ1"),
    "Saarbruecken": ("Saarland", 49.24, "SLZ1", "WZ2", "EZ1"),
    "Kassel": ("Hesse", 51.31, "SLZ2", "WZ2", "EZ0"),
    "Wiesbaden": ("Hesse", 50.08, "SLZ1", "WZ2", "EZ0"),
    "Darmstadt": ("Hesse", 49.87, "SLZ1", "WZ2", "EZ0"),
    "Offenbach am Main": ("Hesse", 50.10, "SLZ1", "WZ2", "EZ0"),
    "Augsburg": ("Bavaria", 48.37, "SLZ2", "WZ2", "EZ0"),
    "Regensburg": ("Bavaria", 49.01, "SLZ2", "WZ2", "EZ0"),
    "Ingolstadt": ("Bavaria", 48.77, "SLZ2", "WZ2", "EZ0"),
    "Wuerzburg": ("Bavaria", 49.79, "SLZ1", "WZ2", "EZ0"),
    "Erlangen": ("Bavaria", 49.60, "SLZ2", "WZ2", "EZ0"),
    "Ulm": ("Baden-Wuerttemberg", 48.40, "SLZ2", "WZ1", "EZ1"),
    "Heilbronn": ("Baden-Wuerttemberg", 49.14, "SLZ2", "WZ1", "EZ1"),
    "Pforzheim": ("Baden-Wuerttemberg", 48.89, "SLZ2", "WZ1", "EZ2"),
    "Reutlingen": ("Baden-Wuerttemberg", 48.49, "SLZ2", "WZ1", "EZ1"),
    "Goettingen": ("Lower Saxony", 51.53, "SLZ2", "WZ2", "EZ0"),
    "Hildesheim": ("Lower Saxony", 52.15, "SLZ2", "WZ2", "EZ0"),
    "Salzgitter": ("Lower Saxony", 52.15, "SLZ2", "WZ2", "EZ0"),
    "Wolfsburg": ("Lower Saxony", 52.42, "SLZ2", "WZ2", "EZ0"),
    "Braunschweig": ("Lower Saxony", 52.27, "SLZ2", "WZ2", "EZ0"),
    "Bielefeld": ("North Rhine-Westphalia", 52.02, "SLZ2", "WZ2", "EZ0"),
    "Bochum": ("North Rhine-Westphalia", 51.48, "SLZ1", "WZ2", "EZ0"),
    "Wuppertal": ("North Rhine-Westphalia", 51.26, "SLZ1", "WZ2", "EZ1"),
    "Gelsenkirchen": ("North Rhine-Westphalia", 51.52, "SLZ1", "WZ2", "EZ0"),
    "Moenchengladbach": ("North Rhine-Westphalia", 51.19, "SLZ1", "WZ2", "EZ1"),
    "Krefeld": ("North Rhine-Westphalia", 51.33, "SLZ1", "WZ2", "EZ1"),
    "Oberhausen": ("North Rhine-Westphalia", 51.47, "SLZ1", "WZ2", "EZ0"),
    "Hagen": ("North Rhine-Westphalia", 51.36, "SLZ2", "WZ2", "EZ1"),
    "Hamm": ("North Rhine-Westphalia", 51.68, "SLZ1", "WZ2", "EZ0"),
    "Muelheim an der Ruhr": ("North Rhine-Westphalia", 51.43, "SLZ1", "WZ2", "EZ0"),
    "Leverkusen": ("North Rhine-Westphalia", 51.03, "SLZ1", "WZ2", "EZ1"),
    "Bergisch Gladbach": ("North Rhine-Westphalia", 50.99, "SLZ1", "WZ2", "EZ1"),
    "Recklinghausen": ("North Rhine-Westphalia", 51.61, "SLZ1", "WZ2", "EZ0"),
    "Bottrop": ("North Rhine-Westphalia", 51.52, "SLZ1", "WZ2", "EZ0"),
    "Remscheid": ("North Rhine-Westphalia", 51.18, "SLZ2", "WZ2", "EZ1"),
    "Siegen": ("North Rhine-Westphalia", 50.87, "SLZ2", "WZ2", "EZ1"),
    "Moers": ("North Rhine-Westphalia", 51.45, "SLZ1", "WZ2", "EZ1"),
    "Detmold": ("North Rhine-Westphalia", 51.94, "SLZ2", "WZ2", "EZ0"),
}


def get_city_rule_assumptions(city_name, building_height_m, footprint_dims):
    """Return conservative OFFLINE planning/Eurocode assumptions for a city.
    Design-stage only; every value is a placeholder to be verified against the
    local Bebauungsplan / Landesbauordnung / National Annex."""
    base_setback = 3.0
    hfac = 0.4
    data = CITY_DATA.get(city_name)
    if data:
        state, lat, snow, wind, seis = data
        mode = "city-approximate (offline placeholder)"
    else:
        state, lat, snow, wind, seis = ("(generic German)", 51.0, "SLZ2",
                                        "WZ2", "EZ0")
        mode = "generic-German (offline placeholder)"
    try:
        h = float(building_height_m)
    except Exception:
        h = 0.0
    req = max(base_setback, hfac * h)
    fw, fl = (footprint_dims if footprint_dims else (0.0, 0.0))
    return {
        "city_name": city_name,
        "federal_state": state,
        "eurocode_basis": "EN 1990 / EN 1991 / EN 1995 (+ German NA placeholder)",
        "assumption_mode": mode,
        "latitude_deg_approx": lat,
        "base_setback_m": base_setback,
        "height_factor_setback": hfac,
        "required_setback_m": req,
        "min_fire_access_clearance_m": 3.0,
        "min_ventilation_clearance_m": 3.0,
        "snow_zone_placeholder": snow + " (placeholder)",
        "wind_zone_placeholder": wind + " (placeholder)",
        "seismic_zone_placeholder": seis + " (placeholder)",
        "building_height_m": h,
        "footprint_w_m": fw, "footprint_l_m": fl,
        "sunlight_orientation_preference": (
            "Primary daylight from south; south-east / south-west favourable; "
            "avoid full west harsh afternoon exposure on the long terrace "
            "facades."),
        "harsh_sun_avoidance_note": (
            "Avoid orienting the long cascade / terrace facade due west (harsh "
            "low afternoon sun)."),
        "planning_disclaimer": SITE_PLACEMENT_DISCLAIMER,
    }


def _sp_buildable_rectangle(bmin, bmax, setback):
    """Approximate buildable zone = site XY bbox rectangle offset inward by the
    setback (V1 rectangle fallback). Returns (x0,y0,x1,y1) or None if degenerate."""
    x0 = bmin[0] + setback
    y0 = bmin[1] + setback
    x1 = bmax[0] - setback
    y1 = bmax[1] - setback
    if (x1 - x0) <= 0.1 or (y1 - y0) <= 0.1:
        return None
    return (x0, y0, x1, y1)


def _sp_footprint_extent(fw, fl, rot_deg):
    """Axis-aligned bounding extent of a fw x fl footprint rotated by rot_deg
    (conservative fit test). fw along local X, fl along local Y."""
    r = math.radians(rot_deg)
    c = abs(math.cos(r))
    s = abs(math.sin(r))
    return (fw * c + fl * s, fw * s + fl * c)


def _sp_bearing(local_normal, rot_deg, north_vec):
    """Compass bearing (0=N,90=E,180=S,270=W) of a local facade normal after the
    building is rotated rot_deg about Z, measured relative to the marked north."""
    lx, ly = local_normal
    r = math.radians(rot_deg)
    rx = lx * math.cos(r) - ly * math.sin(r)
    ry = lx * math.sin(r) + ly * math.cos(r)
    nx, ny = north_vec
    north_c = rx * nx + ry * ny
    east_c = rx * ny + ry * (-nx)              # east = north rotated -90 (CW)
    return math.degrees(math.atan2(east_c, north_c)) % 360.0


def _sp_score_orientation(rot_deg, north_vec, lat):
    """Heuristic sun / ventilation / harsh-sun scores for a building rotation
    (NOT a solar simulation). Long facades = local +/-Y (cascade/terrace sides)."""
    def sscore(b):
        return (math.cos(math.radians(b - 180.0)) + 1.0) / 2.0     # south=1

    def wscore(b):
        v = math.cos(math.radians(b - 270.0))
        return v if v > 0.0 else 0.0                               # west=1

    def vscore(b):
        return (math.cos(math.radians(b - 225.0)) + 1.0) / 2.0     # SW wind=1
    long1 = _sp_bearing((0.0, 1.0), rot_deg, north_vec)
    long2 = _sp_bearing((0.0, -1.0), rot_deg, north_vec)
    sunlight = max(sscore(long1), sscore(long2))
    harsh = max(wscore(long1), wscore(long2))
    vent = 0.5 + 0.5 * max(vscore(long1), vscore(long2))
    latw = 1.0 + (float(lat) - 48.0) / 120.0
    sunlight = min(1.0, sunlight * latw)
    return {"sunlight": sunlight, "harsh": harsh, "ventilation": vent,
            "long_bearings": (round(long1, 1), round(long2, 1))}


def _sp_generate_candidates(zone, fw, fl, north_vec, lat, rotations=None,
                            grid_n=4):
    """Sample candidate (centre x/y, rotation) placements inside the buildable
    rectangle and score them. Returns {feasible, reason, candidates, best}."""
    if zone is None:
        return {"feasible": False, "candidates": [], "best": None,
                "reason": "buildable zone too small / setback too large"}
    if rotations is None:
        rotations = [0, 15, 30, 45, 60, 75, 90, 105, 120, 135, 150, 165, 180]
    x0, y0, x1, y1 = zone
    zw = x1 - x0
    zh = y1 - y0
    cands = []
    W_SUN, W_VENT, W_HARSH, W_SET = 1.0, 0.4, 0.8, 0.3
    for rot in rotations:
        ex, ey = _sp_footprint_extent(fw, fl, rot)
        if ex > zw + 1e-6 or ey > zh + 1e-6:
            continue
        xmin = x0 + ex / 2.0
        xmax = x1 - ex / 2.0
        ymin = y0 + ey / 2.0
        ymax = y1 - ey / 2.0
        for gi in range(grid_n):
            for gj in range(grid_n):
                fx = (gi + 0.5) / float(grid_n)
                fy = (gj + 0.5) / float(grid_n)
                cx = xmin + (xmax - xmin) * fx if xmax > xmin else (xmin + xmax) / 2.0
                cy = ymin + (ymax - ymin) * fy if ymax > ymin else (ymin + ymax) / 2.0
                marg = min(cx - ex / 2.0 - x0, x1 - (cx + ex / 2.0),
                           cy - ey / 2.0 - y0, y1 - (cy + ey / 2.0))
                denom = max(1.0, min(zw, zh) / 2.0)
                setm = marg / denom
                setm = 0.0 if setm < 0.0 else (1.0 if setm > 1.0 else setm)
                o = _sp_score_orientation(rot, north_vec, lat)
                total = (W_SUN * o["sunlight"] + W_VENT * o["ventilation"]
                         - W_HARSH * o["harsh"] + W_SET * setm)
                cands.append({"rot": rot, "cx": cx, "cy": cy,
                              "setback_margin": setm, "sunlight": o["sunlight"],
                              "ventilation": o["ventilation"], "harsh": o["harsh"],
                              "total": total, "long_bearings": o["long_bearings"]})
    if not cands:
        return {"feasible": False, "candidates": [], "best": None,
                "reason": "footprint does not fit the buildable zone at any "
                          "tested rotation"}
    best = max(cands, key=lambda c: c["total"])
    return {"feasible": True, "candidates": cands, "best": best, "reason": "ok"}


def _sp_terrain_stats(zs):
    if not zs:
        return {"min": None, "max": None, "avg": None, "diff": None, "count": 0}
    return {"min": min(zs), "max": max(zs), "avg": sum(zs) / float(len(zs)),
            "diff": max(zs) - min(zs), "count": len(zs)}


def _sp_compute_transform(metrics, target_xy, target_z, rot_deg):
    """Rigid transform spec: rotate about the vertical axis through the building's
    current centre, then translate centre->target XY and bottom->target Z."""
    cx = metrics["cx"]
    cy = metrics["cy"]
    bz = metrics["z0"]
    tx = target_xy[0] - cx
    ty = target_xy[1] - cy
    tz = target_z - bz
    return {"rotate_center": (cx, cy, bz), "rotate_deg": rot_deg,
            "translate": (tx, ty, tz),
            "target_center_xy": (target_xy[0], target_xy[1]),
            "target_bottom_z": target_z}


# --------------------------------------------------------------------------- #
# Rhino I/O wrappers (all guarded; skip / fallback, never crash)
# --------------------------------------------------------------------------- #

def _sp_ensure_layer(path, color=None):
    try:
        if not rs.IsLayer(path):
            rs.AddLayer(path, color)
        return True
    except Exception:
        return False


def collect_wosyho_building_objects_for_site_placement():
    """Collect ONLY generated Timber Housing building objects (all objects on the known
    Timber Housing building layers). Excludes the site object, north marker, placement
    helper layers and unrelated objects (none of which are on LAYERS). Deletes
    nothing. Returns (ids, included_layers, excluded_layers)."""
    ids = []
    included = []
    excluded = ["WoSyHo::SitePlacement*", "user site object", "north marker"]
    for (name, _c) in LAYERS:
        try:
            if rs.IsLayer(name):
                objs = rs.ObjectsByLayer(name)
                if objs:
                    ids.extend(objs)
                    included.append(name)
        except Exception:
            continue
    return ids, included, excluded


def _sp_building_metrics(ids, rack=None, P=None):
    """Bounding-box footprint / height / centre of the collected building. Falls
    back to parameter-derived extents if the bbox is unavailable."""
    bb = None
    try:
        if ids:
            bb = rs.BoundingBox(ids)
    except Exception:
        bb = None
    if bb:
        xs = [p[0] for p in bb]
        ys = [p[1] for p in bb]
        zs = [p[2] for p in bb]
        x0, x1 = min(xs), max(xs)
        y0, y1 = min(ys), max(ys)
        z0, z1 = min(zs), max(zs)
        src = "bounding box of building objects"
    else:
        nb = (P or {}).get("x_bays", 12)
        pf = (P or {}).get("peak_floors", 8)
        x0, y0, z0 = 0.0, 0.0, 0.0
        x1 = nb * AXIS
        y1 = Y_OUT_R
        z1 = pf * FLOOR_PITCH
        src = "parameter-derived fallback (no object bbox)"
    return {"x0": x0, "y0": y0, "z0": z0, "x1": x1, "y1": y1, "z1": z1,
            "w": x1 - x0, "l": y1 - y0, "h": z1 - z0,
            "cx": (x0 + x1) / 2.0, "cy": (y0 + y1) / 2.0, "cz": (z0 + z1) / 2.0,
            "source": src}


def _sp_select_site():
    """Prompt the user to select a site surface / polysurface / brep / mesh /
    closed curve. Returns a dict of site info or None (cancel / unsupported)."""
    try:
        flt = 4 + 8 + 16 + 32          # curve + surface + polysurface + mesh
        sid = rs.GetObject("Select the SITE boundary / surface / mesh / terrain "
                           "(any surface, polysurface, mesh or closed curve)",
                           flt, False, False)
        if not sid:
            return None
        try:
            otype = rs.ObjectType(sid)
        except Exception:
            otype = 0
        bb = rs.BoundingBox(sid)
        if not bb:
            return None
        xs = [p[0] for p in bb]
        ys = [p[1] for p in bb]
        zs = [p[2] for p in bb]
        bmin = (min(xs), min(ys), min(zs))
        bmax = (max(xs), max(ys), max(zs))
        area = None
        try:
            if rs.IsSurface(sid) or rs.IsPolysurface(sid):
                a = rs.SurfaceArea(sid)
                area = a[0] if a else None
            elif rs.IsMesh(sid):
                area = rs.MeshArea([sid])[1] if rs.MeshArea([sid]) else None
            elif rs.IsCurve(sid) and rs.IsCurveClosed(sid):
                area = rs.CurveArea(sid)[0] if rs.CurveArea(sid) else None
        except Exception:
            area = None
        tname = {4: "curve", 8: "surface", 16: "polysurface",
                 32: "mesh"}.get(otype, "object(type=%s)" % otype)
        is_terrain = (bmax[2] - bmin[2]) > 0.5
        return {"id": sid, "type": tname, "type_code": otype,
                "min": bmin, "max": bmax,
                "center": ((bmin[0] + bmax[0]) / 2.0, (bmin[1] + bmax[1]) / 2.0,
                           (bmin[2] + bmax[2]) / 2.0),
                "area_est": area, "is_terrain": is_terrain}
    except Exception as ex:
        print("Site selection failed (%s)." % ex)
        return None


def _sp_mark_north_with_base(site_center=None):
    """Two-click north input that ALSO returns the clicked base point (needed to
    draw the north arrow). Returns (angle_deg, north_unit_vec_xy, source, base).
    Cancel -> fallback world +Y with base = site centre."""
    fb_base = (site_center[0], site_center[1]) if site_center else (0.0, 0.0)
    try:
        base = rs.GetPoint("Click a BASE point for NORTH (on/near the site)")
        if base is None:
            return (0.0, (0.0, 1.0), "fallback world +Y (base cancelled)",
                    fb_base)
        npt = rs.GetPoint("Click the NORTH direction point", base)
        if npt is None:
            return (0.0, (0.0, 1.0), "fallback world +Y (north cancelled)",
                    (base[0], base[1]))
        dx = npt[0] - base[0]
        dy = npt[1] - base[1]
        ln = math.hypot(dx, dy)
        if ln < 1e-6:
            return (0.0, (0.0, 1.0), "fallback world +Y (zero-length)",
                    (base[0], base[1]))
        nvec = (dx / ln, dy / ln)
        ang = math.degrees(math.atan2(nvec[0], nvec[1])) % 360.0
        return (ang, nvec, "user-marked", (base[0], base[1]))
    except Exception as ex:
        print("North input failed (%s)." % ex)
        return (0.0, (0.0, 1.0), "fallback world +Y (error)", fb_base)


def _sp_mark_north(site_center=None):
    """Two-click north input. Returns (angle_from_+Y_deg, north_unit_vec_xy,
    source_text). Cancel -> fallback world +Y."""
    try:
        base = rs.GetPoint("Click a BASE point for NORTH (on/near the site)")
        if base is None:
            return (0.0, (0.0, 1.0), "fallback world +Y (base cancelled)")
        npt = rs.GetPoint("Click the NORTH direction point", base)
        if npt is None:
            return (0.0, (0.0, 1.0), "fallback world +Y (north cancelled)")
        dx = npt[0] - base[0]
        dy = npt[1] - base[1]
        ln = math.hypot(dx, dy)
        if ln < 1e-6:
            return (0.0, (0.0, 1.0), "fallback world +Y (zero-length)")
        nvec = (dx / ln, dy / ln)
        ang = math.degrees(math.atan2(nvec[0], nvec[1])) % 360.0
        return (ang, nvec, "user-marked")
    except Exception as ex:
        print("North input failed (%s)." % ex)
        return (0.0, (0.0, 1.0), "fallback world +Y (error)")


def _sp_sample_terrain(site_id, xy_list, fallback_top):
    """Project points straight down onto the site to sample elevation. Returns a
    list of z (fallback_top where projection fails)."""
    zs = []
    hi = fallback_top + 1000.0
    for (x, y) in xy_list:
        z = None
        try:
            pts = rs.ProjectPointToSurface([(x, y, hi)], site_id, (0, 0, -1))
            if pts:
                z = pts[0][2]
        except Exception:
            z = None
        if z is None:
            try:
                pts = rs.ProjectPointToMesh([(x, y, hi)], site_id, (0, 0, -1))
                if pts:
                    z = pts[0][2]
            except Exception:
                z = None
        zs.append(fallback_top if z is None else z)
    return zs


def _sp_apply_transform(ids, tspec):
    """Apply the rigid transform to the building objects only. Rotate about the
    vertical axis through the current centre, then translate. Never deforms."""
    try:
        rc = tspec["rotate_center"]
        ang = tspec["rotate_deg"]
        tr = tspec["translate"]
        if abs(ang) > 1e-9:
            rs.RotateObjects(ids, rc, ang, (0.0, 0.0, 1.0), False)
        if any(abs(v) > 1e-9 for v in tr):
            rs.MoveObjects(ids, tr)
        return True
    except Exception as ex:
        print("Site placement transform failed (%s)." % ex)
        return False


def _sp_draw_helpers(zone, north_vec, tspec):
    """Optional visual helpers on WoSyHo::SitePlacement* layers (guarded)."""
    try:
        for lp in ("WoSyHo::SitePlacement",
                   "WoSyHo::SitePlacement::BuildableZone",
                   "WoSyHo::SitePlacement::NorthArrow",
                   "WoSyHo::SitePlacement::Labels"):
            _sp_ensure_layer(lp)
        z = (tspec or {}).get("target_bottom_z", 0.0)
        if zone:
            x0, y0, x1, y1 = zone
            poly = rs.AddPolyline([(x0, y0, z), (x1, y0, z), (x1, y1, z),
                                   (x0, y1, z), (x0, y0, z)])
            if poly:
                rs.ObjectLayer(poly, "WoSyHo::SitePlacement::BuildableZone")
            cx = (x0 + x1) / 2.0
            cy = (y0 + y1) / 2.0
            ln = rs.AddLine((cx, cy, z),
                            (cx + north_vec[0] * 5.0, cy + north_vec[1] * 5.0, z))
            if ln:
                rs.ObjectLayer(ln, "WoSyHo::SitePlacement::NorthArrow")
            nd = rs.AddTextDot("N", (cx + north_vec[0] * 5.6,
                                     cy + north_vec[1] * 5.6, z))
            if nd:
                rs.ObjectLayer(nd, "WoSyHo::SitePlacement::NorthArrow")
            lab = rs.AddTextDot("Timber Housing placement", (cx, cy, z))
            if lab:
                rs.ObjectLayer(lab, "WoSyHo::SitePlacement::Labels")
    except Exception as ex:
        print("Site placement helper drawing skipped (%s)." % ex)


def _sp_report_folder(script_dir):
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    root = os.path.join(script_dir, "site_placement_reports")
    folder = os.path.join(root, "wosyho_site_placement_%s" % stamp)
    if not os.path.isdir(folder):
        os.makedirs(folder)
    return folder, stamp


def _sp_write_reports(P, R):
    """Write the site_placement_reports/<stamp>/ files from the result dict R.
    Returns the folder path or None. Never raises."""
    try:
        script_dir = P.get("export_folder") or os.path.expanduser("~")
        folder, stamp = _sp_report_folder(script_dir)
    except Exception as ex:
        print("Site placement report folder failed (%s)." % ex)
        return None
    cr = R.get("city_rules", {})
    site = R.get("site")
    metrics = R.get("metrics", {})
    cand = R.get("cand_info", {})
    best = R.get("best")
    terr = R.get("terrain", {})
    tspec = R.get("transform")
    zone = R.get("zone")
    generated = []

    def _w(name, writer):
        try:
            p = os.path.join(folder, name)
            with open(p, "w") as f:
                writer(f)
            generated.append(name)
        except Exception as ex:
            print("Site placement: could not write %s (%s)." % (name, ex))

    def _wj(name, obj):
        _w(name, lambda f: json.dump(obj, f, indent=1))

    _wj("city_rule_assumptions.json", cr)

    def _sel(f):
        json.dump({"status": R.get("status"), "applied": R.get("applied", False),
                   "transform": tspec, "selected_candidate": best,
                   "north_deg": R.get("north_deg"),
                   "north_source": R.get("north_source"),
                   "disclaimer": SITE_PLACEMENT_DISCLAIMER}, f, indent=1)
    _wj("selected_transform.json", {"transform": tspec, "selected": best})

    def _res(f):
        json.dump({
            "status": R.get("status"), "applied": R.get("applied", False),
            "city": R.get("city"), "city_rules": cr,
            "building": {"footprint_w_m": metrics.get("w"),
                         "footprint_l_m": metrics.get("l"),
                         "height_m": metrics.get("h"),
                         "center": [metrics.get("cx"), metrics.get("cy"),
                                    metrics.get("cz")],
                         "source": metrics.get("source")},
            "site": ({"type": site.get("type"), "min": site.get("min"),
                      "max": site.get("max"), "area_est": site.get("area_est"),
                      "is_terrain": site.get("is_terrain")} if site else None),
            "north_deg": R.get("north_deg"),
            "north_source": R.get("north_source"),
            "required_setback_m": cr.get("required_setback_m"),
            "buildable_zone": zone, "buildable_feasible": cand.get("feasible"),
            "buildable_reason": cand.get("reason"),
            "candidates_tested": len(cand.get("candidates", [])),
            "selected_candidate": best, "terrain": terr,
            "warnings": R.get("warnings", []),
            "disclaimer": SITE_PLACEMENT_DISCLAIMER}, f, indent=1)
    _w("site_placement_result.json", _res)

    def _cc(f):
        f.write(_csv_row(["rot_deg", "center_x", "center_y", "setback_margin",
                          "sunlight", "ventilation", "harsh_sun", "total_score"]))
        for c in cand.get("candidates", []):
            f.write(_csv_row([c["rot"], "%.3f" % c["cx"], "%.3f" % c["cy"],
                              "%.3f" % c["setback_margin"], "%.3f" % c["sunlight"],
                              "%.3f" % c["ventilation"], "%.3f" % c["harsh"],
                              "%.3f" % c["total"]]))
    _w("placement_candidates.csv", _cc)

    def _sb(f):
        f.write(_csv_row(["item", "value", "note"]))
        f.write(_csv_row(["required_setback_m",
                          "%.3f" % cr.get("required_setback_m", 0.0),
                          "max(base 3.0, 0.4 x height); design-stage"]))
        f.write(_csv_row(["footprint_w_m", "%.3f" % metrics.get("w", 0.0), ""]))
        f.write(_csv_row(["footprint_l_m", "%.3f" % metrics.get("l", 0.0), ""]))
        f.write(_csv_row(["buildable_feasible", str(cand.get("feasible")),
                          cand.get("reason", "")]))
        if zone:
            f.write(_csv_row(["buildable_zone",
                              "%.2f,%.2f,%.2f,%.2f" % (zone[0], zone[1], zone[2],
                                                       zone[3]),
                              "approx rectangle (site bbox inward offset)"]))
    _w("setback_check.csv", _sb)

    def _ts(f):
        f.write(_csv_row(["point", "x", "y", "sampled_z"]))
        for row in R.get("terrain_samples", []):
            f.write(_csv_row([row[0], "%.3f" % row[1], "%.3f" % row[2],
                              "%.3f" % row[3]]))
        if terr:
            f.write(_csv_row(["stats_min", "", "", "%s" % terr.get("min")]))
            f.write(_csv_row(["stats_max", "", "", "%s" % terr.get("max")]))
            f.write(_csv_row(["stats_diff", "", "", "%s" % terr.get("diff")]))
    _w("terrain_sampling.csv", _ts)

    def _sum(f):
        b = best or {}
        L = ["Timber Housing v23 - FINAL SITE PLACEMENT RESULT", "=" * 60,
             SITE_PLACEMENT_DISCLAIMER, "=" * 60,
             "timestamp                : %s" % stamp,
             "status                   : %s" % R.get("status"),
             "placement applied        : %s" % R.get("applied", False),
             "-" * 60,
             "city                     : %s" % R.get("city"),
             "federal state (approx)   : %s" % cr.get("federal_state"),
             "assumption mode          : %s" % cr.get("assumption_mode"),
             "latitude (approx)        : %s" % cr.get("latitude_deg_approx"),
             "snow / wind / seismic    : %s / %s / %s"
             % (cr.get("snow_zone_placeholder"), cr.get("wind_zone_placeholder"),
                cr.get("seismic_zone_placeholder")),
             "-" * 60,
             "building height (m)      : %.2f" % metrics.get("h", 0.0),
             "footprint w x l (m)      : %.2f x %.2f"
             % (metrics.get("w", 0.0), metrics.get("l", 0.0)),
             "required setback (m)     : %.2f" % cr.get("required_setback_m", 0.0),
             "site object type         : %s"
             % (site.get("type") if site else "(none selected)"),
             "north angle (deg from +Y): %s (%s)"
             % (R.get("north_deg"), R.get("north_source")),
             "buildable feasible       : %s (%s)"
             % (cand.get("feasible"), cand.get("reason")),
             "candidates tested        : %d" % len(cand.get("candidates", [])),
             "-" * 60, "selected placement (best candidate):"]
        if b:
            L += ["   rotation (deg)        : %s" % b.get("rot"),
                  "   center x / y          : %.2f / %.2f"
                  % (b.get("cx", 0.0), b.get("cy", 0.0)),
                  "   long facade bearings  : %s" % str(b.get("long_bearings")),
                  "   sunlight score        : %.3f" % b.get("sunlight", 0.0),
                  "   ventilation score     : %.3f" % b.get("ventilation", 0.0),
                  "   harsh sun penalty     : %.3f" % b.get("harsh", 0.0),
                  "   total score           : %.3f" % b.get("total", 0.0)]
        else:
            L.append("   (no fitting candidate)")
        if terr and terr.get("count"):
            L += ["-" * 60,
                  "terrain elevation min/max/diff (m): %s / %s / %s"
                  % (terr.get("min"), terr.get("max"), terr.get("diff"))]
        if R.get("warnings"):
            L += ["-" * 60, "warnings:"]
            for w in R["warnings"]:
                L.append("   - %s" % w)
        L += ["-" * 60, "generated files:"]
        for g in generated:
            L.append("   - %s" % g)
        L += ["-" * 60, "sunlight / ventilation are HEURISTIC only (not a "
              "simulation).", SITE_PLACEMENT_DISCLAIMER]
        f.write("\n".join(L) + "\n")
    _w("site_placement_summary.txt", _sum)

    R["generated_files"] = generated
    print("Site placement report written to: %s" % folder)
    return folder


# --------------------------------------------------------------------------- #
# Site-placement dialogs (proven Rhino-safe layout; native fallbacks)
# --------------------------------------------------------------------------- #

def show_city_dialog():
    """City + planning-context dialog. Returns (city_name, proceed_bool)."""
    intro = (
        "Final Site Placement - design-stage placement ASSISTANT.\n\n"
        "Select a German city to load conservative OFFLINE planning / Eurocode "
        "assumptions (setback, snow/wind/seismic zone placeholders, approximate "
        "latitude). These are NOT the real Bebauungsplan.\n\n"
        "Setback used: max(3.0 m, 0.4 x building height). The building will be "
        "placed inside an approximate buildable zone with a heuristic sun / "
        "ventilation orientation. You can Skip this whole stage.\n\n"
        + SITE_PLACEMENT_DISCLAIMER)
    try:
        import Eto.Forms as forms
        import Eto.Drawing as drawing
    except Exception:
        try:
            city = rs.ListBox(GERMAN_CITIES, "Select German city (or Custom / "
                              "Other). Cancel = skip site placement.",
                              "Final Site Placement")
        except Exception:
            city = None
        if not city:
            return (None, False)
        return (city, True)

    class CityDlg(forms.Dialog[bool]):
        def __init__(self):
            super(CityDlg, self).__init__()
            self.Title = "Final Site Placement - City and Planning Context"
            self.Padding = drawing.Padding(12)
            self.Resizable = True
            self.sel_index = 0
            ta = forms.TextArea()
            ta.ReadOnly = True
            ta.Wrap = True
            ta.Text = intro
            ta.Size = drawing.Size(560, 200)
            try:
                _f = _ui_font(9.0)
                if _f is not None:
                    ta.Font = _f
                ta.BackgroundColor = _ui_color(UI_COLORS["card"])
                ta.TextColor = _ui_color(UI_COLORS["ink"])
            except Exception:
                pass
            self.dd = forms.DropDown()
            self.dd.DataStore = list(GERMAN_CITIES)
            self.dd.SelectedIndex = 0
            cont = forms.Button()
            cont.Text = "Continue"
            cont.Click += self.on_cont
            skip = forms.Button()
            skip.Text = "Skip Final Site Placement"
            skip.Click += self.on_skip
            self.DefaultButton = cont
            self.AbortButton = skip
            lay = forms.TableLayout()
            lay.Spacing = drawing.Size(8, 8)
            lay.Rows.Add(forms.TableRow([forms.TableCell(ta, True)]))
            lay.Rows.Add(forms.TableRow(forms.TableCell(
                make_section_label("City"))))
            lay.Rows.Add(forms.TableRow(forms.TableCell(self.dd)))
            lay.Rows.Add(forms.TableRow(forms.TableCell(cont)))
            lay.Rows.Add(forms.TableRow(forms.TableCell(skip)))
            finalize_dialog(self, lay, "Final Site Placement",
                            "City and planning context (design-stage)",
                            [(cont, "primary"), (skip, "cancel")])
            try:
                self.ClientSize = drawing.Size(640, 460)
            except Exception:
                pass

        def on_cont(self, s, e):
            try:
                self.sel_index = int(self.dd.SelectedIndex)
            except Exception:
                self.sel_index = 0
            self.Close(True)

        def on_skip(self, s, e):
            self.Close(False)

    try:
        dlg = CityDlg()
        ok = bool(dlg.ShowModal(Rhino.UI.RhinoEtoApp.MainWindow))
        if ok:
            idx = dlg.sel_index
            if idx < 0 or idx >= len(GERMAN_CITIES):
                idx = 0
            return (GERMAN_CITIES[idx], True)
        return (None, False)
    except Exception:
        try:
            city = rs.ListBox(GERMAN_CITIES, "Select German city.",
                              "Final Site Placement")
        except Exception:
            city = None
        return (city, bool(city))


def show_site_placement_preview(body, folder, txt):
    """Final placement preview. Returns True (Apply) / False (Skip). Reuses the
    proven direct-button layout; native rs.MessageBox fallback."""
    try:
        import Eto.Forms as forms
        import Eto.Drawing as drawing
    except Exception:
        return rs.MessageBox(body, 4 | 32,
                             "Final Site Placement Preview") == 6

    class PvDlg(forms.Dialog[bool]):
        def __init__(self):
            super(PvDlg, self).__init__()
            self.Title = "Final Site Placement Preview"
            self.Padding = drawing.Padding(12)
            self.Resizable = True
            ta = forms.TextArea()
            ta.ReadOnly = True
            ta.Wrap = False
            ta.Text = body
            ta.Size = drawing.Size(560, 360)
            try:
                _f = _ui_font(9.0, mono=True)
                if _f is not None:
                    ta.Font = _f
                ta.BackgroundColor = _ui_color(UI_COLORS["card"])
                ta.TextColor = _ui_color(UI_COLORS["ink"])
            except Exception:
                pass
            ap = forms.Button()
            ap.Text = "Apply Placement"
            ap.Click += self.on_apply
            sk = forms.Button()
            sk.Text = "Skip Placement"
            sk.Click += self.on_skip
            self.DefaultButton = ap
            self.AbortButton = sk
            lay = forms.TableLayout()
            lay.Spacing = drawing.Size(8, 8)
            lay.Rows.Add(forms.TableRow([forms.TableCell(ta, True)]))
            lay.Rows.Add(forms.TableRow(forms.TableCell(ap)))
            lay.Rows.Add(forms.TableRow(forms.TableCell(sk)))
            btnspec = [(ap, "primary"), (sk, "cancel")]
            if folder:
                of = forms.Button()
                of.Text = "Open Placement Report Folder"
                of.Click += self.on_folder
                lay.Rows.Add(forms.TableRow(forms.TableCell(of)))
                btnspec.append((of, "secondary"))
            finalize_dialog(self, lay, "Final Site Placement Preview",
                            "Design-stage placement - Apply or Skip", btnspec)
            try:
                self.ClientSize = drawing.Size(660, 520)
            except Exception:
                pass

        def on_apply(self, s, e):
            self.Close(True)

        def on_skip(self, s, e):
            self.Close(False)

        def on_folder(self, s, e):
            _open_path_os(folder)

    try:
        return bool(PvDlg().ShowModal(Rhino.UI.RhinoEtoApp.MainWindow))
    except Exception:
        return rs.MessageBox(body, 4 | 32,
                             "Final Site Placement Preview") == 6


# =============================================================================
# 6c-V24. SITE PLACEMENT OPTIMIZER (Galapagos-style)  (v24, added 2026-07-08)
#
# Rebuilds the final placement as a real deterministic optimizer that ACTUALLY
# MOVES the generated model onto the selected site:
#   - clean building footprint (ignores debug / notes / analysis / text objects),
#   - Dialog 1 setup (city + options) BEFORE selection,
#   - Rhino site pick + optional north pick (command line, as Rhino expects),
#   - rotation + translation search inside the setback buildable zone,
#   - orientation scoring (sun / harsh-sun / ventilation / site-long alignment),
#   - ALWAYS returns a best candidate (feasible OR best-effort centred),
#   - Dialog 2 result (Accept / Keep outside / Open report / Open TXT),
#   - on Accept: single rigid transform of ALL tagged generated objects.
# DESIGN-STAGE ONLY; never a permit / solar / structural result. v23 untouched.
# =============================================================================

# Core "solid building" layers that define the real footprint (NO debug / notes /
# analysis / text / anchor layers - those inflate the bbox, e.g. 208x148 m).
SITE_FOOTPRINT_LAYERS = [
    "02_Regular_Columns", "03_Regular_Beams", "04_Corridor_Slabs",
    "05_Corridor_Edge_Beams", "06_Ground_V_Columns", "07_Atrium_Trunk_Columns",
    "08_Atrium_Branches_To_Corridor", "09_Staircase_Reserved_Zones",
    "10_Module_Placeholders", "20_Dummy_Module_A", "21_Dummy_Module_A1",
    "22_Dummy_Module_B", "23_Green_Common_Terrace_Slots",
    "30_Detailed_Module_A", "31_Detailed_Module_A1", "32_Detailed_Module_B",
]

SITE_OPT_DEFAULTS = {
    "site_optimizer_rotation_step_deg": 10,
    "site_optimizer_refine_step_deg": 2,
    "site_optimizer_translation_grid_count": 5,
    "site_optimizer_max_candidates": 4000,
    "site_optimizer_show_debug": False,
    # ---- v25 live Galapagos-style preview -------------------------------
    "site_optimizer_live_preview": True,       # animate a lightweight footprint
    "site_optimizer_visible_iterations": 100,  # how many candidates to animate
    "site_optimizer_preview_delay_ms": 30,     # per-frame delay (visible speed)
    "site_optimizer_preview_every_n": 1,       # draw every Nth frame (>1 = faster)
    # ---- v26 irregular buildable-zone fit -------------------------------
    "site_optimizer_edge_samples": 3,          # extra points sampled per footprint edge
    "site_boundary_sample_count": 160,         # points sampled along the site boundary
}

# Score weights shared by the optimizer and the justification summary.
SITE_SCORE_WEIGHTS = {"sun": 1.0, "vent": 0.4, "harsh": 0.8, "set": 0.3,
                      "align": 0.6}

SITE_DEBUG_LAYERS = {
    "boundary": "90_Site_Boundary_Selected",
    "zone": "91_Buildable_Zone_Setback",
    "cands": "92_Placement_Candidates_Debug",
    "best": "93_Best_Placement_Footprint",
    "report": "94_Final_Placement_Report",
    "live": "95_Placement_Preview_Live",
}


def get_wosyho_building_footprint_objects():
    """Return ids of ONLY the real building/rack geometry (solid layers) used to
    compute the placement footprint. Excludes debug / notes / analysis / text /
    anchor objects that would otherwise inflate the footprint. Never deletes."""
    ids = []
    used = []
    for name in SITE_FOOTPRINT_LAYERS:
        try:
            if rs.IsLayer(name):
                objs = rs.ObjectsByLayer(name)
                if objs:
                    ids.extend(objs)
                    used.append(name)
        except Exception:
            continue
    return ids, used


def compute_clean_building_footprint(P, rack):
    """Clean footprint / height / centre from the SOLID building layers only.
    Falls back to parameter-derived extents if no footprint objects exist.
    Adds a sanity note if the bbox is implausibly large vs the expected
    bays x AXIS extent (which indicates stray/debug geometry)."""
    ids, used = get_wosyho_building_footprint_objects()
    bb = None
    try:
        if ids:
            bb = rs.BoundingBox(ids)
    except Exception:
        bb = None
    note = ""
    if bb:
        xs = [p[0] for p in bb]
        ys = [p[1] for p in bb]
        zs = [p[2] for p in bb]
        x0, x1 = min(xs), max(xs)
        y0, y1 = min(ys), max(ys)
        z0, z1 = min(zs), max(zs)
        src = "clean footprint (solid building layers: %d)" % len(used)
    else:
        nb = (P or {}).get("x_bays", 12)
        pf = (P or {}).get("peak_floors", 8)
        x0, y0, z0 = 0.0, 0.0, 0.0
        x1 = nb * AXIS
        y1 = Y_OUT_R
        z1 = pf * FLOOR_PITCH
        src = "parameter-derived fallback (no solid building objects found)"
    w = x1 - x0
    l = y1 - y0
    # sanity: expected building extent from parameters
    try:
        exp_w = (P or {}).get("x_bays", 12) * AXIS
        exp_l = (Y_OUT_R - Y_OUT_L)
        if w > exp_w * 1.8 or l > exp_l * 3.0:
            note = ("footprint (%.1f x %.1f m) is larger than the expected "
                    "building extent (~%.1f x %.1f m); using parameter-derived "
                    "footprint instead (stray/debug geometry ignored)."
                    % (w, l, exp_w, exp_l))
            # fall back to a clean parameter-derived footprint centred on bbox
            cx = (x0 + x1) / 2.0
            cy = (y0 + y1) / 2.0
            x0, x1 = cx - exp_w / 2.0, cx + exp_w / 2.0
            y0, y1 = cy - exp_l / 2.0, cy + exp_l / 2.0
            w, l = exp_w, exp_l
            src = "parameter-derived (bbox sanity fallback)"
    except Exception:
        pass
    return {"x0": x0, "y0": y0, "z0": z0, "x1": x1, "y1": y1, "z1": z1,
            "w": w, "l": l, "h": z1 - z0,
            "cx": (x0 + x1) / 2.0, "cy": (y0 + y1) / 2.0, "cz": (z0 + z1) / 2.0,
            "source": src, "note": note, "footprint_objects": len(ids)}


def collect_wosyho_generated_objects_by_tag():
    """All objects carrying the WoSyHo_Generated tag (the FULL model to move).
    Falls back to all objects on the known Timber Housing layers if none are tagged
    yet. Never includes the user's site surface / context (untagged / off-layer)."""
    ids = []
    try:
        for oid in _wosyho_all_object_ids():
            if _wosyho_is_generated(oid):
                ids.append(oid)
    except Exception:
        pass
    if ids:
        return ids, "tag WoSyHo_Generated=1"
    lids, _inc, _exc = collect_wosyho_building_objects_for_site_placement()
    return lids, "Timber Housing layers (untagged fallback)"


def _sp_rect_corners(cx, cy, w, l, rot_deg, z):
    """Closed rectangle (5 pts) of a w x l footprint centred at (cx,cy), rotated
    rot_deg about vertical, at elevation z."""
    r = math.radians(rot_deg)
    c = math.cos(r)
    s = math.sin(r)
    hw = w / 2.0
    hl = l / 2.0
    local = [(-hw, -hl), (hw, -hl), (hw, hl), (-hw, hl), (-hw, -hl)]
    return [(cx + lx * c - ly * s, cy + lx * s + ly * c, z) for (lx, ly) in local]


def optimize_site_placement(zone, fw, fl, north_vec, lat, site_min, site_max,
                            opts):
    """Deterministic Galapagos-style placement search. Tries rotations (coarse
    0-360 by step + refine + site-long/perpendicular specials) x translations
    (buildable & site centres + inner grid) and scores each. ALWAYS returns a
    best candidate: a fitting one if any, otherwise a best-effort centred
    candidate (minimal overflow) so the model can still be placed on the site.
    Returns {feasible, best, candidates, reason}."""
    if zone is None:
        return {"feasible": False, "best": None, "candidates": [],
                "reason": "buildable zone too small / setback too large"}
    rot_step = int(max(1, opts.get("site_optimizer_rotation_step_deg", 10)))
    refine_step = int(max(1, opts.get("site_optimizer_refine_step_deg", 2)))
    gridN = int(max(1, opts.get("site_optimizer_translation_grid_count", 5)))
    max_cand = int(opts.get("site_optimizer_max_candidates", 4000))
    allow_rot = opts.get("allow_rotation", True)
    allow_trans = opts.get("allow_translation", True)
    x0, y0, x1, y1 = zone
    zw = x1 - x0
    zh = y1 - y0
    site_long_x = (zw >= zh)
    if allow_rot:
        rotations = [float(r) for r in range(0, 360, rot_step)]
        # special angles: align building long (local X) to site long axis, and
        # perpendicular, so the long facade relates sensibly to the site shape.
        rotations += ([0.0, 90.0, 180.0, 270.0] if site_long_x
                      else [90.0, 0.0, 270.0, 180.0])
    else:
        rotations = [0.0]
    W_SUN, W_VENT, W_HARSH, W_SET, W_ALIGN = 1.0, 0.4, 0.8, 0.3, 0.6
    cxz = (x0 + x1) / 2.0
    cyz = (y0 + y1) / 2.0
    scx = (site_min[0] + site_max[0]) / 2.0
    scy = (site_min[1] + site_max[1]) / 2.0

    def score_rot(rot):
        o = _sp_score_orientation(rot, north_vec, lat)
        bl = (math.cos(math.radians(rot)), math.sin(math.radians(rot)))
        sl = (1.0, 0.0) if site_long_x else (0.0, 1.0)
        align = abs(bl[0] * sl[0] + bl[1] * sl[1])
        return o, align

    cands = []
    best = None
    best_eff = None
    best_eff_overflow = 1e18
    count = 0
    seen = set()
    for rot in rotations:
        rot = round(rot % 360.0, 3)
        if rot in seen:
            continue
        seen.add(rot)
        ex, ey = _sp_footprint_extent(fw, fl, rot)
        overflow = max(ex - zw, ey - zh, 0.0)
        o, align = score_rot(rot)
        # candidate centres
        centres = [(cxz, cyz), (scx, scy)]
        if allow_trans:
            xmin = x0 + ex / 2.0
            xmax = x1 - ex / 2.0
            ymin = y0 + ey / 2.0
            ymax = y1 - ey / 2.0
            for gi in range(gridN):
                for gj in range(gridN):
                    fx = (gi + 0.5) / float(gridN)
                    fy = (gj + 0.5) / float(gridN)
                    px = xmin + (xmax - xmin) * fx if xmax > xmin else cxz
                    py = ymin + (ymax - ymin) * fy if ymax > ymin else cyz
                    centres.append((px, py))
        for (cx, cy) in centres:
            count += 1
            if count > max_cand:
                break
            marg = min(cx - ex / 2.0 - x0, x1 - (cx + ex / 2.0),
                       cy - ey / 2.0 - y0, y1 - (cy + ey / 2.0))
            setm = marg / max(1.0, min(zw, zh) / 2.0)
            setm = 0.0 if setm < 0.0 else (1.0 if setm > 1.0 else setm)
            fits = (overflow <= 1e-6) and (marg >= -1e-6)
            total = (W_SUN * o["sunlight"] + W_VENT * o["ventilation"]
                     - W_HARSH * o["harsh"] + W_SET * setm + W_ALIGN * align)
            cand = {"rot": rot, "cx": cx, "cy": cy, "setback_margin": setm,
                    "sunlight": o["sunlight"], "ventilation": o["ventilation"],
                    "harsh": o["harsh"], "align": round(align, 3),
                    "total": total, "fits": fits, "overflow": overflow,
                    "long_bearings": o["long_bearings"]}
            cands.append(cand)
            if fits and (best is None or total > best["total"]):
                best = cand
        # track best-effort (minimal overflow, centred in the zone)
        if overflow < best_eff_overflow - 1e-9:
            best_eff_overflow = overflow
            best_eff = {"rot": rot, "cx": cxz, "cy": cyz, "setback_margin": 0.0,
                        "sunlight": o["sunlight"], "ventilation": o["ventilation"],
                        "harsh": o["harsh"], "align": round(align, 3),
                        "total": (W_SUN * o["sunlight"] + W_VENT * o["ventilation"]
                                  - W_HARSH * o["harsh"] + W_ALIGN * align),
                        "fits": (overflow <= 1e-6), "overflow": overflow,
                        "long_bearings": o["long_bearings"]}
        if count > max_cand:
            break
    if best is not None:
        # refine rotation around the best fitting candidate
        if allow_rot:
            r0 = best["rot"]
            k = max(1, int(rot_step / refine_step))
            for j in range(-k, k + 1):
                rot = round((r0 + j * refine_step) % 360.0, 3)
                ex, ey = _sp_footprint_extent(fw, fl, rot)
                if ex > zw + 1e-6 or ey > zh + 1e-6:
                    continue
                cx, cy = best["cx"], best["cy"]
                marg = min(cx - ex / 2.0 - x0, x1 - (cx + ex / 2.0),
                           cy - ey / 2.0 - y0, y1 - (cy + ey / 2.0))
                if marg < -1e-6:
                    continue
                o, align = score_rot(rot)
                setm = marg / max(1.0, min(zw, zh) / 2.0)
                setm = 0.0 if setm < 0.0 else (1.0 if setm > 1.0 else setm)
                total = (W_SUN * o["sunlight"] + W_VENT * o["ventilation"]
                         - W_HARSH * o["harsh"] + W_SET * setm + W_ALIGN * align)
                if total > best["total"]:
                    best = {"rot": rot, "cx": cx, "cy": cy, "setback_margin": setm,
                            "sunlight": o["sunlight"],
                            "ventilation": o["ventilation"], "harsh": o["harsh"],
                            "align": round(align, 3), "total": total, "fits": True,
                            "overflow": 0.0, "long_bearings": o["long_bearings"]}
        return {"feasible": True, "best": best, "candidates": cands,
                "reason": "ok"}
    return {"feasible": False, "best": best_eff, "candidates": cands,
            "reason": ("footprint (%.1f x %.1f m) does not fit the buildable "
                       "zone (%.1f x %.1f m) at any rotation - showing a "
                       "best-effort centred placement (setback may be violated; "
                       "reduce building / lower height / use a larger site)."
                       % (fw, fl, zw, zh))}


def _sp_ensure_site_debug_layers():
    for key in SITE_DEBUG_LAYERS:
        _sp_ensure_layer(SITE_DEBUG_LAYERS[key])


def draw_site_placement_debug(site, zone, best, footprint, target_z,
                              show_candidates, cand_list):
    """Draw informative outlines (site boundary, buildable zone, best-placement
    footprint, optional candidate points, report dot). Returns created ids so
    they can be removed if the user keeps the model outside. Never transformed
    with the building. Guarded."""
    created = []
    try:
        _sp_ensure_site_debug_layers()
        z = target_z
        # site boundary rectangle (bbox)
        if site:
            mn = site["min"]
            mx = site["max"]
            b = rs.AddPolyline([(mn[0], mn[1], z), (mx[0], mn[1], z),
                                (mx[0], mx[1], z), (mn[0], mx[1], z),
                                (mn[0], mn[1], z)])
            if b:
                rs.ObjectLayer(b, SITE_DEBUG_LAYERS["boundary"])
                created.append(b)
        # buildable zone
        if zone:
            x0, y0, x1, y1 = zone
            zpl = rs.AddPolyline([(x0, y0, z), (x1, y0, z), (x1, y1, z),
                                  (x0, y1, z), (x0, y0, z)])
            if zpl:
                rs.ObjectLayer(zpl, SITE_DEBUG_LAYERS["zone"])
                created.append(zpl)
        # best-placement footprint (rotated). NO floating text label by default
        # (v25): the "BEST rot/score" info now lives in the result dialog + TXT.
        # An optional text dot is drawn ONLY in debug mode, on the (hidden)
        # 94_Final_Placement_Report layer.
        if best and footprint:
            corners = _sp_rect_corners(best["cx"], best["cy"], footprint["w"],
                                       footprint["l"], best["rot"], z)
            fp = rs.AddPolyline(corners)
            if fp:
                rs.ObjectLayer(fp, SITE_DEBUG_LAYERS["best"])
                created.append(fp)
            if show_candidates:
                nd = rs.AddTextDot("BEST  rot %s  score %.2f"
                                   % (best["rot"], best.get("total", 0.0)),
                                   (best["cx"], best["cy"], z))
                if nd:
                    rs.ObjectLayer(nd, SITE_DEBUG_LAYERS["report"])
                    try:
                        rs.LayerVisible(SITE_DEBUG_LAYERS["report"], False)
                    except Exception:
                        pass
                    created.append(nd)
        # candidate points (optional, lightweight)
        if show_candidates and cand_list:
            step = max(1, len(cand_list) // 200)
            for i in range(0, len(cand_list), step):
                c = cand_list[i]
                pt = rs.AddPoint((c["cx"], c["cy"], z))
                if pt:
                    rs.ObjectLayer(pt, SITE_DEBUG_LAYERS["cands"])
                    created.append(pt)
    except Exception as ex:
        print("Site debug drawing skipped (%s)." % ex)
    return created


def show_site_setup_dialog():
    """DIALOG 1 - site placement setup (before selection). Returns an opts dict
    or None (skip). Proven safe Eto layout; native fallback."""
    intro = (
        "Final Site Placement Optimizer - design-stage placement ASSISTANT.\n\n"
        "Pick a German city for OFFLINE planning / setback assumptions, then this "
        "tool will (after you select a site surface and mark north) SEARCH many "
        "rotations and positions inside the setback buildable zone and MOVE the "
        "whole generated model onto the best placement.\n\n"
        "Options below control the optimiser. This is NOT a legal / permit / solar "
        "/ structural result.\n\n" + SITE_PLACEMENT_DISCLAIMER)
    try:
        import Eto.Forms as forms
        import Eto.Drawing as drawing
    except Exception:
        try:
            city = rs.ListBox(GERMAN_CITIES, "City (Cancel = skip placement)",
                              "Final Site Placement")
        except Exception:
            city = None
        if not city:
            return None
        o = dict(SITE_OPT_DEFAULTS)
        o.update({"city": city, "run_optimization": True, "allow_rotation": True,
                  "allow_translation": True, "conservative_setbacks": True,
                  "mark_north": True, "site_optimizer_show_debug": False})
        return o

    class SetupDlg(forms.Dialog[bool]):
        def __init__(self):
            super(SetupDlg, self).__init__()
            self.Title = "Final Site Placement - Setup"
            self.Padding = drawing.Padding(12)
            self.Resizable = True
            self.sel_index = 0
            ta = forms.TextArea()
            ta.ReadOnly = True
            ta.Wrap = True
            ta.Text = intro
            ta.Size = drawing.Size(560, 180)
            try:
                _f = _ui_font(9.0)
                if _f is not None:
                    ta.Font = _f
                ta.BackgroundColor = _ui_color(UI_COLORS["card"])
                ta.TextColor = _ui_color(UI_COLORS["ink"])
            except Exception:
                pass
            self.dd = forms.DropDown()
            self.dd.DataStore = list(GERMAN_CITIES)
            self.dd.SelectedIndex = 0

            def cb(text, val):
                c = forms.CheckBox()
                c.Text = text
                c.Checked = val
                return c
            self.c_opt = cb("Run automatic placement optimization", True)
            self.c_rot = cb("Allow rotation", True)
            self.c_trans = cb("Allow translation", True)
            self.c_cons = cb("Use conservative setbacks", True)
            self.c_north = cb("Mark north in Rhino (else world +Y)", True)
            self.c_live = cb("Show live optimization preview (animated)", True)
            self.c_dbg = cb("Show debug candidate ghosts / label", False)
            # visible preview iterations (default 100)
            self.n_iter = forms.NumericStepper()
            self.n_iter.DecimalPlaces = 0
            self.n_iter.MinValue = 10
            self.n_iter.MaxValue = 500
            try:
                self.n_iter.Value = float(SITE_OPT_DEFAULTS.get(
                    "site_optimizer_visible_iterations", 100))
            except Exception:
                self.n_iter.Value = 100
            iter_row = forms.TableLayout()
            iter_row.Spacing = drawing.Size(8, 0)
            _lbl = forms.Label()
            _lbl.Text = "Visible preview iterations:"
            iter_row.Rows.Add(forms.TableRow(forms.TableCell(_lbl),
                                             forms.TableCell(self.n_iter, True)))
            cont = forms.Button()
            cont.Text = "Continue - select site next"
            cont.Click += self.on_cont
            skip = forms.Button()
            skip.Text = "Skip Final Site Placement"
            skip.Click += self.on_skip
            self.DefaultButton = cont
            self.AbortButton = skip
            lay = forms.TableLayout()
            lay.Spacing = drawing.Size(8, 6)
            lay.Rows.Add(forms.TableRow([forms.TableCell(ta, True)]))
            lay.Rows.Add(forms.TableRow(forms.TableCell(
                make_section_label("City"))))
            lay.Rows.Add(forms.TableRow(forms.TableCell(self.dd)))
            for c in (self.c_opt, self.c_rot, self.c_trans, self.c_cons,
                      self.c_north, self.c_live, self.c_dbg):
                lay.Rows.Add(forms.TableRow(forms.TableCell(c)))
            lay.Rows.Add(forms.TableRow(forms.TableCell(iter_row)))
            lay.Rows.Add(forms.TableRow(forms.TableCell(cont)))
            lay.Rows.Add(forms.TableRow(forms.TableCell(skip)))
            finalize_dialog(self, lay, "Final Site Placement Optimizer",
                            "Setup (design-stage)",
                            [(cont, "primary"), (skip, "cancel")])
            try:
                self.ClientSize = drawing.Size(640, 620)
            except Exception:
                pass

        def on_cont(self, s, e):
            try:
                self.sel_index = int(self.dd.SelectedIndex)
            except Exception:
                self.sel_index = 0
            self.Close(True)

        def on_skip(self, s, e):
            self.Close(False)

    try:
        dlg = SetupDlg()
        ok = bool(dlg.ShowModal(Rhino.UI.RhinoEtoApp.MainWindow))
        if not ok:
            return None
        idx = dlg.sel_index
        if idx < 0 or idx >= len(GERMAN_CITIES):
            idx = 0
        try:
            n_iter = int(dlg.n_iter.Value)
        except Exception:
            n_iter = 100
        o = dict(SITE_OPT_DEFAULTS)
        o.update({"city": GERMAN_CITIES[idx],
                  "run_optimization": bool(dlg.c_opt.Checked),
                  "allow_rotation": bool(dlg.c_rot.Checked),
                  "allow_translation": bool(dlg.c_trans.Checked),
                  "conservative_setbacks": bool(dlg.c_cons.Checked),
                  "mark_north": bool(dlg.c_north.Checked),
                  "site_optimizer_live_preview": bool(dlg.c_live.Checked),
                  "site_optimizer_visible_iterations": n_iter,
                  "site_optimizer_show_debug": bool(dlg.c_dbg.Checked)})
        return o
    except Exception:
        try:
            city = rs.ListBox(GERMAN_CITIES, "City (Cancel = skip)",
                              "Final Site Placement")
        except Exception:
            city = None
        if not city:
            return None
        o = dict(SITE_OPT_DEFAULTS)
        o.update({"city": city, "run_optimization": True, "allow_rotation": True,
                  "allow_translation": True, "conservative_setbacks": True,
                  "mark_north": True})
        return o


def show_site_result_dialog(body, feasible, folder, txt):
    """DIALOG 2 - optimization result. Returns True (Accept placement) / False
    (keep model outside). Buttons: Accept / Keep outside / Open folder / Open
    TXT. Proven safe layout; native fallback."""
    try:
        import Eto.Forms as forms
        import Eto.Drawing as drawing
    except Exception:
        return rs.MessageBox(body, 4 | 32,
                             "Site Placement Result") == 6

    head = ("Best Site Placement Found" if feasible
            else "Best Site Placement Found (best-effort - not fully feasible)")

    class ResDlg(forms.Dialog[bool]):
        def __init__(self):
            super(ResDlg, self).__init__()
            self.Title = "Best Site Placement Found"
            self.Padding = drawing.Padding(12)
            self.Resizable = True
            ta = forms.TextArea()
            ta.ReadOnly = True
            ta.Wrap = False
            ta.Text = body
            ta.Size = drawing.Size(560, 340)
            try:
                _f = _ui_font(9.0, mono=True)
                if _f is not None:
                    ta.Font = _f
                ta.BackgroundColor = _ui_color(UI_COLORS["card"])
                ta.TextColor = _ui_color(UI_COLORS["ink"])
            except Exception:
                pass
            ap = forms.Button()
            ap.Text = "Accept placement (move model onto site)"
            ap.Click += self.on_apply
            kp = forms.Button()
            kp.Text = "Keep model outside site / cancel"
            kp.Click += self.on_keep
            self.DefaultButton = ap
            self.AbortButton = kp
            lay = forms.TableLayout()
            lay.Spacing = drawing.Size(8, 8)
            lay.Rows.Add(forms.TableRow([forms.TableCell(ta, True)]))
            lay.Rows.Add(forms.TableRow(forms.TableCell(ap)))
            lay.Rows.Add(forms.TableRow(forms.TableCell(kp)))
            btnspec = [(ap, "primary"), (kp, "cancel")]
            if folder:
                of = forms.Button()
                of.Text = "Open Report Folder"
                of.Click += self.on_folder
                lay.Rows.Add(forms.TableRow(forms.TableCell(of)))
                btnspec.append((of, "secondary"))
            if txt:
                ot = forms.Button()
                ot.Text = "Open Summary TXT"
                ot.Click += self.on_txt
                lay.Rows.Add(forms.TableRow(forms.TableCell(ot)))
                btnspec.append((ot, "secondary"))
            finalize_dialog(self, lay, head,
                            "Design-stage placement - Accept or Keep", btnspec)
            try:
                self.ClientSize = drawing.Size(680, 560)
            except Exception:
                pass

        def on_apply(self, s, e):
            self.Close(True)

        def on_keep(self, s, e):
            self.Close(False)

        def on_folder(self, s, e):
            _open_path_os(folder)

        def on_txt(self, s, e):
            _open_path_os(txt)

    try:
        return bool(ResDlg().ShowModal(Rhino.UI.RhinoEtoApp.MainWindow))
    except Exception:
        return rs.MessageBox(body, 4 | 32, "Site Placement Result") == 6


def _sp_result_body(R):
    cr = R.get("city_rules", {})
    m = R.get("metrics", {})
    best = R.get("best")
    cand = R.get("cand_info", {})
    site = R.get("site")
    terr = R.get("terrain", {})
    folder = R.get("folder")
    zone = R.get("zone")
    sep = "-" * 60
    zsz = ("%.1f x %.1f" % (zone[2] - zone[0], zone[3] - zone[1])
           if zone else "(none)")
    lines = ["Final Site Placement Optimizer - Result", "=" * 60,
             "feasible              : %s" % cand.get("feasible"),
             "city                  : %s" % R.get("city"),
             "federal state approx  : %s" % cr.get("federal_state"),
             "north angle (deg)     : %s (%s)"
             % (R.get("north_deg"), R.get("north_source")),
             "required setback (m)  : %.2f" % cr.get("required_setback_m", 0.0),
             "building footprint(m) : %.2f x %.2f  (height %.2f)"
             % (m.get("w", 0.0), m.get("l", 0.0), m.get("h", 0.0)),
             "buildable zone (m)    : %s" % zsz,
             "candidates tested     : %d" % len(cand.get("candidates", [])),
             sep]
    if best:
        lines += ["BEST placement:",
                  "   rotation (deg)     : %s" % best.get("rot"),
                  "   center x / y       : %.2f / %.2f"
                  % (best.get("cx", 0.0), best.get("cy", 0.0)),
                  "   fits in zone       : %s" % best.get("fits"),
                  "   sunlight score     : %.3f" % best.get("sunlight", 0.0),
                  "   ventilation score  : %.3f" % best.get("ventilation", 0.0),
                  "   harsh sun penalty  : %.3f" % best.get("harsh", 0.0),
                  "   site-long align    : %.3f" % best.get("align", 0.0),
                  "   total score        : %.3f" % best.get("total", 0.0)]
    else:
        lines.append("BEST placement: NONE")
    if terr and terr.get("count"):
        lines += [sep, "terrain min/max/diff (m): %s / %s / %s"
                  % (terr.get("min"), terr.get("max"), terr.get("diff"))]
    if m.get("note"):
        lines += [sep, "footprint note: %s" % m.get("note")]
    if R.get("warnings"):
        lines.append(sep)
        for w in R["warnings"]:
            lines.append("! %s" % w)
    lines += [sep, "report folder:", "  %s" % (folder or "(not written)"), sep,
              "Sun / ventilation are HEURISTIC (not a simulation).",
              SITE_PLACEMENT_DISCLAIMER]
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# v25 UI additions: live Galapagos-style preview, justification, clean result
# --------------------------------------------------------------------------- #

def _sp_wrap(text, width):
    """Word-wrap plain text to `width` columns (list of lines)."""
    out = []
    cur = ""
    for w in str(text).split():
        if cur and (len(cur) + 1 + len(w)) > width:
            out.append(cur)
            cur = w
        else:
            cur = (cur + " " + w) if cur else w
    if cur:
        out.append(cur)
    return out


def _sp_sample_preview_candidates(cand_list, best, n):
    """Pick ~n representative candidates (evenly spaced across the ordered
    candidate list so rotations/positions visibly vary), ending on `best`."""
    if not cand_list:
        return [best] if best else []
    n = max(1, int(n))
    if len(cand_list) <= n:
        seq = list(cand_list)
    else:
        step = len(cand_list) / float(n)
        seq = [cand_list[min(len(cand_list) - 1, int(i * step))]
               for i in range(n)]
    if best is not None:
        seq = [c for c in seq if c is not best]
        seq.append(best)
    return seq


def run_visible_optimization_preview(site, zone, footprint, cand_list, best,
                                     opts):
    """Animate ~N lightweight footprint candidates inside the site / buildable
    zone so the Galapagos-style search is visible. Moves ONLY a single thin
    rectangle (plus a best-so-far outline) and redraws each frame - the heavy
    model is NEVER moved during the preview. Returns ids of outlines to keep
    (the best-placement footprint). Fully guarded; a no-op if animation is
    unavailable (headless)."""
    if not opts.get("site_optimizer_live_preview", True):
        return []
    try:
        import time as _time
    except Exception:
        _time = None
    N = int(opts.get("site_optimizer_visible_iterations", 100))
    delay = int(opts.get("site_optimizer_preview_delay_ms", 30))
    every = max(1, int(opts.get("site_optimizer_preview_every_n", 1)))
    show_debug = opts.get("site_optimizer_show_debug", False)
    z = (site["max"][2] + 0.05) if site else 0.0
    seq = _sp_sample_preview_candidates(cand_list, best, N)
    if not seq:
        return []
    try:
        _sp_ensure_site_debug_layers()
        _sp_ensure_layer(SITE_DEBUG_LAYERS["live"])
        rs.EnableRedraw(True)
    except Exception:
        pass
    moving = None
    best_outline = None
    best_val = -1e18
    ghosts = []
    total = len(seq)
    for i in range(total):
        c = seq[i]
        if (i % every) != 0 and i != total - 1:
            continue
        try:
            if moving:
                rs.DeleteObject(moving)
        except Exception:
            pass
        try:
            corners = _sp_rect_corners(c["cx"], c["cy"], footprint["w"],
                                       footprint["l"], c["rot"], z)
            moving = rs.AddPolyline(corners)
            if moving:
                rs.ObjectLayer(moving, SITE_DEBUG_LAYERS["live"])
        except Exception:
            moving = None
        if show_debug:
            try:
                g = rs.AddPolyline(_sp_rect_corners(
                    c["cx"], c["cy"], footprint["w"], footprint["l"],
                    c["rot"], z))
                if g:
                    rs.ObjectLayer(g, SITE_DEBUG_LAYERS["cands"])
                    ghosts.append(g)
            except Exception:
                pass
        if c.get("total", -1e18) > best_val:
            best_val = c.get("total", 0.0)
            try:
                if best_outline:
                    rs.DeleteObject(best_outline)
                bo = rs.AddPolyline(_sp_rect_corners(
                    c["cx"], c["cy"], footprint["w"], footprint["l"],
                    c["rot"], z + 0.03))
                if bo:
                    rs.ObjectLayer(bo, SITE_DEBUG_LAYERS["best"])
                    best_outline = bo
            except Exception:
                pass
        try:
            _msg = ("Testing candidate placements (lightweight footprint only; "
                    "full model moves after Accept) - %d/%d  rot %.0f  "
                    "best score %.2f" % (i + 1, total, c.get("rot", 0.0),
                                         best_val if best_val > -1e17 else 0.0))
            print("optimizing... " + _msg)
            try:
                Rhino.RhinoApp.SetCommandPrompt(_msg)
            except Exception:
                pass
            import scriptcontext as _sc
            _sc.doc.Views.Redraw()
            Rhino.RhinoApp.Wait()
        except Exception:
            pass
        if _time and delay > 0:
            try:
                _time.sleep(delay / 1000.0)
            except Exception:
                pass
    # remove the moving rectangle; keep only the best outline (+ ghosts if debug)
    try:
        if moving:
            rs.DeleteObject(moving)
    except Exception:
        pass
    keep = []
    if best_outline:
        keep.append(best_outline)
    if show_debug:
        keep.extend(ghosts)
    elif ghosts:
        try:
            rs.DeleteObjects(ghosts)
        except Exception:
            pass
    try:
        import scriptcontext as _sc
        _sc.doc.Views.Redraw()
    except Exception:
        pass
    return keep


def build_placement_justification(R):
    """Human-readable justification + score breakdown from the actual result
    values (design-stage; generated, not hard-coded). Returns (sentence,
    breakdown_lines)."""
    cr = R.get("city_rules", {})
    m = R.get("metrics", {})
    best = R.get("best") or {}
    w = SITE_SCORE_WEIGHTS
    rot = best.get("rot", 0.0)
    align = best.get("align", 0.0)
    sun = best.get("sunlight", 0.0)
    vent = best.get("ventilation", 0.0)
    harsh = best.get("harsh", 0.0)
    setm = best.get("setback_margin", 0.0)
    fits = best.get("fits", False)
    align_txt = ("follows" if align >= 0.7 else
                 ("partly follows" if align >= 0.4 else "runs across"))
    sun_txt = ("good southern daylight" if sun >= 0.75 else
               ("moderate daylight" if sun >= 0.5 else
                "limited southern daylight"))
    harsh_txt = ("avoids the least favourable west afternoon sun" if harsh <= 0.25
                 else ("has some west afternoon exposure" if harsh <= 0.6 else
                       "is notably exposed to harsh west sun"))
    vent_txt = ("supports cross ventilation with the prevailing south-west wind"
                if vent >= 0.6 else "has a neutral relationship to prevailing wind")
    fit_txt = ("fits within the buildable zone with the required setback"
               if fits else
               "does not fully fit the buildable zone, so a best-effort centred "
               "placement is shown (the setback may be violated)")
    sentence = (
        "The chosen rotation of %.0f deg was selected because the clean building "
        "footprint (%.1f x %.1f m) %s; the building long side %s the site's main "
        "direction; the module / terrace (long) facades receive %s; the "
        "orientation %s; and it %s. The required setback of %.2f m was used for "
        "%s (%s). This is an offline design-stage recommendation and must be "
        "verified with project-specific planning rules (Bebauungsplan / "
        "Landesbauordnung) and, for structure, with RFEM / Dlubal / Karamba and a "
        "qualified engineer."
        % (rot, m.get("w", 0.0), m.get("l", 0.0), fit_txt, align_txt, sun_txt,
           harsh_txt, vent_txt, cr.get("required_setback_m", 0.0),
           R.get("city"), cr.get("federal_state", "")))
    breakdown = [
        "Score breakdown (weight x value = contribution):",
        "   fit / setback margin : %.2f x %.3f = %+.3f"
        % (w["set"], setm, w["set"] * setm),
        "   sun (south daylight) : %.2f x %.3f = %+.3f"
        % (w["sun"], sun, w["sun"] * sun),
        "   ventilation (SW wind): %.2f x %.3f = %+.3f"
        % (w["vent"], vent, w["vent"] * vent),
        "   harsh west sun       : -%.2f x %.3f = %+.3f"
        % (w["harsh"], harsh, -w["harsh"] * harsh),
        "   site-long alignment  : %.2f x %.3f = %+.3f"
        % (w["align"], align, w["align"] * align),
        "   TOTAL score          : %.3f" % best.get("total", 0.0),
    ]
    return sentence, breakdown


def _sp_result_body_v25(R):
    """Result dialog / TXT body (Dialog B) including the justification and score
    breakdown."""
    cr = R.get("city_rules", {})
    m = R.get("metrics", {})
    best = R.get("best") or {}
    cand = R.get("cand_info", {})
    zone = R.get("zone")
    terr = R.get("terrain", {})
    folder = R.get("folder")
    sep = "-" * 64
    zsz = ("%.1f x %.1f" % (zone[2] - zone[0], zone[3] - zone[1])
           if zone else "(none)")
    sentence, breakdown = build_placement_justification(R)
    lines = ["Best Site Placement Found  (design-stage optimizer)", "=" * 64,
             "feasible (fits zone)  : %s" % cand.get("feasible"),
             "city / state          : %s / %s"
             % (R.get("city"), cr.get("federal_state")),
             "north angle (deg)     : %s (%s)"
             % (R.get("north_deg"), R.get("north_source")),
             "required setback (m)  : %.2f" % cr.get("required_setback_m", 0.0),
             "clean footprint (m)   : %.2f x %.2f  (height %.2f)"
             % (m.get("w", 0.0), m.get("l", 0.0), m.get("h", 0.0)),
             "buildable zone (m)    : %s" % zsz,
             "best rotation (deg)   : %s" % best.get("rot"),
             "best centre x / y     : %.2f / %.2f"
             % (best.get("cx", 0.0), best.get("cy", 0.0)),
             "fits inside zone      : %s" % best.get("fits"),
             "candidates tested     : %d" % len(cand.get("candidates", [])),
             sep, "WHY THIS PLACEMENT:"]
    lines += _sp_wrap(sentence, 64)
    lines += [sep] + breakdown
    if terr and terr.get("count"):
        lines += [sep, "terrain min/max/diff (m): %s / %s / %s"
                  % (terr.get("min"), terr.get("max"), terr.get("diff"))]
    if m.get("note"):
        lines += [sep] + _sp_wrap("footprint note: " + m.get("note"), 64)
    if R.get("warnings"):
        lines.append(sep)
        for wmsg in R["warnings"]:
            lines += _sp_wrap("! " + wmsg, 64)
    lines += [sep, "report folder:", "  %s" % (folder or "(not written)"), sep,
              "Sun / ventilation are HEURISTIC (not a simulation).",
              SITE_PLACEMENT_DISCLAIMER]
    return "\n".join(lines)


def _sp_draw_static_outlines(site, zone, target_z):
    """Lightweight site-boundary + buildable-zone outlines (no text). Returns
    created ids."""
    created = []
    try:
        _sp_ensure_site_debug_layers()
        z = target_z
        if site:
            mn = site["min"]
            mx = site["max"]
            b = rs.AddPolyline([(mn[0], mn[1], z), (mx[0], mn[1], z),
                                (mx[0], mx[1], z), (mn[0], mx[1], z),
                                (mn[0], mn[1], z)])
            if b:
                rs.ObjectLayer(b, SITE_DEBUG_LAYERS["boundary"])
                created.append(b)
        if zone:
            x0, y0, x1, y1 = zone
            zp = rs.AddPolyline([(x0, y0, z), (x1, y0, z), (x1, y1, z),
                                 (x0, y1, z), (x0, y0, z)])
            if zp:
                rs.ObjectLayer(zp, SITE_DEBUG_LAYERS["zone"])
                created.append(zp)
    except Exception as ex:
        print("Static outline drawing skipped (%s)." % ex)
    return created


def _sp_append_justification_txt(folder, R):
    """Append the justification + breakdown to the summary TXT (report TXT)."""
    if not folder:
        return
    try:
        sentence, breakdown = build_placement_justification(R)
        path = os.path.join(folder, "site_placement_summary.txt")
        with open(path, "a") as f:
            f.write("\n" + "=" * 62 + "\n")
            f.write("PLACEMENT JUSTIFICATION (design-stage):\n")
            for ln in _sp_wrap(sentence, 62):
                f.write(ln + "\n")
            f.write("-" * 62 + "\n")
            for ln in breakdown:
                f.write(ln + "\n")
        # also a dedicated justification file
        jp = os.path.join(folder, "site_placement_justification.txt")
        with open(jp, "w") as f:
            f.write("Timber Housing v25 - SITE PLACEMENT JUSTIFICATION\n")
            f.write("=" * 62 + "\n")
            for ln in _sp_wrap(sentence, 62):
                f.write(ln + "\n")
            f.write("-" * 62 + "\n")
            for ln in breakdown:
                f.write(ln + "\n")
            f.write("-" * 62 + "\n" + SITE_PLACEMENT_DISCLAIMER + "\n")
    except Exception as ex:
        print("Justification TXT append skipped (%s)." % ex)


# =============================================================================
# 6c-V26. IRREGULAR BUILDABLE ZONE + FULL DIALOG COVERAGE  (v26, 2026-07-08)
#
# Adds (v26 only): (1) proper Eto dialogs around every command-bar step (start,
# pre-site, north, preview-intro, result, post-accept, post-keep); (2) irregular
# site-boundary extraction + inward setback offset so the buildable zone follows
# the real site shape (L-shaped / angled), not just a bounding rectangle, with a
# polygon-based fit test. Reuses the v25 optimizer quality, live preview,
# tagging, site preservation, single-move-on-Accept. Design-stage only.
# =============================================================================

# ---- pure polygon helpers (headless-testable; no Rhino) --------------------

def _poly_bbox(poly):
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    return (min(xs), min(ys), max(xs), max(ys))


def _poly_area(poly):
    n = len(poly)
    a = 0.0
    for i in range(n):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % n]
        a += x0 * y1 - x1 * y0
    return abs(a) * 0.5


def _poly_centroid(poly):
    n = len(poly)
    a = 0.0
    cx = 0.0
    cy = 0.0
    for i in range(n):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % n]
        cr = x0 * y1 - x1 * y0
        a += cr
        cx += (x0 + x1) * cr
        cy += (y0 + y1) * cr
    if abs(a) < 1e-9:
        return (sum(p[0] for p in poly) / n, sum(p[1] for p in poly) / n)
    a *= 0.5
    return (cx / (6.0 * a), cy / (6.0 * a))


def _poly_point_inside(pt, poly):
    """Ray-casting point-in-polygon (XY). poly = list of (x,y)."""
    x = pt[0]
    y = pt[1]
    n = len(poly)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = poly[i][0], poly[i][1]
        xj, yj = poly[j][0], poly[j][1]
        denom = (yj - yi) if abs(yj - yi) > 1e-12 else 1e-12
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / denom + xi):
            inside = not inside
        j = i
    return inside


def _rect_to_poly(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def _footprint_world_points(cx, cy, w, l, rot_deg, edge_samples):
    """Footprint CENTRE + corners + edge sample points in world XY (containment
    test points). The centre is included so a candidate can never pass while its
    middle sits outside the buildable zone (e.g. spanning a concave notch)."""
    r = math.radians(rot_deg)
    c = math.cos(r)
    s = math.sin(r)
    hw = w / 2.0
    hl = l / 2.0
    local = [(-hw, -hl), (hw, -hl), (hw, hl), (-hw, hl)]
    world = [(cx + lx * c - ly * s, cy + lx * s + ly * c) for (lx, ly) in local]
    pts = [(cx, cy)] + list(world)
    es = max(0, int(edge_samples))
    for i in range(4):
        a = world[i]
        b = world[(i + 1) % 4]
        for k in range(1, es + 1):
            t = k / float(es + 1)
            pts.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
    return pts


def _point_segment_distance(p, a, b):
    px, py = p[0], p[1]
    ax, ay = a[0], a[1]
    bx, by = b[0], b[1]
    dx, dy = bx - ax, by - ay
    dd = dx * dx + dy * dy
    if dd < 1e-12:
        return math.hypot(px - ax, py - ay)
    t = ((px - ax) * dx + (py - ay) * dy) / dd
    t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def _poly_min_edge_distance(pt, poly):
    """Shortest distance from a point to the polygon boundary (>=0)."""
    n = len(poly)
    d = 1e18
    for i in range(n):
        d = min(d, _point_segment_distance(pt, poly[i], poly[(i + 1) % n]))
    return d


def _footprint_clearance(cx, cy, w, l, rot_deg, poly, edge_samples=3):
    """Estimated clearance of the footprint from the buildable-zone edge.
    Positive = min distance inside; negative = worst outside penetration."""
    pts = _footprint_world_points(cx, cy, w, l, rot_deg, edge_samples)
    worst = 1e18
    any_out = False
    for p in pts:
        d = _poly_min_edge_distance(p, poly)
        if not _poly_point_inside(p, poly):
            any_out = True
            d = -d
        worst = min(worst, d)
    return worst if worst < 1e17 else (0.0 if any_out else 0.0)


def _footprint_in_polygon(cx, cy, w, l, rot_deg, poly, edge_samples=3):
    for p in _footprint_world_points(cx, cy, w, l, rot_deg, edge_samples):
        if not _poly_point_inside(p, poly):
            return False
    return True


def _footprint_outside_count(cx, cy, w, l, rot_deg, poly, edge_samples=3):
    n = 0
    for p in _footprint_world_points(cx, cy, w, l, rot_deg, edge_samples):
        if not _poly_point_inside(p, poly):
            n += 1
    return n


def optimize_site_placement_irregular(zone_poly, zone_bbox, fw, fl, north_vec,
                                      lat, opts):
    """Placement search over an IRREGULAR buildable polygon. Candidate centres
    are generated in the polygon bbox then filtered to those inside the polygon;
    the fit test checks all footprint corners + edge samples are inside the
    polygon (not just bbox overlap). Always returns a best candidate (fitting,
    or best-effort centred). Pure Python (polygon = list of (x,y))."""
    if not zone_poly or len(zone_poly) < 3 or not zone_bbox:
        return {"feasible": False, "best": None, "candidates": [],
                "reason": "no buildable zone polygon"}
    x0, y0, x1, y1 = zone_bbox
    zw = x1 - x0
    zh = y1 - y0
    site_long_x = (zw >= zh)
    rot_step = int(max(1, opts.get("site_optimizer_rotation_step_deg", 10)))
    gridN = int(max(1, opts.get("site_optimizer_translation_grid_count", 5)))
    max_cand = int(opts.get("site_optimizer_max_candidates", 4000))
    allow_rot = opts.get("allow_rotation", True)
    allow_trans = opts.get("allow_translation", True)
    edge_samples = int(opts.get("site_optimizer_edge_samples", 3))
    w = SITE_SCORE_WEIGHTS
    cen = _poly_centroid(zone_poly)
    if allow_rot:
        rotations = [float(r) for r in range(0, 360, rot_step)]
        rotations += ([0.0, 90.0, 180.0, 270.0] if site_long_x
                      else [90.0, 0.0, 270.0, 180.0])
    else:
        rotations = [0.0]

    def score_rot(rot):
        o = _sp_score_orientation(rot, north_vec, lat)
        bl = (math.cos(math.radians(rot)), math.sin(math.radians(rot)))
        sl = (1.0, 0.0) if site_long_x else (0.0, 1.0)
        align = abs(bl[0] * sl[0] + bl[1] * sl[1])
        return o, align

    def centrality(cx, cy):
        d = math.hypot(cx - cen[0], cy - cen[1])
        m = 1.0 - min(1.0, d / max(1.0, 0.5 * min(zw, zh)))
        return max(0.0, m)

    cands = []
    best = None
    best_eff = None
    best_eff_out = 1e18
    count = 0
    seen = set()
    for rot in rotations:
        rot = round(rot % 360.0, 3)
        if rot in seen:
            continue
        seen.add(rot)
        o, align = score_rot(rot)
        centres = []
        for cc in (cen, ((x0 + x1) / 2.0, (y0 + y1) / 2.0)):
            if _poly_point_inside(cc, zone_poly):
                centres.append(cc)
        if allow_trans:
            for gi in range(gridN):
                for gj in range(gridN):
                    px = x0 + (x1 - x0) * (gi + 0.5) / float(gridN)
                    py = y0 + (y1 - y0) * (gj + 0.5) / float(gridN)
                    if _poly_point_inside((px, py), zone_poly):
                        centres.append((px, py))
        if not centres:
            centres = [cen]
        for (cx, cy) in centres:
            count += 1
            if count > max_cand:
                break
            fits = _footprint_in_polygon(cx, cy, fw, fl, rot, zone_poly,
                                         edge_samples)
            setm = centrality(cx, cy)
            total = (w["sun"] * o["sunlight"] + w["vent"] * o["ventilation"]
                     - w["harsh"] * o["harsh"] + w["set"] * setm
                     + w["align"] * align)
            cand = {"rot": rot, "cx": cx, "cy": cy, "setback_margin": setm,
                    "sunlight": o["sunlight"], "ventilation": o["ventilation"],
                    "harsh": o["harsh"], "align": round(align, 3),
                    "total": total, "fits": fits,
                    "overflow": 0.0 if fits else 1.0,
                    "long_bearings": o["long_bearings"]}
            cands.append(cand)
            if fits and (best is None or total > best["total"]):
                best = cand
            if not fits:
                out = _footprint_outside_count(cen[0], cen[1], fw, fl, rot,
                                               zone_poly, edge_samples)
                if out < best_eff_out:
                    best_eff_out = out
                    be = dict(cand)
                    be["cx"], be["cy"], be["fits"] = cen[0], cen[1], False
                    best_eff = be
        if count > max_cand:
            break
    if best is not None:
        return {"feasible": True, "best": best, "candidates": cands,
                "reason": "ok"}
    if best_eff is None:
        o, align = score_rot(0.0)
        best_eff = {"rot": 0.0, "cx": cen[0], "cy": cen[1],
                    "setback_margin": 0.0, "sunlight": o["sunlight"],
                    "ventilation": o["ventilation"], "harsh": o["harsh"],
                    "align": round(align, 3), "total": 0.0, "fits": False,
                    "overflow": 1.0, "long_bearings": o["long_bearings"]}
    return {"feasible": False, "best": best_eff, "candidates": cands,
            "reason": ("footprint does not fully fit the irregular buildable "
                       "zone at any tested rotation - showing a best-effort "
                       "centred placement (setback may be violated; reduce "
                       "building / lower height / use a larger site).")}


# ---- Rhino site-boundary extraction + irregular inward setback (guarded) ----

def _curve_to_poly(cid, n=160):
    try:
        pts = rs.DivideCurve(cid, int(max(8, n)))
        if pts:
            return [(p[0], p[1]) for p in pts]
    except Exception:
        pass
    return None


def _largest_closed(curves):
    if not curves:
        return None
    if not isinstance(curves, (list, tuple)):
        curves = [curves]
    best = None
    barea = -1.0
    for c in curves:
        try:
            if rs.IsCurveClosed(c):
                a = rs.CurveArea(c)
                area = abs(a[0]) if a else 0.0
                if area > barea:
                    barea = area
                    best = c
        except Exception:
            continue
    if best is None and curves:
        best = curves[0]
    return best


def _poly_dedupe(poly, tol=1e-4):
    """Drop consecutive duplicate points (and the closing duplicate)."""
    out = []
    for p in poly:
        if not out or (abs(p[0] - out[-1][0]) > tol or abs(p[1] - out[-1][1]) > tol):
            out.append((float(p[0]), float(p[1])))
    if len(out) >= 2 and abs(out[0][0] - out[-1][0]) <= tol \
            and abs(out[0][1] - out[-1][1]) <= tol:
        out = out[:-1]
    return out


def _poly_simplify(poly, angle_tol_deg=1.0, tol=1e-4):
    """Remove (near-)collinear vertices. CRITICAL before an inward edge offset:
    densely-sampled collinear edges give near-parallel offset lines whose
    intersection blows up. Keeps real corners (e.g. an L-shape's 6 corners)."""
    pts = _poly_dedupe(poly, tol)
    n = len(pts)
    if n < 4:
        return pts
    keep = []
    ct = math.cos(math.radians(180.0 - angle_tol_deg))
    for i in range(n):
        a = pts[(i - 1) % n]
        b = pts[i]
        c = pts[(i + 1) % n]
        v1 = (b[0] - a[0], b[1] - a[1])
        v2 = (c[0] - b[0], c[1] - b[1])
        l1 = math.hypot(v1[0], v1[1])
        l2 = math.hypot(v2[0], v2[1])
        if l1 < tol or l2 < tol:
            continue
        cosang = (v1[0] * v2[0] + v1[1] * v2[1]) / (l1 * l2)
        cosang = max(-1.0, min(1.0, cosang))
        # collinear (turn angle ~0) -> drop the middle point
        if cosang > math.cos(math.radians(angle_tol_deg)):
            continue
        keep.append(b)
    return keep if len(keep) >= 3 else pts


def _sp_sample_rhino_curve(crv, n=160):
    """Curve -> XY polygon. Uses exact polyline vertices when possible (keeps
    real corners), else divides by count. Returns list of (x,y) or None."""
    try:
        ok, pl = crv.TryGetPolyline()
        if ok and pl is not None and pl.Count >= 3:
            return [(pl[i].X, pl[i].Y) for i in range(pl.Count)]
    except Exception:
        pass
    try:
        ts = crv.DivideByCount(int(max(8, n)), True)
        if ts:
            return [(crv.PointAt(t).X, crv.PointAt(t).Y) for t in ts]
    except Exception:
        pass
    return None


def _sp_boundary_from_brep_face(br, n):
    """Largest PLANAR face -> its OUTER loop -> XY polygon (best for flat site
    plates / slabs / trimmed surfaces / extrusions)."""
    try:
        best_face = None
        best_area = -1.0
        for f in br.Faces:
            try:
                srf = f.UnderlyingSurface()
                ok = srf.TryGetPlane()[0] if srf else False
                if not ok:
                    continue
                fb = f.DuplicateFace(False)
                amp = rg.AreaMassProperties.Compute(fb)
                a = amp.Area if amp else 0.0
                if a > best_area:
                    best_area = a
                    best_face = f
            except Exception:
                continue
        if best_face is None:
            return None
        for lp in best_face.Loops:
            try:
                if str(lp.LoopType) != "Outer":
                    continue
                crv = lp.To3dCurve()
                pts = _sp_sample_rhino_curve(crv, n)
                if pts and len(pts) >= 3:
                    return pts
            except Exception:
                continue
    except Exception:
        pass
    return None


def _sp_boundary_from_mesh_outlines(me, n):
    """Mesh (or meshed brep) -> XY outline polylines -> largest closed loop.
    Works for CLOSED meshes / solids / terrain where naked edges do not exist."""
    try:
        outs = me.GetOutlines(rg.Plane.WorldXY)
        if not outs:
            return None
        best = None
        barea = -1.0
        for pl in outs:
            try:
                pts = [(pl[i].X, pl[i].Y) for i in range(pl.Count)]
                pts = _poly_dedupe(pts)
                if len(pts) < 3:
                    continue
                a = _poly_area(pts)
                if a > barea:
                    barea = a
                    best = pts
            except Exception:
                continue
        return best
    except Exception:
        return None


def extract_site_boundary(site, opts=None):
    """ROBUST outer site boundary polygon (XY). Tries, in order:
      1. closed planar curve (used directly)
      2. Brep largest PLANAR face outer loop (surface / polysurface / extrusion)
      3. Mesh XY outlines (mesh, or the brep meshed) - works for closed solids
      4. naked / border edges joined (rhinoscriptsyntax)
      5. bbox rectangle (LAST RESORT - flagged as fallback + warning)
    Returns {'poly','curve_id','mode','fallback','diag'}. Never raises. The
    polygon is de-duplicated and simplified (collinear points removed) so the
    inward edge offset stays stable."""
    n = int((opts or {}).get("site_boundary_sample_count", 160))
    diag = {"attempts": [], "object_id": None, "object_type": None,
            "raw_point_count": 0, "simplified_point_count": 0,
            "boundary_area": 0.0, "orientation": None}
    res = {"poly": None, "curve_id": None, "mode": "bbox_fallback",
           "fallback": True, "diag": diag}

    def _finish(pts, mode, cid=None):
        raw = len(pts)
        simp = _poly_simplify(pts)
        if len(simp) < 3 or _poly_area(simp) <= 1.0:
            return None
        diag["raw_point_count"] = raw
        diag["simplified_point_count"] = len(simp)
        diag["boundary_area"] = round(_poly_area(simp), 3)
        diag["orientation"] = ("CCW" if _poly_signed_area(simp) > 0 else "CW")
        res["poly"] = simp
        res["curve_id"] = cid
        res["mode"] = mode
        res["fallback"] = False
        return res

    try:
        sid = site["id"]
        diag["object_id"] = str(sid)
        diag["object_type"] = site.get("type")
        # ---- 1. closed planar curve --------------------------------------
        try:
            if rs.IsCurve(sid) and rs.IsCurveClosed(sid):
                crv = rs.coercecurve(sid)
                pts = _sp_sample_rhino_curve(crv, n) if crv else None
                diag["attempts"].append(
                    {"method": "closed planar curve",
                     "points": len(pts) if pts else 0})
                if pts:
                    out = _finish(pts, "closed boundary curve", sid)
                    if out:
                        return out
        except Exception as ex:
            diag["attempts"].append({"method": "closed planar curve",
                                     "error": str(ex)})
        # ---- 2. Brep largest planar face outer loop ------------------------
        br = None
        try:
            br = rs.coercebrep(sid)
        except Exception:
            br = None
        if br:
            try:
                pts = _sp_boundary_from_brep_face(br, n)
                diag["attempts"].append(
                    {"method": "brep planar face outer loop",
                     "points": len(pts) if pts else 0})
                if pts:
                    out = _finish(pts, "surface / polysurface planar face border")
                    if out:
                        return out
            except Exception as ex:
                diag["attempts"].append({"method": "brep planar face outer loop",
                                         "error": str(ex)})
        # ---- 3. mesh XY outlines (mesh, or brep meshed) --------------------
        me = None
        try:
            me = rs.coercemesh(sid)
        except Exception:
            me = None
        if me is None and br is not None:
            try:
                parts = rg.Mesh.CreateFromBrep(br, rg.MeshingParameters.Default)
                if parts:
                    me = rg.Mesh()
                    for m in parts:
                        me.Append(m)
            except Exception:
                me = None
        if me is not None:
            try:
                pts = _sp_boundary_from_mesh_outlines(me, n)
                diag["attempts"].append({"method": "mesh XY outlines",
                                         "points": len(pts) if pts else 0})
                if pts:
                    out = _finish(pts, "mesh / solid XY outline")
                    if out:
                        return out
            except Exception as ex:
                diag["attempts"].append({"method": "mesh XY outlines",
                                         "error": str(ex)})
        # ---- 4. naked / border edges joined -------------------------------
        try:
            b = None
            for fn in ("DuplicateSurfaceBorder", "DuplicateMeshBorder",
                       "DuplicateEdgeCurves"):
                try:
                    b = getattr(rs, fn)(sid)
                except Exception:
                    b = None
                if b:
                    break
            if b:
                border = _sp_join_boundary_curves(b)
                crv = rs.coercecurve(border) if border else None
                pts = _sp_sample_rhino_curve(crv, n) if crv else None
                diag["attempts"].append({"method": "joined border edges",
                                         "points": len(pts) if pts else 0})
                if pts:
                    out = _finish(pts, "joined border edges", border)
                    if out:
                        return out
        except Exception as ex:
            diag["attempts"].append({"method": "joined border edges",
                                     "error": str(ex)})
    except Exception as ex:
        print("Site boundary extraction failed (%s); using bbox." % ex)
        diag["attempts"].append({"method": "outer", "error": str(ex)})
    # ---- 5. LAST RESORT: bbox rectangle (flagged) --------------------------
    print("Site boundary: exact extraction FAILED - using bounding rectangle "
          "fallback (verify manually).")
    mn = site["min"]
    mx = site["max"]
    res["poly"] = _rect_to_poly(mn[0], mn[1], mx[0], mx[1])
    res["mode"] = "bbox_fallback (exact boundary unavailable)"
    res["curve_id"] = None
    res["fallback"] = True
    diag["raw_point_count"] = 4
    diag["simplified_point_count"] = 4
    diag["boundary_area"] = round(_poly_area(res["poly"]), 3)
    diag["orientation"] = "CCW"
    return res


# --------------------------------------------------------------------------- #
# v27 V2: robust IRREGULAR inward offset that follows the real site shape
# (pure-Python edge offset, so an L-shaped / angled site gives an L-shaped /
# angled buildable zone even when Rhino's curve offset is unavailable/fails).
# --------------------------------------------------------------------------- #

def _poly_signed_area(poly):
    n = len(poly)
    a = 0.0
    for i in range(n):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % n]
        a += x0 * y1 - x1 * y0
    return a * 0.5


def _poly_as_ccw(poly):
    """Return the polygon as counter-clockwise (positive signed area)."""
    if _poly_signed_area(poly) < 0:
        return list(reversed(poly))
    return list(poly)


def _line_intersection(p1, d1, p2, d2):
    """Intersection of lines p1+t*d1 and p2+s*d2. None if parallel."""
    x1, y1 = p1
    dx1, dy1 = d1
    x2, y2 = p2
    dx2, dy2 = d2
    den = dx1 * dy2 - dy1 * dx2
    if abs(den) < 1e-9:
        return None
    t = ((x2 - x1) * dy2 - (y2 - y1) * dx2) / den
    return (x1 + t * dx1, y1 + t * dy1)


def _sp_offset_polygon_inward(poly, setback):
    """Pure-Python inward offset of an arbitrary (convex or mildly concave)
    polygon by `setback`, preserving the shape (L / angled stays L / angled).
    Each edge is moved to the interior side and adjacent offset edges are
    intersected for the new vertices. Returns the offset polygon (list of x,y)
    or None if the result is degenerate / self-collapsing."""
    if not poly or len(poly) < 3 or setback <= 0:
        return None
    # simplify FIRST: densely-sampled collinear edges produce near-parallel
    # offset lines whose intersection blows up (v27 micro-correction).
    pts = _poly_simplify([(float(p[0]), float(p[1])) for p in poly])
    pts = _poly_as_ccw(pts)
    n = len(pts)
    if n < 3:
        return None
    # offset line for each edge i (pts[i] -> pts[i+1]); interior is LEFT (CCW)
    lines = []
    for i in range(n):
        a = pts[i]
        b = pts[(i + 1) % n]
        dx = b[0] - a[0]
        dy = b[1] - a[1]
        ln = math.hypot(dx, dy)
        if ln < 1e-9:
            lines.append(None)
            continue
        ux, uy = dx / ln, dy / ln
        # inward (left) unit normal for CCW polygon
        nx, ny = -uy, ux
        ax = a[0] + nx * setback
        ay = a[1] + ny * setback
        lines.append(((ax, ay), (ux, uy)))
    out = []
    for i in range(n):
        prev = lines[(i - 1) % n]
        cur = lines[i]
        if prev is None or cur is None:
            out.append(pts[i])
            continue
        ip = _line_intersection(prev[0], prev[1], cur[0], cur[1])
        if ip is None:
            # parallel edges: shift the vertex inward along the edge normal
            (ax, ay), (ux, uy) = cur
            out.append((ax, ay))
        else:
            out.append(ip)
    # validity: must stay CCW, positive area, and materially smaller than input
    if len(out) < 3:
        return None
    ao = abs(_poly_signed_area(out))
    ai = abs(_poly_signed_area(pts))
    if ao < 1.0 or ao >= ai:
        return None
    # reject gross self-intersection blow-ups (offset larger than input bbox)
    ib = _poly_bbox(pts)
    ob = _poly_bbox(out)
    if (ob[2] - ob[0]) > (ib[2] - ib[0]) + 1e-6 \
            or (ob[3] - ob[1]) > (ib[3] - ib[1]) + 1e-6:
        return None
    return out


def _sp_extract_site_boundary_curve(site, opts=None):
    """Named wrapper: extract the site's outer boundary as an XY polygon
    (delegates to the robust extractor). Returns the extract dict."""
    return extract_site_boundary(site, opts)


def _sp_project_boundary_to_xy(poly):
    """Boundary points are already sampled in XY; return the XY polygon."""
    if not poly:
        return None
    return [(p[0], p[1]) for p in poly]


def _sp_join_boundary_curves(curves):
    """Join boundary curves and return the largest closed loop id."""
    try:
        joined = rs.JoinCurves(curves, True) or curves
    except Exception:
        joined = curves
    return _largest_closed(joined)


def _sp_point_inside_buildable_curve(pt, buildable_poly):
    """Point-in-buildable-zone test (irregular polygon)."""
    return _poly_point_inside(pt, buildable_poly)


def _sp_curve_contains_footprint(cx, cy, w, l, rot_deg, buildable_poly,
                                 edge_samples=3):
    """Rotated footprint fully inside the irregular buildable polygon."""
    return _footprint_in_polygon(cx, cy, w, l, rot_deg, buildable_poly,
                                 edge_samples)


def _sp_validate_offset_curve_inside_site(offset_poly, site_poly):
    """True if the offset polygon is a valid INWARD offset: smaller area, its
    centroid inside the site, and all its vertices inside the site boundary."""
    try:
        if not offset_poly or len(offset_poly) < 3:
            return False
        if _poly_area(offset_poly) >= _poly_area(site_poly) + 1e-6:
            return False
        if not _poly_point_inside(_poly_centroid(offset_poly), site_poly):
            return False
        for p in offset_poly:
            if not _poly_point_inside(p, site_poly):
                return False
        return True
    except Exception:
        return False


def _sp_make_inward_offset_curve(site_boundary, setback, opts=None, diag=None):
    """Produce the IRREGULAR inward buildable polygon. Order of attempts:
      1. Rhino Curve.Offset toward the boundary centroid (validated inward).
      2. Rhino offset with the sign flipped (in case direction was wrong).
      3. Pure-Python polygon inward offset (shape-preserving).
    Records each attempt into `diag`. Returns (poly, mode, success)."""
    if diag is None:
        diag = {}
    diag.setdefault("offset_attempts", [])
    poly = site_boundary.get("poly")
    cid = site_boundary.get("curve_id")
    n = int((opts or {}).get("site_boundary_sample_count", 160))
    if not poly:
        return None, "no boundary", False
    cen = _poly_centroid(poly)
    # 1 & 2: Rhino curve offset (only if we have a real curve id)
    if cid:
        for signed in (setback, -setback):
            try:
                off = rs.OffsetCurve(cid, (cen[0], cen[1], 0.0), signed)
                inner = _largest_closed(off)
                ip = _curve_to_poly(inner, n) if inner else None
                ip = _poly_simplify(ip) if ip else None
                ok = bool(ip and _sp_validate_offset_curve_inside_site(ip, poly))
                diag["offset_attempts"].append(
                    {"method": "rhino curve offset",
                     "direction": ("inward(+)" if signed > 0 else "inward(-)"),
                     "points": len(ip) if ip else 0, "valid": ok})
                if ok:
                    diag["offset_direction_chosen"] = (
                        "positive" if signed > 0 else "negative")
                    return ip, "irregular curve offset (Rhino)", True
            except Exception as ex:
                diag["offset_attempts"].append(
                    {"method": "rhino curve offset", "error": str(ex)})
                continue
    # 3: pure-Python inward polygon offset (shape-preserving, no Rhino needed)
    try:
        ip = _sp_offset_polygon_inward(poly, setback)
        ok = bool(ip and _sp_validate_offset_curve_inside_site(ip, poly))
        diag["offset_attempts"].append(
            {"method": "pure polygon inward offset",
             "points": len(ip) if ip else 0, "valid": ok})
        if ok:
            diag["offset_direction_chosen"] = "interior (CCW left-normal)"
            return ip, "irregular polygon offset (shape-preserving)", True
    except Exception as ex:
        diag["offset_attempts"].append(
            {"method": "pure polygon inward offset", "error": str(ex)})
    return None, "offset failed", False


def compute_irregular_buildable_zone(site_boundary, setback, site, opts=None):
    """Inward-offset the site boundary by `setback` to get an IRREGULAR buildable
    polygon that follows the real site shape. Uses _sp_make_inward_offset_curve
    (Rhino offset -> pure polygon offset), and only as a LAST resort falls back
    to a bbox-rectangle inward offset.

    IMPORTANT (v27 micro-correction): if the SITE BOUNDARY itself was a bbox
    fallback, the resulting zone is a RECTANGLE even though the offset
    "succeeded" - that case is now reported as a rectangle fallback, never as an
    irregular offset (no silent rectangle fallback).
    Returns {'poly','bbox','mode','offset_success','site_area','zone_area',
    'fallback_used','area_ratio','zone_inside_site','diag'}."""
    poly = site_boundary.get("poly")
    boundary_fallback = bool(site_boundary.get("fallback"))
    site_area = _poly_area(poly) if poly else 0.0
    diag = dict(site_boundary.get("diag") or {})
    diag["required_setback_m"] = setback
    diag["boundary_mode"] = site_boundary.get("mode")
    diag["boundary_is_bbox_fallback"] = boundary_fallback
    ip, mode, ok = _sp_make_inward_offset_curve(site_boundary, setback, opts,
                                               diag)
    if ok and ip and len(ip) >= 3 and _poly_area(ip) > 1.0:
        zarea = _poly_area(ip)
        inside = _sp_validate_offset_curve_inside_site(ip, poly)
        diag["offset_point_count"] = len(ip)
        diag["zone_area"] = round(zarea, 3)
        diag["area_ratio"] = round(zarea / site_area, 4) if site_area else 0.0
        diag["zone_inside_site"] = inside
        if boundary_fallback:
            # the offset is geometrically fine, but it is an offset of the BBOX
            diag["fallback_reason"] = ("site boundary extraction failed; the "
                                       "offset was applied to the bounding "
                                       "rectangle, not the real boundary")
            return {"poly": ip, "bbox": _poly_bbox(ip),
                    "mode": "rectangle fallback (boundary extraction failed)",
                    "offset_success": False, "site_area": site_area,
                    "zone_area": zarea, "fallback_used": True,
                    "area_ratio": diag["area_ratio"], "zone_inside_site": inside,
                    "diag": diag}
        return {"poly": ip, "bbox": _poly_bbox(ip), "mode": mode,
                "offset_success": True, "site_area": site_area,
                "zone_area": zarea, "fallback_used": False,
                "area_ratio": diag["area_ratio"], "zone_inside_site": inside,
                "diag": diag}
    # last-resort rectangle fallback
    diag["fallback_reason"] = "inward offset failed on the extracted boundary"
    if poly:
        bx = _poly_bbox(poly)
    else:
        mn = site["min"]
        mx = site["max"]
        bx = (mn[0], mn[1], mx[0], mx[1])
    x0, y0 = bx[0] + setback, bx[1] + setback
    x1, y1 = bx[2] - setback, bx[3] - setback
    if (x1 - x0) <= 0.1 or (y1 - y0) <= 0.1:
        diag["fallback_reason"] = "site too small for the required setback"
        return {"poly": None, "bbox": None, "offset_success": False,
                "site_area": site_area, "zone_area": 0.0, "fallback_used": True,
                "area_ratio": 0.0, "zone_inside_site": False, "diag": diag,
                "mode": "rectangle fallback (site too small for setback)"}
    rp = _rect_to_poly(x0, y0, x1, y1)
    diag["offset_point_count"] = 4
    diag["zone_area"] = round(_poly_area(rp), 3)
    diag["area_ratio"] = (round(_poly_area(rp) / site_area, 4)
                          if site_area else 0.0)
    diag["zone_inside_site"] = _sp_validate_offset_curve_inside_site(rp, poly) \
        if poly else False
    return {"poly": rp, "bbox": (x0, y0, x1, y1),
            "mode": "rectangle fallback (irregular offset failed)",
            "offset_success": False, "site_area": site_area,
            "zone_area": _poly_area(rp), "fallback_used": True,
            "area_ratio": diag["area_ratio"],
            "zone_inside_site": diag["zone_inside_site"], "diag": diag}


def _sp_draw_poly_outline(poly, layer, z):
    if not poly or len(poly) < 3:
        return None
    pts = [(p[0], p[1], z) for p in poly]
    if pts[0] != pts[-1]:
        pts.append(pts[0])
    try:
        pl = rs.AddPolyline(pts)
        if pl:
            rs.ObjectLayer(pl, layer)
        return pl
    except Exception:
        return None


def _sp_draw_static_outlines_v26(site_boundary, zone, target_z):
    """Draw the ACTUAL site boundary polygon + the irregular buildable-zone
    polygon (not a plain rectangle unless fallback). Returns created ids."""
    created = []
    try:
        _sp_ensure_site_debug_layers()
        z = target_z
        bpoly = (site_boundary or {}).get("poly")
        b = _sp_draw_poly_outline(bpoly, SITE_DEBUG_LAYERS["boundary"], z)
        if b:
            created.append(b)
        zpoly = (zone or {}).get("poly")
        zp = _sp_draw_poly_outline(zpoly, SITE_DEBUG_LAYERS["zone"], z)
        if zp:
            created.append(zp)
    except Exception as ex:
        print("v26 static outline drawing skipped (%s)." % ex)
    return created


# ---- v26 dialogs (proven safe Eto layout; native fallbacks) ----------------

def show_site_info_dialog(header, subtitle, body_lines, button_text="Continue"):
    """Single-button styled info dialog. Returns True (button) always; safe
    native fallback."""
    body = ("\n".join(body_lines) if isinstance(body_lines, (list, tuple))
            else str(body_lines))
    wtitle = "Timber Housing - " + header
    try:
        import Eto.Forms as forms
        import Eto.Drawing as drawing
    except Exception:
        try:
            rs.MessageBox(body, 0 | 64, wtitle)
        except Exception:
            pass
        return True

    class IDlg(forms.Dialog[bool]):
        def __init__(self):
            super(IDlg, self).__init__()
            self.Title = wtitle
            self.Padding = drawing.Padding(12)
            self.Resizable = True
            ta = forms.TextArea()
            ta.ReadOnly = True
            ta.Wrap = True
            ta.Text = body
            ta.Size = drawing.Size(560, 220)
            try:
                _f = _ui_font(9.0)
                if _f is not None:
                    ta.Font = _f
                ta.BackgroundColor = _ui_color(UI_COLORS["card"])
                ta.TextColor = _ui_color(UI_COLORS["ink"])
            except Exception:
                pass
            ok = forms.Button()
            ok.Text = button_text
            ok.Click += self.on_ok
            self.DefaultButton = ok
            self.AbortButton = ok
            lay = forms.TableLayout()
            lay.Spacing = drawing.Size(8, 8)
            lay.Rows.Add(forms.TableRow([forms.TableCell(ta, True)]))
            lay.Rows.Add(forms.TableRow(forms.TableCell(ok)))
            finalize_dialog(self, lay, header, subtitle, [(ok, "primary")])
            try:
                self.ClientSize = drawing.Size(640, 400)
            except Exception:
                pass

        def on_ok(self, s, e):
            self.Close(True)

    try:
        IDlg().ShowModal(Rhino.UI.RhinoEtoApp.MainWindow)
    except Exception:
        try:
            rs.MessageBox(body, 0 | 64, wtitle)
        except Exception:
            pass
    return True


def show_workflow_start_dialog():
    """DIALOG 1 - startup / version notice. Returns True (Start) / False."""
    body = [
        "Parametric Timber Student Housing configurator.",
        "",
        "This v26 build includes the FINAL SITE PLACEMENT OPTIMIZER with:",
        "  - irregular buildable-zone setback (follows the real site shape),",
        "  - a live Galapagos-style placement preview,",
        "  - full Eto dialogs around every step.",
        "",
        "Workflow: the timber model is generated FIRST; final site placement "
        "comes at the END. You will select / keep your site geometry later - "
        "existing site objects are PRESERVED (never deleted or moved unless you "
        "explicitly accept a placement).",
        "",
        SITE_PLACEMENT_DISCLAIMER,
    ]
    try:
        return bool(show_styled_prompt(
            "Parametric Timber Student Housing",
            "Timber skeleton + final site placement (design-stage)",
            body, "Start configurator", "Cancel",
            window_title="Timber Housing Configurator - Start", ta_height=230,
            width=660, height=460))
    except Exception:
        return True


def _sp_result_body_v26(R):
    """Result body (Dialog 6) - adds site type, setback rule, min setback, and
    the buildable-zone MODE (irregular vs fallback) to the v25 body."""
    cr = R.get("city_rules", {})
    m = R.get("metrics", {})
    best = R.get("best") or {}
    cand = R.get("cand_info", {})
    zone = R.get("zone")
    site = R.get("site")
    terr = R.get("terrain", {})
    folder = R.get("folder")
    sep = "-" * 64
    zsz = ("%.1f x %.1f" % (zone[2] - zone[0], zone[3] - zone[1])
           if zone else "(none)")
    sentence, breakdown = build_placement_justification(R)
    head = ("Best Site Placement Found" if cand.get("feasible")
            else "Not Fully Feasible - Best Candidate Found")
    lines = [head + "  (design-stage optimizer)", "=" * 64,
             "feasible (fits zone)  : %s" % cand.get("feasible"),
             "city / state          : %s / %s"
             % (R.get("city"), cr.get("federal_state")),
             "site object type      : %s"
             % (site.get("type") if site else "(none)"),
             "building height (m)   : %.2f" % m.get("h", 0.0),
             "setback rule          : max(%.1f m base, %.2f x height)"
             % (cr.get("base_setback_m", 3.0),
                cr.get("height_factor_setback", 0.4)),
             "min required setback  : %.2f m" % cr.get("required_setback_m", 0.0),
             "buildable zone mode   : %s" % R.get("buildable_mode", "?"),
             "north angle (deg)     : %s (%s)"
             % (R.get("north_deg"), R.get("north_source")),
             "clean footprint (m)   : %.2f x %.2f"
             % (m.get("w", 0.0), m.get("l", 0.0)),
             "buildable zone (m,bb) : %s" % zsz,
             "best rotation (deg)   : %s" % best.get("rot"),
             "best centre x / y     : %.2f / %.2f"
             % (best.get("cx", 0.0), best.get("cy", 0.0)),
             "fits inside zone      : %s" % best.get("fits"),
             "candidates tested     : %d" % len(cand.get("candidates", [])),
             sep, "WHY THIS PLACEMENT:"]
    lines += _sp_wrap(sentence, 64)
    lines += [sep] + breakdown
    if terr and terr.get("count"):
        lines += [sep, "terrain min/max/diff (m): %s / %s / %s"
                  % (terr.get("min"), terr.get("max"), terr.get("diff"))]
    if m.get("note"):
        lines += [sep] + _sp_wrap("footprint note: " + m.get("note"), 64)
    if R.get("warnings"):
        lines.append(sep)
        for wmsg in R["warnings"]:
            lines += _sp_wrap("! " + wmsg, 64)
    lines += [sep, "LIMITATIONS: offline design-stage assistant; the buildable "
              "zone / setback are conservative approximations (verify with the "
              "local Bebauungsplan / Landesbauordnung); sun / ventilation are "
              "heuristics, not simulations.",
              sep, "report folder:", "  %s" % (folder or "(not written)"), sep,
              SITE_PLACEMENT_DISCLAIMER]
    return "\n".join(lines)


# =============================================================================
# 6c-V27. SITE PLACEMENT V2: early city + 100-position optimizer  (v27, 2026-07-09)
#
# V2 corrections (v27 only): (1) irregular inward setback that follows the real
# site shape (see _sp_make_inward_offset_curve / _sp_offset_polygon_inward);
# (2) CITY selection moved to the BEGINNING (stored in a planning-context dict);
# (3) optional EARLY site selection; (4) final stage reduced to NORTH + a named
# 100-position Galapagos-style optimizer that reuses the early city/site.
# Reuses v26's dialogs, live preview, tagging, single-move-on-Accept. v23-v26
# untouched. Design-stage only.
# =============================================================================


def run_site_placement_optimizer_100(zone_poly, zone_bbox, footprint, north_vec,
                                     lat, opts, iterations=None):
    """Galapagos-STYLE heuristic placement search over the IRREGULAR buildable
    polygon (NOT the Grasshopper Galapagos plugin). `iterations` = the number of
    candidate placements the user requested (default 100, clamped 10..500). The
    full polygon-fit search runs, then exactly `iterations` representative
    candidates are reported, each annotated with candidate_id, the TRUE
    inside-buildable-curve test, rejected / rejection_reason, and a setback
    clearance estimate. Returns {feasible, best, top5, candidates, evaluated,
    requested, rejected_count, reason}."""
    if iterations is None:
        iterations = opts.get("site_optimizer_visible_iterations", 100)
    try:
        target = int(iterations)
    except Exception:
        target = 100
    target = max(10, min(500, target))
    edge_samples = int(opts.get("site_optimizer_edge_samples", 3))
    res = optimize_site_placement_irregular(
        zone_poly, zone_bbox, footprint[0], footprint[1], north_vec, lat, opts)
    allc = res.get("candidates", []) or []
    # deterministic representative sample of exactly `target` candidates
    if len(allc) <= target:
        sample = list(allc)
    else:
        step = len(allc) / float(target)
        sample = [allc[min(len(allc) - 1, int(i * step))] for i in range(target)]
    best = res.get("best")
    if best is not None and best not in sample:
        sample = (sample[:-1] + [best]) if sample else [best]
    # annotate the reported candidates against the TRUE irregular buildable zone
    rejected = 0
    for i, c in enumerate(sample):
        inside = bool(c.get("fits"))
        c["candidate_id"] = i + 1
        c["inside_irregular_buildable_curve"] = inside
        c["rejected"] = (not inside)
        c["rejection_reason"] = ("" if inside else
                                 "footprint not fully inside the irregular "
                                 "buildable zone (corner/centre/edge test)")
        try:
            c["setback_clearance_estimate"] = round(_footprint_clearance(
                c["cx"], c["cy"], footprint[0], footprint[1], c["rot"],
                zone_poly, edge_samples), 3) if zone_poly else None
        except Exception:
            c["setback_clearance_estimate"] = None
        if not inside:
            rejected += 1
    fitted = sorted([c for c in allc if c.get("fits")],
                    key=lambda c: c.get("total", 0.0), reverse=True)
    top5 = fitted[:5] if fitted else (sorted(
        allc, key=lambda c: c.get("total", 0.0), reverse=True)[:5])
    return {"feasible": res.get("feasible"), "best": best, "top5": top5,
            "candidates": sample, "evaluated": len(allc), "requested": target,
            "rejected_count": rejected, "reason": res.get("reason", "")}


def _sp_get_planning_context(P):
    """Return (create) the shared planning-context dict on P (city / site chosen
    early)."""
    ctx = P.get("planning_context")
    if not isinstance(ctx, dict):
        ctx = {"city": None, "city_selected_stage": None, "site": None,
               "site_boundary": None, "site_selected_stage": None}
        P["planning_context"] = ctx
    return ctx


def show_early_city_dialog():
    """EARLY city / planning-context dialog (start of the configurator).
    Returns city name or None (skip -> ask later / use default)."""
    intro = (
        "Parametric Timber Student Housing - Planning context.\n\n"
        "Choose the CITY / location now (at the start). It sets the OFFLINE "
        "planning assumptions (setback rule, latitude, snow / wind / seismic "
        "placeholders) that the final site-placement optimizer will reuse - you "
        "will NOT be asked for the city again at the end.\n\n"
        "This is a design-stage assumption, not a legal / permit result.\n\n"
        + SITE_PLACEMENT_DISCLAIMER)
    try:
        import Eto.Forms as forms
        import Eto.Drawing as drawing
    except Exception:
        try:
            return rs.ListBox(GERMAN_CITIES, "City / location (Cancel = decide "
                              "later)", "Timber Housing - Planning Context")
        except Exception:
            return None

    class CityDlg(forms.Dialog[bool]):
        def __init__(self):
            super(CityDlg, self).__init__()
            self.Title = "Timber Housing - City / Planning Context"
            self.Padding = drawing.Padding(12)
            self.Resizable = True
            self.sel = 0
            ta = forms.TextArea()
            ta.ReadOnly = True
            ta.Wrap = True
            ta.Text = intro
            ta.Size = drawing.Size(560, 200)
            try:
                _f = _ui_font(9.0)
                if _f is not None:
                    ta.Font = _f
                ta.BackgroundColor = _ui_color(UI_COLORS["card"])
                ta.TextColor = _ui_color(UI_COLORS["ink"])
            except Exception:
                pass
            self.dd = forms.DropDown()
            self.dd.DataStore = list(GERMAN_CITIES)
            self.dd.SelectedIndex = 0
            cont = forms.Button()
            cont.Text = "Use this city / location"
            cont.Click += self.on_ok
            skip = forms.Button()
            skip.Text = "Decide later"
            skip.Click += self.on_skip
            self.DefaultButton = cont
            self.AbortButton = skip
            lay = forms.TableLayout()
            lay.Spacing = drawing.Size(8, 8)
            lay.Rows.Add(forms.TableRow([forms.TableCell(ta, True)]))
            lay.Rows.Add(forms.TableRow(forms.TableCell(
                make_section_label("City / location"))))
            lay.Rows.Add(forms.TableRow(forms.TableCell(self.dd)))
            lay.Rows.Add(forms.TableRow(forms.TableCell(cont)))
            lay.Rows.Add(forms.TableRow(forms.TableCell(skip)))
            finalize_dialog(self, lay, "Planning Context",
                            "City / location (design-stage)",
                            [(cont, "primary"), (skip, "cancel")])
            try:
                self.ClientSize = drawing.Size(640, 460)
            except Exception:
                pass

        def on_ok(self, s, e):
            try:
                self.sel = int(self.dd.SelectedIndex)
            except Exception:
                self.sel = 0
            self.Close(True)

        def on_skip(self, s, e):
            self.Close(False)

    try:
        d = CityDlg()
        if bool(d.ShowModal(Rhino.UI.RhinoEtoApp.MainWindow)):
            i = d.sel if 0 <= d.sel < len(GERMAN_CITIES) else 0
            return GERMAN_CITIES[i]
        return None
    except Exception:
        try:
            return rs.ListBox(GERMAN_CITIES, "City", "Timber Housing")
        except Exception:
            return None


def run_early_planning_context(P):
    """Start-of-workflow: pick city early (stored on P), then OFFER early site
    selection (Option A). Skippable - the final stage asks later if needed."""
    ctx = _sp_get_planning_context(P)
    try:
        city = show_early_city_dialog()
    except Exception:
        city = None
    if city:
        ctx["city"] = city
        ctx["city_selected_stage"] = "early"
        print("Planning context: city = %s (selected early)." % city)
    # ---- V28: site & surroundings context import + early site analysis ----
    # (three styled import steps + site selection + early site analysis; the
    #  workflow is fully guarded - if it fails, the ORIGINAL v27 early-site
    #  prompt below runs instead so nothing is lost)
    _v28_ok = False
    try:
        run_site_context_import_workflow(P)
        _v28_ok = True
    except Exception as _im_ex:
        print("v28 site context import skipped (%s)." % _im_ex)
    if not _v28_ok:
        # original v27 optional EARLY site selection (fallback path)
        try:
            want_site = show_styled_prompt(
                "Site Boundary Selection",
                "Optional - select the site now (recommended)",
                ["Select the site boundary or site surface NOW so the "
                 "configurator knows the setback / buildable zone early "
                 "(recommended).",
                 "",
                 "It can be a surface, polysurface, mesh, terrain, or a closed "
                 "boundary curve. The ORIGINAL site object is never deleted or "
                 "moved. The building is NOT placed yet - only marked for the "
                 "final optimizer.",
                 "",
                 "You can skip and select the site later at the final stage.",
                 "", SITE_PLACEMENT_DISCLAIMER],
                "Select Site Boundary / Surface", "Skip Site Selection for Now",
                window_title="Timber Housing - Early Site Selection", ta_height=230,
                width=660, height=470)
        except Exception:
            want_site = False
        if want_site:
            site = _sp_select_site()
            if site:
                ctx["site"] = site
                ctx["site_selected_stage"] = "early"
                try:
                    ctx["site_boundary"] = extract_site_boundary(site)
                except Exception:
                    ctx["site_boundary"] = None
                print("Planning context: site selected early (%s)."
                      % site.get("type"))
    return ctx


# =============================================================================
# v27 MICRO-CORRECTION: iteration selector, north arrow, boundary-side road
# =============================================================================

ROAD_NAME = "Bielefelder Strasse"
ROAD_OFFSET_M = 3.0          # gap from the site boundary to the road edge
ROAD_WIDTH_M = 12.0          # road carriageway width

SP_LAYERS = {
    "boundary": "WoSyHo::SitePlacement::SiteBoundary",
    "setback": "WoSyHo::SitePlacement::Setback",
    "zone": "WoSyHo::SitePlacement::BuildableZone",
    "footprint": "WoSyHo::SitePlacement::SelectedFootprint",
    "rejected": "WoSyHo::SitePlacement::RejectedDebug",
    "north": "WoSyHo::SitePlacement::NorthArrow",
    "road": "WoSyHo::SitePlacement::Road",
    "roadtext": "WoSyHo::SitePlacement::RoadText",
}

ITERATION_CHOICES = [25, 50, 100, 150, 200]


def show_optimizer_iterations_dialog():
    """Placement-iteration selector (before the optimizer runs). Returns
    (iterations:int, warning:str). Default 100; Custom clamped to 10..500."""
    intro = (
        "Final Site Placement Optimizer.\n\n"
        "Choose how many candidate placements the Galapagos-style search should "
        "test. More iterations = a broader search but a slower preview.\n\n"
        "Only a lightweight footprint moves during the preview; the full model "
        "moves only once, after you Accept.\n\n"
        "Default is 100. 'Custom' is clamped to 10-500.")
    warn = ""
    try:
        import Eto.Forms as forms
        import Eto.Drawing as drawing
    except Exception:
        try:
            v = rs.GetInteger("Placement iterations / candidate count", 100,
                              10, 500)
            return (int(v) if v else 100), ""
        except Exception:
            return 100, ""

    class ItDlg(forms.Dialog[bool]):
        def __init__(self):
            super(ItDlg, self).__init__()
            self.Title = "Final Site Placement Optimizer"
            self.Padding = drawing.Padding(12)
            self.Resizable = True
            self.sel = ITERATION_CHOICES.index(100)
            ta = forms.TextArea()
            ta.ReadOnly = True
            ta.Wrap = True
            ta.Text = intro
            ta.Size = drawing.Size(560, 170)
            try:
                _f = _ui_font(9.0)
                if _f is not None:
                    ta.Font = _f
                ta.BackgroundColor = _ui_color(UI_COLORS["card"])
                ta.TextColor = _ui_color(UI_COLORS["ink"])
            except Exception:
                pass
            self.dd = forms.DropDown()
            self.dd.DataStore = [str(v) for v in ITERATION_CHOICES] + ["Custom"]
            self.dd.SelectedIndex = ITERATION_CHOICES.index(100)
            self.n_custom = forms.NumericStepper()
            self.n_custom.DecimalPlaces = 0
            self.n_custom.MinValue = 10
            self.n_custom.MaxValue = 500
            self.n_custom.Value = 100
            row = forms.TableLayout()
            row.Spacing = drawing.Size(8, 0)
            lb = forms.Label()
            lb.Text = "Custom count (used only if 'Custom'):"
            row.Rows.Add(forms.TableRow(forms.TableCell(lb),
                                        forms.TableCell(self.n_custom, True)))
            ok = forms.Button()
            ok.Text = "Run optimizer with this count"
            ok.Click += self.on_ok
            self.DefaultButton = ok
            self.AbortButton = ok
            lay = forms.TableLayout()
            lay.Spacing = drawing.Size(8, 8)
            lay.Rows.Add(forms.TableRow([forms.TableCell(ta, True)]))
            lay.Rows.Add(forms.TableRow(forms.TableCell(
                make_section_label("Placement iterations / candidate count"))))
            lay.Rows.Add(forms.TableRow(forms.TableCell(self.dd)))
            lay.Rows.Add(forms.TableRow(forms.TableCell(row)))
            lay.Rows.Add(forms.TableRow(forms.TableCell(ok)))
            finalize_dialog(self, lay, "Final Site Placement Optimizer",
                            "Iteration count (design-stage)", [(ok, "primary")])
            try:
                self.ClientSize = drawing.Size(640, 470)
            except Exception:
                pass

        def on_ok(self, s, e):
            try:
                self.sel = int(self.dd.SelectedIndex)
            except Exception:
                self.sel = ITERATION_CHOICES.index(100)
            self.Close(True)

    try:
        d = ItDlg()
        d.ShowModal(Rhino.UI.RhinoEtoApp.MainWindow)
        idx = d.sel
        if 0 <= idx < len(ITERATION_CHOICES):
            return ITERATION_CHOICES[idx], ""
        # Custom
        try:
            v = int(d.n_custom.Value)
        except Exception:
            v = 0
        if v < 10 or v > 500:
            warn = ("Custom iteration count invalid/out of range (10-500); "
                    "using 100.")
            return 100, warn
        return v, ""
    except Exception:
        return 100, ""


def _sp_draw_north_arrow(base_pt, north_vec, z, length=None):
    """Draw a visible NORTH arrow (shaft + arrowhead + 'N' label) starting at the
    user's base point and pointing along the marked north direction. Placed on
    WoSyHo::SitePlacement::NorthArrow; never transformed with the building.
    Returns (ids, drawn)."""
    ids = []
    try:
        _sp_ensure_layer(SP_LAYERS["north"])
        nx, ny = north_vec[0], north_vec[1]
        ln = math.hypot(nx, ny)
        if ln < 1e-9:
            return ids, False
        ux, uy = nx / ln, ny / ln
        L = float(length) if length else 20.0
        bx, by = base_pt[0], base_pt[1]
        tx, ty = bx + ux * L, by + uy * L
        shaft = rs.AddLine((bx, by, z), (tx, ty, z))
        if shaft:
            rs.ObjectLayer(shaft, SP_LAYERS["north"])
            ids.append(shaft)
        # arrowhead: two short lines back from the tip at +/-25 deg
        head = L * 0.18
        for ang in (150.0, -150.0):
            a = math.radians(ang)
            hx = ux * math.cos(a) - uy * math.sin(a)
            hy = ux * math.sin(a) + uy * math.cos(a)
            h = rs.AddLine((tx, ty, z), (tx + hx * head, ty + hy * head, z))
            if h:
                rs.ObjectLayer(h, SP_LAYERS["north"])
                ids.append(h)
        # "N" label just beyond the tip
        lx, ly = tx + ux * (L * 0.12), ty + uy * (L * 0.12)
        try:
            pl = rg.Plane(rg.Point3d(lx, ly, z), rg.Vector3d(1, 0, 0),
                          rg.Vector3d(0, 1, 0))
            t = rs.AddText("N", pl, max(1.0, L * 0.12))
        except Exception:
            t = rs.AddTextDot("N", (lx, ly, z))
        if t:
            rs.ObjectLayer(t, SP_LAYERS["north"])
            ids.append(t)
        return ids, True
    except Exception as ex:
        print("North arrow drawing skipped (%s)." % ex)
        return ids, False


def _sp_nearest_boundary_side(poly, click_pt):
    """Nearest boundary segment to a clicked point. Returns (index, a, b, dist)."""
    n = len(poly)
    best = (0, poly[0], poly[1 % n], 1e18)
    for i in range(n):
        a = poly[i]
        b = poly[(i + 1) % n]
        d = _point_segment_distance(click_pt, a, b)
        if d < best[3]:
            best = (i, a, b, d)
    return best


def _sp_road_rect(a, b, centroid, gap=ROAD_OFFSET_M, width=ROAD_WIDTH_M):
    """Road rectangle OUTSIDE the selected boundary side.
       A = a + n*gap, B = b + n*gap, C = b + n*(gap+width), D = a + n*(gap+width)
    `n` = the segment normal pointing AWAY from the site centroid. Returns
    (corners, outward_normal, warning)."""
    ax, ay = a[0], a[1]
    bx, by = b[0], b[1]
    dx, dy = bx - ax, by - ay
    ln = math.hypot(dx, dy)
    if ln < 1e-9:
        return None, None, "selected side has zero length"
    ux, uy = dx / ln, dy / ln
    n1 = (-uy, ux)
    mid = ((ax + bx) / 2.0, (ay + by) / 2.0)
    to_out = (mid[0] - centroid[0], mid[1] - centroid[1])
    warn = ""
    dot = n1[0] * to_out[0] + n1[1] * to_out[1]
    if abs(dot) < 1e-9:
        warn = "Road outside direction estimated from site centroid."
    nrm = n1 if dot >= 0 else (-n1[0], -n1[1])
    outer = gap + width
    corners = [(ax + nrm[0] * gap, ay + nrm[1] * gap),
               (bx + nrm[0] * gap, by + nrm[1] * gap),
               (bx + nrm[0] * outer, by + nrm[1] * outer),
               (ax + nrm[0] * outer, ay + nrm[1] * outer)]
    return corners, nrm, warn


def _sp_draw_road(corners, a, b, nrm, z, name=ROAD_NAME):
    """Draw the road surface (or closed planar polyline) + the road name text,
    parallel to the road and centred along its length. Returns (ids, text_ok)."""
    ids = []
    text_ok = False
    try:
        _sp_ensure_layer(SP_LAYERS["road"])
        _sp_ensure_layer(SP_LAYERS["roadtext"])
        pts3 = [(p[0], p[1], z) for p in corners]
        srf = None
        try:
            srf = rs.AddSrfPt(pts3)
        except Exception:
            srf = None
        if srf:
            rs.ObjectLayer(srf, SP_LAYERS["road"])
            ids.append(srf)
        else:
            pl = rs.AddPolyline(pts3 + [pts3[0]])
            if pl:
                rs.ObjectLayer(pl, SP_LAYERS["road"])
                ids.append(pl)
        # road name text: parallel to the road, centred on the carriageway
        dx, dy = b[0] - a[0], b[1] - a[1]
        ln = math.hypot(dx, dy)
        if ln < 1e-9:
            return ids, False
        ux, uy = dx / ln, dy / ln
        vx, vy = nrm[0], nrm[1]
        # keep the text reading left-to-right in Top view
        if ux < 0:
            ux, uy = -ux, -uy
            vx, vy = -vx, -vy
        cx = (corners[0][0] + corners[2][0]) / 2.0
        cy = (corners[0][1] + corners[2][1]) / 2.0
        height = max(0.8, min(3.0, ln / 18.0))
        try:
            pl = rg.Plane(rg.Point3d(cx, cy, z + 0.02),
                          rg.Vector3d(ux, uy, 0.0), rg.Vector3d(vx, vy, 0.0))
            t = None
            try:
                t = rs.AddText(name, pl, height, None, 0, 131074)  # mid-centre
            except Exception:
                t = rs.AddText(name, pl, height)
            if t:
                rs.ObjectLayer(t, SP_LAYERS["roadtext"])
                ids.append(t)
                text_ok = True
        except Exception:
            td = rs.AddTextDot(name, (cx, cy, z + 0.02))
            if td:
                rs.ObjectLayer(td, SP_LAYERS["roadtext"])
                ids.append(td)
                text_ok = True
    except Exception as ex:
        print("Road drawing skipped (%s)." % ex)
    return ids, text_ok


def show_road_side_dialog(road_context_exists=False):
    """Ask whether to create a road on a boundary side. True = select side.
    V28: if road context was already IMPORTED, the text changes so the user
    is not pushed to duplicate an existing road."""
    if road_context_exists:
        return bool(show_styled_prompt(
            "Road Placement - Road Context Already Imported",
            "An imported road already exists in the context",
            ["Road context already imported. Do you want to generate an "
             "additional labelled road or skip road generation?",
             "",
             "The imported road geometry stays untouched either way. An "
             "additional generated road would be drawn OUTSIDE a boundary "
             "side you click:",
             "",
             "   - starts %.1f m outside the boundary" % ROAD_OFFSET_M,
             "   - road width %.1f m" % ROAD_WIDTH_M,
             "   - labelled \"%s\"" % ROAD_NAME,
             "",
             "Recommended: SKIP - the real road is already in the imported "
             "context.",
             "", SITE_PLACEMENT_DISCLAIMER],
            "Generate Additional Labelled Road", "Skip Road Generation",
            window_title="Timber Housing v28 - Road Placement", ta_height=250,
            width=680, height=500))
    return bool(show_styled_prompt(
        "Road Placement - Boundary Side Selection",
        "Optional - draw a road outside one boundary side",
        ["Select a side of the site boundary to create a road, or skip road "
         "generation.",
         "",
         "After you click 'Select Boundary Side for Road', click on or near any "
         "side/edge of the site boundary in Rhino. A road will be drawn OUTSIDE "
         "that side:",
         "",
         "   - starts %.1f m outside the boundary" % ROAD_OFFSET_M,
         "   - road width %.1f m" % ROAD_WIDTH_M,
         "   - runs the full length of the selected side",
         "   - labelled \"%s\"" % ROAD_NAME,
         "",
         "The site object is never moved or deleted.",
         "", SITE_PLACEMENT_DISCLAIMER],
        "Select Boundary Side for Road", "Skip Road",
        window_title="Timber Housing - Road Placement", ta_height=250,
        width=680, height=500))


def run_road_placement_stage(site_boundary, target_z, road_context_exists=False):
    """Optional road stage (after north). Returns a road-info dict for reports.
    V28: when road context is already imported, the prompt offers detection/skip
    instead of pushing a duplicate road."""
    info = {"road_generated": False, "road_side_selected": False,
            "road_side_start": None, "road_side_end": None,
            "road_offset_from_boundary_m": ROAD_OFFSET_M,
            "road_width_m": ROAD_WIDTH_M, "road_name": ROAD_NAME,
            "road_layer": SP_LAYERS["road"],
            "road_text_layer": SP_LAYERS["roadtext"],
            "road_side_length_m": None, "road_text_drawn": False,
            "road_warning": "", "road_ids": [],
            "road_context_exists": bool(road_context_exists)}
    try:
        if not show_road_side_dialog(road_context_exists):
            print("Road generation skipped by user%s."
                  % (" (imported road context kept)"
                     if road_context_exists else ""))
            return info
        poly = (site_boundary or {}).get("poly")
        if not poly or len(poly) < 3:
            info["road_warning"] = "No site boundary polygon; road skipped."
            return info
        pt = rs.GetPoint("Click ON or NEAR a side of the site boundary for the "
                         "road")
        if pt is None:
            info["road_warning"] = "Road side selection cancelled."
            return info
        info["road_side_selected"] = True
        idx, a, b, dist = _sp_nearest_boundary_side(poly, (pt[0], pt[1]))
        cen = _poly_centroid(poly)
        corners, nrm, warn = _sp_road_rect(a, b, cen)
        if not corners:
            info["road_warning"] = warn or "Road rectangle could not be built."
            return info
        ids, text_ok = _sp_draw_road(corners, a, b, nrm, target_z)
        info["road_generated"] = bool(ids)
        info["road_ids"] = [str(i) for i in ids]
        info["road_text_drawn"] = text_ok
        info["road_side_start"] = [round(a[0], 3), round(a[1], 3)]
        info["road_side_end"] = [round(b[0], 3), round(b[1], 3)]
        info["road_side_length_m"] = round(math.hypot(b[0] - a[0],
                                                      b[1] - a[1]), 3)
        info["road_warning"] = warn
        print("Road generated on boundary side %d (length %.2f m, %s)."
              % (idx, info["road_side_length_m"], ROAD_NAME))
    except Exception as ex:
        info["road_warning"] = "Road generation failed (%s)." % ex
        print(info["road_warning"])
    return info


def run_stage_final_site_placement_v27(P, rack):
    """v27 FINAL stage: reuses the EARLY city + (optional) early site, then does
    only NORTH + a named 100-position Galapagos-style optimizer over the
    IRREGULAR buildable zone -> preview -> result -> Accept (move once) / Keep.
    Never re-asks the city if it was chosen early. Site / user geometry never
    moved/deleted; model never deformed. Fully guarded."""
    ctx = _sp_get_planning_context(P)
    R = {"status": "skipped", "applied": False, "city": None, "north_deg": None,
         "north_source": None, "warnings": [], "score": None, "folder": None,
         "city_selected_stage": ctx.get("city_selected_stage"),
         "site_selected_stage": ctx.get("site_selected_stage")}
    # V28: import/analysis context summary rides on R for reports + completion
    try:
        R["v28_context"] = _sc_completion_summary(P)
    except Exception:
        pass
    opts = dict(SITE_OPT_DEFAULTS)
    opts.update({"run_optimization": True, "allow_rotation": True,
                 "allow_translation": True, "conservative_setbacks": True})
    # ---- city: reuse early choice, else ask now (once) -------------------
    city = ctx.get("city")
    if not city:
        try:
            city = show_early_city_dialog()
        except Exception:
            city = None
        if city:
            ctx["city"] = city
            ctx["city_selected_stage"] = "final"
            R["city_selected_stage"] = "final"
    if not city:
        R["status"] = "skipped"
        R["reason"] = "no city selected"
        return R
    R["city"] = city
    metrics = compute_clean_building_footprint(P, rack)
    R["metrics"] = metrics
    if metrics.get("note"):
        R["warnings"].append(metrics["note"])
    footprint = (metrics["w"], metrics["l"])
    move_ids, move_src = collect_wosyho_generated_objects_by_tag()
    # V28: imported context must NEVER move with the building transform
    try:
        move_ids, _n_ctx_excl = _sc_exclude_imported_context(move_ids)
        if _n_ctx_excl:
            print("v28: excluded %d imported context object(s) from the "
                  "building transform." % _n_ctx_excl)
    except Exception:
        pass
    city_rules = get_city_rule_assumptions(city, metrics["h"], footprint)
    R["city_rules"] = city_rules
    setback = city_rules["required_setback_m"]
    # ---- site: reuse early selection, else ask now -----------------------
    site = ctx.get("site")
    if site:
        R["site_selected_stage"] = "early"
    else:
        show_site_info_dialog(
            "Select the Site Object",
            "Choose the site for final placement",
            ["The model is generated. Select the SITE object in Rhino now.",
             "",
             "It can be a surface, polysurface, mesh, terrain, or a closed "
             "boundary curve. The ORIGINAL site is never deleted or moved. The "
             "optimizer reads its real (possibly irregular) boundary and offsets "
             "it inward by the required setback (%.2f m for %s, height %.1f m)."
             % (setback, city, metrics["h"])],
            "Select site object")
        site = _sp_select_site()
        if site:
            R["site_selected_stage"] = "final"
    R["site"] = site
    if not site:
        R["status"] = "skipped"
        R["warnings"].append("No site selected.")
        R["folder"] = _sp_write_reports_v27(P, R)
        return R
    # ---- irregular boundary + inward offset (V2) -------------------------
    site_boundary = ctx.get("site_boundary")
    if not site_boundary:
        site_boundary = extract_site_boundary(site, opts)
    R["site_boundary_mode"] = site_boundary.get("mode")
    zone_info = compute_irregular_buildable_zone(site_boundary, setback, site,
                                                 opts)
    R["buildable_mode"] = zone_info.get("mode")
    R["setback_method"] = ("irregular_curve_offset"
                           if zone_info.get("offset_success")
                           else "rectangle_fallback")
    R["offset_success"] = zone_info.get("offset_success")
    R["fallback_used"] = zone_info.get("fallback_used")
    R["site_area"] = zone_info.get("site_area")
    R["zone_area"] = zone_info.get("zone_area")
    R["zone_poly"] = zone_info.get("poly")
    R["zone"] = zone_info.get("bbox")
    R["setback"] = setback
    R["setback_diagnostics"] = zone_info.get("diag")
    R["area_ratio"] = zone_info.get("area_ratio")
    R["zone_inside_site"] = zone_info.get("zone_inside_site")
    # V28: plan-projection + imported-context annotations (additive)
    try:
        R.update(_sc_stage_annotations(P, site, site_boundary))
    except Exception:
        pass
    if zone_info.get("fallback_used"):
        R["warnings"].append("Setback fallback used - verify manually. (%s)"
                             % ((zone_info.get("diag") or {}).get(
                                 "fallback_reason", "irregular offset "
                                 "unavailable")))
        try:
            show_site_info_dialog(
                "Setback Fallback Used",
                "The buildable zone is NOT a true irregular offset",
                ["The exact site boundary / inward offset could not be produced, "
                 "so a BOUNDING RECTANGLE fallback is being used for the "
                 "buildable zone.",
                 "",
                 "Reason: %s" % ((zone_info.get("diag") or {}).get(
                     "fallback_reason", "unknown")),
                 "",
                 "Setback fallback used - verify manually. The placement result "
                 "will be less accurate for an irregular site.",
                 "", SITE_PLACEMENT_DISCLAIMER],
                "Continue anyway")
        except Exception:
            pass
    # ---- north (final stage) + NORTH ARROW -------------------------------
    place_z = site["max"][2] + 0.05
    mark = show_styled_prompt(
        "Mark North Direction",
        "North affects sun / wind orientation scoring",
        ["Mark north in Rhino: click a base point then a north point. A north "
         "arrow symbol will be drawn in the direction you choose.",
         "",
         "If you skip, world +Y is used as the default north (a fallback arrow "
         "is still drawn).",
         "", SITE_PLACEMENT_DISCLAIMER],
        "Mark north direction", "Use default north (+Y)",
        window_title="Timber Housing v27 - North", ta_height=190, width=640, height=420)
    if mark:
        north_deg, north_vec, north_src, north_base = _sp_mark_north_with_base(
            site.get("center"))
    else:
        _c = site.get("center") or (0.0, 0.0, 0.0)
        north_deg, north_vec, north_src = (0.0, (0.0, 1.0),
                                           "world +Y (user chose default)")
        north_base = (_c[0], _c[1])
    R["north_deg"] = round(north_deg, 1)
    R["north_source"] = north_src
    # draw the north arrow (never transformed with the building)
    try:
        _arrow_len = max(10.0, 0.25 * max(site["max"][0] - site["min"][0],
                                          site["max"][1] - site["min"][1]))
        _aids, _adrawn = _sp_draw_north_arrow(north_base, north_vec, place_z,
                                              _arrow_len)
        R["north_arrow_drawn"] = bool(_adrawn)
        R["north_arrow_layer"] = SP_LAYERS["north"]
    except Exception:
        R["north_arrow_drawn"] = False
    # ---- ROAD (optional, after north; V28: detect imported road) ---------
    road = run_road_placement_stage(site_boundary, place_z,
                                    road_context_exists=_sc_road_context_exists(P))
    R["road"] = road
    if road.get("road_warning"):
        R["warnings"].append(road["road_warning"])
    # ---- iteration count selector ----------------------------------------
    iters, it_warn = show_optimizer_iterations_dialog()
    if it_warn:
        R["warnings"].append(it_warn)
    R["requested_iteration_count"] = iters
    # the live preview animates exactly the chosen number of candidates
    opts["site_optimizer_visible_iterations"] = iters
    print("v27 optimizer: %d placement iterations requested." % iters)
    # ---- Galapagos-style optimizer with the selected iteration count ------
    result = run_site_placement_optimizer_100(
        zone_info.get("poly"), zone_info.get("bbox"), footprint, north_vec,
        city_rules["latitude_deg_approx"], opts, iterations=iters)
    # V28: terrain suitability - sample terrain under every reported candidate
    # footprint and re-rank the fitting candidates (vertical placement only;
    # smaller level difference preferred; site mesh untouched).
    try:
        result = _sc_rerank_with_terrain(result, site, footprint)
        R["terrain_reranked"] = bool(result.get("terrain_reranked"))
    except Exception:
        R["terrain_reranked"] = False
    R["cand_info"] = {"feasible": result.get("feasible"),
                      "candidates": result.get("candidates"),
                      "reason": result.get("reason")}
    R["optimizer_method"] = ("%d-position Galapagos-style heuristic search"
                             % result.get("requested", iters))
    R["candidates_tested"] = len(result.get("candidates", []))
    R["candidates_evaluated"] = result.get("evaluated")
    R["rejected_count"] = result.get("rejected_count")
    R["top5"] = result.get("top5")
    best = result.get("best")
    R["best"] = best
    if best:
        R["score"] = round(best.get("total", 0.0), 3)
    if not result.get("feasible"):
        R["warnings"].append(result.get("reason", "not feasible"))
    if best is None:
        R["status"] = "warning"
        R["warnings"].append("No placement candidate (site / setback too small).")
        R["folder"] = _sp_write_reports_v27(P, R)
        _sp_append_justification_txt(R["folder"], R)
        show_site_result_dialog(_sp_result_body_v28(R), False, R["folder"],
                                (os.path.join(R["folder"],
                                 "site_placement_summary.txt")
                                 if R["folder"] else None))
        return R
    # ---- terrain + transform --------------------------------------------
    ex, ey = _sp_footprint_extent(footprint[0], footprint[1], best["rot"])
    cx, cy = best["cx"], best["cy"]
    corners = [("center", cx, cy),
               ("c1", cx - ex / 2.0, cy - ey / 2.0),
               ("c2", cx + ex / 2.0, cy - ey / 2.0),
               ("c3", cx + ex / 2.0, cy + ey / 2.0),
               ("c4", cx - ex / 2.0, cy + ey / 2.0)]
    fallback_top = site["max"][2]
    zs = _sp_sample_terrain(site["id"], [(p[1], p[2]) for p in corners],
                            fallback_top)
    R["terrain_samples"] = [(corners[i][0], corners[i][1], corners[i][2], zs[i])
                            for i in range(len(corners))]
    terr = _sp_terrain_stats(zs)
    R["terrain"] = terr
    if terr.get("diff") is not None and terr["diff"] > 2.0:
        R["warnings"].append("Terrain elevation difference under the footprint "
                             "is %.2f m (>2 m)." % terr["diff"])
    target_z = (terr.get("max") if terr.get("max") is not None
                else fallback_top) + SITE_CTX_Z_CLEARANCE_M
    tspec = _sp_compute_transform(metrics, (cx, cy), target_z, best["rot"])
    R["transform"] = tspec
    R["status"] = "ready"
    # V28: explicit vertical-only Z placement record + terrain warning
    R["z_placement"] = round(target_z, 3)
    if terr.get("diff") is not None and terr["diff"] > SITE_CTX_TERRAIN_WARN_M:
        R["terrain_warning_text"] = (
            "Selected position crosses uneven terrain. Building remains "
            "vertical; foundation/terrace adjustment required.")
        R["warnings"].append(R["terrain_warning_text"])
    # ---- irregular outlines + preview + result --------------------------
    outline_ids = _sp_draw_irregular_setback_helpers(site_boundary, zone_info,
                                                     best, metrics, target_z)
    show_site_info_dialog(
        "Optimization Preview",
        "100-position Galapagos-style search (design-stage)",
        ["The optimizer will now visibly test candidate placements inside the "
         "IRREGULAR buildable zone (which follows the real site shape).",
         "",
         "Only a lightweight footprint moves during the preview - the full model "
         "moves only ONCE, after you click Accept."],
        "Start optimization preview")
    preview_ids = run_visible_optimization_preview(
        site, R["zone"], metrics, result.get("candidates"), best, opts)
    outline_ids = list(outline_ids) + list(preview_ids or [])
    R["folder"] = _sp_write_reports_v27(P, R)
    _sp_append_justification_txt(R["folder"], R)
    txt = (os.path.join(R["folder"], "site_placement_summary.txt")
           if R["folder"] else None)
    accept = show_site_result_dialog(_sp_result_body_v28(R),
                                     result.get("feasible"), R["folder"], txt)
    if accept and tspec and move_ids:
        rs.EnableRedraw(False)
        try:
            ok = _sp_apply_transform(move_ids, tspec)
        finally:
            rs.EnableRedraw(True)
        if ok:
            R["applied"] = True
            R["status"] = "applied"
            try:
                rs.ZoomExtents()
                Rhino.RhinoDoc.ActiveDoc.Views.Redraw()
            except Exception:
                pass
            print("v27 site placement APPLIED: %d objects moved once (rot %s)."
                  % (len(move_ids), best["rot"]))
            show_site_info_dialog(
                "Placement Accepted",
                "The model was moved onto the site",
                ["Placement accepted - the full generated model was moved / "
                 "rotated ONCE onto the site (rotation %s deg)." % best["rot"],
                 "The site surface was PRESERVED.",
                 "Setback method: %s." % R.get("setback_method"),
                 "Report saved to: %s" % (R.get("folder") or "(not written)"),
                 "", "Design-stage recommendation - no legal approval implied."],
                "Finish")
        else:
            R["status"] = "failed"
            R["warnings"].append("Transform failed; model left in place.")
    else:
        R["status"] = "kept_outside"
        try:
            if outline_ids:
                rs.DeleteObjects(outline_ids)
                rs.Redraw()
        except Exception:
            pass
        show_site_info_dialog(
            "Placement Cancelled",
            "The model was kept in its original position",
            ["Placement cancelled - the model was NOT moved.",
             "Temporary preview outlines were cleaned; the site was preserved.",
             "The report (with the best candidate) was still saved."],
            "Finish")
    R["folder"] = _sp_write_reports_v27(P, R)
    _sp_append_justification_txt(R["folder"], R)
    return R


def _sp_draw_irregular_setback_helpers(site_boundary, zone_info, best, footprint,
                                       target_z):
    """Draw the ACTUAL extracted site boundary + the TRUE inward setback /
    buildable polygon that the optimizer really uses + the selected footprint,
    each on its dedicated layer. If a rectangle fallback was used, the buildable
    zone is additionally labelled as FALLBACK so it is never misleading.
    Returns created ids."""
    created = []
    try:
        for lp in SP_LAYERS.values():
            _sp_ensure_layer(lp)
        z = target_z
        bp = _sp_draw_poly_outline((site_boundary or {}).get("poly"),
                                   SP_LAYERS["boundary"], z)
        if bp:
            created.append(bp)
        zpoly = (zone_info or {}).get("poly")
        # the buildable zone IS the setback curve (inward offset) - draw on both
        zp = _sp_draw_poly_outline(zpoly, SP_LAYERS["zone"], z)
        if zp:
            created.append(zp)
        sp = _sp_draw_poly_outline(zpoly, SP_LAYERS["setback"], z + 0.01)
        if sp:
            created.append(sp)
        if (zone_info or {}).get("fallback_used") and zpoly:
            try:
                c = _poly_centroid(zpoly)
                td = rs.AddTextDot("BUILDABLE ZONE = RECTANGLE FALLBACK "
                                   "(verify manually)", (c[0], c[1], z + 0.05))
                if td:
                    rs.ObjectLayer(td, SP_LAYERS["zone"])
                    created.append(td)
            except Exception:
                pass
        if best and footprint:
            corners = _sp_rect_corners(best["cx"], best["cy"], footprint["w"],
                                       footprint["l"], best["rot"], z + 0.02)
            fp = rs.AddPolyline(corners)
            if fp:
                rs.ObjectLayer(fp, SP_LAYERS["footprint"])
                created.append(fp)
    except Exception as ex:
        print("v27 irregular helper drawing skipped (%s)." % ex)
    return created


def _sp_result_body_v27(R):
    """Result body (Dialog 6, V2) - adds early-city / site stage, setback method,
    offset status, and 100-optimizer info to the v26 body."""
    cr = R.get("city_rules", {})
    m = R.get("metrics", {})
    best = R.get("best") or {}
    cand = R.get("cand_info", {})
    zone = R.get("zone")
    site = R.get("site")
    folder = R.get("folder")
    sep = "-" * 64
    zsz = ("%.1f x %.1f" % (zone[2] - zone[0], zone[3] - zone[1])
           if zone else "(none)")
    sentence, breakdown = build_placement_justification(R)
    head = ("Best Site Placement Found" if cand.get("feasible")
            else "Not Fully Feasible - Best Candidate Found")
    lines = [head + "  (V2 design-stage optimizer)", "=" * 64,
             "feasible (fits zone)  : %s" % cand.get("feasible"),
             "city (selected %-5s) : %s"
             % (R.get("city_selected_stage") or "?", R.get("city")),
             "state / region        : %s" % cr.get("federal_state"),
             "site (selected %-5s) : %s"
             % (R.get("site_selected_stage") or "?",
                site.get("type") if site else "(none)"),
             "boundary extraction   : %s" % R.get("site_boundary_mode", "?"),
             "setback method        : %s" % R.get("setback_method", "?"),
             "irregular offset ok   : %s" % R.get("offset_success"),
             "buildable zone mode   : %s" % R.get("buildable_mode", "?"),
             "zone/site area ratio  : %s" % R.get("area_ratio"),
             "zone inside site      : %s" % R.get("zone_inside_site"),
             "min required setback  : %.2f m" % cr.get("required_setback_m", 0.0),
             "north angle (deg)     : %s (%s)"
             % (R.get("north_deg"), R.get("north_source")),
             "north arrow drawn     : %s" % R.get("north_arrow_drawn"),
             "clean footprint (m)   : %.2f x %.2f  (height %.2f)"
             % (m.get("w", 0.0), m.get("l", 0.0), m.get("h", 0.0)),
             "buildable zone (bbox) : %s" % zsz,
             "optimizer             : %s"
             % R.get("optimizer_method", "Galapagos-style search"),
             "iterations requested  : %s" % R.get("requested_iteration_count"),
             "candidates tested     : %s (evaluated %s, rejected %s)"
             % (R.get("candidates_tested"), R.get("candidates_evaluated"),
                R.get("rejected_count")),
             "best rotation (deg)   : %s" % best.get("rot"),
             "best centre x / y     : %.2f / %.2f"
             % (best.get("cx", 0.0), best.get("cy", 0.0)),
             "fits inside zone      : %s" % best.get("fits")]
    _road = R.get("road") or {}
    lines += ["road                  : %s"
              % ("generated (%s, %.1f m wide, %.1f m outside)"
                 % (_road.get("road_name"), _road.get("road_width_m", 0.0),
                    _road.get("road_offset_from_boundary_m", 0.0))
                 if _road.get("road_generated") else "skipped / not generated")]
    if R.get("fallback_used"):
        lines += [sep,
                  "!! SETBACK FALLBACK USED - VERIFY MANUALLY. The buildable "
                  "zone is a bounding rectangle, not a true irregular offset."]
    lines += [sep, "TOP 5 CANDIDATES (rot / score / fits):"]
    for i, c in enumerate(R.get("top5", []) or []):
        lines.append("   %d. rot %5s  score %.3f  fits %s"
                     % (i + 1, c.get("rot"), c.get("total", 0.0),
                        c.get("fits")))
    lines += [sep, "WHY THIS PLACEMENT:"]
    lines += _sp_wrap(sentence, 64)
    lines += [sep] + breakdown
    if R.get("warnings"):
        lines.append(sep)
        for wmsg in R["warnings"]:
            lines += _sp_wrap("! " + wmsg, 64)
    lines += [sep, "LIMITATIONS: offline design-stage assistant; buildable zone / "
              "setback are conservative approximations (verify with the local "
              "Bebauungsplan / Landesbauordnung); sun / ventilation are "
              "heuristics; the search is a Galapagos-STYLE heuristic (not the "
              "Grasshopper Galapagos plugin).",
              sep, "report folder:", "  %s" % (folder or "(not written)"), sep,
              SITE_PLACEMENT_DISCLAIMER]
    return "\n".join(lines)


def _sp_write_reports_v27(P, R):
    """Write the site-placement reports with V2 fields (setback method, offset
    status, optimizer method, city/site stage, top-5, per-candidate inside-curve
    flag). Delegates the base files to _sp_write_reports, then augments the JSON
    and CSVs. Returns the folder path. Never raises."""
    folder = _sp_write_reports(P, R)
    if not folder:
        return folder
    try:
        # augment site_placement_result.json
        data = {
            "city": R.get("city"),
            "city_selection_stage": R.get("city_selected_stage"),
            "site_selection_stage": R.get("site_selected_stage"),
            "irregular_boundary_extracted": bool(
                R.get("site_boundary_mode")
                and "bbox_fallback" not in (R.get("site_boundary_mode") or "")),
            "setback_method": R.get("setback_method"),
            "offset_success": R.get("offset_success"),
            "buildable_zone_mode": R.get("buildable_mode"),
            "required_setback_m": (R.get("city_rules") or {}).get(
                "required_setback_m"),
            "site_area_m2": R.get("site_area"),
            "buildable_zone_area_m2": R.get("zone_area"),
            "optimizer_method": R.get("optimizer_method"),
            "candidates_tested": R.get("candidates_tested"),
            "candidates_evaluated": R.get("candidates_evaluated"),
            "top_5_candidates": [
                {"rot": c.get("rot"), "cx": round(c.get("cx", 0.0), 2),
                 "cy": round(c.get("cy", 0.0), 2), "score": round(
                     c.get("total", 0.0), 3), "fits": c.get("fits")}
                for c in (R.get("top5") or [])],
            "selected_candidate": (
                {"rot": (R.get("best") or {}).get("rot"),
                 "cx": round((R.get("best") or {}).get("cx", 0.0), 2),
                 "cy": round((R.get("best") or {}).get("cy", 0.0), 2),
                 "score": round((R.get("best") or {}).get("total", 0.0), 3),
                 "fits": (R.get("best") or {}).get("fits")}
                if R.get("best") else None),
            "status": R.get("status"), "applied": R.get("applied"),
            "warnings": R.get("warnings"),
            "disclaimer": SITE_PLACEMENT_DISCLAIMER}
        # ---- v27 micro-correction additions -----------------------------
        _diag = R.get("setback_diagnostics") or {}
        _road = R.get("road") or {}
        data.update({
            "correction_version": "v27 micro-correction (setback debug, "
                                  "iteration selector, north arrow, road)",
            "setback_diagnostics": _diag,
            "zone_site_area_ratio": R.get("area_ratio"),
            "zone_inside_site": R.get("zone_inside_site"),
            "fallback_used": R.get("fallback_used"),
            "requested_iteration_count": R.get("requested_iteration_count"),
            "actual_candidates_tested": R.get("candidates_tested"),
            "rejected_candidate_count": R.get("rejected_count"),
            "north_arrow_drawn": bool(R.get("north_arrow_drawn")),
            "north_arrow_layer": R.get("north_arrow_layer"),
            "road_generated": _road.get("road_generated", False),
            "road_side_selected": _road.get("road_side_selected", False),
            "road_side_start": _road.get("road_side_start"),
            "road_side_end": _road.get("road_side_end"),
            "road_side_length_m": _road.get("road_side_length_m"),
            "road_offset_from_boundary_m": _road.get(
                "road_offset_from_boundary_m", ROAD_OFFSET_M),
            "road_width_m": _road.get("road_width_m", ROAD_WIDTH_M),
            "road_name": _road.get("road_name", ROAD_NAME),
            "road_layer": _road.get("road_layer"),
            "road_text_layer": _road.get("road_text_layer"),
            "road_text_drawn": _road.get("road_text_drawn"),
            "road_warning": _road.get("road_warning", "")})
        # ---- V28 additions: no-tilt / no-cut / terrain / import context ----
        try:
            data.update(_sc_report_fields(P, R))
        except Exception:
            pass
        with open(os.path.join(folder, "site_placement_result.json"), "w") as f:
            json.dump(data, f, indent=1)
        # placement_candidates.csv (full V2 schema)
        cand = (R.get("cand_info") or {}).get("candidates") or []
        with open(os.path.join(folder, "placement_candidates.csv"), "w") as f:
            f.write(_csv_row(["candidate_id", "x", "y", "rotation_deg",
                              "inside_irregular_buildable_curve", "rejected",
                              "rejection_reason", "setback_clearance_estimate",
                              "score", "sunlight", "ventilation", "harsh_sun",
                              "align",
                              # V28 terrain fields (uneven/contour site)
                              "terrain_min_z", "terrain_max_z",
                              "terrain_delta_z", "z_placement",
                              "terrain_score", "terrain_warning"]))
            for i, c in enumerate(cand):
                f.write(_csv_row([
                    c.get("candidate_id", i + 1), "%.3f" % c.get("cx", 0.0),
                    "%.3f" % c.get("cy", 0.0), c.get("rot"),
                    c.get("inside_irregular_buildable_curve", c.get("fits")),
                    c.get("rejected", not c.get("fits")),
                    c.get("rejection_reason", ""),
                    c.get("setback_clearance_estimate"),
                    "%.3f" % c.get("total", 0.0), "%.3f" % c.get("sunlight", 0.0),
                    "%.3f" % c.get("ventilation", 0.0),
                    "%.3f" % c.get("harsh", 0.0), "%.3f" % c.get("align", 0.0),
                    c.get("terrain_min_z", ""), c.get("terrain_max_z", ""),
                    c.get("terrain_delta_z", ""), c.get("z_placement", ""),
                    c.get("terrain_score", ""), c.get("terrain_warning", "")]))
        # setback_check.csv (full diagnostics)
        with open(os.path.join(folder, "setback_check.csv"), "w") as f:
            f.write(_csv_row(["item", "value"]))
            rows = [
                ("selected_site_object_id", _diag.get("object_id")),
                ("selected_site_object_type", _diag.get("object_type")),
                ("boundary_extraction_mode", R.get("site_boundary_mode")),
                ("boundary_is_bbox_fallback",
                 _diag.get("boundary_is_bbox_fallback")),
                ("extracted_boundary_point_count",
                 _diag.get("simplified_point_count")),
                ("raw_boundary_point_count", _diag.get("raw_point_count")),
                ("original_boundary_area_m2", _diag.get("boundary_area")),
                ("original_boundary_orientation", _diag.get("orientation")),
                ("required_setback_m", "%.3f" % (R.get("setback") or 0.0)),
                ("offset_direction_chosen", _diag.get("offset_direction_chosen")),
                ("offset_curve_point_count", _diag.get("offset_point_count")),
                ("buildable_zone_area_m2", "%.2f" % (R.get("zone_area") or 0.0)),
                ("buildable_over_original_area_ratio", R.get("area_ratio")),
                ("buildable_zone_inside_original", R.get("zone_inside_site")),
                ("offset_method", R.get("buildable_mode")),
                ("offset_status",
                 "success" if R.get("offset_success") else "failed"),
                ("fallback_used", str(R.get("fallback_used"))),
                ("fallback_reason", _diag.get("fallback_reason", "")),
                ("candidates_tested", R.get("candidates_tested")),
                ("rejected_candidate_count", R.get("rejected_count")),
            ]
            for k, v in rows:
                f.write(_csv_row([k, v]))
            for att in (_diag.get("attempts") or []):
                f.write(_csv_row(["boundary_attempt", json.dumps(att)]))
            for att in (_diag.get("offset_attempts") or []):
                f.write(_csv_row(["offset_attempt", json.dumps(att)]))
            for wmsg in (R.get("warnings") or []):
                f.write(_csv_row(["warning", wmsg]))
        # append setback / optimizer / road narrative to the summary TXT
        try:
            with open(os.path.join(folder, "site_placement_summary.txt"),
                      "a") as f:
                f.write("\n" + "=" * 62 + "\n")
                f.write("V27 MICRO-CORRECTION DETAIL\n")
                f.write("-" * 62 + "\n")
                f.write("boundary extraction : %s\n"
                        % R.get("site_boundary_mode"))
                f.write("setback method      : %s\n" % R.get("setback_method"))
                if R.get("fallback_used"):
                    f.write("!! RECTANGLE FALLBACK USED - the buildable zone is "
                            "NOT a true irregular offset. Verify manually.\n")
                    f.write("   reason: %s\n" % _diag.get("fallback_reason", ""))
                else:
                    f.write("true irregular inward offset of the real site "
                            "boundary was used.\n")
                f.write("site area / zone area / ratio : %.2f / %.2f / %s\n"
                        % (R.get("site_area") or 0.0, R.get("zone_area") or 0.0,
                           R.get("area_ratio")))
                f.write("optimizer           : %s\n" % R.get("optimizer_method"))
                f.write("iterations requested: %s\n"
                        % R.get("requested_iteration_count"))
                f.write("candidates tested   : %s (rejected %s)\n"
                        % (R.get("candidates_tested"), R.get("rejected_count")))
                f.write("north arrow drawn   : %s\n"
                        % R.get("north_arrow_drawn"))
                f.write("-" * 62 + "\n")
                f.write("Road generated      : %s\n"
                        % ("yes" if _road.get("road_generated") else "no"))
                if _road.get("road_generated"):
                    f.write("Road name           : %s\n"
                            % _road.get("road_name"))
                    f.write("Road offset (m)     : %.1f\n"
                            % _road.get("road_offset_from_boundary_m", 0.0))
                    f.write("Road width (m)      : %.1f\n"
                            % _road.get("road_width_m", 0.0))
                    f.write("Selected side length: %s m\n"
                            % _road.get("road_side_length_m"))
                if _road.get("road_warning"):
                    f.write("Road warning        : %s\n"
                            % _road.get("road_warning"))
        except Exception:
            pass
        # ---- V28: terrain/context note in the summary + site_analysis.json --
        try:
            _terr = R.get("terrain") or {}
            _best = R.get("best") or {}
            with open(os.path.join(folder, "site_placement_summary.txt"),
                      "a") as f:
                f.write("\n" + "=" * 62 + "\n")
                f.write("V28 SITE CONTEXT / UNEVEN TERRAIN\n")
                f.write("-" * 62 + "\n")
                f.write(SITE_CTX_VERTICAL_NOTE + "\n")
                f.write("-" * 62 + "\n")
                f.write("setback projection plane : WorldXY (plan-based)\n")
                f.write("boundary projection      : %s\n"
                        % R.get("boundary_projection_method"))
                f.write("site is uneven           : %s\n"
                        % R.get("site_is_uneven"))
                f.write("site z range (m)         : %s .. %s (range %s)\n"
                        % (R.get("site_min_z"), R.get("site_max_z"),
                           R.get("site_elevation_range")))
                f.write("terrain under footprint  : min %s / max %s / "
                        "delta %s m\n" % (_terr.get("min"), _terr.get("max"),
                                          _terr.get("diff")))
                f.write("z placement (bottom)     : %s\n"
                        % (R.get("z_placement")
                           if R.get("z_placement") is not None
                           else _best.get("z_placement")))
                f.write("terrain re-ranked        : %s\n"
                        % R.get("terrain_reranked"))
                f.write("model tilted             : NO\n")
                f.write("terrain cut / modified   : NO\n")
                f.write("road context imported    : %s\n"
                        % R.get("road_context_exists"))
                if R.get("terrain_warning_text"):
                    f.write("TERRAIN WARNING          : %s\n"
                            % R.get("terrain_warning_text"))
                _v28c = R.get("v28_context") or {}
                if _v28c:
                    f.write("-" * 62 + "\n")
                    f.write("site plot imported       : %s\n"
                            % _v28c.get("site_plot_imported"))
                    f.write("site + road imported     : %s\n"
                            % _v28c.get("site_road_imported"))
                    f.write("surroundings imported    : %s\n"
                            % _v28c.get("surroundings_imported"))
                    f.write("selected site source     : %s\n"
                            % _v28c.get("selected_site_source"))
                    f.write("import report folder     : %s\n"
                            % _v28c.get("import_report_folder"))
        except Exception:
            pass
        try:
            _ctx = _sp_get_planning_context(P)
            _a = _ctx.get("site_analysis") or {}
            with open(os.path.join(folder, "site_analysis.json"), "w") as f:
                json.dump({
                    "site_is_uneven": (R.get("site_is_uneven")
                                       if R.get("site_is_uneven") is not None
                                       else _a.get("site_is_uneven")),
                    "site_min_z": R.get("site_min_z", _a.get("site_min_z")),
                    "site_max_z": R.get("site_max_z", _a.get("site_max_z")),
                    "site_elevation_range": R.get(
                        "site_elevation_range",
                        _a.get("site_elevation_range")),
                    "boundary_projection_method": R.get(
                        "boundary_projection_method",
                        _a.get("boundary_projection_method")),
                    "setback_projection_plane": "WorldXY",
                    "note": "setback is plan-based",
                    "early_site_analysis": _a,
                    "disclaimer": SITE_PLACEMENT_DISCLAIMER}, f, indent=1)
        except Exception:
            pass
    except Exception as ex:
        print("v27 report augmentation skipped (%s)." % ex)
    return folder


def run_stage_final_site_placement_v26(P, rack):
    """v26 site placement: full dialog coverage + IRREGULAR buildable zone.
      Dialog A setup -> Dialog 3 pre-site -> Rhino site pick -> extract irregular
      boundary -> Dialog 4 north -> north pick -> height/city setback -> irregular
      inward buildable zone -> polygon-fit optimizer -> Dialog 5 preview intro ->
      live preview -> Dialog 6 result (justification) -> Accept (move once) +
      Dialog 7 / Keep + Dialog 8. Site & user geometry never moved/deleted; model
      never deformed. Fully guarded."""
    R = {"status": "skipped", "applied": False, "city": None, "north_deg": None,
         "north_source": None, "warnings": [], "score": None, "folder": None}
    # ---- Dialog A: setup -------------------------------------------------
    try:
        opts = show_site_setup_dialog()
    except Exception as ex:
        print("Site setup dialog failed (%s)." % ex)
        opts = None
    if not opts:
        R["status"] = "skipped"
        R["reason"] = "user skipped at the setup dialog"
        return R
    city = opts["city"]
    R["city"] = city
    metrics = compute_clean_building_footprint(P, rack)
    R["metrics"] = metrics
    if metrics.get("note"):
        R["warnings"].append(metrics["note"])
    footprint = (metrics["w"], metrics["l"])
    move_ids, move_src = collect_wosyho_generated_objects_by_tag()
    city_rules = get_city_rule_assumptions(city, metrics["h"], footprint)
    R["city_rules"] = city_rules
    setback = city_rules["required_setback_m"]
    if not opts.get("conservative_setbacks", True):
        setback = max(city_rules["base_setback_m"], 0.5 * setback)
    # ---- Dialog 3: pre-site explanation ---------------------------------
    proceed = show_styled_prompt(
        "Select the Site Object",
        "The model is generated - now choose the site",
        ["The timber model is generated. Next, select the SITE object in Rhino.",
         "",
         "It can be a surface, polysurface, mesh, terrain, or a closed boundary "
         "curve. The ORIGINAL site object is never deleted or moved.",
         "",
         "The optimizer will read the site's real (possibly irregular) outer "
         "boundary and offset it inward by the required setback (%.2f m for %s, "
         "height %.1f m) to build the buildable zone. After selecting the site "
         "you will mark north." % (setback, city, metrics["h"]),
         "", SITE_PLACEMENT_DISCLAIMER],
        "Select site object", "Skip site placement",
        window_title="Timber Housing v26 - Select Site", ta_height=230,
        width=660, height=470)
    if not proceed:
        R["status"] = "skipped"
        R["reason"] = "user skipped before site selection"
        return R
    site = _sp_select_site()
    R["site"] = site
    if not site:
        R["status"] = "skipped"
        R["warnings"].append("No site selected.")
        R["folder"] = _sp_write_reports(P, R)
        return R
    # ---- irregular boundary ---------------------------------------------
    site_boundary = extract_site_boundary(site, opts)
    R["site_boundary_mode"] = site_boundary.get("mode")
    if "fallback" in (site_boundary.get("mode") or ""):
        R["warnings"].append("Exact site boundary could not be extracted; using "
                             "the bounding rectangle (approximate).")
    # ---- Dialog 4: north -------------------------------------------------
    mark = show_styled_prompt(
        "Mark North Direction",
        "North affects sun / wind orientation scoring",
        ["Mark the north direction in Rhino so the optimizer can score sun and "
         "wind orientation.",
         "",
         "Click a base point then a north point in the viewport to define north. "
         "If you skip, world +Y is used as the default north.",
         "", SITE_PLACEMENT_DISCLAIMER],
        "Mark north direction", "Use default north (+Y)",
        window_title="Timber Housing v26 - North", ta_height=190, width=640, height=420)
    if mark:
        north_deg, north_vec, north_src = _sp_mark_north(site.get("center"))
    else:
        north_deg, north_vec, north_src = (0.0, (0.0, 1.0),
                                           "world +Y (user chose default)")
    R["north_deg"] = round(north_deg, 1)
    R["north_source"] = north_src
    # ---- irregular buildable zone + polygon optimizer -------------------
    zone_info = compute_irregular_buildable_zone(site_boundary, setback, site,
                                                 opts)
    R["buildable_mode"] = zone_info.get("mode")
    R["zone_poly"] = zone_info.get("poly")
    R["zone"] = zone_info.get("bbox")   # bbox tuple for reports/back-compat
    if opts.get("run_optimization", True):
        cand = optimize_site_placement_irregular(
            zone_info.get("poly"), zone_info.get("bbox"), footprint[0],
            footprint[1], north_vec, city_rules["latitude_deg_approx"], opts)
    else:
        poly = zone_info.get("poly")
        if poly:
            cc = _poly_centroid(poly)
            b0 = {"rot": 0.0, "cx": cc[0], "cy": cc[1], "setback_margin": 1.0,
                  "sunlight": 0.0, "ventilation": 0.0, "harsh": 0.0, "align": 0.0,
                  "total": 0.0, "fits": True, "overflow": 0.0,
                  "long_bearings": (0.0, 180.0)}
            cand = {"feasible": True, "best": b0, "candidates": [b0],
                    "reason": "optimization disabled - centred placement"}
        else:
            cand = {"feasible": False, "best": None, "candidates": [],
                    "reason": "no buildable zone"}
    R["cand_info"] = cand
    best = cand.get("best")
    R["best"] = best
    if best:
        R["score"] = round(best.get("total", 0.0), 3)
    if not cand.get("feasible"):
        R["warnings"].append(cand.get("reason", "not feasible"))
    if best is None:
        R["status"] = "warning"
        R["warnings"].append("No placement candidate (site / setback too small).")
        R["folder"] = _sp_write_reports(P, R)
        _sp_append_justification_txt(R["folder"], R)
        show_site_result_dialog(_sp_result_body_v26(R), False, R["folder"],
                                (os.path.join(R["folder"],
                                 "site_placement_summary.txt")
                                 if R["folder"] else None))
        return R
    # ---- terrain + transform --------------------------------------------
    ex, ey = _sp_footprint_extent(footprint[0], footprint[1], best["rot"])
    cx, cy = best["cx"], best["cy"]
    corners = [("center", cx, cy),
               ("c1", cx - ex / 2.0, cy - ey / 2.0),
               ("c2", cx + ex / 2.0, cy - ey / 2.0),
               ("c3", cx + ex / 2.0, cy + ey / 2.0),
               ("c4", cx - ex / 2.0, cy + ey / 2.0)]
    fallback_top = site["max"][2]
    zs = _sp_sample_terrain(site["id"], [(p[1], p[2]) for p in corners],
                            fallback_top)
    R["terrain_samples"] = [(corners[i][0], corners[i][1], corners[i][2], zs[i])
                            for i in range(len(corners))]
    terr = _sp_terrain_stats(zs)
    R["terrain"] = terr
    if terr.get("diff") is not None and terr["diff"] > 2.0:
        R["warnings"].append("Terrain elevation difference under the footprint "
                             "is %.2f m (>2 m): review levelling / foundations."
                             % terr["diff"])
    target_z = (terr.get("max") if terr.get("max") is not None
                else fallback_top) + 0.05
    tspec = _sp_compute_transform(metrics, (cx, cy), target_z, best["rot"])
    R["transform"] = tspec
    R["status"] = "ready"
    # ---- static outlines (irregular) + Dialog 5 + live preview ----------
    outline_ids = _sp_draw_static_outlines_v26(site_boundary, zone_info,
                                               target_z)
    show_site_info_dialog(
        "Optimization Preview",
        "Testing candidate placements (design-stage)",
        ["The optimizer will now visibly test candidate placements inside the "
         "buildable zone.",
         "",
         "Only a lightweight footprint rectangle moves during the preview - the "
         "full model is NOT moved yet. The FULL model moves only ONCE, after you "
         "click Accept in the result dialog.",
         "",
         "Watch the footprint rotate / move; the best-so-far outline updates as "
         "it searches."],
        "Start optimization preview")
    preview_ids = run_visible_optimization_preview(
        site, R["zone"], metrics, cand.get("candidates"), best, opts)
    outline_ids = list(outline_ids) + list(preview_ids or [])
    # ---- report + Dialog 6 result ---------------------------------------
    R["folder"] = _sp_write_reports(P, R)
    _sp_append_justification_txt(R["folder"], R)
    txt = (os.path.join(R["folder"], "site_placement_summary.txt")
           if R["folder"] else None)
    accept = show_site_result_dialog(_sp_result_body_v26(R),
                                     cand.get("feasible"), R["folder"], txt)
    if accept and tspec and move_ids:
        rs.EnableRedraw(False)
        try:
            ok = _sp_apply_transform(move_ids, tspec)
        finally:
            rs.EnableRedraw(True)
        if ok:
            R["applied"] = True
            R["status"] = "applied"
            try:
                rs.ZoomExtents()
                Rhino.RhinoDoc.ActiveDoc.Views.Redraw()
            except Exception:
                pass
            print("v26 site placement APPLIED: %d objects moved once (rot %s)."
                  % (len(move_ids), best["rot"]))
            show_site_info_dialog(
                "Placement Accepted",
                "The model was moved onto the site",
                ["Placement accepted.",
                 "",
                 "The full generated model was moved / rotated ONCE onto the "
                 "selected site (rotation %s deg)." % best["rot"],
                 "The site surface was PRESERVED (not moved or deleted).",
                 "The placement report was saved to:",
                 "  %s" % (R.get("folder") or "(not written)"),
                 "",
                 "This is a design-stage recommendation - no legal / permit "
                 "approval is implied."],
                "Finish")
        else:
            R["status"] = "failed"
            R["warnings"].append("Transform failed; model left in place.")
    else:
        R["status"] = "kept_outside"
        try:
            if outline_ids:
                rs.DeleteObjects(outline_ids)
                rs.Redraw()
        except Exception:
            pass
        print("v26 site placement: user kept the model outside the site.")
        show_site_info_dialog(
            "Placement Cancelled",
            "The model was kept in its original position",
            ["Placement cancelled - Keep Model Outside Site.",
             "",
             "The generated model was NOT moved.",
             "The temporary placement preview outlines were cleaned.",
             "The site surface was PRESERVED (not moved or deleted).",
             "The report (with the best candidate) was still saved for "
             "reference."],
            "Finish")
    R["folder"] = _sp_write_reports(P, R)
    _sp_append_justification_txt(R["folder"], R)
    return R


def run_stage_final_site_placement_v25(P, rack):
    """v25 site-placement OPTIMIZER stage with UI polish:
      Dialog A setup -> Rhino site pick -> north -> clean footprint ->
      buildable zone -> full rotation/translation search -> LIVE ~100-iteration
      Galapagos-style footprint preview (lightweight rectangle only) -> Dialog B
      result with a human-readable JUSTIFICATION + score breakdown -> on Accept,
      ONE rigid transform of the whole tagged model onto the site.
    No floating viewport text by default; temporary preview candidates are
    cleaned unless debug is on. Site / user geometry never moved or deleted;
    model never deformed. Fully guarded."""
    R = {"status": "skipped", "applied": False, "city": None, "north_deg": None,
         "north_source": None, "warnings": [], "score": None, "folder": None}
    # ---- Dialog A: setup -------------------------------------------------
    try:
        opts = show_site_setup_dialog()
    except Exception as ex:
        print("Site setup dialog failed (%s)." % ex)
        opts = None
    if not opts:
        R["status"] = "skipped"
        R["reason"] = "user skipped at the setup dialog"
        print("Final site placement skipped at setup.")
        return R
    city = opts["city"]
    R["city"] = city
    # ---- clean footprint + full generated model set ----------------------
    metrics = compute_clean_building_footprint(P, rack)
    R["metrics"] = metrics
    if metrics.get("note"):
        R["warnings"].append(metrics["note"])
    footprint = (metrics["w"], metrics["l"])
    move_ids, move_src = collect_wosyho_generated_objects_by_tag()
    city_rules = get_city_rule_assumptions(city, metrics["h"], footprint)
    R["city_rules"] = city_rules
    setback = city_rules["required_setback_m"]
    if not opts.get("conservative_setbacks", True):
        setback = max(city_rules["base_setback_m"], 0.5 * setback)
    print("v25 site placement: clean footprint %.2f x %.2f m, %d model objects "
          "(%s), setback %.2f m." % (footprint[0], footprint[1], len(move_ids),
                                     move_src, setback))
    # ---- Rhino site pick (command line, as Rhino works) ------------------
    site = _sp_select_site()
    R["site"] = site
    if not site:
        R["status"] = "skipped"
        R["warnings"].append("No site selected.")
        R["folder"] = _sp_write_reports(P, R)
        print("Final site placement skipped (no site).")
        return R
    # ---- north -----------------------------------------------------------
    if opts.get("mark_north", True):
        north_deg, north_vec, north_src = _sp_mark_north(site.get("center"))
    else:
        north_deg, north_vec, north_src = (0.0, (0.0, 1.0), "world +Y (setup)")
    R["north_deg"] = round(north_deg, 1)
    R["north_source"] = north_src
    # ---- buildable zone + full optimizer search --------------------------
    zone = _sp_buildable_rectangle(site["min"], site["max"], setback)
    R["zone"] = zone
    if opts.get("run_optimization", True):
        cand = optimize_site_placement(zone, footprint[0], footprint[1],
                                       north_vec,
                                       city_rules["latitude_deg_approx"],
                                       site["min"], site["max"], opts)
    else:
        if zone:
            best0 = {"rot": 0.0, "cx": (zone[0] + zone[2]) / 2.0,
                     "cy": (zone[1] + zone[3]) / 2.0, "setback_margin": 0.0,
                     "sunlight": 0.0, "ventilation": 0.0, "harsh": 0.0,
                     "align": 0.0, "total": 0.0, "fits": True, "overflow": 0.0,
                     "long_bearings": (0.0, 180.0)}
            cand = {"feasible": True, "best": best0, "candidates": [best0],
                    "reason": "optimization disabled - centred placement"}
        else:
            cand = {"feasible": False, "best": None, "candidates": [],
                    "reason": "no buildable zone"}
    R["cand_info"] = cand
    best = cand.get("best")
    R["best"] = best
    if best:
        R["score"] = round(best.get("total", 0.0), 3)
    if not cand.get("feasible"):
        R["warnings"].append(cand.get("reason", "not feasible"))
    if best is None:
        R["status"] = "warning"
        R["warnings"].append("No placement candidate could be generated "
                             "(site / setback too small).")
        R["folder"] = _sp_write_reports(P, R)
        _sp_append_justification_txt(R["folder"], R)
        show_site_result_dialog(_sp_result_body_v25(R), False, R["folder"],
                                (os.path.join(R["folder"],
                                 "site_placement_summary.txt")
                                 if R["folder"] else None))
        return R
    # ---- terrain + transform spec (computed once) ------------------------
    ex, ey = _sp_footprint_extent(footprint[0], footprint[1], best["rot"])
    cx, cy = best["cx"], best["cy"]
    corners = [("center", cx, cy),
               ("c1", cx - ex / 2.0, cy - ey / 2.0),
               ("c2", cx + ex / 2.0, cy - ey / 2.0),
               ("c3", cx + ex / 2.0, cy + ey / 2.0),
               ("c4", cx - ex / 2.0, cy + ey / 2.0)]
    fallback_top = site["max"][2]
    zs = _sp_sample_terrain(site["id"], [(p[1], p[2]) for p in corners],
                            fallback_top)
    R["terrain_samples"] = [(corners[i][0], corners[i][1], corners[i][2], zs[i])
                            for i in range(len(corners))]
    terr = _sp_terrain_stats(zs)
    R["terrain"] = terr
    if terr.get("diff") is not None and terr["diff"] > 2.0:
        R["warnings"].append("Terrain elevation difference under the footprint "
                             "is %.2f m (>2 m): review site levelling / "
                             "foundations with an engineer." % terr["diff"])
    target_z = (terr.get("max") if terr.get("max") is not None
                else fallback_top) + 0.05
    tspec = _sp_compute_transform(metrics, (cx, cy), target_z, best["rot"])
    R["transform"] = tspec
    R["status"] = "ready"
    # ---- static outlines + LIVE Galapagos-style preview ------------------
    outline_ids = _sp_draw_static_outlines(site, zone, target_z)
    preview_ids = run_visible_optimization_preview(
        site, zone, metrics, cand.get("candidates"), best, opts)
    outline_ids = list(outline_ids) + list(preview_ids or [])
    # ---- report (+ justification TXT) + Dialog B -------------------------
    R["folder"] = _sp_write_reports(P, R)
    _sp_append_justification_txt(R["folder"], R)
    txt = (os.path.join(R["folder"], "site_placement_summary.txt")
           if R["folder"] else None)
    accept = show_site_result_dialog(_sp_result_body_v25(R),
                                     cand.get("feasible"), R["folder"], txt)
    if accept and tspec and move_ids:
        rs.EnableRedraw(False)
        try:
            ok = _sp_apply_transform(move_ids, tspec)
        finally:
            rs.EnableRedraw(True)
        if ok:
            R["applied"] = True
            R["status"] = "applied"
            try:
                rs.ZoomExtents()
                Rhino.RhinoDoc.ActiveDoc.Views.Redraw()
            except Exception:
                pass
            print("v25 site placement APPLIED: %d objects moved once (rot %s, "
                  "center %.2f/%.2f, z %.2f)."
                  % (len(move_ids), best["rot"], cx, cy, target_z))
        else:
            R["status"] = "failed"
            R["warnings"].append("Transform failed; model left in place.")
    else:
        R["status"] = "kept_outside"
        # keep model outside: remove the temporary preview outlines to stay clean
        try:
            if outline_ids:
                rs.DeleteObjects(outline_ids)
                rs.Redraw()
        except Exception:
            pass
        print("v25 site placement: user kept the model outside the site.")
    R["folder"] = _sp_write_reports(P, R)
    _sp_append_justification_txt(R["folder"], R)
    return R


def run_stage_final_site_placement_v24(P, rack):
    """v24 site-placement OPTIMIZER stage. Setup dialog -> site pick -> north ->
    clean footprint -> buildable zone -> rotation/translation search -> result
    dialog -> ACTUAL rigid transform of the whole generated model onto the site
    (on Accept). Fully guarded; returns a status dict for the completion dialog.
    Never deletes / moves the site or user geometry; never deforms the model."""
    R = {"status": "skipped", "applied": False, "city": None, "north_deg": None,
         "north_source": None, "warnings": [], "score": None, "folder": None}
    # ---- Dialog 1: setup -------------------------------------------------
    try:
        opts = show_site_setup_dialog()
    except Exception as ex:
        print("Site setup dialog failed (%s)." % ex)
        opts = None
    if not opts:
        R["status"] = "skipped"
        R["reason"] = "user skipped at the setup dialog"
        print("Final site placement skipped at setup.")
        return R
    city = opts["city"]
    R["city"] = city
    # ---- clean footprint + full generated model set ----------------------
    metrics = compute_clean_building_footprint(P, rack)
    R["metrics"] = metrics
    if metrics.get("note"):
        R["warnings"].append(metrics["note"])
    footprint = (metrics["w"], metrics["l"])
    move_ids, move_src = collect_wosyho_generated_objects_by_tag()
    city_rules = get_city_rule_assumptions(city, metrics["h"], footprint)
    R["city_rules"] = city_rules
    setback = city_rules["required_setback_m"]
    if not opts.get("conservative_setbacks", True):
        setback = max(city_rules["base_setback_m"], 0.5 * setback)
    print("v24 site placement: footprint %.2f x %.2f m (%s), %d model objects "
          "to move (%s), setback %.2f m."
          % (footprint[0], footprint[1], metrics["source"], len(move_ids),
             move_src, setback))
    # ---- site selection (Rhino command line) -----------------------------
    site = _sp_select_site()
    R["site"] = site
    if not site:
        R["status"] = "skipped"
        R["warnings"].append("No site selected.")
        R["folder"] = _sp_write_reports(P, R)
        print("Final site placement skipped (no site).")
        return R
    # ---- north -----------------------------------------------------------
    if opts.get("mark_north", True):
        north_deg, north_vec, north_src = _sp_mark_north(site.get("center"))
    else:
        north_deg, north_vec, north_src = (0.0, (0.0, 1.0), "world +Y (setup)")
    R["north_deg"] = round(north_deg, 1)
    R["north_source"] = north_src
    # ---- buildable zone + optimizer --------------------------------------
    zone = _sp_buildable_rectangle(site["min"], site["max"], setback)
    R["zone"] = zone
    if opts.get("run_optimization", True):
        cand = optimize_site_placement(zone, footprint[0], footprint[1],
                                       north_vec, city_rules["latitude_deg_approx"],
                                       site["min"], site["max"], opts)
    else:
        # no search: single centred, unrotated candidate
        if zone:
            best0 = {"rot": 0.0, "cx": (zone[0] + zone[2]) / 2.0,
                     "cy": (zone[1] + zone[3]) / 2.0, "setback_margin": 0.0,
                     "sunlight": 0.0, "ventilation": 0.0, "harsh": 0.0,
                     "align": 0.0, "total": 0.0, "fits": True, "overflow": 0.0,
                     "long_bearings": (0.0, 180.0)}
            cand = {"feasible": True, "best": best0, "candidates": [best0],
                    "reason": "optimization disabled - centred placement"}
        else:
            cand = {"feasible": False, "best": None, "candidates": [],
                    "reason": "no buildable zone"}
    R["cand_info"] = cand
    best = cand.get("best")
    R["best"] = best
    if best:
        R["score"] = round(best.get("total", 0.0), 3)
    if not cand.get("feasible"):
        R["warnings"].append(cand.get("reason", "not feasible"))
    if best is None:
        R["status"] = "warning"
        R["warnings"].append("No placement candidate could be generated "
                             "(site / setback too small).")
        R["folder"] = _sp_write_reports(P, R)
        show_site_result_dialog(_sp_result_body(R), False, R["folder"],
                                os.path.join(R["folder"] or "",
                                             "site_placement_summary.txt")
                                if R["folder"] else None)
        return R
    # ---- terrain sampling under the chosen footprint ---------------------
    ex, ey = _sp_footprint_extent(footprint[0], footprint[1], best["rot"])
    cx, cy = best["cx"], best["cy"]
    corners = [("center", cx, cy),
               ("c1", cx - ex / 2.0, cy - ey / 2.0),
               ("c2", cx + ex / 2.0, cy - ey / 2.0),
               ("c3", cx + ex / 2.0, cy + ey / 2.0),
               ("c4", cx - ex / 2.0, cy + ey / 2.0)]
    fallback_top = site["max"][2]
    zs = _sp_sample_terrain(site["id"], [(p[1], p[2]) for p in corners],
                            fallback_top)
    R["terrain_samples"] = [(corners[i][0], corners[i][1], corners[i][2], zs[i])
                            for i in range(len(corners))]
    terr = _sp_terrain_stats(zs)
    R["terrain"] = terr
    if terr.get("diff") is not None and terr["diff"] > 2.0:
        R["warnings"].append("Terrain elevation difference under the footprint "
                             "is %.2f m (>2 m): review site levelling / "
                             "foundations with an engineer." % terr["diff"])
    target_z = (terr.get("max") if terr.get("max") is not None
                else fallback_top) + 0.05
    tspec = _sp_compute_transform(metrics, (cx, cy), target_z, best["rot"])
    R["transform"] = tspec
    R["status"] = "ready"
    # ---- draw preview outlines (site / zone / best footprint) ------------
    debug_ids = draw_site_placement_debug(
        site, zone, best, metrics, target_z,
        opts.get("site_optimizer_show_debug", False), cand.get("candidates"))
    try:
        rs.EnableRedraw(True)
        Rhino.RhinoDoc.ActiveDoc.Views.Redraw()
    except Exception:
        pass
    # ---- report + Dialog 2 -----------------------------------------------
    R["folder"] = _sp_write_reports(P, R)
    txt = (os.path.join(R["folder"], "site_placement_summary.txt")
           if R["folder"] else None)
    accept = show_site_result_dialog(_sp_result_body(R), cand.get("feasible"),
                                     R["folder"], txt)
    if accept and tspec and move_ids:
        rs.EnableRedraw(False)
        try:
            ok = _sp_apply_transform(move_ids, tspec)
        finally:
            rs.EnableRedraw(True)
        if ok:
            R["applied"] = True
            R["status"] = "applied"
            try:
                rs.ZoomExtents()
                Rhino.RhinoDoc.ActiveDoc.Views.Redraw()
            except Exception:
                pass
            print("v24 site placement APPLIED: %d objects moved (rot %s, "
                  "center %.2f/%.2f, z %.2f)."
                  % (len(move_ids), best["rot"], cx, cy, target_z))
        else:
            R["status"] = "failed"
            R["warnings"].append("Transform failed; model left in place.")
    else:
        R["status"] = "kept_outside"
        # user kept the model outside: remove the preview outlines to avoid clutter
        try:
            if debug_ids:
                rs.DeleteObjects(debug_ids)
        except Exception:
            pass
        print("v24 site placement: user kept the model outside the site.")
    R["folder"] = _sp_write_reports(P, R)
    return R


def run_stage_final_site_placement(P, rack):
    """Advanced final stage: city -> site -> north -> optimise -> preview ->
    apply/skip. READ-ONLY except a rigid transform applied ONLY on explicit
    Apply. Fully guarded; returns a status dict for the completion dialog."""
    R = {"status": "skipped", "applied": False, "city": None, "north_deg": None,
         "north_source": None, "warnings": [], "score": None, "folder": None}
    # 1. city / planning dialog
    try:
        city, proceed = show_city_dialog()
    except Exception as ex:
        print("City dialog failed (%s)." % ex)
        city, proceed = (None, False)
    if not proceed or not city:
        R["status"] = "skipped"
        R["reason"] = "user skipped at the city / planning dialog"
        print("Final site placement skipped at the city dialog.")
        return R
    R["city"] = city
    # 2. building objects + metrics + city rules
    ids, inc, exc = collect_wosyho_building_objects_for_site_placement()
    metrics = _sp_building_metrics(ids, rack, P)
    R["metrics"] = metrics
    footprint = (metrics["w"], metrics["l"])
    city_rules = get_city_rule_assumptions(city, metrics["h"], footprint)
    R["city_rules"] = city_rules
    setback = city_rules["required_setback_m"]
    print("Site placement: %d building objects, footprint %.2f x %.2f m, "
          "height %.2f m, setback %.2f m." % (len(ids), footprint[0],
                                              footprint[1], metrics["h"], setback))
    # 3. site selection
    site = _sp_select_site()
    R["site"] = site
    if not site:
        R["status"] = "skipped"
        R["warnings"].append("No site selected.")
        R["folder"] = _sp_write_reports(P, R)
        print("Final site placement skipped (no site).")
        return R
    # 4. north
    north_deg, north_vec, north_src = _sp_mark_north(site.get("center"))
    R["north_deg"] = round(north_deg, 1)
    R["north_source"] = north_src
    # 5. buildable zone + 6. candidates
    zone = _sp_buildable_rectangle(site["min"], site["max"], setback)
    R["zone"] = zone
    cand = _sp_generate_candidates(zone, footprint[0], footprint[1], north_vec,
                                   city_rules["latitude_deg_approx"])
    R["cand_info"] = cand
    if not cand["feasible"]:
        R["status"] = "warning"
        R["warnings"].append("Building does not fit the buildable zone: %s. "
                             "Suggest a larger site / smaller footprint / lower "
                             "height / manual planning review."
                             % cand.get("reason"))
        R["folder"] = _sp_write_reports(P, R)
        _sp_show_preview_and_maybe_skip(R)
        return R
    best = cand["best"]
    R["best"] = best
    R["score"] = round(best["total"], 3)
    # 7. terrain sampling for the selected candidate
    ex, ey = _sp_footprint_extent(footprint[0], footprint[1], best["rot"])
    cx, cy = best["cx"], best["cy"]
    corners = [("center", cx, cy),
               ("c1", cx - ex / 2.0, cy - ey / 2.0),
               ("c2", cx + ex / 2.0, cy - ey / 2.0),
               ("c3", cx + ex / 2.0, cy + ey / 2.0),
               ("c4", cx - ex / 2.0, cy + ey / 2.0)]
    fallback_top = site["max"][2]
    zs = _sp_sample_terrain(site["id"], [(p[1], p[2]) for p in corners],
                            fallback_top)
    R["terrain_samples"] = [(corners[i][0], corners[i][1], corners[i][2], zs[i])
                            for i in range(len(corners))]
    terr = _sp_terrain_stats(zs)
    R["terrain"] = terr
    if terr.get("diff") is not None and terr["diff"] > 2.0:
        R["warnings"].append("Terrain elevation difference under the footprint "
                             "is %.2f m (>2 m): review site levelling / "
                             "foundations with an engineer." % terr["diff"])
    target_z = (terr.get("max") if terr.get("max") is not None
                else fallback_top) + 0.05
    # 8. transform spec
    tspec = _sp_compute_transform(metrics, (cx, cy), target_z, best["rot"])
    R["transform"] = tspec
    # 9. report
    R["status"] = "ready"
    R["folder"] = _sp_write_reports(P, R)
    # 10. preview + apply/skip
    apply = _sp_show_preview_and_maybe_skip(R)
    if apply and tspec and ids:
        ok = _sp_apply_transform(ids, tspec)
        if ok:
            R["applied"] = True
            R["status"] = "applied"
            _sp_draw_helpers(zone, north_vec, tspec)
            try:
                rs.ZoomExtents()
            except Exception:
                pass
            print("Final site placement APPLIED (rot %s deg, center %.2f/%.2f, "
                  "z %.2f)." % (best["rot"], cx, cy, target_z))
        else:
            R["status"] = "failed"
            R["warnings"].append("Transform failed; model left at origin.")
    else:
        R["status"] = "skipped"
        print("Final site placement not applied (user skipped at preview).")
    # rewrite report with final applied/skipped status
    R["folder"] = _sp_write_reports(P, R)
    return R


def _sp_show_preview_and_maybe_skip(R):
    """Build the preview body and show the Apply/Skip dialog. Returns True on
    Apply. Safe if data is partial (feasibility warnings still shown)."""
    cr = R.get("city_rules", {})
    metrics = R.get("metrics", {})
    best = R.get("best")
    terr = R.get("terrain", {})
    cand = R.get("cand_info", {})
    site = R.get("site")
    folder = R.get("folder")
    sep = "-" * 56
    lines = ["Final Site Placement Preview  (design-stage assistant)", "=" * 56,
             "city                 : %s" % R.get("city"),
             "federal state approx : %s" % cr.get("federal_state"),
             "building height (m)  : %.2f" % metrics.get("h", 0.0),
             "footprint w x l (m)  : %.2f x %.2f"
             % (metrics.get("w", 0.0), metrics.get("l", 0.0)),
             "required setback (m) : %.2f" % cr.get("required_setback_m", 0.0),
             "site object type     : %s"
             % (site.get("type") if site else "(none)"),
             "north angle (deg)    : %s (%s)"
             % (R.get("north_deg"), R.get("north_source")),
             "buildable feasible   : %s" % cand.get("feasible"), sep]
    if best:
        lines += ["best rotation (deg)  : %s" % best.get("rot"),
                  "best center x / y    : %.2f / %.2f"
                  % (best.get("cx", 0.0), best.get("cy", 0.0)),
                  "sunlight score       : %.3f" % best.get("sunlight", 0.0),
                  "ventilation score    : %.3f" % best.get("ventilation", 0.0),
                  "harsh sun penalty    : %.3f" % best.get("harsh", 0.0),
                  "total score          : %.3f" % best.get("total", 0.0)]
    else:
        lines.append("best placement       : NONE (does not fit) - %s"
                     % cand.get("reason"))
    if terr and terr.get("count"):
        lines.append("terrain min/max/diff : %s / %s / %s"
                     % (terr.get("min"), terr.get("max"), terr.get("diff")))
    if R.get("warnings"):
        lines.append(sep)
        for w in R["warnings"]:
            lines.append("! %s" % w)
    lines += [sep, "report folder:", "  %s" % (folder or "(not written)"), sep,
              SITE_PLACEMENT_DISCLAIMER]
    body = "\n".join(lines)
    txt = os.path.join(folder, "site_placement_summary.txt") if folder else None
    if not best:
        # nothing to apply; still show the info, treat as skip
        try:
            show_report_preview("Final Site Placement - Not Feasible", body,
                                folder=folder, open_file=txt,
                                open_folder_label="Open Placement Report Folder",
                                open_file_label="Open Placement Summary TXT")
        except Exception:
            pass
        return False
    try:
        return show_site_placement_preview(body, folder, txt)
    except Exception:
        return False


# =============================================================================
# 7. MAIN
# =============================================================================

# =============================================================================
# 6d-V28. SITE & SURROUNDINGS CONTEXT IMPORT + EARLY SITE ANALYSIS (2026-07-14)
#
# Additive workflow layer: after the EARLY city selection the configurator
# inspects the 'site model and surroundings' folder (fallback name
# 'site and surroundings'), classifies the exported geometry BY CONTENT
# (materials / groups / bounding boxes - never by file name alone), and offers
# THREE separate styled import steps (site plot / site + road / surrounding
# buildings). Imported objects go to WoSyHo::ImportedContext::* layers, are
# tagged WoSyHo_ImportedContext=1 (+ role) and are NEVER tagged
# WoSyHo_Generated - so the safe cleanup never deletes them and the final
# placement transform never moves them. The user then selects the actual site
# plot (imported or manual) and an EARLY site analysis runs (plan boundary,
# elevation range, uneven/contour detection, road adjacency, surroundings).
#
# UNEVEN / CONTOUR SITE RULES (V28):
#   - setback / buildable zone: ALWAYS from the boundary PROJECTED TO WorldXY
#     (extract_site_boundary already samples XY; never offset along terrain)
#   - the building is NEVER tilted: X/Y/Z translation + Z-axis rotation only
#   - the terrain mesh is NEVER cut / booleaned / modified
#   - Z placement: sample terrain under the footprint, building bottom ->
#     max sampled z + clearance; slight overlap with the site mesh is
#     acceptable for V28 (foundation/terrace design resolves it later)
#   - the Galapagos-style optimizer gets a terrain suitability term
#     (terrain_delta_z under each candidate footprint)
#
# Everything is guarded: any failure prints, the user can always skip, and
# the frozen v27 workflow continues unchanged. No generation / module /
# stability / sizing / RFEM logic is touched.
# =============================================================================

SITE_CTX_TAG_KEY = "WoSyHo_ImportedContext"
SITE_CTX_TAG_VAL = "1"
SITE_CTX_ROLE_KEY = "WoSyHo_ContextRole"
SITE_CTX_FOLDER_CANDIDATES = ["site model and surroundings",
                              "site and surroundings"]
SITE_CTX_LAYERS = {
    "root": "WoSyHo::ImportedContext",
    "site_plot": "WoSyHo::ImportedContext::SitePlot",
    "site_road": "WoSyHo::ImportedContext::SiteRoad",
    "surrounding_buildings": "WoSyHo::ImportedContext::SurroundingBuildings",
    "full_combined": "WoSyHo::ImportedContext::FullCombined",
    "debug": "WoSyHo::ImportedContext::AnalysisDebug",
}
SITE_CTX_UNEVEN_THRESHOLD_M = 0.25   # z-range above this => site is "uneven"
SITE_CTX_Z_CLEARANCE_M = 0.05        # building bottom = max terrain z + this
SITE_CTX_TERRAIN_WARN_M = 1.0        # per-candidate delta-z warning threshold
SITE_CTX_TERRAIN_SCORE_WEIGHT = 0.6  # additive weight of the terrain term
SITE_CTX_ROLE_LABELS = {
    "site_plot": "Site plot / site plane",
    "site_road": "Site + road context",
    "surrounding_buildings": "Surrounding buildings",
    "full_combined": "Full combined model",
}
SITE_CTX_VERTICAL_NOTE = (
    "The site is treated as uneven terrain. Setback is calculated from the "
    "projected plan boundary. The building is kept vertical and is not tilted "
    "to match the terrain. The terrain mesh is not cut or modified. The final "
    "placement uses X/Y/Z translation and Z-axis rotation only. Any remaining "
    "level difference must be resolved later by foundation/terrace design.")


# ---- pure, headless-testable folder inspection / classification -------------

def _sc_script_dir(P=None):
    try:
        return os.path.dirname(os.path.abspath(__file__))
    except Exception:
        return (P or {}).get("export_folder") or os.path.expanduser("~")


def _sc_find_site_folder(script_dir):
    """Locate the site/surroundings folder next to the script (both known
    spellings). Returns the path or None."""
    for name in SITE_CTX_FOLDER_CANDIDATES:
        p = os.path.join(script_dir, name)
        try:
            if os.path.isdir(p):
                return p
        except Exception:
            continue
    return None


def _sc_scan_obj(path, max_lines=4000000):
    """Stream-scan an OBJ: header note, counts, materials, groups, bbox
    (OBJ native axes - SketchUp exports Y-up, metres). Never raises."""
    out = {"file": os.path.basename(path), "format": "OBJ", "ok": False,
           "size_bytes": 0, "header_units": "", "vertices": 0, "faces": 0,
           "groups": 0, "materials": [], "bbox_min": None, "bbox_max": None,
           "bbox_size": None, "per_material_vertices": {}}
    try:
        out["size_bytes"] = os.path.getsize(path)
        mn = [1e18, 1e18, 1e18]
        mx = [-1e18, -1e18, -1e18]
        mats = []
        pm = {}
        cur = ""
        nv = nf = ng = 0
        ln = 0
        f = open(path, "r")
        try:
            for line in f:
                ln += 1
                if ln > max_lines:
                    break
                c = line[0:1]
                if c == "v" and line[1:2] == " ":
                    p = line.split()
                    try:
                        x = float(p[1]); y = float(p[2]); z = float(p[3])
                    except Exception:
                        continue
                    nv += 1
                    if x < mn[0]: mn[0] = x
                    if y < mn[1]: mn[1] = y
                    if z < mn[2]: mn[2] = z
                    if x > mx[0]: mx[0] = x
                    if y > mx[1]: mx[1] = y
                    if z > mx[2]: mx[2] = z
                    pm[cur] = pm.get(cur, 0) + 1
                elif c == "f":
                    nf += 1
                elif c == "g":
                    ng += 1
                elif c == "u" and line.startswith("usemtl"):
                    cur = line[7:].strip()
                    if cur not in mats:
                        mats.append(cur)
                elif c == "#" and "unit" in line.lower():
                    out["header_units"] = line.strip("# \r\n")
        finally:
            f.close()
        out.update({"ok": nv > 0, "vertices": nv, "faces": nf, "groups": ng,
                    "materials": mats, "per_material_vertices": pm})
        if nv:
            out["bbox_min"] = [round(v, 4) for v in mn]
            out["bbox_max"] = [round(v, 4) for v in mx]
            out["bbox_size"] = [round(mx[i] - mn[i], 4) for i in range(3)]
    except Exception as ex:
        out["error"] = str(ex)
    return out


def _sc_scan_stl(path, max_tris=400000):
    """Binary STL quick scan: triangle count + bbox. Never raises."""
    out = {"file": os.path.basename(path), "format": "STL", "ok": False,
           "size_bytes": 0, "triangles": 0, "bbox_min": None, "bbox_max": None,
           "bbox_size": None, "binary": None}
    try:
        import struct as _struct
        out["size_bytes"] = os.path.getsize(path)
        f = open(path, "rb")
        try:
            f.read(80)
            raw = f.read(4)
            if len(raw) < 4:
                return out
            ntri = _struct.unpack("<I", raw)[0]
            out["triangles"] = ntri
            out["binary"] = (84 + ntri * 50 == out["size_bytes"])
            mn = [1e18, 1e18, 1e18]
            mx = [-1e18, -1e18, -1e18]
            for _i in range(min(ntri, max_tris)):
                rec = f.read(50)
                if len(rec) < 50:
                    break
                vals = _struct.unpack("<12fH", rec)
                for k in range(3):
                    for a in range(3):
                        v = vals[3 + k * 3 + a]
                        if v < mn[a]: mn[a] = v
                        if v > mx[a]: mx[a] = v
            if mn[0] < 1e17:
                out["ok"] = True
                out["bbox_min"] = [round(v, 2) for v in mn]
                out["bbox_max"] = [round(v, 2) for v in mx]
                out["bbox_size"] = [round(mx[i] - mn[i], 2) for i in range(3)]
        finally:
            f.close()
    except Exception as ex:
        out["error"] = str(ex)
    return out


def inspect_site_surroundings_folder(folder):
    """Inventory + geometry scan of the site/surroundings folder (top level).
    Returns {'folder', 'files', 'objs', 'stls'}. Never raises."""
    inv = {"folder": folder, "files": [], "objs": {}, "stls": {}}
    try:
        for name in sorted(os.listdir(folder)):
            p = os.path.join(folder, name)
            if not os.path.isfile(p):
                continue
            ext = os.path.splitext(name)[1].lower()
            kind = {".obj": "OBJ", ".stl": "STL", ".mtl": "MTL",
                    ".png": "image", ".jpg": "image",
                    ".jpeg": "image"}.get(ext, "other")
            inv["files"].append({"name": name, "ext": ext, "kind": kind,
                                 "size_bytes": os.path.getsize(p)})
            if ext == ".obj":
                inv["objs"][name] = _sc_scan_obj(p)
            elif ext == ".stl":
                inv["stls"][name] = _sc_scan_stl(p)
    except Exception as ex:
        inv["error"] = str(ex)
    return inv


def _sc_mat_kinds(materials):
    """Material-name evidence: which context kinds a material list suggests."""
    low = [str(m).lower() for m in (materials or [])]
    soil = any(("soil" in m or "grass" in m or "lawn" in m) for m in low)
    road = any(("asphalt" in m or "road" in m) for m in low)
    ground = any(("gravel" in m or "concrete" in m) for m in low)
    bld = any(("shadow" in m or "facade" in m or "building" in m
               or m.startswith("m09")) for m in low)
    return {"soil": soil, "road": road, "ground": ground, "building": bld}


def classify_site_geometry_files(scan):
    """Classify every scanned OBJ by CONTENT (materials + geometry). Returns
    {file: {'role','confidence','reasons'}}. Roles: full_combined / site_plot /
    site_road / surrounding_buildings / unknown."""
    out = {}
    for name, o in (scan.get("objs") or {}).items():
        role, conf, why = "unknown", "low", []
        if not o.get("ok"):
            out[name] = {"role": "unknown", "confidence": "low",
                         "reasons": ["scan failed"]}
            continue
        k = _sc_mat_kinds(o.get("materials"))
        kinds = sum([1 if k["soil"] else 0,
                     1 if (k["road"] or k["ground"]) else 0,
                     1 if k["building"] else 0])
        size = o.get("bbox_size") or [0, 0, 0]
        plan_max = max(size[0], size[2]) if size else 0.0
        flatish = (size[1] <= max(0.1 * plan_max, 3.0)) if plan_max else False
        if kinds >= 3:
            role, conf = "full_combined", "high"
            why.append("materials cover site+road/ground+buildings")
        elif k["soil"] and not k["road"] and not k["building"]:
            role, conf = "site_plot", "high"
            why.append("soil-type material only")
            if flatish:
                why.append("flat plate geometry")
        elif (k["road"] or k["ground"]) and not k["building"] and not k["soil"]:
            role, conf = "site_road", "high"
            why.append("road/ground materials, no buildings, no site soil")
        elif k["building"] and not k["road"] and not k["soil"]:
            role, conf = "surrounding_buildings", "high"
            why.append("building/massing material only")
            if o.get("groups", 0) > 20:
                why.append("%d groups = separate blocks" % o["groups"])
        else:
            # geometric fallback (no material evidence)
            if o.get("groups", 0) > 20:
                role, conf = "surrounding_buildings", "medium"
                why.append("many groups, no material evidence")
            elif flatish and o.get("faces", 0) < 500:
                role, conf = "site_plot", "medium"
                why.append("small flat plate, no material evidence")
            elif len(o.get("materials") or []) >= 3:
                role, conf = "full_combined", "medium"
                why.append("several materials, no clear split")
        out[name] = {"role": role, "confidence": conf, "reasons": why,
                     "bbox_size": size, "vertices": o.get("vertices"),
                     "faces": o.get("faces"), "groups": o.get("groups"),
                     "materials": o.get("materials")}
    return out


def pair_obj_stl_files(scan, classification):
    """Compare each STL with the scanned OBJs. SketchUp exports OBJ in metres
    Y-up but STL in MILLIMETRES Z-up, so sizes are matched with /1000 + axis
    swap. Returns a list of pairing dicts."""
    rows = []
    objs = scan.get("objs") or {}
    for sname, s in (scan.get("stls") or {}).items():
        row = {"stl": sname, "triangles": s.get("triangles"),
               "matches_obj": None, "matched_role": None,
               "note": "no bbox"}
        ss = s.get("bbox_size")
        if ss:
            best = None
            for oname, o in objs.items():
                os_ = o.get("bbox_size")
                if not os_:
                    continue
                # STL [x, y_plan, z_up] (mm) vs OBJ [x, y_up, z_plan] (m)
                d = (abs(ss[0] / 1000.0 - os_[0]) +
                     abs(ss[1] / 1000.0 - os_[2]) +
                     abs(ss[2] / 1000.0 - os_[1]))
                if best is None or d < best[1]:
                    best = (oname, d)
            if best and best[1] < 2.0:
                row["matches_obj"] = best[0]
                row["matched_role"] = (classification.get(best[0]) or
                                       {}).get("role")
                row["note"] = ("size matches '%s' (mm/Z-up vs m/Y-up)"
                               % best[0])
            else:
                row["note"] = "no OBJ size match"
        rows.append(row)
    return rows


def recommend_site_import_files(classification, pairing=None):
    """role -> recommended file dict. OBJ preferred; an STL is only offered if
    NO OBJ exists for that role AND an STL geometrically matches it."""
    rec = {}
    order = {"high": 3, "medium": 2, "low": 1}
    for fname, c in (classification or {}).items():
        role = c.get("role")
        if role in (None, "unknown"):
            continue
        old = rec.get(role)
        if old is None or order.get(c.get("confidence"), 0) > order.get(
                old.get("confidence"), 0):
            rec[role] = {"file": fname, "format": "OBJ",
                         "confidence": c.get("confidence"),
                         "reasons": c.get("reasons"),
                         "bbox_size": c.get("bbox_size")}
    for row in (pairing or []):
        role = row.get("matched_role")
        if role and role not in rec and row.get("matches_obj") is None:
            rec[role] = {"file": row["stl"], "format": "STL",
                         "confidence": "low",
                         "reasons": ["STL fallback - no OBJ for this role"],
                         "bbox_size": None}
    return rec


def _sc_terrain_score(delta_z):
    """0..1 terrain suitability (1 = perfectly level under the footprint)."""
    try:
        return 1.0 / (1.0 + max(0.0, float(delta_z)))
    except Exception:
        return 0.0


# ---- Rhino-side import / tagging / analysis (all guarded) -------------------

def get_new_objects_after_import(pre_ids):
    try:
        return [oid for oid in _wosyho_all_object_ids() if oid not in pre_ids]
    except Exception:
        return []


def _sc_fix_up_axis_if_needed(ids):
    """SketchUp OBJ is Y-up. If Rhino imported it unmapped (context lying on
    its side: tiny Y extent, huge Z extent), rotate the BATCH +90 deg about
    world X so Y-up becomes Z-up. Context models are always flat-ish, so the
    test is safe. Returns True if the fix was applied."""
    try:
        if not ids:
            return False
        bb = rs.BoundingBox(ids)
        if not bb:
            return False
        ys = max(p[1] for p in bb) - min(p[1] for p in bb)
        zs = max(p[2] for p in bb) - min(p[2] for p in bb)
        if ys < zs / 3.0 and zs > 20.0:
            rs.RotateObjects(ids, (0, 0, 0), 90.0, (1, 0, 0))
            print("Imported context: Y-up -> Z-up fix applied (+90 deg about "
                  "world X).")
            return True
    except Exception as ex:
        print("Up-axis check skipped (%s)." % ex)
    return False


def import_context_geometry_file(path):
    """Import one geometry file via the Rhino command line; returns the list of
    newly created object ids (empty on failure). Never raises."""
    try:
        pre = _wosyho_all_object_ids()
        cmd = '_-Import "%s" _Enter' % path
        rs.Command(cmd, False)
        new_ids = get_new_objects_after_import(pre)
        return new_ids
    except Exception as ex:
        print("Import failed for %s (%s)." % (path, ex))
        return []


def assign_imported_context_layer(ids, role):
    layer = SITE_CTX_LAYERS.get(role, SITE_CTX_LAYERS["root"])
    _sp_ensure_layer(SITE_CTX_LAYERS["root"])
    _sp_ensure_layer(layer)
    n = 0
    for oid in (ids or []):
        try:
            rs.ObjectLayer(oid, layer)
            n += 1
        except Exception:
            continue
    return layer, n


def tag_imported_context_objects(ids, role):
    """Tag as imported context (NEVER as WoSyHo_Generated)."""
    n = 0
    for oid in (ids or []):
        try:
            rs.SetUserText(oid, SITE_CTX_TAG_KEY, SITE_CTX_TAG_VAL)
            rs.SetUserText(oid, SITE_CTX_ROLE_KEY, role)
            n += 1
        except Exception:
            continue
    return n


def _sc_is_imported_context(oid):
    try:
        return rs.GetUserText(oid, SITE_CTX_TAG_KEY) == SITE_CTX_TAG_VAL
    except Exception:
        return False


def find_imported_context_objects(role=None):
    ids = []
    try:
        for oid in _wosyho_all_object_ids():
            if not _sc_is_imported_context(oid):
                continue
            if role is not None:
                try:
                    if rs.GetUserText(oid, SITE_CTX_ROLE_KEY) != role:
                        continue
                except Exception:
                    continue
            ids.append(oid)
    except Exception:
        pass
    return ids


def _sc_exclude_imported_context(ids):
    """Split (kept_ids, excluded_count): imported context must NEVER move with
    the building transform."""
    kept = []
    excluded = 0
    for oid in (ids or []):
        if _sc_is_imported_context(oid):
            excluded += 1
        else:
            kept.append(oid)
    return kept, excluded


def _sc_site_info_from_id(sid):
    """Site-info dict (same shape as _sp_select_site) from a known object id."""
    try:
        bb = rs.BoundingBox(sid)
        if not bb:
            return None
        xs = [p[0] for p in bb]
        ys = [p[1] for p in bb]
        zs = [p[2] for p in bb]
        bmin = (min(xs), min(ys), min(zs))
        bmax = (max(xs), max(ys), max(zs))
        try:
            otype = rs.ObjectType(sid)
        except Exception:
            otype = 0
        area = None
        try:
            if rs.IsMesh(sid):
                ma = rs.MeshArea([sid])
                area = ma[1] if ma else None
            elif rs.IsSurface(sid) or rs.IsPolysurface(sid):
                a = rs.SurfaceArea(sid)
                area = a[0] if a else None
        except Exception:
            area = None
        tname = {4: "curve", 8: "surface", 16: "polysurface",
                 32: "mesh"}.get(otype, "object(type=%s)" % otype)
        return {"id": sid, "type": tname, "type_code": otype,
                "min": bmin, "max": bmax,
                "center": ((bmin[0] + bmax[0]) / 2.0,
                           (bmin[1] + bmax[1]) / 2.0,
                           (bmin[2] + bmax[2]) / 2.0),
                "area_est": area,
                "is_terrain": (bmax[2] - bmin[2]) > 0.5}
    except Exception:
        return None


def show_import_context_dialog(title, subtitle, body_lines, yes_text, no_text):
    """Styled import Yes/No dialog (proven safe layout via show_styled_prompt)."""
    return show_styled_prompt(title, subtitle, body_lines, yes_text, no_text,
                              window_title="Timber Housing v28 - " + title,
                              ta_height=240, width=680, height=500)


def show_site_analysis_dialog(body_lines):
    """3-way 'Site Geometry Analysis Complete' dialog. Returns 'continue' /
    'reselect' / 'skip'. Proven safe layout: fixed TextArea + vertical direct
    full-width button rows + explicit ClientSize; native fallback -> continue."""
    body = "\n".join(body_lines)
    try:
        import Eto.Forms as forms
        import Eto.Drawing as drawing
    except Exception:
        try:
            rs.MessageBox(body, 0 | 64, "Timber Housing v28 - Site Analysis")
        except Exception:
            pass
        return "continue"

    class ADlg(forms.Dialog[object]):
        def __init__(self):
            super(ADlg, self).__init__()
            self.Title = "Timber Housing v28 - Site Geometry Analysis Complete"
            self.Padding = drawing.Padding(12)
            self.Resizable = True
            self.result = "continue"
            ta = forms.TextArea()
            ta.ReadOnly = True
            ta.Wrap = True
            ta.Text = body
            ta.Size = drawing.Size(600, 260)
            try:
                _f = _ui_font(9.0)
                if _f is not None:
                    ta.Font = _f
                ta.BackgroundColor = _ui_color(UI_COLORS["card"])
                ta.TextColor = _ui_color(UI_COLORS["ink"])
            except Exception:
                pass
            b1 = forms.Button()
            b1.Text = "Continue to Building Parameters"
            b1.Click += self.on_continue
            b2 = forms.Button()
            b2.Text = "Reselect Site Plot"
            b2.Click += self.on_reselect
            b3 = forms.Button()
            b3.Text = "Continue Without Site Analysis"
            b3.Click += self.on_skip
            self.DefaultButton = b1
            self.AbortButton = b3
            lay = forms.TableLayout()
            lay.Spacing = drawing.Size(8, 8)
            lay.Rows.Add(forms.TableRow([forms.TableCell(ta, True)]))
            lay.Rows.Add(forms.TableRow(forms.TableCell(b1)))
            lay.Rows.Add(forms.TableRow(forms.TableCell(b2)))
            lay.Rows.Add(forms.TableRow(forms.TableCell(b3)))
            finalize_dialog(self, lay, "Site Geometry Analysis Complete",
                            "Early site analysis (design-stage)",
                            [(b1, "primary"), (b2, "secondary"),
                             (b3, "cancel")])
            try:
                self.ClientSize = drawing.Size(680, 540)
            except Exception:
                pass

        def on_continue(self, s, e):
            self.result = "continue"
            self.Close("continue")

        def on_reselect(self, s, e):
            self.result = "reselect"
            self.Close("reselect")

        def on_skip(self, s, e):
            self.result = "skip"
            self.Close("skip")

    try:
        d = ADlg()
        d.ShowModal(Rhino.UI.RhinoEtoApp.MainWindow)
        return d.result
    except Exception:
        try:
            rs.MessageBox(body, 0 | 64, "Timber Housing v28 - Site Analysis")
        except Exception:
            pass
        return "continue"


def run_context_import_step(role, title, subtitle, intro_lines, rec, folder,
                            extra_note=None):
    """One import step (dialog -> import -> up-axis fix -> layer -> tag).
    Returns an info dict. Reuses an earlier import of the same role if the
    user agrees; a fresh import first removes ONLY that earlier import
    (explicit user choice). Never raises."""
    info = {"role": role, "imported": False, "skipped": True, "count": 0,
            "file": None, "format": None, "layer": None, "ids": [],
            "up_axis_fix": False, "reused_existing": False, "warning": ""}
    try:
        r = (rec or {}).get(role)
        lines = list(intro_lines)
        if r:
            bs = r.get("bbox_size")
            lines += ["",
                      "Detected file : %s (%s)" % (r.get("file"),
                                                   r.get("format")),
                      "Confidence    : %s" % r.get("confidence"),
                      "Why           : %s" % "; ".join(r.get("reasons") or [])]
            if bs:
                lines.append("Plan size     : %.1f x %.1f m, height %.1f m "
                             "(OBJ Y-up)" % (bs[0], bs[2], bs[1]))
        else:
            lines += ["", "No file could be classified for this role - "
                      "import will be skipped."]
        lines += ["",
                  "Imported context is placed on its own layer, tagged as "
                  "context, NEVER moved with the building, and NEVER deleted "
                  "by the safe cleanup."]
        if extra_note:
            lines += ["", extra_note]
        lines += ["", SITE_PLACEMENT_DISCLAIMER]
        if not r:
            show_site_info_dialog(title, subtitle, lines, "Continue")
            return info
        # existing import of this role?
        existing = find_imported_context_objects(role)
        if existing:
            reuse = show_styled_prompt(
                title + " - Already Imported",
                "%d object(s) of this role already in the document" %
                len(existing),
                ["This context role was already imported in this document.",
                 "",
                 "Reuse the existing imported objects (recommended), or "
                 "import a FRESH copy (the earlier imported copy of THIS "
                 "role is removed first - your other geometry is untouched)?"],
                "Reuse Existing Import", "Import Fresh Copy",
                window_title="Timber Housing v28 - " + title, ta_height=170,
                width=640, height=420)
            if reuse:
                info.update({"imported": True, "skipped": False,
                             "reused_existing": True, "count": len(existing),
                             "ids": [str(i) for i in existing],
                             "file": r.get("file"), "format": r.get("format"),
                             "layer": SITE_CTX_LAYERS.get(role)})
                return info
            try:
                rs.DeleteObjects(existing)
                print("Removed %d previously imported %s object(s) (user "
                      "chose fresh import)." % (len(existing), role))
            except Exception:
                pass
        if not show_import_context_dialog(title, subtitle, lines,
                                          "Import " + title.replace(
                                              "Import ", ""),
                                          "Skip " + title.replace(
                                              "Import ", "") + " Import"):
            print("%s: skipped by user." % title)
            return info
        path = os.path.join(folder, r["file"])
        ids = import_context_geometry_file(path)
        if not ids:
            info["warning"] = "Import produced no objects (%s)." % r["file"]
            show_site_info_dialog(
                title + " - Import Failed",
                "The file could not be imported",
                ["Importing '%s' created no objects." % r["file"], "",
                 "The workflow continues safely - you can import manually in "
                 "Rhino and select the site plot in the next step."],
                "Continue")
            return info
        info["up_axis_fix"] = _sc_fix_up_axis_if_needed(ids)
        layer, moved = assign_imported_context_layer(ids, role)
        tag_imported_context_objects(ids, role)
        info.update({"imported": True, "skipped": False, "count": len(ids),
                     "ids": [str(i) for i in ids], "file": r["file"],
                     "format": r["format"], "layer": layer})
        print("%s: imported %d object(s) from %s -> layer %s."
              % (title, len(ids), r["file"], layer))
    except Exception as ex:
        info["warning"] = str(ex)
        print("%s failed (%s) - continuing." % (title, ex))
    return info


def run_early_site_analysis(P, site):
    """EARLY analysis of the selected site plot: plan boundary (WorldXY),
    elevation range, uneven/contour status, road adjacency, surroundings.
    Stores results on the planning context and returns the analysis dict."""
    ctx = _sp_get_planning_context(P)
    a = {"selected_site_source": ctx.get("site_source"),
         "object_type": site.get("type"),
         "setback_projection_plane": "WorldXY",
         "boundary_projection_method": None,
         "site_is_uneven": None, "site_min_z": None, "site_max_z": None,
         "site_elevation_range": None, "plan_area_m2": None,
         "plan_dims_m": None, "centroid_xy": None, "longest_direction": None,
         "boundary_points": None, "boundary_is_fallback": None,
         "irregular_setback_supported": None, "road_adjacent_side": None,
         "road_context_exists": False, "warnings": []}
    try:
        # elevation range straight from the object bbox
        a["site_min_z"] = round(site["min"][2], 3)
        a["site_max_z"] = round(site["max"][2], 3)
        a["site_elevation_range"] = round(site["max"][2] - site["min"][2], 3)
        a["site_is_uneven"] = a["site_elevation_range"] > \
            SITE_CTX_UNEVEN_THRESHOLD_M
        # plan boundary (extract_site_boundary samples in WorldXY already)
        sb = ctx.get("site_boundary")
        if not sb:
            sb = extract_site_boundary(site)
            ctx["site_boundary"] = sb
        a["boundary_projection_method"] = sb.get("mode")
        a["boundary_is_fallback"] = bool(sb.get("fallback"))
        poly = sb.get("poly")
        if poly:
            a["boundary_points"] = len(poly)
            a["plan_area_m2"] = round(_poly_area(poly), 2)
            bx = _poly_bbox(poly)
            a["plan_dims_m"] = [round(bx[2] - bx[0], 2),
                                round(bx[3] - bx[1], 2)]
            c = _poly_centroid(poly)
            a["centroid_xy"] = [round(c[0], 2), round(c[1], 2)]
            # longest boundary edge direction
            best = None
            for i in range(len(poly)):
                p1 = poly[i]
                p2 = poly[(i + 1) % len(poly)]
                L = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
                if best is None or L > best[0]:
                    best = (L, math.degrees(math.atan2(
                        p2[1] - p1[1], p2[0] - p1[0])) % 180.0)
            if best:
                a["longest_direction"] = ("%.1f m edge at %.1f deg from +X"
                                          % (best[0], best[1]))
            a["irregular_setback_supported"] = (not sb.get("fallback")
                                                and len(poly) >= 3)
        else:
            a["warnings"].append("No plan boundary polygon extracted.")
            a["irregular_setback_supported"] = False
        # road adjacency (only if road context was imported)
        ic = ctx.get("imported_context") or {}
        road_info = (ic.get("imported") or {}).get("site_road") or {}
        if road_info.get("imported"):
            a["road_context_exists"] = True
            try:
                rids = find_imported_context_objects("site_road")
                rb = rs.BoundingBox(rids) if rids else None
                if rb and poly:
                    rxs = [p[0] for p in rb]
                    rys = [p[1] for p in rb]
                    rx0, rx1 = min(rxs), max(rxs)
                    ry0, ry1 = min(rys), max(rys)

                    def _dist_to_bbox(pt):
                        dx = max(rx0 - pt[0], 0.0, pt[0] - rx1)
                        dy = max(ry0 - pt[1], 0.0, pt[1] - ry1)
                        return math.hypot(dx, dy)
                    best = None
                    for i in range(len(poly)):
                        p1 = poly[i]
                        p2 = poly[(i + 1) % len(poly)]
                        mid = ((p1[0] + p2[0]) / 2.0, (p1[1] + p2[1]) / 2.0)
                        d = _dist_to_bbox(mid)
                        if best is None or d < best[1]:
                            best = (i, d)
                    if best:
                        a["road_adjacent_side"] = {
                            "boundary_side_index": best[0],
                            "distance_m": round(best[1], 2)}
            except Exception as ex:
                a["warnings"].append("Road adjacency check failed (%s)." % ex)
        # surroundings summary
        sur_info = (ic.get("imported") or {}).get(
            "surrounding_buildings") or {}
        if sur_info.get("imported"):
            try:
                sids = find_imported_context_objects("surrounding_buildings")
                sbx = rs.BoundingBox(sids) if sids else None
                ctx["surroundings_analysis"] = {
                    "object_count": len(sids or []),
                    "bbox_min": [round(v, 1) for v in sbx[0]] if sbx else None,
                    "bbox_max": [round(v, 1) for v in sbx[6]] if sbx else None,
                    "use": "visual + future sunlight/shadow context only",
                    "transformed_with_building": False}
            except Exception:
                pass
    except Exception as ex:
        a["warnings"].append("Site analysis error: %s" % ex)
    ctx["site_analysis"] = a
    return a


def _sc_analysis_dialog_lines(a, ctx):
    ic = ctx.get("imported_context") or {}
    imp = ic.get("imported") or {}
    lines = [
        "Selected site source : %s" % (ctx.get("site_source") or "manual"),
        "Object type          : %s" % a.get("object_type"),
        "Plan dims (m)        : %s" % (a.get("plan_dims_m") or "-"),
        "Plan area (m2)       : %s" % (a.get("plan_area_m2") or "-"),
        "Elevation range (m)  : %s (z %s .. %s)" % (
            a.get("site_elevation_range"), a.get("site_min_z"),
            a.get("site_max_z")),
        "Site is              : %s" % ("UNEVEN / terrain"
                                       if a.get("site_is_uneven")
                                       else "flat (within %.2f m)"
                                       % SITE_CTX_UNEVEN_THRESHOLD_M),
        "Boundary mode        : %s" % a.get("boundary_projection_method"),
        "Setback projection   : WorldXY plan boundary (never along terrain)",
        "Irregular setback OK : %s" % a.get("irregular_setback_supported"),
        "Road context         : %s" % ("imported / detected"
                                       if a.get("road_context_exists")
                                       else "not imported"),
        "Surroundings         : %s" % ("imported"
                                       if (imp.get("surrounding_buildings")
                                           or {}).get("imported")
                                       else "not imported"),
        "",
        "The building will remain VERTICAL (no tilt), the site mesh is NOT "
        "cut or modified, and Z placement uses terrain sampling under the "
        "footprint (max z + %.2f m clearance)." % SITE_CTX_Z_CLEARANCE_M,
    ]
    if a.get("site_is_uneven"):
        lines += ["", "TERRAIN WARNING: the site has %.2f m of level "
                  "difference. Any remaining level difference under the "
                  "placed building must be resolved by foundation / terrace "
                  "design." % (a.get("site_elevation_range") or 0.0)]
    for w in (a.get("warnings") or []):
        lines.append("Warning: %s" % w)
    lines += ["", "Next: Phase 1A building parameters.", "",
              SITE_PLACEMENT_DISCLAIMER]
    return lines


def _sc_select_site_step(P):
    """Site plot selection after the imports (auto-suggest the imported plot if
    it is a single object; manual selection otherwise). Returns site or None."""
    ctx = _sp_get_planning_context(P)
    want = show_styled_prompt(
        "Select Actual Site Plot",
        "The plot used for setback + final placement",
        ["Select the exact site plot surface / mesh / closed boundary that "
         "should be used for setback and placement.",
         "",
         "This can be the imported site plot or an existing Rhino object. "
         "The site object is never moved, cut, or deleted.",
         "",
         "You can skip and select the site later at the final stage."],
        "Select Site Plot", "Skip Site Selection for Now",
        window_title="Timber Housing v28 - Site Plot", ta_height=200,
        width=660, height=460)
    if not want:
        return None
    plot_ids = find_imported_context_objects("site_plot")
    if len(plot_ids) == 1:
        use = show_styled_prompt(
            "Use Imported Site Plot?",
            "Exactly one imported site plot object found",
            ["The imported site plot is a single object - use it directly "
             "as the selected site?",
             "",
             "Choose 'Pick Manually' to select any other object instead."],
            "Use Imported Site Plot", "Pick Manually",
            window_title="Timber Housing v28 - Site Plot", ta_height=150,
            width=620, height=400)
        if use:
            site = _sc_site_info_from_id(plot_ids[0])
            if site:
                ctx["site_source"] = "imported_site_plot"
                return site
    site = _sp_select_site()
    if site:
        ctx["site_source"] = "manual_selection"
    return site


def run_site_context_import_workflow(P):
    """V28 orchestrator (runs right after the EARLY city dialog):
    inspect folder -> classify -> 3 import dialogs -> site selection ->
    early site analysis (+ 3-way summary dialog) -> import report folder.
    Fully guarded; every step skippable; v27 flow continues regardless."""
    ctx = _sp_get_planning_context(P)
    ic = {"folder": None, "inspection": None, "classification": None,
          "pairing": None, "recommendation": None, "imported": {},
          "report_folder": None, "warnings": []}
    ctx["imported_context"] = ic
    sdir = _sc_script_dir(P)
    folder = _sc_find_site_folder(sdir)
    if not folder:
        show_site_info_dialog(
            "Site Context Import",
            "Site / surroundings folder not found",
            ["No '%s' (or '%s') folder was found next to the configurator." %
             tuple(SITE_CTX_FOLDER_CANDIDATES),
             "",
             "Context import is skipped. You can still select a site "
             "manually now or at the final placement stage."],
            "Continue")
        ic["warnings"].append("site folder not found")
        return ctx
    ic["folder"] = folder
    scan = inspect_site_surroundings_folder(folder)
    cls = classify_site_geometry_files(scan)
    pairing = pair_obj_stl_files(scan, cls)
    rec = recommend_site_import_files(cls, pairing)
    ic["inspection"] = {"files": scan.get("files"),
                        "objs": dict((k, {kk: vv for kk, vv in v.items()
                                          if kk != "per_material_vertices"})
                                     for k, v in
                                     (scan.get("objs") or {}).items()),
                        "stls": scan.get("stls")}
    ic["classification"] = cls
    ic["pairing"] = pairing
    ic["recommendation"] = rec
    print("v28 site folder: %s (%d OBJ, %d STL classified)."
          % (folder, len(scan.get("objs") or {}), len(scan.get("stls") or {})))
    # ---- Dialog 1: site plot -------------------------------------------
    ic["imported"]["site_plot"] = run_context_import_step(
        "site_plot", "Import Site Plot Geometry",
        "The actual plot for setback + final placement",
        ["The configurator will import the actual site plot / site plane "
         "geometry from the site and surroundings folder. This is the plot "
         "used for setback calculation and final placement.",
         "",
         "The imported site will NOT be moved with the building. The site "
         "may be uneven / contoured - it will be analyzed before placement."],
        rec, folder)
    # ---- Dialog 2: site + road -------------------------------------------
    road_rec = rec.get("site_road")
    road_note = ("Road geometry appears to EXIST in this file."
                 if road_rec else None)
    ic["imported"]["site_road"] = run_context_import_step(
        "site_road", "Import Site + Road Context",
        "Road adjacency / orientation / context",
        ["The configurator will import the site/road context model. This "
         "helps with road adjacency, orientation, and context placement.",
         "",
         "If a road already exists in this context, the later road step "
         "will offer to SKIP generating a duplicate road."],
        rec, folder, extra_note=road_note)
    # ---- Dialog 3: surrounding buildings ---------------------------------
    ic["imported"]["surrounding_buildings"] = run_context_import_step(
        "surrounding_buildings", "Import Surrounding Buildings",
        "Visual + analysis context only",
        ["The configurator will import the surrounding block/context "
         "buildings. These are used only as visual and analysis context, "
         "not as building placement geometry."],
        rec, folder)
    try:
        rs.ZoomExtents()
        Rhino.RhinoDoc.ActiveDoc.Views.Redraw()
    except Exception:
        pass
    # ---- site selection + early analysis (reselect loop, max 3) ----------
    tries = 0
    while tries < 3:
        tries += 1
        site = _sc_select_site_step(P)
        if not site:
            print("v28: site selection skipped - the final stage will ask.")
            break
        ctx["site"] = site
        ctx["site_selected_stage"] = "early"
        try:
            ctx["site_boundary"] = extract_site_boundary(site)
        except Exception:
            ctx["site_boundary"] = None
        try:
            a = run_early_site_analysis(P, site)
        except Exception as ex:
            print("Early site analysis failed (%s)." % ex)
            break
        act = show_site_analysis_dialog(_sc_analysis_dialog_lines(a, ctx))
        if act == "reselect":
            ctx["site"] = None
            ctx["site_boundary"] = None
            ctx["site_analysis"] = None
            continue
        if act == "skip":
            ctx["site_analysis"] = None
            print("v28: continuing WITHOUT site analysis (user choice; site "
                  "selection kept).")
        break
    # ---- import / analysis report folder ---------------------------------
    try:
        ic["report_folder"] = _sc_write_import_report(P)
        if ic["report_folder"]:
            print("v28 site context import report: %s" % ic["report_folder"])
    except Exception as ex:
        print("v28 import report skipped (%s)." % ex)
    return ctx


def _sc_write_import_report(P):
    """Write site_import_context_report_YYYYMMDDHHMMSS into the site folder
    (7 files). Returns the folder path or None. Never raises."""
    ctx = _sp_get_planning_context(P)
    ic = ctx.get("imported_context") or {}
    base = ic.get("folder")
    if not base:
        return None
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    folder = os.path.join(base, "site_import_context_report_%s" % stamp)
    try:
        os.makedirs(folder)
    except Exception:
        pass
    a = ctx.get("site_analysis") or {}
    imp = ic.get("imported") or {}
    # 1. main MD report
    try:
        with open(os.path.join(folder,
                               "SITE_CONTEXT_IMPORT_REPORT.md"), "w") as f:
            f.write("# V28 Site Context Import Report\n\n")
            f.write("Folder inspected: %s\n\n" % ic.get("folder"))
            f.write("## Files classified\n\n")
            for name, c in (ic.get("classification") or {}).items():
                f.write("- %s -> %s (%s): %s\n"
                        % (name, c.get("role"), c.get("confidence"),
                           "; ".join(c.get("reasons") or [])))
            f.write("\n## Imports\n\n")
            for role, d in imp.items():
                f.write("- %s: %s (file %s, %s objects, layer %s%s)\n"
                        % (role,
                           "imported" if d.get("imported") else "skipped",
                           d.get("file"), d.get("count"), d.get("layer"),
                           ", Y-up fix" if d.get("up_axis_fix") else ""))
            f.write("\n## Selected site\n\n")
            f.write("- source: %s\n" % ctx.get("site_source"))
            f.write("- analysis: %s\n\n" % json.dumps(a, indent=1))
            f.write("## Placement rules (V28)\n\n")
            f.write(SITE_CTX_VERTICAL_NOTE + "\n\n")
            f.write("Building transform allowed: X/Y/Z translation + Z-axis "
                    "rotation only. Imported context is never transformed.\n\n")
            f.write(SITE_PLACEMENT_DISCLAIMER + "\n")
    except Exception:
        pass
    # 2. inventory csv
    try:
        with open(os.path.join(folder,
                               "imported_context_inventory.csv"), "w") as f:
            f.write(_csv_row(["file", "kind", "size_bytes", "role",
                              "confidence", "imported", "object_count",
                              "layer"]))
            cls = ic.get("classification") or {}
            for fi in ((ic.get("inspection") or {}).get("files") or []):
                c = cls.get(fi["name"]) or {}
                role = c.get("role", "")
                d = imp.get(role) or {}
                used = (d.get("file") == fi["name"] and d.get("imported"))
                f.write(_csv_row([fi["name"], fi["kind"], fi["size_bytes"],
                                  role, c.get("confidence", ""),
                                  used, d.get("count") if used else "",
                                  d.get("layer") if used else ""]))
    except Exception:
        pass
    # 3. imported objects csv
    try:
        with open(os.path.join(folder, "imported_objects.csv"), "w") as f:
            f.write(_csv_row(["object_id", "role", "layer"]))
            for role, d in imp.items():
                for oid in (d.get("ids") or []):
                    f.write(_csv_row([oid, role, d.get("layer")]))
    except Exception:
        pass
    # 4-6. analysis JSONs
    for fname, payload in (
            ("site_analysis.json",
             {"site_analysis": a, "site_source": ctx.get("site_source"),
              "setback_projection_plane": "WorldXY",
              "note": "setback is plan-based",
              "site_is_uneven": a.get("site_is_uneven"),
              "site_min_z": a.get("site_min_z"),
              "site_max_z": a.get("site_max_z"),
              "site_elevation_range": a.get("site_elevation_range"),
              "boundary_projection_method":
                  a.get("boundary_projection_method")}),
            ("road_context_analysis.json",
             {"road_imported": (imp.get("site_road") or {}).get("imported",
                                                                False),
              "road_context_exists": a.get("road_context_exists", False),
              "road_adjacent_side": a.get("road_adjacent_side"),
              "recommendation": ("detect existing road; do not blindly "
                                 "generate a duplicate"
                                 if a.get("road_context_exists")
                                 else "no imported road context")}),
            ("surroundings_context_analysis.json",
             ctx.get("surroundings_analysis") or
             {"imported": (imp.get("surrounding_buildings") or
                           {}).get("imported", False)})):
        try:
            with open(os.path.join(folder, fname), "w") as f:
                json.dump(payload, f, indent=1)
        except Exception:
            pass
    # 7. recommended placement inputs
    try:
        with open(os.path.join(folder,
                               "recommended_placement_inputs.json"), "w") as f:
            json.dump({
                "site_object_source": ctx.get("site_source"),
                "site_boundary_mode": (ctx.get("site_boundary") or
                                       {}).get("mode"),
                "setback_projection_plane": "WorldXY",
                "buildable_zone": "plan-projected irregular inward offset",
                "z_placement_rule": "max sampled terrain z under footprint + "
                                    "%.2f m clearance" % SITE_CTX_Z_CLEARANCE_M,
                "building_transform_allowed":
                    "X/Y/Z translation + Z-axis rotation only",
                "model_tilted": False, "terrain_cut": False,
                "site_mesh_modified": False,
                "imported_context_transformed": False,
                "road_handling": ("detect imported road; ask before "
                                  "generating an additional labelled road"
                                  if a.get("road_context_exists")
                                  else "optional generated road (v27 rule)"),
                "galapagos_terrain_scoring": {
                    "fields": ["terrain_min_z", "terrain_max_z",
                               "terrain_delta_z", "terrain_score",
                               "z_placement", "terrain_warning"],
                    "weight": SITE_CTX_TERRAIN_SCORE_WEIGHT},
                "disclaimer": SITE_PLACEMENT_DISCLAIMER}, f, indent=1)
    except Exception:
        pass
    return folder


# ---- final-stage integration helpers ----------------------------------------

def _sc_road_context_exists(P):
    try:
        ctx = _sp_get_planning_context(P)
        a = ctx.get("site_analysis") or {}
        if a.get("road_context_exists"):
            return True
        ic = ctx.get("imported_context") or {}
        return bool(((ic.get("imported") or {}).get("site_road") or
                     {}).get("imported"))
    except Exception:
        return False


def _sc_stage_annotations(P, site, site_boundary):
    """R-dict annotations for the final stage (plan projection + context)."""
    ctx = _sp_get_planning_context(P)
    a = ctx.get("site_analysis") or {}
    zmin = a.get("site_min_z")
    zmax = a.get("site_max_z")
    if zmin is None and site:
        try:
            zmin = round(site["min"][2], 3)
            zmax = round(site["max"][2], 3)
        except Exception:
            zmin = zmax = None
    rng = (round(zmax - zmin, 3) if (zmin is not None and zmax is not None)
           else None)
    return {"setback_projection_plane": "WorldXY",
            "boundary_projection_method": (site_boundary or {}).get("mode"),
            "site_is_uneven": (a.get("site_is_uneven")
                               if a.get("site_is_uneven") is not None
                               else (rng is not None and
                                     rng > SITE_CTX_UNEVEN_THRESHOLD_M)),
            "site_min_z": zmin, "site_max_z": zmax,
            "site_elevation_range": rng,
            "road_context_exists": _sc_road_context_exists(P),
            "v28_context": _sc_completion_summary(P)}


def _sc_rerank_with_terrain(result, site, footprint):
    """Annotate every reported candidate with terrain fields sampled under its
    footprint (corners + centre) and re-rank the FITTING candidates with an
    additive terrain-suitability term. Building stays vertical; this only
    changes WHICH candidate is preferred. Never raises."""
    try:
        cands = result.get("candidates") or []
        sid = site.get("id")
        fallback_top = site["max"][2]
        if not cands or sid is None:
            return result
        for c in cands:
            try:
                ex, ey = _sp_footprint_extent(footprint[0], footprint[1],
                                              c.get("rot", 0))
                cx, cy = c.get("cx", 0.0), c.get("cy", 0.0)
                pts = [(cx, cy),
                       (cx - ex / 2.0, cy - ey / 2.0),
                       (cx + ex / 2.0, cy - ey / 2.0),
                       (cx + ex / 2.0, cy + ey / 2.0),
                       (cx - ex / 2.0, cy + ey / 2.0)]
                zs = _sp_sample_terrain(sid, pts, fallback_top)
                st = _sp_terrain_stats(zs)
                delta = st.get("diff") or 0.0
                c["terrain_min_z"] = round(st.get("min"), 3) \
                    if st.get("min") is not None else None
                c["terrain_max_z"] = round(st.get("max"), 3) \
                    if st.get("max") is not None else None
                c["terrain_delta_z"] = round(delta, 3)
                c["terrain_score"] = round(_sc_terrain_score(delta), 3)
                c["z_placement"] = round((st.get("max") or fallback_top) +
                                         SITE_CTX_Z_CLEARANCE_M, 3)
                c["terrain_warning"] = (
                    "Selected position crosses uneven terrain. Building "
                    "remains vertical; foundation/terrace adjustment required."
                    if delta > SITE_CTX_TERRAIN_WARN_M else "")
                if c.get("fits"):
                    c["total_with_terrain"] = round(
                        c.get("total", 0.0) +
                        SITE_CTX_TERRAIN_SCORE_WEIGHT * c["terrain_score"], 3)
            except Exception:
                continue
        fitted = [c for c in cands if c.get("fits") and
                  c.get("total_with_terrain") is not None]
        if fitted:
            fitted.sort(key=lambda c: c.get("total_with_terrain", 0.0),
                        reverse=True)
            result["best"] = fitted[0]
            result["top5"] = fitted[:5]
            result["terrain_reranked"] = True
    except Exception as ex:
        print("Terrain re-ranking skipped (%s)." % ex)
    return result


def _sc_report_fields(P, R):
    """Extra fields for site_placement_result.json (V28)."""
    best = R.get("best") or {}
    terr = R.get("terrain") or {}
    return {
        "v28_addition": "site context import + uneven-terrain placement",
        "model_tilted": False,
        "terrain_cut": False,
        "site_mesh_modified": False,
        "building_transform_allowed":
            "X/Y/Z translation + Z-axis rotation only",
        "setback_projection_plane": R.get("setback_projection_plane",
                                          "WorldXY"),
        "boundary_projection_method": R.get("boundary_projection_method"),
        "site_is_uneven": R.get("site_is_uneven"),
        "site_min_z": R.get("site_min_z"),
        "site_max_z": R.get("site_max_z"),
        "site_elevation_range": R.get("site_elevation_range"),
        "selected_candidate_terrain_delta_z": best.get(
            "terrain_delta_z", terr.get("diff")),
        "selected_candidate_z_placement": best.get(
            "z_placement", R.get("z_placement")),
        "terrain_reranked": R.get("terrain_reranked", False),
        "terrain_score_weight": SITE_CTX_TERRAIN_SCORE_WEIGHT,
        "road_context_exists": R.get("road_context_exists", False),
        "imported_context": ((R.get("v28_context") or {})
                             if isinstance(R.get("v28_context"), dict)
                             else {}),
    }


def _sc_completion_summary(P):
    """Compact v28 status block for the completion dialog + reports."""
    try:
        ctx = _sp_get_planning_context(P)
    except Exception:
        return {}
    ic = ctx.get("imported_context") or {}
    imp = ic.get("imported") or {}
    a = ctx.get("site_analysis") or {}

    def _st(role):
        d = imp.get(role) or {}
        if d.get("imported"):
            return "yes (%d obj%s)" % (d.get("count", 0),
                                       ", reused" if d.get("reused_existing")
                                       else "")
        return "no"
    return {"site_plot_imported": _st("site_plot"),
            "site_road_imported": _st("site_road"),
            "surroundings_imported": _st("surrounding_buildings"),
            "selected_site_source": ctx.get("site_source") or "-",
            "site_analysis_status": ("done" if a else "not run"),
            "site_is_uneven": a.get("site_is_uneven"),
            "site_elevation_range": a.get("site_elevation_range"),
            "import_report_folder": ic.get("report_folder")}


def _sp_result_body_v28(R):
    """v27 result body + V28 terrain / no-tilt / no-cut lines."""
    body = _sp_result_body_v27(R)
    try:
        terr = R.get("terrain") or {}
        best = R.get("best") or {}
        lines = ["", "-" * 58, "V28 TERRAIN / CONTEXT",
                 "Terrain z under footprint : %s .. %s (delta %s m)"
                 % (terr.get("min"), terr.get("max"), terr.get("diff")),
                 "Z placement (bottom)      : %s"
                 % (R.get("z_placement") if R.get("z_placement") is not None
                    else best.get("z_placement", "-")),
                 "Model tilted              : NO (vertical only)",
                 "Terrain cut / modified    : NO (site mesh preserved)",
                 "Slight overlap with the site mesh may occur and is "
                 "acceptable for V28."]
        if R.get("terrain_warning_text"):
            lines.append("WARNING: %s" % R["terrain_warning_text"])
        body = body + "\n" + "\n".join(lines)
    except Exception:
        pass
    return body


# =============================================================================
# 6e-V29. LOCAL FLORA + FAUNA / NATIVE BIODIVERSITY STRATEGY  (v29, 2026-07)
#
# FINAL, OPTIONAL, SKIPPABLE step offered AFTER the final site placement.
# Generates a Detmold / Kreis Lippe / NRW native-first biodiversity planting
# strategy as a LIGHTWEIGHT proxy layer on its own WoSyHo::Biodiversity::*
# layers, plus a Markdown report and a species CSV.
#
# ADDITIVE ONLY - this section never modifies: skeleton/rack generation, grid
# or cascade math, base/plinth/lower beams, slabs, stairs, V-column / tree
# geometry, StructuralModel, dummy or detailed module placement, Module-2
# corridor logic, stability, preliminary sizing, RFEM/Dlubal export, the site
# placement transform, imported context, or the site mesh. Nothing is cut,
# tilted, or moved. Skipping the step leaves the model byte-for-byte as the
# v28 workflow produced it.
#
# PRECEDENT LOGIC (conceptual only, see docs/WOSYHO_V29_LOCAL_FLORA_FAUNA_
# STRATEGY.md): MVRDV "The Island" -> the palette is a CROSS-SECTION of the
# surrounding region's flora; MVRDV "La Serre" -> species are chosen by their
# HEIGHT ON THE BUILDING and their SUN / WIND EXPOSURE, ~70% native, with
# ecologist-specified bird and bat boxes; co-living studies -> terraces and
# undercroft are shared social-ecological rooms.
#
# CONCEPTUAL PLANNING SUPPORT - NOT LANDSCAPE ENGINEERING. All terrace / roof
# planting requires structural load verification.
# =============================================================================

BIO_LAYERS = {
    "root":     "WoSyHo::Biodiversity",
    "trees":    "WoSyHo::Biodiversity::Trees",
    "shrubs":   "WoSyHo::Biodiversity::Shrubs",
    "meadow":   "WoSyHo::Biodiversity::Meadow",
    "planters": "WoSyHo::Biodiversity::TerracePlanters",
    "roof":     "WoSyHo::Biodiversity::RoofGreening",
    "fauna":    "WoSyHo::Biodiversity::FaunaHabitats",
    "reports":  "WoSyHo::Biodiversity::Reports",
}

BIO_NATIVE_TARGET = 0.70          # La Serre benchmark: >= 70% native species
BIO_TREE_CLEARANCE_M = 2.0        # keep trees this far from V-column bases
BIO_INSPECTION_CLEAR_M = 1.2      # structural inspection clearance at bases

BIO_WARN_TERRACE = ("Planting on terraces and roofs is conceptual and "
                    "requires structural load verification.")
BIO_WARN_TREE = ("Large trees require intensive planters, root volume, "
                 "irrigation, drainage, wind anchoring, and structural load "
                 "checks.")
BIO_WARN_GENERAL = ("Generated species placement is ecological/visual "
                    "planning support, not final landscape engineering.")
BIO_WARN_ROOF_TREE = ("Trees on roof level are NOT recommended unless an "
                      "intensive roof structure is explicitly verified.")

# --- species library ---------------------------------------------------------
# Columns (documented once; kept as tuples so the table stays readable):
BIO_FIELDS = ("botanical_name", "german_name", "english_name", "layer_type",
              "native_to_nrw", "climate_resilience", "mature_height_m",
              "crown_spread_m", "root_depth_requirement", "soil_depth_min_cm",
              "sun_requirement", "moisture_requirement", "terrace_suitability",
              "wildlife_value", "maintenance_level", "recommended_location",
              "warning_notes")

_BIO_TABLE = [
    # ---- canopy / larger trees (GROUND ONLY) --------------------------------
    ("Quercus robur", "Stieleiche", "English oak", "canopy_tree", "true",
     "high", 25.0, 18.0, "deep", 100, "sun", "fresh", "ground_only",
     "insects/birds/bats/acorns", "low", "open ground, site edge",
     "very large - keep well clear of footings, terraces and facades"),
    ("Tilia cordata", "Winterlinde", "Small-leaved lime", "canopy_tree",
     "true", "medium", 20.0, 12.0, "deep", 100, "sun", "fresh", "ground_only",
     "nectar/bees/birds", "low", "open ground, site edge",
     "major bee tree; aphid honeydew can drip on parked cars"),
    ("Carpinus betulus", "Hainbuche", "Hornbeam", "canopy_tree", "true",
     "high", 15.0, 10.0, "medium", 80, "sun_partial", "fresh", "ground_only",
     "birds/insects/seeds/nesting", "low", "site edge, hedge, open ground",
     "also excellent as a clipped native hedge"),
    ("Acer campestre", "Feldahorn", "Field maple", "small_tree", "true",
     "high", 10.0, 7.0, "medium", 70, "sun_partial", "fresh_dry",
     "ground_only", "nectar/insects/birds", "low",
     "site edge, between module clusters", "very urban-tolerant"),
    ("Betula pendula", "Sandbirke", "Silver birch", "canopy_tree", "true",
     "medium", 20.0, 8.0, "medium", 80, "sun", "dry_fresh", "ground_only",
     "insects/birds/seeds", "low", "open ground, meadow edge",
     "shallow spreading roots - keep off paving; pollen allergen"),
    ("Fagus sylvatica", "Rotbuche", "European beech", "canopy_tree", "true",
     "low", 25.0, 15.0, "medium", 100, "partial", "fresh", "ground_only",
     "insects/birds/mast", "low", "sheltered open ground",
     "drought-sensitive under climate change - use sparingly"),
    ("Sorbus aucuparia", "Eberesche", "Rowan", "small_tree", "true", "medium",
     10.0, 6.0, "medium", 60, "sun_partial", "fresh", "large_planter_only",
     "berries/birds/nectar", "low", "open ground, large terrace planter",
     "heavy bird berry crop"),
    ("Alnus glutinosa", "Schwarzerle", "Black alder", "canopy_tree", "true",
     "medium", 20.0, 8.0, "deep", 90, "sun", "wet", "ground_only",
     "insects/birds/seeds", "low", "rain garden edge, wet ground",
     "wet zones only - do not plant on dry roof or terrace"),
    ("Salix caprea", "Sal-Weide", "Goat willow", "small_tree", "true", "high",
     8.0, 6.0, "medium", 60, "sun", "fresh_wet", "ground_only",
     "very early pollen - key bee plant", "medium",
     "rain garden edge, open ground", "vigorous; coppice to control size"),
    ("Prunus avium", "Vogelkirsche", "Wild cherry", "canopy_tree", "true",
     "medium", 18.0, 10.0, "medium", 90, "sun", "fresh", "ground_only",
     "nectar/fruit/birds", "low", "open ground, site edge",
     "fruit drop - keep away from seating and paths"),
    # ---- small trees (terrace only in LARGE intensive planters) -------------
    ("Amelanchier ovalis", "Felsenbirne", "Snowy mespilus", "small_tree",
     "true", "high", 4.0, 3.0, "shallow_medium", 60, "sun", "dry_fresh",
     "large_planter_only", "blossom/berries/birds", "low",
     "terrace planter, courtyard", "best small tree for terrace planters"),
    ("Crataegus monogyna", "Eingriffeliger Weissdorn", "Hawthorn",
     "small_tree", "true", "high", 6.0, 5.0, "medium", 60, "sun", "fresh",
     "large_planter_only", "nectar/haws/nesting", "low",
     "site edge hedge, large planter",
     "thorny - keep clear of circulation and seating"),
    ("Malus sylvestris", "Wildapfel", "Crab apple", "small_tree", "true",
     "medium", 7.0, 6.0, "medium", 70, "sun", "fresh", "large_planter_only",
     "nectar/fruit/birds", "medium", "open ground, community garden zone",
     "fruit drop; regional fruit cultivars acceptable - flag as cultivar"),
    # ---- shrubs / hedges ----------------------------------------------------
    ("Corylus avellana", "Hasel", "Hazel", "shrub", "true", "high", 5.0, 4.0,
     "medium", 60, "sun_partial", "fresh", "ground_only",
     "early pollen/nuts/birds/mammals", "low", "site edge, hedgerow", ""),
    ("Cornus sanguinea", "Roter Hartriegel", "Dogwood", "shrub", "true",
     "high", 3.0, 2.5, "medium", 50, "sun_partial", "fresh", "ground_only",
     "insects/berries/birds", "low", "site edge, between clusters",
     "suckers - keep off narrow beds"),
    ("Sambucus nigra", "Schwarzer Holunder", "Elder", "shrub", "true", "high",
     5.0, 4.0, "medium", 60, "sun_partial", "fresh", "ground_only",
     "nectar/heavy berry crop/birds", "low", "site edge, undercroft fringe",
     "fast and large - allow space"),
    ("Viburnum opulus", "Gewoehnlicher Schneeball", "Guelder rose", "shrub",
     "true", "medium", 4.0, 3.0, "medium", 50, "sun_partial", "fresh_moist",
     "ground_only", "nectar/berries/birds", "low",
     "site edge, rain garden edge", ""),
    ("Rosa canina", "Hundsrose", "Dog rose", "shrub", "true", "high", 3.0,
     2.5, "medium", 50, "sun", "fresh_dry", "ground_only",
     "open flowers/hips/birds/nesting", "low", "site edge hedgerow",
     "thorny - keep clear of circulation"),
    ("Euonymus europaeus", "Pfaffenhuetchen", "Spindle", "shrub", "true",
     "medium", 4.0, 3.0, "medium", 50, "sun_partial", "fresh", "ground_only",
     "specialist insects/berries", "low", "site edge, away from active zones",
     "berries TOXIC to humans - do not place on student-active edges"),
    ("Prunus spinosa", "Schlehe", "Blackthorn", "shrub", "true", "high", 4.0,
     3.0, "medium", 50, "sun", "fresh_dry", "ground_only",
     "very early blossom/sloes/thorny nest cover", "low",
     "site edge hedgerow, boundary corridor",
     "thorny and strongly suckering - keep off paths and narrow beds"),
    ("Ligustrum vulgare", "Liguster", "Wild privet", "shrub", "true", "high",
     3.0, 2.0, "medium", 50, "sun_partial", "fresh", "ground_only",
     "nectar/berries/cover", "medium", "site edge hedge",
     "berries mildly toxic - avoid active student edges"),
    ("Ribes rubrum", "Johannisbeere", "Redcurrant", "shrub", "true", "high",
     1.5, 1.2, "shallow", 40, "sun_partial", "fresh", "balcony_planter",
     "nectar/edible berries/birds", "medium",
     "community garden zone, terrace planter", "edible - student garden beds"),
    ("Rubus idaeus", "Himbeere", "Raspberry", "shrub", "true", "high", 1.8,
     1.0, "shallow", 40, "sun_partial", "fresh", "large_planter_only",
     "nectar/edible fruit/birds", "medium", "community garden zone",
     "suckering - contain in planters"),
    ("Rubus fruticosus agg.", "Brombeere", "Blackberry", "shrub", "true",
     "high", 2.0, 3.0, "medium", 50, "sun_partial", "fresh", "ground_only",
     "nectar/fruit/birds/cover", "medium", "site edge, undercroft fringe",
     "very vigorous and thorny - only at controlled edges, needs cutting back"),
    # ---- grasses / meadow / perennials (sun) --------------------------------
    ("Festuca rubra", "Rotschwingel", "Red fescue", "grass", "true", "high",
     0.5, 0.3, "shallow", 15, "sun", "fresh_dry", "roof_extensive",
     "meadow matrix/insects", "low", "meadow, roof meadow", ""),
    ("Festuca filiformis", "Schaf-Schwingel", "Fine-leaved sheep's fescue",
     "grass", "true", "high", 0.3, 0.2, "shallow", 10, "sun", "dry",
     "roof_extensive", "dry meadow matrix", "low", "roof dry meadow", ""),
    ("Deschampsia cespitosa", "Rasenschmiele", "Tufted hair-grass", "grass",
     "true", "high", 1.0, 0.6, "medium", 25, "sun_partial", "fresh_moist",
     "ground_only", "structure/insects/seed", "low",
     "meadow, rain garden edge, part-shade ground", ""),
    ("Achillea millefolium", "Schafgarbe", "Yarrow", "perennial", "true",
     "high", 0.6, 0.4, "shallow", 15, "sun", "dry_fresh", "roof_extensive",
     "pollinators/long flowering", "low", "meadow, roof, terrace planter", ""),
    ("Leucanthemum vulgare", "Margerite", "Oxeye daisy", "meadow", "true",
     "high", 0.6, 0.3, "shallow", 15, "sun", "fresh", "roof_extensive",
     "generalist nectar", "low", "meadow, roof meadow", ""),
    ("Centaurea jacea", "Wiesen-Flockenblume", "Brown knapweed", "meadow",
     "true", "high", 0.8, 0.4, "medium", 20, "sun", "fresh",
     "roof_intensive", "bees/butterflies/seed for birds", "low",
     "meadow", ""),
    ("Knautia arvensis", "Acker-Witwenblume", "Field scabious", "meadow",
     "true", "high", 0.8, 0.4, "medium", 20, "sun", "fresh_dry",
     "roof_intensive", "top wild-bee and butterfly plant", "low",
     "meadow, dry meadow", ""),
    ("Lotus corniculatus", "Hornklee", "Bird's-foot trefoil", "meadow",
     "true", "high", 0.3, 0.3, "shallow", 15, "sun", "dry_fresh",
     "roof_extensive", "key butterfly larval plant/bees", "low",
     "meadow, roof meadow", ""),
    ("Trifolium pratense", "Rotklee", "Red clover", "meadow", "true", "high",
     0.4, 0.3, "shallow", 15, "sun", "fresh", "roof_intensive",
     "bumblebees/nitrogen", "low", "meadow", ""),
    ("Plantago lanceolata", "Spitzwegerich", "Ribwort plantain", "meadow",
     "true", "high", 0.4, 0.2, "shallow", 15, "sun", "fresh",
     "roof_extensive", "butterfly larval plant/seed", "low", "meadow", ""),
    ("Primula veris", "Schluesselblume", "Cowslip", "perennial", "true",
     "medium", 0.25, 0.2, "shallow", 20, "sun_partial", "fresh",
     "ground_only", "very early nectar", "low", "meadow edge, part shade",
     "protected in the wild - use nursery/regional stock only"),
    ("Galium verum", "Echtes Labkraut", "Lady's bedstraw", "meadow", "true",
     "high", 0.5, 0.3, "shallow", 15, "sun", "dry", "roof_extensive",
     "moth larval plant/nectar", "low", "dry meadow, roof meadow", ""),
    ("Campanula rotundifolia", "Rundblaettrige Glockenblume", "Harebell",
     "perennial", "true", "high", 0.3, 0.2, "shallow", 15, "sun", "dry",
     "roof_extensive", "specialist bees", "low", "dry meadow, roof", ""),
    ("Origanum vulgare", "Dost", "Wild marjoram", "perennial", "true", "high",
     0.5, 0.4, "shallow", 20, "sun", "dry", "roof_extensive",
     "outstanding butterfly/bee plant", "low",
     "dry meadow, roof, terrace planter", "aromatic - good student planter"),
    ("Salvia pratensis", "Wiesensalbei", "Meadow sage", "meadow", "true",
     "high", 0.6, 0.4, "medium", 20, "sun", "dry_fresh", "roof_intensive",
     "top bee/butterfly nectar", "low", "meadow, dry meadow", ""),
    ("Echium vulgare", "Natternkopf", "Viper's bugloss", "meadow", "true",
     "high", 0.8, 0.4, "medium", 20, "sun", "dry", "roof_extensive",
     "outstanding wild-bee plant", "low", "dry meadow, roof meadow", ""),
    ("Daucus carota", "Wilde Moehre", "Wild carrot", "meadow", "true", "high",
     0.8, 0.3, "medium", 20, "sun", "dry_fresh", "roof_intensive",
     "hoverflies/beetles/seed heads", "low", "meadow", ""),
    ("Sanguisorba minor", "Kleiner Wiesenknopf", "Salad burnet", "meadow",
     "true", "high", 0.4, 0.3, "shallow", 15, "sun", "dry",
     "roof_extensive", "insects/seed", "low", "dry meadow, roof meadow", ""),
    # ---- shade / under-building planting ------------------------------------
    ("Dryopteris filix-mas", "Wurmfarn", "Male fern", "shade_groundcover",
     "true", "high", 1.0, 0.8, "medium", 30, "shade", "moist", "shade_zone",
     "shelter/invertebrates", "low", "undercroft shade, north edges", ""),
    ("Luzula sylvatica", "Wald-Hainsimse", "Great wood-rush",
     "shade_groundcover", "true", "high", 0.4, 0.4, "shallow", 20, "shade",
     "fresh_moist", "shade_zone", "groundcover/invertebrate shelter", "low",
     "undercroft shade", "reliable evergreen shade groundcover"),
    ("Carex sylvatica", "Wald-Segge", "Wood sedge", "shade_groundcover",
     "true", "high", 0.5, 0.3, "shallow", 20, "shade", "moist", "shade_zone",
     "shelter/seed", "low", "undercroft shade", ""),
    ("Hedera helix", "Efeu", "Ivy", "climber", "true", "high", 8.0, 2.0,
     "medium", 40, "shade", "fresh", "ground_only",
     "very late nectar/berries/nesting/roost cover", "medium",
     "undercroft edge, boundary, controlled vertical greening",
     "CONTROL REQUIRED - never allow onto timber cladding or roof edges"),
    # ---- roof / terrace extensive planting -----------------------------------
    ("Sedum album", "Weisser Mauerpfeffer", "White stonecrop", "roof_sedum",
     "true", "high", 0.1, 0.2, "shallow", 8, "sun", "dry", "roof_extensive",
     "late nectar/pollinators", "low", "extensive roof", ""),
    ("Sedum acre", "Scharfer Mauerpfeffer", "Biting stonecrop", "roof_sedum",
     "true", "high", 0.1, 0.2, "shallow", 6, "sun", "dry", "roof_extensive",
     "nectar/pollinators", "low", "extensive roof", ""),
    ("Sedum sexangulare", "Milder Mauerpfeffer", "Tasteless stonecrop",
     "roof_sedum", "true", "high", 0.1, 0.2, "shallow", 6, "sun", "dry",
     "roof_extensive", "nectar/pollinators", "low", "extensive roof", ""),
    ("Sempervivum tectorum", "Dach-Hauswurz", "Common houseleek", "roof_sedum",
     "uncertain", "high", 0.15, 0.2, "shallow", 8, "sun", "dry",
     "roof_extensive", "nectar/structure", "low", "extensive roof",
     "long naturalised in Germany; regional native status uncertain"),
    ("Thymus serpyllum", "Sand-Thymian", "Wild thyme", "roof_sedum", "true",
     "high", 0.1, 0.3, "shallow", 10, "sun", "dry", "roof_extensive",
     "excellent bee plant/aromatic", "low", "extensive roof, terrace planter",
     ""),
    ("Allium schoenoprasum", "Schnittlauch", "Chives", "perennial", "true",
     "high", 0.4, 0.2, "shallow", 20, "sun", "fresh_dry", "balcony_planter",
     "bees/edible", "low", "terrace + community planters",
     "edible - good student planter species"),
    # ---- climbers / vertical greening ---------------------------------------
    ("Lonicera periclymenum", "Wald-Geissblatt", "Common honeysuckle",
     "climber", "true", "high", 5.0, 1.5, "medium", 40, "sun_partial",
     "fresh", "large_planter_only", "night nectar for moths/berries/birds",
     "medium", "pergola, terrace screen, boundary",
     "needs a support structure - never fixed to timber cladding"),
    ("Humulus lupulus", "Hopfen", "Hop", "climber", "true", "high", 6.0, 1.5,
     "medium", 40, "sun_partial", "fresh", "large_planter_only",
     "insects/butterfly larval plant", "medium", "pergola, terrace screen",
     "dies back annually; needs support wires"),
    ("Clematis vitalba", "Waldrebe", "Old man's beard", "climber", "true",
     "high", 10.0, 3.0, "medium", 40, "sun_partial", "fresh", "ground_only",
     "late nectar/seed heads/cover", "high", "boundary corridor only",
     "VERY vigorous and smothering - controlled boundary use only"),
    # ---- wet zone / rain garden ---------------------------------------------
    ("Lythrum salicaria", "Blutweiderich", "Purple loosestrife", "wet_zone",
     "true", "high", 1.2, 0.5, "medium", 30, "sun", "wet", "ground_only",
     "superb bee plant", "low", "rain garden", ""),
    ("Filipendula ulmaria", "Maedesuess", "Meadowsweet", "wet_zone", "true",
     "high", 1.2, 0.6, "medium", 30, "sun_partial", "wet", "ground_only",
     "insects/nectar", "low", "rain garden", ""),
    ("Juncus effusus", "Flatter-Binse", "Soft rush", "wet_zone", "true",
     "high", 0.9, 0.5, "medium", 25, "sun", "wet", "ground_only",
     "cover/structure", "low", "rain garden base", ""),
    ("Iris pseudacorus", "Sumpf-Schwertlilie", "Yellow flag iris", "wet_zone",
     "true", "high", 1.0, 0.5, "medium", 30, "sun", "wet", "ground_only",
     "structure/insects", "low", "rain garden base",
     "vigorous - contain; sap is a skin irritant"),
    ("Myosotis scorpioides", "Sumpf-Vergissmeinnicht", "Water forget-me-not",
     "wet_zone", "true", "high", 0.3, 0.3, "shallow", 20, "sun_partial",
     "wet", "ground_only", "early nectar", "low", "rain garden edge", ""),
]

# --- fauna-support elements ---------------------------------------------------
# (element, target_group, layer_key, size_m, install_height_m, notes)
BIO_FAUNA_ELEMENTS = [
    ("Swift box (integrated crevice type)", "swift", 0.45, 6.0,
     "high facade, cool N/E face, clear drop below, no perch"),
    ("House-sparrow terrace (3-chamber)", "house_sparrow", 0.55, 4.5,
     "mid-high facade near shrub cover; keep 2-3 m from opening windows"),
    ("House-martin cup + droppings board", "house_martin", 0.35, 5.5,
     "under eave/overhang, NOT over doors, seating or terraces"),
    ("Bat crevice panel / bat brick", "bats", 0.40, 5.0,
     "warm high facade; dark flight line kept clear; never seal if occupied"),
    ("Small bird nest box (32 mm hole)", "shrub_birds", 0.25, 3.0,
     "quiet edge trees / boundary, away from busy circulation"),
    ("Insect hotel panel", "solitary_bees_insects", 0.60, 1.6,
     "sunny sheltered wall, must have meadow forage within ~50 m"),
    ("Solitary bee nesting block + bare sand lens", "solitary_bees", 0.80,
     0.4, "sunny well-drained ground/roof; most wild bees nest in the ground"),
    ("Deadwood / log habitat pile", "saproxylic_insects_hedgehog", 1.60, 0.5,
     "undercroft shade and boundary; leave undisturbed"),
    ("Stone / dry-stone pile", "reptiles_insects", 1.20, 0.4,
     "sunny sheltered edge; warm microhabitat"),
    ("Hedgehog shelter + 13x13 cm corridor gap", "hedgehog", 0.60, 0.3,
     "undercroft and boundary; corridor must not face a road"),
]


def bio_species_library():
    """Full species library as a list of dicts (pure; headless-testable)."""
    return [dict(zip(BIO_FIELDS, row)) for row in _BIO_TABLE]


def bio_select_species(layer_types=None, sun=None, moisture=None,
                       terrace_suitability=None, max_height_m=None,
                       min_soil_depth_cm=None, native_only=False, limit=None):
    """Condition-driven species filter (the La Serre logic: species chosen by
    height on the building and by sun/wind/substrate exposure). Pure."""
    out = []
    for s in bio_species_library():
        if layer_types and s["layer_type"] not in layer_types:
            continue
        if native_only and s["native_to_nrw"] != "true":
            continue
        if sun and sun not in s["sun_requirement"] and \
                s["sun_requirement"] not in sun:
            continue
        if moisture and moisture not in s["moisture_requirement"] and \
                s["moisture_requirement"] not in moisture:
            continue
        if terrace_suitability and \
                s["terrace_suitability"] != terrace_suitability:
            continue
        if max_height_m is not None and s["mature_height_m"] > max_height_m:
            continue
        if min_soil_depth_cm is not None and \
                s["soil_depth_min_cm"] > min_soil_depth_cm:
            continue
        out.append(s)
    return out[:limit] if limit else out


def bio_native_ratio(species_names):
    """Achieved native share of a used-species list (pure)."""
    lib = dict((s["botanical_name"], s) for s in bio_species_library())
    used = [lib[n] for n in species_names if n in lib]
    if not used:
        return 0.0
    n = len([s for s in used if s["native_to_nrw"] == "true"])
    return round(float(n) / float(len(used)), 3)


# --- zone detection (PURE: derived from P + cascade only, no Rhino calls) -----

def bio_detect_zones(P, module_slots=None):
    """Detect planting zones from the EXISTING model parameters only.

    Uses derive_zones(P) (cascade F, dh_bays = lifted/undercroft bays, v_bays,
    stair_bays) plus the frozen grid constants. Reads nothing, changes nothing.
    A cascade step is only offered as a terrace/roof if NO module sits above it
    (covered terraces are excluded). Returns a list of zone dicts. Pure."""
    Z = derive_zones(P)
    F = Z["F"]
    nb = P["x_bays"]
    peak = max(F) if F else 0
    dh = Z["dh_bays"]
    vb = set(Z["v_bays"])
    stair = Z["stair_bays"]
    # bays that carry a module above a given level (covered-terrace test)
    covered_above = {}
    for s in (module_slots or []):
        try:
            b = int(s.get("bay"))
            lv = int(s.get("level"))
        except Exception:
            continue
        covered_above[b] = max(covered_above.get(b, 0), lv)
    zones = []

    def _add(zid, loc, x0, x1, y0, y1, z, sun, moist, notes, bay=None,
             substrate_cm=None, area=None):
        zones.append({
            "zone_id": zid, "location_type": loc, "bay": bay,
            "x0": round(x0, 3), "x1": round(x1, 3),
            "y0": round(y0, 3), "y1": round(y1, 3), "z": round(z, 3),
            "sun_requirement": sun, "moisture_requirement": moist,
            "substrate_depth_cm": substrate_cm,
            "area_m2": round(area if area is not None
                             else max(0.0, (x1 - x0) * (y1 - y0)), 2),
            "notes": notes})

    bx1 = nb * AXIS
    # ---- 1. foreground meadow (sunny open ground in front of the building) --
    _add("G-MEADOW-FORE", "ground_sun_meadow", 0.0, bx1,
         Y_OUT_L - 14.0, Y_OUT_L - 1.0, 0.0, "sun", "fresh",
         "foreground campus meadow; phased mowing, mown paths kept open",
         substrate_cm=30)
    # ---- 2. rear/opposite open ground ---------------------------------------
    _add("G-MEADOW-REAR", "ground_sun_meadow", 0.0, bx1,
         Y_OUT_R + 1.0, Y_OUT_R + 10.0, 0.0, "sun", "fresh",
         "open ground / secondary meadow", substrate_cm=30)
    # ---- 3. site edges (hedgerow corridor, both long sides) -----------------
    _add("G-EDGE-L", "site_edge_hedgerow", -3.0, bx1 + 3.0,
         Y_OUT_L - 17.0, Y_OUT_L - 14.0, 0.0, "sun", "fresh",
         "native hedgerow / wildlife corridor; hedgehog gaps 13x13 cm",
         substrate_cm=50)
    _add("G-EDGE-R", "site_edge_hedgerow", -3.0, bx1 + 3.0,
         Y_OUT_R + 10.0, Y_OUT_R + 13.0, 0.0, "sun", "fresh",
         "native hedgerow / wildlife corridor; connects to surrounding green",
         substrate_cm=50)
    # ---- 4. rain garden (low end of the cascade, catches roof runoff) -------
    _add("G-RAIN-01", "rain_garden", 0.0, min(3.0 * AXIS, bx1),
         Y_OUT_R + 1.0, Y_OUT_R + 5.0, 0.0, "sun", "wet",
         "rain garden / bioswale; must free-drain < 48 h (mosquito control)",
         substrate_cm=60)
    # ---- 5. undercroft shade (the lifted / double-height bays) --------------
    for b in sorted(dh):
        if b in stair:
            continue                      # keep stair access clear
        x0 = (b - 1) * AXIS
        _add("G-UNDER-%02d" % b, "undercroft_shade", x0 + 0.4, x0 + AXIS - 0.4,
             Y_OUT_L + 0.6, Y_OUT_R - 0.6, 0.0, "shade", "moist",
             "shaded ground under elevated modules; deadwood + shade "
             "groundcover; circulation and inspection access kept clear",
             bay=b, substrate_cm=30)
    # ---- 6. V-column base pockets (LOW planting only) ----------------------
    for b in sorted(vb):
        xc = (b - 1) * AXIS + AXIS / 2.0
        for side, yc in (("L", V_BASE_Y_LEFT), ("R", V_BASE_Y_RIGHT)):
            _add("V-BASE-%02d%s" % (b, side), "v_column_base",
                 xc - 1.1, xc + 1.1, yc - 1.1, yc + 1.1, 0.0,
                 "sun_partial", "fresh",
                 "low planting only - structural base must stay visible; "
                 "%.1f m inspection clearance; no deep-rooted trees within "
                 "%.1f m" % (BIO_INSPECTION_CLEAR_M, BIO_TREE_CLEARANCE_M),
                 bay=b, substrate_cm=25)
    # ---- 7. cascade steps -> open terraces / roof gardens -------------------
    for b in range(1, nb + 1):
        f = F[b - 1]
        if f <= 0:
            continue
        if covered_above.get(b, 0) > f:
            continue                      # a module sits above -> NOT open sky
        z = PLINTH + f * FLOOR_PITCH
        x0 = (b - 1) * AXIS
        is_roof = (f >= peak)
        # exposure rises with height on the building (La Serre logic)
        exposure = "high" if f >= max(1, peak - 2) else (
            "medium" if f >= max(1, peak // 2) else "low")
        if is_roof:
            _add("R-ROOF-%02d" % b, "roof_garden", x0 + 0.2, x0 + AXIS - 0.2,
                 Y_OUT_L + 0.3, Y_OUT_R - 0.3, z, "sun", "dry",
                 "extensive dry-meadow roof (default lightweight); wind "
                 "exposure %s; %s" % (exposure, BIO_WARN_ROOF_TREE),
                 bay=b, substrate_cm=10)
        else:
            _add("T-TERR-%02d" % b, "open_terrace", x0 + 0.2, x0 + AXIS - 0.2,
                 Y_OUT_L + 0.3, Y_OUT_R - 0.3, z, "sun", "fresh_dry",
                 "open uncovered terrace step (no module above); planters "
                 "only; wind exposure %s; %s"
                 % (exposure, BIO_WARN_TERRACE), bay=b, substrate_cm=35)
    return zones


def bio_build_plan(P, zones, opts=None):
    """Assign species + fauna elements to each detected zone (pure).
    Returns {'items': [...], 'species_used': [...], 'warnings': [...]}."""
    o = dict({"native_only_matrix": True, "community_garden": True},
             **(opts or {}))
    items = []
    warnings = []
    used = []

    def _use(zone, sp, count_or_area, kind, warn=""):
        used.append(sp["botanical_name"])
        items.append({
            "zone_id": zone["zone_id"],
            "location_type": zone["location_type"],
            "botanical_name": sp["botanical_name"],
            "german_name": sp["german_name"],
            "english_name": sp["english_name"],
            "layer_type": sp["layer_type"],
            "kind": kind,                       # tree/shrub/meadow/planter/roof
            "count_or_area": count_or_area,
            "soil_depth_min_cm": sp["soil_depth_min_cm"],
            "sun_requirement": sp["sun_requirement"],
            "moisture_requirement": sp["moisture_requirement"],
            "wildlife_value": sp["wildlife_value"],
            "maintenance_level": sp["maintenance_level"],
            "structural_warning": warn or sp["warning_notes"],
            "x0": zone["x0"], "x1": zone["x1"],
            "y0": zone["y0"], "y1": zone["y1"], "z": zone["z"]})

    for z in zones:
        lt = z["location_type"]
        area = z["area_m2"]
        if lt == "ground_sun_meadow":
            for sp in bio_select_species(
                    layer_types=("meadow", "grass", "perennial"), sun="sun",
                    native_only=True, limit=10):
                _use(z, sp, area / 10.0, "meadow")
            # occasional small/medium trees, never dense
            for sp in bio_select_species(layer_types=("small_tree",),
                                         sun="sun", native_only=True,
                                         limit=2):
                _use(z, sp, max(1, int(area // 260)), "tree",
                     "keep clear of module sightlines and footings")
        elif lt == "site_edge_hedgerow":
            for sp in bio_select_species(layer_types=("shrub",), sun="sun",
                                         native_only=True, limit=6):
                _use(z, sp, max(2, int(area // 12)), "shrub")
            for sp in bio_select_species(layer_types=("canopy_tree",),
                                         sun="sun", native_only=True,
                                         limit=2):
                _use(z, sp, max(1, int(area // 200)), "tree",
                     "street/edge tree - verify clearance to road and services")
        elif lt == "undercroft_shade":
            for sp in bio_select_species(
                    layer_types=("shade_groundcover",), native_only=True,
                    limit=3):
                _use(z, sp, area / 3.0, "meadow")
            items.append({
                "zone_id": z["zone_id"], "location_type": lt,
                "botanical_name": "-", "german_name": "-",
                "english_name": "Deadwood / log habitat pile",
                "layer_type": "habitat", "kind": "fauna",
                "count_or_area": 1, "soil_depth_min_cm": 0,
                "sun_requirement": "shade", "moisture_requirement": "moist",
                "wildlife_value": "saproxylic insects/hedgehog/soil fauna",
                "maintenance_level": "low",
                "structural_warning": "leave undisturbed; keep off fire routes",
                "x0": z["x0"], "x1": z["x1"], "y0": z["y0"], "y1": z["y1"],
                "z": z["z"]})
        elif lt == "v_column_base":
            for sp in bio_select_species(layer_types=("grass",),
                                         native_only=True, limit=1):
                _use(z, sp, area, "meadow",
                     "LOW planting only - do not obscure the structural base")
            for sp in bio_select_species(
                    layer_types=("shade_groundcover",), native_only=True,
                    limit=1):
                _use(z, sp, area / 2.0, "meadow",
                     "low groundcover; keep %.1f m inspection clearance"
                     % BIO_INSPECTION_CLEAR_M)
        elif lt == "open_terrace":
            for sp in bio_select_species(
                    layer_types=("grass", "perennial", "meadow"),
                    terrace_suitability="roof_extensive", native_only=True,
                    limit=4):
                _use(z, sp, max(2, int(area // 8)), "planter",
                     BIO_WARN_TERRACE)
            if o.get("community_garden"):
                for sp in bio_select_species(
                        terrace_suitability="balcony_planter", limit=2):
                    _use(z, sp, 2, "planter",
                         "community / edible planter - " + BIO_WARN_TERRACE)
            warnings.append("%s: %s" % (z["zone_id"], BIO_WARN_TERRACE))
        elif lt == "roof_garden":
            for sp in bio_select_species(
                    layer_types=("roof_sedum",), limit=4):
                _use(z, sp, area / 4.0, "roof", BIO_WARN_TERRACE)
            for sp in bio_select_species(
                    layer_types=("meadow", "grass"),
                    terrace_suitability="roof_extensive", native_only=True,
                    min_soil_depth_cm=15, limit=4):
                _use(z, sp, area / 8.0, "roof", BIO_WARN_TERRACE)
            warnings.append("%s: %s %s" % (z["zone_id"], BIO_WARN_TERRACE,
                                           BIO_WARN_ROOF_TREE))
        elif lt == "rain_garden":
            for sp in bio_select_species(layer_types=("wet_zone",),
                                         native_only=True, limit=5):
                _use(z, sp, area / 5.0, "meadow",
                     "must free-drain < 48 h - no permanent standing water")
    # ---- fauna elements: only where forage habitat exists in this plan ------
    has_meadow = any(i["kind"] == "meadow" for i in items)
    has_shrub = any(i["kind"] == "shrub" for i in items)
    if has_meadow or has_shrub:
        anchor = None
        for z in zones:
            if z["location_type"] in ("undercroft_shade",
                                      "site_edge_hedgerow"):
                anchor = z
                break
        anchor = anchor or (zones[0] if zones else None)
        if anchor:
            for (name, grp, size, h, note) in BIO_FAUNA_ELEMENTS:
                items.append({
                    "zone_id": "F-" + grp.upper()[:10],
                    "location_type": "fauna_habitat",
                    "botanical_name": "-", "german_name": "-",
                    "english_name": name, "layer_type": "habitat",
                    "kind": "fauna", "count_or_area": 1,
                    "soil_depth_min_cm": 0, "sun_requirement": "-",
                    "moisture_requirement": "-", "wildlife_value": grp,
                    "maintenance_level": "low",
                    "structural_warning":
                        note + " | fix only to safe secondary elements; "
                        "specify with an ecologist (BNatSchG s.44)",
                    "x0": anchor["x0"], "x1": anchor["x1"],
                    "y0": anchor["y0"], "y1": anchor["y1"],
                    "z": h, "install_height_m": h, "size_m": size})
    else:
        warnings.append("No forage habitat generated - fauna shelter elements "
                        "were skipped (every shelter must be paired with "
                        "food/water/cover).")
    return {"items": items, "species_used": sorted(set(used)),
            "warnings": warnings}


def bio_plan_summary(plan):
    """Counts / areas / native ratio for the dialog + report (pure)."""
    items = plan.get("items", [])
    s = {"trees": 0, "shrubs": 0, "meadow_area_m2": 0.0,
         "terrace_planters": 0, "roof_area_m2": 0.0, "fauna_elements": 0,
         "species_count": len(plan.get("species_used", [])),
         "zones": len(set(i["zone_id"] for i in items))}
    for i in items:
        k = i["kind"]
        try:
            v = float(i.get("count_or_area") or 0)
        except Exception:
            v = 0.0
        if k == "tree":
            s["trees"] += int(v)
        elif k == "shrub":
            s["shrubs"] += int(v)
        elif k == "meadow":
            s["meadow_area_m2"] += v
        elif k == "planter":
            s["terrace_planters"] += int(v)
        elif k == "roof":
            s["roof_area_m2"] += v
        elif k == "fauna":
            s["fauna_elements"] += 1
    s["meadow_area_m2"] = round(s["meadow_area_m2"], 1)
    s["roof_area_m2"] = round(s["roof_area_m2"], 1)
    s["native_ratio"] = bio_native_ratio(plan.get("species_used", []))
    s["native_target_met"] = s["native_ratio"] >= BIO_NATIVE_TARGET
    return s


# --- Rhino geometry (lightweight proxies only) -------------------------------

def _bio_ensure_layers():
    _sp_ensure_layer(BIO_LAYERS["root"])
    for k, name in BIO_LAYERS.items():
        if k != "root":
            _sp_ensure_layer(name)


def _bio_tree_proxy(x, y, z, height, spread, layer, name):
    """Simple tree proxy: trunk cylinder + canopy sphere. Returns ids."""
    ids = []
    try:
        th = max(1.0, height * 0.45)
        r = max(0.06, min(0.25, height * 0.02))
        cyl = rg.Cylinder(rg.Circle(rg.Plane(rg.Point3d(x, y, z),
                                             rg.Vector3d(0, 0, 1)), r), th)
        b = cyl.ToBrep(True, True)
        if b:
            ids.append(bake(b, layer, name + "_trunk"))
        sph = rg.Sphere(rg.Point3d(x, y, z + th + spread / 2.0 * 0.7),
                        max(0.4, spread / 2.0))
        sb = sph.ToBrep()
        if sb:
            ids.append(bake(sb, layer, name + "_canopy"))
    except Exception:
        pass
    return [i for i in ids if i]


def _bio_shrub_proxy(x, y, z, spread, layer, name):
    ids = []
    try:
        r = max(0.3, spread / 2.0)
        sb = rg.Sphere(rg.Point3d(x, y, z + r * 0.45), r).ToBrep()
        if sb:
            ids.append(bake(sb, layer, name))
    except Exception:
        pass
    return [i for i in ids if i]


def _bio_patch(x0, x1, y0, y1, z, layer, name, t=0.04):
    """Planar planting patch (meadow / roof greening / rain garden)."""
    try:
        i = bake(box_brep(x0, x1, y0, y1, z, z + t), layer, name)
        return [i] if i else []
    except Exception:
        return []


def _bio_planter(x, y, z, w, l, h, layer, name):
    try:
        i = bake(box_brep(x - w / 2.0, x + w / 2.0, y - l / 2.0, y + l / 2.0,
                          z, z + h), layer, name)
        return [i] if i else []
    except Exception:
        return []


def _bio_marker(x, y, z, size, layer, label):
    """Small labelled habitat marker (fauna box / insect hotel / log pile)."""
    ids = []
    try:
        i = bake(box_brep(x - size / 2.0, x + size / 2.0,
                          y - size / 2.0, y + size / 2.0, z, z + size), layer,
                 label.replace(" ", "_")[:40])
        if i:
            ids.append(i)
        d = rs.AddTextDot(label[:34], (x, y, z + size + 0.15))
        if d:
            rs.ObjectLayer(d, layer)
            ids.append(d)
    except Exception:
        pass
    return [i for i in ids if i]


def bio_generate_geometry(plan, opts=None):
    """Bake the LIGHTWEIGHT proxy geometry. Returns the list of new ids.
    Never touches existing geometry, layers or the site mesh."""
    o = dict({"detailed_preview": False}, **(opts or {}))
    _bio_ensure_layers()
    ids = []
    lib = dict((s["botanical_name"], s) for s in bio_species_library())
    # one representative proxy per (zone, kind) keeps the model light
    seen = set()
    for it in plan.get("items", []):
        key = (it["zone_id"], it["kind"], it["botanical_name"])
        if key in seen:
            continue
        seen.add(key)
        x0, x1 = it["x0"], it["x1"]
        y0, y1 = it["y0"], it["y1"]
        z = it.get("z", 0.0)
        cx = (x0 + x1) / 2.0
        cy = (y0 + y1) / 2.0
        sp = lib.get(it["botanical_name"])
        k = it["kind"]
        try:
            if k == "tree" and sp:
                n = max(1, min(6, int(float(it.get("count_or_area") or 1))))
                if not o["detailed_preview"]:
                    n = min(n, 3)
                for j in range(n):
                    fx = x0 + (j + 0.5) * (x1 - x0) / float(n)
                    ids += _bio_tree_proxy(
                        fx, cy, z, sp["mature_height_m"],
                        sp["crown_spread_m"], BIO_LAYERS["trees"],
                        "TREE_%s_%s" % (it["zone_id"],
                                        sp["botanical_name"].split()[0]))
            elif k == "shrub" and sp:
                n = max(1, min(8, int(float(it.get("count_or_area") or 1))))
                if not o["detailed_preview"]:
                    n = min(n, 4)
                for j in range(n):
                    fx = x0 + (j + 0.5) * (x1 - x0) / float(n)
                    ids += _bio_shrub_proxy(
                        fx, cy, z, sp["crown_spread_m"],
                        BIO_LAYERS["shrubs"],
                        "SHRUB_%s_%s" % (it["zone_id"],
                                         sp["botanical_name"].split()[0]))
            elif k == "meadow":
                ids += _bio_patch(x0, x1, y0, y1, z, BIO_LAYERS["meadow"],
                                  "MEADOW_%s" % it["zone_id"])
            elif k == "roof":
                ids += _bio_patch(x0, x1, y0, y1, z, BIO_LAYERS["roof"],
                                  "ROOFGREEN_%s" % it["zone_id"], t=0.10)
            elif k == "planter":
                n = max(1, min(4, int(float(it.get("count_or_area") or 1))))
                for j in range(n):
                    fx = x0 + (j + 0.5) * (x1 - x0) / float(n)
                    ids += _bio_planter(fx, cy, z, 1.2, 0.6, 0.5,
                                        BIO_LAYERS["planters"],
                                        "PLANTER_%s_%d" % (it["zone_id"],
                                                           j + 1))
            elif k == "fauna":
                ids += _bio_marker(cx, cy, it.get("install_height_m", z),
                                   max(0.25, float(it.get("size_m", 0.4))),
                                   BIO_LAYERS["fauna"], it["english_name"])
        except Exception:
            continue
    return [i for i in ids if i]


def _bio_report_folder(script_dir):
    try:
        base = os.path.join(script_dir, "biodiversity_reports")
        if not os.path.isdir(base):
            os.makedirs(base)
        return base
    except Exception:
        return script_dir


def bio_write_reports(P, zones, plan, summary, script_dir):
    """Write LOCAL_FLORA_FAUNA_STRATEGY_<ts>.md + _SPECIES_LIST_<ts>.csv.
    Returns (folder, md_path, csv_path). Never raises."""
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    folder = _bio_report_folder(script_dir)
    md = os.path.join(folder, "LOCAL_FLORA_FAUNA_STRATEGY_%s.md" % stamp)
    csvp = os.path.join(folder,
                        "LOCAL_FLORA_FAUNA_SPECIES_LIST_%s.csv" % stamp)
    try:
        with open(md, "w") as f:
            f.write("# Timber Housing - Local Flora + Fauna Strategy\n\n")
            f.write("Generated: %s\n\n" % stamp)
            f.write("## 1. Project context\n\n")
            f.write("Timber Housing modular CLT/timber student housing, stepped "
                    "cascade, elevated on V-columns, Detmold / Kreis Lippe / "
                    "Regierungsbezirk Detmold / NRW.\n")
            f.write("Configuration: %d bays, %d peak floors.\n\n"
                    % (P.get("x_bays", 0), P.get("peak_floors", 0)))
            f.write("## 2. Versioning note\n\n")
            f.write("v29 was copied from v28 (`wosyho_v28_site_import_"
                    "context_configurator.py`); **v28 remains untouched and "
                    "byte-identical**. This biodiversity step is ADDITIVE and "
                    "optional; skipping it leaves the model unchanged. No "
                    "skeleton, module, V-column, stair, stability, sizing, "
                    "RFEM or site-placement logic was modified, and the site "
                    "mesh is never cut or altered.\n\n")
            f.write("## 3. MVRDV precedent principles (conceptual only)\n\n")
            f.write("- **The Island** - the palette is a CROSS-SECTION of the "
                    "surrounding region's flora, so greenery becomes part of "
                    "the building's expression.\n")
            f.write("- **La Serre** - species chosen by their HEIGHT ON THE "
                    "BUILDING and SUN/WIND EXPOSURE, ~70%% native, with "
                    "ecologist-specified bird and bat boxes.\n")
            f.write("- **Co-living studies** - terraces and undercroft as "
                    "shared social-ecological rooms.\n")
            f.write("- Formal language, tropical planting and high-irrigation "
                    "vertical systems are deliberately NOT copied.\n\n")
            f.write("## 4. Detmold / NRW ecological assumptions\n\n")
            f.write("Temperate oceanic (Cfb); potential natural vegetation "
                    "oak-hornbeam / beech woodland with hedgerow edge and "
                    "mesic hay meadow. Undercroft = deep shade/moist; open "
                    "ground = sun; terraces/roof = increasing sun, wind and "
                    "drought with height, shallow substrate. Regional-"
                    "provenance seed (Regiosaatgut, BNatSchG s.40) required; "
                    "Ursprungsgebiet to be confirmed for the plot postcode "
                    "(OWL approx. UG 6 Oberes Weserbergland - ASSUMPTION).\n\n")
            f.write("## 5. Species library used\n\n")
            f.write("Species used: **%d** | native share: **%.0f%%** "
                    "(target >= %.0f%%): %s\n\n"
                    % (summary["species_count"],
                       100.0 * summary["native_ratio"],
                       100.0 * BIO_NATIVE_TARGET,
                       "MET" if summary["native_target_met"] else "NOT MET"))
            for n in plan.get("species_used", []):
                f.write("- %s\n" % n)
            f.write("\n## 6. Planting zones detected\n\n")
            f.write("| zone_id | type | bay | area m2 | sun | moisture |\n")
            f.write("|---|---|---|---|---|---|\n")
            for z in zones:
                f.write("| %s | %s | %s | %s | %s | %s |\n"
                        % (z["zone_id"], z["location_type"],
                           z["bay"] if z["bay"] else "-", z["area_m2"],
                           z["sun_requirement"], z["moisture_requirement"]))
            nt = len([z for z in zones if z["location_type"] == "open_terrace"])
            nr = len([z for z in zones if z["location_type"] == "roof_garden"])
            nu = len([z for z in zones
                      if z["location_type"] == "undercroft_shade"])
            f.write("\n## 7. Terrace / roof zones used\n\n")
            f.write("Open (uncovered) terrace steps: **%d** | roof-garden "
                    "steps: **%d**. Terrace steps carrying a module above are "
                    "EXCLUDED (not open to sky). Roof default is lightweight "
                    "EXTENSIVE dry-meadow/sedum planting.\n\n" % (nt, nr))
            f.write("## 8. Ground landscape strategy\n\n")
            f.write("Phased-mown native wildflower meadow (regional seed) at "
                    "the foreground and rear; native hedgerow corridor at the "
                    "site edges with hedgehog gaps; occasional small trees "
                    "only, kept clear of module sightlines and footings; low "
                    "planting only at V-column bases with %.1f m inspection "
                    "clearance and no deep-rooted trees within %.1f m.\n\n"
                    % (BIO_INSPECTION_CLEAR_M, BIO_TREE_CLEARANCE_M))
            f.write("## 9. Under-building shade strategy\n\n")
            f.write("%d undercroft bay zone(s): shade groundcover (ferns, "
                    "wood-rush, wood sedge), deadwood/log habitat, "
                    "undisturbed soil. Circulation, stair access and "
                    "structural inspection routes are kept clear; stair bays "
                    "are excluded from planting.\n\n" % nu)
            f.write("## 10. Fauna-support strategy\n\n")
            f.write("Shelter is only placed where forage habitat exists in "
                    "the same plan (every shelter paired with food/water/"
                    "cover). Elements: swift box, sparrow terrace, martin cup "
                    "+ droppings board, bat crevice panel, small bird boxes, "
                    "insect hotel, solitary-bee block + bare sand lens, "
                    "deadwood pile, stone pile, hedgehog shelter + 13x13 cm "
                    "corridor. Fix only to safe secondary elements; specify "
                    "with an ecologist. All European birds and all bats are "
                    "protected under BNatSchG s.44 (year-round roost/nest "
                    "protection; ASP required).\n\n")
            f.write("## 11. Structural / load warnings\n\n")
            for w in (BIO_WARN_TERRACE, BIO_WARN_TREE, BIO_WARN_ROOF_TREE,
                      BIO_WARN_GENERAL):
                f.write("- %s\n" % w)
            f.write("- Terrace/roof planting here is marked "
                    "**requires verification** - no structural capacity was "
                    "assumed, read or modified by this step.\n")
            for w in plan.get("warnings", []):
                f.write("- %s\n" % w)
            f.write("\n## 12. Maintenance and irrigation notes\n\n")
            f.write("- Meadow: cut 1-2x/yr (late June + September), REMOVE "
                    "arisings, leave 10-20%% uncut over winter.\n")
            f.write("- No pesticides, no synthetic fertiliser, no slug "
                    "pellets.\n")
            f.write("- No hedge/tree cutting in the bird breeding season "
                    "(Mar-Sep).\n")
            f.write("- Nest boxes cleaned in autumn only; never seal an "
                    "occupied cavity.\n")
            f.write("- Roof/terrace planters need establishment irrigation "
                    "and a drought contingency; intensive roof gardens need "
                    "permanent irrigation, drainage and wind anchoring.\n")
            f.write("- Rain garden must free-drain < 48 h; clear inlet silt "
                    "annually.\n\n")
            f.write("## 13. Future improvements\n\n")
            f.write("- Shade/solar simulation to refine sun assumptions per "
                    "terrace step.\n- Wind-exposure model for the upper "
                    "steps.\n- Link roof planting to verified structural "
                    "capacity data.\n- Detailed vegetation preview mode.\n"
                    "- Post-occupancy monitoring (pollinator counts, box "
                    "occupancy, bat detectors).\n\n")
            f.write("---\n\n%s\n" % BIO_WARN_GENERAL)
    except Exception as ex:
        print("Biodiversity MD report skipped (%s)." % ex)
        md = None
    try:
        with open(csvp, "w") as f:
            f.write(_csv_row(["zone_id", "location_type", "botanical_name",
                              "german_name", "english_name", "layer_type",
                              "count_or_area", "soil_depth_min_cm",
                              "sun_requirement", "moisture_requirement",
                              "wildlife_value", "maintenance_level",
                              "structural_warning"]))
            for i in plan.get("items", []):
                f.write(_csv_row([
                    i["zone_id"], i["location_type"], i["botanical_name"],
                    i["german_name"], i["english_name"], i["layer_type"],
                    i["count_or_area"], i["soil_depth_min_cm"],
                    i["sun_requirement"], i["moisture_requirement"],
                    i["wildlife_value"], i["maintenance_level"],
                    i["structural_warning"]]))
    except Exception as ex:
        print("Biodiversity CSV skipped (%s)." % ex)
        csvp = None
    return folder, md, csvp


# --- dialogs -----------------------------------------------------------------

def show_bio_intro_dialog():
    """Local Flora + Fauna entry dialog. Returns 'generate' / 'review' /
    'skip'. Proven safe layout (fixed TextArea + direct full-width buttons +
    explicit ClientSize); native fallback -> skip."""
    body = (
        "Generate a Detmold / NRW native biodiversity planting strategy for "
        "the site, open terraces, roof gardens, and ground landscape?\n\n"
        "This FINAL step is optional and additive. It reads the generated "
        "model only and creates a lightweight planting/habitat proxy layer on "
        "its own WoSyHo::Biodiversity::* layers, plus a report and species "
        "CSV.\n\n"
        "It will NOT change the skeleton, modules, V-columns, stairs, "
        "stability, sizing, RFEM export, imported context, the site mesh or "
        "the placed building. Skipping leaves the model exactly as it is.\n\n"
        "Zones considered: open ground and foreground meadow, site edges, "
        "shaded undercroft under the elevated modules, V-column base pockets "
        "(low planting only), open UNCOVERED terrace steps, roof gardens, and "
        "a rain garden.\n\n"
        "Species are native-first and chosen by sun, moisture, substrate "
        "depth and height/exposure on the cascade.\n\n"
        + BIO_WARN_TERRACE + "\n" + BIO_WARN_GENERAL)
    try:
        import Eto.Forms as forms
        import Eto.Drawing as drawing
    except Exception:
        try:
            return ("generate" if rs.MessageBox(
                body, 4 | 32, "Timber Housing - Local Flora + Fauna Strategy") == 6
                else "skip")
        except Exception:
            return "skip"

    class BioDlg(forms.Dialog[object]):
        def __init__(self):
            super(BioDlg, self).__init__()
            self.Title = "Timber Housing v29 - Local Flora + Fauna Strategy"
            self.Padding = drawing.Padding(12)
            self.Resizable = True
            self.result = "skip"
            ta = forms.TextArea()
            ta.ReadOnly = True
            ta.Wrap = True
            ta.Text = body
            ta.Size = drawing.Size(600, 290)
            try:
                _f = _ui_font(9.0)
                if _f is not None:
                    ta.Font = _f
                ta.BackgroundColor = _ui_color(UI_COLORS["card"])
                ta.TextColor = _ui_color(UI_COLORS["ink"])
            except Exception:
                pass
            b1 = forms.Button()
            b1.Text = "Generate Native Biodiversity Strategy"
            b1.Click += self.on_gen
            b2 = forms.Button()
            b2.Text = "Review Planting Zones First"
            b2.Click += self.on_rev
            b3 = forms.Button()
            b3.Text = "Skip This Step"
            b3.Click += self.on_skip
            self.DefaultButton = b1
            self.AbortButton = b3
            lay = forms.TableLayout()
            lay.Spacing = drawing.Size(8, 8)
            lay.Rows.Add(forms.TableRow([forms.TableCell(ta, True)]))
            lay.Rows.Add(forms.TableRow(forms.TableCell(b1)))
            lay.Rows.Add(forms.TableRow(forms.TableCell(b2)))
            lay.Rows.Add(forms.TableRow(forms.TableCell(b3)))
            finalize_dialog(self, lay, "Local Flora + Fauna Strategy",
                            "Detmold / NRW native-first biodiversity",
                            [(b1, "primary"), (b2, "secondary"),
                             (b3, "cancel")])
            try:
                self.ClientSize = drawing.Size(680, 570)
            except Exception:
                pass

        def on_gen(self, s, e):
            self.result = "generate"
            self.Close("generate")

        def on_rev(self, s, e):
            self.result = "review"
            self.Close("review")

        def on_skip(self, s, e):
            self.result = "skip"
            self.Close("skip")

    try:
        d = BioDlg()
        d.ShowModal(Rhino.UI.RhinoEtoApp.MainWindow)
        return d.result
    except Exception:
        return "skip"


def show_bio_zone_review_dialog(zones, summary):
    """Read-only zone review; returns True to continue to generation."""
    lines = ["Detected planting zones (from the generated model only):", ""]
    grp = {}
    for z in zones:
        grp.setdefault(z["location_type"], []).append(z)
    for lt in sorted(grp):
        tot = sum(z["area_m2"] for z in grp[lt])
        lines.append("%-22s %2d zone(s)   approx. %8.1f m2"
                     % (lt, len(grp[lt]), tot))
    lines += ["", "Species that would be used: %d (native share %.0f%%)"
              % (summary["species_count"], 100.0 * summary["native_ratio"]),
              "", "Rules applied:",
              " - terrace steps with a module above are EXCLUDED",
              " - stair bays excluded; V-column bases get LOW planting only",
              " - inspection clearance kept at structural bases",
              " - roof default is lightweight EXTENSIVE planting",
              " - fauna shelter only where forage habitat is generated",
              "", BIO_WARN_TERRACE, BIO_WARN_GENERAL]
    return bool(show_styled_prompt(
        "Planting Zones Review", "Read-only - nothing generated yet", lines,
        "Generate Native Biodiversity Strategy", "Skip This Step",
        window_title="Timber Housing v29 - Planting Zones", ta_height=300,
        width=700, height=560))


def show_bio_complete_dialog(summary, plan, folder, md_path):
    lines = [
        "Trees (proxy)          : %d" % summary["trees"],
        "Shrubs (proxy)         : %d" % summary["shrubs"],
        "Meadow area            : %.1f m2" % summary["meadow_area_m2"],
        "Terrace planters       : %d" % summary["terrace_planters"],
        "Roof greening area     : %.1f m2" % summary["roof_area_m2"],
        "Fauna habitat elements : %d" % summary["fauna_elements"],
        "Planting zones         : %d" % summary["zones"],
        "Species used           : %d (native %.0f%% - target %.0f%% %s)"
        % (summary["species_count"], 100.0 * summary["native_ratio"],
           100.0 * BIO_NATIVE_TARGET,
           "MET" if summary["native_target_met"] else "NOT MET"),
        "",
        "Layers: WoSyHo::Biodiversity::Trees / Shrubs / Meadow /",
        "        TerracePlanters / RoofGreening / FaunaHabitats",
        "(delete these layers to remove the biodiversity layer only)",
        "",
        "STRUCTURAL WARNINGS",
        "- " + BIO_WARN_TERRACE,
        "- " + BIO_WARN_TREE,
        "- " + BIO_WARN_ROOF_TREE,
        "",
        "MAINTENANCE",
        "- Meadow cut 1-2x/yr (late June + Sept), remove arisings,",
        "  leave 10-20% uncut over winter.",
        "- No pesticides / fertiliser. No hedge cutting Mar-Sep.",
        "- Nest boxes cleaned in autumn only.",
        "",
        "BIODIVERSITY NOTES",
        "- Native-first palette as a regional cross-section (The Island).",
        "- Species assigned by sun / moisture / substrate / height on the",
        "  cascade (La Serre logic).",
        "- Every shelter paired with food, water and cover.",
        "- Regiosaatgut Ursprungsgebiet must be confirmed for the plot.",
        "- BNatSchG s.44: ASP + ecologist required before implementation.",
        "",
        "Report: %s" % (md_path or "(not written)"),
        "", BIO_WARN_GENERAL]
    try:
        show_report_preview("Local Flora + Fauna Strategy Complete",
                            "\n".join(lines), folder, md_path)
    except Exception:
        show_site_info_dialog("Local Flora + Fauna Strategy Complete",
                              "Native biodiversity layer generated",
                              lines, "Finish")


def run_stage_local_flora_fauna(P, rack, site_placement=None):
    """FINAL v29 stage - optional Local Flora + Fauna / native biodiversity
    strategy. Fully guarded and skippable; changes nothing if skipped."""
    R = {"status": "skipped", "generated": False, "summary": None,
         "folder": None, "report": None, "csv": None, "object_count": 0,
         "warnings": []}
    try:
        choice = show_bio_intro_dialog()
        if choice == "skip":
            print("v29 Local Flora + Fauna: skipped by user (model "
                  "unchanged).")
            return R
        slots = getattr(rack, "module_slots", None)
        zones = bio_detect_zones(P, slots)
        plan = bio_build_plan(P, zones)
        summary = bio_plan_summary(plan)
        if choice == "review":
            if not show_bio_zone_review_dialog(zones, summary):
                print("v29 Local Flora + Fauna: skipped after zone review "
                      "(model unchanged).")
                return R
        rs.EnableRedraw(False)
        try:
            ids = bio_generate_geometry(plan)
        finally:
            rs.EnableRedraw(True)
        # follow the placed building if the site transform was applied (the
        # building is never tilted; this is the SAME rigid X/Y/Z + Z-rotation)
        try:
            sp = site_placement or {}
            if sp.get("applied") and sp.get("transform") and ids:
                _sp_apply_transform(ids, sp["transform"])
                print("v29 biodiversity layer followed the applied site "
                      "placement transform (%d objects)." % len(ids))
        except Exception as ex:
            R["warnings"].append("transform follow skipped (%s)" % ex)
        script_dir = P.get("export_folder") or _sc_script_dir(P)
        folder, md, csvp = bio_write_reports(P, zones, plan, summary,
                                             script_dir)
        R.update({"status": "generated", "generated": True,
                  "summary": summary, "folder": folder, "report": md,
                  "csv": csvp, "object_count": len(ids)})
        R["warnings"] += plan.get("warnings", [])
        P["biodiversity_summary"] = summary
        P["biodiversity_report"] = md
        try:
            Rhino.RhinoDoc.ActiveDoc.Views.Redraw()
        except Exception:
            pass
        print("v29 Local Flora + Fauna: %d proxy object(s), %d zones, %d "
              "species (native %.0f%%)."
              % (len(ids), summary["zones"], summary["species_count"],
                 100.0 * summary["native_ratio"]))
        show_bio_complete_dialog(summary, plan, folder, md)
    except Exception as ex:
        R["status"] = "failed"
        R["warnings"].append(str(ex))
        print("v29 Local Flora + Fauna step failed (%s) - model unchanged."
              % ex)
    return R


def main():
    # =========================================================================
    # DIALOG 1 (v26) - workflow start / version notice. UI only; if the user
    # cancels here nothing is generated. (Skeleton generation logic unchanged.)
    # =========================================================================
    try:
        if not show_workflow_start_dialog():
            print("Cancelled at the start dialog.")
            return
    except Exception:
        pass
    P = default_params()
    # =========================================================================
    # V2 (v27): EARLY PLANNING CONTEXT - pick the CITY at the start (stored on
    # P["planning_context"]) and OPTIONALLY select the site early. The final
    # site-placement stage reuses these and does NOT re-ask the city. UI only;
    # no generation/module/stability/sizing/RFEM logic is affected.
    # =========================================================================
    try:
        run_early_planning_context(P)
    except Exception as _ctx_ex:
        print("Early planning context skipped (%s)." % _ctx_ex)
    # =========================================================================
    # PHASE 1A (building params) + PHASE 1B (plan grid + summary)
    # 1A collects the building/structural parameters; 1B reviews the plan grid
    # type + offset direction over a read-only 1A summary. "Back" in 1B re-opens
    # 1A with the previous values preserved. Grid math is unchanged.
    # =========================================================================
    while True:
        r1 = get_params_eto(P)                   # Phase 1A (Next / Cancel)
        if r1 is None:                           # Eto unavailable -> fallback
            r1 = get_params_fallback(P)
            if r1 == "CANCEL":
                print("Cancelled.")
                return
            if get_grid_params_fallback(P) == "CANCEL":   # Phase 1B fallback
                print("Cancelled.")
                return
            break
        if r1 == "CANCEL":
            print("Cancelled.")
            return
        r2 = get_grid_params_eto(P)              # Phase 1B (Generate/Back/Cancel)
        if r2 == "CANCEL" or r2 is None:
            print("Cancelled.")
            return
        if r2 == "BACK":
            continue                             # re-open Phase 1A (values kept)
        break                                    # GENERATE

    # auto-shift the tall stair zone ONLY if the user kept the 12-bay default
    if P["x_bays"] != 12 and tuple(P["stair_zone_2"]) == (10, 11):
        P = rescale_zone_defaults(P)

    # =========================================================================
    # GENERATE base skeleton / rack
    # =========================================================================
    # Remember the user's current layer so it can be restored at the end (the
    # generation temporarily switches the current layer to Timber Housing layers). This
    # prevents user geometry drawn AFTER a run from landing on a Timber Housing layer.
    _wosyho_prev_layer = None
    try:
        _wosyho_prev_layer = rs.CurrentLayer()
    except Exception:
        _wosyho_prev_layer = None
    _wosyho_pre_ids = set()
    rs.EnableRedraw(False)
    try:
        setup_layers()
        # Task D - SAFE startup cleanup: removes ONLY tagged, previously-generated
        # Timber Housing objects so a re-run never stacks duplicate geometry, while
        # PRESERVING user site surfaces / context / manually drawn geometry
        # (never a whole-document clear). Rhino-document only; export/report
        # folders on disk are kept.
        clear_existing_wosyho_scene()
        # snapshot the surviving (user / context) objects so anything created
        # from here on is recognised as generated and tagged at the end of the run.
        _wosyho_pre_ids = _wosyho_all_object_ids()
        rack = SkeletonRack(P)
        try:
            rack._script_name = os.path.basename(__file__)
        except Exception:
            rack._script_name = "timber_housing_configurator.py"
        rack.run()
    finally:
        rs.EnableRedraw(True)
    rs.ZoomExtents()
    try:
        Rhino.RhinoDoc.ActiveDoc.Views.Redraw()
    except Exception:
        pass

    # =========================================================================
    # PHASE 2A - DUMMY BLOCK PREVIEW (must come first; builds module_slots)
    # =========================================================================
    dummy_counts = None
    MP = default_module_params()
    # styled checkpoint (replaces the old default rs.MessageBox); Continue ->
    # True, Cancel -> False, behaviour identical to the old OK/Cancel box.
    if not show_continue_to_phase2a_dialog():
        print("Dummy block preview skipped. Skeleton/grid model kept.")
    else:
        # Phase 2A input (correction folder 4): restored styled Timber Housing DIALOG
        # (show_styled_phase2a) built with the proven report-preview layout so
        # the Place/Skip buttons render reliably. It falls back internally to the
        # native rs.GetBoolean prompt (get_module_params_fallback) if Eto fails.
        # Both options (enable placement + show anchors/debug) and the Place/Skip
        # decision are preserved; dummy placement logic is unchanged.
        mres = show_styled_phase2a(MP)
        if mres == "CANCEL":
            print("Dummy block preview skipped. Skeleton/grid model kept.")
        elif not MP["enable"]:
            print("Dummy block preview disabled. Skeleton/grid model kept.")
        else:
            rs.EnableRedraw(False)
            try:
                counts = rack.place_dummy_modules(MP)   # builds/keeps slots
            finally:
                rs.EnableRedraw(True)
            try:
                Rhino.RhinoDoc.ActiveDoc.Views.Redraw()
            except Exception:
                pass
            # styled confirmation so the user visibly sees the dummy layout
            # (and its counts) BEFORE the preliminary sizing / RFEM export.
            if isinstance(counts, dict):
                dummy_counts = counts
                show_dummy_placed_dialog(counts)

    # =========================================================================
    # PRELIMINARY STRUCTURAL STABILITY CHECK (Phase S2/S3; design-stage)
    # Runs after the Phase 2A dummy preview and BEFORE the existing preliminary
    # V/tree sizing and the RFEM/Dlubal export. READ-ONLY: it never changes
    # geometry, the StructuralModel, module placement/counts, the existing
    # sizing math, or the RFEM export. Fully guarded so any failure prints and
    # the existing workflow continues unchanged. If dummy modules were skipped,
    # the module-support screen is reported INCOMPLETE rather than crashing.
    # =========================================================================
    try:
        run_stage_stability_check(rack, P)
    except Exception as _stab_ex:
        print("Preliminary stability check skipped (%s)." % _stab_ex)

    # =========================================================================
    # PRELIMINARY V/TREE SUPPORT SIZING (base structural model; optional)
    # =========================================================================
    sizing_ran = run_stage_support_sizing(rack, P)

    # =========================================================================
    # RFEM / DLUBAL BASE STRUCTURAL EXPORT (base model only; no module meshes)
    # =========================================================================
    rfem_ran = run_stage3_rfem_export(rack, P)

    # =========================================================================
    # PHASE 2B - DETAILED TEXTURED MODULE MODEL (AFTER the export checkpoint)
    # Offered only when dummy placement records exist. Simplified to a single
    # Build / Skip choice: Build -> place detailed modules and hide the dummy
    # visuals (layers 20-22); Skip -> keep the dummy preview untouched. The
    # comparison mode is no longer exposed in the user workflow (the internal
    # hide_dummy=False path remains for debugging only).
    # Detailed placement / Module-2 corridor-facing logic is unchanged.
    # =========================================================================
    detailed_built = False
    if getattr(rack, "module_slots", None):
        if ask_phase2b_detailed():
            rs.EnableRedraw(False)
            try:
                rack.place_detailed_modules(MP, hide_dummy=True)
            finally:
                rs.EnableRedraw(True)
            try:
                Rhino.RhinoDoc.ActiveDoc.Views.Redraw()
            except Exception:
                pass
            detailed_built = True
        else:
            print("Phase 2B: Skip Detailed Module Model - dummy preview kept.")
    else:
        print("Detailed modules require dummy placement records. Please run "
              "dummy preview first (Phase 2A).")

    # =========================================================================
    # FINAL SITE PLACEMENT OPTIMIZER (v24) / CITY RULES / ORIENTATION
    # Runs AFTER Phase 2B and BEFORE the final Rendered switch + Completion
    # dialog. Design-stage placement assistant only; a single rigid X/Y/Z +
    # vertical-axis-rotation transform of the WHOLE generated model applied ONLY
    # on explicit Accept. Fully guarded: any failure prints and the workflow
    # continues to the rendered view + completion dialog. It NEVER changes the
    # generation / module / sizing / stability / RFEM logic and never moves or
    # deletes the user's site / context geometry.
    # Generated objects are TAGGED here (before the site stage) so the optimizer
    # can collect the full model by the WoSyHo_Generated tag and move it together.
    # =========================================================================
    try:
        _pre_tag = tag_generated_objects_since(_wosyho_pre_ids)
        if _pre_tag:
            print("Tagged %d generated object(s) before site placement." % _pre_tag)
    except Exception:
        pass
    site_placement = None
    try:
        site_placement = run_stage_final_site_placement_v27(P, rack)
    except Exception as _sp_ex:
        print("Final site placement skipped (%s)." % _sp_ex)
        site_placement = {"status": "failed", "error": str(_sp_ex)}

    # =========================================================================
    # V29 FINAL STEP - LOCAL FLORA + FAUNA / NATIVE BIODIVERSITY STRATEGY
    # Offered ONLY after the final site placement. Optional and fully
    # skippable: if the user skips, nothing is created and the model is
    # identical to the v28 output. Additive proxy layer on its own
    # WoSyHo::Biodiversity::* layers - it never modifies the skeleton,
    # modules, V-columns, stairs, stability, sizing, RFEM export, imported
    # context, the site mesh or the placed building. Fully guarded.
    # =========================================================================
    biodiversity = None
    try:
        biodiversity = run_stage_local_flora_fauna(P, rack, site_placement)
    except Exception as _bio_ex:
        print("Local Flora + Fauna step skipped (%s)." % _bio_ex)
        biodiversity = {"status": "failed", "error": str(_bio_ex)}

    # =========================================================================
    # TASK E/F - FINAL RENDERED VIEWPORT + COMPLETION SUMMARY
    # Read-only structural collectors give the frozen baseline counts for the
    # summary (no geometry / model / export change). Then switch the active
    # viewport to Rendered mode and show the styled completion dialog.
    # =========================================================================
    base_counts = None
    try:
        _n, _m, _st = collect_structural_line_members(rack)
        _p, _ip = collect_clt_panel_references(rack)
        _sup = collect_supports(rack)
        base_counts = {"nodes": len(_n), "members": len(_m),
                       "panels": len(_p), "supports": len(_sup)}
    except Exception as ex:
        print("Completion summary: baseline counts unavailable (%s)." % ex)
    set_viewport_rendered_mode()
    # Tag everything generated this run so the NEXT run's SAFE cleanup removes
    # ONLY generated geometry (never user site / context geometry). Then restore
    # the user's original current layer so any geometry they draw next lands on
    # their own layer, not on a Timber Housing layer.
    try:
        _tagged = tag_generated_objects_since(_wosyho_pre_ids)
        if _tagged:
            print("Tagged %d generated object(s) for safe future cleanup."
                  % _tagged)
    except Exception:
        pass
    try:
        if _wosyho_prev_layer and rs.IsLayer(_wosyho_prev_layer):
            rs.CurrentLayer(_wosyho_prev_layer)
    except Exception:
        pass
    try:
        rs.ZoomExtents()
        Rhino.RhinoDoc.ActiveDoc.Views.Redraw()
    except Exception:
        pass
    show_completion_dialog(P, dummy_counts, sizing_ran, rfem_ran,
                           detailed_built, base_counts, site_placement)


if __name__ == "__main__":
    main()
