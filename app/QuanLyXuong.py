# =========================================
# CLIENT V2.0.0 - OUTBOX DURABLE + POS BRIDGE READY
# =========================================
import os, time, json, shutil, threading, subprocess, socket, requests, base64, sqlite3, re, uuid
from datetime import datetime
from io import BytesIO
from qlx_config import API_SERVER_URL, MACHINE_ALIASES, NAS_CLIENT_EXE_PATH
from qlx_outbox import EventOutbox
from qlx_workstation_logic import (
    get_expected_meta as pure_get_expected_meta,
    is_export_file as pure_is_export_file,
    is_meta_file as pure_is_meta_file,
    is_target_file_for_machine,
    LogTailState,
    make_event_identity,
    normalize_inbat_feed_progress,
    parse_inbat_printmon_snapshot,
    read_new_log_lines,
    resolve_machine_config,
)

from machine_file_meta import HAS_PIL, collect_machine_file_meta, find_thumbnail_source, resolve_machine_file_path
if HAS_PIL:
    from PIL import Image

CLIENT_VERSION = "V2.1.1_INDECAL_READY_RIP"

NAS_EXE_PATH = NAS_CLIENT_EXE_PATH

PC_INBAT = "inbat"; PC_INDECAL = "indecal"; PC_CNC = "cnc"          

ROOT = ""; MACHINE_NAME = ""; MACHINE_DISPLAY = ""; BASE_STORAGE = ""; STATE_FILE = ""; LOG_FILE = ""
OUTBOX = None
SCAN_INTERVAL = 30

state_lock = threading.Lock() 
recent_moved = dict(); processed_set = set(); processed_prt = dict(); processed_prn = set()  
prn_tracking = {}; stable_prts = dict(); current_print_job = None; current_print_id = None 
CLIENT_START_TIME = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
CLIENT_INSTANCE_ID = f"{socket.gethostname()}-{os.getpid()}-{uuid.uuid4().hex[:8]}"
CLIENT_INSTANCE_LOCK = None
INDECAL_RENAME_STUCK_SECONDS = 90

def now(): return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def acquire_client_instance_lock(machine_name, base_storage):
    try:
        import msvcrt
        os.makedirs(base_storage, exist_ok=True)
        lock_path = os.path.join(base_storage, f"QuanLyXuong_{machine_name}.lock")
        handle = open(lock_path, "a+", encoding="utf-8")
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        handle.seek(0)
        handle.truncate()
        handle.write(json.dumps({
            "machine": machine_name,
            "pid": os.getpid(),
            "start_time": CLIENT_START_TIME,
            "instance_id": CLIENT_INSTANCE_ID,
        }, ensure_ascii=False))
        handle.flush()
        return handle
    except Exception:
        try:
            handle.close()
        except Exception:
            pass
        return None

def release_client_instance_lock(handle):
    if not handle:
        return
    try:
        import msvcrt
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    except Exception:
        pass
    try:
        handle.close()
    except Exception:
        pass

def log_system(msg, is_error=False):
    print(f"[{now()}] {msg}")
    try:
        os.makedirs(BASE_STORAGE, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f: f.write(f"{now()} | {msg}\n")
    except: pass
    if is_error:
        def send_sos():
            try: requests.post(API_SERVER_URL.replace("/log_event", "/alert"), json={"machine": MACHINE_NAME, "message": msg}, timeout=5)
            except: pass
        threading.Thread(target=send_sos, daemon=True).start()

def indecal_rename_audit_url():
    return API_SERVER_URL.replace("/api/log_event", "/api/indecal_rename_audit")

def indecal_audit(action, prn_path="", meta_path="", target_prn_path="", source_image_path="", target_image_path="", file_size=0, retry_count=0, error="", extra=None):
    if MACHINE_NAME != "indecal":
        return None
    payload = {
        "machine": MACHINE_NAME,
        "action": action,
        "prn_path": prn_path or "",
        "meta_path": meta_path or "",
        "target_prn_path": target_prn_path or "",
        "source_image_path": source_image_path or "",
        "target_image_path": target_image_path or "",
        "file_size": int(file_size or 0),
        "retry_count": int(retry_count or 0),
        "error": str(error or ""),
        "event_time": now(),
        "extra": extra or {},
    }
    try:
        data_dir = os.path.join(BASE_STORAGE, "Data")
        os.makedirs(data_dir, exist_ok=True)
        conn = sqlite3.connect(os.path.join(data_dir, "indecal_rename_audit.db"), timeout=5)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS rename_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                machine TEXT,
                action TEXT,
                prn_path TEXT,
                meta_path TEXT,
                target_prn_path TEXT,
                source_image_path TEXT,
                target_image_path TEXT,
                file_size INTEGER,
                retry_count INTEGER,
                error TEXT,
                event_time TEXT,
                extra_json TEXT
            )
            """
        )
        conn.execute(
            """
            INSERT INTO rename_audit
                (machine, action, prn_path, meta_path, target_prn_path, source_image_path,
                 target_image_path, file_size, retry_count, error, event_time, extra_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "InDecal",
                payload["action"],
                payload["prn_path"],
                payload["meta_path"],
                payload["target_prn_path"],
                payload["source_image_path"],
                payload["target_image_path"],
                payload["file_size"],
                payload["retry_count"],
                payload["error"],
                payload["event_time"],
                json.dumps(payload["extra"], ensure_ascii=False),
            ),
        )
        conn.commit()
        conn.close()
    except Exception as exc:
        log_system(f"[INDECAL_AUDIT_LOCAL_FAIL] {action}: {exc}")
    try:
        requests.post(indecal_rename_audit_url(), json=payload, timeout=2)
    except Exception:
        pass
    return payload

def load_state():
    loaded_set = set()
    try:
        os.makedirs(BASE_STORAGE, exist_ok=True)
        if os.path.exists(STATE_FILE): 
            loaded_set = set(json.load(open(STATE_FILE)))
            global processed_prt
            for p in loaded_set:
                if p.endswith(".prt") or p.endswith(".prn"):
                    try: processed_prt[p] = os.path.getmtime(p)
                    except: processed_prt[p] = 0
    except: pass
    return loaded_set

def save_state(state):
    try:
        os.makedirs(BASE_STORAGE, exist_ok=True)
        tmp = STATE_FILE + ".tmp"
        with open(tmp, "w") as f: json.dump(list(state), f)
        os.replace(tmp, STATE_FILE)
    except: pass

