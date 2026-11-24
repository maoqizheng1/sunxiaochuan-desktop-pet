@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0add_autostart.ps1"
ping -n 3 127.0.0.1 >nul
