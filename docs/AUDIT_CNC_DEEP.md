# Audit CNC deep - 2026-07-11

## Pham vi

Muc tieu: nghien cuu toan dien may CNC dang mo de nang cap V2.

Nguon da doc:

- `\\CNC\CNC\CLIENT_CNC\file_history.csv`
- `\\CNC\CNC\CLIENT_CNC\system_log.txt`
- `\\CNC\CNC\CLIENT_CNC\CLIENT_CNC.py`
- `\\CNC\Ncstudio V5.5.60\NCSTUDIO.LOG`
- `\\CNC\CNC\CNC\2026-07-11`
- `C:\QuanLyXuong\Data\CNC.db`
- `C:\QuanLyXuong\Data\cnc_legacy_bridge_state.json`
- `Z:\Tools\app\cnc_legacy_bridge.py`
- `Z:\Tools\app\tap_preview.py`
- `Z:\Tools\app\QuanLyXuong.py`

## Ket noi LAN

- Host `CNC` resolve: `192.168.1.33`.
- Ping OK nhung cham: khoang `1537ms`.
- NetBIOS:
  - `CNC <00>`
  - `CNC <20>`
  - `WORKGROUP`
- Share doc duoc:
  - `\\CNC\CNC`
  - `\\CNC\Ncstudio V5.5.60`
  - `\\CNC\Users`

Nhan dinh:

- Co the doc log va file qua LAN.
- Mang toi Win7 CNC cham, nen bridge/dashboard can timeout ngan va khong block UI.

## Kien truc hien tai

Hien CNC V2 chua chay native tren may CNC.

Luong dang dung:

```text
May CNC Win7
  -> CLIENT_CNC.py V1 ghi file_history.csv + system_log.txt
  -> Server may chinh chay cnc_legacy_bridge.exe
  -> Bridge doc \\CNC\CNC\CLIENT_CNC\file_history.csv
  -> Bridge gui /api/ping + /api/log_event vao Server V2
  -> Dashboard doc CNC.db
```

Bang chung:

- `CNC.db/app_info.version = V2.0.2_CNC_LEGACY_BRIDGE`
- `CNC.db/app_info.hostname = CNC qua bridge V1`
- `cnc_legacy_bridge_state.json.host = DESKTOP-1OSJVQE`
- Bridge default history: `\\CNC\CNC\CLIENT_CNC\file_history.csv`

## Trang thai may CNC luc audit

- `NCSTUDIO.LOG` last write: `2026-07-11 17:45:51`
- `file_history.csv` last write: `2026-07-11 17:44:33`
- `system_log.txt` last write: `2026-07-11 17:47:26`
- `state_CNC.json` last write: sau do van cap nhat.
- Dong cuoi quan trong trong `NCSTUDIO.LOG`: `Nc Studio exits` luc `2026-07-11 17:45:51`.

Nhan dinh:

- May tinh CNC/share dang mo.
- Client V1 co the van loop.
- Phan mem NcStudio da thoat luc `17:45:51`, nen dashboard "CNC dang mo" hien tai chi co nghia la bridge con ping duoc, khong co nghia la NcStudio dang chay/cat.

## Du lieu ngay 2026-07-11 trong V2

Trong `CNC.db`:

- DONE:
  - `xxd_120x25_f5_mui15.tap`
  - `hy.tap`
  - `huong_120x240.tap`
- EXPORTED:
  - `xxd_micatrong.tap`
  - `xxxd_micatrong2.tap`
- REMOVED/source delete:
  - `xd_120x17.tap`
  - `xd_120x25_f5_mui15.tap`
- Expected stop/template:
  - `5p ngang chuan dut vip1.tap` 2 lan

Dashboard hien tai:

- `RUNNING = 0`
- `ATTENTION = 0` cho CNC
- `5p ngang chuan dut vip1.tap` khong tinh la loi hong tren UI.

## Van de 1: Online CNC dang sai nghia

