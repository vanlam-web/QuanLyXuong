# Audit file sinh ra tu may san xuat - 2026-07-13

## Muc tieu

Doc truc tiep cac file do may in/cat sinh ra, de biet co the lay them thong tin nao cho dashboard va server.

## Nguon da doc

- InDecal:
  - `\\InDecal\D\2026-07-13\New Folder`
  - `\\InDecal\Log\Log[2026_07_13].txt`
- InBat:
  - `\\InBat\D\2026-07-13\New Folder`
  - `\\InBat\PrintMon USB3.0 510 508GS 1020\PrintFile.ini`
- CNC:
  - `\\CNC\CNC\CNC\2026-07-13\New Folder`
  - `\\CNC\CNC\CNC\Luu`
  - `\\CNC\CNC\CLIENT_CNC\file_history.csv`
  - `\\CNC\CNC\CLIENT_CNC\system_log.txt`
  - `\\CNC\Ncstudio V5.5.60\NCSTUDIO.LOG`

## InDecal

File trong ngay 2026-07-13:

- 9 file `.prn`.
- 9 file `.tif`.
- 12 file `.bmp`.

Phat hien quan trong:

- Moi file `.prn` sau RIP co file preview `.prn.bmp`.
- Vi du:
  - `9~balong_80x10.prn`
  - `9~balong_80x10.prn.bmp`
  - `balong_80x10.tif`
- `.prn.bmp` doc duoc bang PIL:
  - `9~balong_80x10.prn.bmp`: BMP, 710x88, RGB.
  - `8.prn.bmp` va `8~loi_121x23.prn.bmp`: cung kich thuoc, cung dung de xac nhan rename.
- `.tif` co kich thuoc va DPI that:
  - `balong_80x10.tif`: 4725x592 px, 150 DPI, CMYK.

Huong nang cap:

1. Uu tien dung `.prn.bmp` lam preview InDecal, vi day la preview do RIP sinh ra.
2. Khi rename `8.prn -> 8~loi_121x23.prn`, copy/doi ten ca `8.prn.bmp -> 8~loi_121x23.prn.bmp`.
3. Neu thumbnail server thieu, may tram co the tim `.prn.bmp` theo:
   - ten `.prn` hien tai.
   - ten `.prn` truoc rename.
   - phan sau dau `~`.
4. Dung kich thuoc TIFF + DPI de tinh m2 that khi ten file khong chuan.
5. Log InDecal decode bang `gb18030`, co cac moc:
   - `打印完成` = in hoan thanh.
   - `打印任务结束` = ket thuc task.
   - `nCurPassIndex` = chi so pass dang in.
6. Co the nghien cuu them `nCurPassIndex` de uoc tinh tien do in, nhung can gan voi job hien tai vi log khong luon ghi ten file trong tung dong pass.

## InBat

File trong ngay 2026-07-13:

- 4 file `.tif`.
- 1 file `.prt`.

Phat hien quan trong:

- `PrintFile.ini` hien chua path file dang/gan nhat:
  - `D:\2026-07-13\New Folder\ut_160x230.prt`
- Phan dau file la ASCII path, phan sau la byte trang thai/bo dem.
- `.tif` co kich thuoc/DPI that:
  - `ut_160x230.tif`: 9450x13584 px, 150 DPI, CMYK, suy ra gan 160x230 cm.
  - `DAOTUAN_200X120.tif`: 9449x5669 px, 120 DPI, CMYK, suy ra gan 200x120 cm.

Huong nang cap:

1. Dung TIFF dimensions + DPI de tinh m2 that thay vi chi parse ten file.
2. Luu `image_width_px`, `image_height_px`, `dpi_x`, `dpi_y`, `width_cm`, `height_cm`, `area_m2`.
3. Doc `PrintFile.ini` lien tuc trong luc may dang in de xem byte trang thai co thay doi theo tien do hay khong.
4. Neu byte trang thai thay doi co quy luat, co the lay `% dang in` that cho InBat.

## CNC

File va log tim thay:

- File `.tap` ngay 2026-07-13 nam o `\\CNC\CNC\CNC\2026-07-13\New Folder`.
- CNC co file client cu:
  - `\\CNC\CNC\CLIENT_CNC\file_history.csv`
  - `\\CNC\CNC\CLIENT_CNC\system_log.txt`
- Log NcStudio decode bang `gb18030`.

Phat hien tu `.tap`:

- `f8_120x67.tap`:
  - 575544 bytes.
  - 32195 dong.
  - X: -0.999 -> 1198.496.
  - Y: -0.997 -> 670.206.
  - Z: 0 -> 20.
  - Feed: 780 -> 2520.
- `al.tap`:
  - 294321 bytes.
  - 16113 dong.
  - X: -0.75 -> 1199.25.
  - Y: 0 -> 1510.75.
  - Z: 0 -> 15.
  - Feed: 600 -> 1800.
- `5p ngang chuan dut vip1.tap` trong `Luu`:
  - 195 dong.
  - X: 0 -> 1230.
  - Y: 0 -> 2392.
  - Day la file mau/cat ngan, khong nen mac dinh tinh la loi neu tho dung dung diem cat du kien.

Phat hien tu log:

- NcStudio log co:
  - `Initiate a simulation` = chay mo phong.
  - `Initiate a machining task` = bat dau cat that.
  - `文件'...'正常完毕` = file hoan thanh binh thuong.
  - `中断终止` = dung/huy giua chung.
  - `Initiate a machining task (Advanced) ... to L194` = cat den dong chi dinh.
- `file_history.csv` co timeline structured, de doi chieu:
  - EXPORT.
  - CUTTING.
  - DONE.
  - DELETE sau DONE.
  - WRONG_DAY.

Huong nang cap:

1. Parse `.tap` de luu metadata:
   - line_count.
   - bounds X/Y/Z.
   - feed_min/feed_max.
   - tool/spindle neu co.
   - width_mm, height_mm.
2. Dung `.tap` de tao preview CNC va hien kich thuoc that, khong chi theo ten file.
3. Khi CNC bi huy:
   - neu log co `to Lxxx`, tinh progress = `xxx / line_count`.
   - neu khong co line, dung thoi gian chay / thoi gian DONE trung binh.
4. DELETE sau DONE trong `file_history.csv` thuong la don dep/move file, khong tinh loi.
5. Dung `file_history.csv` lam nguon doi chieu khi bridge V2 mat/moi restart.

## Uu tien code tiep theo

1. InDecal preview:
   - tim va gui `.prn.bmp` ve server.
   - copy/doi ten `.prn.bmp` cung luc rename `.prn`.
2. Tinh kich thuoc that:
   - InDecal/InBat lay TIFF dimensions + DPI.
   - CNC lay bounds tu TAP.
3. CNC progress:
   - parse TAP line_count.
   - parse NcStudio `Advanced ... to Lxxx`.
4. Diagnostic UI:
   - them tab/phan chi tiet "Nguon file may" de xem file goc, file preview, kich thuoc, log lien quan.

## Da lam 2026-07-13

1. Them `machine_file_meta.py` de doc metadata file may dung chung cho client/server/backfill.
2. Server `V7.6.3_SERVER_META_BACKFILL` tu resolve duong dan `D:\...` sang UNC:
   - InDecal: `\\InDecal\D\...`
   - InBat: `\\InBat\D\...`
   - CNC: `\\CNC\CNC\CNC\...`
3. Client `V2.0.5_ORIGINAL_IMAGE_META` gui metadata moi.
4. Backfill DB cu bang `scripts/backfill_machine_meta.py`.
5. Nguyen tac da chot:
   - `.prn.bmp` chi dung lam preview nhanh.
   - m2/kich thuoc InDecal/InBat phai lay tu `.tif/.jpg` goc neu co.
   - CNC lay kich thuoc/m2 tu bounds trong `.tap`.

Ket qua backfill tren DB live:

- InDecal: cap nhat 102 dong lan dau, sau do sua them 97 dong da tinh sai tu `.prn.bmp`.
- InBat: cap nhat duoc 1 dong con file goc tren share; nhieu dong cu thieu file goc nen khong backfill duoc.
- CNC: cap nhat 78 dong tu TAP.

Can lam tiep:

1. InBat: khi may in mo va sinh job moi, theo doi them `PrintFile.ini`, `Printed.dat`, thu muc `Preview/spool` de tim cach lay tien do hoac lich su in tot hon.
2. CNC: parse `NCSTUDIO.LOG` de tinh % huy theo `to Lxxx / line_count`.
3. UI: them man "Nguon file may" neu can xem file goc, preview, metadata_source, preview_source, log lien quan.

## Kiem tra truc tiep khi may dang mo 2026-07-13 13:56-13:59

Trang thai live:

- InDecal dang mo, co du lieu moi.
- InBat dang mo nhung khong co job moi sau `2026-07-13 11:19:56`.
- CNC dang mo, co job `xxd_micatrong_ngay11_ngay12.tap` dang `CUTTING`.

InDecal:

- `ghep_105x220.tif` xuat luc `13:55:58`, m2 doc tu TIFF la `2.312`.
- RIP sinh `11.prn`, sau do file thuc te thanh `11~ghep_105x220.prn`.
- Audit ghi:
  - `RENAME_WAIT_STABLE` cho `11.prn`.
  - `RENAME_META_SELECTED` voi `ghep_105x220._tf`.
  - `RENAME_FAIL_GHOST`, nhung file thuc te van da duoc doi thanh `11~ghep_105x220.prn`.
- Mau nay lap lai voi `10.prn` / `10~tho_119x191.prn`.
- Ket luan: `RENAME_FAIL_GHOST` hien tai co the la loi gia do race/2 process/2 thread; khong nen tinh la loi that neu target `N~ten.prn` da ton tai sau do.

Log InDecal co tin hieu hoan thanh that:

- `13:47:39`: `启动任务：10~tho_119x191.prn`
- `13:47:40`: `pInitParam->nTotalPrintPass=342`
- `13:57:07`: `nCurPassIndex=341`
- `13:57:13`: `COMMAND_END`
- `13:57:14`: `打印结束`
- `13:57:17`: `打印动作完成`
- `13:57:17`: `打印完成`

