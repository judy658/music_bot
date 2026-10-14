@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Discord Bot - internet izni

echo ============================================
echo   Discord Bot - Windows guvenlik duvari
echo ============================================
echo.
echo Bu dosya python.exe icin "internet erisimi" izni ekler.
echo Yonetici (Administrator) parolasi istenebilir.
echo.

if not "%~1"=="/elevated" (
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -ArgumentList '/elevated' -Verb RunAs"
    if errorlevel 1 echo [HATA] Yonetici izni verilmedi. Kurali elle eklemelisin.
    timeout /t 3 >nul
    exit /b 0
)

echo [1/2] Python yollari icin izin ekleniyor...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$p=(Get-Command python -ErrorAction SilentlyContinue).Source; $v='%~dp0venv\Scripts\python.exe'; $list=@($p); if(Test-Path $v){$list+=$v}; foreach($x in $list){ if($x){ New-NetFirewallRule -DisplayName ('Python Discord Bot: '+$x) -Direction Outbound -Program $x -Action Allow -Profile Any | Out-Null; Write-Host ('    eklendi: '+$x) } }"
echo.

echo [2/2] Test ediliyor...
python -c "import socket; s=socket.create_connection(('discord.com',443),timeout=10); s.close(); print('    Python internet erisimi: TAMAM')"
if errorlevel 1 (
    echo.
    echo    HALA ENGELLI. Engelleyen kurallar:
    powershell -NoProfile -Command "Get-NetFirewallRule -Direction Outbound -Action Block | Format-Table DisplayName,Profile -AutoSize"
) else (
    echo.
    echo    Tamam. Simdi start.bat calistirabilirsin.
)
echo.
pause
