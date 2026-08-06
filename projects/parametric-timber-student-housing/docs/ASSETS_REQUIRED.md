# External 3-D assets required

**These files are not included in this repository.**

The configurator reads reference geometry produced in SketchUp and exported as
OBJ. Those files are design assets rather than source code, so they are excluded
by `.gitignore` and are not distributed here.

---

## What the code expects

### Block module geometry

Folder: `block module placement`

| File | Module |
|---|---|
| `block module 1.obj` | Module A |
| `block module 1A.obj` | Module A1 (mirrored variant, its own file) |
| `block module 2.obj` | Module B |

A legacy combined file, `block module 1 and 1A.obj`, is still accepted as a
fallback but no longer exists in the author's own asset folder.

### Detail meshes

| Key | Path |
|---|---|
| `M1` | `module 1 and  1a/module.glb` |
| `M1A` | `module 1 and  1a/modulee/modulee.glb` |
| `M2` | `module 2/module 2.glb` |

### Reference model

`skeleton structure with slabs and staircase.obj` — the SketchUp export the axis
grid was measured from (units: metres). All grid constants in
`src/timber_housing_configurator.py` derive from this model.

---

## Pointing the code at your assets

The script resolves asset paths relative to its own location first. If that
fails — which can happen inside Rhino, where `__file__` and the document path do
not always resolve as expected — it falls back to an explicit hint.

Set the hint with an environment variable:

```
set TIMBER_HOUSING_ASSETS=C:\path\to\your\asset\folder
```

The original hardcoded absolute path was **removed during preparation for
publication** because it exposed a personal directory layout and would not work
on any other machine.

---

## Running without the assets

The configurator still runs. It detects that the OBJ files are missing and
falls back to **procedural block placeholders** — correct in position and
dimension, but simplified in form.

**What this affects:**

- Module geometry is shown as simplified blocks rather than detailed meshes.
- 5 of the 23 smoke tests in `tests/headless_validation.py` fail — the site-folder inspection group. The first failure cascades into the other four.

**What this does not affect:**

- The structural rack, grid, slabs and supports are generated procedurally and are unaffected.
- The core regression test passes in full: 935 nodes, 901 members, 12 CLT panels, 42 supports, and module counts 22 / 28 / 18 / 32.

In other words, the **structural engine is verifiable without the assets**; only
the asset-import and detail-geometry paths are not.
