@echo off
title HE THONG QUAN LY XUONG CNC WIN7 32BIT - DANG CHAY...

echo [0] Dang tat tien trinh cu...
taskkill /F /IM QuanLyXuong_Local.exe /T >nul 2>&1
taskkill /F /IM QuanLyXuong_CNC_Win7_py36_x86.exe /T >nul 2>&1
taskkill /F /IM QuanLyXuong_CNC_Win7_py36_x86_console.exe /T >nul 2>&1

echo [1] Dang doi Windows nha file...
timeout /T 2 /NOBREAK >nul

echo [2] Dang ket noi NAS...
net use \\192.168.1.188\AI Lam650909@1 /user:adminnas >nul 2>&1

echo [3] Dang copy ban CNC Win7 32-bit ve local...
if not exist "C:\QuanLyXuong" mkdir "C:\QuanLyXuong"
set QLX_NAS_CLIENT_EXE_PATH=\\192.168.1.188\AI\Tools\dist\QuanLyXuong_CNC_Win7_py36_x86.exe
copy /Y "\\192.168.1.188\AI\Tools\dist\QuanLyXuong_CNC_Win7_py36_x86.exe" "C:\QuanLyXuong\QuanLyXuong_Local.exe"

echo [4] Dang khoi dong client local...
"C:\QuanLyXuong\QuanLyXuong_Local.exe"
