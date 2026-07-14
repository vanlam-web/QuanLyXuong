# V2 direction decisions

Ngay ghi nhan: 2026-07-09.

## Muc tieu V2

V2 thay vai tro cua he cu theo huong an toan hon:

```text
May san xuat
  -> agent doc log/file
  -> luu dem local
  -> gui event sang QCVL tren NAS
  -> QCVL POS production queue
  -> nhan vien kiem tra va tao bill
```

## Quyet dinh da chot

1. V2 van giu nhiem vu doc log/file tu may san xuat.
2. V2 khong tu tao hoa don KiotViet.
3. V2 khong dung KiotViet trong luong chinh nua.
4. V2 khong tu gui tin nhan Zalo cho khach.
5. V2 chi day du lieu may sang QCVL POS de nhan vien kiem tra va nhap bill.
6. QCVL la noi thay POS/KiotViet ve sau.
7. QCVL chay Node API + PostgreSQL tren NAS.
8. `Z:\Tools` truoc mat duoc chuan hoa thanh agent/bridge an toan, chua thay QCVL.
9. QCVL chua sua trong giai doan nay; chi chuan bi contract, payload mau va checklist.
10. Khong cho QCVL dieu khien nguoc may san xuat trong giai doan dau.
11. May tram phai ghi event vao SQLite outbox local truoc khi gui di.
12. Moi event gui ra ngoai phai co `event_id`/`idempotency_key` de retry khong tao trung.
13. Ten may du phong/doi main duoc khai bao bang `QLX_MACHINE_ALIASES`, khong sua code.

## Ranh gioi V2

V2 nen lam:

- Doc event tu InBat, InDecal, CNC.
- Luu dem khi QCVL/NAS/mang loi.
- Gui lai an toan bang idempotency key.
- Co healthcheck, backup, rollback, build release.
- Co log ro de AI/nguoi van hanh chan doan.
- Co outbox local de restart/mat mang khong lam mat event.
- Healthcheck phai doc duoc so event pending trong outbox.

V2 khong nen lam:

- Tu tao bill.
- Tu thu tien/cong no.
- Tu tru kho.
- Tu gui Zalo cho khach.
- Tu sua du lieu QCVL.
- Phu thuoc QCVL de may san xuat tiep tuc chay.

## Kien truc dich

```text
May InBat / InDecal / CNC
  -> QuanLyXuong V2 agent
  -> NAS QCVL API
  -> PostgreSQL production_* tables
  -> POS production queue
  -> bill QCVL do nhan vien xac nhan
```

## Cach chuyen doi an toan

1. Chuan hoa V2 trong `Z:\Tools`.
2. Build V2 vao `dist-new`, khong ghi de `dist` dang chay.
3. Chay dry-run bridge va xuat payload mau.
4. Khi QCVL san sang, them API/table production ben QCVL.
5. Cho V2 gui thu sang QCVL staging/NAS.
6. Chay song song voi he cu.
7. Tat Auto_CRM/KiotViet/Zalo auto khoi luong chinh.
8. Chuyen tung may sang V2, co rollback ve ban cu.

## Dinh nghia V2 san sang thay ban cu

- Healthcheck OK.
- Quality gate OK.
- Build 5 exe OK.
- Backup DB OK.
- Rollback da test.
- Bridge dry-run co payload dung.
- Auto_CRM khong con nam trong luong chinh.
- Co cach tat/bat bridge rieng.
- Loi QCVL khong lam mat event may san xuat.
- Hostname that cua may san xuat map dung InBat/InDecal/CNC.

## Quyet dinh bo sung ngay 2026-07-10

### Runtime va van hanh

1. Server V2 chay bang NSSM service `khoidongbot`.
2. Web van hanh xem tai `http://192.168.1.104:5000/`.
3. V2 runtime chay cac thanh phan chinh:
   - `server_Local.exe` tren cong `8000`.
   - `Dashboard_Local.exe` tren cong `5000`.
   - `cnc_legacy_bridge.exe` cho CNC Win 7 32-bit.