def is_target_file(f):
    return is_target_file_for_machine(MACHINE_NAME, f)

def is_export_file(filename):
    return pure_is_export_file(filename)

def is_meta_file(filename):
    return pure_is_meta_file(filename)

def get_expected_meta(ext_str):
    return pure_get_expected_meta(ext_str)

def resolve_indecal_runtime_path(path, file_name="", event_time=""):
    display = os.path.basename(str(file_name or path or "")).strip()
    candidates = [str(path or "").strip()]
    if display:
        if ROOT:
            candidates.extend([
                os.path.join(ROOT, "Tem", display),
                os.path.join(ROOT, datetime.now().strftime("%Y-%m-%d"), "New Folder", display),
                os.path.join(ROOT, datetime.now().strftime("%Y-%m-%d"), display),
            ])
    for candidate in candidates:
        try:
            if candidate and os.path.exists(candidate):
                return candidate
        except Exception:
            continue
    try:
        resolved = resolve_machine_file_path(MACHINE_DISPLAY or MACHINE_NAME, path, file_name, event_time)
        if resolved:
            return resolved
    except Exception:
        pass
    return str(path or "")

def process_event(path, event_type, forced_base_id=None, forced_display_name=None, machine_meta_extra=None):
    global OUTBOX
    resolved_path = path
    if MACHINE_NAME == "indecal" and event_type in {"PRINTING", "DONE", "DELETE"}:
        try:
            candidate = resolve_indecal_runtime_path(
                path,
                forced_display_name or os.path.basename(path),
                (machine_meta_extra or {}).get("log_event_time") or now(),
            )
            if candidate:
                resolved_path = candidate
        except Exception:
            pass
    thumb_b64 = None
    file_to_thumb = None
    if HAS_PIL and MACHINE_NAME != "cnc" and event_type in ["EXPORT", "RIP", "WRONG_DAY", "PRINTING", "DONE"]:
        file_to_thumb = find_thumbnail_source(resolved_path) or find_thumbnail_source(path)
        if file_to_thumb:
            try:
                with Image.open(file_to_thumb) as img:
                    if img.mode == 'CMYK': img = img.convert('RGB')
                    img.thumbnail((250, 250)) 
                    buffered = BytesIO()
                    img.save(buffered, format="JPEG", quality=60)
                    thumb_b64 = base64.b64encode(buffered.getvalue()).decode('utf-8')
            except Exception as exc:
                log_system(f"⚠️ Không tạo được ảnh xem trước [{event_type}]: {path} -> {file_to_thumb} | {exc}", is_error=True)
        else:
                log_system(f"⚠️ Không tìm thấy file gốc để tạo ảnh xem trước [{event_type}]: {resolved_path}", is_error=True)

    event_time = (machine_meta_extra or {}).get("log_event_time") or now()
    event_id = make_event_identity(MACHINE_NAME, event_type, resolved_path, event_time, forced_base_id)
    machine_meta = collect_machine_file_meta(resolved_path, file_to_thumb) or collect_machine_file_meta(path, file_to_thumb)
    if machine_meta_extra:
        machine_meta.update(machine_meta_extra)
    if MACHINE_NAME == "inbat":
        normalize_inbat_feed_progress(machine_meta)
    payload = {
        "machine": MACHINE_NAME, "path": resolved_path, "event_type": event_type,
        "forced_base_id": forced_base_id, "forced_display_name": forced_display_name,
        "thumbnail_b64": thumb_b64,
        "machine_meta": machine_meta,
        "event_time": event_time,
        "event_id": event_id,
        "idempotency_key": event_id,
    }

    if OUTBOX is None:
        log_system(f"⚠️ Outbox chưa sẵn sàng, gửi trực tiếp [{event_type}]: {os.path.basename(resolved_path)}", is_error=True)
        try:
            res = requests.post(API_SERVER_URL, json=payload, timeout=5)
            if res.status_code == 200:
                log_system(f"📡 API Bắn Thành Công [{event_type}]: {os.path.basename(resolved_path)}")
            else:
                log_system(f"⚠️ API lỗi HTTP {res.status_code} [{event_type}]: {os.path.basename(resolved_path)}", is_error=True)
        except requests.exceptions.RequestException as exc:
            log_system(f"⚠️ Mạng lỗi, chưa thể gửi trực tiếp: {exc}", is_error=True)
        return

    event_id = OUTBOX.enqueue(payload)
    log_system(f"🧾 Outbox nhận [{event_type}]: {os.path.basename(resolved_path)} ({event_id[:8]})")

def outbox_sender_worker():
    while True:
        try:
            if OUTBOX is None:
                time.sleep(2)
                continue

            events = OUTBOX.next_pending(limit=10)
            if not events:
                OUTBOX.prune_sent()
                time.sleep(1)
                continue

            for event in events:
                payload = event.payload
                path = payload.get("path", "")
                event_type = payload.get("event_type", "")
                try:
                    res = requests.post(API_SERVER_URL, json=payload, timeout=5)
                    if res.status_code == 200:
                        OUTBOX.mark_sent(event.event_id)
                        log_system(f"📡 API Bắn Thành Công [{event_type}]: {os.path.basename(path)} ({event.event_id[:8]})")
                    else:
                        OUTBOX.mark_failed(event.event_id, f"HTTP {res.status_code}: {res.text[:200]}")
                        log_system(f"⚠️ API lỗi HTTP {res.status_code}, sẽ retry [{event_type}]: {os.path.basename(path)}")
                except requests.exceptions.RequestException as exc:
                    OUTBOX.mark_failed(event.event_id, str(exc))
                    pending = OUTBOX.pending_count()
                    log_system(f"⚠️ Mạng LAN nghẽn. Outbox còn {pending} event, sẽ retry...")
        except Exception as exc:
            log_system(f"❌ LỖI OUTBOX: {exc}", is_error=True)
            time.sleep(5)

