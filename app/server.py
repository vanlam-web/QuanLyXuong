# =========================================
# SERVER V7.6.0 - GỌT GIŨA NHẬT KÝ & BẤM GIỜ THÔNG MINH
# Tích hợp: Anti-Spam + Cắt gọt text (Rip file, In lần n) + Đo thời gian chạy
# =========================================
import os, time, sqlite3, subprocess, hashlib, threading, json, requests, base64, re
from datetime import datetime
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import uvicorn
from pydantic import BaseModel
from typing import Optional, List
from contextlib import asynccontextmanager
from qlx_config import AUTO_CRM_WAKE_URL, DB_DIR, ENABLE_AUTO_CRM, ENABLE_SERVER_ZALO, NAS_SERVER_EXE_PATH, OPENCLAW_PATH, RUNTIME_MODE, SERVER_HOST, SERVER_PORT
from machine_file_meta import collect_machine_file_meta_for_server

# ================= CONFIG =================
SERVER_VERSION = "V7.6.7_INSTANCE_PING"
MACHINES = dict(InBat="PRINT", InDecal="PRINT", CNC="CUT")
ZALO_TARGET = os.getenv("SERVER_ZALO_TARGET", "")
LOG_FILE = r"C:\QuanLyXuong\Server_Log.txt"
NAS_EXE_PATH = NAS_SERVER_EXE_PATH
CREATE_NO_WINDOW = 0x08000000  

os.makedirs(DB_DIR, exist_ok=True)
THUMB_DIR = os.path.join(DB_DIR, "Thumbnails")
os.makedirs(THUMB_DIR, exist_ok=True)

class RequestData(BaseModel):
    machine: str
    path: str
    event_type: str
    forced_base_id: Optional[str] = None
    forced_display_name: Optional[str] = None
    thumbnail_b64: Optional[str] = None
    event_time: Optional[str] = None
    event_id: Optional[str] = None
    idempotency_key: Optional[str] = None
    machine_meta: Optional[dict] = None

class RenameAuditPayload(BaseModel):
    machine: str = "indecal"
    action: str
    prn_path: Optional[str] = None
    meta_path: Optional[str] = None
    target_prn_path: Optional[str] = None
    source_image_path: Optional[str] = None
    target_image_path: Optional[str] = None
    file_size: Optional[int] = 0
    retry_count: Optional[int] = 0
    error: Optional[str] = ""
    event_time: Optional[str] = None
    extra: Optional[dict] = None

def now(): return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def event_timestamp(value):
    if not value:
        return now()
    try:
        datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
        return value
    except Exception:
        return now()

def log_sys(msg):
    print(f"[{now()}] {msg}")
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f: 
            f.write(f"[{now()}] {msg}\n")
    except: pass

def has_useful_machine_meta(meta):
    if not isinstance(meta, dict):
        return False
    useful_keys = ("area_m2", "width_cm", "height_cm", "image_width_px", "image_height_px", "line_count", "width_mm", "height_mm")
    return any(meta.get(key) not in (None, "", 0) for key in useful_keys)

def needs_machine_meta_refresh(meta):
    if not has_useful_machine_meta(meta):
        return True
    source_kind = str(meta.get("source_kind") or "").lower()
    metadata_source = str(meta.get("metadata_source") or "").lower()
    return source_kind == "rip_preview_bmp" or metadata_source.endswith(".prn.bmp")

def rename_audit_db_path():
    return os.path.join(DB_DIR, "indecal_rename_audit.db")

def init_rename_audit_db():
    conn = sqlite3.connect(rename_audit_db_path(), timeout=10)
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
            received_time TEXT,
            extra_json TEXT
        )
        """
    )
    conn.commit()
    return conn

def store_rename_audit(data: RenameAuditPayload):
    machine = {"indecal": "InDecal", "InDecal": "InDecal"}.get(str(data.machine or "").strip(), "InDecal")
    event_time = event_timestamp(data.event_time)
    conn = init_rename_audit_db()
    try:
        conn.execute(
            """
            INSERT INTO rename_audit
                (machine, action, prn_path, meta_path, target_prn_path, source_image_path,
                 target_image_path, file_size, retry_count, error, event_time, received_time, extra_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                machine,
                str(data.action or "").strip(),
                data.prn_path or "",
                data.meta_path or "",
                data.target_prn_path or "",
                data.source_image_path or "",
                data.target_image_path or "",
                int(data.file_size or 0),
                int(data.retry_count or 0),
                data.error or "",
                event_time,
                now(),
                json.dumps(data.extra or {}, ensure_ascii=False),
            ),
        )
        conn.commit()
    finally:
        conn.close()

