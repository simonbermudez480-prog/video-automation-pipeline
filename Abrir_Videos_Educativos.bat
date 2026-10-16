@echo off
rem Abre la interfaz de Videos Educativos sin ventana de comandos.
cd /d "%~dp0"
if exist "%~dp0tools\ffmpeg\bin\ffmpeg.exe" set "PATH=%~dp0tools\ffmpeg\bin;%PATH%"
if exist "%~dp0.venv\Scripts\pythonw.exe" (
    start "" "%~dp0.venv\Scripts\pythonw.exe" app.py
    exit /b
)
where pythonw >nul 2>&1
if %errorlevel%==0 (
    start "" pythonw app.py
) else (
    start "" python app.py
)
