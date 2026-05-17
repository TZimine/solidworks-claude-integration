"""STEP 4 — Apply a declarative edit instruction to a SolidWorks model.

CLI:
    py scripts/apply_edit.py <edit-instruction.json> [--dry-run] [--keep-open]

Edit instruction format:
    {
      "target_file": "D:/ClaudeProjects/TS2/models/working/foo.SLDPRT",
      "operations": [
        {"op": "set_dimension", "name": "D1@Sketch1", "value": 75, "units": "mm",
         "config": "Default"},                                  // config optional, default = active
        {"op": "suppress_feature",   "name": "Fillet1"},
        {"op": "unsuppress_feature", "name": "Chamfer1"},
        {"op": "set_custom_property", "name": "FINISH", "value": "ANODIZE BLACK",
         "config": ""},                                          // "" = file-level
        {"op": "set_material", "name": "6061 Alloy",
         "database": ""},                                        // "" = default db
        {"op": "set_active_configuration", "name": "Default"},
        {"op": "set_dimension_tolerance", "name": "D1@Sketch1",
         "type": "NONE"},                                       // clear tolerance
        {"op": "set_dimension_tolerance", "name": "D1@Sketch2",
         "type": "BILAT", "min": -0.05, "max": 0.10, "units": "mm"},
        {"op": "rename_feature", "name": "Sketch1", "new_name": "Base"},
        {"op": "delete_feature", "name": "Hole1"}
      ]
    }

Refuses to operate on paths under models\\originals\\. Always makes a .bak
beside the target before editing; restores from .bak if the post-edit rebuild
check reports an error. Deletes .bak on clean success.
"""
import argparse
import json
import os
import shutil
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _sw
import rebuild_check

LENGTH_TO_M = {
    "m":  1.0,
    "mm": 1e-3,
    "cm": 1e-2,
    "in": 0.0254,
    "ft": 0.3048,
}

CUSTOM_PROP_TYPE_TEXT = 30
CUSTOM_PROP_TYPE_NUMBER = 5
CUSTOM_PROP_TYPE_YESNO = 11
CUSTOM_PROP_TYPE_DATE = 64

# IDimension tolerance type codes (swTolerance_e)
TOL_TYPE_CODES = {
    "NONE": 0, "BASIC": 1, "BILAT": 2, "LIMIT": 3, "SYM": 4,
    "MIN": 5, "MAX": 6, "FIT": 7, "FITTOLONLY": 8, "FITWITHTOL": 9,
    "GENERAL": 10,
}
# Tolerance types that need a (min, max) value pair on top of the type set.
TOL_NEEDS_VALUES = {"BILAT", "LIMIT", "SYM"}

# swEndConditions_e — for drill_hole
END_CONDITIONS = {
    "blind":             0,
    "through_all":       1,
    "up_to_next":        2,
    "up_to_vertex":      3,
    "up_to_surface":     4,
    "offset_from_surface": 5,
    "up_to_body":        6,
    "mid_plane":         7,
    "through_all_both":  8,
}

# SetSuppression2 / Add3 config options
CONFIG_OPT_THIS = 1
CONFIG_OPT_ALL = 2
CONFIG_OPT_SPECIFIED = 3

# SetSuppression2 actions
SUPP_SUPPRESS = 0
SUPP_UNSUPPRESS = 1
SUPP_UNSUPPRESS_WITH_DEPS = 2


class OpFailure(Exception):
    pass


def _is_under_originals(abs_path):
    norm = os.path.normpath(abs_path).lower()
    bad = os.path.normpath(r"models\originals").lower()
    return bad in norm


def _resolve_value_in_meters(value, units):
    units = (units or "mm").lower()
    if units not in LENGTH_TO_M:
        raise OpFailure(f"unknown units {units!r} (supported: {sorted(LENGTH_TO_M)})")
    return float(value) * LENGTH_TO_M[units]


def _config_args(config_name):
    """Translate an optional config name into (configOpt, configNames) for the SW API."""
    if config_name is None:
        return CONFIG_OPT_THIS, None  # operates on active config
    if config_name == "*":
        return CONFIG_OPT_ALL, None
    return CONFIG_OPT_SPECIFIED, [config_name]


