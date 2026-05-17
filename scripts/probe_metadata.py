import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _sw

TARGET = r"D:\ClaudeProjects\TS2\models\working\testpart.SLDPRT"

DOC_TYPE_NAMES = {1: "PART", 2: "ASSEMBLY", 3: "DRAWING"}

LENGTH_UNIT_NAMES = {
    0: "mm", 1: "cm", 2: "m", 3: "in", 4: "ft", 5: "ft&in",
    6: "angstrom", 7: "nm", 8: "micron", 9: "mil", 10: "microinch",
    11: "user-defined",
}


def main():
    sw = _sw.connect()
    print(f"Connected. SolidWorks {_sw.prop(sw, 'RevisionNumber')}")

    model, errors, warnings = _sw.open_part(sw, TARGET)
    if model is None:
        print(f"FAIL: OpenDoc6 returned None (errors={errors}, warnings={warnings})")
        sys.exit(1)

    title = _sw.prop(model, "GetTitle")
    path = _sw.prop(model, "GetPathName")
    doctype = _sw.prop(model, "GetType")

    print(f"Title:  {title}")
    print(f"Path:   {path}")
    print(f"Type:   {doctype} ({DOC_TYPE_NAMES.get(doctype, '?')})")

    units = _sw.prop(model, "GetUnits")
    print(f"\nGetUnits raw: {units!r}")
    if isinstance(units, (tuple, list)) and len(units) >= 3:
        length_code = units[0]
        print(f"  [0] length unit code: {length_code} ({LENGTH_UNIT_NAMES.get(length_code, '?')})")
        print(f"  [1] fraction denom:   {units[1]}")
        print(f"  [2] decimal places:   {units[2]}")
        if len(units) >= 6:
            dual_code = units[3]
            print(f"  [3] dual length code: {dual_code} ({LENGTH_UNIT_NAMES.get(dual_code, '?')})")
            print(f"  [4] dual fraction:    {units[4]}")
            print(f"  [5] dual decimals:    {units[5]}")
        if len(units) > 6:
            print(f"  [6+] extra:           {units[6:]}")


if __name__ == "__main__":
    main()
