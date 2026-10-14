@echo off
chcp 65001 >nul
cd /d "%~dp0"

set "PY="
if exist "venv\Scripts\python.exe" (
    "venv\Scripts\python.exe" -c "import discord, yt_dlp, nacl, dotenv" >nul 2>&1
    if not errorlevel 1 set "PY=venv\Scripts\python.exe"
)
if not defined PY (
    python -c "import discord, yt_dlp, nacl, dotenv" >nul 2>&1
    if not errorlevel 1 set "PY=python"
)
if not defined PY (
    echo [HATA] Once start.bat ile kurulumu tamamla.
    exit /b 1
)

if not exist "logs" mkdir "logs"
rem bot.log'u yalnizca Python yazici kullanir; buradaki ciktilar ayrildedir.
"%PY%" "%~dp0bot.py" >> "logs\stdout.log" 2>&1
