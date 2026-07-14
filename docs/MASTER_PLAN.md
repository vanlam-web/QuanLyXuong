# Master Plan - Nang cap he thong xuong Van Lam

Muc tieu: dua he thong tu bo tool tu viet sang mot he thong van hanh chuan, co backup, rollback, staging, audit log va lo trinh noi QCVL, nhung khong lam gian doan xuong.

## 1. Nguyen tac bat buoc

1. Production dang nuoi xuong khong duoc sua truc tiep neu khong co duong quay lai.
2. Moi thay doi phai co rollback.
3. Moi cau hinh nhay cam phai nam ngoai Git.
4. QCVL ban dau chi nghe/nhan ban sao du lieu, khong dieu khien nguoc may xuong.
5. Khong viet lai toan bo mot lan.
6. Uu tien do on dinh hon tinh nang moi.
7. AI lam viec ky thuat, chu xuong xac nhan nghiep vu.

## 2. He thong hien tai

```text
May san xuat
  -> QuanLyXuong.exe
  -> server.exe
  -> SQLite C:\QuanLyXuong\Data
  -> Dashboard.exe
  -> Auto_CRM.exe
  -> OpenClaw
  -> Zalo / KiotViet
```

Thanh phan:

| Thanh phan | Vai tro | Ranh gioi an toan |
|---|---|---|
| `QuanLyXuong.py` | Doc log/file may san xuat, gui event | Khong doi loop may khi chua test |
| `server.py` | Nhan event, ghi SQLite, broadcast | Phai giu `/api/log_event` on dinh |
| `Dashboard.py` | Man hinh tien do xuong | Co the thay sau bang QCVL dashboard |
| `Auto_CRM.py` | Tao bill KiotViet, gui Zalo | RUi ro cao vi dung Selenium |
| `KhoiDongBot.bat` | Khoi dong client tu NAS | Chua credential that, khong commit |

## 3. Kien truc dich

```text
May san xuat
  -> Agent/Bridge an toan
  -> QCVL API
  -> PostgreSQL
  -> POS production queue
  -> Dashboard san xuat
```

Trong giai doan chuyen doi:

```text
May san xuat
  -> He cu van chay
  -> Bridge doc SQLite cu
  -> QCVL nhan ban sao
```

## 4. Moi truong van hanh

### Production

Ban dang dung hang ngay cho xuong.

```text
Z:\Tools\dist
C:\QuanLyXuong\Data
C:\QuanLyXuong\*.txt log
```

Quy tac: chi publish vao production khi co backup va rollback.

### Staging

Ban thu nghiem cho AI nang cap.

```text
Z:\Tools\dist-new
Database copy
Zalo target test
QCVL test
```

Quy tac: duoc phep sai, nhung khong dung DB/Zalo/KiotViet that neu chua xac nhan.

### Releases

Noi luu ban cu va ban moi.

```text
Z:\Tools\releases
```

Duoc quan ly boi:

```text
Z:\Tools\scripts\Publish-Release.ps1
Z:\Tools\scripts\Rollback-Release.ps1
```

## 5. Lo trinh nang cap

### Phase 0 - Dong bang va bao ve

Muc tieu: biet ban nao dang chay, co the quay lai ban cu.

Viec can co:

- Release/rollback script.
- Backup DB script.
- Tai lieu rollback.
- Khong commit secret.
- Backup DB truoc deploy.
- Ghi ro version ban dang chay.

Trang thai: da bat dau.

### Phase 1 - Chuan hoa cau hinh va log

Muc tieu: bot hardcode, loi nhin duoc.

Viec can lam:

- Dua IP, port, path, PIN, Zalo target, Kiot credential ra env/config.
- Them `config.py` dung chung.
- Ghi log co level: INFO/WARN/ERROR.
- Giam `except: pass`, thay bang log loi.
- Them health check cho server, Auto CRM, OpenClaw, DB, NAS.

Lenh healthcheck:

```powershell
powershell -ExecutionPolicy Bypass -File Z:\Tools\scripts\Test-QuanLyXuongHealth.ps1
```

Runbook cau hinh: [CONFIG_RUNBOOK.md](./CONFIG_RUNBOOK.md).

### Phase 2 - Bridge sang QCVL

Muc tieu: QCVL doc duoc du lieu may san xuat ma khong anh huong he cu.

Viec can lam:

- `bridge_qcvl.py` dry-run.
- QCVL them `POST /api/v1/production-events`.
- QCVL them bang `production_machines`, `production_events`, `production_queue_items`.
- Doi POS production queue tu mock sang DB.
- Bridge gui that khi endpoint san sang.

Trang thai: bridge dry-run da tao.

### Phase 3 - QCVL production queue that

Muc tieu: POS thay file may san xuat that, them vao nhap duoc.

Viec can lam:

- Parse ten file thanh customer/product/dimension/quantity.
- Match customer QCVL.
- Match product/material QCVL.
- Hien item parse loi de thao tac tay.
- Nut `add-to-draft` tao dong POS dung gia, m2, so luong.