4. `Auto_CRM` khong con nam trong luong V2 chinh.
5. `Auto_CRM` chi giu de build/rollback/tham khao, khong tu chay trong V2.
6. Khong bao Zalo cap nhat/lien tuc nua; trang `:5000` la noi xem trang thai V2.

### Trang thai va phan loai loi

1. `Xoa thao tac` khong tinh la loi san xuat.
2. Chi `Huy/Loi khi chay` moi tinh vao loi san xuat.
3. File bi xoa khi con o `EXPORTED`/`RIP` la thao tac xoa file xuat, khong phai hang loi.
4. File bi xoa khi dang `PRINTING`/`CUTTING` la huy/loi san xuat.
5. Neu file da co `DONE` truoc do, nhung thoi gian `PRINTING -> DONE` qua ngan so voi dien tich/mau cung loai, khong tin la da xong that.
6. Truong hop `DONE` qua nhanh roi sau do `PRINTING -> DELETE` phai giu o `Huy/Loi khi chay`, kem canh bao can kiem tra tin hieu/may.
7. Truong hop `DONE` binh thuong roi sau do co tin hieu `PRINTING -> DELETE` moi duoc xem la tin hieu in lai sau DONE bi xoa, khong tinh loi san xuat.
8. Canh bao `DONE qua nhanh` phai dua vao lich su file cung may va dien tich gan tuong duong; khong dung san thoi gian co dinh cho moi file, vi file decal nho co the DONE dung trong khoang 1 phut.
9. CNC file mau/cat ngan co ten dang `ngang chuan dut` duoc xem la dung diem dung du kien, khong mac dinh tinh la hang hong khi log ket thuc bang DELETE sau CUTTING.

### Tinh tien do va hao hut

1. Neu log/event co `progress_percent` that, dung gia tri do.
2. Neu khong co `%` that, uoc tinh bang thoi gian da chay / thoi gian DONE trung binh cua file cung may va dien tich gan tuong duong.
3. Neu khong du mau so sanh hoac khong co kich thuoc file, hien `Tien do: chua ro`.
4. `% uoc tinh` chi de hien thi/phan tich, khong ghi de du lieu goc.
5. `estimated_bad_m2` = dien tich file * `% loi uoc tinh`.
6. Thong ke `Ti le m2 hong uoc tinh` tinh theo cong thuc:

```text
m2_hong_uoc_tinh / (m2_hoan_thanh + m2_hong_uoc_tinh) * 100
```

7. Khong tinh ti le loi bang so file nua, vi khong dung thuc te san xuat.
8. Rieng job CNC/TAP dang chay:
   - Neu may khong tra `%` that va chua co mau DONE phu hop, Dashboard duoc uoc tinh bang `machine_meta_json.line_count`.
   - Nguong fallback hien tai: thoi gian du kien = `max(180 giay, line_count / 9)`.
   - Label bat buoc co chu `ước tính`, vi day khong phai `%` that tu may.
   - Vi du `f3_120x75.tap` co `line_count=3339`; sau 186 giay tu moc `CUTTING`, Dashboard hien khoang `50% ước tính`.

### In lai va so luong dung

1. Ten co `_x2`, `_x5`, `_SL`, `_xSL` la so luong dung neu so lan in bang so do.
2. In dung so luong khai bao khong can xac nhan loi.
3. Chi can xac nhan khi file khong khai bao so luong ma in xong nhieu lan.
4. Neu mot lan xong va mot lan huy, khong mac dinh la in lai that; phai xet thoi gian/tin hieu.

### Thumbnail va preview

1. Card tren dashboard chi hien ten ngan; hover de xem anh, click de ghim anh va chi tiet.

## Quyet dinh bo sung ngay 2026-07-11 - Chong replay InBat

