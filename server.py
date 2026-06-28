# =========================================
# SERVER V7.6.0 - GỌT GIŨA NHẬT KÝ & BẤM GIỜ THÔNG MINH
# Tích hợp: Anti-Spam + Cắt gọt text (Rip file, In lần n) + Đo thời gian chạy
# =========================================
import os, time, sqlite3, subprocess, hashlib, threading, json, requests, base64
from datetime import datetime
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import uvicorn
from pydantic import BaseModel
from typing import Optional, List
from contextlib import asynccontextmanager

# ================= CONFIG =================
SERVER_VERSION = "V7.6.0_SMART_LOG"
DB_DIR = r"C:\QuanLyXuong\Data"
MACHINES = dict(InBat="PRINT", InDecal="PRINT", CNC="CUT")
OPENCLAW_PATH = r"C:\Users\Admin\AppData\Roaming\npm\openclaw.cmd"
ZALO_TARGET = os.getenv("SERVER_ZALO_TARGET", "")
LOG_FILE = r"C:\QuanLyXuong\Server_Log.txt"
NAS_EXE_PATH = r"\\192.168.1.188\AI\Tools\dist\server.exe"
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

def now(): return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def log_sys(msg):
    print(f"[{now()}] {msg}")
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f: 
            f.write(f"[{now()}] {msg}\n")
    except: pass

def send_zalo(msg):
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

class PingPayload(BaseModel):
    machine: str; version: str

@app.post("/api/ping")
def ping_client(data: PingPayload):
    machine_mapped = {"inbat": "InBat", "indecal": "InDecal", "cnc": "CNC"}.get(data.machine.lower(), "Unknown")
    if machine_mapped == "Unknown": return {"status": "error"}
    try:
        db_path = os.path.join(DB_DIR, f"{machine_mapped}.db")
        conn = sqlite3.connect(db_path, timeout=10)
        conn.execute("INSERT OR REPLACE INTO app_info (key, value) VALUES ('version', ?)", (data.version,))
        conn.commit(); conn.close()
        log_sys(f"🔔 MÁY {machine_mapped} ĐIỂM DANH: Bản {data.version}")
        return {"status": "ok"}
    except: return {"status": "error"}

