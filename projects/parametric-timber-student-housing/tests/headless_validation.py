# -*- coding: utf-8 -*-
"""
headless_validation.py

Headless validation for src/timber_housing_configurator.py.

Rhino is not required: this harness stubs the Rhino runtime so the
configurator's pure-Python logic can be exercised outside Rhino.

  1. stubs rhinoscriptsyntax / scriptcontext / Rhino / Rhino.Geometry / Eto
  2. imports the configurator
  3. 12x8 regression: nodes/members/CLT/supports + module counts
     (must still equal the frozen baseline 935/901/12/42, 22/28/18/32)
  4. smoke tests for the Local Flora + Fauna functions (pure paths)
     + the site-context functions
  5. writes a biodiversity report + CSV via the configurator's own code

Read-only towards the configurator; creates report files only.

Run from the project root:   python tests/headless_validation.py
"""

import datetime
import io
import json
import os
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
# Path updated for the repository layout: the configurator now lives in src/.
CONFIGURATOR = os.path.join(ROOT, "src", "timber_housing_configurator.py")
V28 = CONFIGURATOR  # kept as an alias so the rest of this harness is unchanged


# ---------------------------------------------------------------- stubs -----
class Dummy(object):
    def __init__(self, name="Dummy"):
        object.__setattr__(self, "_name", name)

    def __call__(self, *a, **k):
        return Dummy(self._name + "()")

    def __getattr__(self, n):
        if n.startswith("__") and n.endswith("__"):
            raise AttributeError(n)
        return Dummy(self._name + "." + n)

    def __setattr__(self, n, v):
        object.__setattr__(self, n, v)

    def __iter__(self):
        return iter([])

    def __len__(self):
        return 0

    def __bool__(self):
        return True
    __nonzero__ = __bool__

    def __getitem__(self, k):
        return Dummy(self._name + "[]")

    def __repr__(self):
        return "<Dummy %s>" % self._name


def _module(name):
    m = types.ModuleType(name)
    sys.modules[name] = m
    return m


rs = _module("rhinoscriptsyntax")


def _rs_getattr(n):
    return Dummy("rs." + n)


rs.__getattr__ = _rs_getattr
rs.AllObjects = lambda *a, **k: []
rs.ObjectsByLayer = lambda *a, **k: []
rs.IsLayer = lambda *a, **k: True
rs.AddLayer = lambda *a, **k: True
rs.CurrentLayer = lambda *a, **k: "Default"
rs.GetUserText = lambda *a, **k: None
rs.SetUserText = lambda *a, **k: True
rs.DeleteObjects = lambda ids: len(ids) if ids else 0
rs.LayerVisible = lambda *a, **k: True
rs.LayerLocked = lambda *a, **k: False
rs.EnableRedraw = lambda *a, **k: None
rs.ZoomExtents = lambda *a, **k: None
rs.Redraw = lambda *a, **k: None
rs.BoundingBox = lambda *a, **k: None
rs.ObjectLayer = lambda *a, **k: None
rs.MessageBox = lambda *a, **k: 6
rs.Command = lambda *a, **k: True
rs.ProjectPointToSurface = lambda *a, **k: None
rs.ProjectPointToMesh = lambda *a, **k: None
rs.RotateObjects = lambda *a, **k: True

sc = _module("scriptcontext")
sc.doc = Dummy("sc.doc")
sc.sticky = {}

rhino = _module("Rhino")
rhino.__getattr__ = lambda n: Dummy("Rhino." + n)
rg = _module("Rhino.Geometry")


class _GeoMeta(type):
    """Class-level attribute fallback (rg.Brep.CreateFromBox -> Dummy)."""
    def __getattr__(cls, n):
        if n.startswith("__") and n.endswith("__"):
            raise AttributeError(n)
        return Dummy(cls.__name__ + "." + n)


class DummyGeo(object, metaclass=_GeoMeta):
    def __init__(self, *a, **k):
        pass

    def __getattr__(self, n):
        if n.startswith("__") and n.endswith("__"):
            raise AttributeError(n)
        return Dummy(type(self).__name__ + "." + n)


import math as _math