def copy_thumbnail_if_missing(source_hash, target_hash):
    if not source_hash or not target_hash:
        return
    source = os.path.join(THUMB_DIR, f"{source_hash}.jpg")
    target = os.path.join(THUMB_DIR, f"{target_hash}.jpg")
    if os.path.exists(target) or not os.path.exists(source):
        return
    try:
        with open(source, "rb") as src, open(target, "wb") as dst:
            dst.write(src.read())
    except Exception as exc:
        log_sys(f"Khong copy duoc thumbnail {source_hash} -> {target_hash}: {exc}")

def prefer_full_file_path(current_path, incoming_path):
    if incoming_path and os.path.isabs(str(incoming_path)):
        return incoming_path
    if current_path and os.path.isabs(str(current_path)):
        return current_path
    return incoming_path or current_path or ""

def seconds_between(start_time, end_time):
    try:
        start = datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S")
        end = datetime.strptime(end_time, "%Y-%m-%d %H:%M:%S")
        return (end - start).total_seconds()
    except Exception:
        return None

def merge_machine_meta(stored_meta_json, incoming_meta):
    try:
        stored_meta = json.loads(stored_meta_json or "{}")
    except Exception:
        stored_meta = {}
    if isinstance(incoming_meta, dict):
        stored_meta.update(incoming_meta)
    return stored_meta

def meta_progress_percent(meta):
    if not isinstance(meta, dict):
        return None
    value = meta.get("progress_percent")
    try:
        return float(value) if value is not None else None
    except Exception:
        return None

def normalized_job_core(machine, display_name, forced_base_id=None):
    source = forced_base_id if machine.lower() == "indecal" and forced_base_id else display_name
    core_name = os.path.splitext(os.path.basename(str(source or "")))[0]
    if machine.lower() == "indecal" and "~" in core_name:
        prefix, rest = core_name.split("~", 1)
        if prefix.isdigit() and rest:
            core_name = rest
    return core_name.lower().strip()

def storage_day_for_event(event_time, file_path):
    if event_time:
        try:
            return datetime.strptime(event_time, "%Y-%m-%d %H:%M:%S").strftime("%Y-%m-%d")
        except Exception:
            pass
    match = re.search(r"(20\d{2}-\d{2}-\d{2})", str(file_path or ""))
    if match:
        try:
            return datetime.strptime(match.group(1), "%Y-%m-%d").strftime("%Y-%m-%d")
        except Exception:
            pass
    return datetime.now().strftime("%Y-%m-%d")

def normalize_event_path(file_path):
    return str(file_path or "").replace("/", "\\").lower().strip()

def logical_event_key(machine, event_type, file_path, event_time, forced_base_id=None):
    path_part = normalize_event_path(forced_base_id or file_path)
    raw = "|".join([
        "logical-v2",
        str(machine or "").lower().strip(),
        str(event_type or "").upper().strip(),
        path_part,
        str(event_time or "").strip(),
    ])
    return "logical:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()

