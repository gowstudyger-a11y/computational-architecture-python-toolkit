"""
================================================================================
Parametric Timber Student Housing  -  Cluster Aggregator
                       STANDALONE RHINO PYTHON VERSION
================================================================================
Runs directly inside Rhinoceros via _RunPythonScript.
Prompts you to pick a closed site curve, then bakes the aggregated geometry.

Usage:
  1. In Rhino, draw a closed planar curve on the XY plane (the site boundary).
  2. Run command: _RunPythonScript and select this file.
  3. Follow prompts (or accept defaults).
  4. The script bakes layers:
        WoSyHo::Site
        WoSyHo::Buildable
        WoSyHo::Courtyard
        WoSyHo::Module_A_horizontal   (yellow)
        WoSyHo::Module_B_vertical     (cyan)
        WoSyHo::CommonZones           (magenta)
        WoSyHo::ClusterCenters        (red points)
================================================================================
"""

import rhinoscriptsyntax as rs
import scriptcontext as sc
import Rhino.Geometry as rg
import System.Drawing as sd
import random
import math

# -------------------- constants (match the GH version) --------------------
MOD_W      = 3.5
MOD_L      = 5.0
MOD_H      = 3.5
MOD_V      = 5.0
LEVEL_H    = 3.5
CANTILEVER = 1.0

# -------------------- layer helper --------------------
def ensure_layer(name, color):
    full = "WoSyHo::" + name
    if not rs.IsLayer(full):
        rs.AddLayer("WoSyHo")
        rs.AddLayer(full, color)
    return full

# -------------------- geometry builders (identical to GH) --------------------
def make_module_A(plane, level=0):
    base_z = level * LEVEL_H
    return rg.Box(plane,
                  rg.Interval(-MOD_L * 0.5, MOD_L * 0.5),
                  rg.Interval(-MOD_W * 0.5, MOD_W * 0.5),
                  rg.Interval(base_z, base_z + MOD_H)).ToBrep()

def make_module_B(plane, level=0):
    base_z = level * LEVEL_H
    return rg.Box(plane,
                  rg.Interval(-MOD_W * 0.5, MOD_W * 0.5),
                  rg.Interval(-MOD_W * 0.5, MOD_W * 0.5),
                  rg.Interval(base_z, base_z + MOD_V)).ToBrep()

def offset_curve_inward(crv, dist):
    if dist <= 0.0:
        return crv.DuplicateCurve()
    plane = rg.Plane.WorldXY
    tol = sc.doc.ModelAbsoluteTolerance
    offs_pos = crv.Offset(plane,  dist, tol, rg.CurveOffsetCornerStyle.Sharp)
    offs_neg = crv.Offset(plane, -dist, tol, rg.CurveOffsetCornerStyle.Sharp)
    candidates = []
    if offs_pos: candidates.extend(offs_pos)
    if offs_neg: candidates.extend(offs_neg)
    best, best_a = None, float('inf')
    for c in candidates:
        if not c.IsClosed: continue
        amp = rg.AreaMassProperties.Compute(c)
        if amp and amp.Area < best_a:
            best_a = amp.Area
            best = c
    return best

def site_area(crv):
    amp = rg.AreaMassProperties.Compute(crv)
    return amp.Area if amp else 0.0

def site_centroid(crv):
    amp = rg.AreaMassProperties.Compute(crv)
    return amp.Centroid if amp else rg.Point3d(0, 0, 0)

def is_inside(curve_2d, pt_3d):
    test_pt = rg.Point3d(pt_3d.X, pt_3d.Y, 0)
    return curve_2d.Contains(test_pt, rg.Plane.WorldXY,
                             sc.doc.ModelAbsoluteTolerance) == rg.PointContainment.Inside

def build_cluster(center_pt, orient_angle_rad, n_modules, rng):
    list_A, list_B = [], []
    cluster_plane = rg.Plane(center_pt, rg.Vector3d.ZAxis)
    cluster_plane.Rotate(orient_angle_rad, rg.Vector3d.ZAxis)
    common_brep = rg.Box(cluster_plane,
                         rg.Interval(-MOD_W * 0.5, MOD_W * 0.5),
                         rg.Interval(-MOD_W * 0.5, MOD_W * 0.5),
                         rg.Interval(0, MOD_H)).ToBrep()
    off_AX = (MOD_W * 0.5) + (MOD_L * 0.5)
    off_BY = (MOD_W * 0.5) + (MOD_W * 0.5)
    slot_specs = [
        ("A",  off_AX,    0.0,   0.0,  0, None),
        ("B",     0.0,  off_BY,  0.0,  0, None),
        ("A", -off_AX,    0.0,   0.0,  0, None),
        ("B",     0.0, -off_BY,  0.0,  0, None),
        ("A",  off_AX,  off_BY, 90.0,  1, "+x"),
        ("A", -off_AX,  off_BY, 90.0,  1, "-x"),
        ("B",  off_AX, -off_BY,  0.0,  0, None),
        ("A", -off_AX, -off_BY, 90.0,  1, "-x"),
    ]
    for i in range(min(n_modules, len(slot_specs))):
        kind, dx, dy, rot_deg, level, cant = slot_specs[i]
        local_pt = rg.Point3d(dx, dy, 0)
        xform = rg.Transform.PlaneToPlane(rg.Plane.WorldXY, cluster_plane)
        world_pt = rg.Point3d(local_pt)
        world_pt.Transform(xform)
        mod_plane = rg.Plane(world_pt, rg.Vector3d.ZAxis)
        mod_plane.Rotate(orient_angle_rad + math.radians(rot_deg),
                         rg.Vector3d.ZAxis)
        if cant is not None:
            cv = rg.Vector3d(0, 0, 0)
            if   cant == "+x": cv =  mod_plane.XAxis * CANTILEVER
            elif cant == "-x": cv = -mod_plane.XAxis * CANTILEVER
            elif cant == "+y": cv =  mod_plane.YAxis * CANTILEVER
            elif cant == "-y": cv = -mod_plane.YAxis * CANTILEVER
            mod_plane.Origin = mod_plane.Origin + cv
        if level == 1 and rng.random() < 0.3:
            level = 0
        if kind == "A":
            list_A.append(make_module_A(mod_plane, level=level))
        else:
            list_B.append(make_module_B(mod_plane, level=level))
    return list_A, list_B, common_brep