def _validate(model, op, dry_run):
    """Raise OpFailure if the op references a target that doesn't exist."""
    kind = op.get("op")
    if kind == "set_dimension":
        name = op["name"]
        dim_raw = None
        try:
            dim_raw = model.Parameter(name)
        except Exception as e:
            raise OpFailure(f"Parameter({name!r}) raised {type(e).__name__}: {e}")
        if dim_raw is None or isinstance(dim_raw, str):
            raise OpFailure(f"dimension {name!r} not found")
    elif kind in ("suppress_feature", "unsuppress_feature"):
        name = op["name"]
        feat = _sw.feature_by_name(model, name)
        if feat is None:
            raise OpFailure(f"feature {name!r} not found")
    elif kind == "delete_feature":
        # Existence check deferred to apply time — earlier ops in the same
        # batch can change which names exist (e.g. deleting a parent that
        # also kills children).
        name = op.get("name")
        if not isinstance(name, str) or not name.strip():
            raise OpFailure("delete_feature requires non-empty 'name'")
    elif kind == "rename_feature":
        # Only validate op shape here; existence/collision are checked at apply
        # time because earlier ops in the same batch can change which names
        # exist (e.g. Base -> Sketch1 -> Base round-trips).
        name = op.get("name")
        new_name = op.get("new_name")
        if not isinstance(name, str) or not name.strip():
            raise OpFailure("rename_feature requires non-empty 'name'")
        if not isinstance(new_name, str) or not new_name.strip():
            raise OpFailure("rename_feature requires non-empty 'new_name'")
        if name == new_name:
            raise OpFailure(f"rename_feature: new_name {new_name!r} matches current name")
    elif kind == "set_active_configuration":
        name = op["name"]
        names = list(_sw.prop(model, "GetConfigurationNames") or ())
        if name not in names:
            raise OpFailure(f"configuration {name!r} not found (have: {names})")
    elif kind == "drill_hole":
        pt = op.get("face_point_mm")
        if not (isinstance(pt, (list, tuple)) and len(pt) == 3):
            raise OpFailure("drill_hole requires face_point_mm = [x, y, z] in mm")
        if "diameter_mm" not in op:
            raise OpFailure("drill_hole requires diameter_mm")
        end = str(op.get("end_condition", "through_all")).lower()
        if end not in END_CONDITIONS:
            raise OpFailure(f"unknown end_condition {end!r} (supported: {sorted(END_CONDITIONS)})")
        if end == "blind" and not op.get("depth_mm"):
            raise OpFailure("blind end condition requires depth_mm")
    elif kind == "set_dimension_tolerance":
        name = op["name"]
        try:
            dim_raw = model.Parameter(name)
        except Exception as e:
            raise OpFailure(f"Parameter({name!r}) raised {type(e).__name__}: {e}")
        if dim_raw is None or isinstance(dim_raw, str):
            raise OpFailure(f"dimension {name!r} not found")
        tol_type = str(op.get("type", "")).upper()
        if tol_type not in TOL_TYPE_CODES:
            raise OpFailure(f"unknown tolerance type {tol_type!r} (supported: {sorted(TOL_TYPE_CODES)})")
        if tol_type in TOL_NEEDS_VALUES:
            if "min" not in op or "max" not in op:
                raise OpFailure(f"tolerance type {tol_type} requires 'min' and 'max'")
    elif kind in ("set_custom_property", "set_material"):
        # Both are creation-allowed; only validate config if specified.
        cfg = op.get("config")
        if cfg:
            names = list(_sw.prop(model, "GetConfigurationNames") or ())
            if cfg not in names:
                raise OpFailure(f"configuration {cfg!r} not found (have: {names})")
    else:
        raise OpFailure(f"unknown op {kind!r}")


