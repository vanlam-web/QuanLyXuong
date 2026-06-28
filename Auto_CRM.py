# =========================================
# AUTO CRM V5.1 - (BẢN HOÀN CHỈNH THỰC SỰ)
# (Core Selenium V4.1 FINAL + Logic V5.0)
# =========================================
import os, sys, time, sqlite3, json, re, subprocess, unicodedata, threading, requests, random
from datetime import datetime
import uvicorn
from fastapi import FastAPI
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains

DB_DIR = r"C:\QuanLyXuong\Data"
MACHINES = ["InBat", "InDecal"]
OPENCLAW_PATH = r"C:\Users\Admin\AppData\Roaming\npm\openclaw.cmd"
NAS_CRM_EXE_PATH = r"\\192.168.1.188\AI\Tools\dist\Auto_CRM.exe"

KIOT_URL = "https://quangcaoinvanlam.kiotviet.vn/" 
USERNAME = os.getenv("KIOT_USERNAME", "Bot")
PASSWORD = os.getenv("KIOT_PASSWORD", "")
ZALO_GROUP_ID = os.getenv("AUTO_CRM_ZALO_GROUP_ID", "")

# =========================================
# CỐ ĐỊNH 100% ĐƯỜNG DẪN VỀ Ổ C BẤT CHẤP VỊ TRÍ FILE CHẠY
# =========================================
BASE_DATA_CRM = r"C:\QuanLyXuong\Data_Auto_CRM"
os.makedirs(BASE_DATA_CRM, exist_ok=True)

FILE_VIP = os.path.join(BASE_DATA_CRM, "DanhBa_VIP.json")
FILE_MATERIAL = os.path.join(BASE_DATA_CRM, "Map_ChatLieu.json")
CRM_MEMORY_FILE = os.path.join(BASE_DATA_CRM, "crm_memory.json")
BOT_PROFILE_DIR = os.path.join(BASE_DATA_CRM, "Bot_Profile")
LOG_FILE = os.path.join(BASE_DATA_CRM, "Auto_CRM_Log.txt")

POLL = 180
CREATE_NO_WINDOW = 0x08000000

wake_up_event = threading.Event()
crm_webhook_app = FastAPI()

@crm_webhook_app.get("/wake_up")
def wake_up_crm():
    print_log("🔔 NHẬN TÍN HIỆU: Đang đánh thức Bot...")
    wake_up_event.set()
    return {"status": "Bot CRM Đã Tỉnh Giấc!"}

def start_webhook_listener():
    uvicorn.run(crm_webhook_app, host="127.0.0.1", port=8001, log_level="critical")

def auto_update_watcher():
    start_mtime = 0
    while True:
        time.sleep(10)
        try:
            if not os.path.exists(NAS_CRM_EXE_PATH): continue
            cur_mtime = os.path.getmtime(NAS_CRM_EXE_PATH)
            if start_mtime == 0: start_mtime = cur_mtime
            elif cur_mtime != start_mtime:
                print_log("🚀 PHÁT HIỆN BẢN MỚI TRÊN NAS! BOT SẼ THOÁT ĐỂ LÊN ĐỜI...")
                subprocess.call("taskkill /F /IM server_Local.exe /T", shell=True)
                os._exit(0) 
        except: pass

def now(): return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
def print_log(msg):
    log_str = f"[{now()}] {msg}"
    print(log_str)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f: f.write(log_str + "\n")
    except: pass

def chuan_hoa_chuoi(text):
    if not text: return ""
    text = text.lower()
    text = unicodedata.normalize('NFKD', text).encode('ASCII', 'ignore').decode('utf-8')
    text = re.sub(r'[^a-z0-9]', '', text)
    return text

def load_json(filepath):
    try:
        if os.path.exists(filepath):
            with open(filepath, "r", encoding="utf-8") as f: return json.load(f)
    except: pass
    return {}

def save_memory(data):
    try:
        with open(CRM_MEMORY_FILE, "w", encoding="utf-8") as f: json.dump(list(data), f)
    except: pass