def cluster_seeds(courtyard_crv, buildable_crv, n_clusters):
    centroid = site_centroid(buildable_crv)
    seeds = []
    tol = sc.doc.ModelAbsoluteTolerance
    for i in range(n_clusters):
        theta = (2.0 * math.pi * i) / n_clusters
        direction = rg.Vector3d(math.cos(theta), math.sin(theta), 0.0)
        ray = rg.Line(centroid, centroid + direction * 1e6).ToNurbsCurve()
        ev_c = rg.Intersect.Intersection.CurveCurve(ray, courtyard_crv,  tol, tol)
        ev_b = rg.Intersect.Intersection.CurveCurve(ray, buildable_crv, tol, tol)
        if ev_c.Count == 0 or ev_b.Count == 0: continue
        seed_pt = (ev_c[0].PointA + ev_b[0].PointA) * 0.5
        seeds.append((seed_pt, math.atan2(direction.Y, direction.X)))
    return seeds

def cull_outside(brep_list, buildable_crv, courtyard_crv):
    keep = []
    for b in brep_list:
        amp = rg.VolumeMassProperties.Compute(b)
        if amp is None: continue
        c = amp.Centroid
        if is_inside(buildable_crv, c) and not is_inside(courtyard_crv, c):
            keep.append(b)
    return keep

# -------------------- main interactive flow --------------------
def main():
    site_id = rs.GetObject("Pick the closed site curve",
                           rs.filter.curve, preselect=True)
    if not site_id: return
    if not rs.IsCurveClosed(site_id):
        print("Site curve must be closed."); return
    if not rs.IsCurvePlanar(site_id):
        print("Site curve must be planar."); return

    setback      = rs.GetReal("Setback distance (m)",      number=5.0, minimum=0.0)
    court_ratio  = rs.GetReal("Courtyard ratio (0-0.6)",   number=0.30, minimum=0.0, maximum=0.6)
    num_clusters = rs.GetInteger("Number of clusters",      number=6,   minimum=1)
    modules_per  = rs.GetInteger("Modules per cluster",     number=8,   minimum=1, maximum=8)
    seed_val     = rs.GetInteger("Random seed",             number=1)

    if None in (setback, court_ratio, num_clusters, modules_per, seed_val):
        return

    rng = random.Random(seed_val)
    site_crv = rs.coercecurve(site_id)

    buildable = offset_curve_inward(site_crv, setback)
    if buildable is None:
        print("Setback too large for this site."); return

    target_court_area = site_area(buildable) * court_ratio
    lo, hi = 0.5, 200.0
    courtyard = None
    for _ in range(40):
        mid = 0.5 * (lo + hi)
        cand = offset_curve_inward(buildable, mid)
        if cand is None:
            hi = mid; continue
        if site_area(cand) > target_court_area:
            lo = mid
        else:
            hi = mid
        courtyard = cand
    if courtyard is None:
        print("Could not generate courtyard."); return

    seeds = cluster_seeds(courtyard, buildable, num_clusters)

    hor_modules, ver_modules, common_zones, cluster_pts = [], [], [], []
    for (pt, ang) in seeds:
        cluster_pts.append(pt)
        As, Bs, common = build_cluster(pt, ang, modules_per, rng)
        hor_modules.extend(As)
        ver_modules.extend(Bs)
        common_zones.append(common)

    hor_modules = cull_outside(hor_modules, buildable, courtyard)
    ver_modules = cull_outside(ver_modules, buildable, courtyard)

    # ---- bake to layers ----
    L_site   = ensure_layer("Site",            sd.Color.LightGray)
    L_build  = ensure_layer("Buildable",       sd.Color.Gray)
    L_court  = ensure_layer("Courtyard",       sd.Color.YellowGreen)
    L_A      = ensure_layer("Module_A_horizontal", sd.Color.SandyBrown)
    L_B      = ensure_layer("Module_B_vertical",   sd.Color.SteelBlue)
    L_common = ensure_layer("CommonZones",     sd.Color.Plum)
    L_seed   = ensure_layer("ClusterCenters",  sd.Color.Red)

    rs.CurrentLayer(L_build);  sc.doc.Objects.AddCurve(buildable)
    rs.CurrentLayer(L_court);  sc.doc.Objects.AddCurve(courtyard)
    rs.CurrentLayer(L_A)
    for b in hor_modules: sc.doc.Objects.AddBrep(b)
    rs.CurrentLayer(L_B)
    for b in ver_modules: sc.doc.Objects.AddBrep(b)
    rs.CurrentLayer(L_common)
    for b in common_zones: sc.doc.Objects.AddBrep(b)
    rs.CurrentLayer(L_seed)
    for p in cluster_pts: sc.doc.Objects.AddPoint(p)

    sc.doc.Views.Redraw()
    print("Timber Housing Configurator complete.")
    print("  clusters:    {}".format(len(cluster_pts)))
    print("  horizontal:  {}".format(len(hor_modules)))
    print("  vertical:    {}".format(len(ver_modules)))
    print("  total units: {}".format(len(hor_modules) + len(ver_modules)))

if __name__ == "__main__":
    main()