def _apply_set_dimension(model, op):
    name = op["name"]
    value_m = _resolve_value_in_meters(op["value"], op.get("units", "mm"))
    cfg_opt, cfg_names = _config_args(op.get("config"))
    dim_raw = model.Parameter(name)
    dim = _sw.cast(dim_raw, "IDimension")
    rc = dim.SetSystemValue3(value_m, cfg_opt, cfg_names) if cfg_names else \
         dim.SetSystemValue3(value_m, cfg_opt, None)
    return {"sw_return": int(rc) if isinstance(rc, (int, bool)) else str(rc),
            "value_m": value_m, "config_opt": cfg_opt}


def _apply_suppression(model, op, action):
    name = op["name"]
    cfg_opt, cfg_names = _config_args(op.get("config"))
    feat = _sw.feature_by_name(model, name)
    rc = feat.SetSuppression2(action, cfg_opt, cfg_names)
    return {"sw_return": bool(rc), "action": action, "config_opt": cfg_opt}


def _apply_set_custom_property(model, op):
    name = op["name"]
    value = "" if op.get("value") is None else str(op["value"])
    config = op.get("config", "")
    type_code = int(op.get("type_code", CUSTOM_PROP_TYPE_TEXT))
    cpm = model.Extension.CustomPropertyManager(config)
    existing = cpm.GetNames() or ()
    if name in existing:
        rc = cpm.Set2(name, value)
        method = "Set2"
    else:
        # Add3(name, type, value, overwrite). overwrite=2 means add or replace.
        rc = cpm.Add3(name, type_code, value, 2)
        method = "Add3"
    return {"sw_return": int(rc) if isinstance(rc, (int, bool)) else str(rc),
            "method": method, "config": config}


def _apply_set_material(model, op):
    name = op["name"]
    db = op.get("database", "")
    config = op.get("config", "")
    rc = model.SetMaterialPropertyName2(config, db, name)
    return {"sw_return": int(rc) if isinstance(rc, (int, bool)) else str(rc),
            "database": db, "config": config}


def _apply_set_active_configuration(model, op):
    name = op["name"]
    rc = model.ShowConfiguration2(name)
    return {"sw_return": bool(rc)}


def _apply_drill_hole(model, op):
    """Drill a simple hole on the face that contains the given 3D point.
    Uses IFeatureManager.SimpleHole2 — face selection's click point is the hole center.
    """
    pt_mm = op["face_point_mm"]
    x, y, z = (float(v) / 1000.0 for v in pt_mm)
    diameter_m = float(op["diameter_mm"]) / 1000.0
    end_name = str(op.get("end_condition", "through_all")).lower()
    end_code = END_CONDITIONS[end_name]
    depth_m = float(op["depth_mm"]) / 1000.0 if op.get("depth_mm") else 0.0

    model.ClearSelection2(True)
    sel = model.Extension.SelectByID2("", "FACE", x, y, z, False, 0, None, 0)
    if not sel:
        raise OpFailure(f"face selection failed at point {pt_mm} mm — point may not lie on any face")

    feat = model.FeatureManager.SimpleHole2(
        diameter_m,        # Dia
        True,              # Sd
        False,             # Flip
        False,             # Dir
        end_code,          # T1
        0,                 # T2
        depth_m, 0.0,      # D1, D2
        False, False,      # Dchk1, Dchk2
        False, False,      # Ddir1, Ddir2
        0.0, 0.0,          # Dang1, Dang2
        False, False,      # OffsetReverse1, OffsetReverse2
        False, False,      # TranslateSurface1, TranslateSurface2
        True, True,        # UseFeatScope, UseAutoSelect
        False, False, False,  # Assembly*
    )
    if feat is None:
        raise OpFailure("SimpleHole2 returned None")
    feat = _sw.cast(feat, "IFeature")
    return {
        "feature_name":  _sw.prop(feat, "Name"),
        "diameter_mm":   diameter_m * 1000,
        "face_point_mm": pt_mm,
        "end_condition": end_name,
        "depth_mm":      depth_m * 1000 if end_name == "blind" else None,
    }


