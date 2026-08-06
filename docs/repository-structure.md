# Repository structure

Why this repository is laid out the way it is.

---

## Tree

```
computational-architecture-python-toolkit/
│
├── README.md                        Overview, projects, compatibility, limitations
├── .gitignore
│
├── docs/
│   ├── compatibility.md             Software, libraries, runtime environments
│   ├── validation-status.md         Exact commands run and their results
│   ├── repository-structure.md      This file
│   └── image-capture-checklist.md   Screenshots still to be captured
│
└── projects/
    │
    ├── parametric-timber-student-housing/
    │   ├── README.md
    │   ├── src/
    │   │   ├── timber_housing_configurator.py       Main configurator (Rhino)
    │   │   ├── grasshopper_cluster_aggregator.py    GHPython component
    │   │   └── rhino_cluster_aggregator.py          Rhino-Python counterpart
    │   ├── tests/
    │   │   └── headless_validation.py               Runs without Rhino
    │   ├── examples/
    │   │   ├── 01_habitat67_aggregation.py
    │   │   ├── 02_collision_free_placement.py
    │   │   ├── 03_courtyard_driven_placement.py
    │   │   ├── 04_deterministic_cascade_ring.py
    │   │   ├── 05_hourglass_cascade_study.py
    │   │   └── 06_corridor_projection_system.py
    │   ├── docs/
    │   │   └── ASSETS_REQUIRED.md                   External 3-D files needed
    │   └── images/
    │
    └── programming-and-simulation/
        ├── README.md
        ├── src/
        │   ├── pixel_perfect_living_house_generator.py
        │   └── phase2_rfem_structural_export.py
        ├── examples/
        │   ├── parametric_envelope_system.py
        │   └── envelope_configurator_oop.py
        └── images/
```

---

## Conventions

| Folder | Contains |
|---|---|
| `src/` | The scripts that do the main work — what to read first |
| `tests/` | Automated checks. **Only one project has this**, which is honest. |
| `examples/` | Supporting or illustrative scripts, not required by `src/` |
| `docs/` | Documentation specific to that project |
| `images/` | Screenshots (none captured yet) |

Filenames are lower case and descriptive. Version numbers live in documentation
rather than filenames, so that `src/` always names the current version.

---

## Two different uses of `examples/`

The folder means something different in each project, and both are explained in
the project READMEs.

**Timber Student Housing** — `examples/` is a **development sequence**. The
numbered files `01_` … `06_` are successive stages showing how the aggregation
strategy evolved: initial stepped-mass aggregation, then footprint tracking to
prevent module collisions, then courtyard-first placement, then the removal of
randomness, then the hourglass cascade study, then corridor projection.

They are kept because the progression is part of what the project demonstrates.
They are *not* six alternative scripts, and they are not duplicates.

**Programming and Simulation** — `examples/` holds **two implementations of the
same problem**: one procedural (functions over a shared dictionary) and one
object-oriented (classes plus an Eto GUI). The contrast is the point.

---

## Why the timber project is listed first

It is the only project with an automated regression harness, and its development
history is documented stage by stage. Programming and Simulation is the larger
body of code but has no tests.

---

## Empty folders

Git does not track empty directories. The two `images/` folders will therefore
not appear in a fresh clone until real screenshots are added. This is intentional
— no placeholder file has been added purely to make a folder exist, and no
placeholder image has been added to fill it.

---

## What is not in this repository

| Not included | Why |
|---|---|
| 3-D assets (`.obj`, `.glb`, `.3dm`) | Design assets rather than source code; excluded by `.gitignore`. The timber project's `docs/ASSETS_REQUIRED.md` documents exactly what the code expects. |
| Grasshopper definitions (`.gh`, `.ghx`) | None are required — the one Grasshopper component is plain Python, pasted into a GHPython component. |
| Generated output | Reports, CSVs and test artefacts are regenerated on each run and are excluded by `.gitignore`. |
| Byte-code caches | `__pycache__/` and `*.pyc` are excluded. |
| Earlier drafts and working snapshots | The coursework folders contained many intermediate versions. Only the final version of each capability is published, plus the six documented development stages described above. |
| Incomplete files | Two truncated envelope drafts existed; neither compiled. The complete implementation is included instead — see the Programming and Simulation README. |

---

## Reading order

For a first look:

1. This file, for the layout
2. The root `README.md`, for what each project does
3. `projects/parametric-timber-student-housing/README.md` — the tested project
4. `projects/parametric-timber-student-housing/src/timber_housing_configurator.py` — the header documents the coordinate convention and grid constants before any code
5. `docs/validation-status.md`, for exactly what was and was not verified
