# Ke Hoach Nang Cap Phan Mem Quan Ly Xuong

## Tom Tat

Muc tieu nang cap: **on dinh truoc**, lam theo tung giai doan nho, khong viet lai toan bo, khong lam gian doan xuong. Giu nguyen luong hien tai:

```text
QuanLyXuong client -> server -> SQLite -> Dashboard -> Auto CRM -> OpenClaw -> Zalo
```

Repo GitHub hien tai: `vanlam-web/QuanLyXuong`. Moi giai doan phai co commit rieng, test duoc, rollback duoc.

## Giai Doan Nang Cap

### Giai doan 0: Dong bang hien trang va bao ve du lieu

Muc tieu: co diem quay lai an toan truoc khi sua sau.

Viec can lam:

- Tao tag Git: `baseline-before-upgrade`.
- Backup toan bo:
  - `C:\QuanLyXuong\Data`
  - `C:\QuanLyXuong\Data_Auto_CRM`
  - `Z:\Tools`
- Ghi lai process dang chay: `server_Local.exe`, `Dashboard_Local.exe`, `Auto_CRM_Local.exe`, `openclaw`.
- Luu snapshot cau hinh OpenClaw hien tai.

Ket qua dat:

- Co tag Git baseline.
- Co ban backup SQLite, JSON, source.
- Neu loi co the quay lai ban cu.

### Giai doan 1: Tach cau hinh khoi code

Muc tieu: khong hardcode IP, mat khau, PIN, group Zalo, duong dan.

Viec can lam:

- Tao file cau hinh dung chung: `config.example.json`.
- Tao config that local, khong commit: `config.local.json`.
- Chuyen cac gia tri sau ra config/env:
  - IP server `192.168.1.104`
  - NAS `192.168.1.188`
  - OpenClaw path
  - Zalo group target
  - KiotViet username/password
  - Dashboard admin PIN
  - duong dan DB/log/profile
- Giu fallback tuong thich de app cu khong hong ngay.

Ket qua dat:

- Source khong con mat khau that.
- May chay that chi can config local.
- Repo an toan hon khi push GitHub.

### Giai doan 2: Chuan hoa log va canh bao loi

Muc tieu: loi khong con bi nuot im lang.

Viec can lam:

- Thay cac `except: pass` quan trong bang log ro rang.
- Tao ham log chuan dung chung:
  - thoi gian
  - module
  - cap do: INFO/WARN/ERROR
  - noi dung loi
- Log rieng cho:
  - client may in/cat
  - server
  - dashboard
  - Auto CRM
  - OpenClaw send
  - KiotViet Selenium
- Khi loi nghiem trong, gui canh bao noi bo qua Zalo neu OpenClaw con hoat dong.

Ket qua dat:

- Khi mat log may, mat server, loi KiotViet, loi Zalo, deu biet ly do.
- De debug hon thay vi chi thay app im.

### Giai doan 3: Health check va giam sat

Muc tieu: biet phan nao dang song/chet.

Them endpoint moi:

```text
GET /api/health
GET /api/status
```

`/api/health` tra don gian:

```json
{
  "ok": true,
  "server": "running",
  "db": "ok",
  "time": "..."
}
```

`/api/status` tra chi tiet:

```json
{
  "server_version": "...",
  "last_client_ping": {
    "InBat": "...",
    "InDecal": "...",
    "CNC": "..."
  },
  "database": {
    "InBat": "ok",
    "InDecal": "ok",
    "CNC": "ok"
  },
  "openclaw": "unknown|ok|error",
  "auto_crm": "ok|error"
}
```

Viec can lam:

- Client ping dinh ky len server.
- Server luu `last_seen` tung may.
- Dashboard hien thi trang thai 3 may.
- Canh bao neu mot may khong ping qua 5 phut.
- Canh bao neu database khong ghi duoc.
- Canh bao neu OpenClaw gui tin that bai.

Ket qua dat:

- Mo dashboard la biet may nao dang mat ket noi.
- Khong can doi khach bao moi biet bot chet.

### Giai doan 4: Backup va an toan du lieu SQLite

Muc tieu: khong mat du lieu san xuat.

Viec can lam:

- Tao job backup tu dong moi ngay.
- Backup cac file:
  - `InBat.db`
  - `InDecal.db`
  - `CNC.db`
  - `versions_tracking.json`
  - `DanhBa_VIP.json`
  - `Map_ChatLieu.json`
  - `crm_memory.json`
- Luu backup vao:
  - local: `C:\QuanLyXuong\Backups`
  - NAS: `\\192.168.1.188\AI\Backups\QuanLyXuong`
- Giu 30 ngay backup gan nhat.
- Truoc khi auto update, tu backup nhanh.

Ket qua dat:

- Co the phuc hoi DB khi loi.
- Auto update khong con nguy hiem nhu hien tai.

### Giai doan 5: Lam chac luong doc log may in/cat

Muc tieu: doc log on dinh hon, phat hien duoc khi log doi format.

Viec can lam:

- Tach reader cho tung may:
  - `InBatLogReader`
  - `InDecalLogReader`
  - `CncLogReader`
- Moi reader phai log ro:
  - file log co ton tai khong
  - lan cuoi doc thanh cong
  - lan cuoi parse ra event
  - dong log khong parse duoc
- Them canh bao:
  - log file khong ton tai
  - log khong cap nhat qua lau trong gio lam
  - doc duoc log nhung khong parse duoc event
- Giu nguyen event output hien tai:
  - `EXPORT`
  - `RIP`
  - `PRINTING`
  - `CUTTING`
  - `DONE`
  - `DELETE`

Ket qua dat:

- Khong doi luong san xuat.
- Neu phan mem may in/cat doi log, he thong bao ngay.

### Giai doan 6: Chuan hoa auto update va deploy

Muc tieu: cap nhat app khong kill nham, khong restart day chuyen lung tung.

Viec can lam:

- Tao script deploy chuan:
  - build exe
  - copy len `Z:\Tools\dist`
  - ghi version
  - tao changelog
- Moi app chi tu thoat chinh no khi co ban moi.
- Khong de `Dashboard` hoac `Auto_CRM` kill `server_Local.exe` tuy tien.
- Them rollback:
  - giu lai ban `.exe` truoc do
  - neu ban moi loi, chay lai ban cu
- Version hoa ro:
  - client
  - server
  - dashboard
  - Auto CRM

Ket qua dat:

- Cap nhat co kiem soat.
- De biet may nao dang chay version nao.

### Giai doan 7: Nang cap Dashboard quan tri

Muc tieu: giam sua JSON tay.

Viec can lam:

- Them trang quan ly khach VIP:
  - ma khach
  - ten day du
  - KiotViet ID
  - Zalo ID/group
  - bat/tat gui Zalo
- Them trang quan ly chat lieu:
  - ten goi trong file
  - ma hang KiotViet
  - ten hien thi gui khach
- Validate du lieu truoc khi luu.
- Tao backup JSON truoc moi lan sua.
- Giu JSON hien tai lam nguon du lieu de khong phai migrate lon.

Ket qua dat:

- Chu xuong sua khach/chat lieu tren web.
- Giam loi do sua `DanhBa_VIP.json` va `Map_ChatLieu.json` bang tay.

### Giai doan 8: Lam chac Auto CRM/KiotViet

Muc tieu: bot tao bill it ket hon, loi ro hon.

Viec can lam:

- Tach Auto CRM thanh cac buoc co trang thai:
  - doc job
  - parse file
  - kiem tra VIP
  - kiem tra chat lieu
  - mo KiotViet
  - tao bill
  - chup bill
  - gui Zalo
  - cap nhat DB
- Moi job co retry count va loi cuoi cung.
- Neu KiotViet loi 3 lan, danh dau trang thai loi ro trong DB.
- Chup screenshot loi va link tren dashboard.
- Khong retry vo han ma khong hien thi tren dashboard.

Ket qua dat:

- Biet don nao tao bill loi, loi o buoc nao.
- Khong bi tinh trang bot am tham thu lai mai.

## Thay Doi Giao Dien/API Quan Trong

- Giu nguyen `POST /api/log_event` de client cu van chay.
- Them `GET /api/health` va `GET /api/status`.
- Them cau hinh local khong commit: `config.local.json` hoac bien moi truong.
- Giu nguyen SQLite hien tai, chi them cot/bang phu neu can:
  - `last_error`
  - `last_seen`
  - `job_attempts`
- Giu OpenClaw lam cong gui Zalo, khong chuyen sang Zalo OA/ZNS trong ke hoach nay.

## Test Va Nghiem Thu

Moi giai doan phai test toi thieu:

- Server khoi dong duoc port `8000`.
- Dashboard mo duoc port `5000`.
- Auto CRM mo duoc port `8001`.
- Client gui thu event `EXPORTED`, `RIP`, `PRINTING`, `DONE`.
- Database ghi dung trang thai.
- Dashboard realtime cap nhat.
- OpenClaw gui duoc tin test ra nhom noi bo.
- Backup tao file dung.
- App restart khong mat du lieu.
- Repo Git khong chua mat khau that.

Test tinh huong loi:

- Tat OpenClaw roi gui Zalo.
- Tat Auto CRM roi server goi `/wake_up`.
- Doi sai duong dan log may.
- SQLite bi khoa tam thoi.
- KiotViet login that bai.
- Client mat ket noi server.

## Gia Dinh Da Chot

- Uu tien so 1 la on dinh, khong viet lai toan bo.
- Trien khai tung giai doan nho, co rollback.
- Repo GitHub nen de private.
- Van dung OpenClaw de gui Zalo ca nhan/nhom.
- Chua chuyen sang Zalo OA/ZNS.
- Chua doi database lon, tiep tuc dung SQLite.
- Chua thay KiotViet bang API chinh thuc.
- Cong hien tai giu nguyen: server `8000`, dashboard `5000`, Auto CRM `8001`.
