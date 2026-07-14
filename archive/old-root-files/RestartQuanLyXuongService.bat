@echo off
title RESTART QUAN LY XUONG SERVICE
powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process powershell -Verb RunAs -ArgumentList '-NoProfile -ExecutionPolicy Bypass -Command ""Restart-Service -Name khoidongbot -Force; Start-Sleep -Seconds 15; Get-Service khoidongbot; Get-NetTCPConnection -LocalPort 5000 -State Listen""'"