Van de code:

- `worker_indecal_log` dang bat chuoi mojibake/cac keyword cu, nen bo sot `打印完成`.
- Vi bo sot `打印完成`, DB van giu `10~tho_119x191.prn` o `PRINTING` du thuc te da xong.

Nang cap phu hop:

1. Sua parser InDecal log:
   - doc bang `gb18030` hoac `gbk` co fallback.
   - bat dung keyword Chinese: `启动任务`, `pInitParam->nTotalPrintPass`, `nCurPassIndex`, `COMMAND_END`, `打印结束`, `打印动作完成`, `打印完成`, `Cancel`.
   - luu `total_pass`, `current_pass`, `% progress = current_pass / total_pass`.
   - khi gap `打印完成` hoac `打印动作完成`: gui `DONE`.
2. Sua rename audit:
   - neu `11.prn` mat nhung `11~ghep_105x220.prn` ton tai thi doi audit thanh `RENAME_OK_INFERRED` hoac `RENAME_RACE_OK`, khong tinh loi.
   - them `target_prn_path` khi suy luan duoc file dich.
3. Chong chay 2 instance client:
   - them lock file/mutex theo may, vi mau audit cho thay kha nang co 2 process cung rename mot file.
   - ping server kem `pid`, `start_time`, `instance_id` de dashboard canh bao "may dang chay 2 client".

## Trang thai sua code 2026-07-13 14:06

Da sua trong source `app/QuanLyXuong.py`, chua deploy live vi InDecal/CNC dang co job active.

Da them:

1. `parse_indecal_log_events(lines, state)`:
   - bat `启动任务`.
   - bat `pInitParam->nTotalPrintPass`.
   - bat `nCurPassIndex`.
   - bat `打印完成`, `打印动作完成`, `打印结束`.
   - gui `DONE` kem `current_pass`, `total_pass`, `progress_percent`.
2. `infer_existing_renamed_prn(path, meta_path)`:
   - neu source `11.prn` mat nhung target `11~ghep_105x220.prn` da ton tai thi ghi `RENAME_RACE_OK` thay vi `RENAME_FAIL_GHOST`.
3. `process_event(..., machine_meta_extra=None)`:
   - cho phep log parser gui them progress vao metadata.

Kiem chung:

- `python -m unittest Z:\Tools\tests\test_quanlyxuong_scan.py` -> 14 test OK.
- `python -m unittest discover -s Z:\Tools\tests` -> 89 test OK.
- `py_compile` OK.
- Build ban cho OK: `Z:\Tools\dist-audit\QuanLyXuong.exe`.

Chua lam de tranh loi may dang chay:

- Chua copy `Z:\Tools\dist-audit\QuanLyXuong.exe` sang `\\192.168.1.188\AI\Tools\dist\QuanLyXuong.exe`.
- Chua restart/kill client InDecal/InBat.
- Live van `V2.0.5_ORIGINAL_IMAGE_META` luc kiem tra, tuc may dang chay khong bi anh huong.

Khi may ranh:

1. Copy `Z:\Tools\dist-audit\QuanLyXuong.exe` sang `\\192.168.1.188\AI\Tools\dist\QuanLyXuong.exe`.
2. De auto-update hoac restart client.
3. Kiem tra `/api/v2_status` phai len `V2.0.6_INDECAL_LOG_FIX`.
4. Theo doi job InDecal tiep theo:
   - `PRINTING` phai co progress.
- Gap `打印完成` phai tu chuyen `DONE`.
- Rename race phai ghi `RENAME_RACE_OK`, khong tinh fail.

## Tiep tuc an toan 2026-07-13 14:12

May van dang chay:

- InDecal active 2.
- CNC active 1.
- Live client van `V2.0.5_ORIGINAL_IMAGE_META`, chua deploy ban moi.

Da lam them trong source:

1. Parser InDecal giu `max_pass` thay vi `current_pass` cuoi cung.
   - Ly do: log co dong reset `nCurPassIndex=0` sau khi da chay toi pass cuoi.
   - Vi du `10~tho_119x191.prn`: pass that `341/342 = 99.71%`, khong phai `0%`.
2. Parser lay `log_done_time` tu dong log dang `YYYY/MM/DD HH:MM:SS`.
3. Them script `scripts/reconcile_indecal_log.py`.
   - Dry-run mac dinh.
   - `--apply` moi ghi DB.
   - Dung de doi chieu log InDecal va chot cac dong `PRINTING` da co `打印完成`.

Da sua DB live an toan (khong restart may):

- Chot rieng dong moi nhat `10~tho_119x191.prn` tu `PRINTING` sang `DONE`.
- Gio DONE lay tu log that: `2026-07-13 13:57:17`.
- Progress: `99.71%`.
- InDecal active giam tu 3 xuong 2.

Kiem chung:

- `python -m unittest discover -s Z:\Tools\tests` -> 90 test OK.
- `py_compile` OK.
- `python Z:\Tools\scripts\reconcile_indecal_log.py` dry-run -> khong con dong can chot.
- Build ban cho OK: `Z:\Tools\dist-audit\QuanLyXuong.exe`.

Van chua deploy:

- Chua copy sang `\\192.168.1.188\AI\Tools\dist\QuanLyXuong.exe`.
- Cho InDecal/CNC het active hoac nguoi dung xac nhan co the update.

CNC:

- `NCSTUDIO.LOG` co du tin hieu:
  - `Initiate a machining task: ...`
  - `文件'...'正常完毕`
  - `Initiate a machining task (Advanced): ... to L194`
- `file_history.csv` hien `xxd_micatrong_ngay11_ngay12` bat dau `CUTTING` luc `13:50:33`, chua co `DONE` tai thoi diem kiem tra.
- Nang cap phu hop: parse `NCSTUDIO.LOG` truc tiep vao bridge de chot DONE/DELETE va tinh % huy theo `to Lxxx / line_count`.

InBat:

- `PrintFile.ini` van tro `D:\2026-07-13\New Folder\ut_160x230.prt`, khong doi sau `11:19:54`.
- Thu muc co cac TIFF lon va `ut_160x230.prt`; chi job nay backfill duoc metadata that.
- Nang cap phu hop: can theo doi thay doi raw bytes `PrintFile.ini` trong luc co job moi, tach status byte va thoi diem doi 1/2 de tinh PRINTING/DONE chac hon.

## Tiep tuc an toan 2026-07-13 14:17

May van dang chay:

- InDecal active 2.
- CNC active 1.
- Live chua deploy ban moi.

Da lam them cho CNC:

1. Them `app/cnc_log_parser.py`.
   - Parse `Initiate a machining task` thanh `CUTTING`.
   - Parse `文件'...'正常完毕` thanh `DONE`.
   - Parse `Initiate a machining task (Advanced) ... to Lxxx` de tinh progress theo `line_count`.
2. Them `scripts/reconcile_cnc_log.py`.
   - Dry-run mac dinh.
   - `--apply` moi ghi DB.
   - Dung de doi chieu `CNC.db` voi `\\CNC\Ncstudio V5.5.60\NCSTUDIO.LOG`.

Kiem chung:

- Them test `test_parse_cnc_log_detects_cutting_done_and_advanced_progress`.
- `python -m unittest discover -s Z:\Tools\tests` -> 91 test OK.
- `py_compile` OK.
- `python Z:\Tools\scripts\reconcile_cnc_log.py` dry-run -> khong co dong can chot.

Ket luan luc 14:17:

- CNC job `xxd_micatrong_ngay11_ngay12.tap` chua co `正常完毕` trong `NCSTUDIO.LOG`, nen van de `CUTTING`.
- Khong sua DB CNC khi chua co log DONE that.
## Tiep tuc an toan 2026-07-13 14:26

Trang thai live luc kiem tra:

- InBat active 0, live `V2.0.5_ORIGINAL_IMAGE_META`.
- InDecal active 1, live `V2.0.5_ORIGINAL_IMAGE_META`.
- CNC active 0, live `V2.0.3_CNC_TAP_META`.

Da lam trong source CNC bridge:

1. `app/cnc_legacy_bridge.py` len `V2.0.4_CNC_NCSTUDIO_LOG`.
2. Bridge van doc `file_history.csv` nhu cu.
3. Bridge doc them `\\CNC\Ncstudio V5.5.60\NCSTUDIO.LOG` bang encoding `gb18030`.
4. Dung offset rieng `ncstudio_offset`, khong lam lech offset cua `file_history.csv`.
5. Chuyen event tu `NCSTUDIO.LOG`:
   - `Initiate a machining task` -> `CUTTING`.
   - dong ket thuc binh thuong trong log CNC -> `DONE`.
   - dung `machine_meta` tu log neu co progress.
6. Neu `file_history.csv` mat nhung `NCSTUDIO.LOG` con, bridge van doc log duoc.

Kiem chung:

- Test do truoc khi sua:
  - `python -m unittest Z:\Tools\tests\test_cnc_legacy_bridge.py` -> fail dung cho: khong co event tu `NCSTUDIO.LOG`.
- Sau khi sua:
  - `python -m unittest Z:\Tools\tests\test_cnc_legacy_bridge.py` -> 4 test OK.
  - `python -m unittest discover -s Z:\Tools\tests` -> 92 test OK.
  - `py_compile` OK.
  - `Z:\Tools\dist-audit\cnc_legacy_bridge.exe --help` OK, co tham so `--ncstudio-log`, `--import-existing-ncstudio`.
- Build audit:
  - `Z:\Tools\dist-audit\cnc_legacy_bridge.exe`.
  - SHA256 `EEDF12637141A7F88261722966093E43FB2C9CC93FAA38E9D349B1F55CA76739`.

Chua deploy live:

