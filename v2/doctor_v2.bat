@echo off
REM Run this FIRST if anything misbehaves. Reports interpreter, paths,
REM numpy/PyQt5 availability and whether all six characters load.
setlocal
cd /d "%~dp0"
set "PY=%~dp0..\python.exe"
if not exist "%PY%" set "PY=python"
"%PY%" "%~dp0launch.py" doctor
echo.
pause
endlocal
