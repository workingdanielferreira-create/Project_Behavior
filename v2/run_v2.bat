@echo off
REM ===================================================================
REM  Project Behavior V2 launcher
REM  Usage:  run_v2.bat [p1] [p2] [seed]
REM  e.g.    run_v2.bat mage ronin
REM  Uses the embedded Python at the repo root (same one v1 uses).
REM ===================================================================
setlocal
cd /d "%~dp0"

set "PY=%~dp0..\python.exe"
if not exist "%PY%" set "PY=python"

set P1=%1
set P2=%2
if "%P1%"=="" set P1=runner
if "%P2%"=="" set P2=swordsman

"%PY%" -c "import PyQt5" 2>nul
if errorlevel 1 (
  echo [pb2] PyQt5 not found in the embedded runtime.
  echo [pb2] Install with:  "%PY%" -m pip install PyQt5
  pause
  exit /b 1
)

"%PY%" -c "import numpy" 2>nul
if errorlevel 1 (
  echo [pb2] numpy not installed - running pure-Python fallback ^(lower FX budget^).
  echo [pb2] Optional speedup:  "%PY%" -m pip install numpy
  echo.
)

"%PY%" -m pb2.app.main %P1% %P2% %3
if errorlevel 1 pause
endlocal
