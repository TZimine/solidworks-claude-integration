"""STEP 3 — Rebuild safety net.

Opens a model, snapshots mass props, runs ForceRebuild3, walks features for
error/warning codes, snapshots mass props again, writes a JSON report, and
exits 0 on a clean rebuild or non-zero on any rebuild/feature error.

CLI:
    py scripts/rebuild_check.py <path-to-model> [--keep-open]

Module use (called from apply_edit.py):
    from rebuild_check import check_open_model
    report, exit_code = check_open_model(sw, model, source_path)
"""
import argparse
import datetime
import json
import os
import sys
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _sw

OUTPUT_DIR = r"D:\ClaudeProjects\TS2\outputs\logs"

# Threshold for considering a mass-property scalar "drifted". Anything below
# this is treated as floating-point noise (probe showed e-17 noise on CoM).
DRIFT_ABS_TOL = 1e-9


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:
        return default


def _mass_snapshot(model):
    try:
        mp = model.Extension.CreateMassProperty()
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}
    out = {}
    for name in ("Mass", "Volume", "SurfaceArea", "Density"):
        out[name] = _safe(lambda n=name: float(getattr(mp, n)))
    com = _safe(lambda: list(mp.CenterOfMass))
    out["CenterOfMass"] = com
    return out


def _diff_scalar(after, before):
    if not (isinstance(after, (int, float)) and isinstance(before, (int, float))):
        return None
    return after - before


def _mass_diff(before, after):
    out = {}
    drifted = False
    for name in ("Mass", "Volume", "SurfaceArea", "Density"):
        d = _diff_scalar(after.get(name), before.get(name))
        out[name] = d
        if d is not None and abs(d) > DRIFT_ABS_TOL:
            drifted = True
    com_a, com_b = after.get("CenterOfMass"), before.get("CenterOfMass")
    if isinstance(com_a, list) and isinstance(com_b, list) and len(com_a) == len(com_b) == 3:
        com_d = [com_a[i] - com_b[i] for i in range(3)]
        out["CenterOfMass"] = com_d
        if any(abs(x) > DRIFT_ABS_TOL for x in com_d):
            drifted = True
    else:
        out["CenterOfMass"] = None
    out["drifted"] = drifted
    return out


def _walk_features_for_errors(model):
    """Walk the feature tree (top-level + subfeatures) and collect anything
    reporting a non-zero error code or warning flag.

    Returns (issues_list, total_walked).
    """
    issues = []
    seen_ids = set()
    total = 0

    def visit(feat, parent_name, sub):
        nonlocal total
        while feat is not None:
            feat = _sw.cast(feat, "IFeature")
            fid = _safe(lambda: feat.GetID())
            if fid is not None and fid in seen_ids:
                already = True
            else:
                already = False
                if fid is not None:
                    seen_ids.add(fid)

            name = _safe(lambda: feat.Name)
            type_name = _safe(lambda: feat.GetTypeName2())
            err_pair = _safe(lambda: feat.GetErrorCode2())
            if isinstance(err_pair, tuple) and len(err_pair) >= 2:
                err_code, has_warn = int(err_pair[0]), bool(err_pair[1])
            else:
                err_code, has_warn = 0, False
            suppressed = bool(_safe(lambda: feat.IsSuppressed(), default=False))

            if not already:
                total += 1
                if err_code != 0 or has_warn:
                    issues.append({
                        "name": name,
                        "type_name": type_name,
                        "parent": parent_name,
                        "is_sub_feature": sub,
                        "error_code": err_code,
                        "has_warning": has_warn,
                        "suppressed": suppressed,
                    })

                child = _safe(lambda f=feat: f.GetFirstSubFeature())
                if child is not None:
                    visit(child, parent_name=name, sub=True)

            try:
                feat = feat.GetNextSubFeature() if sub else feat.GetNextFeature()
            except Exception:
                feat = None

    first = _safe(lambda: model.FirstFeature())
    if first is not None:
        visit(first, parent_name=None, sub=False)
    return issues, total


