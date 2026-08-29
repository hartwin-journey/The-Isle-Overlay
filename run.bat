@echo off
setlocal
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
    py app.py
) else (
    python app.py
)
if errorlevel 1 pause
