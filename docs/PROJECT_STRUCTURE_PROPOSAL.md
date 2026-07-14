# Cấu trúc V2 đề xuất

Mục tiêu: thư mục `Z:\Tools` dễ nhìn, dễ update, dễ rollback, không lẫn file thử với file chạy thật.

## Hiện trạng

- Source Python, file bat chạy thật, file bat test, build output, PyInstaller workdir, backup, release đang nằm lẫn ở root.
- Nhiều thư mục `build-*`, `dist-*` là sản phẩm tạm sau các lần build thử.
- Runtime thật đang lấy file từ `Z:\Tools\dist`.
- NSSM thật đang chạy `C:\nssm\KhoiDongBot.bat`, source chuẩn nằm ở `Z:\Tools\scripts\KhoiDongBot_V2_NSSM.bat`.

## Cấu trúc hiện tại nên giữ

```text
Z:\Tools
  app\
    Auto_CRM.py
    Dashboard.py
    QuanLyXuong.py
    server.py
    bridge_qcvl.py
    cnc_legacy_bridge.py
    qlx_config.py
    qlx_outbox.py
    qlx_workstation_logic.py
    tap_preview.py
  scripts\
    *.ps1
    *.bat
  specs\
    *.spec
  tests\
    test_*.py
  docs\
    *.md
  dist\
    server.exe
    Dashboard.exe
    QuanLyXuong.exe
    cnc_legacy_bridge.exe
    bridge_qcvl.exe
  releases\
    V2.x.x\
  archive\
    old-root-files\
    old-builds\
    old-dist\
    v1-backup\
```

## Quy tắc vận hành

- `dist` là nơi NSSM copy exe chạy thật.
- `scripts` là nơi chứa lệnh vận hành.
- `app` là source code.
- `build-*` và `dist-*` cũ chỉ là đồ tạm, có thể chuyển vào `archive`.
- Không xóa file cũ ngay; move vào `archive` trước.
- Trước mỗi lần dọn hoặc update: chạy test và tạo backup manifest.

## Việc đã làm

- Đã chuyển source Python vào `app`.
- Đã chuyển build output tạm vào `archive\old-builds`.
- Đã chuyển file bat/helper cũ ở root vào `archive\old-root-files`.
- Đã chuyển tài liệu cũ ở root vào `archive\old-root-docs`.
- Đã chuyển backup V1 `05062026-1632` vào `archive\v1-backup`.
- Đã giữ `dist` ở root vì NSSM runtime đang copy exe từ đó.
- Đã giữ manifest rollback trong `archive`.

## Việc nên làm tiếp

1. Chuẩn hóa release version `V2.x.x`.
2. Tách NSSM thành service riêng nếu cần vận hành kiểu phần mềm lớn.
3. Thêm healthcheck sâu cho bridge, thumbnail, DB writable.
4. Giữ root chỉ còn README, requirements, dist, docs, scripts, tests, app, archive.

## Lưu ý

Source đã nằm trong `app`. Nếu rollback, dùng manifest `source_move_manifest_*` trong `archive`.
