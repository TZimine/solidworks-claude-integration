# SolidWorks 2025 API Quirks

Twenty undocumented or counterintuitive behaviors in the SolidWorks 2025 / pywin32 boundary that I had to discover while building this toolkit. Each is baked into the code; this document exists so the next person doesn't have to rediscover them.

Most of these came out of probe scripts (`scripts/probe_*.py`) that read actual COM responses and compared them against what `gen_py` claimed the API would return. Where there's a workaround, it's named.

---

### 1. `Dispatch("SldWorks.Application")` alone is too dynamic

The deep API surface (`model.Extension`, mass props, mate manager, …) requires typed bindings. `_sw.connect()` does `gencache.EnsureModule` + a manual cast via `mod.ISldWorks(disp._oleobj_)`. `EnsureDispatch` doesn't work because the COM object doesn't expose `IProvideClassInfo`.

### 2. `makepy` must include the main `sldworks.tlb`

…not just the SwAddin typelib. Regenerate with:

```
py -m win32com.client.makepy "C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\sldworks.tlb"
```

Cached at `%LOCALAPPDATA%\Temp\gen_py\3.14\…`.

### 3. Property vs method ambiguity flips between dispatch modes

With dynamic dispatch, names like `RevisionNumber`, `GetTitle`, `GetType`, `GetTypeName2`, `IsSuppressed` come back as plain values. With typed dispatch they're bound methods. `_sw.prop(obj, name)` handles both — returns primitives directly, calls callables. Use it for any single-name accessor.

### 4. Most `GetXxx` calls that return COM objects return untyped `CDispatch` wrappers

`FirstFeature`, `GetNextFeature`, `GetFirstSubFeature`, `GetNextSubFeature`, `GetFirstDisplayDimension`, `GetDimension`, etc. Wrap them with `_sw.cast(disp, "IFeature")` / `IDisplayDimension` / `IDimension` before continuing the walk, otherwise the next call silently fails with *"Member not found"*.

### 5. `OpenDoc6` byref args

Pass plain `0`s for errors/warnings (not VARIANT byref objects); the typed call returns a tuple `(model, errors, warnings)`. Implemented in `_sw.open_doc`, which also auto-detects part/asm/drawing from the extension.

### 6. Mass properties use British spelling

`PrincipleMomentsOfInertia`, `PrincipleAxesOfInertia(axisIndex)` (note "ple", not "pal"). `IMassProperty2` has modern `Principal…` names but isn't auto-cast — needs a manual `_sw.cast`.

### 7. `IDisplayDimension::GetNext{,2,3,4,5}` does not reliably traverse all dimensions

In SW 2025, every variant returned `None` after the first dim. `describe_model.py` works around this by brute-forcing `model.Parameter("Dn@feat")` for `n=1..20` per feature, then deduping by `FullName`. The linked-list walk is kept as a fallback for custom-named dims.

### 8. `CustomPropertyManager.GetNames()` returns `None` (not `()`) when empty

Use `cpm.GetNames() or ()`. `Get6(name, useCached=False)` returns a 5-tuple `(retcode, value, resolved, was_resolved, link)`.

### 9. Dimensions come in two flavours

`dim.Value` is in document units (mm here), `dim.SystemValue` is SI (m). Tolerances (`GetToleranceValues()`) come back in m. `describe_model.py` records both.

### 10. Sketches appear twice in the feature tree

Top-level *and* as a sub-feature of the absorbing extrude. Dedupe by `feat.GetID()`.

### 11. `Feature.GetWarningCode` does not exist

Not on `IFeature` in SW 2025 typed bindings. Use `Feature.GetErrorCode2()` instead — it returns a 2-tuple `(error_code: int, has_warning: bool)`, so error and warning state come from one call.

### 12. `ModelDoc2.Save3` returns the byref tuple under typed bindings

Same pattern as `OpenDoc6`. Pass plain `0`s for errors/warnings and unpack:

```python
(ok, errors, warnings) = model.Save3(1, 0, 0)
```

Plain `Save()` returned `False` after a successful write because pywin32 surfaced the byref tuple where a bool was expected.

### 13. `ModelDoc2.GetUpdateStamp` is a method, not a property

In typed bindings — `_sw.prop` handles both. The stamp advances by ~18 per `ForceRebuild3` even when geometry is unchanged, so it's a "did SW recompute" signal, not a "did anything change" signal.

### 14. `ShowConfiguration2` returns `False` if the named configuration is already active

That's a no-op success, not a failure. `apply_edit.py` logs the return code but does not treat `False` as an error here.

### 15. Mass-drift detection measures stability across a rebuild, not across an edit

`rebuild_check.py` samples mass before and after `ForceRebuild3` on the *currently-open model*. `apply_edit` triggers SW's internal rebuild during `Save3`, so by the time `rebuild_check.check_open_model` samples mass-before, the geometry is already stable post-edit — `drifted=no` is the expected outcome of a successful edit. To verify edits actually took effect, diff `outputs/snapshots/<part>.json` before and after.

### 16. `IDimension.SetToleranceType(0)` clears the tolerance but retains the values

Sets it to `swTolNONE`, but `GetToleranceValues()` still returns the previously-set `(min_m, max_m)` afterwards — SW retains them internally even though the type is `NONE`. Snapshots show `type: "NONE"` and the values are effectively inert. If you switch a dim back to `BILAT`/`LIMIT` the old values would resurface, so always pair a tol-type set with explicit `min`/`max` when re-enabling.

### 17. `IModelDoc2.FeatureByName` is not exposed

In SW 2025 typed bindings even though the SW API docs list it. Use `_sw.feature_by_name(model, name)` which walks `FirstFeature`/`GetNextFeature` (and sub-features) and matches by `.Name`.

### 18. `IModelDoc2.GetBodies2` is not exposed either

Cast the model to `IPartDoc` first:

```python
_sw.cast(model, "IPartDoc").GetBodies2(0, True)
```

### 19. `HoleWizard5` returns `None` from external Automation

Returned `None` from every parameter combination tried (Hole/Tap, ANSI Metric/ISO, several `FastenerTypeIndex` values, even Legacy with explicit diameter). There are pre-conditions that aren't documented in the gen_py signature — likely an editing-context state. `IFeatureManager.SimpleHole2` works reliably and is what `apply_edit.drill_hole` uses.

### 20. `IFeatureManager.FeatureCut4` also returns `None` from script context

From a script-created sketch on Front Plane — even with the sketch explicitly re-selected by name. The sketch was created (`Sketch4` appeared in the tree) but the cut wouldn't form. Same call worked from the SW UI on the same sketch. Probably another hidden editing-context requirement. Avoid the cut-extrude route for hole-like operations; prefer `SimpleHole2`.

---

## Methodology note

These were found by writing one probe script per quirk (`scripts/probe_*.py`) and reading actual COM responses against a known-good test part. The probes are kept in the repo as scratch files — they're not part of the working pipeline but they document what was tried and what worked.
