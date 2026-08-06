# Programming and Simulation

A fully parametric **single-family house generator** written in Python for
Rhino, together with a structural-analysis export stage and two contrasting
envelope implementations.

**Academic context:** TH OWL (Technische Hochschule Ostwestfalen-Lippe) —
*Programming and Simulation*, individual project.

---

## Objective

Generate a complete house model from parameters rather than drawing it: take
plot dimensions and a handful of design choices, and produce site, structure,
floors, walls, façade, circulation and enclosure as coordinated Rhino geometry.

---

## What the main generator builds

- **Site** — plot boundary, road geometry, site filling, grass top, vehicular ramp, pedestrian entry steps
- **Structure** — structural grid, timber/CLT columns, plinth beams
- **Floors** — per-floor CLT build-up: structural layer → insulation → membrane → screed → parquet
- **Walls** — 5-layer build-up: cladding → wind barrier → insulation → vapour barrier → plasterboard
- **Façade** — wall and volume extrusions subdivided into glazing, doors and glass balustrades; parametric timber louvre screens
- **Circulation** — internal UC-shaped staircase per floor, laid out to **DIN 18065**
- **Enclosure** — compound perimeter wall with vehicular and pedestrian gate openings; double-leaf entrance door auto-placed on the north wall
- **Presentation** — Rhino material assignment so colours appear in Shaded and Rendered display modes

### Rule-based massing

Cells are classified **BUILT / GARDEN / EMPTY**. GARDEN cells emerge at the
Built/Empty boundary to form terraces, and isolated BUILT clusters are
automatically downgraded so the built mass stays connected. This
cellular-automata-style rule set is the most distinctive part of the project.

### Coordinate system

Origin `(0, 0, 0)` is the centre of the plot at finished-floor level; ground
floor is Z = 0. X is the plot length direction, Y the width, Z vertical.

---

## Retained scripts

```
src/
  pixel_perfect_living_house_generator.py  Main generator — run this in Rhino
  phase2_rfem_structural_export.py         Structural analysis stage, RFEM export
examples/
  parametric_envelope_system.py            Envelope, procedural style (25 functions)
  envelope_configurator_oop.py             Envelope, object-oriented + Eto GUI (5 classes)
images/                                    Screenshots — none captured yet
```

| Script | Role |
|---|---|
| `pixel_perfect_living_house_generator.py` | The complete house generator and the best-documented file in the project. Its header records the platform, dependencies, full build sequence and coordinate system. |
| `phase2_rfem_structural_export.py` | The structural stage. Specifies **GL24h glulam** per **EN 14080 / DIN EN 1995-1-1** and writes an export for RFEM (Dlubal). |
| `parametric_envelope_system.py` | Envelope generation in a **procedural** style — 25 functions operating on a shared `Building` dictionary. |
| `envelope_configurator_oop.py` | The same problem in an **object-oriented** style — `EnvelopeGeometry`, `EnvelopeModules`, `OpeningsSystem`, `BuildingGenerator` and an `EnvelopeConfiguratorDialog` Eto GUI. |

The two envelope files are kept **deliberately**. They are two different
architectures for the same problem, and the contrast between them is the point.

---

## Inputs and outputs

**Inputs** — plot dimensions, floor count (1–3), grid spacing, column and plinth
beam sizing, envelope module type, staircase option, louvre density, material
choices. All collected through Eto dialogs; no command-line arguments.

**Outputs** — a complete Rhino building model on named layers with assigned
materials. The structural stage additionally writes an RFEM export file.

---

## Requirements

| Requirement | Detail |
|---|---|
| Rhinoceros | 7+ per the original header; developed against Rhino 8 |
| Python | 3.x via Rhino's script editor |
| RFEM (Dlubal) | Only for `phase2_rfem_structural_export.py`. Version **UNKNOWN** — not stated in the source. |
| Pip packages | **None** |
| External assets | **None** — these scripts are self-contained |

**Dependencies:** `rhinoscriptsyntax`, `scriptcontext`, `Rhino`,
`Rhino.Geometry`, `Rhino.UI`, `Rhino.DocObjects`, `Eto.Forms`, `Eto.Drawing`,
`System`, `System.Drawing`, plus `math`, `time` and `pprint` from the standard
library.

---

## How to run

1. Open Rhino
2. Run `RunPythonScript`
3. Select `src/pixel_perfect_living_house_generator.py`
4. Follow the dialogs

**To inspect without running anything**, start with the same file — its header
documents the whole build sequence before any code.

---

## Validation status

| Check | Result |
|---|---|
| Syntax compilation | **4 / 4 files pass** |
| Automated tests | **None exist for this project** |
| Executed inside Rhino during preparation | **No** — Rhino was not available |
| Classification | Syntax-checked and statically reviewed |

These scripts are **syntax-checked only**. No claim is made that they run
without error in Rhino. See [`../../docs/validation-status.md`](../../docs/validation-status.md).

Unlike the timber-housing project, this one has **no regression harness**. That
is a real gap, stated rather than glossed over.

---

## Why two files were excluded

The original coursework contained a two-part envelope configurator that was
**never completed**:

| File | Problem |
|---|---|
| `1 envelope_configurator.py` | **Truncated.** Ends mid-statement at line 807 (`self.louver_angle_slider.Value = self.`). Raises `SyntaxError`. |
| `2 envelope_config_part2.py` | **Begins mid-class.** Starts with indented methods intended to continue Part 1, so it is not a valid standalone module. Raises `IndentationError` at line 12. |

**Neither file compiles.**

Both are incomplete drafts of the same configurator that
`examples/envelope_configurator_oop.py` implements **completely** — that
finished version contains the `EnvelopeConfiguratorDialog` class the fragments
were building towards. The complete version is included here; the two broken
fragments were intentionally excluded, so nothing of value is lost.

---

## Known limitations

- **Rhino is required.** Every file imports `rhinoscriptsyntax`; nothing runs as ordinary Python.
- **RFEM is required** for the structural export stage, and that export has not been executed or validated.
- **No automated tests.**
- **Not executed in Rhino** during preparation — runtime behaviour there is unverified.
- **No screenshots yet.**
- This is coursework — not packaged, distributed or production software.
