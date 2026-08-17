@echo off
REM Runs the V2 self-checks. No overlay, no Qt required.
setlocal
cd /d "%~dp0"
set "PY=%~dp0..\python.exe"
if not exist "%PY%" set "PY=python"

echo ============ DETERMINISM ============
"%PY%" -m pb2.harness.golden determinism
echo.
echo ============ GOLDEN CHECKSUMS =======
"%PY%" -m pb2.harness.golden verify
echo.
echo ============ SCALE BENCHMARK ========
"%PY%" -m pb2.harness.bench
echo.
pause
endlocal
