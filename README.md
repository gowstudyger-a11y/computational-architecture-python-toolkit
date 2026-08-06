# Computational Architecture Python Toolkit

Python tools for parametric architectural design, written for **McNeel
Rhinoceros** and **Grasshopper**.

This repository collects computational-design work from my Master's studies in
Integrated Design / Computational Architecture at TH OWL, Germany. Each project
generates architectural geometry procedurally — structural grids, timber
skeletons, envelope build-ups, module aggregation and site analysis — driven by
user input through Rhino's Eto dialog framework.

The aim is to show how design intent can be expressed as rules and parameters
rather than drawn by hand, and to make that logic readable.

---

## Projects

| Project | What it generates | Tested |
|---|---|---|
| **[Parametric Timber Student Housing](projects/parametric-timber-student-housing/)** | A timber skeleton / rack system for a multi-storey student housing block: structural grid, CLT slabs, module placement, site context and native-species planting. | Core logic verified by an included headless harness. Full 3-D output needs Rhino. |
| **[Programming and Simulation](projects/programming-and-simulation/)** | A single-family house: site, structure, layered CLT floors and walls, façade, DIN 18065 staircase, plus a structural-analysis export stage and two envelope systems. | Syntax-checked. Requires Rhino to run. |

---

## What this work demonstrates

- **Parametric modelling** — geometry driven by parameters and rules rather than manual drawing
- **Architectural geometry** — grid systems, module aggregation, footprint/collision tracking, projection onto surfaces
- **Design automation** — multi-stage building models generated from a sequence of user inputs
- **Rhino / RhinoCommon scripting** — `rhinoscriptsyntax`, `Rhino.Geometry`, `scriptcontext`
- **Grasshopper workflows** — a GHPython component alongside its Rhino-Python counterpart, showing the same logic in both environments
- **Interactive design tools** — Eto dialogs, sliders, list boxes and styled panels inside Rhino
- **Envelope generation** — layered wall and floor build-ups; two contrasting implementations, one procedural and one object-oriented
- **Timber systems** — CLT slabs, glulam specification, timber strength grades (C24, GL24h) per EN 14080 / DIN EN 1995-1-1
- **Rule-based massing** — a cellular BUILT / GARDEN / EMPTY classification where terraces emerge at boundaries and isolated clusters are downgraded to keep the mass connected
- **Headless testing** — a harness that stubs the Rhino runtime so core logic can be exercised without Rhino

---

## Repository structure

```
computational-architecture-python-toolkit/
├── README.md
├── .gitignore
├── docs/
│   ├── compatibility.md              Software, libraries, runtime requirements
│   ├── validation-status.md          What was tested, and what was not
│   ├── repository-structure.md       Why the repository is laid out this way
│   └── image-capture-checklist.md    Screenshots still to be captured
└── projects/
    ├── parametric-timber-student-housing/
    │   ├── README.md
    │   ├── src/        Main configurator, Grasshopper + Rhino aggregators
    │   ├── tests/      Headless validation harness
    │   ├── examples/   Six numbered development stages
    │   ├── docs/       External asset requirements
    │   └── images/
    └── programming-and-simulation/
        ├── README.md
        ├── src/        House generator, structural export
        ├── examples/   Two envelope implementations
        └── images/
```

See [`docs/repository-structure.md`](docs/repository-structure.md) for the
reasoning behind this layout.

---

## Compatibility

| Requirement | Version | Needed for |
|---|---|---|
| Rhinoceros | 8 (7 may work — **unverified**) | Every script except the test harness |
| Python | 3.x via Rhino's script editor | All scripts |
| Grasshopper | Bundled with Rhino | One GHPython component |
| RFEM | Version **UNKNOWN** — not stated in the source | The structural export stage only |
| CPython | 3.x standalone | The headless harness only |

**No third-party pip packages are used anywhere.** No commercial plugins are
required or bundled. No code in this repository makes network requests.

The timber-housing code is deliberately written to stay **IronPython 2.7
tolerant** — no f-strings, no walrus operator, explicit float division — so it
runs under both Rhino script engines. That constraint is stated in the original
source and was kept.

Full detail in [`docs/compatibility.md`](docs/compatibility.md).

---

## Validation summary

| Check | Result |
|---|---|
| Syntax compilation | **14 / 14 files pass** |
| Headless harness executed | **Yes** |
| Core regression | **Pass** — 935 nodes, 901 members, 12 CLT elements, 42 supports |
| Harness checks | **18 of 23 pass** |
| Scripts run inside Rhino | **No** — Rhino was not available |

The 5 non-passing checks all belong to the site-folder inspection group and
require external 3-D asset files that are not distributed with this repository.
They are documented, not hidden — see
[`docs/validation-status.md`](docs/validation-status.md).

These figures are **validation outputs from the included harness**, not
performance or quality metrics.

---

## Known limitations

- **Rhino is required** for everything except the headless harness. Nothing here runs as an ordinary Python program.
- **External 3-D assets are not included.** The timber-housing configurator reads OBJ/GLB module geometry that is not part of this repository; without it, the configurator falls back to procedural block placeholders. See the project's `docs/ASSETS_REQUIRED.md`.
- **No script has been executed inside Rhino** during preparation, so runtime behaviour there is unverified.
- **Only one project has tests.** Programming and Simulation has none.
- **No screenshots yet.** See [`docs/image-capture-checklist.md`](docs/image-capture-checklist.md).
- This is academic coursework. It has not been packaged, distributed or used in production.

---

## Academic context

Master's studies in Integrated Design / Computational Architecture,
**TH OWL (Technische Hochschule Ostwestfalen-Lippe), Germany**.

- *Parametric Timber Student Housing* — Computational Design 2; MID Integrated Design Project, SoSe 2026, Detmold campus
- *Programming and Simulation* — individual project

The code is presented as it was written for coursework, with structure and
documentation improved for reading. Computational behaviour has not been
altered.

---

## Images

**None yet.** These are visual, geometry-generating projects, and screenshots
would communicate them far better than code alone. They must be captured from
Rhino; no placeholder or stock imagery has been added.
[`docs/image-capture-checklist.md`](docs/image-capture-checklist.md) lists what
to capture.

---

## Licence

No software licence has currently been assigned to the academic source files in
this repository. The material is shared as a portfolio and a record of academic
work. Please contact the author before copying, modifying or redistributing it.

A final licence decision is still pending.

---

## Author

**Gowthaman Marimuthu**
Master's student, Integrated Design / Computational Architecture
TH OWL, Germany