def check_open_model(sw, model, source_path):
    """Run a rebuild check on an already-open model. Returns (report_dict, exit_code)."""
    title = _sw.prop(model, "GetTitle")
    stamp_before = _safe(lambda: int(_sw.prop(model, "GetUpdateStamp")))

    mass_before = _mass_snapshot(model)

    t0 = time.perf_counter()
    try:
        rb_ret = bool(model.ForceRebuild3(False))
        rb_error = None
    except Exception as e:
        rb_ret = False
        rb_error = f"{type(e).__name__}: {e}"
    rebuild_ms = (time.perf_counter() - t0) * 1000.0

    mass_after = _mass_snapshot(model)
    stamp_after = _safe(lambda: int(_sw.prop(model, "GetUpdateStamp")))
    mass_diff = _mass_diff(mass_before, mass_after)

    issues, total_features = _walk_features_for_errors(model)

    error_count = sum(1 for x in issues if x["error_code"] != 0)
    warning_count = sum(1 for x in issues if x["has_warning"])

    if rb_error is not None or rb_ret is False:
        status = "error"
    elif error_count > 0:
        status = "error"
    elif warning_count > 0:
        status = "warning"
    else:
        status = "ok"

    report = {
        "schema_version": 1,
        "captured_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "source": {
            "path": source_path,
            "title": title,
        },
        "status": status,
        "rebuild": {
            "force_rebuild3_return": rb_ret,
            "force_rebuild3_error":  rb_error,
            "duration_ms":           round(rebuild_ms, 2),
            "update_stamp_before":   stamp_before,
            "update_stamp_after":    stamp_after,
            "stamp_advanced":        (stamp_before is not None and stamp_after is not None
                                      and stamp_after > stamp_before),
        },
        "features": {
            "walked":   total_features,
            "errors":   error_count,
            "warnings": warning_count,
            "issues":   issues,
        },
        "mass_before": mass_before,
        "mass_after":  mass_after,
        "mass_diff":   mass_diff,
        "mates": None,  # TODO: assembly mate-error walk once we have an assembly fixture
    }
    exit_code = 0 if status == "ok" or status == "warning" else 1
    # Treat warnings as exit-0 but flagged; only hard errors block.
    return report, exit_code


def write_report(report, source_path):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    base = os.path.splitext(os.path.basename(source_path))[0]
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(OUTPUT_DIR, f"rebuild_{base}_{ts}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False, default=str)
    return out_path


def run_cli(path, keep_open=False):
    abs_path = os.path.abspath(path)
    if not os.path.isfile(abs_path):
        print(f"FAIL: not a file: {abs_path}")
        return 2

    try:
        _sw.doctype_for(abs_path)
    except ValueError as e:
        print(f"FAIL: {e}")
        return 2

    sw = _sw.connect()
    print(f"Connected. SolidWorks {_sw.prop(sw, 'RevisionNumber')}")
    model, errors, warnings = _sw.open_doc(sw, abs_path)
    if model is None:
        print(f"FAIL: OpenDoc6 returned None (errors={errors}, warnings={warnings})")
        return 4
    print(f"Opened: {_sw.prop(model, 'GetTitle')} (errors={errors}, warnings={warnings})")

    try:
        report, exit_code = check_open_model(sw, model, abs_path)
    except Exception:
        traceback.print_exc()
        if not keep_open:
            _sw.close(sw, model)
        return 5

    out_path = write_report(report, abs_path)

    rb = report["rebuild"]
    fb = report["features"]
    md = report["mass_diff"]
    print(f"\nstatus: {report['status']}")
    print(f"  ForceRebuild3 = {rb['force_rebuild3_return']}  ({rb['duration_ms']} ms)")
    print(f"  update stamp:  {rb['update_stamp_before']} -> {rb['update_stamp_after']}")
    print(f"  features walked: {fb['walked']}  errors: {fb['errors']}  warnings: {fb['warnings']}")
    if fb["issues"]:
        for it in fb["issues"]:
            tag = []
            if it["error_code"] != 0: tag.append(f"err={it['error_code']}")
            if it["has_warning"]:     tag.append("warn")
            print(f"    - {it['name']!r} ({it['type_name']}) {' '.join(tag)}")
    print(f"  mass drift: {'YES' if md.get('drifted') else 'no'}")
    print(f"\nWrote {out_path}")

    if not keep_open:
        _sw.close(sw, model)
    return exit_code


def main():
    p = argparse.ArgumentParser()
    p.add_argument("path")
    p.add_argument("--keep-open", action="store_true")
    args = p.parse_args()
    sys.exit(run_cli(args.path, keep_open=args.keep_open))


if __name__ == "__main__":
    main()
