"""
================================================================================
Parametric Timber Student Housing  -  Cluster Aggregator
================================================================================
GHPython component for Grasshopper.
Aggregates Module A (horizontal 3.5 x 5 x 3.5) and Module B (vertical 3.5 x 3.5 x 5)
into pinwheel clusters distributed around a central courtyard inside a site
boundary.

Version:  configurator v0.1
Project:  MID Integrated Design Project SoSe2026, Detmold Campus
Tools:    Rhinoceros + Grasshopper, GHPython (IronPython 2.7 compatible)

--------------------------------------------------------------------------------
INPUTS (set these on the GHPython component)
--------------------------------------------------------------------------------
  site_crv      : Curve     - closed planar curve (site boundary)
  setback       : float     - inward offset distance from site edge   (default 5.0 m)
  court_ratio   : float     - courtyard size as ratio of site         (0.0 - 0.6)
                              0.30 means courtyard ~30% of site footprint
  num_clusters  : int       - target number of clusters around ring   (e.g. 4 - 12)
  modules_per   : int       - modules per cluster                     (e.g. 6 - 10)
  seed          : int       - random seed for variation               (any integer)
  refresh       : bool      - toggle to recompute                     (True/False)

--------------------------------------------------------------------------------
OUTPUTS
--------------------------------------------------------------------------------
  buildable     : Curve         - inward-offset site boundary
  courtyard     : Curve         - central courtyard boundary (the green void)
  hor_modules   : List[Brep]    - all horizontal Module A volumes
  ver_modules   : List[Brep]    - all vertical   Module B volumes
  cluster_pts   : List[Point3d] - center point of each cluster
  common_zones  : List[Brep]    - common-zone voids per cluster (for visualization)
  info          : str           - text report of counts and parameters

--------------------------------------------------------------------------------
HOW TO USE
--------------------------------------------------------------------------------
1.  Drop a GHPython component on the canvas.
2.  Right-click input '0', rename to 'site_crv', set type-hint = Curve.
3.  Add inputs 1..6 and rename / set hints as listed above.
4.  Add outputs 0..6 with names from the OUTPUTS list above.
5.  Paste this entire script into the component editor and click OK.
6.  Wire a closed curve drawn on the XY plane in Rhino into 'site_crv'.
7.  Tune parameters with sliders.

--------------------------------------------------------------------------------
DESIGN LOGIC  (the configurator's intelligence)
--------------------------------------------------------------------------------
- Module A (horizontal): 5.0 long x 3.5 wide x 3.5 high  (one student, 1 floor)
- Module B (vertical):   3.5 long x 3.5 wide x 5.0 high  (one student, 2 floors)

- Site is offset inward by 'setback' to form the BUILDABLE region.
- A central COURTYARD is reserved (offset of buildable, scaled by court_ratio).
- The annular BUILD RING between buildable and courtyard hosts the clusters.
- Clusters are placed at polar positions on a ring midway in the annulus.
- Each cluster is a PINWHEEL of modules around a 3.5 x 3.5 common zone:
    slot 0 (E) : horizontal A, long axis pointing East
    slot 1 (N) : vertical   B
    slot 2 (W) : horizontal A, long axis pointing West
    slot 3 (S) : vertical   B
    slot 4..7  : second ring of modules, rotated 45 degrees, stacked on level 2
- Stacking rule: ~50% of slot 4..7 modules sit at level 2 with a small cantilever.
- Every placed module is checked against the buildable region; out-of-bounds
  modules are culled. This is what makes the configurator site-aware.
================================================================================
"""

import Rhino.Geometry as rg
import scriptcontext as sc
import random
import math

# ------------------------------------------------------------------------------
# 0. CONSTANTS  -  the system's DNA. Change these to change the whole settlement.
# ------------------------------------------------------------------------------
MOD_W = 3.5   # module width  (common to both A and B)
MOD_L = 5.0   # horizontal module length  (Module A long side)
MOD_H = 3.5   # horizontal module height
MOD_V = 5.0   # vertical module height    (Module B)

LEVEL_H = 3.5     # vertical step between stacked horizontal modules
CANTILEVER = 1.0  # offset for cascading deck effect when stacking

# ------------------------------------------------------------------------------
# 1. INPUT VALIDATION  -  fail fast with a useful message if inputs are missing.
# ------------------------------------------------------------------------------
def validate_inputs():
    msgs = []
    if site_crv is None:
        msgs.append("site_crv is empty. Reference a closed planar curve.")
    elif not site_crv.IsClosed:
        msgs.append("site_crv must be a CLOSED curve.")
    elif not site_crv.IsPlanar():
        msgs.append("site_crv must be PLANAR (drawn on XY).")
    return msgs

