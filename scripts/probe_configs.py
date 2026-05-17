import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _sw

TARGET = r"D:\ClaudeProjects\TS2\models\working\testpart.SLDPRT"


def try_call(label, fn):
    try:
        result = fn()
        print(f"  {label:50s} = {result!r}")
        return result
    except Exception as e:
        print(f"  {label:50s} ! {type(e).__name__}: {e}")
        return None


def main():
    sw = _sw.connect()
    print(f"Connected. SolidWorks {_sw.prop(sw, 'RevisionNumber')}")

    model, errors, warnings = _sw.open_part(sw, TARGET)
    if model is None:
        print(f"FAIL: OpenDoc6 returned None (errors={errors}, warnings={warnings})")
        sys.exit(1)

    print(f"Title: {_sw.prop(model, 'GetTitle')}\n")

    print("--- via GetConfigurationNames + GetActiveConfiguration ---")
    names = try_call("model.GetConfigurationNames()", lambda: model.GetConfigurationNames())
    active = try_call("model.GetActiveConfiguration()", lambda: model.GetActiveConfiguration())
    if active is not None:
        try_call("active.Name", lambda: active.Name)
        try_call("active.IsDerived", lambda: active.IsDerived)
        try_call("active.Comment", lambda: active.Comment)

    print("\n--- via ConfigurationManager ---")
    cmgr = try_call("model.ConfigurationManager", lambda: model.ConfigurationManager)
    if cmgr is not None:
        try_call("cmgr.ActiveConfiguration", lambda: cmgr.ActiveConfiguration)
        active2 = cmgr.ActiveConfiguration
        if active2 is not None:
            try_call("cmgr.ActiveConfiguration.Name", lambda: active2.Name)

    print("\n--- per-config detail ---")
    if names:
        active_name = active.Name if active is not None else None
        for n in names:
            cfg = try_call(f"model.GetConfigurationByName({n!r})",
                           lambda nm=n: model.GetConfigurationByName(nm))
            if cfg is None:
                continue
            is_active = (n == active_name)
            try_call(f"  [{n}] cfg.Name", lambda c=cfg: c.Name)
            try_call(f"  [{n}] cfg.IsDerived", lambda c=cfg: c.IsDerived)
            try_call(f"  [{n}] cfg.Comment", lambda c=cfg: c.Comment)
            print(f"  [{n}] active? {is_active}")


if __name__ == "__main__":
    main()
