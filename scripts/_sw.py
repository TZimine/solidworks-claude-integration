import os
import win32com.client
import pythoncom

SW_DOC_PART = 1
SW_DOC_ASSEMBLY = 2
SW_DOC_DRAWING = 3

SW_OPEN_DOC_OPTIONS_SILENT = 1


SLDWORKS_TLB_GUID = "{83A33D31-27C5-11CE-BFD4-00400513BB57}"
SLDWORKS_TLB_MAJOR = 33
SLDWORKS_TLB_MINOR = 0


_mod = None


def _ensure_mod():
    global _mod
    if _mod is None:
        _mod = win32com.client.gencache.EnsureModule(
            SLDWORKS_TLB_GUID, 0, SLDWORKS_TLB_MAJOR, SLDWORKS_TLB_MINOR
        )
    return _mod


def cast(disp, iface_name):
    if disp is None:
        return None
    mod = _ensure_mod()
    iface_cls = getattr(mod, iface_name)
    raw = disp._oleobj_ if hasattr(disp, "_oleobj_") else disp
    return iface_cls(raw)


def connect():
    pythoncom.CoInitialize()
    _ensure_mod()
    disp = win32com.client.Dispatch("SldWorks.Application")
    sw = cast(disp, "ISldWorks")
    sw.Visible = True
    return sw


def prop(obj, name):
    val = getattr(obj, name)
    if isinstance(val, (str, int, float, bool, tuple, list, type(None))):
        return val
    if callable(val):
        try:
            return val()
        except Exception:
            pass
    return val


_DOCTYPE_BY_EXT = {
    ".sldprt": SW_DOC_PART,
    ".sldasm": SW_DOC_ASSEMBLY,
    ".slddrw": SW_DOC_DRAWING,
}


def doctype_for(path):
    ext = os.path.splitext(path)[1].lower()
    if ext not in _DOCTYPE_BY_EXT:
        raise ValueError(f"Unrecognised SolidWorks extension: {ext!r}")
    return _DOCTYPE_BY_EXT[ext]


def open_doc(sw, path, doctype=None):
    abs_path = os.path.abspath(path)
    if not os.path.isfile(abs_path):
        raise FileNotFoundError(abs_path)
    if doctype is None:
        doctype = doctype_for(abs_path)

    sw.CloseAllDocuments(True)

    result = sw.OpenDoc6(abs_path, doctype, SW_OPEN_DOC_OPTIONS_SILENT, "", 0, 0)
    if isinstance(result, tuple):
        model, errors, warnings = result[0], result[1], result[2]
    else:
        model, errors, warnings = result, 0, 0
    return model, errors, warnings


def open_part(sw, path):
    return open_doc(sw, path, SW_DOC_PART)


def close(sw, model):
    if model is None:
        return
    title = model.GetTitle if isinstance(model.GetTitle, str) else model.GetTitle()
    sw.CloseDoc(title)


def feature_by_name(model, target_name):
    """Walk top-level + sub-features looking for a feature whose .Name matches.
    Returns an IFeature-cast handle, or None. Replacement for IModelDoc2.FeatureByName,
    which isn't exposed by SW 2025's typed bindings.
    """
    seen = set()

    def walk(feat, sub):
        while feat is not None:
            feat = cast(feat, "IFeature")
            fid = None
            try:
                fid = feat.GetID()
            except Exception:
                pass
            if fid is not None and fid in seen:
                return None
            if fid is not None:
                seen.add(fid)
            try:
                if feat.Name == target_name:
                    return feat
            except Exception:
                pass
            try:
                child = feat.GetFirstSubFeature()
            except Exception:
                child = None
            if child is not None:
                hit = walk(child, True)
                if hit is not None:
                    return hit
            try:
                feat = feat.GetNextSubFeature() if sub else feat.GetNextFeature()
            except Exception:
                feat = None
        return None

    try:
        first = model.FirstFeature()
    except Exception:
        return None
    return walk(first, sub=False)