- Chua copy `Z:\Tools\dist-audit\cnc_legacy_bridge.exe` sang dist live.
- Ly do: InDecal con active 1, tranh restart/update trong luc may dang chay.
- Khi tat ca active = 0, co the deploy rieng CNC bridge truoc, it rui ro hon deploy toan bo.

Huong tiep theo khi deploy CNC bridge:

1. Copy exe audit sang dist live cho `cnc_legacy_bridge.exe`.
2. Restart rieng service bridge CNC bang NSSM.
3. Kiem tra `/api/v2_status` CNC phai len `V2.0.4_CNC_NCSTUDIO_LOG`.
4. Theo doi job CNC tiep theo:
   - bat dau cat phai co `CUTTING`.
   - log ket thuc binh thuong phai chot `DONE`.
   - neu co `Advanced ... to Lxxx`, metadata co the dung de tinh % da chay.

## Tiep tuc an toan 2026-07-13 14:34

Phat hien:

- `/api/v2_status` live dang tinh `active` gom ca `EXPORTED/RIP`.
- Vi vay co the hien may "dang" trong khi thuc te chi co file cho xu ly.
- Vi du DB co `EXPORTED` nhung khong co `PRINTING/CUTTING`, nhung dashboard cu van lam nguoi dung tuong may dang chay.

Da sua trong source `app/Dashboard.py`:

1. `active` va `running` chi dem `PRINTING/CUTTING` trong ngay.
2. Them `queued_today` dem `EXPORTED/RIP` trong ngay.
3. Them `unfinished_today = running + queued_today`.
4. Sidebar may hien:
   - `Dang`: dang chay that.
   - `Cho`: file xuat/RIP dang cho.
   - `Xong`: DONE trong ngay.
   - `Ton cu`: file chua xong khac ngay.
5. Dong chi tiet "Hom nay chua xong / da xong" dung `unfinished_today / done_today`.

Kiem chung:

- Test do moi: `test_v2_status_separates_waiting_files_from_machine_running`.
- `python -m unittest Z:\Tools\tests\test_dashboard_v2_status.py` -> 33 test OK.
- `python -m unittest discover -s Z:\Tools\tests` -> 93 test OK.
- `py_compile` OK.
- Build audit `Z:\Tools\dist-audit\Dashboard.exe`.
- SHA256 `2219F0CF61728642DFA49DD0B94D85E1E1D48F9817B75978FEC33F8DF322C448`.

Ghi chu an toan:

- Khong deploy live vi live van co may active theo dashboard cu: InDecal 2, CNC 1 luc 14:34.
- Khi kiem exe, `Dashboard.exe --help` tu khoi dong Flask vi app khong co help flag; da dung dung 2 process audit theo dung path `Z:\Tools\dist-audit\Dashboard.exe`.
- Sau khi dung, chi con `C:\QuanLyXuong\Dashboard_Local.exe` live dang chay.

## Tiep tuc an toan 2026-07-13 14:39

Phat hien khi doc `NCSTUDIO.LOG` that:

- Job CNC hien tai `XXXD_MICATRONG2_Ngay11_Ngay12.tap` co nhieu dong simulation:
  - `Initiate a simulation`.
  - log ket thuc binh thuong luc 14:28:32, 14:29:58, 14:30:10.
- Dong cat that chi bat dau luc 14:31:20:
  - `Initiate a machining task`.
- Chua co log ket thuc cat that cho job nay.

Rui ro da chan:

- Parser cu co the bat DONE cua simulation thanh DONE that.
- Neu deploy nhu vay, bridge co nguy co chot DONE gia cho file CNC.

Da sua:

1. `app/cnc_log_parser.py` chi ghi `DONE` khi truoc do co `Initiate a machining task` cho dung path.
2. `Initiate a simulation` khong tao `CUTTING`, va DONE sau simulation bi bo qua.
3. Parser co `state["current_cut_path"]` de bridge khong mat context neu `CUTTING` va `DONE` nam o 2 lan doc khac nhau.
4. `app/cnc_legacy_bridge.py` truyen state vao parser CNC log.

Kiem chung:

- Them test `test_parse_cnc_log_ignores_simulation_done_before_real_machining`.
- Test moi do truoc khi sua: parser tra `DONE, CUTTING`.
- Sau khi sua:
  - `python -m unittest Z:\Tools\tests\test_tap_preview.py -k cnc_log` -> 2 test OK.
  - `python -m unittest Z:\Tools\tests\test_cnc_legacy_bridge.py` -> 4 test OK.
  - `python -m unittest discover -s Z:\Tools\tests` -> 94 test OK.
  - `py_compile` OK.
- Log CNC that sau khi parse:
  - giu `CUTTING` luc 14:31:20 cho `XXXD_MICATRONG2_Ngay11_Ngay12.tap`.
  - khong con cac DONE simulation cho job nay.
- Rebuild audit `Z:\Tools\dist-audit\cnc_legacy_bridge.exe`.
- SHA256 moi `93A0DAD4C7F6BC593CB06639E90AF8ADA9F3D0053026B07244C6ECA6F69E2DE7`.

Chua deploy live:

- CNC dang co `CUTTING` that luc kiem tra.
- Khong copy exe, khong restart NSSM.

## Tiep tuc an toan 2026-07-13 14:52

Phat hien:

- InDecal log co du pass live cho job dang in.
- Vi du `12~hl_120x240.prn`:
  - `nTotalPrintPass=429`.
  - luc 14:50:22: `current_pass=396`, tuong duong `92.3%`.
- Source cu co 2 lo hong:
  1. May tram chi gui progress khi DONE/DELETE, khong gui khi dang PRINTING.
  2. Server chan event trung trang thai, nen neu gui `PRINTING` lan nua thi `machine_meta_json` khong cap nhat.

Da sua trong source:

1. `app/QuanLyXuong.py` len `V2.0.7_INDECAL_PROGRESS_META`.
2. Parser InDecal gui event `PRINTING` kem `machine_meta` khi phan tram nguyen tang.
   - Vi du 10%, 11%, 12%...
   - Khong gui tung pass, tranh spam server.
3. Metadata progress gom:
   - `current_pass`.
   - `total_pass`.
   - `progress_percent`.
   - `log_event_time`.
4. Progress event khong dung `log_done_time`.
   - `log_done_time` chi danh cho DONE/DELETE.
5. `process_event` dung `log_event_time` lam `event_time` neu co, de idempotency khong trung voi event start cung giay.
6. `app/server.py` len `V7.6.4_PROGRESS_META`.
7. Server cho phep event trung trang thai `PRINTING/CUTTING` cap nhat `machine_meta_json` va `updated_time`, khong tao dong moi.

Kiem chung:

- Them test `test_indecal_log_parser_emits_progress_printing_events`.
- Them test `test_duplicate_running_status_can_refresh_machine_meta`.
- Test do dung:
  - parser truoc do khong emit progress.
  - server truoc do giu `current_pass=1`, khong cap nhat len pass moi.
- Sau khi sua:
  - `python -m unittest Z:\Tools\tests\test_quanlyxuong_scan.py` -> 16 test OK.
  - `python -m unittest Z:\Tools\tests\test_server_reprint_noise.py` -> 10 test OK.
  - `python -m unittest discover -s Z:\Tools\tests` -> 96 test OK.
  - `py_compile` OK.
- Build audit:
  - `Z:\Tools\dist-audit\QuanLyXuong.exe`, SHA256 `FE7890AE560FE34D9BD7CC65AEEC7500F6CDA61E4E14019F4B947F8DF2A400F7`.
  - `Z:\Tools\dist-audit\server.exe`, SHA256 `1DF38E8EF174481B719DE6DD7E09C89E3885D5EE19ED7FE475D4BC7CF2042C59`.

Chua deploy live:

- Luc 14:52 DB that:
  - InDecal running 1: `13~hl_120x67.prn`.
  - CNC running 1: `xxxd_micatrong2_ngay11_ngay12.tap`.
  - InBat running 0.
- Khong copy exe, khong restart NSSM.

## Tiep tuc an toan 2026-07-13 14:55

Phat hien:

- Pipeline da co `machine_meta.progress_percent`, nhung Dashboard chi hien `file.progress_label`.
- Neu khong map meta sang label, thẻ đang chạy vẫn không hiện `%`.

Da sua trong source `app/Dashboard.py`:

1. Them `active_progress_label(machine_meta)`.
2. Neu file dang `PRINTING/CUTTING` co `progress_percent`, backend gan:
   - `progress_label = "Tien do: NN%"`.
3. Card va preview da co san vung hien `progress_label`, nen UI se hien % sau khi deploy Dashboard + server + client moi.

Kiem chung:

- Them test `test_active_progress_label_uses_machine_meta_percent`.
- `python -m unittest Z:\Tools\tests\test_dashboard_v2_status.py` -> 34 test OK.
- `python -m unittest discover -s Z:\Tools\tests` -> 97 test OK.
- `py_compile` OK.
- Rebuild audit `Z:\Tools\dist-audit\Dashboard.exe`.
- SHA256 moi `99B50D561A03EA3DB2088A9A1CBC57C131B11A172983909CD73C08E457213ED7`.

Live luc 14:55:

- InBat active 0.
- InDecal active 1.
- CNC active 1.
- Van chua deploy live.

## Deploy live 2026-07-13 14:57

Dieu kien truoc deploy:

- Kiem DB that, khong dung so active cu tren web:
  - InBat `PRINTING/CUTTING = 0`.
  - InDecal `PRINTING/CUTTING = 0`.
  - CNC `PRINTING/CUTTING = 0`.
- Web cu van co active do dem ca `EXPORTED/RIP`, nhung ban moi da tach `Dang` va `Cho`.

Cach deploy:

1. Tao backup live dist:
   - `Z:\Tools\releases\manual-update-20260713-145711\dist-before`.
2. Copy 3 file truoc:
   - `QuanLyXuong.exe`.
   - `Dashboard.exe`.
   - `cnc_legacy_bridge.exe`.
