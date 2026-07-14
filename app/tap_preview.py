import base64
import os
import re
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont


COORD_RE = re.compile(r"([XYZ])\s*(-?\d+(?:\.\d+)?)", re.IGNORECASE)
FEED_RE = re.compile(r"F\s*(-?\d+(?:\.\d+)?)", re.IGNORECASE)
MOTION_RE = re.compile(r"\bG0?([0123])(?=[^0-9.]|$)", re.IGNORECASE)


def parse_tap_segments(path, max_segments=20000):
    current = {"X": 0.0, "Y": 0.0, "Z": 0.0}
    motion = None
    cutting = False
    segments = []

    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for raw in f:
            line = raw.split(";", 1)[0].strip()
            if not line:
                continue

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
                    segments.append((start, end))
                    if len(segments) >= max_segments:
                        break

    return segments

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


def render_tap_preview(path, out_path=None, size=900, padding=40):
    segments = parse_tap_segments(path)
    image = Image.new("RGB", (size, size), "#f7f8fb")
    draw = ImageDraw.Draw(image)

    title = os.path.basename(path)
    if not segments:
        draw.text((padding, padding), f"Khong doc duoc duong cat\n{title}", fill="#222")
        if out_path:
            image.save(out_path, "JPEG", quality=86)
        return image

    min_x, min_y, max_x, max_y = _bounds(segments)
    width = max(max_x - min_x, 1.0)
    height = max(max_y - min_y, 1.0)
    scale = min((size - padding * 2) / width, (size - padding * 2) / height)
    offset_x = (size - width * scale) / 2
    offset_y = (size - height * scale) / 2

    def pt(x, y):
        px = offset_x + (x - min_x) * scale
        py = size - (offset_y + (y - min_y) * scale)
        return px, py

    # Light grid helps operator see shape and aspect ratio.
    for i in range(0, size, 100):
        draw.line([(i, 0), (i, size)], fill="#e7e9ef")
        draw.line([(0, i), (size, i)], fill="#e7e9ef")

    for start, end in segments:
        draw.line([pt(*start), pt(*end)], fill="#111827", width=2)

    info = f"{title}  |  {width:.0f} x {height:.0f}  |  {len(segments)} doan"
    draw.rectangle([(0, 0), (size, 34)], fill="#ffffff")
    draw.text((12, 10), info, fill="#111827")

    if out_path:
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        image.save(out_path, "JPEG", quality=86)
    return image


def render_tap_preview_bytes(path, size=900):
    image = render_tap_preview(path, size=size)
    output = BytesIO()
    image.thumbnail((300, 300))
    image.save(output, "JPEG", quality=72)
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
    candidates.append(normalized)
    return candidates


def find_existing_tap(path):
    for candidate in cnc_unc_candidates(path):
        if os.path.exists(candidate):
            return candidate
    return None