def fix_short_folder_names():
    try:
        if not os.path.exists(ROOT): return
        now_dt = datetime.now()
        y_str = now_dt.strftime("%Y"); m_str = now_dt.strftime("%m")
        for d in os.listdir(ROOT):
            if d.isdigit() and 1 <= int(d) <= 31:
                new_name = f"{y_str}-{m_str}-{str(int(d)).zfill(2)}"
                old_p = os.path.join(ROOT, d); new_p = os.path.join(ROOT, new_name)
                os.makedirs(new_p, exist_ok=True)
                for item in os.listdir(old_p):
                    src = os.path.join(old_p, item); dst = os.path.join(new_p, item)
                    if os.path.isdir(src):
                        os.makedirs(dst, exist_ok=True)
                        for sub in os.listdir(src):
                            try: 
                                if MACHINE_NAME == "cnc": os.rename(os.path.join(src, sub), os.path.join(dst, sub))
                                else: os.replace(os.path.join(src, sub), os.path.join(dst, sub))
                            except: pass
                        try: os.rmdir(src)
                        except: pass
                    else:
                        try: 
                            if MACHINE_NAME == "cnc": os.rename(src, dst)
                            else: os.replace(src, dst)
                        except: pass
                try: os.rmdir(old_p)
                except: pass
    except: pass

def fast_folder_renamer_worker():
    while True:
        try: fix_short_folder_names()
        except: pass
        time.sleep(1)

def cleanup_old_folders(days_to_keep=10):
    try:
        if not os.path.exists(ROOT): return
        now_dt = datetime.now()
        for d in os.listdir(ROOT):
            if len(d) == 10:
                try:
                    folder_dt = datetime.strptime(d, "%Y-%m-%d")
                    delta_days = (now_dt - folder_dt).days
                    if delta_days < -1 and MACHINE_NAME == "cnc": pass
                    elif delta_days > days_to_keep:
                        shutil.rmtree(os.path.join(ROOT, d))
                        log_system(f"🗑️ ĐÃ XÓA DỌN DẸP THƯ MỤC CŨ ({delta_days} ngày): {d}")
                except: pass
    except: pass

def sweep_old_files_to_today():
    today_str = datetime.now().strftime("%Y-%m-%d")
    if not os.path.exists(ROOT): return
    for d in os.listdir(ROOT):
        if d == today_str or len(d) != 10: continue
        try: datetime.strptime(d, "%Y-%m-%d")
        except: continue
        if d >= today_str: continue
            
        d_path = os.path.join(ROOT, d)
        if not os.path.isdir(d_path): continue
        
        def check_move(tdir):
            for f in os.listdir(tdir):
                p = os.path.join(tdir, f) 
                if not os.path.isfile(p): continue
                if is_target_file(f):
                    rel_path = os.path.relpath(tdir, d_path)
                    today_dir = os.path.join(ROOT, today_str)
                    if rel_path != ".": today_dir = os.path.join(today_dir, rel_path)
                    old_day = d.split("-")[-1]
                    base_name, ext = os.path.splitext(f)
                    new_f_name = f"{base_name}_Ngay{old_day}{ext}" if f"_ngay{old_day}" not in base_name.lower() else f
                    target = os.path.join(today_dir, new_f_name)
                    try:
                        os.makedirs(os.path.dirname(target), exist_ok=True); time.sleep(0.5) 
                        if MACHINE_NAME == "cnc": os.rename(p, target)
                        else: os.replace(p, target)
                        
                        with state_lock:
                            recent_moved[p.lower()] = time.time(); recent_moved[target.lower()] = time.time()
                            processed_set.discard(p.lower()); processed_set.add(target.lower())
                            
                        new_base = os.path.splitext(new_f_name)[0]
                        process_event(
                            p,
                            "ROLLOVER",
                            machine_meta_extra={
                                "rollover_source_path": p,
                                "rollover_source_name": f,
                                "rollover_target_path": target,
                                "rollover_target_name": new_f_name,
                                "rollover_old_date": d,
                                "rollover_new_date": today_str,
                                "rollover_reason": "new_day",
                            },
                        )
                        process_event(target, "WRONG_DAY", forced_base_id=new_base, forced_display_name=new_base)
                    except: pass
        check_move(d_path)
        for sub in os.listdir(d_path):
            sp = os.path.join(d_path, sub)
            if os.path.isdir(sp) and sub.lower() != "new folder": check_move(sp)

# ----------------- MÁY IN BẠT -----------------
def worker_inbat_log():
    paths = [r"C:\Program Files (x86)\PrintMon USB3.0 510 508GS 1020\PrintFile.ini", r"C:\Program Files (x86)\PrintMon USB3.0 510 508GS 1020\PrintFile"]
    active = next((p for p in paths if os.path.exists(p)), paths[0])
    last_raw = b""; cur_job = None; cur_switch = None; cur_progress_bucket = None
    
    if os.path.exists(active):
        try:
            with open(active, "rb") as f: last_raw = f.read()
        except: pass

    while True:
        try:
            if os.path.exists(active):
                with open(active, "rb") as f: raw = f.read()
                if raw != last_raw:
                    time.sleep(0.5); 
                    with open(active, "rb") as f: raw = f.read(); last_raw = raw
                    event, state = parse_inbat_printmon_snapshot(raw, cur_job, cur_switch, cur_progress_bucket)
                    next_job, next_switch, next_progress_bucket = state
                    if event:
                        event_type, fp = event[0], event[1]
                        meta = event[2] if len(event) > 2 else None
                        bn = os.path.basename(fp).lower().strip()
                        if cur_job != fp:
                            if event_type == "PRINTING": log_system(f"Đang In: {bn}")
                            elif event_type == "DONE": log_system(f"IN XONG SIÊU TỐC: {bn}")
                        elif cur_switch == 1 and event_type == "DONE":
                            log_system(f"CHỐT ĐƠN IN XONG: {bn}")
                        elif cur_switch == 2 and event_type == "PRINTING":
                            log_system(f"Đang In Lại: {bn}")
                        process_event(fp, event_type, machine_meta_extra=meta)
                    if cur_job is not None and next_job is None:
                        log_system(f"Lệnh in DỪNG: {os.path.basename(cur_job)}")
                    cur_job, cur_switch, cur_progress_bucket = next_job, next_switch, next_progress_bucket
                    continue
                    ext_idx = raw.lower().find(b'.prt'); ext_idx = raw.lower().find(b'.prn') if ext_idx == -1 else ext_idx
                    if ext_idx != -1:
                        start_idx = -1
                        for i in range(ext_idx, -1, -1):
                            if i > 0 and raw[i:i+2] == b':\\': start_idx = i - 1; break
                        if start_idx != -1:
                            fp = raw[start_idx:ext_idx+4].decode('utf-8', 'ignore').strip()
                            bn = os.path.basename(fp).lower().strip()
                            sw = next((b for b in raw[ext_idx+4:] if b not in (0x00, 0x20, 0x09, 0x0A, 0x0D)), None)
                            if sw in (1, 2):
                                if cur_job != fp:
                                    cur_job = fp; cur_switch = sw
                                    if sw == 1: log_system(f"⏳ Đang In: {bn}"); process_event(fp, "PRINTING")
                                    elif sw == 2: log_system(f"🎯 IN XONG SIÊU TỐC: {bn}"); process_event(fp, "DONE")
                                else:
                                    if cur_switch == 1 and sw == 2:
                                        log_system(f"🎯 CHỐT ĐƠN IN XONG: {bn}"); process_event(fp, "DONE"); cur_switch = 2 
                                    elif cur_switch == 2 and sw == 1:
                                        log_system(f"⏳ Đang In Lại: {bn}"); cur_switch = 1
                                    else: cur_switch = sw
                    else:
                        if cur_job is not None: log_system(f"🛑 Lệnh in DỪNG: {os.path.basename(cur_job)}"); cur_job = None; cur_switch = None
        except: pass
        time.sleep(1)

