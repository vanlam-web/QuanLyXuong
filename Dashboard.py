# =========================================
# WEB DASHBOARD V8.7.0 - (VÁ LỖI HIỂN THỊ M2 + CHỐNG CRASH JS)
# =========================================
import sqlite3, os, sys, json, requests, re, unicodedata, time, threading
from flask import Flask, render_template_string, jsonify, request, send_from_directory, Response
from datetime import datetime

app = Flask(__name__)

# --- CONFIG ĐƯỜNG DẪN CỐ ĐỊNH CHUẨN EXE ---
DB_DIR = r"C:\QuanLyXuong\Data"
BASE_DATA_CRM = r"C:\QuanLyXuong\Data_Auto_CRM"
MACHINES = ["InBat", "InDecal", "CNC"]
ADMIN_PIN = os.getenv("DASHBOARD_ADMIN_PIN", "")
NAS_DASHBOARD_EXE_PATH = r"\\192.168.1.188\AI\Tools\dist\Dashboard.exe"

THUMB_DIR = os.path.join(DB_DIR, "Thumbnails")
os.makedirs(THUMB_DIR, exist_ok=True)

# 🌟 THÊM KHAI BÁO FILE LOG CHO DASHBOARD
LOG_FILE = r"C:\QuanLyXuong\Dashboard_Log.txt"

def print_log(msg):
    log_str = f"[{now()}] {msg}"
    print(log_str)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(log_str + "\n")
    except: pass

# 🌟 CẢM BIẾN TỰ ĐỘNG CẬP NHẬT TỪ NAS CHO DASHBOARD
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
                print_log("🚀 PHÁT HIỆN DASHBOARD MỚI TRÊN NAS! KÍCH HOẠT BAT...")
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
    if not filename: return 0.0  # Chặn lỗi file không tên
    m2 = 0.0
    match = re.search(r'(\d{2,4})\s*[xX]\s*(\d{2,4})', str(filename).lower()) # Ép kiểu String
    if match:
        try: m2 = (int(match.group(1)) * int(match.group(2))) / 10000.0
        except: pass
    return m2

