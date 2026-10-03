@echo off
chcp 65001 >nul
powershell -NoProfile -ExecutionPolicy Bypass -Command "Unregister-ScheduledTask -TaskName 'Stellen-Radar Abruf' -Confirm:$false"
echo Der taegliche Abruf wurde entfernt.
pause
