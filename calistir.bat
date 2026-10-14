@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Muzik Botu

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
    echo Once start.bat calistir.
    pause
    exit /b 1
)

if not exist "logs" mkdir "logs"
echo Bot baslatiliyor...
"%PY%" bot.py
echo Bot kapandi.
pause
