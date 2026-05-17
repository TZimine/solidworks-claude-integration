# STATUS — SolidWorks Automation Toolkit

For an at-a-glance project overview (what it is, why it exists, the 20 SW API quirks list, license), read `README.md`. **This file is the cold-start guide** for picking the project back up after time away — it describes the state of the code itself, what's mid-flight, and where to look.

## Right now

All four pipeline scripts work end-to-end against `models/working/testpart.SLDPRT`. Read paths (snapshot, render, rebuild-check) are stable. The edit pipeline (`apply_edit.py`) handles nine operations with `.bak` rollback on failure. The only major capability gap that has actually been *attempted* and *defeated* is creating wizard holes (`HoleWzd`) via external Automation — see "Open threads" below. Everything else listed as untested in `README.md` is simply not yet exercised against real fixture geometry.

## Resume command

```
py scripts/describe_model.py models/working/testpart.SLDPRT
py scripts/render_views.py   models/working/testpart.SLDPRT
py scripts/rebuild_check.py  models/working/testpart.SLDPRT
py scripts/apply_edit.py     edits/smoke_roundtrip.json
```

All four should exit 0. The last is an idempotent round-trip that touches every dispatch path in `apply_edit.py` without changing state — run it after any change to `apply_edit.py` or `_sw.py`.

## Code map

### `scripts/_sw.py` — the shared COM helper

Don't bypass it. Every other script imports it. Public surface:

- `connect()` — `gencache.EnsureModule` + manual `ISldWorks` cast, returns a typed `SldWorks` handle. Sets `Visible = True`.
- `cast(disp, iface_name)` — wraps an untyped CDispatch into a typed interface (`IFeature`, `IDimension`, `IDisplayDimension`, `IPartDoc`, …). Required after every `Get*` that returns a COM object.
- `prop(obj, name)` — papers over the property-vs-method ambiguity for single-name accessors.
- `doctype_for(path)` / `open_doc(sw, path, doctype=None)` / `open_part(sw, path)` — extension-detected doctype, plain `0` for byref errors/warnings, unpacks the tuple return.
- `close(sw, model)` — title-based close.
- `feature_by_name(model, name)` — walks top-level + sub-features and matches on `.Name`. Replacement for the missing `IModelDoc2.FeatureByName`.

Typed-bindings major version is hard-coded as `33` (SW 2025). Bump it if SolidWorks moves.

### `scripts/describe_model.py` — STEP 1

Read-only JSON snapshot to `outputs/snapshots/<base>.json`. Refuses `.SLDDRW`. Captures features (type, suppression, parent), dimensions (value, system value, tolerance, read-only flag), file + per-config custom properties, configurations, and mass properties. The dimension walk fuses three paths (brute-force `model.Parameter("Dn@feat")`, the `GetFirst/GetNextDisplayDimension` linked list, and sub-feature recursion) and dedupes by `FullName` — this is the workaround for the SW 2025 dimension-traversal bug.

The snapshot is *the contract* — every other tool (and any future agent loop) reads from it. After any geometry-changing edit, re-snapshot before authoring the next edit JSON.

### `scripts/render_views.py` — STEP 2

Five PNGs at 1600×1200 to `outputs/renders/<base>/`: `iso.png`, `front.png`, `top.png`, `right.png`, `iso_wireframe.png`. Uses `ShowNamedView2` → `ViewZoomtofit2` → `ModelDocExtension.SaveAs`. Renders go stale immediately after an edit — the `render-part` Claude skill at `.claude/skills/render-part/SKILL.md` wraps `describe_model.py` + `render_views.py` together.

### `scripts/rebuild_check.py` — STEP 3