for machine in MACHINES:
    db_path = os.path.join(DB_DIR, f"{machine}.db")
    if os.path.exists(db_path):
        try:
            conn = sqlite3.connect(db_path, timeout=5)
            cols = [c[1] for c in conn.execute("PRAGMA table_info(files)").fetchall()]
            if "run_count" not in cols: conn.execute("ALTER TABLE files ADD COLUMN run_count INTEGER DEFAULT 1")
            if "history" not in cols: conn.execute("ALTER TABLE files ADD COLUMN history TEXT DEFAULT '[]'")
            if "zalo_sent" not in cols: conn.execute("ALTER TABLE files ADD COLUMN zalo_sent INTEGER DEFAULT 0")
            conn.commit(); conn.close()
        except: pass

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>BẢNG ĐIỀU KHIỂN & THỐNG KÊ ERP</title>
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
        .col-export { border-color: #ff9900; } .col-rip { border-color: #00ccff; } .col-run { border-color: #ff3366; } .col-done { border-color: #33cc33; } .col-cancel { border-color: #ff3333; opacity: 0.9; } 
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
        .badge-InBat { background-color: #ffd700; } .badge-InDecal { background-color: #00fa9a; } .badge-CNC { background-color: #ff6347; color: white;}
        .badge-run { background-color: #ff3333; color: white; float: right; padding: 2px 5px; border-radius: 5px; font-size: 10px;}

        /* ERP STYLES */
        .erp-btn { background: #1e1e1e; border: 1px solid #444; color: white; padding: 8px 20px; border-radius: 8px; cursor: pointer; font-weight: bold; transition: 0.2s;}
        .erp-btn:hover { background: #333; }
        .erp-btn.active { background: #00ffcc; color: black; border-color: #00ffcc;}
        .btn-excel { background: #28a745 !important; border-color: #28a745 !important; color: white !important;}
        .btn-excel:hover { background: #218838 !important; }
        
        .erp-summary-row { display: flex; gap: 15px; margin-bottom: 15px; flex-shrink: 0;}
        .erp-sum-card { flex: 1; background: #1e1e1e; border-radius: 10px; padding: 15px; text-align: center; border: 1px solid #333;}
        .erp-sum-val { font-size: 24px; font-weight: bold; color: #00ffcc; margin-top: 5px;}
        .val-err { color: #ff3333; }
        .val-m2-erp { color: #ffd700; }

        .erp-grid { display: grid; grid-template-columns: repeat(2, 1fr); grid-template-rows: repeat(2, 1fr); gap: 15px; flex-grow: 1; overflow-y: auto;}
        .chart-box { background: #1e1e1e; border-radius: 12px; padding: 15px; display: flex; flex-direction: column; border: 1px solid #333;}
        .chart-box h3 { text-align: center; margin-top: 0; color: #ff9900; font-size: 14px; text-transform: uppercase; border-bottom: 1px dashed #444; padding-bottom: 8px;}
        .canvas-container { flex-grow: 1; position: relative; min-height: 200px;}
        .chart-box.full-width { grid-column: span 2; }

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
        .tl-item.tl-export::before { background: #ff9900; } .tl-item.tl-rip::before { background: #00ccff; } .tl-item.tl-run::before { background: #ff3366; } .tl-item.tl-done::before { background: #00fa9a; } .tl-item.tl-cancel::before { background: #ff3333; }
        .tl-time { font-size: 10px; color: #aaa; margin-bottom: 1px;} .tl-desc { font-size: 12px; font-weight: bold; color: #fff;}
        .tl-duration { font-size: 10px; color: #ff9900; margin-top: 3px; display: inline-block; background: rgba(255,153,0,0.1); padding: 2px 6px; border-radius: 4px; border: 1px solid #ff9900;}
        .admin-section { display: none; margin-top: 15px; padding-top: 10px; border-top: 2px solid #444; }
        .admin-title { font-size: 11px; color: #ff3333; font-weight: bold; text-transform: uppercase; margin-bottom: 8px; text-align: center;}
        .action-btn { display: block; width: 100%; padding: 8px; margin-bottom: 6px; border: none; border-radius: 5px; font-size: 12px; font-weight: bold; cursor: pointer;}
        .btn-submit { background-color: #00ffcc; color: black; margin-top: 10px;} .btn-done { background-color: #33cc33; color: black;} .btn-cancel { background-color: #ff3333; color: white;} .btn-reset { background-color: #ff9900; color: black;}

        /* LỌC NHANH XỊN XÒ */
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
    </style>
</head>
<body>
    
    <div class="top-navbar">
        <button class="tab-btn active" id="tabbtn-board" onclick="switchTab('board')">📦 BẢNG SẢN XUẤT</button>
        <button class="tab-btn" id="tabbtn-erp" onclick="switchTab('erp')">📊 THỐNG KÊ ERP</button>
        <div class="header-controls">
            <span id="socket-status" class="status-off">Đang dò sóng...</span>
            <button id="authBtn" class="login-btn" onclick="toggleAuth()">Đăng nhập</button>
        </div>
    </div>

    <div id="view-board" class="view-section active">
        <div class="controls">
            <input type="date" id="datePicker">
            <select id="machineFilter">
                <option value="ALL">Tất cả máy</option>
                <option value="InBat">In Bạt</option>
                <option value="InDecal">In Decal</option>
                <option value="CNC">CNC</option>
            </select>
        </div>
        <div class="summary-panel">
            <div class="summary-title">TỔNG M² TRONG NGÀY (ĐÃ NHÂN SỐ LẦN CHẠY)</div>
            <div id="m2-summary">Đang tính toán...</div>
        </div>
        <div class="board">
            <div class="column col-export"><h2>XUẤT FILE <span class="count-badge" id="count-export">0</span></h2><div id="exported-list" class="list-container"></div></div>
            <div class="column col-rip"><h2>ĐÃ RIP <span class="count-badge" id="count-rip">0</span></h2><div id="rip-list" class="list-container"></div></div>
            <div class="column col-run"><h2>ĐANG CHẠY <span class="count-badge" id="count-run">0</span></h2><div id="run-list" class="list-container"></div></div>
            <div class="column col-done"><h2>ĐÃ XONG <span class="count-badge" id="count-done">0</span></h2><div id="done-list" class="list-container"></div></div>
            <div class="column col-cancel"><h2>HỦY/LỖI <span class="count-badge" id="count-cancel">0</span></h2><div id="cancel-list" class="list-container"></div></div>
        </div>
    </div>

    <div id="view-erp" class="view-section">
        <div class="controls">
            <select id="erpQuickDate" class="quick-select" onchange="applyQuickDate()">
                <option value="this_month">📅 Tháng này</option>
                <option value="today">🕒 Hôm nay</option>
                <option value="yesterday">⌛ Hôm qua</option>
                <option value="this_week">📆 Tuần này</option>
                <option value="last_week">🗓️ Tuần trước</option>
                <option value="last_month">📉 Tháng trước</option>
                <option value="this_quarter">🥧 Quý này</option>
                <option value="last_quarter">🍕 Quý trước</option>
                <option value="this_year">🏆 Năm nay</option>
                <option value="last_year">🏅 Năm trước</option>
            </select>

            <span style="font-size:12px; color:#aaa; margin-left:5px;">Từ:</span>
            <input type="date" id="erpStart" onchange="fetchERP()">
            <span style="font-size:12px; color:#aaa;">Đến:</span>
            <input type="date" id="erpEnd" onchange="fetchERP()">
            
            <select id="erpMachine" onchange="fetchERP()">
                <option value="ALL">Tất cả máy</option>
                <option value="InBat">In Bạt</option>
                <option value="InDecal">In Decal</option>
                <option value="CNC">CNC</option>
            </select>
            
            <button class="erp-btn btn-excel" onclick="exportExcel()">📥 XUẤT EXCEL</button>
        </div>
        
        <div class="erp-summary-row">
            <div class="erp-sum-card">
                <div style="font-size: 12px; color: #aaa;">TỔNG ĐƠN HOÀN THÀNH</div>
                <div class="erp-sum-val" id="erp-total-jobs">0</div>
            </div>
            <div class="erp-sum-card">
                <div style="font-size: 12px; color: #aaa;">TỔNG DIỆN TÍCH IN CẮT</div>
                <div class="erp-sum-val val-m2-erp" id="erp-total-m2">0.00 m²</div>
            </div>
            <div class="erp-sum-card">
                <div style="font-size: 12px; color: #aaa;">TỈ LỆ FILE HỎNG / HỦY</div>
                <div class="erp-sum-val val-err" id="erp-err-rate">0%</div>
            </div>
        </div>

        <div class="erp-grid">
            <div class="chart-box">
                <h3>Hiệu Suất Diện Tích (m²)</h3>
                <div class="canvas-container"><canvas id="m2Chart"></canvas></div>
            </div>
            <div class="chart-box">
                <h3>TOP Khách Hàng VIP (Số Lượng Đơn)</h3>
                <div class="canvas-container"><canvas id="cusChart"></canvas></div>
            </div>
            <div class="chart-box full-width">
                <h3>Khung Giờ Cao Điểm (Đơn Hoàn Thành)</h3>
                <div class="canvas-container"><canvas id="hourChart"></canvas></div>
            </div>
        </div>
    </div>

    <div id="loginModal" class="modal">
        <div class="modal-content">
            <span class="close-x" onclick="closeModals()">&times;</span>
            <h3 style="color: #00ffcc; margin-top: 0; text-align: center; font-size:16px;">ĐĂNG NHẬP QUẢN TRỊ</h3>
            <p style="text-align: center; color: #aaa; font-size: 12px; margin: 0;">Nhập mã PIN để cấp quyền.</p>
            <input type="password" id="pin-input" class="pin-input" placeholder="****" autocomplete="off" maxlength="10">
            <button class="action-btn btn-submit" onclick="submitLogin()">XÁC NHẬN</button>
        </div>
    </div>

    <div id="detailModal" class="modal">
        <div class="modal-content">
            <span class="close-x" onclick="closeModals()">&times;</span>
            <div class="detail-header">
                <span id="dt-badge" class="badge"></span>
                <div id="dt-name" class="detail-name">Tên File</div>
            </div>
            <div class="detail-row"><span class="detail-label">📌 Trạng thái:</span><span class="detail-value" id="dt-status"></span></div>
            <div class="detail-row"><span class="detail-label">📏 Kích thước:</span><span class="detail-value val-m2" id="dt-m2"></span></div>
            <div style="margin-top: 12px; font-size: 12px; color: #00ffcc; font-weight: bold; border-bottom: 1px solid #333; padding-bottom: 4px;">📜 NHẬT KÝ CHI TIẾT</div>
            <div id="dt-timeline-container"></div>

            <input type="hidden" id="modal-machine-name">
            <input type="hidden" id="modal-real-name">

            <div id="adminArea" class="admin-section">
                <div class="admin-title">🛠️ QUẢN TRỊ VIÊN</div>
                <button class="action-btn btn-done" onclick="forceUpdate('DONE')">✅ CHUYỂN SANG: ĐÃ XONG</button>
                <button class="action-btn btn-cancel" onclick="forceUpdate('DELETED')">🛑 CHUYỂN SANG: HỦY / LỖI</button>
                <button class="action-btn btn-reset" onclick="forceUpdate('EXPORTED')">🔄 CHUYỂN SANG: XUẤT LẠI</button>
            </div>
        </div>
    </div>

    <script>
        Chart.defaults.color = '#aaaaaa';
        Chart.defaults.font.family = "'Segoe UI', Tahoma, sans-serif";
        let m2ChartInst = null; let cusChartInst = null; let hourChartInst = null;
        let currentTab = 'board';

        // 🌟 BỌC THÉP: Hàm lấy ngày hôm nay chuẩn an toàn nhất
        function getLocalToday() {
            let d = new Date();
            let m = '' + (d.getMonth() + 1), day = '' + d.getDate(), y = d.getFullYear();
            if (m.length < 2) m = '0' + m;
            if (day.length < 2) day = '0' + day;
            return [y, m, day].join('-');
        }

        // Khởi tạo ngày mặc định
        document.getElementById('datePicker').value = getLocalToday();

        // 🌟 LỌC NHANH ERP
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

            let sm = '' + (start.getMonth() + 1), sd = '' + start.getDate(), sy = start.getFullYear();
            if (sm.length < 2) sm = '0' + sm; if (sd.length < 2) sd = '0' + sd;
            
            let em = '' + (end.getMonth() + 1), ed = '' + end.getDate(), ey = end.getFullYear();
            if (em.length < 2) em = '0' + em; if (ed.length < 2) ed = '0' + ed;

            document.getElementById('erpStart').value = [sy, sm, sd].join('-');
            document.getElementById('erpEnd').value = [ey, em, ed].join('-');
            fetchERP();
        }

        function switchTab(tabId) {
            currentTab = tabId;
            document.getElementById('tabbtn-board').className = (tabId === 'board') ? "tab-btn active" : "tab-btn";
            document.getElementById('tabbtn-erp').className = (tabId === 'erp') ? "tab-btn active" : "tab-btn";
            document.getElementById('view-board').className = (tabId === 'board') ? "view-section active" : "view-section";
            document.getElementById('view-erp').className = (tabId === 'erp') ? "view-section active" : "view-section";
            if(tabId === 'erp') fetchERP();
        }

        function exportExcel() {
            let s = document.getElementById('erpStart').value; let e = document.getElementById('erpEnd').value; let m = document.getElementById('erpMachine').value;
            window.location.href = `/api/export_csv?start=${s}&end=${e}&machine=${m}`;
        }

        async function fetchERP() {
            let s = document.getElementById('erpStart').value; let e = document.getElementById('erpEnd').value; let m = document.getElementById('erpMachine').value;
            try {
                let res = await fetch(`/api/stats?start=${s}&end=${e}&machine=${m}`);
                let data = await res.json();
                
                document.getElementById('erp-total-jobs').innerText = data.summary.total_jobs;
                document.getElementById('erp-total-m2').innerText = data.summary.total_m2.toFixed(2) + ' m²';
                document.getElementById('erp-err-rate').innerText = data.summary.cancel_rate.toFixed(1) + '%';
                
                renderCharts(data);
            } catch(e) {}
        }

        function renderCharts(data) {
            if(m2ChartInst) m2ChartInst.destroy();
            let ctxM2 = document.getElementById('m2Chart').getContext('2d');
            m2ChartInst = new Chart(ctxM2, {
                type: 'bar', data: { labels: Object.keys(data.m2), datasets: [{ data: Object.values(data.m2), backgroundColor: ['#ffd700', '#00fa9a', '#ff6347'], borderRadius: 5 }] },
                options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true, grid: { color: '#333' } }, x: { grid: { display: false } } } }
            });

            if(cusChartInst) cusChartInst.destroy();
            let ctxCus = document.getElementById('cusChart').getContext('2d');
            cusChartInst = new Chart(ctxCus, {
                type: 'doughnut', data: { labels: data.customers.labels, datasets: [{ data: data.customers.data, backgroundColor: ['#00ccff', '#ff3366', '#00fa9a', '#ff9900', '#9d00ff', '#ffeb3b', '#ff3333', '#1e90ff', '#00ffcc', '#ff1493'], borderWidth: 2, borderColor: '#1e1e1e' }] },
                options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'right', labels: { boxWidth: 12, font: { size: 10 } } } }, cutout: '60%' }
            });

            if(hourChartInst) hourChartInst.destroy();
            let ctxHour = document.getElementById('hourChart').getContext('2d');
            hourChartInst = new Chart(ctxHour, {
                type: 'line', data: { labels: data.hours.labels, datasets: [{ data: data.hours.data, borderColor: '#00ffcc', backgroundColor: 'rgba(0, 255, 204, 0.1)', tension: 0.4, fill: true, pointRadius: 3, pointBackgroundColor: '#ff9900' }] },
                options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true, grid: { color: '#333' } }, x: { grid: { color: '#222' } } } }
            });
        }

        // ================= LOGIC BẢNG SẢN XUẤT =================
        let allData = { EXPORTED: [], RIP: [], RUNNING: [], DONE: [], CANCELED: [] };

        window.onclick = function(event) {
            let loginModal = document.getElementById('loginModal'); let detailModal = document.getElementById('detailModal');
            if (event.target == loginModal || event.target == detailModal) closeModals();
        }

        function connectWebSocket() {
            const ws = new WebSocket("ws://" + window.location.hostname + ":8000/ws/dashboard");
            const statusEl = document.getElementById('socket-status');
            ws.onopen = function() { statusEl.innerText = "⚡ Real-time: Bật"; statusEl.className = "status-on"; fetchData(); };
            ws.onmessage = function(event) { 
                if(event.data === "NEW_DATA") { if(currentTab === 'board') fetchData(); else fetchERP(); }
            };
            ws.onclose = function() { statusEl.innerText = "🔴 Mất sóng"; statusEl.className = "status-off"; setTimeout(connectWebSocket, 3000); };
        }

        function checkAuthUI() {
            let pin = localStorage.getItem("admin_pin"); let btn = document.getElementById("authBtn");
            if (pin) { btn.innerText = "Admin (Đăng xuất)"; btn.classList.add("btn-logout"); } 
            else { btn.innerText = "Đăng nhập"; btn.classList.remove("btn-logout"); }
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

        // 🌟 BỌC THÉP BỘ TÍNH TOÁN BẰNG CHUỖI (Tránh truyền lộn số nguyên gây crash)
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
                let found = allData[k].find(f => f.machine === machine && f.name === realName);
                if(found) { file = found; 
                    if(k==="EXPORTED") statusName="📥 Xuất File"; if(k==="RIP") statusName="⚙️ Xong RIP"; if(k==="RUNNING") statusName="▶️ Đang Chạy"; if(k==="DONE") statusName="✅ Đã Xong"; if(k==="CANCELED") statusName="🛑 Hủy/Lỗi"; break; 
                }
            }
            if(!file) return;

            document.getElementById('dt-badge').innerText = file.machine; document.getElementById('dt-badge').className = "badge badge-" + file.machine;
            document.getElementById('dt-name').innerText = file.name; document.getElementById('dt-status').innerText = statusName;
            
            let actionText = (file.machine === "CNC") ? "Cắt" : "In";
            let m2 = parseArea(file.name); let totalM2 = m2 > 0 ? (m2 * file.run).toFixed(2) + " m²" : "N/A";
            document.getElementById('dt-m2').innerHTML = totalM2 + (file.run > 1 ? ` <span style="color:#ff9900; font-size:11px;">(${actionText} x${file.run})</span>` : "");

            document.getElementById('modal-machine-name').value = file.machine; document.getElementById('modal-real-name').value = file.name;

            let hist = []; try { hist = JSON.parse(file.history || '[]'); } catch(e){}
            let html = '';
            if(hist.length === 0) { html = '<div style="color:#aaa; font-size:11px; margin-top:10px; font-style:italic;">Không có nhật ký chi tiết.</div>'; } 
            else {
                html = '<div class="timeline">'; 
                let lastStartTime = null; let runCounter = 0; let doneCounter = 0;
                
                hist.forEach(h => {
                    let desc = h.event; let durHtml = ""; let color = "#fff"; let tlClass = "tl-export";
                    if(h.event === 'EXPORT' || h.event === 'WRONG_DAY') { desc = "📥 Xuất file"; color = "#ff9900"; tlClass = "tl-export"; }
                    else if(h.event === 'RIP') { desc = "⚙️ Xong RIP"; color = "#00ccff"; tlClass = "tl-rip"; }
                    else if(h.event === 'PRINTING' || h.event === 'CUTTING') { 
                        runCounter++; desc = `▶️ Đang ${actionText.toLowerCase()} (L${runCounter})`; color = "#ff3366"; tlClass = "tl-run"; lastStartTime = h.time; 
                    }
                    else if(h.event === 'DONE') { 
                        doneCounter++; let l_text = runCounter > 0 ? ` (L${doneCounter})` : "";
                        desc = `✅ Hoàn tất${l_text}`; color = "#00fa9a"; tlClass = "tl-done"; 
                        if(lastStartTime) { durHtml = `<div class="tl-duration">⏱️ ${calculateDurationRaw(lastStartTime, h.time)}</div>`; lastStartTime = null; } 
                    }
                    else if(h.event === 'DELETE' || h.event === 'ADMIN_DELETE') { desc = "🛑 Hủy / Lỗi"; color = "#ff3333"; tlClass = "tl-cancel"; }
                    else if(h.event === 'ADMIN_DONE') { desc = "🛠️ Quản trị: Chốt Xong"; color = "#00fa9a"; tlClass = "tl-done"; }
                    else if(h.event === 'ADMIN_EXPORT') { desc = "🛠️ Quản trị: Trả về xuất lại"; color = "#ff9900"; tlClass = "tl-export"; }

                    html += `<div class="tl-item ${tlClass}"><div class="tl-time">${h.time.split(" ")[1]}</div><div class="tl-desc" style="color: ${color};">${desc}</div>${durHtml}</div>`;
                });
                html += '</div>';
            }
            document.getElementById('dt-timeline-container').innerHTML = html;
            document.getElementById('adminArea').style.display = localStorage.getItem("admin_pin") ? "block" : "none";
            document.getElementById('detailModal').style.display = 'block';
        }

        async function forceUpdate(newStatus) {
            let machine = document.getElementById('modal-machine-name').value; let fileName = document.getElementById('modal-real-name').value; let pin = localStorage.getItem("admin_pin");
            if (!pin) { alert("Phiên đăng nhập hết hạn."); closeModals(); toggleAuth(); return; }
            try {
                let res = await fetch('/api/update_status', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ machine: machine, name: fileName, status: newStatus, pin: pin }) });
                let result = await res.json();
                if(result.success) { closeModals(); fetchData(); } else { alert("Lỗi: " + result.error); if(result.error.includes("PIN")) { localStorage.removeItem("admin_pin"); checkAuthUI(); } }
            } catch (error) { alert("Lỗi kết nối."); }
        }

        function createCard(file) {
            let safeName = String(file.name || "Khong_Ten").replace(/'/g, "\\'").replace(/"/g, '&quot;');
            let actionText = (file.machine === "CNC") ? "Cắt" : "In";
            let runBadge = file.run > 1 ? `<span class="badge-run">${actionText}: ${file.run}</span>` : '';
            let zaloBadge = file.zalo_sent === 1 ? `<span class="badge" style="background-color: #0068ff; color: white; float: right; margin-left: 5px; font-size: 11px;">💬 Zalo</span>` : '';
            let imgHtml = file.machine !== 'CNC' ? `<img src="/thumbs/${file.hash}.jpg" class="card-thumb" onerror="this.style.display='none'" alt="Ảnh In">` : '';
            
            return `
                <div class="card" onclick="openDetailModal('${file.machine}', '${safeName}')">
                    <span class="badge badge-${file.machine}">${file.machine}</span>
                    ${zaloBadge}
                    ${runBadge}
                    ${imgHtml}
                    <div class="card-title">${file.name || "Khong_Ten"}</div>
                    <div class="card-time">${file.time_short}</div>
                </div>
            `;
        }

        function renderData() {
            try {
                let filter = document.getElementById('machineFilter').value;
                let filterFn = f => filter === 'ALL' || f.machine === filter;
                
                // 🌟 BỌC THÉP TRÁNH CRASH KHI CÓ FILE NULL
                let sortFn = (a, b) => (b.updated || "").localeCompare(a.updated || "");
                
                let fExport = allData.EXPORTED.filter(filterFn).sort(sortFn); let fRip = allData.RIP.filter(filterFn).sort(sortFn); let fRun = allData.RUNNING.filter(filterFn).sort(sortFn); let fDone = allData.DONE.filter(filterFn).sort(sortFn); let fCancel = allData.CANCELED.filter(filterFn).sort(sortFn);

                document.getElementById('exported-list').innerHTML = fExport.map(f => createCard(f)).join('');
                document.getElementById('rip-list').innerHTML = fRip.map(f => createCard(f)).join('');
                document.getElementById('run-list').innerHTML = fRun.map(f => createCard(f)).join('');
                document.getElementById('done-list').innerHTML = fDone.map(f => createCard(f)).join('');
                document.getElementById('cancel-list').innerHTML = fCancel.map(f => createCard(f)).join('');

                document.getElementById('count-export').innerText = fExport.length; document.getElementById('count-rip').innerText = fRip.length; document.getElementById('count-run').innerText = fRun.length; document.getElementById('count-done').innerText = fDone.length; document.getElementById('count-cancel').innerText = fCancel.length;

                let stats = {};
                fDone.forEach(f => {
                    let m2 = parseArea(f.name);
                    if(m2 > 0) { let finalM2 = m2 * f.run; if(!stats[f.machine]) stats[f.machine] = 0; stats[f.machine] += finalM2; }
                });
                let sumHtml = '';
                for(let m in stats) sumHtml += `<span style="margin-right: 15px; font-size: 13px;"><b>${m}:</b> <span style="color:#00fa9a;">${stats[m].toFixed(2)}m²</span></span>`;
                
                if(sumHtml === '') sumHtml = '<span style="color:#777; font-size:12px;">Chưa có dữ liệu m²</span>';
                document.getElementById('m2-summary').innerHTML = sumHtml;
            } catch (err) {
                console.error("Lỗi Render JS:", err);
                document.getElementById('m2-summary').innerHTML = '<span style="color:#ff3333; font-size:12px;">Có lỗi dữ liệu. Vui lòng F5.</span>';
            }
        }

        async function fetchData() {
            let selectedDate = document.getElementById('datePicker').value;
            if(!selectedDate) return;
            try {
                const response = await fetch('/api/data?date=' + selectedDate);
                allData = await response.json(); 
                renderData();
            } catch (error) { 
                console.log("Lỗi fetch API:", error); 
                document.getElementById('m2-summary').innerHTML = '<span style="color:#ff3333; font-size:12px;">Mất kết nối máy chủ...</span>';
            }
        }

        // 🌟 VÁ LỖI ÉP TRÌNH DUYỆT PHẢI TẢI DỮ LIỆU NGAY KHI MỞ TRANG
        fetchData();
        applyQuickDate(); // Chạy luôn phần ERP

        document.getElementById('datePicker').addEventListener('change', fetchData);
        document.getElementById('machineFilter').addEventListener('change', renderData);
        
        checkAuthUI(); connectWebSocket();
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

@app.route("/api/data")
def api_data():
    target_date = request.args.get('date', datetime.now().strftime("%Y-%m-%d"))
    result = {"EXPORTED": [], "RIP": [], "RUNNING": [], "DONE": [], "CANCELED": []}
    
    for machine in MACHINES:
        db_path = os.path.join(DB_DIR, f"{machine}.db")
        if not os.path.exists(db_path): continue
        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
            c = conn.cursor()
            c.execute(f"SELECT file_hash, file_name, status, created_time, updated_time, run_count, history, zalo_sent FROM files WHERE DATE(updated_time) = '{target_date}'")
            rows = c.fetchall()
            for f_hash, name, status, c_time, up_time, run_cnt, history_data, z_sent in rows:
                time_short = up_time.split(" ")[1] if up_time and " " in up_time else ""
                try: r_cnt = int(run_cnt)
                except: r_cnt = 1
                
                # BỌC THÉP DỮ LIỆU ĐỔ VỀ WEB KHÔNG ĐƯỢC CHỨA NULL
                item = {
                    "hash": f_hash or "", 
                    "machine": machine or "", 
                    "name": str(name) if name else "Khong_Ten", 
                    "created": c_time or "", 
                    "updated": up_time or "", 
                    "time_short": time_short or "", 
                    "run": r_cnt, 
                    "history": history_data or "[]", 
                    "zalo_sent": z_sent or 0 
                }
                
                if status in ["EXPORTED", "WRONG_DAY"]: result["EXPORTED"].append(item)
                elif status == "RIP": result["RIP"].append(item)
                elif status in ["PRINTING", "CUTTING"]: result["RUNNING"].append(item)
                elif status == "DONE": result["DONE"].append(item)
                elif status in ["DELETED", "LỖI"]: result["CANCELED"].append(item) 
            conn.close()
        except Exception: pass
    return jsonify(result)

# LẤY THÔNG TIN THỐNG KÊ (CÓ TÙY CHỈNH NGÀY/MÁY)
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
    jobs_by_customer = {}
    jobs_by_hour = {str(i).zfill(2): 0 for i in range(24)}
    
    total_done = 0
    total_cancelled = 0
    total_m2_all = 0.0
    
    date_filter = f"DATE(updated_time) BETWEEN '{start_date}' AND '{end_date} 23:59:59'"

    machines_to_scan = MACHINES if machine_filter == "ALL" else [machine_filter]

    for machine in machines_to_scan:
        db_path = os.path.join(DB_DIR, f"{machine}.db")
        if not os.path.exists(db_path): continue
        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
            c = conn.cursor()
            
            c.execute(f"SELECT COUNT(*) FROM files WHERE status='DELETED' AND {date_filter}")
            total_cancelled += c.fetchone()[0]
            
            c.execute(f"SELECT file_name, updated_time, run_count FROM files WHERE status='DONE' AND {date_filter}")
            for name, up_time, run_cnt in c.fetchall():
                total_done += 1
                try: r_cnt = int(run_cnt)
                except: r_cnt = 1
                
                m2 = parse_area_python(name)
                if m2 > 0: 
                    m2_by_machine[machine] += (m2 * r_cnt)
                    total_m2_all += (m2 * r_cnt)
                
                parts = str(name).split('_') if name else []
                if parts:
                    raw_cus = parts[0]
                    cus_code = chuan_hoa_chuoi(raw_cus)
                    cus_name = vip_dict.get(cus_code, raw_cus.upper())
                    if len(cus_name) > 15: cus_name = cus_name[:15] + "..." 
                    jobs_by_customer[cus_name] = jobs_by_customer.get(cus_name, 0) + 1
                
                if up_time and " " in up_time:
                    hour = up_time.split(" ")[1].split(":")[0]
                    jobs_by_hour[hour] = jobs_by_hour.get(hour, 0) + 1
            conn.close()
        except: pass

    sorted_customers = sorted(jobs_by_customer.items(), key=lambda x: x[1], reverse=True)[:10]
    cancel_rate = (total_cancelled / (total_done + total_cancelled) * 100) if (total_done + total_cancelled) > 0 else 0

    return jsonify({
        "summary": { "total_jobs": total_done, "total_m2": total_m2_all, "cancel_rate": cancel_rate },
        "m2": {k: v for k, v in m2_by_machine.items() if k in machines_to_scan},
        "customers": {"labels": [x[0] for x in sorted_customers], "data": [x[1] for x in sorted_customers]},
        "hours": {"labels": list(jobs_by_hour.keys()), "data": list(jobs_by_hour.values())}
    })

@app.route("/api/export_csv")
def export_csv():
    start_date = request.args.get('start')
    end_date = request.args.get('end')
    machine_filter = request.args.get('machine', 'ALL')
    
    if not start_date or not end_date: return "Missing dates", 400
    date_filter = f"DATE(updated_time) BETWEEN '{start_date}' AND '{end_date} 23:59:59'"
    machines_to_scan = MACHINES if machine_filter == "ALL" else [machine_filter]
    
    csv_data = "\ufeffMÁY,TÊN FILE,TRẠNG THÁI,DIỆN TÍCH (m2),SỐ LẦN CHẠY,THỜI GIAN CẬP NHẬT\n"
    
    for machine in machines_to_scan:
        db_path = os.path.join(DB_DIR, f"{machine}.db")
        if not os.path.exists(db_path): continue
        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
            c = conn.cursor()
            c.execute(f"SELECT file_name, status, run_count, updated_time FROM files WHERE {date_filter} ORDER BY updated_time DESC")
            for name, status, run_cnt, up_time in c.fetchall():
                m2 = parse_area_python(name)
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
    if request.json.get("pin") == ADMIN_PIN: return jsonify({"success": True})
    return jsonify({"success": False, "error": "Mã PIN không đúng."})

@app.route("/api/update_status", methods=["POST"])
def update_status():
    data = request.json
    machine = data.get("machine"); file_name = data.get("name")
    new_status = data.get("status"); pin_code = data.get("pin")
    
    if pin_code != ADMIN_PIN: return jsonify({"success": False, "error": "Mã PIN không hợp lệ."})
    db_path = os.path.join(DB_DIR, f"{machine}.db")
    if not os.path.exists(db_path): return jsonify({"success": False, "error": "Không tìm thấy CSDL."})

    try:
        conn = sqlite3.connect(db_path, timeout=15)
        conn.execute("PRAGMA journal_mode=WAL;")
        c = conn.cursor()
        c.execute("SELECT history FROM files WHERE file_name=?", (file_name,))
        row = c.fetchone()
        hist_str = row[0] if row and row[0] else "[]"
        try:
            h_list = json.loads(hist_str)
            event_name = "DONE" if new_status == "DONE" else ("DELETE" if new_status == "DELETED" else "EXPORT")
            h_list.append({"status": new_status, "time": now(), "event": f"ADMIN_{event_name}"})
            hist_str = json.dumps(h_list)
        except: pass

        c.execute("UPDATE files SET status=?, updated_time=?, zalo_sent=0, history=? WHERE file_name=?", (new_status, now(), hist_str, file_name))
        conn.commit(); conn.close()
        try: requests.get("http://127.0.0.1:8000/api/broadcast", timeout=2)
        except: pass
        return jsonify({"success": True})
    except Exception as e: return jsonify({"success": False, "error": str(e)})

if __name__ == "__main__":
    # In ra màn hình để biết web đã chạy
    print_log("🚀 KHỞI ĐỘNG WEB DASHBOARD (BẢN CHUẨN LAN, CHỐNG ĐƠ WEB)...")
    
    # Chạy máy chủ (debug=False để không bao giờ bị đơ/reset tự động)
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
