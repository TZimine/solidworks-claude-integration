import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _sw

TARGET = r"D:\ClaudeProjects\TS2\models\working\testpart.SLDPRT"

MAX_DEPTH = 10


def feat_info(feat):
    name = feat.Name
    try:
        type_name = feat.GetTypeName2()
    except Exception:
        try:
            type_name = feat.GetTypeName()
        except Exception as e:
            type_name = f"<err: {e!r}>"
    try:
        suppressed = bool(feat.IsSuppressed())
    except Exception as e:
        suppressed = f"<err: {e!r}>"
    return name, type_name, suppressed


def walk(feat, depth, count, sub=False):
    if depth > MAX_DEPTH:
        print(f"{'  ' * depth}... max depth reached")
        return count
    while feat is not None:
        feat = _sw.cast(feat, "IFeature")
        name, type_name, suppressed = feat_info(feat)
        marker = "S" if suppressed is True else " "
        prefix = "  " * depth
        kind = "sub" if sub else "top"
        print(f"  [{count:3d}] {prefix}{marker} ({kind}) {type_name:25s} {name!r}")
        count += 1

        try:
            child = feat.GetFirstSubFeature()
        except Exception:
            child = None
        if child is not None:
            count = walk(child, depth + 1, count, sub=True)

        try:
            feat = feat.GetNextSubFeature() if sub else feat.GetNextFeature()
        except Exception:
            feat = None
    return count


def main():
    sw = _sw.connect()
    print(f"Connected. SolidWorks {_sw.prop(sw, 'RevisionNumber')}")

    model, errors, warnings = _sw.open_part(sw, TARGET)
    if model is None:
        print(f"FAIL: OpenDoc6 returned None (errors={errors}, warnings={warnings})")
        sys.exit(1)

    print(f"Title: {_sw.prop(model, 'GetTitle')}\n")

    print("Feature tree:")
    first = model.FirstFeature()
    if first is None:
        print("  (no features)")
        return

    total = walk(first, depth=0, count=1, sub=False)
    print(f"\nTotal features visited: {total - 1}")


if __name__ == "__main__":
    main()