def send_zalo(msg):
    if not ENABLE_SERVER_ZALO:
        log_sys("V2 mode: SERVER_ZALO disabled, skip send.")
        return
    if not ZALO_TARGET:
        log_sys("⚠️ Chưa cấu hình SERVER_ZALO_TARGET, bỏ qua gửi Zalo.")
        return
    try:
        cmd_args = [OPENCLAW_PATH, "message", "send", "--channel", "zalouser", "--target", ZALO_TARGET, "--message", msg.replace("\n", "\\n"), "--profile", "default"]
        p = subprocess.Popen(cmd_args, creationflags=CREATE_NO_WINDOW, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if p.wait() == 0: log_sys("🟢 Đã gửi Zalo!")
    except Exception as e: log_sys(f"❌ LỖI GỬI ZALO: {e}")

# 🌟 BỘ GỌT GIŨA CHỮ: Chuẩn hóa "Đang in (L1)" -> "In", "Xong RIP" -> "Rip file"
def format_event_name(txt):
    if not txt: return "Không rõ"
    if txt == "EXPORT" or txt == "EXPORTED" or "Xuất" in txt: return "Xuất file"
    if "RIP" in txt.upper(): return "Rip file"
    
    if "Đang in" in txt or "Đang cắt" in txt:
        action = "In" if "in" in txt.lower() else "Cắt"
        match = re.search(r'\(L(\d+)\)', txt)
        if match:
            num = int(match.group(1))
            return action if num <= 1 else f"{action} lần {num}"
        return action
    return txt

# 🌟 BỘ BẤM GIỜ ĐIỆN TỬ
def get_duration(hist_str, end_time_str):
    try:
        h_list = json.loads(hist_str)
        start_time = None
        for item in reversed(h_list):
            if item.get("status") in ["PRINTING", "CUTTING"]:
                start_time = item.get("time")
                break
        if start_time:
            fmt = "%Y-%m-%d %H:%M:%S"
            t1 = datetime.strptime(start_time, fmt)
            t2 = datetime.strptime(end_time_str, fmt)
            diff = int((t2 - t1).total_seconds())
            if diff <= 0: return ""
            if diff < 60: return f"(⏱️ {diff} giây)"
            return f"(⏱️ {diff//60} phút {diff%60} giây)"
    except: pass
    return ""

def init_all_databases():
    for m in MACHINES.keys():
        db_path = os.path.join(DB_DIR, f"{m}.db")
        conn = sqlite3.connect(db_path, timeout=30)
        conn.execute("PRAGMA journal_mode=WAL;")
        c = conn.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS files (
            file_hash TEXT PRIMARY KEY, file_name TEXT, file_path TEXT, machine TEXT, job_type TEXT, status TEXT, 
            created_time TEXT, updated_time TEXT, zalo_sent INTEGER DEFAULT 0, run_count INTEGER DEFAULT 1)""")
        c.execute("CREATE TABLE IF NOT EXISTS app_info (key TEXT PRIMARY KEY, value TEXT)")
        try:
            cols = [col[1] for col in c.execute("PRAGMA table_info(files)").fetchall()]
            if "run_count" not in cols: c.execute("ALTER TABLE files ADD COLUMN run_count INTEGER DEFAULT 1")
            if "history" not in cols: c.execute("ALTER TABLE files ADD COLUMN history TEXT DEFAULT '[]'")
            if "machine_meta_json" not in cols: c.execute("ALTER TABLE files ADD COLUMN machine_meta_json TEXT DEFAULT '{}'")
        except: pass
        try: c.execute("UPDATE files SET status='EXPORTED' WHERE status='EXPORT'")
        except: pass
        conn.commit(); conn.close()

def get_stats(conn, mtype):
    try:
        c = conn.cursor()
        t = "DATE('now', 'localtime')"
        c.execute(f"SELECT COUNT(*) FROM files WHERE DATE(created_time)={t}"); tx = c.fetchone()[0]
        if mtype == "PRINT":
            c.execute("SELECT COUNT(*) FROM files WHERE status='EXPORTED'"); tx_t = c.fetchone()[0]
            c.execute(f"SELECT COUNT(*) FROM files WHERE status IN ('RIP','PRINTING','DONE') AND DATE(updated_time)={t}"); tr = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM files WHERE status='RIP'"); tr_t = c.fetchone()[0]
            c.execute(f"SELECT COUNT(*) FROM files WHERE status='DONE' AND DATE(updated_time)={t}"); ti = c.fetchone()[0]
            return f"   📊 Tiến độ: 📥 {tx}({tx_t}) ➔ 🖨️ {tr}({tr_t}) ➔ ✅ {ti}"
        else:
            c.execute("SELECT COUNT(*) FROM files WHERE status IN ('EXPORTED','CUTTING')"); tx_t = c.fetchone()[0]
            c.execute(f"SELECT COUNT(*) FROM files WHERE status='DONE' AND DATE(updated_time)={t}"); tc = c.fetchone()[0]
            return f"   📊 Tiến độ: 📥 {tx}({tx_t}) ➔ ✅ {tc}"
    except: return ""

def get_all_stats_msg(title):
    lines = [f"📋 {title} ({datetime.now().strftime('%d/%m - %H:%M')})"]
    m_icons = dict(InBat="🖼️", InDecal="🌈", CNC="⚙️")
    for m, mtype in MACHINES.items():
        db = os.path.join(DB_DIR, f"{m}.db")
        if not os.path.exists(db): continue
        try:
            conn = sqlite3.connect(db, timeout=10)
            stats = get_stats(conn, mtype)
            if stats: lines.append(f"{m_icons.get(m,'')} {m.upper()}:\n{stats}")
            conn.close()
        except: pass
    return "\n".join(lines)

def background_zalo_scheduler():
    log_sys("Đã khởi chạy trình quản lý báo cáo Zalo...")
    version_file = os.path.join(DB_DIR, "versions_tracking.json")
    known_versions = {"Server": "", "InBat": "", "InDecal": "", "CNC": ""}
    if os.path.exists(version_file):
        try:
            with open(version_file, "r") as f: known_versions = json.load(f)
        except: pass

    if known_versions.get("Server") != SERVER_VERSION:
        if known_versions.get("Server") != "":
            send_zalo(f"🎉 SERVER CẬP NHẬT THÀNH CÔNG BẢN MỚI: {SERVER_VERSION}\n⏰ {now()}")
        else:
            send_zalo(f"🟢 SERVER LÊN ĐÈN (Bản: {SERVER_VERSION})\n⏰ {now()}")
        known_versions["Server"] = SERVER_VERSION
        with open(version_file, "w") as f: json.dump(known_versions, f)
    else:
        send_zalo(f"⚡ SERVER VỪA ĐƯỢC KHỞI ĐỘNG LẠI\n⏰ {now()}")

    sent_flags = {"11:30": "", "17:30": "", "22:30": ""}
    while True:
        try:
            current_hm = datetime.now().strftime("%H:%M")
            current_date = datetime.now().strftime("%Y-%m-%d")
            updated_json = False
            for m in MACHINES:
                db = os.path.join(DB_DIR, f"{m}.db")
                if not os.path.exists(db): continue
                try:
                    conn = sqlite3.connect(db, timeout=5)
                    row = conn.execute("SELECT value FROM app_info WHERE key='version'").fetchone()
                    conn.close()
                    if row:
                        ver = row[0]
                        old_ver = known_versions.get(m, "")
                        if ver != old_ver:
                            if old_ver != "": send_zalo(f"🚀 MÁY [{m.upper()}] CẬP NHẬT THÀNH CÔNG BẢN: {ver}\n⏰ {now()}")
                            known_versions[m] = ver
                            updated_json = True
                except: pass
            
            if updated_json:
                with open(version_file, "w") as f: json.dump(known_versions, f)

            if current_hm == "11:30" and sent_flags["11:30"] != current_date:
                send_zalo(get_all_stats_msg("BÁO CÁO TIẾN ĐỘ GIỮA CA"))
                sent_flags["11:30"] = current_date
            elif current_hm == "17:30" and sent_flags["17:30"] != current_date:
                send_zalo(get_all_stats_msg("BÁO CÁO TỔNG KẾT CUỐI CA"))
                sent_flags["17:30"] = current_date
            elif current_hm == "22:30" and sent_flags["22:30"] != current_date:
                has_night_shift = False
                for m in MACHINES:
                    try:
                        conn = sqlite3.connect(os.path.join(DB_DIR, f"{m}.db"), timeout=10); c = conn.cursor()
                        c.execute("SELECT COUNT(*) FROM files WHERE updated_time >= ?", (f"{current_date} 17:30:00",))
                        if c.fetchone()[0] > 0: has_night_shift = True
                        conn.close()
                    except: pass
                if has_night_shift: send_zalo(get_all_stats_msg("BÁO CÁO TĂNG CA ĐÊM"))
                sent_flags["22:30"] = current_date
            time.sleep(20)
        except: time.sleep(20)

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
                log_sys("🚀 PHÁT HIỆN BẢN SERVER MỚI TRÊN NAS! ĐANG TỰ SÁT ĐỂ BAT LÀM VIỆC...")
                import subprocess
                subprocess.call("taskkill /F /IM server_Local.exe /T", shell=True)
                os._exit(0) 
        except: pass

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_all_databases()
    threading.Thread(target=background_zalo_scheduler, daemon=True).start()
    threading.Thread(target=auto_update_watcher, daemon=True).start()
    yield

app = FastAPI(title="Quản Lý Xưởng API", lifespan=lifespan)

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections: self.active_connections.remove(websocket)
    async def broadcast(self, message: str):
        for connection in self.active_connections:
            try: await connection.send_text(message)
            except: pass

manager = ConnectionManager()

@app.websocket("/ws/dashboard")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True: await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

@app.get("/api/broadcast")
async def manual_broadcast():
    await manager.broadcast("NEW_DATA")
    return {"status": "ok"}

class AlertPayload(BaseModel):
    machine: str; message: str

@app.post("/api/alert")
def receive_alert(data: AlertPayload):
    send_zalo(f"🚨 CẢNH BÁO TỪ MÁY [{data.machine.upper()}]:\n{data.message}\n⏰ {now()}")
    return {"status": "ok"}

@app.post("/api/indecal_rename_audit")
def receive_indecal_rename_audit(data: RenameAuditPayload):
    try:
        store_rename_audit(data)
        return {"status": "ok"}
    except Exception as exc:
        log_sys(f"[INDECAL_RENAME_AUDIT_ERROR] {exc}")
        return {"status": "error", "message": str(exc)}

class PingPayload(BaseModel):
    machine: str; version: str; hostname: Optional[str] = None
    pid: Optional[int] = None
    start_time: Optional[str] = None
    instance_id: Optional[str] = None

@app.post("/api/ping")
def ping_client(data: PingPayload):
    machine_mapped = {"inbat": "InBat", "indecal": "InDecal", "cnc": "CNC"}.get(data.machine.lower(), "Unknown")
    if machine_mapped == "Unknown": return {"status": "error"}
    try:
        db_path = os.path.join(DB_DIR, f"{machine_mapped}.db")
        conn = sqlite3.connect(db_path, timeout=10)
        old_version_row = conn.execute("SELECT value FROM app_info WHERE key='version'").fetchone()
        old_ping_row = conn.execute("SELECT value FROM app_info WHERE key='last_ping'").fetchone()
        old_version = old_version_row[0] if old_version_row else ""
        old_ping = old_ping_row[0] if old_ping_row else ""
        conn.execute("INSERT OR REPLACE INTO app_info (key, value) VALUES ('version', ?)", (data.version,))
        conn.execute("INSERT OR REPLACE INTO app_info (key, value) VALUES ('last_ping', ?)", (now(),))
        if data.hostname:
            conn.execute("INSERT OR REPLACE INTO app_info (key, value) VALUES ('hostname', ?)", (data.hostname,))
        if data.pid is not None:
            conn.execute("INSERT OR REPLACE INTO app_info (key, value) VALUES ('pid', ?)", (str(data.pid),))
        if data.start_time:
            conn.execute("INSERT OR REPLACE INTO app_info (key, value) VALUES ('start_time', ?)", (data.start_time,))
        if data.instance_id:
            conn.execute("INSERT OR REPLACE INTO app_info (key, value) VALUES ('instance_id', ?)", (data.instance_id,))
        conn.commit(); conn.close()
        if old_version != data.version or not old_ping:
            try:
                log_sys(f"🔔 MÁY {machine_mapped} ĐIỂM DANH: Bản {data.version}")
            except Exception:
                pass
        return {"status": "ok"}
    except: return {"status": "error"}

@app.post("/api/log_event")
async def log_event(data: RequestData): 
    try:
        event_time = event_timestamp(data.event_time)
        real_machine = {"inbat": "InBat", "indecal": "InDecal", "cnc": "CNC"}.get(data.machine.lower(), "Unknown")
        machine_mapped = MACHINES.get(real_machine, "UNKNOWN")
        display_name = os.path.basename(data.path)
        
        new_status = "EXPORTED" if data.event_type == "EXPORT" else data.event_type

        # GỌT TÊN CHUẨN MỰC
        core_name_clean = normalized_job_core(data.machine, display_name, data.forced_base_id)
        event_day = storage_day_for_event(event_time, data.path)
        base_string = f"{real_machine.lower()}_core_{core_name_clean}_{event_day}"
        logic_key = logical_event_key(real_machine, data.event_type, data.path, event_time, data.forced_base_id)
        
        active_hash = hashlib.md5((base_string + "_active").encode('utf-8')).hexdigest()
        done_hash = hashlib.md5((base_string + "_done").encode('utf-8')).hexdigest()
        deleted_hash = hashlib.md5((base_string + f"_deleted_{int(time.time()*1000)}").encode('utf-8')).hexdigest()

        if data.thumbnail_b64:
            try:
                img_data = base64.b64decode(data.thumbnail_b64)
                for h in [active_hash, done_hash, deleted_hash]:
                    with open(os.path.join(THUMB_DIR, f"{h}.jpg"), "wb") as f: 
                        f.write(img_data)
            except: pass
        incoming_meta = data.machine_meta or {}
        if needs_machine_meta_refresh(incoming_meta):
            try:
                fallback_meta = collect_machine_file_meta_for_server(real_machine, data.path, display_name, event_time)
                if fallback_meta:
                    incoming_meta = {**incoming_meta, **fallback_meta}
            except Exception as exc:
                incoming_meta = {"meta_error": str(exc)}
        machine_meta_json = json.dumps(incoming_meta or {}, ensure_ascii=False)

        db_path = os.path.join(DB_DIR, f"{real_machine}.db") 
        conn = sqlite3.connect(db_path, timeout=15)
        conn.execute("PRAGMA journal_mode=WAL;")
        c = conn.cursor()
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS processed_event_keys (
                idempotency_key TEXT PRIMARY KEY,
                event_id TEXT,
                machine TEXT,
                event_type TEXT,
                file_path TEXT,
                created_time TEXT
            )
            """
        )
        keys_to_check = [key for key in (data.idempotency_key, logic_key) if key]
        if keys_to_check:
            c.execute(
                "SELECT idempotency_key FROM processed_event_keys WHERE idempotency_key IN (%s)" % ",".join("?" for _ in keys_to_check),
                tuple(keys_to_check),
            )
            if c.fetchone():
                conn.close()
                return {"status": "success", "msg": "Duplicate event ignored"}

        status_weight = {"EXPORT": 1, "EXPORTED": 1, "RIP": 2, "PRINTING": 3, "DONE": 4, "DELETE": 0, "DELETED": 0}
        new_weight = status_weight.get(new_status, 0)
        
        m_action = "Cắt" if MACHINES.get(real_machine, "PRINT") == "CUT" else "In"

        # ==========================================
        # KỊCH BẢN 1: IN XONG (DONE) - ĐÃ BỔ SUNG GHI NHẬT KÝ & TÍNH GIỜ
        # ==========================================
        if new_status == "DONE":
            c.execute("SELECT run_count, history FROM files WHERE file_hash=?", (done_hash,))
            row_done = c.fetchone()
            
            if row_done:
                c.execute("SELECT file_hash FROM files WHERE file_hash=?", (active_hash,))
                if not c.fetchone():
                    for key in keys_to_check:
                        c.execute(
                            """
                            INSERT OR IGNORE INTO processed_event_keys
                                (idempotency_key, event_id, machine, event_type, file_path, created_time)
                            VALUES (?, ?, ?, ?, ?, ?)
                            """,
                            (key, data.event_id, real_machine, data.event_type, data.path, event_time),
                        )
                    conn.commit()
                    conn.close()
                    log_sys(f"[DONE-REPLAY] Bo qua DONE trung khong co active run: {display_name} luc {event_time}")
                    return {"status": "success", "msg": "Duplicate DONE ignored"}
                current_rc = int(row_done[0] if row_done[0] else 1)
                new_rc = current_rc + 1
                new_display = f"{display_name} (x{new_rc})"
                
                hist_str = row_done[1] if row_done[1] else "[]"
                duration_str = get_duration(hist_str, event_time)
                event_text = f"{m_action} xong lần {new_rc} {duration_str}".strip()
                
                try:
                    h_list = json.loads(hist_str)
                    h_list.append({"status": "DONE", "time": event_time, "event": event_text})
                    hist_str = json.dumps(h_list)
                except: pass
                
                c.execute("UPDATE files SET run_count=?, file_name=?, updated_time=?, history=? WHERE file_hash=?", 
                          (new_rc, new_display, event_time, hist_str, done_hash))
                c.execute("DELETE FROM files WHERE file_hash=?", (active_hash,))
            else:
                c.execute("SELECT run_count, history FROM files WHERE file_hash=?", (active_hash,))
                row_active = c.fetchone()
                if row_active:
                    rc = int(row_active[0] if row_active[0] else 1)
                    hist_str = row_active[1] if row_active[1] else "[]"
                    duration_str = get_duration(hist_str, event_time)
                    
                    event_text = f"{m_action} xong {duration_str}".strip() if rc == 1 else f"{m_action} xong lần {rc} {duration_str}".strip()
                    
                    try:
                        h_list = json.loads(hist_str)
                        h_list.append({"status": "DONE", "time": event_time, "event": event_text})
                        hist_str = json.dumps(h_list)
                    except: pass
                    
                    c.execute("UPDATE files SET file_hash=?, status='DONE', updated_time=?, history=? WHERE file_hash=?", 
                              (done_hash, event_time, hist_str, active_hash))
                else:
                    event_text = f"{m_action} xong"
                    h_list = [{"status": "DONE", "time": event_time, "event": event_text}]
                    try: 
                        c.execute("INSERT INTO files (file_hash, file_name, file_path, machine, job_type, status, created_time, updated_time, zalo_sent, run_count, history, machine_meta_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 1, ?, ?)", 
                                  (done_hash, display_name, data.path, real_machine, data.event_type, "DONE", event_time, event_time, json.dumps(h_list), machine_meta_json))
                    except: pass

        # ==========================================
        # KỊCH BẢN 2: XÓA (DELETE)
        # ==========================================
        elif new_status == "DELETE":
            c.execute("SELECT status, history, machine_meta_json FROM files WHERE file_hash=?", (active_hash,))
            row_active = c.fetchone()
            
            if row_active:
                curr_status = row_active[0]
                hist_str = row_active[1] if row_active[1] else "[]"
                merged_meta = merge_machine_meta(row_active[2] if row_active[2] else "{}", incoming_meta)
                progress_percent = meta_progress_percent(merged_meta)
                valid_exts = (".prn", ".prt", ".tap", ".nc", ".txt", ".tif", ".tiff", ".jpg", ".jpeg")
                if not display_name.lower().endswith(valid_exts):
                    conn.close()
                    return {"status": "success", "msg": "Chặn lệnh Hủy ảo từ file ảnh"}
                    
                source_image_exts = (".tif", ".tiff", ".jpg", ".jpeg")
                if real_machine == "InDecal" and display_name.lower().endswith(source_image_exts) and curr_status in ("RIP", "PRINTING"):
                    conn.close()
                    return {"status": "success", "msg": "Ignore source image delete after RIP/PRINTING"}

                if curr_status in ("PRINTING", "CUTTING"):
                    cancel_type = "production_cancel"
                    reason = "Hủy khi đang chạy"
                elif curr_status in ("EXPORTED", "RIP"):
                    cancel_type = "source_delete"
                    reason = "Xóa file xuất"
                else:
                    cancel_type = "unknown_delete"
                    reason = "Đã xóa"

                try:
                    h_list = json.loads(hist_str)
                    h_list.append({
                        "status": "DELETED",
                        "time": event_time,
                        "event": "DELETE",
                        "old_status": curr_status,
                        "cancel_type": cancel_type,
                        "reason": reason,
                        "progress_percent": progress_percent,
                    })
                    hist_str = json.dumps(h_list)
                except:
                    pass

                c.execute("UPDATE files SET file_hash=?, status='DELETED', updated_time=?, zalo_sent=0, history=?, machine_meta_json=? WHERE file_hash=?", 
                          (deleted_hash, event_time, hist_str, json.dumps(merged_meta, ensure_ascii=False), active_hash))
                copy_thumbnail_if_missing(active_hash, deleted_hash)

        # ==========================================
        # KỊCH BẢN 3: XUẤT / RIP / ĐANG IN
        # ==========================================
        else:
            c.execute("SELECT status, history, updated_time, file_path, machine_meta_json FROM files WHERE file_hash=?", (active_hash,))
            row_active = c.fetchone()
            
            if row_active:
                curr_status = row_active[0]
                hist_str = row_active[1] if row_active[1] else "[]"
                last_updated_str = row_active[2]
                stored_file_path = row_active[3] if row_active[3] else ""
                stored_meta_json = row_active[4] if row_active[4] else "{}"
                
                curr_weight = status_weight.get(curr_status, 0)
                if new_weight > 0 and new_weight < curr_weight:
                    conn.close(); return {"status": "success", "msg": "Chặn lệnh kéo lùi trạng thái"}
                
                # Duplicate status events can happen when scanners restart or replay logs.
                # Keep the current status instead of auto-moving production jobs to DELETED.
                if new_status == curr_status:
                    try:
                        last_updated = datetime.strptime(last_updated_str, "%Y-%m-%d %H:%M:%S")
                        elapsed_mins = (datetime.strptime(event_time, "%Y-%m-%d %H:%M:%S") - last_updated).total_seconds() / 60
                        
                        if elapsed_mins > 15:
                            log_sys(f"[STUCK-WARN] File '{display_name}' van o {curr_status} sau {int(elapsed_mins)} phut. Khong tu chuyen sang DELETED.")
                        if data.machine_meta and curr_status in ("PRINTING", "CUTTING"):
                            try:
                                stored_meta = json.loads(stored_meta_json or "{}")
                            except Exception:
                                stored_meta = {}
                            stored_meta.update(incoming_meta or {})
                            c.execute(
                                "UPDATE files SET updated_time=?, machine_meta_json=? WHERE file_hash=?",
                                (event_time, json.dumps(stored_meta, ensure_ascii=False), active_hash),
                            )
                            conn.commit()
                        conn.close(); return {"status": "success", "msg": "Blocked duplicate status"}
                    except: pass 
                
                # 🌟 THAY ĐỔI TÊN HIỂN THỊ
                event_text = format_event_name(data.event_type)
                
                try:
                    h_list = json.loads(hist_str)
                    h_list.append({"status": new_status, "time": event_time, "event": event_text})
                    hist_str = json.dumps(h_list)
                except: pass
                
                resolved_file_path = prefer_full_file_path(stored_file_path, data.path)
                resolved_meta_json = machine_meta_json if data.machine_meta else stored_meta_json
                c.execute("UPDATE files SET file_name=?, file_path=?, status=?, updated_time=?, history=?, machine_meta_json=? WHERE file_hash=?", 
                          (display_name, resolved_file_path, new_status, event_time, hist_str, resolved_meta_json, active_hash))
            else:
                event_text = format_event_name(data.event_type)
                if new_status in ("PRINTING", "CUTTING"):
                    c.execute(
                        """
                        SELECT file_hash, history, updated_time, file_path, machine_meta_json
                        FROM files
                        WHERE status='DELETED' AND file_name=?
                        ORDER BY updated_time DESC
                        LIMIT 1
                        """,
                        (display_name,),
                    )
                    row_deleted_for_resume = c.fetchone()
                    if row_deleted_for_resume:
                        elapsed_after_delete = seconds_between(row_deleted_for_resume[2], event_time)
                        try:
                            deleted_history = json.loads(row_deleted_for_resume[1] or "[]")
                        except Exception:
                            deleted_history = []
                        last_history = deleted_history[-1] if deleted_history else {}
                        can_resume_deleted = (
                            elapsed_after_delete is not None
                            and 0 <= elapsed_after_delete <= 120
                            and last_history.get("status") == "DELETED"
                            and last_history.get("old_status") in ("PRINTING", "CUTTING")
                        )
                        if can_resume_deleted:
                            resumed_meta = merge_machine_meta(row_deleted_for_resume[4] if row_deleted_for_resume[4] else "{}", incoming_meta)
                            deleted_history.append({"status": new_status, "time": event_time, "event": event_text, "resume_after_delete": True})
                            resolved_file_path = prefer_full_file_path(row_deleted_for_resume[3] if row_deleted_for_resume[3] else "", data.path)
                            c.execute(
                                "UPDATE files SET file_hash=?, file_name=?, file_path=?, status=?, updated_time=?, history=?, machine_meta_json=? WHERE file_hash=?",
                                (
                                    active_hash,
                                    display_name,
                                    resolved_file_path,
                                    new_status,
                                    event_time,
                                    json.dumps(deleted_history, ensure_ascii=False),
                                    json.dumps(resumed_meta, ensure_ascii=False),
                                    row_deleted_for_resume[0],
                                ),
                            )
                            copy_thumbnail_if_missing(row_deleted_for_resume[0], active_hash)
                            log_sys(f"[DELETE-RESUME] {display_name} tiep tuc {new_status} sau DELETE gan nhat, khong tach row moi")
                            for key in keys_to_check:
                                c.execute(
                                    """
                                    INSERT OR IGNORE INTO processed_event_keys
                                        (idempotency_key, event_id, machine, event_type, file_path, created_time)
                                    VALUES (?, ?, ?, ?, ?, ?)
                                    """,
                                    (key, data.event_id, real_machine, data.event_type, data.path, event_time),
                                )
                            conn.commit()
                            try: await manager.broadcast("NEW_DATA")
                            except: pass
                            conn.close()
                            return {"status": "success", "msg": "Resumed row after false delete"}

                    c.execute("SELECT run_count, updated_time FROM files WHERE file_hash=?", (done_hash,))
                    row_done_for_reprint = c.fetchone()
                    if row_done_for_reprint:
                        done_runs = int(row_done_for_reprint[0] if row_done_for_reprint[0] else 1)
                        event_text = "In lại sau khi đã xong - chờ tín hiệu xong" if new_status == "PRINTING" else "Cắt lại sau khi đã xong - chờ tín hiệu xong"
                        log_sys(f"[REPRINT-WAIT] {display_name} da DONE {done_runs} lan, nhan {new_status} moi luc {event_time}")
                h_list = [{"status": new_status, "time": event_time, "event": event_text}]
                try: 
                    c.execute("INSERT INTO files (file_hash, file_name, file_path, machine, job_type, status, created_time, updated_time, zalo_sent, run_count, history, machine_meta_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 1, ?, ?)", 
                              (active_hash, display_name, data.path, real_machine, data.event_type, new_status, event_time, event_time, json.dumps(h_list), machine_meta_json))
                except: pass

        keys_to_insert = []
        for key in keys_to_check:
            if key not in keys_to_insert:
                keys_to_insert.append(key)
        for key in keys_to_insert:
            c.execute(
                """
                INSERT OR IGNORE INTO processed_event_keys
                    (idempotency_key, event_id, machine, event_type, file_path, created_time)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (key, data.event_id, real_machine, data.event_type, data.path, event_time),
            )

        conn.commit()
        conn.close()
        
        await manager.broadcast("NEW_DATA")
        
        if new_status == "DONE" and ENABLE_AUTO_CRM:
            def wake_crm():
                try: requests.get(AUTO_CRM_WAKE_URL, timeout=0.5)
                except: pass
            threading.Thread(target=wake_crm, daemon=True).start()
        elif new_status == "DONE":
            log_sys("V2 mode: Auto_CRM wake disabled.")
        
        log_sys(f"[{real_machine.upper()}] {new_status}: {display_name}")
        return {"status": "success"}
        
    except Exception as e: 
        log_sys(f"[ERROR] server.py -> log_event: {str(e)}")
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    log_sys(f"🚀 KHỞI ĐỘNG {SERVER_VERSION}")
    log_sys(f"Runtime mode: {RUNTIME_MODE}")
    uvicorn.run(app, host=SERVER_HOST, port=SERVER_PORT, log_level="warning")
