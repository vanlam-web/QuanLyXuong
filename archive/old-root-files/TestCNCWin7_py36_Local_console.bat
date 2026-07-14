@echo off
title TEST CNC WIN7 32BIT CONSOLE

echo [0] Dang tat tien trinh cu...
taskkill /F /IM QuanLyXuong_Local.exe /T >nul 2>&1
taskkill /F /IM QuanLyXuong_CNC_Win7_py36_x86_console.exe /T >nul 2>&1

echo [1] Dang ket noi NAS...
net use \\192.168.1.188\AI Lam650909@1 /user:adminnas >nul 2>&1

echo [2] Dang copy ban console ve local...
if not exist "C:\QuanLyXuong" mkdir "C:\QuanLyXuong"
set QLX_NAS_CLIENT_EXE_PATH=\\192.168.1.188\AI\Tools\dist\QuanLyXuong_CNC_Win7_py36_x86.exe
copy /Y "\\192.168.1.188\AI\Tools\dist\QuanLyXuong_CNC_Win7_py36_x86_console.exe" "C:\QuanLyXuong\QuanLyXuong_Local.exe"

echo [3] Dang chay console. Neu loi, chup/man hinh gui lai.
"C:\QuanLyXuong\QuanLyXuong_Local.exe"
pause