def safe_move_tif_worker():
    global processed_prt, stable_prts
    while True:
        try:
            today_str = datetime.now().strftime("%Y-%m-%d")
            today_path = os.path.join(ROOT, today_str)
            if not os.path.exists(today_path): time.sleep(5); continue

            target_folders = [os.path.join(today_path, "New Folder")]
            for item in os.listdir(today_path):
                sub = os.path.join(today_path, item)
                if os.path.isdir(sub) and item.lower() != "new folder":
                    nf = os.path.join(sub, "New Folder")
                    if os.path.exists(nf): target_folders.append(nf)

            current_scan = set()
            for nf in target_folders:
                if not os.path.exists(nf): continue
                for f in os.listdir(nf):
                    if f.lower().endswith((".prt", ".prn")):
                        p = os.path.join(nf, f)
                        current_scan.add(p)

                        try: sz = os.path.getsize(p); mtime = os.path.getmtime(p) 
                        except: continue
                        ts = time.time()
                        if p not in stable_prts: stable_prts[p] = (sz, mtime, ts); continue

                        last_sz, last_mtime, last_time = stable_prts.get(p)
                        if sz != last_sz or mtime != last_mtime: stable_prts[p] = (sz, mtime, ts); continue

                        prt_mb = sz / (1024 * 1024)
                        required_wait = 10      
                        if prt_mb > 250: required_wait = 15  
                        if prt_mb > 800: required_wait = 25  
                        if prt_mb > 1500: required_wait = 45 

                        if ts - last_time < required_wait: continue

                        p_lower = p.lower()
                        if p_lower not in processed_prt or processed_prt[p_lower] != mtime:
                            processed_prt[p_lower] = mtime
                            process_event(p, "RIP")
                            with state_lock:
                                processed_set.add(p_lower)
                                save_state(processed_set)
                            
                            base = os.path.splitext(f)[0].lower().strip()
                            if base.endswith(".tif") or base.endswith(".jpg"): base = base[:-4]
                                
                            parent_dir = os.path.dirname(os.path.dirname(p))
                            origin_name = None
                            for f_orig in os.listdir(parent_dir):
                                if os.path.splitext(f_orig)[0].lower().strip() == base and f_orig.lower().endswith((".tif", ".jpg")):
                                    origin_name = f_orig
                                    break

                            if origin_name:
                                tif_origin = os.path.join(parent_dir, origin_name)
                                target = os.path.join(nf, origin_name)
                                if os.path.exists(target) and os.path.exists(tif_origin):
                                    try: os.remove(target)
                                    except: pass
                                try:
                                    with state_lock:
                                        recent_moved[tif_origin.lower()] = time.time()
                                        recent_moved[target.lower()] = time.time()
                                    shutil.move(tif_origin, target)
                                except Exception as e: pass
                                    
            for p in list(stable_prts.keys()):
                if p not in current_scan: stable_prts.pop(p, None)
        except: pass
        time.sleep(3)

def start_inbat_mode():
    threading.Thread(target=worker_inbat_log, daemon=True).start()
    threading.Thread(target=safe_move_tif_worker, daemon=True).start()
    log_system("🚀 [IN BẠT] - Khởi động bộ quét...")

