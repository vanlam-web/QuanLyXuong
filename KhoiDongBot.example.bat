@echo off
title HE THONG QUAN LY XUONG - DANG CHAY...

taskkill /F /IM QuanLyXuong_Local.exe /T >nul 2>&1
timeout /T 2 /NOBREAK >nul

REM Configure NAS credentials outside git, then replace these placeholders locally.
net use \\192.168.1.188\AI YOUR_NAS_PASSWORD /user:YOUR_NAS_USER >nul 2>&1

if not exist "C:\QuanLyXuong" mkdir "C:\QuanLyXuong"
copy /Y "\\192.168.1.188\AI\Tools\dist\QuanLyXuong.exe" "C:\QuanLyXuong\QuanLyXuong_Local.exe"

"C:\QuanLyXuong\QuanLyXuong_Local.exe"

