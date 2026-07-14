# =========================================
# WEB DASHBOARD V8.7.0 - V2 STATUS
# =========================================
import sqlite3, os, sys, json, requests, re, unicodedata, time, threading, subprocess, socket
from flask import Flask, render_template_string, jsonify, request, send_from_directory, Response
from datetime import datetime, timedelta
from qlx_config import BASE_DATA_CRM, DASHBOARD_HOST, DASHBOARD_PORT, DB_DIR, NAS_DASHBOARD_EXE_PATH, SERVER_BROADCAST_URL

app = Flask(__name__)

# --- CONFIG DUONG DAN EXE ---
MACHINES = ["InBat", "InDecal", "CNC"]
ADMIN_PIN = os.getenv("DASHBOARD_ADMIN_PIN", "").strip()

THUMB_DIR = os.path.join(DB_DIR, "Thumbnails")
os.makedirs(THUMB_DIR, exist_ok=True)

# LOG FILES
LOG_FILE = r"C:\QuanLyXuong\Dashboard_Log.txt"
SERVER_LOG_FILE = r"C:\QuanLyXuong\Server_Log.txt"
MACHINE_LOG_FILE = r"C:\QuanLyXuong\system_log.txt"
QCVL_BRIDGE_LOG_FILE = r"C:\QuanLyXuong\QCVL_Bridge_Log.txt"

def print_log(msg):
    log_str = f"[{now()}] {msg}"
    print(log_str)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(log_str + "\n")
    except: pass

# AUTO UPDATE WATCHER
def auto_update_watcher():
    start_mtime = 0
    while True:
        time.sleep(10)
        try:
            if not os.path.exists(NAS_DASHBOARD_EXE_PATH): continue
            cur_mtime = os.path.getmtime(NAS_DASHBOARD_EXE_PATH)
            
            if start_mtime == 0: 
                start_mtime = cur_mtime
            elif cur_mtime != start_mtime:
                print_log("Phat hien Dashboard moi tren NAS. Kich hoat cap nhat.")
                import subprocess
                subprocess.call("taskkill /F /IM server_Local.exe /T", shell=True)
                os._exit(0) 
        except: pass

def now(): return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def chuan_hoa_chuoi(text):
    if not text: return ""
    text = text.lower()
    text = unicodedata.normalize('NFKD', text).encode('ASCII', 'ignore').decode('utf-8')
    text = re.sub(r'[^a-z0-9]', '', text)
    return text

def parse_area_python(filename):
    if not filename: return 0.0
    m2 = 0.0
    match = re.search(r'(\d{2,4})\s*[xX]\s*(\d{2,4})', str(filename).lower())
    if match:
        try: m2 = (int(match.group(1)) * int(match.group(2))) / 10000.0
        except: pass
    return m2

def parse_machine_meta_json(value):
    if not value:
        return {}
    try:
        data = json.loads(value) if isinstance(value, str) else value
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}

def area_from_machine_meta(meta):
    data = parse_machine_meta_json(meta)
    try:
        area = float(data.get("area_m2") or 0)
        return area if area > 0 else 0.0
    except Exception:
        return 0.0

def best_area_m2(filename, machine_meta=None):
    return area_from_machine_meta(machine_meta) or parse_area_python(filename)

def safe_float(value, default=0.0):
    try:
        return float(value or default)
    except (TypeError, ValueError):
        return default

def machine_meta_select_expr(conn):
    try:
        cols = [col[1] for col in conn.execute("PRAGMA table_info(files)").fetchall()]
        if "machine_meta_json" in cols:
            return "machine_meta_json"
    except Exception:
        pass
    return "'{}' AS machine_meta_json"

def parse_expected_runs(filename):
    name = os.path.splitext(str(filename or ""))[0]
    # Remove display suffix added for repeated legacy DONE rows, not customer quantity.
    name = re.sub(r"\s+\(x\d+\)$", "", name, flags=re.IGNORECASE)
    patterns = (
        r"(?:^|[_\s-])x(\d+)(?:$|[_\s-])",
        r"(?:^|[_\s-])sl(\d+)(?:$|[_\s-])",
        r"(?:^|[_\s-])xsl(\d+)(?:$|[_\s-])",
        r"(?:^|[_\s-])so\s*luong\s*(\d+)(?:$|[_\s-])",
    )
    for pattern in patterns:
        match = re.search(pattern, name, flags=re.IGNORECASE)
        if match:
            try:
                return max(int(match.group(1)), 1)
            except ValueError:
                return 1
    return 1

def classify_reprint(file_name, run_count):
    try:
        actual_runs = max(int(run_count or 1), 1)
    except (TypeError, ValueError):
        actual_runs = 1
    expected_runs = parse_expected_runs(file_name)
    has_explicit_qty = expected_runs > 1
    needs_review = actual_runs > expected_runs or (actual_runs > 1 and not has_explicit_qty)
    extra_runs = max(actual_runs - expected_runs, 0)
    return {
        "expected_runs": expected_runs,
        "actual_runs": actual_runs,
        "billable_runs": max(actual_runs, expected_runs),
        "extra_runs": extra_runs,
        "needs_review": needs_review,
        "label": "Cần xác nhận in lại" if needs_review else ("Đúng số lượng" if has_explicit_qty else ""),
    }

def classify_active_reprint(history_data, has_done_before=False, file_name=""):
    history = load_history(history_data)
    for item in reversed(history):
        event_text = str(item.get("event") or "")
        if "In lại sau khi đã xong" in event_text or "Cắt lại sau khi đã xong" in event_text:
            return {
                "is_reprint_waiting_done": True,
                "label": event_text,
                "needs_review": True,
            }
    if has_done_before and parse_expected_runs(file_name) <= 1:
        return {
            "is_reprint_waiting_done": True,
            "label": "In lại sau khi đã xong - chờ tín hiệu xong",
            "needs_review": True,
        }
    return {
        "is_reprint_waiting_done": False,
        "label": "",
        "needs_review": False,
    }

def classify_reprint_cancel_after_done(file_name, has_done_before, is_production_error):
    if has_done_before and is_production_error and parse_expected_runs(file_name) <= 1:
        return {
            "is_reprint_cancel_after_done": True,
            "label": "Tín hiệu in lại sau DONE rồi bị xóa - cần kiểm tra tín hiệu/máy",
            "needs_review": False,
        }
    return {
        "is_reprint_cancel_after_done": False,
        "label": "",
        "needs_review": False,
    }

def load_history(history_data):
    try:
        history = json.loads(history_data or "[]")
        return history if isinstance(history, list) else []
    except Exception:
        return []

def parse_event_time(value):
    try:
        return datetime.strptime(str(value or ""), "%Y-%m-%d %H:%M:%S")
    except Exception:
        return None

def dashboard_job_core(file_name):
    name = os.path.basename(str(file_name or "")).lower().strip()
    name = re.sub(r"^\d+~", "", name)
    return name

def dashboard_job_tokens(file_name):
    core = dashboard_job_core(file_name)
    core = re.sub(r"\.[a-z0-9]+$", "", core)
    parts = re.split(r"[^a-z0-9]+", core)
    stopwords = {"copy", "new", "folder", "final", "file"}
    return {
        part
        for part in parts
        if len(part) >= 2 and part not in stopwords
    }

def dashboard_jobs_related(removed_name, done_name):
    if dashboard_job_core(removed_name) == dashboard_job_core(done_name):
        return True
    removed_tokens = dashboard_job_tokens(removed_name)
    done_tokens = dashboard_job_tokens(done_name)
    if len(removed_tokens) < 2:
        return False
    if not removed_tokens.issubset(done_tokens):
        return False
    return any(re.search(r"\d", token) for token in removed_tokens)

def active_start_time(history_data, fallback_updated_time):
    history = load_history(history_data)
    for item in reversed(history):
        if not isinstance(item, dict):
            continue
        if str(item.get("status") or "").upper() in {"PRINTING", "CUTTING"}:
            return parse_event_time(item.get("time"))
    return parse_event_time(fallback_updated_time)

def find_later_machine_run(rows, current_name, active_time):
    if not active_time:
        return None
    current_core = dashboard_job_core(current_name)
    candidates = []
    for row in rows:
        other_name = row[1]
        if dashboard_job_core(other_name) == current_core:
            continue
        history = load_history(row[7])
        for item in history:
            if not isinstance(item, dict):
                continue
            status = str(item.get("status") or "").upper()
            if status not in {"PRINTING", "CUTTING"}:
                continue
            event_time = parse_event_time(item.get("time"))
            if event_time and event_time > active_time:
                candidates.append({
                    "event_time": event_time,
                    "name": str(other_name or ""),
                    "status": status,
                    "time": event_time.strftime("%Y-%m-%d %H:%M:%S"),
                })
        if history:
            continue
        fallback_time = parse_event_time(row[5])
        if row[3] == "DONE" and fallback_time and fallback_time > active_time:
            candidates.append({
                "event_time": fallback_time,
                "name": str(other_name or ""),
                "status": str(row[3] or ""),
                "time": fallback_time.strftime("%Y-%m-%d %H:%M:%S"),
            })
    if not candidates:
        return None
    candidates.sort(key=lambda item: item["event_time"])
    candidates[0].pop("event_time", None)
    return candidates[0]

def duration_between(history, start_statuses, end_statuses):
    start_time = None
    end_time = None
    for item in history:
        if not isinstance(item, dict):
            continue
        status = str(item.get("status") or "").upper()
        event = str(item.get("event") or "").upper()
        item_time = parse_event_time(item.get("time"))
        if not item_time:
            continue
        if status in start_statuses or event in start_statuses:
            start_time = item_time
        if start_time and (status in end_statuses or event in end_statuses):
            end_time = item_time
    if not start_time or not end_time:
        return None
    seconds = int((end_time - start_time).total_seconds())
    return seconds if seconds > 0 else None

def format_duration_label(seconds):
    try:
        seconds = int(seconds)
    except (TypeError, ValueError):
        return ""
    minutes = seconds // 60
    remain = seconds % 60
    if minutes <= 0:
        return f"{remain} giây"
    if remain <= 0:
        return f"{minutes} phút"
    return f"{minutes} phút {remain} giây"

