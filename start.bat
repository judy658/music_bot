@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Muzik Botu - kurulum

echo ============================================
echo   Muzik Botu - kurulum ve baslatma
echo ============================================
echo.

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
    echo [HATA] Gerekli paketler kurulu degil:
    echo         discord.py, yt-dlp, PyNaCl, python-dotenv
    echo.
    echo Kurulum komutu:
    echo     py -m pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)

echo [1/3] Python: %PY%

echo [2/3] Ayarlar ve token kontrol ediliyor...
"%PY%" -c "import config; print('    FFmpeg: ' + str(config.FFMPEG_PATH)); print('    Onek: ' + config.PREFIX)"
if errorlevel 1 (
    echo [HATA] .env okunamadi. Dosyada DISCORD_TOKEN=... satiri olmali.
    pause
    exit /b 1
)
"%PY%" token_kontrol.py
if errorlevel 1 (
    echo.
    pause
    exit /b 1
)

echo [3/3] Bot baslatiliyor...
echo.
"%PY%" bot.py
echo.
echo Bot kapandi. Pencereyi kapatabilirsin.
pause
