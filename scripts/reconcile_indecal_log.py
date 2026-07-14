import argparse
import json
import os
import sqlite3
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
APP_ROOT = os.path.join(PROJECT_ROOT, "app")
if APP_ROOT not in sys.path:
    sys.path.insert(0, APP_ROOT)

from QuanLyXuong import parse_indecal_log_events
from qlx_config import DB_DIR


def load_last_events(log_path):
    with open(log_path, "rb") as handle:
        lines = handle.read().decode("gb18030", errors="ignore").splitlines()
    state = {}
    events = parse_indecal_log_events(lines, state)
    last = {}
    for event in events:
        last[event["file_name"].lower()] = event
    return last


def reconcile(db_path, log_path, apply=False):
    last_events = load_last_events(log_path)
    conn = sqlite3.connect(db_path, timeout=20)
    conn.row_factory = sqlite3.Row
    changes = []
    try:
        rows = conn.execute(
            """
            SELECT file_hash, file_name, status, updated_time, history, machine_meta_json
            FROM files
            WHERE status='PRINTING'
            ORDER BY updated_time DESC
            """
        ).fetchall()
        for row in rows:
            event = last_events.get(row["file_name"].lower())
            if not event or event.get("event_type") != "DONE":
                continue
            meta_extra = event.get("machine_meta") or {}
            done_time = meta_extra.get("log_done_time") or row["updated_time"]
            history = json.loads(row["history"] or "[]")
            history.append({
                "status": "DONE",
                "time": done_time,
                "event": "DONE_FROM_INDECAL_LOG",
                "progress_percent": meta_extra.get("progress_percent"),
            })
            meta = json.loads(row["machine_meta_json"] or "{}")
            meta.update(meta_extra)
            meta["log_source"] = "InDecal PrintExp log"
            change = {
                "file_hash": row["file_hash"],
                "file_name": row["file_name"],
                "from_status": row["status"],
                "to_status": "DONE",
                "done_time": done_time,
                "progress_percent": meta_extra.get("progress_percent"),
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
    parser.add_argument("--db", default=os.path.join(DB_DIR, "InDecal.db"))
    parser.add_argument("--log", default=r"\\InDecal\Log\Log[2026_07_13].txt")
    args = parser.parse_args()
    for change in reconcile(args.db, args.log, apply=args.apply):
        print(json.dumps(change, ensure_ascii=False))


if __name__ == "__main__":
    main()