class _XYZ(DummyGeo, metaclass=_GeoMeta):
    """Functional 3D point/vector stub with real math (needed so the analytic
    collectors compute true coordinates -> true baseline counts)."""

    def __init__(self, x=0.0, y=0.0, z=0.0):
        if hasattr(x, "X"):
            self.X, self.Y, self.Z = float(x.X), float(x.Y), float(x.Z)
        else:
            self.X, self.Y, self.Z = float(x), float(y), float(z)

    def __add__(self, o):
        return type(self)(self.X + o.X, self.Y + o.Y, self.Z + o.Z)

    def __sub__(self, o):
        return _rg_cache["Vector3d"](self.X - o.X, self.Y - o.Y,
                                     self.Z - o.Z)

    def __mul__(self, s):
        if isinstance(s, (int, float)):
            return type(self)(self.X * s, self.Y * s, self.Z * s)
        return self.X * s.X + self.Y * s.Y + self.Z * s.Z

    def __rmul__(self, s):
        return self.__mul__(s)

    def __neg__(self):
        return type(self)(-self.X, -self.Y, -self.Z)

    def __getitem__(self, i):
        return (self.X, self.Y, self.Z)[i]

    def __iter__(self):
        return iter((self.X, self.Y, self.Z))

    def __repr__(self):
        return "%s(%.3f,%.3f,%.3f)" % (type(self).__name__, self.X, self.Y,
                                       self.Z)

    def DistanceTo(self, o):
        return _math.sqrt((self.X - o.X) ** 2 + (self.Y - o.Y) ** 2 +
                          (self.Z - o.Z) ** 2)

    @property
    def Length(self):
        return _math.sqrt(self.X ** 2 + self.Y ** 2 + self.Z ** 2)

    def Unitize(self):
        L = self.Length
        if L > 1e-12:
            self.X, self.Y, self.Z = self.X / L, self.Y / L, self.Z / L
            return True
        return False


class _Line(DummyGeo, metaclass=_GeoMeta):
    def __init__(self, p0=None, p1=None):
        self.From = p0
        self.To = p1

    @property
    def Length(self):
        try:
            return self.From.DistanceTo(self.To)
        except Exception:
            return 0.0

    def PointAt(self, t):
        try:
            return _rg_cache["Point3d"](
                self.From.X + (self.To.X - self.From.X) * t,
                self.From.Y + (self.To.Y - self.From.Y) * t,
                self.From.Z + (self.To.Z - self.From.Z) * t)
        except Exception:
            return _rg_cache["Point3d"](0, 0, 0)


class _Plane(DummyGeo, metaclass=_GeoMeta):
    def __init__(self, *a, **k):
        self.Origin = a[0] if a else None
        self.Normal = a[1] if len(a) > 1 else None


class _Interval(DummyGeo, metaclass=_GeoMeta):
    def __init__(self, a=0.0, b=0.0):
        self.T0, self.T1 = a, b
        self.Length = b - a


_rg_cache = {}


def _rg_getattr(n):
    """Every rg.<Name> is a cached REAL class so isinstance() checks work."""
    if n.startswith("__") and n.endswith("__"):
        raise AttributeError(n)
    if n not in _rg_cache:
        _rg_cache[n] = _GeoMeta(n, (DummyGeo,), {})
    return _rg_cache[n]


for _name in ("Point3d", "Point3f", "Vector3d", "Vector3f"):
    _rg_cache[_name] = _GeoMeta(_name, (_XYZ,), {})
_rg_cache["Line"] = _GeoMeta("Line", (_Line,), {})
_rg_cache["Plane"] = _GeoMeta("Plane", (_Plane,), {})
_rg_cache["Interval"] = _GeoMeta("Interval", (_Interval,), {})
_rg_cache["Point3d"].Origin = _rg_cache["Point3d"](0, 0, 0)
_rg_cache["Vector3d"].XAxis = _rg_cache["Vector3d"](1, 0, 0)
_rg_cache["Vector3d"].YAxis = _rg_cache["Vector3d"](0, 1, 0)
_rg_cache["Vector3d"].ZAxis = _rg_cache["Vector3d"](0, 0, 1)
_rg_cache["Plane"].WorldXY = _rg_cache["Plane"](
    _rg_cache["Point3d"](0, 0, 0), _rg_cache["Vector3d"](0, 0, 1))

rg.__getattr__ = _rg_getattr
rhino.Geometry = rg
rhino.RhinoDoc = Dummy("Rhino.RhinoDoc")
rhino.UI = Dummy("Rhino.UI")


