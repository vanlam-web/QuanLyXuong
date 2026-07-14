# Audit InDecal rename/RIP - 2026-07-11

## Pham vi

Audit nay chi ghi nhan hien trang va diem code chua chat che. Chua sua code.

Nguon du lieu da xem:

- `C:\QuanLyXuong\Data\InDecal.db`
- bang `files`
- bang `processed_event_keys`
- `Z:\Tools\app\QuanLyXuong.py`
- `Z:\Tools\app\server.py`

## So lieu ngay 2026-07-11

- Tong dong InDecal trong ngay: 25.
- Dong con `file_path` ngan, khong co duong dan day du: 5.
  - `1~LOI_120X20.prn` DELETE.
  - `1~LOI_120X20.prn` DONE.
  - `7~xd_148x552.prn` DONE.
  - `8~xd_148x658.prn` DONE.
  - `19~huong_121x240.prn` DONE.
- Dong dang `PRINTING`: 1.
  - `17~hh3_110x60.prn`, update luc `2026-07-11 16:59:27`.
- Dong thieu thumbnail: 6.
  - `xd4.tif` DELETED.
  - `10~PICK_120X80.prn` DONE.
  - `13~hhhh_decal_62x62.prn` DELETED.
  - `13~hhhh_decal_62x62.prn` DONE.
  - `16~hh2_117x230.prn` DONE.
  - `18~hh4_100x70.prn` DONE.

## Do thoi gian da thay

`EXPORT -> RIP` dao dong lon:

- Nhanh: `13~hhhh_decal_62x62.prn` = 31 giay.
- Cham: `21~quochoang_80x6.5.prn` = 2351 giay.
- Nhieu file trong khoang 200-900 giay.

`RIP -> PRINTING` dao dong rat lon:

- Nhanh: `13~hhhh_decal_62x62.prn` = 12 giay.
- Rat cham: `8~xd_148x658.prn` = 11293 giay.
- Day co the la cho tho bam in, khong phai loi rename.

Ket luan: khong the dung mot nguong thoi gian co dinh de ket luan RIP cham hay loi. Can tach:

1. `EXPORT -> file prn xuat hien`.
2. `file prn xuat hien -> rename xong`.
3. `rename xong -> gui RIP`.
4. `RIP -> PRINTING`.

Hien DB chi cho thay moc `EXPORT/RIP/PRINTING/DONE`, chua du de biet ket rename nam o dau.

## Van de 1: so truoc dau `~` khong on dinh

Bang event cho thay:

- `RIP D:\2026-07-11\New Folder\4~xd_148x552.prn`
- nhung khi in/xong log la `7~xd_148x552.prn`.

Tuong tu:

- `RIP D:\2026-07-11\New Folder\5~xd_148x658.prn`
- nhung `PRINTING/DONE` la `8~xd_148x658.prn`.

Nhan dinh:

- So dau la so hang doi/hay ten do phan mem InDecal sinh ra, khong phai ID on dinh.
- Server khong nen ghep job bang full filename gom ca so dau.
- Can ghep theo core sau dau `~` + may + ngay + trang thai gan nhat.

## Van de 2: DELETE gia khi rename

Bang event co cap cung thoi diem:

```text
2026-07-11 16:22:27 RIP    d:\2026-07-11\new folder\16~hh2_117x230.prn
2026-07-11 16:22:27 DELETE d:\2026-07-11\new folder\16.prn
```

Nhan dinh:

- Day gan nhu chac la rename `16.prn -> 16~hh2_117x230.prn`.
- Scanner thay file cu bien mat nen gui `DELETE`.
- Day khong phai tho huy file.

Rui ro:

- Thong ke huy/loi bi sai.
- Lich su job co them tin hieu xoa nhieu.
- Neu DELETE den server khong duoc loc, co the day job vao `DELETED`.

## Van de 3: tach mot job thanh nhieu dong

Vi du `19~huong_121x240.prn`:

Dong 1:

```text
EXPORTED -> RIP -> PRINTING -> DELETED
file_path = D:\2026-07-11\New Folder\19~huong_121x240.prn
```

Dong 2:

```text
PRINTING -> DONE
file_path = 19~huong_121x240.prn
```

Nhan dinh:

- Day co the la in lai sau khi huy.
- Cung co the la server ghep sai vi `PRINTING/DONE` tu log chi co ten ngan.
- Khi tach dong, thong ke reprint/huy/loi va preview deu de sai.

## Van de 4: `forced_base_id` gui len nhung server chua dung

Client InDecal gui:

```text
process_event(..., forced_base_id=current_print_id)
```

Nhung server hien tinh hash bang:

```text
core_name = os.path.splitext(display_name)[0]
...
base_string = f"{real_machine.lower()}_core_{core_name_clean}_{today_str}"
```

Nhan dinh:

- `forced_base_id` dang la du lieu tot de ghep job nhung chua duoc dung.
- Khi log chi co ten ngan, server mat co hoi ghep ve record RIP co duong dan day du.

## Van de 5: renamer chon meta moi nhat qua don gian

