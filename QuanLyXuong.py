# =========================================
# CLIENT V6.4.4 - (BỌC THÉP: CHỐNG ĐỌC ĐỨT DÒNG LOG MÁY DECAL)
# =========================================
import os, time, json, shutil, threading, subprocess, socket, requests, base64
from datetime import datetime
from io import BytesIO

try:
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None 
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

CLIENT_VERSION = "V6.4.4_DECAL_MASTER"

API_SERVER_URL = "http://192.168.1.104:8000/api/log_event" 
NAS_EXE_PATH = r"\\192.168.1.188\AI\Tools\dist\QuanLyXuong.exe"

PC_INBAT = "inbat"; PC_INDECAL = "indecal"; PC_CNC = "cnc"          

ROOT = ""; MACHINE_NAME = ""; MACHINE_DISPLAY = ""; BASE_STORAGE = ""; STATE_FILE = ""; LOG_FILE = ""
SCAN_INTERVAL = 30

state_lock = threading.Lock() 
recent_moved = dict(); processed_set = set(); processed_prt = dict(); processed_prn = set()  
prn_tracking = {}; stable_prts = dict(); current_print_job = None; current_print_id = None 

def now(): return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

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
    if MACHINE_NAME == "cnc": return f.lower().endswith((".tap", ".nc", ".txt"))
    else: return f.lower().endswith((".tif", ".jpg"))

def is_export_file(filename):
    f_lower = filename.lower()
    ext = os.path.splitext(f_lower)[1]
    if not ext or ext.startswith("._") or f_lower.endswith(".bmp") or ".prn." in f_lower or ".prt." in f_lower: return False
    if ext in (".prn", ".prt", ".ini", ".db", ".json", ".csv", ".txt", ".tmp", ".exe", ".sys", ".log"): return False
    return True

def is_meta_file(filename):
    ext = os.path.splitext(filename)[1].lower()
    return ext.startswith("._") and len(ext) == 4

def get_expected_meta(ext_str):
    clean = ext_str.replace(".", "").lower()
    return f"._{clean[0]}{clean[-1]}" if clean else ""

def process_event(path, event_type, forced_base_id=None, forced_display_name=None):
    thumb_b64 = None
    if HAS_PIL and MACHINE_NAME != "cnc" and event_type in ["EXPORT", "RIP", "WRONG_DAY"]:
        file_to_thumb = path
        if path.lower().endswith((".prn", ".prt")):
            base = os.path.splitext(path)[0]
            if base.lower().endswith("~ghost"): base = base[:-6]
            if "~" in base: base = base.split("~")[0]
            tif_p = base + ".tif"; jpg_p = base + ".jpg"
            if os.path.exists(tif_p): file_to_thumb = tif_p
            elif os.path.exists(jpg_p): file_to_thumb = jpg_p

        if os.path.exists(file_to_thumb) and file_to_thumb.lower().endswith((".tif", ".jpg")):
            try:
                with Image.open(file_to_thumb) as img:
                    if img.mode == 'CMYK': img = img.convert('RGB')
                    img.thumbnail((250, 250)) 
                    buffered = BytesIO()
                    img.save(buffered, format="JPEG", quality=60)
                    thumb_b64 = base64.b64encode(buffered.getvalue()).decode('utf-8')
            except: pass

    payload = {
        "machine": MACHINE_NAME, "path": path, "event_type": event_type,
        "forced_base_id": forced_base_id, "forced_display_name": forced_display_name,
        "thumbnail_b64": thumb_b64
    }
    
    while True:
        try:
            res = requests.post(API_SERVER_URL, json=payload, timeout=5)
            if res.status_code == 200:
                log_system(f"📡 API Bắn Thành Công [{event_type}]: {os.path.basename(path)}")
                break 
        except requests.exceptions.RequestException:
            log_system(f"⚠️ Mạng LAN nghẽn. Đang ôm file chờ thử lại...")
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
    last_raw = b""; cur_job = None; cur_switch = None 
    
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
def worker_indecal_log():
    global current_print_job, current_print_id
    last_sz = 0; cur_f = None

    while True:
        try:
            today_log = f"C:\\Program Files (x86)\\PrintExp_V5.7.6.5.23\\Log\\Log[{datetime.now().strftime('%Y_%m_%d')}].txt"
            
            if today_log != cur_f:
                cur_f = today_log
                if os.path.exists(today_log): last_sz = os.path.getsize(today_log)
                else: last_sz = 0
                
            if os.path.exists(today_log):
                sz = os.path.getsize(today_log)
                if sz < last_sz: last_sz = 0 
                if sz > last_sz:
                    with open(today_log, "rb") as f: 
                        f.seek(last_sz)
                        raw_data = f.read()
                        
                    # 🌟 BỌC THÉP V6.4.4: CHỐNG ĐỌC ĐỨT ĐOẠN DÒNG LOG KHI MÁY ĐANG GHI
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
                        try:
                            current_size = os.path.getsize(path)
                            if current_size == 0: continue 
                        except: continue 

                        if path not in prn_tracking:
                            prn_tracking[path] = {'size': current_size, 'last_changed': time.time()}; continue
                        if current_size != prn_tracking[path]['size']:
                            prn_tracking[path]['size'] = current_size; prn_tracking[path]['last_changed'] = time.time(); continue
                        if time.time() - prn_tracking[path]['last_changed'] < 5: continue 
                            
                        meta_files = [mf for mf in os.listdir(day_folder) if is_meta_file(mf)]
                        if len(meta_files) == 0: 
                            del prn_tracking[path]
                            processed_prn.add(path.lower())
                            with state_lock: processed_set.add(path.lower())
                            process_event(path, "RIP")
                            continue
                            
                        meta_files.sort(key=lambda x: os.path.getctime(os.path.join(day_folder, x)), reverse=True)
                        matched_meta_name = meta_files[0]
                        meta_path = os.path.join(day_folder, matched_meta_name)
                        
                        try:
                            if os.path.getmtime(path) < os.path.getctime(meta_path) - 3:
                                prn_base, prn_ext = os.path.splitext(f)
                                os.replace(path, os.path.join(new_folder, f"{prn_base}~ghost{prn_ext}")) 
                                del prn_tracking[path]; continue
                        except: continue

                        prn_base, prn_ext = os.path.splitext(f)
                        meta_base, meta_ext = os.path.splitext(matched_meta_name)
                        new_prn_name = f"{prn_base}~{meta_base}{prn_ext}"
                        new_prn_path = os.path.join(new_folder, new_prn_name)
                        with state_lock:
                            recent_moved[path.lower()] = time.time() 
                            processed_set.add(new_prn_path.lower())

                        try: os.replace(path, new_prn_path) 
                        except: prn_tracking[path]['last_changed'] = time.time() - 3; continue
                        
                        del prn_tracking[path]
                        orig_path = None
                        for f_orig in os.listdir(day_folder):
                            f_base, f_ext = os.path.splitext(f_orig)
                            if f_base.lower() == meta_base.lower():
                                if get_expected_meta(f_ext) == meta_ext.lower():
                                    orig_path = os.path.join(day_folder, f_orig); break
                                
                        if orig_path and os.path.exists(orig_path):
                            target_tif = os.path.join(new_folder, os.path.basename(orig_path))
                            with state_lock:
                                recent_moved[orig_path.lower()] = time.time()
                                recent_moved[target_tif.lower()] = time.time()
                            try: os.replace(orig_path, target_tif)
                            except: pass
                        
                        for trash_mf in meta_files:
                            try: os.remove(os.path.join(day_folder, trash_mf))
                            except: pass

                        processed_prn.add(new_prn_path.lower())
                        with state_lock: processed_set.add(new_prn_path.lower())
                        process_event(new_prn_path, "RIP")
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

