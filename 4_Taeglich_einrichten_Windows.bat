@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Stellen-Radar - taeglichen Abruf einrichten
if not exist ".venv\Scripts\pythonw.exe" (
  echo Bitte zuerst 1_Installieren_Windows.bat ausfuehren.
  pause
  exit /b 1
)
set "ZEIT="
set /p ZEIT=Um wie viel Uhr soll der Abruf taeglich laufen? (z.B. 07:00, Enter = 07:00): 
if "%ZEIT%"=="" set "ZEIT=07:00"
set "ORDNER=%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$a = New-ScheduledTaskAction -Execute ($env:ORDNER + '.venv\Scripts\pythonw.exe') -Argument 'abruf.py' -WorkingDirectory $env:ORDNER;" ^
  "$t = New-ScheduledTaskTrigger -Daily -At $env:ZEIT;" ^
  "$s = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 2);" ^
  "Register-ScheduledTask -TaskName 'Stellen-Radar Abruf' -Action $a -Trigger $t -Settings $s -Description 'Taeglicher Abruf Stellen-Radar' -Force | Out-Null"
if errorlevel 1 (
  echo.
  echo Das Einrichten hat nicht geklappt. Bitte die Anleitung "Variante B" in ANLEITUNG.md verwenden.
  pause
  exit /b 1
)
echo.
echo Eingerichtet: Der Abruf laeuft ab jetzt taeglich um %ZEIT% Uhr.
echo War der PC um diese Zeit aus, wird der Abruf beim naechsten Start nachgeholt.
echo Sie finden die Aufgabe in der Windows-Aufgabenplanung unter "Stellen-Radar Abruf".
pause
