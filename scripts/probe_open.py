import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _sw

TARGET = r"D:\ClaudeProjects\TS2\models\working\testpart.SLDPRT"


def main():
    sw = _sw.connect()
    print(f"Connected. SolidWorks {_sw.prop(sw, 'RevisionNumber')}")

    model, errors, warnings = _sw.open_part(sw, TARGET)

    print(f"OpenDoc6 errors:   {errors}")
    print(f"OpenDoc6 warnings: {warnings}")

    if model is None:
        print("FAIL: OpenDoc6 returned None")
        sys.exit(1)

    title = model.GetTitle if isinstance(model.GetTitle, str) else model.GetTitle()
    path = model.GetPathName if isinstance(model.GetPathName, str) else model.GetPathName()
    doctype = model.GetType if isinstance(model.GetType, int) else model.GetType()

    print(f"GetTitle:    {title}")
    print(f"GetPathName: {path}")
    print(f"GetType:     {doctype}  (1=part, 2=asm, 3=drw)")


if __name__ == "__main__":
    main()
