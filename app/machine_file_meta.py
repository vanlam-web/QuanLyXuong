import os
import re

try:
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    from tap_preview import analyze_tap_file
except Exception:
    analyze_tap_file = None


MACHINE_SHARE_ROOTS = {
    "InDecal": [r"\\InDecal\D"],
    "indecal": [r"\\InDecal\D"],
    "InBat": [r"\\InBat\D"],
    "inbat": [r"\\InBat\D"],
    "CNC": [r"\\CNC\CNC\CNC"],
    "cnc": [r"\\CNC\CNC\CNC"],
}


def _norm(path):
    return str(path or "").replace("/", "\\").strip()


def _join_win(*parts):
    raw = [str(part) for part in parts if str(part or "").strip("\\/")]
    if not raw:
        return ""
    first = raw[0].rstrip("\\/")
    rest = [part.strip("\\/") for part in raw[1:]]
    if first.startswith("\\\\"):
        return first + ("\\" + "\\".join(rest) if rest else "")
    return "\\".join([first.strip("\\/")] + rest)


def _date_from_values(*values):
    for value in values:
        match = re.search(r"(20\d{2}-\d{2}-\d{2})", str(value or ""))
        if match:
            return match.group(1)
    return ""


def _dedupe(paths):
    seen = set()
    out = []
    for path in paths:
        key = _norm(path).lower()
        if path and key not in seen:
            seen.add(key)
            out.append(_norm(path))
    return out


def machine_file_candidates(machine, file_path, file_name="", event_time=""):
    machine_key = str(machine or "").strip()
    original = _norm(file_path)
    display = _norm(file_name) or os.path.basename(original)
    date_part = _date_from_values(original, event_time)
    candidates = []

    if original:
        candidates.append(original)

    lowered = original.lower()
    roots = MACHINE_SHARE_ROOTS.get(machine_key, [])
    for root in roots:
        root = _norm(root)
        if lowered.startswith("d:\\cnc\\") and machine_key.lower() == "cnc":
            rel = original[7:]
            candidates.append(_join_win(root, rel))
        elif lowered.startswith("d:\\"):
            rel = original[3:]
            candidates.append(_join_win(root, rel))
        elif date_part and display:
            candidates.append(_join_win(root, date_part, "New Folder", display))
            candidates.append(_join_win(root, date_part, display))

    expanded = []
    for candidate in candidates:
        expanded.append(candidate)
        folder = os.path.dirname(candidate)
        base = os.path.basename(candidate)
        if folder and base and os.path.basename(folder).lower() != "new folder":
            expanded.append(os.path.join(folder, "New Folder", base))

    return _dedupe(expanded)


def resolve_machine_file_path(machine, file_path, file_name="", event_time="", exists_func=os.path.exists):
    for candidate in machine_file_candidates(machine, file_path, file_name, event_time):
        try:
            if exists_func(candidate):
                return candidate
        except Exception:
            continue
    return ""


def find_thumbnail_source(file_path):
    lowered = str(file_path or "").lower()
    if lowered.endswith((".tif", ".tiff", ".jpg", ".jpeg")) and os.path.exists(file_path):
        return file_path
    if not lowered.endswith((".prn", ".prt")):
        return None

    direct_bmp = file_path + ".bmp"
    if os.path.exists(direct_bmp):
        return direct_bmp

    base = os.path.splitext(file_path)[0]
    if base.lower().endswith("~ghost"):
        base = base[:-6]
    if "~" in base:
        prefix, suffix = base.split("~", 1)
        if os.path.basename(prefix).isdigit() and suffix:
            base = os.path.join(os.path.dirname(prefix), suffix)
        else:
            base = prefix

    stem = os.path.basename(base)
    folders = [os.path.dirname(base)]
    parent = os.path.dirname(folders[0])
    if parent and parent not in folders:
        folders.append(parent)

    exts = (".tif", ".tiff", ".jpg", ".jpeg")
    for folder in folders:
        for ext in exts:
            candidate = os.path.join(folder, stem + ext)
            if os.path.exists(candidate):
                return candidate
        try:
            for filename in os.listdir(folder):
                name, ext = os.path.splitext(filename)
                if name.lower() == stem.lower() and ext.lower() in exts:
                    candidate = os.path.join(folder, filename)
                    if os.path.exists(candidate):
                        return candidate
        except Exception:
            continue
    return None