# ----------------- MÁY IN DECAL -----------------
def parse_indecal_log_events(lines, state):
    events = []
    start_keywords = ("启动任务：", "启动任务:", "å¯åŠ¨ä»»åŠ¡ï¼š", "å¯åŠ¨ä»»åŠ¡:", "Ã†Ã´Â¶Â¯ÃˆÃŽÃŽÃ±Â£Âº")
    done_keywords = ("打印动作完成", "打印完成", "打印结束", "æ‰“å°åŠ¨ä½œå®Œæˆ", "æ‰“å°ç»“æŸ", "æ‰“å°å®Œæˆ")
    cancel_keywords = ("PRINT_RESULT_CANCEL", "printing is cancelled", "取消打印", "ÃˆÂ¡ÃÃ»Â´Ã²Ã“Â¡")

    def progress_meta(text="", include_done_time=False):
        total_pass = state.get("total_pass") or 0
        current_pass = state.get("max_pass")
        meta = {}
        time_match = re.search(r"(20\d{2})/(\d{2})/(\d{2})\s+(\d{2}:\d{2}:\d{2})", str(text or ""))
        if time_match:
            log_time = f"{time_match.group(1)}-{time_match.group(2)}-{time_match.group(3)} {time_match.group(4)}"
            meta["log_event_time"] = log_time
            if include_done_time:
                meta["log_done_time"] = log_time
        if total_pass and current_pass is not None:
            meta.update({
                "current_pass": current_pass,
                "total_pass": total_pass,
                "progress_percent": min(100.0, max(0.0, current_pass * 100.0 / total_pass)),
            })
        return meta

    for line in lines:
        text = str(line or "")
        start_name = ""
        for keyword in start_keywords:
            if keyword in text:
                start_name = text.split(keyword, 1)[1].strip()
                break
        if start_name:
            task_name = os.path.basename(start_name.strip("'\""))
            if not task_name.lower().endswith(".prn"):
                task_name = os.path.splitext(task_name)[0] + ".prn"
            stem = os.path.splitext(task_name)[0]
            base_id = stem.split("~", 1)[1] if "~" in stem else stem
            if base_id.lower().endswith((".tif", ".jpg")):
                base_id = os.path.splitext(base_id)[0]
            state["current_print_job"] = task_name
            state["current_print_id"] = base_id
            state["total_pass"] = None
            state["current_pass"] = None
            state["max_pass"] = None
            state["last_progress_bucket"] = None
            events.append({"event_type": "PRINTING", "file_name": task_name, "forced_base_id": base_id, "machine_meta": {}})
            continue

        total_match = re.search(r"nTotalPrintPass=(\d+)", text)
        if total_match:
            state["total_pass"] = int(total_match.group(1))
            continue

        pass_match = re.search(r"nCurPassIndex=(\d+)", text)
        if pass_match:
            current_pass = int(pass_match.group(1))
            state["current_pass"] = current_pass
            state["max_pass"] = max(state.get("max_pass") or 0, current_pass)
            job = state.get("current_print_job")
            base_id = state.get("current_print_id") or (os.path.splitext(job)[0] if job else "")
            total_pass = state.get("total_pass") or 0
            if job and total_pass:
                progress = min(100.0, max(0.0, (state.get("max_pass") or 0) * 100.0 / total_pass))
                bucket = int(progress)
                last_bucket = state.get("last_progress_bucket")
                if last_bucket is None or bucket > int(last_bucket):
                    state["last_progress_bucket"] = bucket
                    events.append({"event_type": "PRINTING", "file_name": job, "forced_base_id": base_id, "machine_meta": progress_meta(text)})
            continue

        job = state.get("current_print_job")
        if not job:
            continue
        base_id = state.get("current_print_id") or os.path.splitext(job)[0]

        if any(keyword in text for keyword in done_keywords):
            events.append({"event_type": "DONE", "file_name": job, "forced_base_id": base_id, "machine_meta": progress_meta(text, include_done_time=True)})
            state["current_print_job"] = None
            state["current_print_id"] = None
            continue
        if any(keyword in text for keyword in cancel_keywords):
            events.append({"event_type": "DELETE", "file_name": job, "forced_base_id": base_id, "machine_meta": progress_meta(text, include_done_time=True)})
            state["current_print_job"] = None
            state["current_print_id"] = None
            continue
    return events

def infer_existing_renamed_prn(path, meta_path):
    prn_base, prn_ext = os.path.splitext(os.path.basename(path))
    meta_base = os.path.splitext(os.path.basename(meta_path))[0]
    candidate = os.path.join(os.path.dirname(path), f"{prn_base}~{meta_base}{prn_ext}")
    return candidate if os.path.exists(candidate) else None

def select_indecal_meta_file(day_folder):
    meta_files = [mf for mf in os.listdir(day_folder) if is_meta_file(mf)]
    meta_files.sort(key=lambda x: os.path.getmtime(os.path.join(day_folder, x)), reverse=True)
    return meta_files

