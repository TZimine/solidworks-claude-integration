"""Render isometric, front, top, right, and a wireframe iso of a model
to outputs/renders/<basename>/<view>.png.

Usage:
    py render_views.py <path-to-file> [--keep-open]
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _sw

OUTPUT_ROOT = r"D:\ClaudeProjects\TS2\outputs\renders"

VIEWS = [
    ("*Isometric", "iso.png"),
    ("*Front",     "front.png"),
    ("*Top",       "top.png"),
    ("*Right",     "right.png"),
]


def save_view(model, view_name, out_path):
    model.ShowNamedView2(view_name, -1)
    model.ViewZoomtofit2()
    # let SolidWorks render before snapping
    time.sleep(0.2)

    ext = model.Extension
    result = ext.SaveAs(out_path, 0, 0, None, 0, 0)
    if isinstance(result, tuple):
        ok, errors, warnings = result[0], result[1], result[2]
    else:
        ok, errors, warnings = result, 0, 0
    size = os.path.getsize(out_path) if os.path.isfile(out_path) else None
    return ok, errors, warnings, size


def main():
    p = argparse.ArgumentParser()
    p.add_argument("path")
    p.add_argument("--keep-open", action="store_true")
    args = p.parse_args()

    abs_path = os.path.abspath(args.path)
    if not os.path.isfile(abs_path):
        print(f"FAIL: not a file: {abs_path}")
        sys.exit(2)

    sw = _sw.connect()
    print(f"Connected. SolidWorks {_sw.prop(sw, 'RevisionNumber')}")

    model, errors, warnings = _sw.open_doc(sw, abs_path)
    if model is None:
        print(f"FAIL: OpenDoc6 returned None (errors={errors}, warnings={warnings})")
        sys.exit(4)

    title = _sw.prop(model, "GetTitle")
    print(f"Opened: {title}")

    base = os.path.splitext(os.path.basename(abs_path))[0]
    out_dir = os.path.join(OUTPUT_ROOT, base)
    os.makedirs(out_dir, exist_ok=True)

    print(f"\nWriting renders to {out_dir}\\")

    for view_name, fname in VIEWS:
        out_path = os.path.join(out_dir, fname)
        ok, errs, warns, size = save_view(model, view_name, out_path)
        marker = "OK" if ok else "FAIL"
        size_str = f"{size:,} bytes" if size else "no file"
        print(f"  [{marker}] {fname:20s} ({view_name:14s}) errs={errs} warns={warns} {size_str}")

    # Wireframe iso
    print("\nSwitching to wireframe display mode...")
    try:
        model.ViewDisplayWireframe()
    except Exception as e:
        print(f"  ! ViewDisplayWireframe failed: {e}")
    out_path = os.path.join(out_dir, "iso_wireframe.png")
    ok, errs, warns, size = save_view(model, "*Isometric", out_path)
    marker = "OK" if ok else "FAIL"
    size_str = f"{size:,} bytes" if size else "no file"
    print(f"  [{marker}] iso_wireframe.png    (*Isometric)    errs={errs} warns={warns} {size_str}")

    # restore shaded-with-edges
    try:
        model.ViewDisplayShaded()
    except Exception:
        pass

    if not args.keep_open:
        _sw.close(sw, model)


if __name__ == "__main__":
    main()
