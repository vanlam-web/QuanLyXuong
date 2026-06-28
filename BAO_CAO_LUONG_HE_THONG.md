# Bao cao luong he thong Quan Ly Xuong

Ngay lap: 2026-06-28

## Tong quan

He thong hien tai gom 4 phan chinh:

```text
QuanLyXuong.exe  ->  server.exe  ->  Dashboard.exe
                         |
                         v
                    Auto_CRM.exe
                         |
                         v
                      OpenClaw -> Zalo
```

## 1. Luong may san xuat

Tren tung may `inbat`, `indecal`, `cnc`, chuong trinh `QuanLyXuong.exe` chay nhu client.

No tu nhan biet may bang hostname:

```text
inbat   -> InBat
indecal -> InDecal
cnc     -> CNC
```

Sau do no quet file va doc log may:

- In Bat: doc `PrintFile.ini` hoac `PrintFile` cua PrintMon.
- In Decal: doc log ngay cua `PrintExp`.
- CNC: doc `Ncstudio.log`.

Khi thay su kien, no gui ve server:

```text
EXPORT / RIP / PRINTING / CUTTING / DONE / DELETE
```

Server nhan qua:

```text
http://192.168.1.104:8000/api/log_event
```

## 2. Luong server trung tam

`server.exe` chay FastAPI port `8000`.

No nhan event tu client, xu ly roi luu vao SQLite:

```text
C:\QuanLyXuong\Data\InBat.db
C:\QuanLyXuong\Data\InDecal.db
C:\QuanLyXuong\Data\CNC.db
```

Trang thai chuan:

```text
EXPORTED -> RIP -> PRINTING/CUTTING -> DONE
                         |
                         v
                      DELETED
```

Server cung lam cac viec:

- Gui bao cao Zalo theo gio `11:30`, `17:30`, `22:30`.
- Gui canh bao loi tu client.
- Bao khi server/client cap nhat version.
- Broadcast realtime cho dashboard.
- Khi co job `DONE`, goi Auto CRM:

```text
http://127.0.0.1:8001/wake_up
```

## 3. Luong dashboard

`Dashboard.exe` chay web port `5000`.

Dashboard doc database de hien thi:

- Xuat file.
- Da RIP.
- Dang chay.
- Da xong.
- Huy/loi.
- Thumbnail.
- Timeline tung file.
- Tong m2.
- Thong ke khach hang, san luong, gio lam.
- Export CSV.
- Admin doi trang thai bang PIN.

Dashboard cap nhat realtime qua WebSocket tu server:

```text
/ws/dashboard
```

## 4. Luong Auto CRM

`Auto_CRM.exe` chay port `8001`, cho server goi `/wake_up`.

Khi duoc danh thuc, no:

1. Doc cac job `DONE` trong `InBat.db` va `InDecal.db`.
2. Kiem tra da xu ly chua bang `crm_memory.json`.
3. Parse ten file de lay ma khach, chat lieu, kich thuoc, so luong.
4. So voi `DanhBa_VIP.json` va `Map_ChatLieu.json`.
5. Neu thieu kich thuoc hoac chat lieu chua khai bao thi bao Zalo noi bo va bo qua.
6. Neu hop le thi mo Chrome/Selenium vao KiotViet.
7. Tao bill, chot thanh toan `0`.
8. Chup anh bill.
9. Gui bill/tin nhan cho Zalo khach hoac nhom bang OpenClaw.
10. Danh dau `zalo_sent = 1` trong database.

## 5. Vai tro OpenClaw

OpenClaw khong phai loi quan ly xuong. No la cong gui Zalo.

Server va Auto CRM deu goi:

```text
openclaw message send --channel zalouser --target ...
```

Nghia la:

```text
Phan mem xuong -> OpenClaw -> Zalo ca nhan/nhom
```

Hien tai chieu nhan tin tu nguoi la/nhom da duoc tat:

```json
{
  "dmPolicy": "disabled",
  "groupPolicy": "disabled"
}
```

Chieu gui tin tu dong ra Zalo van dung duoc.

## 6. Diem manh

He thong rat sat nghiep vu that cua xuong. No gom duoc vong doi san xuat:

- Xuat file.
- RIP.
- In/cat.
- Hoan thanh.
- Dashboard.
- Bao cao.
- CRM.
- Gui bill.

Voi phan mem noi bo, day la luong rat co gia tri.

## 7. Diem rui ro lon

Rui ro chinh:

- Nhieu mat khau, IP, PIN, group Zalo hardcode trong source.
- Rat nhieu `except: pass`, loi co the bi nuot mat.
- Doc log may in/cat phu thuoc format log va encoding.
- KiotViet phu thuoc giao dien web; neu KiotViet doi UI thi Auto CRM co the ket.
- Auto update dang co cho kill `server_Local.exe` tu nhieu app, de gay restart day chuyen.
- Neu OpenClaw/Zalo mat session, viec gui tin se loi.
- Neu hostname/IP doi, client co the khong chay dung.

## 8. Ket luan

Phan mem nay la mot he thong noi bo thuc chien, dang giai quyet dung bai toan xuong. Luong tong the hop ly, nhung do ben va bao tri con phu thuoc nhieu vao moi truong co dinh.

Nen nang cap dan theo huong:

- Tach config rieng.
- Log loi ro hon.
- Them health check cho log may, OpenClaw, KiotViet.
- Backup database tu dong.
- Quan ly khach/chat lieu bang giao dien thay vi sua JSON tay.
