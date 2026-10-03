@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Stellen-Radar - Installation
echo ============================================
echo   Stellen-Radar wird eingerichtet ...
echo ============================================
echo.
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY (
  where python >nul 2>nul && set "PY=python"
)
if not defined PY goto :keinpython
%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
if errorlevel 1 goto :keinpython

if not exist ".venv\Scripts\python.exe" (
  echo Lege Programmumgebung an ...
  %PY% -m venv .venv
  if errorlevel 1 goto :fehler
)
echo Installiere benoetigte Pakete (dauert einige Minuten) ...
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :fehler
echo.
echo ============================================
echo   Fertig! Starten Sie jetzt
echo   2_Dashboard_starten_Windows.bat
echo ============================================
pause
exit /b 0

:keinpython
echo Python (Version 3.10 oder neuer) wurde nicht gefunden.
echo Bitte Python von https://www.python.org/downloads/ installieren
echo und dabei "Add python.exe to PATH" ankreuzen. Danach diese Datei erneut starten.
pause
exit /b 1

:fehler
echo.
echo FEHLER bei der Installation. Bitte Internetverbindung pruefen und erneut versuchen.
pause
exit /b 1
