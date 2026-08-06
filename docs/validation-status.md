# Validation status

What was actually run, with the exact commands and results. Nothing here is
assumed. Where something was not tested, that is stated rather than omitted.

**Date:** 2026-08-06
**Environment:** Windows, CPython 3.13
**Rhino was not available**, so no script was executed inside Rhino.

---

## Classification scheme

| Class | Meaning |
|---|---|
| **1** | Tested in the required original environment (Rhino / Grasshopper / RFEM) |
| **2** | Syntax-checked only |
| **3** | Statically reviewed only |
| **4** | Depends on software not available here |
| **5** | Incomplete prototype |

---

## 1. Syntax compilation — all pass

**Command**

```
python -c "import py_compile, glob;
[py_compile.compile(f, doraise=True) for f in glob.glob('projects/**/*.py', recursive=True)]"
```

**Result**

```
checked: 14   failures: 0
```

| Project | Files | Result |
|---|---:|---|
| Parametric Timber Student Housing | 10 | **10 / 10 pass** |
| Programming and Simulation | 4 | **4 / 4 pass** |
| **Total** | **14** | **14 / 14 pass — zero syntax errors** |

> Compiling proves the syntax is valid. It does **not** prove the code runs
> correctly in Rhino.

---

## 2. Headless regression harness — executed

**Command**

```
cd projects/parametric-timber-student-housing
python tests/headless_validation.py
```

The harness stubs `rhinoscriptsyntax`, `scriptcontext`, `Rhino`,
`Rhino.Geometry` and `Eto`, including functional 3-D point and vector classes
with real arithmetic so the analytic collectors compute true coordinates. It
then imports the configurator and exercises its pure-Python logic.

### 2a. Core regression — PASS

**Result**

```json
{"nodes": 935, "members": 901, "panels": 12, "supports": 42,
 "M1": 22, "M1A": 28, "M2": 18, "GREEN": 32, "PASS": true}
```

On a 12 × 8 grid the frozen baseline is reproduced exactly: 935 nodes, 901
members, 12 CLT panels, 42 supports, module counts 22 / 28 / 18 / 32.

> These are **validation outputs** — a check that the geometry engine still
> produces the expected model. They are not performance figures.

### 2b. Checks — 18 of 23 pass

**Passing (18)**

`terrain_score` · `rerank_with_terrain_no_tilt` · `exclude_imported_context` ·
`report_fields_no_tilt_no_cut` · `import_report_7_files` · `completion_summary` ·
`species_library_native_first` · `select_by_conditions` · `zone_detection` ·
`covered_terrace_excluded` · `plan_rules_no_tree_on_roof_or_vbase` ·
`shelter_requires_forage` · `summary_native_target` ·
`layers_separate_from_core` · `reports_md_and_csv` · `skip_is_noop` ·
plus two further site-context checks.

**Not passing (5)**

| Check | Error |
|---|---|
| `find_site_folder` | `AssertionError('site folder not found')` |
| `inspect_folder` | `KeyError('folder')` |
| `classify_by_content` | `KeyError('scan')` |
| `obj_stl_pairing` | `KeyError('scan')` |
| `recommend_obj_preferred` | `KeyError('cls')` |

### 2c. Cause of the 5 non-passing checks

All five belong to the **site-folder inspection group** and require the external
3-D asset folder, which is not distributed with this repository — see
[`../projects/parametric-timber-student-housing/docs/ASSETS_REQUIRED.md`](../projects/parametric-timber-student-housing/docs/ASSETS_REQUIRED.md).

`find_site_folder` fails first; the remaining four cascade from it.

**These are an environmental limitation, not a code defect.** The harness was
run against the original unmodified coursework files in an isolated copy before
this repository was assembled, and produced **identical** results — the same
core regression pass and the same five non-passing checks. They were therefore
**not introduced** when the files were organised for publication.

