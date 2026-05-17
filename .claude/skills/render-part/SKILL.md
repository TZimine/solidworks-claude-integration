---
name: render-part
description: Refresh a SolidWorks part's JSON snapshot and PNG renders, then display the iso view inline. Use when the user asks to render, re-render, view, show, or look at a part. Accepts an optional file path; defaults to models/working/testpart.SLDPRT.
---

# render-part

Re-snapshot a SolidWorks part and render its standard views, then surface the iso PNG inline.

## Input

`$ARGUMENTS` (optional): path to a `.SLDPRT` or `.SLDASM` file, relative to the project root or absolute. If empty or whitespace, default to `models/working/testpart.SLDPRT`.

## Steps

1. **Resolve target.** Take `$ARGUMENTS`, strip whitespace. If empty, use `models/working/testpart.SLDPRT`. Compute basename without extension — you'll need it for output paths.

2. **Refresh snapshot.** Run via the Bash tool:
   ```
   py scripts/describe_model.py <path> --keep-open
   ```
   On non-zero exit, stop and report the script's stderr verbatim.

3. **Render views.** Run via the Bash tool:
   ```
   py scripts/render_views.py <path> --keep-open
   ```
   This writes five PNGs to `outputs/renders/<basename>/`: `iso.png`, `front.png`, `top.png`, `right.png`, `iso_wireframe.png`. On non-zero exit, stop and report.

4. **Display iso.** Use the Read tool on `outputs/renders/<basename>/iso.png` so the image renders inline.

5. **Summarize** in two short lines:
   - Part name and the feature/dimension/config counts from the snapshot output.
   - Where the rest of the PNGs are: `outputs/renders/<basename>/{front,top,right,iso_wireframe}.png`.

## Notes for the model

- The `--keep-open` flag on both scripts is intentional: it leaves the SolidWorks COM session up so the user can inspect the part directly in SW and so follow-up tools don't pay re-open cost.
- Both scripts use `_sw.py` — don't bypass it with raw COM. The dispatch and casting quirks are documented in `STATUS.md`.
- After geometry-changing edits, the renders on disk go stale immediately. This skill is the canonical refresh path; suggest invoking it after any `apply_edit.py` run that changes geometry.
- Don't re-render if `$ARGUMENTS` resolves to a non-existent file — both scripts will exit 2 and you should surface that cleanly.
