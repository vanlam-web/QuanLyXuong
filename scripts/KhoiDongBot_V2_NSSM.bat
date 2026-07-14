@echo off
title HE THONG QUAN LY XUONG V2 - NSSM RUNTIME
color 0A

set NAS=\\192.168.1.188\AI
set SCRIPT=%NAS%\Tools\scripts\Start-V2RuntimeNssm.ps1
set LOCAL=C:\QuanLyXuong

if not exist "%LOCAL%" mkdir "%LOCAL%"
if not exist "%LOCAL%\Logs" mkdir "%LOCAL%\Logs"

echo Delegating NSSM runtime to PowerShell owner script...
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%" >> "%LOCAL%\Logs\KhoiDongBot_V2_NSSM.stdout.log" 2>&1
