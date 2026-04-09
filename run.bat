@echo off
:: NS Joy-Con R Keyboard Mapper - Admin Launcher
:: Run this script as administrator for keyboard simulation to work.

net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Requesting administrator privileges...
    powershell -Command "Start-Process cmd -ArgumentList '/c cd /d \"%~dp0\" && python src/main.py %*' -Verb RunAs"
    exit /b
)

cd /d "%~dp0"
python src/main.py %*
pause