# default values if sliders are not wired
if 'setback'      not in globals() or setback      is None: setback      = 5.0
if 'court_ratio'  not in globals() or court_ratio  is None: court_ratio  = 0.30
if 'num_clusters' not in globals() or num_clusters is None: num_clusters = 6
if 'modules_per'  not in globals() or modules_per  is None: modules_per  = 8
if 'seed'         not in globals() or seed         is None: seed         = 1
if 'refresh'      not in globals() or refresh      is None: refresh      = True

errs = validate_inputs()

# ------------------------------------------------------------------------------
# 2. SITE PROCESSING  -  buildable area, courtyard, and build-ring annulus.
# ------------------------------------------------------------------------------
def offset_curve_inward(crv, dist):
    """Offset a closed planar curve inward by `dist`. Returns the largest result."""
    if dist <= 0.0:
        return crv.DuplicateCurve()
    plane = rg.Plane.WorldXY
    tol = sc.doc.ModelAbsoluteTolerance
    # try both directions; keep the one with smaller area (= inward)
    offs_pos = crv.Offset(plane,  dist, tol, rg.CurveOffsetCornerStyle.Sharp)
    offs_neg = crv.Offset(plane, -dist, tol, rg.CurveOffsetCornerStyle.Sharp)
    candidates = []
    if offs_pos: candidates.extend(offs_pos)
    if offs_neg: candidates.extend(offs_neg)
    if not candidates:
        return None
    # pick closed candidate with smallest area (= inward offset)
    best = None
    best_area = float('inf')
    for c in candidates:
        if not c.IsClosed:
            continue
        amp = rg.AreaMassProperties.Compute(c)
        if amp is None:
            continue
        if amp.Area < best_area:
            best_area = amp.Area
            best = c
    return best

def site_centroid(crv):
    amp = rg.AreaMassProperties.Compute(crv)
    return amp.Centroid if amp else rg.Point3d(0, 0, 0)

def site_area(crv):
    amp = rg.AreaMassProperties.Compute(crv)
    return amp.Area if amp else 0.0

# ------------------------------------------------------------------------------
# 3. MODULE GEOMETRY  -  build a single Module A or Module B at a given plane.
# ------------------------------------------------------------------------------
def make_module_A(plane, level=0):
    """Horizontal module: 5 (X) x 3.5 (Y) x 3.5 (Z), origin at module center base."""
    base_z = level * LEVEL_H
    box = rg.Box(plane,
                 rg.Interval(-MOD_L * 0.5, MOD_L * 0.5),
                 rg.Interval(-MOD_W * 0.5, MOD_W * 0.5),
                 rg.Interval(base_z, base_z + MOD_H))
    return box.ToBrep()

def make_module_B(plane, level=0):
    """Vertical module: 3.5 (X) x 3.5 (Y) x 5.0 (Z), origin at module center base."""
    base_z = level * LEVEL_H
    box = rg.Box(plane,
                 rg.Interval(-MOD_W * 0.5, MOD_W * 0.5),
                 rg.Interval(-MOD_W * 0.5, MOD_W * 0.5),
                 rg.Interval(base_z, base_z + MOD_V))
    return box.ToBrep()