def handle_indecal_prn_rename_candidate(path, today_str, day_folder, new_folder, filename, now_ts=None):
    global prn_tracking, processed_prn, processed_set
    now_ts = now_ts or time.time()
    try:
        current_size = os.path.getsize(path)
        if current_size == 0:
            return "EMPTY"
    except Exception as exc:
        inferred_path = None
        try:
            meta_files = select_indecal_meta_file(day_folder)
            if meta_files:
                inferred_path = infer_existing_renamed_prn(path, os.path.join(day_folder, meta_files[0]))
        except Exception:
            inferred_path = None
        if inferred_path:
            indecal_audit("RENAME_RACE_OK", prn_path=path, target_prn_path=inferred_path, error=str(exc))
            processed_prn.add(inferred_path.lower())
            with state_lock:
                processed_set.add(inferred_path.lower())
            process_event(inferred_path, "RIP")
            prn_tracking.pop(path, None)
            return "RACE_OK"
        return "MISSING"

    if path not in prn_tracking:
        prn_tracking[path] = {
            "size": current_size,
            "last_changed": now_ts,
            "first_seen": now_ts,
            "last_meta_wait_log": 0,
            "retry": 0,
        }
        indecal_audit("RENAME_WAIT_STABLE", prn_path=path, file_size=current_size)
        return "WAIT_STABLE"

    tracking = prn_tracking[path]
    if current_size != tracking.get("size"):
        tracking["size"] = current_size
        tracking["last_changed"] = now_ts
        return "WAIT_STABLE"

    if now_ts - tracking.get("last_changed", now_ts) < 5:
        return "WAIT_STABLE"

    meta_files = select_indecal_meta_file(day_folder)
    if not meta_files:
        first_seen = tracking.setdefault("first_seen", tracking.get("last_changed", now_ts))
        action = "RENAME_STUCK_NO_META" if now_ts - first_seen >= INDECAL_RENAME_STUCK_SECONDS else "RENAME_WAIT_META"
        if now_ts - tracking.get("last_meta_wait_log", 0) >= 15:
            indecal_audit(
                action,
                prn_path=path,
                file_size=current_size,
                retry_count=tracking.get("retry", 0),
                error="Plain PRN is held until metadata arrives",
                extra={"wait_seconds": int(now_ts - first_seen)},
            )
            tracking["last_meta_wait_log"] = now_ts
        return "WAIT_META"

    matched_meta_name = meta_files[0]
    meta_path = os.path.join(day_folder, matched_meta_name)
    indecal_audit("RENAME_META_SELECTED", prn_path=path, meta_path=meta_path, file_size=current_size, extra={"meta_count": len(meta_files)})

    try:
        if os.path.getmtime(path) < os.path.getctime(meta_path) - 3:
            prn_base, prn_ext = os.path.splitext(filename)
            ghost_path = os.path.join(new_folder, f"{prn_base}~ghost{prn_ext}")
            os.replace(path, ghost_path)
            indecal_audit("RENAME_GHOST_OLD_PRN", prn_path=path, meta_path=meta_path, target_prn_path=ghost_path, file_size=current_size)
            prn_tracking.pop(path, None)
            return "GHOST"
    except Exception as exc:
        inferred_path = infer_existing_renamed_prn(path, meta_path)
        if inferred_path:
            indecal_audit("RENAME_RACE_OK", prn_path=path, meta_path=meta_path, target_prn_path=inferred_path, file_size=current_size, error=str(exc))
            prn_tracking.pop(path, None)
            return "RACE_OK"
        indecal_audit("RENAME_FAIL_GHOST", prn_path=path, meta_path=meta_path, file_size=current_size, error=str(exc))
        return "RETRY"

    prn_base, prn_ext = os.path.splitext(filename)
    meta_base, meta_ext = os.path.splitext(matched_meta_name)
    new_prn_name = f"{prn_base}~{meta_base}{prn_ext}"
    new_prn_path = os.path.join(new_folder, new_prn_name)
    with state_lock:
        recent_moved[path.lower()] = time.time()
        processed_set.add(new_prn_path.lower())

    try:
        os.replace(path, new_prn_path)
        indecal_audit("RENAME_OK", prn_path=path, meta_path=meta_path, target_prn_path=new_prn_path, file_size=current_size, retry_count=tracking.get("retry", 0))
    except Exception as exc:
        inferred_path = infer_existing_renamed_prn(path, meta_path)
        if inferred_path:
            indecal_audit("RENAME_RACE_OK", prn_path=path, meta_path=meta_path, target_prn_path=inferred_path, file_size=current_size, error=str(exc))
            prn_tracking.pop(path, None)
            processed_prn.add(inferred_path.lower())
            with state_lock:
                processed_set.add(inferred_path.lower())
            process_event(inferred_path, "RIP")
            return "RACE_OK"
        tracking["retry"] = tracking.get("retry", 0) + 1
        tracking["last_changed"] = now_ts - 3
        indecal_audit("RENAME_FAIL_REPLACE", prn_path=path, meta_path=meta_path, target_prn_path=new_prn_path, file_size=current_size, retry_count=tracking.get("retry", 0), error=str(exc))
        return "RETRY"

    prn_tracking.pop(path, None)
    orig_path = None
    for f_orig in os.listdir(day_folder):
        f_base, f_ext = os.path.splitext(f_orig)
        if f_base.lower() == meta_base.lower() and get_expected_meta(f_ext) == meta_ext.lower():
            orig_path = os.path.join(day_folder, f_orig)
            break

    if orig_path and os.path.exists(orig_path):
        target_tif = os.path.join(new_folder, os.path.basename(orig_path))
        with state_lock:
            recent_moved[orig_path.lower()] = time.time()
            recent_moved[target_tif.lower()] = time.time()
        try:
            os.replace(orig_path, target_tif)
            indecal_audit("SOURCE_IMAGE_MOVE_OK", prn_path=new_prn_path, meta_path=meta_path, source_image_path=orig_path, target_image_path=target_tif, file_size=current_size)
        except Exception as exc:
            indecal_audit("SOURCE_IMAGE_MOVE_FAIL", prn_path=new_prn_path, meta_path=meta_path, source_image_path=orig_path, target_image_path=target_tif, file_size=current_size, error=str(exc))
    else:
        indecal_audit("SOURCE_IMAGE_MISSING", prn_path=new_prn_path, meta_path=meta_path, file_size=current_size, error="No matching source image found")

    try:
        os.remove(meta_path)
        indecal_audit("META_CLEANUP_OK", prn_path=new_prn_path, meta_path=meta_path, file_size=current_size, extra={"selected_meta": matched_meta_name})
    except Exception as exc:
        indecal_audit("META_CLEANUP_FAIL", prn_path=new_prn_path, meta_path=meta_path, file_size=current_size, error=str(exc), extra={"selected_meta": matched_meta_name})

    processed_prn.add(new_prn_path.lower())
    with state_lock:
        processed_set.add(new_prn_path.lower())
    process_event(new_prn_path, "RIP")
    return "RENAMED"

def worker_indecal_log():
    global current_print_job, current_print_id
    cur_f = None
    tail_state = LogTailState()
    parser_state = {}

    while True:
        try:
            today_log = f"C:\\Program Files (x86)\\PrintExp_V5.7.6.5.23\\Log\\Log[{datetime.now().strftime('%Y_%m_%d')}].txt"
            
            if today_log != cur_f:
                cur_f = today_log
                if os.path.exists(today_log):
                    tail_state = LogTailState(offset=os.path.getsize(today_log))
                else:
                    tail_state = LogTailState()
                
            if os.path.exists(today_log):
                lines, tail_state = read_new_log_lines(today_log, tail_state, encoding="gb18030")
                if lines:
                    parsed_events = parse_indecal_log_events(lines, parser_state)
                    for event in parsed_events:
                        if event["event_type"] == "DONE":
                            log_system(f"✅ IN XONG: {event['file_name']}")
                        elif event["event_type"] == "DELETE":
                            log_system(f"🛑 THỢ HỦY: {event['file_name']}")
                        process_event(
                            event["file_name"],
                            event["event_type"],
                            forced_base_id=event.get("forced_base_id"),
                            machine_meta_extra=event.get("machine_meta"),
                        )
                    current_print_job = parser_state.get("current_print_job")
                    current_print_id = parser_state.get("current_print_id")
                time.sleep(5)
                continue
                if False:
                        
                    # 🌟 BỌC THÉP V6.4.4: CHỐNG ĐỌC ĐỨT ĐOẠN DÒNG LOG KHI MÁY ĐANG GHI
                    for event in []:
                        if True:
                            if event["event_type"] == "DONE":
                                log_system(f"✅ IN XONG: {event['file_name']}")
                            elif event["event_type"] == "DELETE":
                                log_system(f"🛑 THỢ HỦY: {event['file_name']}")
                            process_event(
                                event["file_name"],
                                event["event_type"],
                                forced_base_id=event.get("forced_base_id"),
                                machine_meta_extra=event.get("machine_meta"),
                            )
                        current_print_job = parser_state.get("current_print_job")
                        current_print_id = parser_state.get("current_print_id")
                        continue
                    for line in lines:
                        if "启动任务" in line or "Æô¶¯ÈÎÎñ" in line:
                            r_name = line
                            for kw in ("启动任务：", "启动任务:", "Æô¶¯ÈÎÎñ£º"):
                                if kw in r_name: r_name = r_name.split(kw)[-1].strip(); break
                            c_name = os.path.splitext(r_name.split("\\")[-1])[0]
                            bid = c_name.split("~")[-1] if "~" in c_name else c_name
                            if bid.endswith((".tif", ".jpg")): bid = bid[:-4]
                            current_print_job = c_name; current_print_id = bid
                            process_event(current_print_job + ".prn", "PRINTING", forced_base_id=current_print_id)
                        elif current_print_job:
                            if any(k in line for k in ["打印动作完成", "打印结束", "打印完成"]):
                                log_system(f"✅ IN XONG: {current_print_job}")
                                process_event(current_print_job + ".prn", "DONE", forced_base_id=current_print_id)
                                current_print_job = None; current_print_id = None
                            elif any(k in line for k in ["PRINT_RESULT_CANCEL", "printing is cancelled", "È¡Ïû´òÓ¡"]):
                                log_system(f"🛑 THỢ HỦY: {current_print_job}"); process_event(current_print_job + ".prn", "DELETE", forced_base_id=current_print_id)
                                current_print_job = None; current_print_id = None
        except: pass
        time.sleep(5)

