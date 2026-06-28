# Quan Ly Xuong

He thong noi bo quan ly luong san xuat, dashboard, Auto CRM va gui Zalo qua OpenClaw.

## Cau hinh can dat ngoai Git

Khong commit mat khau/PIN/group that vao repo. Dat cac bien moi truong sau tren may chay:

```text
KIOT_USERNAME
KIOT_PASSWORD
AUTO_CRM_ZALO_GROUP_ID
SERVER_ZALO_TARGET
DASHBOARD_ADMIN_PIN
```

Xem `.env.example` va `KhoiDongBot.example.bat` de biet mau cau hinh.

## Luong tong quan

```text
QuanLyXuong.exe -> server.exe -> Dashboard.exe
                       |
                       v
                  Auto_CRM.exe -> OpenClaw -> Zalo
```

Bao cao chi tiet nam trong `BAO_CAO_LUONG_HE_THONG.md`.
