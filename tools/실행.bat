@echo off
cd /d "%~dp0.."
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" tools\app.py
) else (
  py -3 tools\app.py
)
if errorlevel 1 pause