def universal_folder_scanner():
    global processed_set
    cur_date = datetime.now().strftime("%Y-%m-%d")
    last_curr = scan_day(cur_date)
    
    while True:
        try:
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

            last_curr = curr; save_state(processed_set)
            
            dead = [p for p in processed_set if not os.path.exists(p)]; [processed_set.discard(p) for p in dead]
            if MACHINE_NAME == "indecal":
                d_prn = [p for p in processed_prn if not os.path.exists(p)]; [processed_prn.discard(p) for p in d_prn]
            
            time.sleep(SCAN_INTERVAL)
        except Exception as e: 
            log_system(f"❌ LỖI QUÉT THƯ MỤC: {str(e)}", is_error=True)
            time.sleep(5)

def report_version_to_server():
    ping_url = API_SERVER_URL.replace("/log_event", "/ping")
    payload = {"machine": MACHINE_NAME, "version": CLIENT_VERSION}
    for _ in range(5):
        try:
            requests.post(ping_url, json=payload, timeout=5)
            log_system(f"✅ Đã báo cáo phiên bản {CLIENT_VERSION} lên Server!")
            break
        except: time.sleep(3)

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

    if current_pc == PC_INBAT:
        MACHINE_NAME = "inbat"; MACHINE_DISPLAY = "InBat"; ROOT = r"D:\\"; BASE_STORAGE = r"C:\QuanLyXuong"
    elif current_pc == PC_INDECAL:
        MACHINE_NAME = "indecal"; MACHINE_DISPLAY = "InDecal"; ROOT = r"D:\\"; BASE_STORAGE = r"C:\QuanLyXuong"
    elif current_pc == PC_CNC:
        MACHINE_NAME = "cnc"; MACHINE_DISPLAY = "CNC"; ROOT = r"D:\CNC"; BASE_STORAGE = r"C:\QuanLyXuong"
    else:
        print(f"🛑 MAY NAY KHONG CO TRONG DANH SACH!"); time.sleep(100); os._exit(0)

    STATE_FILE = os.path.join(BASE_STORAGE, f"state_{MACHINE_NAME}.json")
    LOG_FILE = os.path.join(BASE_STORAGE, "system_log.txt")
    
    processed_set = load_state()
    threading.Thread(target=report_version_to_server, daemon=True).start()
    threading.Thread(target=auto_update_watcher, daemon=True).start()
    threading.Thread(target=fast_folder_renamer_worker, daemon=True).start()

    if MACHINE_NAME == "inbat": start_inbat_mode()
    elif MACHINE_NAME == "indecal": start_indecal_mode()
    elif MACHINE_NAME == "cnc": start_cnc_mode()

    universal_folder_scanner()