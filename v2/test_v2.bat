@echo off
REM V2 self-checks. Headless - no overlay, no Qt required.
setlocal
cd /d "%~dp0"
set "PY=%~dp0..\python.exe"
if not exist "%PY%" set "PY=python"
"%PY%" "%~dp0launch.py" test all
echo.
pause
endlocal
