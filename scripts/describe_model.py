"""Capture a JSON snapshot of a SolidWorks part or assembly.

Usage:
    py describe_model.py <path-to-file> [--keep-open]

Output: outputs/snapshots/<filename>.json (relative to project root).
"""
import argparse
import datetime
import json
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _sw

OUTPUT_DIR = r"D:\ClaudeProjects\TS2\outputs\snapshots"

DOC_TYPE_NAMES = {1: "part", 2: "assembly", 3: "drawing"}

LENGTH_UNIT_NAMES = {
    0: "mm", 1: "cm", 2: "m", 3: "in", 4: "ft", 5: "ft&in",
    6: "angstrom", 7: "nm", 8: "micron", 9: "mil", 10: "microinch",
    11: "user-defined",
}

TOLERANCE_TYPE_NAMES = {
    0: "NONE", 1: "BASIC", 2: "BILAT", 3: "LIMIT", 4: "SYMMETRIC",
    5: "MIN", 6: "MAX", 7: "FIT", 8: "FITTOLONLY", 9: "FITWITHTOL",
    10: "GENERAL",
}

CUSTOM_PROP_TYPE_NAMES = {0: "unknown", 5: "number", 11: "yes/no", 30: "text", 64: "date"}

SCHEMA_VERSION = 1


def safe(fn, default=None):
    try:
        return fn()
    except Exception:
        return default


def collect_units(model):
    raw = safe(lambda: _sw.prop(model, "GetUnits"))
    if not isinstance(raw, (tuple, list)):
        return {"raw": raw, "length": None, "decimal_places": None}
    length_code = raw[0] if len(raw) > 0 else None
    return {
        "raw": list(raw),
        "length_code": length_code,
        "length": LENGTH_UNIT_NAMES.get(length_code),
        "fraction_denom": raw[1] if len(raw) > 1 else None,
        "decimal_places": raw[2] if len(raw) > 2 else None,
    }


def collect_mass_props(model):
    try:
        ext = model.Extension
        mp = ext.CreateMassProperty()
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}

    def to_list(v):
        if v is None:
            return None
        if isinstance(v, (tuple, list)):
            return list(v)
        return v

    return {
        "mass_kg":               safe(lambda: float(mp.Mass)),
        "volume_m3":             safe(lambda: float(mp.Volume)),
        "surface_area_m2":       safe(lambda: float(mp.SurfaceArea)),
        "density_kg_m3":         safe(lambda: float(mp.Density)),
        "center_of_mass_m":      to_list(safe(lambda: mp.CenterOfMass)),
        "principle_moments_kg_m2": to_list(safe(lambda: mp.PrincipleMomentsOfInertia)),
        "principle_axes": [
            to_list(safe(lambda: mp.PrincipleAxesOfInertia(0))),
            to_list(safe(lambda: mp.PrincipleAxesOfInertia(1))),
            to_list(safe(lambda: mp.PrincipleAxesOfInertia(2))),
        ],
        "moment_of_inertia_at_origin": to_list(safe(lambda: mp.GetMomentOfInertia(0))),
    }


def collect_configurations(model):
    names = list(safe(lambda: _sw.prop(model, "GetConfigurationNames"), default=()) or ())
    active_name = None
    try:
        cmgr = model.ConfigurationManager
        active = cmgr.ActiveConfiguration
        active_name = active.Name
    except Exception:
        try:
            active = model.GetActiveConfiguration()
            active_name = active.Name
        except Exception:
            pass

    details = {}
    for n in names:
        try:
            cfg = model.GetConfigurationByName(n)
            details[n] = {
                "is_derived": bool(safe(lambda c=cfg: c.IsDerived, default=False)),
                "comment":    safe(lambda c=cfg: c.Comment, default=""),
            }
        except Exception as e:
            details[n] = {"error": f"{type(e).__name__}: {e}"}

    return {
        "names": names,
        "active": active_name,
        "details": details,
    }


def _read_props(cpm):
    out = {}
    if cpm is None:
        return out
    names = safe(lambda: cpm.GetNames(), default=()) or ()
    for n in names:
        type_code = safe(lambda: cpm.GetType2(n))
        got = safe(lambda: cpm.Get6(n, False))
        if isinstance(got, tuple) and len(got) >= 5:
            _retcode, value, resolved, was_resolved, link = got[:5]
        else:
            value = resolved = None
            was_resolved = False
            link = False
        out[n] = {
            "type_code": type_code,
            "type": CUSTOM_PROP_TYPE_NAMES.get(type_code, str(type_code)),
            "value": value,
            "resolved_value": resolved,
            "was_resolved": bool(was_resolved),
            "linked": bool(link),
        }
    return out


def collect_custom_properties(model, config_names):
    ext = model.Extension
    file_cpm = safe(lambda: ext.CustomPropertyManager(""))
    by_config = {}
    for cname in config_names:
        cpm = safe(lambda c=cname: ext.CustomPropertyManager(c))
        by_config[cname] = _read_props(cpm)
    return {
        "file": _read_props(file_cpm),
        "by_config": by_config,
    }