def _apply_delete_feature(model, op):
    name = op["name"]
    feat = _sw.feature_by_name(model, name)
    if feat is None:
        raise OpFailure(f"feature {name!r} not found")
    model.ClearSelection2(True)
    if not feat.Select2(False, 0):
        raise OpFailure(f"could not select feature {name!r} for deletion")
    # EditDelete returns None; verify by re-querying the feature tree.
    model.EditDelete()
    still = _sw.feature_by_name(model, name)
    if still is not None:
        raise OpFailure(f"feature {name!r} still present after EditDelete")
    return {"deleted": name}


def _apply_rename_feature(model, op):
    name = op["name"]
    new_name = op["new_name"]
    feat = _sw.feature_by_name(model, name)
    if feat is None:
        raise OpFailure(f"feature {name!r} not found")
    if _sw.feature_by_name(model, new_name) is not None:
        raise OpFailure(f"a feature named {new_name!r} already exists")
    feat.Name = new_name
    after = _sw.prop(feat, "Name")
    if after != new_name:
        raise OpFailure(f"rename did not stick: feat.Name == {after!r} after assignment")
    return {"from": name, "to": after}


def _apply_set_dimension_tolerance(model, op):
    name = op["name"]
    tol_type = str(op["type"]).upper()
    code = TOL_TYPE_CODES[tol_type]
    dim_raw = model.Parameter(name)
    dim = _sw.cast(dim_raw, "IDimension")
    type_rc = dim.SetToleranceType(code)
    out = {"sw_return": bool(type_rc), "type": tol_type, "type_code": code}
    if tol_type in TOL_NEEDS_VALUES:
        units = op.get("units", "mm")
        min_m = _resolve_value_in_meters(op["min"], units)
        max_m = _resolve_value_in_meters(op["max"], units)
        try:
            val_rc = dim.SetToleranceValues(min_m, max_m)
            out["values_return"] = bool(val_rc) if isinstance(val_rc, bool) else val_rc
            out["min_m"] = min_m
            out["max_m"] = max_m
        except Exception as e:
            out["values_error"] = f"{type(e).__name__}: {e}"
    return out


_DISPATCHERS = {
    "set_dimension":            _apply_set_dimension,
    "suppress_feature":         lambda m, o: _apply_suppression(m, o, SUPP_SUPPRESS),
    "unsuppress_feature":       lambda m, o: _apply_suppression(m, o, SUPP_UNSUPPRESS),
    "set_custom_property":      _apply_set_custom_property,
    "set_material":             _apply_set_material,
    "set_active_configuration": _apply_set_active_configuration,
    "set_dimension_tolerance":  _apply_set_dimension_tolerance,
    "drill_hole":               _apply_drill_hole,
    "rename_feature":           _apply_rename_feature,
    "delete_feature":           _apply_delete_feature,
}


def _apply(model, op):
    fn = _DISPATCHERS[op["op"]]
    return fn(model, op)


def _save(model):
    """Save the document via Save3 (silent), returning a small dict describing
    the result. Save3 returns (status, errors, warnings) under typed bindings —
    the same byref unwrap pattern as OpenDoc6.
    """
    try:
        result = model.Save3(1, 0, 0)  # 1 = swSaveAsOptions_Silent
        if isinstance(result, tuple):
            ok, errs, warns = result[0], result[1], result[2]
        else:
            ok, errs, warns = result, 0, 0
        return {
            "saved":    bool(ok),
            "errors":   int(errs)  if errs  is not None else None,
            "warnings": int(warns) if warns is not None else None,
        }
    except Exception as e:
        return {"saved": False, "error": f"{type(e).__name__}: {e}"}


