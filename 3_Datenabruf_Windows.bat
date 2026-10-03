@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Stellen-Radar - Datenabruf
set PYTHONUTF8=1
if not exist ".venv\Scripts\python.exe" (
  echo Bitte zuerst 1_Installieren_Windows.bat ausfuehren.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" abruf.py %*
echo.
echo Fertig. Das Protokoll steht im Ordner "logs".
pause