def fast_prn_renamer():
    global prn_tracking, processed_prn, processed_set
    while True:
        try:
            today_str = datetime.now().strftime("%Y-%m-%d")
            day_folder = os.path.join(ROOT, today_str)
            new_folder = os.path.join(day_folder, "New Folder")
            if os.path.exists(new_folder):
                current_files = os.listdir(new_folder)
                for tracked_path in list(prn_tracking.keys()):
                    if os.path.basename(tracked_path) not in current_files: del prn_tracking[tracked_path]

                for f in current_files:
                    if f.lower().endswith((".prn", ".prt")) and "~" not in f:
                        path = os.path.join(new_folder, f)
                        handle_indecal_prn_rename_candidate(path, today_str, day_folder, new_folder, f)
        except: pass
        time.sleep(2) 

def start_indecal_mode():
    threading.Thread(target=worker_indecal_log, daemon=True).start()
    threading.Thread(target=fast_prn_renamer, daemon=True).start()
    log_system("🚀 [IN DECAL] - Khởi động bộ quét...")

# ----------------- MÁY CNC -----------------
def worker_cnc_log():
    last_sz = 0; cur_f = None; m_state = "IDLE"; cur_job = "" 
    log_p = r"C:\Program Files\Weihong\Ncstudio V5.5.60\Ncstudio.log"
    
    if os.path.exists(log_p): 
        try: last_sz = os.path.getsize(log_p); cur_f = log_p
        except: pass

    while True:
        try:
            if not os.path.exists(log_p): time.sleep(2); continue
            sz = os.path.getsize(log_p)
            if log_p != cur_f: cur_f = log_p; last_sz = sz 
            if sz < last_sz: last_sz = 0
            if sz > last_sz:
                with open(log_p, "rb") as f: 
                    f.seek(last_sz)
                    raw_data = f.read()
                    
                if not raw_data.endswith(b'\n'):
                    last_nl = raw_data.rfind(b'\n')
                    if last_nl != -1:
                        raw_data = raw_data[:last_nl+1]
                        last_sz += len(raw_data)
                    else:
                        time.sleep(1); continue
                else:
                    last_sz = sz

                lines = raw_data.decode("gbk", "ignore").splitlines()
                for l in lines:
                    line = l.replace("‘", "'").replace("’", "'")
                    if "Initiate a simulation" in line: m_state = "SIMULATING"
                    elif "Initiate a machining task" in line:
                        m_state = "CUTTING"
                        try:
                            ep = list(line.split("'"))[1]
                            if ep: cur_job = ep; process_event(ep, "CUTTING")
                        except: pass
                    elif "中断终止" in line:
                        if m_state == "CUTTING" and cur_job: 
                            log_system(f"🛑 THỢ HỦY: {cur_job}"); process_event(cur_job, "DELETE"); m_state = "IDLE"; cur_job = ""
                    elif "正常完毕" in line:
                        if m_state == "CUTTING" and cur_job:
                            log_system(f"✅ CẮT XONG: {cur_job}"); process_event(cur_job, "DONE")
                            if os.path.exists(cur_job):
                                fold = os.path.dirname(cur_job)
                                if os.path.basename(fold).lower() != "new folder":
                                    nf = os.path.join(fold, "New Folder"); os.makedirs(nf, exist_ok=True); tp = os.path.join(nf, os.path.basename(cur_job))
                                    for attempt in range(3):
                                        try:
                                            time.sleep(1)
                                            shutil.move(cur_job, tp)
                                            with state_lock: 
                                                recent_moved[tp.lower()] = time.time()
                                                recent_moved[cur_job.lower()] = time.time() 
                                            break
                                        except:
                                            time.sleep(2)
                            m_state = "IDLE"; cur_job = ""
                        elif m_state == "SIMULATING": m_state = "IDLE"
        except: pass
        time.sleep(2)

def start_cnc_mode():
    threading.Thread(target=worker_cnc_log, daemon=True).start()
    log_system("🚀 [CNC] - Khởi động bộ quét...")

# =========================================
# VÒNG LẶP QUÉT FOLDER CHUNG
# =========================================
def scan_pair_folder(tdir, fset):
    if not os.path.exists(tdir): return
    for f in os.listdir(tdir):
        p = os.path.join(tdir, f)
        if os.path.isfile(p) and is_target_file(f): fset.add(p.lower())
    nf_dir = os.path.join(tdir, "New Folder")
    if os.path.exists(nf_dir):
        for f in os.listdir(nf_dir):
            p = os.path.join(nf_dir, f)
            if os.path.isfile(p):
                if MACHINE_NAME == "cnc" and is_target_file(f): fset.add(p.lower())
                elif MACHINE_NAME in ["inbat", "indecal"] and f.lower().endswith((".prt", ".prn")): fset.add(p.lower())

def scan_day(today_str):
    fset = set(); tpath = os.path.join(ROOT, today_str)
    if not os.path.exists(tpath): return fset
    scan_pair_folder(tpath, fset)
    for item in os.listdir(tpath):
        ipath = os.path.join(tpath, item)
        if os.path.isdir(ipath) and item.lower() != "new folder": scan_pair_folder(ipath, fset)
    return fset

