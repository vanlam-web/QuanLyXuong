import argparse
import hashlib
import json
import os
import re
import sqlite3
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path


DEFAULT_DATA_DIR = r"C:\QuanLyXuong\Data"
DEFAULT_STATE_FILE = r"C:\QuanLyXuong\Data\qcvl_bridge_state.json"
DEFAULT_LOG_FILE = r"C:\QuanLyXuong\QCVL_Bridge_Log.txt"
MACHINES = {
    "InBat": {"code": "INBAT", "name": "In bat", "type": "banner_print"},
    "InDecal": {"code": "INDECAL", "name": "In decal", "type": "decal_print"},
    "CNC": {"code": "CNC", "name": "Cat CNC", "type": "cnc_cut"},
}
STATUS_TO_EVENT = {
    "EXPORT": "EXPORTED",
    "EXPORTED": "EXPORTED",
    "RIP": "RIP",
    "PRINTING": "PRINTING",
    "CUTTING": "CUTTING",
    "DONE": "DONE",
    "DELETE": "DELETED",
    "DELETED": "DELETED",
}


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log(message, log_file):
    line = f"[{now()}] {message}"
    print(line)
    try:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        with open(log_file, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except OSError:
        pass


def load_state(path):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            state = json.load(handle)
            if isinstance(state, dict):
                return state
    except (OSError, json.JSONDecodeError):
        pass
    return {"processed": {}}


def save_state(path, state):
    state_path = Path(path)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = state_path.with_suffix(state_path.suffix + ".tmp")
    with open(tmp_path, "w", encoding="utf-8") as handle:
        json.dump(state, handle, ensure_ascii=False, indent=2)
    os.replace(tmp_path, state_path)


def connect_readonly(db_path):
    uri = Path(db_path).resolve().as_uri() + "?mode=ro"
    return sqlite3.connect(uri, uri=True, timeout=10)


def parse_filename(file_name):
    name = Path(file_name).stem
    clean_name = name
    if "~" in clean_name and clean_name.split("~", 1)[0].isdigit():
        clean_name = clean_name.split("~", 1)[1]
    if "~" in clean_name:
        clean_name = clean_name.split("~", 1)[0]

    parts = [part for part in re.split(r"[_\s]+", clean_name) if part]
    customer_code = parts[0] if parts else None
    quantity = 1
    for quantity_pattern in (
        r"(?:^|[_\s-])x(\d+)(?:$|[_\s-])",
        r"(?:^|[_\s-])sl(\d+)(?:$|[_\s-])",
        r"(?:^|[_\s-])xsl(\d+)(?:$|[_\s-])",
    ):
        quantity_match = re.search(quantity_pattern, name, flags=re.IGNORECASE)
        if quantity_match:
            quantity = max(int(quantity_match.group(1)), 1)
            break

    dimension_match = re.search(r"(\d{2,5}(?:[.,]\d+)?)\s*[xX*]\s*(\d{2,5}(?:[.,]\d+)?)", name)
    width_m = height_m = None
    if dimension_match:
        width = float(dimension_match.group(1).replace(",", "."))
        height = float(dimension_match.group(2).replace(",", "."))
        # Legacy filenames usually store cm for print/cut dimensions.
        width_m = round(width / 100, 4)
        height_m = round(height / 100, 4)

    return {
        "customer_code": customer_code,
        "width_m": width_m,
        "height_m": height_m,
        "quantity": quantity,
        "raw_name": name,
        "dimension_source": "filename" if width_m and height_m else None,
    }

def apply_machine_meta_dimensions(parsed, machine_meta):
    if not isinstance(machine_meta, dict):
        return parsed
    if str(machine_meta.get("source_kind") or "").lower() != "rip_file_header":
        return parsed

    try:
        width_cm = float(machine_meta.get("width_cm") or 0)
        height_cm = float(machine_meta.get("height_cm") or 0)
    except (TypeError, ValueError):
        return parsed
    if width_cm <= 0 or height_cm <= 0:
        return parsed

    updated = dict(parsed)
    updated["width_m"] = round(width_cm / 100, 4)
    updated["height_m"] = round(height_cm / 100, 4)
    updated["dimension_source"] = "rip_file_header"
    try:
        area_m2 = float(machine_meta.get("area_m2") or 0)
    except (TypeError, ValueError):
        area_m2 = 0
    if area_m2 > 0:
        updated["area_m2"] = round(area_m2, 4)
    if machine_meta.get("metadata_source"):
        updated["dimension_metadata_source"] = machine_meta.get("metadata_source")
    return updated


def legacy_event_key(machine, row):
    raw = "|".join(
        [
            machine,
            row["file_hash"] or "",
            row["status"] or "",
            row["updated_time"] or "",
            str(row["run_count"] or 1),
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def make_payload(machine, row):
    machine_info = MACHINES[machine]
    raw_file_name = row["file_name"] or Path(row["file_path"] or "").name
    event_type = STATUS_TO_EVENT.get((row["status"] or "").upper(), row["status"] or "UNKNOWN")
    parsed = parse_filename(raw_file_name)
    parsed = apply_machine_meta_dimensions(parsed, safe_json(row.get("machine_meta_json"), {}))
    parse_status = "ok" if parsed["width_m"] and parsed["height_m"] else "pending"
    event_key = legacy_event_key(machine, row)
    return {
        "legacy_event_hash": event_key,
        "source": "QuanLyXuong",
        "machine": {
            "legacy_name": machine,
            "code": machine_info["code"],
            "name": machine_info["name"],
            "machine_type": machine_info["type"],
        },
        "raw_file_name": raw_file_name,
        "raw_file_path": row["file_path"] or "",
        "event_type": event_type,
        "job_type": row["job_type"] or "",
        "status": row["status"] or "",
        "received_at": row["created_time"] or row["updated_time"] or now(),
        "updated_at": row["updated_time"] or row["created_time"] or now(),
        "run_count": int(row["run_count"] or 1),
        "parse_status": parse_status,
        "parse_error": None if parse_status == "ok" else "missing_dimension",
        "parsed": parsed,
        "legacy": {
            "file_hash": row["file_hash"],
            "history": safe_json(row["history"], []),
        },
    }


def safe_json(value, fallback):
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


def read_machine_rows(data_dir, machine, since_time, limit):
    db_path = Path(data_dir) / f"{machine}.db"
    if not db_path.exists():
        return []

    with connect_readonly(db_path) as conn:
        conn.row_factory = sqlite3.Row
        cols = {row["name"] for row in conn.execute("pragma table_info(files)").fetchall()}
        meta_expr = "machine_meta_json" if "machine_meta_json" in cols else "'' as machine_meta_json"
        query = f"""
            select file_hash, file_name, file_path, machine, job_type, status,
                   created_time, updated_time, run_count, history, {meta_expr}
            from files
            where coalesce(updated_time, created_time, '') >= ?
            order by coalesce(updated_time, created_time, '') asc
            limit ?
        """
        return [dict(row) for row in conn.execute(query, (since_time, limit)).fetchall()]


def post_payload(api_base_url, token, payload, timeout):
    url = api_base_url.rstrip("/") + "/api/v1/production-events"
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"content-type": "application/json"}
    if token:
        headers["authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        response_body = response.read().decode("utf-8", errors="replace")
        return response.status, response_body


def run_once(args):
    state = load_state(args.state_file)
    processed = state.setdefault("processed", {})
    since_dt = datetime.now() - timedelta(minutes=args.since_minutes)
    since_time = since_dt.strftime("%Y-%m-%d %H:%M:%S")
    dry_run = args.dry_run if args.dry_run is not None else os.getenv("QCVL_BRIDGE_DRY_RUN", "1") != "0"
    api_base_url = args.api_base_url or os.getenv("QCVL_API_BASE_URL", "")
    token = args.api_token or os.getenv("QCVL_API_TOKEN", "")
    dump_handle = None
    if args.dump_jsonl:
        dump_path = Path(args.dump_jsonl)
        dump_path.parent.mkdir(parents=True, exist_ok=True)
        dump_handle = open(dump_path, "a", encoding="utf-8")

    try:
        if not dry_run and not api_base_url:
            raise SystemExit("QCVL_API_BASE_URL is required when dry-run is disabled.")

        sent = skipped = failed = 0
        for machine in MACHINES:
            rows = read_machine_rows(args.data_dir, machine, since_time, args.limit)
            for row in rows:
                payload = make_payload(machine, row)
                event_key = payload["legacy_event_hash"]
                if processed.get(event_key) == "ok":
                    skipped += 1
                    continue

                if dump_handle:
                    dump_handle.write(json.dumps(payload, ensure_ascii=False) + "\n")

                if dry_run:
                    log(f"DRY-RUN {machine} {payload['event_type']} {payload['raw_file_name']} key={event_key[:12]}", args.log_file)
                    if args.save_checkpoint:
                        processed[event_key] = "ok"
                    sent += 1
                    continue

                try:
                    status, body = post_payload(api_base_url, token, payload, args.timeout)
                    if 200 <= status < 300:
                        processed[event_key] = "ok"
                        sent += 1
                        log(f"SENT {machine} {payload['event_type']} {payload['raw_file_name']} status={status}", args.log_file)
                    else:
                        failed += 1
                        log(f"FAIL {machine} {payload['raw_file_name']} status={status} body={body[:300]}", args.log_file)
                except (urllib.error.URLError, TimeoutError, OSError) as error:
                    failed += 1
                    log(f"FAIL {machine} {payload['raw_file_name']} error={error}", args.log_file)

        state["last_run_at"] = now()
        state["dry_run"] = dry_run
        save_state(args.state_file, state)
        if dump_handle:
            log(f"DUMP jsonl={args.dump_jsonl}", args.log_file)
        log(f"SUMMARY sent_or_seen={sent} skipped={skipped} failed={failed} dry_run={dry_run}", args.log_file)
        return failed
    finally:
        if dump_handle:
            dump_handle.close()


def build_parser():
    parser = argparse.ArgumentParser(description="Bridge QuanLyXuong SQLite events to QCVL production events.")
    parser.add_argument("--data-dir", default=os.getenv("QCVL_BRIDGE_DATA_DIR", DEFAULT_DATA_DIR))
    parser.add_argument("--state-file", default=os.getenv("QCVL_BRIDGE_STATE_FILE", DEFAULT_STATE_FILE))
    parser.add_argument("--log-file", default=os.getenv("QCVL_BRIDGE_LOG_FILE", DEFAULT_LOG_FILE))
    parser.add_argument("--api-base-url", default="")
    parser.add_argument("--api-token", default="")
    parser.add_argument("--since-minutes", type=int, default=int(os.getenv("QCVL_BRIDGE_SINCE_MINUTES", "720")))
    parser.add_argument("--limit", type=int, default=int(os.getenv("QCVL_BRIDGE_LIMIT", "200")))
    parser.add_argument("--timeout", type=int, default=int(os.getenv("QCVL_BRIDGE_TIMEOUT", "8")))
    parser.add_argument("--loop", action="store_true")
    parser.add_argument("--interval", type=int, default=int(os.getenv("QCVL_BRIDGE_INTERVAL", "30")))
    parser.add_argument("--dry-run", dest="dry_run", action="store_true")
    parser.add_argument("--send", dest="dry_run", action="store_false")
    parser.set_defaults(dry_run=None)
    parser.add_argument("--dump-jsonl", default=os.getenv("QCVL_BRIDGE_DUMP_JSONL", ""))
    parser.add_argument("--save-checkpoint", action="store_true", default=os.getenv("QCVL_BRIDGE_SAVE_DRY_RUN_CHECKPOINT", "1") != "0")
    parser.add_argument("--no-save-checkpoint", dest="save_checkpoint", action="store_false")
    return parser


def main():
    args = build_parser().parse_args()
    if args.loop:
        while True:
            run_once(args)
            time.sleep(max(args.interval, 5))
    else:
        raise SystemExit(run_once(args))


if __name__ == "__main__":
    main()
