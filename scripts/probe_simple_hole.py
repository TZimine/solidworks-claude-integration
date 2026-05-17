"""Probe: IFeatureManager.SimpleHole2 to drill ONE Ø2.4mm hole on face[0] at
(-20, 0, +10mm) with end condition Up To Next. NO save.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _sw

PART = r"D:\ClaudeProjects\TS2\models\working\testpart.SLDPRT"

END_BLIND       = 0
END_THROUGH_ALL = 1
END_UP_TO_NEXT  = 2


def mass_g(model):
    mp = model.Extension.CreateMassProperty()
    return float(mp.Mass) * 1000


def main():
    sw = _sw.connect()
    model, _, _ = _sw.open_doc(sw, PART)
    print(f"Opened: {_sw.prop(model, 'GetTitle')}  baseline mass={mass_g(model):.3f} g")

    # Select face[0] at the hole center point
    model.ClearSelection2(True)
    sel = model.Extension.SelectByID2("", "FACE", -0.020, 0.0, 0.010,
                                      False, 0, None, 0)
    print(f"\nSelectByID2 face[0] @ (-20, 0, +10mm): {sel}")

    fm = model.FeatureManager
    feat = fm.SimpleHole2(
        0.0024,           # Dia (m)
        True,             # Sd: single direction
        False,            # Flip
        False,            # Dir
        END_UP_TO_NEXT,   # T1
        END_BLIND,        # T2
        0.0, 0.0,         # D1, D2
        False, False,     # Dchk1, Dchk2
        False, False,     # Ddir1, Ddir2
        0.0, 0.0,         # Dang1, Dang2
        False, False,     # OffsetReverse1, OffsetReverse2
        False, False,     # TranslateSurface1, TranslateSurface2
        True, True,       # UseFeatScope, UseAutoSelect
        False, False, False,  # AssemblyFeatureScope, AutoSelectComponents, PropagateFeatureToParts
    )
    print(f"\nSimpleHole2 -> {feat!r}")
    if feat is not None:
        feat = _sw.cast(feat, "IFeature")
        print(f"  feature name = {_sw.prop(feat, 'Name')!r}  type = {feat.GetTypeName2()!r}")
    print(f"After: mass={mass_g(model):.3f} g")

    sw.QuitDoc(_sw.prop(model, "GetTitle"))
    print("\nClosed without saving.")


if __name__ == "__main__":
    main()
