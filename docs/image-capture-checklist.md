# Image capture checklist

This repository currently contains **no images**. These are visual,
geometry-generating projects, and screenshots would communicate them far better
than code alone.

No placeholder renders, stock architectural imagery or broken image links have
been added. Every image must be a genuine capture from your own Rhino session.

---

## Before you capture anything — clean the interface

Screenshots capture more than the model. Check each of these:

- [ ] **File paths** — hide the title bar, or open the file from a neutral folder. A path such as `D:\…\<personal folders>\…` in the title bar leaks your drive layout.
- [ ] **Student or personal identifiers** — none should appear in filenames, layer names, panels or the title bar.
- [ ] **Unrelated Rhino tabs** — close every other open document. Tabs at the top of the Rhino window are readable in a screenshot.
- [ ] **Unrelated work in the viewport** — no other project geometry visible.
- [ ] **Command history panel** — clear it, or crop it out. It may show commands and paths from earlier sessions.
- [ ] **Layer panel** — if visible, it should show only this project's layers.
- [ ] **Recent-files list** — do not capture Rhino's start screen or any recent-documents menu.
- [ ] **Desktop background and taskbar** — capture the Rhino window only, not the full screen.

Take one test screenshot, view it at 100 %, and read every piece of text in it
before capturing the rest.

---

## Parametric Timber Student Housing

Save into `projects/parametric-timber-student-housing/images/`

| # | Filename | What to show |
|---|---|---|
| 1 | `01-structural-system-overview.png` | Main Rhino viewport, perspective view, showing the complete generated structural system — the timber rack with its cascading height distribution. This is the headline image. |
| 2 | `02-timber-members-and-clt.png` | Closer view showing timber columns, beams and branches together with the CLT slab elements, so the 3.8 m axis grid and 0.3 m member section read clearly. |
| 3 | `03-configurator-dialog.png` | The Eto configurator dialog with its sliders, list boxes and grouped panels — ideally the building-parameters step, showing real input values. |
| 4 | `04-layer-organisation.png` | The Rhino layer panel showing how generated geometry is organised, alongside the model. Demonstrates that output is structured, not a loose pile of objects. |
| 5 | `05-structural-detail-closeup.png` | Close-up of a junction — where columns, beams and a slab meet — showing the centreline grid resolving into real geometry. |

**Optional if you obtain the 3-D assets:** a comparison of procedural block
placeholders versus the detailed OBJ module geometry. That would illustrate the
documented asset limitation directly.

---

## Programming and Simulation

Save into `projects/programming-and-simulation/images/`

| # | Filename | What to show |
|---|---|---|
| 1 | `01-envelope-configurator-dialog.png` | The `EnvelopeConfiguratorDialog` Eto interface with its controls visible. |
| 2 | `02-generated-house-model.png` | The complete generated house in perspective — site, structure, façade and enclosure together. The headline image for this project. |
| 3 | `03-parameter-variation.png` | Two or three outputs side by side from different parameter sets — for example 1, 2 and 3 floors, or different envelope module types. This shows the model is genuinely parametric rather than one fixed design. |
| 4 | `04-script-to-output-workflow.png` | The dialog and the resulting geometry in one frame, so the input-to-output relationship is visible at a glance. |

**Optional:** a façade close-up showing the 5-layer wall build-up, or the
DIN 18065 staircase.

---

## Technical guidance

| Setting | Recommendation |
|---|---|
| **Format** | PNG for interface and geometry captures. JPG only for heavy renders. |
| **Aspect ratio** | 16:9 for viewport and overview images; 4:3 or 3:2 for dialogs and close-ups. |
| **Resolution** | 1920 × 1080 or larger. GitHub scales down cleanly; it cannot add detail. |
| **File size** | Under ~1 MB each. Compress before committing — this repository is currently ~2 MB in total. |
| **Filenames** | Lower case, hyphenated, number-prefixed as above. No spaces, no personal identifiers. |
| **Cropping** | Crop to the Rhino window or to the relevant panel. Avoid full-desktop captures. |
| **Display mode** | Shaded or Rendered for geometry; Wireframe or Ghosted where structural members need to read individually. |
| **Background** | A plain, light viewport background keeps the geometry legible on both GitHub themes. |

---

## After capturing

1. Place the files in the two `images/` folders.
2. Reference them from each project README, for example:
   ```markdown
   ![Generated structural system](images/01-structural-system-overview.png)
   ```
3. Add one image to the root `README.md` as a lead visual.
4. Re-check that no path, identifier or unrelated window is visible in any file.
5. Update [`validation-status.md`](validation-status.md) if capturing them meant
   running the scripts in Rhino — that would upgrade those files from
   "syntax-checked only" to "tested in the required environment", which is worth
   recording.