@app.post("/api/log_event")
async def log_event(data: RequestData): 
    try:
        real_machine = {"inbat": "InBat", "indecal": "InDecal", "cnc": "CNC"}.get(data.machine.lower(), "Unknown")
        machine_mapped = MACHINES.get(real_machine, "UNKNOWN")
        display_name = os.path.basename(data.path)
        
        new_status = "EXPORTED" if data.event_type == "EXPORT" else data.event_type

        # GỌT TÊN CHUẨN MỰC
        core_name = os.path.splitext(display_name)[0]
        if data.machine.lower() == "indecal":
            if "~" in core_name and core_name.split("~")[0].isdigit():
                core_name = core_name.split("~", 1)[-1]
            if "~" in core_name:
                core_name = core_name.split("~")[0]
        
        core_name_clean = core_name.lower().strip()
        today_str = datetime.now().strftime("%Y-%m-%d")
        base_string = f"{real_machine.lower()}_core_{core_name_clean}_{today_str}"
        
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

        db_path = os.path.join(DB_DIR, f"{real_machine}.db") 
        conn = sqlite3.connect(db_path, timeout=15)
        conn.execute("PRAGMA journal_mode=WAL;")
        c = conn.cursor()

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
                current_rc = int(row_done[0] if row_done[0] else 1)
                new_rc = current_rc + 1
                new_display = f"{display_name} (x{new_rc})"
                
                hist_str = row_done[1] if row_done[1] else "[]"
                duration_str = get_duration(hist_str, now())
                event_text = f"{m_action} xong lần {new_rc} {duration_str}".strip()
                
                try:
                    h_list = json.loads(hist_str)
                    h_list.append({"status": "DONE", "time": now(), "event": event_text})
                    hist_str = json.dumps(h_list)
                except: pass
                
                c.execute("UPDATE files SET run_count=?, file_name=?, updated_time=?, history=? WHERE file_hash=?", 
                          (new_rc, new_display, now(), hist_str, done_hash))
                c.execute("DELETE FROM files WHERE file_hash=?", (active_hash,))
            else:
                c.execute("SELECT run_count, history FROM files WHERE file_hash=?", (active_hash,))
                row_active = c.fetchone()
                if row_active:
                    rc = int(row_active[0] if row_active[0] else 1)
                    hist_str = row_active[1] if row_active[1] else "[]"
                    duration_str = get_duration(hist_str, now())
                    
                    event_text = f"{m_action} xong {duration_str}".strip() if rc == 1 else f"{m_action} xong lần {rc} {duration_str}".strip()
                    
                    try:
                        h_list = json.loads(hist_str)
                        h_list.append({"status": "DONE", "time": now(), "event": event_text})
                        hist_str = json.dumps(h_list)
                    except: pass
                    
                    c.execute("UPDATE files SET file_hash=?, status='DONE', updated_time=?, history=? WHERE file_hash=?", 
                              (done_hash, now(), hist_str, active_hash))
                else:
                    event_text = f"{m_action} xong"
                    h_list = [{"status": "DONE", "time": now(), "event": event_text}]
                    try: 
                        c.execute("INSERT INTO files (file_hash, file_name, file_path, machine, job_type, status, created_time, updated_time, zalo_sent, run_count, history) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 1, ?)", 
                                  (done_hash, display_name, data.path, real_machine, data.event_type, "DONE", now(), now(), json.dumps(h_list)))
                    except: pass

        # ==========================================
        # KỊCH BẢN 2: XÓA (DELETE)
        # ==========================================
        elif new_status == "DELETE":
            c.execute("SELECT status, history FROM files WHERE file_hash=?", (active_hash,))
            row_active = c.fetchone()
            
            if row_active:
                valid_exts = (".prn", ".prt", ".tap", ".nc", ".txt", ".tif", ".jpg")
                if not display_name.lower().endswith(valid_exts):
                    conn.close()
                    return {"status": "success", "msg": "Chặn lệnh Hủy ảo từ file ảnh"}
                    
                c.execute("UPDATE files SET file_hash=?, status='DELETED', updated_time=?, zalo_sent=0 WHERE file_hash=?", 
                          (deleted_hash, now(), active_hash))

        # ==========================================
        # KỊCH BẢN 3: XUẤT / RIP / ĐANG IN
        # ==========================================
        else:
            c.execute("SELECT status, history, updated_time FROM files WHERE file_hash=?", (active_hash,))
            row_active = c.fetchone()
            
            if row_active:
                curr_status = row_active[0]
                hist_str = row_active[1] if row_active[1] else "[]"
                last_updated_str = row_active[2]
                
                curr_weight = status_weight.get(curr_status, 0)
                if new_weight > 0 and new_weight < curr_weight:
                    conn.close(); return {"status": "success", "msg": "Chặn lệnh kéo lùi trạng thái"}
                
                # BỘ LỌC CHỐNG SPAM & TỰ ĐỘNG HỦY FILE KẸT
                if new_status == curr_status:
                    try:
                        last_updated = datetime.strptime(last_updated_str, "%Y-%m-%d %H:%M:%S")
                        elapsed_mins = (datetime.now() - last_updated).total_seconds() / 60
                        
                        if elapsed_mins > 15:
                            c.execute("UPDATE files SET file_hash=?, status='DELETED', updated_time=? WHERE file_hash=?", 
                                      (deleted_hash, now(), active_hash))
                            conn.commit(); conn.close()
                            await manager.broadcast("NEW_DATA")
                            log_sys(f"🚨 [AUTO-KILL] File '{display_name}' dậm chân tại {curr_status} quá {int(elapsed_mins)} phút. Đã tự động đưa vào mục Hủy/Lỗi!")
                            return {"status": "success", "msg": "Auto-killed stuck job"}
                        else:
                            conn.close(); return {"status": "success", "msg": "Blocked spam"}
                    except: pass 
                
                # 🌟 THAY ĐỔI TÊN HIỂN THỊ
                event_text = format_event_name(data.event_type)
                
                try:
                    h_list = json.loads(hist_str)
                    h_list.append({"status": new_status, "time": now(), "event": event_text})
                    hist_str = json.dumps(h_list)
                except: pass
                
                c.execute("UPDATE files SET file_name=?, file_path=?, status=?, updated_time=?, history=? WHERE file_hash=?", 
                          (display_name, data.path, new_status, now(), hist_str, active_hash))
            else:
                event_text = format_event_name(data.event_type)
                h_list = [{"status": new_status, "time": now(), "event": event_text}]
                try: 
                    c.execute("INSERT INTO files (file_hash, file_name, file_path, machine, job_type, status, created_time, updated_time, zalo_sent, run_count, history) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 1, ?)", 
                              (active_hash, display_name, data.path, real_machine, data.event_type, new_status, now(), now(), json.dumps(h_list)))
                except: pass

        conn.commit()
        conn.close()
        
        await manager.broadcast("NEW_DATA")
        
        if new_status == "DONE":
            def wake_crm():
                try: requests.get("http://127.0.0.1:8001/wake_up", timeout=0.5)
                except: pass
            threading.Thread(target=wake_crm, daemon=True).start()
        
        log_sys(f"[{real_machine.upper()}] {new_status}: {display_name}")
        return {"status": "success"}
        
    except Exception as e: 
        log_sys(f"[ERROR] server.py -> log_event: {str(e)}")
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    log_sys(f"🚀 KHỞI ĐỘNG {SERVER_VERSION}")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="warning")