1. Event tu may tram phai co `event_time`, `event_id`, `idempotency_key` ngay luc phat sinh.
2. `event_id/idempotency_key` khong dung UUID ngau nhien cho event san xuat moi; phai tao co dinh theo:
   - machine
   - event_type
   - path hoac forced_base_id
   - event_time
3. Server van phai tu tao `logical_event_key` de chan replay neu client cu/gui lai cung event nhung UUID khac.
4. Server khong dung ngay hien tai de hash job neu request co ngay that. Thu tu lay ngay:
   - `event_time`
   - ngay trong path file
   - ngay hien tai cua server neu khong co du lieu nao khac.
5. Event cu replay sang ngay moi khong duoc tao bucket ngay moi.
6. DONE lap lai cung machine/path/event_time/status phai bi bo qua, khong tang `run_count`.
7. DONE lan 2 that van duoc tinh neu co `event_time` khac.
8. Khi InBat dang tat, chi duoc fix phan server/source co test; phan PrintMon live/outbox local doi may mo moi doc.
2. Khi file DELETE doi sang hash moi, server phai giu/copy thumbnail tu hash cu sang hash moi.
3. File da xoa ma khong con file goc va khong co thumbnail cu thi khong the phuc hoi anh.
4. CNC `.tap` khong mac dinh co anh preview nhu file in; can nguon hinh rieng neu muon xem anh.
5. Khi thieu thumbnail, dashboard phai hien ly do cu the neu biet duoc: file goc con nhung tao preview loi, hay file goc da bi xoa/server khong truy cap duoc.
6. Thumbnail cua InDecal phai tao tu may tram khi co `EXPORT/RIP`; server khong doc truc tiep duoc o `D:\...` cua may InDecal.
7. Ten InDecal co so thu tu dang `13~tenfile.prn` phai tim file goc theo phan sau dau `~` (`tenfile.tif`), khong tim theo so `13.tif`.
8. Neu log InDecal chi gui ten file khi `PRINTING/DONE`, server phai giu lai `file_path` day du da nhan tu `RIP`, khong ghi de bang ten ngan.

### Loi can audit sau rieng cho InDecal

1. So truoc dau `~` cua InDecal khong on dinh va khong duoc xem la ID chac chan.
   - Vi du da thay: `RIP` co `4~xd_148x552.prn`, nhung luc `PRINTING/DONE` log lai ra `7~xd_148x552.prn`.
   - Khi ghep job phai uu tien phan sau dau `~` va thoi gian gan nhat, khong tin so dau.
2. Doi ten `.prn` co the tao `DELETE` gia.
   - Vi du da thay: cung thoi diem co `RIP d:\...\16~hh2_117x230.prn` va `DELETE d:\...\16.prn`.
   - Day co kha nang la file cu bien mat do rename, khong phai tho huy/xoa.
3. Server co the tach mot job thanh hai dong DB khi `PRINTING/DONE` chi gui ten ngan.
   - Vi du da thay: `19~huong_121x240.prn` co mot dong `RIP -> PRINTING -> DELETED`, sau do mot dong moi `PRINTING -> DONE`.
   - Can xem day la in lai that, huy roi in lai, hay server ghep sai.
4. `forced_base_id` da duoc client gui len nhung server chua dung day du de ghep record.
   - Day la diem yeu khi log InDecal chi co ten ngan.
5. Renamer dang chon meta moi nhat trong thu muc (`meta_files[0]`), co nguy co gan nham meta neu nhieu file RIP gan nhau.
6. Neu chua thay meta, code co nhanh gui `RIP` cho `.prn` tron.
   - Co nguy co file bi danh dau processed qua som, sau do kho doi ten lai dung.
7. Sau khi doi ten mot file, code dang xoa rong `meta_files`.
   - Co nguy co xoa nham meta cua file khac dang cho.
8. Loi rename dang bi nuot im lang bang `except: pass` hoac retry am tham.
   - Can hien loi tren dashboard: file nao, loi gi, dang bi khoa/trung ten/mat meta/khong tim thay file goc.
