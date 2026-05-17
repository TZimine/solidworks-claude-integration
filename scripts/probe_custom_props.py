import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _sw

TARGET = r"D:\ClaudeProjects\TS2\models\working\testpart.SLDPRT"

PROP_TYPE_NAMES = {
    0: "unknown",
    30: "text",
    63: "date",
    11: "yes/no",
    5: "number",
}


def try_call(label, fn):
    try:
        result = fn()
        print(f"  {label:55s} = {result!r}")
        return result
    except Exception as e:
        print(f"  {label:55s} ! {type(e).__name__}: {e}")
        return None


def dump_cpm(label, cpm):
    print(f"\n--- {label} ---")
    if cpm is None:
        print("  (cpm is None)")
        return

    count = try_call("cpm.Count", lambda: cpm.Count)
    names = try_call("cpm.GetNames()", lambda: cpm.GetNames())

    if not names:
        print("  (no properties)")
        return

    for name in names:
        print(f"\n  Property: {name!r}")
        try_call(f"    GetType2({name!r})", lambda n=name: cpm.GetType2(n))
        # Get6 returns (typecode, ValOut, ResolvedValOut, WasResolved, LinkToProperty)
        try_call(f"    Get6({name!r}, False)",
                 lambda n=name: cpm.Get6(n, False))


def main():
    sw = _sw.connect()
    print(f"Connected. SolidWorks {_sw.prop(sw, 'RevisionNumber')}")

    model, errors, warnings = _sw.open_part(sw, TARGET)
    if model is None:
        print(f"FAIL: OpenDoc6 returned None (errors={errors}, warnings={warnings})")
        sys.exit(1)

    print(f"Title: {_sw.prop(model, 'GetTitle')}")

    ext = model.Extension

    # File-level (config arg = "")
    file_cpm = try_call("ext.CustomPropertyManager('')",
                        lambda: ext.CustomPropertyManager(""))
    dump_cpm("file-level (config='')", file_cpm)

    # Per-config
    config_names = _sw.prop(model, "GetConfigurationNames") or ()
    for cname in config_names:
        cpm = try_call(f"ext.CustomPropertyManager({cname!r})",
                       lambda c=cname: ext.CustomPropertyManager(c))
        dump_cpm(f"config={cname!r}", cpm)


if __name__ == "__main__":
    main()