3. Copy `server.exe` cuoi cung de kich server auto-update/NSSM runtime restart.
4. Runtime log xac nhan:
   - `14:57:16` server cu tu thoat vi phat hien server moi tren NAS.
   - `14:57:21` NSSM runtime bat dau cycle moi.
   - `14:57:27` bat dau Dashboard + CNC bridge + server moi.
   - `14:57:28` server khoi dong `V7.6.4_PROGRESS_META`.

Hash live/local sau deploy:

- NAS `QuanLyXuong.exe`: `FE7890AE560FE34D9BD7CC65AEEC7500F6CDA61E4E14019F4B947F8DF2A400F7`.
- NAS `server.exe`: `1DF38E8EF174481B719DE6DD7E09C89E3885D5EE19ED7FE475D4BC7CF2042C59`.
- NAS `Dashboard.exe`: `99B50D561A03EA3DB2088A9A1CBC57C131B11A172983909CD73C08E457213ED7`.
- NAS `cnc_legacy_bridge.exe`: `93A0DAD4C7F6BC593CB06639E90AF8ADA9F3D0053026B07244C6ECA6F69E2DE7`.
- Local `C:\QuanLyXuong\server_Local.exe` khop NAS server hash.
- Local `C:\QuanLyXuong\Dashboard_Local.exe` khop NAS Dashboard hash.
- Local `C:\QuanLyXuong\cnc_legacy_bridge.exe` khop NAS CNC bridge hash.

Trang thai sau deploy:

- InBat version `V2.0.7_INDECAL_PROGRESS_META`, active 0.
- InDecal version `V2.0.7_INDECAL_PROGRESS_META`, active 0.
- CNC version `V2.0.4_CNC_NCSTUDIO_LOG`, active 0.
- Server log ghi `V7.6.4_PROGRESS_META`.

Ghi chu:

- Process doi cua exe onefile la binh thuong voi PyInstaller: parent + child cung ten exe.
- Khong can kill them neu API/Dashboard dang tra loi va hash local da khop.

## Don ton cu 2026-07-13 15:09

Muc tieu:

- Don cac dong `EXPORTED/RIP` cu lam sidebar hien `Ton cu`.
- Khong dong file hom nay neu file that van con tren may.

Backup truoc khi sua DB:

- `Z:\Tools\backups\manual-db-clean-20260713-150823`.

Da kiem tra:

- Kiem tra DB local `C:\QuanLyXuong\Data`.
- Kiem tra file that qua LAN share:
  - InDecal `D:\...` -> `\\InDecal\D\...`.
  - InBat `D:\...` -> `\\InBat\D\...`.
  - CNC `D:\CNC\...` -> `\\CNC\CNC\CNC\...`.

Da dong 6 dong mat file goc:

- InDecal:
  - `hoatho_118x78_ngay11.tif`.
  - `hoatho_118x78.tif`.
  - `hoatho_120x80.tif`.
- CNC:
  - `xxxd_micatrong2.tap`.
  - `xxd_micatrong.tap`.
- InBat:
  - `balong_162x120.tif`.

Cach dong:

- Doi status sang `DELETED`.
- Giu `updated_time` cu de khong lam sai thong ke ngay.
- Them history:
  - `event = ADMIN_CLEAN_MISSING_SOURCE`.
  - `time = 2026-07-13 15:09:37`.
  - `old_status = EXPORTED`.
  - `reason = Dong ton cu vi file goc khong con tren may`.

Ket qua sau don:

- `/api/v2_status`:
  - InBat `old_active = 0`.
  - InDecal `old_active = 0`.
  - CNC `old_active = 0`.
- Da goi `http://127.0.0.1:8000/api/broadcast` thanh cong de dashboard refresh.

Con giu lai:

- CNC `xp_120x80mica.tap` va `loi_120x23.tap`.
- Ly do: file that con tren `\\CNC\CNC\CNC\2026-07-13\...`, nen van la hang cho hop le trong ngay.

## Fix DONE replay CNC 2026-07-13 15:29

Van de:

- CNC `xp_120x80mica.tap` bi tinh thanh `(x2)` do server nhan DONE tu 2 nguon:
  - `\\CNC\CNC\CLIENT_CNC\file_history.csv`.
  - `\\CNC\Ncstudio V5.5.60\NCSTUDIO.LOG`.
- Day la DONE replay cua cung 1 lan cat, khong phai lan cat thu 2.

Da sua DB live truoc deploy:

- Backup: `Z:\Tools\backups\manual-cnc-done-replay-20260713-152618`.
- Dong `xp_120x80mica.tap` trong `C:\QuanLyXuong\Data\CNC.db`:
  - `status = DONE`.
  - `run_count = 1`.
  - `updated_time = 2026-07-13 15:23:33`.
  - history chi giu `EXPORTED`, `CUTTING`, 1 dong `DONE`.

Da sua source server:

- `app/server.py` len `SERVER_VERSION = "V7.6.5_DONE_REPLAY_FIX"`.
- Khi nhan DONE:
  - Neu co `done_hash` nhung khong co `active_hash`, server coi do la replay DONE cu.
  - Server ghi idempotency key, log `[DONE-REPLAY]`, khong tang `run_count`.
  - Neu co `active_hash` that, van tinh la lan chay moi hop le.

Kiem chung truoc deploy:

- Them test `test_done_replayed_without_new_active_run_does_not_increment_run_count`.
- `python -m unittest discover -s Z:\Tools\tests` -> 98 test OK.
- `py_compile` server OK.
- Build audit: `Z:\Tools\dist-audit\server.exe`.
- SHA256 audit: `3A6B1CC69597618372F14C5D1301EB4D244438F75860F32929628407F86CAB66`.

Deploy live:

- Truoc deploy:
  - `/api/v2_status`: InBat/InDecal/CNC `active = 0`, `old_active = 0`.
  - DB live: InBat/InDecal/CNC khong co dong `PRINTING/CUTTING`.
- Copy duy nhat `server.exe`:
  - Tu `Z:\Tools\dist-audit\server.exe`.
  - Den `\\192.168.1.188\AI\Tools\dist\server.exe`.
- Runtime/NSSM tu nhan server moi va restart:
  - `2026-07-13 15:29:01` phat hien ban server moi tren NAS.
  - `2026-07-13 15:29:14` khoi dong `V7.6.5_DONE_REPLAY_FIX`.

Kiem chung sau deploy:

- `/api/v2_status` tra loi OK.
- Hash 3 noi khop nhau:
  - `Z:\Tools\dist-audit\server.exe`.
  - `\\192.168.1.188\AI\Tools\dist\server.exe`.
  - `C:\QuanLyXuong\server_Local.exe`.
  - SHA256: `3A6B1CC69597618372F14C5D1301EB4D244438F75860F32929628407F86CAB66`.
- Version may giu nguyen:
  - InBat `V2.0.7_INDECAL_PROGRESS_META`.
  - InDecal `V2.0.7_INDECAL_PROGRESS_META`.
  - CNC `V2.0.4_CNC_NCSTUDIO_LOG`.

Con theo doi:

- Neu CNC log cu replay lai DONE da co, server phai ghi `[DONE-REPLAY]` va khong tao `(x2)`.
- Neu may that chay lai file da DONE, phai co `CUTTING/PRINTING` moi truoc DONE thi moi duoc tang `run_count`.

## Fix InDecal DELETE gia khi dang in 2026-07-13 15:51

Quan sat live:

- InDecal job `14~xpppp1_122x164.prn` co log pass dang tang:
  - `15:39:29`: 33/295, 11.2%.
  - `15:41:45`: 124/295, 42.0%.
  - `15:43:17`: 192/295, 65.1%.
- Sau do client gui `DELETE` luc khoang `15:44`, nhung log may InDecal cho thay da chay toi pass 195 roi reset ve 0.
- Server live `V7.6.5_DONE_REPLAY_FIX` tach thanh 2 row:
  - Row 1: `EXPORTED/RIP/PRINTING/DELETED`, progress moi 5.08%.
  - Row 2: `PRINTING/DELETED`, progress 65.08%.
- Day la diem chua chat: neu co `DELETE` gia roi `PRINTING` tiep ngay, server khong nen tach row moi.

Da sua source, chua deploy live:

- `app/server.py` len `SERVER_VERSION = "V7.6.6_INDECAL_DELETE_PROGRESS_FIX"`.
- Khi `DELETE` trong luc `PRINTING/CUTTING`:
  - Lay `progress_percent` tu `machine_meta_json` da luu neu event DELETE khong gui meta.
  - Ghi `% hong` vao history DELETE.
- Khi nhan `PRINTING/CUTTING` sau mot `DELETED` gan nhat cung file trong 120 giay:
  - Neu DELETE truoc do co `old_status = PRINTING/CUTTING`, coi la DELETE gia/tin hieu file tam.
  - Revive lai cung row, khong tao row moi.
  - Ghi log `[DELETE-RESUME]`.

Kiem chung source:

- Them test:
  - `test_running_delete_uses_stored_progress_percent`.
  - `test_indecal_printing_after_recent_running_delete_revives_same_row`.
- `python -m unittest Z:\Tools\tests\test_server_reprint_noise.py` -> 13 test OK.
- `python -m unittest discover -s Z:\Tools\tests` -> 100 test OK.
- `python -m py_compile Z:\Tools\app\server.py` -> OK.
- Build audit `Z:\Tools\dist-audit\server.exe`.
- SHA256 audit: `5850D6CD56D424DEE8FC9BEDD2DB89D31671CABA2A20539923D1F79536E560C0`.

Chua deploy live vi luc 15:51 may con active:

- InDecal `14~xpppp1_122x164.prn` dang `PRINTING`, khoang 61%.
- CNC `loi_120x23.tap` dang `CUTTING`.

Deploy sau khi an toan:

1. Doi InDecal/CNC `active=0` va DB khong con `PRINTING/CUTTING`.
2. Copy `Z:\Tools\dist-audit\server.exe` sang `\\192.168.1.188\AI\Tools\dist\server.exe`.
3. Doi runtime/NSSM restart server.
4. Kiem log server phai co `V7.6.6_INDECAL_DELETE_PROGRESS_FIX`.
5. Kiem hash NAS va `C:\QuanLyXuong\server_Local.exe` khop audit.