# ---------------------------------------------------------------- import ----
def load_v29():
    import importlib.util
    spec = importlib.util.spec_from_file_location("timber_housing_configurator", CONFIGURATOR)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    results = {"import": False, "regression": {}, "smoke": {}, "errors": []}
    try:
        mod = load_v29()
        results["import"] = True
        print("v29 import: OK")
    except Exception as ex:
        results["errors"].append("import failed: %r" % ex)
        print("v29 import FAILED: %r" % ex)
        _finish(results)
        return

    # ---------------------------------------------------------- regression --
    try:
        P = mod.default_params()
        rack = mod.SkeletonRack(P)
        rack.run()
        nodes, members, stats = mod.collect_structural_line_members(rack)
        panels, invalid = mod.collect_clt_panel_references(rack)
        sup = mod.collect_supports(rack)
        MP = mod.default_module_params()
        MP["enable"] = True
        counts = rack.place_dummy_modules(MP)
        reg = {"nodes": len(nodes), "members": len(members),
               "panels": len(panels), "supports": len(sup),
               "M1": counts.get("M1"), "M1A": counts.get("M1A"),
               "M2": counts.get("M2"), "GREEN": counts.get("GREEN")}
        expect = {"nodes": 935, "members": 901, "panels": 12, "supports": 42,
                  "M1": 22, "M1A": 28, "M2": 18, "GREEN": 32}
        reg["PASS"] = all(reg.get(k) == v for k, v in expect.items())
        results["regression"] = reg
        print("regression:", json.dumps(reg))
    except Exception as ex:
        results["errors"].append("regression failed: %r" % ex)
        print("regression FAILED: %r" % ex)

    # ---------------------------------------------------------- smoke -------
    smoke = results["smoke"]

    def check(name, fn):
        try:
            fn()
            smoke[name] = "PASS"
            print("smoke %-42s PASS" % name)
        except Exception as ex:
            smoke[name] = "FAIL: %r" % ex
            results["errors"].append("%s: %r" % (name, ex))
            print("smoke %-42s FAIL %r" % (name, ex))

    holder = {}

    def t_folder():
        f = mod._sc_find_site_folder(ROOT)
        assert f and os.path.isdir(f), "site folder not found"
        holder["folder"] = f

    def t_inspect():
        scan = mod.inspect_site_surroundings_folder(holder["folder"])
        assert scan.get("objs"), "no OBJ scanned"
        holder["scan"] = scan

    def t_classify():
        cls = mod.classify_site_geometry_files(holder["scan"])
        roles = set(c["role"] for c in cls.values())
        assert "site_plot" in roles, "site_plot not classified"
        assert "full_combined" in roles, "full_combined not classified"
        assert "surrounding_buildings" in roles, "buildings not classified"
        assert "site_road" in roles, "site_road not classified"
        holder["cls"] = cls

    def t_pairing():
        pr = mod.pair_obj_stl_files(holder["scan"], holder["cls"])
        assert pr and all(p.get("matches_obj") for p in pr), \
            "STL->OBJ size pairing failed"
        holder["pairing"] = pr

    def t_recommend():
        rec = mod.recommend_site_import_files(holder["cls"],
                                              holder["pairing"])
        for role in ("site_plot", "site_road", "surrounding_buildings"):
            assert role in rec, "no recommendation for " + role
            assert rec[role]["format"] == "OBJ", role + " not OBJ"
        holder["rec"] = rec

    def t_terrain_score():
        assert abs(mod._sc_terrain_score(0.0) - 1.0) < 1e-9
        assert mod._sc_terrain_score(1.0) == 0.5
        assert mod._sc_terrain_score(-5) == 1.0

    def t_rerank():
        cands = [{"cx": 0.0, "cy": 0.0, "rot": 0, "fits": True, "total": 1.0},
                 {"cx": 5.0, "cy": 5.0, "rot": 0, "fits": True, "total": 0.9}]
        result = {"candidates": cands, "best": cands[0], "top5": cands[:2]}
        site = {"id": "fake", "max": (0.0, 0.0, 10.0)}
        out = mod._sc_rerank_with_terrain(result, site, (10.0, 20.0))
        c = out["candidates"][0]
        assert c["terrain_delta_z"] == 0.0, "fallback z should be flat"
        assert c["terrain_score"] == 1.0
        assert abs(c["z_placement"] - (10.0 + mod.SITE_CTX_Z_CLEARANCE_M)) \
            < 1e-9
        assert out.get("terrain_reranked") is True
        assert out["best"]["total_with_terrain"] >= \
            out["candidates"][1]["total_with_terrain"]

    def t_exclude():
        kept, excl = mod._sc_exclude_imported_context(["a", "b"])
        assert kept == ["a", "b"] and excl == 0
        rs.GetUserText = lambda oid, k=None: (
            mod.SITE_CTX_TAG_VAL if (oid == "b" and
                                     k == mod.SITE_CTX_TAG_KEY) else None)
        kept, excl = mod._sc_exclude_imported_context(["a", "b"])
        rs.GetUserText = lambda *a, **k: None
        assert kept == ["a"] and excl == 1

    def t_report_fields():
        R = {"best": {"terrain_delta_z": 0.4, "z_placement": 3.2},
             "terrain": {"diff": 0.4}, "site_is_uneven": True,
             "v28_context": {"site_plot_imported": "yes (1 obj)"}}
        d = mod._sc_report_fields({}, R)
        assert d["model_tilted"] is False
        assert d["terrain_cut"] is False
        assert d["site_mesh_modified"] is False
        assert d["selected_candidate_terrain_delta_z"] == 0.4
        assert "Z-axis rotation only" in d["building_transform_allowed"]

    def t_import_report():
        import tempfile
        tmp = tempfile.mkdtemp(prefix="timber_housing_smoke_")
        P = {}
        ctx = mod._sp_get_planning_context(P)
        ctx["imported_context"] = {
            "folder": tmp,
            "inspection": {"files": [{"name": "x.obj", "kind": "OBJ",
                                      "size_bytes": 1}]},
            "classification": {"x.obj": {"role": "site_plot",
                                         "confidence": "high",
                                         "reasons": ["test"]}},
            "imported": {"site_plot": {"imported": True, "count": 1,
                                       "ids": ["id1"], "file": "x.obj",
                                       "layer": "L"}}}
        ctx["site_analysis"] = {"site_is_uneven": True, "site_min_z": 0.0,
                                "site_max_z": 2.0,
                                "site_elevation_range": 2.0,
                                "road_context_exists": True}
        folder = mod._sc_write_import_report(P)
        assert folder and os.path.isdir(folder)
        files = os.listdir(folder)
        for want in ("SITE_CONTEXT_IMPORT_REPORT.md",
                     "imported_context_inventory.csv",
                     "imported_objects.csv", "site_analysis.json",
                     "road_context_analysis.json",
                     "surroundings_context_analysis.json",
                     "recommended_placement_inputs.json"):
            assert want in files, "missing " + want

    def t_completion_summary():
        P = {}
        ctx = mod._sp_get_planning_context(P)
        ctx["imported_context"] = {"imported": {
            "site_plot": {"imported": True, "count": 3}}}
        s = mod._sc_completion_summary(P)
        assert s["site_plot_imported"].startswith("yes")
        assert s["site_road_imported"] == "no"

    # ---- carried-over v28 checks (must still pass in v29) ----------------
    check("v28 find_site_folder", t_folder)
    check("v28 inspect_folder", t_inspect)
    check("v28 classify_by_content", t_classify)
    check("v28 obj_stl_pairing", t_pairing)
    check("v28 recommend_obj_preferred", t_recommend)
    check("v28 terrain_score", t_terrain_score)
    check("v28 rerank_with_terrain_no_tilt", t_rerank)
    check("v28 exclude_imported_context", t_exclude)
    check("v28 report_fields_no_tilt_no_cut", t_report_fields)
    check("v28 import_report_7_files", t_import_report)
    check("v28 completion_summary", t_completion_summary)

    # ================= NEW v29 LOCAL FLORA + FAUNA CHECKS =================
    bio = {}

    def t_bio_library():
        lib = mod.bio_species_library()
        assert len(lib) >= 50, "species library too small: %d" % len(lib)
        for s in lib:
            for fld in mod.BIO_FIELDS:
                assert fld in s, "missing field %s" % fld
        nat = [s for s in lib if s["native_to_nrw"] == "true"]
        assert float(len(nat)) / len(lib) >= 0.85, "library not native-first"
        names = [s["botanical_name"] for s in lib]
        assert len(names) == len(set(names)), "duplicate species"
        for bad in ("Palm", "Ficus", "Bougainvillea", "Musa"):
            assert not any(bad.lower() in n.lower() for n in names), bad
        bio["lib"] = lib

    def t_bio_select_conditions():
        shade = mod.bio_select_species(layer_types=("shade_groundcover",))
        assert shade and all(s["sun_requirement"] == "shade" for s in shade)
        roof = mod.bio_select_species(layer_types=("roof_sedum",))
        assert roof and all(s["soil_depth_min_cm"] <= 12 for s in roof)
        wet = mod.bio_select_species(layer_types=("wet_zone",))
        assert wet and all(s["moisture_requirement"] == "wet" for s in wet)
        low = mod.bio_select_species(max_height_m=0.6)
        assert low and all(s["mature_height_m"] <= 0.6 for s in low)

    def t_bio_zones():
        P = mod.default_params()
        zones = mod.bio_detect_zones(P)
        assert zones, "no zones detected"
        types = set(z["location_type"] for z in zones)
        for want in ("ground_sun_meadow", "site_edge_hedgerow",
                     "undercroft_shade", "v_column_base", "open_terrace",
                     "roof_garden", "rain_garden"):
            assert want in types, "missing zone type " + want
        Z = mod.derive_zones(P)
        roofs = [z for z in zones if z["location_type"] == "roof_garden"]
        terrs = [z for z in zones if z["location_type"] == "open_terrace"]
        zr = min(z["z"] for z in roofs)
        assert all(t["z"] < zr for t in terrs), "terrace above roof level"
        und = set(z["bay"] for z in zones
                  if z["location_type"] == "undercroft_shade")
        assert not (und & set(Z["stair_bays"])), "stair bay planted"
        vz = [z for z in zones if z["location_type"] == "v_column_base"]
        assert vz and all(z["bay"] in set(Z["v_bays"]) for z in vz)
        assert all(z["area_m2"] <= 6.0 for z in vz), "V-base pocket too big"
        bio["zones"] = zones
        bio["P"] = P

    def t_bio_covered_terrace_excluded():
        P = mod.default_params()
        base = mod.bio_detect_zones(P)
        Z = mod.derive_zones(P)
        peak = max(Z["F"])
        target = None
        for b in range(1, P["x_bays"] + 1):
            if Z["F"][b - 1] < peak:
                target = b
                break
        assert target, "no sub-peak bay to test"
        ids0 = set(z["zone_id"] for z in base)
        assert "T-TERR-%02d" % target in ids0, "test bay not a terrace"
        slots = [{"bay": target, "level": Z["F"][target - 1] + 1}]
        cov = mod.bio_detect_zones(P, slots)
        ids1 = set(z["zone_id"] for z in cov)
        assert "T-TERR-%02d" % target not in ids1, "covered terrace kept"
        assert len(ids1) == len(ids0) - 1, "unexpected zone change"

    def t_bio_plan_and_rules():
        P, zones = bio["P"], bio["zones"]
        plan = mod.bio_build_plan(P, zones)
        items = plan["items"]
        assert items, "empty plan"
        roof_ids = set(z["zone_id"] for z in zones
                       if z["location_type"] == "roof_garden")
        assert not [i for i in items
                    if i["zone_id"] in roof_ids and i["kind"] == "tree"], \
            "tree placed on a roof zone"
        vb_ids = set(z["zone_id"] for z in zones
                     if z["location_type"] == "v_column_base")
        assert not [i for i in items
                    if i["zone_id"] in vb_ids and i["kind"] == "tree"], \
            "tree placed at a V-column base"
        terr_ids = set(z["zone_id"] for z in zones
                       if z["location_type"] in ("open_terrace",
                                                 "roof_garden"))
        for i in items:
            if i["zone_id"] in terr_ids:
                assert i["structural_warning"], "no structural warning"
        und_ids = set(z["zone_id"] for z in zones
                      if z["location_type"] == "undercroft_shade")
        for i in items:
            if i["zone_id"] in und_ids and i["botanical_name"] != "-":
                assert i["sun_requirement"] == "shade", "sun sp in shade zone"
        assert [i for i in items if i["kind"] == "fauna"], "no fauna elements"
        assert [i for i in items if i["kind"] == "meadow"], "no forage"
        bio["plan"] = plan

    def t_bio_shelter_needs_forage():
        only_roof = [z for z in bio["zones"]
                     if z["location_type"] == "roof_garden"]
        plan = mod.bio_build_plan(bio["P"], only_roof)
        assert not [i for i in plan["items"] if i["kind"] == "fauna"], \
            "shelter emitted without forage habitat"
        assert any("shelter" in w for w in plan["warnings"])

    def t_bio_summary_native_target():
        s = mod.bio_plan_summary(bio["plan"])
        for k in ("trees", "shrubs", "meadow_area_m2", "terrace_planters",
                  "roof_area_m2", "fauna_elements", "species_count",
                  "zones", "native_ratio", "native_target_met"):
            assert k in s, "summary missing " + k
        assert s["species_count"] > 0 and s["meadow_area_m2"] > 0
        assert s["native_ratio"] >= mod.BIO_NATIVE_TARGET, \
            "native ratio %.2f below target" % s["native_ratio"]
        assert s["native_target_met"] is True
        bio["summary"] = s

    def t_bio_layers_separate():
        core = set(n for (n, _c) in mod.LAYERS)
        for k, name in mod.BIO_LAYERS.items():
            assert name.startswith("WoSyHo::Biodiversity"), name
            assert name not in core, "biodiversity layer collides with core"

    def t_bio_reports():
        import tempfile
        tmp = tempfile.mkdtemp(prefix="timber_housing_bio_")
        folder, md, csvp = mod.bio_write_reports(
            bio["P"], bio["zones"], bio["plan"], bio["summary"], tmp)
        assert md and os.path.isfile(md), "MD report not written"
        assert csvp and os.path.isfile(csvp), "CSV not written"
        assert os.path.basename(md).startswith("LOCAL_FLORA_FAUNA_STRATEGY_")
        assert os.path.basename(csvp).startswith(
            "LOCAL_FLORA_FAUNA_SPECIES_LIST_")
        txt = io.open(md, encoding="utf-8").read()
        for want in ("Versioning note", "v28 remains untouched", "MVRDV",
                     "La Serre", "structural load verification",
                     "Regiosaatgut", "Maintenance"):
            assert want.lower() in txt.lower(), "report missing: " + want
        head = io.open(csvp, encoding="utf-8").read().splitlines()[0]
        for col in ("zone_id", "location_type", "botanical_name",
                    "german_name", "english_name", "layer_type",
                    "count_or_area", "soil_depth_min_cm", "sun_requirement",
                    "moisture_requirement", "wildlife_value",
                    "maintenance_level", "structural_warning"):
            assert col in head, "CSV missing column " + col
        results["bio_report"] = md
        print("   biodiversity report ->", md)

    def t_bio_skip_creates_nothing():
        orig = mod.show_bio_intro_dialog
        mod.show_bio_intro_dialog = lambda: "skip"
        try:
            R = mod.run_stage_local_flora_fauna(mod.default_params(), None,
                                                None)
        finally:
            mod.show_bio_intro_dialog = orig
        assert R["status"] == "skipped" and R["generated"] is False
        assert R["object_count"] == 0, "skip created objects"

    check("v29 species_library_native_first", t_bio_library)
    check("v29 select_by_conditions", t_bio_select_conditions)
    check("v29 zone_detection", t_bio_zones)
    check("v29 covered_terrace_excluded", t_bio_covered_terrace_excluded)
    check("v29 plan_rules_no_tree_on_roof_or_vbase", t_bio_plan_and_rules)
    check("v29 shelter_requires_forage", t_bio_shelter_needs_forage)
    check("v29 summary_native_target", t_bio_summary_native_target)
    check("v29 layers_separate_from_core", t_bio_layers_separate)
    check("v29 reports_md_and_csv", t_bio_reports)
    check("v29 skip_is_noop", t_bio_skip_creates_nothing)

    _finish(results)


def _finish(results):
    p = os.path.join(HERE, "v29_headless_validation_result.json")
    with open(p, "w") as f:
        json.dump(results, f, indent=1)
    print("\nresult json:", p)
    ok = (results.get("import") and
          (results.get("regression") or {}).get("PASS") and
          all(v == "PASS" for v in (results.get("smoke") or {}).values()))
    print("OVERALL:", "PASS" if ok else "CHECK FAILURES ABOVE")


if __name__ == "__main__":
    main()
