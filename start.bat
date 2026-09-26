@echo off
REM Double-click (or run in a terminal) to start Nightshift: gateway + dashboard, opens the browser.
cd /d "%~dp0"
python start.py %*
if errorlevel 1 pause
