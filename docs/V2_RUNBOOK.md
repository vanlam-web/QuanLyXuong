# V2 runbook

Muc tieu: chay QuanLyXuong theo huong V2 ma khong tu tao bill KiotViet va khong tu gui Zalo.

## Bat V2 mode tren may chay server

Dry-run xem bien se dat:

```powershell
powershell -ExecutionPolicy Bypass -File Z:\Tools\scripts\Set-V2Mode.ps1
```

Bat V2 mode:

```powershell
powershell -ExecutionPolicy Bypass -File Z:\Tools\scripts\Set-V2Mode.ps1 -Apply
```

Dong va mo lai terminal/app sau khi dat env.

Quay ve legacy mode:

```powershell
powershell -ExecutionPolicy Bypass -File Z:\Tools\scripts\Set-V2Mode.ps1 -Legacy -Apply
```

## Kiem tra san sang V2

```powershell
powershell -ExecutionPolicy Bypass -File Z:\Tools\scripts\Test-V2Readiness.ps1
```

Ket qua mong muon:

```text
V2 readiness OK
```

Neu thay `[WARN]`, chua nen publish V2 vao `dist`.

## Luong V2

```text
QuanLyXuong.exe
  -> server.exe
  -> SQLite C:\QuanLyXuong\Data
  -> bridge_qcvl.py dry-run/gui co kiem soat
```

Khong chay trong luong V2:

```text
Auto_CRM.exe
KiotViet Selenium
Zalo auto cho khach
```

## Khoi dong V2 runtime tren may server

Chay file:

```text
Z:\Tools\KhoiDongV2Runtime.bat
```

Hoac chay lenh:

```powershell
powershell -ExecutionPolicy Bypass -File Z:\Tools\scripts\Start-V2Runtime.ps1 -Restart
```

Lenh nay:

- copy `server.exe` thanh `C:\QuanLyXuong\server_Local.exe`
- copy `Dashboard.exe` thanh `C:\QuanLyXuong\Dashboard_Local.exe`
- copy `bridge_qcvl.exe` neu file nay co trong `dist`
- start server va dashboard theo V2 env trong process
- khong start `Auto_CRM.exe`

## Khoi dong V2 tren may san xuat

Khong chay truc tiep `\\192.168.1.188\AI\Tools\dist\QuanLyXuong.exe`.
Neu chay truc tiep tu NAS, file bi khoa va lan deploy sau co the fail.

Tren moi may InBat/InDecal/CNC, dung launcher nay:

```powershell
powershell -ExecutionPolicy Bypass -File \\192.168.1.188\AI\Tools\scripts\Start-WorkstationClient.ps1
```

Launcher nay:

- copy `QuanLyXuong.exe` tu NAS ve `C:\QuanLyXuong\Client`
- verify hash theo `BUILD_MANIFEST.json`
- chay ban local `C:\QuanLyXuong\Client\QuanLyXuong.exe`
- khong khoa file exe tren NAS

Sau khi chay, dashboard `:5000 -> He thong` phai thay version may va co `agent_outbox_<may>.db`.

Neu muon bridge chay dry-run loop cung luc:

```powershell
powershell -ExecutionPolicy Bypass -File Z:\Tools\scripts\Start-V2Runtime.ps1 -Restart -StartBridge
```

## Truoc khi publish V2

Chay:

```powershell
powershell -ExecutionPolicy Bypass -File Z:\Tools\scripts\Invoke-V2Preflight.ps1
```

Lenh nay gom quality gate, healthcheck, V2 readiness va payload sample. Sau do moi build:

```powershell
powershell -ExecutionPolicy Bypass -File Z:\Tools\scripts\Build-Release.ps1 -Clean
```

## Khi QCVL chua san sang

Giu:

```text
QCVL_BRIDGE_DRY_RUN=1
```

Chi xuat payload mau:

```powershell
powershell -ExecutionPolicy Bypass -File Z:\Tools\scripts\Export-QcvlBridgeSample.ps1
```

## Khi QCVL san sang sau nay