Bridge ping moi 10 giay nen `last_ping` moi, dashboard hien `DANG MO`.

Nhung:

- Bridge chay tren server, khong phai may CNC.
- `NCSTUDIO.LOG` dung o `17:45:51`.
- Dong cuoi la `Nc Studio exits`.

Can tach 3 trang thai:

1. `May CNC bat/share vao duoc`
2. `Bridge tren server dang doc CSV`
3. `NcStudio dang chay va log con moi`

De xuat:

- Bridge gui them app_info:
  - `cnc_host = CNC / 192.168.1.33`
  - `cnc_share_online = 1/0`
  - `cnc_history_mtime`
  - `cnc_ncstudio_log_mtime`
  - `cnc_ncstudio_last_line`
  - `cnc_ncstudio_state = RUNNING / EXITED / STALE / UNKNOWN`
- Dashboard hien rieng:
  - `Bridge V2: dang mo`
  - `May CNC: thay qua LAN`
  - `NcStudio: da thoat luc ...`

## Van de 2: Dang co 2 bridge CNC tren server

Tien trinh thay duoc:

- `cnc_legacy_bridge.exe --loop --interval 10`
- `cnc_legacy_bridge.exe --loop --interval 10`

Tac hai:

- Ping trung.
- Doc CSV trung.
- Idempotency trong server chan phan lon event trung, nhung log nhieu va kho debug.

De xuat:

- Startup script phai stop bridge cu truoc khi start bridge moi, ke ca khi restart rieng Dashboard.
- Bridge nen co lock file de chi cho 1 instance.

## Van de 3: DELETE sau DONE la nhieu

Mau trong CSV:

```text
EXPORT -> CUTTING -> DONE -> DELETE
```

Nguyen nhan hop ly:

- Sau DONE, V1 move file vao `New Folder`.
- Scanner thay file goc bien mat nen log DELETE.

Hien server V2 khong ha DONE xuong DELETED neu DELETE den sau DONE, nen du lieu chinh khong bi hong nhieu.

Rui ro:

- Log va history bi nhieu nhieu.
- Neu hash/path khac nhau, co the tao dong DELETED rieng.

De xuat:

- Bridge/server can nhan dien `MOVE_AFTER_DONE`, khong gui DELETE thuong.
- Neu DELETE den trong 1-60 giay sau DONE cung core file, ghi audit la `MOVED_AFTER_DONE`.

## Van de 4: `5p ngang chuan dut vip1.tap` bi xem nhu huy cat

Bang chung:

- File `\\CNC\CNC\CNC\Luu\5p ngang chuan dut vip1.tap` co 195 dong.
- NcStudio log:
  - `Initiate a machining task (Advanced): ... from <first line> to L194`
  - sau do `Interrupted/Stop`.

Nhan dinh:

- May cat template tu `L1` den `L194`.
- File co 195 dong, dong 195 la `M30`.
- Dung o `L194` gan nhu dung diem ket thuc chuong trinh.
- Day la "cat ngang chuan dut", thuong la thao tac dung chu dong, khong phai loi hong.

De xuat:

- Parse dong Advanced:
  - start line
  - end line `L194`
  - tong so dong file
- Neu end_line >= total_lines - 1 va filename/template thuoc `Luu/ngang chuan dut`, classify `EXPECTED_STOP`.
- Khong tinh vao ti le hong.

## Van de 5: Chua tinh duoc % hong that cho CNC

Hien tai `DELETE` khi dang CUTTING khong co percent.

Nguon co the tinh:

- NcStudio Advanced line co `to Lxxx`.
- TAP file dem tong so dong cat.
- Log co thoi gian start/cancel.
- Co the lay duration mau tu cac job DONE cung kich thuoc.

De xuat thu tu uu tien:

1. Neu Advanced line co L-end: `progress = L_end / total_lines`.
2. Neu cancel binh thuong: dung thoi gian chay / duration mau gan nhat cung core/kich thuoc.
3. Neu file trong `Luu` va ten co `ngang chuan dut`: mark `EXPECTED_STOP`.
4. Neu khong du du lieu: `UNKNOWN`, hien can xem lai.

