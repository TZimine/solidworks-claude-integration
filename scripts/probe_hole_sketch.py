"""Probe: inspect the sketch that backs a SimpleHole2-created SketchHole.

Goal: learn whether we can (a) open the hole's sketch for edit, (b) read its
points, (c) call AddDimension2 / SketchAddConstraints on it. This is the
reconnaissance before deciding whether sketch-level edits belong in apply_edit.

Target: Hole1 on testpart. Does NOT save.
"""
import _sw

PATH = r"D:\ClaudeProjects\TS2\models\working\testpart.SLDPRT"
TARGETS = ["Hole1", "Hole2", "Cut-Extrude1"]


def list_sub_features(feat):
    """Walk GetFirstSubFeature / GetNextSubFeature; return [(name, type)]."""
    out = []
    child = None
    try:
        child = feat.GetFirstSubFeature()
    except Exception as e:
        return out, f"GetFirstSubFeature raised {type(e).__name__}: {e}"
    while child is not None:
        child = _sw.cast(child, "IFeature")
        try:
            name = child.Name
        except Exception:
            name = "?"
        try:
            t = _sw.prop(child, "GetTypeName2")
        except Exception:
            t = "?"
        out.append((name, t))
        try:
            child = child.GetNextSubFeature()
        except Exception:
            break
    return out, None


def describe_sketch(sketch_feat):
    """Cast a feature to ISketch (via GetSpecificFeature2) and print contents."""
    print(f"    Casting {sketch_feat.Name!r} to ISketch...")
    spec = None
    try:
        spec = sketch_feat.GetSpecificFeature2()
    except Exception as e:
        print(f"      GetSpecificFeature2 raised {type(e).__name__}: {e}")
        return None
    if spec is None:
        print("      GetSpecificFeature2 returned None")
        return None
    sketch = _sw.cast(spec, "ISketch")
    print(f"      ISketch -> {sketch!r}")

    for getter, label in [
        ("GetSketchPoints2", "points"),
        ("GetSketchSegments", "segments"),
    ]:
        try:
            items = getattr(sketch, getter)() or ()
        except Exception as e:
            print(f"      {getter}: raised {type(e).__name__}: {e}")
            continue
        print(f"      {label} ({len(items)}):")
        for i, item in enumerate(items):
            attrs = {}
            for a in ("X", "Y", "Z"):
                try:
                    attrs[a] = round(getattr(item, a), 6)
                except Exception:
                    pass
            print(f"        [{i}] {attrs}  raw={item!r}")
    return sketch


def main():
    sw = _sw.connect()
    print(f"Connected. SW {_sw.prop(sw, 'RevisionNumber')}")
    model, errs, warns = _sw.open_doc(sw, PATH)
    print(f"Opened: {_sw.prop(model, 'GetTitle')} (errs={errs}, warns={warns})\n")

    for tname in TARGETS:
        print(f"=== {tname} ===")
        feat = _sw.feature_by_name(model, tname)
        if feat is None:
            print("  not found")
            continue
        print(f"  type: {_sw.prop(feat, 'GetTypeName2')}")

        subs, err = list_sub_features(feat)
        if err:
            print(f"  sub-feature walk error: {err}")
        print(f"  sub-features ({len(subs)}):")
        for n, t in subs:
            print(f"    - {n}  ({t})")

        # Try to open the *first sketch* sub-feature in read mode
        sketch_subs = [n for n, t in subs if t == "ProfileFeature"]
        if not sketch_subs:
            print("  no ProfileFeature sub — skipping sketch inspection")
            print()
            continue
        sname = sketch_subs[0]
        sub_feat = _sw.feature_by_name(model, sname)
        if sub_feat is None:
            print(f"  feature_by_name({sname!r}) returned None — skipping")
            print()
            continue
        describe_sketch(sub_feat)
        print()

    # Try AddDimension2 visibility on the model (just a hasattr/dir check)
    print("=== Model.AddDimension2 surface ===")
    try:
        add_dim = getattr(model, "AddDimension2", None)
        print(f"  hasattr(model, 'AddDimension2') -> {add_dim is not None}")
        if add_dim is not None:
            print(f"  type: {type(add_dim).__name__}")
    except Exception as e:
        print(f"  EXC: {e}")
    try:
        sm = model.SketchManager
        print(f"  model.SketchManager -> {sm!r}")
        if sm is not None:
            sm_methods = [m for m in dir(sm) if not m.startswith("_") and "imension" in m.lower() or "elat" in m.lower() or "onstrain" in m.lower()]
            print(f"  SketchManager dim/relation methods: {sm_methods}")
    except Exception as e:
        print(f"  SketchManager EXC: {e}")

    print("\nClosing without saving...")
    sw.CloseDoc(_sw.prop(model, "GetTitle"))


if __name__ == "__main__":
    main()