# ------------------------------------------------------------------------------
# 4. PINWHEEL CLUSTER  -  the heart of the aggregation logic.
# ------------------------------------------------------------------------------
def build_cluster(center_pt, orient_angle_rad, n_modules, rng):
    """
    Build ONE pinwheel cluster around `center_pt`.
    Returns: (list_A, list_B, common_zone_brep)

    Pinwheel slot map (looking down, +X = 'east'):
        slot 0: horizontal A, east of common,  long axis = X
        slot 1: vertical   B, north of common
        slot 2: horizontal A, west of common,  long axis = X
        slot 3: vertical   B, south of common
        slot 4: horizontal A, NE corner, level 2, long axis = Y
        slot 5: horizontal A, NW corner, level 2, long axis = Y
        slot 6: vertical   B, SE corner
        slot 7: horizontal A, level 2 with cantilever
    """
    list_A = []
    list_B = []

    # local frame for this cluster (rotated by orient_angle_rad about Z)
    cluster_plane = rg.Plane(center_pt, rg.Vector3d.ZAxis)
    cluster_plane.Rotate(orient_angle_rad, rg.Vector3d.ZAxis)

    # ---- common zone (3.5 x 3.5 void at center) ----
    common_box = rg.Box(cluster_plane,
                        rg.Interval(-MOD_W * 0.5, MOD_W * 0.5),
                        rg.Interval(-MOD_W * 0.5, MOD_W * 0.5),
                        rg.Interval(0, MOD_H))
    common_brep = common_box.ToBrep()

    # offset distances from cluster center to module centers
    off_AX = (MOD_W * 0.5) + (MOD_L * 0.5)   # east/west of common: 1.75 + 2.5 = 4.25
    off_BY = (MOD_W * 0.5) + (MOD_W * 0.5)   # north/south of common: 1.75 + 1.75 = 3.5

    slot_specs = [
        # (type, dx, dy, rot_about_z_deg, level, cantilever_dir)
        ("A",  off_AX,    0.0,   0.0,  0, None),   # 0  east
        ("B",     0.0,  off_BY,  0.0,  0, None),   # 1  north
        ("A", -off_AX,    0.0,   0.0,  0, None),   # 2  west
        ("B",     0.0, -off_BY,  0.0,  0, None),   # 3  south
        ("A",  off_AX,  off_BY, 90.0,  1, "+x"),   # 4  NE  upper, rotated, cantilever east
        ("A", -off_AX,  off_BY, 90.0,  1, "-x"),   # 5  NW  upper, rotated, cantilever west
        ("B",  off_AX, -off_BY,  0.0,  0, None),   # 6  SE  ground
        ("A", -off_AX, -off_BY, 90.0,  1, "-x"),   # 7  SW  upper, cantilever
    ]

    for i in range(min(n_modules, len(slot_specs))):
        kind, dx, dy, rot_deg, level, cant = slot_specs[i]

        # local position in cluster frame
        local_pt = rg.Point3d(dx, dy, 0)

        # transform to world via cluster_plane
        xform = rg.Transform.PlaneToPlane(rg.Plane.WorldXY, cluster_plane)
        world_pt = rg.Point3d(local_pt)
        world_pt.Transform(xform)

        # module's own plane (orientation)
        mod_plane = rg.Plane(world_pt, rg.Vector3d.ZAxis)
        mod_plane.Rotate(orient_angle_rad + math.radians(rot_deg), rg.Vector3d.ZAxis)

        # apply cantilever offset to upper-level modules
        if cant is not None:
            cv = rg.Vector3d(0, 0, 0)
            if   cant == "+x": cv = mod_plane.XAxis * CANTILEVER
            elif cant == "-x": cv = -mod_plane.XAxis * CANTILEVER
            elif cant == "+y": cv = mod_plane.YAxis * CANTILEVER
            elif cant == "-y": cv = -mod_plane.YAxis * CANTILEVER
            mod_plane.Origin = mod_plane.Origin + cv

        # randomized stacking variation: ~30% of upper modules drop to ground
        if level == 1 and rng.random() < 0.3:
            level = 0

        if kind == "A":
            list_A.append(make_module_A(mod_plane, level=level))
        else:
            list_B.append(make_module_B(mod_plane, level=level))

    return list_A, list_B, common_brep

# ------------------------------------------------------------------------------
# 5. CLUSTER SEED DISTRIBUTION  -  place clusters around the build ring.
# ------------------------------------------------------------------------------
def cluster_seeds(courtyard_crv, buildable_crv, n_clusters):
    """
    Place n_clusters seed points on a ring midway between courtyard and
    buildable boundaries. Returns: list of (Point3d, orient_angle_rad).
    """
    centroid = site_centroid(buildable_crv)
    seeds = []

    for i in range(n_clusters):
        theta = (2.0 * math.pi * i) / n_clusters
        direction = rg.Vector3d(math.cos(theta), math.sin(theta), 0.0)

        # ray from centroid outward; hit the courtyard and buildable curves
        ray_far  = centroid + direction * 1e6
        ray = rg.Line(centroid, ray_far).ToNurbsCurve()

        tol = sc.doc.ModelAbsoluteTolerance
        # courtyard intersection
        ev_court = rg.Intersect.Intersection.CurveCurve(
            ray, courtyard_crv, tol, tol)
        # buildable intersection
        ev_build = rg.Intersect.Intersection.CurveCurve(
            ray, buildable_crv, tol, tol)

        if ev_court.Count == 0 or ev_build.Count == 0:
            continue

        pt_court = ev_court[0].PointA
        pt_build = ev_build[0].PointA
        # midpoint of the annulus along this ray = cluster seed
        seed_pt = (pt_court + pt_build) * 0.5

        # face the cluster outward (its 'east' = away from centroid)
        orient = math.atan2(direction.Y, direction.X)
        seeds.append((seed_pt, orient))

    return seeds