Trong `fast_prn_renamer`:

```text
meta_files.sort(..., reverse=True)
matched_meta_name = meta_files[0]
```

Nhan dinh:

- Neu nhieu PRN/meta xuat gan nhau, lay meta moi nhat co the gan nham.
- Khong co so khop theo thoi gian gan nhat cua PRN, extension du kien, hay file goc.

## Van de 6: gui RIP qua som khi khong co meta

Trong `fast_prn_renamer`, neu khong co meta:

```text
processed_prn.add(path.lower())
processed_set.add(path.lower())
process_event(path, "RIP")
```

Nhan dinh:

- File `.prn` tron co the bi gui RIP truoc khi meta xuat hien.
- Sau do file da vao processed, renamer co the khong doi lai dung nua.
- Day la nguon cua "co luc khong doi ten duoc".

## Van de 7: xoa rong meta sau khi doi mot file

Sau khi rename mot PRN, code xoa tat ca `meta_files`:

```text
for trash_mf in meta_files:
    os.remove(...)
```

Nhan dinh:

- Neu nhieu job cung luc, meta cua job khac co the bi xoa.
- Job khac sau do khong doi ten duoc, hoac bi gui RIP tron.

## Van de 8: loi rename bi nuot im

Cac doan sau dang che mat loi:

- `except: pass`
- `except: continue`
- retry bang cach doi `last_changed`

Nhan dinh:

- Neu file dang bi RIP/PrintExp khoa, rename fail nhung dashboard khong biet.
- Neu target trung ten, khong biet.
- Neu mat quyen/duong dan loi, khong biet.

Can co audit event rieng:

- `RENAME_WAIT_META`
- `RENAME_WAIT_STABLE`
- `RENAME_OK`
- `RENAME_FAIL_LOCKED`
- `RENAME_FAIL_TARGET_EXISTS`
- `RENAME_FAIL_NO_META`
- `RENAME_FAIL_SOURCE_MISSING`

## Van de 9: DB hien tai thieu bang audit rename

Bang `files` chi co history theo trang thai san xuat. Bang `processed_event_keys` chi co event da gui.

Thieu bang rieng de do:

- prn raw path.
- meta da chon.
- source tif.
- target prn.
- target tif.
- file size.
- thoi diem bat dau cho.
- thoi diem on dinh.
- thoi diem rename.
- so lan retry.
- loi cuoi cung.

Khong co bang nay thi viec ket luan "RIP cham" hay "rename ket" van bi doan mo.

## Rui ro theo muc do

### Cao

1. Gui `RIP` cho PRN tron khi chua co meta.
2. Xoa toan bo meta sau khi doi mot file.
3. Server khong dung `forced_base_id` de ghep job.
4. DELETE gia do rename.

### Trung binh

1. Path ngan con ton tai khi DONE/DELETE den sau.
2. Loi rename bi nuot im.
3. Thumbnail phu thuoc rename va move tif.

### Thap

1. `RIP -> PRINTING` cham do tho chua bam in, khong nhat thiet la loi.
2. `EXPORT -> RIP` cham co the la RIP that cham, can log them moi ket luan.

## De xuat buoc tiep theo

Chua nen sua rule chinh ngay. Nen them "audit mode" truoc:

1. Ghi log/bang rename audit moi tren may InDecal.
2. Dashboard hien muc `InDecal rename/RIP`.
3. Chay 1-2 ngay san xuat that.
4. Dua vao du lieu audit de chot rule:
   - bao lau la `ket doi ten`.
   - bao lau duoc phep gui RIP tron.
   - khi nao meta duoc xem la qua cu.
   - cach ghep `PRINTING/DONE` voi `RIP` chinh xac.

## Trang thai trien khai audit - 2026-07-13

Da lam:

- Them bang/server endpoint `POST /api/indecal_rename_audit`.
- May tram InDecal se ghi audit local `Data\indecal_rename_audit.db` va gui ve server.
- Audit da ghi cac moc: cho file on dinh, khong co meta, chon meta, rename OK/FAIL, move anh goc OK/FAIL, cleanup meta OK/FAIL.
- Dashboard source da co muc `InDecal rename/RIP` trong man hinh he thong.
- Test unit da chay OK cho scanner, server anti-replay, dashboard v2 status.
- Build moi da tao o `Z:\Tools\dist-audit`.
- Server local `C:\QuanLyXuong\server_Local.exe` da cap nhat va endpoint audit live tra `{"status":"ok"}`.
- Da test endpoint bang dong `SELF_TEST`, sau do xoa dong test khoi DB.

Da go ket ngay 2026-07-13:

- Da dung `Dashboard_Local.exe` cu giu cong `5000`.
- Da khoi dong lai NSSM service `khoidongbot`.
- Web `http://192.168.1.104:5000/` da co `InDecal rename/RIP`.
- API `/api/v2_status` da co truong `rename_audit`.
- Server live: `V7.6.1_RENAME_AUDIT`.
- InDecal live: `V2.0.3_INDECAL_RENAME_AUDIT`.
- InBat live: `V2.0.3_INDECAL_RENAME_AUDIT`.
- `\\192.168.1.188\AI\Tools\dist\QuanLyXuong.exe` da cap nhat thanh ban audit.