`ForceRebuild3` + per-feature `GetErrorCode2` walk + mass-before/after sampling. Writes `outputs/logs/rebuild_<base>_<ts>.json`. Exit 0 on clean rebuild, non-zero on error. **Also importable as a module** — `check_open_model(sw, model, path)` is what `apply_edit.py` calls. The mass-drift signal measures stability across a *rebuild of the open model*, not across an edit (see README quirk #15); `drifted=no` is the expected outcome of a successful edit.

### `scripts/apply_edit.py` — STEP 4

Declarative JSON-driven edits. Workflow on every run:

1. Refuse any path under `models\originals\` (case-insensitive substring check).
2. **Validate all ops first**, abort the batch if any fail. Validation is shape-only for `rename_feature` (existence/collision checks happen at apply time, so chained renames like Base→Sketch1→Base work).
3. Copy target to `<target>.bak`.
4. Apply ops in order via `_DISPATCHERS`. First exception aborts the rest of the batch.
5. Save via `Save3(1, 0, 0)` and unpack the byref tuple (typed-bindings quirk).
6. Call `rebuild_check.check_open_model`.
7. Restore from `.bak` if apply raised or rebuild status is `"error"`. Delete `.bak` on clean success.

Current dispatch table (`_DISPATCHERS`):

```
set_dimension, set_dimension_tolerance,
suppress_feature, unsuppress_feature,
set_custom_property, set_material,
set_active_configuration,
drill_hole, rename_feature, delete_feature
```

`delete_feature` uses `Feature.Select2` + `model.EditDelete()`. `EditDelete` returns `None` regardless of outcome — verify by re-querying `feature_by_name` after. It cleans up the feature's *absorbed* children (e.g. a HoleWzd's sub-sketch) but leaves stand-alone reference sketches behind; chain a second `delete_feature` op to remove orphan placement sketches.

Adding a new op: extend `_DISPATCHERS`, add a `_validate` branch (shape-strict), write the `_apply_*` function. `OpFailure` is the rollback signal.

### `scripts/probe_*.py` — investigation scratch

Mostly read-only one-offs used while building. Good templates for the next "I don't know what this API call does" moment. The notable ones still in the repo:

- `probe_simple_hole.py` — confirmed `SimpleHole2` works; basis of `drill_hole`.
- `probe_delete_feature.py` — confirmed `Feature.Select2` + `model.EditDelete()` removes a feature (and its absorbed children) cleanly; basis of `delete_feature`.
- `probe_hole_sketch.py` — structural reconnaissance of `SketchHole` sub-sketches (what points/segments exist, what API surface is reachable).

The HoleWzd creation-attempt graveyard (nine variants of `probe_hole_wizard*.py`, plus `probe_inspect_wizard.py` and `probe_create_definition.py`) was cleaned up before publishing — the conclusions are preserved in the "Open threads" section and in README quirks #19/#20.

### `scripts/fixture_setup.py`

One-shot writer that seeds the test part with a couple of custom properties + a bilateral tolerance. Don't re-run unless setting up a clean fixture from `models/originals/testpart.SLDPRT`.

### `edits/`

Example JSON edit files. The important ones:

- `smoke_roundtrip.json` — idempotent dispatch-coverage smoke. Must still pass after any `apply_edit.py` or `_sw.py` change.
- `rename_roundtrip.json` — idempotent smoke for `rename_feature` specifically (Base ↔ Sketch1).
- The rest are point-in-time real edits (the `100×50` resize, the M2 hole pair, etc.) — fine as references for op syntax but state-dependent.

### `models/` and `outputs/`

`models/originals/` is read-only by convention and enforced by `apply_edit.py`. Copy to `models/working/` before doing anything destructive. `outputs/` is regenerated by the scripts — safe to wipe.

## Working part state (`models/working/testpart.SLDPRT`)

The test part is an L-shaped bracket: a vertical Wall plate with a perpendicular Base step at the top. Snapshots and dimension names rotate as we exercise edits — **don't trust any numbers transcribed here, read `outputs/snapshots/testpart.json` for current values**. The stable facts:

- `Sketch1` was renamed to `Base`. `Sketch2` was renamed to `Wall`. Dimensions on those sketches surface as `D1@Base`, `D2@Base`, `D1@Wall`.
- One pre-existing Ø10 mm hole through the top face (`Cut-Extrude1`, `Sketch3`), centered on the origin.
- Two scripted Ø2.4 mm M2 clearance holes at roughly (±20, 0) added via `drill_hole` (`Hole1`, `Hole2`, `SketchHole` type — *not* `HoleWzd`). Position sketches are underdefined (only the diameter dim is constrained); positions are approximate (~−20.2 mm and ~+19.8 mm).
- The previously-present `M2 Clearance Hole1` (`HoleWzd`) and its placement sketch were removed via `delete_feature`.
- File-level custom property: `FINISH = ANODIZE BLACK`. Material: `<not specified>`.

If state ever feels mysterious, copy `models/originals/testpart.SLDPRT` over `models/working/testpart.SLDPRT` and re-run `fixture_setup.py` for a clean slate.

## Open threads

- **`HoleWzd` feature creation via Automation does not work in this SW build.** Read access is fine — we can introspect existing wizard holes — but the standards-database lookup never runs from external Automation. Tried nine variants (`HoleWizard`, `HoleWizard4`, `HoleWizard5`, the modern `CreateDefinition(25)` → `InitializeHole` → `CreateFeature` path, manual property cloning); all return `None` or have read-only setters that silently no-op. `Standard` and `FastenerType` strings won't populate; `ThruHoleDiameter = 0.0024` silently reverts to 0.0. Almost certainly depends on the wizard PropertyManager UI being active. **Workaround in use:** `drill_hole` (`SimpleHole2`) for clearance/tap geometry. **Real fix candidates:** SW VBA macro replay via `SldWorks.RunMacro2`, an in-process SW Add-In, or a service request to the SW VAR.
- **Assemblies — partial.** `describe_model.py` walks components but the mate walk is stubbed and `rebuild_check.mates` is `null`. No assembly fixture exists.
- **Drawings — unsupported.** `describe_model.py` refuses `.SLDDRW` outright.
- **Sketch-level edits — not exposed.** `drill_hole` is the only sketch-creating op and it's hardcoded to a single circle. No path for moving sketch entities, changing relations/constraints, or freeform sketch creation.
- **`suppress_feature` / `unsuppress_feature` / `set_material`** — coded but never exercised against real fixtures (the test part has no fillets/chamfers and `<not specified>` material).
- **`.bak` rollback on rebuild *failure*** — the success path is well-tested; failure-induced rollback is straightforward (close → copy → reopen) but hasn't been triggered against a real broken-geometry edit.

## Meta-gotchas to remember

The 20 SolidWorks-specific API quirks live in `README.md`. The handful of *environmental* things that aren't in there:

- **`py`, not `python`.** Windows launcher; the SW gen_py cache is under the Python 3.14 path.
- **COM bindings cache:** `%LOCALAPPDATA%\Temp\gen_py\3.14\83A33D31-…`. If it gets wiped (Windows temp-cleanup, OS upgrade), regenerate with `py -m win32com.client.makepy "C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\sldworks.tlb"`. `_sw.py` hard-codes typed-bindings major version `33` — bump if SolidWorks moves to a new major.
- **Re-snapshot before authoring an edit JSON.** Feature and dimension names are not guessable, especially after renames.
- **`apply_edit.py` is the only path that should write to a model.** Anything that bypasses it loses the `.bak` safety net and the rebuild check.
- **Probe first, integrate second.** The probe scripts exist because every quirk in README was discovered the hard way. Write `scripts/probe_<thing>.py` before touching a main script with a new API call.

## Plausible next sessions

None of these are committed.

1. **Assembly support** — fixture an assembly, extend the `describe_model` mate walk, add component-level ops to `apply_edit` (`mate_dimension`, `set_component_config`, `replace_component`).
2. **Drawing automation** — auto-generate a drawing from a part: title-block fill, named views, dimension transfer.
3. **Pattern features** — `linear_pattern` / `circular_pattern` as `apply_edit` ops; useful for hole arrays.
4. **`HoleWzd` via macro replay** — record a parameterised SW VBA wizard-hole macro, replay via `SldWorks.RunMacro2`. The only realistic path to true wizard holes.
5. **Diff-aware edits** — given two snapshots, emit the edit JSON that converts A → B. Useful for templating part variants.
6. **Exercise the untested ops** — pull in a real bracket / production part with fillets, materials, and multiple configs, then run `suppress_feature` / `unsuppress_feature` / `set_material` / per-config edits against it.

## Where to look

- Public-facing overview + the 20-quirks reference: `README.md`
- Working principles + how to talk to this repo from Claude Code: `CLAUDE.md`
- Latest outputs: `outputs/snapshots/`, `outputs/renders/<part>/`, `outputs/logs/`
- Re-render skill: `.claude/skills/render-part/SKILL.md`