def find_original_image_source(file_path):
    lowered = str(file_path or "").lower()
    if lowered.endswith((".tif", ".tiff", ".jpg", ".jpeg")) and os.path.exists(file_path):
        return file_path
    if not lowered.endswith((".prn", ".prt")):
        return None

    base = os.path.splitext(file_path)[0]
    if base.lower().endswith("~ghost"):
        base = base[:-6]
    if "~" in base:
        prefix, suffix = base.split("~", 1)
        if os.path.basename(prefix).isdigit() and suffix:
            base = os.path.join(os.path.dirname(prefix), suffix)
        else:
            base = prefix

    stem = os.path.basename(base)
    folders = [os.path.dirname(base)]
    parent = os.path.dirname(folders[0])
    if parent and parent not in folders:
        folders.append(parent)

    exts = (".tif", ".tiff", ".jpg", ".jpeg")
    for folder in folders:
        for ext in exts:
            candidate = os.path.join(folder, stem + ext)
            if os.path.exists(candidate):
                return candidate
        try:
            for filename in os.listdir(folder):
                name, ext = os.path.splitext(filename)
                if name.lower() == stem.lower() and ext.lower() in exts:
                    candidate = os.path.join(folder, filename)
                    if os.path.exists(candidate):
                        return candidate
        except Exception:
            continue
    return None


def _read_image_meta(source, include_area=True, source_kind="image"):
    meta = {}
    if not (HAS_PIL and source and os.path.exists(source)):
        return meta
    with Image.open(source) as img:
        dpi = img.info.get("dpi") or (0, 0)
        dpi_x = float(dpi[0] or 0)
        dpi_y = float(dpi[1] or 0)
        width_px, height_px = img.size
        meta.update({
            "source_kind": source_kind,
            "image_width_px": width_px,
            "image_height_px": height_px,
            "dpi_x": dpi_x,
            "dpi_y": dpi_y,
            "image_mode": img.mode,
            "image_format": img.format,
        })
        if include_area and dpi_x > 0 and dpi_y > 0:
            width_cm = width_px / dpi_x * 2.54
            height_cm = height_px / dpi_y * 2.54
            meta.update({
                "width_cm": width_cm,
                "height_cm": height_cm,
                "area_m2": (width_cm * height_cm) / 10000.0,
            })
    return meta


def collect_machine_file_meta(file_path, thumbnail_source=None):
    meta = {}
    source = thumbnail_source or file_path
    lowered = str(source or "").lower()

    original_source = find_original_image_source(file_path)
    image_source = original_source or source
    image_lowered = str(image_source or "").lower()
    include_area = not image_lowered.endswith(".prn.bmp")
    source_kind = "image" if include_area else "rip_preview_bmp"

    if HAS_PIL and image_lowered.endswith((".tif", ".tiff", ".jpg", ".jpeg", ".bmp")) and os.path.exists(image_source):
        try:
            meta.update(_read_image_meta(image_source, include_area=include_area, source_kind=source_kind))
        except Exception as exc:
            meta["meta_error"] = str(exc)

    path_lowered = str(file_path or "").lower()
    if analyze_tap_file and path_lowered.endswith((".tap", ".nc", ".txt")) and os.path.exists(file_path):
        try:
            tap_meta = analyze_tap_file(file_path)
            meta.update({k: v for k, v in tap_meta.items() if v is not None})
        except Exception as exc:
            meta["meta_error"] = str(exc)

    if image_source:
        meta["metadata_source"] = image_source
    if source and source != image_source:
        meta["preview_source"] = source
    return meta


def collect_machine_file_meta_for_server(machine, file_path, file_name="", event_time=""):
    resolved = resolve_machine_file_path(machine, file_path, file_name, event_time)
    if not resolved:
        return {}
    thumb = find_thumbnail_source(resolved)
    meta = collect_machine_file_meta(resolved, thumb)
    if meta:
        meta["resolved_file_path"] = resolved
    return meta
