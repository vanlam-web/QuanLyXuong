@echo off
set QLX_NAS_CLIENT_EXE_PATH=\\192.168.1.188\AI\Tools\dist\QuanLyXuong_CNC_Win7_py36_x86.exe
if not exist C:\QuanLyXuong mkdir C:\QuanLyXuong
copy /Y "\\192.168.1.188\AI\Tools\dist\QuanLyXuong_CNC_Win7_py36_x86.exe" "C:\QuanLyXuong\QuanLyXuong_CNC_Win7_py36_x86.exe"
start "" "C:\QuanLyXuong\QuanLyXuong_CNC_Win7_py36_x86.exe"
