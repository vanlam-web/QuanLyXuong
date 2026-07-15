import base64
import math
import os
import re
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont


COORD_RE = re.compile(r"([XYZ])\s*(-?\d+(?:\.\d+)?)", re.IGNORECASE)
FEED_RE = re.compile(r"F\s*(-?\d+(?:\.\d+)?)", re.IGNORECASE)
MOTION_RE = re.compile(r"\bG0?([0123])(?=[^0-9.]|$)", re.IGNORECASE)
TAP_PREVIEW_MAX_SEGMENTS = 120000
TAP_PROGRESS_MAX_SEGMENTS = 120000


def parse_tap_segments_with_lines(path, max_segments=TAP_PREVIEW_MAX_SEGMENTS):
    current = {"X": 0.0, "Y": 0.0, "Z": 0.0}
    motion = None
    cutting = False
    segments = []
    code_line_no = 0

    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for raw in f:
            line = raw.split(";", 1)[0].strip()
            if not line:
                continue
            code_line_no += 1

            motion_match = MOTION_RE.search(line)
            if motion_match:
                motion = int(motion_match.group(1))

            coords = {axis.upper(): float(value) for axis, value in COORD_RE.findall(line)}
            if not coords:
                continue

            previous = current.copy()
            current.update(coords)

            if "Z" in coords:
                cutting = current["Z"] <= 0.01

            if "X" not in coords and "Y" not in coords:
                continue

            if motion in (1, 2, 3) and cutting:
                start = (previous["X"], previous["Y"])
                end = (current["X"], current["Y"])
                if start != end:
                    segments.append({"start": start, "end": end, "line_no": code_line_no})
                    if len(segments) >= max_segments:
                        break

    return segments


def parse_tap_segments(path, max_segments=TAP_PREVIEW_MAX_SEGMENTS):
    return [
        (item["start"], item["end"])
        for item in parse_tap_segments_with_lines(path, max_segments=max_segments)
    ]

def tap_segment_length(segment):
    (x1, y1), (x2, y2) = segment["start"], segment["end"]
    return math.hypot(x2 - x1, y2 - y1)

def estimate_tap_path_progress(path, current_line, max_segments=TAP_PROGRESS_MAX_SEGMENTS):
    try:
        current_line_no = int(float(current_line))
    except Exception:
        return {}
    if current_line_no <= 0:
        return {}

    segments = parse_tap_segments_with_lines(path, max_segments=max_segments)
    if not segments:
        return {}

    total_length = sum(tap_segment_length(segment) for segment in segments)
    if total_length <= 0:
        return {}

    current_length = sum(
        tap_segment_length(segment)
        for segment in segments
        if int(segment.get("line_no") or 0) <= current_line_no
    )
    percent = min(100.0, max(0.0, current_length * 100.0 / total_length))
    return {
        "current_path_length": current_length,
        "total_path_length": total_length,
        "progress_percent": percent,
        "progress_source": "cnc_tap_path",
    }

def analyze_tap_file(path):
    x_values = []
    y_values = []
    z_values = []
    feeds = []
    line_count = 0

    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for raw in f:
            line = raw.split(";", 1)[0].strip()
            if not line:
                continue
            line_count += 1
            for axis, value in COORD_RE.findall(line):
                number = float(value)
                axis = axis.upper()
                if axis == "X":
                    x_values.append(number)
                elif axis == "Y":
                    y_values.append(number)
                elif axis == "Z":
                    z_values.append(number)
            for value in FEED_RE.findall(line):
                feeds.append(float(value))

    def min_or_none(values):
        return min(values) if values else None

    def max_or_none(values):
        return max(values) if values else None

    x_min = min_or_none(x_values)
    x_max = max_or_none(x_values)
    y_min = min_or_none(y_values)
    y_max = max_or_none(y_values)
    width_mm = (x_max - x_min) if x_min is not None and x_max is not None else None
    height_mm = (y_max - y_min) if y_min is not None and y_max is not None else None
    area_m2 = (width_mm * height_mm / 1_000_000.0) if width_mm is not None and height_mm is not None else None

    return {
        "source_kind": "tap",
        "line_count": line_count,
        "x_min": x_min,
        "x_max": x_max,
        "y_min": y_min,
        "y_max": y_max,
        "z_min": min_or_none(z_values),
        "z_max": max_or_none(z_values),
        "width_mm": width_mm,
        "height_mm": height_mm,
        "area_m2": area_m2,
        "feed_min": min_or_none(feeds),
        "feed_max": max_or_none(feeds),
    }


def _bounds(segments):
    xs = []
    ys = []
    for (x1, y1), (x2, y2) in segments:
        xs.extend([x1, x2])
        ys.extend([y1, y2])
    return min(xs), min(ys), max(xs), max(ys)


