@echo off
REM ===================================================================
REM  Project Behavior V2
REM  Usage:  run_v2.bat [p1] [p2] [seed]
REM    e.g.  run_v2.bat mage ronin
REM  Roster: runner swordsman mage ronin jumper new_fighter
REM ===================================================================
setlocal
cd /d "%~dp0"
set "PY=%~dp0..\python.exe"
if not exist "%PY%" set "PY=python"
"%PY%" "%~dp0launch.py" run %1 %2 %3
if errorlevel 1 pause
endlocal
