import argparse
import json
import os
import sqlite3
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
APP_ROOT = os.path.join(PROJECT_ROOT, "app")
if APP_ROOT not in sys.path:
    sys.path.insert(0, APP_ROOT)

from cnc_log_parser import parse_cnc_log_events
from qlx_config import DB_DIR
from tap_preview import analyze_tap_file, find_existing_tap


def build_tap_line_counts(paths):
    counts = {}
    for path in paths:
        tap_path = find_existing_tap(path)
        if not tap_path:
            continue
        try:
            meta = analyze_tap_file(tap_path)
            counts[os.path.basename(path)] = int(meta.get("line_count") or 0)
        except Exception:
            pass
    return counts


def load_last_events(log_path, tap_paths):
    with open(log_path, "rb") as handle:
        lines = handle.read().decode("gb18030", errors="ignore").splitlines()
    events = parse_cnc_log_events(lines, build_tap_line_counts(tap_paths))
    last = {}
    for event in events:
        last[os.path.basename(event["path"]).lower()] = event
    return last


def reconcile(db_path, log_path, apply=False):
    conn = sqlite3.connect(db_path, timeout=20)
    conn.row_factory = sqlite3.Row
    changes = []
    try:
        rows = conn.execute(
            """
            SELECT file_hash, file_name, file_path, status, updated_time, history, machine_meta_json
            FROM files
            WHERE status='CUTTING'
            ORDER BY updated_time DESC
            """
        ).fetchall()
        last_events = load_last_events(log_path, [row["file_path"] for row in rows])
        for row in rows:
            event = last_events.get(row["file_name"].lower())
            if not event or event.get("event_type") != "DONE":
                continue
            done_time = event.get("event_time") or row["updated_time"]
            history = json.loads(row["history"] or "[]")
            history.append({"status": "DONE", "time": done_time, "event": "DONE_FROM_NCSTUDIO_LOG"})
            meta = json.loads(row["machine_meta_json"] or "{}")
            meta.update(event.get("machine_meta") or {})
            meta["log_done_time"] = done_time
            meta["log_source"] = "NcStudio log"
            change = {
                "file_hash": row["file_hash"],
                "file_name": row["file_name"],
                "from_status": row["status"],
                "to_status": "DONE",
                "done_time": done_time,
            }
            changes.append(change)
            if apply:
                conn.execute(
                    "UPDATE files SET status=?, updated_time=?, history=?, machine_meta_json=?, zalo_sent=0 WHERE file_hash=?",
                    ("DONE", done_time, json.dumps(history, ensure_ascii=False), json.dumps(meta, ensure_ascii=False), row["file_hash"]),
                )
        if apply:
            conn.commit()
    finally:
        conn.close()
    return changes


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--db", default=os.path.join(DB_DIR, "CNC.db"))
    parser.add_argument("--log", default=r"\\CNC\Ncstudio V5.5.60\NCSTUDIO.LOG")
    args = parser.parse_args()
    for change in reconcile(args.db, args.log, apply=args.apply):
        print(json.dumps(change, ensure_ascii=False))


if __name__ == "__main__":
    main()