def _feat_basic(feat):
    name = safe(lambda: feat.Name)
    type_name = safe(lambda: feat.GetTypeName2()) or safe(lambda: feat.GetTypeName())
    suppressed = safe(lambda: bool(feat.IsSuppressed()))
    fid = safe(lambda: feat.GetID())
    return name, type_name, suppressed, fid


def _read_dim(disp_dim):
    disp_dim = _sw.cast(disp_dim, "IDisplayDimension")
    sel_name = safe(lambda: disp_dim.GetNameForSelection())
    dim_raw = safe(lambda: disp_dim.GetDimension())
    if dim_raw is None:
        return None
    dim = _sw.cast(dim_raw, "IDimension")
    full_name = safe(lambda: dim.FullName)
    tol_type = safe(lambda: dim.GetToleranceType(), default=0) or 0
    tol_vals = safe(lambda: dim.GetToleranceValues())
    if isinstance(tol_vals, (tuple, list)) and len(tol_vals) >= 2:
        tol_min, tol_max = float(tol_vals[0]), float(tol_vals[1])
    else:
        tol_min = tol_max = None
    return {
        "selection_name": sel_name,
        "name": safe(lambda: dim.Name),
        "full_name": full_name,
        "value_doc_units": safe(lambda: float(dim.Value)),
        "system_value_m": safe(lambda: float(dim.SystemValue)),
        "read_only": bool(safe(lambda: dim.ReadOnly, default=False)),
        "tolerance": {
            "type_code": tol_type,
            "type": TOLERANCE_TYPE_NAMES.get(tol_type, str(tol_type)),
            "min_m": tol_min,
            "max_m": tol_max,
        },
    }


DIM_NAME_PROBE_LIMIT = 20  # try D1..D{limit} per feature


def _read_dim_from_idim(dim_raw):
    """Build a dim record from a bare IDimension (no IDisplayDimension)."""
    if dim_raw is None:
        return None
    dim = _sw.cast(dim_raw, "IDimension")
    full_name = safe(lambda: dim.FullName)
    tol_type = safe(lambda: dim.GetToleranceType(), default=0) or 0
    tol_vals = safe(lambda: dim.GetToleranceValues())
    if isinstance(tol_vals, (tuple, list)) and len(tol_vals) >= 2:
        tol_min, tol_max = float(tol_vals[0]), float(tol_vals[1])
    else:
        tol_min = tol_max = None
    short_name = safe(lambda: dim.Name)
    sel = None
    if short_name and full_name:
        sel = f"{short_name}@{full_name.split('@')[1]}" if "@" in full_name else short_name
    return {
        "selection_name": sel,
        "name": short_name,
        "full_name": full_name,
        "value_doc_units": safe(lambda: float(dim.Value)),
        "system_value_m": safe(lambda: float(dim.SystemValue)),
        "read_only": bool(safe(lambda: dim.ReadOnly, default=False)),
        "tolerance": {
            "type_code": tol_type,
            "type": TOLERANCE_TYPE_NAMES.get(tol_type, str(tol_type)),
            "min_m": tol_min,
            "max_m": tol_max,
        },
    }


def _walk_feature_dims(feat, model, feat_name):
    """Combine three paths to defeat the GetNext linked-list short-circuit:
    1. Brute-force model.Parameter('Dn@feat') for n=1..LIMIT
    2. GetFirstDisplayDimension chain (catches custom-named dims that aren't D{n})
    Returns a list, deduped by FullName.
    """
    out_by_full = {}

    # Path A: brute-force by default name
    if feat_name:
        for n in range(1, DIM_NAME_PROBE_LIMIT + 1):
            label = f"D{n}@{feat_name}"
            dim_raw = safe(lambda l=label: model.Parameter(l))
            if dim_raw is None or isinstance(dim_raw, str):
                continue
            d = _read_dim_from_idim(dim_raw)
            if d and d.get("full_name") and d["full_name"] not in out_by_full:
                out_by_full[d["full_name"]] = d

    # Path B: linked list (catches custom-named dims, only the first one tends to work)
    first = safe(lambda: feat.GetFirstDisplayDimension())
    dd = first
    seen = set()
    while dd is not None:
        dd = _sw.cast(dd, "IDisplayDimension")
        key = id(dd._oleobj_) if hasattr(dd, "_oleobj_") else id(dd)
        if key in seen:
            break
        seen.add(key)
        dim_data = _read_dim(dd)
        if dim_data and dim_data.get("full_name") and dim_data["full_name"] not in out_by_full:
            out_by_full[dim_data["full_name"]] = dim_data
        nxt = safe(lambda: dd.GetNext5())
        if nxt is None:
            nxt = safe(lambda: dd.GetNext2())
        if nxt is None:
            nxt = safe(lambda: dd.GetNext())
        dd = nxt

    return list(out_by_full.values())