def send_zalo(msg, target, image_path=None):
    if not target: return
    try:
        channel_name = "zalouser" 
        base_cmd = [OPENCLAW_PATH, "message", "send", "--channel", channel_name, "--target", target, "--message", msg.replace("\n", "\\n"), "--profile", "default"]
        
        if image_path and os.path.exists(image_path):
            cmd_args = base_cmd + ["--media", image_path] 
            p = subprocess.Popen(cmd_args, creationflags=CREATE_NO_WINDOW, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if p.wait() == 0: 
                print_log(f"🟢 Đã gửi Zalo kèm Bill -> {target[:15]}...")
                return 
            else:
                print_log(f"⚠️ OpenClaw từ chối ảnh. Đang tự động gửi tin nhắn chữ thay thế...")

        p = subprocess.Popen(base_cmd, creationflags=CREATE_NO_WINDOW, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if p.wait() == 0: print_log(f"🟢 Đã gửi Zalo chữ -> {target[:15]}...")
        else: print_log(f"❌ Lỗi gửi Zalo: Kênh '{channel_name}' không khả dụng!")
    except Exception as e: print_log(f"❌ Lỗi hệ thống Zalo: {e}")

def parse_filename(filename, machine_name, map_chatlieu):
    name_no_ext = os.path.splitext(filename)[0]
    
    if "~" in name_no_ext: 
        name_no_ext = name_no_ext.split("~", 1)[-1]
        
    parts = name_no_ext.split("_")
    cus_code_norm = chuan_hoa_chuoi(parts[0])
    
    parsed_data = {
        "cus_code": cus_code_norm, "material_raw": "Chưa rõ", "kiot_code": "IB",
        "ten_khach_thay": "Sản phẩm In", "dimension": "Chưa rõ", "quantity": 1, 
        "notes": "", "raw_name": name_no_ext, "is_mapped": False
    }
    
    if len(parts) == 1: return parsed_data

    quantity = 1
    last_part = parts[-1].strip()
    if re.match(r'^[xX]\d+$', last_part):
        quantity = int(last_part[1:])
        parts.pop() 
    
    dimension = "Chưa rõ"; dim_idx = -1
    for i in range(1, len(parts)):
        if re.search(r'^\d+(\.\d+)?[xX*]\d+(\.\d+)?$', parts[i].strip()):
            dimension = parts[i].lower().replace('*', 'x'); dim_idx = i; break
            
    material_raw = ""
    if dim_idx > 1: material_raw = "_".join(parts[1:dim_idx])
    elif dim_idx == -1 and len(parts) > 1: material_raw = parts[1]
        
    # 🌟 KỶ LUẬT THÉP VÀ MẶC ĐỊNH
    search_key = chuan_hoa_chuoi(material_raw) if material_raw else f"default{machine_name.lower()}"
    is_mapped = search_key in map_chatlieu
    
    if is_mapped:
        res = map_chatlieu[search_key]
        if isinstance(res, list): 
            kiot_code, ten_khach_thay = res[0], res[1]
        else: 
            kiot_code, ten_khach_thay = res, material_raw
    else:
        kiot_code, ten_khach_thay = None, material_raw

    notes = ", ".join(parts[dim_idx+1:]) if dim_idx != -1 and dim_idx < len(parts) - 1 else ""
    parsed_data.update({"material_raw": material_raw, "kiot_code": kiot_code, "ten_khach_thay": ten_khach_thay, "dimension": dimension, "quantity": quantity, "is_mapped": is_mapped, "notes": notes})
    return parsed_data

def tao_bill_kiotviet(cus_code, search_kh, search_sp, dai_m, rong_m, so_luong, file_name=""):
    print_log(f"🤖 KiotViet: Đang lên đơn cho KH [{cus_code}] - SP [{search_sp}]...")
    try: 
        subprocess.call("taskkill /f /im chromedriver.exe /T", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(1)
    except: pass

    options = webdriver.ChromeOptions()
    # options.add_argument("--headless=new") 
    options.add_argument("--window-size=1920,1080") 
    options.add_argument(f"--user-data-dir={BOT_PROFILE_DIR}")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    
    js_hacker = """
    window.print = function() {
        var htmlContent = document.documentElement.outerHTML;
        var botFrame = window.top.document.createElement('iframe');
        botFrame.id = 'bot-bill-overlay';
        botFrame.style.cssText = 'position:fixed; top:0; left:0; width:794px; height:794px; background:white; z-index:2147483647; border:none;';
        window.top.document.body.appendChild(botFrame);
        botFrame.contentWindow.document.open();
        botFrame.contentWindow.document.write(htmlContent);
        botFrame.contentWindow.document.close();
    };
    """
    
    driver = None
    current_step = "Khởi động Trình duyệt Chrome"
    try:
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {"source": js_hacker})
        wait = WebDriverWait(driver, 15)
        actions = ActionChains(driver)

        current_step = "Bước 0: Đăng nhập"
        driver.get(KIOT_URL)
        time.sleep(3)
        try:
            pass_input = driver.find_elements(By.ID, "Password")
            if len(pass_input) > 0 and pass_input[0].is_displayed():
                print_log("🔑 Phát hiện chưa đăng nhập. Đang tiến hành đăng nhập...")
                driver.find_element(By.ID, "UserName").send_keys(USERNAME)
                pass_input[0].send_keys(PASSWORD + Keys.RETURN)
                time.sleep(7)
        except: pass
        
        current_step = "Bước 1: Vào Bán Hàng & Dọn rác"
        driver.get(KIOT_URL + "sale/#/")
        time.sleep(6) # 🌟 KHÔI PHỤC LẠI THỜI GIAN CHỜ SỐNG CÒN CỦA V4.1
        try:
            for nut in driver.find_elements(By.XPATH, "//button[contains(text(), 'Đã hiểu')] | //a[contains(text(), 'Bỏ qua')] | //a[contains(text(), 'Đóng')]"):
                if nut.is_displayed(): nut.click(); time.sleep(1)
        except: pass 
        try:
            for nut_x in driver.find_elements(By.XPATH, "//li[contains(@class, 'active')]//i[contains(@class, 'times') or contains(@class, 'remove')] | //a[@title='Đóng' or contains(@title, 'Đóng Hóa đơn')]"):
                if nut_x.is_displayed():
                    nut_x.click(); time.sleep(1)
                    driver.find_element(By.XPATH, "//button[contains(text(), 'Đồng ý')]").click(); time.sleep(2)
        except: pass

        current_step = "Bước 2: Nhập khách hàng"
        khach_hang = wait.until(EC.presence_of_element_located((By.XPATH, "//input[@placeholder='Tìm khách hàng (F4)']")))
        khach_hang.send_keys(Keys.CONTROL + "a"); khach_hang.send_keys(Keys.BACKSPACE) # Xoá rác cũ nếu có
        time.sleep(0.5)
        khach_hang.send_keys(search_kh)
        time.sleep(3.5) # ⏳ Tăng thời gian chờ KiotViet load danh sách lên 3.5 giây
        khach_hang.send_keys(Keys.ARROW_DOWN)
        time.sleep(0.5) # Chờ mũi tên khựng lại đúng ô
        khach_hang.send_keys(Keys.RETURN)
        time.sleep(1.5)
        
        driver.execute_script("""
            var btns = document.querySelectorAll('.k-window button, .modal-dialog button');
            for(var i=0; i<btns.length; i++) {
                var txt = (btns[i].innerText || '').toUpperCase();
                if(txt === 'ĐỒNG Ý' || txt === 'BỎ QUA' || txt === 'ĐÓNG') { if(btns[i].offsetParent !== null) btns[i].click(); }
            }
        """)
        
        current_step = "Bước 3: Chọn sản phẩm"
        san_pham = wait.until(EC.presence_of_element_located((By.XPATH, "//input[@placeholder='Tìm hàng hóa (F3)']")))
        san_pham.send_keys(Keys.CONTROL + "a"); san_pham.send_keys(Keys.BACKSPACE)
        time.sleep(0.5)
        san_pham.send_keys(search_sp)
        time.sleep(3.5) # ⏳ Tăng thời gian chờ load sản phẩm
        san_pham.send_keys(Keys.ARROW_DOWN)
        time.sleep(0.5)
        san_pham.send_keys(Keys.RETURN)
        time.sleep(2)
        
        current_step = "Bước 4: Mở bảng Thước kẻ"
        try:
            tat_ca_chu = driver.find_elements(By.XPATH, f"//*[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{search_sp.lower()}')]")
            chu_that = next((chu for chu in tat_ca_chu if chu.is_displayed() and chu.size['width'] > 0), None)
            if chu_that:
                actions.move_to_element(chu_that).perform(); time.sleep(1)
                dong_chua = chu_that.find_element(By.XPATH, "./ancestor::li | ./ancestor::tr | ./ancestor::div[contains(@class, 'row') or contains(@class, 'item')]")
                btn_thuoc_ke = dong_chua.find_element(By.XPATH, ".//button[contains(@class, 'btn-calSize')]")
                driver.execute_script("arguments[0].click();", btn_thuoc_ke)
            else:
                btn_thuoc_ke = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".btn-calSize")))
                driver.execute_script("arguments[0].click();", btn_thuoc_ke)
        except:
            btn_thuoc_ke = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".btn-calSize")))
            driver.execute_script("arguments[0].click();", btn_thuoc_ke)
        time.sleep(2) 
        
        current_step = "Bước 5: Nhập Kích thước & Số lượng"
        cac_o_nhap_m = driver.find_elements(By.XPATH, "//input[@placeholder='0 (m)' or contains(@placeholder, 'm)')]")
        if len(cac_o_nhap_m) >= 2:
            driver.execute_script("arguments[0].click();", cac_o_nhap_m[0]); time.sleep(0.2)
            cac_o_nhap_m[0].send_keys(Keys.CONTROL + "a"); cac_o_nhap_m[0].send_keys(Keys.BACKSPACE); cac_o_nhap_m[0].send_keys(str(rong_m)); time.sleep(0.4)
            
            driver.execute_script("arguments[0].click();", cac_o_nhap_m[1]); time.sleep(0.2)
            cac_o_nhap_m[1].send_keys(Keys.CONTROL + "a"); cac_o_nhap_m[1].send_keys(Keys.BACKSPACE); cac_o_nhap_m[1].send_keys(str(dai_m)); time.sleep(0.4)
            
            try:
                xpath_sl = "//input[contains(@ng-model, 'Attribute3') or contains(@ng-change, '3)')]"
                o_sl = driver.find_element(By.XPATH, xpath_sl)
                driver.execute_script("arguments[0].click();", o_sl); time.sleep(0.2)
                o_sl.send_keys(Keys.CONTROL + "a"); o_sl.send_keys(Keys.BACKSPACE); o_sl.send_keys(str(so_luong))
            except:
                cac_o_nhap_m[1].send_keys(Keys.TAB); time.sleep(0.2)
                active = driver.switch_to.active_element; active.send_keys(str(so_luong))
            time.sleep(0.5)

        current_step = "Bước 6: Bấm nút Xong"
        try:
            driver.execute_script("""
                var btns = document.querySelectorAll('.k-window button');
                for(var i=0; i<btns.length; i++) {
                    if((btns[i].innerText || '').trim().toUpperCase() === 'XONG' && btns[i].offsetParent !== null) { btns[i].click(); }
                }
            """)
            time.sleep(1)
            try: driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.ENTER)
            except: pass
            time.sleep(1.5)
        except Exception as e: print_log(f"⚠️ Bỏ qua kẹt nút Xong: {e}")
        
        current_step = "Bước 7+8: Ghi nợ và Chốt đơn"
        try:
            time.sleep(2) 
            for lan_thu in range(3):
                try:
                    driver.execute_script("""
                        var popups = document.querySelectorAll('.k-window button');
                        for(var i=0; i<popups.length; i++) {
                            var txt = (popups[i].innerText || '').toUpperCase();
                            if((txt.includes('ĐỒNG Ý') || txt.includes('BỎ QUA') || txt.includes('ĐÓNG')) && popups[i].offsetParent !== null) { popups[i].click(); }
                        }
                    """)
                    time.sleep(1)

                    driver.execute_script("""
                        var btnThanhToan = document.querySelector("#saveTransaction") || document.querySelector(".btn-payment") || document.querySelector("a[title*='Thanh toán']");
                        if(btnThanhToan) btnThanhToan.click();
                    """)
                    time.sleep(1)
                    try: driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.F9)
                    except: pass
                    time.sleep(2.5) 
                    
                    driver.execute_script("""
                        var inputs = document.querySelectorAll('input');
                        for(var i=0; i<inputs.length; i++) {
                            var css = inputs[i].className || ''; var id = inputs[i].id || '';
                            if(css.includes('payingAmt') || id.includes('payingAmtInvoice')) {
                                inputs[i].focus(); inputs[i].value = '0';
                                inputs[i].dispatchEvent(new Event('input', { bubbles: true })); inputs[i].dispatchEvent(new Event('change', { bubbles: true })); break;
                            }
                        }
                    """)
                    time.sleep(1); print_log("✅ Đã chốt Khách thanh toán = 0 thành công!")

                    driver.execute_script("""
                        var saveBtn = document.querySelector("#saveTransactionRegPmt") || document.querySelector("#saveTransactionNormal");
                        if(saveBtn && !saveBtn.disabled && saveBtn.offsetParent !== null) { saveBtn.click(); } 
                        else {
                            var btns = document.querySelectorAll('button');
                            for(var i=0; i<btns.length; i++) {
                                var txt = (btns[i].innerText || '').toUpperCase().trim();
                                if((txt === 'THANH TOÁN (F9)' || txt === 'THANH TOÁN') && btns[i].offsetParent !== null) { btns[i].click(); break; }
                            }
                        }
                    """)
                    time.sleep(1)
                    try: driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.F9)
                    except: pass
                    time.sleep(3) 

                    driver.execute_script("""
                        var btnKendo = document.querySelector("body > div.k-widget.k-window.k-window-danger button.btn.btn-danger");
                        if (btnKendo) btnKendo.click();
                        else {
                            var btns = document.querySelectorAll('.k-window button, .modal-dialog button');
                            for(var i=0; i<btns.length; i++) {
                                var txt = (btns[i].innerText || '').toUpperCase();
                                if((txt.includes('ĐỒNG Ý') || txt.includes('XÁC NHẬN') || btns[i].classList.contains('btn-danger')) && btns[i].offsetParent !== null) { btns[i].click(); break; }
                            }
                        }
                    """)
                    time.sleep(2.5)
                    
                    if driver.execute_script("return document.getElementById('bot-bill-overlay') != null;"): break
                        
                except Exception as loi_nho:
                    print_log(f"⚠️ Kẹt nhẹ lần {lan_thu + 1}, đang thử ép lại: {loi_nho}")
                    try: driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
                    except: pass
                    time.sleep(1)
            
        except Exception as e:
            print_log(f"⚠️ Kẹt Bước 7-8, ép qua bằng Enter... ({e})")
            try: driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.ENTER)
            except: pass

        current_step = "Bước 9: Chụp ảnh Bill"
        try:
            khung_bill = WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.ID, "bot-bill-overlay")))
            time.sleep(1.5) 
            filename = os.path.join(BASE_DATA_CRM, f"Bill_{cus_code}.png")
            khung_bill.screenshot(filename)
            print_log(f"📸 Đã tóm gọn Bill xuất sắc: {filename}")
            driver.execute_script("arguments[0].remove();", khung_bill)
            return True
        except Exception as e:
            print_log(f"⚠️ Lỗi Không tóm được Bill: Timeout (Chốt đơn không thành công)")
            return False
            
    except Exception as e:
        if "session not created" in str(e) or "Chrome instance exited" in str(e): 
            print_log("⚠️ LỖI NẶNG: Trình duyệt bị khóa chết cứng. Sếp thử reset lại máy tính nhé.")
        else: 
            print_log(f"❌ Kẹt KiotViet tại [{current_step}]: {str(e)}")
            try:
                debug_img = os.path.join(BASE_DATA_CRM, f"Loi_KiotViet_{cus_code}.png")
                driver.save_screenshot(debug_img)
            except: pass
        return False
    finally:
        if driver:
            try: driver.quit() 
            except: pass

