@echo off
REM Project Behavior V2 launcher.
REM Usage: run_v2.bat [p1] [p2] [seed]
setlocal
cd /d "%~dp0"
set P1=%1
set P2=%2
if "%P1%"=="" set P1=runner
if "%P2%"=="" set P2=swordsman
REM numpy is OPTIONAL: it raises the FX budget. The engine runs without it.
python -c "import numpy" 2>nul || echo [pb2] numpy not found - running in pure-python fallback (lower FX budget). Install with: python -m pip install numpy
python -m pb2.app.main %P1% %P2% %3
endlocal
