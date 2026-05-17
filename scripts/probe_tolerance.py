"""Probe IDimension tolerance API. Reads, clears, re-reads — does NOT save.

Run:
    py scripts/probe_tolerance.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _sw

PART = r"D:\ClaudeProjects\TS2\models\working\testpart.SLDPRT"
DIM_NAME = "D1@Sketch1"

TOL_NAMES = {0: "NONE", 1: "BASIC", 2: "BILAT", 3: "LIMIT", 4: "SYM",
             5: "MIN", 6: "MAX", 7: "FIT", 10: "GENERAL"}


def read_tol(dim):
    t = dim.GetToleranceType()
    vals = dim.GetToleranceValues()
    return t, vals


def main():
    sw = _sw.connect()
    print(f"Connected. SolidWorks {_sw.prop(sw, 'RevisionNumber')}")
    model, errs, warns = _sw.open_doc(sw, PART)
    print(f"Opened: {_sw.prop(model, 'GetTitle')}")

    dim_raw = model.Parameter(DIM_NAME)
    dim = _sw.cast(dim_raw, "IDimension")

    t, v = read_tol(dim)
    print(f"\nBefore: type={t} ({TOL_NAMES.get(t,'?')}) values={v}")

    print("Calling SetToleranceType(0) ...")
    try:
        rc = dim.SetToleranceType(0)
        print(f"  return = {rc!r}")
    except Exception as e:
        print(f"  FAIL: {type(e).__name__}: {e}")

    t2, v2 = read_tol(dim)
    print(f"After:  type={t2} ({TOL_NAMES.get(t2,'?')}) values={v2}")

    # CRITICAL: close WITHOUT saving so disk file is untouched.
    title = _sw.prop(model, "GetTitle")
    sw.QuitDoc(title)  # discards changes
    print("\nClosed without saving (QuitDoc).")


if __name__ == "__main__":
    main()