def run(edit_path, dry_run=False, keep_open=False):
    edit_path = os.path.abspath(edit_path)
    if not os.path.isfile(edit_path):
        print(f"FAIL: edit instruction not found: {edit_path}")
        return 2
    with open(edit_path, "r", encoding="utf-8") as f:
        edit = json.load(f)

    target = os.path.abspath(edit["target_file"])
    if not os.path.isfile(target):
        print(f"FAIL: target_file not found: {target}")
        return 2
    if _is_under_originals(target):
        print(f"FAIL: refusing to edit a file under models\\originals: {target}")
        return 2
    operations = edit.get("operations") or []
    if not operations:
        print("FAIL: no operations in edit instruction")
        return 2

    sw = _sw.connect()
    print(f"Connected. SolidWorks {_sw.prop(sw, 'RevisionNumber')}")
    model, errors, warnings = _sw.open_doc(sw, target)
    if model is None:
        print(f"FAIL: OpenDoc6 returned None (errors={errors}, warnings={warnings})")
        return 4
    print(f"Opened: {_sw.prop(model, 'GetTitle')}  ({len(operations)} op(s){'  [DRY RUN]' if dry_run else ''})")

    # ---- 1. validate everything before touching anything ----
    print("\nValidating operations...")
    bad = []
    for i, op in enumerate(operations):
        try:
            _validate(model, op, dry_run)
            print(f"  [{i:02d}] {op['op']:<28} ok")
        except OpFailure as e:
            print(f"  [{i:02d}] {op['op']:<28} FAIL: {e}")
            bad.append((i, str(e)))
    if bad:
        print(f"\nValidation failed on {len(bad)} op(s); aborting.")
        if not keep_open:
            _sw.close(sw, model)
        return 6

    if dry_run:
        print("\nDry run: validation passed, no changes written.")
        if not keep_open:
            _sw.close(sw, model)
        return 0

    # ---- 2. backup ----
    bak_path = target + ".bak"
    # Close the SW-held doc temporarily? No — Windows allows reading an open file
    # for shutil.copy2 since SW opens with shared read. But to be safe, copy the
    # source file (on disk it's already last-saved state).
    shutil.copy2(target, bak_path)
    print(f"\nBackup: {bak_path}")

    # ---- 3. apply ----
    print("\nApplying operations...")
    op_results = []
    apply_failed = False
    for i, op in enumerate(operations):
        try:
            res = _apply(model, op)
            op_results.append({"index": i, "op": op["op"], "name": op.get("name"),
                               "result": res, "ok": True})
            print(f"  [{i:02d}] {op['op']:<28} -> {res}")
        except Exception as e:
            traceback.print_exc()
            op_results.append({"index": i, "op": op["op"], "name": op.get("name"),
                               "error": f"{type(e).__name__}: {e}", "ok": False})
            print(f"  [{i:02d}] {op['op']:<28} EXCEPTION: {type(e).__name__}: {e}")
            apply_failed = True
            break

    # ---- 4. save ----
    print("\nSaving...")
    save_result = _save(model)
    print(f"  {save_result}")

    # ---- 5. rebuild check ----
    print("\nRebuild check...")
    try:
        report, rc_exit = rebuild_check.check_open_model(sw, model, target)
    except Exception:
        traceback.print_exc()
        report, rc_exit = None, 5

    if report is not None:
        rebuild_check.write_report(report, target)
        rb = report["rebuild"]
        fb = report["features"]
        print(f"  status: {report['status']}  "
              f"({fb['errors']} err, {fb['warnings']} warn, "
              f"stamp {rb['update_stamp_before']}->{rb['update_stamp_after']}, "
              f"drift={'yes' if report['mass_diff'].get('drifted') else 'no'})")

    # ---- 6. roll back on hard failure ----
    rollback = False
    if apply_failed or (report is not None and report["status"] == "error"):
        rollback = True
        print("\nRolling back from .bak (rebuild error or apply exception).")
        if not keep_open:
            _sw.close(sw, model)
        shutil.copy2(bak_path, target)
        # Reopen so the user sees the restored model.
        model, _, _ = _sw.open_doc(sw, target)
        if not keep_open and model is not None:
            _sw.close(sw, model)

    if not rollback:
        try:
            os.remove(bak_path)
            print(f"Removed {bak_path}")
        except OSError:
            pass
        if not keep_open:
            _sw.close(sw, model)

    # ---- 7. exit code ----
    if apply_failed:
        return 7
    if report is None:
        return 5
    return 0 if report["status"] in ("ok", "warning") else 1


def main():
    p = argparse.ArgumentParser()
    p.add_argument("edit_path")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--keep-open", action="store_true")
    args = p.parse_args()
    sys.exit(run(args.edit_path, dry_run=args.dry_run, keep_open=args.keep_open))


if __name__ == "__main__":
    main()