9. Preview phu thuoc rename dung.
   - Neu rename cham/sai, file goc `.tif` co the khong duoc move vao `New Folder`, thumbnail thieu hoac gan khong chac.

### Huong dao sau tiep cho InDecal

1. Do timeline that theo tung job:
   - `EXPORT tif`
   - meta xuat hien
   - `.prn` xuat hien trong `New Folder`
   - file on dinh kich thuoc
   - rename `.prn -> so~ten.prn`
   - move `.tif` vao `New Folder`
   - gui `RIP`
   - log `PRINTING`
   - log `DONE/DELETE`
2. Them audit tam thoi de ghi ro:
   - thoi gian cho meta
   - thoi gian cho file `.prn` on dinh
   - rename thanh cong/that bai
   - ly do that bai: file dang khoa, trung ten, khong co meta, meta qua cu, khong tim thay tif goc.
3. Xac dinh nguong thoi gian:
   - bao lau thi coi la `dang cho meta`
   - bao lau thi coi la `ket doi ten`
   - bao lau thi duoc gui `RIP` neu khong co meta.
4. Sau khi co log audit that, moi sua rule chinh de tranh doan mo.

### QCVL

1. Chua sua QCVL trong giai doan chuan hoa V2.
2. Viec noi sang QCVL se lam o du an QCVL khi V2 agent/server on dinh.
3. V2 hien tai uu tien doc log, giu event, dashboard, rollback, va thong ke dung truoc.

## Quyet dinh bo sung ngay 2026-07-13 - InDecal rename/RIP audit

1. Uu tien InDecal audit rename/RIP truoc khi sua rule chinh.
2. Khong doan loi rename/RIP bang thoi gian `EXPORT/RIP/PRINTING/DONE` cu nua, vi thieu moc trung gian.
3. Can ghi audit rieng cho cac moc:
   - PRN cho on dinh.
   - khong co meta.
   - meta duoc chon.
   - rename OK/FAIL.
   - move anh goc OK/FAIL.
   - cleanup meta OK/FAIL.
4. Audit khong duoc chan san xuat; neu gui server loi thi van ghi local va bo qua loi mang.
5. Server dung DB rieng `indecal_rename_audit.db`.
6. Dashboard hien muc `InDecal rename/RIP` trong man hinh he thong/log.
7. Chi chot nguong `ket doi ten`, `gui RIP tron`, `meta qua cu` sau khi co du lieu audit san xuat that.
8. Trang thai trien khai ngay 2026-07-13:
   - code/test/build audit da xong.
   - server endpoint audit live OK.
   - dashboard/client con cho go lock process/file cu hoac reboot de len live hoan toan.

## Quyet dinh bo sung ngay 2026-07-14 - Dashboard compact/report

1. Dashboard la man hinh van hanh chinh, uu tien goi gon trong mot viewport.
2. Sidebar ben trai chi hien thong tin can nhin nhanh:
   - May san xuat: trang thai tung may va so dang/cho/xong/ton cu.
   - Thong ke: tong va tung may.
   - Khach hang top ngan gon.
3. O `Thong ke`:
   - Tong hien mot hang: `Tong | hoan thanh | loi`.
   - Khong hien chu phu `Hoan thanh`/`Loi` trong o tong de tiet kiem chieu cao.
   - So tong phai lon hon va tach mau: hoan thanh mau xanh, loi mau do/hong.
   - Tieng `Loi m2 %` rieng trong sidebar bi bo, vi loi da hien ro o tong va tung may.
4. Metric `So luong`/`m2` dieu khien dong thoi:
   - tong hoan thanh;
   - tong loi;
   - hoan thanh/loi tung may;
   - bieu do don hang va top khach hang.
