"""Set fixture data on testpart.SLDPRT for verifying probe_custom_props (S5)
and probe_dimensions (S7) against real values. Operates only on
models/working/testpart.SLDPRT (originals/ untouched).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _sw

TARGET = r"D:\ClaudeProjects\TS2\models\working\testpart.SLDPRT"

SW_CUSTOM_INFO_TEXT = 30
SW_CUSTOM_PROPERTY_REPLACE_VALUE = 2

SW_TOL_BILAT = 2

DIM_FULLNAME = "D1@Sketch1"
TOL_MAX_M = 0.0001    # +0.1 mm
TOL_MIN_M = -0.00005  # -0.05 mm


def add_prop(cpm, name, value, label):
    rc = cpm.Add3(name, SW_CUSTOM_INFO_TEXT, value,
                  SW_CUSTOM_PROPERTY_REPLACE_VALUE)
    print(f"  [{label}] Add3({name!r}, text, {value!r}) -> {rc}")


def main():
    sw = _sw.connect()
    print(f"Connected. SolidWorks {_sw.prop(sw, 'RevisionNumber')}\n")

    model, errors, warnings = _sw.open_part(sw, TARGET)
    if model is None:
        print(f"FAIL: OpenDoc6 returned None (errors={errors}, warnings={warnings})")
        sys.exit(1)
    print(f"Opened: {_sw.prop(model, 'GetTitle')}\n")

    ext = model.Extension

    print("Adding custom properties...")
    file_cpm = ext.CustomPropertyManager("")
    add_prop(file_cpm, "FINISH",      "ANODIZE BLACK",       "file")
    add_prop(file_cpm, "DESCRIPTION", "Test bracket part",   "file")

    cfg_cpm = ext.CustomPropertyManager("Default")
    add_prop(cfg_cpm, "PARTNO",   "TS2-001",  "config=Default")
    add_prop(cfg_cpm, "REVISION", "A",        "config=Default")

    print(f"\nSetting bilateral tolerance on {DIM_FULLNAME}...")
    dim_raw = model.Parameter(DIM_FULLNAME)
    if dim_raw is None:
        print(f"  FAIL: Parameter({DIM_FULLNAME!r}) returned None")
    else:
        dim = _sw.cast(dim_raw, "IDimension")
        print(f"  Found: Name={dim.Name!r}  Value={dim.Value}")

        tol = dim.Tolerance
        # Tolerance is auto-cast (IID is in the property entry); confirm:
        print(f"  Tolerance obj: {tol!r}")
        try:
            tol.Type = SW_TOL_BILAT
            print(f"  set Tolerance.Type = {SW_TOL_BILAT} (BILAT)")
        except Exception as e:
            print(f"  ! Tolerance.Type = ... raised {type(e).__name__}: {e}")

        try:
            rc = tol.SetValues(TOL_MIN_M, TOL_MAX_M)
            print(f"  SetValues(min={TOL_MIN_M}, max={TOL_MAX_M}) -> {rc}")
        except Exception as e:
            print(f"  ! SetValues raised {type(e).__name__}: {e}")

    print("\nSaving model...")
    # Save3 takes (Options, Errors_byref, Warnings_byref) — typed-mode tuple return
    save_options = 0
    result = model.Save3(save_options, 0, 0)
    if isinstance(result, tuple):
        ok, errs, warns = result[0], result[1] if len(result) > 1 else 0, result[2] if len(result) > 2 else 0
    else:
        ok, errs, warns = result, 0, 0
    print(f"  Save3 -> ok={ok}  errors={errs}  warnings={warns}")

    print("\nClosing.")
    _sw.close(sw, model)


if __name__ == "__main__":
    main()
