"""S-probe: ForceRebuild3 + per-feature error/warning enumeration.

Goal — confirm on a real part:
  1. ModelDoc2.ForceRebuild3(stopAtError) is callable and what it returns.
  2. Whether Feature.GetErrorCode2 / GetWarningCode2 exist and what a clean
     feature reports (expected: 0 / 0 on a healthy part).
  3. Whether mass properties drift across a no-op rebuild (expected: identical).
  4. Whether ModelDoc2.RegenManager (or similar) gives an alternative error list.

Run:
    py scripts/probe_rebuild.py [path-to-part]

Default target is models/working/testpart.SLDPRT.
"""
import os
import sys
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _sw

DEFAULT_PART = r"D:\ClaudeProjects\TS2\models\working\testpart.SLDPRT"


def safe(fn, default=None):
    try:
        return fn()
    except Exception as e:
        return ("__error__", f"{type(e).__name__}: {e}", default)


def mass_snapshot(model):
    try:
        mp = model.Extension.CreateMassProperty()
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}
    out = {}
    for name in ("Mass", "Volume", "SurfaceArea", "Density"):
        try:
            out[name] = float(getattr(mp, name))
        except Exception as e:
            out[name] = f"<{type(e).__name__}: {e}>"
    try:
        out["CenterOfMass"] = list(mp.CenterOfMass)
    except Exception as e:
        out["CenterOfMass"] = f"<{type(e).__name__}: {e}>"
    return out


def feat_basic(feat):
    feat = _sw.cast(feat, "IFeature")
    name = safe(lambda: feat.Name)
    type_name = safe(lambda: feat.GetTypeName2())
    return feat, name, type_name


def probe_feature_error_calls(feat):
    """Try a battery of error/warning accessors and report what works."""
    results = {}
    candidates = [
        ("GetErrorCode2", lambda: feat.GetErrorCode2()),
        ("GetErrorCode",  lambda: feat.GetErrorCode()),
        ("GetWarningCode", lambda: feat.GetWarningCode()),
        ("IsSuppressed",  lambda: feat.IsSuppressed()),
    ]
    for label, call in candidates:
        try:
            results[label] = call()
        except Exception as e:
            results[label] = f"<{type(e).__name__}: {e}>"
    return results


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PART
    target = os.path.abspath(target)
    if not os.path.isfile(target):
        print(f"FAIL: not a file: {target}")
        sys.exit(2)

    sw = _sw.connect()
    print(f"Connected. SolidWorks {_sw.prop(sw, 'RevisionNumber')}")

    model, errors, warnings = _sw.open_doc(sw, target)
    if model is None:
        print(f"FAIL: OpenDoc6 returned None (errors={errors}, warnings={warnings})")
        sys.exit(3)
    print(f"Opened: {_sw.prop(model, 'GetTitle')} (errors={errors}, warnings={warnings})")

    # ---- 1. mass before ----
    before = mass_snapshot(model)
    print("\n[1] mass before rebuild:")
    for k, v in before.items():
        print(f"    {k}: {v}")

    # ---- 2. ForceRebuild3 ----
    print("\n[2] ForceRebuild3(False):")
    t0 = time.perf_counter()
    try:
        rb_ret = model.ForceRebuild3(False)
        dt = time.perf_counter() - t0
        print(f"    return = {rb_ret!r} (type {type(rb_ret).__name__})  in {dt*1000:.1f} ms")
    except Exception:
        traceback.print_exc()
        rb_ret = None

    # ---- 3. mass after ----
    after = mass_snapshot(model)
    print("\n[3] mass after rebuild:")
    for k, v in after.items():
        print(f"    {k}: {v}")

    # ---- 4. drift ----
    print("\n[4] drift (after - before):")
    for k in ("Mass", "Volume", "SurfaceArea", "Density"):
        a, b = after.get(k), before.get(k)
        if isinstance(a, float) and isinstance(b, float):
            print(f"    {k}: {a - b:+.6e}")
        else:
            print(f"    {k}: <not comparable>")

    # ---- 5. walk features, ask each for error/warning codes ----
    print("\n[5] feature error/warning probe (top-level only):")
    feat = safe(lambda: model.FirstFeature())
    if isinstance(feat, tuple) and feat and feat[0] == "__error__":
        print(f"    FirstFeature failed: {feat[1]}")
        feat = None
    count = 0
    while feat is not None and count < 50:
        feat, name, type_name = feat_basic(feat)
        info = probe_feature_error_calls(feat)
        print(f"    [{count:02d}] {name!r}  type={type_name!r}")
        for k, v in info.items():
            print(f"           {k}: {v!r}")
        try:
            feat = feat.GetNextFeature()
        except Exception as e:
            print(f"           GetNextFeature failed: {e}")
            feat = None
        count += 1

    # ---- 6. RegenManager / similar surfaces ----
    print("\n[6] alternative error-list surfaces:")
    for label in ("RegenManager", "FeatureManager", "GetRebuildState", "GetUpdateStamp"):
        try:
            val = getattr(model, label)
            if callable(val):
                try:
                    val = val()
                except Exception as e:
                    val = f"<call failed: {type(e).__name__}: {e}>"
            print(f"    {label}: {val!r}")
        except Exception as e:
            print(f"    {label}: <missing: {type(e).__name__}: {e}>")

    _sw.close(sw, model)
    print("\ndone.")


if __name__ == "__main__":
    main()