## Van de 6: Preview TAP da co, nhung path DB la local D:\

DB luu path dang `D:\CNC\...`, server khong co file local do.

Code preview dung map UNC:

```text
D:\CNC\2026-07-11\abc.tap
-> \\CNC\CNC\CNC\2026-07-11\abc.tap
-> \\CNC\CNC\CNC\2026-07-11\New Folder\abc.tap
-> \\CNC\CNC\CNC\Luu\abc.tap
```

Hien ngay 2026-07-11:

- Thumbnail CNC da co cho cac item chinh.
- `has_thumbnail = true`.

De xuat:

- Luu them `source_unc_path` vao app_info/history hoac payload debug.
- Khi preview fail, Dashboard hien ro "khong thay UNC path nao".

## Van de 7: File goc va New Folder co the trung

Ngay 2026-07-11 thay:

- `\\CNC\CNC\CNC\2026-07-11\huong_120x240.tap`
- `\\CNC\CNC\CNC\2026-07-11\New Folder\huong_120x240.tap`

System log co:

- `Khong the di chuyen: [WinError 32] ... huong_120x240.tap`

Nhan dinh:

- Move sau DONE co luc bi lock.
- Co the con file o goc, dong thoi da co file New Folder.

De xuat:

- Move sau DONE phai retry theo condition:
  - file unlock
  - target chua ton tai hoac cung hash/size
  - neu target da co cung size thi mark moved OK va xoa/bo qua source sau.

## Huong nang cap hop ly

### Phase 1 - Khong dung may CNC

Lam tren server/bridge:

1. Chi cho 1 `cnc_legacy_bridge.exe` chay.
2. Bridge doc them `NCSTUDIO.LOG` qua share.
3. Bridge gui health NcStudio vao server app_info.
4. Dashboard tach `Bridge online` va `NcStudio online`.
5. Dashboard hien "NcStudio da thoat luc ...".
6. Add audit/attention neu:
   - file_history moi nhat qua cu.
   - NCSTUDIO.LOG moi nhat qua cu.
   - last line la `Nc Studio exits`.

### Phase 2 - Chuan hoa logic CNC

1. Parse NcStudio direct thay vi chi doc CSV V1.
2. Classify:
   - `CUTTING`
   - `DONE`
   - `CANCEL`
   - `EXPECTED_STOP`
   - `SIMULATION`
   - `MOVE_AFTER_DONE`
3. Tinh percent:
   - Advanced L-end / total lines.
   - Duration estimate fallback.
4. Khong tinh template `ngang chuan dut` vao loi/hong.

### Phase 3 - Native V2 tren Win7 CNC

May CNC la Win7 32-bit, nen can rieng:

1. Build client Python 3.6/3.8 32-bit.
2. Khong dung package moi nang neu khong can.
3. Ghi outbox local tren may CNC.
4. Gui truc tiep server V2 khi LAN OK.
5. Neu LAN mat, queue lai.
6. Van giu bridge server lam fallback trong 1-2 tuan.

## Ket luan

CNC khong nen nang cap bang cach bo bridge ngay.

Huong an toan:

1. Giu V1 + bridge dang chay.
2. Nang bridge truoc de doc health/log tot hon.
3. Sua dashboard de bao dung trang thai NcStudio.
4. Sau khi on dinh moi build client native Win7 32-bit.

## Audit bo sung khi may CNC dang bat - 2026-07-11 19:50

Nguon kiem tra them:

- Ping `CNC`: OK, `192.168.1.33`, thoi gian phan hoi khoang `397-411ms`.
- Share `\\CNC`: doc duoc `CNC`, `Ncstudio V5.5.60`, `Users`.
- Remote process `tasklist /S CNC`: khong doc duoc, bao `RPC server is unavailable`.
- `\\CNC\CNC\CLIENT_CNC\state_CNC.json`: van cap nhat luc `2026-07-11 19:49:37`.
- `\\CNC\CNC\CLIENT_CNC\file_history.csv`: moi nhat `2026-07-11 17:44:33`.
- `\\CNC\CNC\CLIENT_CNC\system_log.txt`: moi nhat `2026-07-11 17:47:26`.
- `\\CNC\Ncstudio V5.5.60\NCSTUDIO.LOG`: moi nhat `2026-07-11 17:45:51`.
- `C:\QuanLyXuong\Data\CNC.db`: CNC last ping moi do bridge, latest machine event dung o `2026-07-11 17:44:33`.

Nhan dinh ngay luc may CNC duoc bao la dang mo:

- May tinh CNC/share dang bat va truy cap duoc qua LAN.
- Client/loop V1 tren may CNC co dau hieu con song vi `state_CNC.json` van cap nhat.
- NcStudio khong co log moi sau `17:45:51`.
- Dong cuoi `NCSTUDIO.LOG`: `Nc Studio exits`.
- Vi vay trang thai dung phai la: `May CNC bat`, `bridge dang chay`, `NcStudio da thoat`, khong phai `CNC dang cat`.

## Doi chieu job CNC ngay 2026-07-11

Job da xong hop ly:

- `XXD_120X25_F5_MUI15.tap`
  - CUTTING: `15:31:52`
  - DONE: `15:42:44`
  - NcStudio co loi noi bo luc `15:31:59` nhung van `normal finished` luc `15:42:43`.
- `hy.tap`
  - CUTTING: `16:52:30`
  - DONE: `16:56:30`
  - NcStudio `normal finished` luc `16:56:28`.
- `huong_120x240.tap`
  - CUTTING: `17:33:34`
  - DONE: `17:44:33`
  - NcStudio `normal finished` luc `17:44:31`.

Job can hieu la file mau/dung dung diem:

- `5p ngang chuan dut vip1.tap`
  - Co 2 lan CUTTING -> DELETE.
  - Lan 2 trong NcStudio la `Initiate a machining task (Advanced) ... to L194`.
  - File mau trong `\\CNC\CNC\CNC\Luu`.
  - Day khong nen tinh la hong neu dung de cat ngang chuan/dut.

File dang o trang thai xuat, chua cat:

- `xxd_micatrong.tap`
- `xxxd_micatrong2.tap`

2 file nay dang nam o `\\CNC\CNC\CNC\2026-07-11`. Neu day la file luu de cat sau, dashboard can tach rieng khoi tien trinh dang san xuat hom nay.

## Loi move sau DONE

Phat hien:

- `huong_120x240.tap` ton tai dong thoi o:
  - `\\CNC\CNC\CNC\2026-07-11\huong_120x240.tap`
  - `\\CNC\CNC\CNC\2026-07-11\New Folder\huong_120x240.tap`
- Hai file cung size `345321`.
- `system_log.txt` bao:
  - `Khong the di chuyen: [WinError 32] The process cannot access the file because it is being used by another process`

Nhan dinh:

- May da cat xong.
- Move vao `New Folder` co luc bi lock.
- Scanner co the thay file goc con ton tai va gay nhieu trang thai phu.

Huong fix:

- Sau DONE, move file can retry lau hon va kiem tra theo condition:
  - neu target da ton tai cung size/hash thi coi nhu move OK.
  - neu source van bi lock thi ghi `MOVE_PENDING`, khong coi la dang chay.
  - dashboard hien "Da xong, file goc con bi lock" thay vi tao loi/huy.

## Runtime server dang trung tien trinh

Luc audit thay tren server:

- 2 `server_Local.exe`
- 2 `Dashboard_Local.exe`
- 2 `cnc_legacy_bridge.exe`

Tac hai:

- Bridge ping trung lam dashboard tuong CNC dang mo.
- Event co idempotency nen phan lon khong trung du lieu, nhung log va trang thai bi nhieu.
- Debug kho vi khong biet process nao dang phuc vu web/API.