If you obtain the assets and set `TIMBER_HOUSING_ASSETS`, these five checks are
expected to pass.

---

## 3. Per-file classification

### Parametric Timber Student Housing

| File | Class | Compiles | Notes |
|---|---|---|---|
| `tests/headless_validation.py` | **1** | Yes | Runs without Rhino by design. **Executed successfully.** |
| `src/timber_housing_configurator.py` | **2 + 4** | Yes | Core logic **executed and verified** through the harness. Full 3-D output needs Rhino. |
| `src/grasshopper_cluster_aggregator.py` | **4** | Yes | Needs Grasshopper. Not executed. |
| `src/rhino_cluster_aggregator.py` | **4** | Yes | Needs Rhino. Not executed. |
| `examples/01_habitat67_aggregation.py` | **2 + 4** | Yes | Not executed. |
| `examples/02_collision_free_placement.py` | **2 + 4** | Yes | Not executed. |
| `examples/03_courtyard_driven_placement.py` | **2 + 4** | Yes | Not executed. |
| `examples/04_deterministic_cascade_ring.py` | **2 + 4** | Yes | Not executed. |
| `examples/05_hourglass_cascade_study.py` | **2 + 4** | Yes | Not executed. |
| `examples/06_corridor_projection_system.py` | **2 + 4** | Yes | Not executed. |

### Programming and Simulation

| File | Class | Compiles | Notes |
|---|---|---|---|
| `src/pixel_perfect_living_house_generator.py` | **2 + 4** | Yes | Needs Rhino. Not executed. |
| `src/phase2_rfem_structural_export.py` | **2 + 4** | Yes | Needs Rhino **and RFEM**. Not executed. |
| `examples/parametric_envelope_system.py` | **2 + 4** | Yes | Not executed. |
| `examples/envelope_configurator_oop.py` | **2 + 4** | Yes | Not executed. |

**No file in this repository is class 5.** Two incomplete prototypes existed in
the original coursework — both truncated, neither compiling — and were
deliberately excluded rather than published as "prototypes". See the
Programming and Simulation README.

---

## 4. Import review

| Category | Finding |
|---|---|
| Third-party pip packages | **None imported anywhere** — nothing to install |
| Commercial plugins | **None imported or bundled** |
| Network libraries | **None** — no `requests`, `urllib`, `socket` or `http` |
| Rhino-provided modules | 13 of 14 files require them |
| Standard library only | 1 of 14 (`tests/headless_validation.py`) |

---

## 5. What is explicitly NOT claimed

- **No script has been run inside Rhino.** Rhino was unavailable.
- **No Grasshopper component has been run in Grasshopper.**
- **No RFEM export has been executed or validated.**
- **No geometric output has been visually inspected.** No screenshot exists.
- **No performance measurement was taken** — no timings, benchmarks or metrics.
- **No claim that any script is production-ready**, packaged or distributable.
- **No claim that Programming and Simulation has tests** — it has none.

---

## 6. Safety of what was executed

| Check | Result |
|---|---|
| Packages installed | **None** |
| Network access | **None** |
| Files written outside the workspace | **None** — the harness writes only to `tempfile.mkdtemp()` |
| Rhino / Grasshopper / RFEM invoked | **None** |
| Generated artefacts afterwards | Removed (`__pycache__`, `.pyc`, `*_result.json`); also covered by `.gitignore` |

---

## 7. How to complete validation

1. Open Rhino 8 and run each `src/` script via `RunPythonScript`; record what works and what does not.
2. Obtain the OBJ/GLB assets, set `TIMBER_HOUSING_ASSETS`, and re-run the harness — the 5 non-passing checks should then pass.
3. Load `src/grasshopper_cluster_aggregator.py` into a GHPython component and test with a closed planar curve.
4. Capture screenshots — see [`image-capture-checklist.md`](image-capture-checklist.md).
5. Update this document with the results, **including any failures**. The value of this file depends on it matching reality.