def run_universal_scan_once(cur_date, last_curr):
    global processed_set
    ts = time.time()
    n_date = datetime.now().strftime("%Y-%m-%d")
    if n_date != cur_date: cur_date = n_date; last_curr = set()
    try: os.makedirs(os.path.join(ROOT, cur_date, "New Folder"), exist_ok=True)
    except: pass

    sweep_old_files_to_today()

    with state_lock:
        for k in list(recent_moved.keys()):
            if ts - recent_moved.get(k) > 900: recent_moved.pop(k, None)

    curr = scan_day(cur_date)

    with state_lock:
        created = curr - processed_set
        deleted = last_curr - curr

        for p in created:
            if not os.path.exists(p): continue

            if p.lower() in recent_moved:
                recent_moved.pop(p.lower(), None)
                continue

            should_remember = True

            if MACHINE_NAME == "cnc":
                if "new folder" not in p.lower(): process_event(p, "EXPORT")
            else:
                ext = os.path.splitext(p)[1].lower()
                if MACHINE_NAME == "indecal" and ("~error" in p.lower() or "~skipped" in p.lower() or "~ghost" in p.lower()):
                    pass
                elif is_export_file(p):
                    process_event(p, "EXPORT")
                elif ext in (".prn", ".prt") and MACHINE_NAME != "inbat":
                    if MACHINE_NAME == "indecal" and "~" not in os.path.basename(p):
                        should_remember = False
                    else:
                        process_event(p, "RIP")

            if should_remember:
                processed_set.add(p)

        for p in deleted:
            if p.lower().endswith((".prt", ".prn")):
                base_name = os.path.splitext(os.path.basename(p))[0].lower().strip()
                if base_name.endswith(".tif") or base_name.endswith(".jpg"): base_name = base_name[:-4]
                parent_dir = os.path.dirname(os.path.dirname(p))
                tif_origin = os.path.join(parent_dir, base_name + ".tif").lower()
                tif_target = os.path.join(os.path.dirname(p), base_name + ".tif").lower()
                if os.path.exists(tif_origin):
                    try:
                        recent_moved[tif_origin] = time.time(); recent_moved[tif_target] = time.time()
                        os.replace(tif_origin, tif_target)
                    except: pass
                processed_prt.pop(p.lower(), None)

            if p.lower() in recent_moved:
                recent_moved.pop(p.lower(), None)
            else:
                process_event(p, "DELETE")

            processed_set.discard(p)

    save_state(processed_set)

    dead = [p for p in processed_set if not os.path.exists(p)]; [processed_set.discard(p) for p in dead]
    if MACHINE_NAME == "indecal":
        d_prn = [p for p in processed_prn if not os.path.exists(p)]; [processed_prn.discard(p) for p in d_prn]

    return cur_date, curr

def universal_folder_scanner():
    global processed_set
    cur_date = datetime.now().strftime("%Y-%m-%d")
    last_curr = scan_day(cur_date)
    
    while True:
        try:
            cur_date, last_curr = run_universal_scan_once(cur_date, last_curr)
            time.sleep(SCAN_INTERVAL)
        except Exception as e: 
            log_system(f"❌ LỖI QUÉT THƯ MỤC: {str(e)}", is_error=True)
            time.sleep(5)

def report_version_to_server():
    ping_url = API_SERVER_URL.replace("/log_event", "/ping")
    payload = {
        "machine": MACHINE_NAME,
        "version": CLIENT_VERSION,
        "hostname": socket.gethostname(),
        "pid": os.getpid(),
        "start_time": CLIENT_START_TIME,
        "instance_id": CLIENT_INSTANCE_ID,
    }
    logged_success = False
    while True:
        try:
            requests.post(ping_url, json=payload, timeout=5)
            if not logged_success:
                log_system(f"✅ Đã báo cáo phiên bản {CLIENT_VERSION} lên Server!")
                logged_success = True
            time.sleep(60)
        except:
            time.sleep(10)

def auto_update_watcher():
    start_mtime = 0
    while True:
        time.sleep(10)
        try:
            if not os.path.exists(NAS_EXE_PATH): continue
            cur_mtime = os.path.getmtime(NAS_EXE_PATH)
            
            if start_mtime == 0: 
                start_mtime = cur_mtime
            elif cur_mtime != start_mtime:
                log_system("🚀 PHÁT HIỆN BẢN MỚI TRÊN NAS! SẼ THOÁT ĐỂ LÊN ĐỜI...")
                os._exit(0) 
        except: pass

if __name__ == "__main__":
    current_pc = socket.gethostname().lower() 
    print("=====================================================")
    print(f"🤖 PHAN MEM QUAN LY XUONG - {CLIENT_VERSION}")
    print("=====================================================")

    machine_config = resolve_machine_config(current_pc, MACHINE_ALIASES)
    if machine_config:
        MACHINE_NAME = machine_config.machine_name
        MACHINE_DISPLAY = machine_config.machine_display
        ROOT = machine_config.root
        BASE_STORAGE = machine_config.base_storage
    else:
        print(f"🛑 MAY NAY KHONG CO TRONG DANH SACH!"); time.sleep(100); os._exit(0)

    STATE_FILE = os.path.join(BASE_STORAGE, f"state_{MACHINE_NAME}.json")
    LOG_FILE = os.path.join(BASE_STORAGE, "system_log.txt")

    CLIENT_INSTANCE_LOCK = acquire_client_instance_lock(MACHINE_NAME, BASE_STORAGE)
    if CLIENT_INSTANCE_LOCK is None:
        print(f"🛑 {MACHINE_DISPLAY} da co QuanLyXuong dang chay. Thoat instance trung.")
        time.sleep(3)
        os._exit(0)

    outbox_path = os.path.join(BASE_STORAGE, "Data", f"agent_outbox_{MACHINE_NAME}.db")
    OUTBOX = EventOutbox(outbox_path)
    log_system(f"🧾 Outbox local: {outbox_path}")

    processed_set = load_state()
    threading.Thread(target=outbox_sender_worker, daemon=True).start()
    threading.Thread(target=report_version_to_server, daemon=True).start()
    threading.Thread(target=auto_update_watcher, daemon=True).start()
    threading.Thread(target=fast_folder_renamer_worker, daemon=True).start()

    if MACHINE_NAME == "inbat": start_inbat_mode()
    elif MACHINE_NAME == "indecal": start_indecal_mode()
    elif MACHINE_NAME == "cnc": start_cnc_mode()

    universal_folder_scanner()
