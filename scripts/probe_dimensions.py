import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _sw

TARGET = r"D:\ClaudeProjects\TS2\models\working\testpart.SLDPRT"


def safe(label, fn):
    try:
        return fn()
    except Exception as e:
        return f"<{type(e).__name__}: {e}>"


def dump_dim(disp_dim, indent="    "):
    disp_dim = _sw.cast(disp_dim, "IDisplayDimension")
    sel_name = safe("GetNameForSelection", lambda: disp_dim.GetNameForSelection())

    dim_raw = disp_dim.GetDimension()
    if dim_raw is None:
        print(f"{indent}sel={sel_name!r}  (GetDimension returned None)")
        return
    dim = _sw.cast(dim_raw, "IDimension")

    name = safe("Name",        lambda: dim.Name)
    full = safe("FullName",    lambda: dim.FullName)
    value = safe("Value",       lambda: dim.Value)
    sys_val = safe("SystemValue", lambda: dim.SystemValue)
    read_only = safe("ReadOnly", lambda: dim.ReadOnly)
    tol_type = safe("GetToleranceType", lambda: dim.GetToleranceType())
    tol_vals = safe("GetToleranceValues", lambda: dim.GetToleranceValues())

    print(f"{indent}sel={sel_name!r}")
    print(f"{indent}  Name={name!r}  FullName={full!r}")
    print(f"{indent}  Value={value!r}  SystemValue={sys_val!r}  ReadOnly={read_only!r}")
    print(f"{indent}  ToleranceType={tol_type!r}  ToleranceValues={tol_vals!r}")


def walk_features(feat, sub=False):
    while feat is not None:
        feat = _sw.cast(feat, "IFeature")
        name = feat.Name
        try:
            type_name = feat.GetTypeName2()
        except Exception:
            type_name = "?"

        first_dim = None
        try:
            first_dim = feat.GetFirstDisplayDimension()
        except Exception:
            pass

        if first_dim is not None:
            print(f"\n[{type_name}] {name!r}")
            dd = first_dim
            i = 0
            seen_ids = set()
            while dd is not None:
                dd = _sw.cast(dd, "IDisplayDimension")
                # avoid infinite loop on bad GetNext implementations
                key = id(dd._oleobj_) if hasattr(dd, "_oleobj_") else id(dd)
                if key in seen_ids:
                    print("    (loop detected, stopping)")
                    break
                seen_ids.add(key)
                print(f"  dim #{i}:")
                dump_dim(dd)
                i += 1
                try:
                    dd = dd.GetNext5()
                except Exception:
                    try:
                        dd = dd.GetNext2()
                    except Exception:
                        try:
                            dd = dd.GetNext()
                        except Exception:
                            dd = None

        # recurse into sub-features
        try:
            child = feat.GetFirstSubFeature()
        except Exception:
            child = None
        if child is not None:
            walk_features(child, sub=True)

        try:
            feat = feat.GetNextSubFeature() if sub else feat.GetNextFeature()
        except Exception:
            feat = None


def main():
    sw = _sw.connect()
    print(f"Connected. SolidWorks {_sw.prop(sw, 'RevisionNumber')}")

    model, errors, warnings = _sw.open_part(sw, TARGET)
    if model is None:
        print(f"FAIL: OpenDoc6 returned None (errors={errors}, warnings={warnings})")
        sys.exit(1)

    print(f"Title: {_sw.prop(model, 'GetTitle')}")

    first = model.FirstFeature()
    if first is None:
        print("(no features)")
        return

    walk_features(first)


if __name__ == "__main__":
    main()
