# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Read first

`STATUS.md` is the cold-start guide — current state of the code, file-by-file map, open threads, and the resume command. Read it before doing anything substantive. `README.md` is the public-facing overview. QUIRKS.md is the home of the full 20-item SolidWorks API quirks reference.

## Environment

- Windows, SolidWorks 2025 SP3 (`RevisionNumber` reports `33.3.0`), Python 3.14, `pywin32`.
- Python is invoked as `py` (the Windows launcher), not `python`.
- COM bindings are cached in `gen_py` under `%LOCALAPPDATA%\Temp\gen_py\3.14\…`. If those get blown away, regenerate with:
  `py -m win32com.client.makepy "C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\sldworks.tlb"`

## Common commands

The four-script pipeline, each operating on a part/assembly path:

```
py scripts/describe_model.py  models/working/testpart.SLDPRT     # JSON snapshot -> outputs/snapshots/
py scripts/render_views.py    models/working/testpart.SLDPRT     # PNGs          -> outputs/renders/<part>/
py scripts/rebuild_check.py   models/working/testpart.SLDPRT     # JSON report   -> outputs/logs/
py scripts/apply_edit.py      edits/<edit>.json                  # declarative edits; writes .bak
```

Useful flags: `--keep-open` (don't close SolidWorks after the script), `--dry-run` (apply_edit only; validates without writing).

`edits/smoke_roundtrip.json` is an idempotent round-trip that exercises every `apply_edit.py` dispatch path without changing state — run it after touching `apply_edit.py` or `_sw.py`.

There is no test framework; verification is "all four scripts above exit 0." For new API surface, write a tiny `scripts/probe_*.py` first (the existing probes are good templates) before integrating into the main scripts.

## Architecture

Four scripts on top of one shared helper. They are deliberately independent CLIs but `apply_edit.py` imports `rebuild_check.py` as a module for the post-edit safety net.

```
_sw.py            shared COM bridge — connect/cast/open_doc/close/prop/feature_by_name
  ^
  |  imported by all four
  |
describe_model.py     STEP 1 — read-only JSON snapshot
render_views.py       STEP 2 — PNG views
rebuild_check.py      STEP 3 — ForceRebuild3 + feature-error walk + mass-drift; also a module
apply_edit.py         STEP 4 — declarative edits; imports rebuild_check.check_open_model
```

### `_sw.py` is non-negotiable

Use it for every script. Bypassing it (raw `win32com.client.Dispatch`) will hit the dynamic/typed dispatch ambiguity that took the most time to figure out. Specifically:

- **`_sw.connect()`** does `gencache.EnsureModule` then a manual cast — `EnsureDispatch` does *not* work for SldWorks (no `IProvideClassInfo`).
- **`_sw.cast(disp, "IFeature")`** etc. must wrap every COM object returned from a `Get*` call (`FirstFeature`, `GetNextFeature`, `GetFirstSubFeature`, `GetDimension`, `GetFirstDisplayDimension`, …). Without the cast the next call silently fails with "Member not found".
- **`_sw.prop(obj, name)`** handles the property-vs-method flip between dynamic and typed dispatch (e.g. `RevisionNumber`, `GetTitle`, `GetTypeName2`, `IsSuppressed`, `GetUpdateStamp` are all this way).
- **`_sw.open_doc(sw, path)`** auto-detects doctype from extension and handles the typed-binding tuple return of `OpenDoc6` (no `VARIANT` byref dance needed).
- **`_sw.feature_by_name(model, name)`** is the replacement for `IModelDoc2.FeatureByName`, which is not exposed by SW 2025's typed bindings.

### `apply_edit.py` workflow invariants

1. Refuses to edit any path under `models\originals\` (case-insensitive substring check).
2. **Validate all ops first, abort if any fail** — nothing is written until the whole batch validates.
3. Copies the target to `<target>.bak` before applying.
4. Applies ops in order via `_DISPATCHERS`. First exception aborts the rest of the batch.
5. Saves via `Save3` (returns a byref tuple under typed bindings — same unwrap pattern as `OpenDoc6`).
6. Calls `rebuild_check.check_open_model` for the post-edit check.
7. Restores from `.bak` if apply raised or rebuild status is `"error"`. Deletes `.bak` on clean success.

Adding a new edit op means: add the op name to `_DISPATCHERS`, add a `_validate` branch (so the pre-flight check covers it), and write the `_apply_*` function. Keep the validation strict — a bad op should never reach the apply phase.

### `describe_model.py` snapshot is the contract

Other parts of the toolkit (and any future agent loops) consume `outputs/snapshots/<part>.json`. Don't propose edits without reading the latest snapshot first — the feature/dimension names you need (`D1@Sketch1` style) come from there.

The dimension walk uses three paths fused together because `IDisplayDimension::GetNext*` does not reliably traverse dimensions in SW 2025 — see _walk_feature_dims and QUIRKS.md #7.

## Working principles (project-specific)

- **`models/originals/` is read-only.** Copy to `models/working/` before doing anything destructive. `apply_edit.py` enforces this.
- **Run `describe_model.py` before authoring an edit JSON.** Feature and dimension names are not guessable.
- **Verify after every write.** `apply_edit.py` already does this via `rebuild_check`; if you write a new edit path, keep this property.
- **Don't hallucinate API signatures.** When unsure, write a throwaway `scripts/probe_*.py` (e.g. `dir(obj)`, try the call, print the result) before integrating. The 20 quirks in README were all discovered this way.
- **Stop between phases and let the user verify.** Memory notes record a strong preference for small probes, deliberate pacing, and running scripts ourselves rather than batching changes blindly.

## Where to find things

- Cold-start guide / code state: `STATUS.md`
- Public-facing overview: `README.md`
- Latest snapshot/report outputs: `outputs/snapshots/`, `outputs/renders/<part>/`, `outputs/logs/`
- The full catalogue of SolidWorks-API quirks (20 items, all encoded in code already) lives in QUIRKS.md — re-read before touching _sw.py or feature/dimension walking.