## Fix hien % tren card web 2026-07-13 16:03

Van de:

- DB/API da co tien do InDecal:
  - `/api/data` co `progress_label = "Tien do: 59%"` cho `15~xppp2_120x240.prn`.
  - `machine_meta.progress_percent` van tang theo pass log.
- Web khong thay % vi `createCard()` dat `progressBadge` ben trong `.card-extra`.
- CSS compact dang co `.card-extra { display: none; }`, nen % bi an.

Da sua:

- `app/Dashboard.py`:
  - Dua `${progressBadge}` ra ngoai `.card-extra`, ngay duoi `.card-main`.
  - Giu cac badge phu trong `.card-extra` de giao dien van gon.

Kiem chung:

- `python -m unittest Z:\Tools\tests\test_dashboard_v2_status.py` -> 34 test OK.
- `python -m py_compile Z:\Tools\app\Dashboard.py` -> OK.
- Build audit `Z:\Tools\dist-audit\Dashboard.exe`.
- SHA256 audit/NAS/local: `8B5CEAEEAB2C0968C3DA1CE81ED9C15BF9D85B9FC1859915716D46C03C3518C0`.
- Restart rieng `Dashboard_Local.exe` bang `scripts\Restart-DashboardV2.ps1`, khong restart server/client may.
- Browser reload xac nhan:
  - Card `15~xppp2_120x240.prn` hien `Tien do: 79%`.
  - Console khong co error/warn.

## Source fix InDecal rename guard 2026-07-13 16:29

Muc tieu:

- Giam loi thuc te: tho bam in khi file `.prn` chua kip rename.
- Giam tranh doc log voi PrintExp.
- Chan truong hop 2 client cung chay tren mot may lam rename race.

Quyet dinh an toan:

- Chua khoa/move file in truc tiep bang cach doi extension hay dua vao thu muc hold.
- Ly do: cach do co the lam PrintExp/RIP khong thay file hoac anh huong job dang chay.
- Ban nay chi lam guard mem:
  - `.prn` tron thieu meta khong duoc gui `RIP` len server nua.
  - File giu trong `prn_tracking` va ghi audit `RENAME_WAIT_META`.
  - Qua 90 giay van thieu meta thi ghi `RENAME_STUCK_NO_META`.
  - Khi meta den, moi rename va gui `RIP`.

Da sua source, chua deploy live:

1. `app/QuanLyXuong.py` len `CLIENT_VERSION = "V2.0.8_INDECAL_RENAME_GUARD"`.
2. Tach `handle_indecal_prn_rename_candidate()` de test duoc logic rename.
3. Bo hanh vi cu nguy hiem:
   - truoc day: thieu meta thi `RENAME_FAIL_NO_META` roi van `process_event(path, "RIP")`.
   - bay gio: thieu meta thi chi cho/audit, khong `RIP`.
4. Cleanup meta chi xoa meta da dung, khong xoa toan bo meta trong ngay.
5. Chon meta theo `mtime` thay vi `ctime`, hop voi file ghi moi/thuc te hon tren Windows.
6. Them `LogTailState` + `read_new_log_lines()`:
   - doc bytes moi tu offset.
   - giu dong log ghi do dang.
   - reset khi log truncate/rotate.
   - decode `gb18030`.
7. `worker_indecal_log()` da dung helper tail moi.
8. Them lock 1 instance client theo may:
   - file lock `C:\QuanLyXuong\QuanLyXuong_<machine>.lock`.
   - instance thu hai tu thoat, khong quet/rename nua.
9. Heartbeat gui them:
   - `pid`.
   - `start_time`.
   - `instance_id`.
10. `app/server.py` len `SERVER_VERSION = "V7.6.7_INSTANCE_PING"` va luu cac gia tri heartbeat moi vao `app_info`.
11. `app/Dashboard.py` doc them `pid/start_time/instance_id` tu `app_info`.

Kiem chung source:

- `python -m unittest discover -s Z:\Tools\tests` -> 106 test OK.
- `python -m py_compile Z:\Tools\app\QuanLyXuong.py Z:\Tools\app\server.py Z:\Tools\app\Dashboard.py Z:\Tools\app\qlx_workstation_logic.py` -> OK.
- Build audit OK:
  - `Z:\Tools\dist-audit\QuanLyXuong.exe`
    - SHA256 `CDD3E271205D5BC9815E35235FDFE3202E1DBD8C5B23B08013E5C022378027D3`
  - `Z:\Tools\dist-audit\server.exe`
    - SHA256 `DBD6D68266B5FC91262ECEF49168BCA9D14F5288FA9F8FE8891A10974D51D4B6`
  - `Z:\Tools\dist-audit\Dashboard.exe`
    - SHA256 `565FAE14896F7244B0A0A34ACA97C042BB4033107E8DB5CB9C36411DB4AED13E`

Chua deploy live vi luc 16:29:

- InDecal active 1:
  - `20~lhhh1_decal_120x240.prn`
  - tien do `92%`.
- InBat active 0.
- CNC active 0.

Kiem tra lai luc 16:35:

- InDecal active 0, done_today 21.
- InBat active 0.
- CNC active 1:
  - `xp2.tap`.
- Van chua deploy vi client exe dung chung, copy ban moi co the lam CNC auto-update/restart trong luc dang cat.

Deploy sau khi an toan:

1. Doi `/api/v2_status` tat ca `active=0`.
2. Copy `QuanLyXuong.exe`, `server.exe`, `Dashboard.exe` tu `Z:\Tools\dist-audit` sang `\\192.168.1.188\AI\Tools\dist`.
3. Copy `server.exe` cuoi cung de runtime restart dung thu tu.
4. Sau deploy:
   - InDecal/InBat version phai len `V2.0.8_INDECAL_RENAME_GUARD`.
   - Server phai len `V7.6.7_INSTANCE_PING`.
   - Dashboard van tra `/api/v2_status`.
5. Theo doi job InDecal tiep theo:
   - neu `.prn` thieu meta, dashboard/audit phai co `RENAME_WAIT_META`, khong co `RIP` tron.
   - neu meta den, file phai thanh `N~ten.prn` roi moi co `RIP`.
   - khong con xoa nham meta cua job khac.

## Dashboard production polish 2026-07-13 17:21

Van de tu ghi chu tren web:

1. CNC dang chay khong hien `%`.
2. `14~xpppp1_122x164.prn` hien trung 2 dong trong Xoa/Huy.
3. Cot Loi/Xoa co nhieu khoang trong khi chi co mot nhom co du lieu.
4. Nhan "Huy khi dang chay" chua tach ro xoa sau DONE, dung, hay huy.
5. Preview CNC hien `TAP` va `Feed` kho hieu.

Ket luan log CNC:

- `NCSTUDIO.LOG` cua `xp3.tap` chi co:
  - `17:04:58 Initiate a machining task`.
  - `17:10:50 hoan thanh binh thuong`.
- Khong co dong % tien do that nhu InDecal `nCurPassIndex`.
- Muon co % trong luc cat phai uoc tinh bang thoi gian chay + baseline job da DONE + metadata TAP.

Da sua va deploy rieng Dashboard:

1. Them `estimate_active_progress()`:
   - uu tien `machine_meta.progress_percent` neu co.
   - neu khong co, uoc tinh theo thoi gian dang chay va job DONE gan tuong dong.
   - CNC uu tien so dong cat `line_count`; may in uu tien dien tich tu ten/meta.
2. Them `dedupe_visible_items()` cho danh sach `CANCELED/REMOVED`:
   - gom trung theo may + core ten file + loai thao tac.
   - giu dong moi nhat.
   - `14~xpppp1_122x164.prn` hien 1 dong thay vi 2 dong.
3. Doi CSS `problem-stack`:
   - neu chi co mot nhom loi/xoa thi nhom do tu chiem het chieu cao.
   - neu co ca hai nhom thi chia deu.
4. `DELETE` sau `DONE` duoc gan `done_cleanup` = `Xoa sau khi xong`, khong tinh la loi san xuat.
5. Doi text preview CNC:
   - `TAP` -> `Dong cat`.
   - `Feed` -> `Toc do cat`.
   - Them tooltip ngan de giai thich.

Kiem chung:

- `python -m unittest Z:\Tools\tests\test_dashboard_v2_status.py` -> 37 test OK.
- `python -m unittest discover -s Z:\Tools\tests` -> 109 test OK.
- `python -m py_compile Z:\Tools\app\Dashboard.py` -> OK.
- Build `Z:\Tools\dist-audit\Dashboard.exe`.
- SHA256 Dashboard moi:
  - `7DFA80A32D8667F841536FC2E129DB39F4E19978BDCA74084890D4AB6992EE8F`.

Deploy:

- Copy `Dashboard.exe` sang `\\192.168.1.188\AI\Tools\dist\Dashboard.exe`.
- Restart rieng Dashboard bang `scripts\Restart-DashboardV2.ps1`.
- Khong copy `QuanLyXuong.exe`.
- Khong copy `server.exe`.
- Khong restart client may san xuat.

Kiem tra sau deploy:

- `/api/v2_status` tra 200.
- Hash 3 noi khop:
  - `C:\QuanLyXuong\Dashboard_Local.exe`.
  - `\\192.168.1.188\AI\Tools\dist\Dashboard.exe`.
  - `Z:\Tools\dist-audit\Dashboard.exe`.
- `/api/data` sau deploy:
  - `14~xpppp1_122x164.prn` chi con 1 dong trong `REMOVED`.
  - InDecal active co `%` that tu meta.

Con chua deploy:

- `QuanLyXuong.exe` V2.0.8 va `server.exe` V7.6.7 van cho tat ca may `active=0`.

## Don HOATHO wrong-day da doi ten 2026-07-13 17:31

Van de:

- Web hien `HOATHO_120X80_Ngay11.tif` trong Hang cho luc `2026-07-13 07:45:08`.
- Nguoi dung nghi file da duoc doi ten thanh ngay 12 va da in xong.

Kiem tra thu muc InDecal:

- Khong con:
  - `\\InDecal\D\2026-07-12\HOATHO_120X80_Ngay11.tif`.
- Dang ton tai:
  - `\\InDecal\D\2026-07-13\New Folder\HOATHO_120X80_Ngay11_Ngay12.tif`.
  - `\\InDecal\D\2026-07-13\New Folder\2~HOATHO_120X80_Ngay11_Ngay12.prn`.
  - `\\InDecal\D\2026-07-13\New Folder\2~HOATHO_120X80_Ngay11_Ngay12.prn.bmp`.

Kiem tra DB:

- Row cu:
  - `file_name = HOATHO_120X80_Ngay11.tif`.
  - `file_path = D:\2026-07-12\HOATHO_120X80_Ngay11.tif`.
  - `status = WRONG_DAY`.
- Row dung da in:
  - `file_name = 2~HOATHO_120X80_Ngay11_Ngay12.prn`.
  - `status = DONE`.
  - `DONE = 2026-07-13 07:58:27`.

Da sua DB live an toan:

- Backup truoc khi sua:
  - `Z:\Tools\backups\manual-hoatho-wrong-day-clean-20260713-173109\InDecal.db`.
- Chuyen dung 1 row `HOATHO_120X80_Ngay11.tif` tu `WRONG_DAY` sang `DELETED`.
- Giu `updated_time = 2026-07-13 07:45:08` de khong lam sai thong ke thoi gian.
- Them history:
  - `event = ADMIN_CLEAN_RENAMED_DONE`.
  - `old_status = WRONG_DAY`.
  - `cancel_type = source_renamed_done`.
  - `reason = File goc khong con; da doi ten thanh 2~HOATHO_120X80_Ngay11_Ngay12.prn va in xong luc 2026-07-13 07:58:27`.

Kiem tra sau sua:

- Goi broadcast refresh thanh cong.
- `/api/data`:
  - Khong con `HOATHO_120X80_Ngay11.tif` trong Hang cho.
  - `2~HOATHO_120X80_Ngay11_Ngay12.prn` nam trong DONE.
  - `HOATHO_120X80_Ngay11.tif` nam trong REMOVED voi ly do da doi ten/in xong.

Can nang cap sau:

- Dashboard/server nen tu dong an/dong cac row `WRONG_DAY` ma file goc da mat va da co successor `*_NgayXX_NgayYY` DONE.

## Dashboard an DELETE cu khi da co DONE sau do 2026-07-13 17:45

Van de:

- File `25~temm_hlll_125x103.prn` co 2 row trong DB:
  - Row 1: `DELETED` luc `17:14:08`, old_status `PRINTING`, progress khoang `4.79%`.
  - Row 2: `DONE` luc `17:26:29`, in xong that `10 phut 18 giay`.
- Web van hien row `DELETED` trong Xoa/Huy du file da co DONE sau do.

Nhan dinh:

- Day la tin hieu DELETE gia/tam trong khi may con tiep tuc in.
- Server V7.6.6 da co fix delete-resume cho cac event moi, nhung row cu truoc/ngoai luong fix van co the con trong DB.
- Khong nen de Dashboard hien DELETE cu neu cung may + cung core file da co DONE muon hon trong ngay.

Da sua Dashboard:

1. Them `filter_removed_items_with_later_done()`:
   - Neu item trong `CANCELED/REMOVED` co cung may + cung core ten file voi item `DONE` muon hon, thi an item xoa/huy cu.
2. Ap dung sau khi dedupe `CANCELED/REMOVED`.
3. Khong sua DB cho truong hop nay, chi sua hien thi de tranh lam mat lich su.

Kiem chung:

- Them test `test_filter_removed_items_hides_old_delete_when_same_job_is_done`.
- `python -m unittest Z:\Tools\tests\test_dashboard_v2_status.py` -> 38 test OK.
- `python -m py_compile Z:\Tools\app\Dashboard.py` -> OK.
- Build/deploy rieng `Dashboard.exe`.
- SHA256 moi:
  - `88DD54E7AED396B5DAD4AF6664B4BC688C210412492200D79A3D82E54E7AB800`.
- Restart rieng Dashboard, khong restart client/server may.

Kiem tra sau deploy:

- `/api/data`:
  - `25~temm_hlll_125x103.prn` con trong DONE.
  - Khong con trong REMOVED.
  - Khong con trong CANCELED.
- Hash 3 noi khop:
  - `C:\QuanLyXuong\Dashboard_Local.exe`.
  - `\\192.168.1.188\AI\Tools\dist\Dashboard.exe`.
  - `Z:\Tools\dist-audit\Dashboard.exe`.

## Kiem tra file 10~tho_119x191.prn 2026-07-13

Van de:

- Web preview tung hien `10~tho_119x191.prn` trong nhom `Xoa/Huy`.
- Timeline lai co dau hieu da chay va co metadata anh:
  - Dien tich khoang `2.28 m2`.
  - Kho anh `119.5 x 191.0 cm`.
  - DPI `150 x 150`.

Kiem tra thu muc may:

- File van ton tai trong thu muc InDecal ngay 2026-07-13:
  - `\\InDecal\D\2026-07-13\New Folder\10~tho_119x191.prn`.
  - `\\InDecal\D\2026-07-13\New Folder\10~tho_119x191.prn.bmp`.
  - `\\InDecal\D\2026-07-13\New Folder\tho_119x191.tif`.

Kiem tra DB:

- Co 3 row cung ten file:
  - Row 1: `DELETED` luc `2026-07-13 13:48:09`, `old_status = PRINTING`.
  - Row 2: `DELETED` luc `2026-07-13 13:48:54`, `old_status = PRINTING`.
  - Row 3: `DONE` luc `2026-07-13 13:57:17`, `event = DONE_FROM_INDECAL_LOG`, `progress_percent = 99.70760233918129`.

Ket luan:

- File nay da in xong that luc `13:57:17`.
- Hai dong `DELETED` la tin hieu xoa/huy cu trong qua trinh chay, khong nen tinh la huy cuoi cung.
- Khong sua DB cho truong hop nay de giu lich su day du.
- Dashboard da co logic an `DELETED/CANCELED` cu neu cung may + cung core file da co `DONE` muon hon.

Kiem tra sau fix hien thi:

- `/api/data` hien `10~tho_119x191.prn` trong `DONE`.
- Khong con hien trong `REMOVED`.
- Khong con hien trong `CANCELED`.

## Kiem tra file hoatho_118x78_ngay11.tif 2026-07-13

Van de:

- Web hien `hoatho_118x78_ngay11.tif` trong `Xoa/Huy` luc `07:45:08`.
- Nguoi dung nghi day la chuoi file cu:
  - Xuat file ngay 10/11.
  - Doi ten sang ngay 11.
  - Sau do doi tiep/ngay 12 va da in.

Kiem tra thu muc may:

- Khong thay file goc trong cac ngay `2026-07-10`, `2026-07-11`, `2026-07-12`.
- Tim thay ban da doi ten trong ngay `2026-07-13`:
  - `\\InDecal\D\2026-07-13\New Folder\1~HOATHO_118X78_Ngay11_Ngay12.prn`.
  - `\\InDecal\D\2026-07-13\New Folder\1~HOATHO_118X78_Ngay11_Ngay12.prn.bmp`.
  - `\\InDecal\D\2026-07-13\New Folder\HOATHO_118X78_Ngay11_Ngay12.tif`.

Kiem tra DB:

- Row cu `hoatho_118x78.tif`:
  - `status = DELETED`.
  - `created_time = 2026-07-11 15:53:21`.
  - History co `ADMIN_CLEAN_MISSING_SOURCE`.
- Row cu `hoatho_118x78_ngay11.tif`:
  - `status = DELETED`.
  - `created_time = 2026-07-13 07:45:08`.
  - `file_path = d:\2026-07-12\hoatho_118x78_ngay11.tif`.
  - History co `ADMIN_CLEAN_MISSING_SOURCE`.
- Row dung da in:
  - `file_name = 1~HOATHO_118X78_Ngay11_Ngay12.prn`.
  - `status = DONE`.
  - `created_time = 2026-07-13 07:45:08`.
  - `updated_time = 2026-07-13 07:53:25`.
  - History:
    - `RIP` luc `07:45:08`.
    - `WRONG_DAY` luc `07:46:32`.
    - `PRINTING` luc `07:50:00`.
    - `DONE` luc `07:53:25`.

Ket luan:

- `hoatho_118x78_ngay11.tif` khong phai huy loi that.
- Day la file nguon/ten cu, sau do da thanh `1~HOATHO_118X78_Ngay11_Ngay12.prn` va in xong.
- Khong sua DB, giu lich su day du.

Da sua Dashboard:

- Them nhan dang quan he file nguon doi ten sang ban DONE muon hon:
  - Cung may.
  - DONE co thoi gian muon hon.
  - Token ten file nguon la tap con cua token ten file DONE.
  - Co it nhat mot token chua so/kich thuoc de tranh gom nham.
- Vi du duoc an khoi `Xoa/Huy`:
  - `hoatho_118x78_ngay11.tif`.
  - `1~HOATHO_118X78_Ngay11_Ngay12.prn` van hien trong `DONE`.

Kiem chung:

- `python -m unittest Z:\Tools\tests\test_dashboard_v2_status.py` -> 40 test OK.
- `python -m py_compile Z:\Tools\app\Dashboard.py` -> OK.
- Build/deploy rieng `Dashboard.exe`.
- SHA256 moi:
  - `884E4A20DD3F861D3939D84F5D10333B5402D5485AAD1941AF718B57DE585239`.
- Hash khop 4 noi:
  - `Z:\Tools\dist-audit\Dashboard.exe`.
  - `Z:\Tools\dist\Dashboard.exe`.
  - `C:\QuanLyXuong\Dashboard_Local.exe`.
  - `\\192.168.1.188\AI\Tools\dist\Dashboard.exe`.