Con can lam:

1. Chay thu mot job InDecal nho de tao audit that.
2. Xem `rename_audit.today` tang va co recent event tren dashboard.
3. Doi chieu audit voi log InDecal de chot rule rename/RIP.

## Huong sua sau khi co audit

1. Khong gui `RIP` cho `.prn` tron qua som.
2. Chi xoa meta da dung, khong xoa tat ca.
3. Khi rename, dua old path/new path vao `recent_moved` truoc va sau rename de chan DELETE gia.
4. Server dung `forced_base_id` hoac core sau dau `~` de tim active/done gan nhat.
5. Them bang `indecal_rename_audit`.
6. Them canh bao dashboard cho file ket rename/metafile/thieu tif.

## Kiem tra LAN log truc tiep - 2026-07-11 18:xx

Muc tieu: doc truc tiep log may InDecal:

```text
C:\Program Files (x86)\PrintExp_V5.7.6.5.23\Log\Log[2026_07_11].txt
```

Ket qua:

- Dashboard hien `InDecal CHUA MO`, version `V2.0.2_INDECAL_THUMB_FIX`.
- `app_info.last_ping = 2026-07-11 17:55:02`.
- Server log InDecal event cuoi: `2026-07-11 17:25:19 [INDECAL] DONE: 19~huong_121x240.prn`.
- DB `updated_time = 2026-07-11 18:33:01` khong phai event may InDecal. Day la `ADMIN_DELETE` tren web cho `xd4.tif`.
- Ten LAN `InDecal` khong resolve:
  - `ping InDecal` = host not found.
  - `nbtstat -a InDecal` = host not found.
  - `\\InDecal\c$` = network path not found.
- May thay trong LAN:
  - `192.168.1.101` / `PC01`: ping OK, NetBIOS OK, admin share `c$`/`d$` khong vao duoc.
  - `192.168.1.102` / `PC03`: ping OK, NetBIOS OK, share `Users` mo duoc, admin share `c$`/`d$` khong vao duoc.
- `PC03` co share may in:
  - `EPSON PX-1004`
  - `TOSHIBA Universal Printer 2`
- `\\192.168.1.102\Users` doc duoc, nhung khong thay `PrintExp` log hay `QuanLyXuong` log trong phan share nay.

Nhan dinh:

- Hien chua doc duoc log PrintExp truc tiep qua LAN vi thu muc can doc nam trong `C:\Program Files (x86)` va admin share bi chan.
- `PC03` la ung vien manh nhat cua may InDecal, nhung chua chung minh 100% neu khong doc duoc `C:\QuanLyXuong` hoac `PrintExp` tren may do.
- Dashboard can tach ro:
  - "Ping may tram cuoi" = trang thai chuong trinh V2 tren may.
  - "Du lieu san xuat moi nhat" = co the do may tram, server, hoac admin web tao.

Huong khac neu van khong mo admin share:

1. Mo share chi-doc thu muc log PrintExp tren may InDecal.
2. Hoac them endpoint/debug-agent trong V2 client de gui:
   - tail `Log[yyyy_mm_dd].txt`
   - trang thai file `.prn/.prt/.tif`
   - audit rename
   ve server.
3. Dashboard hien "Log may tram" de khong can remote vao may qua LAN nua.

## Viec de lai khi may InDecal mo lai

Trang thai: chua lam trong luc may InDecal dang tat. Can may mo va co thao tac that de xac minh.

Can lam tiep:

1. Doc truc tiep/tail log PrintExp:
   - `C:\Program Files (x86)\PrintExp_V5.7.6.5.23\Log\Log[yyyy_mm_dd].txt`
   - So sanh log may voi DB server theo tung file.
2. Bat loi rename that:
   - `.prn` tron xuat hien luc nao.
   - meta `._tf/._jg` xuat hien luc nao.
   - rename thanh `so~tenfile.prn` thanh cong hay loi.
   - file bi khoa, target trung ten, meta thieu, meta qua cu.
3. Them audit mode tren client InDecal:
   - `RENAME_WAIT_META`
   - `RENAME_WAIT_STABLE`
   - `RENAME_OK`
   - `RENAME_FAIL_LOCKED`
   - `RENAME_FAIL_TARGET_EXISTS`
   - `RENAME_FAIL_NO_META`
   - `RENAME_FAIL_SOURCE_MISSING`
4. Dashboard hien muc `InDecal audit`:
   - dang ket doi ten.
   - thieu meta.
   - thieu anh goc.
   - RIP tron chua co meta.
   - log PrintExp moi nhat.
5. Sau 1-2 ngay co audit that, moi chot rule:
   - bao lau la ket rename.
   - bao lau duoc phep gui RIP tron.
   - cach tinh % huy/hong khi dang chay.
   - cach nhan dien in lai dung so luong hay loi tin hieu.
