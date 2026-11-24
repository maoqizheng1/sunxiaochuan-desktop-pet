@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0close_pet.ps1"
ping -n 2 127.0.0.1 >nul
