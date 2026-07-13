@echo off
REM ============================================================================
REM  VX-0057 IO-board QA station - one-click launcher (double-click to run).
REM  Runs the setup preflight (auto-installs deps, checks bench + firmware +
REM  cloud), then starts the program-and-test station dashboard.
REM  Bench COM ports + device keys come from secrets\station.env (copy the
REM  .example first time and fill it in).
REM ============================================================================
setlocal
cd /d "%~dp0tests\tank-monitor"

echo Running setup preflight...
python setup_check.py
if errorlevel 1 (
    echo.
    echo Preflight found BLOCKING issues above. Fix them, then run this again.
    pause
    exit /b 1
)

echo.
echo Starting the station - open http://127.0.0.1:8792 in a browser.
echo Press Ctrl+C in this window to stop.
echo.
python station.py 8792
pause
