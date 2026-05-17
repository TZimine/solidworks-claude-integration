import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _sw

TARGET = r"D:\ClaudeProjects\TS2\models\working\testpart.SLDPRT"


def try_call(label, fn):
    try:
        result = fn()
        print(f"  {label:40s} = {result!r}")
        return result
    except Exception as e:
        print(f"  {label:40s} ! {type(e).__name__}: {e}")
        return None


def main():
    sw = _sw.connect()
    print(f"Connected. SolidWorks {_sw.prop(sw, 'RevisionNumber')}")

    model, errors, warnings = _sw.open_part(sw, TARGET)
    if model is None:
        print(f"FAIL: OpenDoc6 returned None (errors={errors}, warnings={warnings})")
        sys.exit(1)

    print(f"Title: {_sw.prop(model, 'GetTitle')}")

    ext = model.Extension
    print(f"\nExtension: {ext}")

    print("\n--- CreateMassProperty variants ---")
    mp = try_call("ext.CreateMassProperty()", lambda: ext.CreateMassProperty())
    if mp is None:
        mp = try_call("ext.CreateMassProperty2(0)", lambda: ext.CreateMassProperty2(0))
    if mp is None:
        print("could not create mass property; aborting")
        sys.exit(1)

    print(f"\nMassProperty obj: {mp}")
    print("\n--- scalar reads ---")
    try_call("mp.Mass",         lambda: mp.Mass)
    try_call("mp.Volume",       lambda: mp.Volume)
    try_call("mp.SurfaceArea",  lambda: mp.SurfaceArea)
    try_call("mp.Density",      lambda: mp.Density)

    print("\n--- vector reads ---")
    try_call("mp.CenterOfMass",                  lambda: mp.CenterOfMass)
    try_call("mp.PrincipleMomentsOfInertia",     lambda: mp.PrincipleMomentsOfInertia)
    try_call("mp.PrincipleAxesOfInertia(0)",     lambda: mp.PrincipleAxesOfInertia(0))
    try_call("mp.PrincipleAxesOfInertia(1)",     lambda: mp.PrincipleAxesOfInertia(1))
    try_call("mp.PrincipleAxesOfInertia(2)",     lambda: mp.PrincipleAxesOfInertia(2))
    try_call("mp.GetMomentOfInertia(0)",         lambda: mp.GetMomentOfInertia(0))


if __name__ == "__main__":
    main()