def assess_prior_done_duration(file_name, done_histories, completed_samples):
    area = parse_area_python(file_name)
    durations = []
    for history_data in done_histories or []:
        duration = duration_between(load_history(history_data), {"PRINTING", "CUTTING"}, {"DONE"})
        if duration:
            durations.append(duration)

    if not durations or area <= 0:
        return {"trusted": True, "is_suspicious": False, "label": ""}

    sample_durations = []
    normalized_name = str(file_name or "").lower().strip()
    for sample in completed_samples or []:
        if not isinstance(sample, dict):
            continue
        sample_name = str(sample.get("file_name") or "").lower().strip()
        if sample_name == normalized_name:
            continue
        sample_area = parse_area_python(sample_name)
        if sample_area <= 0:
            continue
        ratio = sample_area / area
        if ratio < 0.65 or ratio > 1.35:
            continue
        sample_duration = duration_between(load_history(sample.get("history")), {"PRINTING", "CUTTING"}, {"DONE"})
        if sample_duration:
            sample_durations.append(sample_duration)

    shortest_done = min(durations)
    suspicious = False
    if sample_durations:
        ordered = sorted(sample_durations)
        expected = ordered[len(ordered) // 2]
        suspicious = shortest_done < max(30, expected * 0.45)
    else:
        suspicious = shortest_done < 180 and (shortest_done / area) < 45

    if not suspicious:
        return {"trusted": True, "is_suspicious": False, "label": ""}

    return {
        "trusted": False,
        "is_suspicious": True,
        "label": f"DONE trước đó quá nhanh ({format_duration_label(shortest_done)}) - cần kiểm tra tín hiệu/máy",
    }

def estimate_cancel_progress(file_name, history_data, completed_samples):
    history = load_history(history_data)
    delete_events = [
        item for item in history
        if isinstance(item, dict) and str(item.get("status") or "").upper() == "DELETED"
    ]
    last_delete = delete_events[-1] if delete_events else {}
    explicit_progress = last_delete.get("progress_percent")
    if explicit_progress is not None:
        try:
            percent = max(0, min(100, int(round(float(explicit_progress)))))
            area = parse_area_python(file_name)
            return {
                "progress_percent": percent,
                "progress_source": "explicit",
                "progress_label": f"Tiến độ: {percent}%",
                "estimated_bad_m2": (area * percent / 100) if area > 0 else None,
            }
        except (TypeError, ValueError):
            pass

    elapsed = duration_between(history, {"PRINTING", "CUTTING"}, {"DELETED", "DELETE"})
    area = parse_area_python(file_name)
    if not elapsed or area <= 0:
        return {"progress_percent": None, "progress_source": "unknown", "progress_label": "Tiến độ: chưa rõ"}

    durations = []
    for sample in completed_samples or []:
        sample_name = sample.get("file_name") if isinstance(sample, dict) else None
        sample_area = parse_area_python(sample_name)
        if sample_area <= 0:
            continue
        ratio = sample_area / area
        if ratio < 0.65 or ratio > 1.35:
            continue
        sample_history = load_history(sample.get("history") if isinstance(sample, dict) else None)
        sample_duration = duration_between(sample_history, {"PRINTING", "CUTTING"}, {"DONE"})
        if sample_duration:
            durations.append(sample_duration)

    if not durations:
        return {"progress_percent": None, "progress_source": "unknown", "progress_label": "Tiến độ: chưa rõ"}

    avg_duration = sum(durations) / len(durations)
    percent = max(1, min(99, int(round((elapsed / avg_duration) * 100))))
    bad_m2 = area * percent / 100 if area > 0 else None
    return {
        "progress_percent": percent,
        "progress_source": "estimated",
        "progress_label": f"Tiến độ: {percent}% ước tính",
        "estimated_bad_m2": bad_m2,
    }

def active_progress_label(machine_meta):
    meta = machine_meta if isinstance(machine_meta, dict) else parse_machine_meta_json(machine_meta)
    try:
        progress = meta.get("progress_percent")
        if progress is None:
            return ""
        percent = max(0, min(100, int(round(float(progress)))))
        return f"Tiến độ: {percent}%"
    except Exception:
        return ""

def estimate_active_progress(file_name, history_data, completed_samples, machine_meta=None, now_dt=None):
    history = load_history(history_data)
    start_dt = active_start_time(history_data, "")
    if not start_dt:
        return {"progress_percent": None, "progress_source": "unknown", "progress_label": ""}
    now_dt = now_dt or datetime.now()
    elapsed = max(0, int((now_dt - start_dt).total_seconds()))
    if elapsed <= 0:
        return {"progress_percent": None, "progress_source": "unknown", "progress_label": ""}

    meta = machine_meta if isinstance(machine_meta, dict) else parse_machine_meta_json(machine_meta)
    active_lines = safe_float(meta.get("line_count"))
    area = parse_area_python(file_name)
    durations = []
    for sample in completed_samples or []:
        if not isinstance(sample, dict):
            continue
        sample_history = load_history(sample.get("history"))
        sample_duration = duration_between(sample_history, {"PRINTING", "CUTTING"}, {"DONE"})
        if not sample_duration:
            continue
        sample_meta = sample.get("machine_meta") if isinstance(sample.get("machine_meta"), dict) else parse_machine_meta_json(sample.get("machine_meta"))
        sample_lines = safe_float(sample_meta.get("line_count"))
        if active_lines > 0 and sample_lines > 0:
            ratio = active_lines / sample_lines
            if 0.45 <= ratio <= 2.2:
                durations.append(sample_duration * ratio)
            continue
        sample_area = parse_area_python(sample.get("file_name"))
        if area > 0 and sample_area > 0:
            ratio = area / sample_area
            if 0.45 <= ratio <= 2.2:
                durations.append(sample_duration * ratio)

    if not durations:
        return {"progress_percent": None, "progress_source": "unknown", "progress_label": ""}

    expected = sorted(durations)[len(durations) // 2]
    percent = max(1, min(99, int(round(elapsed * 100 / expected))))
    return {
        "progress_percent": percent,
        "progress_source": "estimated",
        "progress_label": f"Tiến độ: {percent}% ước tính",
    }

def dedupe_visible_items(items):
    best = {}
    order = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        key = (
            str(item.get("machine") or "").lower(),
            dashboard_job_core(item.get("name")),
            str(item.get("cancel_type") or item.get("status") or "").lower(),
        )
        if key not in best:
            best[key] = item
            order.append(key)
            continue
        current_time = str(item.get("updated") or item.get("time_short") or "")
        old_time = str(best[key].get("updated") or best[key].get("time_short") or "")
        if current_time >= old_time:
            best[key] = item
    return [best[key] for key in order]

def filter_removed_items_with_later_done(removed_items, done_items):
    done_by_machine = {}
    for item in done_items or []:
        if not isinstance(item, dict):
            continue
        machine = str(item.get("machine") or "").lower()
        done_by_machine.setdefault(machine, []).append(item)

    filtered = []
    for item in removed_items or []:
        if str(item.get("cancel_type") or "").lower() in {"source_renamed_done", "done_cleanup"}:
            continue
        machine = str(item.get("machine") or "").lower()
        removed_time = str(item.get("updated") or "")
        has_later_done = any(
            str(done.get("updated") or "") >= removed_time
            and dashboard_jobs_related(item.get("name"), done.get("name"))
            for done in done_by_machine.get(machine, [])
        )
        if has_later_done:
            continue
        filtered.append(item)
    return filtered

def calculate_cancel_rate_by_m2(total_done_m2, total_bad_m2):
    try:
        done = max(float(total_done_m2 or 0), 0)
        bad = max(float(total_bad_m2 or 0), 0)
    except (TypeError, ValueError):
        return 0
    total = done + bad
    return (bad / total * 100) if total > 0 else 0

def is_cnc_expected_stop(machine, file_name):
    if str(machine or "").strip().upper() != "CNC":
        return False
    normalized = chuan_hoa_chuoi(file_name)
    if "tap" not in normalized:
        return False
    expected_markers = ("ngang", "chuandut")
    return all(marker in normalized for marker in expected_markers)

def missing_thumbnail_reason(file_obj):
    file_path = str(file_obj.get("file_path") or "").strip()
    if file_path:
        if not os.path.isabs(file_path):
            return f"DB chỉ có tên file, thiếu đường dẫn gốc để tìm lại ảnh: {file_path}"
        if os.path.exists(file_path):
            return "File gốc còn nhưng thumbnail chưa tạo được. Cần kiểm tra máy trạm gửi ảnh hoặc lỗi tạo preview."
        return f"File nằm trên máy trạm hoặc đã bị xóa; server không đọc trực tiếp được: {file_path}"
    return "Không có thumbnail trên server và không có đường dẫn file gốc để phục hồi ảnh."

def build_attention_items(data):
    items = []

    def add(title, severity, file_obj, reason):
        items.append({
            "title": title,
            "severity": severity,
            "machine": file_obj.get("machine", ""),
            "name": file_obj.get("name", ""),
            "reason": reason or "",
        })

    for file_obj in data.get("CANCELED", []) or []:
        reason = str(file_obj.get("cancel_reason") or "")
        if file_obj.get("stale_active"):
            add("Thiếu tín hiệu kết thúc", "warning", file_obj, reason)
        if "DONE trước đó quá nhanh" in reason:
            add("DONE quá nhanh", "danger", file_obj, reason)
        if file_obj.get("progress_source") == "unknown":
            add("Chưa rõ % hỏng", "warning", file_obj, "Thiếu dữ liệu để tính phần hỏng. Cần xem log hoặc xử lý thủ công.")
        if file_obj.get("reprint_needs_review") and not file_obj.get("stale_active"):
            add("Cần xác nhận in lại", "warning", file_obj, file_obj.get("reprint_label") or reason)

    for status_key in ("RUNNING", "DONE"):
        for file_obj in data.get(status_key, []) or []:
            if file_obj.get("reprint_needs_review"):
                add("Cần xác nhận in lại", "warning", file_obj, file_obj.get("reprint_label") or "File có tín hiệu in/cắt lại.")

    for file_obj in data.get("CANCELED", []) or []:
        if file_obj.get("hash") and file_obj.get("has_thumbnail") is False:
            add("Thiếu ảnh preview", "info", file_obj, missing_thumbnail_reason(file_obj))

    return items[:20]

def classify_deleted_job(machine, file_name, history_data):
    history = load_history(history_data)
    lower_name = str(file_name or "").lower()
    previous_statuses = [
        str(item.get("old_status") or item.get("status") or "").upper()
        for item in history
        if isinstance(item, dict)
    ]
    delete_events = [
        item for item in history
        if isinstance(item, dict)
        and str(item.get("status", "")).upper() == "DELETED"
    ]
    last_delete = delete_events[-1] if delete_events else {}
    explicit_type = str(last_delete.get("cancel_type") or "").strip()
    explicit_reason = str(last_delete.get("reason") or "").strip()
    explicit_progress = last_delete.get("progress_percent")
    if str(last_delete.get("event") or "").upper() == "ADMIN_DELETE":
        explicit_type = "admin_delete"

    if is_cnc_expected_stop(machine, file_name):
        return {
            "type": "cnc_expected_stop",
            "label": "CNC file mẫu dừng đúng điểm cắt",
            "is_production_error": False,
            "progress_percent": explicit_progress,
        }

    if explicit_type:
        labels = {
            "source_delete": "Xóa file xuất",
            "production_cancel": "Dừng/hủy khi đang chạy",
            "legacy_close": "Đóng tồn cũ V1",
            "admin_delete": "Quản trị xóa",
            "unknown_delete": "Đã xóa",
            "done_cleanup": "Xóa sau khi xong",
            "source_renamed_done": "Đã đổi tên/in xong",
        }
        return {
            "type": explicit_type,
            "label": explicit_reason or labels.get(explicit_type, "Đã xóa"),
            "is_production_error": explicit_type == "production_cancel",
            "progress_percent": explicit_progress,
        }

    if any(item.get("event") == "LEGACY_CLOSE_V1_STUCK" for item in history if isinstance(item, dict)):
        return {"type": "legacy_close", "label": "Đóng tồn cũ V1", "is_production_error": False, "progress_percent": None}

    if "DONE" in previous_statuses:
        return {"type": "done_cleanup", "label": "Xóa sau khi xong", "is_production_error": False, "progress_percent": explicit_progress}

    if "PRINTING" in previous_statuses or "CUTTING" in previous_statuses:
        return {"type": "production_cancel", "label": "Dừng/hủy khi đang chạy", "is_production_error": True, "progress_percent": None}

    source_exts = (".tif", ".tiff", ".jpg", ".jpeg")
    if lower_name.endswith(source_exts) or previous_statuses in (["EXPORTED"], ["EXPORT"]):
        return {"type": "source_delete", "label": "Xóa file xuất", "is_production_error": False, "progress_percent": None}

    return {"type": "unknown_delete", "label": "Đã xóa", "is_production_error": False, "progress_percent": None}

def read_tail_lines(path, max_lines=80):
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            return handle.readlines()[-max_lines:]
    except Exception as exc:
        return [f"Cannot read {path}: {exc}\n"]

def count_log_errors(lines):
    normal_markers = (
        "SERVER_ZALO disabled",
        "Auto_CRM disabled",
        "OpenClaw not required",
        "Runtime mode: v2",
    )
    markers = ("ERROR", "LOI", "WARN", "CANH BAO", "Mat", "nghen")
    count = 0
    for line in lines:
        lowered = line.lower()
        if any(marker.lower() in lowered for marker in normal_markers):
            continue
        if any(marker.lower() in lowered for marker in markers):
            count += 1
    return count

def read_version_history(log_path=SERVER_LOG_FILE, max_items=80):
    if not os.path.exists(log_path):
        return []
    history = []
    last_by_machine = {}
    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                time_match = re.match(r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]", line)
                if not time_match:
                    continue
                event_time = time_match.group(1)
                machine = ""
                version = ""
                if "ĐIỂM DANH" in line and "Bản " in line:
                    for candidate in MACHINES:
                        if candidate.lower() in line.lower():
                            machine = candidate
                            break
                    version = line.split("Bản ", 1)[1].strip() if machine else ""
                elif "KHỞI ĐỘNG" in line:
                    match = re.search(r"KHỞI ĐỘNG\s+([A-Za-z0-9_.-]+)", line)
                    if match:
                        machine = "Server"
                        version = match.group(1).strip()
                if not machine or not version:
                    continue
                if last_by_machine.get(machine) == version:
                    continue
                last_by_machine[machine] = version
                history.append({
                    "time": event_time,
                    "machine": machine,
                    "version": version,
                })
    except Exception as exc:
        return [{"time": now(), "machine": "error", "version": str(exc)}]
    return history[-max_items:][::-1]

def inspect_outbox_db(db_path):
    info = {
        "file": os.path.basename(db_path),
        "path": db_path,
        "exists": os.path.exists(db_path),
        "pending": 0,
        "sent": 0,
        "max_attempts": 0,
        "last_error": "",
        "ok": True,
        "error": "",
    }
    if not info["exists"]:
        info["ok"] = False
        info["error"] = "missing"
        return info
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM outbox_events WHERE status='pending'")
        info["pending"] = int(c.fetchone()[0])
        c.execute("SELECT COUNT(*) FROM outbox_events WHERE status='sent'")
        info["sent"] = int(c.fetchone()[0])
        c.execute("SELECT COALESCE(MAX(attempts), 0) FROM outbox_events WHERE status='pending'")
        info["max_attempts"] = int(c.fetchone()[0])
        c.execute("SELECT last_error FROM outbox_events WHERE status='pending' AND last_error IS NOT NULL ORDER BY updated_at DESC LIMIT 1")
        row = c.fetchone()
        info["last_error"] = row[0] if row else ""
        conn.close()
        info["ok"] = info["pending"] == 0
    except Exception as exc:
        info["ok"] = False
        info["error"] = str(exc)
    return info

def inspect_indecal_rename_audit(data_dir=DB_DIR, max_items=20):
    db_path = os.path.join(data_dir, "indecal_rename_audit.db")
    info = {
        "file": "indecal_rename_audit.db",
        "path": db_path,
        "exists": os.path.exists(db_path),
        "total": 0,
        "today": 0,
        "fail_today": 0,
        "recent": [],
        "ok": True,
        "error": "",
    }
    if not info["exists"]:
        return info
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM rename_audit")
        info["total"] = int(c.fetchone()[0])
        c.execute("SELECT COUNT(*) FROM rename_audit WHERE DATE(event_time)=?", (today,))
        info["today"] = int(c.fetchone()[0])
        c.execute(
            """
            SELECT COUNT(*) FROM rename_audit
            WHERE DATE(event_time)=? AND (action LIKE '%FAIL%' OR COALESCE(error, '') <> '')
            """,
            (today,),
        )
        info["fail_today"] = int(c.fetchone()[0])
        c.execute(
            """
            SELECT machine, action, prn_path, meta_path, target_prn_path, error, event_time
            FROM rename_audit
            ORDER BY id DESC
            LIMIT ?
            """,
            (max_items,),
        )
        info["recent"] = [dict(row) for row in c.fetchall()]
        conn.close()
    except Exception as exc:
        info["ok"] = False
        info["error"] = str(exc)
    return info

def inspect_machine_db(machine, data_dir=DB_DIR):
    db_path = os.path.join(data_dir, f"{machine}.db")
    info = {
        "machine": machine,
        "path": db_path,
        "exists": os.path.exists(db_path),
        "total": 0,
        "active": 0,
        "running": 0,
        "queued_today": 0,
        "unfinished_today": 0,
        "old_active": 0,
        "done_today": 0,
        "latest_update": "",
        "latest_machine_update": "",
        "latest_admin_update": "",
        "version": "",
        "last_ping": "",
        "hostname": "",
        "pid": "",
        "start_time": "",
        "instance_id": "",
        "online": False,
        "network_online": False,
        "online_label": "CHUA MO",
        "ok": True,
        "error": "",
    }
    if not info["exists"]:
        info["ok"] = False
        info["error"] = "missing"
        return info
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM files")
        info["total"] = int(c.fetchone()[0])
        c.execute(
            "SELECT COUNT(*) FROM files WHERE status IN ('PRINTING','CUTTING') AND DATE(updated_time)=?",
            (today,),
        )
        info["running"] = int(c.fetchone()[0])
        info["active"] = info["running"]
        c.execute(
            "SELECT COUNT(*) FROM files WHERE status IN ('EXPORTED','RIP') AND DATE(updated_time)=?",
            (today,),
        )
        info["queued_today"] = int(c.fetchone()[0])
        info["unfinished_today"] = info["running"] + info["queued_today"]
        c.execute(
            "SELECT COUNT(*) FROM files WHERE status IN ('EXPORTED','RIP','PRINTING','CUTTING') AND (updated_time IS NULL OR DATE(updated_time)<>?)",
            (today,),
        )
        info["old_active"] = int(c.fetchone()[0])
        c.execute("SELECT COUNT(*) FROM files WHERE status='DONE' AND DATE(updated_time)=?", (today,))
        info["done_today"] = int(c.fetchone()[0])
        c.execute("SELECT COALESCE(MAX(updated_time), '') FROM files")
        info["latest_update"] = c.fetchone()[0] or ""
        c.execute("SELECT updated_time, history FROM files ORDER BY updated_time DESC LIMIT 200")
        for updated_time, history_data in c.fetchall():
            history = load_history(history_data)
            last_event = str(history[-1].get("event") or "") if history and isinstance(history[-1], dict) else ""
            is_admin_event = last_event.upper().startswith("ADMIN_")
            if is_admin_event and not info["latest_admin_update"]:
                info["latest_admin_update"] = updated_time or ""
            elif not is_admin_event and not info["latest_machine_update"]:
                info["latest_machine_update"] = updated_time or ""
            if info["latest_admin_update"] and info["latest_machine_update"]:
                break
        try:
            app_info = dict(c.execute("SELECT key, value FROM app_info").fetchall())
            info["version"] = app_info.get("version", "")
            info["last_ping"] = app_info.get("last_ping", "")
            info["hostname"] = app_info.get("hostname", "")
            info["pid"] = app_info.get("pid", "")
            info["start_time"] = app_info.get("start_time", "")
            info["instance_id"] = app_info.get("instance_id", "")
            if info["last_ping"]:
                last_ping_dt = datetime.strptime(info["last_ping"], "%Y-%m-%d %H:%M:%S")
                age_seconds = (datetime.now() - last_ping_dt).total_seconds()
                info["online"] = age_seconds <= 180
                info["online_label"] = "DANG MO" if info["online"] else "TAT/CHUA PING"
                info["ping_age_seconds"] = int(age_seconds)
        except Exception:
            pass
        conn.close()
        probe_host = info["hostname"] or machine
        if not info["online"] and not info["last_ping"] and ping_host(probe_host):
            info["network_online"] = True
            info["hostname"] = probe_host
            if not info["last_ping"]:
                info["online_label"] = "MAY BAT/CHUA CO V2"
            else:
                info["online_label"] = "MAY BAT/MAT PING V2"
    except Exception as exc:
        info["ok"] = False
        info["error"] = str(exc)
    return info

def ping_host(hostname):
    if not hostname:
        return False
    try:
        result = subprocess.run(
            ["ping", "-n", "1", "-w", "500", hostname],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=2,
            shell=False,
        )
        return result.returncode == 0
    except Exception:
        return False

def get_v2_status_snapshot(data_dir=DB_DIR):
    outboxes = []
    try:
        outboxes = [
            inspect_outbox_db(os.path.join(data_dir, name))
            for name in sorted(os.listdir(data_dir))
            if name.startswith("agent_outbox_") and name.endswith(".db")
        ] if os.path.isdir(data_dir) else []
    except Exception:
        outboxes = []

    logs = []
    for name, path in [
        ("server", SERVER_LOG_FILE),
        ("dashboard", LOG_FILE),
        ("machine", MACHINE_LOG_FILE),
        ("qcvl_bridge", QCVL_BRIDGE_LOG_FILE),
    ]:
        lines = read_tail_lines(path, 60)
        logs.append({
            "name": name,
            "path": path,
            "exists": os.path.exists(path),
            "error_count": count_log_errors(lines),
            "tail": [line.rstrip("\n") for line in lines[-12:]],
        })

    version_path = os.path.join(data_dir, "versions_tracking.json")
    versions = {}
    try:
        if os.path.exists(version_path):
            with open(version_path, "r", encoding="utf-8") as handle:
                versions = json.load(handle)
    except Exception as exc:
        versions = {"error": str(exc)}

    rename_audit = inspect_indecal_rename_audit(data_dir)
    machines = [inspect_machine_db(machine, data_dir) for machine in MACHINES]
    for machine in machines:
        version = versions.get(machine["machine"]) if isinstance(versions, dict) else ""
        if version and not machine.get("version"):
            machine["version"] = version
    warnings = []
    if not os.path.isdir(data_dir):
        warnings.append(f"Data folder missing: {data_dir}")
    for outbox in outboxes:
        if outbox.get("pending", 0) > 0:
            warnings.append(f"Outbox đang chờ gửi: {outbox['file']} chờ={outbox['pending']} pending={outbox['pending']}")
        if outbox.get("error"):
            warnings.append(f"Outbox lỗi: {outbox['file']} lỗi={outbox['error']}")
    for machine in machines:
        if not machine.get("ok"):
            warnings.append(f"{machine['machine']} lỗi database: {machine['error']}")
        if machine.get("online") and not str(machine.get("version", "")).startswith("V2."):
            warnings.append(f"{machine['machine']} đang mở nhưng chưa lên V2")

    return {
        "generated_at": now(),
        "data_dir": data_dir,
        "overall": "OK" if not warnings else "WARN",
        "warnings": warnings,
        "versions": versions,
        "version_history": read_version_history(),
        "machines": machines,
        "outboxes": outboxes,
        "rename_audit": rename_audit,
        "logs": logs,
    }

for machine in MACHINES:
    db_path = os.path.join(DB_DIR, f"{machine}.db")
    if os.path.exists(db_path):
        try:
            conn = sqlite3.connect(db_path, timeout=5)
            cols = [c[1] for c in conn.execute("PRAGMA table_info(files)").fetchall()]
            if "run_count" not in cols: conn.execute("ALTER TABLE files ADD COLUMN run_count INTEGER DEFAULT 1")
            if "history" not in cols: conn.execute("ALTER TABLE files ADD COLUMN history TEXT DEFAULT '[]'")
            if "zalo_sent" not in cols: conn.execute("ALTER TABLE files ADD COLUMN zalo_sent INTEGER DEFAULT 0")
            if "machine_meta_json" not in cols: conn.execute("ALTER TABLE files ADD COLUMN machine_meta_json TEXT DEFAULT '{}'")
            conn.commit(); conn.close()
        except: pass

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Xưởng V2</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #121212; color: #ffffff; margin: 0; padding: 15px; height: 100vh; display: flex; flex-direction: column; overflow: hidden; box-sizing: border-box; }
        
        .top-navbar { display: flex; justify-content: center; gap: 15px; margin-bottom: 15px; flex-shrink: 0; border-bottom: 2px solid #333; padding-bottom: 10px; position: relative;}
        .tab-btn { background: none; border: none; color: #aaa; font-size: 16px; font-weight: bold; cursor: pointer; text-transform: uppercase; padding: 5px 15px; transition: 0.3s; letter-spacing: 1px;}
        .tab-btn:hover { color: #fff; }
        .tab-btn.active { color: #00ffcc; border-bottom: 3px solid #00ffcc; }
        
        .header-controls { position: absolute; right: 0; top: 0; display: flex; gap: 10px; align-items: center;}
        .login-btn { background: #333; color: #00ffcc; border: 1px solid #00ffcc; padding: 6px 12px; border-radius: 5px; cursor: pointer; font-weight: bold; font-size: 13px;}
        .login-btn:hover { background: #00ffcc; color: #000; }
        .btn-logout { border-color: #ff3333; color: #ff3333; }
        .btn-logout:hover { background: #ff3333; color: #fff; }
        #socket-status { font-size: 11px; padding: 4px 8px; border-radius: 10px; font-weight: bold; }
        .status-on { background: #00fa9a; color: #000; }
        .status-off { background: #ff3333; color: #fff; }

        .view-section { display: none; flex-direction: column; flex-grow: 1; overflow: hidden; }
        .view-section.active { display: flex; }

        .controls { display: flex; justify-content: center; gap: 10px; margin-bottom: 10px; align-items: center; background: #1e1e1e; padding: 10px; border-radius: 10px; flex-shrink: 0; flex-wrap: wrap;}
        input[type="date"], select { background: #333; color: white; border: 1px solid #555; padding: 6px 8px; border-radius: 5px; font-size: 14px; outline: none;}
        .summary-panel { background: #1e1e1e; border: 1px solid #00ffcc; border-radius: 10px; padding: 8px; margin-bottom: 10px; text-align: center; font-size: 14px; flex-shrink: 0;}
        .summary-title { font-weight: bold; color: #ff9900; margin-bottom: 3px; text-transform: uppercase; font-size: 12px;}
        
        .board { display: flex; gap: 10px; justify-content: flex-start; flex-grow: 1; overflow-x: auto; overflow-y: hidden; padding-bottom: 5px; }
        .column { background-color: #1e1e1e; border-radius: 10px; flex: 1; min-width: 200px; padding: 8px; padding-bottom: 0; border-top: 5px solid; display: flex; flex-direction: column; overflow: hidden; }
        .col-export { border-color: #ff9900; } .col-rip { border-color: #00ccff; } .col-run { border-color: #ff3366; } .col-done { border-color: #33cc33; } .col-cancel { border-color: #ff3333; opacity: 0.9; } .col-removed { border-color: #9aa4b2; opacity: 0.86; }
        h2 { text-align: center; font-size: 13px; margin-top: 0; padding-bottom: 8px; border-bottom: 1px solid #333; position: relative; flex-shrink: 0;}
        .count-badge { background: #fff; color: #000; padding: 2px 6px; border-radius: 10px; font-size: 11px; position: absolute; right: 0; top: 0;}
        .list-container { flex-grow: 1; overflow-y: auto; padding-right: 5px; margin-bottom: 10px; }
        .list-container::-webkit-scrollbar { width: 5px; } .list-container::-webkit-scrollbar-track { background: #1a1a1a; border-radius: 10px;} .list-container::-webkit-scrollbar-thumb { background: #555; border-radius: 10px; }
        .card { background-color: #2a2a2a; border-radius: 8px; padding: 8px; margin-bottom: 8px; border-left: 4px solid #555; transition: transform 0.2s;}
        .card:hover { transform: scale(1.02); background-color: #3a3a3a; cursor: pointer;}
        .card-title { font-weight: bold; font-size: 12px; margin-bottom: 4px; word-break: break-all;}
        .card-time { font-size: 11px; color: #aaaaaa; }
        .card-thumb { width: 100%; height: 80px; object-fit: cover; border-radius: 5px; margin: 4px 0; border: 1px solid #444; background: #111;}
        .badge { display: inline-block; padding: 2px 5px; border-radius: 10px; font-size: 10px; font-weight: bold; margin-bottom: 4px; color: #000;}
        .badge-InBat { background-color: #22c55e; } .badge-InDecal { background-color: #3b82f6; } .badge-CNC { background-color: #ff6347; color: white;}
        .badge-run { background-color: #ff3333; color: white; float: right; padding: 2px 5px; border-radius: 5px; font-size: 10px;}

        /* ERP STYLES */
        .erp-btn { background: #1e1e1e; border: 1px solid #444; color: white; padding: 8px 20px; border-radius: 8px; cursor: pointer; font-weight: bold; transition: 0.2s;}
        .erp-btn:hover { background: #333; }
        .erp-btn.active { background: #00ffcc; color: black; border-color: #00ffcc;}
        .btn-excel { background: #28a745 !important; border-color: #28a745 !important; color: white !important;}
        .btn-excel:hover { background: #218838 !important; }
        
        .erp-heading { display: flex; align-items: center; justify-content: flex-end; gap: 12px; margin: 0 0 10px 0; flex-shrink: 0; }
        .erp-summary-row { display: flex; gap: 15px; margin-bottom: 15px; flex-shrink: 0;}
        .erp-sum-card { flex: 1; background: #1e1e1e; border-radius: 10px; padding: 15px; text-align: center; border: 1px solid #333;}
        .erp-sum-card.machine-InBat { border-color: rgba(34, 197, 94, 0.75); }
        .erp-sum-card.machine-InDecal { border-color: rgba(59, 130, 246, 0.75); }
        .erp-sum-card.machine-CNC { border-color: rgba(255, 99, 71, 0.75); }
        .erp-sum-val { font-size: 24px; font-weight: bold; color: #00ffcc; margin-top: 5px;}
        .val-err { color: #ff3333; }
        .val-m2-erp { color: #ffd700; }

        .erp-grid { display: grid; grid-template-columns: 1fr; grid-template-rows: auto; gap: 15px; flex-grow: 1; overflow-y: auto;}
        .chart-box { background: #1e1e1e; border-radius: 12px; padding: 15px; display: flex; flex-direction: column; border: 1px solid #333;}
        .chart-box h3 { text-align: center; margin-top: 0; color: #ff9900; font-size: 14px; text-transform: uppercase; border-bottom: 1px dashed #444; padding-bottom: 8px;}
        .chart-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin: 0 0 8px 0; border-bottom: 1px dashed #444; padding-bottom: 8px; }
        .chart-head h3 { margin: 0; padding: 0; border: 0; text-align: left; }
        .chart-toggle { display: inline-flex; gap: 2px; padding: 2px; background: #11161f; border: 1px solid #2b3442; border-radius: 8px; flex-shrink: 0; }
        .chart-toggle button { border: 0; background: transparent; color: #9aa4b2; border-radius: 6px; padding: 5px 10px; font-size: 12px; font-weight: 700; cursor: pointer; }
        .chart-toggle button.active { background: #3b82f6; color: #fff; }
        .canvas-container { flex-grow: 1; position: relative; min-height: 200px;}
        .chart-box.full-width { grid-column: span 1; }
        .status-shell { display: flex; flex-direction: column; gap: 12px; overflow-y: auto; overflow-x: hidden; padding-bottom: 10px; }
        .status-card { background: #1e1e1e; border: 1px solid #333; border-radius: 8px; padding: 12px; min-height: 80px; width: 100%; box-sizing: border-box; flex: 0 0 auto; }
        .status-card h3 { margin: 0 0 8px 0; font-size: 13px; color: #00ffcc; text-transform: uppercase; border-bottom: 1px solid #333; padding-bottom: 6px; }
        .status-card.full { width: 100%; }
        .status-pill { display: inline-block; padding: 3px 8px; border-radius: 999px; font-size: 11px; font-weight: bold; margin-left: 8px; }
        .pill-ok { background: #00fa9a; color: #000; }
        .pill-warn { background: #ff3333; color: #fff; }
        .pill-idle { background: #555; color: #fff; }
        .machine-name { font-weight: bold; color: #fff; font-size: 13px; }
        .version-ok { color: #00fa9a; font-weight: bold; }
        .version-old { color: #ff9900; font-weight: bold; }
        .muted { color: #999; font-size: 11px; }
        .machine-cards { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; align-items: start; }
        .machine-card { background: #151515; border: 1px solid #333; border-radius: 8px; padding: 0; min-height: 0; overflow: hidden; }
        .machine-card.online { border-color: #00fa9a; }
        .machine-card.offline { border-color: #555; }
        .machine-card summary { cursor: pointer; list-style: none; padding: 10px; }
        .machine-card summary::-webkit-details-marker { display: none; }
        .machine-card .top { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 0; }
        .machine-card .line { display: flex; justify-content: space-between; gap: 8px; border-top: 1px solid #282828; padding-top: 6px; margin-top: 6px; font-size: 12px; }
        .machine-card .label { color: #aaa; }
        .machine-card .value { color: #fff; text-align: right; word-break: break-word; }
        .machine-main { display: grid; grid-template-columns: 1fr auto; gap: 8px; align-items: center; margin-top: 8px; }
        .machine-kpi { display: flex; gap: 8px; flex-wrap: wrap; color: #d6dce6; font-size: 11px; }
        .machine-kpi strong { color: #fff; font-size: 13px; }
        .machine-more { padding: 0 10px 10px; border-top: 1px solid #263044; }
        .machine-card summary::after { content: 'Chi tiết'; color: #93c5fd; display: block; margin-top: 8px; font-size: 11px; font-weight: 800; }
        .machine-card[open] summary::after { content: 'Thu gọn'; color: #fbbf24; }
        .status-subgrid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 10px; flex: 0 0 auto; }
        .status-table { width: 100%; border-collapse: collapse; font-size: 12px; table-layout: fixed; }
        .status-table th, .status-table td { border-bottom: 1px solid #333; padding: 6px; text-align: left; vertical-align: top; }
        .status-table th { color: #ff9900; font-size: 11px; text-transform: uppercase; }
        .version-status-table { table-layout: auto; }
        .version-status-table th, .version-status-table td { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .version-status-table th:nth-child(1), .version-status-table td:nth-child(1) { width: 72px; }
        .version-status-table th:nth-child(2), .version-status-table td:nth-child(2) { width: 34%; min-width: 190px; }
        .version-status-table th:nth-child(3), .version-status-table td:nth-child(3) { width: 24%; max-width: 210px; }
        .version-status-table th:nth-child(4), .version-status-table td:nth-child(4) { width: 26%; min-width: 160px; }
        .version-status-table th:nth-child(5), .version-status-table td:nth-child(5) { width: 88px; }
        .version-status-table tbody tr { cursor: pointer; }
        .version-status-table tbody tr:hover { background: rgba(96,165,250,.12); }
        .version-status-table tbody tr.active { background: rgba(96,165,250,.2); outline: 1px solid rgba(96,165,250,.45); }
        .version-inline-history td { background: rgba(96,165,250,.08); padding: 8px; }
        .version-inline-history .system-note-row { margin-bottom: 8px; }
        .version-history-table { table-layout: auto; }
        .version-history-table th, .version-history-table td { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .version-history-table th:nth-child(1), .version-history-table td:nth-child(1) { width: 190px; }
        .version-history-table th:nth-child(2), .version-history-table td:nth-child(2) { width: 120px; }
        .log-tail { background: #111; border: 1px solid #333; border-radius: 6px; padding: 8px; font-family: Consolas, monospace; font-size: 11px; white-space: pre-wrap; max-height: 180px; overflow-y: auto; color: #ddd; }
        .status-overview { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; }
        .overview-card { background: #151515; border: 1px solid #333; border-radius: 8px; padding: 12px; min-height: 78px; }
        .overview-label { color: #aaa; font-size: 11px; text-transform: uppercase; margin-bottom: 8px; }
        .overview-value { color: #fff; font-size: 24px; font-weight: 800; line-height: 1; }
        .overview-note { color: #999; font-size: 11px; margin-top: 8px; }
        .status-message { border-left: 4px solid #00fa9a; background: #121c18; padding: 10px 12px; border-radius: 6px; color: #c7ffe7; font-size: 13px; }
        .status-message.warn { border-left-color: #ff3333; background: #231414; color: #ffb6b6; }
        .detail-card { background: #1e1e1e; border: 1px solid #333; border-radius: 8px; overflow: hidden; flex: 0 0 auto; }
        .detail-card summary { cursor: pointer; list-style: none; padding: 12px; color: #00ffcc; font-weight: 800; text-transform: uppercase; border-bottom: 1px solid transparent; }
        .detail-card summary::-webkit-details-marker { display: none; }
        .detail-card summary::after { content: '+'; float: right; color: #ff9900; font-size: 16px; }
        .detail-card[open] summary { border-bottom-color: #333; }
        .detail-card[open] summary::after { content: '-'; }
        .detail-body { padding: 12px; }

        /* MODAL */
        .modal { display: none; position: fixed; z-index: 1000; left: 0; top: 0; width: 100%; height: 100%; background-color: rgba(0,0,0,0.85); overflow-y: auto; padding: 20px 0; box-sizing: border-box;}
        .modal-content { background-color: #1e1e1e; margin: 0 auto; padding: 15px; border: 1px solid #444; border-radius: 10px; width: 340px; max-width: 92%; position: relative; margin-bottom: 30px;}
        .close-x { position: absolute; right: 5px; top: 0px; font-size: 28px; color: #aaa; cursor: pointer; padding: 10px; line-height: 1; z-index: 10;}
        .close-x:hover { color: white; }
        .pin-input { width: 100%; box-sizing: border-box; padding: 10px; margin: 10px 0; background: #111; color: #00ffcc; border: 1px solid #555; border-radius: 8px; font-size: 18px; text-align: center; letter-spacing: 5px; font-weight: bold; outline: none;}
        .detail-header { border-bottom: 1px solid #333; padding-bottom: 8px; margin-bottom: 10px; padding-right: 30px; }
        .detail-name { font-size: 14px; color: #00ffcc; font-weight: bold; word-break: break-all; margin-bottom: 3px;}
        .detail-row { display: flex; justify-content: space-between; margin-bottom: 6px; font-size: 12px; border-bottom: 1px dashed #2a2a2a; padding-bottom: 4px;}
        .detail-label { color: #888; } .detail-value { font-weight: bold; color: #fff;} .val-m2 { color: #00fa9a; }
        .timeline { margin-top: 8px; border-left: 2px solid #444; padding-left: 12px; margin-left: 5px; }
        .tl-item { margin-bottom: 12px; position: relative; }
        .tl-item::before { content: ''; position: absolute; left: -18px; top: 3px; width: 8px; height: 8px; border-radius: 50%; background: #555; border: 2px solid #1e1e1e; }
        .tl-item.tl-export::before { background: var(--stage-export); } .tl-item.tl-rip::before { background: var(--stage-rip); } .tl-item.tl-run::before { background: var(--stage-run); } .tl-item.tl-done::before { background: var(--stage-done); } .tl-item.tl-cancel::before { background: var(--stage-cancel); }
        .tl-time { font-size: 10px; color: #aaa; margin-bottom: 1px;} .tl-desc { font-size: 12px; font-weight: bold; color: #fff;}
        .tl-duration { font-size: 10px; color: #ff9900; margin-top: 3px; display: inline-block; background: rgba(255,153,0,0.1); padding: 2px 6px; border-radius: 4px; border: 1px solid #ff9900;}
        .admin-section { display: none; margin-top: 15px; padding-top: 10px; border-top: 2px solid #444; }
        .admin-title { font-size: 11px; color: #ff3333; font-weight: bold; text-transform: uppercase; margin-bottom: 8px; text-align: center;}
        .action-btn { display: block; width: 100%; padding: 8px; margin-bottom: 6px; border: none; border-radius: 5px; font-size: 12px; font-weight: bold; cursor: pointer;}
        .btn-submit { background-color: #00ffcc; color: black; margin-top: 10px;} .btn-done { background-color: #33cc33; color: black;} .btn-cancel { background-color: #ff3333; color: white;} .btn-reset { background-color: #ff9900; color: black;}

        /* QUICK FILTER */
        .quick-select { background: #00ffcc !important; color: #000 !important; font-weight: bold; padding: 6px 12px !important; border-radius: 5px; cursor: pointer; border: 1px solid #00ffcc; outline: none; transition: 0.2s;}
        .quick-select:hover { background: #00e6b8 !important; }

        /* RESPONSIVE MOBILE */
        @media screen and (max-width: 800px) and (orientation: portrait) {
            body { overflow-y: auto !important; height: auto !important; padding: 10px; display: block; }
            .top-navbar { flex-wrap: wrap; margin-bottom: 10px;}
            .header-controls { position: relative; justify-content: center; margin-top: 10px; width: 100%;}
            .board { flex-direction: column; overflow: visible; height: auto; gap: 15px;}
            .column { min-height: unset; height: max-content; margin-bottom: 0; flex: none; padding-bottom: 8px; }
            .list-container { max-height: 400px; overflow-y: auto; margin-bottom: 0;}
            .erp-grid { grid-template-columns: 1fr; grid-template-rows: auto; }
            .chart-box.full-width { grid-column: span 1; }
            .erp-summary-row { flex-wrap: wrap; }
            .erp-sum-card { min-width: 45%; }
            .status-shell { grid-template-columns: 1fr; }
            .status-card.full { grid-column: span 1; }
            .machine-cards { grid-template-columns: 1fr; }
            .status-subgrid { grid-template-columns: 1fr; }
            .status-overview { grid-template-columns: 1fr 1fr; }
        }

        @media screen and (max-height: 600px) and (orientation: landscape) {
            body { padding: 4px; overflow: hidden; height: 100vh;}
            .top-navbar { margin-bottom: 4px; padding-bottom: 4px; }
            .header-controls { position: static; display: flex; width: 100%; justify-content: center; margin-top: 5px;}
            .erp-grid { grid-template-columns: 1fr 1fr 1fr; grid-template-rows: 1fr; }
            .chart-box.full-width { grid-column: span 1; }
            .controls, .summary-panel { margin-bottom: 4px; padding: 4px;}
            .column { min-width: 0; padding: 4px; }
            .card { padding: 4px; margin-bottom: 4px; }
            .card-title { font-size: 9px; line-height: 1.1;}
            .card-thumb { height: 40px; margin: 2px 0;}
            h2 { font-size: 10px; }
            .modal { padding: 10px 0; }
            .modal-content { margin: 0 auto; padding: 8px; width: 320px; }
            .detail-name { font-size: 11px; margin-bottom: 2px;}
            .detail-row { font-size: 9px; margin-bottom: 2px; padding-bottom: 2px;}
            .admin-section { margin-top: 5px; padding-top: 5px; }
            .action-btn { padding: 4px; font-size: 9px; margin-bottom: 3px;}
            .tl-item { margin-bottom: 4px; }
            .tl-desc { font-size: 9px; }
            .tl-time { font-size: 8px; }
            .tl-duration { font-size: 8px; padding: 1px 4px;}
            .erp-summary-row { display: none; } 
        }

        /* V2 modern single-page overrides */
        :root {
            --bg:#0f1115; --panel:#171a21; --panel2:#202634; --line:#303847; --text:#f3f6fb; --muted:#9aa4b2;
            --machine-inbat:#22c55e; --machine-indecal:#3b82f6; --machine-cnc:#ff6347;
            --stage-export:#f5b84b; --stage-rip:#25c2e3; --stage-run:#6aa7ff; --stage-done:#20d489; --stage-cancel:#ef5b68; --stage-removed:#9aa4b2;
            --green:var(--stage-done); --cyan:var(--stage-rip); --amber:var(--stage-export); --red:var(--stage-cancel); --blue:var(--stage-run);
        }
        * { box-sizing: border-box; }
        body { background: var(--bg); color: var(--text); height: 100vh; min-height: 100vh; overflow: hidden; padding: 16px; display: flex; flex-direction: column; letter-spacing: 0; }
        .top-navbar { justify-content: space-between; align-items: center; gap: 12px; margin-bottom: 12px; border: 1px solid var(--line); background: var(--panel); border-radius: 8px; padding: 12px; }
        .top-navbar::before { content: "Xưởng V2"; color: var(--text); font-size: 22px; font-weight: 900; white-space: nowrap; }
        .tab-btn { display: none; }
        .header-controls { position: static; margin-left: auto; }
        .login-btn, .erp-btn, .btn-excel { border-radius: 8px; border: 1px solid var(--line); background: var(--panel2) !important; color: var(--text) !important; min-height: 34px; }
        .login-btn:hover, .erp-btn:hover { border-color: #51607a; background: #273040 !important; color: var(--text) !important; }
        #socket-status, .status-pill { border-radius: 999px; padding: 6px 10px; border: 1px solid var(--line); font-weight: 800; }
        .status-on, .pill-ok { background: rgba(32,212,137,.16); color: #9ff3cf; border-color: rgba(32,212,137,.45); }
        .status-off, .pill-warn { background: rgba(239,91,104,.16); color: #ffb6be; border-color: rgba(239,91,104,.5); }
        .pill-idle { background: #2a303d; color: #d6dce6; }
        .view-section { display: flex !important; overflow: visible; flex-grow: 0; margin-bottom: 14px; }
        .view-section::before { display: block; margin: 0 0 8px 2px; color: var(--muted); font-size: 12px; font-weight: 900; text-transform: uppercase; }
        #view-board::before { display: none; content: ""; }
        #view-erp::before { content: "Thống kê"; }
        #view-v2::before { display: none; content: ""; }
        #view-v2 { order: 1; }
        #view-board { order: 2; }
        #view-erp { order: 3; }
        .top-navbar { order: 0; }
        .controls, .summary-panel, .status-card, .erp-sum-card, .chart-box, .detail-card { background: var(--panel); border: 1px solid var(--line); border-radius: 8px; }
        .controls { justify-content: flex-start; padding: 10px; }
        input[type="date"], select { background: #11161f; border-color: var(--line); border-radius: 8px; min-height: 34px; }
        input[type="date"] { color-scheme: dark; }
        input[type="date"]::-webkit-calendar-picker-indicator { background: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='16' height='16' viewBox='0 0 24 24' fill='none' stroke='%23f3f6fb' stroke-width='2.4' stroke-linecap='round' stroke-linejoin='round'%3E%3Crect x='3' y='4' width='18' height='18' rx='2'/%3E%3Cpath d='M16 2v4M8 2v4M3 10h18'/%3E%3C/svg%3E") center / 14px 14px no-repeat; opacity: .95; cursor: pointer; }
        .summary-panel { padding: 10px; text-align: left; }
        .summary-title { color: var(--muted); }
        #view-v2 { display: flex !important; margin-bottom: 8px; }
        #view-board { margin-top: 0; }
        .board { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 8px; overflow-x: auto; min-height: 410px; }
        .column { background: #11161f; border: 1px solid var(--line); border-radius: 8px; min-width: 155px; height: 410px; padding: 0; border-top: 0; }
        .column.is-empty { display: none; }
        .board:has(.card) .column:not(:has(.card)) { display: none; }
        .column h2 { margin: 0; min-height: 38px; display: flex; align-items: center; justify-content: space-between; padding: 8px; border-top: 4px solid; border-bottom: 1px solid var(--line); font-size: 11px; line-height: 1.2; }
        .col-export h2 { border-top-color: var(--stage-export); } .col-rip h2 { border-top-color: var(--stage-rip); } .col-run h2 { border-top-color: var(--stage-run); } .col-done h2 { border-top-color: var(--stage-done); } .col-cancel h2 { border-top-color: var(--stage-cancel); } .col-removed h2 { border-top-color: var(--stage-removed); }
        .count-badge { position: static; min-width: 24px; border-radius: 999px; font-weight: 900; }
        .list-container { padding: 6px; }
        .card { background: var(--panel2); border: 1px solid #2b3444; border-left: 5px solid #69758a; border-radius: 8px; transform: none !important; padding: 5px 6px 5px 8px; margin-bottom: 5px; position: relative; min-height: 34px; }
        .card[data-machine="InBat"], .badge-InBat, .attention-item[data-machine="InBat"] { border-left-color: var(--machine-inbat); }
        .card[data-machine="InDecal"], .badge-InDecal, .attention-item[data-machine="InDecal"] { border-left-color: var(--machine-indecal); }
        .card[data-machine="CNC"], .badge-CNC, .attention-item[data-machine="CNC"] { border-left-color: var(--machine-cnc); }
        .card:hover, .card:focus-within { background: #252d3a; border-color: #51607a; z-index: 5; }
        .card-main { display: grid; grid-template-columns: 1fr auto auto; gap: 6px; align-items: center; }
        .card-title { font-size: 11px; line-height: 1.15; margin: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; min-width: 0; }
        .card-time { font-size: 10px; color: var(--muted); white-space: nowrap; }
        .stage-chip { font-size: 9px; line-height: 1; color: #d6dce6; background: #11161f; border: 1px solid var(--line); border-radius: 999px; padding: 3px 5px; white-space: nowrap; }
        .card-progress { margin-top: 4px; font-size: 10px; color: #fbbf24; line-height: 1.25; }
        .card-progress strong { color: #fde68a; }
        .card-extra { display: none; }
        .card-thumb { display: none; }
        .card-preview { position: absolute; display: none; z-index: 2500; width: 320px; max-width: calc(100vw - 24px); max-height: calc(100vh - 16px); background: #0b0d11; border: 1px solid var(--line); border-radius: 8px; box-shadow: 0 16px 44px rgba(0,0,0,.55); padding: 8px; pointer-events: none; overflow: hidden; }
        .card-preview.pinned { pointer-events: auto; overflow-y: auto; overscroll-behavior: contain; }
        .card-preview img { width: 100%; max-height: 240px; object-fit: contain; border-radius: 6px; background: #11161f; display: block; }
        .card-preview-empty { display: none; min-height: 120px; align-items: center; justify-content: center; text-align: center; color: var(--muted); background: #11161f; border: 1px dashed #334155; border-radius: 6px; font-size: 12px; }
        .card-preview-details { display: none; margin-top: 8px; border-top: 1px solid #1f2937; padding-top: 8px; }
        .card-preview.pinned .card-preview-details { display: block; }
        .preview-name { font-size: 12px; line-height: 1.35; color: var(--text); word-break: break-word; font-weight: 700; }
        .preview-status { margin-top: 4px; font-size: 11px; color: var(--muted); }
        .preview-timeline { margin-top: 8px; display: grid; gap: 5px; }
        .preview-row { display: grid; grid-template-columns: 58px 1fr; gap: 8px; font-size: 11px; color: var(--muted); border-left: 2px solid #334155; padding-left: 7px; }
        .preview-row strong { color: var(--text); font-weight: 700; }
        .preview-actions { display: none; grid-template-columns: repeat(3, 32px); justify-content: end; gap: 5px; margin-top: 8px; padding-top: 7px; border-top: 1px solid var(--line); }
        .card-preview.pinned .preview-actions.has-admin { display: grid; }
        .preview-action-btn { width: 32px; height: 26px; border: 0; border-radius: 6px; font-size: 14px; font-weight: 900; cursor: pointer; color: #0b0d11; line-height: 1; }
        .preview-action-btn:hover { filter: brightness(1.12); }
        .preview-done { background: var(--stage-done); }
        .preview-cancel { background: var(--stage-cancel); color: #fff; }
        .preview-reset { background: var(--stage-export); }
        .list-more-note { width: 100%; padding: 8px; color: var(--muted); font-size: 11px; text-align: center; border: 1px dashed var(--line); border-radius: 6px; background: rgba(148,163,184,.06); cursor: pointer; }
        .list-more-note:hover { color: var(--text); border-color: #60a5fa; background: rgba(96,165,250,.12); }
        .badge, .badge-run { border-radius: 999px; }
        .badge { margin-bottom: 0; }
        .badge-InBat { background: var(--machine-inbat); color: #111; }
        .badge-InDecal { background: var(--machine-indecal); color: #fff; }
        .badge-CNC { background: var(--machine-cnc); color: #fff; }
        .badge-run { float: none; display: inline-block; margin-left: 4px; }
        .summary-panel { display: flex; gap: 10px; align-items: center; }
        .summary-title { margin: 0; white-space: nowrap; }
        #m2-summary { font-size: 12px; }
        .attention-panel { background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 0; display: flex; flex-direction: column; flex: 1; min-height: 0; margin-bottom: 8px; overflow: hidden; }
        .attention-panel.has-items { display: block; }
        .attention-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; color: var(--text); font-size: 12px; font-weight: 900; text-transform: uppercase; padding: 10px; cursor: pointer; list-style: none; }
        .attention-head::-webkit-details-marker { display: none; }
        .attention-head::after { content: "Mở"; color: var(--muted); font-size: 10px; border: 1px solid var(--line); border-radius: 999px; padding: 3px 8px; }
        .attention-panel[open] .attention-head::after { content: "Ẩn"; }
        .attention-count { color: #fbbf24; font-size: 11px; }
        .attention-list { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); align-content: start; gap: 8px; padding: 0 10px 10px; flex: 1; min-height: 0; overflow-y: auto; }
        .attention-item { background: #11161f; border: 1px solid #334155; border-left: 4px solid var(--stage-export); border-radius: 8px; padding: 8px; min-height: 68px; }
        .attention-item:hover { background: #1b2330; border-color: #51607a; cursor: pointer; }
        .attention-item.danger { border-left-color: var(--red); }
        .attention-item.info { border-left-color: var(--cyan); }
        .attention-item[data-machine="InBat"] { border-left-color: var(--machine-inbat); }
        .attention-item[data-machine="InDecal"] { border-left-color: var(--machine-indecal); }
        .attention-item[data-machine="CNC"] { border-left-color: var(--machine-cnc); }
        .attention-title { font-size: 12px; font-weight: 900; color: var(--text); margin-bottom: 4px; }
        .attention-meta { font-size: 11px; color: #93c5fd; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .attention-reason { font-size: 10px; color: var(--muted); margin-top: 4px; line-height: 1.3; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
        #view-v2 .controls, #v2-status-body > .status-overview, #v2-status-body > .status-card.full:not(.machine-status-card), #view-v2 .ops-advanced { display: none; }
        .status-shell { display: block; padding: 0; }
        .machine-status-card { padding: 8px; }
        .machine-status-card h3 { display: none; }
        .status-overview { grid-template-columns: repeat(4, minmax(0, 1fr)); }
        .overview-card, .machine-card { background: #11161f; border: 1px solid var(--line); border-radius: 8px; }
        .machine-cards { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); align-items: start; gap: 8px; }
        .machine-card { min-height: 64px; }
        .machine-card summary { padding: 8px; }
        .machine-card summary::after { display: none; }
        .machine-card .top { margin-bottom: 6px; }
        .machine-card .machine-main { margin-top: 0; }
        .machine-card .machine-more { display: none; }
        .ops-advanced { margin-top: 2px; }
        .ops-advanced-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
        .ops-advanced-grid .detail-card { background: #11161f; min-height: 0; }
        .erp-grid { grid-template-columns: 1fr; grid-template-rows: auto; overflow: visible; }
        .canvas-container { min-height: 220px; height: 220px; }
        .log-tail { background: #0b0d11; border-color: var(--line); border-radius: 8px; }
        .modal-content { background: var(--panel); border-color: var(--line); border-radius: 8px; }
        .compact-shell { display: grid; grid-template-columns: 310px minmax(0, 1fr); gap: 12px; min-height: 0; flex: 1; overflow: hidden; }
        .compact-sidebar, .compact-main { min-width: 0; }
        .compact-sidebar { display: flex; flex-direction: column; gap: 10px; max-height: calc(100vh - 96px); overflow-y: auto; padding-right: 2px; }
        .compact-main { display: flex; flex-direction: column; gap: 10px; min-height: 0; }
        .compact-filters { margin: 0; padding: 0; background: transparent; border: 0; border-radius: 0; }
        .icon-btn { width: 36px; height: 34px; display: inline-grid; place-items: center; border-radius: 8px; border: 1px solid var(--line); background: var(--panel2); color: var(--text); cursor: pointer; font-weight: 900; }
        .icon-btn:hover { border-color: #51607a; background: #273040; }
        .icon-btn.loading { color: var(--accent); pointer-events: none; }
        .icon-btn.loading .spin { animation: qlx-spin .8s linear infinite; }
        @keyframes qlx-spin { to { transform: rotate(360deg); } }
        .sidebar-card { background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 10px; }
        .sidebar-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 8px; }
        .sidebar-head h3 { margin: 0; font-size: 12px; text-transform: uppercase; color: var(--muted); letter-spacing: 0; }
        .sidebar-note { margin-top: 8px; color: var(--muted); font-size: 10px; line-height: 1.3; word-break: break-word; }
        .sidebar-machines { display: grid; gap: 7px; }
        .compact-sidebar .machine-cards { display: grid; grid-template-columns: 1fr; gap: 7px; }
        .compact-sidebar .machine-card { min-height: 0; border-left: 5px solid #69758a; }
        .compact-sidebar .machine-card[data-machine="InBat"] { border-left-color: var(--machine-inbat); }
        .compact-sidebar .machine-card[data-machine="InDecal"] { border-left-color: var(--machine-indecal); }
        .compact-sidebar .machine-card[data-machine="CNC"] { border-left-color: var(--machine-cnc); }
        .compact-sidebar .machine-card .machine-more { display: none; }
        .compact-sidebar .machine-card[open] .machine-more { display: block; padding: 0 8px 8px; }
        .compact-sidebar .erp-summary-row { display: grid; grid-template-columns: 1fr; gap: 7px; margin: 0; }
        .compact-sidebar .erp-summary-row .erp-sum-card { padding: 10px; text-align: left; }
        .compact-sidebar .erp-summary-row .total-summary-card {
            padding: 8px 10px;
            border-color: rgba(96,165,250,.7);
            background: linear-gradient(135deg, #101827 0%, #172033 100%);
            box-shadow: inset 0 0 0 1px rgba(148,163,184,.08);
        }
        .sidebar-label { color: var(--muted); font-size: 11px; text-transform: uppercase; font-weight: 800; }
        .stat-line { display: flex; align-items: center; justify-content: space-between; gap: 8px; min-height: 30px; padding: 6px 8px; background: #11161f; border: 1px solid var(--line); border-radius: 8px; font-size: 12px; border-left: 5px solid #69758a; }
        .stat-line.machine-InBat { border-left-color: var(--machine-inbat); }
        .stat-line.machine-InDecal { border-left-color: var(--machine-indecal); }
        .stat-line.machine-CNC { border-left-color: var(--machine-cnc); }
        .stat-line strong { color: var(--text); font-size: 13px; }
        .total-summary-row { display: grid; grid-template-columns: auto minmax(0, 1fr) minmax(0, .8fr); align-items: center; gap: 10px; min-height: 34px; }
        .total-summary-title { color: #bfdbfe; font-size: 11px; text-transform: uppercase; font-weight: 950; letter-spacing: 0; }
        .total-summary-value { display: block; font-size: 21px; line-height: 1; font-weight: 950; text-align: right; }
        .total-summary-value.done-value, .stat-line .done-value { color: #7dd3fc; }
        .total-summary-value.error-value, .stat-line .error-value { color: #fb7185; }
        .stat-line .metric-pair { margin-left: auto; display: grid; grid-template-columns: minmax(72px, 1fr) minmax(58px, .8fr); gap: 8px; text-align: right; }
        .attention-badge { min-width: 28px; height: 24px; display: inline-grid; place-items: center; border-radius: 999px; background: #2a303d; color: var(--muted); border: 1px solid var(--line); font-size: 12px; font-weight: 900; }
        .attention-badge.has-items { background: rgba(239,91,104,.16); color: #ffb6be; border-color: rgba(239,91,104,.5); }
        .mini-link { border: 1px solid var(--line); background: #11161f; color: #93c5fd; border-radius: 999px; padding: 4px 8px; cursor: pointer; font-size: 11px; font-weight: 800; }
        .main-tabs { display: flex; align-items: center; gap: 6px; background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 6px; }
        .main-tab { border: 1px solid transparent; background: transparent; color: var(--muted); border-radius: 7px; padding: 8px 10px; font-weight: 900; cursor: pointer; min-height: 34px; }
        .main-tab:hover { color: var(--text); background: #1f2937; }
        .main-tab.active { background: #273040; border-color: #51607a; color: var(--text); }
        .main-tab.icon-only { margin-left: auto; min-width: 38px; }
        .main-tab-panel { display: none; min-height: 0; }
        .main-tab-panel.active { display: flex; flex-direction: column; gap: 10px; min-height: 0; }
        .compact-board { display: grid; grid-template-columns: repeat(3, minmax(220px, 1fr)); gap: 8px; min-height: 0; }
        .compact-board .column { height: calc(100vh - 188px); min-height: 390px; }
        .legacy-states { margin-top: 0; }
        .legacy-board { min-height: 300px; padding: 10px; }
        .legacy-board .column { height: 300px; }
        .customer-mini-list, .customer-full-list { display: grid; gap: 6px; }
        .customer-full-list { grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); margin-top: 10px; }
        .customer-row { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 8px; align-items: center; min-height: 30px; padding: 6px 8px; background: #11161f; border: 1px solid var(--line); border-radius: 8px; font-size: 12px; }
        .customer-row span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .customer-row strong { color: #fbbf24; }
        .report-detail-panel { display: grid; gap: 8px; min-height: 0; overflow: hidden; }
        .report-detail-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
        .report-detail-title { color: var(--text); font-size: 13px; font-weight: 900; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .report-detail-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; }
        .report-metric { background: #11161f; border: 1px solid var(--line); border-radius: 8px; padding: 7px 8px; min-height: 42px; }
        .report-metric span { display: block; color: var(--muted); font-size: 10px; font-weight: 800; text-transform: uppercase; margin-bottom: 5px; }
        .report-metric strong { color: var(--text); font-size: 16px; font-weight: 900; }

        /* Layout C sync layer */
        :root {
            --radius: 8px;
            --space-1: 4px;
            --space-2: 6px;
            --space-3: 8px;
            --space-4: 10px;
            --space-5: 12px;
            --control-h: 36px;
            --control-bg: #11161f;
            --control-bg-hover: #151c27;
            --control-bg-active: #202634;
            --control-border: var(--line);
            --control-border-active: #51607a;
            --machine-inbat-border: color-mix(in srgb, var(--machine-inbat) 55%, var(--line));
            --machine-indecal-border: color-mix(in srgb, var(--machine-indecal) 55%, var(--line));
            --machine-cnc-border: color-mix(in srgb, var(--machine-cnc) 55%, var(--line));
            --font-xs: 10px;
            --font-sm: 11px;
            --font-md: 12px;
            --font-lg: 14px;
        }
        body, button, input, select { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }
        .top-navbar, .sidebar-card, .main-tabs, .chart-box, .detail-card, .column, .machine-card, .erp-sum-card, .stat-line, .customer-row, .attention-item, .modal-content, .card, .card-preview { border-radius: var(--radius); }
        .top-navbar { min-height: 60px; padding: var(--space-5); gap: var(--space-5); }
        .compact-filters { display: flex; gap: var(--space-4); align-items: center; min-width: 0; flex: 1; }
        .compact-filters select, .compact-filters input[type="date"], .chart-toggle, .icon-btn, #socket-status { min-height: var(--control-h); height: var(--control-h); }
        .compact-filters select, .compact-filters input[type="date"] { font-size: var(--font-md); font-weight: 800; }
        .quick-select { min-width: 145px; }
        #erpMachine { min-width: 108px; }
        .chart-toggle { align-items: center; padding: 2px; }
        .chart-toggle button { min-width: 54px; min-height: 30px; padding: 0 var(--space-3); }
        .header-controls { gap: var(--space-3); flex-shrink: 0; }
        #socket-status { display: inline-flex; align-items: center; justify-content: center; min-width: 88px; font-size: var(--font-sm); }
        .compact-shell { gap: var(--space-5); }
        .compact-sidebar { gap: var(--space-4); scrollbar-gutter: stable; }
        .compact-sidebar::-webkit-scrollbar, .list-container::-webkit-scrollbar { width: 6px; }
        .compact-sidebar::-webkit-scrollbar-track, .list-container::-webkit-scrollbar-track { background: transparent; }
        .compact-sidebar::-webkit-scrollbar-thumb, .list-container::-webkit-scrollbar-thumb { background: #475569; border-radius: 999px; }
        .sidebar-card { padding: var(--space-4); }
        .sidebar-head { min-height: 28px; margin-bottom: var(--space-3); }
        .sidebar-head h3, .chart-box h3, .chart-head h3 { color: #9fb0c8; font-size: var(--font-md); letter-spacing: 0; }
        .sidebar-machines, .customer-mini-list, .customer-full-list { gap: var(--space-2); }
        .compact-sidebar .machine-card summary { padding: var(--space-3); }
        .machine-name, .card-title, .attention-title { letter-spacing: 0; }
        .machine-kpi { gap: var(--space-2); }
        .machine-kpi span { white-space: nowrap; }
        .status-pill, .attention-badge, .badge, .badge-run, .stage-chip, .mini-link, .count-badge { letter-spacing: 0; }
        .main-tabs { min-height: 52px; padding: var(--space-2); overflow-x: auto; overflow-y: hidden; scrollbar-width: none; }
        .main-tabs::-webkit-scrollbar { display: none; }
        .main-tab { min-height: 36px; padding: 0 var(--space-5); display: inline-flex; align-items: center; justify-content: center; gap: var(--space-2); white-space: nowrap; }
        .main-tab.icon-only { min-width: 36px; padding: 0; }
        .main-tab-panel.active { min-height: 0; overflow: hidden; }
        .compact-board { min-height: 0; overflow: hidden; }
        .compact-board .column { min-width: 0; min-height: 0; }
        .problem-column { gap: 0; }
        .problem-stack {
            display: grid;
            grid-template-rows: minmax(0, 1fr);
            grid-auto-rows: minmax(0, 1fr);
            gap: var(--space-2);
            min-height: 0;
            flex: 1;
            padding: var(--space-2);
        }
        .problem-section {
            display: flex;
            flex-direction: column;
            min-height: 0;
            border: 1px solid var(--line);
            border-radius: var(--radius);
            overflow: hidden;
            background: #0d121b;
        }
        .problem-section.is-empty {
            display: none;
        }
        .problem-section h3 {
            display: flex;
            align-items: center;
            justify-content: space-between;
            min-height: 28px;
            margin: 0;
            padding: 6px 8px;
            color: #d6dce6;
            font-size: var(--font-sm);
            text-transform: uppercase;
            border-bottom: 1px solid var(--line);
        }
        .problem-section .count-badge {
            position: static;
            background: #2a303d;
            color: var(--text);
        }
        .problem-section .list-container {
            min-height: 0;
            max-height: none;
        }
        @media screen and (min-width: 1800px) {
            .compact-shell {
                grid-template-columns: 340px minmax(0, 1fr);
                gap: 16px;
            }
            .compact-board {
                grid-template-columns: repeat(3, minmax(320px, 1fr));
                gap: 12px;
            }
            .compact-board .column {
                height: calc(100vh - 190px);
                min-height: 560px;
            }
            .compact-sidebar {
                max-height: calc(100vh - 100px);
            }
            .list-container {
                padding: 10px;
            }
            .card {
                min-height: 40px;
                padding: 8px 10px;
            }
        }
        .column { background: #101620; }
        .column h2 { color: #f8fafc; min-height: 40px; padding: 0 var(--space-3); font-size: var(--font-md); text-align: left; }
        .list-container { margin: 0; padding: var(--space-2); }
        .card { min-height: 36px; padding: 6px 8px; margin-bottom: var(--space-2); }
        .card-main { min-height: 22px; }
        .card-time, .stage-chip { font-size: var(--font-xs); }
        .erp-sum-card { min-height: 74px; }
        .erp-sum-val { font-size: 25px; line-height: 1.1; }
        .stat-line, .customer-row { min-height: 32px; }
        .chart-box { padding: var(--space-5); }
        .canvas-container { height: min(44vh, 300px); min-height: 220px; }
        .legacy-states > summary { min-height: 44px; display: flex; align-items: center; color: #00ffcc; }
        .legacy-states {
            background: transparent;
            border-color: var(--line);
        }
        .legacy-states[open] {
            background: #11161f;
        }
        .legacy-board {
            display: grid;
            grid-template-columns: repeat(3, minmax(160px, 1fr));
            min-height: 0;
            max-height: 260px;
            overflow-y: auto;
            overflow-x: hidden;
            background: transparent;
            padding: var(--space-3);
        }
        .legacy-board .column {
            height: 220px;
            min-height: 0;
            background: #0f151e;
        }
        .legacy-board .column h2 {
            min-height: 34px;
            font-size: var(--font-sm);
        }
        .column h2 {
            border-top: 0;
        }
        .col-export { border-color: color-mix(in srgb, var(--stage-export) 55%, var(--line)); }
        .col-rip { border-color: color-mix(in srgb, var(--stage-rip) 55%, var(--line)); }
        .col-run { border-color: color-mix(in srgb, var(--stage-run) 55%, var(--line)); }
        .col-done { border-color: color-mix(in srgb, var(--stage-done) 55%, var(--line)); }
        .col-cancel { border-color: color-mix(in srgb, var(--stage-cancel) 55%, var(--line)); }
        .col-removed { border-color: color-mix(in srgb, var(--stage-removed) 55%, var(--line)); }
        .card-preview { width: 340px; }
        .card-preview img { max-height: 260px; }
        button:focus-visible, select:focus-visible, input:focus-visible, .card:focus-visible, summary:focus-visible { outline: 2px solid #60a5fa; outline-offset: 2px; }
        .compact-filters select,
        .compact-filters input[type="date"] {
            height: var(--control-h);
            padding: 0 12px;
            background: var(--control-bg) !important;
            color: var(--text) !important;
            border: 1px solid var(--control-border) !important;
            border-radius: var(--radius);
            box-shadow: none;
        }
        .quick-select {
            background: var(--control-bg) !important;
            color: var(--text) !important;
            border-color: var(--control-border) !important;
            box-shadow: none;
            padding-right: 32px !important;
        }
        .quick-select:hover,
        .compact-filters select:hover,
        .compact-filters input[type="date"]:hover {
            background: var(--control-bg-hover) !important;
            border-color: var(--control-border-active) !important;
        }
        .chart-toggle {
            background: transparent;
            border: 0;
            border-radius: 0;
            gap: var(--space-2);
            padding: 0;
            box-shadow: none;
        }
        .chart-toggle button {
            height: var(--control-h);
            min-height: var(--control-h);
            border: 1px solid var(--control-border);
            background: var(--control-bg);
            color: var(--muted);
            box-shadow: none;
            border-radius: var(--radius);
            padding: 0 12px;
        }
        .chart-toggle button.active {
            background: var(--control-bg-active);
            border-color: var(--control-border-active);
            color: var(--text);
            box-shadow: inset 0 -2px 0 #6aa7ff;
        }
        .card,
        .compact-sidebar .machine-card,
        .stat-line,
        .attention-item {
            border-left-width: 1px;
        }
        .card[data-machine="InBat"],
        .compact-sidebar .machine-card[data-machine="InBat"],
        .stat-line.machine-InBat,
        .attention-item[data-machine="InBat"] {
            border-color: var(--machine-inbat-border);
        }
        .card[data-machine="InDecal"],
        .compact-sidebar .machine-card[data-machine="InDecal"],
        .stat-line.machine-InDecal,
        .attention-item[data-machine="InDecal"] {
            border-color: var(--machine-indecal-border);
        }
        .card[data-machine="CNC"],
        .compact-sidebar .machine-card[data-machine="CNC"],
        .stat-line.machine-CNC,
        .attention-item[data-machine="CNC"] {
            border-color: var(--machine-cnc-border);
        }
        .card[data-machine="InBat"]:hover,
        .card[data-machine="InBat"]:focus-within {
            border-color: var(--machine-inbat);
        }
        .card[data-machine="InDecal"]:hover,
        .card[data-machine="InDecal"]:focus-within {
            border-color: var(--machine-indecal);
        }
        .card[data-machine="CNC"]:hover,
        .card[data-machine="CNC"]:focus-within {
            border-color: var(--machine-cnc);
        }
        .compact-main {
            min-height: 0;
        }
        .main-tabs {
            gap: 6px;
            padding: 7px;
        }
        .main-tab {
            min-height: 34px;
            padding: 0 13px;
        }
        .compact-board {
            grid-template-columns: repeat(3, minmax(220px, 1fr));
            gap: 8px;
        }
        .compact-board:not(.all-empty) .column.is-empty {
            display: none;
        }
        .empty-state {
            display: none;
            min-height: 220px;
            align-items: center;
            justify-content: center;
            text-align: center;
            color: var(--muted);
            background: #101620;
            border: 1px dashed var(--line);
            border-radius: var(--radius);
            font-size: var(--font-sm);
            font-weight: 700;
        }
        .compact-board.all-empty {
            opacity: 0.88;
        }
        .compact-board.all-empty + .empty-state {
            display: flex;
            min-height: 42px;
            margin-top: 8px;
        }
        .compact-board .column {
            height: calc(100vh - 188px);
            min-height: 360px;
        }
        .column h2 {
            min-height: 32px;
            padding: 7px 8px;
        }
        .legacy-states {
            margin-top: 8px;
        }
        .legacy-states > summary {
            min-height: 34px;
            padding: 8px 10px;
            color: var(--muted);
            background: #11161f;
            border-bottom-color: transparent;
            font-size: 11px;
        }
        .legacy-states[open] > summary {
            color: var(--cyan);
            border-bottom-color: var(--line);
        }
        .legacy-states .legacy-board {
            max-height: 260px;
            min-height: 0;
            overflow: auto;
            padding: 8px;
            gap: 8px;
        }
        .legacy-states .legacy-board .column {
            height: 240px;
            min-height: 0;
        }
        .legacy-states .legacy-board .list-container {
            max-height: 190px;
        }
        #main-tab-technical .legacy-board {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
            gap: 8px;
            min-height: 0;
            overflow: hidden;
            padding: 0;
        }
        #main-tab-technical .legacy-board .column {
            height: calc(100vh - 150px);
            min-height: 360px;
        }
        #main-tab-technical .legacy-board .list-container {
            max-height: none;
        }
        .flow-dashboard {
            display: block;
            min-height: 0;
            height: calc(100vh - 150px);
        }
        .flow-report-stack {
            display: grid;
            grid-template-rows: minmax(170px, 1fr) minmax(160px, 0.95fr) minmax(118px, auto);
            gap: 10px;
            height: 100%;
            min-height: 0;
        }
        .flow-chart-card {
            min-height: 0;
        }
        .flow-chart-card .canvas-container {
            height: 100%;
            min-height: 0;
        }
        .single-flow-panel {
            display: none;
            height: 100%;
            padding: 14px 18px 12px;
            gap: 10px;
            flex-direction: column;
            justify-content: center;
        }
        .single-flow-row {
            display: grid;
            grid-template-columns: 78px 1fr 96px;
            align-items: center;
            gap: 10px;
            min-height: 34px;
            color: var(--muted);
            font-size: 12px;
            font-weight: 800;
        }
        .single-flow-track {
            height: 22px;
            border-radius: 4px;
            background: rgba(255,255,255,0.06);
            overflow: hidden;
            border: 1px solid var(--line);
        }
        .single-flow-fill {
            height: 100%;
            min-width: 6px;
            border-radius: 4px;
        }
        .single-flow-value {
            color: var(--text);
            text-align: right;
            font-size: 13px;
        }
        .single-flow-empty {
            color: var(--muted);
            text-align: center;
            font-size: 12px;
            font-weight: 800;
        }
        .flow-list .attention-item {
            border-left-width: 1px;
            min-height: 54px;
        }
        .flow-list .attention-title {
            font-size: 11px;
        }
        .flow-list .attention-reason {
            -webkit-line-clamp: 1;
        }
        #main-tab-attention.active { flex: 1; height: calc(100vh - 150px); }
        .attention-panel { height: 100%; }
        #main-tab-system.active { flex: 1; height: calc(100vh - 150px); overflow: hidden; }
        .system-status-body { height: 100%; overflow: hidden; padding-right: 2px; display: grid; grid-template-columns: 112px minmax(0, 1fr); gap: 10px; }
        #main-tab-system .status-overview,
        #main-tab-system .status-card.full,
        #main-tab-system .ops-advanced-grid { display: none; }
        .system-mini-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }
        .system-mini-card { background: #0b0d11; border: 1px solid var(--line); border-radius: 8px; padding: 10px; min-height: 72px; }
        .system-mini-label { color: var(--muted); font-size: 10px; text-transform: uppercase; font-weight: 800; }
        .system-mini-value { color: var(--text); font-size: 20px; font-weight: 900; margin-top: 6px; }
        .system-note-list { display: grid; gap: 7px; }
        .system-note-row { display: grid; grid-template-columns: 1fr auto; gap: 8px; align-items: center; border: 1px solid var(--line); border-radius: 8px; padding: 7px 8px; background: #0b0d11; font-size: 11px; }
        .system-note-row span { color: var(--muted); }
        .system-note-row strong { color: var(--text); text-align: right; }
        .version-chip-list { display: grid; gap: 7px; }
        .version-chip { display: grid; grid-template-columns: 72px 1fr; gap: 8px; align-items: center; border: 1px solid var(--line); border-radius: 8px; padding: 7px 8px; background: #0b0d11; font-size: 11px; }
        .version-chip strong { color: var(--text); }
        .version-chip span { color: var(--muted); text-align: right; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .system-log-body { height: 100%; overflow: hidden; display: contents; }
        .system-source-list { display: flex; flex-direction: column; gap: 6px; min-height: 0; overflow-y: auto; padding-right: 2px; }
        .system-source-btn { border: 1px solid var(--line); background: #11161f; color: var(--text); border-radius: 8px; padding: 8px; text-align: left; cursor: pointer; font-weight: 900; display: grid; grid-template-columns: 1fr; gap: 6px; align-items: center; min-height: 50px; }
        .system-source-btn.active, .system-source-btn:hover { border-color: #60a5fa; background: #172235; }
        .system-source-name { font-size: 11px; line-height: 1.1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .system-source-btn .status-pill { margin-left: 0; justify-self: start; }
        .system-viewer { background: #11161f; border: 1px solid var(--line); border-radius: 8px; min-height: 0; display: flex; flex-direction: column; overflow: hidden; }
        .system-viewer-head { display: grid; grid-template-columns: auto minmax(0, 1fr) auto; align-items: center; gap: 10px; padding: 8px 12px; border-bottom: 1px solid var(--line); color: var(--text); font-size: 12px; font-weight: 900; text-transform: uppercase; }
        .system-viewer-title { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .system-viewer-note { color: var(--muted); font-size: 11px; font-weight: 700; text-transform: none; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .system-viewer-body { flex: 1; min-height: 0; overflow: auto; padding: 10px; }
        .system-viewer-body .log-tail { height: 100%; max-height: none; margin: 0; box-sizing: border-box; overflow: auto; }
        .system-viewer-path { display: none; }
        .log-source-list { display: flex; flex-direction: column; gap: 6px; min-height: 0; overflow-y: auto; }
        .log-source-btn { border: 1px solid var(--line); background: #11161f; color: var(--text); border-radius: 8px; padding: 8px; text-align: left; cursor: pointer; font-weight: 900; display: grid; grid-template-columns: 1fr; gap: 6px; align-items: center; min-height: 54px; }
        .log-source-btn.active, .log-source-btn:hover { border-color: #60a5fa; background: #172235; }
        .log-source-name { font-size: 11px; line-height: 1.1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .log-source-btn .status-pill { margin-left: 0; justify-self: start; }
        .log-viewer { background: #11161f; border: 1px solid var(--line); border-radius: 8px; min-height: 0; display: flex; flex-direction: column; overflow: hidden; }
        .log-viewer-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 8px 12px; border-bottom: 1px solid var(--line); color: var(--text); font-size: 12px; font-weight: 900; text-transform: uppercase; }
        .log-viewer-path { color: var(--muted); font-size: 11px; padding: 0 12px 8px; border-bottom: 1px solid var(--line); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .system-log-body .log-tail { flex: 1; max-height: none; margin: 10px; overflow: auto; }
        .attention-head {
            min-height: 38px;
        }
        .compact-sidebar {
            gap: 8px;
        }
        .sidebar-card {
            padding: 9px;
        }
        .compact-sidebar .machine-card summary {
            padding: 8px 9px;
        }
        .machine-name {
            display: flex;
            align-items: center;
            gap: 6px;
        }
        .machine-name::before {
            content: "";
            width: 8px;
            height: 8px;
            border-radius: 999px;
            background: #69758a;
            flex: 0 0 auto;
        }
        .machine-card[data-machine="InBat"] .machine-name::before { background: var(--machine-inbat); }
        .machine-card[data-machine="InDecal"] .machine-name::before { background: var(--machine-indecal); }
        .machine-card[data-machine="CNC"] .machine-name::before { background: var(--machine-cnc); }
        .machine-card .muted {
            font-size: 10px;
            line-height: 1.2;
        }
        .status-pill {
            white-space: nowrap;
        }
        .stat-line {
            min-height: 28px;
            padding: 5px 8px;
        }
        .erp-sum-card {
            min-height: 62px;
            padding: 9px;
        }
        .customer-row {
            min-height: 28px;
            padding: 5px 8px;
        }
        @media screen and (max-width: 1200px) {
            .compact-board {
                grid-template-columns: repeat(2, minmax(220px, 1fr));
                overflow-y: auto;
                padding-right: 2px;
            }
            .compact-board .column {
                height: calc((100vh - 204px) / 2);
                min-height: 280px;
            }
            .problem-column {
                grid-column: 1 / -1;
            }
        }
        @media screen and (max-width: 900px) {
            body { padding: 10px; }
            .top-navbar { display: grid; grid-template-columns: 1fr auto; align-items: center; }
            .top-navbar::before { grid-column: 1; }
            .header-controls { grid-column: 2; grid-row: 1; justify-self: end; margin-left: 0; }
            .compact-filters { grid-column: 1 / -1; grid-row: 2; flex-wrap: wrap; width: 100%; }
            .compact-shell { grid-template-columns: 1fr; }
            .compact-sidebar { max-height: none; overflow: visible; }
            .compact-board { grid-template-columns: 1fr; }
            .compact-board .column { height: auto; min-height: 160px; }
            .board { grid-template-columns: 1fr; overflow-x: visible; min-height: 0; }
            .column { height: auto; min-height: 160px; }
            .list-container { max-height: 360px; }
            .status-overview, .machine-cards, .erp-grid, .erp-summary-row, .ops-advanced-grid, .attention-list { grid-template-columns: 1fr; }
            .chart-box.full-width { grid-column: span 1; }
            .flow-dashboard { height: auto; }
            .flow-report-stack { grid-template-rows: minmax(220px, 1fr) minmax(220px, 1fr) auto; height: auto; }
        }
    </style>
</head>
<body>
    
    <div class="top-navbar">
        <div id="global-filter" class="controls compact-filters">
            <select id="erpQuickDate" class="quick-select" onchange="applyQuickDate()" title="Chọn nhanh ngày">
                <option value="today" selected>Hôm nay</option>
                <option value="yesterday">Hôm qua</option>
                <option value="this_week">Tuần này</option>
                <option value="last_week">Tuần trước</option>
                <option value="this_month">Tháng này</option>
                <option value="last_month">Tháng trước</option>
                <option value="this_quarter">Quý này</option>
                <option value="last_quarter">Quý trước</option>
                <option value="this_year">Năm nay</option>
                <option value="last_year">Năm trước</option>
                <option value="all_time">Toàn thời gian</option>
            </select>
            <input type="date" id="erpStart" onchange="applyGlobalFilters()" title="Từ ngày">
            <input type="date" id="erpEnd" onchange="applyGlobalFilters()" title="Đến ngày">
            <select id="erpMachine" onchange="applyGlobalFilters()" title="Lọc máy">
                <option value="ALL">Tất cả máy</option>
                <option value="InBat">In Bạt</option>
                <option value="InDecal">In Decal</option>
                <option value="CNC">CNC</option>
            </select>
            <div class="chart-toggle" aria-label="Chọn kiểu thống kê">
                <button id="flowMetricCount" class="active" type="button" onclick="setFlowMetric('count')">Số lượng</button>
                <button id="flowMetricM2" type="button" onclick="setFlowMetric('m2')">m2</button>
            </div>
        </div>
        <div class="header-controls">
            <span id="socket-status" class="status-off">Đang kết nối...</span>
            <button id="refreshBtn" class="icon-btn" onclick="applyGlobalFilters()" title="Làm mới" aria-label="Làm mới"><span class="spin">↻</span></button>
            <button id="authBtn" class="icon-btn login-btn" onclick="toggleAuth()" title="Đăng nhập quản trị" aria-label="Đăng nhập quản trị">⚙</button>
        </div>
    </div>

    <div class="compact-shell">
        <aside class="compact-sidebar">
            <section class="sidebar-card">
                <div class="sidebar-head">
                    <h3>Máy sản xuất</h3>
                    <span id="v2-overall" class="status-pill pill-warn">Đang tải</span>
                </div>
                <div id="sidebar-machines" class="sidebar-machines"></div>
                <div id="v2-generated" class="sidebar-note"></div>
            </section>
            <section class="sidebar-card">
                <div class="sidebar-head">
                    <h3>Thống kê</h3>
                    <span id="attentionBadge" class="attention-badge">0</span>
                </div>
                <div class="erp-summary-row">
                    <div class="erp-sum-card total-summary-card">
                        <div class="total-summary-row">
                            <span class="total-summary-title">Tổng</span>
                            <strong id="erp-total-main" class="total-summary-value done-value">0</strong>
                            <strong id="erp-total-error-main" class="total-summary-value error-value">0</strong>
                        </div>
                    </div>
                    <div class="stat-line machine-InBat"><span>InBat</span><div class="metric-pair"><strong id="erp-inbat-value" class="done-value">0</strong><strong id="erp-inbat-error" class="error-value">0</strong></div></div>
                    <div class="stat-line machine-InDecal"><span>InDecal</span><div class="metric-pair"><strong id="erp-indecal-value" class="done-value">0</strong><strong id="erp-indecal-error" class="error-value">0</strong></div></div>
                    <div class="stat-line machine-CNC"><span>CNC</span><div class="metric-pair"><strong id="erp-cnc-value" class="done-value">0</strong><strong id="erp-cnc-error" class="error-value">0</strong></div></div>
                </div>
            </section>
            <section class="sidebar-card">
                <div class="sidebar-head">
                    <h3>Khách hàng</h3>
                    <button class="mini-link" onclick="switchMainTab('flow')" title="Mở báo cáo khách hàng">Mở</button>
                </div>
                <div id="sidebarCustomerList" class="customer-mini-list"></div>
            </section>
        </aside>

        <main class="compact-main">
            <div class="main-tabs" role="tablist">
                <button id="tab-production" class="main-tab active" onclick="switchMainTab('production')" title="Sản xuất">Sản xuất</button>
                <button id="tab-attention" class="main-tab" onclick="switchMainTab('attention')" title="Việc chờ xử lý">Chờ xử lý <span id="attentionTabCount">0</span></button>
                <button id="tab-flow" class="main-tab" onclick="switchMainTab('flow')" title="Báo cáo khách hàng và đơn hàng">Báo cáo</button>
                <button id="tab-system" class="main-tab" onclick="switchMainTab('system')" title="Log, outbox, phiên bản, trạng thái hệ thống">Hệ thống</button>
                <button class="main-tab icon-only" onclick="exportExcel()" title="Xuất Excel" aria-label="Xuất Excel">⬇</button>
            </div>

            <section id="main-tab-production" class="main-tab-panel active">
                <div class="compact-board">
                    <div class="column col-export queue-column"><h2>Hàng chờ <span class="count-badge" id="count-queue">0</span></h2><div id="queue-list" class="list-container"></div></div>
                    <div class="column col-done"><h2>In xong <span class="count-badge" id="count-done-compact">0</span></h2><div id="done-compact-list" class="list-container"></div></div>
                    <div class="column col-cancel problem-column">
                        <h2>Lỗi / thao tác <span class="count-badge" id="count-problem">0</span></h2>
                        <div class="problem-stack">
                            <div class="problem-section" id="true-problem-section">
                                <h3>Lỗi thật <span class="count-badge" id="count-true-problem">0</span></h3>
                                <div id="true-problem-list" class="list-container"></div>
                            </div>
                            <div class="problem-section" id="removed-problem-section">
                                <h3>Xóa / hủy <span class="count-badge" id="count-removed-problem">0</span></h3>
                                <div id="removed-problem-list" class="list-container"></div>
                            </div>
                        </div>
                    </div>
                </div>
                <div id="compact-empty-state" class="empty-state">Chưa có việc trong bộ lọc này.</div>
            </section>

            <section id="main-tab-technical" class="main-tab-panel">
                <div class="board legacy-board">
                    <div class="column col-export"><h2>Xuất file <span class="count-badge" id="count-export">0</span></h2><div id="exported-list" class="list-container"></div></div>
                    <div class="column col-rip"><h2>Đã RIP <span class="count-badge" id="count-rip">0</span></h2><div id="rip-list" class="list-container"></div></div>
                    <div class="column col-run"><h2>Đang chạy <span class="count-badge" id="count-run">0</span></h2><div id="run-list" class="list-container"></div></div>
                    <div class="column col-done"><h2>Đã xong <span class="count-badge" id="count-done">0</span></h2><div id="done-list" class="list-container"></div></div>
                    <div class="column col-cancel"><h2>Lỗi/Hủy <span class="count-badge" id="count-cancel">0</span></h2><div id="cancel-list" class="list-container"></div></div>
                    <div class="column col-removed"><h2>Xóa thao tác <span class="count-badge" id="count-removed">0</span></h2><div id="removed-list" class="list-container"></div></div>
                </div>
            </section>

            <section id="main-tab-attention" class="main-tab-panel">
                <div id="attention-panel" class="attention-panel">
                    <div class="attention-head">
                        <span>Chờ xử lý</span>
                        <span id="attention-count" class="attention-count">0 việc</span>
                    </div>
                    <div id="attention-list" class="attention-list"></div>
                </div>
            </section>

            <section id="main-tab-flow" class="main-tab-panel">
                <div class="flow-dashboard">
                    <div class="flow-report-stack">
                        <div class="chart-box flow-chart-card">
                            <div class="chart-head"><h3 id="orderFlowTitle">Đơn hàng theo máy</h3></div>
                            <div class="canvas-container">
                                <canvas id="orderFlowChart"></canvas>
                                <div id="orderFlowSingle" class="single-flow-panel"></div>
                            </div>
                        </div>
                        <div class="chart-box flow-chart-card">
                            <div class="chart-head"><h3>Khách hàng theo tên file</h3></div>
                            <div class="canvas-container"><canvas id="flowCustomerChart"></canvas></div>
                        </div>
                        <div class="chart-box report-detail-panel">
                            <div class="report-detail-head">
                                <div id="reportDetailTitle" class="report-detail-title">Chỉ số theo bộ lọc hiện tại</div>
                                <button id="clearCustomerFilterBtn" class="main-tab" onclick="clearCustomerFilter()" style="display:none;">Tất cả</button>
                            </div>
                            <div id="reportDetailGrid" class="report-detail-grid"></div>
                        </div>
                    </div>
                </div>
            </section>

            <section id="main-tab-customers" class="main-tab-panel">
                <div class="chart-box full-width">
                    <div class="chart-head"><h3>Thống kê khách hàng</h3></div>
                    <div class="canvas-container"><canvas id="customerChart"></canvas></div>
                    <div id="customerFullList" class="customer-full-list"></div>
                </div>
            </section>

            <section id="main-tab-system" class="main-tab-panel">
                <div id="v2-status-body" class="status-shell system-status-body"></div>
                <div id="system-log-body" class="system-log-body"></div>
            </section>
        </main>
    </div>

    <div id="loginModal" class="modal">
        <div class="modal-content">
            <span class="close-x" onclick="closeModals()">&times;</span>
            <h3 style="color: #00ffcc; margin-top: 0; text-align: center; font-size:16px;">Đăng nhập quản trị</h3>
            <p style="text-align: center; color: #aaa; font-size: 12px; margin: 0;">Nhập mã PIN để cấp quyền.</p>
            <input type="password" id="pin-input" class="pin-input" placeholder="****" autocomplete="off" maxlength="10">
            <button class="action-btn btn-submit" onclick="submitLogin()">Xác nhận</button>
        </div>
    </div>

    <div id="detailModal" class="modal">
        <div class="modal-content">
            <span class="close-x" onclick="closeModals()">&times;</span>
            <div class="detail-header">
                <span id="dt-badge" class="badge"></span>
                <div id="dt-name" class="detail-name">Tên file</div>
            </div>
            <div class="detail-row"><span class="detail-label">Trạng thái:</span><span class="detail-value" id="dt-status"></span></div>
            <div class="detail-row"><span class="detail-label">Kích thước:</span><span class="detail-value val-m2" id="dt-m2"></span></div>
            <div style="margin-top: 12px; font-size: 12px; color: #00ffcc; font-weight: bold; border-bottom: 1px solid #333; padding-bottom: 4px;">Nhật ký chi tiết</div>
            <div id="dt-timeline-container"></div>

            <input type="hidden" id="modal-machine-name">
            <input type="hidden" id="modal-real-name">
            <input type="hidden" id="modal-file-hash">

            <div id="adminArea" class="admin-section">
                <div class="admin-title">Quản trị viên</div>
                <button class="action-btn btn-done" onclick="forceUpdate('DONE')">Chuyển sang: Đã xong</button>
                <button class="action-btn btn-cancel" onclick="forceUpdate('DELETED')">Chuyển sang: Xóa/Hủy</button>
                <button class="action-btn btn-reset" onclick="forceUpdate('EXPORTED')">Chuyển sang: Xuất lại</button>
            </div>
        </div>
    </div>

    <div id="cardPreview" class="card-preview">
        <img id="cardPreviewImg" alt="Ảnh in">
        <div id="cardPreviewEmpty" class="card-preview-empty">Chưa có ảnh xem trước</div>
        <div id="cardPreviewDetails" class="card-preview-details">
            <div id="cardPreviewName" class="preview-name"></div>
            <div id="cardPreviewStatus" class="preview-status"></div>
            <div id="cardPreviewTimeline" class="preview-timeline"></div>
            <div id="cardPreviewActions" class="preview-actions" aria-label="Chuyển trạng thái nhanh">
                <button type="button" class="preview-action-btn preview-done" title="Chuyển sang: Đã xong" onclick="previewForceUpdate('DONE')">✓</button>
                <button type="button" class="preview-action-btn preview-cancel" title="Chuyển sang: Xóa/Hủy" onclick="previewForceUpdate('DELETED')">✕</button>
                <button type="button" class="preview-action-btn preview-reset" title="Chuyển sang: Xuất lại" onclick="previewForceUpdate('EXPORTED')">↻</button>
            </div>
        </div>
    </div>

    <script>
        Chart.defaults.color = '#aaaaaa';
        Chart.defaults.font.family = "'Segoe UI', Tahoma, sans-serif";
        let m2ChartInst = null; let cusChartInst = null; let hourChartInst = null; let flowCustomerChartInst = null;
        let currentTab = 'board';
        let currentMainTab = 'production';
        let currentStatsData = null;
        let statsRequestId = 0;
        let dataRequestId = 0;
        let activeDataRequests = 0;
        let boardVisibleLimit = 20;
        let statsFetchTimer = null;
        let statsDirty = true;
        let flowMetric = 'count';
        let selectedReportCustomer = '';
        const BOARD_PAGE_INCREMENT = 20;
        const MACHINE_COLORS = {
            InBat: '#22c55e',
            InDecal: '#3b82f6',
            CNC: '#ff6347'
        };
        const STAGE_COLORS = {
            EXPORT: '#f5b84b',
            RIP: '#25c2e3',
            RUN: '#6aa7ff',
            DONE: '#20d489',
            CANCEL: '#ef5b68',
            REMOVED: '#9aa4b2'
        };
        function machineColor(machine) {
            return MACHINE_COLORS[machine] || '#9aa4b2';
        }

        function setFlowMetric(metric) {
            flowMetric = metric === 'm2' ? 'm2' : 'count';
            document.getElementById('flowMetricCount')?.classList.toggle('active', flowMetric === 'count');
            document.getElementById('flowMetricM2')?.classList.toggle('active', flowMetric === 'm2');
            if (currentStatsData) {
                renderStatsSummary(currentStatsData);
                renderMachineFlowChart(currentStatsData);
                renderCustomerSummary(currentStatsData);
                renderCustomerChart(currentStatsData);
            }
        }

        function switchMainTab(tab) {
            const selected = ['production', 'technical', 'attention', 'flow', 'customers', 'system'].includes(tab) ? tab : 'production';
            currentMainTab = selected;
            document.querySelectorAll('.main-tab-panel').forEach(panel => panel.classList.remove('active'));
            document.querySelectorAll('.main-tab').forEach(btn => btn.classList.remove('active'));
            document.getElementById('main-tab-' + selected)?.classList.add('active');
            document.getElementById('tab-' + selected)?.classList.add('active');
            if (selected === 'flow' && statsDirty) fetchERP();
            else if (selected === 'flow' && currentStatsData) renderMachineFlowChart(currentStatsData);
            if (selected === 'customers' && currentStatsData) renderCustomerChart(currentStatsData);
        }

        // Safe local date helper.
        function getLocalToday() {
            let d = new Date();
            let m = '' + (d.getMonth() + 1), day = '' + d.getDate(), y = d.getFullYear();
            if (m.length < 2) m = '0' + m;
            if (day.length < 2) day = '0' + day;
            return [y, m, day].join('-');
        }

        function applyGlobalFilters() {
            boardVisibleLimit = BOARD_PAGE_INCREMENT;
            fetchData();
            fetchV2Status();
            scheduleStatsFetch(currentMainTab === 'flow' ? 0 : 900);
        }

        function setBoardLoading(isLoading) {
            const refreshBtn = document.getElementById('refreshBtn');
            const statusEl = document.getElementById('socket-status');
            refreshBtn?.classList.toggle('loading', isLoading);
            if (!statusEl) return;
            if (isLoading) {
                statusEl.dataset.prevText = statusEl.innerText;
                statusEl.dataset.prevClass = statusEl.className;
                statusEl.innerText = 'Đang tải...';
                statusEl.className = 'status-off';
            } else if (statusEl.innerText === 'Đang tải...') {
                statusEl.innerText = statusEl.dataset.prevText || 'Trực tiếp: Bật';
                statusEl.className = statusEl.dataset.prevClass || 'status-on';
            }
        }

        function scheduleStatsFetch(delayMs=400) {
            statsDirty = true;
            if (statsFetchTimer) clearTimeout(statsFetchTimer);
            statsFetchTimer = setTimeout(() => {
                statsFetchTimer = null;
                fetchERP();
            }, delayMs);
        }

        // Global quick date filter.
        function applyQuickDate() {
            let val = document.getElementById('erpQuickDate').value;
            if (!val) return;
            let today = new Date(); let start = new Date(); let end = new Date();

            if (val === 'today') { start = today; end = today; } 
            else if (val === 'yesterday') { start.setDate(today.getDate() - 1); end = new Date(start); } 
            else if (val === 'this_week') { let day = today.getDay() || 7; start.setDate(today.getDate() - day + 1); end = new Date(start); end.setDate(start.getDate() + 6); } 
            else if (val === 'last_week') { let day = today.getDay() || 7; start.setDate(today.getDate() - day - 6); end = new Date(start); end.setDate(start.getDate() + 6); } 
            else if (val === 'this_month') { start = new Date(today.getFullYear(), today.getMonth(), 1); end = new Date(today.getFullYear(), today.getMonth() + 1, 0); } 
            else if (val === 'last_month') { start = new Date(today.getFullYear(), today.getMonth() - 1, 1); end = new Date(today.getFullYear(), today.getMonth(), 0); } 
            else if (val === 'this_quarter') { let q = Math.floor(today.getMonth() / 3); start = new Date(today.getFullYear(), q * 3, 1); end = new Date(today.getFullYear(), q * 3 + 3, 0); } 
            else if (val === 'last_quarter') { let q = Math.floor(today.getMonth() / 3) - 1; let y = today.getFullYear(); if (q < 0) { q = 3; y -= 1; } start = new Date(y, q * 3, 1); end = new Date(y, q * 3 + 3, 0); } 
            else if (val === 'this_year') { start = new Date(today.getFullYear(), 0, 1); end = new Date(today.getFullYear(), 11, 31); } 
            else if (val === 'last_year') { start = new Date(today.getFullYear() - 1, 0, 1); end = new Date(today.getFullYear() - 1, 11, 31); }
            else if (val === 'all_time') { start = new Date(2000, 0, 1); end = today; }
            if (end > today) end = today;

            let sm = '' + (start.getMonth() + 1), sd = '' + start.getDate(), sy = start.getFullYear();
            if (sm.length < 2) sm = '0' + sm; if (sd.length < 2) sd = '0' + sd;
            
            let em = '' + (end.getMonth() + 1), ed = '' + end.getDate(), ey = end.getFullYear();
            if (em.length < 2) em = '0' + em; if (ed.length < 2) ed = '0' + ed;

            document.getElementById('erpStart').value = [sy, sm, sd].join('-');
            document.getElementById('erpEnd').value = [ey, em, ed].join('-');
            applyGlobalFilters();
        }

        function switchTab(tabId) {
            currentTab = tabId;
            if (tabId === 'erp') switchMainTab('flow');
            else switchMainTab('production');
            if(tabId === 'erp') fetchERP();
            if(tabId === 'v2') fetchV2Status();
        }

        function escapeHtml(value) {
            return String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
        }

        function formatAge(seconds) {
            if(seconds === undefined || seconds === null || seconds === '') return '';
            if(seconds < 60) return `${seconds}s trước`;
            if(seconds < 3600) return `${Math.floor(seconds / 60)} phút trước`;
            return `${Math.floor(seconds / 3600)}g ${Math.floor((seconds % 3600) / 60)}p trước`;
        }

        function versionClass(version) {
            return String(version || '').startsWith('V2.') ? 'version-ok' : 'version-old';
        }

        async function fetchV2Status() {
            try {
                const res = await fetch('/api/v2_status');
                const data = await res.json();
                const pill = document.getElementById('v2-overall');
                const overallText = data.overall === 'OK' ? 'Ổn định' : 'Cần xem';
                pill.innerText = overallText;
                pill.className = 'status-pill ' + (data.overall === 'OK' ? 'pill-ok' : 'pill-warn');
                document.getElementById('v2-generated').innerText = data.generated_at + ' | ' + data.data_dir;

                const warningsList = data.warnings || [];
                const warnings = warningsList.map(w => `<div style="color:#ff7777;">${escapeHtml(w)}</div>`).join('') || '<div class="status-message">Bình thường. Chưa có việc cần xử lý.</div>';
                const machineFilter = document.getElementById('erpMachine')?.value || 'ALL';
                const machines = (data.machines || []).filter(m => machineFilter === 'ALL' || m.machine === machineFilter);
                const onlineCount = machines.filter(m => m.online).length;
                const v2Count = machines.filter(m => String(m.version || '').startsWith('V2.')).length;
                const pendingTotal = (data.outboxes || []).reduce((sum, o) => sum + Number(o.pending || 0), 0);
                const overallNote = warningsList.length ? `${warningsList.length} việc cần xem` : 'Hệ thống đang ổn định';
                const systemNotes = `
                    <div class="system-note-list">
                        <div class="system-note-row"><span>Tổng thể</span><strong>${escapeHtml(overallText)}</strong></div>
                        <div class="system-note-row"><span>Máy đang mở</span><strong>${onlineCount}/${machines.length || 0}</strong></div>
                        <div class="system-note-row"><span>Máy V2</span><strong>${v2Count}/${machines.length || 0}</strong></div>
                        <div class="system-note-row"><span>Chờ gửi</span><strong>${pendingTotal}</strong></div>
                        <div class="system-note-row"><span>Cần chú ý</span><strong>${warningsList.length}</strong></div>
                    </div>
                `;
                const summaryCards = `
                    <div class="overview-card"><div class="overview-label">Tổng thể</div><div class="overview-value ${data.overall === 'OK' ? 'version-ok' : 'version-old'}">${escapeHtml(overallText)}</div><div class="overview-note">${escapeHtml(overallNote)}</div></div>
                    <div class="overview-card"><div class="overview-label">Máy đang mở</div><div class="overview-value">${onlineCount}/${machines.length || 0}</div><div class="overview-note">Ping trong 3 phút gần đây</div></div>
                    <div class="overview-card"><div class="overview-label">Máy đã lên V2</div><div class="overview-value">${v2Count}/${machines.length || 0}</div><div class="overview-note">Bản V2.0.0_OUTBOX_READY</div></div>
                    <div class="overview-card"><div class="overview-label">Hàng chờ gửi</div><div class="overview-value ${pendingTotal ? 'version-old' : 'version-ok'}">${pendingTotal}</div><div class="overview-note">Sự kiện chưa gửi lên server</div></div>
                `;
                const machineCards = machines.map(m => {
                    const networkOnly = !m.online && m.network_online;
                    const onlineClass = m.online ? 'pill-ok' : (networkOnly ? 'pill-warn' : 'pill-idle');
                    const cardClass = (m.online || networkOnly) ? 'online' : 'offline';
                    const version = m.version || 'chưa báo';
                    const hostName = String(m.hostname || '').trim();
                    const hostLine = hostName && hostName.toLowerCase() !== String(m.machine || '').toLowerCase()
                        ? `<div class="muted">${escapeHtml(hostName)}</div>`
                        : '';
                    const lastPing = m.last_ping ? `${escapeHtml(m.last_ping)} (${escapeHtml(formatAge(m.ping_age_seconds))})` : (networkOnly ? 'mạng thấy hostname/IP, chưa có heartbeat V2' : 'chưa thấy máy mở/ping');
                    const latestMachine = m.latest_machine_update || 'chưa có log máy';
                    const latestAdmin = m.latest_admin_update || 'chưa có thao tác web';
                    const onlineText = m.online ? 'ĐANG MỞ' : (networkOnly ? 'MÁY BẬT - CHƯA V2' : 'CHƯA MỞ');
                    return `<details class="machine-card ${cardClass}" data-machine="${escapeHtml(m.machine)}">
                        <summary>
                            <div class="top">
                                <div><div class="machine-name">${escapeHtml(m.machine)}</div>${hostLine}</div>
                                <span class="status-pill ${onlineClass}">${onlineText}</span>
                            </div>
                            <div class="machine-main">
                                <div class="machine-kpi">
                                    <span>Đang: <strong>${m.active}</strong></span>
                                    <span>Chờ: <strong>${m.queued_today || 0}</strong></span>
                                    <span>Xong: <strong>${m.done_today}</strong></span>
                                    <span>Tồn cũ: <strong>${m.old_active || 0}</strong></span>
                                </div>
                            </div>
                        </summary>
                        <div class="machine-more">
                            <div class="line"><span class="label">Ping cuối</span><span class="value">${lastPing}</span></div>
                            <div class="line"><span class="label">Log máy gửi cuối</span><span class="value">${escapeHtml(latestMachine)}</span></div>
                            <div class="line"><span class="label">Thao tác web cuối</span><span class="value">${escapeHtml(latestAdmin)}</span></div>
                            <div class="line"><span class="label">Hôm nay chưa xong / đã xong</span><span class="value">${m.unfinished_today || 0} / ${m.done_today}</span></div>
                            <div class="line"><span class="label">Đang chạy thật</span><span class="value">${m.running || 0}</span></div>
                            <div class="line"><span class="label">Tồn cũ chưa tính</span><span class="value">${m.old_active || 0}</span></div>
                        </div>
                    </details>`;
                }).join('');
                document.getElementById('sidebar-machines').innerHTML = machineCards || '<div class="sidebar-note">Không có dữ liệu máy theo bộ lọc.</div>';
                const outboxes = data.outboxes || [];
                const outboxPending = outboxes.reduce((sum, o) => sum + Number(o.pending || 0), 0);
                const outboxSent = outboxes.reduce((sum, o) => sum + Number(o.sent || 0), 0);
                const outboxAttempts = outboxes.reduce((max, o) => Math.max(max, Number(o.max_attempts || 0)), 0);
                const outboxError = outboxes.find(o => o.last_error || o.error);
                const outboxRows = outboxes.length
                    ? `<table class="status-table"><thead><tr><th>File</th><th>Chờ</th><th>Gửi</th><th>Thử</th><th>Lỗi</th></tr></thead><tbody>${outboxes.map(o => `<tr><td>${escapeHtml(o.file)}</td><td>${o.pending}</td><td>${o.sent}</td><td>${o.max_attempts}</td><td>${escapeHtml(o.last_error || o.error)}</td></tr>`).join('')}</tbody></table>`
                    : `<div class="system-note-list">
                        <div class="system-note-row"><span>Trạng thái</span><strong>Không thấy file outbox trên server</strong></div>
                        <div class="system-note-row"><span>Ý nghĩa</span><strong>Máy trạm chưa có hàng chờ gửi, hoặc outbox đang nằm local trên máy trạm</strong></div>
                        <div class="system-note-row"><span>Lịch sử</span><strong>Xem trong log server/máy trạm. Outbox hiện chỉ phục vụ retry, không phải báo cáo lịch sử đầy đủ.</strong></div>
                    </div>`;
                const versionRows = machines.map(m => {
                    const version = m.version || (data.versions || {})[m.machine] || 'chưa báo';
                    const ping = m.last_ping ? `${escapeHtml(m.last_ping)} (${escapeHtml(formatAge(m.ping_age_seconds))})` : 'chưa có ping';
                    return `<tr data-version-machine="${escapeHtml(m.machine)}" onclick="showVersionHistory('${escapeHtml(m.machine)}')">
                        <td>${escapeHtml(m.machine)}</td>
                        <td class="${versionClass(version)}">${escapeHtml(version)}</td>
                        <td>${escapeHtml(m.hostname || m.machine)}</td>
                        <td>${ping}</td>
                        <td>${m.online ? 'Đang mở' : (m.network_online ? 'Máy bật - chưa V2' : 'Chưa mở')}</td>
                    </tr>`;
                }).join('');
                const serverVersion = (data.versions || {}).Server || 'chưa báo';
                const currentVersions = `
                    <table class="status-table version-status-table">
                        <thead><tr><th>Máy</th><th>Bản đang chạy</th><th>Hostname</th><th>Ping cuối</th><th>Trạng thái</th></tr></thead>
                        <tbody>
                            <tr data-version-machine="Server" onclick="showVersionHistory('Server')"><td>Server</td><td class="${versionClass(serverVersion)}">${escapeHtml(serverVersion)}</td><td>${escapeHtml(data.data_dir || '')}</td><td>${escapeHtml(data.generated_at || '')}</td><td>Đang chạy</td></tr>
                            ${versionRows}
                        </tbody>
                    </table>
                `;
                const versions = `
                    <div class="version-chip-list">
                        <div class="system-note-row"><span>Hiện tại</span><strong>${v2Count}/${machines.length || 0} máy trạm đang chạy V2</strong></div>
                        ${currentVersions}
                    </div>
                `;
                const renameAudit = data.rename_audit || {};
                const renameAuditRows = renameAudit.exists && (renameAudit.recent || []).length
                    ? `<table class="status-table"><thead><tr><th>Giờ</th><th>Action</th><th>PRN</th><th>Meta</th><th>Lỗi</th></tr></thead><tbody>${(renameAudit.recent || []).map(row => `<tr><td>${escapeHtml(row.event_time || '')}</td><td>${escapeHtml(row.action || '')}</td><td>${escapeHtml(row.prn_path || '')}</td><td>${escapeHtml(row.meta_path || '')}</td><td>${escapeHtml(row.error || '')}</td></tr>`).join('')}</tbody></table>`
                    : `<div class="system-note-list">
                        <div class="system-note-row"><span>Trạng thái</span><strong>${renameAudit.exists ? 'Chưa có dòng audit rename/RIP' : 'Chưa thấy indecal_rename_audit.db trên server'}</strong></div>
                        <div class="system-note-row"><span>Ý nghĩa</span><strong>Client InDecal cần bản có audit để gửi timeline rename/RIP về server.</strong></div>
                    </div>`;
                const renameAuditBody = `<div class="system-note-list">
                    <div class="system-note-row"><span>Tổng dòng</span><strong>${Number(renameAudit.total || 0)}</strong></div>
                    <div class="system-note-row"><span>Hôm nay</span><strong>${Number(renameAudit.today || 0)}</strong></div>
                    <div class="system-note-row"><span>Lỗi hôm nay</span><strong>${Number(renameAudit.fail_today || 0)}</strong></div>
                    <div class="system-note-row"><span>File</span><strong>${escapeHtml(renameAudit.path || '')}</strong></div>
                </div>${renameAuditRows}`;
                const rawLogs = data.logs || [];
                const systemItems = [
                    {
                        name: 'Outbox',
                        badge: outboxPending,
                        badgeClass: outboxPending ? 'pill-warn' : 'pill-ok',
                        path: 'Sự kiện máy trạm chờ gửi về server',
                        body: outboxRows
                    },
                    {
                        name: 'Phiên bản',
                        badge: Object.keys(data.versions || {}).length,
                        badgeClass: 'pill-ok',
                        path: 'Bản đang chạy và lịch sử đổi phiên bản',
                        body: versions
                    },
                    {
                        name: 'Tổng quan',
                        badge: pendingTotal + warningsList.length,
                        badgeClass: (pendingTotal || warningsList.length) ? 'pill-warn' : 'pill-ok',
                        path: 'Tình trạng chung, outbox và cảnh báo log',
                        body: `<div class="system-note-list">
                            <div class="system-note-row"><span>Tổng thể</span><strong>${escapeHtml(overallText)}</strong></div>
                            <div class="system-note-row"><span>Máy đang mở</span><strong>${onlineCount}/${machines.length || 0}</strong></div>
                            <div class="system-note-row"><span>Máy V2</span><strong>${v2Count}/${machines.length || 0}</strong></div>
                            <div class="system-note-row"><span>Chờ gửi</span><strong>${pendingTotal}</strong></div>
                            <div class="system-note-row"><span>Cần chú ý</span><strong>${warningsList.length}</strong></div>
                            <div class="system-note-row"><span>Lỗi outbox cuối</span><strong>${escapeHtml(outboxError?.last_error || outboxError?.error || 'Không')}</strong></div>
                            <div class="system-note-row"><span>Dòng log có cảnh báo</span><strong>${(rawLogs || []).reduce((sum, log) => sum + Number(log.error_count || 0), 0)}</strong></div>
                        </div>`
                    },
                    {
                        name: 'InDecal rename/RIP',
                        badge: Number(renameAudit.fail_today || 0),
                        badgeClass: Number(renameAudit.fail_today || 0) ? 'pill-warn' : 'pill-ok',
                        path: 'Audit rename, meta, RIP của máy InDecal',
                        body: renameAuditBody
                    },
                    ...rawLogs.map(log => ({
                        name: log.name,
                        badge: log.error_count || 0,
                        badgeClass: log.error_count ? 'pill-warn' : 'pill-ok',
                        path: log.path || '',
                        body: `<div class="log-tail">${escapeHtml((log.tail || []).join('\\n')) || 'Chưa có log.'}</div>`
                    }))
                ];
                const selectedSystemName = window.selectedSystemName || '';
                let selectedSystemIndex = systemItems.findIndex(item => item.name === selectedSystemName);
                if (selectedSystemIndex < 0) selectedSystemIndex = Number.isInteger(window.selectedSystemIndex) ? window.selectedSystemIndex : 0;
                if (selectedSystemIndex < 0 || selectedSystemIndex >= systemItems.length) selectedSystemIndex = 0;
                const systemButtons = systemItems.map((item, index) => `
                    <button class="system-source-btn ${index === selectedSystemIndex ? 'active' : ''}" data-system-index="${index}" onclick="selectSystemItem(${index})">
                        <span class="system-source-name">${escapeHtml(item.name)}</span>
                        <span class="status-pill ${item.badgeClass}">${escapeHtml(item.badge)}</span>
                    </button>
                `).join('');
                const firstItem = systemItems[selectedSystemIndex] || { name: 'Hệ thống', badge: 0, badgeClass: 'pill-idle', path: '', body: '<div class="status-message">Chưa có dữ liệu.</div>' };

                window.systemItems = systemItems;
                window.selectedSystemIndex = selectedSystemIndex;
                window.selectedSystemName = firstItem.name || '';
                window.systemLogs = rawLogs;
                window.versionHistory = data.version_history || [];
                document.getElementById('v2-status-body').innerHTML = `
                    <div class="system-source-list">${systemButtons}</div>
                    <div class="system-viewer">
                        <div class="system-viewer-head"><span id="systemViewerName" class="system-viewer-title">${escapeHtml(firstItem.name)}</span><span id="systemViewerNote" class="system-viewer-note">${escapeHtml(firstItem.path || '')}</span><span id="systemViewerCount" class="status-pill ${firstItem.badgeClass}">${escapeHtml(firstItem.badge)}</span></div>
                        <div id="systemViewerPath" class="system-viewer-path">${escapeHtml(firstItem.path || '')}</div>
                        <div id="systemViewerBody" class="system-viewer-body">${firstItem.body}</div>
                    </div>
                `;
                document.getElementById('system-log-body').innerHTML = '';
            } catch(e) {
                document.getElementById('v2-status-body').innerHTML = '<div class="status-card full"><h3>Lỗi V2 Status</h3><div style="color:#ff3333;">Không tải được /api/v2_status</div></div>';
                document.getElementById('system-log-body').innerHTML = '<div class="status-card full"><h3>Lỗi Log</h3><div style="color:#ff3333;">Không tải được /api/v2_status</div></div>';
                document.getElementById('sidebar-machines').innerHTML = '<div class="sidebar-note">Không tải được trạng thái máy.</div>';
            }
        }

        function selectSystemItem(index) {
            const item = (window.systemItems || [])[index];
            if (!item) return;
            window.selectedSystemIndex = index;
            window.selectedSystemName = item.name || '';
            document.querySelectorAll('.system-source-btn').forEach((btn, i) => btn.classList.toggle('active', i === index));
            document.getElementById('systemViewerName').innerText = item.name || '';
            const count = document.getElementById('systemViewerCount');
            count.innerText = item.badge || 0;
            count.className = 'status-pill ' + (item.badgeClass || 'pill-idle');
            document.getElementById('systemViewerNote').innerText = item.path || '';
            document.getElementById('systemViewerPath').innerText = item.path || '';
            document.getElementById('systemViewerBody').innerHTML = item.body || '<div class="status-message">Chưa có dữ liệu.</div>';
            const tail = document.querySelector('#systemViewerBody .log-tail');
            if (tail) tail.scrollTop = tail.scrollHeight;
        }

        function showVersionHistory(machine) {
            const selectedRow = Array.from(document.querySelectorAll('[data-version-machine]')).find(row => row.dataset.versionMachine === machine);
            if (!selectedRow) return;
            const alreadyOpen = selectedRow.classList.contains('active');
            document.querySelectorAll('.version-inline-history').forEach(row => row.remove());
            document.querySelectorAll('[data-version-machine]').forEach(row => {
                row.classList.remove('active');
            });
            if (alreadyOpen) return;
            selectedRow.classList.add('active');
            const rows = (window.versionHistory || []).filter(item => item.machine === machine);
            const body = rows.map(item => `<tr><td>${escapeHtml(item.time)}</td><td>${escapeHtml(item.version)}</td></tr>`).join('');
            const historyRow = document.createElement('tr');
            historyRow.className = 'version-inline-history';
            historyRow.innerHTML = `<td colspan="5">
                <div class="system-note-row"><span>Lịch sử đổi bản</span><strong>${escapeHtml(machine)} · ${rows.length} mốc gần nhất</strong></div>
                ${body ? `<table class="status-table version-history-table"><thead><tr><th>Thời gian</th><th>Phiên bản</th></tr></thead><tbody>${body}</tbody></table>` : '<div class="sidebar-note">Chưa có lịch sử đổi bản cho máy này.</div>'}
            </td>`;
            selectedRow.after(historyRow);
        }

        function selectSystemLog(index) {
            const offset = 4;
            selectSystemItem(index + offset);
        }

        function exportExcel() {
            let s = document.getElementById('erpStart').value; let e = document.getElementById('erpEnd').value; let m = document.getElementById('erpMachine').value;
            window.location.href = `/api/export_csv?start=${s}&end=${e}&machine=${m}`;
        }

        async function fetchERP() {
            if (statsFetchTimer) {
                clearTimeout(statsFetchTimer);
                statsFetchTimer = null;
            }
            let s = document.getElementById('erpStart').value; let e = document.getElementById('erpEnd').value; let m = document.getElementById('erpMachine').value;
            const requestId = ++statsRequestId;
            setReportLoading(true);
            try {
                let res = await fetch(`/api/stats?start=${s}&end=${e}&machine=${m}`);
                let data = await res.json();
                if (statsRequestId !== requestId) return;
                
                currentStatsData = data;
                statsDirty = false;
                renderCharts(data);
            } catch(e) {
                if (statsRequestId === requestId) setReportLoading(true, 'Không tải được thống kê.');
            }
        }

        function setReportLoading(isLoading, message) {
            if (!isLoading) return;
            const loadingText = message || 'Đang tải dữ liệu...';
            const total = document.getElementById('erp-total-main');
            const totalError = document.getElementById('erp-total-error-main');
            const inbat = document.getElementById('erp-inbat-value');
            const inbatError = document.getElementById('erp-inbat-error');
            const indecal = document.getElementById('erp-indecal-value');
            const indecalError = document.getElementById('erp-indecal-error');
            const cnc = document.getElementById('erp-cnc-value');
            const cncError = document.getElementById('erp-cnc-error');
            if (total) total.innerText = '...';
            if (totalError) totalError.innerText = '...';
            if (inbat) inbat.innerText = '...';
            if (inbatError) inbatError.innerText = '...';
            if (indecal) indecal.innerText = '...';
            if (indecalError) indecalError.innerText = '...';
            if (cnc) cnc.innerText = '...';
            if (cncError) cncError.innerText = '...';
            const sidebarCustomers = document.getElementById('sidebarCustomerList');
            if (sidebarCustomers) sidebarCustomers.innerHTML = `<div class="sidebar-note">${loadingText}</div>`;
            const detailTitle = document.getElementById('reportDetailTitle');
            const detailGrid = document.getElementById('reportDetailGrid');
            if (detailTitle) detailTitle.innerText = loadingText;
            if (detailGrid) detailGrid.innerHTML = '';
        }

        function renderCharts(data) {
            if (selectedReportCustomer && !data.customer_details?.[selectedReportCustomer]) selectedReportCustomer = '';
            renderStatsSummary(data);
            renderMachineFlowChart(data);
            renderCustomerSummary(data);
            renderCustomerChart(data);
            renderReportDetail(data);
        }

        function machineMetricMap(flow) {
            const result = { InBat: 0, InDecal: 0, CNC: 0 };
            (flow?.datasets || []).forEach(ds => {
                if (result[ds.machine] === undefined) result[ds.machine] = 0;
                result[ds.machine] = (ds.data || []).reduce((sum, value) => sum + Number(value || 0), 0);
            });
            return result;
        }

        function formatMetric(value) {
            return flowMetric === 'm2' ? Number(value || 0).toFixed(2) + ' m2' : String(Math.round(Number(value || 0)));
        }

        function compactFlow(flow) {
            const labels = flow?.labels || [];
            const datasets = flow?.datasets || [];
            const keepIndexes = labels.map((label, index) =>
                datasets.some(ds => Number((ds.data || [])[index] || 0) > 0) ? index : -1
            ).filter(index => index >= 0);
            if (!keepIndexes.length) return flow;
            return {
                ...flow,
                labels: keepIndexes.map(index => labels[index]),
                datasets: datasets.map(ds => ({
                    ...ds,
                    data: keepIndexes.map(index => (ds.data || [])[index] || 0)
                }))
            };
        }

        function trimOuterEmptyFlow(flow) {
            const labels = flow?.labels || [];
            const datasets = flow?.datasets || [];
            if (!labels.length || !datasets.length) return flow;
            const hasValue = (label, index) => datasets.some(ds => Number((ds.data || [])[index] || 0) > 0);
            const firstDataIndex = labels.findIndex(hasValue);
            if (firstDataIndex < 0) return flow;
            let lastDataIndex = labels.length - 1;
            while (lastDataIndex > firstDataIndex && !hasValue(labels[lastDataIndex], lastDataIndex)) {
                lastDataIndex--;
            }
            return {
                ...flow,
                labels: labels.slice(firstDataIndex, lastDataIndex + 1),
                datasets: datasets.map(ds => ({
                    ...ds,
                    data: (ds.data || []).slice(firstDataIndex, lastDataIndex + 1)
                }))
            };
        }

        function parseFlowDate(label) {
            if (!label || !String(label).includes('-')) return null;
            const date = new Date(label + 'T00:00:00');
            return Number.isNaN(date.getTime()) ? null : date;
        }

        function flowSpanDays(labels) {
            const dates = (labels || []).map(parseFlowDate).filter(Boolean);
            if (!dates.length) return 1;
            return Math.max(1, Math.round((dates[dates.length - 1] - dates[0]) / 86400000) + 1);
        }

        function flowTickLabel(label, spanDays) {
            const date = parseFlowDate(label);
            if (!date) return label;
            const day = date.getDate();
            const month = String(date.getMonth() + 1).padStart(2, '0');
            if (spanDays > 120) {
                if (day !== 1 && day !== 15) return '';
                return day <= 15 ? `01/${month}` : `15/${month}`;
            }
            if (spanDays > 45) {
                if (day !== 1 && day !== 15) return '';
                return `${String(day).padStart(2, '0')}/${month}`;
            }
            return String(date.getDate()).padStart(2, '0');
        }

        function bucketFlowForDisplay(flow) {
            const labels = flow?.labels || [];
            const datasets = flow?.datasets || [];
            const dates = labels.map(parseFlowDate).filter(Boolean);
            if (!dates.length || !datasets.length) return flow;
            const spanDays = Math.max(1, Math.round((dates[dates.length - 1] - dates[0]) / 86400000) + 1);
            const bucketLabels = [];
            const bucketIndexByLabel = {};
            labels.forEach(label => {
                const bucket = flowTickLabel(label, spanDays);
                if (bucketIndexByLabel[bucket] === undefined) {
                    bucketIndexByLabel[bucket] = bucketLabels.length;
                    bucketLabels.push(bucket);
                }
            });
            return {
                ...flow,
                labels: bucketLabels,
                datasets: datasets.map(ds => {
                    const bucketData = bucketLabels.map(() => 0);
                    labels.forEach((label, index) => {
                        const bucket = flowTickLabel(label, spanDays);
                        bucketData[bucketIndexByLabel[bucket]] += Number((ds.data || [])[index] || 0);
                    });
                    return {...ds, data: bucketData};
                })
            };
        }

        function renderStatsSummary(data) {
            const flow = selectedCustomerFlow(data, flowMetric);
            const byMachine = machineMetricMap(flow);
            const selectedDetail = selectedReportCustomer ? data.customer_details?.[selectedReportCustomer] : null;
            const summary = selectedDetail?.summary || data.summary || {};
            const errorByMachine = selectedDetail
                ? (flowMetric === 'm2' ? (selectedDetail.cancel_bad_m2_by_machine || {}) : (selectedDetail.cancel_by_machine || {}))
                : (flowMetric === 'm2' ? (data.cancel_bad_m2_by_machine || {}) : (data.cancel_by_machine || {}));
            const total = selectedDetail
                ? (flowMetric === 'm2' ? Number(selectedDetail.summary?.total_m2 || 0) : Number(selectedDetail.summary?.total_jobs || 0))
                : (flowMetric === 'm2' ? Number(data.summary?.total_m2 || 0) : Number(data.summary?.total_jobs || 0));
            const totalError = flowMetric === 'm2' ? Number(summary.cancel_bad_m2 || 0) : Number(summary.cancel_jobs || 0);
            document.getElementById('erp-total-main').innerText = formatMetric(total);
            document.getElementById('erp-total-error-main').innerText = formatMetric(totalError);
            document.getElementById('erp-inbat-value').innerText = formatMetric(byMachine.InBat);
            document.getElementById('erp-inbat-error').innerText = formatMetric(errorByMachine.InBat || 0);
            document.getElementById('erp-indecal-value').innerText = formatMetric(byMachine.InDecal);
            document.getElementById('erp-indecal-error').innerText = formatMetric(errorByMachine.InDecal || 0);
            document.getElementById('erp-cnc-value').innerText = formatMetric(byMachine.CNC);
            document.getElementById('erp-cnc-error').innerText = formatMetric(errorByMachine.CNC || 0);
        }

        function renderMachineFlowChart(data) {
            if(hourChartInst) hourChartInst.destroy();
            const canvas = document.getElementById('orderFlowChart');
            const singlePanel = document.getElementById('orderFlowSingle');
            if (!canvas) return;
            let ctxHour = canvas.getContext('2d');
            const fallbackFlow = { labels: data.hours.labels, datasets: [{ machine: "Tất cả", data: data.hours.data }] };
            const flow = trimOuterEmptyFlow(selectedCustomerFlow(data, flowMetric) || fallbackFlow);
            const spanDays = flowSpanDays(flow.labels || []);
            const pointCount = (flow.labels || []).length;
            const chartType = pointCount <= 1 ? 'bar' : 'line';
            window.lastRenderedFlowLabels = flow.labels || [];
            const title = document.getElementById('orderFlowTitle');
            if (title) {
                const baseTitle = selectedReportCustomer ? `Đơn hàng theo máy - ${selectedReportCustomer}` : 'Đơn hàng theo máy';
                title.innerText = pointCount === 1 ? `${baseTitle} · 1 mốc dữ liệu` : baseTitle;
            }
            canvas.style.display = 'block';
            if (singlePanel) {
                singlePanel.style.display = 'none';
                singlePanel.innerHTML = '';
            }
            const flowDatasets = (flow.datasets || []).map(ds => ({
                label: ds.machine,
                data: ds.data,
                borderColor: machineColor(ds.machine),
                backgroundColor: chartType === 'bar' ? machineColor(ds.machine) + "cc" : machineColor(ds.machine) + "22",
                tension: 0.35,
                fill: false,
                pointRadius: pointCount <= 1 ? 5 : (spanDays > 45 ? 0 : 3),
                pointHoverRadius: 6,
                borderWidth: chartType === 'bar' ? 1 : 3,
                borderRadius: chartType === 'bar' ? 4 : 0,
                maxBarThickness: pointCount <= 1 ? 86 : 56,
                barPercentage: pointCount <= 1 ? 0.8 : 0.9,
                categoryPercentage: pointCount <= 1 ? 0.7 : 0.8
            }));
            hourChartInst = new Chart(ctxHour, {
                type: chartType,
                data: { labels: flow.labels || [], datasets: flowDatasets },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { display: true, position: 'top', labels: { boxWidth: 12, font: { size: 11 } } } },
                    scales: {
                        y: { beginAtZero: true, ticks: { precision: flowMetric === 'm2' ? 1 : 0 }, title: { display: true, text: flowMetric === 'm2' ? 'm2' : 'Số lượng' }, grid: { color: '#333' } },
                        x: {
                            ticks: { autoSkip: false, maxRotation: 0, callback: function(value) { return flowTickLabel(this.getLabelForValue(value), spanDays); } },
                            grid: { color: function(context) { return flowTickLabel(context.chart.data.labels[context.index], spanDays) ? '#222' : 'transparent'; } }
                        }
                    }
                }
            });
        }

        function currentCustomerSeries(data) {
            return flowMetric === 'm2' ? (data.customers_m2 || {labels: [], data: []}) : (data.customers || {labels: [], data: []});
        }

        function selectedCustomerFlow(data, metric) {
            if (selectedReportCustomer && data.customer_details?.[selectedReportCustomer]) {
                return metric === 'm2'
                    ? data.customer_details[selectedReportCustomer].machine_flow_m2
                    : data.customer_details[selectedReportCustomer].machine_flow;
            }
            return metric === 'm2' ? (data.machine_flow_m2 || null) : (data.machine_flow || null);
        }

        function renderCustomerSummary(data) {
            const list = document.getElementById('sidebarCustomerList');
            const full = document.getElementById('customerFullList');
            const series = currentCustomerSeries(data);
            const labels = series.labels || [];
            const values = series.data || [];
            const rows = labels.map((label, index) => ({ label, value: Number(values[index] || 0) }));
            const formatCustomerValue = value => flowMetric === 'm2' ? value.toFixed(2) + ' m2' : String(Math.round(value));
            const renderRow = row => `<div class="customer-row" title="${escapeHtml(row.label)}"><span>${escapeHtml(row.label)}</span><strong>${formatCustomerValue(row.value)}</strong></div>`;
            if (list) list.innerHTML = rows.length ? rows.slice(0, 5).map(renderRow).join('') : '<div class="sidebar-note">Chưa có khách trong bộ lọc.</div>';
            if (full) full.innerHTML = rows.length ? rows.map(renderRow).join('') : '<div class="sidebar-note">Chưa có dữ liệu khách hàng.</div>';
        }

        function renderCustomerChart(data) {
            const series = currentCustomerSeries(data);
            const labels = (series.labels || []).slice(0, 10);
            const values = (series.data || []).slice(0, 10);
            const chartData = {
                labels: labels,
                datasets: [{
                    label: flowMetric === 'm2' ? 'm2' : 'Số đơn',
                    data: values,
                    backgroundColor: '#3b82f6cc',
                    borderColor: '#3b82f6',
                    borderWidth: 1,
                    borderRadius: 6
                }]
            };
            const chartOptions = {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                onClick: (event, elements) => {
                    if (!elements.length) return;
                    const index = elements[0].index;
                    selectReportCustomer(labels[index]);
                },
                scales: {
                    y: { beginAtZero: true, ticks: { precision: flowMetric === 'm2' ? 1 : 0 }, title: { display: true, text: flowMetric === 'm2' ? 'm2' : 'Số lượng' }, grid: { color: '#333' } },
                    x: { grid: { display: false }, ticks: { autoSkip: false, maxRotation: 25, minRotation: 0 } }
                }
            };
            const canvas = document.getElementById('customerChart');
            if (canvas) {
                if(cusChartInst) cusChartInst.destroy();
                cusChartInst = new Chart(canvas.getContext('2d'), {
                    type: 'bar',
                    data: chartData,
                    options: chartOptions
                });
            }
            const flowCanvas = document.getElementById('flowCustomerChart');
            if (flowCanvas) {
                if(flowCustomerChartInst) flowCustomerChartInst.destroy();
                flowCustomerChartInst = new Chart(flowCanvas.getContext('2d'), {
                    type: 'bar',
                    data: chartData,
                    options: chartOptions
                });
            }
        }

        function selectReportCustomer(customer) {
            selectedReportCustomer = selectedReportCustomer === customer ? '' : customer;
            if (currentStatsData) renderCharts(currentStatsData);
        }

        function clearCustomerFilter() {
            selectedReportCustomer = '';
            if (currentStatsData) renderCharts(currentStatsData);
        }

        function renderReportDetail(data) {
            const title = document.getElementById('reportDetailTitle');
            const grid = document.getElementById('reportDetailGrid');
            const clearBtn = document.getElementById('clearCustomerFilterBtn');
            if (!title || !grid) return;
            const detail = selectedReportCustomer ? data.customer_details?.[selectedReportCustomer] : null;
            const summary = detail?.summary || data.summary || {};
            const byMachine = detail
                ? (flowMetric === 'm2' ? (detail.by_machine_m2 || {}) : (detail.by_machine || {}))
                : machineMetricMap(flowMetric === 'm2' ? data.machine_flow_m2 : data.machine_flow);
            title.innerText = selectedReportCustomer ? `Chỉ số khách: ${selectedReportCustomer}` : 'Chỉ số theo bộ lọc hiện tại';
            if (clearBtn) clearBtn.style.display = selectedReportCustomer ? 'inline-flex' : 'none';
            const mainValue = flowMetric === 'm2' ? Number(summary.total_m2 || 0).toFixed(2) + ' m2' : String(Math.round(Number(summary.total_jobs || 0)));
            grid.innerHTML = `
                <div class="report-metric"><span>${flowMetric === 'm2' ? 'Tổng m2' : 'Tổng đơn'}</span><strong>${mainValue}</strong></div>
                <div class="report-metric"><span>InBat</span><strong>${formatMetric(byMachine.InBat || 0)}</strong></div>
                <div class="report-metric"><span>InDecal</span><strong>${formatMetric(byMachine.InDecal || 0)}</strong></div>
                <div class="report-metric"><span>CNC</span><strong>${formatMetric(byMachine.CNC || 0)}</strong></div>
                <div class="report-metric"><span>Lỗi m2</span><strong>${Number(summary.cancel_rate || 0).toFixed(1)}%</strong></div>
                <div class="report-metric"><span>M2 hỏng</span><strong>${Number(summary.cancel_bad_m2 || 0).toFixed(2)} m2</strong></div>
                <div class="report-metric"><span>Lỗi thật</span><strong>${Math.round(Number(summary.cancel_jobs || 0))}</strong></div>
                <div class="report-metric"><span>In lại cần xem</span><strong>${Math.round(Number(summary.reprint_jobs || 0))}</strong></div>
            `;
        }

        // ================= BOARD LOGIC =================
        let allData = { EXPORTED: [], RIP: [], RUNNING: [], DONE: [], CANCELED: [], REMOVED: [] };
        let previewPinned = false;
        let previewHoverCard = null;
        let currentPreviewFile = null;

        window.onclick = function(event) {
            let loginModal = document.getElementById('loginModal'); let detailModal = document.getElementById('detailModal');
            if (event.target == loginModal || event.target == detailModal) closeModals();
            if (!event.target.closest('.card') && !event.target.closest('#cardPreview')) hideCardPreview(true);
        }

        function hideCardPreview(force=false) {
            if (previewPinned && !force) return;
            const preview = document.getElementById('cardPreview');
            preview.style.display = 'none';
            preview.classList.remove('pinned');
            previewPinned = false;
            previewHoverCard = null;
            currentPreviewFile = null;
        }

        function syncPreviewAdminActions() {
            const actionEl = document.getElementById('cardPreviewActions');
            if (!actionEl) return;
            actionEl.classList.toggle('has-admin', Boolean(currentPreviewFile && localStorage.getItem("admin_pin")));
        }

        function escapeHtml(value) {
            return String(value ?? '').replace(/[&<>"']/g, function(ch) {
                return ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'})[ch];
            });
        }

        function findCardFile(card) {
            const cardHash = card.dataset.hash || "";
            for (let k in allData) {
                if (k === "ATTENTION" || k === "COUNTS") continue;
                let found = cardHash
                    ? (allData[k] || []).find(f => (f.hash || "") === cardHash)
                    : (allData[k] || []).find(f => f.machine === card.dataset.machine && f.name === card.dataset.name);
                if (found) return { file: found, statusKey: k };
            }
            return { file: null, statusKey: '' };
        }

        function statusLabel(statusKey) {
            if (statusKey === "EXPORTED") return "Xuất file";
            if (statusKey === "RIP") return "Đã RIP";
            if (statusKey === "RUNNING") return "Đang chạy";
            if (statusKey === "DONE") return "Đã xong";
            if (statusKey === "CANCELED") return "Lỗi/Hủy khi chạy";
            if (statusKey === "REMOVED") return "Xóa thao tác";
            return "Chưa rõ";
        }

        function clientJobCore(name) {
            return String(name || '').toLowerCase().trim().replace(/^\d+~/, '');
        }

        function clientJobTokens(name) {
            const core = clientJobCore(name).replace(/\.[a-z0-9]+$/, '');
            return core.split(/[^a-z0-9]+/)
                .filter(token => token.length >= 2 && !['copy', 'new', 'folder', 'final', 'file'].includes(token));
        }

        function clientJobsRelated(oldName, doneName) {
            if (clientJobCore(oldName) === clientJobCore(doneName)) return true;
            const oldTokens = clientJobTokens(oldName);
            const doneTokens = new Set(clientJobTokens(doneName));
            if (oldTokens.length < 2) return false;
            if (!oldTokens.every(token => doneTokens.has(token))) return false;
            return oldTokens.some(token => /\d/.test(token));
        }

        function sanitizeBoardData(data) {
            const clean = data || {};
            const doneItems = clean.DONE || [];
            const shouldHideDoneCleanup = item => {
                const type = String(item.cancel_type || '').toLowerCase();
                if (type === 'source_renamed_done' || type === 'done_cleanup') return true;
                const machine = String(item.machine || '').toLowerCase();
                const removedTime = String(item.updated || '');
                return doneItems.some(done => (
                    String(done.machine || '').toLowerCase() === machine
                    && String(done.updated || '') >= removedTime
                    && clientJobsRelated(item.name, done.name)
                ));
            };
            clean.CANCELED = (clean.CANCELED || []).filter(item => !shouldHideDoneCleanup(item));
            clean.REMOVED = (clean.REMOVED || []).filter(item => !shouldHideDoneCleanup(item));
            return clean;
        }

        function eventLabel(eventName, machine) {
            const actionText = machine === "CNC" ? "Cắt" : "In";
            if (eventName === "EXPORT" || eventName === "WRONG_DAY") return "Xuất file";
            if (eventName === "RIP") return "Đã RIP";
            if (eventName === "PRINTING" || eventName === "CUTTING") return "Đang " + actionText.toLowerCase();
            if (eventName === "DONE") return "Hoàn tất";
            if (eventName === "DELETE" || eventName === "ADMIN_DELETE") return "Xóa/Hủy";
            if (eventName === "ADMIN_DONE") return "Quản trị: chốt xong";
            if (eventName === "ADMIN_EXPORT") return "Quản trị: trả về xuất lại";
            return eventName || "Sự kiện";
        }

        function machineMetaRows(file) {
            const meta = file.machine_meta || {};
            let rows = "";
            const area = Number(meta.area_m2 || 0);
            if (area > 0) {
                rows += `<div class="preview-row"><span>Kích thước</span><strong>${area.toFixed(2)} m2</strong></div>`;
            }
            const widthCm = Number(meta.width_cm || 0);
            const heightCm = Number(meta.height_cm || 0);
            if (widthCm > 0 && heightCm > 0) {
                rows += `<div class="preview-row"><span>Khổ ảnh</span><strong>${widthCm.toFixed(1)} x ${heightCm.toFixed(1)} cm</strong></div>`;
            }
            const widthMm = Number(meta.width_mm || 0);
            const heightMm = Number(meta.height_mm || 0);
            if (widthMm > 0 && heightMm > 0) {
                rows += `<div class="preview-row"><span>Khổ cắt</span><strong>${(widthMm / 10).toFixed(1)} x ${(heightMm / 10).toFixed(1)} cm</strong></div>`;
            }
            if (meta.line_count) {
                rows += `<div class="preview-row" title="Số dòng lệnh cắt trong file TAP"><span>Dòng cắt</span><strong>${Number(meta.line_count).toLocaleString('vi-VN')} dòng</strong></div>`;
            }
            if (meta.feed_min || meta.feed_max) {
                rows += `<div class="preview-row" title="Tốc độ chạy dao trong file CNC"><span>Tốc độ cắt</span><strong>${escapeHtml(meta.feed_min || '')} - ${escapeHtml(meta.feed_max || '')}</strong></div>`;
            }
            if (meta.dpi_x || meta.dpi_y) {
                rows += `<div class="preview-row"><span>DPI</span><strong>${Number(meta.dpi_x || 0).toFixed(0)} x ${Number(meta.dpi_y || 0).toFixed(0)}</strong></div>`;
            }
            if (meta.source_kind) {
                const label = meta.source_kind === 'rip_preview_bmp' ? 'Ảnh RIP BMP' : meta.source_kind;
                rows += `<div class="preview-row"><span>Nguồn</span><strong>${escapeHtml(label)}</strong></div>`;
            }
            return rows;
        }

        function renderPreviewDetails(card) {
            const nameEl = document.getElementById('cardPreviewName');
            const statusEl = document.getElementById('cardPreviewStatus');
            const timelineEl = document.getElementById('cardPreviewTimeline');
            const found = findCardFile(card);
            const file = found.file;
            currentPreviewFile = file || null;
            syncPreviewAdminActions();
            if (!file) {
                nameEl.innerText = card.dataset.name || "";
                statusEl.innerText = "Không tìm thấy dữ liệu chi tiết";
                timelineEl.innerHTML = "";
                return;
            }

            nameEl.innerText = `${file.machine || ""} | ${file.name || ""}`;
            const runInfo = Number(file.run || 1) > 1 ? " | Số lần: " + file.run : "";
            const progressInfo = file.progress_label ? " | " + file.progress_label : "";
            statusEl.innerText = `${runInfo}${progressInfo}`.replace(/^ \| /, '');
            statusEl.style.display = statusEl.innerText ? 'block' : 'none';

            let hist = [];
            try { hist = JSON.parse(file.history || '[]'); } catch(e) {}
            let extraRows = "";
            if (file.estimated_bad_m2) {
                extraRows += `<div class="preview-row"><span>Ước tính</span><strong>Hỏng khoảng ${Number(file.estimated_bad_m2).toFixed(2)} m2</strong></div>`;
            }
            extraRows += machineMetaRows(file);
            if (!hist.length) {
                timelineEl.innerHTML = extraRows + '<div class="preview-row"><span>--:--</span><strong>Chưa có nhật ký chi tiết</strong></div>';
                return;
            }

            let lastStart = null;
            const previewEvents = hist.filter(h => h.event !== "EXPORT" && h.event !== "WRONG_DAY");
            if (!previewEvents.length && !extraRows) {
                timelineEl.innerHTML = "";
                return;
            }
            timelineEl.innerHTML = extraRows + previewEvents.slice(-8).map(h => {
                const time = String(h.time || '').split(' ')[1] || '';
                let label = h.reason || eventLabel(h.event, file.machine);
                if (label === "Xuất file") return "";
                let duration = '';
                if (h.event === 'PRINTING' || h.event === 'CUTTING') lastStart = h.time;
                if (h.event === 'DONE' && lastStart) {
                    duration = ' - ' + calculateDurationRaw(lastStart, h.time);
                    lastStart = null;
                }
                return `<div class="preview-row"><span>${escapeHtml(time)}</span><strong>${escapeHtml(label + duration)}</strong></div>`;
            }).join('');
        }

        function positionCardPreview(card) {
            const preview = document.getElementById('cardPreview');
            const rect = card.getBoundingClientRect();
            const gap = 10;
            const margin = 8;
            const previewWidth = preview.offsetWidth || 340;
            const maxPreviewHeight = Math.max(160, window.innerHeight - (margin * 2));
            preview.style.maxHeight = maxPreviewHeight + 'px';

            const showRight = rect.right + previewWidth + gap <= window.innerWidth - margin;
            let leftViewport = showRight ? rect.right + gap : rect.left - previewWidth - gap;
            const maxLeft = Math.max(margin, window.innerWidth - previewWidth - margin);
            leftViewport = Math.min(Math.max(margin, leftViewport), maxLeft);

            const previewHeight = Math.min(preview.scrollHeight || preview.offsetHeight || 260, maxPreviewHeight);
            let topViewport = Math.max(margin, rect.top);
            if (topViewport + previewHeight > window.innerHeight - margin) {
                topViewport = window.innerHeight - previewHeight - margin;
            }
            topViewport = Math.max(margin, topViewport);

            preview.style.left = (window.scrollX + leftViewport) + 'px';
            preview.style.top = (window.scrollY + topViewport) + 'px';
        }

        function showCardPreview(card, src, title, meta, pin=false) {
            if (!src && !pin) return;
            const preview = document.getElementById('cardPreview');
            const img = document.getElementById('cardPreviewImg');
            const empty = document.getElementById('cardPreviewEmpty');
            const details = document.getElementById('cardPreviewDetails');
            img.style.display = src ? 'block' : 'none';
            empty.style.display = src ? 'none' : 'flex';
            details.style.display = pin ? 'block' : 'none';
            img.onload = function() {
                if (img.naturalWidth > 0) {
                    img.style.display = 'block';
                    empty.style.display = 'none';
                }
                positionCardPreview(card);
            };
            img.onerror = function() {
                img.style.display = 'none';
                empty.style.display = 'flex';
                positionCardPreview(card);
            };
            img.src = src || '';
            if (pin) renderPreviewDetails(card);

            preview.scrollTop = 0;
            preview.style.display = 'block';
            previewPinned = pin;
            previewHoverCard = pin ? null : card;
            preview.classList.toggle('pinned', pin);
            positionCardPreview(card);
        }

        document.addEventListener('mousemove', function(event) {
            if (previewPinned) return;
            const card = event.target.closest('.card');
            if (card && card.dataset.thumb) {
                if (card !== previewHoverCard) {
                    showCardPreview(card, card.dataset.thumb, card.dataset.title, card.dataset.meta, false);
                }
                return;
            }
            if (!event.target.closest('#cardPreview')) hideCardPreview(false);
        });

        function connectWebSocket() {
            const ws = new WebSocket("ws://" + window.location.hostname + ":8000/ws/dashboard");
            const statusEl = document.getElementById('socket-status');
            ws.onopen = function() { stopFallbackPolling(); statusEl.innerText = "Trực tiếp: Bật"; statusEl.className = "status-on"; fetchData(); fetchV2Status(); scheduleStatsFetch(900); };
            ws.onmessage = function(event) { 
                if(event.data === "NEW_DATA") { fetchData(); fetchV2Status(); scheduleStatsFetch(currentMainTab === 'flow' ? 250 : 1200); }
            };
            ws.onerror = function() { startFallbackPolling(); };
            ws.onclose = function() { statusEl.innerText = "Mất realtime"; statusEl.className = "status-off"; startFallbackPolling(); setTimeout(connectWebSocket, 3000); };
        }

        let fallbackPollTimer = null;
        function startFallbackPolling() {
            if (fallbackPollTimer) return;
            fetchData(); fetchV2Status(); scheduleStatsFetch(900);
            fallbackPollTimer = setInterval(() => {
                fetchData(); fetchV2Status(); scheduleStatsFetch(currentMainTab === 'flow' ? 250 : 1200);
            }, 10000);
        }

        function stopFallbackPolling() {
            if (!fallbackPollTimer) return;
            clearInterval(fallbackPollTimer);
            fallbackPollTimer = null;
        }

        function checkAuthUI() {
            let pin = localStorage.getItem("admin_pin"); let btn = document.getElementById("authBtn");
            btn.innerText = "⚙";
            btn.title = pin ? "Đã đăng nhập quản trị - bấm để đăng xuất" : "Đăng nhập quản trị";
            btn.setAttribute("aria-label", btn.title);
            if (pin) { btn.classList.add("btn-logout"); } 
            else { btn.classList.remove("btn-logout"); }
            syncPreviewAdminActions();
        }

        function toggleAuth() {
            if (localStorage.getItem("admin_pin")) { if(confirm("Xác nhận đăng xuất?")) { localStorage.removeItem("admin_pin"); checkAuthUI(); } } 
            else { document.getElementById('loginModal').style.display = 'block'; document.getElementById('pin-input').focus(); }
        }

        async function submitLogin() {
            let pin = document.getElementById('pin-input').value; if(!pin) return;
            try {
                let res = await fetch('/api/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ pin: pin }) });
                let result = await res.json();
                if(result.success) { localStorage.setItem("admin_pin", pin); closeModals(); checkAuthUI(); } 
                else { alert("Sai mã PIN."); document.getElementById('pin-input').value = ''; document.getElementById('pin-input').focus(); }
            } catch (e) { alert("Lỗi kết nối."); }
        }

        document.getElementById("pin-input").addEventListener("keypress", function(e) { if (e.key === "Enter") submitLogin(); });

        function closeModals() { document.getElementById('loginModal').style.display = 'none'; document.getElementById('detailModal').style.display = 'none'; document.getElementById('pin-input').value = ''; }

        function calculateDurationRaw(startStr, endStr) {
            let t1 = new Date(startStr); let t2 = new Date(endStr); let diffMs = t2 - t1;
            if (diffMs < 0) return "0 phút";
            let diffMins = Math.floor(diffMs / 60000);
            if (diffMins < 60) return diffMins + " phút";
            return Math.floor(diffMins / 60) + "g " + (diffMins % 60) + "p";
        }

        // Safe filename area parser.
        function parseArea(filename) {
            if (!filename) return 0;
            let m2 = 0; let f = String(filename).toLowerCase(); 
            let dimMatch = f.match(/(\d{2,4})\s*[xX]\s*(\d{2,4})/);
            if (dimMatch) { m2 = (parseInt(dimMatch[1]) * parseInt(dimMatch[2])) / 10000; }
            return m2;
        }

        function openDetailModal(machine, realName) {
            let file = null; let statusName = "Chưa rõ";
            for(let k in allData) {
                if(k === "ATTENTION" || k === "COUNTS") continue;
                let found = allData[k].find(f => f.machine === machine && f.name === realName);
                if(found) { file = found; 
                    if(k==="EXPORTED") statusName="Xuất file"; if(k==="RIP") statusName="Đã RIP"; if(k==="RUNNING") statusName="Đang chạy"; if(k==="DONE") statusName="Đã xong"; if(k==="CANCELED") statusName="Lỗi/Hủy khi chạy"; if(k==="REMOVED") statusName="Xóa thao tác"; break; 
                }
            }
            if(!file) return;

            document.getElementById('dt-badge').innerText = file.machine; document.getElementById('dt-badge').className = "badge badge-" + file.machine;
            document.getElementById('dt-name').innerText = file.name; document.getElementById('dt-status').innerText = statusName;
            
            let actionText = (file.machine === "CNC") ? "Cắt" : "In";
            let m2 = parseArea(file.name); let totalM2 = m2 > 0 ? (m2 * file.run).toFixed(2) + " m2" : "N/A";
            document.getElementById('dt-m2').innerHTML = totalM2 + (file.run > 1 ? ` <span style="color:${STAGE_COLORS.EXPORT}; font-size:11px;">(${actionText} x${file.run})</span>` : "");

            document.getElementById('modal-machine-name').value = file.machine; document.getElementById('modal-real-name').value = file.name;
            document.getElementById('modal-file-hash').value = file.hash || '';

            let hist = []; try { hist = JSON.parse(file.history || '[]'); } catch(e){}
            let html = '';
            if(hist.length === 0) { html = '<div style="color:#aaa; font-size:11px; margin-top:10px; font-style:italic;">Không có nhật ký chi tiết.</div>'; } 
            else {
                html = '<div class="timeline">'; 
                let lastStartTime = null; let runCounter = 0; let doneCounter = 0;
                
                hist.forEach(h => {
                    let desc = h.event; let durHtml = ""; let color = "#fff"; let tlClass = "tl-export";
                    if(h.event === 'EXPORT' || h.event === 'WRONG_DAY') { desc = "Xuất file"; color = STAGE_COLORS.EXPORT; tlClass = "tl-export"; }
                    else if(h.event === 'RIP') { desc = "Đã RIP"; color = STAGE_COLORS.RIP; tlClass = "tl-rip"; }
                    else if(h.event === 'PRINTING' || h.event === 'CUTTING') { 
                        runCounter++; desc = `Đang ${actionText.toLowerCase()} (L${runCounter})`; color = STAGE_COLORS.RUN; tlClass = "tl-run"; lastStartTime = h.time; 
                    }
                    else if(h.event === 'DONE') { 
                        doneCounter++; let l_text = runCounter > 0 ? ` (L${doneCounter})` : "";
                        desc = `Hoàn tất${l_text}`; color = STAGE_COLORS.DONE; tlClass = "tl-done"; 
                        if(lastStartTime) { durHtml = `<div class="tl-duration">${calculateDurationRaw(lastStartTime, h.time)}</div>`; lastStartTime = null; } 
                    }
                    else if(h.event === 'DELETE' || h.event === 'ADMIN_DELETE') { desc = h.reason || "Xóa/Hủy"; color = h.cancel_type === "source_delete" ? STAGE_COLORS.REMOVED : STAGE_COLORS.CANCEL; tlClass = "tl-cancel"; }
                    else if(h.event === 'ADMIN_DONE') { desc = "Quản trị: chốt xong"; color = STAGE_COLORS.DONE; tlClass = "tl-done"; }
                    else if(h.event === 'ADMIN_EXPORT') { desc = "Quản trị: trả về xuất lại"; color = STAGE_COLORS.EXPORT; tlClass = "tl-export"; }

                    html += `<div class="tl-item ${tlClass}"><div class="tl-time">${h.time.split(" ")[1]}</div><div class="tl-desc" style="color: ${color};">${desc}</div>${durHtml}</div>`;
                });
                html += '</div>';
            }
            document.getElementById('dt-timeline-container').innerHTML = html;
            document.getElementById('adminArea').style.display = localStorage.getItem("admin_pin") ? "block" : "none";
            document.getElementById('detailModal').style.display = 'block';
        }

        async function forceUpdate(newStatus) {
            let machine = document.getElementById('modal-machine-name').value; let fileName = document.getElementById('modal-real-name').value; let fileHash = document.getElementById('modal-file-hash').value; let pin = localStorage.getItem("admin_pin");
            if (!pin) { alert("Phiên đăng nhập hết hạn."); closeModals(); toggleAuth(); return; }
            try {
                let res = await fetch('/api/update_status', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ machine: machine, name: fileName, hash: fileHash, status: newStatus, pin: pin }) });
                let result = await res.json();
                if(result.success) { closeModals(); fetchData(); } else { alert("Lỗi: " + result.error); if(result.error.includes("PIN")) { localStorage.removeItem("admin_pin"); checkAuthUI(); } }
            } catch (error) { alert("Lỗi kết nối."); }
        }

        async function previewForceUpdate(newStatus) {
            const file = currentPreviewFile;
            const pin = localStorage.getItem("admin_pin");
            if (!pin) { hideCardPreview(true); toggleAuth(); return; }
            if (!file) { alert("Không tìm thấy file đang chọn."); return; }
            try {
                let res = await fetch('/api/update_status', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ machine: file.machine, name: file.name, hash: file.hash || "", status: newStatus, pin: pin })
                });
                let result = await res.json();
                if (result.success) {
                    hideCardPreview(true);
                    fetchData();
                } else {
                    alert("Lỗi: " + result.error);
                    if (result.error.includes("PIN")) { localStorage.removeItem("admin_pin"); checkAuthUI(); }
                }
            } catch (error) { alert("Lỗi kết nối."); }
        }

        function createCard(file) {
            let safeName = String(file.name || "Không_Tên").replace(/'/g, "\\'").replace(/"/g, '&quot;');
            let attrName = String(file.name || "Không_Tên").replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
            let attrHash = String(file.hash || "").replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
            let actionText = (file.machine === "CNC") ? "Cắt" : "In";
            let expectedRuns = Number(file.expected_runs || 1);
            let runBadge = file.run > 1 ? `<span class="badge-run">${actionText}: ${file.run}</span>` : '';
            let qtyBadge = expectedRuns > 1 ? `<span class="badge-run" style="background:#1f6feb;">SL đúng: ${expectedRuns}</span>` : '';
            let reasonBadge = file.cancel_reason ? `<div class="card-time" style="color:#ffcc66;">${file.cancel_reason}</div>` : '';
            let showReviewBadge = file.reprint_needs_review && file.reprint_label && file.reprint_label !== file.cancel_reason;
            let reviewBadge = showReviewBadge ? `<div class="card-time" style="color:#ff7777;">${file.reprint_label}</div>` : '';
            let progressText = file.progress_label ? escapeHtml(file.progress_label) : '';
            let badM2 = Number(file.estimated_bad_m2 || 0);
            let progressBadge = progressText ? `<div class="card-progress"><strong>${progressText}</strong>${badM2 > 0 ? ` | Hỏng ~${badM2.toFixed(2)} m2` : ''}</div>` : '';
            let thumbSrc = file.hash ? `/thumbs/${file.hash}.jpg` : '';
            let meta = `${file.machine || ''} ${file.time_short || ''}`.trim();
            let stageChip = file.stage_label ? `<span class="stage-chip">${escapeHtml(file.stage_label)}</span>` : '';

            return `
                <div class="card" data-machine="${file.machine}" data-name="${attrName}" data-hash="${attrHash}" data-thumb="${thumbSrc}" data-title="${attrName}" data-meta="${meta}">
                    <div class="card-main">
                        <div class="card-title">${file.name || "Không_Tên"}</div>
                        ${stageChip}
                        <div class="card-time">${file.time_short || ''}</div>
                    </div>
                    ${progressBadge}
                    <div class="card-extra">
                        <span class="badge badge-${file.machine}">${file.machine}</span>
                        ${runBadge}
                        ${qtyBadge}
                        ${reasonBadge}
                        ${reviewBadge}
                    </div>
                </div>
            `;
        }

        function renderCardList(items, totalCount) {
            const visible = items || [];
            const total = Number(totalCount ?? visible.length);
            const hiddenCount = Math.max(0, total - visible.length);
            const shouldShowMore = hiddenCount > 0 && visible.length >= Math.max(1, boardVisibleLimit - 1);
            const more = shouldShowMore
                ? `<button type="button" class="list-more-note" onclick="loadMoreBoard(event)">Còn ${hiddenCount.toLocaleString('vi-VN')} thẻ cũ hơn - bấm hoặc cuộn để tải</button>`
                : '';
            return visible.map(f => createCard(f)).join('') + more;
        }

        function boardCount(key, fallback) {
            const counts = allData.COUNTS || {};
            return Number(counts[key] ?? fallback ?? 0);
        }

        function attachBoardScrollLoaders() {
            const ids = ['queue-list', 'done-compact-list', 'true-problem-list', 'removed-problem-list'];
            ids.forEach(id => {
                const el = document.getElementById(id);
                if (!el || el.dataset.scrollBound === '1') return;
                el.dataset.scrollBound = '1';
                el.addEventListener('scroll', () => {
                    if (activeDataRequests > 0) return;
                    const nearBottom = el.scrollTop + el.clientHeight >= el.scrollHeight - 80;
                    if (!nearBottom) return;
                    const hasMore =
                        (id === 'queue-list' && (allData.EXPORTED.length + allData.RIP.length + allData.RUNNING.length) < boardCount('QUEUE')) ||
                        (id === 'done-compact-list' && allData.DONE.length < boardCount('DONE')) ||
                        (id === 'true-problem-list' && allData.CANCELED.length < boardCount('CANCELED')) ||
                        (id === 'removed-problem-list' && allData.REMOVED.length < boardCount('REMOVED'));
                    if (!hasMore) return;
                    loadMoreBoard();
                });
            });
        }

        function loadMoreBoard(event) {
            if (event) {
                event.preventDefault();
                event.stopPropagation();
            }
            if (activeDataRequests > 0) return;
            boardVisibleLimit += BOARD_PAGE_INCREMENT;
            fetchData();
        }

        function attachCardPreviewEvents() {
            document.querySelectorAll('.card').forEach(card => {
                if (card.dataset.previewBound === '1') return;
                card.dataset.previewBound = '1';
                card.addEventListener('mouseenter', () => {
                    if (previewPinned) return;
                    showCardPreview(card, card.dataset.thumb, card.dataset.title, card.dataset.meta, false);
                });
                card.addEventListener('mouseleave', () => hideCardPreview(false));
                card.addEventListener('click', (event) => {
                    event.stopPropagation();
                    showCardPreview(card, card.dataset.thumb, card.dataset.title, card.dataset.meta, true);
                });
            });
        }

        function renderAttention(filter) {
            const panel = document.getElementById('attention-panel');
            const list = document.getElementById('attention-list');
            const count = document.getElementById('attention-count');
            const filterFn = item => filter === 'ALL' || item.machine === filter;
            const items = (allData.ATTENTION || []).filter(filterFn);
            panel.classList.toggle('has-items', items.length > 0);
            count.innerText = `${items.length} việc`;
            const badge = document.getElementById('attentionBadge');
            const tabCount = document.getElementById('attentionTabCount');
            if (badge) {
                badge.innerText = items.length;
                badge.classList.toggle('has-items', items.length > 0);
            }
            if (tabCount) tabCount.innerText = items.length;
            if (!items.length) {
                list.innerHTML = '';
                return;
            }
            const renderAttentionItem = item => {
                const severity = item.severity || 'warning';
                const machine = escapeHtml(item.machine || '');
                const name = escapeHtml(item.name || '');
                return `
                    <div class="attention-item ${severity}" data-machine="${machine}" data-name="${name}" title="Bấm để xem chi tiết">
                        <div class="attention-title">${escapeHtml(item.title)}</div>
                        <div class="attention-meta">${machine} · ${name}</div>
                        <div class="attention-reason">${escapeHtml(item.reason || '')}</div>
                    </div>
                `;
            };
            list.innerHTML = items.map(renderAttentionItem).join('');
            list.querySelectorAll('.attention-item').forEach(item => {
                item.addEventListener('click', () => openDetailModal(item.dataset.machine, item.dataset.name));
            });
        }

        function renderData() {
            try {
                allData = sanitizeBoardData(allData);
                let filter = document.getElementById('erpMachine').value;
                let filterFn = f => filter === 'ALL' || f.machine === filter;
                
                // Avoid crash when file data is null.
                let sortFn = (a, b) => (b.updated || "").localeCompare(a.updated || "");
                
                let fExport = (allData.EXPORTED || []).filter(filterFn).sort(sortFn); let fRip = (allData.RIP || []).filter(filterFn).sort(sortFn); let fRun = (allData.RUNNING || []).filter(filterFn).sort(sortFn); let fDone = (allData.DONE || []).filter(filterFn).sort(sortFn); let fCancel = (allData.CANCELED || []).filter(filterFn).sort(sortFn); let fRemoved = (allData.REMOVED || []).filter(filterFn).sort(sortFn);
                renderAttention(filter);

                const queueItems = fExport.map(f => ({...f, stage_label: 'Xuất'}))
                    .concat(fRip.map(f => ({...f, stage_label: 'RIP'})))
                    .concat(fRun.map(f => ({...f, stage_label: 'Đang chạy'})))
                    .sort(sortFn);
                const trueProblemItems = fCancel.map(f => ({...f, stage_label: 'Lỗi'})).sort(sortFn);
                const removedProblemItems = fRemoved.map(f => ({...f, stage_label: 'Xóa'})).sort(sortFn);
                const problemItems = trueProblemItems.concat(removedProblemItems).sort(sortFn);
                document.getElementById('queue-list').innerHTML = renderCardList(queueItems, boardCount('QUEUE', queueItems.length));
                document.getElementById('done-compact-list').innerHTML = renderCardList(fDone, boardCount('DONE', fDone.length));
                document.getElementById('true-problem-list').innerHTML = renderCardList(trueProblemItems, boardCount('CANCELED', trueProblemItems.length));
                document.getElementById('removed-problem-list').innerHTML = renderCardList(removedProblemItems, boardCount('REMOVED', removedProblemItems.length));
                document.getElementById('true-problem-section')?.classList.toggle('is-empty', trueProblemItems.length === 0 && problemItems.length > 0);
                document.getElementById('removed-problem-section')?.classList.toggle('is-empty', removedProblemItems.length === 0 && problemItems.length > 0);

                document.getElementById('exported-list').innerHTML = renderCardList(fExport, boardCount('EXPORTED', fExport.length));
                document.getElementById('rip-list').innerHTML = renderCardList(fRip, boardCount('RIP', fRip.length));
                document.getElementById('run-list').innerHTML = renderCardList(fRun, boardCount('RUNNING', fRun.length));
                document.getElementById('done-list').innerHTML = renderCardList(fDone, boardCount('DONE', fDone.length));
                document.getElementById('cancel-list').innerHTML = renderCardList(fCancel, boardCount('CANCELED', fCancel.length));
                document.getElementById('removed-list').innerHTML = renderCardList(fRemoved, boardCount('REMOVED', fRemoved.length));
                attachCardPreviewEvents();
                attachBoardScrollLoaders();

                const compactCounts = [
                    ['queue-list', boardCount('QUEUE', queueItems.length)],
                    ['done-compact-list', boardCount('DONE', fDone.length)],
                    ['true-problem-list', boardCount('PROBLEM', problemItems.length)],
                ];
                const compactHasAny = compactCounts.some(([, value]) => value > 0);
                document.querySelector('.compact-board')?.classList.toggle('all-empty', !compactHasAny);
                compactCounts.forEach(([id, value]) => {
                    const column = document.getElementById(id)?.closest('.column');
                    if (column) column.classList.toggle('is-empty', compactHasAny && value === 0);
                });

                const columnCounts = [
                    ['count-export', boardCount('EXPORTED', fExport.length)],
                    ['count-rip', boardCount('RIP', fRip.length)],
                    ['count-run', boardCount('RUNNING', fRun.length)],
                    ['count-done', boardCount('DONE', fDone.length)],
                    ['count-cancel', boardCount('CANCELED', fCancel.length)],
                    ['count-removed', boardCount('REMOVED', fRemoved.length)],
                    ['count-queue', boardCount('QUEUE', queueItems.length)],
                    ['count-done-compact', boardCount('DONE', fDone.length)],
                    ['count-problem', boardCount('PROBLEM', problemItems.length)],
                    ['count-true-problem', boardCount('CANCELED', trueProblemItems.length)],
                    ['count-removed-problem', boardCount('REMOVED', removedProblemItems.length)],
                ];
                const hasAnyColumnData = columnCounts.some(([, value]) => value > 0);
                columnCounts.forEach(([id, value]) => {
                    const badge = document.getElementById(id);
                    if (!badge) return;
                    badge.innerText = value;
                    const column = badge.closest('.column');
                    if (column && !column.closest('.compact-board')) column.classList.toggle('is-empty', hasAnyColumnData && value === 0);
                });

            } catch (err) {
                console.error("Lỗi Render JS:", err);
            }
        }

        async function fetchData() {
            let start = document.getElementById('erpStart').value;
            let end = document.getElementById('erpEnd').value;
            let machine = document.getElementById('erpMachine').value;
            if(!start || !end) return;
            const requestId = ++dataRequestId;
            activeDataRequests++;
            setBoardLoading(true);
            try {
                const response = await fetch(`/api/data?start=${start}&end=${end}&machine=${machine}&limit=${boardVisibleLimit}`);
                const payload = await response.json();
                if (requestId !== dataRequestId) return;
                allData = sanitizeBoardData(payload); 
                renderData();
            } catch (error) { 
                console.log("Lỗi fetch API:", error); 
            } finally {
                activeDataRequests = Math.max(0, activeDataRequests - 1);
                if (requestId === dataRequestId || activeDataRequests === 0) {
                    activeDataRequests = 0;
                    setBoardLoading(false);
                }
            }
        }

        // Load data when page opens.
        document.getElementById('erpQuickDate').value = 'today';
        applyQuickDate();

        checkAuthUI(); connectWebSocket();
        setInterval(fetchV2Status, 30000);
    </script>
</body>
</html>
"""

@app.route("/")
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route("/thumbs/<path:filename>")
def serve_thumb(filename):
    return send_from_directory(THUMB_DIR, filename)

@app.route("/api/v2_status")
def api_v2_status():
    return jsonify(get_v2_status_snapshot())

def board_limit_arg():
    raw = request.args.get("limit")
    if raw is None:
        return None
    try:
        return max(1, min(300, int(raw)))
    except (TypeError, ValueError):
        return 20

def board_machines_arg():
    machine_filter = request.args.get("machine", "ALL")
    if machine_filter in MACHINES:
        return [machine_filter]
    return MACHINES

def board_count(cursor, where_sql, params):
    cursor.execute(f"SELECT COUNT(*) FROM files WHERE {where_sql}", params)
    row = cursor.fetchone()
    return int(row[0] or 0) if row else 0

def board_rows(cursor, meta_expr, where_sql, params, limit):
    cursor.execute(
        f"""
        SELECT file_hash, file_name, file_path, status, created_time, updated_time, run_count, history, zalo_sent, {meta_expr}
        FROM files
        WHERE {where_sql}
        ORDER BY updated_time DESC
        LIMIT ?
        """,
        tuple(params) + (limit,),
    )
    return cursor.fetchall()

def build_board_item(machine, row, done_names, done_histories_by_name, completed_samples, context_rows):
    f_hash, name, file_path, status, c_time, up_time, run_cnt, history_data, z_sent, machine_meta_json = row
    time_short = up_time.split(" ")[1] if up_time and " " in up_time else ""
    try:
        r_cnt = int(run_cnt)
    except Exception:
        r_cnt = 1
    reprint_info = classify_reprint(name, r_cnt)
    item = {
        "hash": f_hash or "",
        "machine": machine or "",
        "name": str(name) if name else "Khong_Ten",
        "file_path": str(file_path) if file_path else "",
        "created": c_time or "",
        "updated": up_time or "",
        "time_short": time_short or "",
        "run": r_cnt,
        "expected_runs": reprint_info["expected_runs"],
        "billable_runs": reprint_info["billable_runs"],
        "reprint_needs_review": reprint_info["needs_review"],
        "reprint_label": reprint_info["label"],
        "history": history_data or "[]",
        "zalo_sent": z_sent or 0,
        "machine_meta": parse_machine_meta_json(machine_meta_json),
    }
    item["has_thumbnail"] = bool(item["hash"]) and os.path.exists(os.path.join(THUMB_DIR, f"{item['hash']}.jpg"))
    if status == "DELETED":
        delete_info = classify_deleted_job(machine, item["name"], history_data)
        item["cancel_type"] = delete_info["type"]
        item["cancel_reason"] = delete_info["label"]
        item["is_production_error"] = delete_info["is_production_error"]
        if delete_info["progress_percent"] is not None:
            item["progress_percent"] = delete_info["progress_percent"]
        name_key = str(name or "").lower().strip()
        done_duration_info = assess_prior_done_duration(
            item["name"],
            done_histories_by_name.get(name_key, []),
            completed_samples,
        )
        reprint_cancel = classify_reprint_cancel_after_done(
            item["name"],
            has_done_before=name_key in done_names and done_duration_info["trusted"],
            is_production_error=item["is_production_error"],
        )
        if reprint_cancel["is_reprint_cancel_after_done"]:
            item["cancel_type"] = "suspect_reprint_signal_after_done"
            item["cancel_reason"] = reprint_cancel["label"]
            item["is_production_error"] = False
            item["reprint_needs_review"] = False
            item["reprint_label"] = reprint_cancel["label"]
        elif item.get("is_production_error"):
            if done_duration_info["is_suspicious"]:
                item["cancel_reason"] = done_duration_info["label"]
                item["reprint_needs_review"] = True
                item["reprint_label"] = done_duration_info["label"]
            progress_info = estimate_cancel_progress(item["name"], history_data, completed_samples)
            item.update(progress_info)

    if status in ["PRINTING", "CUTTING"]:
        progress_label = active_progress_label(item.get("machine_meta"))
        if progress_label:
            item["progress_label"] = progress_label
        else:
            progress_info = estimate_active_progress(
                item["name"],
                history_data,
                completed_samples,
                item.get("machine_meta"),
            )
            if progress_info.get("progress_label"):
                item.update(progress_info)
        later_run = find_later_machine_run(
            context_rows,
            name,
            active_start_time(history_data, up_time),
        )
        if later_run:
            next_time_short = later_run["time"].split(" ")[1] if " " in later_run["time"] else later_run["time"]
            item["stale_active"] = True
            item["cancel_type"] = "missing_end_signal"
            item["cancel_reason"] = f"Thiếu tín hiệu kết thúc. Sau đó máy đã chạy {later_run['name']} lúc {next_time_short}."
            item["is_production_error"] = False
            item["reprint_needs_review"] = True
            item["reprint_label"] = "Cần xác nhận: thiếu tín hiệu kết thúc"
            item["next_run_name"] = later_run["name"]
            item["next_run_time"] = later_run["time"]
        active_info = classify_active_reprint(
            history_data,
            has_done_before=str(name or "").lower().strip() in done_names,
            file_name=name,
        )
        if active_info["is_reprint_waiting_done"]:
            item["active_reprint_waiting_done"] = True
            item["reprint_needs_review"] = True
            item["reprint_label"] = active_info["label"]
    return item

def append_board_item(result, item, status):
    if status in ["EXPORTED", "WRONG_DAY"]:
        result["EXPORTED"].append(item)
    elif status == "RIP":
        result["RIP"].append(item)
    elif status in ["PRINTING", "CUTTING"]:
        if item.get("stale_active"):
            result["CANCELED"].append(item)
        else:
            result["RUNNING"].append(item)
    elif status == "DONE":
        result["DONE"].append(item)
    elif status == "DELETED":
        if item.get("is_production_error"):
            result["CANCELED"].append(item)
        else:
            result["REMOVED"].append(item)
    elif status in ["LOI", "Lỗi"]:
        result["CANCELED"].append(item)

def api_data_limited(start_date, end_date, limit):
    result = {
        "EXPORTED": [], "RIP": [], "RUNNING": [], "DONE": [], "CANCELED": [], "REMOVED": [],
        "COUNTS": {"EXPORTED": 0, "RIP": 0, "RUNNING": 0, "DONE": 0, "CANCELED": 0, "REMOVED": 0, "QUEUE": 0, "PROBLEM": 0},
    }
    machines_to_scan = board_machines_arg()
    date_sql = "DATE(updated_time) BETWEEN ? AND ?"
    for machine in machines_to_scan:
        db_path = os.path.join(DB_DIR, f"{machine}.db")
        if not os.path.exists(db_path):
            continue
        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
            c = conn.cursor()
            meta_expr = machine_meta_select_expr(conn)
            done_names = {
                str(row[0] or "").lower().strip()
                for row in c.execute(
                    f"SELECT file_name FROM files WHERE status='DONE' AND {date_sql}",
                    (start_date, end_date),
                ).fetchall()
            }
            recent_done_rows = board_rows(c, meta_expr, f"status='DONE' AND {date_sql}", (start_date, end_date), max(limit, 160))
            done_histories_by_name = {}
            for row in recent_done_rows:
                done_histories_by_name.setdefault(str(row[1] or "").lower().strip(), []).append(row[7])
            completed_samples = [
                {"file_name": row[1], "history": row[7], "machine_meta": parse_machine_meta_json(row[9])}
                for row in recent_done_rows
            ]
            active_rows = board_rows(c, meta_expr, f"status IN ('PRINTING','CUTTING') AND {date_sql}", (start_date, end_date), 200)
            context_rows = recent_done_rows + active_rows

            result["COUNTS"]["EXPORTED"] += board_count(c, f"status IN ('EXPORTED','WRONG_DAY') AND {date_sql}", (start_date, end_date))
            result["COUNTS"]["RIP"] += board_count(c, f"status='RIP' AND {date_sql}", (start_date, end_date))
            result["COUNTS"]["RUNNING"] += board_count(c, f"status IN ('PRINTING','CUTTING') AND {date_sql}", (start_date, end_date))
            result["COUNTS"]["DONE"] += board_count(c, f"status='DONE' AND {date_sql}", (start_date, end_date))

            queue_rows = board_rows(c, meta_expr, f"status IN ('EXPORTED','WRONG_DAY','RIP','PRINTING','CUTTING') AND {date_sql}", (start_date, end_date), limit)
            done_rows = board_rows(c, meta_expr, f"status='DONE' AND {date_sql}", (start_date, end_date), limit)
            deleted_rows = board_rows(c, meta_expr, f"status='DELETED' AND {date_sql}", (start_date, end_date), 10000)

            for row in queue_rows + done_rows:
                item = build_board_item(machine, row, done_names, done_histories_by_name, completed_samples, context_rows)
                append_board_item(result, item, row[3])

            for row in deleted_rows:
                item = build_board_item(machine, row, done_names, done_histories_by_name, completed_samples, context_rows)
                if item.get("is_production_error"):
                    result["COUNTS"]["CANCELED"] += 1
                    if len(result["CANCELED"]) < limit:
                        result["CANCELED"].append(item)
                else:
                    result["COUNTS"]["REMOVED"] += 1
                    if len(result["REMOVED"]) < limit:
                        result["REMOVED"].append(item)
            conn.close()
        except Exception:
            pass

    for key in ["EXPORTED", "RIP", "RUNNING", "DONE", "CANCELED", "REMOVED"]:
        result[key] = dedupe_visible_items(result[key])
        result[key].sort(key=lambda item: item.get("updated") or "", reverse=True)
        result[key] = result[key][:limit]
    result["CANCELED"] = filter_removed_items_with_later_done(result["CANCELED"], result["DONE"])
    result["REMOVED"] = filter_removed_items_with_later_done(result["REMOVED"], result["DONE"])
    result["COUNTS"]["QUEUE"] = result["COUNTS"]["EXPORTED"] + result["COUNTS"]["RIP"] + result["COUNTS"]["RUNNING"]
    result["COUNTS"]["PROBLEM"] = result["COUNTS"]["CANCELED"] + result["COUNTS"]["REMOVED"]
    result["ATTENTION"] = build_attention_items(result)
    return result

@app.route("/api/data")
def api_data():
    target_date = request.args.get('date', datetime.now().strftime("%Y-%m-%d"))
    start_date = request.args.get('start') or target_date
    end_date = request.args.get('end') or start_date
    limit = board_limit_arg()
    if limit is not None:
        return jsonify(api_data_limited(start_date, end_date, limit))
    result = {"EXPORTED": [], "RIP": [], "RUNNING": [], "DONE": [], "CANCELED": [], "REMOVED": []}
    
    for machine in MACHINES:
        db_path = os.path.join(DB_DIR, f"{machine}.db")
        if not os.path.exists(db_path): continue
        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
            c = conn.cursor()
            meta_expr = machine_meta_select_expr(conn)
            c.execute(
                f"SELECT file_hash, file_name, file_path, status, created_time, updated_time, run_count, history, zalo_sent, {meta_expr} "
                "FROM files WHERE DATE(updated_time) BETWEEN ? AND ?",
                (start_date, end_date),
            )
            rows = c.fetchall()
            done_names = {
                str(row[1] or "").lower().strip()
                for row in rows
                if row[3] == "DONE"
            }
            done_histories_by_name = {}
            for row in rows:
                if row[3] == "DONE":
                    done_histories_by_name.setdefault(str(row[1] or "").lower().strip(), []).append(row[7])
            completed_samples = [
                {"file_name": row[1], "history": row[7], "machine_meta": parse_machine_meta_json(row[9])}
                for row in rows
                if row[3] == "DONE"
            ]
            for f_hash, name, file_path, status, c_time, up_time, run_cnt, history_data, z_sent, machine_meta_json in rows:
                time_short = up_time.split(" ")[1] if up_time and " " in up_time else ""
                try: r_cnt = int(run_cnt)
                except: r_cnt = 1
                reprint_info = classify_reprint(name, r_cnt)
                
                # Normalize data before sending to web.
                item = {
                    "hash": f_hash or "", 
                    "machine": machine or "", 
                    "name": str(name) if name else "Khong_Ten", 
                    "file_path": str(file_path) if file_path else "",
                    "created": c_time or "", 
                    "updated": up_time or "", 
                    "time_short": time_short or "", 
                    "run": r_cnt, 
                    "expected_runs": reprint_info["expected_runs"],
                    "billable_runs": reprint_info["billable_runs"],
                    "reprint_needs_review": reprint_info["needs_review"],
                    "reprint_label": reprint_info["label"],
                    "history": history_data or "[]", 
                    "zalo_sent": z_sent or 0,
                    "machine_meta": parse_machine_meta_json(machine_meta_json),
                }
                item["has_thumbnail"] = bool(item["hash"]) and os.path.exists(os.path.join(THUMB_DIR, f"{item['hash']}.jpg"))
                if status == "DELETED":
                    delete_info = classify_deleted_job(machine, item["name"], history_data)
                    item["cancel_type"] = delete_info["type"]
                    item["cancel_reason"] = delete_info["label"]
                    item["is_production_error"] = delete_info["is_production_error"]
                    if delete_info["progress_percent"] is not None:
                        item["progress_percent"] = delete_info["progress_percent"]
                    name_key = str(name or "").lower().strip()
                    done_duration_info = assess_prior_done_duration(
                        item["name"],
                        done_histories_by_name.get(name_key, []),
                        completed_samples,
                    )
                    reprint_cancel = classify_reprint_cancel_after_done(
                        item["name"],
                        has_done_before=name_key in done_names and done_duration_info["trusted"],
                        is_production_error=item["is_production_error"],
                    )
                    if reprint_cancel["is_reprint_cancel_after_done"]:
                        item["cancel_type"] = "suspect_reprint_signal_after_done"
                        item["cancel_reason"] = reprint_cancel["label"]
                        item["is_production_error"] = False
                        item["reprint_needs_review"] = False
                        item["reprint_label"] = reprint_cancel["label"]
                    elif item.get("is_production_error"):
                        if done_duration_info["is_suspicious"]:
                            item["cancel_reason"] = done_duration_info["label"]
                            item["reprint_needs_review"] = True
                            item["reprint_label"] = done_duration_info["label"]
                        progress_info = estimate_cancel_progress(item["name"], history_data, completed_samples)
                        item.update(progress_info)

                if status in ["PRINTING", "CUTTING"]:
                    progress_label = active_progress_label(item.get("machine_meta"))
                    if progress_label:
                        item["progress_label"] = progress_label
                    else:
                        progress_info = estimate_active_progress(
                            item["name"],
                            history_data,
                            completed_samples,
                            item.get("machine_meta"),
                        )
                        if progress_info.get("progress_label"):
                            item.update(progress_info)
                    later_run = find_later_machine_run(
                        rows,
                        name,
                        active_start_time(history_data, up_time),
                    )
                    if later_run:
                        next_time_short = later_run["time"].split(" ")[1] if " " in later_run["time"] else later_run["time"]
                        item["stale_active"] = True
                        item["cancel_type"] = "missing_end_signal"
                        item["cancel_reason"] = f"Thiếu tín hiệu kết thúc. Sau đó máy đã chạy {later_run['name']} lúc {next_time_short}."
                        item["is_production_error"] = False
                        item["reprint_needs_review"] = True
                        item["reprint_label"] = "Cần xác nhận: thiếu tín hiệu kết thúc"
                        item["next_run_name"] = later_run["name"]
                        item["next_run_time"] = later_run["time"]
                    active_info = classify_active_reprint(
                        history_data,
                        has_done_before=str(name or "").lower().strip() in done_names,
                        file_name=name,
                    )
                    if active_info["is_reprint_waiting_done"]:
                        item["active_reprint_waiting_done"] = True
                        item["reprint_needs_review"] = True
                        item["reprint_label"] = active_info["label"]
                
                if status in ["EXPORTED", "WRONG_DAY"]: result["EXPORTED"].append(item)
                elif status == "RIP": result["RIP"].append(item)
                elif status in ["PRINTING", "CUTTING"]:
                    if item.get("stale_active"):
                        result["CANCELED"].append(item)
                    else:
                        result["RUNNING"].append(item)
                elif status == "DONE": result["DONE"].append(item)
                elif status == "DELETED":
                    if item.get("is_production_error"):
                        result["CANCELED"].append(item)
                    else:
                        result["REMOVED"].append(item)
                elif status in ["LOI", "L\u00e1\u00bb\u2013I"]: result["CANCELED"].append(item) 
            conn.close()
        except Exception: pass
    result["CANCELED"] = dedupe_visible_items(result["CANCELED"])
    result["REMOVED"] = dedupe_visible_items(result["REMOVED"])
    result["CANCELED"] = filter_removed_items_with_later_done(result["CANCELED"], result["DONE"])
    result["REMOVED"] = filter_removed_items_with_later_done(result["REMOVED"], result["DONE"])
    result["ATTENTION"] = build_attention_items(result)
    return jsonify(result)

# STATS API
@app.route("/api/stats")
def api_stats():
    vip_dict = {}
    try:
        vip_file = os.path.join(BASE_DATA_CRM, "DanhBa_VIP.json")
        if os.path.exists(vip_file):
            with open(vip_file, "r", encoding="utf-8") as f:
                for k, v in json.load(f).items(): vip_dict[chuan_hoa_chuoi(k)] = v.get("ten_day_du", k)
    except: pass

    start_date = request.args.get('start')
    end_date = request.args.get('end')
    machine_filter = request.args.get('machine', 'ALL')
    
    if not start_date or not end_date: return jsonify({"error": "Missing dates"})

    m2_by_machine = {m: 0 for m in MACHINES}
    cancel_by_machine = {m: 0 for m in MACHINES}
    cancel_bad_m2_by_machine = {m: 0.0 for m in MACHINES}
    jobs_by_customer = {}
    m2_by_customer = {}
    customer_details = {}
    jobs_by_hour = {str(i).zfill(2): 0 for i in range(24)}
    
    total_done = 0
    total_cancelled = 0
    total_removed = 0
    total_reprint_jobs = 0
    total_m2_all = 0.0
    total_bad_m2 = 0.0
    
    date_filter = f"DATE(updated_time) BETWEEN '{start_date}' AND '{end_date} 23:59:59'"

    machines_to_scan = MACHINES if machine_filter == "ALL" else [machine_filter]
    try:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    except Exception:
        start_dt = datetime.now()
        end_dt = start_dt
    today_dt = datetime.now()
    if end_dt.date() > today_dt.date():
        end_dt = today_dt
    single_day_flow = start_dt.date() == end_dt.date()
    if single_day_flow:
        flow_labels = [str(i).zfill(2) for i in range(24)]
    else:
        flow_labels = []
        cursor = start_dt
        while cursor <= end_dt:
            flow_labels.append(cursor.strftime("%Y-%m-%d"))
            cursor += timedelta(days=1)
    flow_by_machine = {
        machine: {label: 0 for label in flow_labels}
        for machine in machines_to_scan
    }
    flow_m2_by_machine = {
        machine: {label: 0.0 for label in flow_labels}
        for machine in machines_to_scan
    }

    def display_customer_name(file_name):
        parts = str(file_name).split('_') if file_name else []
        if not parts:
            return "UNKNOWN"
        raw_cus = parts[0]
        cus_code = chuan_hoa_chuoi(raw_cus)
        cus_name = vip_dict.get(cus_code, raw_cus.upper()) if cus_code else "UNKNOWN"
        if len(cus_name) > 15:
            cus_name = cus_name[:15] + "..."
        return cus_name

    def ensure_customer_detail(customer_name):
        if customer_name not in customer_details:
            customer_details[customer_name] = {
                "summary": {
                    "total_jobs": 0,
                    "total_m2": 0.0,
                    "cancel_rate": 0,
                    "cancel_bad_m2": 0.0,
                    "cancel_jobs": 0,
                    "removed_jobs": 0,
                    "reprint_jobs": 0,
                },
                "by_machine": {m: 0 for m in MACHINES},
                "by_machine_m2": {m: 0.0 for m in MACHINES},
                "cancel_by_machine": {m: 0 for m in MACHINES},
                "cancel_bad_m2_by_machine": {m: 0.0 for m in MACHINES},
                "_flow": {
                    m: {label: 0 for label in flow_labels}
                    for m in machines_to_scan
                },
                "_flow_m2": {
                    m: {label: 0.0 for label in flow_labels}
                    for m in machines_to_scan
                },
            }
        return customer_details[customer_name]

    for machine in machines_to_scan:
        db_path = os.path.join(DB_DIR, f"{machine}.db")
        if not os.path.exists(db_path): continue
        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
            c = conn.cursor()
            meta_expr = machine_meta_select_expr(conn)

            c.execute(f"SELECT file_name, history FROM files WHERE status='DONE' AND {date_filter}")
            completed_samples = [
                {"file_name": done_name, "history": done_history}
                for done_name, done_history in c.fetchall()
            ]
            
            c.execute(f"SELECT file_name, history FROM files WHERE status='DELETED' AND {date_filter}")
            for deleted_name, deleted_history in c.fetchall():
                delete_info = classify_deleted_job(machine, deleted_name, deleted_history)
                deleted_customer = display_customer_name(deleted_name)
                deleted_detail = ensure_customer_detail(deleted_customer)
                if delete_info["is_production_error"]:
                    total_cancelled += 1
                    cancel_by_machine[machine] += 1
                    deleted_detail["summary"]["cancel_jobs"] += 1
                    deleted_detail["cancel_by_machine"][machine] = deleted_detail["cancel_by_machine"].get(machine, 0) + 1
                    progress_info = estimate_cancel_progress(deleted_name, deleted_history, completed_samples)
                    bad_m2 = progress_info.get("estimated_bad_m2")
                    if bad_m2:
                        total_bad_m2 += bad_m2
                        cancel_bad_m2_by_machine[machine] += bad_m2
                        deleted_detail["summary"]["cancel_bad_m2"] += bad_m2
                        deleted_detail["cancel_bad_m2_by_machine"][machine] = deleted_detail["cancel_bad_m2_by_machine"].get(machine, 0.0) + bad_m2
                else:
                    total_removed += 1
                    deleted_detail["summary"]["removed_jobs"] += 1
            
            c.execute(f"SELECT file_name, updated_time, run_count, {meta_expr} FROM files WHERE status='DONE' AND {date_filter}")
            for name, up_time, run_cnt, machine_meta_json in c.fetchall():
                total_done += 1
                try: r_cnt = int(run_cnt)
                except: r_cnt = 1
                reprint_info = classify_reprint(name, r_cnt)
                if reprint_info["needs_review"]:
                    total_reprint_jobs += 1
                
                m2 = best_area_m2(name, machine_meta_json)
                billable_m2 = 0.0
                if m2 > 0: 
                    billable_m2 = m2 * reprint_info["billable_runs"]
                    m2_by_machine[machine] += billable_m2
                    total_m2_all += billable_m2
                
                cus_name = display_customer_name(name)
                cus_detail = ensure_customer_detail(cus_name)
                cus_detail["summary"]["total_jobs"] += 1
                cus_detail["summary"]["total_m2"] += billable_m2
                cus_detail["by_machine"][machine] = cus_detail["by_machine"].get(machine, 0) + 1
                cus_detail["by_machine_m2"][machine] = cus_detail["by_machine_m2"].get(machine, 0.0) + billable_m2
                if reprint_info["needs_review"]:
                    cus_detail["summary"]["reprint_jobs"] += 1
                jobs_by_customer[cus_name] = jobs_by_customer.get(cus_name, 0) + 1
                if billable_m2 > 0:
                    m2_by_customer[cus_name] = m2_by_customer.get(cus_name, 0.0) + billable_m2
                
                if up_time and " " in up_time:
                    hour = up_time.split(" ")[1].split(":")[0]
                    jobs_by_hour[hour] = jobs_by_hour.get(hour, 0) + 1
                    flow_key = hour if single_day_flow else up_time.split(" ")[0]
                    if machine in flow_by_machine and flow_key in flow_by_machine[machine]:
                        flow_by_machine[machine][flow_key] += 1
                    if machine in flow_m2_by_machine and flow_key in flow_m2_by_machine[machine]:
                        flow_m2_by_machine[machine][flow_key] += billable_m2
                    if machine in cus_detail["_flow"] and flow_key in cus_detail["_flow"][machine]:
                        cus_detail["_flow"][machine][flow_key] += 1
                    if machine in cus_detail["_flow_m2"] and flow_key in cus_detail["_flow_m2"][machine]:
                        cus_detail["_flow_m2"][machine][flow_key] += billable_m2
            conn.close()
        except: pass

    sorted_customers = sorted(jobs_by_customer.items(), key=lambda x: x[1], reverse=True)[:10]
    sorted_customers_m2 = sorted(m2_by_customer.items(), key=lambda x: x[1], reverse=True)[:10]
    cancel_rate = calculate_cancel_rate_by_m2(total_m2_all, total_bad_m2)
    customer_detail_payload = {}
    for customer_name, detail in customer_details.items():
        summary = detail["summary"]
        summary["total_m2"] = round(summary.get("total_m2", 0.0), 2)
        summary["cancel_bad_m2"] = round(summary.get("cancel_bad_m2", 0.0), 2)
        summary["cancel_rate"] = round(calculate_cancel_rate_by_m2(summary["total_m2"], summary["cancel_bad_m2"]), 1)
        customer_detail_payload[customer_name] = {
                "summary": summary,
                "by_machine": detail["by_machine"],
                "by_machine_m2": {k: round(v, 2) for k, v in detail["by_machine_m2"].items()},
                "cancel_by_machine": detail["cancel_by_machine"],
                "cancel_bad_m2_by_machine": {k: round(v, 2) for k, v in detail["cancel_bad_m2_by_machine"].items()},
                "machine_flow": {
                "labels": flow_labels,
                "mode": "hour" if single_day_flow else "day",
                "datasets": [
                    {"machine": machine, "data": [detail["_flow"][machine].get(label, 0) for label in flow_labels]}
                    for machine in machines_to_scan
                ],
            },
            "machine_flow_m2": {
                "labels": flow_labels,
                "mode": "hour" if single_day_flow else "day",
                "datasets": [
                    {"machine": machine, "data": [round(detail["_flow_m2"][machine].get(label, 0.0), 2) for label in flow_labels]}
                    for machine in machines_to_scan
                ],
            },
        }

    return jsonify({
        "summary": { "total_jobs": total_done, "total_m2": total_m2_all, "cancel_rate": cancel_rate, "cancel_bad_m2": total_bad_m2, "cancel_jobs": total_cancelled, "removed_jobs": total_removed, "reprint_jobs": total_reprint_jobs },
        "m2": {k: v for k, v in m2_by_machine.items() if k in machines_to_scan},
        "cancel_by_machine": {k: v for k, v in cancel_by_machine.items() if k in machines_to_scan},
        "cancel_bad_m2_by_machine": {k: round(v, 2) for k, v in cancel_bad_m2_by_machine.items() if k in machines_to_scan},
        "customers": {"labels": [x[0] for x in sorted_customers], "data": [x[1] for x in sorted_customers]},
        "customers_m2": {"labels": [x[0] for x in sorted_customers_m2], "data": [round(x[1], 2) for x in sorted_customers_m2]},
        "customer_details": customer_detail_payload,
        "hours": {"labels": list(jobs_by_hour.keys()), "data": list(jobs_by_hour.values())},
        "machine_flow": {
            "labels": flow_labels,
            "mode": "hour" if single_day_flow else "day",
            "datasets": [
                {"machine": machine, "data": [flow_by_machine[machine].get(label, 0) for label in flow_labels]}
                for machine in machines_to_scan
            ]
        },
        "machine_flow_m2": {
            "labels": flow_labels,
            "mode": "hour" if single_day_flow else "day",
            "datasets": [
                {"machine": machine, "data": [round(flow_m2_by_machine[machine].get(label, 0.0), 2) for label in flow_labels]}
                for machine in machines_to_scan
            ]
        }
    })

@app.route("/api/export_csv")
def export_csv():
    start_date = request.args.get('start')
    end_date = request.args.get('end')
    machine_filter = request.args.get('machine', 'ALL')
    
    if not start_date or not end_date: return "Missing dates", 400
    date_filter = f"DATE(updated_time) BETWEEN '{start_date}' AND '{end_date} 23:59:59'"
    machines_to_scan = MACHINES if machine_filter == "ALL" else [machine_filter]
    
    csv_data = "\ufeffMAY,TEN FILE,TRANG THAI,DIEN TICH (m2),SO LAN CHAY,THOI GIAN CAP NHAT\n"
    
    for machine in machines_to_scan:
        db_path = os.path.join(DB_DIR, f"{machine}.db")
        if not os.path.exists(db_path): continue
        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
            c = conn.cursor()
            meta_expr = machine_meta_select_expr(conn)
            c.execute(f"SELECT file_name, status, run_count, updated_time, {meta_expr} FROM files WHERE {date_filter} ORDER BY updated_time DESC")
            for name, status, run_cnt, up_time, machine_meta_json in c.fetchall():
                m2 = best_area_m2(name, machine_meta_json)
                safe_name = str(name).replace(',', ';').replace('"', '') if name else "Khong_Ten"
                row_str = f"{machine},{safe_name},{status},{m2},{run_cnt},{up_time}\n"
                csv_data += row_str
            conn.close()
        except: pass

    filename = f"BaoCao_SanXuat_{start_date}_den_{end_date}.csv"
    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-disposition": f"attachment; filename={filename}"}
    )

@app.route("/api/login", methods=["POST"])
def login():
    if not ADMIN_PIN:
        return jsonify({"success": False, "error": "Chưa cấu hình mã PIN quản trị."})
    payload = request.get_json(silent=True) or {}
    if payload.get("pin") == ADMIN_PIN: return jsonify({"success": True})
    return jsonify({"success": False, "error": "Mã PIN không đúng."})

@app.route("/api/update_status", methods=["POST"])
def update_status():
    if not ADMIN_PIN:
        return jsonify({"success": False, "error": "Chưa cấu hình mã PIN quản trị."})
    data = request.get_json(silent=True) or {}
    machine = data.get("machine"); file_name = data.get("name")
    file_hash = str(data.get("hash") or "").strip()
    new_status = data.get("status"); pin_code = data.get("pin")
    
    if pin_code != ADMIN_PIN: return jsonify({"success": False, "error": "Mã PIN không hợp lệ."})
    db_path = os.path.join(DB_DIR, f"{machine}.db")
    if not os.path.exists(db_path): return jsonify({"success": False, "error": "Khong tim thay CSDL."})

    try:
        conn = sqlite3.connect(db_path, timeout=15)
        conn.execute("PRAGMA journal_mode=WAL;")
        c = conn.cursor()
        if file_hash:
            c.execute("SELECT history FROM files WHERE file_hash=?", (file_hash,))
        else:
            c.execute("SELECT history FROM files WHERE file_name=? ORDER BY updated_time DESC LIMIT 1", (file_name,))
        row = c.fetchone()
        if not row:
            conn.close()
            return jsonify({"success": False, "error": "Khong tim thay file can cap nhat."})
        hist_str = row[0] if row and row[0] else "[]"
        try:
            h_list = json.loads(hist_str)
            event_name = "DONE" if new_status == "DONE" else ("DELETE" if new_status == "DELETED" else "EXPORT")
            h_list.append({"status": new_status, "time": now(), "event": f"ADMIN_{event_name}"})
            hist_str = json.dumps(h_list)
        except: pass

        updated_at = now()
        if file_hash:
            c.execute(
                "UPDATE files SET status=?, updated_time=?, zalo_sent=0, history=? WHERE file_hash=?",
                (new_status, updated_at, hist_str, file_hash),
            )
        else:
            c.execute(
                """
                UPDATE files
                SET status=?, updated_time=?, zalo_sent=0, history=?
                WHERE rowid = (
                    SELECT rowid FROM files WHERE file_name=? ORDER BY updated_time DESC LIMIT 1
                )
                """,
                (new_status, updated_at, hist_str, file_name),
            )
        if c.rowcount <= 0:
            conn.close()
            return jsonify({"success": False, "error": "Khong co row nao duoc cap nhat."})
        conn.commit(); conn.close()
        try: requests.get(SERVER_BROADCAST_URL, timeout=2)
        except: pass
        return jsonify({"success": True})
    except Exception as e: return jsonify({"success": False, "error": str(e)})

if __name__ == "__main__":
    print_log("Khoi dong web dashboard V2.")
    
    # Run server.
    app.run(host=DASHBOARD_HOST, port=DASHBOARD_PORT, debug=False, threaded=True)