- `/api/data` sau deploy:
  - `1~HOATHO_118X78_Ngay11_Ngay12.prn` nam trong `DONE`.
  - `hoatho_118x78_ngay11.tif` khong con nam trong `REMOVED`.
  - `hoatho_118x78_ngay11.tif` khong con nam trong `CANCELED`.
- `python -m unittest discover -s Z:\Tools\tests` -> 112 test OK.

## Deploy rename guard khi may het in 2026-07-13 19:21

Dieu kien truoc deploy:

- Nguoi dung xac nhan cac may da het in.
- Kiem tra live API:
  - InBat `active = 0`.
  - InDecal `active = 0`.
  - CNC `active = 0`.
  - `RUNNING` rong.
- `python -m unittest discover -s Z:\Tools\tests` -> 112 test OK.

Ban deploy:

- `QuanLyXuong.exe`
  - SHA256 `CDD3E271205D5BC9815E35235FDFE3202E1DBD8C5B23B08013E5C022378027D3`.
  - Source version `V2.0.8_INDECAL_RENAME_GUARD`.
- `server.exe`
  - SHA256 `DBD6D68266B5FC91262ECEF49168BCA9D14F5288FA9F8FE8891A10974D51D4B6`.
  - Source version `V7.6.7_INSTANCE_PING`.
- `Dashboard.exe`
  - SHA256 `884E4A20DD3F861D3939D84F5D10333B5402D5485AAD1941AF718B57DE585239`.

Backup truoc deploy:

- `Z:\Tools\releases\manual-update-20260713-192142\dist-before`.
- Luu ca ban NAS va ban local `Z:\Tools\dist` truoc khi ghi de.

Da copy:

- `Z:\Tools\dist-audit\QuanLyXuong.exe` sang:
  - `Z:\Tools\dist\QuanLyXuong.exe`.
  - `\\192.168.1.188\AI\Tools\dist\QuanLyXuong.exe`.
- `Z:\Tools\dist-audit\Dashboard.exe` sang:
  - `Z:\Tools\dist\Dashboard.exe`.
  - `\\192.168.1.188\AI\Tools\dist\Dashboard.exe`.
- `Z:\Tools\dist-audit\server.exe` sang cuoi cung:
  - `Z:\Tools\dist\server.exe`.
  - `\\192.168.1.188\AI\Tools\dist\server.exe`.

Kiem tra sau deploy:

- Hash khop giua `dist-audit`, `Z:\Tools\dist`, va NAS dist cho 3 exe.
- Runtime phat hien server moi va restart:
  - Log: `PHAT HIEN BAN SERVER MOI TREN NAS`.
  - Log: `KHOI DONG V7.6.7_INSTANCE_PING`.
- Process sau cung:
  - Dashboard giu cong `5000`.
  - Server giu cong `8000`.
  - PyInstaller co cap parent/child process, khong phai 2 app doc lap.
- `/api/v2_status`:
  - `overall = OK`.
  - `versions.Server = V7.6.7_INSTANCE_PING`.
  - `versions.InDecal = V2.0.8_INDECAL_RENAME_GUARD`.
  - `InDecal` ping moi co `pid` va `instance_id`.
  - `InBat` dang offline/chua ping lai, van hien version cu `V2.0.7_INDECAL_PROGRESS_META`; se lay ban `V2.0.8` khi may/client mo lai.
  - `CNC` van `V2.0.4_CNC_NCSTUDIO_LOG`, khong nam trong ban InDecal rename guard.
  - Tat ca `active = 0`, `running = 0`.

Luu y tiep theo:

- Khi mo lai InBat, can xem version co len `V2.0.8_INDECAL_RENAME_GUARD` khong.
- Neu InBat khong tu cap nhat sau khi mo, restart rieng service client InBat bang NSSM/script may tram.

## Dashboard an source_renamed_done khoi Xoa/Huy 2026-07-13 19:28

Van de:

- `HOATHO_120X80_Ngay11.tif` da doi ten thanh `2~HOATHO_120X80_Ngay11_Ngay12.prn` va in xong.
- Web preview van co the hien nhan `Xoa`, gay hieu nham.

Kiem tra live:

- `/api/data` hien:
  - `2~HOATHO_120X80_Ngay11_Ngay12.prn` trong `DONE`.
  - `HOATHO_120X80_Ngay11.tif` khong con trong `REMOVED/CANCELED`.
- DB row cu co history:
  - `event = ADMIN_CLEAN_RENAMED_DONE`.
  - `cancel_type = source_renamed_done`.
  - `successor_file = 2~HOATHO_120X80_Ngay11_Ngay12.prn`.
  - `successor_done_time = 2026-07-13 07:58:27`.

Da sua Dashboard:

- `source_renamed_done` khong con di vao nhom `Xoa/Huy`.
- Neu can hien nhan noi bo, label dung la `Da doi ten/in xong`, khong dung chu `Xoa`.
- Them test:
  - An item `cancel_type = source_renamed_done` khoi removed.
  - Label `source_renamed_done` la `Da doi ten/in xong`.

Deploy:

- Build/deploy rieng `Dashboard.exe`.
- SHA256 moi:
  - `AAF5C17242864B9920533178C43D086BC4E69FC00A5D4C612F6723D27DEA82AA`.
- Hash khop:
  - `Z:\Tools\dist-audit\Dashboard.exe`.
  - `Z:\Tools\dist\Dashboard.exe`.
  - `C:\QuanLyXuong\Dashboard_Local.exe`.
  - `\\192.168.1.188\AI\Tools\dist\Dashboard.exe`.

Kiem chung:

- `python -m unittest Z:\Tools\tests\test_dashboard_v2_status.py` -> 42 test OK.
- `python -m py_compile Z:\Tools\app\Dashboard.py` -> OK.
- `python -m unittest discover -s Z:\Tools\tests` -> 114 test OK.
- `/api/data` sau deploy:
  - Chi thay `2~HOATHO_120X80_Ngay11_Ngay12.prn` trong `DONE`.
  - Khong thay `HOATHO_120X80_Ngay11.tif` trong `REMOVED`.
  - Khong thay `HOATHO_120X80_Ngay11.tif` trong `CANCELED`.

## Dashboard stale Xoa/Huy khi mat realtime 2026-07-13 19:35

Van de:

- Browser hien `10~tho_119x191.prn` va `11~ghep_105x220.prn` trong cot `Xoa/Huy`.
- Preview lai co timeline `DONE`:
  - `10~tho_119x191.prn`: `DONE_FROM_INDECAL_LOG` luc `13:57:17`.
  - `11~ghep_105x220.prn`: `In xong` luc `14:18:31`.
- Man hinh co luc hien `Mat realtime`, nen DOM co the giu state cu.

Giai thich:

- `DONE_FROM_INDECAL_LOG` nghia la server khong nhan event DONE truc tiep tu client tai thoi diem do, nhung doc log InDecal thay may da chay het gan `100%` nen chot la in xong.
- Day la tin hieu xong hop le hon so voi DELETE cu truoc do.

Kiem tra live:

- DB co cac row `DELETED` cu truoc, sau do co row `DONE` muon hon:
  - `10~tho_119x191.prn`: DELETE `13:48:09`, DELETE `13:48:54`, DONE `13:57:17`.
  - `11~ghep_105x220.prn`: DELETE `14:09:09`, DELETE `14:09:49`, DONE `14:18:31`.
- File van ton tai trong thu muc InDecal:
  - `\\InDecal\D\2026-07-13\New Folder\10~tho_119x191.prn`.
  - `\\InDecal\D\2026-07-13\New Folder\11~ghep_105x220.prn`.
- `/api/data` live chi tra 2 file nay trong `DONE`, khong tra trong `REMOVED/CANCELED`.

Da sua Dashboard:

- Frontend them `sanitizeBoardData()`:
  - Khi render, neu item `REMOVED/CANCELED` co cung may + cung core file voi DONE muon hon thi loai khoi Xoa/Huy.
  - Loai luon `cancel_type = source_renamed_done` va `cancel_type = done_cleanup`.
- Khi websocket mat realtime:
  - Tu fetch lai data ngay.
  - Bat fallback polling moi 10 giay.
  - Khi realtime noi lai thi dung fallback polling.
- Backend cung loai `done_cleanup` khoi `Xoa/Huy`.

Deploy:

- Build/deploy rieng `Dashboard.exe`.
- SHA256 moi:
  - `64C26182FE4067F491146FDC8A781C2F2CF53BAEF7D672FB958094B29D6F3D67`.

Kiem chung:

- `python -m unittest Z:\Tools\tests\test_dashboard_v2_status.py` -> 43 test OK.
- `python -m py_compile Z:\Tools\app\Dashboard.py` -> OK.
- `python -m unittest discover -s Z:\Tools\tests` -> 115 test OK.

## Admin doi trang thai theo file_hash 2026-07-14

Van de:

- Nut admin `Chuyen sang: Xoa/Huy` co luc nhin nhu khong doi duoc.
- DB co nhieu dong trung `file_name`, nhat la file da doi ten / in xong / xoa cu.
- API cu update theo `file_name`, nen co the doi nham dong cu; dong dang xem trong modal van giu trang thai cu.

Da sua Dashboard:

- Modal luu them `file_hash` cua the dang xem.
- `forceUpdate()` gui them `hash` len `/api/update_status`.
- API uu tien update theo `file_hash`.
- Neu khong co `hash`, moi fallback sang dong moi nhat theo `file_name`.
- Neu khong update duoc dong nao, API tra loi loi ro thay vi bao nhu da xong.

Kiem chung:

- Them test duplicate `same_name.prn`.
- Goi `/api/update_status` voi `hash-3`, chi `hash-3` doi sang `DELETED`; `hash-1` giu nguyen.
- `python -m unittest Z:\Tools\tests\test_dashboard_v2_status.py -k update_status_uses_hash_when_duplicate_file_names_exist` -> OK.
- Dashboard da deploy dong bo 4 noi.
- SHA256:
  - `A802913670E5681DDDC0B7F765E956D6D8CB94A2D19DFE0219687E20E7381A23`.