def collect_features_and_dims(model):
    features = []
    dims_by_full_name = {}
    seen_feat_ids = set()

    def visit_chain(feat, parent_id, depth, sub):
        while feat is not None:
            feat = _sw.cast(feat, "IFeature")
            name, type_name, suppressed, fid = _feat_basic(feat)

            if fid is not None and fid in seen_feat_ids:
                already_seen = True
            else:
                already_seen = False
                if fid is not None:
                    seen_feat_ids.add(fid)
                features.append({
                    "id": fid,
                    "name": name,
                    "type_name": type_name,
                    "suppressed": suppressed,
                    "parent_id": parent_id,
                    "depth": depth,
                    "is_sub_feature": sub,
                })

            for d in _walk_feature_dims(feat, model, name):
                fn = d.get("full_name")
                if fn and fn in dims_by_full_name:
                    continue
                if fn:
                    dims_by_full_name[fn] = d
                else:
                    dims_by_full_name[f"<anon-{len(dims_by_full_name)}>"] = d

            if not already_seen:
                child = safe(lambda f=feat: f.GetFirstSubFeature())
                if child is not None:
                    visit_chain(child, parent_id=fid, depth=depth + 1, sub=True)

            try:
                feat = feat.GetNextSubFeature() if sub else feat.GetNextFeature()
            except Exception:
                feat = None

    first = safe(lambda: model.FirstFeature())
    if first is not None:
        visit_chain(first, parent_id=None, depth=0, sub=False)

    return features, list(dims_by_full_name.values())


def collect_components(model):
    components = []
    try:
        comps = model.GetComponents(False)
    except Exception:
        comps = None
    if comps is None:
        return components
    for c in comps:
        components.append({
            "name":         safe(lambda x=c: x.Name2, default=safe(lambda x=c: x.Name)),
            "path":         safe(lambda x=c: x.GetPathName()),
            "suppressed":   safe(lambda x=c: bool(x.IsSuppressed()), default=None),
            "is_fixed":     safe(lambda x=c: bool(x.IsFixed()), default=None),
            "config_name":  safe(lambda x=c: x.ReferencedConfiguration),
        })
    return components


def collect(model, doc_type_code):
    config_block = collect_configurations(model)
    features, dimensions = collect_features_and_dims(model)
    snapshot = {
        "schema_version": SCHEMA_VERSION,
        "captured_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "source": {
            "path":      safe(lambda: _sw.prop(model, "GetPathName")),
            "title":     safe(lambda: _sw.prop(model, "GetTitle")),
            "type_code": doc_type_code,
            "type":      DOC_TYPE_NAMES.get(doc_type_code, "unknown"),
        },
        "units":             collect_units(model),
        "configurations":    config_block,
        "custom_properties": collect_custom_properties(model, config_block["names"]),
        "features":          features,
        "dimensions":        dimensions,
    }
    if doc_type_code == 1:  # part
        snapshot["mass_properties"] = collect_mass_props(model)
    elif doc_type_code == 2:  # assembly
        snapshot["mass_properties"] = collect_mass_props(model)
        snapshot["components"] = collect_components(model)
        snapshot["mates"] = []  # TODO: walk mate group when we have a real assembly
    return snapshot


def main():
    p = argparse.ArgumentParser()
    p.add_argument("path")
    p.add_argument("--keep-open", action="store_true")
    args = p.parse_args()

    abs_path = os.path.abspath(args.path)
    if not os.path.isfile(abs_path):
        print(f"FAIL: not a file: {abs_path}")
        sys.exit(2)

    try:
        doctype = _sw.doctype_for(abs_path)
    except ValueError as e:
        print(f"FAIL: {e}")
        sys.exit(2)

    if doctype == _sw.SW_DOC_DRAWING:
        print("Drawings not supported yet.")
        sys.exit(3)

    sw = _sw.connect()
    print(f"Connected. SolidWorks {_sw.prop(sw, 'RevisionNumber')}")

    model, errors, warnings = _sw.open_doc(sw, abs_path)
    if model is None:
        print(f"FAIL: OpenDoc6 returned None (errors={errors}, warnings={warnings})")
        sys.exit(4)

    title = _sw.prop(model, "GetTitle")
    print(f"Opened: {title} (errors={errors}, warnings={warnings})")

    try:
        snapshot = collect(model, doctype)
    except Exception:
        traceback.print_exc()
        if not args.keep_open:
            _sw.close(sw, model)
        sys.exit(5)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    base = os.path.splitext(os.path.basename(abs_path))[0]
    out_path = os.path.join(OUTPUT_DIR, base + ".json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, indent=2, ensure_ascii=False, default=str)

    feat_count = len(snapshot["features"])
    dim_count = len(snapshot["dimensions"])
    cfg_count = len(snapshot["configurations"]["names"])
    type_label = snapshot["source"]["type"].capitalize()
    print(f"\n{type_label}: {os.path.basename(abs_path)}, "
          f"{feat_count} features, {dim_count} dimensions, "
          f"{cfg_count} configurations")
    print(f"Wrote {out_path}")

    if not args.keep_open:
        _sw.close(sw, model)


if __name__ == "__main__":
    main()
