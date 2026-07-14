# Config runbook

Muc tieu: doi IP, port, duong dan NAS, OpenClaw, KiotViet ma khong sua code.

## File lien quan

```text
Z:\Tools\qlx_config.py
Z:\Tools\.env.example
```

`qlx_config.py` doc environment variable. Neu bien khong co, no dung default giong he hien tai.

## Bien cau hinh chinh

| Bien | Mac dinh | Vai tro |
|---|---|---|
| `QLX_RUNTIME_MODE` | `legacy` | `legacy` giu luong cu, `v2` dung khi chuan hoa V2 |
| `QLX_ENABLE_AUTO_CRM` | `1` | `0` de server khong danh thuc Auto_CRM khi job DONE |
| `QLX_ENABLE_SERVER_ZALO` | `1` | `0` de server khong gui Zalo tu dong |
| `QLX_DB_DIR` | `C:\QuanLyXuong\Data` | Thu muc DB SQLite |
| `QLX_BASE_DATA_CRM` | `C:\QuanLyXuong\Data_Auto_CRM` | Du lieu Auto CRM |
| `QLX_OPENCLAW_PATH` | `C:\Users\Admin\AppData\Roaming\npm\openclaw.cmd` | Lenh OpenClaw |
| `QLX_API_SERVER_URL` | `http://192.168.1.104:8000/api/log_event` | Client may gui event |
| `QLX_AUTO_CRM_WAKE_URL` | `http://127.0.0.1:8001/wake_up` | Server danh thuc Auto CRM |
| `QLX_SERVER_BROADCAST_URL` | `http://127.0.0.1:8000/api/broadcast` | Dashboard refresh |
| `QLX_SERVER_PORT` | `8000` | Port server cu |
| `QLX_DASHBOARD_PORT` | `5000` | Port dashboard cu |
| `QLX_AUTO_CRM_PORT` | `8001` | Port Auto CRM |
| `QLX_NAS_CLIENT_EXE_PATH` | `\\192.168.1.188\AI\Tools\dist\QuanLyXuong.exe` | Exe client tren NAS |
| `QLX_NAS_SERVER_EXE_PATH` | `\\192.168.1.188\AI\Tools\dist\server.exe` | Exe server tren NAS |
| `QLX_NAS_DASHBOARD_EXE_PATH` | `\\192.168.1.188\AI\Tools\dist\Dashboard.exe` | Exe dashboard tren NAS |
| `QLX_NAS_CRM_EXE_PATH` | `\\192.168.1.188\AI\Tools\dist\Auto_CRM.exe` | Exe Auto CRM tren NAS |
| `QLX_KIOT_URL` | `https://quangcaoinvanlam.kiotviet.vn/` | KiotViet URL |

## Profile V2

V2 dung cac flag sau:

```powershell
[Environment]::SetEnvironmentVariable("QLX_RUNTIME_MODE", "v2", "User")
[Environment]::SetEnvironmentVariable("QLX_ENABLE_AUTO_CRM", "0", "User")
[Environment]::SetEnvironmentVariable("QLX_ENABLE_SERVER_ZALO", "0", "User")
[Environment]::SetEnvironmentVariable("QCVL_BRIDGE_DRY_RUN", "1", "User")
```

V2 khong tu tao bill KiotViet va khong tu gui Zalo cho khach.

## Cach dung an toan

Trong production hien tai, co the khong set gi ca. Default van giong ban cu.

Khi can doi IP server client gui ve:

```powershell
setx QLX_API_SERVER_URL "http://IP-MOI:8000/api/log_event"
```

Sau do restart client.

## Nguyen tac

- Khong dua mat khau vao `.env.example`.
- May nao can config rieng thi set environment variable tren may do.
- Doi config xong chay healthcheck.

```powershell
powershell -ExecutionPolicy Bypass -File Z:\Tools\scripts\Test-QuanLyXuongHealth.ps1
```
