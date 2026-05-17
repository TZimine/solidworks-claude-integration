"""Audit how many dims actually exist per user feature, via three paths:
1. Display dimension chain via GetFirstDisplayDimension + GetNext{,2,5}
2. model.Parameter("Dn@FeatName") for n=1..6
3. feat.GetDisplayDimensionCount + GetDisplayDimension(i)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _sw

TARGET = r"D:\ClaudeProjects\TS2\models\working\testpart.SLDPRT"
USER_FEATS = ["Sketch1", "Boss-Extrude1", "Sketch2", "Boss-Extrude2", "Sketch3", "Cut-Extrude1"]


def safe(fn, default=None):
    try:
        return fn()
    except Exception as e:
        return f"<{type(e).__name__}: {e}>"


def main():
    sw = _sw.connect()
    print(f"Connected. SolidWorks {_sw.prop(sw, 'RevisionNumber')}")
    model, errors, warnings = _sw.open_part(sw, TARGET)
    if model is None:
        print(f"FAIL: errors={errors}, warnings={warnings}")
        return

    print(f"Title: {_sw.prop(model, 'GetTitle')}\n")

    # Path A: model.Parameter("Dn@FeatName") brute-force
    print("=== Path A: model.Parameter('Dn@<feat>') brute-force ===")
    for feat_name in USER_FEATS:
        print(f"\n  feat={feat_name}")
        for n in range(1, 8):
            label = f"D{n}@{feat_name}"
            dim_raw = safe(lambda l=label: model.Parameter(l))
            if dim_raw is None or isinstance(dim_raw, str):
                print(f"    Parameter({label!r}) -> {dim_raw!r}")
                continue
            dim = _sw.cast(dim_raw, "IDimension")
            val = safe(lambda d=dim: float(d.Value))
            full = safe(lambda d=dim: d.FullName)
            print(f"    Parameter({label!r}) -> Value={val}  FullName={full!r}")

    first = model.FirstFeature()

    # Path C: feat.GetDisplayDimension(Index)
    print("\n=== Path C: feat.GetDisplayDimension(Index) ===")
    seen_feat_ids2 = set()
    def visit_for_indexed(feat, sub):
        while feat is not None:
            feat = _sw.cast(feat, "IFeature")
            fid = safe(lambda f=feat: f.GetID())
            name = safe(lambda f=feat: f.Name)
            if fid in seen_feat_ids2:
                feat = safe(lambda f=feat: f.GetNextSubFeature() if sub else f.GetNextFeature())
                continue
            seen_feat_ids2.add(fid)
            if name in USER_FEATS:
                print(f"\n  {name}:")
                for i in range(0, 8):
                    raw = safe(lambda f=feat, i=i: f.GetDisplayDimension(i))
                    if raw is None or isinstance(raw, str):
                        print(f"    [{i}] -> {raw!r}")
                        continue
                    dd = _sw.cast(raw, "IDisplayDimension")
                    sel = safe(lambda x=dd: x.GetNameForSelection())
                    dim_raw = safe(lambda x=dd: x.GetDimension())
                    fn = "?"
                    val = "?"
                    if dim_raw is not None and not isinstance(dim_raw, str):
                        d = _sw.cast(dim_raw, "IDimension")
                        fn = safe(lambda x=d: x.FullName)
                        val = safe(lambda x=d: float(x.Value))
                    print(f"    [{i}] sel={sel!r}  full={fn!r}  val={val}")
            child = safe(lambda f=feat: f.GetFirstSubFeature())
            if child is not None and not isinstance(child, str):
                visit_for_indexed(child, sub=True)
            feat = safe(lambda f=feat: f.GetNextSubFeature() if sub else f.GetNextFeature())

    if first is not None:
        visit_for_indexed(first, sub=False)

    # Path B: walk features again, print every dim via the linked list, but DEEPER
    print("\n=== Path B: linked-list walk with full repr per step ===")
    seen_feat_ids = set()

    def walk(feat, sub):
        while feat is not None:
            feat = _sw.cast(feat, "IFeature")
            fid = safe(lambda f=feat: f.GetID())
            name = safe(lambda f=feat: f.Name)
            if fid in seen_feat_ids:
                feat = safe(lambda f=feat: f.GetNextSubFeature() if sub else f.GetNextFeature())
                continue
            seen_feat_ids.add(fid)

            if name in USER_FEATS:
                first_dd = safe(lambda f=feat: f.GetFirstDisplayDimension())
                print(f"\n  {name} -- GetFirstDisplayDimension -> {first_dd!r}")
                dd = first_dd
                step = 0
                while dd is not None and step < 10:
                    dd = _sw.cast(dd, "IDisplayDimension")
                    sel = safe(lambda x=dd: x.GetNameForSelection())
                    dim_raw = safe(lambda x=dd: x.GetDimension())
                    fn = "?"
                    val = "?"
                    if dim_raw is not None and not isinstance(dim_raw, str):
                        d = _sw.cast(dim_raw, "IDimension")
                        fn = safe(lambda x=d: x.FullName)
                        val = safe(lambda x=d: float(x.Value))
                    print(f"    step {step}: sel={sel!r}  full={fn!r}  val={val}")
                    nxt5 = safe(lambda x=dd: x.GetNext5())
                    nxt2 = safe(lambda x=dd: x.GetNext2())
                    nxt1 = safe(lambda x=dd: x.GetNext())
                    print(f"      GetNext5={nxt5!r}  GetNext2={nxt2!r}  GetNext={nxt1!r}")
                    nxt = nxt5 if nxt5 is not None and not isinstance(nxt5, str) else None
                    if nxt is None:
                        nxt = nxt2 if nxt2 is not None and not isinstance(nxt2, str) else None
                    if nxt is None:
                        nxt = nxt1 if nxt1 is not None and not isinstance(nxt1, str) else None
                    dd = nxt
                    step += 1

            child = safe(lambda f=feat: f.GetFirstSubFeature())
            if child is not None and not isinstance(child, str):
                walk(child, sub=True)
            feat = safe(lambda f=feat: f.GetNextSubFeature() if sub else f.GetNextFeature())

    if first is not None:
        walk(first, sub=False)


if __name__ == "__main__":
    main()
