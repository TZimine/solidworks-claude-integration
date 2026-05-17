"""Probe: delete a named feature via EditDelete. Does NOT save.

Verifies the API path before integrating delete_feature into apply_edit.py.
Target: M2 Clearance Hole1 on testpart. After running, the model is closed
without saving so testpart stays untouched.
"""
import sys
import _sw

PATH = r"D:\ClaudeProjects\TS2\models\working\testpart.SLDPRT"
TARGET = "M2 Clearance Hole1"


def main():
    sw = _sw.connect()
    print(f"Connected. SolidWorks {_sw.prop(sw, 'RevisionNumber')}")

    model, errs, warns = _sw.open_doc(sw, PATH)
    print(f"Opened: {_sw.prop(model, 'GetTitle')} (errs={errs}, warns={warns})")

    feat = _sw.feature_by_name(model, TARGET)
    if feat is None:
        print(f"FAIL: feature {TARGET!r} not found")
        sys.exit(1)
    print(f"Found {TARGET!r}: type={_sw.prop(feat, 'GetTypeName2')}")

    print("Calling Select2(False, 0)...")
    sel_ok = feat.Select2(False, 0)
    print(f"  -> {sel_ok!r}")
    if not sel_ok:
        print("FAIL: could not select feature")
        sw.CloseDoc(_sw.prop(model, "GetTitle"))
        sys.exit(2)

    sel_count = model.SelectionManager.GetSelectedObjectCount2(-1)
    print(f"  selection count after Select2: {sel_count}")

    print("Calling EditDelete()...")
    try:
        rc = model.EditDelete()
        print(f"  -> {rc!r} (type {type(rc).__name__})")
    except Exception as e:
        print(f"  EXCEPTION: {type(e).__name__}: {e}")
        rc = None

    print("Verifying feature is gone via feature_by_name...")
    still = _sw.feature_by_name(model, TARGET)
    if still is None:
        print(f"  OK: {TARGET!r} no longer present in feature tree")
    else:
        print(f"  STILL PRESENT: {TARGET!r}")

    # Sub-features that came with the wizard hole
    for n in ("Sketch6", "Sketch7"):
        f = _sw.feature_by_name(model, n)
        print(f"  {n}: {'still present' if f is not None else 'gone'}")

    print("Closing WITHOUT saving (CloseDoc discards changes)...")
    sw.CloseDoc(_sw.prop(model, "GetTitle"))
    print("Done.")


if __name__ == "__main__":
    main()