5. Loi theo may:
   - Khi chon `So luong`, hien so job loi/huy san xuat.
   - Khi chon `m2`, hien m2 hong uoc tinh.
   - Khong dem cac dong xoa thao tac/cleanup da in xong vao loi san xuat.
6. Bao cao khach hang:
   - Top 10 theo metric dang chon.
   - Bam mot cot khach hang se loc bieu do don hang theo thoi gian va theo may cho dung khach do.
   - Phan chi so duoi cung hien theo khach dang chon hoac tong neu khong chon khach.
7. Bieu do theo thoi gian:
   - Voi khoang ngay dai, truc duoi duoc rut gon nhan cho de doc.
   - Du lieu van ve theo ngay that, khong gom sai thanh duong thang theo thang.
   - Khong hien doan rong truoc moc dau tien co du lieu trong khoang loc.
8. Danh sach san xuat:
   - API `/api/data` ho tro `limit`.
   - Dashboard tai 20 the dau, cuon/bam de tai tiep.
   - Badge/count va thong ke van dung tong that, khong phu thuoc so the dang render.
   - Cot `Hang cho` trong dashboard compact hien tab tong `Hang cho`, kem tab con `Xuat/RIP/Dang chay`; header van la tong hang cho.
   - Cot `Loi / thao tac` hien tab tong `Loi / thao tac`, kem tab con `Huy/Loi`; header van la tong loi + thao tac, danh sach hien theo tab dang chon.
9. Loading:
   - Doi bo loc phai co dau hieu dang tai.
   - Ket qua request cu bi bo qua neu co request moi hon, tranh nhay nguoc du lieu.
10. He thong/log:
   - Gop tab `He thong` va `Log` thanh mot tab `He thong`.
   - Cac nguon nhu Outbox, Phien ban, Ghi chu, server, dashboard, machine, qcvl_bridge nam tren mot hang chon nguon.
   - Phien ban chi hien lich su inline khi chon mot may, khong hien panel lich su rong mac dinh.
11. Deploy dashboard-only:
   - Neu chi doi giao dien/API Dashboard, chi build/copy/restart `Dashboard_Local.exe`.
   - Khong restart server hoac client may san xuat khi khong can.
   - Luon chay unit test va browser smoke truoc khi bao xong.

## Quyet dinh bo sung ngay 2026-07-14 - Bao cao m2 theo khach

1. Loi goc da gap voi `QUOCHOANG`:
   - File `quochoang_366x2544.prt` bi parser cu doc la `366 x 2544 cm`.
   - Ket qua thanh `93.1104 m2`, lam top khach va bieu do khach lech thanh `99.59 m2`.
   - Thuc te phai hieu `2544` la `254.4 cm` trong truong hop outlier, nen file nay la `9.31104 m2`.
2. Day la loi tinh m2 tu ten file, khong phai loi trang thai may.
3. Nguon tinh m2:
   - Uu tien `machine_meta_json.area_m2` neu co, vi day la meta doc tu file/may that.
   - Neu khong co meta thi moi parse ten file.
   - Neu parse ten file tao ra m2 qua lon bat thuong va co chieu 4 chu so, can ap dung rule outlier thay vi tin tuyet doi ten file.
4. Khong sua rieng theo ten khach.
   - Rule phai ap dung cho moi khach co mau ten tuong tu.
   - Test phai co it nhat 1 mau khach that va 1 mau khach khac de tranh hard-code.
5. Test neo hien tai:
   - `quochoang_366x2544.prt` -> `9.31104 m2`.
   - `NTDQq_800x310.prt` -> `24.8 m2`.
6. Khi nguoi dung bao "khach X sai du lieu", quy trinh bat buoc:
   - Tim cac file cua khach do trong DB.
   - So sanh `machine_meta_json.area_m2`, kich thuoc that trong meta, va m2 parse tu ten file.
   - Neu chenh lech lon, sua parser/rule chung va them test bang file that.
   - Chay lai `/api/stats` de doi chieu top khach, chi so khach, va bieu do drill-down.
