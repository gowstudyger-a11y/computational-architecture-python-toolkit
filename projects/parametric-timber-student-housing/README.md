# Parametric Timber Student Housing

A parametric **timber skeleton / rack configurator** for a multi-storey student
housing block, written in Python for Rhino 8.

**Academic context:** TH OWL, *Computational Design 2* — MID Integrated Design
Project, SoSe 2026, Detmold campus.

---

## Objective

Design a student housing block as a **timber rack** — a repeating structural
skeleton of columns, beams and CLT slabs — into which prefabricated dwelling
modules are placed. Rather than drawing one fixed building, the configurator
expresses the design as rules, so that grid size, height distribution, module mix
and site placement can be varied and regenerated.

---

## Generation approach

The system is **rule-based and largely deterministic**. Geometry is derived from
an axis grid measured from a reference model rather than from arbitrary values.

### Grid constants

Units are metres. All coordinates are **member centreline / axis** coordinates.

| Value | Dimension | Derivation |
|---|---|---|
| Axis-to-axis grid | 3.8 m | 3.5 m clear + 0.3 m member |
| Floor-to-floor | 3.8 m | 3.5 m clear + 0.3 m structure |
| Member section | 0.3 m square | column / beam / branch |
| Corridor band | 2.3 m | 2.0 m clear + 0.3 m member |
| Plinth height | 0.7 m | measured 0.65–0.7 |
| Slab thickness | 0.3 m | CLT plate |

### What it produces

- Structural grid — columns, beams and branches
- CLT slabs, plinth and support geometry
- Module placement — three types (A, A1, B) fitted into the rack
- Cascading massing — building height varies across the plan by rule
- Site context — buildable-zone setback following the real site outline, with a placement preview
- Local flora and fauna — a native-first planting strategy for the Detmold / Kreis Lippe / NRW region, exported as a Markdown report and CSV

---

## File organisation

```
src/
  timber_housing_configurator.py     Main configurator — run this in Rhino
  grasshopper_cluster_aggregator.py  GHPython component (Grasshopper)
  rhino_cluster_aggregator.py        Rhino-Python counterpart of the above
tests/
  headless_validation.py             Regression harness — runs WITHOUT Rhino
examples/
  01_habitat67_aggregation.py        Stepped mass with sky-courts (Habitat-'67 reference)
  02_collision_free_placement.py     Adds footprint tracking so modules reserve cells
  03_courtyard_driven_placement.py   Courtyard placed first as a void; modules ring it
  04_deterministic_cascade_ring.py   Randomness removed; rule-based cascading ring
  05_hourglass_cascade_study.py      Four-corner-peak / hourglass cascade study
  06_corridor_projection_system.py   Corridor projection system
docs/
  ASSETS_REQUIRED.md                 External 3-D files this project reads
images/                              Screenshots — none captured yet
```

### About `examples/`

These are a **development sequence**, not six alternative scripts. The numbering
follows how the aggregation strategy evolved, and each stage's purpose is taken
from that file's own header — for instance, stage 02 documents the
footprint-tracking fix for stage 01's module collisions, and stage 03 describes
itself as a "fundamental rethink" that places the courtyard first.

One caveat, stated plainly: some later files in the original coursework carried
**stale header titles** (a v20 file still titled itself v16m). File contents and
sizes differ, so they are genuinely distinct stages, but the author did not
always update the internal title.

---

## Main script roles

| Script | Role |
|---|---|
| `timber_housing_configurator.py` | The complete configurator. Collects input through a sequence of Eto dialogs, then builds the rack, slabs, modules, site context and planting. |
| `grasshopper_cluster_aggregator.py` | A GHPython component that aggregates Module A and Module B into pinwheel clusters around a central courtyard inside a site boundary. Inputs: `site_crv`, `setback`, `court_ratio`, `num_clusters`, `modules_per`, `seed`, `refresh`. |
| `rhino_cluster_aggregator.py` | The same aggregation logic as a standalone Rhino-Python script, showing the port between the two environments. |
| `headless_validation.py` | Stubs the Rhino API so the configurator's pure-Python logic can be exercised without Rhino. |

---

## User interface

All input is collected through **Eto dialogs** inside Rhino — no command-line
arguments. The dialogs use sliders, list boxes and grouped panels, with a
consistent card-style layout.

Every styling helper is wrapped in `try`/`except`: if a particular Rhino build
rejects a styling property, the dialog still displays. Styling never breaks
working logic. Rounded corners are not available in Eto, so the card effect is
approximated with background colours, padding and grouped panels.