# ------------------------------------------------------------------------------
# 6. VALIDATION  -  cull modules that escape the buildable region.
# ------------------------------------------------------------------------------
def is_inside(curve_2d, pt_3d):
    """Test whether a point's XY projection is inside a closed planar curve."""
    test_pt = rg.Point3d(pt_3d.X, pt_3d.Y, 0)
    rel = curve_2d.Contains(test_pt, rg.Plane.WorldXY,
                            sc.doc.ModelAbsoluteTolerance)
    return rel == rg.PointContainment.Inside

def cull_outside(brep_list, buildable_crv, courtyard_crv):
    """Keep breps whose XY centroid is inside buildable AND outside courtyard."""
    keep = []
    for b in brep_list:
        amp = rg.VolumeMassProperties.Compute(b)
        if amp is None:
            continue
        c = amp.Centroid
        if is_inside(buildable_crv, c) and not is_inside(courtyard_crv, c):
            keep.append(b)
    return keep

# ------------------------------------------------------------------------------
# 7. MAIN  -  run only if inputs are valid and refresh is True.
# ------------------------------------------------------------------------------
buildable    = None
courtyard    = None
hor_modules  = []
ver_modules  = []
cluster_pts  = []
common_zones = []
info         = ""

if errs:
    info = "INPUT ERRORS:\n - " + "\n - ".join(errs)
elif refresh:
    rng = random.Random(int(seed))

    # --- step 1: buildable boundary ---
    buildable = offset_curve_inward(site_crv, float(setback))
    if buildable is None:
        info = "Setback too large or site curve invalid: no buildable area."
    else:
        # --- step 2: courtyard boundary ---
        # courtyard radius = sqrt(area * court_ratio / pi) is too coarse;
        # instead, offset buildable inward until area shrinks to ratio * site_area.
        target_court_area = site_area(buildable) * float(court_ratio)
        # binary search for offset distance that yields target courtyard area
        lo, hi = 0.5, 200.0
        courtyard = None
        for _ in range(40):
            mid = 0.5 * (lo + hi)
            cand = offset_curve_inward(buildable, mid)
            if cand is None:
                hi = mid
                continue
            a = site_area(cand)
            if a > target_court_area:
                lo = mid
            else:
                hi = mid
            courtyard = cand
        if courtyard is None:
            info = "Could not generate courtyard. Reduce court_ratio."
        else:
            # --- step 3: cluster seeds around the ring ---
            seeds = cluster_seeds(courtyard, buildable, int(num_clusters))

            # --- step 4: build each cluster ---
            for (pt, ang) in seeds:
                cluster_pts.append(pt)
                As, Bs, common = build_cluster(pt, ang,
                                                int(modules_per), rng)
                hor_modules.extend(As)
                ver_modules.extend(Bs)
                common_zones.append(common)

            # --- step 5: cull modules that fall outside the build ring ---
            hor_modules = cull_outside(hor_modules, buildable, courtyard)
            ver_modules = cull_outside(ver_modules, buildable, courtyard)

            # --- step 6: report ---
            info = (
                "Timber Housing Configurator v0.1\n"
                "------------------------\n"
                " site area      : {:.1f} m2\n"
                " buildable area : {:.1f} m2\n"
                " courtyard area : {:.1f} m2  ({:.0%} of site)\n"
                " clusters built : {}\n"
                " modules total  : {}\n"
                "   horizontal A : {}\n"
                "   vertical   B : {}\n"
                " students (~1/module)  : {}\n"
                " parameters: setback={}, court_ratio={}, "
                "num_clusters={}, modules_per={}, seed={}"
            ).format(
                site_area(site_crv),
                site_area(buildable),
                site_area(courtyard), court_ratio,
                len(cluster_pts),
                len(hor_modules) + len(ver_modules),
                len(hor_modules),
                len(ver_modules),
                len(hor_modules) + len(ver_modules),
                setback, court_ratio, num_clusters, modules_per, seed
            )
else:
    info = "refresh = False. Set refresh to True to generate."