Chi bat gui that sau khi QCVL co:

- `POST /api/v1/production-events`
- PostgreSQL `production_*`
- POS production queue doc DB that
- token/API URL da test staging

Luc do moi dat:

```text
QCVL_BRIDGE_DRY_RUN=0
QCVL_API_BASE_URL=<qcvl-api-url>
QCVL_API_TOKEN=<token>
```

## Rollback

Neu V2 loi sau publish:

```powershell
powershell -ExecutionPolicy Bypass -File Z:\Tools\scripts\Rollback-Release.ps1
```
## Man hinh theo doi V2

Mo dashboard `http://<server-ip>:5000`.

Tab chinh:

- `San xuat`: theo doi file cho/chay/xong/loi. Danh sach chi render 20 the dau, cuon hoac bam dong `Con ... the cu hon` de tai tiep. Badge/count van la tong that.
- `Cho xu ly`: cac canh bao can xem lai, vi du thieu tin hieu ket thuc, DONE qua nhanh, chua ro % hong.
- `Bao cao`: top khach hang va bieu do theo thoi gian. Bam cot khach hang de loc rieng khach do. Nut `So luong/m2` doi ca bieu do, thong ke tong, loi va top khach.
- `He thong`: gom he thong va log. Chon nguon tren mot hang: Outbox, Phien ban, Ghi chu, server, dashboard, machine, qcvl_bridge.

Sidebar:

- `May san xuat`: xem nhanh may dang mo/chua mo va so dang/cho/xong/ton cu.
- `Thong ke`: dong `Tong | hoan thanh | loi` tren mot hang. Tung may `InBat/InDecal/CNC` hien hoan thanh ben trai va loi ben phai. Khi chon `m2`, loi la m2 hong uoc tinh; khi chon `So luong`, loi la so job loi/huy san xuat.
- `Khach hang`: top ngan gon theo bo loc hien tai.

Can xem trong tab `He thong`:

- `Outbox`: pending > 0 nghia la event dang cho gui lai; neu tang lien tuc thi kiem tra server/mang.
- `Phien ban`: bang version hien tai tung may; bam mot may de xem lich su inline.
- `server/dashboard/machine/qcvl_bridge`: log gan nhat theo nguon.

API may doc duoc: `http://<server-ip>:5000/api/v2_status`.

## Kiem tra khi bao cao khach/m2 sai

Trieu chung da gap:

- Khach `QUOCHOANG` tung hien `99.59 m2` vi file `quochoang_366x2544.prt` bi doc thanh `366 x 2544 cm`.
- Gia tri dung sau rule outlier la `9.31104 m2` cho rieng file nay.

Checklist:

1. Xem file cua khach trong DB may lien quan.
2. Uu tien so `area_m2` trong `machine_meta_json` neu co.
3. Neu chi con ten file, parse kich thuoc nhung phai soi outlier:
   - kich thuoc 4 chu so co the la thieu dau thap phan;
   - neu m2 vuot bat thuong, can chia lai chieu 4 chu so theo rule parser chung.
4. Khong hard-code theo ten khach. Them test bang ten file that de rule ap dung cho khach khac.
5. Sau khi sua, kiem tra lai:
   - top khach;
   - bieu do khach khi click cot;
   - chi so duoi cung theo khach;
   - sidebar thong ke theo `m2`.

## Preflight truoc khi thay V1 bang V2

Chay:

```powershell
powershell -ExecutionPolicy Bypass -File Z:\Tools\scripts\Invoke-V2CutoverPreflight.ps1
```

Script nay chi kiem tra, khong publish, khong restart.

Neu fail, khong thay ban moi. Loi hay gap:

- Chua co backup moi trong `Z:\Tools\backups\data`.
- Chua set env `QLX_RUNTIME_MODE=v2`.
- Chua set `QLX_ENABLE_AUTO_CRM=0`.
- Chua set `QLX_ENABLE_SERVER_ZALO=0`.
- Chua build du `dist-new`.

Sau khi script OK moi chay publish.
