@echo off
rem Crea el paquete para otra PC (dist\VideosEducativos_Instalador.exe).
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0empaquetar.ps1"
echo.
pause