def main():
    print_log(f"🚀 KHỞI ĐỘNG AUTO CRM V5.1 (BẢN HOÀN CHỈNH THỰC SỰ - SELENIUM V4.1)")
    threading.Thread(target=start_webhook_listener, daemon=True).start()
    threading.Thread(target=auto_update_watcher, daemon=True).start()
    
    crm_memory = set(load_json(CRM_MEMORY_FILE)) if isinstance(load_json(CRM_MEMORY_FILE), list) else set()
    retry_counts = {}

    while True:
        try:
            vip_dict_raw = load_json(FILE_VIP); map_chatlieu_raw = load_json(FILE_MATERIAL)
            if not vip_dict_raw: 
                print_log(f"⚠️ CẢNH BÁO: Không tìm thấy danh bạ tại [{FILE_VIP}].")
                wake_up_event.wait(10); wake_up_event.clear(); continue
                
            vip_dict = {chuan_hoa_chuoi(k): v for k, v in vip_dict_raw.items()}
            map_chatlieu = {chuan_hoa_chuoi(k): v for k, v in map_chatlieu_raw.items()}
            
            for m in MACHINES:
                db = os.path.join(DB_DIR, f"{m}.db")
                if not os.path.exists(db): continue
                try:
                    conn = sqlite3.connect(db, timeout=15)
                    rows = conn.execute("SELECT file_name, file_hash, run_count FROM files WHERE status = 'DONE' AND DATE(updated_time) = DATE('now', 'localtime')").fetchall()
                    conn.close()

                    for name, f_hash, run_count in rows:
                        run_count = int(run_count)
                        mem_key = f"{f_hash}_L{run_count}"
                        if mem_key in crm_memory: continue

                        parsed = parse_filename(name, m, map_chatlieu)
                        cus_code = parsed.get("cus_code")
                        if cus_code not in vip_dict:
                            crm_memory.add(mem_key); save_memory(crm_memory); continue

                        # 🚨 KỶ LUẬT THÉP: Chặn đứng nếu thiếu kích thước HOẶC chất liệu chưa có trong JSON
                        if parsed['dimension'] == "Chưa rõ" or not parsed.get("is_mapped"):
                            ly_do = "THIẾU KÍCH THƯỚC" if parsed['dimension'] == "Chưa rõ" else f"CHẤT LIỆU LẠ CHƯA KHAI BÁO ({parsed['material_raw']})"
                            print_log(f"⚠️ BỎ QUA [{name}]: {ly_do}")
                            
                            if ZALO_GROUP_ID:
                                send_zalo(f"🚨 CẢNH BÁO ĐƠN HÀNG VIP: {name}\n❌ Lý do: {ly_do}.\n⚠️ Bot từ chối lên đơn này. Sếp xử lý tay nhé!", ZALO_GROUP_ID)
                            
                            crm_memory.add(mem_key); save_memory(crm_memory); continue

                        info_khach = vip_dict[cus_code]; target_id = info_khach.get("zalo_id")
                        is_zalo_off = "zalo_id_off" in info_khach
                        ten_khach = info_khach.get("ten_day_du", cus_code)
                        kiot_id = info_khach.get("kiot_id", cus_code)
                        
                        kich_str = parsed['dimension']; dai_m, rong_m = "1", "1"
                        if "x" in kich_str:
                            d, r = kich_str.split("x"); dai_m, rong_m = str(float(d)/100), str(float(r)/100)
                        
                        sl_text = f" (SL: {parsed['quantity']} tấm)" if parsed['quantity'] > 1 else ""
                        chat_lieu = parsed.get('ten_khach_thay')

                        if run_count == 1:
                            success = tao_bill_kiotviet(cus_code, kiot_id, parsed['kiot_code'], dai_m, rong_m, parsed['quantity'], name)
                            bill_p = os.path.join(BASE_DATA_CRM, f"Bill_{cus_code}.png")
                            
                            if success and os.path.exists(bill_p):
                                if is_zalo_off:
                                    print_log(f"🔕 Đã lên KiotViet thành công cho [{name}] (Zalo đang TẮT).")
                                elif target_id:
                                    loi_chao = [
                                        f"Đại vương ơi, {chat_lieu} xong rồi, qua rước ẻm đi! 🏃‍♂️💨",
                                        f"SOS! {chat_lieu} đã ra lò, qua bế lẹ sếp ơi! 🚑",
                                        f"Thượng đế ơi! Lên xe qua lấy {chat_lieu} thôi! 🛵",
                                        f"Báo cáo: Đã hoàn thành nhiệm vụ! 🫡", 
                                        f"{chat_lieu} in xong! Mau qua hốt về! 📜",
                                        f"Ét ô ét! {chat_lieu} xong rồi, ra nhận hàng sếp ơi! 📢",
                                        f"{chat_lieu} xong nghe chủ Shop! ♂️",
                                        f"{chat_lieu} quá đẹp, qua lấy ngay kẻo mất! 🚨",
                                        f"{chat_lieu} đã hoàn tất, mời đại ca qua lấy! 💥",
                                        f"{chat_lieu} đang bơ vơ giữa xưởng! 🥺",
                                        f"[BOT]: Đã in xong {chat_lieu} nha sếp!" 
                                    ]
                                    msg = f"{random.choice(loi_chao)}{sl_text}\n"
                                    send_zalo(msg, target_id, bill_p)
                                try: os.remove(bill_p) 
                                except: pass
                                
                                try:
                                    c_up = sqlite3.connect(db, timeout=15)
                                    c_up.execute("PRAGMA journal_mode=WAL;") 
                                    c_up.execute("UPDATE files SET zalo_sent = 1 WHERE file_hash = ?", (f_hash,))
                                    c_up.commit(); c_up.close()
                                    try: requests.get("http://127.0.0.1:8000/api/broadcast", timeout=1)
                                    except: pass
                                except Exception as e:
                                    print_log(f"⚠️ Lỗi cập nhật icon Zalo: {e}")
                                    
                                crm_memory.add(mem_key); save_memory(crm_memory); retry_counts.pop(mem_key, None)
                            else:
                                # 🌟 LOGIC LÌ LỢM
                                att = retry_counts.get(mem_key, 0) + 1; retry_counts[mem_key] = att
                                if att < 3:
                                    print_log(f"⚠️ Thử lại đơn [{name}] lần {att}/3...")
                                elif att == 3:
                                    print_log(f"❌ KiotViet từ chối [{name}] 3 lần. Đã báo Zalo, đang tiếp tục ngâm để thử lại ngầm...")
                                    send_zalo(f"🚨 LỖI KIOTVIET: {name}\n❌ Đã thử 3 lần thất bại. \n⏳ Bot sẽ không bỏ cuộc, đang tự động đưa vào hàng đợi để thử lên lại bill liên tục...", ZALO_GROUP_ID)
                                elif att % 5 == 0:
                                    print_log(f"⚠️ Vẫn đang kiên trì thử lại đơn [{name}] (Lần {att})...")
                        else:
                            if is_zalo_off:
                                print_log(f"🔄 Đơn bù hao (Lần {run_count}) cho [{name}]: Đã bị tắt Zalo, bỏ qua.")
                            elif target_id:
                                loi_chao_bu_hao = [
                                    f"Báo cáo Đại vương! {chat_lieu} in lần {run_count} đã xong! 🛠️",
                                    f"{chat_lieu} lần {run_count} ra lò rồi sếp ơi 🚑",
                                    f" Đã in lại {chat_lieu} lần {run_count} ♻️",
                                    f"Lạy chúa, {chat_lieu} in lần {run_count} xong rồi! 😭",
                                    f"Xong {chat_lieu} KT: {kich_str} lần{run_count} nghe chủ Shop! 😭"
                                ]
                                msg = f"{random.choice(loi_chao_bu_hao)}\n"
                                send_zalo(msg, target_id)
                                
                            try:
                                c_up = sqlite3.connect(db, timeout=15)
                                c_up.execute("PRAGMA journal_mode=WAL;") 
                                c_up.execute("UPDATE files SET zalo_sent = 1 WHERE file_hash = ?", (f_hash,))
                                c_up.commit(); c_up.close()
                                try: requests.get("http://127.0.0.1:8000/api/broadcast", timeout=1)
                                except: pass
                            except Exception as e:
                                print_log(f"⚠️ Lỗi cập nhật icon Zalo: {e}")

                            crm_memory.add(mem_key); save_memory(crm_memory)
                except: pass
            
            wake_up_event.wait(POLL); wake_up_event.clear() 
        except Exception as e: print_log(f"Lỗi: {e}"); time.sleep(5)

if __name__ == "__main__": main()
