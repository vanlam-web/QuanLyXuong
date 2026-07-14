@echo off
title CAP NHAT DASHBOARD PREVIEW CNC
powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process powershell -Verb RunAs -ArgumentList '-NoProfile -ExecutionPolicy Bypass -File ""Z:\Tools\scripts\Restart-DashboardV2.ps1""'"
