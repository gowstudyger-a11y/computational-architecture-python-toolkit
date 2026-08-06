# Compatibility and dependencies

Where a version cannot be proven from the source files, it is recorded as
**UNKNOWN** rather than guessed.

---

## 1. Why there is no `requirements.txt`

Almost every dependency in this repository is **provided by Rhino**, not by PyPI.
`rhinoscriptsyntax`, `Rhino.Geometry`, `scriptcontext` and `Eto.Forms` cannot be
installed with `pip` and do not exist outside the Rhino runtime.

A `requirements.txt` listing them would be misleading — it would suggest a
`pip install -r` that cannot work. Dependencies are therefore documented here
by category instead.

---

## 2. Dependencies by category

### 2a. Python standard library — always available

`math` · `os` · `json` · `datetime` · `time` · `random` · `pprint` · `io` ·
`sys` · `types` · `tempfile` · `importlib`

### 2b. Pip-installable packages

**None.** No third-party package is imported anywhere in this repository.
Nothing needs to be installed.

### 2c. Rhino-provided modules — require Rhino

| Module | Purpose | Files |
|---|---|---:|
| `rhinoscriptsyntax` | High-level Rhino scripting | 13 of 14 |
| `scriptcontext` | Active document context (`sc.doc`, `sc.sticky`) | 12 |

### 2d. RhinoCommon — require Rhino

| Module | Purpose |
|---|---|
| `Rhino` | Core RhinoCommon namespace |
| `Rhino.Geometry` | `Point3d`, `Vector3d`, `Line`, `Plane`, `Brep`, `Mesh`, `Interval` |
| `Rhino.UI` | Rhino UI integration |
| `Rhino.DocObjects` | Materials, so colours appear in Shaded / Rendered modes |

### 2e. GUI dependencies — .NET / Eto, supplied by Rhino

| Module | Purpose |
|---|---|
| `Eto.Forms` | Dialogs, buttons, sliders, list boxes, table layouts |
| `Eto.Drawing` | Colours, fonts, sizes |
| `System`, `System.Drawing` | .NET support types |

### 2f. Grasshopper

Only `projects/parametric-timber-student-housing/src/grasshopper_cluster_aggregator.py`
targets Grasshopper. It is a **GHPython component** — paste the file into a
GHPython component rather than running it as a script. It uses no Grasshopper-specific
imports beyond the standard GHPython input/output convention.

### 2g. External analysis software

| Software | Used by | Version |
|---|---|---|
| RFEM (Dlubal) | `phase2_rfem_structural_export.py` | **UNKNOWN** — not stated in the source |

### 2h. External 3-D assets — not distributed

The timber-housing configurator reads OBJ and GLB module geometry that is **not
part of this repository**. See
[`../projects/parametric-timber-student-housing/docs/ASSETS_REQUIRED.md`](../projects/parametric-timber-student-housing/docs/ASSETS_REQUIRED.md).

Without them the configurator falls back to procedural block placeholders. The
structural rack, grid, slabs and supports are generated procedurally and are
unaffected.

---

## 3. Runtime environments

Four distinct environments appear in this repository. They are **not**
interchangeable.

| Environment | What it means | Files |
|---|---|---:|
| **Ordinary Python** | Runs on plain CPython 3 with no Rhino present | 1 — `tests/headless_validation.py` |
| **Rhino Python** | Executed inside Rhino via `RunPythonScript`; needs `rhinoscriptsyntax` | 12 |
| **RhinoCommon** | Uses the `Rhino.*` .NET API directly, beyond `rhinoscriptsyntax` | 12 |
| **Grasshopper (GHPython)** | Pasted into a GHPython component, driven by component inputs | 1 |

`tests/headless_validation.py` is the only file that runs outside Rhino. It does
so by **stubbing** the Rhino API — including functional 3-D point and vector
classes with real arithmetic — so the configurator's pure-Python logic can be
exercised.

---

## 4. Software versions

| Requirement | Version | Basis |
|---|---|---|
| Rhinoceros | **8** | Stated in the timber-housing source header |
| Rhinoceros (alternative) | 7+ | Stated in the Programming and Simulation header — **not verified** |
| Python (in Rhino) | **3.x** | Stated in the source header |
| Python (headless harness) | 3.x — tested on **3.13** | The version used to run it |
| Grasshopper | Bundled with Rhino | No separate version stated |
| RFEM | **UNKNOWN** | Not stated anywhere in the source |
| Operating system | Windows | Developed and prepared on Windows; Rhino for Mac **untested** |

No version compatibility beyond the above is claimed.

---

## 5. Python language level

The timber-housing code is deliberately written to run under **both** Rhino
script engines and avoids modern-only syntax:

- no f-strings
- no walrus operator (`:=`)
- explicit float division
- no type annotations

This keeps it **IronPython 2.7 tolerant** while still running under Rhino 8's
Python 3. It is a stated design constraint in the original source, not an
oversight, and it was preserved rather than "modernised".

The Programming and Simulation scripts were not written under that constraint
and target Python 3.

---

## 6. Eto dialog behaviour

Every Eto styling helper is wrapped in `try`/`except`. If a particular Rhino
build rejects a styling property, the dialog still displays — styling never
breaks working logic.

Two consequences:

- Rounded corners are unavailable in Eto, so the "card" appearance is approximated with background colours, padding and grouped panels.
- Dialog widths are capped by explicit constants, because Eto labels do not wrap by default and a long line could otherwise push a dialog off-screen.

**Fonts:** `Segoe UI` and `Consolas` — both standard on Windows. No font is
downloaded.

---

## 7. Network access

**None.** No file in this repository imports `requests`, `urllib`, `socket` or
`http`. No downloads, no API calls, no telemetry.

All planning data — climate zones, latitude, snow/wind/seismic placeholders,
regional species lists — is embedded as offline lookup tables in the source.