---

## Inputs and outputs

**Inputs** — grid dimensions in bays, peak and base floor counts, peak corner
(NE/NW/SE/SW), courtyard size, cascade sharpness, city/location for planning
context, and a site boundary curve. Optionally, external OBJ module geometry.

**Outputs** — Rhino geometry organised onto named layers; a structural data
collection (nodes, members, panels, supports); a biodiversity planting report in
Markdown; a species CSV.

---

## Requirements

| Requirement | Detail |
|---|---|
| Rhinoceros | **8** (Rhino 7 may work — unverified) |
| Python | 3.x via Rhino's script editor |
| Grasshopper | Only for `grasshopper_cluster_aggregator.py` |
| Pip packages | **None** |
| External assets | OBJ / GLB module geometry — **not included**, see `docs/ASSETS_REQUIRED.md` |

Written to remain **IronPython 2.7 tolerant** so it runs under both Rhino script
engines.

---

## How to run

**Configurator** (requires Rhino 8):

1. Open Rhino 8
2. Run `RunPythonScript`
3. Select `src/timber_housing_configurator.py`
4. Follow the dialogs

**Grasshopper aggregator:** paste `src/grasshopper_cluster_aggregator.py` into a
GHPython component and wire the inputs listed above.

**Validation harness** (no Rhino needed):

```
cd projects/parametric-timber-student-housing
python tests/headless_validation.py
```

**To inspect without running anything**, start with
`src/timber_housing_configurator.py` — the header documents the coordinate
convention and grid constants, and the file is organised into numbered sections.

---

## Validation

The harness stubs `rhinoscriptsyntax`, `scriptcontext`, `Rhino`,
`Rhino.Geometry` and `Eto` — including functional 3-D point and vector classes
with real arithmetic, so the analytic collectors compute true coordinates — then
imports the configurator and exercises its logic.

### Core regression — pass

On a 12 × 8 grid the harness reproduces the frozen baseline exactly:

| Output | Value |
|---|---:|
| Nodes | **935** |
| Members | **901** |
| CLT elements | **12** |
| Supports | **42** |
| Module A | 22 |
| Module A1 | 28 |
| Module B | 18 |
| Green / common | 32 |

> These are **validation outputs from the included harness** — a check that the
> geometry engine still produces the expected model. They are not performance
> figures and not a measure of quality.

### Checks — 18 of 23 pass

**Passing (18):** terrain scoring · terrain re-ranking · imported-context
exclusion · report fields · import report · completion summary · native-first
species library · condition-based species selection · zone detection ·
covered-terrace exclusion · planting rules · shelter/forage dependency ·
native-target summary · biodiversity layers kept separate from core layers ·
Markdown + CSV report generation · skip-is-noop · and two further site-context
checks.

**Not passing (5):** `find_site_folder` · `inspect_folder` ·
`classify_by_content` · `obj_stl_pairing` · `recommend_obj_preferred`

### Why those 5 do not pass

They require the external 3-D asset folder, which is **not distributed with this
repository**. `find_site_folder` raises `AssertionError('site folder not found')`
and the other four cascade from it.

**The same five checks failed identically in the original unmodified source.**
This was verified by running the harness against the original files in an
isolated copy before this repository was prepared. They are a consequence of the
missing assets, and were **not introduced when the code was organised for
publication**.

---

## Known limitations

- **External assets are not included.** Without them the configurator falls back to procedural block placeholders — correct in position and dimension, simplified in form. See `docs/ASSETS_REQUIRED.md`.
- **Rhino is required** for everything except the harness.
- **The configurator has not been executed inside Rhino** during preparation, so its Rhino runtime behaviour is unverified here.
- The site-inspection functions cannot be exercised without the asset folder.
- **No screenshots yet.**
- This is coursework — not packaged, distributed or production software.

---

## A note on internal identifiers

Some internal code identifiers keep the abbreviation used in the original
academic implementation — Rhino root and sublayer names, a few class names and
function names.

They were **left unchanged deliberately**. Those strings are used to create and
then find Rhino layers at runtime; the root layer name in particular anchors an
entire sublayer hierarchy. Renaming them carried a genuine risk of breaking
layer resolution for no functional benefit, so the code retains its original
identifiers while the project's public title is *Parametric Timber Student
Housing*.

The regression harness confirms the layer structure is intact: the
`layers_separate_from_core` check passes.