def render_tap_preview(path, out_path=None, size=900, padding=32, current_line=None):
    max_segments = TAP_PROGRESS_MAX_SEGMENTS if current_line is not None else TAP_PREVIEW_MAX_SEGMENTS
    segment_items = parse_tap_segments_with_lines(path, max_segments=max_segments)
    segments = [(item["start"], item["end"]) for item in segment_items]
    title = os.path.basename(path)
    if not segments:
        image = Image.new("RGB", (min(size, 420), 180), "#f7f8fb")
        draw = ImageDraw.Draw(image)
        draw.text((padding, padding), f"Khong doc duoc duong cat\n{title}", fill="#222")
        if out_path:
            image.save(out_path, "JPEG", quality=86)
        return image

    min_x, min_y, max_x, max_y = _bounds(segments)
    width = max(max_x - min_x, 1.0)
    height = max(max_y - min_y, 1.0)
    header_height = 34
    max_draw_width = max(1, size - padding * 2)
    max_draw_height = max(1, size - padding * 2 - header_height)
    scale = min(max_draw_width / width, max_draw_height / height)
    draw_width = width * scale
    draw_height = height * scale
    canvas_width = max(180, min(size, int(draw_width + padding * 2 + 0.5)))
    canvas_height = max(140, min(size, int(draw_height + padding * 2 + header_height + 0.5)))
    offset_x = (canvas_width - draw_width) / 2
    offset_y = header_height + (canvas_height - header_height - draw_height) / 2

    image = Image.new("RGB", (canvas_width, canvas_height), "#f7f8fb")
    draw = ImageDraw.Draw(image)

    def pt(x, y):
        px = offset_x + (x - min_x) * scale
        py = offset_y + (max_y - y) * scale
        return px, py

    # Light grid helps operator see shape and aspect ratio.
    for i in range(0, canvas_width, 100):
        draw.line([(i, header_height), (i, canvas_height)], fill="#e7e9ef")
    for i in range(header_height, canvas_height, 100):
        draw.line([(0, i), (canvas_width, i)], fill="#e7e9ef")

    current_line_no = None
    try:
        current_line_no = int(float(current_line)) if current_line is not None else None
    except Exception:
        current_line_no = None

    if current_line_no is None:
        for start, end in segments:
            draw.line([pt(*start), pt(*end)], fill="#1f2937", width=2)
    else:
        for item in segment_items:
            draw.line([pt(*item["start"]), pt(*item["end"])], fill="#1f2937", width=2)
        for item in segment_items:
            if int(item["line_no"]) <= current_line_no:
                draw.line([pt(*item["start"]), pt(*item["end"])], fill="#22c55e", width=3)

    info = f"{title}  |  {width:.0f} x {height:.0f}  |  {len(segments)} doan"
    if current_line_no is not None:
        info += f"  |  da cat den L{current_line_no}"
    draw.rectangle([(0, 0), (canvas_width, header_height)], fill="#ffffff")
    draw.text((12, 10), info, fill="#111827")

    if out_path:
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        image.save(out_path, "JPEG", quality=86)
    return image


def render_tap_preview_bytes(path, size=620):
    image = render_tap_preview(path, size=size)
    output = BytesIO()
    image.thumbnail((300, 300))
    image.save(output, "JPEG", quality=72)
    return output.getvalue()


def render_tap_progress_preview_bytes(path, current_line, size=620):
    image = render_tap_preview(path, size=size, current_line=current_line)
    output = BytesIO()
    image.thumbnail((300, 300))
    image.save(output, "JPEG", quality=78)
    return output.getvalue()


def render_tap_preview_b64(path, size=900):
    return base64.b64encode(render_tap_preview_bytes(path, size=size)).decode("ascii")


def cnc_unc_candidates(path):
    normalized = path.replace("/", "\\")
    candidates = []
    lower = normalized.lower()
    if lower.startswith("d:\\cnc\\"):
        rel = normalized[7:]
        candidates.append(r"\\CNC\CNC\CNC" + "\\" + rel)
        parts = rel.split("\\", 1)
        if len(parts) == 2:
            candidates.append(r"\\CNC\CNC\CNC" + "\\" + parts[0] + r"\New Folder" + "\\" + parts[1])
            candidates.append(r"\\CNC\CNC\CNC\Luu" + "\\" + parts[1])
    elif lower.startswith("\\\\cnc\\cnc\\cnc\\"):
        rel = normalized[len("\\\\CNC\\CNC\\CNC\\"):]
        candidates.append(normalized)
        parts = rel.split("\\", 1)
        if len(parts) == 2:
            day_folder, rest = parts
            if day_folder and rest and "new folder" not in lower and "\\luu\\" not in lower:
                candidates.append(r"\\CNC\CNC\CNC" + "\\" + day_folder + r"\New Folder" + "\\" + rest)
                candidates.append(r"\\CNC\CNC\CNC\Luu" + "\\" + rest)
        return candidates
    candidates.append(normalized)
    return candidates


def find_existing_tap(path):
    for candidate in cnc_unc_candidates(path):
        if os.path.exists(candidate):
            return candidate
    return None
