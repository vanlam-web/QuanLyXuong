import argparse
import csv
import json
import os
import socket
import time
from datetime import datetime

import requests

from cnc_log_parser import parse_cnc_dyn_progress, parse_cnc_log_events
from tap_preview import analyze_tap_file, estimate_tap_path_progress, find_existing_tap, render_tap_preview_b64


BRIDGE_VERSION = "V2.1.0_TEST_CNC_BRIDGE"
DEFAULT_HISTORY = r"\\CNC\CNC\CLIENT_CNC\file_history.csv"
DEFAULT_NCSTUDIO_LOG = r"\\CNC\Ncstudio V5.5.60\NCSTUDIO.LOG"
DEFAULT_NCSTUDIO_DYN = r"\\CNC\Ncstudio V5.5.60\NCSTUDIO.DYN"
DEFAULT_DYN_STALE_SECONDS = 60
DEFAULT_STATE = r"C:\QuanLyXuong\Data\cnc_legacy_bridge_state.json"
DEFAULT_API = "http://127.0.0.1:8000"


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def print_log(message):
    print(f"[{now()}] {message}", flush=True)


def load_state(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(path, state):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except Exception as exc:
        print_log(f"Cannot save state: {exc}")


def post_ping(api_base, source_path):
    payload = {
        "machine": "cnc",
        "version": BRIDGE_VERSION,
        "hostname": "CNC qua bridge V1",
    }
    res = requests.post(f"{api_base}/api/ping", json=payload, timeout=5)
    res.raise_for_status()
    print_log(f"Ping V2 OK from {source_path}")


def normalize_event_type(value):
    value = (value or "").strip().upper()
    if value in ("EXPORT", "EXPORTED"):
        return "EXPORT"
    if value in ("CUTTING", "DONE", "DELETE", "PAUSE"):
        return value
    return ""


def legacy_path(file_name, event_time):
    clean = (file_name or "").strip()
    if not clean:
        clean = "unknown"
    _, ext = os.path.splitext(clean)
    if not ext:
        clean = clean + ".tap"
    day = "unknown-day"
    try:
        day = datetime.strptime(event_time, "%Y-%m-%d %H:%M:%S").strftime("%Y-%m-%d")
    except Exception:
        pass
    return rf"D:\CNC\{day}\{clean}"


def parse_history_lines(text):
    rows = []
    reader = csv.reader(text.splitlines())
    for row in reader:
        if not row or row[0].strip().lower() in ("thoigian", "time"):
            continue
        if len(row) < 3:
            continue
        event_time = row[0].strip()
        event_type = normalize_event_type(row[1])
        rest = row[2:]
        if len(rest) >= 2 and len(rest) % 2 == 0:
            file_name = ",".join(rest[: len(rest) // 2]).strip()
        else:
            file_name = rest[0].strip()
        if not event_type or not file_name:
            continue
        rows.append(
            {
                "event_time": event_time,
                "event_type": event_type,
                "file_name": file_name,
                "path": legacy_path(file_name, event_time),
            }
        )
    return rows


def read_new_text(path, state, import_existing=False, offset_key="offset", encoding="utf-8-sig"):
    size = os.path.getsize(path)
    offset = int(state.get(offset_key) or 0)

    if offset <= 0 and not import_existing:
        state[offset_key] = size
        return ""
    if size < offset:
        offset = 0

    with open(path, "rb") as f:
        f.seek(offset)
        data = f.read()
        state[offset_key] = f.tell()

    return data.decode(encoding, errors="ignore")

def convert_ncstudio_events(raw_events):
    events = []
    for event in raw_events:
        file_name = event.get("forced_base_id") or os.path.splitext(os.path.basename(event.get("path") or ""))[0]
        if not file_name or not event.get("event_type") or not event.get("event_time"):
            continue
        events.append(
            {
                "event_time": event["event_time"],
                "event_type": event["event_type"],
                "file_name": file_name,
                "path": event.get("path") or legacy_path(file_name, event["event_time"]),
                "machine_meta": event.get("machine_meta") or {},
            }
        )
    return events

def read_dyn_progress_event(dyn_path, state, stale_seconds=DEFAULT_DYN_STALE_SECONDS):
    current_path = (state or {}).get("current_cut_path") or ""
    if not current_path or not dyn_path or not os.path.exists(dyn_path):
        return None
    tap_path = find_existing_tap(current_path)
    line_count = 0
    if tap_path:
        try:
            line_count = int((analyze_tap_file(tap_path) or {}).get("line_count") or 0)
        except Exception as exc:
            print_log(f"Cannot analyze TAP for DYN progress {tap_path}: {exc}")
    try:
        with open(dyn_path, "rb") as handle:
            meta = parse_cnc_dyn_progress(handle.read(), line_count)
    except Exception as exc:
        print_log(f"Cannot read NCStudio DYN: {exc}")
        return None
    current_line = meta.get("current_line")
    if not current_line:
        return None
    mtime = os.path.getmtime(dyn_path)
    if stale_seconds and time.time() - mtime >= max(10, int(stale_seconds or 0)):
        return None
    dyn_key = f"{current_path}|{int(mtime)}|{current_line}"
    if state.get("last_dyn_progress_key") == dyn_key:
        return None
    state["last_dyn_progress_key"] = dyn_key
    event_time = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
    meta["progress_source"] = "cnc_dyn_line"
    meta["progress_signal_time"] = event_time
    if tap_path:
        try:
            path_meta = estimate_tap_path_progress(tap_path, current_line)
            if path_meta:
                meta.update(path_meta)
        except Exception as exc:
            print_log(f"Cannot estimate TAP path progress {tap_path}: {exc}")
    return {
        "event_time": event_time,
        "event_type": "CUTTING",
        "file_name": os.path.splitext(os.path.basename(current_path))[0],
        "path": current_path,
        "machine_meta": meta,
    }


def post_event(api_base, event):
    key_src = f"cnc-legacy|{event['event_time']}|{event['event_type']}|{event['file_name']}"
    thumbnail_b64 = None
    machine_meta = dict(event.get("machine_meta") or {})
    tap_path = find_existing_tap(event["path"])
    if tap_path:
        try:
            thumbnail_b64 = render_tap_preview_b64(tap_path)
            tap_meta = analyze_tap_file(tap_path)
            tap_meta["metadata_source"] = tap_path
            tap_meta.update(machine_meta)
            machine_meta = tap_meta
        except Exception as exc:
            print_log(f"Cannot render TAP preview {tap_path}: {exc}")
    payload = {
        "machine": "cnc",
        "path": event["path"],
        "event_type": event["event_type"],
        "forced_base_id": event["file_name"],
        "forced_display_name": event["file_name"],
        "event_time": event["event_time"],
        "thumbnail_b64": thumbnail_b64,
        "machine_meta": machine_meta,
        "event_id": key_src,
        "idempotency_key": key_src,
    }
    res = requests.post(f"{api_base}/api/log_event", json=payload, timeout=8)
    res.raise_for_status()
    print_log(f"Event V2 OK {event['event_type']}: {event['file_name']}")


def run_once(args, state):
    history_exists = os.path.exists(args.history)
    ncstudio_log = getattr(args, "ncstudio_log", DEFAULT_NCSTUDIO_LOG)
    ncstudio_exists = bool(ncstudio_log) and os.path.exists(ncstudio_log)
    if not history_exists and not ncstudio_exists:
        print_log(f"History not found: {args.history}")
        print_log(f"NCStudio log not found: {ncstudio_log}")
        return state

    post_ping(args.api, args.history if history_exists else ncstudio_log)
    events = []
    if history_exists:
        text = read_new_text(args.history, state, import_existing=args.import_existing)
        events.extend(parse_history_lines(text))
    else:
        print_log(f"History not found: {args.history}")
    if ncstudio_exists:
        text = read_new_text(
            ncstudio_log,
            state,
            import_existing=getattr(args, "import_existing_ncstudio", False),
            offset_key="ncstudio_offset",
            encoding="gb18030",
        )
        events.extend(convert_ncstudio_events(parse_cnc_log_events(text.splitlines(), state=state)))
    elif ncstudio_log:
        print_log(f"NCStudio log not found: {ncstudio_log}")
    dyn_event = read_dyn_progress_event(
        getattr(args, "ncstudio_dyn", DEFAULT_NCSTUDIO_DYN),
        state,
        getattr(args, "dyn_stale_seconds", DEFAULT_DYN_STALE_SECONDS),
    )
    if dyn_event:
        events.append(dyn_event)
    for event in events:
        if args.dry_run:
            print_log(f"DRY {event['event_type']}: {event['file_name']}")
        else:
            post_event(args.api, event)
    state["last_seen"] = now()
    state["host"] = socket.gethostname()
    state["version"] = BRIDGE_VERSION
    return state


def main():
    parser = argparse.ArgumentParser(description="Bridge CNC V1 history into QuanLyXuong V2.")
    parser.add_argument("--history", default=DEFAULT_HISTORY)
    parser.add_argument("--state", default=DEFAULT_STATE)
    parser.add_argument("--api", default=DEFAULT_API)
    parser.add_argument("--ncstudio-log", default=DEFAULT_NCSTUDIO_LOG)
    parser.add_argument("--ncstudio-dyn", default=DEFAULT_NCSTUDIO_DYN)
    parser.add_argument("--dyn-stale-seconds", type=int, default=DEFAULT_DYN_STALE_SECONDS)
    parser.add_argument("--interval", type=int, default=10)
    parser.add_argument("--loop", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--import-existing", action="store_true")
    parser.add_argument("--import-existing-ncstudio", action="store_true")
    args = parser.parse_args()

    state = load_state(args.state)
    while True:
        try:
            state = run_once(args, state)
            save_state(args.state, state)
        except Exception as exc:
            print_log(f"Bridge error: {exc}")
        if not args.loop:
            break
        time.sleep(max(2, args.interval))


if __name__ == "__main__":
    main()