### Phase 4 - Dashboard moi

Muc tieu: QCVL thay Dashboard cu dan dan.

Viec can lam:

- Man hinh trang thai may.
- File dang chay, da xong, loi/huy.
- Timeline tung file.
- Thong ke ngay/ca.
- Canh bao may khong ping.
- Doi soat POS bill voi file may.

### Phase 5 - Bo Auto_CRM/KiotViet/Zalo auto khoi luong chinh

Muc tieu: V2 khong tu tao bill KiotViet va khong tu gui Zalo cho khach nua. QCVL POS la noi nhan vien kiem tra file may va tao bill.

Viec can lam:

- Tach parser file thanh module test duoc.
- Giu mapping khach/vat lieu de phuc vu QCVL production queue.
- Tat Auto_CRM khoi luong production khi QCVL POS san sang.
- Khong dung Selenium/KiotViet trong luong V2.
- Khong gui tin nhan khach tu dong trong luong V2.
- Neu sau nay can gui tin, chi lam co che ho tro nhan vien kiem tra va bam gui.

### Phase 6 - Agent moi cho may san xuat

Muc tieu: thay `QuanLyXuong.py` tung may, khong thay mot lan.

Thu tu:

1. May phu/test.
2. CNC.
3. InDecal.
4. InBat.

Moi may phai co rollback ve client cu.

## 6. Vai tro AI va chu xuong

AI lam:

- Doc code.
- Tao script.
- Viet test.
- Viet docs.
- Refactor tung phan.
- Chay kiem tra.
- Bao rui ro.
- Tao release/rollback.

Chu xuong lam:

- Xac nhan nghiep vu dung/sai.
- Chon thoi diem deploy.
- Bao loi thuc te ngoai xuong.
- Khong can code.

Cong cu cho chu xuong:

```text
Z:\Tools\KhoiDongAdminConsole.bat
```

Menu nay gom healthcheck, backup, bridge dry-run, publish va rollback.

Quality gate:

```powershell
powershell -ExecutionPolicy Bypass -File Z:\Tools\scripts\Test-QuanLyXuongCode.ps1
```

Changelog:

```text
Z:\Tools\CHANGELOG.md
```

## 7. Checklist truoc deploy

- Da backup `C:\QuanLyXuong\Data`.
- Lenh backup khuyen nghi:

```powershell
powershell -ExecutionPolicy Bypass -File Z:\Tools\scripts\Backup-QuanLyXuongData.ps1
```

Backup tu dong hang ngay:

```powershell
powershell -ExecutionPolicy Bypass -File Z:\Tools\scripts\Install-QuanLyXuongBackupTask.ps1
```

- Da backup `Z:\Tools\dist` vao `releases\rollback-*`.
- Ban moi nam o `dist-new`.
- Khong co secret trong Git.
- Build khong loi.
- Bridge/QCVL neu co chi dry-run hoac da test staging.
- Co lenh rollback san.

Lenh preflight gom quality gate, healthcheck, backup va support bundle:

```powershell
powershell -ExecutionPolicy Bypass -File Z:\Tools\scripts\Invoke-PreDeployCheck.ps1
```

## 8. Checklist khi loi

1. Khong sua tiep tren production.
2. Chay rollback:

```powershell
powershell -ExecutionPolicy Bypass -File Z:\Tools\scripts\Rollback-Release.ps1
```

3. Khoi dong lai service/bat neu can.
4. Ghi lai loi vao docs hoac log.
5. Sua o staging, khong sua nong neu khong bat buoc.

Neu can khoi phuc DB tu backup:

```powershell
powershell -ExecutionPolicy Bypass -File Z:\Tools\scripts\Restore-QuanLyXuongData.ps1 -BackupPath <backup-folder>
```

## 9. Viec uu tien ngay

1. Chuan hoa V2 trong `Z:\Tools` truoc.
2. Giu QCVL chua sua cho den khi V2 va contract on dinh.
3. Hoan thien bridge dry-run va doc payload de chot format.
4. Dam bao Auto_CRM/KiotViet/Zalo auto khong con la luong chinh cua V2.
5. Sau do moi tao QCVL endpoint production-events.
6. Sau nua moi doi QCVL production queue tu mock sang DB.

## 10. Dinh nghia thanh cong

He thong duoc coi la chuan hon khi:

- Co the deploy ban moi va rollback trong vai phut.
- Loi co log de doc, khong mat hut.
- Config khong nam trong code.
- QCVL nhan du lieu may that ma he cu van chay.
- POS tao nhap tu file may that.
- V2 khong tu tao bill KiotViet va khong tu gui tin khach.
- Co backup DB truoc moi release.
- Chu xuong khong can code van van hanh duoc.

Quyet dinh dinh huong V2 da ghi tai [V2_DIRECTION_DECISIONS.md](./V2_DIRECTION_DECISIONS.md).