Huong fix:

- `Start-V2Runtime.ps1` phai stop dung va day du truoc khi start.
- Them lock file trong `cnc_legacy_bridge.py`.
- Dashboard/server nen co single instance guard hoac health hien PID dang phuc vu.

## Diem yeu kien truc CNC hien tai

1. Bridge chi doc `file_history.csv`, khong doc truc tiep `NCSTUDIO.LOG`.
2. Dashboard dang dung `last_ping` cua bridge de bao `DANG MO`, sai nghia voi CNC.
3. V1 ghi DELETE cho nhieu tinh huong:
   - huy that khi dang cat.
   - file source bi xoa truoc khi cat.
   - move sau DONE.
   - file mau dung co chu dich.
4. Chua luu du lieu chi tiet tu NcStudio:
   - simulation/start/cancel/done.
   - Advanced start/end line.
   - last log time.
   - NcStudio exited/running/stale.
5. Chua tinh duoc % hong CNC tu log.
6. Win7 CNC khong cho remote process qua RPC, nen phai dua health vao file/log/heartbeat.

## Huong nang cap CNC de lam tiep

### Buoc 1 - Sua bridge tren server, it rui ro

- Chi cho 1 `cnc_legacy_bridge.exe` chay.
- Bridge doc them:
  - `\\CNC\Ncstudio V5.5.60\NCSTUDIO.LOG`
  - mtime log
  - dong cuoi quan trong
  - state: `NCSTUDIO_RUNNING`, `NCSTUDIO_EXITED`, `NCSTUDIO_STALE`, `UNKNOWN`
- Bridge gui them health vao `/api/ping`.
- Server luu cac key moi trong `app_info`.
- Dashboard tach 3 dong:
  - `May CNC LAN`
  - `Bridge V2`
  - `NcStudio`

### Buoc 2 - Chuan hoa logic job CNC

- Phan loai rieng:
  - `EXPORT`
  - `SIMULATION`
  - `CUTTING`
  - `DONE`
  - `CANCEL_BY_OPERATOR`
  - `EXPECTED_STOP`
  - `MOVE_AFTER_DONE`
  - `SOURCE_DELETE`
- `DELETE` khong duoc mac dinh la loi/hong.
- File mau trong `Luu` + ten `ngang chuan dut` phai vao `EXPECTED_STOP`.
- Neu DONE roi DELETE cung core trong 60 giay thi vao `MOVE_AFTER_DONE`.

### Buoc 3 - Tinh % hong gan dung

Thu tu uu tien:

1. Neu log Advanced co `to Lxxx`: tinh `xxx / tong so dong TAP`.
2. Neu cancel khong co line: lay thoi gian da cat / thoi gian DONE trung kich thuoc gan nhat.
3. Neu file mau `ngang chuan dut`: `EXPECTED_STOP`, khong tinh hong.
4. Neu khong du du lieu: hien `Chua tinh duoc %`, khong dua vao ty le hong.

### Buoc 4 - Native V2 cho Win7 CNC

- Lam sau khi bridge on dinh.
- Build Python 32-bit rieng cho Win7.
- Client native doc `NCSTUDIO.LOG` truc tiep, ghi outbox local.
- Mat LAN thi queue, co LAN thi gui server.
- Giu bridge server lam fallback trong 1-2 tuan.

## Ket luan bo sung

Hien CNC khong nen xem la "dang mo day du" neu chi co bridge ping.

Trang thai dung luc audit:

```text
May CNC: bat, share vao duoc
Client V1: co dau hieu con loop
Bridge V2: dang chay, nhung dang bi trung 2 process
NcStudio: da thoat luc 2026-07-11 17:45:51
Job CNC moi nhat: huong_120x240.tap da DONE luc 17:44:33
```

Viec can lam tiep dau tien: nang bridge + dashboard de bao dung trang thai CNC/NcStudio, dong thoi chan duplicate bridge.
