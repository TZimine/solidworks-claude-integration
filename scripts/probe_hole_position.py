"""Probe: find the existing hole's center and the face it lives on.

Strategy:
  1. Read Sketch3 (the cut sketch) — enumerate sketch arcs/circles, get center.
  2. Query Cut-Extrude1's sketch plane via IFeature.GetDefinition / FeatureData
     to determine the face the hole was drilled into.
  3. Print enough info to feed into HoleWizard5.

Closes WITHOUT saving.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _sw

PART = r"D:\ClaudeProjects\TS2\models\working\testpart.SLDPRT"


def main():
    sw = _sw.connect()
    model, _, _ = _sw.open_doc(sw, PART)
    print(f"Opened: {_sw.prop(model, 'GetTitle')}")

    # 1) Walk all features, find Sketch3
    sk3_feat = _sw.feature_by_name(model, "Sketch3")
    if sk3_feat is None:
        print("FAIL: Sketch3 not found"); return
    sk3_feat = _sw.cast(sk3_feat, "IFeature")
    print(f"Sketch3 type: {sk3_feat.GetTypeName2()}")

    sk3 = sk3_feat.GetSpecificFeature2()  # ISketch
    sk3 = _sw.cast(sk3, "ISketch")

    # Sketch entities — try GetArcs2 (no args), fall back to GetSketchSegments
    circles = None
    try:
        circles = sk3.GetArcs2() or ()
        print(f"Sketch3: GetArcs2 returned {len(circles)} entries")
    except Exception as e:
        print(f"  GetArcs2 failed: {e}")
    if not circles:
        try:
            segs = sk3.GetSketchSegments() or ()
            print(f"Sketch3: GetSketchSegments returned {len(segs)} entries")
            circles = segs
        except Exception as e:
            print(f"  GetSketchSegments failed: {e}")
            circles = ()
    for i, c in enumerate(circles):
        try:
            c_arc = _sw.cast(c, "ISketchArc")
            center = c_arc.GetCenterPoint2()
            radius = c_arc.GetRadius()
            print(f"    [{i}] arc center(model_units_m)={center}  r={radius}  ({radius*1000:.3f} mm)")
        except Exception as e:
            print(f"    [{i}] not arc: {e}")

    # 2) Cut-Extrude1 -> find sketch plane / referenced face
    cut_feat = _sw.feature_by_name(model, "Cut-Extrude1")
    cut_feat = _sw.cast(cut_feat, "IFeature")
    print(f"\nCut-Extrude1 type: {cut_feat.GetTypeName2()}")
    try:
        defn = cut_feat.GetDefinition()
        print(f"  GetDefinition: {defn!r}")
        # Try ExtrudeFeatureData2 surface
        try:
            ext = _sw.cast(defn, "IExtrudeFeatureData2")
            print(f"    cast IExtrudeFeatureData2 ok")
        except Exception as e:
            print(f"    cast IExtrudeFeatureData2 failed: {e}")
    except Exception as e:
        print(f"  GetDefinition failed: {e}")

    # 3) Walk body faces — identify by normal direction and area
    print("\nBody faces:")
    part = _sw.cast(model, "IPartDoc")
    bodies = part.GetBodies2(0, True)  # 0 = solid bodies
    if bodies:
        body = _sw.cast(bodies[0], "IBody2")
        face = body.GetFirstFace()
        idx = 0
        while face is not None:
            face = _sw.cast(face, "IFace2")
            try:
                normal = face.Normal  # 3-tuple
            except Exception:
                normal = None
            try:
                area = face.GetArea()
            except Exception:
                area = None
            try:
                box = face.GetBox()  # (xmin,ymin,zmin,xmax,ymax,zmax)
            except Exception:
                box = None
            print(f"  face[{idx}] normal={normal} area={area} bbox={box}")
            try:
                face = face.GetNextFace()
            except Exception:
                face = None
            idx += 1
            if idx > 30: break

    sw.QuitDoc(_sw.prop(model, "GetTitle"))
    print("\nClosed without saving.")


if __name__ == "__main__":
    main()
