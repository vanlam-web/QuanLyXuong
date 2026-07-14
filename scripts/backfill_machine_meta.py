import json
import os
import sqlite3
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
APP_ROOT = os.path.join(PROJECT_ROOT, "app")
if APP_ROOT not in sys.path:
    sys.path.insert(0, APP_ROOT)

from machine_file_meta import collect_machine_file_meta_for_server
from qlx_config import DB_DIR


def has_useful_meta(raw):
    try:
        meta = json.loads(raw or "{}")
    except Exception:
        return False
    useful_keys = ("area_m2", "width_cm", "height_cm", "image_width_px", "image_height_px", "line_count", "width_mm", "height_mm")
    return any(meta.get(key) not in (None, "", 0) for key in useful_keys)


def needs_refresh(raw):
    try:
        meta = json.loads(raw or "{}")
    except Exception:
        return True
    if not has_useful_meta(raw):
        return True
    source_kind = str(meta.get("source_kind") or "").lower()
    metadata_source = str(meta.get("metadata_source") or "").lower()
    return source_kind == "rip_preview_bmp" or metadata_source.endswith(".prn.bmp")


def backfill_machine(machine):
    db_path = os.path.join(DB_DIR, f"{machine}.db")
    if not os.path.exists(db_path):
        return {"machine": machine, "updated": 0, "missing": 0, "db": db_path}

    conn = sqlite3.connect(db_path, timeout=20)
    try:
        cols = [row[1] for row in conn.execute("PRAGMA table_info(files)")]
        if "machine_meta_json" not in cols:
            conn.execute("ALTER TABLE files ADD COLUMN machine_meta_json TEXT DEFAULT '{}'")
        rows = conn.execute(
            """
            SELECT file_hash, file_name, file_path, updated_time, machine_meta_json
            FROM files
            ORDER BY updated_time DESC
            """
        ).fetchall()
        updated = 0
        missing = 0
        for file_hash, file_name, file_path, updated_time, machine_meta_json in rows:
            if not needs_refresh(machine_meta_json):
                continue
            meta = collect_machine_file_meta_for_server(machine, file_path, file_name, updated_time)
            if not meta:
                missing += 1
                continue
            conn.execute(
                "UPDATE files SET machine_meta_json=? WHERE file_hash=?",
                (json.dumps(meta, ensure_ascii=False), file_hash),
            )
            updated += 1
        conn.commit()
        return {"machine": machine, "updated": updated, "missing": missing, "db": db_path}
    finally:
        conn.close()


def main():
    results = [backfill_machine(machine) for machine in ("InDecal", "InBat", "CNC")]
    for result in results:
        print(result)


if __name__ == "__main__":
    main()
