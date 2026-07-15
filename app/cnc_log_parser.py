import os
import re


TIME_RE = re.compile(r"(20\d{2}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})")
PATH_RE = re.compile(r"'([^']+\.(?:tap|nc|txt))'", re.IGNORECASE)
ADVANCED_RE = re.compile(r"\bto\s+L(\d+)", re.IGNORECASE)
DYN_LINE_RE = re.compile(rb"L(\d+)")


def _event_time(line):
    match = TIME_RE.search(str(line or ""))
    return match.group(1) if match else ""


def _event_path(line):
    match = PATH_RE.search(str(line or ""))
    return match.group(1) if match else ""


def _base_id(path):
    return os.path.splitext(os.path.basename(path or ""))[0]


def _progress_for_line(path, line_no, tap_line_counts):
    line_count = int((tap_line_counts or {}).get(os.path.basename(path), 0) or 0)
    if line_count <= 0:
        return {"current_line": line_no}
    return {
        "current_line": line_no,
        "line_count": line_count,
        "progress_percent": min(100.0, max(0.0, line_no * 100.0 / line_count)),
    }


def parse_cnc_dyn_progress(data, line_count=0):
    raw = data if isinstance(data, (bytes, bytearray)) else str(data or "").encode("latin1", errors="ignore")
    matches = DYN_LINE_RE.findall(raw)
    if not matches:
        return {}
    current_line = int(matches[-1])
    total_lines = int(float(line_count or 0) or 0)
    meta = {"current_line": current_line}
    if total_lines > 0:
        meta["line_count"] = total_lines
        meta["progress_percent"] = min(100.0, max(0.0, current_line * 100.0 / total_lines))
    return meta


def _is_done_text(text):
    return "正常完毕" in text or "æ­£å¸¸å®Œæ¯•" in text


def _is_pause_text(text):
    return "中断" in text or "终止" in text or "ä¸­æ–­" in text or "ç»ˆæ­¢" in text


def parse_cnc_log_events(lines, tap_line_counts=None, state=None):
    events = []
    state = state if isinstance(state, dict) else {}
    current_cut_path = state.get("current_cut_path") or ""
    for line in lines:
        text = str(line or "")
        path = _event_path(text)
        event_time = _event_time(text)
        if "Initiate a machining task" in text and path:
            current_cut_path = path
            state["current_cut_path"] = current_cut_path
            meta = {}
            advanced = ADVANCED_RE.search(text)
            if advanced:
                meta = _progress_for_line(path, int(advanced.group(1)), tap_line_counts or {})
            events.append({
                "event_time": event_time,
                "event_type": "CUTTING",
                "path": path,
                "forced_base_id": _base_id(path),
                "machine_meta": meta,
            })
        elif _is_done_text(text) and path and current_cut_path.lower() == path.lower():
            events.append({
                "event_time": event_time,
                "event_type": "DONE",
                "path": path,
                "forced_base_id": _base_id(path),
                "machine_meta": {},
            })
            current_cut_path = ""
            state["current_cut_path"] = ""
        elif _is_pause_text(text) and current_cut_path:
            events.append({
                "event_time": event_time,
                "event_type": "PAUSE",
                "path": current_cut_path,
                "forced_base_id": _base_id(current_cut_path),
                "machine_meta": {},
            })
            current_cut_path = ""
            state["current_cut_path"] = ""
    return events