## Preview card co nut doi trang thai nhanh 2026-07-14

Van de:

- Khi bam / double-click the san xuat, modal chi tiet lon hien ra che man hinh.
- Nguoi dung muon thao tac truc tiep tren preview nho ben duoi:
  - Chuyen sang da xong.
  - Chuyen sang xoa / huy.
  - Chuyen sang xuat lai.

Da sua Dashboard:

- Bo handler double-click mo `detailModal` tren cac the san xuat.
- Preview pin khi click the, khong mo modal chi tiet.
- Preview co 3 nut icon:
  - `✓` = `DONE`.
  - `✕` = `DELETED`.
  - `↻` = `EXPORTED`.
- Nut preview dung chung `/api/update_status` va gui `file.hash` de tranh doi nham khi trung ten file.
- The san xuat co them `data-hash` de preview tim dung dong DB.

Kiem chung:

- `python -m unittest Z:\Tools\tests\test_dashboard_v2_status.py -k card_preview_has_inline_admin_status_actions` -> OK.
- `python -m py_compile Z:\Tools\app\Dashboard.py` -> OK.
- Build/deploy rieng `Dashboard.exe`.
- SHA256:
  - `05B8DA1FFFE5835F53B59AEA2881E4306DF986A2C60EB6F57586067AE75A08FF`.

Cap nhat them:

- Khi dang xuat, preview khong hien nut icon admin.
- Khi dang nhap lai, preview dang mo se hien lai icon.
- Icon thu gon thanh 32 x 26 px, canh phai preview.

## Toi uu doi bo loc san xuat 2026-07-14

Van de:

- Doi bo loc ngay o tab San xuat bi cam giac cham / do.
- Nguyen nhan:
  - `applyGlobalFilters()` goi ca `/api/stats` nang cho Bao cao.
  - Khoang thoi gian lon co hang tram / hang nghin the, DOM render qua nhieu the cung luc.
  - Khong co dau hieu dang tai nen de hieu nham la treo.

Da sua Dashboard:

- Tab San xuat uu tien `/api/data` va `/api/v2_status`; `/api/stats` chay debounce nen.
- Khi dang o tab Bao cao thi stats tai ngay.
- Them loading UI:
  - Nut lam moi xoay.
  - Badge realtime doi thanh `Dang tai...`.
- Chong response cu render de len response moi khi doi filter lien tiep.
- Moi list chi render toi da 80 the moi nhat, van giu count tong va hien dong `Con ... the cu hon`.

Kiem chung:

- `python -m unittest Z:\Tools\tests\test_dashboard_v2_status.py` -> 46 test OK.
- Build/deploy rieng `Dashboard.exe`.
- SHA256:
  - `FC18F2015B04B0BDDDA236BAF6273607D5DFE7AD17C73C0E3D0AEDEE4B726223`.

## Board paging 20 the moi lan 2026-07-14

Van de:

- Gioi han DOM o frontend van chua du nhanh, vi `/api/data` van tra nhieu row cho range lon.
- Nguoi dung muon chi tai 20 ket qua dau, cuon tiep moi tai them, nhung count/thong ke van dung.

Da sua Dashboard:

- Frontend gui `/api/data?...&limit=20` o lan dau.
- Moi lan cuon gan cuoi cot se tang limit them 20 va tai lai board.
- API limited tra:
  - Count tong rieng trong `COUNTS`.
  - Chi toi da `limit` the moi nhat cho moi nhom hien thi.
- Badge count cot dung `COUNTS`, khong dung so the da tai.
- Bao cao/thong ke van lay tu `/api/stats`, khong bi cat theo 20 the board.
- Them test backend:
  - DB co 55 file DONE.
  - `/api/data?limit=20` tra 20 item, `COUNTS.DONE=55`.

Kiem chung:

- `python -m unittest Z:\Tools\tests\test_dashboard_v2_status.py` -> 47 test OK.
- Build/deploy rieng `Dashboard.exe`.
- SHA256:
  - `362012A9D56C12147F7BF6F064FC586365B1F418B6C49AEF7705AD91714D7043`.

## Rollback thanh ngang 1 moc ve bieu do thoi gian 2026-07-14 07:03

Van de:

- Nguoi dung nhac dung: `Don hang theo may` la bieu do theo thoi gian va theo loai may.
- Ban panel thanh ngang `InBat 99.59 m2` lam mat y nghia truc thoi gian.

Da sua Dashboard:

- Bo che do panel thanh ngang cho 1 moc du lieu.
- Neu chi co 1 moc du lieu:
  - Van dung bieu do theo thoi gian.
  - Chart type la cot doc tai dung moc thoi gian.
  - Vi du `QUOCHOANG`: cot InBat nam tai moc `11`, gia tri `99.59 m2`.
- Neu co 2 moc tro len:
  - Van dung line chart nhu cu.

Deploy:

- Build/deploy rieng `Dashboard.exe`.
- SHA256 moi:
  - `30519B669B5191F1F66DAD5EDD87516A0DAAECB607124B4F0E7B2DC9FF811525`.

Kiem chung:

- `python -m unittest Z:\Tools\tests\test_dashboard_v2_status.py` -> 43 test OK.
- `python -m py_compile Z:\Tools\app\Dashboard.py` -> OK.
- Browser sau deploy:
  - Chon `Quy nay`.
  - Chon metric `m2`.
  - Click khach `QUOCHOANG`.
  - Tieu de: `Don hang theo may - QUOCHOANG · 1 moc du lieu`.
  - `orderFlowChart` hien `block`.
  - `orderFlowSingle` an `none`.
  - Bieu do hien cot InBat tai moc `11`.
  - Tong `99.59 m2`.
  - `Truc tiep: Bat`.
- `python -m unittest discover -s Z:\Tools\tests` -> 115 test OK.
- Browser sau reload:
  - `socket = Truc tiep: Bat`.
  - `10~tho_119x191.prn` co trong `In xong`.
  - `11~ghep_105x220.prn` co trong `In xong`.
  - `10~tho_119x191.prn` khong con trong `Xoa/Huy`.
  - `11~ghep_105x220.prn` khong con trong `Xoa/Huy`.
  - `Xoa/Huy` con 1 item: `ns_64x58.tif`.

## Bao cao khach 1 moc du lieu khong thay bieu do 2026-07-13 19:45

Van de:

- Khi chon khach `Ut Teo`, bo loc `InBat`, metric `m2`, bieu do `Don hang theo may - Ut Teo` gan nhu trong.
- Thuc te khach co du lieu:
  - Tong `3.68 m2`.
  - May `InBat`.
  - Chi co 1 moc thoi gian co gia tri.

Nguyen nhan:

- API tra dung du lieu, nhung chart dang ve dang line.
- Khi chi co 1 diem du lieu, line chart khong co duong noi, chi co 1 cham nho nen nhin nhu khong co bieu do.

Da sua Dashboard:

- Neu flow chart chi con `1` moc du lieu sau khi trim empty range:
  - Doi chart type sang `bar`.
  - Bar co mau may ro hon.
  - Tieu de them `1 moc du lieu`.
- Neu co tu 2 moc tro len:
  - Van giu line chart nhu cu.

Deploy:

- Build/deploy rieng `Dashboard.exe`.
- SHA256 moi:
  - `93A6B0FAFE924F13A83F6B4F2D4F5C3E2336A31E7E150035888060C4655D8720`.

Kiem chung:

- `python -m unittest Z:\Tools\tests\test_dashboard_v2_status.py` -> 43 test OK.
- `python -m py_compile Z:\Tools\app\Dashboard.py` -> OK.
- Browser sau deploy:
  - Chon `Báo cáo`.
  - Chon may `InBat`.
  - Chon metric `m2`.
  - Click cot khach `Ut Teo`.
  - Tieu de: `Don hang theo may - Ut Teo · 1 moc du lieu`.
  - Tong: `3.68 m2`.
  - `Truc tiep: Bat`.
- `python -m unittest discover -s Z:\Tools\tests` -> 115 test OK.

## Bao cao 1 moc du lieu doi sang thanh ngang 2026-07-13 21:07

Van de:

- Sau khi doi 1 moc du lieu sang bar chart, mot so khach nhu `QUOCHOANG` van thay kho nhin:
  - Chi co 1 cot doc nam giua chart.
  - Marker/hover co the che cot.
  - Nguoi dung van cam giac khong co bieu do.

Da sua Dashboard:

- Neu bieu do `Don hang theo may` chi co 1 moc du lieu:
  - An canvas chart.
  - Hien panel thanh ngang rieng.
  - Moi may co mot dong: ten may, thanh mau, gia tri truc tiep.
  - Vi du `QUOCHOANG`: `InBat 99.59 m2`.
- Neu co 2 moc du lieu tro len:
  - Van hien line chart nhu cu.

Deploy:

- Build/deploy rieng `Dashboard.exe`.
- SHA256 moi:
  - `44A93C2EF200950487835D10E0D9EF1CF4D5B1FB000D8E3F41CABD9CF53F1A44`.

Kiem chung:

- `python -m unittest Z:\Tools\tests\test_dashboard_v2_status.py` -> 43 test OK.
- `python -m py_compile Z:\Tools\app\Dashboard.py` -> OK.
- Browser sau deploy:
  - Chon `Quy nay`.
  - Chon metric `m2`.
  - Click khach `QUOCHOANG`.
  - Tieu de: `Don hang theo may - QUOCHOANG · 1 moc du lieu`.
  - `orderFlowSingle` hien `flex`.
  - Canvas chart an.
  - Panel hien `InBat 99.59 m2`.
  - Tong: `99.59 m2`.
  - `Truc tiep: Bat`.
- `python -m unittest discover -s Z:\Tools\tests` -> 115 test OK.
