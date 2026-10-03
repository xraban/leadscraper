@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Stellen-Radar - Dashboard
if not exist ".venv\Scripts\python.exe" (
  echo Bitte zuerst 1_Installieren_Windows.bat ausfuehren.
  pause
  exit /b 1
)
echo Das Dashboard oeffnet sich gleich im Browser.
echo Dieses Fenster bitte OFFEN LASSEN - Schliessen beendet das Dashboard.
echo.
".venv\Scripts\python.exe" stellenradar_starten.py
pause
